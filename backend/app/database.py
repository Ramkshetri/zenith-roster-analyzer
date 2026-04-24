"""Persistence layer with two backends:
   - local dev: SQLite file (no DATABASE_URL set)
   - cloud:     Postgres via psycopg2 (DATABASE_URL=postgresql://...)

Selection is decided once at import time from the DATABASE_URL env var.
The public API (list_staff, add_shift, ...) is identical for both, so
no caller outside this file needs to change.
"""
import json
import os
from contextlib import contextmanager

DATABASE_URL = os.getenv("DATABASE_URL", "")
USE_POSTGRES = DATABASE_URL.startswith(("postgres://", "postgresql://"))

if USE_POSTGRES:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    # Heroku/Vercel/Neon sometimes hand out URLs with the legacy "postgres://"
    # scheme. psycopg2 v2.9+ wants "postgresql://".
    DSN = DATABASE_URL.replace("postgres://", "postgresql://", 1)
else:
    import sqlite3
    DB_PATH = os.path.join(os.path.dirname(__file__), "..", "zenith.db")


# ---------- Schemas (per dialect) ----------
SCHEMA_SQLITE = """
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

SCHEMA_POSTGRES = """
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
    "end"           TEXT NOT NULL,           -- "end" is reserved in PG
    required_roles  JSONB NOT NULL           -- native JSON in Postgres
);

CREATE TABLE IF NOT EXISTS assignments (
    id        SERIAL PRIMARY KEY,
    shift_id  TEXT NOT NULL REFERENCES shifts(id) ON DELETE CASCADE,
    staff_id  TEXT NOT NULL REFERENCES staff(id)  ON DELETE CASCADE,
    role      TEXT NOT NULL,
    UNIQUE(shift_id, staff_id)
);

