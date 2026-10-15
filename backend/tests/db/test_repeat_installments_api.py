"""Gasto que se repete e compra parcelada no carnê ou boleto (hoje: 15/10/2026)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import Engine, text

from tests.db.api_helpers import Api
from tests.db.conftest_api import Trio, balance, category_id, new_account


def _bills(api: Api, start: str, end: str, kind: str = "pagar", overdue: bool = True) -> list[dict[str, Any]]:
    q = f"/api/contas-a-pagar?inicio={start}&fim={end}&tipo={kind}&incluir_vencidas={str(overdue).lower()}"
    return list(api.get(q).json())


def _expense(api: Api, acc: str, key: str = "auto", **extra: Any) -> Any:
    body = {
        "kind": "despesa",
        "account_id": acc,
        "amount_cents": 11990,
        "tx_date": "2026-10-15",
        "description": "Internet",
        "category_id": category_id(api, "Contas da casa"),
        **extra,
    }
    return api.post("/api/lancamentos", body, key=key)


# ---------- repetir ----------


def test_gasto_que_repete_paga_hoje_e_preve_os_proximos(trio: Trio) -> None:
    api = trio.ana
    acc = new_account(api, balance=100000)
    r = _expense(api, acc, repeat={"frequency": "mensal"})
    assert r.status_code == 201, r.text
    assert r.json()["recurring_rule_id"]
    assert balance(api, acc) == 100000 - 11990  # saiu uma vez só

    oct_items = [b for b in _bills(api, "2026-10-01", "2026-10-31") if b["description"] == "Internet"]
    assert [(b["due_date"], b["situation"]) for b in oct_items] == [("2026-10-15", "paga")]
    future = _bills(api, "2026-11-01", "2027-01-31", overdue=False)
    assert [(b["due_date"], b["amount_cents"], b["virtual"]) for b in future] == [
        ("2026-11-15", 11990, True),
        ("2026-12-15", 11990, True),
        ("2027-01-15", 11990, True),
    ]
    # A categoria acompanha o lançamento e as próximas vezes.
    tx = api.get("/api/lancamentos").json()["items"]
    assert [t["category_name"] for t in tx if t["description"] == "Internet"] == ["Contas da casa"]
    assert all(b["category_name"] == "Contas da casa" for b in future)


def test_repeticao_no_dia_31_nao_desliza(trio: Trio) -> None:
    api = trio.ana
    acc = new_account(api, on="2026-08-01")
    assert _expense(api, acc, tx_date="2026-08-31", repeat={"frequency": "mensal"}).status_code == 201
    future = _bills(api, "2026-10-16", "2027-03-31", overdue=False)
    assert [b["due_date"] for b in future] == [
        "2026-10-31",
        "2026-11-30",
        "2026-12-31",
        "2027-01-31",
        "2027-02-28",
        "2027-03-31",
    ]


def test_repeticao_semanal_anual_e_com_fim(trio: Trio) -> None:
    api = trio.ana
    acc = new_account(api)
    _expense(api, acc, description="Feira", repeat={"frequency": "semanal", "end_date": "2026-11-05"})
    _expense(api, acc, description="Seguro", repeat={"frequency": "anual"})
    future = _bills(api, "2026-10-16", "2027-12-31", overdue=False)
    assert [(b["description"], b["due_date"]) for b in future] == [
        ("Feira", "2026-10-22"),
        ("Feira", "2026-10-29"),
        ("Feira", "2026-11-05"),  # a data final conta
        ("Seguro", "2027-10-15"),
    ]


def test_receita_que_repete_vira_conta_a_receber(trio: Trio) -> None:
    api = trio.ana
    acc = new_account(api, balance=0)
    r = api.post(
        "/api/lancamentos",
        {
            "kind": "receita",
            "account_id": acc,
            "amount_cents": 450000,
            "tx_date": "2026-10-05",
            "description": "Salário",
            "category_id": category_id(api, "Salário", "receita"),
            "repeat": {"frequency": "mensal"},
        },
    )
    assert r.status_code == 201, r.text
    assert balance(api, acc) == 450000
    nov = _bills(api, "2026-11-01", "2026-11-30", kind="receber", overdue=False)
    assert [(b["description"], b["due_date"]) for b in nov] == [("Salário", "2026-11-05")]


def test_repeticao_invalida_nao_grava_nada(trio: Trio, admin_engine: Engine) -> None:
    api = trio.ana
    acc = new_account(api, on="2026-10-10")
    assert _expense(api, acc, repeat={"frequency": "mensal", "end_date": "2026-10-01"}).status_code == 422
    assert _expense(api, acc, tx_date="2026-10-20", repeat={"frequency": "mensal"}).status_code == 422
    r = api.post(
        "/api/lancamentos",
        {
            "kind": "reembolso",
            "account_id": acc,
            "amount_cents": 1,
            "tx_date": "2026-10-15",
            "description": "x",
            "repeat": {"frequency": "mensal"},
        },
    )
    assert r.status_code == 422
    # Falha depois de criar a recorrência (data antes do saldo inicial): tudo desfeito.
    assert _expense(api, acc, tx_date="2026-10-05", repeat={"frequency": "mensal"}).status_code == 422
    with admin_engine.connect() as conn:
        for table in ("recurring_rules", "bills", "transactions"):
            assert conn.execute(text(f"SELECT count(*) FROM {table}")).scalar() == 0, table


def test_repeticao_com_a_mesma_chave_nao_duplica(trio: Trio, admin_engine: Engine) -> None:
    api = trio.ana
    acc = new_account(api)
    first = _expense(api, acc, repeat={"frequency": "mensal"}, key="repetir-internet-123456")
    again = _expense(api, acc, repeat={"frequency": "mensal"}, key="repetir-internet-123456")
    assert first.status_code == 201 and again.status_code == 201
    assert first.json() == again.json()
    with admin_engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM recurring_rules")).scalar() == 1
        assert conn.execute(text("SELECT count(*) FROM transactions")).scalar() == 1


# ---------- parcelado no carnê ou boleto ----------


def _plan(api: Api, **extra: Any) -> Any:
    body = {
        "description": "Geladeira",
        "total_cents": 100000,
        "installments_count": 10,
        "first_due_date": "2026-11-15",
        "category_id": category_id(api, "Casa"),
        **extra,
    }
    return api.post("/api/parcelamentos", body)


def test_mil_reais_em_dez_vezes_vira_dez_contas_a_pagar(trio: Trio) -> None:
    api = trio.ana
    acc = new_account(api)
    r = _plan(api, account_id=acc)
    assert r.status_code == 201, r.text
    plan = r.json()
    assert plan["total_cents"] == 100000 and plan["remaining_cents"] == 100000
    assert [
        (b["installment_number"], b["installments_total"], b["amount_cents"], b["due_date"])
        for b in plan["bills"][:3]
    ] == [
        (1, 10, 10000, "2026-11-15"),
        (2, 10, 10000, "2026-12-15"),
        (3, 10, 10000, "2027-01-15"),
    ]
    assert plan["bills"][-1]["due_date"] == "2027-08-15"
    # Comprar não é gastar: o gasto nasce quando a parcela é paga (F13).
    home = api.get("/api/resumo").json()
    assert home["spending_month_cents"] == 0
    assert home["installments_outstanding_cents"] == 100000
    assert home["debts_total_cents"] == 100000
    nov = _bills(api, "2026-11-01", "2026-11-30", overdue=False)
    assert [(b["description"], b["installment_number"]) for b in nov] == [("Geladeira", 1)]
    obligations = api.get("/api/a-pagar?dias=60").json()
    assert "Geladeira · parcela 1 de 10" in [o["description"] for o in obligations["items"]]

    first = plan["bills"][0]["id"]
    assert api.post(f"/api/contas-a-pagar/{first}/pagar", {}).status_code == 201
    home = api.get("/api/resumo").json()
    assert home["debts_total_cents"] == 90000
    assert home["spending_month_cents"] == 10000
    assert balance(api, acc) == 90000


def test_resto_da_divisao_vai_na_primeira_parcela_e_dia_31_nao_desliza(trio: Trio) -> None:
    api = trio.ana
    plan = _plan(api, total_cents=100000, installments_count=3, first_due_date="2027-01-31").json()
    assert [(b["amount_cents"], b["due_date"]) for b in plan["bills"]] == [
        (33334, "2027-01-31"),
        (33333, "2027-02-28"),
        (33333, "2027-03-31"),
    ]


def test_cancelar_parcelas_restantes_mantem_as_pagas(trio: Trio) -> None:
    api = trio.ana
    acc = new_account(api)
    plan = _plan(api, account_id=acc).json()
    api.post(f"/api/contas-a-pagar/{plan['bills'][0]['id']}/pagar", {})
    api.post(f"/api/contas-a-pagar/{plan['bills'][1]['id']}/pagar", {"amount_cents": 4000})
    r = api.post(f"/api/parcelamentos/{plan['installment_group']}/cancelar")
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["cancelled"] == 9  # a parcial também, no que falta
    assert out["remaining_cents"] == 0
    assert [b["situation"] for b in out["bills"][:3]] == ["paga", "cancelada", "cancelada"]
    assert balance(api, acc) == 100000 - 10000 - 4000  # o que foi pago continua
    assert api.get("/api/resumo").json()["debts_total_cents"] == 0
    assert api.post(f"/api/parcelamentos/{plan['installment_group']}/cancelar").status_code == 409


def test_parcelamento_validacoes(trio: Trio) -> None:
    api = trio.ana
    assert _plan(api, installments_count=1).status_code == 422
    assert _plan(api, installments_count=73).status_code == 422
    assert _plan(api, total_cents=0).status_code == 422
    assert _plan(api, total_cents=5, installments_count=7).status_code == 422  # parcelas de R$ 0,00
    assert _plan(api, category_id=category_id(api, "Salário", "receita")).status_code == 422


def test_parcelamento_de_outra_pessoa(trio: Trio) -> None:
    plan = _plan(trio.ana).json()
    group = plan["installment_group"]
    for api in (trio.bruno, trio.carla):
        r = api.get(f"/api/parcelamentos/{group}")
        assert r.status_code == 404
        assert r.json()["detail"] == "Parcelamento não encontrado."
        assert api.post(f"/api/parcelamentos/{group}/cancelar").status_code == 404
        assert api.get("/api/resumo").json()["debts_total_cents"] == 0
    # Conta e categoria de outra pessoa não podem ser usadas.
    bruno_acc = new_account(trio.bruno)
    assert _plan(trio.ana, account_id=bruno_acc).status_code == 422
    assert _plan(trio.ana, category_id=category_id(trio.bruno, "Casa")).status_code in (404, 422)
    assert trio.ana.get(f"/api/parcelamentos/{group}").json()["remaining_cents"] == 100000
