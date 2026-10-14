"""Session helpers shared by all routes."""

import sqlite3
from typing import Optional

from fastapi import Request

from . import db


def login_user(request: Request, user_id: int) -> None:
    """Store the user id in the signed session cookie."""
    request.session["user_id"] = user_id


def logout_user(request: Request) -> None:
    request.session.clear()


def is_logged_in(request: Request) -> bool:
    return bool(request.session.get("user_id"))


def current_user(
    request: Request, conn: sqlite3.Connection
) -> Optional[sqlite3.Row]:
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    return db.get_user(conn, int(user_id))
