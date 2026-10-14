"""Reusable FastAPI dependencies for the JSON API."""

from fastapi import HTTPException, Request

from . import auth
from .security import check_csrf


def require_owner(request: Request) -> None:
    """The API is only for the logged-in owner."""
    if not auth.is_logged_in(request):
        raise HTTPException(status_code=401, detail="Not logged in")


def require_csrf(request: Request) -> None:
    """Every state-changing API call must carry the session CSRF token.

    The token is placed in a <meta> tag on the page and sent back in the
    X-CSRF-Token header, so another site cannot make requests as you.
    """
    if not check_csrf(request, request.headers.get("x-csrf-token")):
        raise HTTPException(status_code=403, detail="Invalid or missing CSRF token")
