"""Everything the request handlers need, built once when the app starts."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from esn_engine.core.cache import Cache, build_cache
from esn_engine.core.config import Settings
from esn_engine.db.session import create_engine, session_factory
from esn_engine.embeddings.clip import TextEncoder


@dataclass
class Services:
    settings: Settings
    engine: AsyncEngine
    sessions: async_sessionmaker[AsyncSession]
    # Loading the ONNX session takes about a second, so it happens once and not per request.
    encoder: TextEncoder
    cache: Cache


def build_services(settings: Settings) -> Services:
    engine = create_engine(settings)
    return Services(
        settings=settings,
        engine=engine,
        sessions=session_factory(engine),
        encoder=TextEncoder(settings.models_dir),
        cache=build_cache(settings.redis_url),
    )


def get_services(request: Request) -> Services:
    services: Services = request.app.state.services
    return services


async def get_session(
    services: Annotated[Services, Depends(get_services)],
) -> AsyncIterator[AsyncSession]:
    async with services.sessions() as session:
        yield session


ServicesDep = Annotated[Services, Depends(get_services)]
SessionDep = Annotated[AsyncSession, Depends(get_session)]
