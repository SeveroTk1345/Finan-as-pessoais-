"""Cartões, faturas e dívidas pela API: regressão contra dupla contagem.

Hoje (relógio fixo): 15/10/2026. Cartão de teste: fecha dia 25, vence dia 5.
Fatura aberta hoje: vencimento 05/11/2026.
"""

from __future__ import annotations

from typing import Any

from tests.db.api_helpers import Api
from tests.db.conftest_api import Trio, balance, new_account


def _card(api: Api, limit: int = 500000) -> str:
    r = api.post(
        "/api/cartoes",
        {
            "name": "Cartão Azul",
            "institution": "Banco Fictício",
            "limit_cents": limit,
            "closing_day": 25,
            "due_day": 5,
        },
    )
    assert r.status_code == 201, r.text
    return str(r.json()["id"])


def _buy(
    api: Api,
    card: str,
    total: int,
    n: int = 1,
    on: str = "2026-10-10",
    desc: str = "Geladeira",
    kind: str = "compra",
) -> dict[str, Any]:
    r = api.post(
        f"/api/cartoes/{card}/compras",
        {
            "description": desc,
            "total_cents": total,
            "purchase_date": on,
            "installments_count": n,
            "kind": kind,
        },
    )
    assert r.status_code == 201, r.text
    return dict(r.json())


def _card_state(api: Api, card: str) -> dict[str, Any]:
    return dict(api.get(f"/api/cartoes/{card}").json())


def _invoice(api: Api, card: str, due: str) -> dict[str, Any]:
    return dict(api.get(f"/api/cartoes/{card}/faturas/{due}").json())


def _expenses_total(api: Api) -> int:
    items = api.get("/api/lancamentos?tipo=despesa&limite=200").json()["items"]
    return sum(i["amount_cents"] for i in items)


# --- compras e limite -----------------------------------------------------------------


def test_compra_parcelada_ocupa_o_limite_uma_vez(trio: Trio) -> None:
    api = trio.ana
    card = _card(api)
    p = _buy(api, card, 100000, 3)
    assert [i["amount_cents"] for i in p["installments"]] == [33334, 33333, 33333]
    assert [i["invoice_due_date"] for i in p["installments"]] == ["2026-11-05", "2026-12-05", "2027-01-05"]
    s = _card_state(api, card)
    assert s["limit_used_cents"] == 100000
    assert s["limit_available_cents"] == 400000
    assert s["open_invoice"]["total_cents"] == 33334
    # As faturas futuras existem, mas o limite não soma de novo.
    futures = [i for i in s["invoices"] if i["status"] == "futura"] if "invoices" in s else []
    assert sum(i["total_cents"] for i in futures) == 66666


def test_compra_no_dia_do_fechamento_vai_para_a_proxima_fatura(trio: Trio) -> None:
    api = trio.ana
    card = _card(api)
    p = _buy(api, card, 1000, on="2026-09-25")
    assert p["installments"][0]["invoice_due_date"] == "2026-11-05"
    p2 = _buy(api, card, 1000, on="2026-09-24")
    assert p2["installments"][0]["invoice_due_date"] == "2026-10-05"


def test_pagar_fatura_nao_cria_segunda_despesa(trio: Trio) -> None:
    api = trio.ana
    acc = new_account(api, balance=300000)
    card = _card(api)
    _buy(api, card, 60000, 1, on="2026-09-10")  # fatura de 05/10/2026, já vencida
    inv = _invoice(api, card, "2026-10-05")
    assert inv["status"] == "vencida" and inv["remaining_cents"] == 60000
    r = api.post(f"/api/cartoes/{card}/faturas/2026-10-05/pagar", {"account_id": acc})
    assert r.status_code == 201, r.text
    assert r.json()["invoice"]["status"] == "paga"
    assert r.json()["transaction"]["kind"] == "pagamento_fatura"
    assert balance(api, acc) == 240000
    assert _expenses_total(api) == 0  # o gasto é a compra; o pagamento é liquidação
    s = _card_state(api, card)
    assert s["limit_used_cents"] == 0
    assert s["limit_available_cents"] == 500000


