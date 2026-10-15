"""Cartões, compras, faturas, pagamentos, estornos e renegociação de fatura.

Regras em docs/DECISOES.md (F-CARTAO-1 a 9). Resumo:
* compra (origem única) -> parcelas atribuídas a faturas na criação;
* fatura = agrupamento derivado (parcelas + encargos - créditos - pagamentos);
* pagamento de fatura = lançamento ``pagamento_fatura`` na conta, nunca despesa;
* renegociação: crédito na fatura + dívida + parcelas do acordo nas próximas faturas.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any
from uuid import UUID

from sqlalchemy import Row

from app.api.errors import ApiError, not_found
from app.domain.cards import (
    CardCycle,
    InstallmentState,
    Invoice,
    InvoiceItems,
    build_invoices,
    limit_summary,
    plan_cancellation,
    plan_installments,
)
from app.domain.money import Money, format_brl
from app.services.base import Ctx, check_version, reject_future, row_dict
from app.services.ledger import _insert_tx, check_category


def _cycle(card: Row[Any]) -> CardCycle:
    return CardCycle(card.closing_day, card.due_day, card.closing_day_goes_next)


def _card(ctx: Ctx, card_id: UUID) -> Row[Any]:
    return ctx.require("cards", card_id, "Cartão")


def _totals(ctx: Ctx, card_id: UUID) -> tuple[dict[date, list[int]], int, int, int]:
    """Somas por fatura: [encargos, créditos, pagamentos]."""
    per: dict[date, list[int]] = defaultdict(lambda: [0, 0, 0])
    for r in ctx.all(
        "SELECT invoice_due_date AS d, sum(amount_cents)::bigint AS v FROM card_installments "
        "WHERE owner_id=:o AND card_id=:c AND status='ativa' GROUP BY 1",
        c=card_id,
    ):
        per[r.d][0] += r.v
    for r in ctx.all(
        "SELECT invoice_due_date AS d, sum(amount_cents)::bigint AS v FROM card_credits "
        "WHERE owner_id=:o AND card_id=:c GROUP BY 1",
        c=card_id,
    ):
        per[r.d][1] += r.v
    for r in ctx.all(
        "SELECT invoice_due_date AS d, sum(amount_cents)::bigint AS v FROM transactions "
        "WHERE owner_id=:o AND card_id=:c AND kind='pagamento_fatura' AND status='ativo' GROUP BY 1",
        c=card_id,
    ):
        per[r.d][2] += r.v
    charges = sum(v[0] for v in per.values())
    credits = sum(v[1] for v in per.values())
    payments = sum(v[2] for v in per.values())
    return per, charges, credits, payments


def invoices(ctx: Ctx, card: Row[Any]) -> list[Invoice]:
    per, *_ = _totals(ctx, card.id)
    cycle = _cycle(card)
    open_due = cycle.invoice_due_for_purchase(ctx.today)
    per.setdefault(open_due, [0, 0, 0])  # a fatura aberta sempre aparece
    items = [InvoiceItems(d, Money(v[0]), Money(v[1]), Money(v[2])) for d, v in per.items()]
    return build_invoices(cycle, ctx.today, items)


def _invoice_dict(inv: Invoice) -> dict[str, Any]:
    return {
        "due_date": inv.due_date,
        "closing_date": inv.closing_date,
        "charges_cents": inv.charges.cents,
        "credits_cents": inv.credits.cents,
        "carried_credit_cents": inv.carried_credit.cents,
        "payments_cents": inv.payments.cents,
        "total_cents": inv.total.cents,
        "remaining_cents": inv.remaining.cents,
        "credit_left_cents": inv.credit_left.cents,
        "status": inv.status.value,
    }


def card_summary(ctx: Ctx, card: Row[Any]) -> dict[str, Any]:
    _, charges, credits, payments = _totals(ctx, card.id)
    lim = limit_summary(Money(card.limit_cents), Money(charges), Money(credits), Money(payments))
    invs = invoices(ctx, card)
    open_due = _cycle(card).invoice_due_for_purchase(ctx.today)
    open_inv = next(i for i in invs if i.due_date == open_due)
    pending = [i for i in invs if i.status.value in ("fechada", "vencida", "parcialmente_paga")]
    out = row_dict(card)
    out.update(
        {
            "limit_used_cents": lim.used.cents,
            "limit_available_cents": lim.available.cents,
            "credit_balance_cents": lim.credit_balance.cents,
            "open_invoice": _invoice_dict(open_inv),
            "invoices_to_pay": [_invoice_dict(i) for i in pending],
            "outstanding_cents": sum(i.remaining.cents for i in invs),
        }
    )
    return out


def list_cards(ctx: Ctx) -> list[dict[str, Any]]:
    rows = ctx.all("SELECT * FROM cards WHERE owner_id=:o ORDER BY is_active DESC, name, id")
    return [card_summary(ctx, r) for r in rows]


def get_card(ctx: Ctx, card_id: UUID) -> dict[str, Any]:
    card = _card(ctx, card_id)
    out = card_summary(ctx, card)
    out["invoices"] = [_invoice_dict(i) for i in invoices(ctx, card)]
    return out


def create_card(ctx: Ctx, data: dict[str, Any]) -> dict[str, Any]:
    row = ctx.one(
        """INSERT INTO cards (owner_id, name, institution, limit_cents, closing_day, due_day,
               closing_day_goes_next) VALUES (:o, :name, :institution, :limit_cents, :closing_day,
               :due_day, :closing_day_goes_next) RETURNING *""",
        name=data["name"].strip(),
        institution=data.get("institution"),
        limit_cents=data["limit_cents"],
        closing_day=data["closing_day"],
        due_day=data["due_day"],
        closing_day_goes_next=data.get("closing_day_goes_next", True),
    )
    if row is None:  # pragma: no cover
        raise RuntimeError("falha ao gravar")
    return card_summary(ctx, row)


def update_card(ctx: Ctx, card_id: UUID, data: dict[str, Any]) -> dict[str, Any]:
    """Mudar o ciclo vale para compras novas; parcelas já lançadas não mudam (F-CARTAO-4)."""
    card = _card(ctx, card_id)
    check_version(card, data.get("version"))
    new = {
        k: data.get(k, getattr(card, k))
        for k in (
            "name",
            "institution",
            "limit_cents",
            "closing_day",
            "due_day",
            "closing_day_goes_next",
            "is_active",
        )
    }
    row = ctx.one(
        """UPDATE cards SET name=:name, institution=:institution, limit_cents=:limit_cents,
             closing_day=:closing_day, due_day=:due_day,
             closing_day_goes_next=:closing_day_goes_next, is_active=:is_active,
             version=version+1, updated_at=now()
           WHERE id=:id AND owner_id=:o RETURNING *""",
        id=card_id,
        **new,
    )
    ctx.audit("cartao", card_id, "editar", {k: getattr(card, k) for k in new}, new)
    if row is None:  # pragma: no cover
        raise RuntimeError("falha ao gravar")
    return card_summary(ctx, row)


# --- compras ---------------------------------------------------------------------


def _default_fee_category(ctx: Ctx) -> UUID | None:
    v = ctx.scalar(
        "SELECT id FROM categories WHERE owner_id=:o AND kind='despesa' AND name='Juros e tarifas'"
    )
    return UUID(str(v)) if v else None


def create_purchase(ctx: Ctx, card_id: UUID, data: dict[str, Any]) -> dict[str, Any]:
    card = _card(ctx, card_id)
    if not card.is_active:
        raise ApiError(422, "Este cartão está desativado.")
    kind = data.get("kind", "compra")
    reject_future(data["purchase_date"], ctx.today, "purchase_date", "A data da compra")
    category_id = data.get("category_id")
    if kind == "encargo":
        category_id = category_id or _default_fee_category(ctx)
        count = 1
    else:
        count = data.get("installments_count", 1)
    check_category(ctx, category_id, "despesa")
    cycle = _cycle(card)
    computed = cycle.invoice_due_for_purchase(data["purchase_date"])
    first = data.get("first_invoice_due")
    if first is not None and first not in {
        cycle.shift_invoice(computed, -1),
        computed,
        cycle.shift_invoice(computed, 1),
    }:
        raise ApiError(
            422,
            "Escolha a fatura sugerida ou uma vizinha a ela.",
            {"first_invoice_due": "Fatura fora do ciclo do cartão."},
        )
    plan = plan_installments(
        cycle, data["purchase_date"], Money(data["total_cents"]), count, first_invoice_due=first
    )
    purchase = ctx.one(
        """INSERT INTO card_purchases (owner_id, card_id, kind, description, category_id,
               purchase_date, total_cents, installments_count, note)
           VALUES (:o, :c, :k, :d, :cat, :pd, :t, :n, :note) RETURNING *""",
        c=card_id,
        k=kind,
        d=data["description"].strip(),
        cat=category_id,
        pd=data["purchase_date"],
        t=data["total_cents"],
        n=count,
        note=data.get("note"),
    )
    if purchase is None:  # pragma: no cover
        raise RuntimeError("falha ao gravar")
    _insert_installments(ctx, card_id, purchase.id, plan)
    return get_purchase(ctx, purchase.id)


def _insert_installments(ctx: Ctx, card_id: UUID, purchase_id: UUID, plan: list[Any]) -> None:
    for p in plan:
        ctx.exec(
            """INSERT INTO card_installments (owner_id, purchase_id, card_id, number, amount_cents,
                   invoice_due_date) VALUES (:o, :p, :c, :n, :a, :d)""",
            p=purchase_id,
            c=card_id,
            n=p.number,
            a=p.amount.cents,
            d=p.invoice_due_date,
        )


def get_purchase(ctx: Ctx, purchase_id: UUID) -> dict[str, Any]:
    row = ctx.one(
        """SELECT p.*, c.name AS category_name, k.name AS card_name FROM card_purchases p
           JOIN cards k ON k.id = p.card_id AND k.owner_id = p.owner_id
           LEFT JOIN categories c ON c.id = p.category_id AND c.owner_id = p.owner_id
           WHERE p.id=:id AND p.owner_id=:o""",
        id=purchase_id,
    )
    if row is None:
        raise not_found("Compra")
    out = row_dict(row)
    out["installments"] = [
        row_dict(i)
        for i in ctx.all(
            "SELECT id, number, amount_cents, invoice_due_date, status FROM card_installments "
            "WHERE owner_id=:o AND purchase_id=:p ORDER BY number",
            p=purchase_id,
        )
    ]
    out["credits"] = [
        row_dict(c)
        for c in ctx.all(
            "SELECT id, kind, description, credit_date, invoice_due_date, amount_cents "
            "FROM card_credits WHERE owner_id=:o AND purchase_id=:p ORDER BY credit_date, created_at",
            p=purchase_id,
        )
    ]
    active = sum(i["amount_cents"] for i in out["installments"] if i["status"] == "ativa")
    credited = sum(c["amount_cents"] for c in out["credits"])
    out["net_cents"] = active - credited
    return out


def _purchase_for_change(ctx: Ctx, purchase_id: UUID) -> Row[Any]:
    p = ctx.require("card_purchases", purchase_id, "Compra")
    if p.status != "ativa":
        raise ApiError(409, "Esta compra já foi cancelada.")
    if p.kind == "parcelamento_fatura":
        raise ApiError(409, "Parcelas de renegociação são acompanhadas na área de Dívidas.")
    return p


def cancel_purchase(ctx: Ctx, purchase_id: UUID) -> dict[str, Any]:
    """F-CARTAO-7: parcelas ainda não faturadas são canceladas; as já faturadas viram
    crédito na fatura aberta. Estornos anteriores são descontados do crédito."""
    p = _purchase_for_change(ctx, purchase_id)
    card = _card(ctx, p.card_id)
    rows = ctx.all(
        "SELECT id, amount_cents, invoice_due_date, status FROM card_installments "
        "WHERE owner_id=:o AND purchase_id=:p ORDER BY number",
        p=purchase_id,
    )
    states = [
        InstallmentState(r.id, Money(r.amount_cents), r.invoice_due_date, r.status == "ativa") for r in rows
    ]
    plan = plan_cancellation(_cycle(card), ctx.today, states)
    already = int(
        ctx.scalar(
            "SELECT coalesce(sum(amount_cents),0) FROM card_credits WHERE owner_id=:o AND purchase_id=:p",
            p=purchase_id,
        )
    )
    active_total = sum(s.amount.cents for s in states if s.active)
    open_due = _cycle(card).invoice_due_for_purchase(ctx.today)
    if already <= plan.credit_amount.cents:
        # Caso normal: cancela o que não foi faturado e credita o que já foi cobrado,
        # descontando estornos anteriores. Consumo líquido final: zero.
        cancel_ids = plan.cancel_ids
        credit = plan.credit_amount.cents - already
    else:
        # Estornos anteriores já superam o que foi faturado: as parcelas continuam e
        # um crédito fecha a diferença. Consumo líquido final: zero.
        cancel_ids = []
        credit = max(active_total - already, 0)
    for inst_id in cancel_ids:
        ctx.exec(
            "UPDATE card_installments SET status='cancelada', updated_at=now() WHERE id=:id AND owner_id=:o",
            id=inst_id,
        )
    if credit > 0:
        ctx.exec(
            """INSERT INTO card_credits (owner_id, card_id, purchase_id, kind, description,
                   credit_date, invoice_due_date, amount_cents)
               VALUES (:o, :c, :p, 'cancelamento', :d, :cd, :due, :a)""",
            c=p.card_id,
            p=purchase_id,
            d=f"Cancelamento: {p.description}"[:120],
            cd=ctx.today,
            due=open_due,
            a=credit,
        )
    ctx.exec(
        "UPDATE card_purchases SET status='cancelada', cancelled_at=now(), updated_at=now() "
        "WHERE id=:id AND owner_id=:o",
        id=purchase_id,
    )
    ctx.audit("compra_cartao", purchase_id, "cancelar")
    return get_purchase(ctx, purchase_id)


def refund_purchase(ctx: Ctx, purchase_id: UUID, amount: int, on: date | None) -> dict[str, Any]:
    """F-CARTAO-8: estorno parcial ou total como crédito na fatura aberta."""
    p = _purchase_for_change(ctx, purchase_id)
    card = _card(ctx, p.card_id)
    on = on or ctx.today
    reject_future(on, ctx.today, "credit_date", "O estorno")
    current = get_purchase(ctx, purchase_id)
    if amount > current["net_cents"]:
        raise ApiError(
            422,
            "O estorno passa do valor da compra ainda não estornado "
            f"({format_brl(Money(current['net_cents']))}).",
            {"amount_cents": "Valor maior que o da compra."},
        )
    ctx.exec(
        """INSERT INTO card_credits (owner_id, card_id, purchase_id, kind, description, credit_date,
               invoice_due_date, amount_cents) VALUES (:o, :c, :p, 'estorno', :d, :cd, :due, :a)""",
        c=p.card_id,
        p=purchase_id,
        d=f"Estorno: {p.description}"[:120],
        cd=on,
        due=_cycle(card).invoice_due_for_purchase(on),
        a=amount,
    )
    return get_purchase(ctx, purchase_id)


def invoice_detail(ctx: Ctx, card_id: UUID, due: date) -> dict[str, Any]:
    card = _card(ctx, card_id)
    inv = next((i for i in invoices(ctx, card) if i.due_date == due), None)
    if inv is None:
        raise not_found("Fatura")
    out = _invoice_dict(inv)
    out["card"] = {"id": card.id, "name": card.name}
    out["items"] = [
        row_dict(r)
        for r in ctx.all(
            """SELECT i.id, i.number, i.amount_cents, i.status, p.id AS purchase_id, p.description,
                      p.purchase_date, p.installments_count, p.kind, c.name AS category_name
               FROM card_installments i
               JOIN card_purchases p ON p.id = i.purchase_id AND p.owner_id = i.owner_id
               LEFT JOIN categories c ON c.id = p.category_id AND c.owner_id = p.owner_id
               WHERE i.owner_id=:o AND i.card_id=:c AND i.invoice_due_date=:d
               ORDER BY p.purchase_date, p.description, i.number""",
            c=card_id,
            d=due,
        )
    ]
    out["credits"] = [
        row_dict(r)
        for r in ctx.all(
            "SELECT id, kind, description, credit_date, amount_cents FROM card_credits "
            "WHERE owner_id=:o AND card_id=:c AND invoice_due_date=:d ORDER BY credit_date",
            c=card_id,
            d=due,
        )
    ]
    out["payments"] = [
        row_dict(r)
        for r in ctx.all(
            """SELECT t.id, t.amount_cents, t.tx_date, t.status, a.name AS account_name
               FROM transactions t JOIN accounts a ON a.id=t.account_id AND a.owner_id=t.owner_id
               WHERE t.owner_id=:o AND t.card_id=:c AND t.invoice_due_date=:d
                 AND t.kind='pagamento_fatura' ORDER BY t.tx_date""",
            c=card_id,
            d=due,
        )
    ]
    return out


def pay_invoice(ctx: Ctx, card_id: UUID, due: date, data: dict[str, Any]) -> dict[str, Any]:
    """O pagamento sai da conta e liquida a fatura; não é uma nova despesa."""
    card = _card(ctx, card_id)
    inv = next((i for i in invoices(ctx, card) if i.due_date == due), None)
    if inv is None or inv.remaining.cents == 0:
        raise ApiError(409, "Esta fatura não tem valor a pagar.")
    amount = data.get("amount_cents") or inv.remaining.cents
    if amount > inv.remaining.cents:
        raise ApiError(
            422,
            f"O valor passa do que falta pagar nesta fatura ({format_brl(inv.remaining)}).",
            {"amount_cents": "Valor maior que o restante."},
        )
    on = data.get("tx_date") or ctx.today
    reject_future(on, ctx.today, "tx_date", "O pagamento")
    tx = _insert_tx(
        ctx,
        account_id=data["account_id"],
        direction="saida",
        amount=amount,
        on=on,
        kind="pagamento_fatura",
        description=f"Fatura {card.name} {due.strftime('%m/%Y')}",
        card_id=card_id,
        invoice_due_date=due,
    )
    return {"invoice": invoice_detail(ctx, card_id, due), "transaction": tx}


def renegotiate_invoice(ctx: Ctx, card_id: UUID, due: date, data: dict[str, Any]) -> dict[str, Any]:
    """F-CARTAO-6: transfere parte da fatura para uma dívida de parcelamento.

    * a fatura recebe crédito do valor renegociado (sai do "a pagar" dela);
    * nasce uma dívida "parcelamento de fatura", acompanhada em Dívidas;
    * as parcelas do acordo entram nas próximas faturas, ligadas à dívida;
    * a diferença entre o total do acordo e o valor renegociado é juros.
    Cada real aparece uma única vez no que falta pagar.
    """
    card = _card(ctx, card_id)
    inv = next((i for i in invoices(ctx, card) if i.due_date == due), None)
    if inv is None or inv.remaining.cents == 0:
        raise ApiError(409, "Esta fatura não tem valor a renegociar.")
    financed = data["financed_cents"]
    count = data["installments_count"]
    installment = data["installment_cents"]
    if financed > inv.remaining.cents:
        raise ApiError(
            422,
            f"O valor renegociado passa do que falta pagar ({format_brl(inv.remaining)}).",
            {"financed_cents": "Valor maior que o restante da fatura."},
        )
    total = count * installment
    if total < financed:
        raise ApiError(
            422,
            "As parcelas somadas ficam abaixo do valor renegociado. Confira os valores do acordo.",
            {"installment_cents": "Parcela pequena demais."},
        )
    cycle = _cycle(card)
    first_due = data.get("first_invoice_due") or cycle.shift_invoice(due, 1)
    if first_due <= due or first_due.day != cycle.shift_invoice(first_due, 0).day:
        raise ApiError(
            422,
            "A primeira parcela precisa cair em uma fatura posterior.",
            {"first_invoice_due": "Fatura inválida."},
        )
    debt = ctx.one(
        """INSERT INTO debts (owner_id, creditor, description, kind, original_amount_cents,
               start_date, anchor_balance_cents, anchor_date, installments_total,
               installment_amount_cents, first_due_date, card_id, card_invoice_due_date)
           VALUES (:o, :cred, :desc, 'parcelamento_fatura', :orig, :today, :total, :today, :n,
               :inst, :first, :card, :due) RETURNING id""",
        cred=(data.get("creditor") or card.institution or card.name)[:80],
        desc=f"Parcelamento da fatura {due.strftime('%m/%Y')} do {card.name}"[:120],
        orig=financed,
        today=ctx.today,
        total=total,
        n=count,
        inst=installment,
        first=first_due,
        card=card_id,
        due=due,
    )
    if debt is None:  # pragma: no cover
        raise RuntimeError("falha ao gravar")
    ctx.exec(
        """INSERT INTO card_credits (owner_id, card_id, debt_id, kind, description, credit_date,
               invoice_due_date, amount_cents)
           VALUES (:o, :c, :d, 'renegociacao', 'Valor transferido para renegociação', :t, :due, :a)""",
        c=card_id,
        d=debt.id,
        t=ctx.today,
        due=due,
        a=financed,
    )
    purchase = ctx.one(
        """INSERT INTO card_purchases (owner_id, card_id, kind, description, category_id,
               purchase_date, total_cents, installments_count, financed_principal_cents, debt_id)
           VALUES (:o, :c, 'parcelamento_fatura', :d, :cat, :t, :total, :n, :fin, :debt)
           RETURNING id""",
        c=card_id,
        d=f"Parcelamento da fatura {due.strftime('%m/%Y')}",
        cat=_default_fee_category(ctx),
        t=ctx.today,
        total=total,
        n=count,
        fin=financed,
        debt=debt.id,
    )
    if purchase is None:  # pragma: no cover
        raise RuntimeError("falha ao gravar")
    plan = plan_installments(cycle, ctx.today, Money(total), count, first_invoice_due=first_due)
    _insert_installments(ctx, card_id, purchase.id, plan)
    ctx.audit("fatura", card_id, "renegociar", None, {"due": due, "financed": financed, "total": total})
    return {"debt_id": debt.id, "invoice": invoice_detail(ctx, card_id, due)}


def card_channel_debt_remaining(ctx: Ctx, debt_id: UUID, card_id: UUID) -> tuple[int, int]:
    """Quanto falta de um parcelamento de fatura e quantas parcelas já foram pagas,
    a partir das faturas (paga = fatura quitada)."""
    card = _card(ctx, card_id)
    paid_dues = {i.due_date for i in invoices(ctx, card) if i.status.value in ("paga", "com_credito")}
    rows = ctx.all(
        """SELECT i.amount_cents, i.invoice_due_date FROM card_installments i
           JOIN card_purchases p ON p.id=i.purchase_id AND p.owner_id=i.owner_id
           WHERE i.owner_id=:o AND p.debt_id=:d AND i.status='ativa'""",
        d=debt_id,
    )
    remaining = sum(r.amount_cents for r in rows if r.invoice_due_date not in paid_dues)
    paid_count = sum(1 for r in rows if r.invoice_due_date in paid_dues)
    return remaining, paid_count
