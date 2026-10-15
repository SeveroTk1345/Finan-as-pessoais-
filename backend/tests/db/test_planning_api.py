"""Investimentos, metas, resumo da tela inicial, relatórios e exportação.

Hoje (relógio fixo): 15/10/2026.
"""

from __future__ import annotations

import csv
import io
from typing import Any

from tests.db.api_helpers import Api
from tests.db.conftest_api import Trio, balance, category_id, new_account


def _fixed_income(api: Api, acc: str | None = None, **kw: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "asset_class": "renda_fixa",
        "product_type": "CDB",
        "name": "CDB Banco X",
        "institution": "Banco Fictício",
        "indexer": "CDI",
        "rate_description": "110% do CDI",
        **kw,
    }
    if acc:
        payload["first_movement"] = {
            "kind": "aporte",
            "movement_date": "2025-10-15",
            "amount_cents": 1000000,
            "account_id": acc,
        }
    r = api.post("/api/investimentos", payload)
    assert r.status_code == 201, r.text
    return dict(r.json())


# --- investimentos ------------------------------------------------------------------


def test_aporte_sai_da_conta_sem_virar_despesa(trio: Trio) -> None:
    api = trio.ana
    acc = new_account(api, balance=2000000, on="2025-01-01")
    inv = _fixed_income(api, acc)
    assert balance(api, acc) == 1000000
    assert inv["invested_cents"] == 1000000
    assert inv["current_value_cents"] is None  # sem valor informado, nada inventado
    assert inv["estimated_gain_cents"] is None
    assert api.get("/api/lancamentos?tipo=despesa").json()["total"] == 0
    tx = api.get("/api/lancamentos").json()["items"]
    assert [t["kind"] for t in tx] == ["investimento"]


def test_valor_informado_ganho_e_rentabilidade(trio: Trio) -> None:
    api = trio.ana
    acc = new_account(api, balance=2000000, on="2025-01-01")
    inv = _fixed_income(api, acc)
    r = api.post(
        f"/api/investimentos/{inv['id']}/valores", {"valuation_date": "2026-10-15", "value_cents": 1100000}
    )
    assert r.status_code == 201, r.text
    after = r.json()
    assert after["current_value_cents"] == 1100000
    assert after["estimated_gain_cents"] == 100000
    assert after["value_is_stale"] is False
    rate = float(after["annual_return"])
    assert 0.099 < rate < 0.101  # 10% em um ano


def test_retirada_reduz_capital_sem_virar_perda(trio: Trio) -> None:
    api = trio.ana
    acc = new_account(api, balance=2000000, on="2025-01-01")
    inv = _fixed_income(api, acc)
    r = api.post(
        f"/api/investimentos/{inv['id']}/movimentos",
        {"kind": "retirada", "movement_date": "2026-06-01", "amount_cents": 400000, "account_id": acc},
    )
    assert r.status_code == 201, r.text
    after = r.json()
    assert after["invested_cents"] == 600000
    assert balance(api, acc) == 1400000
    api.post(f"/api/investimentos/{inv['id']}/valores", {"value_cents": 600000})
    assert api.get(f"/api/investimentos/{inv['id']}").json()["estimated_gain_cents"] == 0


