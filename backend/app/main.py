from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse, Response
from sqlalchemy import Engine
from sqlalchemy.pool import NullPool

from app.api import auth, health, setup
from app.api.errors import install_error_handlers
from app.api.middleware import install_middleware
from app.api.routes import register_routes
from app.core.clock import Clock, SystemClock
from app.core.config import Settings, get_settings
from app.db.engine import make_engine

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")


def create_app(
    settings: Settings | None = None, *, engine: Engine | None = None, clock: Clock | None = None
) -> FastAPI:
    settings = settings or get_settings()
    if engine is None and settings.database_url is not None:
        url = settings.database_url.get_secret_value()
        if settings.db_keep_connections:
            engine = make_engine(url, pool_size=5, max_overflow=5)
        else:
            engine = make_engine(url, poolclass=NullPool)

    # Documentação interativa só fora de produção.
    docs_enabled = not settings.is_production
    app = FastAPI(
        title="Finanças Pessoais",
        version=settings.app_version,
        docs_url="/api/docs" if docs_enabled else None,
        redoc_url=None,
        openapi_url="/api/openapi.json" if docs_enabled else None,
    )
    app.state.settings = settings
    app.state.engine = engine
    app.state.clock = clock or SystemClock()

    install_error_handlers(app)
    install_middleware(app, settings)
    app.include_router(health.router, prefix="/api")
    app.include_router(auth.router, prefix="/api")
    app.include_router(setup.router, prefix="/api")
    register_routes(app)

    if settings.static_dir is not None:
        _serve_static(app, settings.static_dir)
    return app


def _serve_static(app: FastAPI, root: Path) -> None:
    """Serve o site exportado pelo Next.js na mesma origem da API."""
    root = root.resolve()

    # GET e HEAD: o roteador do Next.js usa HEAD para pré-carregar páginas.
    @app.api_route("/{path:path}", methods=["GET", "HEAD"], include_in_schema=False)
    def static(path: str) -> Response:
        if path.startswith("api/") or path == "api":
            return JSONResponse({"detail": "Não encontrado."}, status_code=404)
        candidate = (root / path).resolve()
        if not candidate.is_relative_to(root):
            return JSONResponse({"detail": "Não encontrado."}, status_code=404)
        for option in (candidate, candidate / "index.html", candidate.with_suffix(".html")):
            if option.is_file():
                headers = {}
                if option.name == "sw.js" or option.suffix == ".html":
                    headers["Cache-Control"] = "no-cache"
                elif "/_next/static/" in str(option):
                    headers["Cache-Control"] = "public, max-age=31536000, immutable"
                return FileResponse(option, headers=headers)
        not_found = root / "404.html"
        if not_found.is_file():
            return FileResponse(not_found, status_code=404)
        return JSONResponse({"detail": "Não encontrado."}, status_code=404)


app = create_app()
