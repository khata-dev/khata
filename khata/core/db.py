"""SQLite connection + schema init."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from khata.config import Config

SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def connect(cfg: Config | None = None) -> sqlite3.Connection:
    cfg = cfg or Config.load()
    conn = sqlite3.connect(cfg.db_path, isolation_level=None)  # autocommit off via BEGIN
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    with open(SCHEMA_PATH) as f:
        conn.executescript(f.read())


def user_id_for(conn: sqlite3.Connection, username: str) -> int:
    row = conn.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
    if row:
        return row["id"]
    cur = conn.execute("INSERT INTO users (username) VALUES (?)", (username,))
    return cur.lastrowid
