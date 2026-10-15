"""Teto por categoria, gasto por dia e contas anuais (regras puras)."""

from __future__ import annotations

from datetime import date

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.domain.insights import (
    BudgetLevel,
    annual_saving,
    budget_status,
    median_cents,
    spend_per_day,
    suggest_limit,
)


@pytest.mark.parametrize(
    ("spent", "percent", "level", "left"),
    [
        (0, 0, BudgetLevel.OK, 50000),
        (39999, 79, BudgetLevel.OK, 10001),
        (40000, 80, BudgetLevel.PERTO, 10000),
        (50000, 100, BudgetLevel.PERTO, 0),  # chegou no teto, ainda não passou
        (50001, 100, BudgetLevel.PASSOU, -1),
        (75000, 150, BudgetLevel.PASSOU, -25000),
        (-1000, 0, BudgetLevel.OK, 50000),  # estorno maior que o gasto não vira "crédito" de teto
    ],
)
def test_situacao_do_teto(spent: int, percent: int, level: BudgetLevel, left: int) -> None:
    s = budget_status(50000, spent)
    assert (s.percent, s.level, s.left_cents) == (percent, level, left)


def test_teto_precisa_ser_positivo() -> None:
    with pytest.raises(ValueError):
        budget_status(0, 100)


def test_mediana_impar_e_par() -> None:
    assert median_cents([300, 100, 200]) == 200
    assert median_cents([100, 200, 300, 400]) == 250
    assert median_cents([100, 201]) == 151  # arredonda para cima


def test_sugestao_ignora_mes_fora_do_comum() -> None:
    # Mercado: cerca de R$ 600 por mês e um mês de R$ 3.000 (festa). A média passaria
    # de R$ 1.000; a mediana é R$ 605,00 e a sugestão, arredondada, R$ 610,00.
    months = [60000, 58000, 300000, 61000, 62000, 59500]
    assert sum(months) // len(months) > 100000
    assert suggest_limit(months) == 61000


def test_sugestao_arredonda_para_cima_de_dez_em_dez() -> None:
    assert suggest_limit([12345, 12345, 12345]) == 13000


def test_sem_base_nao_sugere() -> None:
    assert suggest_limit([]) is None
    assert suggest_limit([0, 0, 0, 0, 0, 5000]) is None  # só 1 mês com gasto
    assert suggest_limit([0, 0, 0, 5000, 5000, 5000]) == 3000  # mediana com zeros: (0 + 5000) / 2


@given(st.lists(st.integers(min_value=0, max_value=10**9), min_size=1, max_size=12))
def test_sugestao_fica_entre_o_minimo_e_o_maximo_arredondado(values: list[int]) -> None:
    s = suggest_limit(values)
    if s is not None:
        assert s % 1000 == 0
        assert min(values) <= s <= max(values) + 999


def test_gasto_por_dia_ate_a_proxima_renda() -> None:
    p = spend_per_day(100000, date(2026, 10, 15), date(2026, 10, 20))
    assert (p.days, p.per_day_cents) == (5, 20000)


def test_gasto_por_dia_sem_sobra_e_renda_hoje() -> None:
    assert spend_per_day(-5000, date(2026, 10, 15), date(2026, 11, 5)).per_day_cents == 0
    p = spend_per_day(999, date(2026, 10, 15), date(2026, 10, 15))
    assert (p.days, p.per_day_cents) == (1, 999)


def test_gasto_por_dia_arredonda_para_baixo() -> None:
    assert spend_per_day(100, date(2026, 10, 1), date(2026, 10, 4)).per_day_cents == 33


def test_conta_anual_guardar_ate_o_vencimento() -> None:
    # IPVA de R$ 1.200,00 em janeiro, olhando em outubro: 3 meses para juntar.
    a = annual_saving(120000, date(2026, 10, 15), date(2027, 1, 20))
    assert (a.months_left, a.per_month_cents, a.steady_cents) == (3, 40000, 10000)


def test_conta_anual_vencendo_neste_mes_e_arredondamento() -> None:
    assert annual_saving(120000, date(2026, 10, 1), date(2026, 10, 30)).per_month_cents == 120000
    a = annual_saving(100000, date(2026, 10, 15), date(2027, 1, 10))
    assert a.per_month_cents == 33334 and a.steady_cents == 8334
