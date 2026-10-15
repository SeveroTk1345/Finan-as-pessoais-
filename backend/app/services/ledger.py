"""Contas, categorias, lançamentos e transferências.

Saldo da conta = saldo inicial + entradas - saídas dos lançamentos ativos com data
igual ou posterior à data do saldo inicial (F17: o saldo inicial vale para o começo
daquele dia; lançamentos anteriores a ele são recusados).
"""

from __future__ import annotations

from datetime import date
from typing import Any, Literal
from uuid import UUID, uuid4

from sqlalchemy import Row

from app.api.errors import ApiError, not_found
from app.domain.money import Money
from app.services.base import Ctx, check_version, reject_future, row_dict

BALANCE_SQL = """
    (a.initial_balance_cents + COALESCE((
        SELECT SUM(CASE WHEN t.direction = 'entrada' THEN t.amount_cents ELSE -t.amount_cents END)
        FROM transactions t
        WHERE t.owner_id = a.owner_id AND t.account_id = a.id AND t.status = 'ativo'
          AND t.tx_date >= a.initial_balance_date AND t.tx_date <= :until
    ), 0))::bigint
"""

ACCOUNT_KINDS = ("corrente", "poupanca", "especie", "outra")


# --- contas ----------------------------------------------------------------------


def list_accounts(
    ctx: Ctx, *, include_inactive: bool = True, until: date | None = None
) -> list[dict[str, Any]]:
    rows = ctx.all(
        f"""SELECT a.*, {BALANCE_SQL} AS balance_cents,
                   (SELECT count(*) FROM transactions t WHERE t.owner_id = a.owner_id
                      AND t.account_id = a.id) AS tx_count
            FROM accounts a WHERE a.owner_id = :o
              AND (:inactive OR a.is_active)
            ORDER BY a.is_active DESC, a.name, a.id""",  # noqa: S608
        until=until or date.max,
        inactive=include_inactive,
    )
    return [row_dict(r) for r in rows]


def get_account(ctx: Ctx, account_id: UUID) -> dict[str, Any]:
    row = ctx.one(
        f"SELECT a.*, {BALANCE_SQL} AS balance_cents FROM accounts a "  # noqa: S608
        "WHERE a.id = :id AND a.owner_id = :o",
        id=account_id,
        until=date.max,
    )
    if row is None:
        raise not_found("Conta")
    return row_dict(row)


def create_account(ctx: Ctx, data: dict[str, Any]) -> dict[str, Any]:
    daily = data.get("daily_use")
    if daily is None:
        daily = data["kind"] != "outra"  # F10
    row = ctx.one(
        """INSERT INTO accounts (owner_id, name, institution, kind, initial_balance_cents,
               initial_balance_date, daily_use, note)
           VALUES (:o, :name, :inst, :kind, :bal, :d, :daily, :note) RETURNING id""",
        name=data["name"].strip(),
        inst=data.get("institution"),
        kind=data["kind"],
        bal=data["initial_balance_cents"],
        d=data["initial_balance_date"],
        daily=daily,
        note=data.get("note"),
    )
    if row is None:  # pragma: no cover - INSERT/UPDATE ... RETURNING sempre retorna
        raise RuntimeError("falha ao gravar")
    return get_account(ctx, row.id)


def update_account(ctx: Ctx, account_id: UUID, data: dict[str, Any]) -> dict[str, Any]:
    before = ctx.require("accounts", account_id, "Conta")
    check_version(before, data.get("version"))
    new_date = data.get("initial_balance_date", before.initial_balance_date)
    if new_date != before.initial_balance_date:
        earliest = ctx.scalar(
            "SELECT min(tx_date) FROM transactions WHERE owner_id=:o AND account_id=:a AND status='ativo'",
            a=account_id,
        )
        if earliest is not None and new_date > earliest:
            raise ApiError(
                422,
                "Há lançamentos antes dessa data. Escolha uma data igual ou anterior "
                f"a {earliest.strftime('%d/%m/%Y')}.",
                {"initial_balance_date": "Data posterior a lançamentos existentes."},
            )
    fields = {
        "name": data.get("name", before.name),
        "institution": data.get("institution", before.institution),
        "kind": data.get("kind", before.kind),
        "initial_balance_cents": data.get("initial_balance_cents", before.initial_balance_cents),
        "initial_balance_date": new_date,
        "daily_use": data.get("daily_use", before.daily_use),
        "is_active": data.get("is_active", before.is_active),
        "note": data.get("note", before.note),
    }
    ctx.exec(
        """UPDATE accounts SET name=:name, institution=:institution, kind=:kind,
             initial_balance_cents=:initial_balance_cents,
             initial_balance_date=:initial_balance_date, daily_use=:daily_use,
             is_active=:is_active, note=:note, version=version+1, updated_at=now()
           WHERE id=:id AND owner_id=:o""",
        id=account_id,
        **fields,
    )
    ctx.audit("conta", account_id, "editar", row_dict(before), fields)
    return get_account(ctx, account_id)