def test_pagamento_parcial_mantem_o_restante(trio: Trio) -> None:
    api = trio.ana
    acc = new_account(api, balance=300000)
    card = _card(api)
    _buy(api, card, 50000, 1, on="2026-09-10")
    r = api.post(f"/api/cartoes/{card}/faturas/2026-10-05/pagar", {"account_id": acc, "amount_cents": 30000})
    assert r.status_code == 201
    inv = r.json()["invoice"]
    assert inv["remaining_cents"] == 20000
    assert inv["status"] == "vencida"
    s = _card_state(api, card)
    assert s["limit_used_cents"] == 20000
    assert s["outstanding_cents"] == 20000
    over = api.post(
        f"/api/cartoes/{card}/faturas/2026-10-05/pagar", {"account_id": acc, "amount_cents": 20001}
    )
    assert over.status_code == 422
    assert balance(api, acc) == 270000


def test_cancelamento_com_parcelas_ja_faturadas_gera_credito(trio: Trio) -> None:
    api = trio.ana
    card = _card(api)
    p = _buy(api, card, 60000, 6, on="2026-08-10")  # faturas 09, 10 (fechadas), 11 (aberta)...
    r = api.post(f"/api/compras/{p['id']}/cancelar", key=None)
    assert r.status_code == 200, r.text
    after = r.json()
    assert after["status"] == "cancelada"
    statuses = [i["status"] for i in after["installments"]]
    assert statuses == ["ativa", "ativa", "cancelada", "cancelada", "cancelada", "cancelada"]
    assert after["credits"][0]["amount_cents"] == 20000
    assert after["credits"][0]["invoice_due_date"] == "2026-11-05"
    assert after["net_cents"] == 0
    s = _card_state(api, card)
    assert s["limit_used_cents"] == 0
    # Histórico preservado: a compra e as parcelas continuam consultáveis.
    assert api.get(f"/api/compras/{p['id']}").status_code == 200


def test_estorno_parcial_e_limite(trio: Trio) -> None:
    api = trio.ana
    card = _card(api)
    p = _buy(api, card, 30000, 3)
    r = api.post(f"/api/compras/{p['id']}/estornar", {"amount_cents": 10000})
    assert r.status_code == 201, r.text
    assert r.json()["net_cents"] == 20000
    assert _card_state(api, card)["limit_used_cents"] == 20000
    too_much = api.post(f"/api/compras/{p['id']}/estornar", {"amount_cents": 20001})
    assert too_much.status_code == 422


def test_estorno_seguido_de_cancelamento_nao_credita_em_dobro(trio: Trio) -> None:
    api = trio.ana
    card = _card(api)
    p = _buy(api, card, 30000, 3)
    api.post(f"/api/compras/{p['id']}/estornar", {"amount_cents": 30000})
    after = api.post(f"/api/compras/{p['id']}/cancelar", key=None).json()
    assert after["net_cents"] == 0
    s = _card_state(api, card)
    assert s["limit_used_cents"] == 0
    assert s["credit_balance_cents"] == 0


def test_estorno_maior_que_a_fatura_vira_credito_na_seguinte(trio: Trio) -> None:
    api = trio.ana
    card = _card(api)
    big = _buy(api, card, 90000, 3)  # 300,00 por fatura a partir de 05/11
    api.post(f"/api/compras/{big['id']}/estornar", {"amount_cents": 50000})
    s = api.get(f"/api/cartoes/{card}").json()
    invs = {i["due_date"]: i for i in s["invoices"]}
    assert invs["2026-11-05"]["remaining_cents"] == 0
    assert invs["2026-11-05"]["credit_left_cents"] == 20000
    assert invs["2026-12-05"]["carried_credit_cents"] == 20000
    assert invs["2026-12-05"]["remaining_cents"] == 10000
    assert sum(i["remaining_cents"] for i in s["invoices"]) == 40000
    assert s["limit_used_cents"] == 40000


def test_encargo_entra_na_fatura_aberta(trio: Trio) -> None:
    api = trio.ana
    card = _card(api)
    _buy(api, card, 350, kind="encargo", desc="IOF")
    inv = _invoice(api, card, "2026-11-05")
    assert inv["total_cents"] == 350
    assert inv["items"][0]["category_name"] == "Juros e tarifas"


# --- renegociação de fatura -------------------------------------------------------------


