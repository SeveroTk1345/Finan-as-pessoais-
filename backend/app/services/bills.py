"""Contas a pagar e a receber, com recorrência.

* A conta a pagar não é despesa: a despesa nasce quando o pagamento é registrado
  (F13). A situação (pendente, vencida, parcial, paga) é derivada dos pagamentos.
* Recorrências geram ocorrências calculadas na hora; só são gravadas ao serem pagas,
  editadas ou canceladas (F8).
* Vencidas continuam aparecendo até serem pagas ou canceladas (F12).
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import Row

from app.api.errors import ApiError
from app.domain.bills import bill_status, due_soon
from app.domain.dates import add_months, monthly_occurrence
from app.domain.money import Money
from app.services.base import Ctx, check_version, reject_future, row_dict
from app.services.ledger import _check_bill_payment_limit, _insert_tx, check_category

OVERDUE_LOOKBACK_MONTHS = 12


def occurrences(rule: Row[Any], start: date, end: date) -> Iterator[date]:
    """Datas de vencimento de uma regra dentro de [start, end], sempre a partir da
    data original (sem deslizar o dia)."""
    last = min(end, rule.end_date) if rule.end_date else end
    k = 0
    if rule.frequency in ("mensal", "anual"):
        step = 1 if rule.frequency == "mensal" else 12
        if start > rule.anchor_date:
            months = (start.year - rule.anchor_date.year) * 12 + start.month - rule.anchor_date.month
            k = max(0, months // step - 1)
        while True:
            d = monthly_occurrence(rule.anchor_date, k * step)
            if d > last:
                return
            if d >= start:
                yield d
            k += 1
    else:  # semanal
        if start > rule.anchor_date:
            k = max(0, (start - rule.anchor_date).days // 7 - 1)
        while True:
            d = rule.anchor_date + timedelta(days=7 * k)
            if d > last:
                return
            if d >= start:
                yield d
            k += 1


def _bill_view(ctx: Ctx, row: dict[str, Any]) -> dict[str, Any]:
    paid = int(row.get("paid_cents") or 0)
    status = bill_status(
        amount=Money(row["amount_cents"]),
        paid=Money(paid),
        due=row["due_date"],
        today=ctx.today,
        cancelled=row["status"] == "cancelada",
    )
    row["paid_cents"] = paid
    row["remaining_cents"] = 0 if status.value == "cancelada" else max(row["amount_cents"] - paid, 0)
    row["situation"] = status.value
    row["due_soon"] = status.value in ("pendente", "parcialmente_paga") and due_soon(
        row["due_date"], ctx.today
    )
    return row


BILL_SQL = """
SELECT b.*, c.name AS category_name,
       (SELECT coalesce(sum(t.amount_cents), 0) FROM transactions t
         WHERE t.owner_id = b.owner_id AND t.bill_id = b.id AND t.status = 'ativo')::bigint
         AS paid_cents
