"""Token minting and verification.

Two kinds of token:
  - access token: a short-lived JWT, verified statelessly by signature.
  - refresh token: an opaque random string; only its SHA-256 hash is stored,
    and it is checked against the database.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any, TypedDict, cast

import jwt

from app.platform.config import get_settings


class AccessTokenPayload(TypedDict):
    sub: str    # user_id as string (JWT standard claim)
    email: str
    iat: datetime
    exp: datetime


def mint_access_token(user_id: int, email: str) -> str:
    """Sign a short-lived access JWT carrying the user's id (sub) and email."""
    settings = get_settings()
    now = datetime.now(UTC)
    payload: AccessTokenPayload = {
        "sub": str(user_id),
        "email": email,
        "iat": now,
        "exp": now + timedelta(seconds=settings.access_token_ttl_seconds),
    }
    return jwt.encode(cast(dict[str, Any], payload), settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> AccessTokenPayload | None:
    """Return the JWT claims, or None if the token is invalid or expired."""
    settings = get_settings()
    try:
        return cast(
            AccessTokenPayload,
            jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]),
        )
    except jwt.PyJWTError:
        return None


def hash_token(raw: str) -> str:
    """SHA-256 hex digest — store/look up for refresh tokens."""
    return hashlib.sha256(raw.encode()).hexdigest()


def new_refresh_token() -> tuple[str, str]:
    """The raw token goes in the cookie; only
    the hash is persisted."""
    raw = secrets.token_urlsafe(48)
    return raw, hash_token(raw)


def refresh_expiry() -> datetime:
    settings = get_settings()
    return datetime.now(UTC) + timedelta(seconds=settings.refresh_token_ttl_seconds)