def test_renegociacao_de_fatura_transfere_sem_duplicar(trio: Trio) -> None:
    api = trio.ana
    acc = new_account(api, balance=500000)
    card = _card(api)
    _buy(api, card, 100000, 1, on="2026-09-10")  # fatura 05/10 de R$ 1.000,00, vencida
    # Entrada de R$ 200,00 e R$ 800,00 em 10x de R$ 100,00 (total R$ 1.000,00).
    api.post(f"/api/cartoes/{card}/faturas/2026-10-05/pagar", {"account_id": acc, "amount_cents": 20000})
    r = api.post(
        f"/api/cartoes/{card}/faturas/2026-10-05/renegociar",
        {"financed_cents": 80000, "installments_count": 10, "installment_cents": 10000},
    )
    assert r.status_code == 201, r.text
    assert r.json()["invoice"]["remaining_cents"] == 0
    assert r.json()["invoice"]["status"] == "paga"
    debt_id = r.json()["debt_id"]

    s = _card_state(api, card)
    # Usado: 1.000 da compra + 1.000 do acordo - 800 renegociados - 200 pagos = 1.000
    assert s["limit_used_cents"] == 100000
    assert s["outstanding_cents"] == 100000
    debt = api.get(f"/api/dividas/{debt_id}").json()
    assert debt["kind"] == "parcelamento_fatura"
    assert debt["balance_cents"] == 100000
    assert debt["installments_remaining"] == 10
    assert debt["is_card_channel"] is True
    # A dívida não pode ser paga diretamente: é paga pelas faturas.
    direct = api.post(f"/api/dividas/{debt_id}/pagamentos", {"account_id": acc, "amount_cents": 10000})
    assert direct.status_code == 409
    # Parcela do acordo na fatura de 05/11.
    nov = _invoice(api, card, "2026-11-05")
    assert nov["total_cents"] == 10000
    assert nov["items"][0]["kind"] == "parcelamento_fatura"


def test_renegociacao_acima_do_restante_e_recusada(trio: Trio) -> None:
    api = trio.ana
    card = _card(api)
    _buy(api, card, 10000, on="2026-09-10")
    r = api.post(
        f"/api/cartoes/{card}/faturas/2026-10-05/renegociar",
        {"financed_cents": 10001, "installments_count": 2, "installment_cents": 6000},
    )
    assert r.status_code == 422
    r = api.post(
        f"/api/cartoes/{card}/faturas/2026-10-05/renegociar",
        {"financed_cents": 10000, "installments_count": 2, "installment_cents": 4000},
    )
    assert r.status_code == 422  # parcelas somam menos que o valor


# --- dívidas -----------------------------------------------------------------------------


def _debt(api: Api, **kw: Any) -> dict[str, Any]:
    payload = {
        "creditor": "Banco Fictício",
        "kind": "emprestimo",
        "original_amount_cents": 1000000,
        "current_balance_cents": 1000000,
        "balance_date": "2026-10-01",
        "interest_rate": "2.5",
        "rate_period": "mensal",
        "installments_total": 10,
        "installment_amount_cents": 114000,
        "first_due_date": "2026-10-10",
        **kw,
    }
    r = api.post("/api/dividas", payload)
    assert r.status_code == 201, r.text
    return dict(r.json())


def test_divida_pagamentos_e_progresso(trio: Trio) -> None:
    api = trio.ana
    acc = new_account(api, balance=1000000)
    d = _debt(api)
    assert d["overdue"] is True  # parcela de 10/10 ainda não registrada
    r = api.post(
        f"/api/dividas/{d['id']}/pagamentos",
        {"account_id": acc, "amount_cents": 114000, "interest_cents": 25000, "tx_date": "2026-10-10"},
    )
    assert r.status_code == 201, r.text
    after = r.json()["debt"]
    assert after["balance_cents"] == 1000000 - 89000
    assert after["installments_paid"] == 1
    assert after["installments_remaining"] == 9
    assert after["next_due_date"] == "2026-11-10"
    assert after["overdue"] is False
    assert after["balance_estimated"] is False
    assert balance(api, acc) == 1000000 - 114000
    assert _expenses_total(api) == 0  # pagamento de dívida não é despesa de consumo


def test_pagamento_sem_juros_informados_e_estimado(trio: Trio) -> None:
    api = trio.ana
    acc = new_account(api, balance=1000000)
    d = _debt(api, interest_rate=None, rate_period=None)
    after = api.post(
        f"/api/dividas/{d['id']}/pagamentos", {"account_id": acc, "amount_cents": 100000}
    ).json()["debt"]
    assert after["balance_cents"] == 900000
    assert after["balance_estimated"] is True


