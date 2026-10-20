"""Transações executadas em nome de um usuário autenticado."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from uuid import UUID

from sqlalchemy import Connection, Engine, text

from app.db.ownership import IDENTITY_SETTING


@contextmanager
def user_transaction(engine: Engine, user_id: UUID) -> Iterator[Connection]:
    """Abre uma transação com a identidade do usuário definida só para ela.

    ``user_id`` deve vir da sessão validada no servidor (T1.3), nunca do corpo ou da
    URL da requisição. O tipo ``UUID`` é exigido para impedir que um texto qualquer
    seja usado como identidade.

    A identidade usa ``set_config(..., true)``, equivalente a ``SET LOCAL``: termina
    com o COMMIT ou o ROLLBACK, então a conexão volta ao pool sem identidade.
    """
    if not isinstance(user_id, UUID):
        raise TypeError("user_id deve ser UUID vindo da sessão autenticada")
    with engine.begin() as conn:
        conn.execute(
            text("SELECT set_config(:name, :value, true)"),
            {"name": IDENTITY_SETTING, "value": str(user_id)},
        )
        yield conn
