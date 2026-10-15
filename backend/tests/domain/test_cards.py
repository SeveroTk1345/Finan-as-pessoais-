from __future__ import annotations

from datetime import date

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.domain.cards import (
    CardCycle,
    InstallmentState,
    InvoiceItems,
    InvoiceStatus,
    build_invoices,
    limit_summary,
    plan_cancellation,
    plan_installments,
)
from app.domain.money import Money, total

# Fecha dia 25, vence dia 5 do mês seguinte (caso mais comum).
NEXT = CardCycle(closing_day=25, due_day=5)
# Fecha dia 3, vence dia 10 do mesmo mês.
SAME = CardCycle(closing_day=3, due_day=10)


@pytest.mark.parametrize(
    ("cycle", "purchase", "due"),
    [
        (NEXT, date(2026, 10, 24), date(2026, 11, 5)),
        (NEXT, date(2026, 10, 25), date(2026, 12, 5)),  # dia do fechamento: próxima (A1)
        (NEXT, date(2026, 10, 26), date(2026, 12, 5)),
        (NEXT, date(2026, 12, 24), date(2027, 1, 5)),  # virada de ano
        (NEXT, date(2026, 12, 26), date(2027, 2, 5)),
        (SAME, date(2026, 10, 2), date(2026, 10, 10)),
        (SAME, date(2026, 10, 3), date(2026, 11, 10)),
        (SAME, date(2026, 10, 20), date(2026, 11, 10)),
    ],
)
def test_fatura_da_compra(cycle: CardCycle, purchase: date, due: date) -> None:
    assert cycle.invoice_due_for_purchase(purchase) == due


def test_compra_no_dia_do_fechamento_configuravel() -> None:
    current = CardCycle(closing_day=25, due_day=5, closing_day_goes_next=False)
    assert current.invoice_due_for_purchase(date(2026, 10, 25)) == date(2026, 11, 5)


def test_fechamento_em_dia_inexistente_vira_fim_do_mes() -> None:
    # Fecha dia 30, vence dia 7: em fevereiro fecha no dia 28 (A2).
    cycle = CardCycle(closing_day=30, due_day=7)
    assert cycle.closing_date_for_due(date(2027, 3, 7)) == date(2027, 2, 28)
    assert cycle.invoice_due_for_purchase(date(2027, 2, 28)) == date(2027, 4, 7)
    assert cycle.invoice_due_for_purchase(date(2027, 2, 27)) == date(2027, 3, 7)
    assert cycle.closing_date_for_due(date(2028, 3, 7)) == date(2028, 2, 29)


def test_vencimento_dia_31_nao_desliza() -> None:
    cycle = CardCycle(closing_day=20, due_day=31)
    plan = plan_installments(cycle, date(2026, 1, 10), Money(40000), 4)
    assert [p.invoice_due_date for p in plan] == [
        date(2026, 1, 31),
        date(2026, 2, 28),
        date(2026, 3, 31),
        date(2026, 4, 30),
    ]


def test_parcelas_somam_o_total_e_vao_para_faturas_seguidas() -> None:
    plan = plan_installments(NEXT, date(2026, 10, 10), Money(100000), 3)
    assert [p.amount for p in plan] == [Money(33334), Money(33333), Money(33333)]
    assert [p.invoice_due_date for p in plan] == [
        date(2026, 11, 5),
        date(2026, 12, 5),
        date(2027, 1, 5),
    ]
    assert [p.number for p in plan] == [1, 2, 3]


@given(
    st.dates(min_value=date(2020, 1, 1), max_value=date(2035, 12, 31)),
    st.integers(1, 31),
    st.integers(1, 31),
    st.integers(1, 1_000_000_00),
    st.integers(1, 24),
)
def test_propriedades_do_parcelamento(purchase: date, closing: int, due: int, amount: int, n: int) -> None:
    cycle = CardCycle(closing_day=closing, due_day=due)
    plan = plan_installments(cycle, purchase, Money(amount), n)
    assert total([p.amount for p in plan]) == Money(amount)
    dues = [p.invoice_due_date for p in plan]
    assert dues == sorted(set(dues))  # uma parcela por fatura, sem repetir
    # A fatura sempre vence depois da compra e a compra é anterior ao fechamento dela
    # (ou igual, se o cartão estiver configurado assim).
    assert dues[0] > purchase
    assert cycle.closing_date_for_due(dues[0]) >= purchase


# --- faturas -------------------------------------------------------------------


def _items(due: date, charges: int, credits: int = 0, payments: int = 0) -> InvoiceItems:
    return InvoiceItems(due, Money(charges), Money(credits), Money(payments))


TODAY = date(2026, 10, 15)  # fatura aberta de NEXT: vence 05/11/2026


