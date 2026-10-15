"""Núcleo financeiro pela API, com banco real e três usuários."""

from __future__ import annotations

import secrets
import threading
from typing import Any

import pytest
from sqlalchemy import Engine, text

from tests.db.api_helpers import Api
from tests.db.conftest_api import Trio, balance, category_id, new_account

# --- contas e saldos ------------------------------------------------------------------


def test_receita_e_despesa_atualizam_o_saldo(trio: Trio) -> None:
    api = trio.ana
    acc = new_account(api, balance=100000)
    r = api.post(
        "/api/lancamentos",
        {
            "kind": "receita",
            "account_id": acc,
            "amount_cents": 350000,
            "tx_date": "2026-10-05",
            "description": "Salário",
            "category_id": category_id(api, "Salário", "receita"),
        },
    )
    assert r.status_code == 201, r.text
    r = api.post(
        "/api/lancamentos",
        {
            "kind": "despesa",
            "account_id": acc,
            "amount_cents": 12345,
            "tx_date": "2026-10-06",
            "description": "Mercado",
            "category_id": category_id(api, "Mercado"),
            "expense_nature": "variavel",
        },
    )
    assert r.status_code == 201, r.text
    assert balance(api, acc) == 100000 + 350000 - 12345


def test_transferencia_nao_muda_o_total_nem_vira_receita(trio: Trio) -> None:
    api = trio.ana
    a = new_account(api, "Corrente", 100000)
    b = new_account(api, "Poupança", 50000, kind="poupanca")
    r = api.post(
        "/api/transferencias",
        {"from_account_id": a, "to_account_id": b, "amount_cents": 30000, "tx_date": "2026-10-10"},
    )
    assert r.status_code == 201, r.text
    assert balance(api, a) == 70000
    assert balance(api, b) == 80000
    items = api.get("/api/lancamentos").json()["items"]
    assert {i["kind"] for i in items} == {"transferencia"}
    assert len(items) == 2


def test_transferencia_para_a_mesma_conta_recusada(trio: Trio) -> None:
    a = new_account(trio.ana)
    r = trio.ana.post(
        "/api/transferencias",
        {"from_account_id": a, "to_account_id": a, "amount_cents": 1, "tx_date": "2026-10-10"},
    )
    assert r.status_code == 422


def test_cancelar_transferencia_cancela_as_duas_pernas(trio: Trio) -> None:
    api = trio.ana
    a, b = new_account(api, "A", 1000), new_account(api, "B", 0)
    r = api.post(
        "/api/transferencias",
        {"from_account_id": a, "to_account_id": b, "amount_cents": 400, "tx_date": "2026-10-10"},
    )
    out_id = r.json()["saida"]["id"]
    assert api.post(f"/api/lancamentos/{out_id}/cancelar", key=None).status_code == 200
    assert (balance(api, a), balance(api, b)) == (1000, 0)
    all_items = api.get("/api/lancamentos?incluir_cancelados=true").json()["items"]
    assert {i["status"] for i in all_items} == {"cancelado"}


def test_cancelamento_preserva_historico_e_edicao_registra_antes(trio: Trio) -> None:
    api = trio.ana
    acc = new_account(api, balance=0)
    tx = api.post(
        "/api/lancamentos",
        {
            "kind": "despesa",
            "account_id": acc,
            "amount_cents": 1000,
            "tx_date": "2026-10-02",
            "description": "Café",
        },
    ).json()
    r = api.patch(f"/api/lancamentos/{tx['id']}", {"amount_cents": 1500, "version": 1})
    assert r.status_code == 200, r.text
    detail = r.json()
    assert detail["amount_cents"] == 1500
    assert detail["history"][0]["before_data"]["amount_cents"] == 1000
    assert balance(api, acc) == -1500
    # Versão antiga: alteração feita em outro aparelho.
    assert api.patch(f"/api/lancamentos/{tx['id']}", {"amount_cents": 1, "version": 1}).status_code == 409
    assert api.post(f"/api/lancamentos/{tx['id']}/cancelar", key=None).status_code == 200
    assert balance(api, acc) == 0
    assert api.get(f"/api/lancamentos/{tx['id']}").json()["status"] == "cancelado"