def test_quitacao_e_cancelamento_de_pagamento(trio: Trio) -> None:
    api = trio.ana
    acc = new_account(api, balance=2000000)
    d = _debt(api, current_balance_cents=50000)
    r = api.post(
        f"/api/dividas/{d['id']}/pagamentos",
        {"account_id": acc, "amount_cents": 50000, "payment_type": "quitacao"},
    )
    assert r.json()["debt"]["status"] == "quitada"
    over = api.post(f"/api/dividas/{d['id']}/pagamentos", {"account_id": acc, "amount_cents": 1})
    assert over.status_code == 409
    api.post(f"/api/lancamentos/{r.json()['transaction']['id']}/cancelar", key=None)
    assert api.get(f"/api/dividas/{d['id']}").json()["status"] == "ativa"


def test_pagamento_acima_do_saldo_recusado(trio: Trio) -> None:
    api = trio.ana
    acc = new_account(api)
    d = _debt(api, current_balance_cents=10000)
    r = api.post(f"/api/dividas/{d['id']}/pagamentos", {"account_id": acc, "amount_cents": 10001})
    assert r.status_code == 422
    assert "saldo devedor" in r.json()["detail"]


def test_entrada_do_emprestimo_nao_e_receita(trio: Trio) -> None:
    api = trio.ana
    acc = new_account(api, balance=0)
    _debt(api, disbursement_account_id=acc, start_date="2026-10-01")
    assert balance(api, acc) == 1000000
    items = api.get("/api/lancamentos").json()["items"]
    assert [i["kind"] for i in items] == ["entrada_emprestimo"]
    assert api.get("/api/lancamentos?tipo=receita").json()["total"] == 0


def test_renegociacao_de_divida(trio: Trio) -> None:
    api = trio.ana
    d = _debt(api)
    r = api.post(
        f"/api/dividas/{d['id']}/renegociar",
        {
            "new_balance_cents": 800000,
            "installments_total": 20,
            "installment_amount_cents": 45000,
            "first_due_date": "2026-11-15",
        },
    )
    assert r.status_code == 201, r.text
    old, new = r.json()["old"], r.json()["new"]
    assert old["status"] == "renegociada" and old["balance_cents"] == 0
    assert new["balance_cents"] == 800000
    assert new["renegotiated_from_id"] == d["id"]
    active = api.get("/api/dividas?incluir_encerradas=false").json()
    assert [x["id"] for x in active] == [new["id"]]
    assert sum(x["balance_cents"] for x in active) == 800000


def test_encargo_e_desconto(trio: Trio) -> None:
    api = trio.ana
    d = _debt(api, current_balance_cents=10000)
    api.post(f"/api/dividas/{d['id']}/eventos", {"kind": "encargo", "amount_cents": 500})
    after = api.post(f"/api/dividas/{d['id']}/eventos", {"kind": "desconto", "amount_cents": 200}).json()
    assert after["balance_cents"] == 10300


def test_taxa_sem_periodo_e_recusada(trio: Trio) -> None:
    r = trio.ana.post(
        "/api/dividas",
        {"creditor": "X", "original_amount_cents": 100, "interest_rate": "2", "rate_period": None},
    )
    assert r.status_code == 422


def test_estrategias_comparam_as_quatro_opcoes(trio: Trio) -> None:
    api = trio.ana
    _debt(
        api,
        creditor="Banco A",
        current_balance_cents=300000,
        interest_rate="4",
        installment_amount_cents=30000,
        installments_total=None,
    )
    _debt(
        api,
        creditor="Loja B",
        current_balance_cents=100000,
        interest_rate=None,
        rate_period=None,
        installment_amount_cents=20000,
        installments_total=None,
    )
    r = api.post("/api/dividas/estrategias", {"extra_monthly_cents": 10000}, key=None)
    assert r.status_code == 200, r.text
    body = r.json()
    assert [x["strategy"] for x in body["results"]] == [
        "maior_juros",
        "menor_saldo",
        "menor_parcela",
        "equilibrada",
    ]
    assert all(x["months"] for x in body["results"])
    assert any("sem taxa" in w for w in body["results"][0]["warnings"])


# --- isolamento -----------------------------------------------------------------------


