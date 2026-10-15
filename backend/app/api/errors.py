"""Erros da API com mensagens em português, sem detalhes internos."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("financas.api")


class ApiError(Exception):
    """Erro de regra de negócio com mensagem pronta para o usuário."""

    def __init__(self, status_code: int, message: str, fields: dict[str, str] | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.message = message
        self.fields = fields or {}


def not_found(what: str = "Registro") -> ApiError:
    # Mesma resposta para "não existe" e "é de outra pessoa".
    return ApiError(404, f"{what} não encontrado.")


_MESSAGES = {
    "missing": "Preencha este campo.",
    "string_too_short": "Preencha este campo.",
    "string_too_long": "Texto longo demais.",
    "greater_than": "O valor precisa ser maior que zero.",
    "greater_than_equal": "O valor não pode ser negativo.",
    "less_than_equal": "Valor alto demais.",
    "int_parsing": "Informe um número inteiro.",
    "int_type": "Informe um número inteiro.",
    "date_from_datetime_parsing": "Data inválida. Use o formato DD/MM/AAAA.",
    "date_parsing": "Data inválida. Use o formato DD/MM/AAAA.",
    "date_type": "Data inválida. Use o formato DD/MM/AAAA.",
    "uuid_parsing": "Seleção inválida.",
    "uuid_type": "Seleção inválida.",
    "literal_error": "Escolha uma das opções.",
    "enum": "Escolha uma das opções.",
    "bool_parsing": "Valor inválido.",
    "decimal_parsing": "Informe um número.",
    "extra_forbidden": "Campo não reconhecido.",
}

_HTTP_MESSAGES = {
    401: "Sua sessão terminou. Entre novamente.",
    403: "Operação não permitida.",
    404: "Não encontrado.",
    405: "Operação não permitida.",
    413: "Arquivo grande demais.",
}


def _field_name(loc: tuple[Any, ...]) -> str:
    parts = [str(p) for p in loc if p not in ("body", "query", "path")]
    return ".".join(parts) or "geral"


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError) -> JSONResponse:
        body: dict[str, Any] = {"detail": exc.message}
        if exc.fields:
            body["campos"] = exc.fields
        return JSONResponse(body, status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        fields: dict[str, str] = {}
        for err in exc.errors():
            name = _field_name(tuple(err.get("loc", ())))
            ctx_msg = (err.get("ctx") or {}).get("error")
            msg = str(ctx_msg) if ctx_msg else _MESSAGES.get(err.get("type", ""), "Valor inválido.")
            fields.setdefault(name, msg)
        return JSONResponse({"detail": "Confira os campos destacados.", "campos": fields}, status_code=422)

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        message = exc.detail if isinstance(exc.detail, str) and exc.status_code not in (404, 405) else None
        return JSONResponse(
            {"detail": message or _HTTP_MESSAGES.get(exc.status_code, "Erro na requisição.")},
            status_code=exc.status_code,
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(IntegrityError)
    async def _integrity(request: Request, exc: IntegrityError) -> JSONResponse:
        # Última barreira (chaves compostas, restrições do banco). Sem detalhes internos.
        logger.warning("integridade recusada em %s %s", request.method, request.url.path)
        return JSONResponse(
            {
                "detail": "Não foi possível salvar: algum dado não é válido ou não pertence a você. "
                "Nada foi gravado."
            },
            status_code=422,
        )

    @app.exception_handler(Exception)
    async def _unexpected(request: Request, exc: Exception) -> JSONResponse:
        # Só o tipo do erro e a rota vão para o log: nunca valores ou descrições.
        logger.error("erro inesperado em %s %s: %s", request.method, request.url.path, type(exc).__name__)
        return JSONResponse(
            {"detail": "Algo deu errado e nada foi salvo. Tente de novo em instantes."},
            status_code=500,
        )