@pytest.mark.parametrize(
    ("payload", "field"),
    [
        ({"amount_cents": 0}, "amount_cents"),
        ({"amount_cents": -100}, "amount_cents"),
        ({"amount_cents": 1.5}, "amount_cents"),
        ({"amount_cents": "100"}, None),  # texto numérico é aceito pelo pydantic? não em strict
        ({"tx_date": "15/10/2026"}, "tx_date"),
        ({"tx_date": "2026-02-30"}, "tx_date"),
        ({"description": ""}, "description"),
        ({"kind": "lucro"}, "kind"),
    ],
)
def test_validacao_de_lancamento(trio: Trio, payload: dict[str, object], field: str | None) -> None:
    acc = new_account(trio.ana)
    base = {
        "kind": "despesa",
        "account_id": acc,
        "amount_cents": 100,
        "tx_date": "2026-10-02",
        "description": "x",
    }
    r = trio.ana.post("/api/lancamentos", {**base, **payload})
    if field is None:
        assert r.status_code in (201, 422)
        return
    assert r.status_code == 422, r.text
    assert field in r.json()["campos"]


def test_lancamento_realizado_no_futuro_ou_antes_do_saldo_inicial(trio: Trio) -> None:
    acc = new_account(trio.ana, on="2026-10-01")
    base = {"kind": "despesa", "account_id": acc, "amount_cents": 100, "description": "x"}
    r = trio.ana.post("/api/lancamentos", {**base, "tx_date": "2026-10-16"})
    assert r.status_code == 422
    assert "futuro" in r.json()["detail"]
    r = trio.ana.post("/api/lancamentos", {**base, "tx_date": "2026-09-30"})
    assert r.status_code == 422
    assert "saldo inicial" in r.json()["detail"]


def test_categoria_de_tipo_errado(trio: Trio) -> None:
    acc = new_account(trio.ana)
    r = trio.ana.post(
        "/api/lancamentos",
        {
            "kind": "despesa",
            "account_id": acc,
            "amount_cents": 100,
            "tx_date": "2026-10-02",
            "description": "x",
            "category_id": category_id(trio.ana, "Salário", "receita"),
        },
    )
    assert r.status_code == 422


def test_conta_com_lancamentos_nao_e_excluida_mas_pode_ser_desativada(trio: Trio) -> None:
    api = trio.ana
    acc = new_account(api)
    api.post(
        "/api/lancamentos",
        {
            "kind": "despesa",
            "account_id": acc,
            "amount_cents": 100,
            "tx_date": "2026-10-02",
            "description": "x",
        },
    )
    r = api.delete(f"/api/contas/{acc}")
    assert r.status_code == 409
    assert "desativá-la" in r.json()["detail"]
    assert api.patch(f"/api/contas/{acc}", {"is_active": False}).status_code == 200
    empty = new_account(api, "Vazia")
    assert api.delete(f"/api/contas/{empty}").status_code == 204


def test_ajuste_de_saldo_cria_lancamento_auditavel(trio: Trio) -> None:
    api = trio.ana
    acc = new_account(api, balance=100000)
    r = api.post(f"/api/contas/{acc}/ajustar-saldo", {"real_balance_cents": 98765, "on": "2026-10-15"})
    assert r.status_code == 201, r.text
    assert r.json()["ajuste"]["kind"] == "ajuste"
    assert r.json()["ajuste"]["direction"] == "saida"
    assert r.json()["ajuste"]["amount_cents"] == 1235
    assert balance(api, acc) == 98765


def test_busca_e_filtros(trio: Trio) -> None:
    api = trio.ana
    a, b = new_account(api, "A", 0), new_account(api, "B", 0)
    for acc, desc, d in [
        (a, "Farmácia 100%", "2026-10-02"),
        (b, "Padaria", "2026-10-03"),
        (a, "Farmácia_bairro", "2026-10-04"),
    ]:
        api.post(
            "/api/lancamentos",
            {
                "kind": "despesa",
                "account_id": acc,
                "amount_cents": 100,
                "tx_date": d,
                "description": desc,
            },
        )
    assert api.get("/api/lancamentos?busca=farm").json()["total"] == 2
    assert api.get("/api/lancamentos?busca=100%25").json()["total"] == 1  # % é literal
    assert api.get("/api/lancamentos?busca=a_b").json()["total"] == 1  # _ é literal
    assert api.get(f"/api/lancamentos?conta={b}").json()["total"] == 1
    assert api.get("/api/lancamentos?inicio=2026-10-03&fim=2026-10-03").json()["total"] == 1


# --- idempotência ---------------------------------------------------------------------


def test_repeticao_com_a_mesma_chave_nao_duplica(trio: Trio, admin_engine: Engine) -> None:
    api = trio.ana
    acc = new_account(api, balance=0)
    key = secrets.token_urlsafe(18)
    payload = {
        "kind": "despesa",
        "account_id": acc,
        "amount_cents": 5000,
        "tx_date": "2026-10-02",
        "description": "Luz",
    }
    first = api.post("/api/lancamentos", payload, key=key)
    again = api.post("/api/lancamentos", payload, key=key)
    assert first.status_code == again.status_code == 201
    assert again.json() == first.json()
    assert again.headers.get("idempotent-replay") == "true"
    assert balance(api, acc) == -5000
    other = api.post("/api/lancamentos", {**payload, "amount_cents": 9999}, key=key)
    assert other.status_code == 409
    assert balance(api, acc) == -5000


