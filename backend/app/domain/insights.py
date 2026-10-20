"""Regras puras dos recursos de acompanhamento (só inteiros, sem float).

* Teto por categoria: situação e sugestão pela mediana dos meses anteriores.
* Quanto posso gastar por dia até a próxima renda.
* Contas anuais: quanto guardar por mês até o vencimento.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum

NEAR_LIMIT_PERCENT = 80
SUGGESTION_STEP_CENTS = 1000  # sugestões arredondadas para cima, de R$ 10,00 em R$ 10,00
MIN_MONTHS_WITH_SPENDING = 3


class BudgetLevel(StrEnum):
    OK = "ok"
    PERTO = "perto"  # a partir de 80% do teto
    PASSOU = "passou"  # acima do teto


@dataclass(frozen=True, slots=True)
class BudgetStatus:
    percent: int  # arredondado para baixo; pode passar de 100
    level: BudgetLevel
    left_cents: int  # negativo quando passou


def budget_status(limit_cents: int, spent_cents: int) -> BudgetStatus:
    if limit_cents <= 0:
        raise ValueError("o teto deve ser positivo")
    spent = max(spent_cents, 0)
    percent = spent * 100 // limit_cents
    if spent > limit_cents:
        level = BudgetLevel.PASSOU
    elif percent >= NEAR_LIMIT_PERCENT:
        level = BudgetLevel.PERTO
    else:
        level = BudgetLevel.OK
    return BudgetStatus(percent, level, limit_cents - spent)


def median_cents(values: list[int]) -> int:
    """Mediana em inteiros; com quantidade par, média dos dois do meio arredondada para cima."""
    if not values:
        raise ValueError("lista vazia")
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return -(-(ordered[mid - 1] + ordered[mid]) // 2)


def suggest_limit(monthly_spending: list[int]) -> int | None:
    """Teto sugerido: mediana dos gastos mensais (meses completos, inclusive os de zero),
    arredondada para cima de R$ 10,00 em R$ 10,00. A mediana não se deixa levar por um
    mês fora do comum (um conserto grande, por exemplo), ao contrário da média.
    Sem pelo menos 3 meses com gasto, não há base para sugerir."""
    if sum(1 for v in monthly_spending if v > 0) < MIN_MONTHS_WITH_SPENDING:
        return None
    m = median_cents([max(v, 0) for v in monthly_spending])
    if m <= 0:
        return None
    return -(-m // SUGGESTION_STEP_CENTS) * SUGGESTION_STEP_CENTS


@dataclass(frozen=True, slots=True)
class PerDay:
    days: int
    per_day_cents: int  # 0 quando não sobra


def spend_per_day(free_cents: int, today: date, until: date) -> PerDay:
    """Quanto dá para gastar por dia até a data da próxima renda (sem contar esse dia,
    em que o dinheiro novo entra). Pelo menos 1 dia; arredonda para baixo."""
    days = max(1, (until - today).days)
    return PerDay(days, max(free_cents, 0) // days)


@dataclass(frozen=True, slots=True)
class AnnualSaving:
    months_left: int  # meses de guardar antes do vencimento (0 = vence neste mês)
    per_month_cents: int  # para juntar até o vencimento
    steady_cents: int  # um doze avos: o ritmo de todo ano


def annual_saving(amount_cents: int, today: date, due: date) -> AnnualSaving:
    """Conta anual (IPVA, IPTU, seguro): quanto guardar por mês, arredondado para cima.
    Vencendo neste mês, o valor inteiro é para agora."""
    months_left = max(0, (due.year - today.year) * 12 + due.month - today.month)
    per_month = amount_cents if months_left == 0 else -(-amount_cents // months_left)
    return AnnualSaving(months_left, per_month, -(-amount_cents // 12))
