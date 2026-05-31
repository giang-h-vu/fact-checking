"""Async SQLAlchemy/SQLModel engine + session factory.

SQLite by default (works zero-config); swap by setting DATABASE_URL to a
postgres+asyncpg / mysql+aiomysql URL.
"""
from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import lru_cache

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel

from app.platform.config import get_settings


@lru_cache
def _engine():
    return create_async_engine(get_settings().database_url, echo=False)


@lru_cache
def _sessionmaker():
    return async_sessionmaker(_engine(), class_=AsyncSession,
        expire_on_commit=False
    )


async def init_db() -> None:
    # Import models so SQLModel.metadata sees the tables before create_all.
    from app.platform.db import models  # noqa: F401

    async with _engine().begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    async with _sessionmaker()() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