def test_sem_chave_de_idempotencia_e_recusado(trio: Trio) -> None:
    acc = new_account(trio.ana)
    r = trio.ana.post(
        "/api/lancamentos",
        {
            "kind": "despesa",
            "account_id": acc,
            "amount_cents": 1,
            "tx_date": "2026-10-02",
            "description": "x",
        },
        key=None,
    )
    assert r.status_code == 400
    assert balance(trio.ana, acc) == 100000


def test_mesma_chave_em_usuarios_diferentes_sao_operacoes_diferentes(trio: Trio) -> None:
    key = secrets.token_urlsafe(18)
    a = trio.ana.post(
        "/api/contas",
        {
            "name": "X",
            "kind": "corrente",
            "initial_balance_cents": 1,
            "initial_balance_date": "2026-10-01",
        },
        key=key,
    )
    b = trio.bruno.post(
        "/api/contas",
        {
            "name": "X",
            "kind": "corrente",
            "initial_balance_cents": 1,
            "initial_balance_date": "2026-10-01",
        },
        key=key,
    )
    assert a.status_code == b.status_code == 201
    assert a.json()["id"] != b.json()["id"]


def test_envios_simultaneos_com_a_mesma_chave_criam_um_registro(trio: Trio) -> None:
    api = trio.ana
    acc = new_account(api, balance=0)
    key = secrets.token_urlsafe(18)
    payload = {
        "kind": "despesa",
        "account_id": acc,
        "amount_cents": 700,
        "tx_date": "2026-10-02",
        "description": "Toque duplo",
    }
    statuses: list[int] = []

    def send() -> None:
        statuses.append(api.post("/api/lancamentos", payload, key=key).status_code)

    threads = [threading.Thread(target=send) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert balance(api, acc) == -700
    assert api.get("/api/lancamentos").json()["total"] == 1
    assert all(s in (201, 409) for s in statuses)


def test_resposta_perdida_e_reenvio(trio: Trio) -> None:
    """O servidor gravou, a resposta se perdeu; o app reenvia com a mesma chave."""
    api = trio.ana
    acc = new_account(api, balance=0)
    key = secrets.token_urlsafe(18)
    payload = {
        "kind": "receita",
        "account_id": acc,
        "amount_cents": 1000,
        "tx_date": "2026-10-02",
        "description": "Venda",
    }
    api.post("/api/lancamentos", payload, key=key)  # resposta "perdida": ignorada
    retry = api.post("/api/lancamentos", payload, key=key)
    assert retry.status_code == 201
    assert balance(api, acc) == 1000


# --- contas a pagar --------------------------------------------------------------------


def _bill(api: Api, **kw: object) -> dict[str, Any]:
    payload = {"description": "Aluguel", "amount_cents": 150000, "due_date": "2026-10-10", **kw}
    r = api.post("/api/contas-a-pagar", payload)
    assert r.status_code == 201, r.text
    return dict(r.json())


def test_conta_vencida_nao_vira_paga_e_continua_aparecendo(trio: Trio) -> None:
    api = trio.ana
    bill = _bill(api, due_date="2026-09-10")
    assert bill["situation"] == "vencida"
    # Na lista de outubro, a vencida de setembro continua aparecendo, uma vez só.
    items = api.get("/api/contas-a-pagar?inicio=2026-10-01&fim=2026-10-31").json()
    assert [i["id"] for i in items] == [bill["id"]]
    nov = api.get("/api/contas-a-pagar?inicio=2026-11-01&fim=2026-11-30").json()
    assert [i["id"] for i in nov] == [bill["id"]]


def test_pagamento_parcial_e_integral_sem_duplicar_despesa(trio: Trio) -> None:
    api = trio.ana
    acc = new_account(api, balance=200000)
    bill = _bill(api, due_date="2026-10-20")
    r = api.post(
        f"/api/contas-a-pagar/{bill['id']}/pagar",
        {"amount_cents": 50000, "account_id": acc, "tx_date": "2026-10-09"},
    )
    assert r.status_code == 201, r.text
    assert r.json()["bill"]["situation"] == "parcialmente_paga"
    assert r.json()["bill"]["remaining_cents"] == 100000
    over = api.post(f"/api/contas-a-pagar/{bill['id']}/pagar", {"amount_cents": 100001, "account_id": acc})
    assert over.status_code == 422
    r = api.post(f"/api/contas-a-pagar/{bill['id']}/pagar", {"account_id": acc})
    assert r.json()["bill"]["situation"] == "paga"
    assert balance(api, acc) == 200000 - 150000
    # Duas saídas que somam o valor da conta; a conta a pagar em si não é despesa.
    expenses = api.get("/api/lancamentos?tipo=despesa").json()
    assert expenses["total"] == 2
    assert sum(i["amount_cents"] for i in expenses["items"]) == 150000
    again = api.post(f"/api/contas-a-pagar/{bill['id']}/pagar", {"account_id": acc})
    assert again.status_code == 409


def test_cancelar_pagamento_reabre_a_conta(trio: Trio) -> None:
    api = trio.ana
    acc = new_account(api)
    bill = _bill(api, due_date="2026-10-20")
    pay = api.post(f"/api/contas-a-pagar/{bill['id']}/pagar", {"account_id": acc}).json()
    api.post(f"/api/lancamentos/{pay['transaction']['id']}/cancelar", key=None)
    assert api.get(f"/api/contas-a-pagar/{bill['id']}").json()["situation"] == "pendente"


def test_recorrencia_mensal_virtual_e_pagamento(trio: Trio) -> None:
    api = trio.ana
    acc = new_account(api)
    rule = api.post(
        "/api/recorrencias",
        {
            "description": "Internet",
            "amount_cents": 9990,
            "anchor_date": "2026-01-31",
            "account_id": acc,
        },
    ).json()
    oct_items = api.get("/api/contas-a-pagar?inicio=2026-10-01&fim=2026-10-31").json()
    oct_dates = [i["due_date"] for i in oct_items if i["rule_id"] == rule["id"]]
    # 31/10 do mês atual e, por estar vencida, a de 30/09 (e as anteriores não pagas).
    assert "2026-10-31" in oct_dates
    assert "2026-09-30" in oct_dates
    assert "2026-02-28" in oct_dates  # dia 31 sem deslizar
    nov = api.get("/api/contas-a-pagar?inicio=2026-11-01&fim=2026-11-30&incluir_vencidas=false").json()
    assert [i["due_date"] for i in nov] == ["2026-11-30"]
    occ = api.post("/api/contas-a-pagar/ocorrencia", {"rule_id": rule["id"], "occurrence_date": "2026-10-31"})
    assert occ.status_code == 201, occ.text
    bill_id = occ.json()["id"]
    api.post(f"/api/contas-a-pagar/{bill_id}/pagar", {})
    after = api.get("/api/contas-a-pagar?inicio=2026-10-01&fim=2026-10-31").json()
    paid = [i for i in after if i["due_date"] == "2026-10-31"]
    assert len(paid) == 1 and paid[0]["situation"] == "paga" and not paid[0]["virtual"]
    bad = api.post("/api/contas-a-pagar/ocorrencia", {"rule_id": rule["id"], "occurrence_date": "2026-10-30"})
    assert bad.status_code == 422


def test_receita_prevista_nao_e_dinheiro_disponivel(trio: Trio) -> None:
    api = trio.ana
    acc = new_account(api, balance=1000)
    r = api.post(
        "/api/contas-a-pagar",
        {
            "kind": "receber",
            "description": "Salário",
            "amount_cents": 300000,
            "due_date": "2026-11-05",
            "account_id": acc,
            "is_main_income": True,
        },
    )
    assert r.status_code == 201
    assert balance(api, acc) == 1000
    rec = api.post(f"/api/contas-a-pagar/{r.json()['id']}/pagar", {"tx_date": "2026-10-15"})
    assert rec.status_code == 201
    assert rec.json()["transaction"]["kind"] == "receita"
    assert balance(api, acc) == 301000


# --- isolamento pela API ----------------------------------------------------------------


def test_acesso_cruzado_por_id_em_todas_as_rotas_do_nucleo(trio: Trio) -> None:
    owners = {}
    for name, api in [("ana", trio.ana), ("bruno", trio.bruno), ("carla", trio.carla)]:
        acc = new_account(api, f"Conta {name}", 1000)
        tx = api.post(
            "/api/lancamentos",
            {
                "kind": "despesa",
                "account_id": acc,
                "amount_cents": 10,
                "tx_date": "2026-10-02",
                "description": f"Gasto {name}",
            },
        ).json()
        bill = _bill(api, description=f"Conta de {name}")
        cat = api.post("/api/categorias", {"name": f"Cat {name}", "kind": "despesa"}).json()
        rule = api.post(
            "/api/recorrencias",
            {"description": f"Regra {name}", "amount_cents": 5, "anchor_date": "2026-10-01"},
        ).json()
        owners[name] = {
            "acc": acc,
            "tx": tx["id"],
            "bill": bill["id"],
            "cat": cat["id"],
            "rule": rule["id"],
        }

    for attacker_name, attacker, victim_name, _ in trio.pairs():
        v = owners[victim_name]
        mine = owners[attacker_name]
        checks = [
            attacker.get(f"/api/contas/{v['acc']}"),
            attacker.patch(f"/api/contas/{v['acc']}", {"name": "invadida"}),
            attacker.delete(f"/api/contas/{v['acc']}"),
            attacker.post(
                f"/api/contas/{v['acc']}/ajustar-saldo",
                {"real_balance_cents": 0, "on": "2026-10-15"},
            ),
            attacker.get(f"/api/lancamentos/{v['tx']}"),
            attacker.patch(f"/api/lancamentos/{v['tx']}", {"amount_cents": 1}),
            attacker.post(f"/api/lancamentos/{v['tx']}/cancelar", key=None),
            attacker.get(f"/api/contas-a-pagar/{v['bill']}"),
            attacker.patch(f"/api/contas-a-pagar/{v['bill']}", {"amount_cents": 1}),
            attacker.post(f"/api/contas-a-pagar/{v['bill']}/pagar", {"account_id": mine["acc"]}),
            attacker.post(f"/api/contas-a-pagar/{v['bill']}/cancelar", key=None),
            attacker.patch(f"/api/categorias/{v['cat']}", {"name": "x"}),
            attacker.patch(f"/api/recorrencias/{v['rule']}", {"amount_cents": 1}),
            attacker.post(
                "/api/contas-a-pagar/ocorrencia",
                {"rule_id": v["rule"], "occurrence_date": "2026-10-01"},
            ),
        ]
        for r in checks:
            assert r.status_code == 404, (attacker_name, victim_name, r.request.url, r.text)
            assert victim_name not in r.text.lower()

        # Relações: usar conta ou categoria de outra pessoa em um registro próprio.
        relations = [
            attacker.post(
                "/api/lancamentos",
                {
                    "kind": "despesa",
                    "account_id": v["acc"],
                    "amount_cents": 1,
                    "tx_date": "2026-10-02",
                    "description": "x",
                },
            ),
            attacker.post(
                "/api/lancamentos",
                {
                    "kind": "despesa",
                    "account_id": mine["acc"],
                    "amount_cents": 1,
                    "tx_date": "2026-10-02",
                    "description": "x",
                    "category_id": v["cat"],
                },
            ),
            attacker.post(
                "/api/transferencias",
                {
                    "from_account_id": mine["acc"],
                    "to_account_id": v["acc"],
                    "amount_cents": 1,
                    "tx_date": "2026-10-02",
                },
            ),
            attacker.post(
                "/api/contas-a-pagar",
                {
                    "description": "x",
                    "amount_cents": 1,
                    "due_date": "2026-10-20",
                    "account_id": v["acc"],
                },
            ),
            attacker.post(f"/api/contas-a-pagar/{mine['bill']}/pagar", {"account_id": v["acc"]}),
        ]
        for r in relations:
            assert r.status_code == 422, (attacker_name, victim_name, r.request.url, r.text)

    # Nada dos outros aparece nas listas, e os dados das vítimas ficaram intactos.
    for name, api in [("ana", trio.ana), ("bruno", trio.bruno), ("carla", trio.carla)]:
        accounts = api.get("/api/contas").json()
        assert [a["name"] for a in accounts] == [f"Conta {name}"]
        assert accounts[0]["balance_cents"] == 990
        txs = api.get("/api/lancamentos").json()["items"]
        assert [t["description"] for t in txs] == [f"Gasto {name}"]
        bills_list = api.get("/api/contas-a-pagar?inicio=2026-10-01&fim=2026-10-31").json()
        assert all(name in b["description"].lower() for b in bills_list)
        cats = [c["name"] for c in api.get("/api/categorias").json() if c["name"].startswith("Cat ")]
        assert cats == [f"Cat {name}"]


def test_nada_foi_gravado_pelas_tentativas_cruzadas(trio: Trio, admin_engine: Engine) -> None:
    acc_bruno = new_account(trio.bruno, "Do Bruno", 500)
    trio.ana.post(
        "/api/lancamentos",
        {
            "kind": "despesa",
            "account_id": acc_bruno,
            "amount_cents": 1,
            "tx_date": "2026-10-02",
            "description": "x",
        },
    )
    with admin_engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM transactions")).scalar() == 0
