"""Senhas e tokens de sessão."""

from __future__ import annotations

import hashlib
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

# Parâmetros padrão do argon2-cffi (Argon2id, RFC 9106 perfil de baixa memória).
_hasher = PasswordHasher()

MIN_PASSWORD_LENGTH = 10
MAX_PASSWORD_LENGTH = 200

# Hash válido usado quando o usuário não existe, para o tempo de resposta não revelar
# se um nome de usuário existe.
_DUMMY_HASH = _hasher.hash(secrets.token_urlsafe(16))


class WeakPasswordError(ValueError):
    pass


def validate_new_password(password: str, *, username: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise WeakPasswordError(f"A senha precisa ter pelo menos {MIN_PASSWORD_LENGTH} caracteres.")
    if len(password) > MAX_PASSWORD_LENGTH:
        raise WeakPasswordError("A senha é longa demais.")
    if username and username.lower() in password.lower():
        raise WeakPasswordError("A senha não pode conter o nome de usuário.")
    if len(set(password)) < 4:
        raise WeakPasswordError("A senha tem caracteres repetidos demais.")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    """Confere a senha. Com ``password_hash`` ausente, gasta o mesmo tempo e retorna False."""
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def new_session_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> bytes:
    """Só o SHA-256 do token vai para o banco: um vazamento do banco não dá acesso."""
    return hashlib.sha256(token.encode("utf-8")).digest()
