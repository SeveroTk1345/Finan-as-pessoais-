from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Engine, text

from app.api.deps import (
    SESSION_COOKIE,
    CurrentUser,
    client_ip,
    current_user,
    get_engine,
    get_settings_dep,
)
from app.api.errors import ApiError, not_found
from app.core.config import Settings
from app.core.security import WeakPasswordError
from app.db.identity import user_transaction
from app.services import auth as auth_service
from app.services import passkeys

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
) -> MeOut:
    try:
        session = auth_service.login(
            engine,
            settings,
            username=payload.usuario,
            password=payload.senha,
            remember=payload.manter_conectado,
            ip=client_ip(request),
        )
    except auth_service.LoginBlockedError as exc:
        raise ApiError(429, "Muitas tentativas erradas. Espere 15 minutos e tente de novo.") from exc
    except auth_service.InvalidCredentialsError as exc:
        # Mesma mensagem para usuário inexistente e senha errada.
        raise ApiError(401, "Usuário ou senha incorretos.") from exc

    _set_session_cookie(response, settings, session)
    return _me(engine, CurrentUser(id=session.user_id, token_hash=b""))


def _set_session_cookie(response: Response, settings: Settings, session: auth_service.NewSession) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        session.token,
        max_age=session.max_age_seconds,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
        path="/api",
    )


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
        raise ApiError(400, "A senha atual está incorreta.", {"senha_atual": "Senha incorreta."}) from exc
    except WeakPasswordError as exc:
        raise ApiError(400, str(exc), {"nova_senha": str(exc)}) from exc
    return Response(status_code=204)


# ---------- Entrar com digital ou rosto (passkeys) ----------
# Os POST abaixo só chegam aqui com Origin permitida (proteção CSRF no middleware);
# essa mesma origem define o domínio ao qual a credencial fica presa.


class ChallengeOut(BaseModel):
    desafio_id: str
    opcoes: dict[str, Any]


class PasskeyRegisterIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    desafio_id: UUID
    credencial: dict[str, Any]
    nome_aparelho: str = Field(min_length=1, max_length=60)


class PasskeyLoginIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    desafio_id: UUID
    credencial: dict[str, Any]
    manter_conectado: bool = False


class PasskeyOut(BaseModel):
    id: str
    nome: str
    criada_em: str
    usada_em: str | None


def _origin(request: Request) -> str:
    return (request.headers.get("origin") or "").rstrip("/")


@router.get("/digital", response_model=list[PasskeyOut])
def digital_listar(
    engine: Annotated[Engine, Depends(get_engine)],
    user: Annotated[CurrentUser, Depends(current_user)],
) -> list[dict[str, Any]]:
    return passkeys.list_passkeys(engine, user.id)


@router.post("/digital/cadastro/opcoes", response_model=ChallengeOut)
def digital_cadastro_opcoes(
    request: Request,
    engine: Annotated[Engine, Depends(get_engine)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
    user: Annotated[CurrentUser, Depends(current_user)],
) -> ChallengeOut:
    ch = passkeys.registration_options(engine, settings, user.id, _origin(request))
    return ChallengeOut(desafio_id=str(ch.id), opcoes=ch.options)


@router.post("/digital/cadastro", response_model=PasskeyOut, status_code=201)
def digital_cadastro(
    payload: PasskeyRegisterIn,
    request: Request,
    engine: Annotated[Engine, Depends(get_engine)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
    user: Annotated[CurrentUser, Depends(current_user)],
) -> dict[str, Any]:
    try:
        return passkeys.register(
            engine,
            settings,
            user.id,
            _origin(request),
            challenge_id=payload.desafio_id,
            credential=payload.credencial,
            device_name=payload.nome_aparelho,
        )
    except passkeys.PasskeyError as exc:
        raise ApiError(400, str(exc)) from exc


@router.delete("/digital/{passkey_id}", status_code=204)
def digital_remover(
    passkey_id: UUID,
    engine: Annotated[Engine, Depends(get_engine)],
    user: Annotated[CurrentUser, Depends(current_user)],
) -> Response:
    if not passkeys.remove(engine, user.id, passkey_id):
        raise not_found("Aparelho")
    return Response(status_code=204)


@router.post("/digital/entrar/opcoes", response_model=ChallengeOut)
def digital_entrar_opcoes(
    request: Request,
    engine: Annotated[Engine, Depends(get_engine)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
) -> ChallengeOut:
    try:
        ch = passkeys.login_options(engine, settings, _origin(request), client_ip(request))
    except auth_service.LoginBlockedError as exc:
        raise ApiError(429, "Muitas tentativas erradas. Espere 15 minutos e tente de novo.") from exc
    return ChallengeOut(desafio_id=str(ch.id), opcoes=ch.options)


@router.post("/digital/entrar", response_model=MeOut)
def digital_entrar(
    payload: PasskeyLoginIn,
    request: Request,
    response: Response,
    engine: Annotated[Engine, Depends(get_engine)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
) -> MeOut:
    try:
        session = passkeys.login(
            engine,
            settings,
            _origin(request),
            client_ip(request),
            challenge_id=payload.desafio_id,
            credential=payload.credencial,
            remember=payload.manter_conectado,
        )
    except auth_service.LoginBlockedError as exc:
        raise ApiError(429, "Muitas tentativas erradas. Espere 15 minutos e tente de novo.") from exc
    except passkeys.PasskeyError as exc:
        raise ApiError(401, str(exc)) from exc
    _set_session_cookie(response, settings, session)
    return _me(engine, CurrentUser(id=session.user_id, token_hash=b""))
