"""Dependências comuns: sessão autenticada e transação com identidade."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends, Request
from sqlalchemy import Connection, Engine, text

from app.api.errors import ApiError
from app.core.clock import Clock
from app.core.config import Settings
from app.core.security import hash_token
from app.db.identity import user_transaction

SESSION_COOKIE = "fin_sessao"


def get_settings_dep(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def get_engine(request: Request) -> Engine:
    engine: Engine | None = request.app.state.engine
    if engine is None:
        raise ApiError(503, "Serviço indisponível no momento. Tente de novo em instantes.")
    return engine


def get_clock(request: Request) -> Clock:
    clock: Clock = request.app.state.clock
    return clock


def client_ip(request: Request) -> str:
    # Atrás do Caddy, o IP real é o primeiro do X-Forwarded-For (o Caddy sobrescreve o
    # valor enviado pelo cliente). Em plataformas cujo proxy só acrescenta, é o último
    # (o primeiro poderia ser forjado). Sem proxy, usa o IP da conexão.
    forwarded = request.headers.get("x-forwarded-for")
    settings = request.app.state.settings
    if forwarded and settings.is_production:
        parts = [p.strip() for p in forwarded.split(",") if p.strip()]
        if parts:
            return (parts[-1] if settings.client_ip_from == "ultimo" else parts[0])[:64]
    return (request.client.host if request.client else "desconhecido")[:64]


@dataclass(frozen=True)
class CurrentUser:
    id: UUID
    token_hash: bytes


def current_user(request: Request, engine: Engine = Depends(get_engine)) -> CurrentUser:
    token = request.cookies.get(SESSION_COOKIE)
    if not token or len(token) > 200:
        raise ApiError(401, "Sua sessão terminou. Entre novamente.")
    token_hash = hash_token(token)
    with engine.begin() as conn:
        user_id = conn.execute(text("SELECT auth_session_user(:h)"), {"h": token_hash}).scalar_one_or_none()
    if user_id is None:
        raise ApiError(401, "Sua sessão terminou. Entre novamente.")
    return CurrentUser(id=user_id, token_hash=token_hash)


@dataclass(frozen=True)
class UserDb:
    """Acesso ao banco em nome do usuário da sessão.

    O endpoint abre a transação com ``with db.tx() as conn:`` e só responde depois
    do ``with``. Assim o COMMIT acontece antes da resposta: se a gravação falhar, o
    usuário recebe erro, nunca uma confirmação falsa.
    """

    engine: Engine
    user_id: UUID

    @contextmanager
    def tx(self) -> Iterator[Connection]:
        with user_transaction(self.engine, self.user_id) as conn:
            yield conn


def user_db(user: CurrentUser = Depends(current_user), engine: Engine = Depends(get_engine)) -> UserDb:
    return UserDb(engine=engine, user_id=user.id)
