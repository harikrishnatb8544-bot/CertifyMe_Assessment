import sqlite3
from pathlib import Path

from flask import current_app, g

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS admins (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_admins_created_at ON admins (created_at);

CREATE TABLE IF NOT EXISTS opportunities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    admin_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    duration TEXT NOT NULL,
    start_date TEXT NOT NULL,
    description TEXT NOT NULL,
    skills TEXT NOT NULL,
    future_opportunities TEXT NOT NULL,
    max_applicants INTEGER,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (admin_id) REFERENCES admins (id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_opportunities_admin_id
ON opportunities (admin_id, created_at DESC);

CREATE TABLE IF NOT EXISTS password_reset_tokens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    admin_id INTEGER NOT NULL,
    token_hash TEXT NOT NULL UNIQUE,
    expires_at TEXT NOT NULL,
    used_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (admin_id) REFERENCES admins (id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_password_reset_tokens_admin_id
ON password_reset_tokens (admin_id, created_at DESC);
"""


def _resolve_db_path():
    db_path = Path(current_app.config["DATABASE_PATH"])
    if not db_path.is_absolute():
        db_path = Path(current_app.root_path).parent / db_path
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return db_path


def get_db():
    if "db" not in g:
        db_path = _resolve_db_path()
        connection = sqlite3.connect(
            db_path,
            timeout=30,
            isolation_level=None,
            check_same_thread=False,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=NORMAL")
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=30000")
        g.db = connection
    return g.db


def init_db():
    db = get_db()
    db.executescript(SCHEMA_SQL)


def init_app(app):
    with app.app_context():
        init_db()


def close_db(_error=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def execute_write(query, params=()):
    db = get_db()
    cursor = db.execute("BEGIN IMMEDIATE")
    try:
        db.execute(query, params)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        cursor.close()


def execute_insert(query, params=()):
    db = get_db()
    transaction = db.execute("BEGIN IMMEDIATE")
    try:
        cursor = db.execute(query, params)
        row_id = cursor.lastrowid
        db.commit()
        return row_id
    except Exception:
        db.rollback()
        raise
    finally:
        transaction.close()


def fetch_one(query, params=()):
    db = get_db()
    return db.execute(query, params).fetchone()


def fetch_all(query, params=()):
    db = get_db()
    return db.execute(query, params).fetchall()
