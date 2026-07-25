"""Engine and session factory."""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from esn_engine.core.config import Settings


def create_engine(settings: Settings) -> AsyncEngine:
    return create_async_engine(settings.database_url, pool_pre_ping=True)


def session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


async def open_session(factory: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncSession]:
    """One session per request.

    This has to yield and not return. If it returns, the handler gets a session that is
    already closed. It seemed to work locally and then failed with two workers.
    """
    async with factory() as session:
        yield session
