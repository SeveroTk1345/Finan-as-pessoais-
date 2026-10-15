"""CSRF e cabeçalhos de segurança."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from app.core.config import Settings

UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
CSRF_HEADER = "x-requested-with"

# O Next.js exportado usa scripts inline para hidratação; sem nonce em site estático,
# 'unsafe-inline' é necessário. O React escapa todo conteúdo exibido, e nada é
# carregado de outros domínios.
CSP = (
    "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; font-src 'self'; connect-src 'self'; manifest-src 'self'; "
    "worker-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'; "
    "object-src 'none'"
)


def install_middleware(app: FastAPI, settings: Settings) -> None:
    origins = settings.origins

    @app.middleware("http")
    async def security(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        path = request.url.path
        if path.startswith("/api/") and request.method in UNSAFE_METHODS:
            origin = (request.headers.get("origin") or "").rstrip("/")
            if origin not in origins or not request.headers.get(CSRF_HEADER):
                return JSONResponse(
                    {"detail": "Requisição recusada por segurança. Recarregue a página."},
                    status_code=403,
                )

        response = await call_next(request)

        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault(
            "Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=()"
        )
        response.headers.setdefault("Content-Security-Policy", CSP)
        response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        if settings.is_production:
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
            )
        if path.startswith("/api/"):
            # Dados financeiros nunca ficam em cache do navegador nem de proxies,
            # e o botão "voltar" após sair não reexibe respostas antigas.
            response.headers["Cache-Control"] = "no-store"
            response.headers["Pragma"] = "no-cache"
        return response
