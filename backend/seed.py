"""Seed the database with 20 realistic hospitality staff and a week of shifts.

Idempotent: if staff already exist, it exits without touching anything.
Works against SQLite (local) or Postgres (Neon) — picks the backend from
DATABASE_URL just like the app does.

Usage:
    # Local SQLite:
    cd backend && python seed.py

    # Against Neon (from your machine):
    cd backend
    DATABASE_URL="postgresql://...neon.tech/neondb?sslmode=require" python seed.py
"""
import uuid
from app.database import init_db, list_staff, add_staff, add_shift, list_shifts


# ---- 20 staff reflecting a real hospitality mix ----
# role mix: 2 Managers, 3 Chefs, 2 Bartenders, 4 Waiters, 3 Receptionists,
#           3 Housekeeping, 1 Security, 1 Concierge, 1 Porter
# hours mix: full-time (38), part-time (20–25), casual (15)
STAFF = [
    # Managers
    ("Amelia Chen",        "Manager",       38),
    ("Liam O'Connor",      "Manager",       38),
    # Chefs
    ("Marcus Nakamura",    "Chef",          38),
    ("Isabella Rossi",     "Chef",          38),
    ("Thomas Schmidt",     "Chef",          25),
    # Bartenders
    ("Jamal Okafor",       "Bartender",     25),
    ("Ben Kowalski",       "Bartender",     20),
    # Waiters
    ("Sophie Tran",        "Waiter",        20),
    ("Diego Alvarez",      "Waiter",        25),
    ("Hana Kim",           "Waiter",        15),
    ("Ravi Desai",         "Waiter",        20),
    # Receptionists
    ("Fatima Al-Rashid",   "Receptionist",  38),
    ("Zara Ahmed",         "Receptionist",  25),
    ("Chloe Dubois",       "Receptionist",  20),
    # Housekeeping
    ("Mei Wong",           "Housekeeping",  38),
    ("Arjun Patel",        "Housekeeping",  25),
    ("Kenji Tanaka",       "Housekeeping",  15),
    # Support roles
    ("Oliver Walsh",       "Security",      38),
    ("Priya Sharma",       "Concierge",     25),
    ("Noah Williams",      "Porter",        20),
]


# ---- A realistic week of shifts for a mid-size hotel ----
# Two shift bands: Morning (07:00–15:00) and Evening (15:00–23:00)
# Each day needs coverage across the core roles.
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

MORNING_REQUIREMENTS = {
    "Manager": 1,
    "Receptionist": 1,
    "Chef": 1,
    "Housekeeping": 2,
    "Waiter": 1,
}

EVENING_REQUIREMENTS = {
    "Manager": 1,
    "Receptionist": 1,
    "Chef": 1,
    "Bartender": 1,
    "Waiter": 2,
    "Security": 1,
}

# Weekends need a bit more bar + waiter coverage
WEEKEND_EVENING_REQUIREMENTS = {
    **EVENING_REQUIREMENTS,
    "Bartender": 2,
    "Waiter": 3,
}


def _short_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def seed():
    print("Initialising schema ...")
    init_db()

    existing_names = {s["name"] for s in list_staff()}
    seed_names = {name for name, _, _ in STAFF}
    if seed_names.issubset(existing_names):
        print("Seed staff already present — skipping.")
        return

    print(f"Inserting {len(STAFF)} staff (existing rows are left alone) ...")
    for name, role, max_hours in STAFF:
        add_staff({
            "id": _short_id("stf"),
            "name": name,
            "role": role,
            "max_hours": max_hours,
        })

    print("Inserting weekly shift template (morning + evening, Mon–Sun) ...")
    existing_shifts = {(s["day"], s["start"]) for s in list_shifts()}
    count = 0
    for day in DAYS:
        # Morning
        if (day, "07:00") not in existing_shifts:
            add_shift({
                "id": _short_id("sft"),
                "day": day,
                "start": "07:00",
                "end": "15:00",
                "required_roles": MORNING_REQUIREMENTS,
            })
            count += 1
        # Evening
        if (day, "15:00") not in existing_shifts:
            reqs = WEEKEND_EVENING_REQUIREMENTS if day in ("Fri", "Sat") else EVENING_REQUIREMENTS
            add_shift({
                "id": _short_id("sft"),
                "day": day,
                "start": "15:00",
                "end": "23:00",
                "required_roles": reqs,
            })
            count += 1

    print(f"Done. Inserted {len(STAFF)} staff and {count} shifts.")
    print("Generate a roster from the UI to fill in assignments.")


if __name__ == "__main__":
    seed()
