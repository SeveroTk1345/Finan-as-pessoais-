"""As migrações sobem, descem e sobem de novo em um banco vazio."""

from __future__ import annotations

import secrets
from collections.abc import Iterator

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text

from tests.db.conftest import BACKEND_DIR, DbInfo

HEAD = "0006"


@pytest.fixture
def empty_db(test_db: DbInfo) -> Iterator[str]:
    name = f"fin_mig_{secrets.token_hex(4)}"
    server = create_engine(test_db.admin_url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with server.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{name}"'))
    try:
        yield name
    finally:
        with server.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        server.dispose()


def _tables(engine: Engine) -> list[str]:
    with engine.connect() as conn:
        return list(
            conn.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY 1")
            ).scalars()
        )


def test_upgrade_downgrade_upgrade(test_db: DbInfo, empty_db: str) -> None:
    url = test_db.admin_url.set(database=empty_db)
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.attributes["url"] = url.render_as_string(False)
    engine = create_engine(url)
    try:
        command.upgrade(cfg, "head")
        assert set(_tables(engine)) >= {"accounts", "alembic_version", "users"}
        command.downgrade(cfg, "base")
        assert _tables(engine) == ["alembic_version"]
        command.upgrade(cfg, "head")
        assert set(_tables(engine)) >= {"accounts", "alembic_version", "users"}
        with engine.connect() as conn:
            assert conn.execute(text("SELECT version_num FROM alembic_version")).scalar() == HEAD
    finally:
        engine.dispose()


def test_restricoes_da_tabela_accounts(admin_engine: Engine) -> None:
    """Validações no banco, além das da API: o banco é a última barreira."""
    bad_values = [
        "('', 'corrente', 1)",  # nome vazio
        "('   ', 'corrente', 1)",  # só espaços
        "('x', 'cartao', 1)",  # tipo inexistente
        "('x', 'corrente', 100000000000001)",  # acima do limite
    ]
    with admin_engine.begin() as conn:
        owner = conn.execute(
            text(
                "INSERT INTO users (username, display_name, password_hash) "
                "VALUES ('teste_restricao', 'T', '!') RETURNING id"
            )
        ).scalar_one()
    try:
        for values in bad_values:
            with (
                pytest.raises(Exception, match="violates check constraint"),
                admin_engine.begin() as conn,
            ):
                conn.execute(
                    text(
                        "INSERT INTO accounts (owner_id, name, kind, initial_balance_cents, "
                        f"initial_balance_date) SELECT :o, v.* , DATE '2026-10-01' FROM (VALUES {values}) v"
                    ),
                    {"o": owner},
                )
    finally:
        with admin_engine.begin() as conn:
            conn.execute(text("DELETE FROM users WHERE id = :o"), {"o": owner})


@pytest.mark.parametrize("username", ["AB", "Maiuscula", "com espaço", "a" * 41])
def test_restricoes_de_username(admin_engine: Engine, username: str) -> None:
    with pytest.raises(Exception, match="violates check constraint"), admin_engine.begin() as conn:
        conn.execute(
            text("INSERT INTO users (username, display_name, password_hash) VALUES (:u, 'X', '!')"),
            {"u": username},
        )


def test_username_unico(admin_engine: Engine) -> None:
    with admin_engine.begin() as conn:
        conn.execute(
            text("INSERT INTO users (username, display_name, password_hash) VALUES ('dup', 'X', '!')")
        )
    try:
        with pytest.raises(Exception, match="duplicate key"), admin_engine.begin() as conn:
            conn.execute(
                text("INSERT INTO users (username, display_name, password_hash) VALUES ('dup', 'Y', '!')")
            )
    finally:
        with admin_engine.begin() as conn:
            conn.execute(text("DELETE FROM users WHERE username = 'dup'"))
