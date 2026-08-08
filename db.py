"""
db.py
-----
Thin data-access layer over SQLite. Every query in this project goes
through get_db(), query(), query_one(), or execute() -- all of which use
parameterized placeholders (?), never string-formatted SQL. This is what
actually prevents SQL injection (see Security features): user input is
always passed as a bound parameter, never concatenated into the query text.

Example of the pattern used everywhere in this project:
    query_one("SELECT * FROM users WHERE email = ?", (email,))   # SAFE
    query_one(f"SELECT * FROM users WHERE email = '{email}'")     # NEVER DO THIS
"""

from __future__ import annotations

import sqlite3
import os
from flask import g, current_app


def get_db() -> sqlite3.Connection:
    """
    Returns a SQLite connection stored on Flask's `g` (request-scoped
    context), so the same connection is reused for the duration of one
    request instead of opening a new one per query.
    """
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE_PATH"])
        g.db.row_factory = sqlite3.Row  # rows behave like dicts (row["email"])
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(e=None) -> None:
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db(app) -> None:
    """Creates all tables from schema.sql if they don't already exist."""
    db_path = app.config["DATABASE_PATH"]
    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    schema_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "schema.sql")
    with sqlite3.connect(db_path) as conn:
        with open(schema_path, "r") as f:
            conn.executescript(f.read())
    app.teardown_appcontext(close_db)


def query(sql: str, params: tuple = ()) -> list[sqlite3.Row]:
    """Run a SELECT and return all matching rows."""
    return get_db().execute(sql, params).fetchall()


def query_one(sql: str, params: tuple = ()) -> sqlite3.Row | None:
    """Run a SELECT expected to return zero or one row."""
    return get_db().execute(sql, params).fetchone()


def execute(sql: str, params: tuple = ()) -> int:
    """
    Run an INSERT/UPDATE/DELETE, commit it, and return the new row id
    (for INSERTs) via cursor.lastrowid.
    """
    db = get_db()
    cursor = db.execute(sql, params)
    db.commit()
    return cursor.lastrowid
