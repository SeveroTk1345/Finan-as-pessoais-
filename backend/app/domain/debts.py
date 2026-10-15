"""Regras de dívidas e simulação de estratégias de quitação (funções puras).

Matemática com ``Decimal``; valores finais arredondados para centavos meio para
cima (F6). Taxas desconhecidas nunca viram zero sem aviso (F-DIV-3).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum

from app.domain.dates import monthly_occurrence
from app.domain.money import MAX_ABS_CENTS, Money, round_to_cents

HUNDRED = Decimal(100)


def monthly_rate(rate_percent: Decimal, period: str) -> Decimal:
    """Taxa mensal equivalente, em fração (1% -> 0.01). Anual: (1 + a)^(1/12) - 1."""
    r = rate_percent / HUNDRED
    if period == "mensal":
        return r
    if period == "anual":
        return (Decimal(1) + r) ** (Decimal(1) / Decimal(12)) - Decimal(1)
    raise ValueError(f"período de taxa inválido: {period}")


def annual_rate(rate_percent: Decimal, period: str) -> Decimal:
    r = rate_percent / HUNDRED
    if period == "anual":
        return r
    if period == "mensal":
        return (Decimal(1) + r) ** 12 - Decimal(1)
    raise ValueError(f"período de taxa inválido: {period}")


@dataclass(frozen=True, slots=True)
class DebtMovement:
    """Algo que muda o saldo devedor depois da data âncora."""

    on: date
    kind: str  # pagamento | encargo | desconto | renegociacao_baixa
    amount: Money
    interest: Money | None = None  # só para pagamento


@dataclass(frozen=True, slots=True)
class DebtBalance:
    balance: Money
    principal_paid: Money
    interest_paid: Money
    total_paid: Money
    estimated: bool  # algum pagamento sem informação de juros abateu o valor inteiro


def debt_balance(anchor: Money, anchor_date: date, movements: Sequence[DebtMovement]) -> DebtBalance:
    """Saldo ancorado (F-DIV-1): saldo informado + encargos - descontos - principal pago.

    Sem juros informados, o pagamento inteiro abate o saldo e o resultado é marcado
    como estimado (F-DIV-2). O saldo nunca fica negativo.
    """
    bal = anchor.cents
    principal = interest = total_paid = 0
    estimated = False
    for m in sorted(movements, key=lambda x: x.on):
        if m.on < anchor_date:
            continue
        if m.kind == "pagamento":
            paid_interest = m.interest.cents if m.interest is not None else 0
            if m.interest is None:
                estimated = True
            principal_part = m.amount.cents - paid_interest
            bal -= principal_part
            principal += principal_part
            interest += paid_interest
            total_paid += m.amount.cents
        elif m.kind == "encargo":
            bal += m.amount.cents
        elif m.kind in ("desconto", "renegociacao_baixa"):
            bal -= m.amount.cents
        else:
            raise ValueError(f"movimento de dívida inválido: {m.kind}")
    return DebtBalance(
        balance=Money(max(bal, 0)),
        principal_paid=Money(principal),
        interest_paid=Money(interest),
        total_paid=Money(total_paid),
        estimated=estimated,
    )


@dataclass(frozen=True, slots=True)
class InstallmentProgress:
    paid: int
    total: int | None
    remaining: int | None
    next_due: date | None


def installment_progress(
    total: int | None, paid_before: int, paid_now: int, first_due: date | None
) -> InstallmentProgress:
    paid = paid_before + paid_now
    if total is not None:
        paid = min(paid, total)
    remaining = None if total is None else total - paid
    next_due = None
    if first_due is not None and (remaining is None or remaining > 0):
        next_due = monthly_occurrence(first_due, paid)
    return InstallmentProgress(paid, total, remaining, next_due)


# --- estratégias ---------------------------------------------------------------


class Strategy(StrEnum):
    AVALANCHE = "maior_juros"
    BOLA_DE_NEVE = "menor_saldo"
    MENOR_PARCELA = "menor_parcela"
    EQUILIBRADA = "equilibrada"


STRATEGY_LABELS = {
    Strategy.AVALANCHE: "Maior juros primeiro",
    Strategy.BOLA_DE_NEVE: "Menor saldo primeiro",
    Strategy.MENOR_PARCELA: "Menor parcela primeiro",
    Strategy.EQUILIBRADA: "Equilibrada",
}


@dataclass(frozen=True, slots=True)
class SimDebt:
    id: str
    name: str
    balance: Money
    monthly_rate: Decimal | None  # fração; None = desconhecida
    minimum_payment: Money  # parcela; zero se desconhecida


@dataclass(frozen=True, slots=True)
class StrategyResult:
    strategy: Strategy
    order: list[str]
    months: int | None  # None: não quita dentro do horizonte
    total_paid: Money
    total_interest: Money
    payoff_month: dict[str, int]
    warnings: list[str] = field(default_factory=list)


def _priority(strategy: Strategy, debts: Sequence[SimDebt]) -> list[SimDebt]:
    if strategy is Strategy.AVALANCHE:
        known = sorted(
            (d for d in debts if d.monthly_rate is not None),
            key=lambda d: (-(d.monthly_rate or Decimal(0)), d.balance.cents, d.id),
        )
        unknown = sorted((d for d in debts if d.monthly_rate is None), key=lambda d: d.balance.cents)
        return known + unknown
    if strategy is Strategy.BOLA_DE_NEVE:
        return sorted(debts, key=lambda d: (d.balance.cents, d.id))
    if strategy is Strategy.MENOR_PARCELA:
        # Quitar primeiro a dívida que acaba mais rápido libera a parcela dela no mês.
        return sorted(
            debts,
            key=lambda d: (
                Decimal(d.balance.cents) / Decimal(d.minimum_payment.cents)
                if d.minimum_payment.cents
                else Decimal("Infinity"),
                d.id,
            ),
        )
    # Equilibrada (F-DIV-6)
    max_rate = max((d.monthly_rate for d in debts if d.monthly_rate is not None), default=None)
    ratios = {
        d.id: (Decimal(d.minimum_payment.cents) / Decimal(d.balance.cents)) if d.balance.cents else Decimal(0)
        for d in debts
    }
    max_ratio = max(ratios.values(), default=Decimal(0))

    def score(d: SimDebt) -> Decimal:
        flow = ratios[d.id] / max_ratio if max_ratio else Decimal(0)
        if d.monthly_rate is None or not max_rate:
            return Decimal("0.5") * flow
        return Decimal("0.5") * (d.monthly_rate / max_rate) + Decimal("0.5") * flow

    return sorted(debts, key=lambda d: (-score(d), d.id))


def simulate(
    strategy: Strategy, debts: Sequence[SimDebt], extra_monthly: Money, *, max_months: int = 600
) -> StrategyResult:
    """Simula mês a mês: juros (taxas conhecidas), parcelas mínimas e o valor extra
    direcionado à primeira dívida da fila. Parcelas de dívidas quitadas passam a
    reforçar a próxima da fila."""
    warnings: list[str] = []
    if any(d.monthly_rate is None for d in debts):
        warnings.append(
            "Há dívidas sem taxa de juros informada: os juros delas não foram considerados, "
            "então o resultado é otimista."
        )
    if any(d.minimum_payment.cents == 0 for d in debts):
        warnings.append("Há dívidas sem valor de parcela informado.")

    order = _priority(strategy, debts)
    balances = {d.id: Decimal(d.balance.cents) for d in debts}
    budget = sum((d.minimum_payment.cents for d in debts), 0) + extra_monthly.cents
    total_paid = Decimal(0)
    total_interest = Decimal(0)
    payoff: dict[str, int] = {}

    month = 0
    while any(b > 0 for b in balances.values()):
        month += 1
        # Saldo crescendo sem parar (juros maiores que os pagamentos): interrompe antes
        # de os números ficarem absurdos.
        if month > max_months or sum(balances.values()) > MAX_ABS_CENTS:
            warnings.append(
                "Com esses valores, as dívidas não são quitadas em 50 anos. Os juros superam os pagamentos."
            )
            return StrategyResult(strategy, [d.id for d in order], None, Money(0), Money(0), payoff, warnings)
        for d in debts:
            if balances[d.id] > 0 and d.monthly_rate:
                interest = (balances[d.id] * d.monthly_rate).quantize(Decimal(1), rounding=ROUND_HALF_UP)
                balances[d.id] += interest
                total_interest += interest
        available = Decimal(budget)
        for d in debts:  # mínimos primeiro
            if balances[d.id] > 0:
                pay = min(Decimal(d.minimum_payment.cents), balances[d.id], available)
                balances[d.id] -= pay
                available -= pay
                total_paid += pay
        for d in order:  # sobra vai para a prioridade
            if available <= 0:
                break
            if balances[d.id] > 0:
                pay = min(balances[d.id], available)
                balances[d.id] -= pay
                available -= pay
                total_paid += pay
        for d in debts:
            if balances[d.id] <= 0 and d.id not in payoff:
                payoff[d.id] = month
        if available == Decimal(budget) and budget == 0:
            warnings.append("Sem parcelas nem valor extra, não há como simular a quitação.")
            return StrategyResult(strategy, [d.id for d in order], None, Money(0), Money(0), payoff, warnings)

    return StrategyResult(
        strategy=strategy,
        order=[d.id for d in order],
        months=month,
        total_paid=round_to_cents(total_paid / HUNDRED, ROUND_HALF_UP),
        total_interest=round_to_cents(total_interest / HUNDRED, ROUND_HALF_UP),
        payoff_month=payoff,
        warnings=warnings,
    )
