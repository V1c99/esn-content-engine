"""Test fixtures. The database tests build their own schema from the migration."""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys

import asyncpg
import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from esn_engine.core.config import Settings, get_settings
from esn_engine.db.session import session_factory
from tests import helpers

# CI sets DATABASE_URL to the esn_test database it starts. Locally it points at the compose
# Postgres on 5433, and the database gets created below if it is missing.
TEST_DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql+asyncpg://esn:esn@localhost:5433/esn_test"
)
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
get_settings.cache_clear()

TABLES = "media, media_embedding, media_tag, tag, media_use, media_avoid, probe, probe_meta"


def raw_dsn(url: str) -> str:
    return url.replace("postgresql+asyncpg://", "postgresql://")


async def _ensure_database() -> None:
    name = TEST_DATABASE_URL.rsplit("/", 1)[-1]
    admin = raw_dsn(TEST_DATABASE_URL).rsplit("/", 1)[0] + "/postgres"
    connection = await asyncpg.connect(admin)
    try:
        exists = await connection.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", name)
        if not exists:
            await connection.execute(f'CREATE DATABASE "{name}"')
    finally:
        await connection.close()


async def _reseed() -> None:
    engine = create_async_engine(TEST_DATABASE_URL)
    try:
        async with session_factory(engine)() as session:
            await session.execute(text(f"TRUNCATE {TABLES} CASCADE"))
            await session.commit()
            await helpers.seed(session)
    finally:
        await engine.dispose()


@pytest.fixture(scope="session")
def library() -> str:
    """A database with the migration applied.

    The schema comes from the migration and not from create_all, because the HNSW index and
    the tag_match function only exist in the migration.
    """
    try:
        asyncio.run(_ensure_database())
    except (OSError, asyncpg.PostgresError):
        pytest.skip("no Postgres on DATABASE_URL, run: docker compose up -d db")

    finished = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        env={**os.environ, "DATABASE_URL": TEST_DATABASE_URL},
        capture_output=True,
        text=True,
        check=False,
    )
    if finished.returncode != 0:
        pytest.fail(f"alembic upgrade failed\n{finished.stdout}\n{finished.stderr}")

    return TEST_DATABASE_URL


@pytest_asyncio.fixture(scope="session")
async def seeded(library):
    """The test library, inserted once. The tests only read, so they can share it."""
    engine = create_async_engine(library)
    async with session_factory(engine)() as session:
        await session.execute(text(f"TRUNCATE {TABLES} CASCADE"))
        await session.commit()
        await helpers.seed(session)
    return True


@pytest_asyncio.fixture
async def engine(library, seeded):
    made = create_async_engine(library, pool_pre_ping=True)
    yield made
    await made.dispose()


@pytest_asyncio.fixture
async def session(engine):
    async with session_factory(engine)() as opened:
        yield opened


@pytest.fixture
def settings() -> Settings:
    return Settings(database_url=TEST_DATABASE_URL)