CREATE TABLE IF NOT EXISTS applications (
    id          SERIAL PRIMARY KEY,
    shift_id    TEXT NOT NULL REFERENCES shifts(id) ON DELETE CASCADE,
    staff_id    TEXT NOT NULL REFERENCES staff(id)  ON DELETE CASCADE,
    status      TEXT NOT NULL DEFAULT 'pending',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(shift_id, staff_id)
);
"""


@contextmanager
def get_db():
    """Yield a connection. Commits on clean exit, always closes."""
    if USE_POSTGRES:
        conn = psycopg2.connect(DSN, cursor_factory=RealDictCursor)
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()
    else:
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
        if USE_POSTGRES:
            conn.cursor().execute(SCHEMA_POSTGRES)
        else:
            conn.executescript(SCHEMA_SQLITE)


# ---------- Tiny helpers: pick the right SQL per driver ----------
def _exec(conn, sql_sqlite, sql_pg, params=()):
    """Execute the dialect-appropriate SQL and return the cursor."""
    cur = conn.cursor()
    cur.execute(sql_pg if USE_POSTGRES else sql_sqlite, params)
    return cur


def _rows(cur):
    """Normalise rows to plain dicts (works for both Row and RealDictRow)."""
    return [dict(r) for r in cur.fetchall()]


# ---------- Staff ----------
def list_staff():
    with get_db() as conn:
        cur = _exec(conn,
            "SELECT * FROM staff ORDER BY name",
            "SELECT * FROM staff ORDER BY name")
        return _rows(cur)


def add_staff(s: dict):
    with get_db() as conn:
        _exec(conn,
            "INSERT OR REPLACE INTO staff (id, name, role, max_hours) VALUES (?, ?, ?, ?)",
            """INSERT INTO staff (id, name, role, max_hours) VALUES (%s, %s, %s, %s)
               ON CONFLICT (id) DO UPDATE
                 SET name = EXCLUDED.name,
                     role = EXCLUDED.role,
                     max_hours = EXCLUDED.max_hours""",
            (s["id"], s["name"], s["role"], s["max_hours"]))


def remove_staff(staff_id: str):
    with get_db() as conn:
        _exec(conn,
            "DELETE FROM staff WHERE id = ?",
            "DELETE FROM staff WHERE id = %s",
            (staff_id,))


# ---------- Shifts ----------
def list_shifts():
    with get_db() as conn:
        cur = _exec(conn,
            "SELECT * FROM shifts ORDER BY day, start",
            "SELECT * FROM shifts ORDER BY day, start")
        rows = _rows(cur)
    # Postgres JSONB comes back as a dict; SQLite gives us a string.
    for r in rows:
        if isinstance(r.get("required_roles"), str):
            r["required_roles"] = json.loads(r["required_roles"])
    return rows


def add_shift(sh: dict):
    rr = sh["required_roles"]
    with get_db() as conn:
        _exec(conn,
            "INSERT OR REPLACE INTO shifts (id, day, start, end, required_roles) "
            "VALUES (?, ?, ?, ?, ?)",
            """INSERT INTO shifts (id, day, start, "end", required_roles)
               VALUES (%s, %s, %s, %s, %s)
               ON CONFLICT (id) DO UPDATE
                 SET day = EXCLUDED.day,
                     start = EXCLUDED.start,
                     "end" = EXCLUDED."end",
                     required_roles = EXCLUDED.required_roles""",
            (sh["id"], sh["day"], sh["start"], sh["end"], json.dumps(rr)))


def remove_shift(shift_id: str):
    with get_db() as conn:
        _exec(conn,
            "DELETE FROM shifts WHERE id = ?",
            "DELETE FROM shifts WHERE id = %s",
            (shift_id,))


# ---------- Assignments ----------
def list_assignments():
    """Joined view: assignment + staff + shift details."""
    with get_db() as conn:
        cur = _exec(conn,
            """SELECT a.id, a.shift_id, a.staff_id, a.role,
                      s.name AS staff_name, s.role AS staff_role,
                      sh.day, sh.start, sh.end
                 FROM assignments a
                 JOIN staff  s  ON a.staff_id = s.id
                 JOIN shifts sh ON a.shift_id = sh.id
                ORDER BY sh.day, sh.start""",
            """SELECT a.id, a.shift_id, a.staff_id, a.role,
                      s.name AS staff_name, s.role AS staff_role,
                      sh.day, sh.start, sh."end" AS "end"
                 FROM assignments a
                 JOIN staff  s  ON a.staff_id = s.id
                 JOIN shifts sh ON a.shift_id = sh.id
                ORDER BY sh.day, sh.start""")
        return _rows(cur)


def assign_staff(shift_id: str, staff_id: str, role: str):
    with get_db() as conn:
        _exec(conn,
            "INSERT OR REPLACE INTO assignments (shift_id, staff_id, role) "
            "VALUES (?, ?, ?)",
            """INSERT INTO assignments (shift_id, staff_id, role)
               VALUES (%s, %s, %s)
               ON CONFLICT (shift_id, staff_id) DO UPDATE
                 SET role = EXCLUDED.role""",
            (shift_id, staff_id, role))


def unassign_staff(shift_id: str, staff_id: str) -> bool:
    with get_db() as conn:
        cur = _exec(conn,
            "DELETE FROM assignments WHERE shift_id = ? AND staff_id = ?",
            "DELETE FROM assignments WHERE shift_id = %s AND staff_id = %s",
            (shift_id, staff_id))
        return cur.rowcount > 0


def replace_all_assignments(assignments: list):
    """Wipe and rewrite. Used after a fresh AI-generated roster."""
    with get_db() as conn:
        _exec(conn, "DELETE FROM assignments", "DELETE FROM assignments")
        for a in assignments:
            _exec(conn,
                "INSERT OR IGNORE INTO assignments (shift_id, staff_id, role) "
                "VALUES (?, ?, ?)",
                """INSERT INTO assignments (shift_id, staff_id, role)
                   VALUES (%s, %s, %s)
                   ON CONFLICT (shift_id, staff_id) DO NOTHING""",
                (a["shift_id"], a["staff_id"], a["role"]))


# ---------- Applications (shift bidding) ----------
def list_applications():
    with get_db() as conn:
        cur = _exec(conn,
            """SELECT a.id, a.shift_id, a.staff_id, a.status, a.created_at,
                      s.name AS staff_name, s.role AS staff_role,
                      sh.day, sh.start, sh.end
                 FROM applications a
                 JOIN staff  s  ON a.staff_id = s.id
                 JOIN shifts sh ON a.shift_id = sh.id
                ORDER BY a.created_at DESC""",
            """SELECT a.id, a.shift_id, a.staff_id, a.status, a.created_at,
                      s.name AS staff_name, s.role AS staff_role,
                      sh.day, sh.start, sh."end" AS "end"
                 FROM applications a
                 JOIN staff  s  ON a.staff_id = s.id
                 JOIN shifts sh ON a.shift_id = sh.id
                ORDER BY a.created_at DESC""")
        return _rows(cur)


def add_application(shift_id: str, staff_id: str):
    with get_db() as conn:
        _exec(conn,
            "INSERT OR IGNORE INTO applications (shift_id, staff_id, status) "
            "VALUES (?, ?, 'pending')",
            """INSERT INTO applications (shift_id, staff_id, status)
               VALUES (%s, %s, 'pending')
               ON CONFLICT (shift_id, staff_id) DO NOTHING""",
            (shift_id, staff_id))


def update_application_status(application_id: int, status: str):
    with get_db() as conn:
        _exec(conn,
            "UPDATE applications SET status = ? WHERE id = ?",
            "UPDATE applications SET status = %s WHERE id = %s",
            (status, application_id))
