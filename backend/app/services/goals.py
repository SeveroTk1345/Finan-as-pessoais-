"""Metas financeiras."""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import Row

from app.api.errors import ApiError
from app.domain.goals import goal_progress
from app.domain.money import Money
from app.services.base import Ctx, check_version, reject_future, row_dict

GOAL_KINDS = {
    "reserva_emergencia": "Reserva de emergência",
    "carro": "Carro",
    "imovel": "Imóvel",
    "viagem": "Viagem",
    "quitar_dividas": "Quitar dívidas",
    "outro": "Outro objetivo",
}


def _view(ctx: Ctx, goal: Row[Any]) -> dict[str, Any]:
    acc = int(
        ctx.scalar(
            "SELECT coalesce(sum(CASE WHEN direction='deposito' THEN amount_cents ELSE -amount_cents END), 0)"
            " FROM goal_contributions WHERE owner_id=:o AND goal_id=:g",
            g=goal.id,
        )
    )
    p = goal_progress(
        Money(goal.target_cents),
        Money(acc),
        today=ctx.today,
        planned_monthly=Money(goal.planned_monthly_cents) if goal.planned_monthly_cents else None,
        annual_rate_percent=Decimal(goal.assumed_annual_rate) if goal.assumed_annual_rate else None,
        target_date=goal.target_date,
    )
    out = row_dict(goal)
    out.update(
        kind_label=GOAL_KINDS[goal.kind],
        assumed_annual_rate=str(goal.assumed_annual_rate) if goal.assumed_annual_rate is not None else None,
        accumulated_cents=p.accumulated.cents,
        missing_cents=p.missing.cents,
        percent=p.percent,
        months_needed=p.months_needed,
        projected_date=p.projected_date,
        on_track=p.on_track,
        assumption=p.assumption,
    )
    return out


def list_goals(ctx: Ctx) -> list[dict[str, Any]]:
    return [
        _view(ctx, g)
        for g in ctx.all(
            "SELECT * FROM goals WHERE owner_id=:o ORDER BY is_active DESC, target_date NULLS LAST, name"
        )
    ]


def get_goal(ctx: Ctx, goal_id: UUID) -> dict[str, Any]:
    goal = ctx.require("goals", goal_id, "Meta")
    out = _view(ctx, goal)
    out["contributions"] = [
        row_dict(r)
        for r in ctx.all(
            "SELECT * FROM goal_contributions WHERE owner_id=:o AND goal_id=:g "
            "ORDER BY contribution_date DESC, created_at DESC",
            g=goal_id,
        )
    ]
    return out


def create_goal(ctx: Ctx, data: dict[str, Any]) -> dict[str, Any]:
    row = ctx.one(
        """INSERT INTO goals (owner_id, name, kind, target_cents, target_date, planned_monthly_cents,
               assumed_annual_rate, note)
           VALUES (:o, :name, :kind, :target, :tdate, :monthly, :rate, :note) RETURNING id""",
        name=data["name"].strip(),
        kind=data["kind"],
        target=data["target_cents"],
        tdate=data.get("target_date"),
        monthly=data.get("planned_monthly_cents"),
        rate=data.get("assumed_annual_rate"),
        note=data.get("note"),
    )
    if row is None:  # pragma: no cover
        raise RuntimeError("falha ao gravar")
    initial = data.get("initial_amount_cents")
    if initial:
        add_contribution(
            ctx,
            row.id,
            {"amount_cents": initial, "direction": "deposito", "note": "Valor que já estava guardado"},
        )
    return get_goal(ctx, row.id)


def update_goal(ctx: Ctx, goal_id: UUID, data: dict[str, Any]) -> dict[str, Any]:
    goal = ctx.require("goals", goal_id, "Meta")
    check_version(goal, data.get("version"))
    fields = (
        "name",
        "kind",
        "target_cents",
        "target_date",
        "planned_monthly_cents",
        "assumed_annual_rate",
        "is_active",
        "note",
    )
    new = {k: data.get(k, getattr(goal, k)) for k in fields}
    ctx.exec(
        """UPDATE goals SET name=:name, kind=:kind, target_cents=:target_cents,
             target_date=:target_date, planned_monthly_cents=:planned_monthly_cents,
             assumed_annual_rate=:assumed_annual_rate, is_active=:is_active, note=:note,
             version=version+1, updated_at=now() WHERE id=:id AND owner_id=:o""",
        id=goal_id,
        **new,
    )
    return get_goal(ctx, goal_id)


def add_contribution(ctx: Ctx, goal_id: UUID, data: dict[str, Any]) -> dict[str, Any]:
    ctx.require("goals", goal_id, "Meta")
    on = data.get("contribution_date") or ctx.today
    reject_future(on, ctx.today, "contribution_date", "A data")
    if data["direction"] == "retirada":
        current = _view(ctx, ctx.require("goals", goal_id, "Meta"))["accumulated_cents"]
        if data["amount_cents"] > current:
            raise ApiError(
                422, "A retirada passa do valor guardado na meta.", {"amount_cents": "Maior que o guardado."}
            )
    ctx.exec(
        "INSERT INTO goal_contributions (owner_id, goal_id, contribution_date, direction, amount_cents, note) "
        "VALUES (:o, :g, :d, :dir, :a, :n)",
        g=goal_id,
        d=on,
        dir=data["direction"],
        a=data["amount_cents"],
        n=data.get("note"),
    )
    return get_goal(ctx, goal_id)


def delete_contribution(ctx: Ctx, contribution_id: UUID) -> dict[str, Any]:
    c = ctx.require("goal_contributions", contribution_id, "Contribuição")
    ctx.exec("DELETE FROM goal_contributions WHERE id=:id AND owner_id=:o", id=contribution_id)
    ctx.audit("meta", c.goal_id, "excluir_contribuicao", row_dict(c))
    return get_goal(ctx, c.goal_id)
