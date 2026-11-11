from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from fastapi import HTTPException, Request, Response, status
from pwdlib import PasswordHash

from . import db

PASSWORD_HASHER = PasswordHash.recommended()
SESSION_SECRET = os.getenv("SESSION_SECRET_KEY", "development-only-change-this-before-deploying")
SESSION_COOKIE = "nexus_session"
CSRF_COOKIE = "nexus_csrf"
SESSION_TTL_HOURS = int(os.getenv("SESSION_TTL_HOURS", "12"))
COOKIE_SECURE = os.getenv("AUTH_COOKIE_SECURE", "false").lower() in {"1", "true", "yes"}


def hash_password(password: str) -> str:
    return PASSWORD_HASHER.hash(password)


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        return PASSWORD_HASHER.verify(password, stored_hash)
    except Exception:
        return False


def _csrf_signature(nonce: str) -> str:
    return hmac.new(SESSION_SECRET.encode(), nonce.encode(), hashlib.sha256).hexdigest()


def new_csrf_token() -> str:
    nonce = secrets.token_urlsafe(32)
    return f"{nonce}.{_csrf_signature(nonce)}"


def valid_csrf_token(token: str | None) -> bool:
    if not token or "." not in token:
        return False
    nonce, signature = token.rsplit(".", 1)
    return hmac.compare_digest(signature, _csrf_signature(nonce))


def set_session(response: Response, user_id: int) -> None:
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(hours=SESSION_TTL_HOURS),
        "iss": "nexus-research",
    }
    token = jwt.encode(payload, SESSION_SECRET, algorithm="HS256")
    csrf = new_csrf_token()
    common = {"max_age": SESSION_TTL_HOURS * 3600, "secure": COOKIE_SECURE,
              "samesite": "lax", "path": "/"}
    response.set_cookie(SESSION_COOKIE, token, httponly=True, **common)
    response.set_cookie(CSRF_COOKIE, csrf, httponly=False, **common)


def clear_session(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/", secure=COOKIE_SECURE, httponly=True, samesite="lax")
    response.delete_cookie(CSRF_COOKIE, path="/", secure=COOKIE_SECURE, httponly=False, samesite="lax")


def enforce_same_origin(request: Request) -> None:
    origin = request.headers.get("origin")
    if origin:
        expected = f"{request.url.scheme}://{request.url.netloc}"
        if not hmac.compare_digest(origin.rstrip("/"), expected.rstrip("/")):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cross-origin authentication request rejected.")
    if request.headers.get("sec-fetch-site") == "cross-site":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cross-site authentication request rejected.")


def require_csrf(request: Request) -> None:
    cookie_value = request.cookies.get(CSRF_COOKIE)
    header_value = request.headers.get("x-csrf-token")
    if not cookie_value or not header_value:
        raise HTTPException(status_code=403, detail="CSRF token missing.")
    if not hmac.compare_digest(cookie_value, header_value) or not valid_csrf_token(cookie_value):
        raise HTTPException(status_code=403, detail="CSRF token invalid.")


def get_current_user(request: Request) -> dict[str, Any]:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise HTTPException(status_code=401, detail="Sign in to access your research workspace.")
    try:
        payload = jwt.decode(token, SESSION_SECRET, algorithms=["HS256"], issuer="nexus-research")
        user_id = int(payload["sub"])
    except (jwt.PyJWTError, KeyError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=401, detail="Your session has expired. Sign in again.") from exc
    user = db.get_user_by_id(user_id)
    if not user or not user["is_active"]:
        raise HTTPException(status_code=401, detail="This account is unavailable.")
    return user