def delete_account(ctx: Ctx, account_id: UUID) -> None:
    ctx.require("accounts", account_id, "Conta")
    used = ctx.scalar(
        """SELECT EXISTS (SELECT 1 FROM transactions WHERE owner_id=:o AND account_id=:a)
             OR EXISTS (SELECT 1 FROM bills WHERE owner_id=:o AND account_id=:a)
             OR EXISTS (SELECT 1 FROM recurring_rules WHERE owner_id=:o AND account_id=:a)
             OR EXISTS (SELECT 1 FROM investment_movements WHERE owner_id=:o AND account_id=:a)""",
        a=account_id,
    )
    if used:
        raise ApiError(
            409,
            "Esta conta tem lançamentos e não pode ser excluída. Você pode desativá-la: "
            "ela some das listas, mas o histórico fica guardado.",
        )
    ctx.exec("DELETE FROM accounts WHERE id=:id AND owner_id=:o", id=account_id)


def adjust_balance(
    ctx: Ctx, account_id: UUID, *, real_balance_cents: int, on: date, note: str | None
) -> dict[str, Any] | None:
    """Conciliação: cria um lançamento de ajuste com a diferença entre o saldo do app
    e o saldo real informado. Ajuste não é receita nem despesa."""
    acc = ctx.require("accounts", account_id, "Conta")
    reject_future(on, ctx.today, "data")
    if on < acc.initial_balance_date:
        raise ApiError(422, "A data é anterior ao saldo inicial da conta.", {"data": "Data inválida."})
    current = ctx.scalar(
        f"SELECT {BALANCE_SQL} FROM accounts a WHERE a.id=:id AND a.owner_id=:o",  # noqa: S608
        id=account_id,
        until=on,
    )
    diff = real_balance_cents - int(current)
    if diff == 0:
        return None
    return _insert_tx(
        ctx,
        account_id=account_id,
        direction="entrada" if diff > 0 else "saida",
        amount=abs(diff),
        on=on,
        kind="ajuste",
        description="Ajuste de saldo",
        note=note,
    )


# --- categorias ------------------------------------------------------------------


def list_categories(ctx: Ctx) -> list[dict[str, Any]]:
    return [
        row_dict(r)
        for r in ctx.all(
            "SELECT * FROM categories WHERE owner_id=:o ORDER BY kind, is_archived, position, name"
        )
    ]


def create_category(ctx: Ctx, name: str, kind: str) -> dict[str, Any]:
    exists = ctx.scalar(
        "SELECT 1 FROM categories WHERE owner_id=:o AND kind=:k AND lower(name)=lower(:n)",
        k=kind,
        n=name.strip(),
    )
    if exists:
        raise ApiError(409, "Já existe uma categoria com esse nome.", {"name": "Nome repetido."})
    row = ctx.one(
        "INSERT INTO categories (owner_id, name, kind, position) VALUES (:o, :n, :k, "
        "(SELECT coalesce(max(position), 0) + 1 FROM categories WHERE owner_id=:o AND kind=:k)) "
        "RETURNING *",
        n=name.strip(),
        k=kind,
    )
    if row is None:  # pragma: no cover - INSERT/UPDATE ... RETURNING sempre retorna
        raise RuntimeError("falha ao gravar")
    return row_dict(row)


