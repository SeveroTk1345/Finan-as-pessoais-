"""Infraestrutura dos testes com PostgreSQL real.

Requer ``FIN_TEST_ADMIN_URL`` apontando para um servidor PostgreSQL 16 **dedicado a
testes** (``scripts/test-db.sh`` sobe um no Docker). Sem a variável, os testes deste
pacote são pulados com aviso; ``make test-backend`` sempre define a variável.

Cada execução cria um banco novo ``fin_test_<aleatório>``, aplica as migrações e o
apaga no fim. Os dados são sintéticos: nenhum dado financeiro real é usado.
"""

from __future__ import annotations

import os
import secrets
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from psycopg import sql
from sqlalchemy import Engine, create_engine, make_url, text
from sqlalchemy.engine import URL

from app.db.engine import make_engine

BACKEND_DIR = Path(__file__).resolve().parents[2]
ADMIN_URL_ENV = "FIN_TEST_ADMIN_URL"


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    if os.environ.get(ADMIN_URL_ENV):
        return
    skip = pytest.mark.skip(reason=f"{ADMIN_URL_ENV} não definida (use scripts/test-db.sh)")
    for item in items:
        if "tests/db/" in str(item.fspath).replace(os.sep, "/"):
            item.add_marker(skip)


@dataclass(frozen=True)
class DbInfo:
    name: str
    admin_url: URL
    app_url: URL
    app_password: str


def _admin_server_url() -> URL:
    raw = os.environ.get(ADMIN_URL_ENV)
    if not raw:
        pytest.skip(f"{ADMIN_URL_ENV} não definida")
    return make_url(raw)


@pytest.fixture(scope="session")
def test_db() -> Iterator[DbInfo]:
    server = _admin_server_url()
    name = f"fin_test_{secrets.token_hex(6)}"
    app_password = secrets.token_urlsafe(24)

    maint = create_engine(server, isolation_level="AUTOCOMMIT")
    with maint.connect() as conn:
        role_exists = conn.execute(text("SELECT 1 FROM pg_roles WHERE rolname='fin_app'")).scalar()
        if not role_exists:
            conn.execute(
                text("CREATE ROLE fin_app LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOINHERIT")
            )
        # O servidor de teste é dedicado; a senha muda a cada execução.
        # Comandos utilitários não aceitam parâmetros no servidor: o psycopg monta o
        # literal com escape no cliente.
        stmt = sql.SQL("ALTER ROLE fin_app PASSWORD {}").format(sql.Literal(app_password))
        conn.exec_driver_sql(stmt.as_string(None))
        conn.execute(text(f'CREATE DATABASE "{name}"'))
        conn.execute(text(f'REVOKE ALL ON DATABASE "{name}" FROM PUBLIC'))
        conn.execute(text(f'GRANT CONNECT ON DATABASE "{name}" TO fin_app'))

    admin_url = server.set(database=name)
    app_url = server.set(database=name, username="fin_app", password=app_password)

    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.attributes["url"] = admin_url.render_as_string(False)
    command.upgrade(cfg, "head")

    try:
        yield DbInfo(name, admin_url, app_url, app_password)
    finally:
        with maint.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        maint.dispose()


@pytest.fixture(scope="session")
def admin_engine(test_db: DbInfo) -> Iterator[Engine]:
    engine = create_engine(test_db.admin_url)
    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
def app_engine(test_db: DbInfo) -> Iterator[Engine]:
    engine = make_engine(test_db.app_url.render_as_string(False))
    yield engine
    engine.dispose()


@dataclass(frozen=True)
class Users:
    ana: UUID
    bruno: UUID
    carla: UUID

    def all(self) -> list[UUID]:
        return [self.ana, self.bruno, self.carla]


@pytest.fixture
def users(admin_engine: Engine) -> Iterator[Users]:
    """Três usuários independentes, criados pelo administrador (como fará a T1.3)."""
    ids: dict[str, UUID] = {}
    with admin_engine.begin() as conn:
        for username, display in [("ana", "Ana"), ("bruno", "Bruno"), ("carla", "Carla")]:
            ids[username] = conn.execute(
                text(
                    "INSERT INTO users (username, display_name, password_hash) "
                    "VALUES (:u, :d, '!sem-senha') RETURNING id"
                ),
                {"u": username, "d": display},
            ).scalar_one()
    try:
        yield Users(ids["ana"], ids["bruno"], ids["carla"])
    finally:
        with admin_engine.begin() as conn:
            conn.execute(text("TRUNCATE users, login_attempts CASCADE"))


@pytest.fixture
def neon_like_factory(test_db: DbInfo) -> Iterator[Callable[[], URL]]:
    """Cria bancos cujo dono imita o do Neon: sem superusuário, com BYPASSRLS e
    CREATEROLE. Cada chamada devolve o endereço de um banco novo e vazio."""
    server = test_db.admin_url.set(database="postgres")
    maint = create_engine(server, isolation_level="AUTOCOMMIT")
    created: list[tuple[str, str]] = []

    def make() -> URL:
        owner = f"neon_dono_{secrets.token_hex(4)}"
        owner_pw = secrets.token_hex(16)
        db = f"neon_sim_{secrets.token_hex(4)}"
        with maint.connect() as conn:
            conn.exec_driver_sql(
                sql.SQL("CREATE ROLE {} LOGIN NOSUPERUSER CREATEDB CREATEROLE BYPASSRLS PASSWORD {}")
                .format(sql.Identifier(owner), sql.Literal(owner_pw))
                .as_string(None)
            )
            # No Neon o próprio dono cria fin_app; aqui o papel já existe no servidor de
            # teste, então o dono recebe permissão de administrá-lo (sem herdar nada dele).
            conn.exec_driver_sql(f'GRANT fin_app TO "{owner}" WITH ADMIN OPTION, INHERIT FALSE, SET FALSE')
            conn.exec_driver_sql(f'CREATE DATABASE "{db}" OWNER "{owner}"')
        created.append((db, owner))
        return server.set(database=db, username=owner, password=owner_pw)

    try:
        yield make
    finally:
        with maint.connect() as conn:
            for db, owner in reversed(created):
                conn.exec_driver_sql(f'DROP DATABASE IF EXISTS "{db}" WITH (FORCE)')
                conn.exec_driver_sql(f'DROP OWNED BY "{owner}"')
                conn.exec_driver_sql(f'DROP ROLE IF EXISTS "{owner}"')
        maint.dispose()


@pytest.fixture
def neon_like(neon_like_factory: Callable[[], URL]) -> URL:
    """Um banco vazio com dono estilo Neon."""
    return neon_like_factory()
