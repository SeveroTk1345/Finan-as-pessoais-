"""Proteção contra operações repetidas (resposta perdida, toque duplo, reenvio).

O frontend gera uma chave por operação e a reenvia em todas as tentativas da mesma
operação. A primeira execução grava o resultado na mesma transação da operação;
repetições recebem o resultado gravado, sem executar de novo.

Duas requisições simultâneas com a mesma chave: a segunda espera na restrição
única até a primeira terminar e então lê o resultado dela.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from typing import Any
from uuid import UUID

from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy import Connection, text

from app.api.errors import ApiError

KEY_PATTERN = re.compile(r"^[A-Za-z0-9_-]{16,100}$")


def fingerprint(method: str, path: str, payload: Any) -> str:
    canonical = json.dumps(jsonable_encoder(payload), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(f"{method} {path}\n{canonical}".encode()).hexdigest()


def run_idempotent(
    conn: Connection,
    owner_id: UUID,
    key: str | None,
    fp: str,
    action: Callable[[], Any],
    *,
    status_code: int = 201,
) -> JSONResponse:
    if key is None or not KEY_PATTERN.match(key):
        raise ApiError(400, "Falta a identificação da operação. Recarregue a página e tente de novo.")

    inserted = conn.execute(
        text(
            "INSERT INTO idempotency_keys (owner_id, key, fingerprint) VALUES (:o, :k, :f) "
            "ON CONFLICT (owner_id, key) DO NOTHING RETURNING id"
        ),
        {"o": owner_id, "k": key, "f": fp},
    ).scalar_one_or_none()

    if inserted is None:
        row = conn.execute(
            text(
                "SELECT fingerprint, status_code, response_body FROM idempotency_keys "
                "WHERE owner_id = :o AND key = :k"
            ),
            {"o": owner_id, "k": key},
        ).one()
        if row.fingerprint != fp:
            raise ApiError(409, "Esta operação já foi enviada com outros dados. Recarregue a página.")
        if row.status_code is None:
            raise ApiError(409, "Esta operação ainda está sendo processada. Aguarde.")
        response = JSONResponse(row.response_body, status_code=row.status_code)
        response.headers["Idempotent-Replay"] = "true"
        return response

    body = jsonable_encoder(action())
    conn.execute(
        text("UPDATE idempotency_keys SET status_code = :s, response_body = CAST(:b AS jsonb) WHERE id = :i"),
        {"s": status_code, "b": json.dumps(body), "i": inserted},
    )
    return JSONResponse(body, status_code=status_code)
