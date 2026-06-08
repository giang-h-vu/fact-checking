import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlmodel import SQLModel

from app.platform.config import get_settings
from app.platform.db.models import RefreshToken, SearchRequest, User
from app.platform.db.session import _engine, _sessionmaker


@pytest.fixture(autouse=True)
def reset_caches():
    get_settings.cache_clear()
    _engine.cache_clear()
    _sessionmaker.cache_clear()
    yield
    get_settings.cache_clear()
    _engine.cache_clear()
    _sessionmaker.cache_clear()


# --- DB seeding helpers -----------------------------------------------------
# These open their own short-lived engine against the test's SQLite file so they
# don't depend on the app's cached (loop-bound) engine. They commit to the same
# file the app reads, so seeded rows are visible to the running app.


def _run_db(db_url: str, op):
    async def _go():
        engine = create_async_engine(db_url)
        async with engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.create_all)
        async with AsyncSession(engine) as session:
            result = await op(session)
            await session.commit()
        await engine.dispose()
        return result

    return asyncio.run(_go())


def seed_user(db_url: str, email: str = "test@example.com", name: str = "Test User") -> int:
    async def op(session: AsyncSession) -> int:
        user = User(email=email, name=name)
        session.add(user)
        await session.flush()
        await session.refresh(user)
        assert user.id is not None
        return user.id

    return _run_db(db_url, op)


def seed_refresh_token(db_url: str, user_id: int, token_hash: str, *, ttl_seconds: int = 3600,
                       revoked: bool = False) -> None:
    async def op(session: AsyncSession) -> None:
        session.add(
            RefreshToken(
                user_id=user_id,
                token_hash=token_hash,
                expires_at=datetime.now(UTC) + timedelta(seconds=ttl_seconds),
                revoked=revoked,
            )
        )

    _run_db(db_url, op)


def seed_search_request(db_url: str, user_id: int, claim: str, verdict: str = "SUPPORTED") -> None:
    async def op(session: AsyncSession) -> None:
        session.add(SearchRequest(user_id=user_id, claim=claim, verdict=verdict))

    _run_db(db_url, op)
