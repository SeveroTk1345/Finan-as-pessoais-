"""Início em plataforma gerenciada (Render + Neon), com banco real.

O Neon entrega um dono do banco que NÃO é superusuário (tem CREATEROLE, CREATEDB e
BYPASSRLS). Aqui um papel assim é criado para provar que as migrações funcionam sem
superusuário e que o papel da API continua sujeito à Row-Level Security.
"""

from __future__ import annotations

import os
import secrets
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, make_url

from app.core.config import normalize_database_url
from app.deploy_start import (
    UnsafeDatabaseRoleError,
    app_database_url,
    check_app_role,
    ensure_app_role,
    run_migrations,
    server_environment,
)
from tests.db.conftest import BACKEND_DIR, DbInfo


def test_normaliza_o_endereco_como_o_neon_entrega() -> None:
    neon = (
        "postgresql://dono:s3nha@ep-x.us-east-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require"
    )
    assert normalize_database_url(neon).startswith("postgresql+psycopg://dono:s3nha@ep-x")
    assert normalize_database_url("postgres://a:b@h/d") == "postgresql+psycopg://a:b@h/d"
    assert normalize_database_url("postgresql+psycopg://a:b@h/d") == "postgresql+psycopg://a:b@h/d"


def test_endereco_da_api_troca_usuario_e_senha_e_mantem_o_resto() -> None:
    neon = "postgresql://dono:s3nha@ep-x.neon.tech:5432/neondb?sslmode=require"
    url = make_url(app_database_url(neon, "a/b+c=d"))  # base64 com / + = não quebra
    assert (url.drivername, url.username, url.password) == ("postgresql+psycopg", "fin_app", "a/b+c=d")
    assert (url.host, url.port, url.database) == ("ep-x.neon.tech", 5432, "neondb")
    assert url.query["sslmode"] == "require"


def test_ambiente_do_servidor_nao_leva_as_credenciais_do_dono() -> None:
    env = server_environment(
        {
            "FIN_DATABASE_ADMIN_URL": "postgresql://dono:segredo@h/db",
            "FIN_DB_APP_PASSWORD": "x" * 32,
            "RENDER_EXTERNAL_URL": "https://financas.onrender.com",
            "PATH": "/usr/bin",
        }
    )
    assert "FIN_DATABASE_ADMIN_URL" not in env and "FIN_DB_APP_PASSWORD" not in env
    assert "segredo" not in " ".join(env.values())
    assert make_url(env["FIN_DATABASE_URL"]).username == "fin_app"
    assert env["FIN_ALLOWED_ORIGINS"] == "https://financas.onrender.com"
    assert env["FIN_ENVIRONMENT"] == "production"
    assert env["FIN_CLIENT_IP_FROM"] == "ultimo"
    assert env["FIN_DB_KEEP_CONNECTIONS"] == "false"


def test_sem_conexoes_paradas_quando_o_banco_dorme(test_db: DbInfo) -> None:
    from pydantic import SecretStr
    from sqlalchemy.pool import NullPool, QueuePool

    from app.core.config import Settings
    from app.main import create_app

    url = test_db.app_url.render_as_string(hide_password=False)
    for keep, pool in ((True, QueuePool), (False, NullPool)):
        app = create_app(Settings(database_url=SecretStr(url), db_keep_connections=keep))
        engine = app.state.engine
        assert isinstance(engine.pool, pool)
        with engine.connect() as conn:
            assert conn.execute(text("SELECT 1")).scalar() == 1
        engine.dispose()


def test_senha_curta_da_api_e_recusada() -> None:
    with pytest.raises(SystemExit):
        ensure_app_role("postgresql://x:y@127.0.0.1:1/z", "curta")


def test_prepara_banco_sem_superusuario_e_api_fica_sob_rls(test_db: DbInfo, neon_like: URL) -> None:
    owner_url = neon_like.render_as_string(hide_password=False)
    # A senha é a mesma do servidor de teste, para não derrubar as outras conexões.
    ensure_app_role(owner_url, test_db.app_password)
    ensure_app_role(owner_url, test_db.app_password)  # repetir não estraga
    run_migrations(owner_url)
    run_migrations(owner_url)  # já atualizado: nada a fazer
    check_app_role(owner_url)

    owner = create_engine(normalize_database_url(owner_url))
    with owner.begin() as conn:
        conn.execute(
            text("INSERT INTO users (username, display_name, password_hash) VALUES ('ana', 'Ana', 'x')")
        )
    api = create_engine(app_database_url(owner_url, test_db.app_password))
    with api.connect() as conn:
        role = conn.execute(
            text("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user")
        ).one()
        assert tuple(role) == (False, False)
        # Sem identidade na transação, a RLS esconde a linha da Ana.
        assert conn.execute(text("SELECT count(*) FROM users")).scalar() == 0
    owner.dispose()
    api.dispose()


