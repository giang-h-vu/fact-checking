"""SQLModel persistence for verification history.

Two tables: SearchRequest (one per claim) and Citation (one per supporting/
refuting passage). No ORM relationship — citations are queried by FK.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(UTC)


class User(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    email: str = Field(index=True, unique=True, max_length=320)
    name: str = Field(max_length=200)
    picture: str = Field(default="", max_length=2000)
    created_at: datetime = Field(default_factory=_utcnow)


class RefreshToken(SQLModel, table=True):
    """One row per issued refresh token. Only the SHA-256 hash is stored, never
    the raw token. Rotated on every use (old row revoked, new row inserted)."""

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    token_hash: str = Field(index=True, unique=True, max_length=64)
    expires_at: datetime
    revoked: bool = Field(default=False)
    created_at: datetime = Field(default_factory=_utcnow)


class SearchRequest(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    claim: str = Field(index=True, max_length=1000)
    created_at: datetime = Field(default_factory=_utcnow, index=True)
    verdict: str = Field(max_length=20)


class Citation(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    request_id: int = Field(foreign_key="searchrequest.id", index=True)
    url: str = Field(max_length=2000)
    title: str = Field(max_length=500)
    passage: str
    label: str = Field(max_length=20)
    reasoning: str = ""
