"""Investimentos: cadastro, movimentações, valores informados e rentabilidade.

Sem integração com corretoras: valores atuais são sempre informados pelo usuário,
com data, e marcados como desatualizados depois de 30 dias (F-INV-3).
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from sqlalchemy import Row

from app.api.errors import ApiError
from app.domain.investments import (
    CAPITAL_IN,
    CAPITAL_OUT,
    INCOME,
    Movement,
    Valuation,
    cash_flows,
    position,
    summarize,
    xirr,
)
from app.domain.money import Money
from app.services.base import Ctx, check_version, reject_future, row_dict
from app.services.ledger import _insert_tx, check_account_for_tx

KINDS_BY_CLASS = {
    "renda_fixa": {"aporte", "retirada", "rendimento", "juros", "amortizacao", "taxa"},
    "outros": {"aporte", "retirada", "rendimento", "juros", "dividendo", "amortizacao", "taxa"},
    "renda_variavel": {"compra", "venda", "dividendo", "juros", "rendimento", "taxa"},
}

KIND_LABELS = {
    "aporte": "Aporte",
    "retirada": "Retirada",
    "rendimento": "Rendimento",
    "dividendo": "Dividendo",
    "juros": "Juros",
    "amortizacao": "Amortização",
    "taxa": "Taxa",
    "compra": "Compra",
    "venda": "Venda",
}


def _movements(
    ctx: Ctx, inv_id: UUID, until: date | None = None, exclude: UUID | None = None
) -> list[Movement]:
    return [
        Movement(
            r.movement_date,
            r.kind,
            Money(r.amount_cents),
            Money(r.fees_cents),
            Decimal(r.quantity) if r.quantity is not None else None,
            r.paid_to_account,
        )
        for r in ctx.all(
            "SELECT * FROM investment_movements WHERE owner_id=:o AND investment_id=:i "
            "AND status='ativo' AND (CAST(:u AS date) IS NULL OR movement_date <= :u) "
            "AND (CAST(:x AS uuid) IS NULL OR id <> :x) ORDER BY movement_date, created_at",
            i=inv_id,
            u=until,
            x=exclude,
        )
    ]


def _valuations(ctx: Ctx, inv_id: UUID, until: date | None = None) -> list[Valuation]:
    return [
        Valuation(
            r.valuation_date,
            Money(r.value_cents) if r.value_cents is not None else None,
            Money(r.unit_price_cents) if r.unit_price_cents is not None else None,
        )
        for r in ctx.all(
            "SELECT * FROM investment_valuations WHERE owner_id=:o AND investment_id=:i "
            "AND (CAST(:u AS date) IS NULL OR valuation_date <= :u) ORDER BY valuation_date",
            i=inv_id,
            u=until,
        )
    ]


def _view(ctx: Ctx, inv: Row[Any]) -> dict[str, Any]:
    moves = _movements(ctx, inv.id)
    vals = _valuations(ctx, inv.id)
    rv = inv.asset_class == "renda_variavel"
    s = summarize(moves, vals, variable_income=rv, today=ctx.today)
    rate = xirr(cash_flows(moves, s.current_value, s.value_date))
    out = row_dict(inv)
    out.update(
        invested_cents=s.invested.cents,
        total_contributed_cents=s.total_contributed.cents,
        total_withdrawn_cents=s.total_withdrawn.cents,
        income_received_cents=s.income_received.cents,
        fees_paid_cents=s.fees_paid.cents,
        current_value_cents=s.current_value.cents if s.current_value else None,
        value_date=s.value_date,
        value_is_stale=s.stale,
        estimated_gain_cents=s.estimated_gain.cents if s.estimated_gain else None,
        annual_return=str(rate) if rate is not None else None,
    )
    if rv:
        pos = position(moves)
        out.update(
            quantity=format(pos.quantity.normalize(), "f") if pos.quantity else "0",
            average_price_cents=pos.average_price.cents if pos.average_price else None,
            realized_gain_cents=pos.realized_gain.cents,
        )
    return out


def overview(ctx: Ctx) -> dict[str, Any]:
    rows = ctx.all("SELECT * FROM investments WHERE owner_id=:o ORDER BY is_active DESC, asset_class, name")
    items = [_view(ctx, r) for r in rows]
    active = [i for i in items if i["is_active"]]
    by_class: dict[str, int] = defaultdict(int)
    for i in active:
        by_class[i["asset_class"]] += (
            i["current_value_cents"] if i["current_value_cents"] is not None else i["invested_cents"]
        )
    flows: list[tuple[date, int]] = []
    for r in rows:
        if not r.is_active:
            continue
        moves = _movements(ctx, r.id)
        view = next(i for i in items if i["id"] == r.id)
        flows += cash_flows(
            moves,
            Money(view["current_value_cents"]) if view["current_value_cents"] is not None else None,
            view["value_date"],
        )
    all_valued = all(i["current_value_cents"] is not None for i in active)
    rate = xirr(sorted(flows)) if active and all_valued else None
    return {
        "items": items,
        "totals": {
            "invested_cents": sum(i["invested_cents"] for i in active),
            "current_value_cents": sum(i["current_value_cents"] or 0 for i in active),
            "missing_value_count": sum(1 for i in active if i["current_value_cents"] is None),
            "stale_count": sum(1 for i in active if i["value_is_stale"]),
            "estimated_gain_cents": sum(i["estimated_gain_cents"] or 0 for i in active),
            "income_received_cents": sum(i["income_received_cents"] for i in active),
            "annual_return": str(rate) if rate is not None else None,
        },
        "by_class": [{"asset_class": k, "value_cents": v} for k, v in sorted(by_class.items())],
        "notes": [
            "Os valores atuais são os que você informou e podem estar desatualizados.",
            "O ganho é uma estimativa: depende dos valores informados.",
            "Rentabilidade passada não garante rentabilidade futura.",
        ],
    }


def get_investment(ctx: Ctx, inv_id: UUID) -> dict[str, Any]:
    inv = ctx.require("investments", inv_id, "Investimento")
    out = _view(ctx, inv)
    out["movements"] = [
        {
            **row_dict(r),
            "quantity": str(r.quantity) if r.quantity is not None else None,
            "label": KIND_LABELS[r.kind],
        }
        for r in ctx.all(
            """SELECT m.*, a.name AS account_name FROM investment_movements m
               LEFT JOIN accounts a ON a.id=m.account_id AND a.owner_id=m.owner_id
               WHERE m.owner_id=:o AND m.investment_id=:i ORDER BY m.movement_date DESC, m.created_at DESC""",
            i=inv_id,
        )
    ]
    out["valuations"] = [
        row_dict(r)
        for r in ctx.all(
            "SELECT * FROM investment_valuations WHERE owner_id=:o AND investment_id=:i "
            "ORDER BY valuation_date DESC, created_at DESC",
            i=inv_id,
        )
    ]
    out["allowed_kinds"] = sorted(KINDS_BY_CLASS[inv.asset_class])
    return out


def create_investment(ctx: Ctx, data: dict[str, Any]) -> dict[str, Any]:
    if data["asset_class"] == "renda_variavel" and not data.get("ticker"):
        raise ApiError(422, "Informe o código do ativo (ex.: PETR4).", {"ticker": "Obrigatório."})
    row = ctx.one(
        """INSERT INTO investments (owner_id, asset_class, product_type, name, institution, ticker,
               indexer, rate_description, maturity_date, liquidity, note)
           VALUES (:o, :asset_class, :product_type, :name, :institution, :ticker, :indexer,
               :rate_description, :maturity_date, :liquidity, :note) RETURNING id""",
        asset_class=data["asset_class"],
        product_type=data["product_type"].strip(),
        name=data["name"].strip(),
        institution=data.get("institution"),
        ticker=(data.get("ticker") or "").strip().upper() or None,
        indexer=data.get("indexer"),
        rate_description=data.get("rate_description"),
        maturity_date=data.get("maturity_date"),
        liquidity=data.get("liquidity"),
        note=data.get("note"),
    )
    if row is None:  # pragma: no cover
        raise RuntimeError("falha ao gravar")
    first = data.get("first_movement")
    if first:
        add_movement(ctx, row.id, first)
    return get_investment(ctx, row.id)


def update_investment(ctx: Ctx, inv_id: UUID, data: dict[str, Any]) -> dict[str, Any]:
    inv = ctx.require("investments", inv_id, "Investimento")
    check_version(inv, data.get("version"))
    fields = (
        "product_type",
        "name",
        "institution",
        "ticker",
        "indexer",
        "rate_description",
        "maturity_date",
        "liquidity",
        "is_active",
        "note",
    )
    new = {k: data.get(k, getattr(inv, k)) for k in fields}
    if new["ticker"]:
        new["ticker"] = new["ticker"].strip().upper()
    ctx.exec(
        """UPDATE investments SET product_type=:product_type, name=:name, institution=:institution,
             ticker=:ticker, indexer=:indexer, rate_description=:rate_description,
             maturity_date=:maturity_date, liquidity=:liquidity, is_active=:is_active, note=:note,
             version=version+1, updated_at=now() WHERE id=:id AND owner_id=:o""",
        id=inv_id,
        **new,
    )
    return get_investment(ctx, inv_id)


def add_movement(ctx: Ctx, inv_id: UUID, data: dict[str, Any]) -> dict[str, Any]:
    inv = ctx.require("investments", inv_id, "Investimento")
    kind = data["kind"]
    if kind not in KINDS_BY_CLASS[inv.asset_class]:
        raise ApiError(
            422, "Este tipo de movimento não se aplica a este investimento.", {"kind": "Tipo inválido."}
        )
    on = data["movement_date"]
    reject_future(on, ctx.today, "movement_date", "A data do movimento")
    quantity = data.get("quantity")
    if kind in ("compra", "venda"):
        if quantity is None or Decimal(quantity) <= 0:
            raise ApiError(422, "Informe a quantidade.", {"quantity": "Obrigatória."})
        quantity = Decimal(quantity)
        if kind == "venda":
            current = position(_movements(ctx, inv_id, until=on)).quantity
            if quantity > current:
                raise ApiError(
                    422,
                    f"Você tem {format(current.normalize(), 'f')} cotas nesta data; "
                    "não dá para vender mais que isso.",
                    {"quantity": "Maior que a quantidade em carteira."},
                )
    else:
        quantity = None
    fees = data.get("fees_cents") or 0
    amount = data["amount_cents"]
    if kind in CAPITAL_OUT and fees > amount:
        raise ApiError(422, "As taxas passam do valor recebido.", {"fees_cents": "Taxa maior que o valor."})
    account_id = data.get("account_id")
    if account_id is not None:
        check_account_for_tx(ctx, account_id, on)
    paid_to_account = kind in INCOME and account_id is not None
    if kind in INCOME and account_id is None and data.get("paid_to_account"):
        raise ApiError(422, "Escolha a conta onde o rendimento caiu.", {"account_id": "Obrigatória."})
    row = ctx.one(
        """INSERT INTO investment_movements (owner_id, investment_id, movement_date, kind,
               amount_cents, fees_cents, quantity, paid_to_account, account_id, note)
           VALUES (:o, :i, :d, :k, :a, :f, :q, :p, :acc, :note) RETURNING id""",
        i=inv_id,
        d=on,
        k=kind,
        a=amount,
        f=fees,
        q=quantity,
        p=paid_to_account,
        acc=account_id,
        note=data.get("note"),
    )
    if row is None:  # pragma: no cover
        raise RuntimeError("falha ao gravar")
    if account_id is not None:
        # Dinheiro saindo ou entrando na conta, fora de receitas e despesas (F-INV-5).
        direction: Literal["entrada", "saida"]
        if kind in CAPITAL_IN:
            direction, value = "saida", amount + fees
        elif kind == "taxa":
            direction, value = "saida", amount
        elif kind in CAPITAL_OUT:
            direction, value = "entrada", amount - fees
        else:
            direction, value = "entrada", amount
        if value > 0:
            _insert_tx(
                ctx,
                account_id=account_id,
                direction=direction,
                amount=value,
                on=on,
                kind="investimento",
                description=f"{KIND_LABELS[kind]}: {inv.name}"[:120],
                investment_movement_id=row.id,
            )
    return get_investment(ctx, inv_id)


def cancel_movement(ctx: Ctx, movement_id: UUID) -> dict[str, Any]:
    mv = ctx.require("investment_movements", movement_id, "Movimento")
    if mv.status != "ativo":
        raise ApiError(409, "Este movimento já foi cancelado.")
    if mv.kind == "compra":
        # Cancelar uma compra não pode deixar vendas maiores que a carteira.
        try:
            position(_movements(ctx, mv.investment_id, exclude=movement_id))
        except ValueError as exc:
            raise ApiError(409, "Cancele antes as vendas que dependem desta compra.") from exc
    ctx.exec(
        "UPDATE investment_movements SET status='cancelado', updated_at=now() WHERE id=:id AND owner_id=:o",
        id=movement_id,
    )
    ctx.exec(
        "UPDATE transactions SET status='cancelado', cancelled_at=now(), version=version+1, "
        "updated_at=now() WHERE owner_id=:o AND investment_movement_id=:m AND status='ativo'",
        m=movement_id,
    )
    ctx.audit("movimento_investimento", movement_id, "cancelar")
    return get_investment(ctx, mv.investment_id)


def add_valuation(ctx: Ctx, inv_id: UUID, data: dict[str, Any]) -> dict[str, Any]:
    inv = ctx.require("investments", inv_id, "Investimento")
    on = data.get("valuation_date") or ctx.today
    reject_future(on, ctx.today, "valuation_date", "A data do valor")
    rv = inv.asset_class == "renda_variavel"
    value = data.get("value_cents")
    price = data.get("unit_price_cents")
    if rv and price is None:
        raise ApiError(422, "Informe o preço de cada cota.", {"unit_price_cents": "Obrigatório."})
    if not rv and value is None:
        raise ApiError(422, "Informe o saldo atual do investimento.", {"value_cents": "Obrigatório."})
    ctx.exec(
        """INSERT INTO investment_valuations (owner_id, investment_id, valuation_date, value_cents,
               unit_price_cents, note) VALUES (:o, :i, :d, :v, :p, :n)""",
        i=inv_id,
        d=on,
        v=None if rv else value,
        p=price if rv else None,
        n=data.get("note"),
    )
    return get_investment(ctx, inv_id)


def delete_valuation(ctx: Ctx, valuation_id: UUID) -> dict[str, Any]:
    val = ctx.require("investment_valuations", valuation_id, "Valor informado")
    ctx.exec("DELETE FROM investment_valuations WHERE id=:id AND owner_id=:o", id=valuation_id)
    return get_investment(ctx, val.investment_id)


def value_at(ctx: Ctx, on: date) -> int:
    """Valor da carteira em uma data (último valor informado até ela). Investimentos
    sem valor informado entram pelo valor aportado até a data."""
    total = 0
    for inv in ctx.all("SELECT id, asset_class FROM investments WHERE owner_id=:o"):
        moves = _movements(ctx, inv.id, until=on)
        if not moves:
            continue
        s = summarize(
            moves,
            _valuations(ctx, inv.id, until=on),
            variable_income=inv.asset_class == "renda_variavel",
            today=on,
        )
        total += s.current_value.cents if s.current_value is not None else s.invested.cents
    return total