def test_checagem_barra_papel_que_ignoraria_a_rls(test_db: DbInfo, neon_like: URL) -> None:
    owner_url = neon_like.render_as_string(hide_password=False)
    ensure_app_role(owner_url, test_db.app_password)
    run_migrations(owner_url)
    maint = create_engine(test_db.admin_url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    poderoso = f"poderoso_{secrets.token_hex(4)}"
    try:
        with maint.connect() as conn:
            conn.exec_driver_sql("ALTER ROLE fin_app BYPASSRLS")
        with pytest.raises(UnsafeDatabaseRoleError, match="BYPASSRLS"):
            check_app_role(owner_url)
        with maint.connect() as conn:
            conn.exec_driver_sql("ALTER ROLE fin_app NOBYPASSRLS")
            conn.exec_driver_sql(f'CREATE ROLE "{poderoso}" NOLOGIN BYPASSRLS')
            conn.exec_driver_sql(f'GRANT "{poderoso}" TO fin_app')
        with pytest.raises(UnsafeDatabaseRoleError, match="membro"):
            check_app_role(owner_url)
    finally:
        with maint.connect() as conn:
            conn.exec_driver_sql("ALTER ROLE fin_app NOBYPASSRLS")
            conn.exec_driver_sql(f'DROP ROLE IF EXISTS "{poderoso}"')
        maint.dispose()
    check_app_role(owner_url)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def test_inicio_completo_sobe_a_api_sem_a_senha_do_dono(test_db: DbInfo, neon_like: URL) -> None:
    port = _free_port()
    env = {
        "PATH": os.environ["PATH"],
        "FIN_DATABASE_ADMIN_URL": neon_like.render_as_string(hide_password=False),
        "FIN_DB_APP_PASSWORD": test_db.app_password,
        "PORT": str(port),
        "RENDER_EXTERNAL_URL": "https://financas.onrender.com",
    }
    proc = subprocess.Popen(
        [sys.executable, "-m", "app.deploy_start"],
        cwd=BACKEND_DIR,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    try:
        ok = False
        for _ in range(100):
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=1) as r:
                    ok = r.status == 200
                    break
            except OSError:
                time.sleep(0.2)
        assert ok, "a API não respondeu"
        # exec: o mesmo processo virou o servidor web, e o ambiente dele não tem a
        # senha do dono do banco nem a da API em separado.
        environ = Path(f"/proc/{proc.pid}/environ").read_bytes().split(b"\0")
        names = {e.split(b"=", 1)[0] for e in environ if e}
        assert b"FIN_DATABASE_ADMIN_URL" not in names
        assert b"FIN_DB_APP_PASSWORD" not in names
        assert b"FIN_DATABASE_URL" in names
        assert neon_like.password and neon_like.password.encode() not in b"\0".join(environ)
    finally:
        proc.terminate()
        out, _ = proc.communicate(timeout=10)
    text_out = out.decode(errors="replace")
    assert "Conferindo o isolamento entre usuários" in text_out
    assert neon_like.password not in text_out  # a senha não aparece no log


@pytest.mark.parametrize(("mode", "expected"), [("ultimo", "203.0.113.9"), ("primeiro", "1.2.3.4")])
def test_ip_do_visitante_conforme_o_proxy(
    app_engine: Any, admin_engine: Any, mode: str, expected: str
) -> None:
    from fastapi.testclient import TestClient

    from tests.db.api_helpers import ORIGIN, SAFE_HEADERS, build_app

    with admin_engine.begin() as conn:
        conn.execute(text("DELETE FROM login_attempts"))
    app = build_app(app_engine, environment="production", client_ip_from=mode)
    client = TestClient(app, base_url="https://testserver")
    # "1.2.3.4" foi forjado pelo visitante; o proxy acrescentou o IP real no fim.
    client.post(
        "/api/auth/entrar",
        json={"usuario": "ninguem", "senha": "errada-errada"},
        headers={**SAFE_HEADERS, "X-Forwarded-For": "1.2.3.4, 203.0.113.9"},
    )
    with admin_engine.connect() as conn:
        assert conn.execute(text("SELECT client_ip FROM login_attempts")).scalar() == expected
    assert ORIGIN
