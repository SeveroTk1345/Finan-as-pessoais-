from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.domain.debts import (
    DebtMovement,
    SimDebt,
    Strategy,
    annual_rate,
    debt_balance,
    installment_progress,
    monthly_rate,
    simulate,
)
from app.domain.money import Money


def test_taxa_anual_para_mensal_e_composta() -> None:
    m = monthly_rate(Decimal(12), "anual")
    assert abs(m - Decimal("0.009488793")) < Decimal("0.000000001")
    assert m != Decimal("0.01")  # 12/12 seria errado
    assert monthly_rate(Decimal(2), "mensal") == Decimal("0.02")
    assert abs(annual_rate(Decimal(1), "mensal") - Decimal("0.126825")) < Decimal("0.000001")
    with pytest.raises(ValueError):
        monthly_rate(Decimal(1), "semanal")


def test_saldo_ancorado_com_juros_informados() -> None:
    result = debt_balance(
        Money(1000000),
        date(2026, 10, 1),
        [DebtMovement(date(2026, 10, 10), "pagamento", Money(50000), Money(5000))],
    )
    assert result.balance == Money(955000)
    assert result.principal_paid == Money(45000)
    assert result.interest_paid == Money(5000)
    assert result.estimated is False


def test_saldo_sem_juros_informados_e_estimado() -> None:
    result = debt_balance(
        Money(1000000),
        date(2026, 10, 1),
        [DebtMovement(date(2026, 10, 10), "pagamento", Money(50000))],
    )
    assert result.balance == Money(950000)
    assert result.estimated is True


def test_encargo_desconto_e_movimento_antes_da_ancora() -> None:
    result = debt_balance(
        Money(100000),
        date(2026, 10, 1),
        [
            DebtMovement(date(2026, 9, 1), "pagamento", Money(99999)),  # antes da âncora: ignora
            DebtMovement(date(2026, 10, 2), "encargo", Money(2000)),
            DebtMovement(date(2026, 10, 3), "desconto", Money(500)),
        ],
    )
    assert result.balance == Money(101500)


def test_saldo_nunca_negativo_e_renegociacao_zera() -> None:
    over = debt_balance(
        Money(1000), date(2026, 1, 1), [DebtMovement(date(2026, 1, 2), "pagamento", Money(5000))]
    )
    assert over.balance == Money(0)
    reneg = debt_balance(
        Money(1000),
        date(2026, 1, 1),
        [DebtMovement(date(2026, 1, 2), "renegociacao_baixa", Money(1000))],
    )
    assert reneg.balance == Money(0)


def test_progresso_de_parcelas() -> None:
    p = installment_progress(10, 2, 2, date(2026, 1, 31))
    assert (p.paid, p.remaining) == (4, 6)
    assert p.next_due == date(2026, 5, 31)  # 4 meses depois da primeira, sem deslizar
    done = installment_progress(10, 5, 7, date(2026, 1, 10))
    assert (done.paid, done.remaining, done.next_due) == (10, 0, None)
    unknown = installment_progress(None, 0, 3, None)
    assert unknown.remaining is None


# --- estratégias ---------------------------------------------------------------

A = SimDebt("a", "Cartão antigo", Money(500000), Decimal("0.08"), Money(30000))
B = SimDebt("b", "Empréstimo", Money(200000), Decimal("0.02"), Money(20000))
C = SimDebt("c", "Loja", Money(80000), None, Money(10000))


def test_ordem_das_estrategias() -> None:
    assert simulate(Strategy.AVALANCHE, [A, B, C], Money(0)).order == ["a", "b", "c"]
    assert simulate(Strategy.BOLA_DE_NEVE, [A, B, C], Money(0)).order == ["c", "b", "a"]
    # Menor parcela: quem termina antes (saldo/parcela) primeiro: c=8, b=10, a=16,7
    assert simulate(Strategy.MENOR_PARCELA, [A, B, C], Money(0)).order == ["c", "b", "a"]


def test_taxa_desconhecida_gera_aviso() -> None:
    r = simulate(Strategy.AVALANCHE, [A, B, C], Money(10000))
    assert any("sem taxa" in w for w in r.warnings)
    r2 = simulate(Strategy.AVALANCHE, [A, B], Money(10000))
    assert not any("sem taxa" in w for w in r2.warnings)


def test_avalanche_paga_menos_juros_que_bola_de_neve() -> None:
    debts = [SimDebt("d", "Financiamento", Money(500000), Decimal("0.04"), Money(30000)), B]
    ava = simulate(Strategy.AVALANCHE, debts, Money(20000))
    snow = simulate(Strategy.BOLA_DE_NEVE, debts, Money(20000))
    assert ava.months is not None and snow.months is not None
    assert ava.total_interest.cents <= snow.total_interest.cents
    # Total pago = saldo inicial + juros, para qualquer estratégia.
    for r in (ava, snow):
        assert r.total_paid.cents == 700000 + r.total_interest.cents


def test_parcela_menor_que_os_juros_nunca_quita() -> None:
    # Cartão a 8% ao mês: juros de R$ 400,00 sobre R$ 5.000,00, parcela de R$ 300,00.
    r = simulate(Strategy.AVALANCHE, [A], Money(0))
    assert r.months is None


def test_valor_extra_reduz_o_prazo() -> None:
    d = SimDebt("d", "Financiamento", Money(300000), Decimal("0.03"), Money(20000))
    slow = simulate(Strategy.AVALANCHE, [d, B], Money(0))
    fast = simulate(Strategy.AVALANCHE, [d, B], Money(50000))
    assert slow.months is not None and fast.months is not None
    assert fast.months < slow.months


def test_simulacao_sem_juros_e_exata() -> None:
    d = SimDebt("x", "Sem juros", Money(100000), Decimal(0), Money(25000))
    r = simulate(Strategy.BOLA_DE_NEVE, [d], Money(0))
    assert r.months == 4
    assert r.total_interest == Money(0)
    assert r.total_paid == Money(100000)
    assert r.payoff_month == {"x": 4}


def test_juros_maiores_que_pagamento_nao_quitam() -> None:
    d = SimDebt("x", "Impagável", Money(1000000), Decimal("0.10"), Money(50000))
    r = simulate(Strategy.AVALANCHE, [d], Money(0))
    assert r.months is None
    assert any("50 anos" in w for w in r.warnings)


def test_equilibrada_considera_juros_e_fluxo() -> None:
    r = simulate(Strategy.EQUILIBRADA, [A, B, C], Money(0))
    assert set(r.order) == {"a", "b", "c"}
    assert r.order[0] == "a"  # maior taxa e fluxo razoável
