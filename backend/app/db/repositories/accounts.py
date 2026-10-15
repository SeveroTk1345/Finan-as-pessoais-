"""Repositório de contas.

Isolamento em duas camadas independentes:
1. Toda consulta filtra ``owner_id`` explicitamente (aplicação).
2. Row-Level Security no banco filtra de novo pela identidade da transação.

Registro de outro usuário é tratado exatamente como registro inexistente
(``None`` / ``False``), para que a API responda 404 sem revelar que ele existe.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal, cast
from uuid import UUID

from sqlalchemy import Connection, Row, func, insert, select, text, update
from sqlalchemy import delete as sql_delete

from app.db.schema import accounts
from app.domain.money import Money

AccountKind = Literal["corrente", "poupanca", "especie", "outra"]


class IdentityMismatchError(RuntimeError):
    """O repositório foi usado com uma conexão de outro usuário."""


@dataclass(frozen=True, slots=True)
class Account:
    id: UUID
    owner_id: UUID
    name: str
    institution: str | None
    kind: AccountKind
    initial_balance: Money
    initial_balance_date: date
    is_active: bool
    version: int


def _to_account(row: Row[tuple[object, ...]]) -> Account:
    m = row._mapping
    return Account(
        id=cast(UUID, m["id"]),
        owner_id=cast(UUID, m["owner_id"]),
        name=cast(str, m["name"]),
        institution=cast("str | None", m["institution"]),
        kind=cast(AccountKind, m["kind"]),
        initial_balance=Money(cast(int, m["initial_balance_cents"])),
        initial_balance_date=cast(date, m["initial_balance_date"]),
        is_active=cast(bool, m["is_active"]),
        version=cast(int, m["version"]),
    )


class AccountRepository:
    def __init__(self, conn: Connection, owner_id: UUID) -> None:
        current = conn.execute(text("SELECT app_current_user_id()")).scalar_one_or_none()
        if current != owner_id:
            raise IdentityMismatchError("identidade da transação difere do dono informado")
        self._conn = conn
        self._owner_id = owner_id

    def create(
        self,
        *,
        name: str,
        kind: AccountKind,
        initial_balance: Money,
        initial_balance_date: date,
        institution: str | None = None,
    ) -> Account:
        row = self._conn.execute(
            insert(accounts)
            .values(
                owner_id=self._owner_id,
                name=name,
                institution=institution,
                kind=kind,
                initial_balance_cents=initial_balance.cents,
                initial_balance_date=initial_balance_date,
            )
            .returning(*accounts.c)
        ).one()
        return _to_account(row)

    def get(self, account_id: UUID) -> Account | None:
        row = self._conn.execute(
            select(accounts).where(accounts.c.id == account_id, accounts.c.owner_id == self._owner_id)
        ).one_or_none()
        return _to_account(row) if row is not None else None

    def list(self) -> list[Account]:
        rows = self._conn.execute(
            select(accounts)
            .where(accounts.c.owner_id == self._owner_id)
            .order_by(accounts.c.name, accounts.c.id)
        ).all()
        return [_to_account(r) for r in rows]

    def rename(self, account_id: UUID, *, name: str, expected_version: int) -> Account | None:
        """Atualização com bloqueio otimista. ``None`` se não existe, é de outro
        usuário ou a versão mudou (a API distingue os casos na T2.1)."""
        row = self._conn.execute(
            update(accounts)
            .where(
                accounts.c.id == account_id,
                accounts.c.owner_id == self._owner_id,
                accounts.c.version == expected_version,
            )
            .values(name=name, version=accounts.c.version + 1, updated_at=func.now())
            .returning(*accounts.c)
        ).one_or_none()
        return _to_account(row) if row is not None else None

    def delete(self, account_id: UUID) -> bool:
        result = self._conn.execute(
            sql_delete(accounts).where(accounts.c.id == account_id, accounts.c.owner_id == self._owner_id)
        )
        return result.rowcount == 1