def update_category(
    ctx: Ctx, category_id: UUID, *, name: str | None, archived: bool | None
) -> dict[str, Any]:
    cat = ctx.require("categories", category_id, "Categoria")
    new_name = name.strip() if name is not None else cat.name
    if new_name.lower() != cat.name.lower() and ctx.scalar(
        "SELECT 1 FROM categories WHERE owner_id=:o AND kind=:k AND lower(name)=lower(:n)",
        k=cat.kind,
        n=new_name,
    ):
        raise ApiError(409, "Já existe uma categoria com esse nome.", {"name": "Nome repetido."})
    row = ctx.one(
        "UPDATE categories SET name=:n, is_archived=:a, updated_at=now() "
        "WHERE id=:id AND owner_id=:o RETURNING *",
        n=new_name,
        a=cat.is_archived if archived is None else archived,
        id=category_id,
    )
    if row is None:  # pragma: no cover - INSERT/UPDATE ... RETURNING sempre retorna
        raise RuntimeError("falha ao gravar")
    return row_dict(row)


def check_category(ctx: Ctx, category_id: UUID | None, kind: str) -> None:
    if category_id is None:
        return
    cat = ctx.one("SELECT kind FROM categories WHERE id=:id AND owner_id=:o", id=category_id)
    if cat is None:
        raise ApiError(422, "Categoria não encontrada.", {"category_id": "Escolha outra categoria."})
    if cat.kind != kind:
        label = "receita" if kind == "receita" else "despesa"
        raise ApiError(422, f"Escolha uma categoria de {label}.", {"category_id": "Categoria de outro tipo."})


# --- lançamentos -----------------------------------------------------------------

Direction = Literal["entrada", "saida"]


def check_account_for_tx(ctx: Ctx, account_id: UUID, on: date) -> Row[Any]:
    acc = ctx.one("SELECT * FROM accounts WHERE id=:id AND owner_id=:o", id=account_id)
    if acc is None:
        raise ApiError(422, "Conta não encontrada.", {"account_id": "Escolha outra conta."})
    if not acc.is_active:
        raise ApiError(422, "Esta conta está desativada.", {"account_id": "Conta desativada."})
    if on < acc.initial_balance_date:
        raise ApiError(
            422,
            "A data é anterior ao saldo inicial desta conta "
            f"({acc.initial_balance_date.strftime('%d/%m/%Y')}).",
            {"tx_date": "Data anterior ao saldo inicial."},
        )
    return acc


def _insert_tx(
    ctx: Ctx,
    *,
    account_id: UUID,
    direction: Direction,
    amount: int,
    on: date,
    kind: str,
    description: str,
    category_id: UUID | None = None,
    expense_nature: str | None = None,
    note: str | None = None,
    **links: Any,
) -> dict[str, Any]:
    check_account_for_tx(ctx, account_id, on)
    Money(amount)  # valida tipo e limite
    if amount <= 0:
        raise ApiError(422, "O valor precisa ser maior que zero.", {"amount_cents": "Valor inválido."})
    cols = {
        "account_id": account_id,
        "direction": direction,
        "amount_cents": amount,
        "tx_date": on,
        "kind": kind,
        "description": description.strip(),
        "category_id": category_id,
        "expense_nature": expense_nature,
        "note": note,
        **links,
    }
    names = ", ".join(cols)
    values = ", ".join(f":{k}" for k in cols)
    row = ctx.one(
        f"INSERT INTO transactions (owner_id, {names}) VALUES (:o, {values}) RETURNING *",  # noqa: S608
        **cols,
    )
    if row is None:  # pragma: no cover - INSERT/UPDATE ... RETURNING sempre retorna
        raise RuntimeError("falha ao gravar")
    return row_dict(row)


def create_transaction(ctx: Ctx, data: dict[str, Any]) -> dict[str, Any]:
    """Receita, despesa ou reembolso realizados."""
    kind = data["kind"]
    reject_future(data["tx_date"], ctx.today, "tx_date", "Um lançamento realizado")
    category_kind = "receita" if kind == "receita" else "despesa"
    check_category(ctx, data.get("category_id"), category_kind)
    return _insert_tx(
        ctx,
        account_id=data["account_id"],
        direction="entrada" if kind in ("receita", "reembolso") else "saida",
        amount=data["amount_cents"],
        on=data["tx_date"],
        kind=kind,
        description=data["description"],
        category_id=data.get("category_id"),
        expense_nature=data.get("expense_nature") if kind == "despesa" else None,
        note=data.get("note"),
    )


