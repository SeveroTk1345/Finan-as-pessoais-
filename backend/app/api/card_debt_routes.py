"""Rotas de cartões, faturas e dívidas."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import Field

from app.api.core_routes import Cents, Note, Strict, Text120
from app.api.service import Svc
from app.services import cards, debts

router = APIRouter()

Day = Annotated[int, Field(ge=1, le=31)]
Name60 = Annotated[str, Field(min_length=1, max_length=60)]


class CardIn(Strict):
    name: Name60
    institution: Annotated[str | None, Field(default=None, max_length=60)] = None
    limit_cents: Annotated[int, Field(ge=0, le=100_000_000_000_000)]
    closing_day: Day
    due_day: Day
    closing_day_goes_next: bool = True


class CardPatch(Strict):
    name: Name60 | None = None
    institution: Annotated[str | None, Field(default=None, max_length=60)] = None
    limit_cents: Annotated[int | None, Field(default=None, ge=0, le=100_000_000_000_000)] = None
    closing_day: Day | None = None
    due_day: Day | None = None
    closing_day_goes_next: bool | None = None
    is_active: bool | None = None
    version: int | None = None


class PurchaseIn(Strict):
    kind: Literal["compra", "encargo"] = "compra"
    description: Text120
    total_cents: Cents
    purchase_date: date
    installments_count: Annotated[int, Field(ge=1, le=72)] = 1
    category_id: UUID | None = None
    first_invoice_due: date | None = None
    note: Note = None


class RefundIn(Strict):
    amount_cents: Cents
    credit_date: date | None = None


class InvoicePayIn(Strict):
    account_id: UUID
    amount_cents: Cents | None = None
    tx_date: date | None = None


class RenegotiateInvoiceIn(Strict):
    financed_cents: Cents
    installments_count: Annotated[int, Field(ge=1, le=72)]
    installment_cents: Cents
    first_invoice_due: date | None = None
    creditor: Annotated[str | None, Field(default=None, max_length=80)] = None


@router.get("/cartoes")
def cards_list(svc: Svc) -> list[dict[str, Any]]:
    return svc.run(cards.list_cards)


@router.post("/cartoes", status_code=201)
def cards_create(payload: CardIn, svc: Svc) -> JSONResponse:
    return svc.create(payload, lambda c: cards.create_card(c, payload.model_dump()))


@router.get("/cartoes/{card_id}")
def cards_get(card_id: UUID, svc: Svc) -> dict[str, Any]:
    return svc.run(lambda c: cards.get_card(c, card_id))


@router.patch("/cartoes/{card_id}")
def cards_update(card_id: UUID, payload: CardPatch, svc: Svc) -> dict[str, Any]:
    data = payload.model_dump(exclude_unset=True)
    return svc.run(lambda c: cards.update_card(c, card_id, data))


@router.post("/cartoes/{card_id}/compras", status_code=201)
def purchases_create(card_id: UUID, payload: PurchaseIn, svc: Svc) -> JSONResponse:
    return svc.create(payload, lambda c: cards.create_purchase(c, card_id, payload.model_dump()))


@router.get("/compras/{purchase_id}")
def purchases_get(purchase_id: UUID, svc: Svc) -> dict[str, Any]:
    return svc.run(lambda c: cards.get_purchase(c, purchase_id))


@router.post("/compras/{purchase_id}/cancelar")
def purchases_cancel(purchase_id: UUID, svc: Svc) -> dict[str, Any]:
    return svc.run(lambda c: cards.cancel_purchase(c, purchase_id))


@router.post("/compras/{purchase_id}/estornar", status_code=201)
def purchases_refund(purchase_id: UUID, payload: RefundIn, svc: Svc) -> JSONResponse:
    return svc.create(
        payload,
        lambda c: cards.refund_purchase(c, purchase_id, payload.amount_cents, payload.credit_date),
    )


@router.get("/cartoes/{card_id}/faturas/{due}")
def invoice_get(card_id: UUID, due: date, svc: Svc) -> dict[str, Any]:
    return svc.run(lambda c: cards.invoice_detail(c, card_id, due))


@router.post("/cartoes/{card_id}/faturas/{due}/pagar", status_code=201)
def invoice_pay(card_id: UUID, due: date, payload: InvoicePayIn, svc: Svc) -> JSONResponse:
    return svc.create(payload, lambda c: cards.pay_invoice(c, card_id, due, payload.model_dump()))


@router.post("/cartoes/{card_id}/faturas/{due}/renegociar", status_code=201)
def invoice_renegotiate(card_id: UUID, due: date, payload: RenegotiateInvoiceIn, svc: Svc) -> JSONResponse:
    return svc.create(payload, lambda c: cards.renegotiate_invoice(c, card_id, due, payload.model_dump()))


# --- dívidas ---------------------------------------------------------------------

Rate = Annotated[Decimal, Field(ge=0, le=1000, max_digits=12, decimal_places=6)]
DebtKind = Literal["emprestimo", "financiamento", "parcelamento", "renegociacao", "outra"]


class DebtIn(Strict):
    creditor: Annotated[str, Field(min_length=1, max_length=80)]
    description: Annotated[str | None, Field(default=None, max_length=120)] = None
    kind: DebtKind = "outra"
    original_amount_cents: Cents
    current_balance_cents: Annotated[int | None, Field(default=None, ge=0, le=100_000_000_000_000)] = None
    balance_date: date | None = None
    start_date: date | None = None
    interest_rate: Rate | None = None
    rate_period: Literal["mensal", "anual"] | None = None
    installments_total: Annotated[int | None, Field(default=None, ge=1, le=600)] = None
    installments_paid_before: Annotated[int, Field(ge=0, le=600)] = 0
    installment_amount_cents: Cents | None = None
    first_due_date: date | None = None
    disbursement_account_id: UUID | None = None
    note: Note = None


class DebtPatch(Strict):
    creditor: Annotated[str | None, Field(default=None, min_length=1, max_length=80)] = None
    description: Annotated[str | None, Field(default=None, max_length=120)] = None
    interest_rate: Rate | None = None
    rate_period: Literal["mensal", "anual"] | None = None
    installments_total: Annotated[int | None, Field(default=None, ge=1, le=600)] = None
    installments_paid_before: Annotated[int | None, Field(default=None, ge=0, le=600)] = None
    installment_amount_cents: Cents | None = None
    first_due_date: date | None = None
    note: Note = None
    version: int | None = None


class DebtPayIn(Strict):
    account_id: UUID
    amount_cents: Cents
    interest_cents: Annotated[int | None, Field(default=None, ge=0, le=100_000_000_000_000)] = None
    tx_date: date | None = None
    payment_type: Literal["parcela", "amortizacao", "quitacao"] = "parcela"


class DebtEventIn(Strict):
    kind: Literal["encargo", "desconto"]
    amount_cents: Cents
    event_date: date | None = None
    description: Annotated[str | None, Field(default=None, max_length=120)] = None


class DebtRenegotiateIn(Strict):
    new_balance_cents: Cents
    creditor: Annotated[str | None, Field(default=None, max_length=80)] = None
    description: Annotated[str | None, Field(default=None, max_length=120)] = None
    interest_rate: Rate | None = None
    rate_period: Literal["mensal", "anual"] | None = None
    installments_total: Annotated[int | None, Field(default=None, ge=1, le=600)] = None
    installment_amount_cents: Cents | None = None
    first_due_date: date | None = None
    note: Note = None


class StrategyIn(Strict):
    extra_monthly_cents: Annotated[int, Field(ge=0, le=100_000_000_000_000)] = 0


@router.get("/dividas")
def debts_list(svc: Svc, incluir_encerradas: bool = True) -> list[dict[str, Any]]:
    return svc.run(lambda c: debts.list_debts(c, include_closed=incluir_encerradas))


@router.post("/dividas", status_code=201)
def debts_create(payload: DebtIn, svc: Svc) -> JSONResponse:
    return svc.create(payload, lambda c: debts.create_debt(c, payload.model_dump()))


@router.post("/dividas/estrategias")
def debts_strategies(payload: StrategyIn, svc: Svc) -> dict[str, Any]:
    return svc.run(lambda c: debts.strategies(c, payload.extra_monthly_cents))


@router.get("/dividas/{debt_id}")
def debts_get(debt_id: UUID, svc: Svc) -> dict[str, Any]:
    return svc.run(lambda c: debts.get_debt(c, debt_id))


@router.patch("/dividas/{debt_id}")
def debts_update(debt_id: UUID, payload: DebtPatch, svc: Svc) -> dict[str, Any]:
    data = payload.model_dump(exclude_unset=True)
    return svc.run(lambda c: debts.update_debt(c, debt_id, data))


@router.post("/dividas/{debt_id}/pagamentos", status_code=201)
def debts_pay(debt_id: UUID, payload: DebtPayIn, svc: Svc) -> JSONResponse:
    return svc.create(payload, lambda c: debts.pay_debt(c, debt_id, payload.model_dump()))


@router.post("/dividas/{debt_id}/eventos", status_code=201)
def debts_event(debt_id: UUID, payload: DebtEventIn, svc: Svc) -> JSONResponse:
    return svc.create(payload, lambda c: debts.add_event(c, debt_id, payload.model_dump()))


@router.post("/dividas/{debt_id}/renegociar", status_code=201)
def debts_renegotiate(debt_id: UUID, payload: DebtRenegotiateIn, svc: Svc) -> JSONResponse:
    return svc.create(payload, lambda c: debts.renegotiate_debt(c, debt_id, payload.model_dump()))


@router.post("/dividas/{debt_id}/cancelar")
def debts_cancel(debt_id: UUID, svc: Svc) -> dict[str, Any]:
    return svc.run(lambda c: debts.cancel_debt(c, debt_id))
