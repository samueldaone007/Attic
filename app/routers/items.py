"""JSON API for items, tags and Markdown rendering."""

import json
import sqlite3
from datetime import datetime, timezone
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile, File
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .. import auth, config, linkmeta, markdown_render, store
from ..db import get_db, get_setting, set_setting, set_user_password
from ..dependencies import require_csrf, require_owner
from ..security import hash_password, verify_password

router = APIRouter(prefix="/api", dependencies=[Depends(require_owner)])

ItemType = Literal["note", "link", "snippet"]

MAX_IMPORT_BYTES = 25 * 1024 * 1024
MAX_IMPORT_ITEMS = 5000


class ItemIn(BaseModel):
    type: ItemType = "note"
    title: str = ""
    body: str = ""
    url: Optional[str] = None
    language: Optional[str] = None
    tags: List[str] = Field(default_factory=list)


class MarkdownIn(BaseModel):
    text: str = ""


class ItemFlagsIn(BaseModel):
    pinned: Optional[bool] = None
    archived: Optional[bool] = None


class SettingsIn(BaseModel):
    trash_days: Optional[int] = Field(default=None, ge=1, le=365)


class PasswordIn(BaseModel):
    current: str = ""
    new: str = ""


def _clean_item(payload: ItemIn) -> dict:
    title = (payload.title or "").strip()[:300]
    body = payload.body or ""
    url = (payload.url or "").strip() or None
    language = None
    if payload.type == "snippet" and payload.language:
        language = payload.language.strip()[:40] or None
    return {
        "type": payload.type,
        "title": title,
        "body": body,
        "url": url,
        "language": language,
        "tags": payload.tags,
    }


def _apply_link_metadata(data: dict) -> dict:
    """Fill title/description of a Link item from the page itself.

    Only queried when the user left the field empty, and only over http(s).
    If the site is slow or refuses, we keep what we have and move on.
    """
    needs = data["type"] == "link" and data["url"] and (not data["title"] or not data["body"])
    if not needs:
        return data
    meta = linkmeta.fetch_link_metadata(data["url"]) or {}
    if not data["title"] and meta.get("title"):
        data["title"] = meta["title"][:300]
    if not data["body"] and meta.get("description"):
        data["body"] = meta["description"]
    return data


