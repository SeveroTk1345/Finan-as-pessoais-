"""Plano do mês (hoje: 15/10/2026): renda, contas do mês, investir, livre e projeção."""

from __future__ import annotations

from typing import Any

from sqlalchemy import Engine, text

from tests.db.api_helpers import Api
from tests.db.conftest_api import Trio, new_account


def _plan(api: Api, query: str = "") -> dict[str, Any]:
    r = api.get(f"/api/plano-do-mes{query}")
    assert r.status_code == 200, r.text
    return dict(r.json())


def _setup_month(api: Api) -> str:
    acc = new_account(api, balance=500000, on="2026-09-01")
    api.post(
        "/api/recorrencias",
        {
            "kind": "receber",
            "description": "Salário",
            "amount_cents": 450000,
            "anchor_date": "2026-10-05",
            "account_id": acc,
        },
    )
    api.post(
        "/api/contas-a-pagar", {"description": "Aluguel", "amount_cents": 150000, "due_date": "2026-10-20"}
    )
    # Repete todo mês e já foi paga: conta igual (o plano olha o mês inteiro).
    api.post(
        "/api/lancamentos",
        {
            "kind": "despesa",
            "account_id": acc,
            "amount_cents": 11990,
            "tx_date": "2026-10-05",
            "description": "Internet",
            "repeat": {"frequency": "mensal"},
        },
    )
    card = api.post(
        "/api/cartoes", {"name": "Cartão", "limit_cents": 1000000, "closing_day": 25, "due_day": 5}
    ).json()["id"]
    # Compra de 10/09 em 3x: 1ª parcela na fatura que vence em 05/10.
    api.post(
        f"/api/cartoes/{card}/compras",
        {
            "description": "Fogão",
            "total_cents": 120000,
            "purchase_date": "2026-09-10",
            "installments_count": 3,
        },
    )
    api.post(
        "/api/dividas",
        {
            "creditor": "Banco",
            "original_amount_cents": 500000,
            "installment_amount_cents": 52000,
            "first_due_date": "2026-11-10",
        },
    )
    return acc


def test_sem_dados_pede_a_renda(trio: Trio) -> None:
    p = _plan(trio.ana)
    assert p["income"] == {
        "used_cents": 0,
        "suggested_cents": 0,
        "expected_cents": 0,
        "average_cents": 0,
        "source": "nenhuma",
    }
    assert p["bills"]["total_cents"] == 0
    assert p["invest_cents"] == 0 and p["free_cents"] == 0
    assert "Informe a sua renda" in p["warnings"][0]
    assert [x["deposited_cents"] for x in p["projection"]] == [0, 0, 0, 0]


def test_divide_a_renda_entre_contas_investir_e_livre(trio: Trio) -> None:
    api = trio.ana
    _setup_month(api)
    p = _plan(api)
    assert p["month"] == "10/2026"
    assert p["income"]["source"] == "recorrencias"
    assert p["income"]["used_cents"] == 450000
    items = {i["label"]: i["cents"] for i in p["bills"]["items"]}
    assert items == {
        "Contas a pagar do mês": 150000 + 11990,
        "Faturas de cartão do mês": 40000,
        "Parcelas de dívidas": 52000,
    }
    bills = 150000 + 11990 + 40000 + 52000
    assert p["bills"]["total_cents"] == bills
    assert p["invest_suggested_cents"] == 90000  # 20% de R$ 4.500,00
    assert p["invest_cents"] == 90000
    assert p["free_cents"] == 450000 - bills - 90000
    # A soma das três partes é sempre a renda.
    assert p["bills"]["total_cents"] + p["invest_cents"] + p["free_cents"] == p["income"]["used_cents"]
    assert p["projection"][0] == {"years": 1, "deposited_cents": 1080000, "estimated_cents": 1080000}


