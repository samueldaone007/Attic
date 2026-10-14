"""Security helpers: password hashing, CSRF tokens, login throttling.

Keeping these in one place makes it easy to review. Passwords are hashed with
bcrypt (never stored or logged in plain text).
"""

import hmac
import secrets
import time
from collections import defaultdict, deque
from typing import Optional

import bcrypt
from fastapi import Request

from . import config

# --- passwords ----------------------------------------------------------
# bcrypt only reads the first 72 bytes of a password. Trimming to that length
# keeps behaviour identical between hashing and checking on every version.

def _bcrypt_bytes(password: str) -> bytes:
    return password.encode("utf-8")[:72]


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_bcrypt_bytes(password), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(_bcrypt_bytes(password), password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


# --- CSRF ---------------------------------------------------------------
# A random token is stored in the signed session cookie. Forms must send it
# back as a hidden field; the server compares the two with a constant-time
# comparison. This stops another website from submitting forms as you.

def get_csrf_token(request: Request) -> str:
    token = request.session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        request.session["csrf_token"] = token
    return token


def check_csrf(request: Request, submitted: Optional[str]) -> bool:
    token = request.session.get("csrf_token")
    if not token or not submitted:
        return False
    return hmac.compare_digest(token, submitted)


# --- login throttling ---------------------------------------------------
# Simple in-memory limiter keyed by client IP. Good enough for a single-user
# app on one process. Swapping to Redis/DB later only touches this section.

_attempts: dict[str, deque] = defaultdict(deque)


def _client_key(request: Request) -> str:
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def is_rate_limited(request: Request) -> bool:
    key = _client_key(request)
    now = time.time()
    bucket = _attempts[key]
    while bucket and now - bucket[0] > config.LOGIN_WINDOW_SECONDS:
        bucket.popleft()
    return len(bucket) >= config.LOGIN_MAX_ATTEMPTS


def record_failed_attempt(request: Request) -> None:
    _attempts[_client_key(request)].append(time.time())


def clear_attempts(request: Request) -> None:
    _attempts.pop(_client_key(request), None)
