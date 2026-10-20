"""Configuração pelo navegador: criar as contas e redefinir senha onde não há terminal
(ex.: Render grátis). Protegida pelo código FIN_SETUP_TOKEN, que só o administrador
vê no painel da plataforma. Sem o código configurado, tudo aqui responde 404.

Não dá acesso a dado financeiro nenhum: só cria conta (até 3) e troca senha.
"""

from __future__ import annotations

import hmac
import re
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError

from app.api.deps import client_ip, get_engine, get_settings_dep
from app.api.errors import ApiError
from app.core.config import Settings
from app.core.security import WeakPasswordError, hash_password, validate_new_password
from app.db.identity import user_transaction
from app.services.user_setup import seed_user_defaults

router = APIRouter(prefix="/configuracao", tags=["configuração"])

MAX_USERS = 3  # o banco também impõe (migração 0007)
ATTEMPT_KEY = "(configuracao)"
USERNAME = r"^[a-z0-9._-]{3,40}$"


class StatusOut(BaseModel):
    habilitada: bool
    contas: int | None = None
    maximo: int = MAX_USERS


class CreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    codigo: str = Field(min_length=1, max_length=200)
    usuario: str = Field(min_length=3, max_length=40)
    nome: str = Field(min_length=1, max_length=60)
    senha: str = Field(min_length=1, max_length=200)


class ResetIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    codigo: str = Field(min_length=1, max_length=200)
    usuario: str = Field(min_length=3, max_length=40)
    nova_senha: str = Field(min_length=1, max_length=200)


def _enabled(settings: Settings) -> str:
    if settings.setup_token is None or not settings.setup_token.get_secret_value():
        raise ApiError(404, "A configuração pelo navegador está desligada.")
    return settings.setup_token.get_secret_value()


def _check_code(engine: Engine, settings: Settings, request: Request, code: str) -> None:
    expected = _enabled(settings)
    ip = client_ip(request)
    with engine.begin() as conn:
        _, by_ip = conn.execute(
            text("SELECT * FROM auth_recent_failures(:u, :ip, :w)"),
            {"u": ATTEMPT_KEY, "ip": ip, "w": settings.login_window_seconds},
        ).one()
    if by_ip >= settings.login_max_failures_per_ip:
        raise ApiError(429, "Muitas tentativas erradas. Espere 15 minutos e tente de novo.")
    ok = hmac.compare_digest(code.strip().encode(), expected.encode())
    if not ok:
        with engine.begin() as conn:
            conn.execute(text("SELECT auth_register_attempt(:u, :ip, false)"), {"u": ATTEMPT_KEY, "ip": ip})
        raise ApiError(403, "Código de configuração incorreto.", {"codigo": "Código incorreto."})


def _username(raw: str) -> str:
    username = raw.strip().lower()
    if not re.match(USERNAME, username):
        raise ApiError(
            422,
            "Usuário inválido: use de 3 a 40 letras minúsculas, números, ponto, hífen ou sublinhado.",
            {"usuario": "Usuário inválido."},
        )
    return username


def _password(password: str, username: str, field: str) -> str:
    try:
        validate_new_password(password, username=username)
    except WeakPasswordError as exc:
        raise ApiError(422, str(exc), {field: str(exc)}) from exc
    return hash_password(password)


@router.get("", response_model=StatusOut)
def status(
    engine: Annotated[Engine, Depends(get_engine)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
) -> StatusOut:
    if settings.setup_token is None or not settings.setup_token.get_secret_value():
        return StatusOut(habilitada=False)
    with engine.begin() as conn:
        count = int(conn.execute(text("SELECT setup_user_count()")).scalar_one())
    return StatusOut(habilitada=True, contas=count)


@router.post("/contas", status_code=201)
def create_account(
    payload: CreateIn,
    request: Request,
    engine: Annotated[Engine, Depends(get_engine)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
) -> dict[str, str]:
    _check_code(engine, settings, request, payload.codigo)
    username = _username(payload.usuario)
    password_hash = _password(payload.senha, username, "senha")
    try:
        with engine.begin() as conn:
            uid = conn.execute(
                text("SELECT setup_create_user(:u, :n, :h)"),
                {"u": username, "n": payload.nome.strip(), "h": password_hash},
            ).scalar_one()
    except DBAPIError as exc:
        code = getattr(exc.orig, "sqlstate", None)
        if code == "P0001":
            raise ApiError(409, f"Já existem {MAX_USERS} contas, o máximo deste aplicativo.") from exc
        if code == "P0002":
            raise ApiError(409, "Esse usuário já existe.", {"usuario": "Já existe."}) from exc
        raise
    with user_transaction(engine, uid) as conn:
        seed_user_defaults(conn, uid)
    return {"usuario": username, "nome": payload.nome.strip()}


@router.post("/redefinir-senha", status_code=204)
def reset_password(
    payload: ResetIn,
    request: Request,
    engine: Annotated[Engine, Depends(get_engine)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
) -> Response:
    _check_code(engine, settings, request, payload.codigo)
    username = _username(payload.usuario)
    password_hash = _password(payload.nova_senha, username, "nova_senha")
    with engine.begin() as conn:
        found = conn.execute(
            text("SELECT setup_reset_password(:u, :h)"), {"u": username, "h": password_hash}
        ).scalar_one()
    if not found:
        raise ApiError(404, "Usuário não encontrado.", {"usuario": "Não existe."})
    return Response(status_code=204)
