"""Rotas de investimentos, metas, resumo, relatórios e exportação."""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse, Response
from pydantic import Field

from app.api.core_routes import Cents, Note, Strict
from app.api.errors import ApiError
from app.api.service import Svc
from app.domain.dates import YearMonth
from app.services import export, goals, investments, reports, simulator

router = APIRouter()

MAX = 100_000_000_000_000


class MovementIn(Strict):
    kind: Literal[
        "aporte", "retirada", "rendimento", "dividendo", "juros", "amortizacao", "taxa", "compra", "venda"
    ]
    movement_date: date
    amount_cents: Cents
    fees_cents: Annotated[int, Field(ge=0, le=MAX)] = 0
    quantity: Annotated[Decimal | None, Field(default=None, gt=0, max_digits=24, decimal_places=8)] = None
    account_id: UUID | None = None
    paid_to_account: bool = False
    note: Annotated[str | None, Field(default=None, max_length=300)] = None


class InvestmentIn(Strict):
    asset_class: Literal["renda_fixa", "renda_variavel", "outros"]
    product_type: Annotated[str, Field(min_length=1, max_length=40)]
    name: Annotated[str, Field(min_length=1, max_length=80)]
    institution: Annotated[str | None, Field(default=None, max_length=60)] = None
    ticker: Annotated[str | None, Field(default=None, pattern=r"^[A-Za-z0-9.]{1,12}$")] = None
    indexer: Literal["CDI", "IPCA", "Selic", "Prefixado", "Outro"] | None = None
    rate_description: Annotated[str | None, Field(default=None, max_length=60)] = None
    maturity_date: date | None = None
    liquidity: Annotated[str | None, Field(default=None, max_length=60)] = None
    note: Note = None
    first_movement: MovementIn | None = None


class InvestmentPatch(Strict):
    product_type: Annotated[str | None, Field(default=None, min_length=1, max_length=40)] = None
    name: Annotated[str | None, Field(default=None, min_length=1, max_length=80)] = None
    institution: Annotated[str | None, Field(default=None, max_length=60)] = None
    ticker: Annotated[str | None, Field(default=None, pattern=r"^[A-Za-z0-9.]{1,12}$")] = None
    indexer: Literal["CDI", "IPCA", "Selic", "Prefixado", "Outro"] | None = None
    rate_description: Annotated[str | None, Field(default=None, max_length=60)] = None
    maturity_date: date | None = None
    liquidity: Annotated[str | None, Field(default=None, max_length=60)] = None
    is_active: bool | None = None
    note: Note = None
    version: int | None = None


class ValuationIn(Strict):
    valuation_date: date | None = None
    value_cents: Annotated[int | None, Field(default=None, ge=0, le=MAX)] = None
    unit_price_cents: Annotated[int | None, Field(default=None, ge=0, le=MAX)] = None
    note: Annotated[str | None, Field(default=None, max_length=300)] = None


@router.get("/investimentos")
def investments_overview(svc: Svc) -> dict[str, Any]:
    return svc.run(investments.overview)


@router.post("/investimentos", status_code=201)
def investments_create(payload: InvestmentIn, svc: Svc) -> JSONResponse:
    data = payload.model_dump()
    return svc.create(payload, lambda c: investments.create_investment(c, data))


@router.get("/investimentos/{inv_id}")
def investments_get(inv_id: UUID, svc: Svc) -> dict[str, Any]:
    return svc.run(lambda c: investments.get_investment(c, inv_id))


@router.patch("/investimentos/{inv_id}")
def investments_update(inv_id: UUID, payload: InvestmentPatch, svc: Svc) -> dict[str, Any]:
    data = payload.model_dump(exclude_unset=True)
    return svc.run(lambda c: investments.update_investment(c, inv_id, data))


@router.post("/investimentos/{inv_id}/movimentos", status_code=201)
def investments_movement(inv_id: UUID, payload: MovementIn, svc: Svc) -> JSONResponse:
    return svc.create(payload, lambda c: investments.add_movement(c, inv_id, payload.model_dump()))


@router.post("/investimentos/movimentos/{movement_id}/cancelar")
def investments_cancel_movement(movement_id: UUID, svc: Svc) -> dict[str, Any]:
    return svc.run(lambda c: investments.cancel_movement(c, movement_id))


@router.post("/investimentos/{inv_id}/valores", status_code=201)
def investments_valuation(inv_id: UUID, payload: ValuationIn, svc: Svc) -> JSONResponse:
    return svc.create(payload, lambda c: investments.add_valuation(c, inv_id, payload.model_dump()))


@router.delete("/investimentos/valores/{valuation_id}")
def investments_delete_valuation(valuation_id: UUID, svc: Svc) -> dict[str, Any]:
    return svc.run(lambda c: investments.delete_valuation(c, valuation_id))


# --- metas -------------------------------------------------------------------------

GoalKind = Literal["reserva_emergencia", "carro", "imovel", "viagem", "quitar_dividas", "outro"]


