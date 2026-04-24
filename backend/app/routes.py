from flask import Blueprint, request, jsonify
from anthropic import Anthropic
from pydantic import ValidationError
import os, json, uuid

from .schemas import RosterRequest, StaffMember, Shift
from .prompts import ROSTERING_SYSTEM_PROMPT, CHAT_SYSTEM_PROMPT
from . import database as db
from .chat_service import chat as chat_with_tools

api_bp = Blueprint("api", __name__)


@api_bp.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


@api_bp.route("/generate-roster", methods=["POST"])
def generate_roster_endpoint():
    try:
        payload = RosterRequest(**request.get_json())
    except ValidationError as e:
        return jsonify({"error": e.errors()}), 400

    for s in payload.staff:
        d = s.model_dump()
        d.setdefault("id", "stf_" + uuid.uuid4().hex[:8])
        db.add_staff(d)
    for sh in payload.shifts:
        d = sh.model_dump()
        d.setdefault("id", "sft_" + uuid.uuid4().hex[:8])
        if "required_role" in d and "required_roles" not in d:
            d["required_roles"] = {d.pop("required_role"): 1}
        d.setdefault("required_roles", {})
        db.add_shift(d)

    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    user_msg = json.dumps(payload.model_dump(), indent=2)

    resp = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=8192,                       # was 2048 — too small for 7 shifts
        system=ROSTERING_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_msg}],
    )
    text = resp.content[0].text
    print("---- CLAUDE RAW RESPONSE ----")
    print(text)
    print("---- END ----")

    # Defensive parse: strip ```json fences, then try to locate the JSON object
    cleaned = text.strip()
    if cleaned.startswith("```"):
        nl = cleaned.find("\n")
        if nl != -1:
            cleaned = cleaned[nl + 1:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()
    if not cleaned.startswith("{"):
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1:
            cleaned = cleaned[start:end + 1]

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        return jsonify({"error": "Claude did not return valid JSON", "raw": text}), 500

    # Normalize Claude's response: it sometimes returns a nested "roster"
    # shape ({roster:[{shift_id, assignments:[{staff_id, role}]}]}) and
    # sometimes a flat "assignments" shape. We want flat.
    assignments = []
    if isinstance(data.get("assignments"), list) and data["assignments"]:
        assignments = data["assignments"]
    elif isinstance(data.get("roster"), list):
        for shift in data["roster"]:
            sid = shift.get("shift_id")
            for a in shift.get("assignments", []):
                assignments.append({
                    "shift_id": sid,
                    "staff_id": a.get("staff_id"),
                    "role": a.get("role"),
                })

    # Drop any rows referencing staff/shift IDs that don't exist in DB
    valid_staff = {s["id"] for s in db.list_staff()}
    valid_shifts = {sh["id"] for sh in db.list_shifts()}
    assignments = [
        a for a in assignments
        if a["staff_id"] in valid_staff and a["shift_id"] in valid_shifts
    ]

    db.replace_all_assignments(assignments)
    data["assignments"] = assignments  # send flat shape back to frontend
    return jsonify(data)

@api_bp.route("/state", methods=["GET"])
def get_state():
    return jsonify({
        "staff": db.list_staff(),
        "shifts": db.list_shifts(),
        "assignments": db.list_assignments(),
        "applications": db.list_applications(),
    })


@api_bp.route("/staff", methods=["POST"])
def post_staff():
    body = request.get_json() or {}
    name = (body.get("name") or "").strip()
    role = (body.get("role") or "").strip()
    max_hours = body.get("max_hours")
    if not name or not role or max_hours is None:
        return jsonify({"error": "name, role, max_hours required"}), 400
    db.add_staff({
        "id": "stf_" + uuid.uuid4().hex[:8],
        "name": name,
        "role": role,
        "max_hours": int(max_hours),
    })
    return jsonify({"ok": True})


@api_bp.route("/staff/<staff_id>", methods=["DELETE"])
def delete_staff(staff_id):
    db.remove_staff(staff_id)
    return jsonify({"ok": True})


@api_bp.route("/shifts", methods=["POST"])
def post_shift():
    body = request.get_json() or {}
    day = body.get("day")
    start = body.get("start")
    end = body.get("end")
    required_roles = body.get("required_roles") or {}
    if not day or not start or not end:
        return jsonify({"error": "day, start, end required"}), 400
    db.add_shift({
        "id": "sft_" + uuid.uuid4().hex[:8],
        "day": day,
        "start": start,
        "end": end,
        "required_roles": required_roles,
    })
    return jsonify({"ok": True})


@api_bp.route("/shifts/<shift_id>", methods=["DELETE"])
def delete_shift(shift_id):
    db.remove_shift(shift_id)
    return jsonify({"ok": True})


@api_bp.route("/applications", methods=["POST"])
def post_application():
    body = request.get_json() or {}
    staff_id = body.get("staff_id")
    shift_id = body.get("shift_id")
    if staff_id is None or shift_id is None:
        return jsonify({"error": "staff_id and shift_id required"}), 400
    db.add_application(str(shift_id), str(staff_id))
    return jsonify({"ok": True})


@api_bp.route("/applications/<int:app_id>", methods=["PATCH"])
def patch_application(app_id):
    body = request.get_json() or {}
    status = body.get("status")
    if status not in ("approved", "rejected"):
        return jsonify({"error": "status must be 'approved' or 'rejected'"}), 400
    db.update_application_status(app_id, status)
    return jsonify({"ok": True})


@api_bp.route("/chat", methods=["POST"])
def chat_endpoint():
    body = request.get_json() or {}
    messages = body.get("messages", [])
    try:
        reply = chat_with_tools(messages)
        return jsonify({"reply": reply})
    except Exception as e:
        return jsonify({"error": f"Chat error: {e}"}), 500