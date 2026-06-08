"""Helpers to set/clear the auth cookies on a response.

The access cookie is scoped to "/" (sent on every request); the refresh cookie
is scoped to the auth path so the long-lived token is only ever sent to the
refresh/logout endpoints.
"""

from __future__ import annotations

from typing import Literal, cast

from starlette.responses import Response

from app.platform.config import get_settings

ACCESS_COOKIE = "access_token"
REFRESH_COOKIE = "refresh_token"
REFRESH_COOKIE_PATH = "/api/v1/auth"

SameSite = Literal["lax", "strict", "none"]


def set_auth_cookies(response: Response, access_token: str, refresh_token: str) -> None:
    settings = get_settings()
    samesite = cast(SameSite, settings.cookie_samesite)
    response.set_cookie(
        ACCESS_COOKIE,
        access_token,
        max_age=settings.access_token_ttl_seconds,
        path="/",
        httponly=True,
        secure=settings.cookie_secure,
        samesite=samesite,
    )
    response.set_cookie(
        REFRESH_COOKIE,
        refresh_token,
        max_age=settings.refresh_token_ttl_seconds,
        path=REFRESH_COOKIE_PATH,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=samesite,
    )


def clear_auth_cookies(response: Response) -> None:
    response.delete_cookie(ACCESS_COOKIE, path="/")
    response.delete_cookie(REFRESH_COOKIE, path=REFRESH_COOKIE_PATH)
