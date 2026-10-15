"""Resumo da tela inicial e relatórios. As definições estão em docs/DECISOES.md, seção 1.

Tudo é calculado na hora a partir dos registros de origem; nada é gravado.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from typing import Any

from app.domain.dates import YearMonth
from app.domain.debts import DebtMovement, debt_balance
from app.domain.money import Money, format_brl
from app.services import bills as bills_service
from app.services import cards as cards_service
from app.services import debts as debts_service
from app.services import investments as inv_service
from app.services.base import Ctx
from app.services.ledger import BALANCE_SQL

COMMIT_DAYS = 30


# --- blocos de cálculo ------------------------------------------------------------


def accounts_balances(
    ctx: Ctx, until: date | None = None, *, at_start_of: date | None = None
) -> dict[str, int]:
    """Saldos no fim do dia ``until`` ou no começo do dia ``at_start_of``."""
    if at_start_of is not None:
        tx_until, on = at_start_of - timedelta(days=1), at_start_of
    else:
        tx_until = on = until or date.max
    rows = ctx.all(
        f"SELECT a.daily_use, a.is_active, a.initial_balance_date, {BALANCE_SQL} AS bal "  # noqa: S608
        "FROM accounts a WHERE a.owner_id=:o",
        until=tx_until,
    )
    total = sum(r.bal for r in rows if r.initial_balance_date <= on)
    available = sum(r.bal for r in rows if r.daily_use and r.is_active and r.initial_balance_date <= on)
    return {"total": int(total), "available": int(available)}


def income_and_spending(ctx: Ctx, start: date, end: date) -> dict[str, Any]:
    """Recebi e gastei no período, por categoria (cada gasto contado uma vez)."""
    income: dict[str, int] = defaultdict(int)
    spending: dict[str, int] = defaultdict(int)
    for r in ctx.all(
        """SELECT t.kind, coalesce(c.name, 'Sem categoria') AS cat, sum(t.amount_cents)::bigint AS v
           FROM transactions t LEFT JOIN categories c ON c.id=t.category_id AND c.owner_id=t.owner_id
           WHERE t.owner_id=:o AND t.status='ativo' AND t.kind IN ('receita','despesa','reembolso')
             AND t.tx_date BETWEEN :s AND :e GROUP BY 1, 2""",
        s=start,
        e=end,
    ):
        if r.kind == "receita":
            income[r.cat] += r.v
        elif r.kind == "despesa":
            spending[r.cat] += r.v
        else:  # reembolso reduz a categoria do gasto
            spending[r.cat] -= r.v
    for r in ctx.all(
        """SELECT coalesce(c.name, 'Sem categoria') AS cat, p.kind,
                  sum(CASE WHEN p.kind='parcelamento_fatura'
                           THEN p.total_cents - p.financed_principal_cents
                           ELSE p.total_cents END)::bigint AS v
           FROM card_purchases p LEFT JOIN categories c ON c.id=p.category_id AND c.owner_id=p.owner_id
           WHERE p.owner_id=:o AND p.status='ativa' AND p.purchase_date BETWEEN :s AND :e
           GROUP BY 1, 2""",
        s=start,
        e=end,
    ):
        if r.v:
            spending[r.cat] += r.v
    for r in ctx.all(
        """SELECT coalesce(c.name, 'Sem categoria') AS cat, sum(k.amount_cents)::bigint AS v
           FROM card_credits k
           JOIN card_purchases p ON p.id=k.purchase_id AND p.owner_id=k.owner_id
           LEFT JOIN categories c ON c.id=p.category_id AND c.owner_id=p.owner_id
           WHERE k.owner_id=:o AND k.kind='estorno' AND p.status='ativa'
             AND k.credit_date BETWEEN :s AND :e GROUP BY 1""",
        s=start,
        e=end,
    ):
        spending[r.cat] -= r.v
    inc = sorted(((k, v) for k, v in income.items() if v), key=lambda x: -x[1])
    spe = sorted(((k, v) for k, v in spending.items() if v), key=lambda x: -x[1])
    return {
        "income_cents": sum(v for _, v in inc),
        "spending_cents": sum(v for _, v in spe),
        "income_by_category": [{"category": k, "cents": v} for k, v in inc],
        "spending_by_category": [{"category": k, "cents": v} for k, v in spe],
    }


def obligations(ctx: Ctx, until: date) -> list[dict[str, Any]]:
    """O que ainda preciso pagar até a data: contas (inclusive vencidas de antes),
    faturas com vencimento até a data e parcelas de dívidas."""
    items: list[dict[str, Any]] = []
    for b in bills_service.list_bills(ctx, kind="pagar", start=ctx.today, end=until, include_overdue=True):
        if b["situation"] in ("paga", "cancelada") or b["remaining_cents"] <= 0:
            continue
        items.append(
            {
                "source": "conta",
                "id": b["id"],
                "rule_id": b["rule_id"],
                "description": b["description"],
                "due_date": b["due_date"],
                "amount_cents": b["remaining_cents"],
                "overdue": b["situation"] == "vencida",
                "virtual": b["virtual"],
            }
        )
    for card in ctx.all("SELECT * FROM cards WHERE owner_id=:o"):
        for inv in cards_service.invoices(ctx, card):
            if inv.remaining.cents > 0 and inv.due_date <= until:
                items.append(
                    {
                        "source": "fatura",
                        "id": card.id,
                        "description": f"Fatura {card.name}",
                        "due_date": inv.due_date,
                        "amount_cents": inv.remaining.cents,
                        "overdue": inv.status.value == "vencida",
                        "invoice_status": inv.status.value,
                    }
                )
    for d in debts_service.next_installments(ctx, until):
        items.append(
            {
                "source": "divida",
                "id": d["debt_id"],
                "description": f"Parcela: {d['creditor']}",
                "due_date": d["due_date"],
                "amount_cents": d["amount_cents"],
                "overdue": d["overdue"],
            }
        )
    items.sort(key=lambda x: (x["due_date"], x["description"]))
    return items


def debts_total(ctx: Ctx) -> dict[str, int]:
    direct = sum(
        d["balance_cents"]
        for d in debts_service.list_debts(ctx, include_closed=False)
        if not d["is_card_channel"]
    )
    cards_outstanding = 0
    for card in ctx.all("SELECT * FROM cards WHERE owner_id=:o"):
        cards_outstanding += sum(i.remaining.cents for i in cards_service.invoices(ctx, card))
    return {"debts": direct, "cards": cards_outstanding, "total": direct + cards_outstanding}


def _next_income(ctx: Ctx) -> date:
    """F11: próxima receita principal prevista; sem ela, 30 dias."""
    horizon = ctx.today + timedelta(days=62)
    upcoming = [
        b
        for b in bills_service.list_bills(
            ctx, kind="receber", start=ctx.today, end=horizon, include_overdue=False
        )
        if b["is_main_income"]
        and b["situation"] in ("pendente", "parcialmente_paga")
        and b["due_date"] >= ctx.today
    ]
    if upcoming:
        first: date = min(b["due_date"] for b in upcoming)
        return first
    return ctx.today + timedelta(days=COMMIT_DAYS)


# --- tela inicial -------------------------------------------------------------------


def home(ctx: Ctx) -> dict[str, Any]:
    month = YearMonth.of(ctx.today)
    bal = accounts_balances(ctx)
    flows = income_and_spending(ctx, month.first_day, month.last_day)
    to_pay_month = obligations(ctx, month.last_day)
    next_income = _next_income(ctx)
    committed_items = obligations(ctx, max(next_income, ctx.today))
    committed = sum(i["amount_cents"] for i in committed_items)
    debts = debts_total(ctx)
    inv = inv_service.overview(ctx)
    inv_value = sum(
        (i["current_value_cents"] if i["current_value_cents"] is not None else i["invested_cents"])
        for i in inv["items"]
        if i["is_active"]
    )
    free = bal["available"] - committed
    net_worth = bal["total"] + inv_value - debts["total"]
    overdue = [i for i in to_pay_month if i["overdue"]]

    if overdue:
        status = {
            "level": "atencao",
            "message": f"Você tem {len(overdue)} conta(s) vencida(s). Veja em Contas a pagar.",
        }
    elif free < 0:
        status = {
            "level": "atencao",
            "message": "O que vence até o próximo recebimento passa do dinheiro disponível.",
        }
    elif flows["spending_cents"] > flows["income_cents"] and flows["income_cents"] > 0:
        status = {"level": "cuidado", "message": "Neste mês você gastou mais do que recebeu."}
    else:
        status = {"level": "ok", "message": "Suas contas do mês estão em dia."}

    return {
        "today": ctx.today,
        "month": str(month),
        "available_cents": bal["available"],
        "accounts_total_cents": bal["total"],
        "income_month_cents": flows["income_cents"],
        "spending_month_cents": flows["spending_cents"],
        "to_pay_month_cents": sum(i["amount_cents"] for i in to_pay_month),
        "committed_cents": committed,
        "committed_until": max(next_income, ctx.today),
        "free_cents": free,
        "debts_total_cents": debts["total"],
        "debts_direct_cents": debts["debts"],
        "cards_outstanding_cents": debts["cards"],
        "investments_value_cents": inv_value,
        "investments_missing_value": inv["totals"]["missing_value_count"],
        "net_worth_cents": net_worth,
        "upcoming": committed_items[:8],
        "overdue_count": len(overdue),
        "status": status,
        "explanations": {
            "available": "Soma das contas do dia a dia. Não inclui limite de cartão nem investimentos.",
            "free": f"Dinheiro disponível menos o que vence até {max(next_income, ctx.today).strftime('%d/%m/%Y')}. "
            "Receitas que ainda não caíram não entram.",
            "debts": "Saldo das dívidas mais o que falta pagar nas faturas dos cartões.",
            "net_worth": "Dinheiro em todas as contas + investimentos menos o que você deve.",
        },
    }


# --- relatórios ----------------------------------------------------------------------


def monthly(ctx: Ctx, month: YearMonth) -> dict[str, Any]:
    s, e = month.first_day, month.last_day
    flows = income_and_spending(ctx, s, e)
    cash = ctx.all(
        """SELECT kind, direction, sum(amount_cents)::bigint AS v FROM transactions
           WHERE owner_id=:o AND status='ativo' AND tx_date BETWEEN :s AND :e GROUP BY 1, 2""",
        s=s,
        e=e,
    )
    cash_in = sum(r.v for r in cash if r.direction == "entrada" and r.kind != "transferencia")
    cash_out = sum(r.v for r in cash if r.direction == "saida" and r.kind != "transferencia")
    planned = {}
    for kind in ("pagar", "receber"):
        items = [
            b
            for b in bills_service.list_bills(ctx, kind=kind, start=s, end=e, include_overdue=False)
            if b["situation"] != "cancelada"
        ]
        planned[kind] = {
            "planned_cents": sum(b["amount_cents"] for b in items),
            "done_cents": sum(b["paid_cents"] for b in items),
            "open_cents": sum(b["remaining_cents"] for b in items),
        }
    start_balance = accounts_balances(ctx, at_start_of=s)["total"]
    end_balance = accounts_balances(ctx, e)["total"]
    committed_pct = None
    if planned["receber"]["planned_cents"] or flows["income_cents"]:
        base = max(planned["receber"]["planned_cents"], flows["income_cents"])
        obligations_month = planned["pagar"]["planned_cents"] + sum(
            i["amount_cents"] for i in obligations(ctx, e) if i["source"] != "conta" and i["due_date"] >= s
        )
        committed_pct = obligations_month * 100 // base if base else None
    return {
        "month": str(month),
        "start": s,
        "end": e,
        **flows,
        "cash_in_cents": cash_in,
        "cash_out_cents": cash_out,
        "start_balance_cents": start_balance,
        "end_balance_cents": end_balance,
        "bills": planned,
        "income_committed_percent": committed_pct,
        "notes": [
            "Gastos com cartão entram no mês da compra; o pagamento da fatura não é contado de novo.",
            "Transferências entre suas contas não entram como receita nem como gasto.",
        ],
    }


def _card_outstanding_at(ctx: Ctx, on: date) -> int:
    v = ctx.scalar(
        """SELECT
             coalesce((SELECT sum(i.amount_cents) FROM card_installments i
                JOIN card_purchases p ON p.id=i.purchase_id AND p.owner_id=i.owner_id
                WHERE i.owner_id=:o AND i.status='ativa' AND p.purchase_date <= :d), 0)
           - coalesce((SELECT sum(amount_cents) FROM card_credits WHERE owner_id=:o AND credit_date <= :d), 0)
           - coalesce((SELECT sum(amount_cents) FROM transactions WHERE owner_id=:o
                AND kind='pagamento_fatura' AND status='ativo' AND tx_date <= :d), 0)""",
        d=on,
    )
    return max(int(v or 0), 0)


def _debts_at(ctx: Ctx, on: date) -> int:
    total = 0
    for d in ctx.all("SELECT * FROM debts WHERE owner_id=:o AND card_id IS NULL AND anchor_date <= :d", d=on):
        if d.status == "cancelada":
            continue
        moves = [
            DebtMovement(
                r.tx_date,
                "pagamento",
                Money(r.amount_cents),
                Money(r.debt_interest_cents) if r.debt_interest_cents is not None else None,
            )
            for r in ctx.all(
                "SELECT tx_date, amount_cents, debt_interest_cents FROM transactions WHERE owner_id=:o "
                "AND debt_id=:id AND kind='pagamento_divida' AND status='ativo' AND tx_date <= :d",
                id=d.id,
                d=on,
            )
        ] + [
            DebtMovement(r.event_date, r.kind, Money(r.amount_cents))
            for r in ctx.all(
                "SELECT event_date, kind, amount_cents FROM debt_events WHERE owner_id=:o AND debt_id=:id "
                "AND status='ativo' AND event_date <= :d",
                id=d.id,
                d=on,
            )
        ]
        total += debt_balance(Money(d.anchor_balance_cents), d.anchor_date, moves).balance.cents
    return total


def series(ctx: Ctx, months: int) -> dict[str, Any]:
    """Evolução mês a mês (até o fim de cada mês, ou até hoje no mês atual)."""
    current = YearMonth.of(ctx.today)
    out = []
    for k in range(months - 1, -1, -1):
        m = current.shift(-k)
        end = min(m.last_day, ctx.today)
        flows = income_and_spending(ctx, m.first_day, end)
        balance = accounts_balances(ctx, end)["total"]
        debts = _debts_at(ctx, end) + _card_outstanding_at(ctx, end)
        investments = inv_service.value_at(ctx, end)
        out.append(
            {
                "month": str(m),
                "income_cents": flows["income_cents"],
                "spending_cents": flows["spending_cents"],
                "balance_cents": balance,
                "debts_cents": debts,
                "investments_cents": investments,
                "net_worth_cents": balance + investments - debts,
            }
        )
    return {
        "months": out,
        "notes": [
            "Investimentos usam o último valor informado até o fim de cada mês; sem valor informado, "
            "entram pelo valor aportado.",
        ],
    }


def money_text(cents: int) -> str:
    return format_brl(Money(cents))