def test_renda_variavel_preco_medio_e_venda(trio: Trio) -> None:
    api = trio.ana
    r = api.post(
        "/api/investimentos",
        {
            "asset_class": "renda_variavel",
            "product_type": "Ação",
            "name": "Empresa Fictícia",
            "ticker": "fict3",
        },
    )
    assert r.status_code == 201, r.text
    inv = r.json()
    assert inv["ticker"] == "FICT3"
    iid = inv["id"]
    api.post(
        f"/api/investimentos/{iid}/movimentos",
        {"kind": "compra", "movement_date": "2026-01-05", "amount_cents": 100000, "quantity": "100"},
    )
    api.post(
        f"/api/investimentos/{iid}/movimentos",
        {"kind": "compra", "movement_date": "2026-02-05", "amount_cents": 60000, "quantity": "50"},
    )
    too_many = api.post(
        f"/api/investimentos/{iid}/movimentos",
        {"kind": "venda", "movement_date": "2026-03-05", "amount_cents": 1, "quantity": "151"},
    )
    assert too_many.status_code == 422
    r = api.post(f"/api/investimentos/{iid}/valores", {"unit_price_cents": 1200})
    after = r.json()
    assert after["quantity"] == "150"
    assert after["average_price_cents"] == 1067  # R$ 1.600,00 / 150
    assert after["current_value_cents"] == 180000
    assert after["estimated_gain_cents"] == 20000
    wrong = api.post(
        f"/api/investimentos/{iid}/movimentos",
        {"kind": "aporte", "movement_date": "2026-03-05", "amount_cents": 1},
    )
    assert wrong.status_code == 422


def test_cancelar_movimento_desfaz_o_lancamento_da_conta(trio: Trio) -> None:
    api = trio.ana
    acc = new_account(api, balance=2000000, on="2025-01-01")
    inv = _fixed_income(api, acc)
    mv = inv["movements"][0]["id"]
    r = api.post(f"/api/investimentos/movimentos/{mv}/cancelar", key=None)
    assert r.status_code == 200
    assert balance(api, acc) == 2000000
    assert r.json()["invested_cents"] == 0


def test_visao_geral_da_carteira(trio: Trio) -> None:
    api = trio.ana
    acc = new_account(api, balance=5000000, on="2025-01-01")
    inv = _fixed_income(api, acc)
    api.post(
        f"/api/investimentos/{inv['id']}/valores", {"valuation_date": "2026-08-01", "value_cents": 1050000}
    )
    ov = api.get("/api/investimentos").json()
    assert ov["totals"]["invested_cents"] == 1000000
    assert ov["totals"]["current_value_cents"] == 1050000
    assert ov["totals"]["stale_count"] == 1  # informado há mais de 30 dias
    assert ov["by_class"] == [{"asset_class": "renda_fixa", "value_cents": 1050000}]
    assert any("desatualizados" in n for n in ov["notes"])


# --- metas ---------------------------------------------------------------------------


def test_meta_com_progresso_e_premissas(trio: Trio) -> None:
    api = trio.ana
    r = api.post(
        "/api/metas",
        {
            "name": "Reserva",
            "kind": "reserva_emergencia",
            "target_cents": 1000000,
            "planned_monthly_cents": 100000,
            "initial_amount_cents": 400000,
            "target_date": "2027-06-01",
        },
    )
    assert r.status_code == 201, r.text
    g = r.json()
    assert g["percent"] == 40
    assert g["months_needed"] == 6
    assert g["on_track"] is True
    assert "sem rendimento" in g["assumption"]
    g = api.post(f"/api/metas/{g['id']}/contribuicoes", {"amount_cents": 100000}).json()
    assert g["percent"] == 50
    bad = api.post(f"/api/metas/{g['id']}/contribuicoes", {"direction": "retirada", "amount_cents": 600000})
    assert bad.status_code == 422


# --- resumo da tela inicial ---------------------------------------------------------