TX_LIST_SQL = """
SELECT t.*, a.name AS account_name, c.name AS category_name,
       other.account_id AS transfer_other_account_id, oa.name AS transfer_other_account_name
FROM transactions t
JOIN accounts a ON a.id = t.account_id AND a.owner_id = t.owner_id
LEFT JOIN categories c ON c.id = t.category_id AND c.owner_id = t.owner_id
LEFT JOIN transactions other ON other.transfer_id = t.transfer_id AND other.id <> t.id
     AND other.owner_id = t.owner_id
LEFT JOIN accounts oa ON oa.id = other.account_id AND oa.owner_id = t.owner_id
WHERE t.owner_id = :o
"""


def list_transactions(
    ctx: Ctx,
    *,
    start: date | None,
    end: date | None,
    account_id: UUID | None,
    kind: str | None,
    category_id: UUID | None,
    search: str | None,
    include_cancelled: bool,
    limit: int,
    offset: int,
) -> dict[str, Any]:
    where = []
    params: dict[str, Any] = {}
    if start:
        where.append("t.tx_date >= :start")
        params["start"] = start
    if end:
        where.append("t.tx_date <= :end")
        params["end"] = end
    if account_id:
        where.append("t.account_id = :acc")
        params["acc"] = account_id
    if kind:
        where.append("t.kind = :kind")
        params["kind"] = kind
    if category_id:
        where.append("t.category_id = :cat")
        params["cat"] = category_id
    if search:
        where.append("(t.description ILIKE :q OR coalesce(t.note, '') ILIKE :q)")
        escaped = search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        params["q"] = f"%{escaped}%"
    if not include_cancelled:
        where.append("t.status = 'ativo'")
    cond = "".join(f" AND {w}" for w in where)
    total = ctx.scalar(f"SELECT count(*) FROM transactions t WHERE t.owner_id=:o{cond}", **params)  # noqa: S608
    rows = ctx.all(
        f"{TX_LIST_SQL}{cond} ORDER BY t.tx_date DESC, t.created_at DESC, t.id LIMIT :limit OFFSET :offset",
        limit=limit,
        offset=offset,
        **params,
    )
    return {"items": [row_dict(r) for r in rows], "total": total}


def get_transaction(ctx: Ctx, tx_id: UUID) -> dict[str, Any]:
    row = ctx.one(f"{TX_LIST_SQL} AND t.id = :id", id=tx_id)
    if row is None:
        raise not_found("Lançamento")
    out = row_dict(row)
    out["history"] = [
        row_dict(h)
        for h in ctx.all(
            "SELECT action, before_data, after_data, created_at FROM audit_log "
            "WHERE owner_id=:o AND entity='lancamento' AND entity_id=:id ORDER BY created_at",
            id=tx_id,
        )
    ]
    return out


# Pagamentos de fatura e de dívida mexem em outros saldos: são corrigidos cancelando
# e registrando de novo, para as validações de limite valerem outra vez.
EDITABLE_KINDS = {"receita", "despesa", "reembolso", "ajuste"}


def update_transaction(ctx: Ctx, tx_id: UUID, data: dict[str, Any]) -> dict[str, Any]:
    """Edição com histórico (F9). Transferências e movimentos de investimento são
    corrigidos cancelando e lançando de novo, porque envolvem mais de um registro."""
    tx = ctx.require("transactions", tx_id, "Lançamento")
    check_version(tx, data.get("version"))
    if tx.status != "ativo":
        raise ApiError(409, "Lançamento cancelado não pode ser editado.")
    if tx.kind not in EDITABLE_KINDS:
        raise ApiError(
            409,
            "Para corrigir este lançamento, cancele-o e registre de novo.",
        )
    new = {
        "account_id": data.get("account_id", tx.account_id),
        "amount_cents": data.get("amount_cents", tx.amount_cents),
        "tx_date": data.get("tx_date", tx.tx_date),
        "description": (data.get("description") or tx.description).strip(),
        "category_id": data.get("category_id", tx.category_id),
        "expense_nature": data.get("expense_nature", tx.expense_nature),
        "note": data.get("note", tx.note),
    }
    reject_future(new["tx_date"], ctx.today, "tx_date", "Um lançamento realizado")
    if tx.kind in ("receita", "despesa", "reembolso"):
        check_category(ctx, new["category_id"], "receita" if tx.kind == "receita" else "despesa")
    else:
        new["category_id"] = tx.category_id
    check_account_for_tx(ctx, new["account_id"], new["tx_date"])
    if tx.bill_id is not None:
        _check_bill_payment_limit(ctx, tx.bill_id, new["amount_cents"], exclude_tx=tx_id)
    ctx.exec(
        """UPDATE transactions SET account_id=:account_id, amount_cents=:amount_cents,
             tx_date=:tx_date, description=:description, category_id=:category_id,
             expense_nature=:expense_nature, note=:note, version=version+1, updated_at=now()
           WHERE id=:id AND owner_id=:o""",
        id=tx_id,
        **new,
    )
    before = {k: getattr(tx, k) for k in new}
    ctx.audit("lancamento", tx_id, "editar", before, new)
    return get_transaction(ctx, tx_id)