def test_acesso_cruzado_em_cartoes_faturas_parcelas_e_dividas(trio: Trio) -> None:
    data = {}
    for name, api in [("ana", trio.ana), ("bruno", trio.bruno), ("carla", trio.carla)]:
        acc = new_account(api, balance=1000000)
        card = _card(api)
        purchase = _buy(api, card, 30000, 3, on="2026-09-10")
        debt = _debt(api, creditor=f"Credor {name}")
        data[name] = {"acc": acc, "card": card, "purchase": purchase["id"], "debt": debt["id"]}

    for attacker_name, attacker, victim_name, _ in trio.pairs():
        v, mine = data[victim_name], data[attacker_name]
        checks = [
            attacker.get(f"/api/cartoes/{v['card']}"),
            attacker.patch(f"/api/cartoes/{v['card']}", {"limit_cents": 1}),
            attacker.post(
                f"/api/cartoes/{v['card']}/compras",
                {"description": "x", "total_cents": 1, "purchase_date": "2026-10-01"},
            ),
            attacker.get(f"/api/cartoes/{v['card']}/faturas/2026-10-05"),
            attacker.post(f"/api/cartoes/{v['card']}/faturas/2026-10-05/pagar", {"account_id": mine["acc"]}),
            attacker.post(
                f"/api/cartoes/{v['card']}/faturas/2026-10-05/renegociar",
                {"financed_cents": 1, "installments_count": 1, "installment_cents": 1},
            ),
            attacker.get(f"/api/compras/{v['purchase']}"),
            attacker.post(f"/api/compras/{v['purchase']}/cancelar", key=None),
            attacker.post(f"/api/compras/{v['purchase']}/estornar", {"amount_cents": 1}),
            attacker.get(f"/api/dividas/{v['debt']}"),
            attacker.patch(f"/api/dividas/{v['debt']}", {"creditor": "x"}),
            attacker.post(
                f"/api/dividas/{v['debt']}/pagamentos", {"account_id": mine["acc"], "amount_cents": 1}
            ),
            attacker.post(f"/api/dividas/{v['debt']}/eventos", {"kind": "encargo", "amount_cents": 1}),
            attacker.post(f"/api/dividas/{v['debt']}/renegociar", {"new_balance_cents": 1}),
            attacker.post(f"/api/dividas/{v['debt']}/cancelar", key=None),
        ]
        for r in checks:
            assert r.status_code == 404, (attacker_name, victim_name, r.request.url, r.text)
        # Pagar a própria fatura ou dívida com a conta de outra pessoa.
        own_card = mine["card"]
        relations = [
            attacker.post(f"/api/cartoes/{own_card}/faturas/2026-10-05/pagar", {"account_id": v["acc"]}),
            attacker.post(
                f"/api/dividas/{mine['debt']}/pagamentos", {"account_id": v["acc"], "amount_cents": 1}
            ),
            attacker.post(
                "/api/dividas",
                {"creditor": "x", "original_amount_cents": 1, "disbursement_account_id": v["acc"]},
            ),
        ]
        for r in relations:
            assert r.status_code == 422, (attacker_name, victim_name, r.request.url, r.text)

    for name, api in [("ana", trio.ana), ("bruno", trio.bruno), ("carla", trio.carla)]:
        cards = api.get("/api/cartoes").json()
        assert len(cards) == 1 and cards[0]["limit_used_cents"] == 30000
        debts = api.get("/api/dividas").json()
        assert [d["creditor"] for d in debts] == [f"Credor {name}"]
        assert debts[0]["balance_cents"] == 1000000
        assert balance(api, data[name]["acc"]) == 1000000


def test_estorno_parcial_de_compra_faturada_seguido_de_cancelamento(trio: Trio) -> None:
    api = trio.ana
    card = _card(api)
    p = _buy(api, card, 60000, 6, on="2026-08-10")  # 2 parcelas (R$ 200,00) já faturadas
    api.post(f"/api/compras/{p['id']}/estornar", {"amount_cents": 5000})
    after = api.post(f"/api/compras/{p['id']}/cancelar", key=None).json()
    cancel_credit = [c for c in after["credits"] if c["kind"] == "cancelamento"]
    assert cancel_credit[0]["amount_cents"] == 15000  # 200,00 faturados - 50,00 já estornados
    assert after["net_cents"] == 0
    assert _card_state(api, card)["limit_used_cents"] == 0