def test_resumo_separa_disponivel_comprometido_e_patrimonio(trio: Trio) -> None:
    api = trio.ana
    corrente = new_account(api, "Corrente", 300000)
    new_account(api, "Imóvel alugado (outra)", 999999, kind="outra")  # não é do dia a dia
    api.post(
        "/api/lancamentos",
        {
            "kind": "receita",
            "account_id": corrente,
            "amount_cents": 500000,
            "tx_date": "2026-10-05",
            "description": "Salário",
            "category_id": category_id(api, "Salário", "receita"),
        },
    )
    api.post(
        "/api/lancamentos",
        {
            "kind": "despesa",
            "account_id": corrente,
            "amount_cents": 20000,
            "tx_date": "2026-10-06",
            "description": "Mercado",
            "category_id": category_id(api, "Alimentação"),
        },
    )
    card = api.post(
        "/api/cartoes", {"name": "Cartão", "limit_cents": 1000000, "closing_day": 25, "due_day": 5}
    ).json()["id"]
    api.post(
        f"/api/cartoes/{card}/compras",
        {"description": "TV", "total_cents": 300000, "purchase_date": "2026-10-10", "installments_count": 3},
    )
    api.post("/api/contas-a-pagar", {"description": "Luz", "amount_cents": 15000, "due_date": "2026-10-20"})
    api.post(
        "/api/contas-a-pagar", {"description": "Água vencida", "amount_cents": 5000, "due_date": "2026-09-20"}
    )
    h = api.get("/api/resumo").json()
    assert h["available_cents"] == 300000 + 500000 - 20000
    assert h["accounts_total_cents"] == h["available_cents"] + 999999
    assert h["income_month_cents"] == 500000
    # Gasto do mês: mercado + TV (pela data da compra, uma vez só).
    assert h["spending_month_cents"] == 20000 + 300000
    # Até o fim do mês: luz + água vencida (a fatura vence em 05/11).
    assert h["to_pay_month_cents"] == 20000
    # Comprometido nos próximos 30 dias: luz + água + fatura de 05/11 (R$ 1.000,00).
    assert h["committed_cents"] == 20000 + 100000
    assert h["free_cents"] == h["available_cents"] - h["committed_cents"]
    # Dívidas: o cartão inteiro (3 parcelas), sem somar de novo as faturas.
    assert h["debts_total_cents"] == 300000
    assert h["net_worth_cents"] == h["accounts_total_cents"] - 300000
    assert h["overdue_count"] == 1
    assert h["status"]["level"] == "atencao"
    assert "limite de cartão" in h["explanations"]["available"]


def test_resumo_nao_conta_renegociacao_duas_vezes(trio: Trio) -> None:
    api = trio.ana
    acc = new_account(api, balance=500000)
    card = api.post(
        "/api/cartoes", {"name": "Cartão", "limit_cents": 1000000, "closing_day": 25, "due_day": 5}
    ).json()["id"]
    api.post(
        f"/api/cartoes/{card}/compras",
        {"description": "Compra", "total_cents": 100000, "purchase_date": "2026-09-10"},
    )
    api.post(f"/api/cartoes/{card}/faturas/2026-10-05/pagar", {"account_id": acc, "amount_cents": 20000})
    api.post(
        f"/api/cartoes/{card}/faturas/2026-10-05/renegociar",
        {"financed_cents": 80000, "installments_count": 10, "installment_cents": 10000},
    )
    h = api.get("/api/resumo").json()
    assert h["debts_total_cents"] == 100000  # 10 parcelas de R$ 100,00, uma vez só
    assert h["debts_direct_cents"] == 0
    a_pagar = api.get("/api/a-pagar?dias=30").json()
    # Parcela do acordo aparece só dentro da fatura de 05/11, não como dívida separada.
    assert [i["source"] for i in a_pagar["items"]] == ["fatura"]
    assert a_pagar["total_cents"] == 10000


def test_a_pagar_reune_contas_faturas_e_parcelas(trio: Trio) -> None:
    api = trio.ana
    api.post(
        "/api/contas-a-pagar", {"description": "Internet", "amount_cents": 9990, "due_date": "2026-10-25"}
    )
    api.post(
        "/api/dividas",
        {
            "creditor": "Banco",
            "original_amount_cents": 100000,
            "installment_amount_cents": 10000,
            "installments_total": 10,
            "first_due_date": "2026-11-01",
        },
    )
    items = api.get("/api/a-pagar?dias=30").json()["items"]
    assert [(i["source"], i["due_date"]) for i in items] == [
        ("conta", "2026-10-25"),
        ("divida", "2026-11-01"),
    ]