FROM bills b
LEFT JOIN categories c ON c.id = b.category_id AND c.owner_id = b.owner_id
WHERE b.owner_id = :o
"""


def list_bills(
    ctx: Ctx, *, kind: str, start: date, end: date, include_overdue: bool = True
) -> list[dict[str, Any]]:
    """Contas do período + vencidas não resolvidas de antes + ocorrências virtuais."""
    rows = ctx.all(
        f"""{BILL_SQL} AND b.kind = :k AND (
              (b.due_date BETWEEN :s AND :e)
              OR (:ov AND b.due_date < :s AND b.status = 'aberta'
                  AND b.amount_cents > (SELECT coalesce(sum(t.amount_cents), 0) FROM transactions t
                       WHERE t.owner_id = b.owner_id AND t.bill_id = b.id AND t.status = 'ativo')))
            ORDER BY b.due_date, b.description""",  # noqa: S608
        k=kind,
        s=start,
        e=end,
        ov=include_overdue,
    )
    items = [_bill_view(ctx, row_dict(r)) for r in rows]
    materialized = {(r["rule_id"], r["occurrence_date"]) for r in items if r["rule_id"]}
    materialized |= {
        (r.rule_id, r.occurrence_date)
        for r in ctx.all(
            "SELECT rule_id, occurrence_date FROM bills WHERE owner_id=:o AND rule_id IS NOT NULL"
        )
    }

    lookback = add_months(start, -OVERDUE_LOOKBACK_MONTHS) if include_overdue else start
    for rule in ctx.all(
        """SELECT r.*, c.name AS category_name FROM recurring_rules r
           LEFT JOIN categories c ON c.id = r.category_id AND c.owner_id = r.owner_id
           WHERE r.owner_id=:o AND r.kind=:k AND r.is_active""",
        k=kind,
    ):
        for occ in occurrences(rule, lookback, end):
            if (rule.id, occ) in materialized:
                continue
            if occ < start and occ >= ctx.today:
                continue
            if occ < start and occ < ctx.today and not include_overdue:
                continue
            items.append(
                _bill_view(
                    ctx,
                    {
                        "id": None,
                        "kind": rule.kind,
                        "description": rule.description,
                        "amount_cents": rule.amount_cents,
                        "due_date": occ,
                        "category_id": rule.category_id,
                        "category_name": rule.category_name,
                        "account_id": rule.account_id,
                        "expense_nature": rule.expense_nature,
                        "rule_id": rule.id,
                        "occurrence_date": occ,
                        "is_main_income": rule.is_main_income,
                        "status": "aberta",
                        "note": None,
                        "version": None,
                        "paid_cents": 0,
                        "virtual": True,
                    },
                )
            )
    for it in items:
        it.setdefault("virtual", False)
    items.sort(key=lambda x: (x["due_date"], x["description"]))
    return items


def create_bill(ctx: Ctx, data: dict[str, Any]) -> dict[str, Any]:
    check_category(ctx, data.get("category_id"), "receita" if data["kind"] == "receber" else "despesa")
    _check_account(ctx, data.get("account_id"))
    row = ctx.one(
        """INSERT INTO bills (owner_id, kind, description, amount_cents, due_date, category_id,
               account_id, expense_nature, is_main_income, note)
           VALUES (:o, :kind, :description, :amount_cents, :due_date, :category_id, :account_id,
               :expense_nature, :is_main_income, :note) RETURNING id""",
        kind=data["kind"],
        description=data["description"].strip(),
        amount_cents=data["amount_cents"],
        due_date=data["due_date"],
        category_id=data.get("category_id"),
        account_id=data.get("account_id"),
        expense_nature=data.get("expense_nature") if data["kind"] == "pagar" else None,
        is_main_income=bool(data.get("is_main_income")) and data["kind"] == "receber",
        note=data.get("note"),
    )
    if row is None:  # pragma: no cover - INSERT/UPDATE ... RETURNING sempre retorna
        raise RuntimeError("falha ao gravar")
    return get_bill(ctx, row.id)


def _check_account(ctx: Ctx, account_id: UUID | None) -> None:
    if (
        account_id is not None
        and ctx.one("SELECT 1 FROM accounts WHERE id=:id AND owner_id=:o", id=account_id) is None
    ):
        raise ApiError(422, "Conta não encontrada.", {"account_id": "Escolha outra conta."})


def get_bill(ctx: Ctx, bill_id: UUID) -> dict[str, Any]:
    row = ctx.one(f"{BILL_SQL} AND b.id = :id", id=bill_id)
    if row is None:
        from app.api.errors import not_found

        raise not_found("Conta a pagar")
    out = _bill_view(ctx, row_dict(row))
    out["virtual"] = False
    out["payments"] = [
        row_dict(p)
        for p in ctx.all(
            """SELECT t.id, t.amount_cents, t.tx_date, t.status, a.name AS account_name
               FROM transactions t JOIN accounts a ON a.id = t.account_id AND a.owner_id = t.owner_id
               WHERE t.owner_id=:o AND t.bill_id=:b ORDER BY t.tx_date, t.created_at""",
            b=bill_id,
        )
    ]
    return out


def update_bill(ctx: Ctx, bill_id: UUID, data: dict[str, Any]) -> dict[str, Any]:
    bill = ctx.require("bills", bill_id, "Conta a pagar")
    check_version(bill, data.get("version"))
    if bill.status == "cancelada":
        raise ApiError(409, "Conta cancelada não pode ser editada.")
    new = {
        "description": (data.get("description") or bill.description).strip(),
        "amount_cents": data.get("amount_cents", bill.amount_cents),
        "due_date": data.get("due_date", bill.due_date),
        "category_id": data.get("category_id", bill.category_id),
        "account_id": data.get("account_id", bill.account_id),
        "expense_nature": data.get("expense_nature", bill.expense_nature),
        "note": data.get("note", bill.note),
    }
    check_category(ctx, new["category_id"], "receita" if bill.kind == "receber" else "despesa")
    _check_account(ctx, new["account_id"])
    paid = int(
        ctx.scalar(
            "SELECT coalesce(sum(amount_cents),0) FROM transactions WHERE owner_id=:o "
            "AND bill_id=:b AND status='ativo'",
            b=bill_id,
        )
    )
    if new["amount_cents"] < paid:
        raise ApiError(
            422,
            "O valor não pode ser menor do que já foi pago.",
            {"amount_cents": "Menor que o valor pago."},
        )
    ctx.exec(
        """UPDATE bills SET description=:description, amount_cents=:amount_cents,
             due_date=:due_date, category_id=:category_id, account_id=:account_id,
             expense_nature=:expense_nature, note=:note, version=version+1, updated_at=now()
           WHERE id=:id AND owner_id=:o""",
        id=bill_id,
        **new,
    )
    ctx.audit("conta_a_pagar", bill_id, "editar", {k: getattr(bill, k) for k in new}, new)
    return get_bill(ctx, bill_id)


def materialize(ctx: Ctx, rule_id: UUID, occurrence: date) -> UUID:
    """Grava uma ocorrência virtual (para pagar, editar ou cancelar). Idempotente."""
    rule = ctx.require("recurring_rules", rule_id, "Recorrência")
    if occurrence not in set(occurrences(rule, occurrence, occurrence)):
        raise ApiError(422, "Data que não pertence a esta recorrência.")
    existing = ctx.scalar(
        "SELECT id FROM bills WHERE owner_id=:o AND rule_id=:r AND occurrence_date=:d",
        r=rule_id,
        d=occurrence,
    )
    if existing:
        return UUID(str(existing))
    new_id = ctx.scalar(
        """INSERT INTO bills (owner_id, kind, description, amount_cents, due_date, category_id,
               account_id, expense_nature, rule_id, occurrence_date, is_main_income)
           VALUES (:o, :k, :d, :a, :due, :c, :acc, :n, :r, :due, :main) RETURNING id""",
        k=rule.kind,
        d=rule.description,
        a=rule.amount_cents,
        due=occurrence,
        c=rule.category_id,
        acc=rule.account_id,
        n=rule.expense_nature,
        r=rule_id,
        main=rule.is_main_income,
    )
    return UUID(str(new_id))


def pay_bill(ctx: Ctx, bill_id: UUID, data: dict[str, Any]) -> dict[str, Any]:
    """Registra pagamento (ou recebimento) integral ou parcial."""
    bill = ctx.require("bills", bill_id, "Conta a pagar")
    if bill.status == "cancelada":
        raise ApiError(409, "Esta conta foi cancelada.")
    on = data.get("tx_date") or ctx.today
    reject_future(on, ctx.today, "tx_date", "O pagamento")
    paid = int(
        ctx.scalar(
            "SELECT coalesce(sum(amount_cents),0) FROM transactions WHERE owner_id=:o "
            "AND bill_id=:b AND status='ativo'",
            b=bill_id,
        )
    )
    amount = data.get("amount_cents") or (bill.amount_cents - paid)
    if amount <= 0:
        raise ApiError(409, "Esta conta já está paga.")
    _check_bill_payment_limit(ctx, bill_id, amount)
    account_id = data.get("account_id") or bill.account_id
    if account_id is None:
        raise ApiError(422, "Escolha a conta usada no pagamento.", {"account_id": "Escolha a conta."})
    receiving = bill.kind == "receber"
    tx = _insert_tx(
        ctx,
        account_id=account_id,
        direction="entrada" if receiving else "saida",
        amount=amount,
        on=on,
        kind="receita" if receiving else "despesa",
        description=bill.description,
        category_id=bill.category_id,
        expense_nature=None if receiving else bill.expense_nature,
        bill_id=bill_id,
    )
    return {"bill": get_bill(ctx, bill_id), "transaction": tx}


def cancel_bill(ctx: Ctx, bill_id: UUID) -> dict[str, Any]:
    bill = ctx.require("bills", bill_id, "Conta a pagar")
    if bill.status == "cancelada":
        raise ApiError(409, "Esta conta já está cancelada.")
    ctx.exec(
        "UPDATE bills SET status='cancelada', cancelled_at=now(), version=version+1, "
        "updated_at=now() WHERE id=:id AND owner_id=:o",
        id=bill_id,
    )
    ctx.audit("conta_a_pagar", bill_id, "cancelar")
    return get_bill(ctx, bill_id)


# --- recorrências ----------------------------------------------------------------


def list_rules(ctx: Ctx) -> list[dict[str, Any]]:
    return [
        row_dict(r)
        for r in ctx.all(
            """SELECT r.*, c.name AS category_name FROM recurring_rules r
               LEFT JOIN categories c ON c.id = r.category_id AND c.owner_id = r.owner_id
               WHERE r.owner_id=:o ORDER BY r.is_active DESC, r.kind, r.description"""
        )
    ]


def create_rule(ctx: Ctx, data: dict[str, Any]) -> dict[str, Any]:
    check_category(ctx, data.get("category_id"), "receita" if data["kind"] == "receber" else "despesa")
    _check_account(ctx, data.get("account_id"))
    row = ctx.one(
        """INSERT INTO recurring_rules (owner_id, kind, description, amount_cents, category_id,
               account_id, expense_nature, frequency, anchor_date, end_date, is_main_income)
           VALUES (:o, :kind, :description, :amount_cents, :category_id, :account_id,
               :expense_nature, :frequency, :anchor_date, :end_date, :is_main_income)
           RETURNING *""",
        kind=data["kind"],
        description=data["description"].strip(),
        amount_cents=data["amount_cents"],
        category_id=data.get("category_id"),
        account_id=data.get("account_id"),
        expense_nature=data.get("expense_nature") if data["kind"] == "pagar" else None,
        frequency=data["frequency"],
        anchor_date=data["anchor_date"],
        end_date=data.get("end_date"),
        is_main_income=bool(data.get("is_main_income")) and data["kind"] == "receber",
    )
    if row is None:  # pragma: no cover - INSERT/UPDATE ... RETURNING sempre retorna
        raise RuntimeError("falha ao gravar")
    return row_dict(row)


def update_rule(ctx: Ctx, rule_id: UUID, data: dict[str, Any]) -> dict[str, Any]:
    """Mudanças valem para as próximas ocorrências; as já gravadas não mudam."""
    rule = ctx.require("recurring_rules", rule_id, "Recorrência")
    check_version(rule, data.get("version"))
    new = {
        "description": (data.get("description") or rule.description).strip(),
        "amount_cents": data.get("amount_cents", rule.amount_cents),
        "category_id": data.get("category_id", rule.category_id),
        "account_id": data.get("account_id", rule.account_id),
        "end_date": data.get("end_date", rule.end_date),
        "is_active": data.get("is_active", rule.is_active),
    }
    check_category(ctx, new["category_id"], "receita" if rule.kind == "receber" else "despesa")
    _check_account(ctx, new["account_id"])
    if new["end_date"] is not None and new["end_date"] < rule.anchor_date:
        raise ApiError(422, "A data final é anterior à primeira ocorrência.", {"end_date": "Data inválida."})
    row = ctx.one(
        """UPDATE recurring_rules SET description=:description, amount_cents=:amount_cents,
             category_id=:category_id, account_id=:account_id, end_date=:end_date,
             is_active=:is_active, version=version+1, updated_at=now()
           WHERE id=:id AND owner_id=:o RETURNING *""",
        id=rule_id,
        **new,
    )
    if row is None:  # pragma: no cover - INSERT/UPDATE ... RETURNING sempre retorna
        raise RuntimeError("falha ao gravar")
    return row_dict(row)


def reject_future_payment(on: date, today: date) -> None:
    reject_future(on, today, "tx_date", "O pagamento")
