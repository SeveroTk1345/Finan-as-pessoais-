from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.domain.bills import BillStatus, bill_status, due_soon
from app.domain.goals import goal_progress
from app.domain.investments import (
    Movement,
    Valuation,
    cash_flows,
    position,
    real_rate,
    summarize,
    xirr,
)
from app.domain.money import Money

TODAY = date(2026, 10, 15)


# --- investimentos ---------------------------------------------------------------


def test_aporte_nao_e_ganho_e_retirada_nao_e_perda() -> None:
    movs = [
        Movement(date(2026, 1, 10), "aporte", Money(100000)),
        Movement(date(2026, 3, 10), "aporte", Money(100000)),
        Movement(date(2026, 6, 10), "retirada", Money(50000)),
    ]
    # Valor informado igual ao capital líquido: ganho zero.
    s = summarize(movs, [Valuation(date(2026, 10, 1), Money(150000))], variable_income=False, today=TODAY)
    assert s.invested == Money(150000)
    assert s.total_contributed == Money(200000)
    assert s.total_withdrawn == Money(50000)
    assert s.estimated_gain == Money(0)
    assert s.stale is False


def test_rendimento_reinvestido_e_pago_em_conta() -> None:
    movs = [
        Movement(date(2026, 1, 10), "aporte", Money(100000)),
        Movement(date(2026, 6, 10), "rendimento", Money(3000), paid_to_account=True),
        Movement(date(2026, 7, 10), "rendimento", Money(2000)),  # reinvestido
    ]
    s = summarize(movs, [Valuation(date(2026, 10, 1), Money(102000))], variable_income=False, today=TODAY)
    assert s.income_received == Money(3000)
    # Ganho = 1.020,00 + 30,00 recebidos - 1.000,00 aportados.
    assert s.estimated_gain == Money(5000)


def test_sem_valor_informado_nao_inventa_ganho() -> None:
    s = summarize(
        [Movement(date(2026, 1, 10), "aporte", Money(100000))],
        [],
        variable_income=False,
        today=TODAY,
    )
    assert s.current_value is None
    assert s.estimated_gain is None
    assert s.stale is True


def test_valor_desatualizado() -> None:
    s = summarize(
        [Movement(date(2026, 1, 10), "aporte", Money(100000))],
        [Valuation(date(2026, 8, 1), Money(101000))],
        variable_income=False,
        today=TODAY,
    )
    assert s.stale is True


def test_preco_medio_com_compras_e_venda() -> None:
    movs = [
        Movement(date(2026, 1, 5), "compra", Money(100000), Money(500), Decimal(100)),
        Movement(date(2026, 2, 5), "compra", Money(60000), Money(500), Decimal(50)),
        Movement(date(2026, 3, 5), "venda", Money(90000), Money(500), Decimal(60)),
    ]
    pos = position(movs)
    # Custo 1.610,00 por 150 cotas = 10,7333...; venda de 60 cotas retira 644,00.
    assert pos.quantity == Decimal(90)
    assert pos.cost == Money(96600)
    assert pos.average_price == Money(1073)
    assert pos.realized_gain == Money(90000 - 500 - 64400)


def test_venda_maior_que_a_carteira() -> None:
    with pytest.raises(ValueError):
        position(
            [
                Movement(date(2026, 1, 5), "compra", Money(1000), quantity=Decimal(1)),
                Movement(date(2026, 1, 6), "venda", Money(1000), quantity=Decimal(2)),
            ]
        )


def test_renda_variavel_valor_de_mercado_pelo_preco_informado() -> None:
    movs = [Movement(date(2026, 1, 5), "compra", Money(100000), quantity=Decimal(100))]
    s = summarize(
        movs,
        [Valuation(date(2026, 10, 10), unit_price=Money(1250))],
        variable_income=True,
        today=TODAY,
    )
    assert s.invested == Money(100000)
    assert s.current_value == Money(125000)
    assert s.estimated_gain == Money(25000)


