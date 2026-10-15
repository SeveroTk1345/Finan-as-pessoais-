"""Dívidas: saldo ancorado, pagamentos, encargos, renegociação e estratégias.

Parcelamento de fatura (F-CARTAO-6) é uma dívida "do cartão": o saldo vem das
parcelas nas faturas e ela não aceita pagamento direto, para não contar duas vezes.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import Row

from app.api.errors import ApiError
from app.domain.debts import (
    STRATEGY_LABELS,
    DebtMovement,
    SimDebt,
    Strategy,
    debt_balance,
    installment_progress,
    monthly_rate,
    simulate,
)
from app.domain.money import Money, format_brl
from app.services.base import Ctx, check_version, reject_future, row_dict


def _movements(ctx: Ctx, debt_id: UUID) -> list[DebtMovement]:
    moves = [
        DebtMovement(
            r.tx_date,
            "pagamento",
            Money(r.amount_cents),
            Money(r.debt_interest_cents) if r.debt_interest_cents is not None else None,
        )
        for r in ctx.all(
            "SELECT tx_date, amount_cents, debt_interest_cents FROM transactions "
            "WHERE owner_id=:o AND debt_id=:d AND kind='pagamento_divida' AND status='ativo'",
            d=debt_id,
        )
    ]
    moves += [
        DebtMovement(r.event_date, r.kind, Money(r.amount_cents))
        for r in ctx.all(
            "SELECT event_date, kind, amount_cents FROM debt_events "
            "WHERE owner_id=:o AND debt_id=:d AND status='ativo'",
            d=debt_id,
        )
    ]
    return moves


def debt_view(ctx: Ctx, debt: Row[Any]) -> dict[str, Any]:
    out = row_dict(debt)
    out["interest_rate"] = str(debt.interest_rate) if debt.interest_rate is not None else None
    out["is_card_channel"] = debt.card_id is not None
    if debt.card_id is not None:
        from app.services.cards import card_channel_debt_remaining

        remaining, paid_count = card_channel_debt_remaining(ctx, debt.id, debt.card_id)
        out.update(
            balance_cents=remaining,
            balance_estimated=False,
            principal_paid_cents=None,
            interest_paid_cents=None,
            total_paid_cents=(debt.anchor_balance_cents - remaining),
        )
        payments_count = paid_count
    else:
        bal = debt_balance(Money(debt.anchor_balance_cents), debt.anchor_date, _movements(ctx, debt.id))
        out.update(
            balance_cents=bal.balance.cents if debt.status not in ("renegociada", "cancelada") else 0,
            balance_estimated=bal.estimated,
            principal_paid_cents=bal.principal_paid.cents,
            interest_paid_cents=bal.interest_paid.cents,
            total_paid_cents=bal.total_paid.cents,
        )
        payments_count = int(
            ctx.scalar(
                "SELECT count(*) FROM transactions WHERE owner_id=:o AND debt_id=:d "
                "AND kind='pagamento_divida' AND debt_payment_type='parcela' AND status='ativo'",
                d=debt.id,
            )
        )
    prog = installment_progress(
        debt.installments_total,
        debt.installments_paid_before if debt.card_id is None else 0,
        payments_count,
        debt.first_due_date,
    )
    active = debt.status == "ativa" and out["balance_cents"] > 0
    out.update(
        installments_paid=prog.paid,
        installments_remaining=prog.remaining,
        next_due_date=prog.next_due if active else None,
        overdue=bool(active and prog.next_due and prog.next_due < ctx.today),
    )
    return out


def list_debts(ctx: Ctx, include_closed: bool = True) -> list[dict[str, Any]]:
    rows = ctx.all(
        "SELECT * FROM debts WHERE owner_id=:o AND (:all OR status='ativa') "
        "ORDER BY (status='ativa') DESC, creditor, id",
        all=include_closed,
    )
    return [debt_view(ctx, r) for r in rows]


def get_debt(ctx: Ctx, debt_id: UUID) -> dict[str, Any]:
    debt = ctx.require("debts", debt_id, "Dívida")
    out = debt_view(ctx, debt)
    out["payments"] = [
        row_dict(r)
        for r in ctx.all(
            """SELECT t.id, t.tx_date, t.amount_cents, t.debt_interest_cents, t.debt_payment_type,
                      t.status, a.name AS account_name
               FROM transactions t JOIN accounts a ON a.id=t.account_id AND a.owner_id=t.owner_id
               WHERE t.owner_id=:o AND t.debt_id=:d AND t.kind='pagamento_divida'
               ORDER BY t.tx_date, t.created_at""",
            d=debt_id,
        )
    ]
    out["events"] = [
        row_dict(r)
        for r in ctx.all(
            "SELECT id, event_date, kind, amount_cents, description, status FROM debt_events "
            "WHERE owner_id=:o AND debt_id=:d ORDER BY event_date, created_at",
            d=debt_id,
        )
    ]
    out["renegotiated_into"] = [
        r.id for r in ctx.all("SELECT id FROM debts WHERE owner_id=:o AND renegotiated_from_id=:d", d=debt_id)
    ]
    return out


def _validate_terms(data: dict[str, Any]) -> None:
    if (data.get("interest_rate") is None) != (data.get("rate_period") is None):
        raise ApiError(
            422,
            "Informe a taxa e se ela é ao mês ou ao ano, ou deixe as duas em branco.",
            {"rate_period": "Escolha ao mês ou ao ano."},
        )
    total = data.get("installments_total")
    if total is not None and data.get("installments_paid_before", 0) > total:
        raise ApiError(
            422,
            "Parcelas já pagas não podem passar do total.",
            {"installments_paid_before": "Maior que o total."},
        )


def create_debt(ctx: Ctx, data: dict[str, Any]) -> dict[str, Any]:
    _validate_terms(data)
    anchor = data.get("current_balance_cents")
    if anchor is None:
        anchor = data["original_amount_cents"]
    anchor_date = data.get("balance_date") or ctx.today
    reject_future(anchor_date, ctx.today, "balance_date", "A data do saldo")
    row = ctx.one(
        """INSERT INTO debts (owner_id, creditor, description, kind, original_amount_cents,
               start_date, anchor_balance_cents, anchor_date, interest_rate, rate_period,
               installments_total, installments_paid_before, installment_amount_cents,
               first_due_date, note)
           VALUES (:o, :creditor, :description, :kind, :original, :start, :anchor, :adate, :rate,
               :period, :total, :before, :inst, :first, :note) RETURNING id""",
        creditor=data["creditor"].strip(),
        description=data.get("description"),
        kind=data["kind"],
        original=data["original_amount_cents"],
        start=data.get("start_date") or anchor_date,
        anchor=anchor,
        adate=anchor_date,
        rate=data.get("interest_rate"),
        period=data.get("rate_period"),
        total=data.get("installments_total"),
        before=data.get("installments_paid_before", 0),
        inst=data.get("installment_amount_cents"),
        first=data.get("first_due_date"),
        note=data.get("note"),
    )
    if row is None:  # pragma: no cover
        raise RuntimeError("falha ao gravar")
    disb = data.get("disbursement_account_id")
    if disb is not None:
        # Dinheiro do empréstimo entrando na conta: não é receita (F15).
        from app.services.ledger import _insert_tx

        _insert_tx(
            ctx,
            account_id=disb,
            direction="entrada",
            amount=data["original_amount_cents"],
            on=data.get("start_date") or anchor_date,
            kind="entrada_emprestimo",
            description=f"Empréstimo: {data['creditor'].strip()}"[:120],
            debt_id=row.id,
        )
    return get_debt(ctx, row.id)


def update_debt(ctx: Ctx, debt_id: UUID, data: dict[str, Any]) -> dict[str, Any]:
    debt = ctx.require("debts", debt_id, "Dívida")
    check_version(debt, data.get("version"))
    fields = (
        "creditor",
        "description",
        "interest_rate",
        "rate_period",
        "installments_total",
        "installments_paid_before",
        "installment_amount_cents",
        "first_due_date",
        "note",
    )
    new = {k: data.get(k, getattr(debt, k)) for k in fields}
    _validate_terms(new)
    ctx.exec(
        """UPDATE debts SET creditor=:creditor, description=:description,
             interest_rate=:interest_rate, rate_period=:rate_period,
             installments_total=:installments_total,
             installments_paid_before=:installments_paid_before,
             installment_amount_cents=:installment_amount_cents, first_due_date=:first_due_date,
             note=:note, version=version+1, updated_at=now()
           WHERE id=:id AND owner_id=:o""",
        id=debt_id,
        **new,
    )
    ctx.audit("divida", debt_id, "editar", {k: getattr(debt, k) for k in fields}, new)
    return get_debt(ctx, debt_id)


def _active_direct(ctx: Ctx, debt_id: UUID) -> Row[Any]:
    debt = ctx.require("debts", debt_id, "Dívida")
    if debt.card_id is not None:
        raise ApiError(
            409,
            "Esta dívida é paga pelas faturas do cartão. Registre o pagamento na fatura.",
        )
    if debt.status != "ativa":
        raise ApiError(409, "Esta dívida não está ativa.")
    return debt


def pay_debt(ctx: Ctx, debt_id: UUID, data: dict[str, Any]) -> dict[str, Any]:
    debt = _active_direct(ctx, debt_id)
    view = debt_view(ctx, debt)
    on = data.get("tx_date") or ctx.today
    reject_future(on, ctx.today, "tx_date", "O pagamento")
    amount = data["amount_cents"]
    interest = data.get("interest_cents")
    if interest is not None and interest > amount:
        raise ApiError(
            422, "Os juros não podem passar do valor pago.", {"interest_cents": "Maior que o pagamento."}
        )
    principal = amount - (interest or 0)
    if principal > view["balance_cents"]:
        raise ApiError(
            422,
            f"O valor passa do saldo devedor registrado ({format_brl(Money(view['balance_cents']))}). "
            "Se houve juros, informe quanto foi de juros.",
            {"amount_cents": "Maior que o saldo."},
        )
    from app.services.ledger import _insert_tx

    tx = _insert_tx(
        ctx,
        account_id=data["account_id"],
        direction="saida",
        amount=amount,
        on=on,
        kind="pagamento_divida",
        description=f"Pagamento: {debt.creditor}"[:120],
        debt_id=debt_id,
        debt_payment_type=data.get("payment_type", "parcela"),
        debt_interest_cents=interest,
    )
    refresh_debt_status(ctx, debt_id)
    return {"debt": get_debt(ctx, debt_id), "transaction": tx}


def add_event(ctx: Ctx, debt_id: UUID, data: dict[str, Any]) -> dict[str, Any]:
    _active_direct(ctx, debt_id)
    on = data.get("event_date") or ctx.today
    reject_future(on, ctx.today, "event_date", "A data")
    ctx.exec(
        "INSERT INTO debt_events (owner_id, debt_id, event_date, kind, amount_cents, description) "
        "VALUES (:o, :d, :e, :k, :a, :desc)",
        d=debt_id,
        e=on,
        k=data["kind"],
        a=data["amount_cents"],
        desc=data.get("description") or ("Encargo" if data["kind"] == "encargo" else "Desconto"),
    )
    refresh_debt_status(ctx, debt_id)
    return get_debt(ctx, debt_id)


def refresh_debt_status(ctx: Ctx, debt_id: UUID) -> None:
    """Quitada quando o saldo chega a zero; volta a ativa se um pagamento for cancelado."""
    debt = ctx.one("SELECT * FROM debts WHERE id=:id AND owner_id=:o", id=debt_id)
    if debt is None or debt.card_id is not None or debt.status in ("renegociada", "cancelada"):
        return
    bal = debt_balance(Money(debt.anchor_balance_cents), debt.anchor_date, _movements(ctx, debt_id))
    new = "quitada" if bal.balance.cents == 0 else "ativa"
    if new != debt.status:
        ctx.exec(
            "UPDATE debts SET status=:s, version=version+1, updated_at=now() WHERE id=:id AND owner_id=:o",
            s=new,
            id=debt_id,
        )


def renegotiate_debt(ctx: Ctx, debt_id: UUID, data: dict[str, Any]) -> dict[str, Any]:
    """F-DIV-7: a dívida antiga é baixada sem saída de dinheiro e a nova guarda o vínculo.
    O saldo total devido passa a ser só o da nova dívida."""
    old = _active_direct(ctx, debt_id)
    view = debt_view(ctx, old)
    if view["balance_cents"] > 0:
        ctx.exec(
            "INSERT INTO debt_events (owner_id, debt_id, event_date, kind, amount_cents, description) "
            "VALUES (:o, :d, :e, 'renegociacao_baixa', :a, 'Saldo transferido para renegociação')",
            d=debt_id,
            e=ctx.today,
            a=view["balance_cents"],
        )
    ctx.exec(
        "UPDATE debts SET status='renegociada', version=version+1, updated_at=now() "
        "WHERE id=:id AND owner_id=:o",
        id=debt_id,
    )
    payload = {
        "creditor": data.get("creditor") or old.creditor,
        "description": data.get("description") or f"Renegociação de {old.creditor}"[:120],
        "kind": "renegociacao",
        "original_amount_cents": data["new_balance_cents"],
        "current_balance_cents": data["new_balance_cents"],
        "balance_date": ctx.today,
        "start_date": ctx.today,
        "interest_rate": data.get("interest_rate"),
        "rate_period": data.get("rate_period"),
        "installments_total": data.get("installments_total"),
        "installment_amount_cents": data.get("installment_amount_cents"),
        "first_due_date": data.get("first_due_date"),
        "note": data.get("note"),
    }
    new = create_debt(ctx, payload)
    ctx.exec(
        "UPDATE debts SET renegotiated_from_id=:old WHERE id=:id AND owner_id=:o",
        old=debt_id,
        id=new["id"],
    )
    return {"old": get_debt(ctx, debt_id), "new": get_debt(ctx, new["id"])}


def cancel_debt(ctx: Ctx, debt_id: UUID) -> dict[str, Any]:
    """Para dívidas cadastradas por engano: só sem pagamentos registrados."""
    debt = ctx.require("debts", debt_id, "Dívida")
    if debt.card_id is not None:
        raise ApiError(409, "Parcelamentos de fatura não podem ser cancelados por aqui.")
    used = ctx.scalar(
        "SELECT count(*) FROM transactions WHERE owner_id=:o AND debt_id=:d AND status='ativo'",
        d=debt_id,
    )
    if used:
        raise ApiError(409, "Esta dívida tem pagamentos registrados. Cancele os pagamentos antes.")
    ctx.exec(
        "UPDATE debts SET status='cancelada', version=version+1, updated_at=now() "
        "WHERE id=:id AND owner_id=:o",
        id=debt_id,
    )
    ctx.audit("divida", debt_id, "cancelar")
    return get_debt(ctx, debt_id)


def strategies(ctx: Ctx, extra_monthly_cents: int) -> dict[str, Any]:
    debts = [d for d in list_debts(ctx, include_closed=False) if not d["is_card_channel"]]
    debts = [d for d in debts if d["balance_cents"] > 0]
    if not debts:
        return {"debts": [], "results": [], "warnings": ["Nenhuma dívida ativa para comparar."]}
    sims = [
        SimDebt(
            str(d["id"]),
            d["creditor"],
            Money(d["balance_cents"]),
            monthly_rate(Decimal(d["interest_rate"]), d["rate_period"]) if d["interest_rate"] else None,
            Money(d["installment_amount_cents"] or 0),
        )
        for d in debts
    ]
    results = []
    for strategy in Strategy:
        r = simulate(strategy, sims, Money(extra_monthly_cents))
        results.append(
            {
                "strategy": strategy.value,
                "label": STRATEGY_LABELS[strategy],
                "order": r.order,
                "months": r.months,
                "total_paid_cents": r.total_paid.cents,
                "total_interest_cents": r.total_interest.cents,
                "payoff_month": r.payoff_month,
                "warnings": r.warnings,
            }
        )
    return {
        "debts": [
            {
                "id": str(d["id"]),
                "creditor": d["creditor"],
                "balance_cents": d["balance_cents"],
                "has_rate": d["interest_rate"] is not None,
                "has_installment": d["installment_amount_cents"] is not None,
            }
            for d in debts
        ],
        "results": results,
        "warnings": [
            "Simulação com base nos dados registrados. Os resultados reais dependem das condições do credor."
        ],
    }


def next_installments(ctx: Ctx, until: date) -> list[dict[str, Any]]:
    """Próximas parcelas de dívidas pagas diretamente (para "Contas a pagar")."""
    out = []
    for d in list_debts(ctx, include_closed=False):
        if d["is_card_channel"] or d["next_due_date"] is None or not d["installment_amount_cents"]:
            continue
        if d["next_due_date"] <= until:
            out.append(
                {
                    "debt_id": d["id"],
                    "creditor": d["creditor"],
                    "due_date": d["next_due_date"],
                    "amount_cents": min(d["installment_amount_cents"], d["balance_cents"]),
                    "overdue": d["overdue"],
                }
            )
    return out
