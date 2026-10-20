"""Linha de comando do administrador do servidor.

Cria contas, redefine senhas e lista nomes de usuário. Não existe comando para ver
dados financeiros de ninguém.

Uso (no servidor, com FIN_DATABASE_ADMIN_URL definida):
    python -m app.cli criar-usuario --usuario ana --nome "Ana"
    python -m app.cli redefinir-senha --usuario ana
    python -m app.cli listar-usuarios
    python -m app.cli desativar-usuario --usuario ana

A senha é pedida no terminal (sem aparecer na tela). Para automação e testes,
``--senha-stdin`` lê a senha da entrada padrão.
"""

from __future__ import annotations

import argparse
import getpass
import os
import sys
from collections.abc import Sequence

from sqlalchemy import Connection, Engine, create_engine, text

from app.core.config import normalize_database_url
from app.core.security import WeakPasswordError, hash_password, validate_new_password
from app.services.user_setup import seed_user_defaults


def _engine() -> Engine:
    url = os.environ.get("FIN_DATABASE_ADMIN_URL")
    if not url:
        raise SystemExit("Defina FIN_DATABASE_ADMIN_URL.")
    return create_engine(normalize_database_url(url))


def _read_password(username: str, from_stdin: bool) -> str:
    if from_stdin:
        password = sys.stdin.readline().rstrip("\n")
    else:
        password = getpass.getpass("Nova senha: ")
        if getpass.getpass("Repita a senha: ") != password:
            raise SystemExit("As senhas não conferem.")
    try:
        validate_new_password(password, username=username)
    except WeakPasswordError as exc:
        raise SystemExit(str(exc)) from exc
    return password


def _user_id(conn: Connection, username: str) -> object:
    uid = conn.execute(text("SELECT id FROM users WHERE username = :u"), {"u": username}).scalar()
    if uid is None:
        raise SystemExit(f"Usuário {username!r} não existe.")
    return uid


def criar_usuario(engine: Engine, username: str, nome: str, from_stdin: bool) -> None:
    username = username.strip().lower()
    password = _read_password(username, from_stdin)
    with engine.begin() as conn:
        if conn.execute(text("SELECT 1 FROM users WHERE username = :u"), {"u": username}).scalar():
            raise SystemExit(f"Usuário {username!r} já existe.")
        uid = conn.execute(
            text(
                "INSERT INTO users (username, display_name, password_hash, password_changed_at) "
                "VALUES (:u, :n, :h, now()) RETURNING id"
            ),
            {"u": username, "n": nome.strip(), "h": hash_password(password)},
        ).scalar_one()
        seed_user_defaults(conn, uid)
    print(f"Usuário {username!r} criado.")


def redefinir_senha(engine: Engine, username: str, from_stdin: bool) -> None:
    username = username.strip().lower()
    password = _read_password(username, from_stdin)
    with engine.begin() as conn:
        uid = _user_id(conn, username)
        conn.execute(
            text("UPDATE users SET password_hash = :h, password_changed_at = now() WHERE id = :u"),
            {"h": hash_password(password), "u": uid},
        )
        # Encerra todas as sessões abertas desse usuário (e só dele).
        conn.execute(text("DELETE FROM sessions WHERE owner_id = :u"), {"u": uid})
    print(f"Senha de {username!r} redefinida. As sessões abertas foram encerradas.")


def desativar_usuario(engine: Engine, username: str) -> None:
    with engine.begin() as conn:
        uid = _user_id(conn, username.strip().lower())
        conn.execute(text("UPDATE users SET is_active = false WHERE id = :u"), {"u": uid})
        conn.execute(text("DELETE FROM sessions WHERE owner_id = :u"), {"u": uid})
    print("Usuário desativado.")


def listar_usuarios(engine: Engine) -> None:
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT username, display_name, is_active FROM users ORDER BY username")
        ).all()
    for r in rows:
        print(f"{r.username}\t{r.display_name}\t{'ativo' if r.is_active else 'desativado'}")


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("criar-usuario")
    p.add_argument("--usuario", required=True)
    p.add_argument("--nome", required=True)
    p.add_argument("--senha-stdin", action="store_true")
    p = sub.add_parser("redefinir-senha")
    p.add_argument("--usuario", required=True)
    p.add_argument("--senha-stdin", action="store_true")
    p = sub.add_parser("desativar-usuario")
    p.add_argument("--usuario", required=True)
    sub.add_parser("listar-usuarios")
    args = parser.parse_args(argv)

    engine = _engine()
    try:
        if args.cmd == "criar-usuario":
            criar_usuario(engine, args.usuario, args.nome, args.senha_stdin)
        elif args.cmd == "redefinir-senha":
            redefinir_senha(engine, args.usuario, args.senha_stdin)
        elif args.cmd == "desativar-usuario":
            desativar_usuario(engine, args.usuario)
        else:
            listar_usuarios(engine)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
