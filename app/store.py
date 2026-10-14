"""Data access for items and tags.

Kept separate from db.py (which owns the connection) so the query logic for
the knowledge base lives in one readable place. All values are passed as
parameters, never string-formatted into SQL except the ORDER BY, which is
chosen from a fixed dictionary.
"""

import re
import sqlite3
from typing import Iterable, Optional

TAG_SPLIT_RE = re.compile(r"[,\n]")
MAX_TAG_LENGTH = 50

SEARCH_SORTS = {
    "newest": "i.created_at DESC, i.id DESC",
    "edited": "i.updated_at DESC, i.id DESC",
    "title": "LOWER(i.title) ASC, i.id DESC",
}

# FTS5 treats these words as operators even when lowercase. We quote them so
# searching for "and" returns documents instead of a syntax error.
_FTS_RESERVED = {"and", "or", "not", "near"}
_TOKEN_RE = re.compile(r"\w+", re.UNICODE)
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$")


def build_fts_query(raw) -> Optional[str]:
    """Turn free text into a safe FTS5 MATCH expression.

    Every word becomes a prefix search ("dock" -> "dock*" matches Docker),
    punctuation is dropped, and reserved words are quoted so special
    characters in the query can never produce a syntax error.
    """
    parts: list[str] = []
    for token in _TOKEN_RE.findall((raw or "").lower()):
        token = token.strip("_")
        if not token:
            continue
        parts.append(f'"{token}"' if token in _FTS_RESERVED else token + "*")
    return " ".join(parts) if parts else None


# --- tags ---------------------------------------------------------------

def normalize_tags(raw) -> list[str]:
    """Turn a list or "a, b, b" string into clean, unique, lowercase tags."""
    if isinstance(raw, str):
        parts: Iterable[str] = TAG_SPLIT_RE.split(raw)
    else:
        parts = raw or []
    result: list[str] = []
    seen: set[str] = set()
    for part in parts:
        name = " ".join(str(part).strip().lower().split())
        if not name or name in seen:
            continue
        seen.add(name)
        result.append(name[:MAX_TAG_LENGTH])
    return result


def get_item_tags(conn: sqlite3.Connection, item_id: int) -> list[str]:
    rows = conn.execute(
        """
        SELECT t.name FROM tags t
        JOIN item_tags it ON it.tag_id = t.id
        WHERE it.item_id = ?
        ORDER BY t.name COLLATE NOCASE
        """,
        (item_id,),
    ).fetchall()
    return [r["name"] for r in rows]


def set_item_tags(conn: sqlite3.Connection, item_id: int, names) -> None:
    clean = normalize_tags(names)
    conn.execute("DELETE FROM item_tags WHERE item_id = ?", (item_id,))
    for name in clean:
        conn.execute("INSERT OR IGNORE INTO tags(name) VALUES (?)", (name,))
        row = conn.execute("SELECT id FROM tags WHERE name = ?", (name,)).fetchone()
        conn.execute(
            "INSERT OR IGNORE INTO item_tags(item_id, tag_id) VALUES (?, ?)",
            (item_id, row["id"]),
        )


def all_tags(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        """
        SELECT t.name AS name, COUNT(it.item_id) AS count
        FROM tags t
        LEFT JOIN item_tags it ON it.tag_id = t.id
        LEFT JOIN items i ON i.id = it.item_id AND i.archived = 0 AND i.deleted_at IS NULL
        GROUP BY t.id
        ORDER BY t.name COLLATE NOCASE
        """
    ).fetchall()
    return [{"name": r["name"], "count": r["count"]} for r in rows]


# --- full-text index ----------------------------------------------------
# rowid in items_fts equals items.id. We rebuild the row whenever an item or
# its tags change, so search stays in sync. (Used from Step 3 onward.)

def index_item_fts(conn: sqlite3.Connection, item_id: int) -> None:
    row = conn.execute(
        "SELECT title, body, url FROM items WHERE id = ?", (item_id,)
    ).fetchone()
    conn.execute("DELETE FROM items_fts WHERE rowid = ?", (item_id,))
    if row is None:
        return
    tags = " ".join(get_item_tags(conn, item_id))
    conn.execute(
        "INSERT INTO items_fts(rowid, title, body, url, tags) VALUES (?, ?, ?, ?, ?)",
        (item_id, row["title"] or "", row["body"] or "", row["url"] or "", tags),
    )


