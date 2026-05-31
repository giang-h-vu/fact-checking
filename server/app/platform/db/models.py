"""SQLModel persistence for verification history.

Two tables: SearchRequest (one per claim) and Citation (one per supporting/
refuting passage). No ORM relationship — citations are queried by FK
explicitly to keep things easy to reason about under async.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SearchRequest(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    claim: str = Field(index=True, max_length=1000)
    created_at: datetime = Field(default_factory=_utcnow, index=True)
    verdict: str = Field(max_length=20)


class Citation(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    request_id: int = Field(foreign_key="searchrequest.id", index=True)
    url: str = Field(max_length=2000)
    title: str = Field(max_length=500)
    passage: str
    label: str = Field(max_length=20)
    reasoning: str = ""