class GoalIn(Strict):
    name: Annotated[str, Field(min_length=1, max_length=80)]
    kind: GoalKind = "outro"
    target_cents: Cents
    target_date: date | None = None
    planned_monthly_cents: Cents | None = None
    assumed_annual_rate: Annotated[Decimal | None, Field(default=None, ge=0, le=100, decimal_places=4)] = None
    initial_amount_cents: Annotated[int | None, Field(default=None, ge=0, le=MAX)] = None
    note: Note = None


class GoalPatch(Strict):
    name: Annotated[str | None, Field(default=None, min_length=1, max_length=80)] = None
    kind: GoalKind | None = None
    target_cents: Cents | None = None
    target_date: date | None = None
    planned_monthly_cents: Cents | None = None
    assumed_annual_rate: Annotated[Decimal | None, Field(default=None, ge=0, le=100, decimal_places=4)] = None
    is_active: bool | None = None
    note: Note = None
    version: int | None = None


class ContributionIn(Strict):
    direction: Literal["deposito", "retirada"] = "deposito"
    amount_cents: Cents
    contribution_date: date | None = None
    note: Annotated[str | None, Field(default=None, max_length=300)] = None


@router.get("/metas")
def goals_list(svc: Svc) -> list[dict[str, Any]]:
    return svc.run(goals.list_goals)


@router.post("/metas", status_code=201)
def goals_create(payload: GoalIn, svc: Svc) -> JSONResponse:
    return svc.create(payload, lambda c: goals.create_goal(c, payload.model_dump()))


@router.get("/metas/{goal_id}")
def goals_get(goal_id: UUID, svc: Svc) -> dict[str, Any]:
    return svc.run(lambda c: goals.get_goal(c, goal_id))


@router.patch("/metas/{goal_id}")
def goals_update(goal_id: UUID, payload: GoalPatch, svc: Svc) -> dict[str, Any]:
    data = payload.model_dump(exclude_unset=True)
    return svc.run(lambda c: goals.update_goal(c, goal_id, data))


@router.post("/metas/{goal_id}/contribuicoes", status_code=201)
def goals_contribute(goal_id: UUID, payload: ContributionIn, svc: Svc) -> JSONResponse:
    return svc.create(payload, lambda c: goals.add_contribution(c, goal_id, payload.model_dump()))


@router.delete("/metas/contribuicoes/{contribution_id}")
def goals_delete_contribution(contribution_id: UUID, svc: Svc) -> dict[str, Any]:
    return svc.run(lambda c: goals.delete_contribution(c, contribution_id))


# --- resumo, relatórios, exportação ----------------------------------------------------

MONTH = re.compile(r"^(\d{4})-(\d{2})$")


def _month(value: str | None, svc_today: date) -> YearMonth:
    if value is None:
        return YearMonth.of(svc_today)
    m = MONTH.match(value)
    if not m or not 1 <= int(m.group(2)) <= 12:
        raise ApiError(422, "Mês inválido. Use o formato AAAA-MM.", {"mes": "Mês inválido."})
    return YearMonth(int(m.group(1)), int(m.group(2)))


@router.get("/resumo")
def home(svc: Svc) -> dict[str, Any]:
    return svc.run(reports.home)


@router.get("/a-pagar")
def to_pay(svc: Svc, dias: Annotated[int, Query(ge=1, le=366)] = 30) -> dict[str, Any]:
    """Tudo o que vence nos próximos dias (contas, faturas, parcelas), sem duplicar."""

    def run(c: Any) -> dict[str, Any]:
        from datetime import timedelta

        items = reports.obligations(c, c.today + timedelta(days=dias))
        return {"items": items, "total_cents": sum(i["amount_cents"] for i in items)}

    return svc.run(run)


@router.get("/relatorios/mensal")
def report_month(svc: Svc, mes: str | None = None) -> dict[str, Any]:
    month = _month(mes, svc.today)
    return svc.run(lambda c: reports.monthly(c, month))


@router.get("/relatorios/evolucao")
def report_series(svc: Svc, meses: Annotated[int, Query(ge=1, le=36)] = 12) -> dict[str, Any]:
    return svc.run(lambda c: reports.series(c, meses))


@router.get("/exportar/dados.json")
def export_json(svc: Svc) -> JSONResponse:
    data = svc.run(export.export_json)
    return JSONResponse(
        data,
        headers={"Content-Disposition": 'attachment; filename="financas-meus-dados.json"'},
    )


@router.get("/exportar/lancamentos.csv")
def export_csv(svc: Svc) -> Response:
    content = svc.run(export.export_transactions_csv)
    return Response(
        content.encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="financas-lancamentos.csv"'},
    )


# --- Posso comprar? -------------------------------------------------------------------


class SimulationIn(Strict):
    amount_cents: Cents
    method: Literal["conta", "cartao"] = "conta"
    card_id: UUID | None = None
    installments_count: Annotated[int, Field(ge=1, le=72)] = 1
    purchase_date: date | None = None
    months: Annotated[int, Field(ge=1, le=24)] = 6


@router.post("/simulador/compra")
def simulate_purchase(payload: SimulationIn, svc: Svc) -> dict[str, Any]:
    """Só leitura: nada é gravado."""
    return svc.run(lambda c: simulator.simulate_purchase(c, payload.model_dump()))
