"""Ambiente do Alembic. Migrações rodam com o papel administrador, nunca com fin_app."""

from __future__ import annotations

import os

from alembic import context
from sqlalchemy import create_engine, pool


def _admin_url() -> str:
    # Ordem: chamada programática (testes), -x url=... na linha de comando, variável.
    url = (
        context.config.attributes.get("url")
        or context.get_x_argument(as_dictionary=True).get("url")
        or os.environ.get("FIN_DATABASE_ADMIN_URL")
    )
    if not url:
        raise RuntimeError("defina FIN_DATABASE_ADMIN_URL para rodar migrações")
    from app.core.config import normalize_database_url

    return normalize_database_url(url)


def run_migrations_online() -> None:
    engine = create_engine(_admin_url(), poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, transaction_per_migration=True)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    raise RuntimeError("modo offline não suportado: migrações exigem conexão")
run_migrations_online()
