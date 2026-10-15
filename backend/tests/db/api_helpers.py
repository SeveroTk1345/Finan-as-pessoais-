"""Clientes HTTP autenticados para testes de API com banco real."""

from __future__ import annotations

import secrets
from typing import Any
from uuid import UUID

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from app.core.config import Settings
from app.core.security import hash_password
from app.main import create_app

ORIGIN = "http://localhost:3000"
SAFE_HEADERS = {"Origin": ORIGIN, "X-Requested-With": "fetch"}
PASSWORD = "senha-de-teste-123"  # noqa: S105 - senha sintética só para testes


def build_app(app_engine: Engine, **overrides: Any) -> FastAPI:
    params: dict[str, Any] = {"environment": "test", "allowed_origins": ORIGIN, **overrides}
    settings = Settings(**params)
    return create_app(settings, engine=app_engine)


def set_password(admin_engine: Engine, user_id: UUID, password: str = PASSWORD) -> None:
    with admin_engine.begin() as conn:
        conn.execute(
            text("UPDATE users SET password_hash = :h WHERE id = :u"),
            {"h": hash_password(password), "u": user_id},
        )


class Api:
    """Cliente que já envia Origin, X-Requested-With e chave de idempotência."""

    def __init__(self, app: FastAPI) -> None:
        self.client = TestClient(app)

    def login(self, username: str, password: str = PASSWORD, remember: bool = False) -> Any:
        return self.client.post(
            "/api/auth/entrar",
            json={"usuario": username, "senha": password, "manter_conectado": remember},
            headers=SAFE_HEADERS,
        )

    def get(self, url: str, **kw: Any) -> Any:
        return self.client.get(url, **kw)

    def post(self, url: str, json: Any = None, *, key: str | None = "auto", **kw: Any) -> Any:
        headers = dict(SAFE_HEADERS)
        if key == "auto":
            key = secrets.token_urlsafe(18)
        if key is not None:
            headers["Idempotency-Key"] = key
        headers.update(kw.pop("headers", {}))
        return self.client.post(url, json=json, headers=headers, **kw)

    def put(self, url: str, json: Any = None, **kw: Any) -> Any:
        return self.client.put(url, json=json, headers=SAFE_HEADERS, **kw)

    def patch(self, url: str, json: Any = None, **kw: Any) -> Any:
        return self.client.patch(url, json=json, headers=SAFE_HEADERS, **kw)

    def delete(self, url: str, **kw: Any) -> Any:
        return self.client.delete(url, headers=SAFE_HEADERS, **kw)


def logged_in(app: FastAPI, admin_engine: Engine, user_id: UUID, username: str) -> Api:
    set_password(admin_engine, user_id)
    api = Api(app)
    r = api.login(username)
    assert r.status_code == 200, r.text
    return api
