"""Fixtures de API com os três usuários já conectados."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from sqlalchemy import Engine, text

from app.core.clock import FixedClock
from app.core.config import Settings
from app.main import create_app
from tests.db.api_helpers import ORIGIN, Api, logged_in
from tests.db.conftest import Users

# Hoje, para todos os testes de API: 15/10/2026 (meio-dia em São Paulo).
NOW = datetime(2026, 10, 15, 15, 0, tzinfo=UTC)


@dataclass
class Trio:
    ana: Api
    bruno: Api
    carla: Api

    def pairs(self) -> list[tuple[str, Api, str, Api]]:
        named = [("ana", self.ana), ("bruno", self.bruno), ("carla", self.carla)]
        return [(an, a, vn, v) for an, a in named for vn, v in named if an != vn]


@pytest.fixture
def api_app(app_engine: Engine, admin_engine: Engine) -> FastAPI:
    with admin_engine.begin() as conn:
        conn.execute(text("DELETE FROM login_attempts"))
    settings = Settings(environment="test", allowed_origins=ORIGIN)
    return create_app(settings, engine=app_engine, clock=FixedClock(NOW))


@pytest.fixture
def trio(api_app: FastAPI, admin_engine: Engine, users: Users) -> Trio:
    from app.services.user_setup import seed_user_defaults

    with admin_engine.begin() as conn:
        for uid in users.all():
            seed_user_defaults(conn, uid)
    return Trio(
        ana=logged_in(api_app, admin_engine, users.ana, "ana"),
        bruno=logged_in(api_app, admin_engine, users.bruno, "bruno"),
        carla=logged_in(api_app, admin_engine, users.carla, "carla"),
    )


def category_id(api: Api, name: str, kind: str = "despesa") -> str:
    for c in api.get("/api/categorias").json():
        if c["name"] == name and c["kind"] == kind:
            return str(c["id"])
    raise AssertionError(f"categoria {name} não encontrada")


def new_account(
    api: Api,
    name: str = "Conta Corrente",
    balance: int = 100000,
    kind: str = "corrente",
    on: str = "2026-10-01",
) -> str:
    r = api.post(
        "/api/contas",
        {"name": name, "kind": kind, "initial_balance_cents": balance, "initial_balance_date": on},
    )
    assert r.status_code == 201, r.text
    return str(r.json()["id"])


def balance(api: Api, account_id: str) -> int:
    return int(api.get(f"/api/contas/{account_id}").json()["balance_cents"])
