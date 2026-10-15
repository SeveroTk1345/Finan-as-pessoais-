"""Registro das rotas dos módulos financeiros."""

from __future__ import annotations

from fastapi import FastAPI

from app.api import core_routes


def register_routes(app: FastAPI) -> None:
    app.include_router(core_routes.router, prefix="/api")
