"""Password hashing and JWT / refresh-token primitives."""

from __future__ import annotations

import base64
import hashlib
import secrets
import uuid
from datetime import timedelta

import bcrypt
import jwt

from .db import utcnow
from .settings import Settings


# --- passwords -----------------------------------------------------------
def _prep(password: str) -> bytes:
    """bcrypt silently truncates at 72 bytes; pre-hash so full entropy counts."""
    return base64.b64encode(hashlib.sha256(password.encode("utf-8")).digest())


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_prep(password), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(_prep(password), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


# --- access tokens (JWT) ----------------------------------------------
def create_access_token(subject: str, settings: Settings, extra: dict | None = None) -> str:
    now = utcnow()
    payload = {
        "sub": subject,
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_ttl_min),
        "type": "access",
        "jti": uuid.uuid4().hex,
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def decode_access_token(token: str, settings: Settings) -> dict:
    """Raises jwt.PyJWTError on any problem (expired, bad sig, wrong type)."""
    payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
    if payload.get("type") != "access":
        raise jwt.InvalidTokenError("not an access token")
    return payload


# --- refresh tokens (opaque, stored hashed, rotated on use) ------------
def new_refresh_token() -> tuple[str, str]:
    raw = secrets.token_urlsafe(48)
    return raw, hash_refresh_token(raw)


def hash_refresh_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
