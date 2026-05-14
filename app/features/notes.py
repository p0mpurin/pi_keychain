"""SQLite-backed notes / todos."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any


SCHEMA = """
CREATE TABLE IF NOT EXISTS notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    body TEXT NOT NULL,
    done INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute(SCHEMA)
    conn.commit()
    return conn


def list_notes(conn: sqlite3.Connection, include_done: bool = False) -> list[dict[str, Any]]:
    if include_done:
        rows = conn.execute(
            "SELECT id, body, done, created_at FROM notes ORDER BY done ASC, id DESC"
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT id, body, done, created_at FROM notes WHERE done = 0 ORDER BY id DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def add_note(conn: sqlite3.Connection, body: str) -> int:
    cur = conn.execute(
        "INSERT INTO notes (body, done) VALUES (?, 0)",
        (body.strip(),),
    )
    conn.commit()
    return int(cur.lastrowid)


def toggle_note(conn: sqlite3.Connection, note_id: int) -> bool:
    row = conn.execute("SELECT done FROM notes WHERE id = ?", (note_id,)).fetchone()
    if row is None:
        return False
    new_done = 0 if row["done"] else 1
    conn.execute("UPDATE notes SET done = ? WHERE id = ?", (new_done, note_id))
    conn.commit()
    return True


def delete_note(conn: sqlite3.Connection, note_id: int) -> bool:
    cur = conn.execute("DELETE FROM notes WHERE id = ?", (note_id,))
    conn.commit()
    return cur.rowcount > 0


def lines_for_display(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        "SELECT body FROM notes WHERE done = 0 ORDER BY id ASC"
    ).fetchall()
    return [f"• {r['body']}" for r in rows]
