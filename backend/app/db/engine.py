"""Criação do engine e garantia de que nenhuma conexão do pool carrega identidade."""

from __future__ import annotations

from typing import Any

from sqlalchemy import Engine, create_engine, event

from app.db.ownership import IDENTITY_SETTING


def _clear_identity(dbapi_connection: Any) -> None:
    cursor = dbapi_connection.cursor()
    try:
        # Escopo de sessão (false): apaga até um SET não-local feito por engano.
        cursor.execute("SELECT set_config(%s, '', false)", (IDENTITY_SETTING,))
    finally:
        cursor.close()
    # set_config abre uma transação implícita no psycopg; encerra antes de entregar.
    dbapi_connection.commit()


def make_engine(url: str, **kwargs: Any) -> Engine:
    """Engine do SQLAlchemy com limpeza de identidade a cada retirada do pool.

    A identidade correta é definida por ``user_transaction`` com escopo de transação
    (SET LOCAL). A limpeza aqui é uma segunda barreira: mesmo que algum código defina
    a identidade com escopo de sessão, a próxima retirada da conexão a apaga.
    """
    engine = create_engine(url, pool_pre_ping=True, **kwargs)

    @event.listens_for(engine, "checkout")
    def _on_checkout(dbapi_connection: Any, _record: Any, _proxy: Any) -> None:
        _clear_identity(dbapi_connection)

    return engine
