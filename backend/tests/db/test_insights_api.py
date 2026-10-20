"""Teto por categoria, gasto por dia, atalhos, calendário, resumo do mês e contas anuais
(hoje: 15/10/2026)."""

from __future__ import annotations

from typing import Any

from tests.db.api_helpers import Api
from tests.db.conftest_api import Trio, category_id, new_account


def _expense(
    api: Api, acc: str, cents: int, day: str, desc: str, cat: str | None = None, **extra: Any
) -> Any:
    r = api.post(
        "/api/lancamentos",
        {
            "kind": "despesa",
            "account_id": acc,
            "amount_cents": cents,
            "tx_date": day,
            "description": desc,
            "category_id": category_id(api, cat) if cat else None,
            **extra,
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


def _budget(api: Api, name: str) -> dict[str, Any]:
    items = api.get("/api/tetos").json()["items"]
    return next(i for i in items if i["category_name"] == name)


# ---------- teto por categoria ----------


def test_teto_avisa_perto_e_quando_passa(trio: Trio) -> None:
    api = trio.ana
    acc = new_account(api, balance=1000000)
    merc = category_id(api, "Mercado")
    r = api.put(f"/api/tetos/{merc}", {"monthly_limit_cents": 50000})
    assert r.status_code == 200, r.text
    _expense(api, acc, 36000, "2026-10-03", "Supermercado", "Mercado")
    card = api.post(
        "/api/cartoes", {"name": "Cartão", "limit_cents": 900000, "closing_day": 25, "due_day": 5}
    ).json()["id"]
    # Compra no cartão conta no mês da compra.
    api.post(
        f"/api/cartoes/{card}/compras",
        {"description": "Feira", "total_cents": 5000, "purchase_date": "2026-10-10", "category_id": merc},
    )
    b = _budget(api, "Mercado")
    assert (b["limit_cents"], b["spent_cents"], b["percent"], b["level"], b["left_cents"]) == (
        50000,
        41000,
        82,
        "perto",
        9000,
    )
    alerts = api.get("/api/resumo").json()["budget_alerts"]
    assert [(a["category_name"], a["level"]) for a in alerts] == [("Mercado", "perto")]

    _expense(api, acc, 10000, "2026-10-12", "Açougue", "Mercado")
    assert _budget(api, "Mercado")["level"] == "passou"
    # Reembolso reduz o gasto da categoria.
    api.post(
        "/api/lancamentos",
        {
            "kind": "reembolso",
            "account_id": acc,
            "amount_cents": 2000,
            "tx_date": "2026-10-13",
            "description": "Devolução",
            "category_id": merc,
        },
    )
    assert _budget(api, "Mercado")["spent_cents"] == 49000
    assert _budget(api, "Mercado")["level"] == "perto"


def test_teto_troca_de_valor_e_remocao(trio: Trio) -> None:
    api = trio.ana
    merc = category_id(api, "Mercado")
    api.put(f"/api/tetos/{merc}", {"monthly_limit_cents": 50000})
    api.put(f"/api/tetos/{merc}", {"monthly_limit_cents": 80000})
    items = api.get("/api/tetos").json()["items"]
    assert [i["limit_cents"] for i in items if i["category_name"] == "Mercado"] == [80000]
    assert items[0]["category_name"] == "Mercado"  # com teto aparece primeiro
    assert api.delete(f"/api/tetos/{merc}").status_code == 204
    assert _budget(api, "Mercado")["limit_cents"] is None
    assert api.delete(f"/api/tetos/{merc}").status_code == 404


def test_sugestao_de_teto_pela_mediana(trio: Trio) -> None:
    api = trio.ana
    acc = new_account(api, balance=0, on="2026-04-01")
    for month, cents in zip(
        ["04", "05", "06", "07", "08", "09"], [60000, 58000, 300000, 61000, 62000, 59500], strict=True
    ):
        _expense(api, acc, cents, f"2026-{month}-10", "Supermercado", "Mercado")
    _expense(api, acc, 9000, "2026-09-20", "Presente", "Presentes")
    assert _budget(api, "Mercado")["suggested_cents"] == 61000
    assert _budget(api, "Presentes")["suggested_cents"] is None  # só 1 mês com gasto


def test_teto_validacoes_e_isolamento(trio: Trio) -> None:
    ana, bruno = trio.ana, trio.bruno
    merc = category_id(ana, "Mercado")
    assert (
        ana.put(
            f"/api/tetos/{category_id(ana, 'Salário', 'receita')}", {"monthly_limit_cents": 1000}
        ).status_code
        == 422
    )
    assert ana.put(f"/api/tetos/{merc}", {"monthly_limit_cents": 0}).status_code == 422
    ana.put(f"/api/tetos/{merc}", {"monthly_limit_cents": 50000})
    # Bruno não vê, não altera e não remove o teto da Ana.
    assert bruno.put(f"/api/tetos/{merc}", {"monthly_limit_cents": 1}).status_code == 404
    assert bruno.delete(f"/api/tetos/{merc}").status_code == 404
    assert all(i["limit_cents"] is None for i in bruno.get("/api/tetos").json()["items"])
    assert _budget(ana, "Mercado")["limit_cents"] == 50000


# ---------- quanto posso gastar por dia ----------


def test_gasto_por_dia_ate_a_proxima_renda(trio: Trio) -> None:
    api = trio.ana
    acc = new_account(api, balance=100000)
    home = api.get("/api/resumo").json()
    # Sem renda principal cadastrada: 30 dias.
    assert (home["per_day_days"], home["per_day_cents"]) == (30, 3333)
    api.post(
        "/api/contas-a-pagar",
        {
            "kind": "receber",
            "description": "Salário",
            "amount_cents": 400000,
            "due_date": "2026-10-20",
            "account_id": acc,
            "is_main_income": True,
        },
    )
    api.post("/api/contas-a-pagar", {"description": "Luz", "amount_cents": 20000, "due_date": "2026-10-18"})
    home = api.get("/api/resumo").json()
    assert home["free_cents"] == 80000
    assert (home["per_day_days"], home["per_day_cents"]) == (5, 16000)


def test_sem_sobra_o_gasto_por_dia_e_zero(trio: Trio) -> None:
    api = trio.ana
    new_account(api, balance=10000)
    api.post(
        "/api/contas-a-pagar", {"description": "Aluguel", "amount_cents": 150000, "due_date": "2026-10-20"}
    )
    assert api.get("/api/resumo").json()["per_day_cents"] == 0


# ---------- atalhos ----------


def test_atalhos_mostram_gastos_repetidos_com_o_ultimo_valor(trio: Trio) -> None:
    api = trio.ana
    acc = new_account(api, on="2026-06-01")
    _expense(api, acc, 1500, "2026-10-01", "Padaria", "Mercado")
    _expense(api, acc, 1500, "2026-10-08", "padaria ", "Mercado")  # mesma, com outra grafia
    _expense(api, acc, 1800, "2026-10-14", "Padaria", "Mercado")
    _expense(api, acc, 2500, "2026-10-02", "Uber", "Transporte")
    _expense(api, acc, 2700, "2026-10-09", "Uber", "Transporte")
    _expense(api, acc, 9000, "2026-10-05", "Farmácia", "Medicamentos e saúde")  # só uma vez
    _expense(api, acc, 4000, "2026-06-20", "Cinema", "Lazer")  # antigas: mais de 90 dias
    _expense(api, acc, 4000, "2026-06-27", "Cinema", "Lazer")
    cancelled = _expense(api, acc, 3000, "2026-10-10", "Banca", "Lazer")
    _expense(api, acc, 3000, "2026-10-11", "Banca", "Lazer")
    api.post(f"/api/lancamentos/{cancelled['id']}/cancelar")
    out = api.get("/api/atalhos").json()
    assert [(a["description"], a["category_name"], a["amount_cents"], a["times"]) for a in out] == [
        ("Padaria", "Mercado", 1800, 3),
        ("Uber", "Transporte", 2700, 2),
    ]
    assert out[0]["account_id"] == acc
    assert trio.bruno.get("/api/atalhos").json() == []


# ---------- calendário ----------


def test_calendario_junta_contas_faturas_e_parcelas(trio: Trio) -> None:
    api = trio.ana
    acc = new_account(api, balance=500000, on="2026-09-01")
    api.post("/api/contas-a-pagar", {"description": "Luz", "amount_cents": 18000, "due_date": "2026-10-20"})
    cancelled = api.post(
        "/api/contas-a-pagar", {"description": "Revista", "amount_cents": 1000, "due_date": "2026-10-21"}
    ).json()
    api.post(f"/api/contas-a-pagar/{cancelled['id']}/cancelar")
    api.post(
        "/api/recorrencias",
        {
            "kind": "receber",
            "description": "Salário",
            "amount_cents": 450000,
            "anchor_date": "2026-09-05",
            "account_id": acc,
        },
    )
    card = api.post(
        "/api/cartoes", {"name": "Azul", "limit_cents": 900000, "closing_day": 25, "due_day": 5}
    ).json()["id"]
    api.post(
        f"/api/cartoes/{card}/compras",
        {
            "description": "Fogão",
            "total_cents": 90000,
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
            "first_due_date": "2026-10-25",
        },
    )
    cal = api.get("/api/calendario?mes=2026-10").json()
    got = [(i["date"], i["kind"], i["source"], i["description"], i["amount_cents"]) for i in cal["items"]]
    assert got == [
        ("2026-10-05", "receber", "conta", "Salário", 450000),
        ("2026-10-05", "pagar", "fatura", "Fatura Azul", 30000),
        ("2026-10-20", "pagar", "conta", "Luz", 18000),
        ("2026-10-25", "pagar", "divida", "Parcela: Banco", 52000),
    ]
    assert cal["to_pay_cents"] == 100000 and cal["to_receive_cents"] == 450000
    nov = api.get("/api/calendario?mes=2026-11").json()
    assert [(i["date"], i["description"]) for i in nov["items"]] == [
        ("2026-11-05", "Salário"),
        ("2026-11-05", "Fatura Azul"),
        ("2026-11-25", "Parcela: Banco"),
    ]
    assert api.get("/api/calendario?mes=2026-13").status_code == 422
    assert trio.bruno.get("/api/calendario?mes=2026-10").json()["items"] == []


# ---------- resumo do mês ----------


def test_resumo_do_mes_em_linguagem_simples(trio: Trio) -> None:
    api = trio.ana
    acc = new_account(api, balance=0, on="2026-08-01")
    api.post(
        "/api/lancamentos",
        {
            "kind": "receita",
            "account_id": acc,
            "amount_cents": 450000,
            "tx_date": "2026-09-05",
            "description": "Salário",
        },
    )
    _expense(api, acc, 200000, "2026-08-15", "Mercado do mês", "Mercado")
    _expense(api, acc, 140000, "2026-09-10", "Aluguel", "Casa")
    _expense(api, acc, 100000, "2026-09-12", "Mercado do mês", "Mercado")
    card = api.post(
        "/api/cartoes", {"name": "Azul", "limit_cents": 900000, "closing_day": 25, "due_day": 5}
    ).json()["id"]
    api.post(
        f"/api/cartoes/{card}/compras",
        {
            "description": "Show",
            "total_cents": 30000,
            "purchase_date": "2026-09-20",
            "category_id": category_id(api, "Lazer"),
        },
    )
    s = api.get("/api/relatorios/resumo?mes=2026-09").json()
    assert s["partial"] is False
    assert s["lines"] == [
        "Em setembro de 2026, você recebeu R$ 4.500,00 e gastou R$ 2.700,00.",
        "Sobrou R$ 1.800,00.",
        "Onde mais gastou: Casa (R$ 1.400,00), Mercado (R$ 1.000,00), Lazer (R$ 300,00).",
        "Gastou 35% a mais do que em agosto.",
        "Maior gasto: Aluguel, R$ 1.400,00 em 10/09/2026.",
    ]


def test_resumo_do_mes_atual_parcial_e_mes_futuro(trio: Trio) -> None:
    api = trio.ana
    acc = new_account(api)
    merc = category_id(api, "Mercado")
    api.put(f"/api/tetos/{merc}", {"monthly_limit_cents": 10000})
    _expense(api, acc, 15000, "2026-10-03", "Supermercado", "Mercado")
    s = api.get("/api/relatorios/resumo").json()
    assert s["partial"] is True
    assert s["lines"][0].startswith("Até agora, em outubro de 2026, você recebeu R$ 0,00")
    assert s["lines"][1] == "Gastou R$ 150,00 a mais do que recebeu."
    assert s["lines"][-1] == "Passou do teto em: Mercado."
    assert api.get("/api/relatorios/resumo?mes=2026-11").status_code == 422
    empty = trio.bruno.get("/api/relatorios/resumo?mes=2026-09").json()
    assert empty["lines"] == ["Em setembro de 2026, não há receitas nem gastos registrados."]


# ---------- contas anuais ----------


def test_contas_anuais_quanto_guardar_por_mes(trio: Trio) -> None:
    api = trio.ana
    acc = new_account(api, balance=900000, on="2026-01-01")
    api.post(
        "/api/recorrencias",
        {"description": "IPVA", "amount_cents": 120000, "anchor_date": "2026-01-20", "frequency": "anual"},
    )
    # Seguro anual de outubro já pago: o próximo é o do ano que vem.
    api.post(
        "/api/lancamentos",
        {
            "kind": "despesa",
            "account_id": acc,
            "amount_cents": 240000,
            "tx_date": "2026-10-10",
            "description": "Seguro do carro",
            "repeat": {"frequency": "anual"},
        },
    )
    annual = api.get("/api/plano-do-mes").json()["annual"]
    assert [
        (a["description"], a["next_due"], a["months_left"], a["per_month_cents"], a["steady_cents"])
        for a in annual
    ] == [
        ("IPVA", "2027-01-20", 3, 40000, 10000),
        ("Seguro do carro", "2027-10-10", 12, 20000, 20000),
    ]
    assert trio.bruno.get("/api/plano-do-mes").json()["annual"] == []
