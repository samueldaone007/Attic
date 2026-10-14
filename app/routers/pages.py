"""Pages: the main app shell, settings, and the shortcut help stub."""

import sqlite3

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse

from .. import auth, config
from ..db import get_db, get_setting, user_count
from ..security import get_csrf_token
from ..templating import templates

router = APIRouter()


def _render(request, name, **context):
    context.setdefault("csrf_token", get_csrf_token(request))
    return templates.TemplateResponse(request, name, context)


@router.get("/")
def index(
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
):
    if user_count(conn) == 0:
        return RedirectResponse("/setup", status_code=303)
    user = auth.current_user(request, conn)
    if user is None:
        return RedirectResponse("/login", status_code=303)

    # Launch-action query strings only choose what the UI opens. They never
    # change data on their own.
    launch_new = request.query_params.get("new", "")
    if launch_new not in {"note", "link", "snippet"}:
        launch_new = ""
    launch_search = request.query_params.get("search") == "1"

    return _render(
        request,
        "index.html",
        user=user,
        theme=get_setting(conn, "theme", "system"),
        default_item_type=get_setting(conn, "default_item_type", "note"),
        launch_new=launch_new,
        launch_search=launch_search,
        session_hours=config.SESSION_MAX_AGE // 3600,
    )


@router.get("/shortcuts")
def shortcuts_page(
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
):
    if user_count(conn) == 0:
        return RedirectResponse("/setup", status_code=303)
    user = auth.current_user(request, conn)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    return _render(request, "shortcuts.html", user=user)


@router.get("/settings")
def settings_page(
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
):
    if user_count(conn) == 0:
        return RedirectResponse("/setup", status_code=303)
    user = auth.current_user(request, conn)
    if user is None:
        return RedirectResponse("/login", status_code=303)

    return _render(
        request,
        "settings.html",
        user=user,
        theme=get_setting(conn, "theme", "system"),
        default_item_type=get_setting(conn, "default_item_type", "note"),
        trash_days=int(get_setting(conn, "trash_days", "30")),
        session_hours=config.SESSION_MAX_AGE // 3600,
    )
