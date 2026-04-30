"""
core/history.py  --  SQLite session history database.
"""

import sqlite3
import json
import os
from datetime import datetime


def _db_path():
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "data", "history.db")


def init_db():
    conn = sqlite3.connect(_db_path())
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at      TEXT,
            ended_at        TEXT,
            duration_m      REAL,
            categories      TEXT,
            total_phases    INTEGER,
            done_phases     INTEGER,
            status          TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS phase_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id  INTEGER,
            phase_name  TEXT,
            category    TEXT,
            status      TEXT,
            duration_s  REAL,
            FOREIGN KEY (session_id) REFERENCES sessions(id)
        )
    """)
    conn.commit()
    conn.close()


def start_session(categories, total_phases):
    init_db()
    conn = sqlite3.connect(_db_path())
    c = conn.cursor()
    c.execute("""
        INSERT INTO sessions (started_at, categories, total_phases, done_phases, status)
        VALUES (?, ?, ?, 0, 'running')
    """, (datetime.now().isoformat(), json.dumps(categories), total_phases))
    session_id = c.lastrowid
    conn.commit()
    conn.close()
    return session_id


def end_session(session_id, done_phases, status):
    conn = sqlite3.connect(_db_path())
    c = conn.cursor()
    c.execute("SELECT started_at FROM sessions WHERE id=?", (session_id,))
    row = c.fetchone()
    duration_m = 0.0
    if row:
        started = datetime.fromisoformat(row[0])
        duration_m = (datetime.now() - started).total_seconds() / 60
    c.execute("""
        UPDATE sessions
        SET ended_at=?, duration_m=?, done_phases=?, status=?
        WHERE id=?
    """, (datetime.now().isoformat(), round(duration_m, 2), done_phases, status, session_id))
    conn.commit()
    conn.close()


def log_phase(session_id, phase_name, category, status, duration_s):
    conn = sqlite3.connect(_db_path())
    c = conn.cursor()
    c.execute("""
        INSERT INTO phase_log (session_id, phase_name, category, status, duration_s)
        VALUES (?, ?, ?, ?, ?)
    """, (session_id, phase_name, category, status, round(duration_s, 2)))
    conn.commit()
    conn.close()


def get_sessions(limit=100, offset=0):
    init_db()
    conn = sqlite3.connect(_db_path())
    c = conn.cursor()
    c.execute("""
        SELECT id, started_at, ended_at, duration_m, categories,
               total_phases, done_phases, status
        FROM sessions
        ORDER BY id DESC
        LIMIT ? OFFSET ?
    """, (limit, offset))
    rows = c.fetchall()
    conn.close()
    result = []
    for r in rows:
        result.append({
            "id":           r[0],
            "started_at":   r[1],
            "ended_at":     r[2],
            "duration_m":   r[3],
            "categories":   json.loads(r[4]) if r[4] else [],
            "total_phases": r[5],
            "done_phases":  r[6],
            "status":       r[7],
        })
    return result


def get_phase_log(session_id):
    conn = sqlite3.connect(_db_path())
    c = conn.cursor()
    c.execute("""
        SELECT phase_name, category, status, duration_s
        FROM phase_log WHERE session_id=? ORDER BY id
    """, (session_id,))
    rows = c.fetchall()
    conn.close()
    return [{"phase": r[0], "category": r[1], "status": r[2], "duration_s": r[3]}
            for r in rows]


def get_stats():
    init_db()
    conn = sqlite3.connect(_db_path())
    c = conn.cursor()
    c.execute("SELECT COUNT(*), COALESCE(SUM(duration_m),0) FROM sessions WHERE status != 'running'")
    total_sessions, total_minutes = c.fetchone()
    c.execute("SELECT COUNT(*) FROM sessions WHERE status='completed'")
    completed = c.fetchone()[0]
    conn.close()
    return {
        "total_sessions": total_sessions,
        "completed":      completed,
        "total_hours":    round(total_minutes / 60, 1),
    }


def clear_history():
    conn = sqlite3.connect(_db_path())
    c = conn.cursor()
    c.execute("DELETE FROM phase_log")
    c.execute("DELETE FROM sessions")
    conn.commit()
    conn.close()
