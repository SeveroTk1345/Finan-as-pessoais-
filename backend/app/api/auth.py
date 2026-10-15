from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Engine, text

from app.api.deps import (
    SESSION_COOKIE,
    CurrentUser,
    client_ip,
    current_user,
    get_clock,
    get_engine,
    get_settings_dep,
)
from app.api.errors import ApiError
from app.core.clock import Clock
from app.core.config import Settings
from app.core.security import WeakPasswordError
from app.db.identity import user_transaction
from app.services import auth as auth_service

router = APIRouter(prefix="/auth", tags=["autenticação"])


class LoginIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    usuario: str = Field(min_length=1, max_length=100)
    senha: str = Field(min_length=1, max_length=200)
    manter_conectado: bool = False


class MeOut(BaseModel):
    id: str
    usuario: str
    nome: str


class ChangePasswordIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    senha_atual: str = Field(min_length=1, max_length=200)
    nova_senha: str = Field(min_length=1, max_length=200)


def _me(engine: Engine, user: CurrentUser) -> MeOut:
    with user_transaction(engine, user.id) as conn:
        row = conn.execute(
            text("SELECT id, username, display_name FROM users WHERE id = :u"), {"u": user.id}
        ).one()
    return MeOut(id=str(row.id), usuario=row.username, nome=row.display_name)


@router.post("/entrar", response_model=MeOut)
def entrar(
    payload: LoginIn,
    request: Request,
    response: Response,
    engine: Annotated[Engine, Depends(get_engine)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
    clock: Annotated[Clock, Depends(get_clock)],
) -> MeOut:
    try:
        session = auth_service.login(
            engine,
            settings,
            clock,
            username=payload.usuario,
            password=payload.senha,
            remember=payload.manter_conectado,
            ip=client_ip(request),
        )
    except auth_service.LoginBlockedError as exc:
        raise ApiError(
            429, "Muitas tentativas erradas. Espere 15 minutos e tente de novo."
        ) from exc
    except auth_service.InvalidCredentialsError as exc:
        # Mesma mensagem para usuário inexistente e senha errada.
        raise ApiError(401, "Usuário ou senha incorretos.") from exc

    response.set_cookie(
        SESSION_COOKIE,
        session.token,
        max_age=session.max_age_seconds,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
        path="/api",
    )
    return _me(engine, CurrentUser(id=session.user_id, token_hash=b""))


@router.post("/sair", status_code=204)
def sair(
    response: Response,
    engine: Annotated[Engine, Depends(get_engine)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
    user: Annotated[CurrentUser, Depends(current_user)],
) -> Response:
    auth_service.logout(engine, user.id, user.token_hash)
    response.status_code = 204
    response.delete_cookie(
        SESSION_COOKIE, path="/api", httponly=True, secure=settings.cookie_secure, samesite="strict"
    )
    return response


@router.get("/eu", response_model=MeOut)
def eu(
    engine: Annotated[Engine, Depends(get_engine)],
    user: Annotated[CurrentUser, Depends(current_user)],
) -> MeOut:
    return _me(engine, user)


@router.post("/trocar-senha", status_code=204)
def trocar_senha(
    payload: ChangePasswordIn,
    engine: Annotated[Engine, Depends(get_engine)],
    user: Annotated[CurrentUser, Depends(current_user)],
) -> Response:
    try:
        auth_service.change_password(
            engine, user.id, user.token_hash, current=payload.senha_atual, new=payload.nova_senha
        )
    except auth_service.InvalidCredentialsError as exc:
        raise ApiError(
            400, "A senha atual está incorreta.", {"senha_atual": "Senha incorreta."}
        ) from exc
    except WeakPasswordError as exc:
        raise ApiError(400, str(exc), {"nova_senha": str(exc)}) from exc
    return Response(status_code=204)
