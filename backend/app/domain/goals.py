"""Metas: progresso e projeção (puras). Projeções declaram premissas (F-META-1)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from app.domain.dates import add_months
from app.domain.debts import monthly_rate
from app.domain.money import Money


@dataclass(frozen=True, slots=True)
class GoalProgress:
    accumulated: Money
    missing: Money
    percent: int  # 0 a 100, arredondado para baixo
    months_needed: int | None
    projected_date: date | None
    on_track: bool | None  # None: sem prazo ou sem contribuição planejada
    assumption: str


def goal_progress(
    target: Money,
    accumulated: Money,
    *,
    today: date,
    planned_monthly: Money | None,
    annual_rate_percent: Decimal | None,
    target_date: date | None,
    max_months: int = 1200,
) -> GoalProgress:
    acc = max(accumulated.cents, 0)
    missing = max(target.cents - acc, 0)
    percent = min(100, acc * 100 // target.cents) if target.cents else 0

    if annual_rate_percent:
        assumption = (
            f"Estimativa com depósito mensal planejado e rendimento de "
            f"{annual_rate_percent}% ao ano. Rendimento não é garantido."
        )
    else:
        assumption = "Estimativa só com o depósito mensal planejado, sem rendimento."

    if missing == 0:
        return GoalProgress(Money(acc), Money(0), percent, 0, today, True, assumption)
    if not planned_monthly or planned_monthly.cents <= 0:
        return GoalProgress(Money(acc), Money(missing), percent, None, None, None, assumption)

    rate = monthly_rate(annual_rate_percent, "anual") if annual_rate_percent else Decimal(0)
    balance = Decimal(acc)
    months = 0
    while balance < target.cents and months < max_months:
        months += 1
        balance = (balance * (1 + rate)).quantize(Decimal(1), rounding=ROUND_HALF_UP)
        balance += planned_monthly.cents
    if balance < target.cents:
        return GoalProgress(Money(acc), Money(missing), percent, None, None, False, assumption)
    projected = add_months(today, months)
    on_track = None if target_date is None else projected <= target_date
    return GoalProgress(Money(acc), Money(missing), percent, months, projected, on_track, assumption)


@dataclass(frozen=True, slots=True)
class SavingsProjection:
    months: int
    deposited: Money  # só o que a pessoa colocou
    estimated: Money  # com o rendimento informado (igual a deposited se não houver taxa)


def savings_projection(monthly: Money, annual_rate_percent: Decimal | None, months: int) -> SavingsProjection:
    """Depósito no fim de cada mês com rendimento composto mensal equivalente à taxa
    anual informada. Mesma convenção (e arredondamento mensal) de ``goal_progress``."""
    if months < 0 or monthly.cents < 0:
        raise ValueError("meses e depósito não podem ser negativos")
    rate = monthly_rate(annual_rate_percent, "anual") if annual_rate_percent else Decimal(0)
    balance = Decimal(0)
    for _ in range(months):
        balance = (balance * (1 + rate)).quantize(Decimal(1), rounding=ROUND_HALF_UP)
        balance += monthly.cents
    return SavingsProjection(months, Money(monthly.cents * months), Money(int(balance)))


@dataclass(frozen=True, slots=True)
class BudgetSplit:
    income: Money
    bills: Money
    invest: Money
    free: Money  # pode ser negativo: as contas e o investimento passam da renda
    invest_suggested: Money


def suggest_split(
    income: Money, bills: Money, invest: Money | None = None, invest_share_percent: int = 20
) -> BudgetSplit:
    """Divide a renda em contas, investimento e livre para gastar (só inteiros).

    Sugestão de investimento: ``invest_share_percent`` da renda (referência da regra
    50/30/20), sem passar do que sobra depois das contas. Se a pessoa informar outro
    valor, ele é usado e o "livre" pode ficar negativo, o que a tela avisa.
    """
    left = income.cents - bills.cents
    suggested = max(0, min(income.cents * invest_share_percent // 100, left))
    chosen = suggested if invest is None else invest.cents
    return BudgetSplit(income, bills, Money(chosen), Money(left - chosen), Money(suggested))
