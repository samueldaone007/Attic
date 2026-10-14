"""First-run owner account creation, login and logout."""

import re
import sqlite3

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse

from .. import auth, config
from ..db import create_user, get_db, get_user_by_username, user_count
from ..security import (
    check_csrf,
    clear_attempts,
    get_csrf_token,
    hash_password,
    is_rate_limited,
    record_failed_attempt,
    verify_password,
)
from ..templating import templates

router = APIRouter()

USERNAME_RE = re.compile(r"^[A-Za-z0-9_.@-]{3,64}$")
MIN_PASSWORD_LENGTH = 8


def _render(request, name, **context):
    context.setdefault("csrf_token", get_csrf_token(request))
    return templates.TemplateResponse(request, name, context)


@router.get("/setup")
def setup_page(request: Request, conn: sqlite3.Connection = Depends(get_db)):
    # Only allowed until the single owner account exists.
    if user_count(conn) > 0:
        return RedirectResponse("/login", status_code=303)
    return _render(request, "setup.html", error=None, username="")


@router.post("/setup")
def setup_submit(
    request: Request,
    username: str = Form(""),
    password: str = Form(""),
    password2: str = Form(""),
    csrf_token: str = Form(""),
    conn: sqlite3.Connection = Depends(get_db),
):
    if user_count(conn) > 0:
        return RedirectResponse("/login", status_code=303)

    username = username.strip()
    error = None
    if not check_csrf(request, csrf_token):
        error = "Your session expired. Please try again."
    elif not USERNAME_RE.match(username):
        error = "Username must be 3-64 characters: letters, numbers, . _ @ -"
    elif len(password) < MIN_PASSWORD_LENGTH:
        error = f"Password must be at least {MIN_PASSWORD_LENGTH} characters."
    elif password != password2:
        error = "The two passwords do not match."

    if error:
        return _render(request, "setup.html", error=error, username=username)

    user_id = create_user(conn, username, hash_password(password))
    conn.commit()
    auth.login_user(request, user_id)
    return RedirectResponse("/", status_code=303)


@router.get("/login")
def login_page(request: Request, conn: sqlite3.Connection = Depends(get_db)):
    if user_count(conn) == 0:
        return RedirectResponse("/setup", status_code=303)
    if auth.is_logged_in(request):
        return RedirectResponse("/", status_code=303)
    return _render(request, "login.html", error=None, username="")


@router.post("/login")
def login_submit(
    request: Request,
    username: str = Form(""),
    password: str = Form(""),
    csrf_token: str = Form(""),
    conn: sqlite3.Connection = Depends(get_db),
):
    if user_count(conn) == 0:
        return RedirectResponse("/setup", status_code=303)

    username = username.strip()

    if not check_csrf(request, csrf_token):
        return _render(
            request,
            "login.html",
            error="Your session expired. Please try again.",
            username=username,
        )

    if is_rate_limited(request):
        minutes = max(1, config.LOGIN_WINDOW_SECONDS // 60)
        return _render(
            request,
            "login.html",
            error=f"Too many attempts. Please wait about {minutes} minutes and try again.",
            username=username,
        )

    user = get_user_by_username(conn, username)
    if user and verify_password(password, user["password_hash"]):
        clear_attempts(request)
        auth.login_user(request, int(user["id"]))
        return RedirectResponse("/", status_code=303)

    record_failed_attempt(request)
    return _render(
        request,
        "login.html",
        error="Wrong username or password.",
        username=username,
    )


@router.post("/logout")
def logout(
    request: Request,
    csrf_token: str = Form(""),
):
    if check_csrf(request, csrf_token):
        auth.logout_user(request)
    return RedirectResponse("/login", status_code=303)
