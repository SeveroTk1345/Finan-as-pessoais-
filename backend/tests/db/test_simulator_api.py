"""Simulador "Posso comprar?". Hoje (relógio fixo): 15/10/2026."""

from __future__ import annotations

from sqlalchemy import Engine, text

from tests.db.conftest_api import Trio, new_account


def _setup(api, balance: int = 300000) -> str:  # type: ignore[no-untyped-def]
    acc = new_account(api, balance=balance)
    # Salário de R$ 2.000,00 todo dia 5 e aluguel de R$ 1.500,00 todo dia 10.
    api.post(
        "/api/recorrencias",
        {
            "kind": "receber",
            "description": "Salário",
            "amount_cents": 200000,
            "anchor_date": "2026-11-05",
            "account_id": acc,
            "is_main_income": True,
        },
    )
    api.post(
        "/api/recorrencias",
        {"kind": "pagar", "description": "Aluguel", "amount_cents": 150000, "anchor_date": "2026-11-10"},
    )
    return acc


def test_compra_a_vista_projeta_os_meses(trio: Trio) -> None:
    api = trio.ana
    _setup(api)
    r = api.post("/api/simulador/compra", {"amount_cents": 100000, "months": 3}, key=None)
    assert r.status_code == 200, r.text
    body = r.json()
    months = body["months"]
    assert [m["month"] for m in months] == ["10/2026", "11/2026", "12/2026"]
    # Sem compra: 3.000 -> 3.000 -> 3.500 -> 4.000. Com compra hoje: tudo 1.000 a menos.
    assert [m["balance_without_cents"] for m in months] == [300000, 350000, 400000]
    assert [m["balance_with_cents"] for m in months] == [200000, 250000, 300000]
    assert body["risky_months"] == []
    assert body["verdict"]["level"] == "ok"
    assert body["available_after_cents"] == 200000


def test_compra_que_deixa_mes_negativo_e_sinalizada(trio: Trio) -> None:
    api = trio.ana
    _setup(api, balance=50000)
    api.post("/api/contas-a-pagar", {"description": "IPVA", "amount_cents": 90000, "due_date": "2026-11-20"})
    body = api.post("/api/simulador/compra", {"amount_cents": 60000, "months": 3}, key=None).json()
    # Sem compra: 500 -> 500+2000-1500-900 = 100 -> 600. Com compra: -100 em out? não: 500-600 = -100.
    assert body["months"][0]["balance_with_cents"] == -10000
    assert "10/2026" in body["risky_months"]
    assert body["newly_risky_months"]
    assert body["verdict"]["level"] == "atencao"
    assert body["compare"]["dont_buy_min_cents"] == 10000
    assert body["reserve"]["covers"] is False


def test_parcela_que_cabe_nao_e_declarada_segura_sem_olhar_o_conjunto(trio: Trio) -> None:
    api = trio.ana
    acc = new_account(api, balance=10000)  # R$ 100,00
    api.post(
        "/api/recorrencias",
        {
            "kind": "receber",
            "description": "Aposentadoria",
            "amount_cents": 140000,
            "anchor_date": "2026-11-05",
            "account_id": acc,
        },
    )
    api.post(
        "/api/recorrencias",
        {"kind": "pagar", "description": "Aluguel", "amount_cents": 150000, "anchor_date": "2026-11-10"},
    )
    card = api.post(
        "/api/cartoes", {"name": "Cartão", "limit_cents": 1000000, "closing_day": 25, "due_day": 5}
    ).json()["id"]
    # Parcela de só R$ 60,00, mas novembro já fecha com R$ 0,00 sem a compra
    # (100 + 1.400 - 1.500): com a parcela, fica negativo.
    body = api.post(
        "/api/simulador/compra",
        {"amount_cents": 60000, "method": "cartao", "card_id": card, "installments_count": 10, "months": 3},
        key=None,
    ).json()
    assert body["monthly_extra_cents"] == 6000
    assert body["limit"]["available_after_cents"] == 1000000 - 60000
    assert [m["purchase_cents"] for m in body["months"]] == [0, 6000, 6000]
    assert [m["balance_without_cents"] for m in body["months"]] == [10000, 0, -10000]
    assert [m["balance_with_cents"] for m in body["months"]] == [10000, -6000, -22000]
    assert body["newly_risky_months"] == ["11/2026"]
    assert body["verdict"]["level"] == "atencao"


def test_limite_insuficiente_avisa(trio: Trio) -> None:
    api = trio.ana
    new_account(api)
    card = api.post(
        "/api/cartoes", {"name": "Cartão", "limit_cents": 50000, "closing_day": 25, "due_day": 5}
    ).json()["id"]
    body = api.post(
        "/api/simulador/compra", {"amount_cents": 60000, "method": "cartao", "card_id": card}, key=None
    ).json()
    assert any("limite" in w for w in body["warnings"])
    # Mesmo com dinheiro sobrando, uma compra que o limite não comporta nunca "cabe".
    assert body["verdict"]["level"] == "atencao"
    assert "limite" in body["verdict"]["message"]


def test_simulacao_nao_grava_nada(trio: Trio, admin_engine: Engine) -> None:
    api = trio.ana
    _setup(api)
    with admin_engine.connect() as conn:
        before = conn.execute(
            text(
                "SELECT (SELECT count(*) FROM transactions) + (SELECT count(*) FROM bills) "
                "+ (SELECT count(*) FROM card_purchases)"
            )
        ).scalar()
    api.post("/api/simulador/compra", {"amount_cents": 100000}, key=None)
    with admin_engine.connect() as conn:
        after = conn.execute(
            text(
                "SELECT (SELECT count(*) FROM transactions) + (SELECT count(*) FROM bills) "
                "+ (SELECT count(*) FROM card_purchases)"
            )
        ).scalar()
    assert before == after


def test_cartao_de_outra_pessoa_no_simulador(trio: Trio) -> None:
    card = trio.bruno.post(
        "/api/cartoes", {"name": "Do Bruno", "limit_cents": 1, "closing_day": 1, "due_day": 10}
    ).json()["id"]
    r = trio.ana.post(
        "/api/simulador/compra", {"amount_cents": 1, "method": "cartao", "card_id": card}, key=None
    )
    assert r.status_code == 404
    assert "Bruno" not in r.text