def cancel_transaction(ctx: Ctx, tx_id: UUID) -> dict[str, Any]:
    """Cancelamento preserva o registro (F9). Transferência cancela as duas pernas."""
    tx = ctx.require("transactions", tx_id, "Lançamento")
    if tx.status != "ativo":
        raise ApiError(409, "Este lançamento já está cancelado.")
    if tx.kind == "investimento":
        raise ApiError(409, "Cancele este lançamento pela área de Investimentos.")
    ids = [tx_id]
    if tx.transfer_id is not None:
        ids = [
            r.id
            for r in ctx.all(
                "SELECT id FROM transactions WHERE owner_id=:o AND transfer_id=:t", t=tx.transfer_id
            )
        ]
    for i in ids:
        ctx.exec(
            "UPDATE transactions SET status='cancelado', cancelled_at=now(), "
            "version=version+1, updated_at=now() WHERE id=:id AND owner_id=:o",
            id=i,
        )
        ctx.audit("lancamento", i, "cancelar")
    if tx.debt_id is not None:
        from app.services.debts import refresh_debt_status

        refresh_debt_status(ctx, tx.debt_id)
    return get_transaction(ctx, tx_id)


def create_transfer(ctx: Ctx, data: dict[str, Any]) -> dict[str, Any]:
    """Transferência entre contas próprias: dois lançamentos ligados, fora de receitas
    e despesas (F14). O patrimônio total não muda."""
    if data["from_account_id"] == data["to_account_id"]:
        raise ApiError(422, "Escolha contas diferentes.", {"to_account_id": "Mesma conta de origem."})
    reject_future(data["tx_date"], ctx.today, "tx_date", "Uma transferência realizada")
    transfer_id = uuid4()
    desc = data.get("description") or "Transferência"
    out = _insert_tx(
        ctx,
        account_id=data["from_account_id"],
        direction="saida",
        amount=data["amount_cents"],
        on=data["tx_date"],
        kind="transferencia",
        description=desc,
        note=data.get("note"),
        transfer_id=transfer_id,
    )
    inn = _insert_tx(
        ctx,
        account_id=data["to_account_id"],
        direction="entrada",
        amount=data["amount_cents"],
        on=data["tx_date"],
        kind="transferencia",
        description=desc,
        note=data.get("note"),
        transfer_id=transfer_id,
    )
    return {"transfer_id": transfer_id, "saida": out, "entrada": inn}


def _check_bill_payment_limit(ctx: Ctx, bill_id: UUID, amount: int, exclude_tx: UUID | None = None) -> None:
    bill = ctx.require("bills", bill_id, "Conta a pagar")
    paid = ctx.scalar(
        "SELECT coalesce(sum(amount_cents), 0) FROM transactions WHERE owner_id=:o "
        "AND bill_id=:b AND status='ativo' AND (CAST(:x AS uuid) IS NULL OR id <> :x)",
        b=bill_id,
        x=exclude_tx,
    )
    if int(paid) + amount > bill.amount_cents:
        left = Money(bill.amount_cents - int(paid))
        from app.domain.money import format_brl

        raise ApiError(
            422,
            f"O valor passa do que falta pagar ({format_brl(left)}).",
            {"amount_cents": "Valor maior que o restante."},
        )