@pytest.mark.parametrize(
    ("item", "status", "remaining"),
    [
        (_items(date(2026, 12, 5), 100), InvoiceStatus.FUTURA, 100),
        (_items(date(2026, 11, 5), 100), InvoiceStatus.ABERTA, 100),
        (_items(date(2026, 10, 5), 100), InvoiceStatus.VENCIDA, 100),
        (_items(date(2026, 10, 5), 100, payments=100), InvoiceStatus.PAGA, 0),
        (_items(date(2026, 10, 5), 100, payments=40), InvoiceStatus.VENCIDA, 60),
        (_items(date(2026, 10, 5), 100, credits=100), InvoiceStatus.PAGA, 0),
        (_items(date(2026, 10, 5), 100, credits=150), InvoiceStatus.COM_CREDITO, 0),
    ],
)
def test_situacao_da_fatura(item: InvoiceItems, status: InvoiceStatus, remaining: int) -> None:
    [inv] = build_invoices(NEXT, TODAY, [item])
    assert inv.status is status
    assert inv.remaining == Money(remaining)


def test_fatura_fechada_ainda_nao_vencida() -> None:
    # Hoje 28/10: a fatura de 05/11 já fechou (25/10) e ainda não venceu.
    today = date(2026, 10, 28)
    [closed] = build_invoices(NEXT, today, [_items(date(2026, 11, 5), 500)])
    assert closed.status is InvoiceStatus.FECHADA
    [partial] = build_invoices(NEXT, today, [_items(date(2026, 11, 5), 500, payments=200)])
    assert partial.status is InvoiceStatus.PARCIALMENTE_PAGA
    assert partial.remaining == Money(300)


def test_pagamento_parcial_mantem_o_restante_na_propria_fatura() -> None:
    # F-CARTAO-5: o restante não é levado para a próxima fatura automaticamente.
    invoices = build_invoices(
        NEXT,
        TODAY,
        [_items(date(2026, 10, 5), 50000, payments=30000), _items(date(2026, 11, 5), 10000)],
    )
    assert [i.remaining for i in invoices] == [Money(20000), Money(10000)]
    assert sum(i.remaining.cents for i in invoices) == 30000  # nada duplicado


def test_credito_que_sobra_passa_para_a_proxima_fatura_uma_vez_so() -> None:
    invoices = build_invoices(
        NEXT,
        TODAY,
        [
            _items(date(2026, 10, 5), 10000, credits=15000),
            _items(date(2026, 11, 5), 8000),
            _items(date(2026, 12, 5), 8000),
        ],
    )
    assert invoices[0].credit_left == Money(5000)
    assert invoices[1].carried_credit == Money(5000)
    assert invoices[1].remaining == Money(3000)
    assert invoices[2].carried_credit == Money(0)
    assert invoices[2].remaining == Money(8000)


def test_limite_conta_parcelas_futuras_uma_vez() -> None:
    # Compra de R$ 1.200,00 em 12x, duas faturas pagas: usa R$ 1.000,00 do limite.
    s = limit_summary(Money(500000), Money(120000), Money(0), Money(20000))
    assert s.used == Money(100000)
    assert s.available == Money(400000)
    assert s.credit_balance == Money(0)


def test_limite_com_credito_nao_passa_do_total() -> None:
    s = limit_summary(Money(100000), Money(10000), Money(0), Money(15000))
    assert s.used == Money(0)
    assert s.available == Money(100000)
    assert s.credit_balance == Money(5000)


def test_limite_estourado_fica_negativo_e_visivel() -> None:
    s = limit_summary(Money(100000), Money(120000), Money(0), Money(0))
    assert s.available == Money(-20000)


def test_cancelamento_cancela_futuras_e_credita_ja_faturadas() -> None:
    # Compra de R$ 600,00 em 6x; hoje 15/10/2026 a fatura aberta vence 05/11/2026.
    plan = plan_installments(NEXT, date(2026, 8, 10), Money(60000), 6)
    states = [InstallmentState(p.number, p.amount, p.invoice_due_date, True) for p in plan]
    # faturas: 05/09, 05/10 (já fechadas), 05/11 (aberta), 05/12, 05/01, 05/02
    result = plan_cancellation(NEXT, TODAY, states)
    assert result.cancel_ids == [3, 4, 5, 6]
    assert result.credit_amount == Money(20000)
    assert result.credit_invoice_due == date(2026, 11, 5)
    # Consumo líquido zero: o que foi faturado volta como crédito, o resto some.
    cancelled = sum(s.amount.cents for s in states if s.id in result.cancel_ids)
    assert cancelled + result.credit_amount.cents == 60000


def test_cancelamento_de_compra_ainda_nao_faturada_nao_gera_credito() -> None:
    plan = plan_installments(NEXT, date(2026, 10, 10), Money(30000), 3)
    states = [InstallmentState(p.number, p.amount, p.invoice_due_date, True) for p in plan]
    result = plan_cancellation(NEXT, TODAY, states)
    assert result.cancel_ids == [1, 2, 3]
    assert result.credit_amount == Money(0)
    assert result.credit_invoice_due is None


def test_ciclo_invalido() -> None:
    with pytest.raises(ValueError):
        CardCycle(closing_day=0, due_day=5)
    with pytest.raises(ValueError):
        CardCycle(closing_day=10, due_day=32)
