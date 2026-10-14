"""Application-wide configuration.

Everything here can be overridden with environment variables so the same code
runs locally and on a free host. Nothing secret is hard-coded: the session
signing key is generated on first run and stored next to the database.
"""

import os
import secrets
from pathlib import Path

# Project root = folder that contains "app/".
BASE_DIR = Path(__file__).resolve().parent.parent

# Folder where the database and generated secret key live.
DATA_DIR = Path(os.environ.get("ATTIC_DATA_DIR", BASE_DIR / "data")).expanduser()
if not DATA_DIR.is_absolute():
    DATA_DIR = (BASE_DIR / DATA_DIR).resolve()

APP_NAME = "Attic"
TAGLINE = "Keep it. Find it."


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _load_secret_key() -> str:
    """Return a stable secret key, creating one on first run if needed."""
    env = os.environ.get("ATTIC_SECRET_KEY")
    if env:
        return env
    key_file = DATA_DIR / "secret_key"
    try:
        if key_file.exists():
            value = key_file.read_text(encoding="utf-8").strip()
            if value:
                return value
    except OSError:
        pass
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    value = secrets.token_hex(32)
    try:
        key_file.write_text(value, encoding="utf-8")
    except OSError:
        pass
    return value


def _resolve_db_path() -> Path:
    env = os.environ.get("ATTIC_DB")
    path = Path(env).expanduser() if env else DATA_DIR / "attic.db"
    if not path.is_absolute():
        path = (BASE_DIR / path).resolve()
    return path


DB_PATH = _resolve_db_path()
SECRET_KEY = _load_secret_key()

# Session lifetime in hours (default 30 days so the launch shortcut opens
# straight into the app instead of asking for a password every time).
SESSION_MAX_AGE = int(os.environ.get("ATTIC_SESSION_HOURS", "720")) * 3600

# Mark cookies Secure when running behind HTTPS. Off by default for localhost.
COOKIE_SECURE = _env_bool("ATTIC_COOKIE_SECURE", False)

# Login throttling: allow this many failed attempts per window before pausing.
LOGIN_MAX_ATTEMPTS = int(os.environ.get("ATTIC_LOGIN_MAX_ATTEMPTS", "10"))
LOGIN_WINDOW_SECONDS = int(os.environ.get("ATTIC_LOGIN_WINDOW_SECONDS", "900"))

TEMPLATES_DIR = BASE_DIR / "app" / "templates"
STATIC_DIR = BASE_DIR / "app" / "static"