# --- items ---------------------------------------------------------------

def create_item(
    conn: sqlite3.Connection,
    *,
    type: str,
    title: str = "",
    body: str = "",
    url: Optional[str] = None,
    language: Optional[str] = None,
    tags=None,
) -> int:
    cur = conn.execute(
        "INSERT INTO items(type, title, body, url, language) VALUES (?, ?, ?, ?, ?)",
        (type, title, body, url, language),
    )
    item_id = int(cur.lastrowid)
    set_item_tags(conn, item_id, tags)
    index_item_fts(conn, item_id)
    return item_id


def update_item(
    conn: sqlite3.Connection,
    item_id: int,
    *,
    type: str,
    title: str,
    body: str,
    url: Optional[str],
    language: Optional[str],
    tags=None,
) -> bool:
    cur = conn.execute(
        """
        UPDATE items
        SET type = ?, title = ?, body = ?, url = ?, language = ?,
            updated_at = datetime('now')
        WHERE id = ? AND deleted_at IS NULL
        """,
        (type, title, body, url, language, item_id),
    )
    if cur.rowcount == 0:
        return False
    set_item_tags(conn, item_id, tags)
    index_item_fts(conn, item_id)
    return True


def get_item(conn: sqlite3.Connection, item_id: int) -> Optional[sqlite3.Row]:
    return conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()


def trash_item(conn: sqlite3.Connection, item_id: int) -> bool:
    """Soft delete: set deleted_at so the item hides from all normal views."""
    cur = conn.execute(
        "UPDATE items SET deleted_at = datetime('now'), updated_at = datetime('now') "
        "WHERE id = ? AND deleted_at IS NULL",
        (item_id,),
    )
    if cur.rowcount:
        conn.execute("DELETE FROM items_fts WHERE rowid = ?", (item_id,))
    return cur.rowcount > 0


def restore_item(conn: sqlite3.Connection, item_id: int) -> bool:
    """Pull an item back out of the trash."""
    cur = conn.execute(
        "UPDATE items SET deleted_at = NULL, updated_at = datetime('now') "
        "WHERE id = ? AND deleted_at IS NOT NULL",
        (item_id,),
    )
    if cur.rowcount:
        index_item_fts(conn, item_id)
    return cur.rowcount > 0


def delete_item_permanent(conn: sqlite3.Connection, item_id: int) -> bool:
    """Fully destroy an item (only meant to be called from the trash)."""
    conn.execute("DELETE FROM items_fts WHERE rowid = ?", (item_id,))
    cur = conn.execute("DELETE FROM items WHERE id = ?", (item_id,))
    prune_orphan_tags(conn)
    return cur.rowcount > 0


def purge_deleted(conn: sqlite3.Connection, days: int = 30) -> int:
    """Housekeeping: empty trash for anything deleted more than `days` ago."""
    cur = conn.execute(
        "DELETE FROM items WHERE deleted_at IS NOT NULL "
        "AND deleted_at <= datetime('now', ?)",
        (f"-{days} days",),
    )
    if cur.rowcount:
        conn.execute(
            "DELETE FROM items_fts WHERE rowid NOT IN (SELECT id FROM items)"
        )
        prune_orphan_tags(conn)
    return cur.rowcount


def prune_orphan_tags(conn: sqlite3.Connection) -> None:
    """Drop tags that no longer belong to any item (permanent delete leftover)."""
    conn.execute(
        "DELETE FROM tags WHERE id NOT IN (SELECT DISTINCT tag_id FROM item_tags)"
    )


def set_item_flags(
    conn: sqlite3.Connection,
    item_id: int,
    *,
    pinned: Optional[bool] = None,
    archived: Optional[bool] = None,
) -> bool:
    sets = []
    params: list = []
    if pinned is not None:
        sets.append("pinned = ?")
        params.append(1 if pinned else 0)
    if archived is not None:
        sets.append("archived = ?")
        params.append(1 if archived else 0)
    if not sets:
        return False
    sets.append("updated_at = datetime('now')")
    cur = conn.execute(
        "UPDATE items SET " + ", ".join(sets)
        + " WHERE id = ? AND deleted_at IS NULL",
        (*params, item_id),
    )
    return cur.rowcount > 0


