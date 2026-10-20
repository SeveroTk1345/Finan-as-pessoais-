"""Dependência que liga um endpoint ao serviço: transação com identidade, data de hoje
e execução idempotente de criações."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Annotated, Any, TypeVar

from fastapi import Depends, Header, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.api.deps import UserDb, get_clock, user_db
from app.core.clock import Clock, today_sp
from app.services.base import Ctx
from app.services.idempotency import fingerprint, run_idempotent

T = TypeVar("T")


@dataclass(frozen=True)
class Service:
    db: UserDb
    today: date
    method: str
    path: str
    idempotency_key: str | None

    def run(self, fn: Callable[[Ctx], T]) -> T:
        """Leitura ou alteração simples. O COMMIT acontece antes de responder."""
        with self.db.tx() as conn:
            return fn(Ctx(conn, self.db.user_id, self.today))

    def create(
        self,
        payload: BaseModel | dict[str, Any] | None,
        fn: Callable[[Ctx], Any],
        status: int = 201,
    ) -> JSONResponse:
        """Operação que cria registros financeiros: exige chave de idempotência."""
        body = payload.model_dump(mode="json") if isinstance(payload, BaseModel) else payload
        fp = fingerprint(self.method, self.path, body)
        with self.db.tx() as conn:
            ctx = Ctx(conn, self.db.user_id, self.today)
            return run_idempotent(
                conn, self.db.user_id, self.idempotency_key, fp, lambda: fn(ctx), status_code=status
            )


def service(
    request: Request,
    db: Annotated[UserDb, Depends(user_db)],
    clock: Annotated[Clock, Depends(get_clock)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> Service:
    return Service(db, today_sp(clock), request.method, request.url.path, idempotency_key)


Svc = Annotated[Service, Depends(service)]
