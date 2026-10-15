"""Plano do mês: como dividir a renda entre contas, investimento e gastos livres.

É uma sugestão, não uma regra: a pessoa pode mudar a renda e o valor a investir.
Definições (documentadas em DECISOES.md, F-PLANO-*):

* Renda: soma das receitas que se repetem cadastradas (convertidas para um mês);
  sem elas, média do que entrou como receita nos 3 meses completos anteriores.
* Contas do mês: tudo o que vence no mês atual, pago ou não: contas a pagar
  (inclusive as que se repetem e as parcelas de carnê), faturas de cartão e o valor
  da parcela de cada dívida ativa.
* Para investir: sugestão de 20% da renda, sem passar do que sobra das contas.
* Livre para gastar: renda menos contas menos investimento.
* Projeção: depósito no fim de cada mês; rendimento só se a pessoa informar a taxa.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.domain.dates import YearMonth
from app.domain.goals import savings_projection, suggest_split
from app.domain.money import Money
from app.services import bills as bills_service
from app.services import cards as cards_service
from app.services import debts as debts_service
from app.services import goals as goals_service
from app.services.base import Ctx

INVEST_SHARE_PERCENT = 20
PROJECTION_YEARS = (1, 5, 10, 20)


def _expected_income(ctx: Ctx) -> int:
    total = 0
    for r in ctx.all(
        "SELECT amount_cents, frequency FROM recurring_rules WHERE owner_id=:o AND kind='receber' "
        "AND is_active AND (end_date IS NULL OR end_date >= :d)",
        d=ctx.today,
    ):
        if r.frequency == "mensal":
            total += r.amount_cents
        elif r.frequency == "semanal":
            total += r.amount_cents * 52 // 12
        else:
            total += r.amount_cents // 12
    return total


def _average_income(ctx: Ctx, months: int = 3) -> int:
    current = YearMonth.of(ctx.today)
    start = current.shift(-months).first_day
    end = current.shift(-1).last_day
    total = ctx.scalar(
        "SELECT coalesce(sum(amount_cents),0)::bigint FROM transactions WHERE owner_id=:o "
        "AND kind='receita' AND status='ativo' AND tx_date BETWEEN :s AND :e",
        s=start,
        e=end,
    )
    return int(total) // months


def _bills_of_month(ctx: Ctx) -> list[dict[str, Any]]:
    month = YearMonth.of(ctx.today)
    first, last = month.first_day, month.last_day
    bills = sum(
        b["amount_cents"]
        for b in bills_service.list_bills(ctx, kind="pagar", start=first, end=last, include_overdue=False)
        if b["situation"] != "cancelada"
    )
    invoices = 0
    for card in ctx.all("SELECT * FROM cards WHERE owner_id=:o"):
        invoices += sum(
            max(i.total.cents, 0) for i in cards_service.invoices(ctx, card) if first <= i.due_date <= last
        )
    debts = sum(
        d["installment_amount_cents"] or 0
        for d in debts_service.list_debts(ctx, include_closed=False)
        if not d["is_card_channel"] and d["balance_cents"] > 0
    )
    return [
        {"label": "Contas a pagar do mês", "cents": bills},
        {"label": "Faturas de cartão do mês", "cents": invoices},
        {"label": "Parcelas de dívidas", "cents": debts},
    ]


def month_plan(
    ctx: Ctx,
    *,
    income_cents: int | None,
    invest_cents: int | None,
    annual_rate: Decimal | None,
) -> dict[str, Any]:
    expected = _expected_income(ctx)
    average = _average_income(ctx)
    source = "recorrencias" if expected > 0 else ("media" if average > 0 else "nenhuma")
    suggested_income = expected if expected > 0 else average
    income = suggested_income if income_cents is None else income_cents

    items = _bills_of_month(ctx)
    bills_total = sum(i["cents"] for i in items)
    split = suggest_split(
        Money(income),
        Money(bills_total),
        None if invest_cents is None else Money(invest_cents),
        INVEST_SHARE_PERCENT,
    )

    warnings: list[str] = []
    if income == 0:
        warnings.append("Informe a sua renda por mês para ver a sugestão.")
    elif bills_total > income:
        warnings.append(
            "As contas do mês passam da renda. Antes de investir, veja o que dá para reduzir ou renegociar."
        )
    elif bills_total * 2 > income:
        warnings.append("As contas do mês passam da metade da renda: sobra pouco para imprevistos.")
    if split.free.cents < 0 and bills_total <= income:
        warnings.append("Com esse valor para investir, não sobra dinheiro para os gastos do dia a dia.")

    reserve = next(
        (g for g in goals_service.list_goals(ctx) if g["kind"] == "reserva_emergencia" and g["is_active"]),
        None,
    )
    tips: list[str] = []
    if reserve is None:
        tips.append(
            "Comece por uma reserva de emergência (em Planejamento): dinheiro guardado para imprevistos, "
            "fácil de resgatar."
        )
    elif reserve["accumulated_cents"] < reserve["target_cents"]:
        tips.append(
            "Enquanto a reserva de emergência não estiver completa, ela pode ser o destino do investimento."
        )

    monthly = Money(max(split.invest.cents, 0))
    projection = [
        {
            "years": y,
            "deposited_cents": p.deposited.cents,
            "estimated_cents": p.estimated.cents,
        }
        for y in PROJECTION_YEARS
        for p in [savings_projection(monthly, annual_rate, y * 12)]
    ]
    assumptions = [
        "É uma sugestão para ajudar a decidir; você pode mudar a renda e o valor a investir.",
        f"Sugestão de investimento: {INVEST_SHARE_PERCENT}% da renda (referência da regra 50/30/20), "
        "sem passar do que sobra depois das contas.",
        "Contas do mês: tudo o que vence neste mês, pago ou não (contas, parcelas de carnê, faturas e parcelas "
        "de dívidas).",
    ]
    if annual_rate:
        assumptions.append(
            f"Projeção com rendimento de {annual_rate}% ao ano informado por você, depósito no fim de cada mês. "
            "Rendimento não é garantido e não considera impostos nem inflação."
        )
    else:
        assumptions.append("Projeção sem rendimento: só a soma dos depósitos. Informe a taxa para estimar.")

    return {
        "month": str(YearMonth.of(ctx.today)),
        "income": {
            "used_cents": income,
            "suggested_cents": suggested_income,
            "expected_cents": expected,
            "average_cents": average,
            "source": source,
        },
        "bills": {"total_cents": bills_total, "items": items},
        "invest_cents": split.invest.cents,
        "invest_suggested_cents": split.invest_suggested.cents,
        "free_cents": split.free.cents,
        "projection": projection,
        "warnings": warnings,
        "tips": tips,
        "assumptions": assumptions,
    }
