"""Acompanhamento do dia a dia: teto por categoria, gastos frequentes, calendário de
contas, resumo do mês e contas anuais. Tudo calculado na hora a partir dos registros;
só o valor do teto é gravado."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any
from uuid import UUID

from app.api.errors import ApiError, not_found
from app.domain.dates import YearMonth, format_br_date, monthly_occurrence
from app.domain.insights import annual_saving, budget_status, suggest_limit
from app.services import bills as bills_service
from app.services import cards as cards_service
from app.services import debts as debts_service
from app.services.base import Ctx
from app.services.ledger import check_category
from app.services.reports import category_flows, money_text

HISTORY_MONTHS = 6
FREQUENT_DAYS = 90
FREQUENT_MAX = 4

MONTH_NAMES = [
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
]  # fmt: skip


def month_name(m: YearMonth) -> str:
    return f"{MONTH_NAMES[m.month - 1]} de {m.year}"


# --- teto por categoria ------------------------------------------------------------


def _monthly_history(ctx: Ctx, months: int) -> list[dict[str | None, int]]:
    current = YearMonth.of(ctx.today)
    out = []
    for k in range(months, 0, -1):
        m = current.shift(-k)
        out.append(category_flows(ctx, m.first_day, m.last_day)["spending"])
    return out


def list_budgets(ctx: Ctx) -> dict[str, Any]:
    month = YearMonth.of(ctx.today)
    spent = category_flows(ctx, month.first_day, month.last_day)["spending"]
    history = _monthly_history(ctx, HISTORY_MONTHS)
    limits = {
        str(r.category_id): int(r.monthly_limit_cents)
        for r in ctx.all("SELECT category_id, monthly_limit_cents FROM category_budgets WHERE owner_id=:o")
    }
    items = []
    for c in ctx.all(
        "SELECT id, name FROM categories WHERE owner_id=:o AND kind='despesa' AND NOT is_archived "
        "ORDER BY position, name"
    ):
        cid = str(c.id)
        used = spent.get(cid, 0)
        limit = limits.get(cid)
        status = budget_status(limit, used) if limit else None
        items.append(
            {
                "category_id": cid,
                "category_name": c.name,
                "limit_cents": limit,
                "spent_cents": used,
                "percent": status.percent if status else None,
                "level": status.level.value if status else None,
                "left_cents": status.left_cents if status else None,
                "suggested_cents": suggest_limit([h.get(cid, 0) for h in history]),
            }
        )
    items.sort(key=lambda i: (i["limit_cents"] is None, -(i["percent"] or 0), -i["spent_cents"]))
    return {
        "month": str(month),
        "items": items,
        "notes": [
            "O gasto do mês conta despesas, compras no cartão (na data da compra) e parcelas de carnê pagas, "
            "menos reembolsos e estornos.",
            "Sugestão: a mediana dos seus gastos nos últimos 6 meses completos, arredondada para cima. "
            "Aparece quando houver pelo menos 3 meses com gasto na categoria.",
        ],
    }


def budget_alerts(ctx: Ctx) -> list[dict[str, Any]]:
    """Categorias perto do teto (80% ou mais) ou acima dele, para o Início."""
    return [
        {k: i[k] for k in ("category_id", "category_name", "limit_cents", "spent_cents", "percent", "level")}
        for i in list_budgets(ctx)["items"]
        if i["level"] in ("perto", "passou")
    ]


def set_budget(ctx: Ctx, category_id: UUID, limit_cents: int) -> dict[str, Any]:
    if ctx.one("SELECT 1 FROM categories WHERE id=:id AND owner_id=:o", id=category_id) is None:
        raise not_found("Categoria")
    check_category(ctx, category_id, "despesa")
    ctx.exec(
        """INSERT INTO category_budgets (owner_id, category_id, monthly_limit_cents)
           VALUES (:o, :c, :v)
           ON CONFLICT (owner_id, category_id)
           DO UPDATE SET monthly_limit_cents = EXCLUDED.monthly_limit_cents, updated_at = now()""",
        c=category_id,
        v=limit_cents,
    )
    return next(i for i in list_budgets(ctx)["items"] if i["category_id"] == str(category_id))


def delete_budget(ctx: Ctx, category_id: UUID) -> None:
    if (
        ctx.exec("DELETE FROM category_budgets WHERE owner_id=:o AND category_id=:c", c=category_id).rowcount
        == 0
    ):
        raise not_found("Teto")


# --- gastos frequentes (atalhos) ------------------------------------------------------


def frequent_expenses(ctx: Ctx) -> list[dict[str, Any]]:
    """Despesas repetidas nos últimos 90 dias (mesma descrição e categoria, ao menos 2
    vezes), com o último valor e a última conta usados. Servem de atalho: abrem o
    formulário já preenchido; nada é gravado sem a pessoa confirmar."""
    rows = ctx.all(
        """SELECT * FROM (
             SELECT t.description, t.category_id, c.name AS category_name, t.amount_cents,
                    t.account_id, t.tx_date,
                    count(*) OVER w AS times,
                    row_number() OVER (PARTITION BY lower(btrim(t.description)), t.category_id
                                       ORDER BY t.tx_date DESC, t.created_at DESC) AS rn
             FROM transactions t
             JOIN accounts a ON a.id = t.account_id AND a.owner_id = t.owner_id AND a.is_active
             LEFT JOIN categories c ON c.id = t.category_id AND c.owner_id = t.owner_id
             WHERE t.owner_id = :o AND t.kind = 'despesa' AND t.status = 'ativo' AND t.bill_id IS NULL
               AND t.tx_date >= :since
             WINDOW w AS (PARTITION BY lower(btrim(t.description)), t.category_id)
           ) x
           WHERE rn = 1 AND times >= 2
           ORDER BY times DESC, tx_date DESC
           LIMIT :n""",
        since=ctx.today - timedelta(days=FREQUENT_DAYS),
        n=FREQUENT_MAX,
    )
    return [
        {
            "description": r.description,
            "category_id": str(r.category_id) if r.category_id else None,
            "category_name": r.category_name,
            "amount_cents": int(r.amount_cents),
            "account_id": str(r.account_id),
            "times": int(r.times),
        }
        for r in rows
    ]


# --- calendário de contas ------------------------------------------------------------


def calendar(ctx: Ctx, month: YearMonth) -> dict[str, Any]:
    """Tudo o que vence no mês, dia a dia: contas a pagar e a receber (pagas ou não),
    faturas e próximas parcelas de dívidas."""
    first, last = month.first_day, month.last_day
    items: list[dict[str, Any]] = []
    for kind in ("pagar", "receber"):
        for b in bills_service.list_bills(ctx, kind=kind, start=first, end=last, include_overdue=False):
            if b["situation"] == "cancelada":
                continue
            items.append(
                {
                    "date": b["due_date"],
                    "kind": kind,
                    "source": "conta",
                    "id": b["id"],
                    "rule_id": b["rule_id"],
                    "virtual": b["virtual"],
                    "description": bills_service.bill_title(b),
                    "amount_cents": b["amount_cents"],
                    "situation": b["situation"],
                }
            )
    for card in ctx.all("SELECT * FROM cards WHERE owner_id=:o"):
        for inv in cards_service.invoices(ctx, card):
            if first <= inv.due_date <= last and inv.total.cents > 0:
                items.append(
                    {
                        "date": inv.due_date,
                        "kind": "pagar",
                        "source": "fatura",
                        "id": str(card.id),
                        "description": f"Fatura {card.name}",
                        "amount_cents": inv.total.cents,
                        "situation": inv.status.value,
                    }
                )
    for d in debts_service.list_debts(ctx, include_closed=False):
        if d["is_card_channel"] or not d["installment_amount_cents"] or d["next_due_date"] is None:
            continue
        remaining = d["installments_remaining"] if d["installments_remaining"] is not None else 600
        for k in range(remaining):
            due = monthly_occurrence(d["next_due_date"], k)
            if due > last:
                break
            if due >= first:
                items.append(
                    {
                        "date": due,
                        "kind": "pagar",
                        "source": "divida",
                        "id": str(d["id"]),
                        "description": f"Parcela: {d['creditor']}",
                        "amount_cents": d["installment_amount_cents"],
                        "situation": "vencida" if due < ctx.today else "pendente",
                    }
                )
    items.sort(key=lambda i: (i["date"], i["kind"] != "receber", i["description"]))
    return {
        "month": str(month),
        "first_day": first,
        "last_day": last,
        "today": ctx.today,
        "items": items,
        "to_pay_cents": sum(i["amount_cents"] for i in items if i["kind"] == "pagar"),
        "to_receive_cents": sum(i["amount_cents"] for i in items if i["kind"] == "receber"),
    }


# --- resumo do mês em linguagem simples ---------------------------------------------------


def _biggest_expense(ctx: Ctx, first: date, last: date) -> Any:
    return ctx.one(
        """SELECT description, amount_cents, on_date FROM (
             SELECT description, amount_cents, tx_date AS on_date, created_at FROM transactions
              WHERE owner_id=:o AND kind='despesa' AND status='ativo' AND tx_date BETWEEN :s AND :e
             UNION ALL
             SELECT description, total_cents, purchase_date, created_at FROM card_purchases
              WHERE owner_id=:o AND kind='compra' AND status='ativa' AND purchase_date BETWEEN :s AND :e
           ) x ORDER BY amount_cents DESC, on_date, created_at LIMIT 1""",
        s=first,
        e=last,
    )


def month_summary(ctx: Ctx, month: YearMonth) -> dict[str, Any]:
    current = YearMonth.of(ctx.today)
    if month > current:
        raise ApiError(422, "Esse mês ainda não começou.", {"mes": "Mês futuro."})
    partial = month == current
    flows = category_flows(ctx, month.first_day, month.last_day)
    names = flows["names"]
    income = sum(v for v in flows["income"].values())
    spending = sum(v for v in flows["spending"].values())
    top = sorted(((names[k], v) for k, v in flows["spending"].items() if v > 0), key=lambda x: -x[1])[:3]

    lines: list[str] = []
    when = f"Até agora, em {month_name(month)}," if partial else f"Em {month_name(month)},"
    if income == 0 and spending == 0:
        lines.append(f"{when} não há receitas nem gastos registrados.")
        return {"month": str(month), "partial": partial, "lines": lines}
    lines.append(f"{when} você recebeu {money_text(income)} e gastou {money_text(spending)}.")
    diff = income - spending
    if diff >= 0:
        lines.append(f"Sobrou {money_text(diff)}.")
    else:
        lines.append(f"Gastou {money_text(-diff)} a mais do que recebeu.")
    if top:
        parts = ", ".join(f"{n} ({money_text(v)})" for n, v in top)
        lines.append(f"Onde mais gastou: {parts}.")
    prev = month.shift(-1)
    prev_spending = sum(v for v in category_flows(ctx, prev.first_day, prev.last_day)["spending"].values())
    if prev_spending > 0 and not partial:
        change = (spending - prev_spending) * 100 // prev_spending
        if change > 0:
            lines.append(f"Gastou {change}% a mais do que em {MONTH_NAMES[prev.month - 1]}.")
        elif change < 0:
            lines.append(f"Gastou {-change}% a menos do que em {MONTH_NAMES[prev.month - 1]}.")
        else:
            lines.append(f"Gastou o mesmo que em {MONTH_NAMES[prev.month - 1]}.")
    big = _biggest_expense(ctx, month.first_day, month.last_day)
    if big is not None:
        lines.append(
            f"Maior gasto: {big.description}, {money_text(int(big.amount_cents))} em {format_br_date(big.on_date)}."
        )
    if partial:
        over = [a["category_name"] for a in budget_alerts(ctx) if a["level"] == "passou"]
        if over:
            lines.append("Passou do teto em: " + ", ".join(over) + ".")
    return {"month": str(month), "partial": partial, "lines": lines}


# --- contas anuais ----------------------------------------------------------------------


def annual_bills(ctx: Ctx) -> list[dict[str, Any]]:
    """Contas que se repetem todo ano: quanto guardar por mês até o próximo vencimento
    que ainda não foi pago."""
    out = []
    for rule in ctx.all(
        "SELECT * FROM recurring_rules WHERE owner_id=:o AND kind='pagar' AND frequency='anual' "
        "AND is_active AND (end_date IS NULL OR end_date >= :d)",
        d=ctx.today,
    ):
        # Ocorrências já resolvidas (pagas ou canceladas) não são o "próximo vencimento".
        settled = {
            b["occurrence_date"]
            for b in bills_service.rule_bills(ctx, rule.id)
            if b["situation"] in ("paga", "cancelada")
        }
        start = YearMonth.of(ctx.today).first_day
        due = next(
            (
                d
                for d in bills_service.occurrences(rule, start, start + timedelta(days=800))
                if d not in settled
            ),
            None,
        )
        if due is None:
            continue
        s = annual_saving(rule.amount_cents, ctx.today, due)
        out.append(
            {
                "description": rule.description,
                "amount_cents": rule.amount_cents,
                "next_due": due,
                "months_left": s.months_left,
                "per_month_cents": s.per_month_cents,
                "steady_cents": s.steady_cents,
            }
        )
    out.sort(key=lambda i: i["next_due"])
    return out
