"""Início em plataforma gerenciada (Render + Neon), sem Docker Compose.

No servidor próprio (Compose), o PostgreSQL cria o papel ``fin_app`` e um serviço
separado roda as migrações. Numa plataforma gerenciada, tudo acontece aqui, antes da
API subir:

1. converte o endereço do banco para o driver usado (psycopg);
2. cria (ou ajusta) o papel ``fin_app``: sem superusuário e sem BYPASSRLS;
3. aplica as migrações com o papel dono do banco;
4. **confere** que ``fin_app`` não escapa da Row-Level Security, nem diretamente nem
   por ser membro de outro papel; se escapar, a API não sobe;
5. troca o processo pelo servidor web **sem** a senha do dono do banco no ambiente.

Variáveis: ``FIN_DATABASE_ADMIN_URL`` (endereço do dono, ex.: o do Neon),
``FIN_DB_APP_PASSWORD`` (senha do papel da API), ``PORT`` (definida pela plataforma) e,
opcional, ``FIN_ALLOWED_ORIGINS`` (sem ela, usa ``RENDER_EXTERNAL_URL``).

Uso: ``python -m app.deploy_start``
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

import psycopg
from psycopg import sql
from sqlalchemy.engine import make_url

from app.core.config import normalize_database_url
from app.db.ownership import APP_ROLE

BACKEND_DIR = Path(__file__).resolve().parent.parent


class UnsafeDatabaseRoleError(RuntimeError):
    """O papel da API conseguiria ignorar a Row-Level Security."""


def _libpq(url: str) -> str:
    """Endereço no formato da libpq (sem o "+psycopg" do SQLAlchemy)."""
    return make_url(url).set(drivername="postgresql").render_as_string(hide_password=False)


def app_database_url(admin_url: str, app_password: str) -> str:
    """Mesmo servidor, banco e opções (ex.: sslmode do Neon); usuário e senha da API.
    A senha é codificada pelo SQLAlchemy: caracteres como / + = não quebram o endereço."""
    url = make_url(normalize_database_url(admin_url)).set(username=APP_ROLE, password=app_password)
    return url.render_as_string(hide_password=False)


def ensure_app_role(admin_url: str, app_password: str) -> None:
    """Cria o papel da API ou ajusta senha e atributos. Pode rodar a cada início."""
    if len(app_password) < 24:
        raise SystemExit("FIN_DB_APP_PASSWORD precisa ter pelo menos 24 caracteres.")
    # Sem NOSUPERUSER no comando: um dono sem superusuário (caso do Neon) não pode nem
    # mencionar esse atributo. Papel novo já nasce sem ele, e check_app_role confere.
    attrs = sql.SQL("LOGIN NOBYPASSRLS NOCREATEDB NOCREATEROLE NOINHERIT")
    with psycopg.connect(_libpq(admin_url), autocommit=True) as conn:
        exists = conn.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (APP_ROLE,)).fetchone()
        verb = sql.SQL("ALTER ROLE") if exists else sql.SQL("CREATE ROLE")
        # CREATE/ALTER ROLE não aceitam parâmetro: a senha entra como literal escapado.
        conn.execute(
            sql.SQL("{} {} {} PASSWORD {}").format(
                verb, sql.Identifier(APP_ROLE), attrs, sql.Literal(app_password)
            )
        )
        db = conn.execute("SELECT current_database()").fetchone()
        if db is None:  # pragma: no cover - current_database() sempre responde
            raise RuntimeError("banco atual desconhecido")
        conn.execute(sql.SQL("REVOKE ALL ON DATABASE {} FROM PUBLIC").format(sql.Identifier(db[0])))
        conn.execute(
            sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
                sql.Identifier(db[0]), sql.Identifier(APP_ROLE)
            )
        )


def run_migrations(admin_url: str) -> None:
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    cfg.attributes["url"] = normalize_database_url(admin_url)
    command.upgrade(cfg, "head")


def check_app_role(admin_url: str) -> None:
    """Recusa subir se o papel da API puder ignorar a RLS ou for dono de tabelas."""
    with psycopg.connect(_libpq(admin_url)) as conn:
        row = conn.execute(
            """SELECT r.rolsuper, r.rolbypassrls,
                      EXISTS (SELECT 1 FROM pg_roles x
                               WHERE x.oid <> r.oid AND (x.rolsuper OR x.rolbypassrls)
                                 AND pg_has_role(r.oid, x.oid, 'MEMBER')) AS herda,
                      EXISTS (SELECT 1 FROM pg_class c
                               WHERE c.relowner = r.oid AND c.relkind IN ('r', 'p')) AS dono
               FROM pg_roles r WHERE r.rolname = %s""",
            (APP_ROLE,),
        ).fetchone()
    if row is None:
        raise UnsafeDatabaseRoleError(f"o papel {APP_ROLE} não existe")
    superuser, bypass, inherits, owner = row
    problems = [
        msg
        for flag, msg in (
            (superuser, "é superusuário"),
            (bypass, "tem BYPASSRLS"),
            (inherits, "é membro de um papel que ignora a RLS"),
            (owner, "é dono de tabelas"),
        )
        if flag
    ]
    if problems:
        raise UnsafeDatabaseRoleError(f"o papel {APP_ROLE} " + ", ".join(problems))


def server_environment(env: dict[str, str]) -> dict[str, str]:
    """Ambiente do servidor web: com o endereço da API e sem as credenciais do dono."""
    out = {k: v for k, v in env.items() if k not in ("FIN_DATABASE_ADMIN_URL", "FIN_DB_APP_PASSWORD")}
    out["FIN_DATABASE_URL"] = app_database_url(env["FIN_DATABASE_ADMIN_URL"], env["FIN_DB_APP_PASSWORD"])
    out.setdefault("FIN_ENVIRONMENT", "production")
    if not out.get("FIN_ALLOWED_ORIGINS") and out.get("RENDER_EXTERNAL_URL"):
        out["FIN_ALLOWED_ORIGINS"] = out["RENDER_EXTERNAL_URL"]
    # O proxy da plataforma acrescenta o IP real no fim do X-Forwarded-For.
    out.setdefault("FIN_CLIENT_IP_FROM", "ultimo")
    # Banco que dorme sem uso (Neon grátis): nenhuma conexão parada fica aberta.
    out.setdefault("FIN_DB_KEEP_CONNECTIONS", "false")
    return out


def main() -> None:
    env = dict(os.environ)
    missing = [k for k in ("FIN_DATABASE_ADMIN_URL", "FIN_DB_APP_PASSWORD") if not env.get(k)]
    if missing:
        raise SystemExit("Faltam variáveis: " + ", ".join(missing))
    admin_url = env["FIN_DATABASE_ADMIN_URL"]
    print("Preparando o papel da API...", flush=True)
    ensure_app_role(admin_url, env["FIN_DB_APP_PASSWORD"])
    print("Aplicando migrações...", flush=True)
    run_migrations(admin_url)
    print("Conferindo o isolamento entre usuários...", flush=True)
    check_app_role(admin_url)
    server_env = server_environment(env)
    port = env.get("PORT", "8000")
    print(f"Iniciando a API na porta {port}.", flush=True)
    # 0.0.0.0: dentro do container; só o proxy da plataforma chega até aqui.
    host = "0.0.0.0"  # noqa: S104
    workers = env.get("WEB_CONCURRENCY", "1")
    args = ["uvicorn", "app.main:app", "--host", host, "--port", port, "--proxy-headers",
            "--forwarded-allow-ips", "*", "--workers", workers]  # fmt: skip
    sys.stdout.flush()
    uvicorn = shutil.which("uvicorn")
    if uvicorn is None:
        raise SystemExit("uvicorn não encontrado no PATH.")
    os.execve(uvicorn, args, server_env)  # noqa: S606 - substitui o processo, sem shell


if __name__ == "__main__":
    main()