def test_xirr_um_ano_dez_por_cento() -> None:
    flows = [(date(2025, 1, 1), -100000), (date(2026, 1, 1), 110000)]
    rate = xirr(flows)
    assert rate is not None
    assert abs(rate - Decimal("0.10")) < Decimal("0.0001")


def test_xirr_com_aportes_em_datas_diferentes() -> None:
    movs = [
        Movement(date(2025, 1, 1), "aporte", Money(100000)),
        Movement(date(2025, 7, 1), "aporte", Money(100000)),
    ]
    flows = cash_flows(movs, Money(210000), date(2026, 1, 1))
    rate = xirr(flows)
    assert rate is not None
    # Ganho de 100,00 sobre capital médio ~1.500,00 em 1 ano: entre 6% e 7%.
    assert Decimal("0.06") < rate < Decimal("0.07")


def test_xirr_sem_dados_suficientes() -> None:
    assert xirr([]) is None
    assert xirr([(date(2026, 1, 1), -1000)]) is None
    assert xirr([(date(2026, 1, 1), -1000), (date(2026, 1, 10), 1010)]) is None  # < 30 dias


def test_taxa_real() -> None:
    assert abs(real_rate(Decimal("0.10"), Decimal("0.04")) - Decimal("0.0576923")) < Decimal("0.0000001")


# --- metas -----------------------------------------------------------------------


def test_meta_sem_rendimento() -> None:
    g = goal_progress(
        Money(1000000),
        Money(400000),
        today=TODAY,
        planned_monthly=Money(100000),
        annual_rate_percent=None,
        target_date=date(2027, 6, 1),
    )
    assert g.percent == 40
    assert g.missing == Money(600000)
    assert g.months_needed == 6
    assert g.projected_date == date(2027, 4, 15)
    assert g.on_track is True
    assert "sem rendimento" in g.assumption


def test_meta_com_rendimento_chega_antes_e_avisa() -> None:
    base = goal_progress(
        Money(1200000),
        Money(0),
        today=TODAY,
        planned_monthly=Money(100000),
        annual_rate_percent=None,
        target_date=None,
    )
    with_rate = goal_progress(
        Money(1200000),
        Money(0),
        today=TODAY,
        planned_monthly=Money(100000),
        annual_rate_percent=Decimal(12),
        target_date=None,
    )
    assert base.months_needed == 12
    assert with_rate.months_needed is not None and with_rate.months_needed <= 12
    assert "não é garantido" in with_rate.assumption


def test_meta_sem_contribuicao_nao_projeta_e_meta_atingida() -> None:
    g = goal_progress(
        Money(1000),
        Money(0),
        today=TODAY,
        planned_monthly=None,
        annual_rate_percent=None,
        target_date=None,
    )
    assert g.months_needed is None and g.projected_date is None
    done = goal_progress(
        Money(1000),
        Money(1500),
        today=TODAY,
        planned_monthly=None,
        annual_rate_percent=None,
        target_date=None,
    )
    assert done.percent == 100 and done.missing == Money(0)


# --- contas a pagar ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("paid", "due", "cancelled", "status"),
    [
        (0, date(2026, 10, 20), False, BillStatus.PENDENTE),
        (0, date(2026, 10, 1), False, BillStatus.VENCIDA),  # não vira paga sozinha
        (500, date(2026, 10, 20), False, BillStatus.PARCIAL),
        (500, date(2026, 10, 1), False, BillStatus.VENCIDA),
        (1000, date(2026, 10, 1), False, BillStatus.PAGA),
        (0, date(2026, 10, 1), True, BillStatus.CANCELADA),
    ],
)
def test_situacao_conta_a_pagar(paid: int, due: date, cancelled: bool, status: BillStatus) -> None:
    assert (
        bill_status(amount=Money(1000), paid=Money(paid), due=due, today=TODAY, cancelled=cancelled) is status
    )


def test_vence_em_breve() -> None:
    assert due_soon(date(2026, 10, 22), TODAY)
    assert not due_soon(date(2026, 10, 23), TODAY)
    assert not due_soon(date(2026, 10, 14), TODAY)
