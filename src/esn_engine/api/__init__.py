"""The FastAPI app. Gunicorn is pointed at `esn_engine.api:app`."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from esn_engine.api.deps import build_services
from esn_engine.api.routes import router
from esn_engine.core.config import Settings, get_settings
from esn_engine.core.logging import configure_logging

__all__ = ["app", "create_app"]


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the app. Nothing connects until the lifespan runs.

    Building it has no side effects so a test can put its own services on app.state and never
    load the 254 MB ONNX model.
    """
    resolved = settings if settings is not None else get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        configure_logging(resolved.log_level)
        app.state.services = build_services(resolved)
        try:
            yield
        finally:
            await app.state.services.engine.dispose()

    app = FastAPI(
        title="ESN Content Engine",
        version="1.0.0",
        summary="Hybrid semantic and keyword search over the ESN Bucharest media library",
        lifespan=lifespan,
    )
    app.include_router(router)
    return app


app = create_app()
