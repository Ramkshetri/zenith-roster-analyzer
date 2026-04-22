import os
import json
from anthropic import Anthropic, APIError
from .prompts import ROSTERING_SYSTEM_PROMPT

_client = None


def _get_client() -> Anthropic:
    global _client
    if _client is None:
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY not set in environment")
        _client = Anthropic(api_key=api_key)
    return _client


def generate_roster(payload: dict) -> dict:
    """Send validated payload to Claude and return parsed JSON roster."""
    client = _get_client()
    user_message = json.dumps(payload, indent=2)

    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=4096,
            temperature=0.2,                      # Low temp = more deterministic, rule-following
            system=ROSTERING_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )
    except APIError as e:
        raise RuntimeError(f"Claude API error: {e}") from e

    raw = response.content[0].text.strip()

    # Defensive: strip code fences if the model wraps output anyway.
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.lower().startswith("json"):
            raw = raw[4:].strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"Claude returned invalid JSON: {e}. First 500 chars: {raw[:500]}"
        ) from e