"""FastAPI application entry point."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware

from . import config
from .db import connect, get_setting, init_db
from .routers import account, items, pages
from .store import purge_deleted


class SecurityHeaders(BaseHTTPMiddleware):
    """Sensible defaults for a private single-user app."""

    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        response.headers.setdefault(
            "Permissions-Policy", "camera=(), microphone=(), geolocation=()"
        )
        return response


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Runs once at startup: create tables, seed defaults, empty old trash.
    init_db()
    conn = connect()
    try:
        days = int(get_setting(conn, "trash_days", "30"))
        purge_deleted(conn, days=max(1, min(days, 365)))
        conn.commit()
    finally:
        conn.close()
    yield


app = FastAPI(
    title=config.APP_NAME,
    lifespan=lifespan,
    # Private app: don't expose the interactive API docs.
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

# Signed-cookie sessions. The cookie is httpOnly + SameSite=Lax, and marked
# Secure when HTTPS is enabled.
app.add_middleware(SecurityHeaders)
app.add_middleware(
    SessionMiddleware,
    secret_key=config.SECRET_KEY,
    session_cookie="attic_session",
    max_age=config.SESSION_MAX_AGE,
    same_site="lax",
    https_only=config.COOKIE_SECURE,
)

app.mount("/static", StaticFiles(directory=str(config.STATIC_DIR)), name="static")


@app.get("/sw.js", include_in_schema=False)
def service_worker():
    """PWA service worker. Served from root so it controls the whole app."""
    return FileResponse(
        config.STATIC_DIR / "sw.js",
        media_type="application/javascript",
        headers={"Cache-Control": "no-cache"},
    )


@app.get("/manifest.json", include_in_schema=False)
def web_manifest():
    return FileResponse(
        config.STATIC_DIR / "manifest.json",
        media_type="application/manifest+json",
        headers={"Cache-Control": "no-cache"},
    )


@app.get("/offline", include_in_schema=False)
def offline_page():
    """Standalone fallback page the service worker can serve offline."""
    return FileResponse(
        config.STATIC_DIR / "offline.html",
        media_type="text/html",
        headers={"Cache-Control": "no-cache"},
    )


app.include_router(account.router)
app.include_router(items.router)
app.include_router(pages.router)