# --- relatórios ---------------------------------------------------------------------


def test_relatorio_mensal_e_transferencia_fora(trio: Trio) -> None:
    api = trio.ana
    a, b = new_account(api, "A", 100000), new_account(api, "B", 0)
    api.post(
        "/api/transferencias",
        {"from_account_id": a, "to_account_id": b, "amount_cents": 50000, "tx_date": "2026-10-03"},
    )
    api.post(
        "/api/lancamentos",
        {
            "kind": "despesa",
            "account_id": a,
            "amount_cents": 1000,
            "tx_date": "2026-10-04",
            "description": "Pão",
            "category_id": category_id(api, "Alimentação"),
        },
    )
    api.post(
        "/api/lancamentos",
        {
            "kind": "reembolso",
            "account_id": a,
            "amount_cents": 300,
            "tx_date": "2026-10-05",
            "description": "Amigo devolveu",
            "category_id": category_id(api, "Alimentação"),
        },
    )
    r = api.get("/api/relatorios/mensal?mes=2026-10").json()
    assert r["income_cents"] == 0  # transferência e reembolso não são receita
    assert r["spending_cents"] == 700
    assert r["spending_by_category"] == [{"category": "Alimentação", "cents": 700}]
    assert r["cash_out_cents"] == 1000 and r["cash_in_cents"] == 300
    assert r["start_balance_cents"] == 100000
    assert r["end_balance_cents"] == 100000 - 700
    assert api.get("/api/relatorios/mensal?mes=2026-13").status_code == 422


def test_evolucao_mensal(trio: Trio) -> None:
    api = trio.ana
    acc = new_account(api, balance=100000, on="2026-08-01")
    api.post(
        "/api/lancamentos",
        {
            "kind": "receita",
            "account_id": acc,
            "amount_cents": 50000,
            "tx_date": "2026-09-10",
            "description": "Extra",
        },
    )
    s = api.get("/api/relatorios/evolucao?meses=3").json()["months"]
    assert [m["month"] for m in s] == ["08/2026", "09/2026", "10/2026"]
    assert [m["balance_cents"] for m in s] == [100000, 150000, 150000]
    assert [m["income_cents"] for m in s] == [0, 50000, 0]


def test_valores_em_centavos_sao_sempre_inteiros(trio: Trio) -> None:
    """Nenhum valor monetário pode sair como texto ou número com casas decimais."""
    api = trio.ana
    acc = new_account(api, balance=100000)
    api.post(
        "/api/lancamentos",
        {
            "kind": "despesa",
            "account_id": acc,
            "amount_cents": 1,
            "tx_date": "2026-10-02",
            "description": "x",
        },
    )

    def walk(obj: Any, path: str = "") -> None:
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k.endswith("_cents") and v is not None:
                    assert isinstance(v, int) and not isinstance(v, bool), f"{path}.{k}={v!r}"
                walk(v, f"{path}.{k}")
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                walk(v, f"{path}[{i}]")

    for url in [
        "/api/resumo",
        "/api/contas",
        "/api/lancamentos",
        "/api/relatorios/mensal",
        "/api/relatorios/evolucao",
        "/api/investimentos",
        "/api/dividas",
        "/api/cartoes",
        "/api/a-pagar",
    ]:
        walk(api.get(url).json(), url)


# --- exportação -----------------------------------------------------------------------


