"""Auth router — Google OAuth login + JWT session management.

Flow:
  login    → redirect to Google's consent screen
  callback → exchange code, upsert user, mint access+refresh, set cookies, redirect home
  refresh  → rotate the refresh token, mint a new access token
  logout   → revoke the refresh token, clear cookies
  me       → return the authenticated user
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Annotated, NotRequired, TypedDict, cast


class GoogleUserInfo(TypedDict):
    email: str
    name: NotRequired[str]
    picture: NotRequired[str]

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlmodel import select
from starlette.responses import RedirectResponse

from app.api.generated.models import User as ApiUser
from app.platform.auth.cookies import (
    REFRESH_COOKIE,
    clear_auth_cookies,
    set_auth_cookies,
)
from app.platform.auth.dependencies import get_current_user
from app.platform.auth.oauth import get_oauth
from app.platform.auth.tokens import (
    hash_token,
    mint_access_token,
    new_refresh_token,
    refresh_expiry,
)
from app.platform.config import get_settings
from app.platform.db.models import RefreshToken, User
from app.platform.db.session import session_scope

log = logging.getLogger(__name__)

router = APIRouter(tags=["auth"], prefix="/api/v1/auth")


@router.get("/google/login")
async def auth_google_login(request: Request) -> RedirectResponse:
    oauth= get_oauth()
    redirect_uri = get_settings().oauth_redirect_uri
    redirect = await oauth.google.authorize_redirect(request, redirect_uri)
    return cast(RedirectResponse, redirect)


@router.get("/google/callback")
async def auth_google_callback(request: Request) -> RedirectResponse:
    oauth = get_oauth()
    try:
        token = await oauth.google.authorize_access_token(request)
    except Exception as e:
        log.warning("OAuth callback failed: %s", e)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "OAuth failed") from e

    userinfo = cast(GoogleUserInfo | None, token.get("userinfo"))
    if not userinfo or not userinfo.get("email"):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "No user info from Google")

    async with session_scope() as session:
        user = (
            await session.execute(select(User).where(User.email == userinfo["email"]))
        ).scalar_one_or_none()
        if user is None:
            user = User(
                email=userinfo["email"],
                name=userinfo.get("name", userinfo["email"]),
                picture=userinfo.get("picture", ""),
            )
            session.add(user)
            await session.flush()
            await session.refresh(user)

        assert user.id is not None
        access = mint_access_token(user.id, user.email)
        raw_refresh, refresh_hash = new_refresh_token()
        session.add(
            RefreshToken(
                user_id=user.id, token_hash=refresh_hash, expires_at=refresh_expiry()
            )
        )
        await session.commit()

    # Redirect to homepage after login.
    response = RedirectResponse(get_settings().frontend_url)
    set_auth_cookies(response, access, raw_refresh)
    return response


@router.post("/refresh", status_code=status.HTTP_204_NO_CONTENT)
async def auth_refresh(request: Request) -> Response:
    raw = request.cookies.get(REFRESH_COOKIE)
    if not raw:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "No refresh token")

    token_hash = hash_token(raw)
    async with session_scope() as session:
        refresh_token = (
            await session.execute(
                select(RefreshToken).where(RefreshToken.token_hash == token_hash)
            )
        ).scalar_one_or_none()

        now = datetime.now(UTC)
        if refresh_token is None or refresh_token.revoked or _expired(refresh_token.expires_at, now):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid refresh token")

        user = await session.get(User, refresh_token.user_id)
        if user is None or user.id is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Unknown user")

        # Rotate: revoke the presented token, issue a fresh one.
        refresh_token.revoked = True
        session.add(refresh_token)
        access = mint_access_token(user.id, user.email)
        raw_refresh, refresh_hash = new_refresh_token()
        session.add(
            RefreshToken(
                user_id=user.id, token_hash=refresh_hash, expires_at=refresh_expiry()
            )
        )
        await session.commit()

    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    set_auth_cookies(response, access, raw_refresh)
    return response


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def auth_logout(request: Request) -> Response:
    raw = request.cookies.get(REFRESH_COOKIE)
    if raw:
        token_hash = hash_token(raw)
        async with session_scope() as session:
            refresh_token = (
                await session.execute(
                    select(RefreshToken).where(RefreshToken.token_hash == token_hash)
                )
            ).scalar_one_or_none()
            if refresh_token is not None:
                refresh_token.revoked = True
                session.add(refresh_token)
                await session.commit()

    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    clear_auth_cookies(response)
    return response


@router.get("/me", response_model=ApiUser)
async def get_me(user: Annotated[User, Depends(get_current_user)]) -> ApiUser:
    return ApiUser.model_validate(
        {
            "id": user.id,
            "email": user.email,
            "name": user.name,
            "picture": user.picture or None,
        }
    )


def _expired(expires_at: datetime, now: datetime) -> bool:
    # SQLite may return a naive datetime; treat it as UTC for comparison.
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    return expires_at <= now
