"""Admin chatbot using Anthropic Tool Calling.

The chatbot reads/writes the same SQLite tables the REST endpoints use,
so any change here is immediately visible in the UI.
"""
import json
import os
from anthropic import Anthropic
from . import database as db
from .prompts import CHAT_SYSTEM_PROMPT

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    return _client


# ---------- Tool definitions sent to Claude ----------
TOOLS = [
    {
        "name": "list_staff",
        "description": "List all staff with their roles and weekly max hours.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "list_shifts",
        "description": "List all shifts for the week with day, time, and required roles.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "list_assignments",
        "description": "Show the current confirmed roster — every assignment with shift and staff details.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "list_pending_applications",
        "description": "List all pending shift bidding applications submitted by staff.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "assign_staff_to_shift",
        "description": "Assign a staff member to a shift. The role must match the staff member's actual role.",
        "input_schema": {
            "type": "object",
            "properties": {
                "shift_id": {"type": "string", "description": "Shift ID such as 'mon-am' or 'sh-1700000000'"},
                "staff_id": {"type": "string", "description": "Staff ID such as 's1'"},
                "role":     {"type": "string", "description": "The role the staff will fill"},
            },
            "required": ["shift_id", "staff_id", "role"],
        },
    },
    {
        "name": "unassign_staff_from_shift",
        "description": "Remove a specific staff member from a specific shift.",
        "input_schema": {
            "type": "object",
            "properties": {
                "shift_id": {"type": "string"},
                "staff_id": {"type": "string"},
            },
            "required": ["shift_id", "staff_id"],
        },
    },
    {
        "name": "approve_application",
        "description": "Approve a pending shift application. This also assigns the staff to the shift.",
        "input_schema": {
            "type": "object",
            "properties": {"application_id": {"type": "integer"}},
            "required": ["application_id"],
        },
    },
    {
        "name": "reject_application",
        "description": "Reject a pending shift application without assigning the staff.",
        "input_schema": {
            "type": "object",
            "properties": {"application_id": {"type": "integer"}},
            "required": ["application_id"],
        },
    },
]


# ---------- Server-side execution of each tool ----------
def _execute_tool(name: str, args: dict) -> dict:
    if name == "list_staff":
        return {"staff": db.list_staff()}

    if name == "list_shifts":
        return {"shifts": db.list_shifts()}

    if name == "list_assignments":
        return {"assignments": db.list_assignments()}

    if name == "list_pending_applications":
        return {"applications": [a for a in db.list_applications() if a["status"] == "pending"]}

    if name == "assign_staff_to_shift":
        staff = next((s for s in db.list_staff() if s["id"] == args["staff_id"]), None)
        if not staff:
            return {"error": f"No staff with id '{args['staff_id']}'"}
        shift = next((s for s in db.list_shifts() if s["id"] == args["shift_id"]), None)
        if not shift:
            return {"error": f"No shift with id '{args['shift_id']}'"}
        if staff["role"] != args["role"]:
            return {"error": f"{staff['name']} is a {staff['role']}, cannot fill {args['role']} slot"}
        db.assign_staff(args["shift_id"], args["staff_id"], args["role"])
        return {"success": True,
                "message": f"Assigned {staff['name']} to {shift['day']} {shift['start']}–{shift['end']} as {args['role']}"}

    if name == "unassign_staff_from_shift":
        ok = db.unassign_staff(args["shift_id"], args["staff_id"])
        if not ok:
            return {"error": "No matching assignment found"}
        return {"success": True, "message": "Assignment removed"}

    if name == "approve_application":
        app = next((a for a in db.list_applications() if a["id"] == args["application_id"]), None)
        if not app:
            return {"error": f"No application with id {args['application_id']}"}
        if app["status"] != "pending":
            return {"error": f"Application already {app['status']}"}
        db.assign_staff(app["shift_id"], app["staff_id"], app["staff_role"])
        db.update_application_status(args["application_id"], "approved")
        return {"success": True,
                "message": f"Approved — {app['staff_name']} now assigned to {app['day']} {app['start']}–{app['end']}"}

    if name == "reject_application":
        db.update_application_status(args["application_id"], "rejected")
        return {"success": True, "message": f"Rejected application {args['application_id']}"}

    return {"error": f"Unknown tool: {name}"}


def _serialize_assistant(blocks) -> list:
    """Convert SDK content-block objects to plain dicts for the conversation log."""
    out = []
    for b in blocks:
        if b.type == "text":
            out.append({"type": "text", "text": b.text})
        elif b.type == "tool_use":
            out.append({"type": "tool_use", "id": b.id, "name": b.name, "input": b.input})
    return out


# ---------- The agentic loop ----------
def chat(messages: list) -> dict:
    """
    Run a tool-calling chat turn. Loops until Claude stops requesting tools.

    Args:
        messages: full conversation, e.g.
                  [{"role": "user", "content": "Take David off Monday morning"}]

    Returns:
        {
          "reply": "<final natural-language response>",
          "tool_calls": [{tool, input, result}, ...],
          "messages": [...updated conversation, ready for next turn...],
        }
    """
    client = _get_client()
    log = []

    for _ in range(10):  # safety bound to prevent runaway tool loops
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=2048,
            system=CHAT_SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
        )

        messages.append({"role": "assistant", "content": _serialize_assistant(response.content)})

        if response.stop_reason != "tool_use":
            reply = "".join(b.text for b in response.content if b.type == "text")
            return {"reply": reply, "tool_calls": log, "messages": messages}

        # Execute every tool call this turn, send all results back together
        tool_results = []
        for b in response.content:
            if b.type == "tool_use":
                result = _execute_tool(b.name, dict(b.input))
                log.append({"tool": b.name, "input": dict(b.input), "result": result})
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": b.id,
                    "content": json.dumps(result),
                })
        messages.append({"role": "user", "content": tool_results})

    return {
        "reply": "Stopped after 10 tool-use rounds — please try a more specific instruction.",
        "tool_calls": log,
        "messages": messages,
    }