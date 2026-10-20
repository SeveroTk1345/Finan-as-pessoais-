"""Simulador "Posso comprar?" (especificação original, item 4.9).

Projeta mês a mês o dinheiro disponível a partir do que já está registrado e mostra
o efeito de uma compra. Só lê dados: nada é gravado. Não declara uma compra segura só
porque a parcela cabe: considera todas as obrigações previstas no período.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any
from uuid import UUID

from app.api.errors import ApiError
from app.domain.cards import CardCycle, plan_installments
from app.domain.dates import YearMonth, monthly_occurrence
from app.domain.money import Money, format_brl
from app.services import bills as bills_service
from app.services import cards as cards_service
from app.services import debts as debts_service
from app.services.base import Ctx
from app.services.reports import accounts_balances


def _baseline(ctx: Ctx, months: list[YearMonth]) -> tuple[dict[YearMonth, int], dict[YearMonth, int]]:
    """Entradas e saídas previstas por mês (só o que ainda não aconteceu)."""
    first, last = months[0], months[-1]
    inflow: dict[YearMonth, int] = defaultdict(int)
    outflow: dict[YearMonth, int] = defaultdict(int)

    def bucket(d: date) -> YearMonth:
        # Vencidos e pendentes contam no mês atual: ainda precisam ser pagos.
        return first if d < first.first_day else YearMonth.of(d)

    for kind, target in (("receber", inflow), ("pagar", outflow)):
        for b in bills_service.list_bills(
            ctx, kind=kind, start=ctx.today, end=last.last_day, include_overdue=(kind == "pagar")
        ):
            if b["remaining_cents"] > 0 and b["situation"] != "cancelada":
                target[bucket(b["due_date"])] += b["remaining_cents"]

    for card in ctx.all("SELECT * FROM cards WHERE owner_id=:o"):
        for inv in cards_service.invoices(ctx, card):
            if inv.remaining.cents > 0 and inv.due_date <= last.last_day:
                outflow[bucket(inv.due_date)] += inv.remaining.cents

    for d in debts_service.list_debts(ctx, include_closed=False):
        if d["is_card_channel"] or not d["installment_amount_cents"] or d["next_due_date"] is None:
            continue
        remaining_balance = d["balance_cents"]
        count = d["installments_remaining"] if d["installments_remaining"] is not None else 600
        for k in range(count):
            due = monthly_occurrence(d["next_due_date"], k)
            if due > last.last_day or remaining_balance <= 0:
                break
            value = min(d["installment_amount_cents"], remaining_balance)
            outflow[bucket(due)] += value
            remaining_balance -= value
    return inflow, outflow


def _project(
    start: int,
    months: list[YearMonth],
    inflow: dict[YearMonth, int],
    outflow: dict[YearMonth, int],
    extra: dict[YearMonth, int],
) -> list[int]:
    out = []
    balance = start
    for m in months:
        balance += inflow.get(m, 0) - outflow.get(m, 0) - extra.get(m, 0)
        out.append(balance)
    return out


def simulate_purchase(ctx: Ctx, data: dict[str, Any]) -> dict[str, Any]:
    amount = data["amount_cents"]
    months_ahead = data.get("months", 6)
    when = data.get("purchase_date") or ctx.today
    if when < ctx.today:
        raise ApiError(
            422, "Para simular, use a data de hoje ou uma data futura.", {"purchase_date": "Data no passado."}
        )
    months = [YearMonth.of(ctx.today).shift(i) for i in range(months_ahead)]
    if YearMonth.of(when) > months[-1]:
        raise ApiError(
            422, "A data da compra está fora do período simulado.", {"purchase_date": "Data muito distante."}
        )

    available = accounts_balances(ctx)["available"]
    inflow, outflow = _baseline(ctx, months)

    extra: dict[YearMonth, int] = defaultdict(int)
    limit_effect = None
    warnings: list[str] = []
    method = data["method"]
    if method == "conta":
        extra[YearMonth.of(when)] += amount
        monthly_extra = amount
        installments = [{"due_date": when, "amount_cents": amount}]
    else:
        card_id: UUID | None = data.get("card_id")
        if card_id is None:
            raise ApiError(422, "Escolha o cartão.", {"card_id": "Escolha o cartão."})
        card = ctx.require("cards", card_id, "Cartão")
        summary = cards_service.card_summary(ctx, card)
        count = data.get("installments_count", 1)
        plan = plan_installments(
            CardCycle(card.closing_day, card.due_day, card.closing_day_goes_next), when, Money(amount), count
        )
        installments = [{"due_date": p.invoice_due_date, "amount_cents": p.amount.cents} for p in plan]
        for p in plan:
            if p.invoice_due_date <= months[-1].last_day:
                extra[YearMonth.of(p.invoice_due_date)] += p.amount.cents
        monthly_extra = plan[-1].amount.cents if count > 1 else amount
        limit_after = summary["limit_available_cents"] - amount
        limit_effect = {
            "card_name": card.name,
            "available_before_cents": summary["limit_available_cents"],
            "available_after_cents": limit_after,
        }
        if limit_after < 0:
            warnings.append(f"O limite do cartão não é suficiente: faltam {format_brl(Money(-limit_after))}.")
        if plan[-1].invoice_due_date > months[-1].last_day:
            warnings.append("Algumas parcelas vencem depois do período simulado.")

    base = _project(available, months, inflow, outflow, {})
    with_purchase = _project(available, months, inflow, outflow, extra)
    risky = [str(m) for m, v in zip(months, with_purchase, strict=True) if v < 0]
    newly_risky = [str(m) for m, b, v in zip(months, base, with_purchase, strict=True) if v < 0 <= b]

    reserve_row = ctx.one(
        """SELECT coalesce(sum(CASE WHEN c.direction='deposito' THEN c.amount_cents ELSE -c.amount_cents END),0)
                  ::bigint AS v
           FROM goal_contributions c JOIN goals g ON g.id=c.goal_id AND g.owner_id=c.owner_id
           WHERE c.owner_id=:o AND g.kind='reserva_emergencia' AND g.is_active"""
    )
    reserve = int(reserve_row.v) if reserve_row else 0
    worst = min(with_purchase)
    reserve_needed = -worst if worst < 0 else 0

    # Esperar: primeiro mês (a partir do próximo) em que comprar à vista não deixa
    # nenhum mês seguinte negativo.
    wait_month = None
    for i in range(1, len(months)):
        projected = _project(available, months, inflow, outflow, {months[i]: amount})
        if all(v >= 0 for v in projected):
            wait_month = str(months[i])
            break

    if risky:
        verdict = {
            "level": "atencao",
            "message": f"Com essa compra, o dinheiro previsto fica negativo em {len(risky)} mês(es): "
            + ", ".join(risky)
            + ".",
        }
    elif worst < monthly_extra:
        verdict = {
            "level": "cuidado",
            "message": "A compra cabe, mas o dinheiro previsto fica apertado em algum mês. "
            "Qualquer gasto não registrado pode faltar.",
        }
    else:
        verdict = {
            "level": "ok",
            "message": f"O dinheiro previsto não fica negativo nos próximos {months_ahead} meses.",
        }
    # Limite insuficiente: o cartão recusaria a compra, então nunca "cabe" (F-SIM-4).
    if limit_effect is not None and limit_effect["available_after_cents"] < 0:
        verdict = {
            "level": "atencao",
            "message": "O limite disponível do cartão não comporta essa compra. "
            + (verdict["message"] if verdict["level"] == "atencao" else ""),
        }
        verdict["message"] = verdict["message"].strip()

    return {
        "available_now_cents": available,
        "available_after_cents": available - (amount if method == "conta" and when == ctx.today else 0),
        "monthly_extra_cents": monthly_extra,
        "installments": installments,
        "months": [
            {
                "month": str(m),
                "income_cents": inflow.get(m, 0),
                "obligations_cents": outflow.get(m, 0),
                "purchase_cents": extra.get(m, 0),
                "balance_without_cents": b,
                "balance_with_cents": w,
            }
            for m, b, w in zip(months, base, with_purchase, strict=True)
        ],
        "risky_months": risky,
        "newly_risky_months": newly_risky,
        "limit": limit_effect,
        "reserve": {
            "saved_cents": reserve,
            "needed_cents": reserve_needed,
            "covers": reserve_needed == 0 or reserve >= reserve_needed,
        },
        "compare": {
            "buy_now_min_cents": worst,
            "dont_buy_min_cents": min(base),
            "wait_until": wait_month,
        },
        "verdict": verdict,
        "warnings": warnings,
        "assumptions": [
            "Considera o dinheiro das contas do dia a dia, as receitas previstas cadastradas e todas as contas, "
            "faturas e parcelas registradas.",
            "Gastos do dia a dia que não estão cadastrados não entram: deixe uma folga.",
            "O limite do cartão não é considerado dinheiro disponível.",
            "É uma simulação: nada foi registrado.",
        ],
    }
