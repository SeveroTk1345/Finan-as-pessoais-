"""Investimentos: capital aportado, preço médio, valor atual, ganho e TIR (puras).

Regras: aporte não é ganho; retirada não é perda (F-INV-1). O valor atual vem sempre
de informação manual com data (F-INV-3).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from app.domain.money import Money, round_to_cents

CAPITAL_IN = {"aporte", "compra"}
CAPITAL_OUT = {"retirada", "venda", "amortizacao"}
INCOME = {"rendimento", "dividendo", "juros"}
STALE_DAYS = 30


@dataclass(frozen=True, slots=True)
class Movement:
    on: date
    kind: str
    amount: Money  # valor bruto da operação
    fees: Money = field(default_factory=Money.zero)
    quantity: Decimal | None = None
    paid_to_account: bool = False  # rendimento recebido em dinheiro


@dataclass(frozen=True, slots=True)
class Valuation:
    on: date
    value: Money | None = None  # renda fixa e outros
    unit_price: Money | None = None  # renda variável


@dataclass(frozen=True, slots=True)
class Position:
    quantity: Decimal
    cost: Money  # custo de aquisição das cotas que ainda tenho
    average_price: Money | None
    realized_gain: Money  # ganho ou perda nas vendas


def position(movements: Sequence[Movement]) -> Position:
    """Preço médio (F-INV-2): compras somam quantidade e custo (com taxas); vendas
    retiram custo proporcional à quantidade vendida."""
    qty = Decimal(0)
    cost = 0
    realized = 0
    for m in sorted(movements, key=lambda x: x.on):
        if m.kind == "compra" and m.quantity:
            qty += m.quantity
            cost += m.amount.cents + m.fees.cents
        elif m.kind == "venda" and m.quantity:
            if m.quantity > qty:
                raise ValueError("venda maior que a quantidade em carteira")
            removed = int((Decimal(cost) * m.quantity / qty).quantize(Decimal(1), rounding=ROUND_HALF_UP))
            realized += m.amount.cents - m.fees.cents - removed
            cost -= removed
            qty -= m.quantity
    avg = None
    if qty > 0:
        avg = round_to_cents(Decimal(cost) / qty / Decimal(100), ROUND_HALF_UP)
    return Position(qty, Money(cost), avg, Money(realized))


@dataclass(frozen=True, slots=True)
class Summary:
    invested: Money  # aportes - retiradas de capital (custo para renda variável)
    total_contributed: Money  # soma de todos os aportes/compras
    total_withdrawn: Money
    income_received: Money  # rendimentos pagos em dinheiro
    fees_paid: Money
    current_value: Money | None
    value_date: date | None
    stale: bool
    estimated_gain: Money | None


def summarize(
    movements: Sequence[Movement],
    valuations: Sequence[Valuation],
    *,
    variable_income: bool,
    today: date,
) -> Summary:
    contributed = withdrawn = income = fees = 0
    for m in movements:
        if m.kind in CAPITAL_IN:
            contributed += m.amount.cents + m.fees.cents
        elif m.kind in CAPITAL_OUT:
            withdrawn += m.amount.cents - m.fees.cents
        elif m.kind in INCOME and m.paid_to_account:
            income += m.amount.cents
        elif m.kind == "taxa":
            fees += m.amount.cents

    if variable_income:
        pos = position(movements)
        invested = pos.cost
    else:
        invested = Money(contributed - withdrawn)

    latest = max(valuations, key=lambda v: v.on, default=None)
    current: Money | None = None
    value_date: date | None = None
    if latest is not None:
        value_date = latest.on
        if variable_income:
            if latest.unit_price is not None:
                pos = position(movements)
                current = round_to_cents(
                    pos.quantity * Decimal(latest.unit_price.cents) / Decimal(100), ROUND_HALF_UP
                )
        elif latest.value is not None:
            current = latest.value

    gain = None
    if current is not None:
        gain = Money(current.cents + withdrawn + income - contributed - fees)
    stale = value_date is None or (today - value_date).days > STALE_DAYS
    return Summary(
        invested=invested,
        total_contributed=Money(contributed),
        total_withdrawn=Money(withdrawn),
        income_received=Money(income),
        fees_paid=Money(fees),
        current_value=current,
        value_date=value_date,
        stale=stale,
        estimated_gain=gain,
    )


def cash_flows(
    movements: Sequence[Movement], current: Money | None, value_date: date | None
) -> list[tuple[date, int]]:
    """Fluxos do ponto de vista do investidor: saídas negativas, entradas positivas,
    e o valor atual como entrada final na data em que foi informado."""
    flows: list[tuple[date, int]] = []
    for m in movements:
        if m.kind in CAPITAL_IN:
            flows.append((m.on, -(m.amount.cents + m.fees.cents)))
        elif m.kind in CAPITAL_OUT:
            flows.append((m.on, m.amount.cents - m.fees.cents))
        elif m.kind in INCOME and m.paid_to_account:
            flows.append((m.on, m.amount.cents))
        elif m.kind == "taxa":
            flows.append((m.on, -m.amount.cents))
    if current is not None and value_date is not None:
        flows.append((value_date, current.cents))
    return sorted(flows)


def xirr(flows: Sequence[tuple[date, int]]) -> Decimal | None:
    """TIR anualizada (fração: 0.12 = 12% ao ano) por bisseção, com Decimal.

    Retorna None quando os dados não bastam: menos de um fluxo negativo e um positivo,
    ou intervalo menor que 30 dias (anualizar poucos dias distorce o resultado).
    """
    if not flows or not any(v < 0 for _, v in flows) or not any(v > 0 for _, v in flows):
        return None
    start = min(d for d, _ in flows)
    if (max(d for d, _ in flows) - start).days < 30:
        return None
    year = Decimal(365)

    def npv(rate: Decimal) -> Decimal:
        base = Decimal(1) + rate
        return sum(
            (Decimal(v) / base ** (Decimal((d - start).days) / year) for d, v in flows),
            Decimal(0),
        )

    low, high = Decimal("-0.99"), Decimal(10)
    f_low, f_high = npv(low), npv(high)
    if f_low * f_high > 0:
        return None
    for _ in range(200):
        mid = (low + high) / 2
        f_mid = npv(mid)
        if abs(f_mid) < Decimal("0.0001") or (high - low) < Decimal("1e-10"):
            return mid.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
        if f_low * f_mid < 0:
            high, f_high = mid, f_mid
        else:
            low, f_low = mid, f_mid
    return ((low + high) / 2).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)


def real_rate(nominal: Decimal, inflation: Decimal) -> Decimal:
    """Taxa real (F-INV-4): (1 + nominal) / (1 + inflação) - 1."""
    return (Decimal(1) + nominal) / (Decimal(1) + inflation) - Decimal(1)
