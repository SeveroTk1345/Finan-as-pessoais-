"""Dívidas (implementação completa na etapa de cartões e dívidas)."""

from __future__ import annotations

from uuid import UUID

from app.services.base import Ctx


def refresh_debt_status(ctx: Ctx, debt_id: UUID) -> None:
    _ = (ctx, debt_id)