def test_sem_receita_que_se_repete_usa_a_media_dos_ultimos_tres_meses(trio: Trio) -> None:
    api = trio.ana
    acc = new_account(api, balance=0, on="2026-06-01")
    for day, cents in [
        ("2026-07-05", 300000),
        ("2026-08-05", 300000),
        ("2026-09-05", 300001),
        ("2026-10-05", 999999),
        ("2026-06-05", 999999),
    ]:
        api.post(
            "/api/lancamentos",
            {
                "kind": "receita",
                "account_id": acc,
                "amount_cents": cents,
                "tx_date": day,
                "description": "Pagamento",
            },
        )
    p = _plan(api)
    assert p["income"]["source"] == "media"
    assert p["income"]["average_cents"] == 300000  # jul, ago e set; out (incompleto) e jun ficam de fora
    assert p["income"]["used_cents"] == 300000


def test_pessoa_pode_mudar_renda_investimento_e_taxa(trio: Trio) -> None:
    api = trio.ana
    _setup_month(api)
    p = _plan(api, "?renda=600000&investir=100000&taxa=12")
    assert p["income"]["used_cents"] == 600000 and p["income"]["suggested_cents"] == 450000
    assert p["invest_cents"] == 100000 and p["invest_suggested_cents"] == 120000
    assert p["free_cents"] == 600000 - p["bills"]["total_cents"] - 100000
    one_year = p["projection"][0]
    assert one_year["deposited_cents"] == 1200000
    # R$ 1.000,00 por mês a 12% ao ano ≈ R$ 12.646,50 em 12 meses (fórmula fechada).
    assert abs(one_year["estimated_cents"] - 1264650) <= 20
    assert [x["years"] for x in p["projection"]] == [1, 5, 10, 20]
    assert any("12% ao ano" in a for a in p["assumptions"])


def test_avisos_quando_as_contas_apertam(trio: Trio) -> None:
    api = trio.ana
    _setup_month(api)
    tight = _plan(api, "?renda=200000")
    assert tight["invest_cents"] == 0 and tight["free_cents"] < 0
    assert any("passam da renda" in w for w in tight["warnings"])
    half = _plan(api, "?renda=400000")
    assert any("metade da renda" in w for w in half["warnings"])
    too_much = _plan(api, "?renda=450000&investir=400000")
    assert any("não sobra dinheiro" in w for w in too_much["warnings"])


def test_dica_da_reserva_de_emergencia(trio: Trio) -> None:
    api = trio.ana
    assert any("reserva de emergência" in t for t in _plan(api)["tips"])
    api.post(
        "/api/metas",
        {
            "name": "Reserva",
            "kind": "reserva_emergencia",
            "target_cents": 100000,
            "initial_amount_cents": 10000,
        },
    )
    assert any("não estiver completa" in t for t in _plan(api)["tips"])


def test_validacao_dos_parametros(trio: Trio) -> None:
    for q in ["?taxa=101", "?taxa=-1", "?taxa=abc", "?renda=-5", "?investir=x", "?taxa=1.234"]:
        assert trio.ana.get(f"/api/plano-do-mes{q}").status_code == 422, q


def test_cada_pessoa_ve_so_o_proprio_plano(trio: Trio) -> None:
    _setup_month(trio.ana)
    for api in (trio.bruno, trio.carla):
        p = _plan(api)
        assert p["income"]["used_cents"] == 0
        assert p["bills"]["total_cents"] == 0


def test_plano_nao_grava_nada(trio: Trio, admin_engine: Engine) -> None:
    _setup_month(trio.ana)
    sql = text(
        "SELECT (SELECT count(*) FROM transactions) + (SELECT count(*) FROM bills) "
        "+ (SELECT count(*) FROM goals) + (SELECT count(*) FROM audit_log)"
    )
    with admin_engine.connect() as conn:
        before = conn.execute(sql).scalar()
    _plan(trio.ana, "?renda=500000&investir=1000&taxa=10")
    with admin_engine.connect() as conn:
        assert conn.execute(sql).scalar() == before
