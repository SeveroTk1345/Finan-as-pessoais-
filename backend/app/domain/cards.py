"""Regras de cartão de crédito (funções puras).

Conceitos:
* Uma **fatura** é identificada pela data de vencimento (F-CARTAO-1). Ela é só um
  agrupamento: o total vem das parcelas, encargos e créditos atribuídos a ela.
* Cada parcela é atribuída a uma fatura na criação da compra (F-CARTAO-4).
* O **limite usado** soma tudo o que está ativo em todas as faturas e desconta
  créditos e pagamentos. Cada centavo entra uma vez, esteja a fatura aberta, fechada
  ou futura.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum

from app.domain.dates import YearMonth, clamp_day
from app.domain.money import Money, split_installments


@dataclass(frozen=True, slots=True)
class CardCycle:
    closing_day: int
    due_day: int
    closing_day_goes_next: bool = True  # F-CARTAO-2

    def __post_init__(self) -> None:
        if not (1 <= self.closing_day <= 31 and 1 <= self.due_day <= 31):
            raise ValueError("dias de fechamento e vencimento devem estar entre 1 e 31")

    @property
    def due_in_next_month(self) -> bool:
        """Vencimento no mês seguinte ao fechamento quando o dia de vencimento não é
        posterior ao de fechamento (ex.: fecha dia 25, vence dia 5)."""
        return self.due_day <= self.closing_day

    def due_date_for_closing_month(self, closing: YearMonth) -> date:
        month = closing.shift(1) if self.due_in_next_month else closing
        return clamp_day(month.year, month.month, self.due_day)

    def closing_date_for_due(self, due_date: date) -> date:
        due_month = YearMonth.of(due_date)
        month = due_month.shift(-1) if self.due_in_next_month else due_month
        return clamp_day(month.year, month.month, self.closing_day)

    def invoice_due_for_purchase(self, purchase_date: date) -> date:
        """Vencimento da fatura em que uma compra feita nesta data entra."""
        month = YearMonth.of(purchase_date)
        closing = clamp_day(month.year, month.month, self.closing_day)
        if purchase_date > closing or (purchase_date == closing and self.closing_day_goes_next):
            month = month.shift(1)
        return self.due_date_for_closing_month(month)

    def shift_invoice(self, due_date: date, months: int) -> date:
        """Vencimento da fatura ``months`` meses depois, sempre pelo dia configurado
        (não desliza: 31/01 -> 28/02 -> 31/03)."""
        m = YearMonth.of(due_date).shift(months)
        return clamp_day(m.year, m.month, self.due_day)


@dataclass(frozen=True, slots=True)
class PlannedInstallment:
    number: int
    amount: Money
    invoice_due_date: date


def plan_installments(
    cycle: CardCycle,
    purchase_date: date,
    total: Money,
    count: int,
    *,
    first_invoice_due: date | None = None,
) -> list[PlannedInstallment]:
    """Parcelas de uma compra, uma por fatura consecutiva a partir da primeira."""
    first = first_invoice_due or cycle.invoice_due_for_purchase(purchase_date)
    return [
        PlannedInstallment(i + 1, amount, cycle.shift_invoice(first, i))
        for i, amount in enumerate(split_installments(total, count))
    ]


class InvoiceStatus(StrEnum):
    FUTURA = "futura"
    ABERTA = "aberta"
    FECHADA = "fechada"
    VENCIDA = "vencida"
    PARCIALMENTE_PAGA = "parcialmente_paga"
    PAGA = "paga"
    COM_CREDITO = "com_credito"


@dataclass(frozen=True, slots=True)
class InvoiceItems:
    """Valores brutos de uma fatura (já somados por tipo)."""

    due_date: date
    charges: Money  # parcelas e encargos ativos
    credits: Money  # estornos, cancelamentos e renegociação
    payments: Money  # pagamentos de fatura realizados


@dataclass(frozen=True, slots=True)
class Invoice:
    due_date: date
    closing_date: date
    charges: Money
    credits: Money
    carried_credit: Money  # crédito que sobrou da fatura anterior
    payments: Money
    total: Money  # charges - credits - carried_credit
    remaining: Money  # max(total - payments, 0)
    credit_left: Money  # crédito que passa para a próxima fatura
    status: InvoiceStatus


def _status(
    cycle: CardCycle, today: date, due: date, closing: date, total: Money, paid: Money
) -> InvoiceStatus:
    open_due = cycle.invoice_due_for_purchase(today)
    remaining = total - paid
    if due > open_due:
        return InvoiceStatus.FUTURA
    if due == open_due:
        return InvoiceStatus.ABERTA
    _ = closing
    if remaining.is_negative():
        return InvoiceStatus.COM_CREDITO
    if remaining.is_zero():
        return InvoiceStatus.PAGA
    if today > due:
        return InvoiceStatus.VENCIDA
    if paid.cents > 0:
        return InvoiceStatus.PARCIALMENTE_PAGA
    return InvoiceStatus.FECHADA


def build_invoices(cycle: CardCycle, today: date, items: Iterable[InvoiceItems]) -> list[Invoice]:
    """Monta as faturas em ordem de vencimento, levando adiante o crédito que sobrar
    (ex.: estorno maior que a fatura). O crédito é derivado, nunca gravado, então
    não pode ser contado duas vezes."""
    result: list[Invoice] = []
    carry = Money.zero()
    for it in sorted(items, key=lambda x: x.due_date):
        closing = cycle.closing_date_for_due(it.due_date)
        total = it.charges - it.credits - carry
        balance = total - it.payments
        remaining = balance if balance.cents > 0 else Money.zero()
        credit_left = -balance if balance.is_negative() else Money.zero()
        status = _status(cycle, today, it.due_date, closing, total, it.payments)
        result.append(
            Invoice(
                due_date=it.due_date,
                closing_date=closing,
                charges=it.charges,
                credits=it.credits,
                carried_credit=carry,
                payments=it.payments,
                total=total,
                remaining=remaining,
                credit_left=credit_left,
                status=status,
            )
        )
        carry = credit_left
    return result


@dataclass(frozen=True, slots=True)
class LimitSummary:
    limit: Money
    used: Money
    available: Money
    credit_balance: Money  # quando pagamentos e créditos superam o usado


def limit_summary(limit: Money, charges: Money, credits: Money, payments: Money) -> LimitSummary:
    used = charges - credits - payments
    if used.is_negative():
        return LimitSummary(limit, Money.zero(), limit, -used)
    available = limit - used
    return LimitSummary(limit, used, available, Money.zero())


@dataclass(frozen=True, slots=True)
class InstallmentState:
    id: object
    amount: Money
    invoice_due_date: date
    active: bool


@dataclass(frozen=True, slots=True)
class CancellationPlan:
    """Resultado do cancelamento de uma compra (F-CARTAO-7)."""

    cancel_ids: list[object] = field(default_factory=list)
    credit_amount: Money = field(default_factory=Money.zero)
    credit_invoice_due: date | None = None


def plan_cancellation(
    cycle: CardCycle, today: date, installments: Sequence[InstallmentState]
) -> CancellationPlan:
    """Parcelas em faturas ainda abertas ou futuras são canceladas; parcelas em faturas
    já fechadas viram crédito na fatura aberta."""
    open_due = cycle.invoice_due_for_purchase(today)
    cancel: list[object] = []
    credit = Money.zero()
    for inst in installments:
        if not inst.active:
            continue
        if inst.invoice_due_date >= open_due:
            cancel.append(inst.id)
        else:
            credit = credit + inst.amount
    return CancellationPlan(cancel, credit, open_due if credit.cents > 0 else None)
