"""SQLite access layer.

The whole data model lives here. Search uses SQLite's FTS5 extension, which
ships with Python's bundled SQLite on Windows/macOS/Linux. The queries are
written so the app can move to PostgreSQL later with minimal changes.
"""

from __future__ import annotations

import sqlite3

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT    NOT NULL UNIQUE,
    password_hash TEXT    NOT NULL,
    created_at    TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS items (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    type       TEXT    NOT NULL CHECK (type IN ('note', 'link', 'snippet')),
    title      TEXT    NOT NULL DEFAULT '',
    body       TEXT    NOT NULL DEFAULT '',
    url        TEXT,
    language   TEXT,
    pinned     INTEGER NOT NULL DEFAULT 0,
    archived   INTEGER NOT NULL DEFAULT 0,
    deleted_at TEXT,
    created_at TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_items_type     ON items(type);
CREATE INDEX IF NOT EXISTS idx_items_archived ON items(archived);
CREATE INDEX IF NOT EXISTS idx_items_pinned   ON items(pinned);

CREATE TABLE IF NOT EXISTS tags (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT    NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS item_tags (
    item_id INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
    tag_id  INTEGER NOT NULL REFERENCES tags(id)  ON DELETE CASCADE,
    PRIMARY KEY (item_id, tag_id)
);

CREATE INDEX IF NOT EXISTS idx_item_tags_tag ON item_tags(tag_id);

-- Full-text index. rowid is kept equal to items.id by application code.
-- "unicode61 remove_diacritics" lets "cafe" match "café". Prefix matching is
-- done with a trailing "*" in the query (e.g. dock*  ->  Docker).
CREATE VIRTUAL TABLE IF NOT EXISTS items_fts USING fts5(
    title, body, url, tags,
    tokenize = 'unicode61 remove_diacritics 2'
);
"""

DEFAULT_SETTINGS = {
    "theme": "system",
    "default_item_type": "note",
    "trash_days": "30",
}


def connect() -> sqlite3.Connection:
    """Open a new connection with sensible defaults."""
    config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def init_db() -> None:
    """Create tables (if missing), apply small migrations, seed defaults."""
    conn = connect()
    try:
        conn.executescript(SCHEMA)
        migrate(conn)
        for key, value in DEFAULT_SETTINGS.items():
            conn.execute(
                "INSERT OR IGNORE INTO settings(key, value) VALUES (?, ?)",
                (key, value),
            )
        conn.commit()
    finally:
        conn.close()


def migrate(conn: sqlite3.Connection) -> None:
    """Add columns that newer schema versions expect on older databases.

    Each guard is idempotent, so this is safe to run on every startup.
    """
    cols = {row["name"] for row in conn.execute("PRAGMA table_info(items)")}
    if "deleted_at" not in cols:
        conn.execute("ALTER TABLE items ADD COLUMN deleted_at TEXT")
    # Must come after the ALTER: on an existing database the column may not
    # exist yet when SCHEMA's CREATE IF NOT EXISTS statements are skipped.
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_items_deleted ON items(deleted_at)"
    )


def get_db():
    """FastAPI dependency: one connection per request, committed on success."""
    conn = connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


# --- small data helpers -------------------------------------------------

def user_count(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]


def get_user(conn: sqlite3.Connection, user_id: int) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT id, username, created_at FROM users WHERE id = ?", (user_id,)
    ).fetchone()


def get_user_by_username(conn: sqlite3.Connection, username: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM users WHERE username = ?", (username,)
    ).fetchone()


def create_user(conn: sqlite3.Connection, username: str, password_hash: str) -> int:
    cur = conn.execute(
        "INSERT INTO users(username, password_hash) VALUES (?, ?)",
        (username, password_hash),
    )
    return int(cur.lastrowid)


def set_user_password(conn: sqlite3.Connection, user_id: int, password_hash: str) -> None:
    conn.execute(
        "UPDATE users SET password_hash = ? WHERE id = ?",
        (password_hash, user_id),
    )


def get_setting(conn: sqlite3.Connection, key: str, default: str = "") -> str:
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def set_setting(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        """
        INSERT INTO settings(key, value) VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (key, value),
    )
