from __future__ import annotations

from fastapi import FastAPI

from app.api import health
from app.core.config import Settings, get_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    # Documentação interativa só fora de produção.
    docs_enabled = not settings.is_production
    app = FastAPI(
        title="Finanças Pessoais",
        version=settings.app_version,
        docs_url="/api/docs" if docs_enabled else None,
        redoc_url=None,
        openapi_url="/api/openapi.json" if docs_enabled else None,
    )
    app.include_router(health.router, prefix="/api")
    return app


app = create_app()
