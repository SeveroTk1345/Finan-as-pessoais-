"""Situação de contas a pagar e a receber (puras)."""

from __future__ import annotations

from datetime import date
from enum import StrEnum

from app.domain.money import Money


class BillStatus(StrEnum):
    PENDENTE = "pendente"
    VENCIDA = "vencida"
    PARCIAL = "parcialmente_paga"
    PAGA = "paga"
    CANCELADA = "cancelada"


SOON_DAYS = 7


def bill_status(*, amount: Money, paid: Money, due: date, today: date, cancelled: bool) -> BillStatus:
    """F-12: vencida continua pendente até ser paga ou cancelada; nunca vira paga
    sozinha pela passagem do tempo."""
    if cancelled:
        return BillStatus.CANCELADA
    if paid.cents >= amount.cents:
        return BillStatus.PAGA
    if due < today:
        return BillStatus.VENCIDA
    if paid.cents > 0:
        return BillStatus.PARCIAL
    return BillStatus.PENDENTE


def due_soon(due: date, today: date) -> bool:
    return today <= due and (due - today).days <= SOON_DAYS
