"""SQLite persistence layer. Stdlib only — no ORM."""
import json
import os
import sqlite3
from contextlib import contextmanager

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "zenith.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS staff (
    id         TEXT PRIMARY KEY,
    name       TEXT NOT NULL,
    role       TEXT NOT NULL,
    max_hours  INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS shifts (
    id              TEXT PRIMARY KEY,
    day             TEXT NOT NULL,
    start           TEXT NOT NULL,
    end             TEXT NOT NULL,
    required_roles  TEXT NOT NULL  -- JSON {role: count}
);

CREATE TABLE IF NOT EXISTS assignments (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    shift_id  TEXT NOT NULL,
    staff_id  TEXT NOT NULL,
    role      TEXT NOT NULL,
    UNIQUE(shift_id, staff_id),
    FOREIGN KEY(shift_id) REFERENCES shifts(id) ON DELETE CASCADE,
    FOREIGN KEY(staff_id) REFERENCES staff(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS applications (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    shift_id    TEXT NOT NULL,
    staff_id    TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'pending',  -- pending|approved|rejected
    created_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(shift_id, staff_id),
    FOREIGN KEY(shift_id) REFERENCES shifts(id) ON DELETE CASCADE,
    FOREIGN KEY(staff_id) REFERENCES staff(id) ON DELETE CASCADE
);
"""


@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_db() as conn:
        conn.executescript(SCHEMA)


# ---------- Staff ----------
def list_staff():
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM staff ORDER BY name").fetchall()
    return [dict(r) for r in rows]


def add_staff(s: dict):
    with get_db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO staff (id, name, role, max_hours) VALUES (?, ?, ?, ?)",
            (s["id"], s["name"], s["role"], s["max_hours"]),
        )


def remove_staff(staff_id: str):
    with get_db() as conn:
        conn.execute("DELETE FROM staff WHERE id = ?", (staff_id,))


# ---------- Shifts ----------
def list_shifts():
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM shifts ORDER BY day, start").fetchall()
    return [{**dict(r), "required_roles": json.loads(r["required_roles"])} for r in rows]


def add_shift(sh: dict):
    with get_db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO shifts (id, day, start, end, required_roles) VALUES (?, ?, ?, ?, ?)",
            (sh["id"], sh["day"], sh["start"], sh["end"], json.dumps(sh["required_roles"])),
        )


def remove_shift(shift_id: str):
    with get_db() as conn:
        conn.execute("DELETE FROM shifts WHERE id = ?", (shift_id,))


# ---------- Assignments ----------
def list_assignments():
    """Joined view: assignment + staff + shift details."""
    with get_db() as conn:
        rows = conn.execute("""
            SELECT a.id, a.shift_id, a.staff_id, a.role,
                   s.name AS staff_name, s.role AS staff_role,
                   sh.day, sh.start, sh.end
              FROM assignments a
              JOIN staff  s  ON a.staff_id = s.id
              JOIN shifts sh ON a.shift_id = sh.id
             ORDER BY sh.day, sh.start
        """).fetchall()
    return [dict(r) for r in rows]


def assign_staff(shift_id: str, staff_id: str, role: str):
    with get_db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO assignments (shift_id, staff_id, role) VALUES (?, ?, ?)",
            (shift_id, staff_id, role),
        )


def unassign_staff(shift_id: str, staff_id: str) -> bool:
    with get_db() as conn:
        cur = conn.execute(
            "DELETE FROM assignments WHERE shift_id = ? AND staff_id = ?",
            (shift_id, staff_id),
        )
        return cur.rowcount > 0


def replace_all_assignments(assignments: list):
    """Wipe and rewrite. Used after a fresh AI-generated roster."""
    with get_db() as conn:
        conn.execute("DELETE FROM assignments")
        for a in assignments:
            conn.execute(
                "INSERT OR IGNORE INTO assignments (shift_id, staff_id, role) VALUES (?, ?, ?)",
                (a["shift_id"], a["staff_id"], a["role"]),
            )


# ---------- Applications (shift bidding) ----------
def list_applications():
    with get_db() as conn:
        rows = conn.execute("""
            SELECT a.id, a.shift_id, a.staff_id, a.status, a.created_at,
                   s.name AS staff_name, s.role AS staff_role,
                   sh.day, sh.start, sh.end
              FROM applications a
              JOIN staff  s  ON a.staff_id = s.id
              JOIN shifts sh ON a.shift_id = sh.id
             ORDER BY a.created_at DESC
        """).fetchall()
    return [dict(r) for r in rows]


def add_application(shift_id: str, staff_id: str):
    with get_db() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO applications (shift_id, staff_id, status) VALUES (?, ?, 'pending')",
            (shift_id, staff_id),
        )


def update_application_status(application_id: int, status: str):
    with get_db() as conn:
        conn.execute(
            "UPDATE applications SET status = ? WHERE id = ?",
            (status, application_id),
        )