def related_items(
    conn: sqlite3.Connection, item_id: int, limit: int = 4
) -> list[sqlite3.Row]:
    """Best guesses: other items sharing a tag, most shared tags first."""
    return conn.execute(
        """
        SELECT i.*, COUNT(DISTINCT it.tag_id) AS shared
        FROM items i
        JOIN item_tags it ON it.item_id = i.id
        JOIN item_tags peer ON peer.tag_id = it.tag_id AND peer.item_id = ?
        WHERE i.id != ? AND i.deleted_at IS NULL AND i.archived = 0
        GROUP BY i.id
        ORDER BY shared DESC, i.updated_at DESC, i.id DESC
        LIMIT ?
        """,
        (item_id, item_id, max(1, min(limit, 12))),
    ).fetchall()


def _clean_date(value) -> Optional[str]:
    """Keep only strings SQLite can store as a timestamp (UTC "YYYY-MM-DD HH:MM:SS")."""
    if isinstance(value, str) and _DATE_RE.match(value):
        return value
    return None


def find_existing(
    conn: sqlite3.Connection,
    *,
    type: str,
    title: str,
    body: str,
    url: Optional[str],
) -> Optional[sqlite3.Row]:
    """Return the live item whose content exactly matches (used by import
    to skip duplicates instead of piling up copies)."""
    return conn.execute(
        "SELECT id FROM items "
        "WHERE deleted_at IS NULL AND type = ? AND title = ? AND body = ? AND url IS ?",
        (type, title, body, url),
    ).fetchone()


def import_item(
    conn: sqlite3.Connection,
    *,
    type: str,
    title: str,
    body: str,
    url: Optional[str],
    language: Optional[str],
    tags=None,
    created_at=None,
    updated_at=None,
    pinned: bool = False,
    archived: bool = False,
) -> int:
    """Insert a restored item, keeping the original timestamps and flags."""
    created = _clean_date(created_at)
    updated = _clean_date(updated_at)
    cur = conn.execute(
        """
        INSERT INTO items(type, title, body, url, language, pinned, archived,
                          created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?,
                COALESCE(?, datetime('now')), COALESCE(?, datetime('now')))
        """,
        (
            type, title, body, url, language,
            1 if pinned else 0, 1 if archived else 0,
            created, updated,
        ),
    )
    item_id = int(cur.lastrowid)
    set_item_tags(conn, item_id, tags)
    index_item_fts(conn, item_id)
    return item_id


def export_items(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Every live (non-trashed) item, oldest first — full backup source."""
    return conn.execute(
        "SELECT * FROM items WHERE deleted_at IS NULL ORDER BY created_at ASC, id ASC"
    ).fetchall()


def list_items(
    conn: sqlite3.Connection,
    *,
    type: Optional[str] = None,
    tag: Optional[str] = None,
    pinned: bool = False,
    archived: bool = False,
    deleted: bool = False,
    sort: str = "newest",
    q: Optional[str] = None,
    limit: int = 200,
) -> list[sqlite3.Row]:
    if deleted:
        # Trash: no type/tag/search filters, newest-deleted first.
        where = ["i.deleted_at IS NOT NULL"]
        params: list = []
        joins = ""
        rank = ""
        order = "i.deleted_at DESC, i.id DESC"
        pinned_prefix = ""
    else:
        where = ["i.deleted_at IS NULL", "i.archived = ?"]
        params = [1 if archived else 0]
        joins = ""
        rank = ""
        pinned_prefix = "i.pinned DESC, "

        fts = build_fts_query(q)
        if fts:
            joins = " JOIN items_fts ON items_fts.rowid = i.id"
            where.append("items_fts MATCH ?")
            params.append(fts)
            rank = "bm25(items_fts), "

        if type in ("note", "link", "snippet"):
            where.append("i.type = ?")
            params.append(type)
        if pinned:
            where.append("i.pinned = 1")
        if tag:
            clean = normalize_tags([tag])
            where.append(
                "i.id IN (SELECT it.item_id FROM item_tags it "
                "JOIN tags t ON t.id = it.tag_id WHERE t.name = ?)"
            )
            params.append(clean[0] if clean else tag)

        order = SEARCH_SORTS.get(sort, SEARCH_SORTS["newest"])

    sql = (
        "SELECT i.* FROM items i" + joins + " WHERE "
        + " AND ".join(where)
        + " ORDER BY " + pinned_prefix + rank + order
        + " LIMIT ?"
    )
    params.append(max(1, min(limit, 500)))
    sql = " ".join(sql.split())
    return conn.execute(sql, params).fetchall()
