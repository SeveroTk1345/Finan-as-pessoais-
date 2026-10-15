"""Casos de uso de autenticação."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID

from sqlalchemy import Engine, text

from app.core.clock import Clock
from app.core.config import Settings
from app.core.security import (
    hash_password,
    hash_token,
    new_session_token,
    validate_new_password,
    verify_password,
)
from app.db.identity import user_transaction


class LoginBlockedError(Exception):
    pass


class InvalidCredentialsError(Exception):
    pass


@dataclass(frozen=True)
class NewSession:
    token: str
    user_id: UUID
    max_age_seconds: int | None  # None: cookie de sessão do navegador


def login(
    engine: Engine,
    settings: Settings,
    clock: Clock,
    *,
    username: str,
    password: str,
    remember: bool,
    ip: str,
) -> NewSession:
    username = username.strip().lower()
    with engine.begin() as conn:
        by_user, by_ip = conn.execute(
            text("SELECT * FROM auth_recent_failures(:u, :ip, :w)"),
            {"u": username, "ip": ip, "w": settings.login_window_seconds},
        ).one()
    if by_user >= settings.login_max_failures_per_user or by_ip >= settings.login_max_failures_per_ip:
        raise LoginBlockedError

    with engine.begin() as conn:
        row = conn.execute(text("SELECT * FROM auth_login_lookup(:u)"), {"u": username}).one_or_none()
    ok = verify_password(row.password_hash if row else None, password)
    ok = ok and row is not None and bool(row.is_active)

    with engine.begin() as conn:
        conn.execute(
            text("SELECT auth_register_attempt(:u, :ip, :s)"),
            {"u": username, "ip": ip, "s": ok},
        )
    if not ok or row is None:
        raise InvalidCredentialsError

    if remember:
        max_s, idle_s = (
            settings.session_remember_max_seconds,
            settings.session_remember_idle_seconds,
        )
    else:
        max_s, idle_s = settings.session_short_max_seconds, settings.session_short_idle_seconds
    token = new_session_token()
    now = clock.now_utc()
    with user_transaction(engine, row.user_id) as conn:
        conn.execute(
            text(
                "INSERT INTO sessions (owner_id, token_hash, remember, created_at, last_seen_at, "
                "expires_at, idle_timeout_seconds) VALUES (:o, :h, :r, :n, :n, :e, :i)"
            ),
            {
                "o": row.user_id,
                "h": hash_token(token),
                "r": remember,
                "n": now,
                "e": now + timedelta(seconds=max_s),
                "i": idle_s,
            },
        )
    return NewSession(token=token, user_id=row.user_id, max_age_seconds=max_s if remember else None)


def logout(engine: Engine, user_id: UUID, token_hash: bytes) -> None:
    with user_transaction(engine, user_id) as conn:
        conn.execute(text("DELETE FROM sessions WHERE token_hash = :h"), {"h": token_hash})


def change_password(engine: Engine, user_id: UUID, token_hash: bytes, *, current: str, new: str) -> None:
    """Troca a senha e encerra as outras sessões do mesmo usuário (as dos outros
    usuários não são afetadas)."""
    with user_transaction(engine, user_id) as conn:
        row = conn.execute(
            text("SELECT username, password_hash FROM users WHERE id = :u"), {"u": user_id}
        ).one()
        if not verify_password(row.password_hash, current):
            raise InvalidCredentialsError
        validate_new_password(new, username=row.username)
        conn.execute(
            text("UPDATE users SET password_hash = :h, password_changed_at = now() WHERE id = :u"),
            {"h": hash_password(new), "u": user_id},
        )
        conn.execute(
            text("DELETE FROM sessions WHERE owner_id = :u AND token_hash <> :t"),
            {"u": user_id, "t": token_hash},
        )
