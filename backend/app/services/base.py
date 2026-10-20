"""Utilidades comuns dos serviços."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from typing import Any
from uuid import UUID

from fastapi.encoders import jsonable_encoder
from sqlalchemy import Connection, Row, text

from app.api.errors import ApiError, not_found


@dataclass(frozen=True)
class Ctx:
    """Contexto de um caso de uso: conexão com identidade, dono e data de hoje."""

    conn: Connection
    owner: UUID
    today: date

    def one(self, sql: str, **params: Any) -> Row[Any] | None:
        return self.conn.execute(text(sql), {"o": self.owner, **params}).one_or_none()

    def all(self, sql: str, **params: Any) -> list[Row[Any]]:
        return list(self.conn.execute(text(sql), {"o": self.owner, **params}).all())

    def scalar(self, sql: str, **params: Any) -> Any:
        return self.conn.execute(text(sql), {"o": self.owner, **params}).scalar()

    def exec(self, sql: str, **params: Any) -> Any:
        return self.conn.execute(text(sql), {"o": self.owner, **params})

    def require(self, table: str, entity_id: UUID, what: str, extra: str = "") -> Row[Any]:
        """Busca um registro do próprio usuário ou responde 404 (igual para inexistente
        e para registro de outra pessoa)."""
        row = self.one(
            f"SELECT * FROM {table} WHERE id = :id AND owner_id = :o {extra}",  # noqa: S608
            id=entity_id,
        )
        if row is None:
            raise not_found(what)
        return row

    def audit(self, entity: str, entity_id: UUID, action: str, before: Any = None, after: Any = None) -> None:
        self.exec(
            "INSERT INTO audit_log (owner_id, entity, entity_id, action, before_data, after_data) "
            "VALUES (:o, :e, :i, :a, CAST(:b AS jsonb), CAST(:f AS jsonb))",
            e=entity,
            i=entity_id,
            a=action,
            b=json.dumps(jsonable_encoder(before)) if before is not None else None,
            f=json.dumps(jsonable_encoder(after)) if after is not None else None,
        )


def row_dict(row: Row[Any]) -> dict[str, Any]:
    return dict(row._mapping)


def check_version(row: Row[Any], expected: int | None) -> None:
    if expected is not None and row.version != expected:
        raise ApiError(409, "Este registro foi alterado em outro aparelho. Recarregue a página para ver.")


def reject_future(d: date, today: date, field: str, what: str = "A data") -> None:
    if d > today:
        raise ApiError(422, f"{what} não pode ser no futuro.", {field: "Data no futuro."})