def test_exportacao_traz_so_os_dados_do_usuario(trio: Trio) -> None:
    acc_a = new_account(trio.ana, "Conta da Ana", 100)
    trio.ana.post(
        "/api/lancamentos",
        {
            "kind": "despesa",
            "account_id": acc_a,
            "amount_cents": 10,
            "tx_date": "2026-10-02",
            "description": '=HYPERLINK("x")',
        },
    )
    new_account(trio.bruno, "Conta do Bruno", 200)
    data = trio.ana.get("/api/exportar/dados.json")
    assert data.status_code == 200
    assert "attachment" in data.headers["content-disposition"]
    body = data.json()
    assert body["user"]["username"] == "ana"
    assert [a["name"] for a in body["data"]["accounts"]] == ["Conta da Ana"]
    assert "Bruno" not in data.text
    assert all("owner_id" not in row for rows in body["data"].values() for row in rows)

    csv_resp = trio.ana.get("/api/exportar/lancamentos.csv")
    assert csv_resp.status_code == 200
    text = csv_resp.content.decode("utf-8-sig")
    rows = list(csv.reader(io.StringIO(text), delimiter=";"))
    assert rows[0][0] == "Data"
    assert rows[1][0] == "02/10/2026"
    assert rows[1][4].startswith("'=")  # fórmula neutralizada
    assert rows[1][5] == "-0,10"
    assert "Bruno" not in text


# --- isolamento ------------------------------------------------------------------------


def test_acesso_cruzado_em_investimentos_e_metas(trio: Trio) -> None:
    ids = {}
    for name, api in [("ana", trio.ana), ("bruno", trio.bruno), ("carla", trio.carla)]:
        acc = new_account(api, balance=2000000, on="2025-01-01")
        inv = _fixed_income(api, acc, name=f"CDB {name}")
        val = api.post(f"/api/investimentos/{inv['id']}/valores", {"value_cents": 1000}).json()
        goal = api.post(
            "/api/metas", {"name": f"Meta {name}", "target_cents": 1000, "initial_amount_cents": 100}
        ).json()
        ids[name] = {
            "acc": acc,
            "inv": inv["id"],
            "mv": inv["movements"][0]["id"],
            "val": val["valuations"][0]["id"],
            "goal": goal["id"],
            "contrib": goal["contributions"][0]["id"],
        }
    for attacker_name, attacker, victim_name, _ in trio.pairs():
        v, mine = ids[victim_name], ids[attacker_name]
        checks = [
            attacker.get(f"/api/investimentos/{v['inv']}"),
            attacker.patch(f"/api/investimentos/{v['inv']}", {"name": "x"}),
            attacker.post(
                f"/api/investimentos/{v['inv']}/movimentos",
                {"kind": "aporte", "movement_date": "2026-10-01", "amount_cents": 1},
            ),
            attacker.post(f"/api/investimentos/movimentos/{v['mv']}/cancelar", key=None),
            attacker.post(f"/api/investimentos/{v['inv']}/valores", {"value_cents": 1}),
            attacker.delete(f"/api/investimentos/valores/{v['val']}"),
            attacker.get(f"/api/metas/{v['goal']}"),
            attacker.patch(f"/api/metas/{v['goal']}", {"name": "x"}),
            attacker.post(f"/api/metas/{v['goal']}/contribuicoes", {"amount_cents": 1}),
            attacker.delete(f"/api/metas/contribuicoes/{v['contrib']}"),
        ]
        for r in checks:
            assert r.status_code == 404, (attacker_name, victim_name, r.request.url, r.text)
        rel = attacker.post(
            f"/api/investimentos/{mine['inv']}/movimentos",
            {"kind": "aporte", "movement_date": "2026-10-01", "amount_cents": 1, "account_id": v["acc"]},
        )
        assert rel.status_code == 422
    for name, api in [("ana", trio.ana), ("bruno", trio.bruno), ("carla", trio.carla)]:
        ov = api.get("/api/investimentos").json()
        assert [i["name"] for i in ov["items"]] == [f"CDB {name}"]
        assert ov["totals"]["invested_cents"] == 1000000
        assert [g["name"] for g in api.get("/api/metas").json()] == [f"Meta {name}"]
        h = api.get("/api/resumo").json()
        assert h["available_cents"] == 1000000
        assert balance(api, ids[name]["acc"]) == 1000000
