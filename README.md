# Zenith Roster Analyzer

AI-powered staff rostering and compliance tool for hospitality operations. Venue managers input their staff list (with roles and weekly hour limits) and the week's required shifts; the application uses Anthropic's Claude API to generate an optimised roster that respects overtime caps, role-coverage rules, staff availability, and a hard "at least one Manager on duty at all times" constraint.

## Tech Stack

- **Frontend:** Next.js (App Router) + Tailwind CSS
- **Backend:** Python + Flask
- **AI:** Anthropic Claude (`claude-haiku-4-5`) via the official Python SDK
- **Validation:** Pydantic for request schemas

## Architecture
The Claude system prompt is treated as code: versioned in `backend/app/prompts.py`, separated from the HTTP layer so it can be iterated on independently.

## Running locally

### Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
echo "ANTHROPIC_API_KEY=sk-ant-..." > .env
python run.py    # runs on http://localhost:5001
```

### Frontend

```bash
cd frontend
npm install
npm run dev      # runs on http://localhost:3000
```

## API

`POST /api/generate-roster`

Request body:

```json
{
  "staff": [
    {"id": "s1", "name": "Anna", "role": "Manager", "max_hours": 40}
  ],
  "shifts": [
    {"id": "sh1", "day": "Mon", "start": "08:00", "end": "16:00",
     "required_roles": {"Manager": 1}}
  ]
}
```

Returns a structured roster with `assignments`, `staff_summary`, `uncovered_slots`, `manager_gaps`, and `warnings`.

## Why this design

- **Pydantic validation before Claude** — fail fast on malformed input, never burn API credits on junk.
- **Separated prompt file** — prompts are code; reviewable, diffable, testable.
- **Low temperature (0.2)** — rostering is a constraints problem, not a creative one; consistency matters more than variety.
- **Strict JSON output schema in the system prompt** — defensive code-fence stripping in the parser as a backstop for any model deviation.