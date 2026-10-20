"""Entrar com digital ou rosto (passkeys, WebAuthn).

O aparelho guarda a chave privada e só a usa depois de confirmar a digital, o rosto
ou o PIN do próprio aparelho. O servidor guarda a chave pública e confere a
assinatura de um desafio aleatório de uso único. Nenhum dado biométrico chega aqui.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID

from sqlalchemy import Engine, text
from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import parse_authentication_credential_json
from webauthn.helpers.exceptions import WebAuthnException
from webauthn.helpers.structs import (
    AuthenticatorAttachment,
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from app.core.config import Settings
from app.db.identity import user_transaction
from app.services.auth import LoginBlockedError, NewSession, create_session

# Chave usada no registro de tentativas: falhas de passkey contam só por IP (o
# usuário ainda é desconhecido), sem bloquear a senha de ninguém.
ATTEMPT_KEY = "(digital)"


class PasskeyError(Exception):
    """Falha de verificação. A mensagem é segura para mostrar."""


@dataclass(frozen=True)
class Challenge:
    id: UUID
    options: dict[str, Any]


def rp_id_for(settings: Settings, origin: str) -> str:
    if settings.webauthn_rp_id:
        return settings.webauthn_rp_id
    host = urlsplit(origin).hostname
    if not host:
        raise PasskeyError("Endereço do site inválido para entrar com digital ou rosto.")
    return host


def _new_challenge(
    engine: Engine, settings: Settings, purpose: str, user_id: UUID | None, raw: bytes
) -> UUID:
    with engine.begin() as conn:
        return UUID(
            str(
                conn.execute(
                    text("SELECT auth_challenge_new(:p, :u, :c, :t)"),
                    {"p": purpose, "u": user_id, "c": raw, "t": settings.webauthn_challenge_seconds},
                ).scalar_one()
            )
        )


def _take_challenge(engine: Engine, challenge_id: UUID, purpose: str) -> tuple[bytes, UUID | None]:
    with engine.begin() as conn:
        row = conn.execute(
            text("SELECT * FROM auth_challenge_take(:i, :p)"), {"i": challenge_id, "p": purpose}
        ).one_or_none()
    if row is None:
        raise PasskeyError("O pedido expirou. Tente de novo.")
    return bytes(row.challenge), row.user_id


# ---------- cadastro (pessoa já conectada) ----------


def registration_options(engine: Engine, settings: Settings, user_id: UUID, origin: str) -> Challenge:
    with user_transaction(engine, user_id) as conn:
        user = conn.execute(
            text("SELECT username, display_name FROM users WHERE id = :u"), {"u": user_id}
        ).one()
        existing = conn.execute(
            text("SELECT credential_id FROM passkeys WHERE owner_id = :u"), {"u": user_id}
        ).scalars()
        exclude = [PublicKeyCredentialDescriptor(id=bytes(c)) for c in existing]
    opts = generate_registration_options(
        rp_id=rp_id_for(settings, origin),
        rp_name=settings.webauthn_rp_name,
        user_id=user_id.bytes,
        user_name=user.username,
        user_display_name=user.display_name,
        timeout=settings.webauthn_challenge_seconds * 1000,
        # Sensor do próprio aparelho (digital, rosto ou PIN dele), com credencial
        # guardada no aparelho para entrar sem digitar o usuário.
        authenticator_selection=AuthenticatorSelectionCriteria(
            authenticator_attachment=AuthenticatorAttachment.PLATFORM,
            resident_key=ResidentKeyRequirement.REQUIRED,
            user_verification=UserVerificationRequirement.REQUIRED,
        ),
        exclude_credentials=exclude,
    )
    cid = _new_challenge(engine, settings, "cadastro", user_id, opts.challenge)

    return Challenge(id=cid, options=json.loads(options_to_json(opts)))


def register(
    engine: Engine,
    settings: Settings,
    user_id: UUID,
    origin: str,
    *,
    challenge_id: UUID,
    credential: dict[str, Any],
    device_name: str,
) -> dict[str, Any]:
    raw, owner = _take_challenge(engine, challenge_id, "cadastro")
    if owner != user_id:
        # Desafio pedido por outra pessoa: trata como inexistente.
        raise PasskeyError("O pedido expirou. Tente de novo.")
    try:
        verified = verify_registration_response(
            credential=credential,
            expected_challenge=raw,
            expected_rp_id=rp_id_for(settings, origin),
            expected_origin=sorted(settings.origins),
            require_user_verification=True,
        )
    except (WebAuthnException, ValueError, KeyError, TypeError) as exc:
        raise PasskeyError("Não foi possível ativar neste aparelho. Tente de novo.") from exc
    with user_transaction(engine, user_id) as conn:
        if conn.execute(
            text("SELECT 1 FROM passkeys WHERE credential_id = :c"), {"c": verified.credential_id}
        ).first():
            raise PasskeyError("Este aparelho já está ativado.")
        row = conn.execute(
            text(
                "INSERT INTO passkeys (owner_id, credential_id, public_key, sign_count, device_name) "
                "VALUES (:o, :c, :k, :s, :n) RETURNING id, device_name, created_at, last_used_at"
            ),
            {
                "o": user_id,
                "c": verified.credential_id,
                "k": verified.credential_public_key,
                "s": verified.sign_count,
                "n": device_name.strip()[:60] or "Aparelho",
            },
        ).one()
    return _out(row)


def list_passkeys(engine: Engine, user_id: UUID) -> list[dict[str, Any]]:
    with user_transaction(engine, user_id) as conn:
        rows = conn.execute(
            text(
                "SELECT id, device_name, created_at, last_used_at FROM passkeys "
                "WHERE owner_id = :u ORDER BY created_at"
            ),
            {"u": user_id},
        ).all()
    return [_out(r) for r in rows]


def remove(engine: Engine, user_id: UUID, passkey_id: UUID) -> bool:
    with user_transaction(engine, user_id) as conn:
        return (
            conn.execute(
                text("DELETE FROM passkeys WHERE id = :i AND owner_id = :u"), {"i": passkey_id, "u": user_id}
            ).rowcount
            == 1
        )


def _out(row: Any) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "nome": row.device_name,
        "criada_em": row.created_at.date().isoformat(),
        "usada_em": row.last_used_at.date().isoformat() if row.last_used_at else None,
    }


# ---------- entrar (ninguém conectado ainda) ----------


def _check_blocked(engine: Engine, settings: Settings, ip: str) -> None:
    with engine.begin() as conn:
        _, by_ip = conn.execute(
            text("SELECT * FROM auth_recent_failures(:u, :ip, :w)"),
            {"u": ATTEMPT_KEY, "ip": ip, "w": settings.login_window_seconds},
        ).one()
    if by_ip >= settings.login_max_failures_per_ip:
        raise LoginBlockedError


def _register_attempt(engine: Engine, ip: str, ok: bool) -> None:
    with engine.begin() as conn:
        conn.execute(text("SELECT auth_register_attempt(:u, :ip, :s)"), {"u": ATTEMPT_KEY, "ip": ip, "s": ok})


def login_options(engine: Engine, settings: Settings, origin: str, ip: str) -> Challenge:
    _check_blocked(engine, settings, ip)

    opts = generate_authentication_options(
        rp_id=rp_id_for(settings, origin),
        timeout=settings.webauthn_challenge_seconds * 1000,
        user_verification=UserVerificationRequirement.REQUIRED,
    )
    cid = _new_challenge(engine, settings, "entrar", None, opts.challenge)
    return Challenge(id=cid, options=json.loads(options_to_json(opts)))


def login(
    engine: Engine,
    settings: Settings,
    origin: str,
    ip: str,
    *,
    challenge_id: UUID,
    credential: dict[str, Any],
    remember: bool,
) -> NewSession:
    _check_blocked(engine, settings, ip)
    try:
        raw, _ = _take_challenge(engine, challenge_id, "entrar")
        parsed = parse_authentication_credential_json(credential)
        with engine.begin() as conn:
            row = conn.execute(
                text("SELECT * FROM auth_passkey_lookup(:c)"), {"c": parsed.raw_id}
            ).one_or_none()
        if row is None or not row.is_active:
            raise PasskeyError("Este aparelho não está ativado. Entre com usuário e senha.")
        handle = parsed.response.user_handle
        if handle is not None and handle != UUID(str(row.user_id)).bytes:
            raise PasskeyError("Não foi possível confirmar. Entre com usuário e senha.")
        verified = verify_authentication_response(
            credential=parsed,
            expected_challenge=raw,
            expected_rp_id=rp_id_for(settings, origin),
            expected_origin=sorted(settings.origins),
            credential_public_key=bytes(row.public_key),
            credential_current_sign_count=int(row.sign_count),
            require_user_verification=True,
        )
    except PasskeyError:
        _register_attempt(engine, ip, False)
        raise
    except (WebAuthnException, ValueError, KeyError, TypeError) as exc:
        _register_attempt(engine, ip, False)
        raise PasskeyError("Não foi possível confirmar. Entre com usuário e senha.") from exc

    with engine.begin() as conn:
        conn.execute(
            text("SELECT auth_passkey_used(:i, :s)"), {"i": row.passkey_id, "s": verified.new_sign_count}
        )
    _register_attempt(engine, ip, True)
    return create_session(engine, settings, row.user_id, remember=remember)
