from flask import Blueprint, request, jsonify
from pydantic import ValidationError
from .schemas import RosterRequest
from .claude_service import generate_roster

api_bp = Blueprint("api", __name__)


@api_bp.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


@api_bp.route("/generate-roster", methods=["POST"])
def generate_roster_endpoint():
    # 1. Parse JSON body
    try:
        body = request.get_json(force=True)
    except Exception:
        return jsonify({"error": "Invalid JSON in request body"}), 400

    # 2. Validate shape with Pydantic — fail fast, never bill the API for junk input
    try:
        validated = RosterRequest(**body)
    except ValidationError as e:
        return jsonify({"error": "Validation failed", "details": e.errors()}), 422

    # 3. Call Claude
    try:
        roster = generate_roster(validated.model_dump())
    except ValueError as e:
        # Bad output from the model
        return jsonify({"error": str(e)}), 502
    except RuntimeError as e:
        # Config or upstream API error
        return jsonify({"error": str(e)}), 500

    return jsonify(roster), 200