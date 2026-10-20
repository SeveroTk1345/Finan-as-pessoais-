"""Plano do mês: projeção de investimento e divisão da renda."""

from __future__ import annotations

from decimal import Decimal

from hypothesis import given
from hypothesis import strategies as st

from app.domain.goals import savings_projection, suggest_split
from app.domain.money import Money


def test_projecao_sem_rendimento_e_so_a_soma() -> None:
    p = savings_projection(Money(50000), None, 12)
    assert p.deposited == Money(600000) and p.estimated == Money(600000)


def test_projecao_com_rendimento_bate_com_a_formula_fechada() -> None:
    # R$ 100,00 por mês a 12% ao ano por 12 meses: VF = 100 * ((1+i)^12 - 1) / i,
    # com i = 1,12^(1/12) - 1, ou seja, 100 * 0,12 / i ≈ R$ 1.264,65.
    p = savings_projection(Money(10000), Decimal("12"), 12)
    assert p.deposited == Money(120000)
    assert abs(p.estimated.cents - 126465) <= 2  # arredondamento mês a mês


def test_projecao_zero_meses() -> None:
    assert savings_projection(Money(10000), Decimal("10"), 0).estimated == Money(0)


def test_sugestao_vinte_por_cento_sem_passar_do_que_sobra() -> None:
    s = suggest_split(Money(500000), Money(300000))
    assert (s.invest_suggested, s.invest, s.free) == (Money(100000), Money(100000), Money(100000))
    # Sobra pouco: a sugestão é só o que sobra.
    s = suggest_split(Money(500000), Money(450000))
    assert (s.invest, s.free) == (Money(50000), Money(0))
    # Contas maiores que a renda: nada a investir, livre negativo.
    s = suggest_split(Money(300000), Money(350000))
    assert (s.invest, s.free) == (Money(0), Money(-50000))


def test_valor_escolhido_pela_pessoa_e_respeitado() -> None:
    s = suggest_split(Money(500000), Money(300000), invest=Money(250000))
    assert (s.invest, s.free, s.invest_suggested) == (Money(250000), Money(-50000), Money(100000))


@given(
    income=st.integers(min_value=0, max_value=10**10),
    bills=st.integers(min_value=0, max_value=10**10),
)
def test_divisao_sempre_soma_a_renda(income: int, bills: int) -> None:
    s = suggest_split(Money(income), Money(bills))
    assert s.bills.cents + s.invest.cents + s.free.cents == income
    assert 0 <= s.invest.cents <= max(income * 20 // 100, 0)
