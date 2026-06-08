"""FastAPI dependency that resolves the current user from the access cookie.

Verification is stateless: decode the JWT signature, then load the user row by
the `sub` claim. A missing/invalid/expired token, or an unknown user, is a 401.
"""

from __future__ import annotations

from fastapi import HTTPException, Request, status

from app.platform.auth.cookies import ACCESS_COOKIE
from app.platform.auth.tokens import AccessTokenPayload, decode_access_token
from app.platform.db.models import User
from app.platform.db.session import session_scope

UNAUTHORIZED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Not authenticated",
)


async def get_current_user(request: Request) -> User:
    token = request.cookies.get(ACCESS_COOKIE)
    if not token:
        raise UNAUTHORIZED

    claims: AccessTokenPayload | None = decode_access_token(token)
    if claims is None:
        raise UNAUTHORIZED

    try:
        user_id = int(claims["sub"])
    except (TypeError, ValueError):
        raise UNAUTHORIZED from None

    async with session_scope() as session:
        user = await session.get(User, user_id)
    if user is None:
        raise UNAUTHORIZED
    return user
