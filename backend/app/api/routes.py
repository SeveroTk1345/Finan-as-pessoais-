"""Registro das rotas dos módulos financeiros."""

from __future__ import annotations

from fastapi import FastAPI

from app.api import card_debt_routes, core_routes, plan_routes


def register_routes(app: FastAPI) -> None:
    app.include_router(core_routes.router, prefix="/api")
    app.include_router(card_debt_routes.router, prefix="/api")
    app.include_router(plan_routes.router, prefix="/api")
