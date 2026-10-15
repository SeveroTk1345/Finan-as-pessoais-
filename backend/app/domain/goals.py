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