def _serialize(conn: sqlite3.Connection, row: sqlite3.Row, include_html: bool = False) -> dict:
    body = row["body"] or ""
    if row["type"] == "link":
        preview_source = body or (row["url"] or "")
    else:
        preview_source = body
    data = {
        "id": row["id"],
        "type": row["type"],
        "title": row["title"],
        "body": body,
        "url": row["url"],
        "language": row["language"],
        "pinned": bool(row["pinned"]),
        "archived": bool(row["archived"]),
        "deleted_at": row["deleted_at"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "tags": store.get_item_tags(conn, row["id"]),
        "preview": markdown_render.markdown_to_text(preview_source)[:240],
    }
    if include_html:
        if row["type"] == "snippet":
            data["body_html"] = markdown_render.render_snippet(data["body"], row["language"])
        else:
            data["body_html"] = markdown_render.render_markdown(body)
    return data


@router.get("/items")
def list_items(
    type: Optional[ItemType] = Query(None),
    tag: Optional[str] = Query(None),
    pinned: int = Query(0),
    archived: int = Query(0),
    deleted: int = Query(0),
    sort: str = Query("newest"),
    q: Optional[str] = Query(None),
    conn: sqlite3.Connection = Depends(get_db),
):
    rows = store.list_items(
        conn,
        type=type,
        tag=tag,
        pinned=bool(pinned),
        archived=bool(archived),
        deleted=bool(deleted),
        sort=sort,
        q=q,
    )
    return {"items": [_serialize(conn, r) for r in rows]}


@router.get("/items/{item_id}")
def get_item(item_id: int, conn: sqlite3.Connection = Depends(get_db)):
    row = store.get_item(conn, item_id)
    if row is None or row["deleted_at"] is not None:
        raise HTTPException(status_code=404, detail="Item not found")
    return _serialize(conn, row, include_html=True)


@router.get("/items/{item_id}/related")
def get_related(item_id: int, conn: sqlite3.Connection = Depends(get_db)):
    row = store.get_item(conn, item_id)
    if row is None or row["deleted_at"] is not None:
        raise HTTPException(status_code=404, detail="Item not found")
    rows = store.related_items(conn, item_id)
    return {"items": [_serialize(conn, r) for r in rows]}


@router.post("/items", dependencies=[Depends(require_csrf)])
def create_item(payload: ItemIn, conn: sqlite3.Connection = Depends(get_db)):
    data = _apply_link_metadata(_clean_item(payload))
    item_id = store.create_item(conn, **data)
    conn.commit()
    row = store.get_item(conn, item_id)
    return _serialize(conn, row, include_html=True)


@router.put("/items/{item_id}", dependencies=[Depends(require_csrf)])
def update_item(item_id: int, payload: ItemIn, conn: sqlite3.Connection = Depends(get_db)):
    data = _apply_link_metadata(_clean_item(payload))
    if not store.update_item(conn, item_id, **data):
        raise HTTPException(status_code=404, detail="Item not found")
    conn.commit()
    row = store.get_item(conn, item_id)
    return _serialize(conn, row, include_html=True)


@router.patch("/items/{item_id}", dependencies=[Depends(require_csrf)])
def update_flags(item_id: int, payload: ItemFlagsIn, conn: sqlite3.Connection = Depends(get_db)):
    if not store.set_item_flags(conn, item_id, pinned=payload.pinned, archived=payload.archived):
        raise HTTPException(status_code=404, detail="Item not found")
    conn.commit()
    return _serialize(conn, store.get_item(conn, item_id))


@router.delete("/items/{item_id}", dependencies=[Depends(require_csrf)])
def delete_item(item_id: int, conn: sqlite3.Connection = Depends(get_db)):
    if not store.trash_item(conn, item_id):
        raise HTTPException(status_code=404, detail="Item not found")
    conn.commit()
    return {"ok": True, "trashed": True}


@router.delete("/items/{item_id}/permanent", dependencies=[Depends(require_csrf)])
def delete_permanent(item_id: int, conn: sqlite3.Connection = Depends(get_db)):
    if not store.delete_item_permanent(conn, item_id):
        raise HTTPException(status_code=404, detail="Item not found")
    conn.commit()
    return {"ok": True}


@router.post("/items/{item_id}/restore", dependencies=[Depends(require_csrf)])
def restore_item(item_id: int, conn: sqlite3.Connection = Depends(get_db)):
    if not store.restore_item(conn, item_id):
        raise HTTPException(status_code=404, detail="Item not found")
    conn.commit()
    return _serialize(conn, store.get_item(conn, item_id), include_html=True)


@router.get("/tags")
def list_tags(conn: sqlite3.Connection = Depends(get_db)):
    return {"tags": store.all_tags(conn)}


@router.post("/markdown", dependencies=[Depends(require_csrf)])
def render_markdown(payload: MarkdownIn):
    return {"html": markdown_render.render_markdown(payload.text)}


@router.patch("/settings", dependencies=[Depends(require_csrf)])
def update_settings(payload: SettingsIn, conn: sqlite3.Connection = Depends(get_db)):
    """Update app preferences. Only whitelisted keys are accepted."""
    if payload.trash_days is not None:
        set_setting(conn, "trash_days", str(payload.trash_days))
    conn.commit()
    return {
        "trash_days": int(get_setting(conn, "trash_days", "30")),
    }


@router.post("/account/password", dependencies=[Depends(require_csrf)])
def change_password(
    payload: PasswordIn,
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
):
    """Change the owner password. The current one must be confirmed first."""
    user = auth.current_user(request, conn)
    if user is None:
        raise HTTPException(status_code=401, detail="Please log in again.")
    row = conn.execute(
        "SELECT password_hash FROM users WHERE id = ?", (user["id"],)
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Account not found.")

    if not verify_password(payload.current, row["password_hash"]):
        raise HTTPException(status_code=400, detail="Current password is wrong.")
    if len(payload.new) < 8:
        raise HTTPException(status_code=400, detail="New password must be at least 8 characters.")

    set_user_password(conn, user["id"], hash_password(payload.new))
    conn.commit()
    return {"ok": True}


@router.get("/export")
def export_data(conn: sqlite3.Connection = Depends(get_db)):
    """Download every live item as one JSON file (no trashed items)."""
    items = []
    for row in store.export_items(conn):
        items.append({
            "type": row["type"],
            "title": row["title"] or "",
            "body": row["body"] or "",
            "url": row["url"],
            "language": row["language"],
            "pinned": bool(row["pinned"]),
            "archived": bool(row["archived"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "tags": store.get_item_tags(conn, row["id"]),
        })
    now = datetime.now(timezone.utc)
    payload = {
        "app": config.APP_NAME,
        "export_version": 1,
        "exported_at": now.strftime("%Y-%m-%d %H:%M:%S"),
        "items": items,
    }
    filename = f"attic-backup-{now.strftime('%Y-%m-%d')}.json"
    return JSONResponse(
        payload,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/import", dependencies=[Depends(require_csrf)])
def import_data(file: UploadFile = File(...), conn: sqlite3.Connection = Depends(get_db)):
    """Restore a backup. Content-identical items are skipped, the rest become
    new entries (fresh ids, original timestamps/flags preserved)."""
    raw = file.file.read(MAX_IMPORT_BYTES + 1)
    if len(raw) > MAX_IMPORT_BYTES:
        raise HTTPException(status_code=413, detail="Backup file is too large (max 25 MB).")
    try:
        data = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        raise HTTPException(status_code=400, detail="That doesn't look like a JSON backup.")

    items = data.get("items") if isinstance(data, dict) else None
    if not isinstance(items, list):
        raise HTTPException(status_code=400, detail="Backup is missing its 'items' list.")
    if len(items) > MAX_IMPORT_ITEMS:
        raise HTTPException(
            status_code=413,
            detail=f"Backup has too many items (max {MAX_IMPORT_ITEMS}).",
        )

    imported = 0
    skipped = 0
    for raw_item in items:
        if not isinstance(raw_item, dict):
            skipped += 1
            continue
        try:
            item_type = raw_item.get("type", "note")
            if item_type not in ("note", "link", "snippet"):
                skipped += 1
                continue
            title = str(raw_item.get("title") or "")[:300]
            body = str(raw_item.get("body") or "")
            url = str(raw_item.get("url") or "").strip() or None
            language = str(raw_item.get("language") or "").strip()[:40] or None
            if item_type != "snippet":
                language = None
            tags = raw_item.get("tags") or []

            if store.find_existing(conn, type=item_type, title=title, body=body, url=url):
                skipped += 1
                continue

            store.import_item(
                conn,
                type=item_type,
                title=title,
                body=body,
                url=url,
                language=language,
                tags=tags,
                created_at=raw_item.get("created_at"),
                updated_at=raw_item.get("updated_at"),
                pinned=bool(raw_item.get("pinned")),
                archived=bool(raw_item.get("archived")),
            )
            imported += 1
        except Exception:
            skipped += 1

    conn.commit()
    return {"imported": imported, "skipped": skipped}
