"""Rotas de contas, categorias, lançamentos, transferências e contas a pagar."""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Query, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from app.api.service import Svc
from app.domain.money import MAX_ABS_CENTS
from app.services import bills, ledger

router = APIRouter()

Cents = Annotated[int, Field(gt=0, le=MAX_ABS_CENTS)]
SignedCents = Annotated[int, Field(ge=-MAX_ABS_CENTS, le=MAX_ABS_CENTS)]
Text120 = Annotated[str, Field(min_length=1, max_length=120)]
Note = Annotated[str | None, Field(default=None, max_length=500)]
Nature = Literal["fixa", "variavel", "extraordinaria"]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --- contas ----------------------------------------------------------------------


class AccountIn(Strict):
    name: Annotated[str, Field(min_length=1, max_length=80)]
    institution: Annotated[str | None, Field(default=None, max_length=80)] = None
    kind: Literal["corrente", "poupanca", "especie", "outra"]
    initial_balance_cents: SignedCents
    initial_balance_date: date
    daily_use: bool | None = None
    note: Note = None


class AccountPatch(Strict):
    name: Annotated[str | None, Field(default=None, min_length=1, max_length=80)] = None
    institution: Annotated[str | None, Field(default=None, max_length=80)] = None
    kind: Literal["corrente", "poupanca", "especie", "outra"] | None = None
    initial_balance_cents: SignedCents | None = None
    initial_balance_date: date | None = None
    daily_use: bool | None = None
    is_active: bool | None = None
    note: Note = None
    version: int | None = None


class AdjustIn(Strict):
    real_balance_cents: SignedCents
    on: date
    note: Note = None


@router.get("/contas")
def accounts_list(svc: Svc, incluir_inativas: bool = True) -> list[dict[str, Any]]:
    return svc.run(lambda c: ledger.list_accounts(c, include_inactive=incluir_inativas))


@router.post("/contas", status_code=201)
def accounts_create(payload: AccountIn, svc: Svc) -> JSONResponse:
    return svc.create(payload, lambda c: ledger.create_account(c, payload.model_dump()))


@router.get("/contas/{account_id}")
def accounts_get(account_id: UUID, svc: Svc) -> dict[str, Any]:
    return svc.run(lambda c: ledger.get_account(c, account_id))


@router.patch("/contas/{account_id}")
def accounts_update(account_id: UUID, payload: AccountPatch, svc: Svc) -> dict[str, Any]:
    data = payload.model_dump(exclude_unset=True)
    return svc.run(lambda c: ledger.update_account(c, account_id, data))


@router.delete("/contas/{account_id}", status_code=204)
def accounts_delete(account_id: UUID, svc: Svc) -> Response:
    svc.run(lambda c: ledger.delete_account(c, account_id))
    return Response(status_code=204)


@router.post("/contas/{account_id}/ajustar-saldo", status_code=201)
def accounts_adjust(account_id: UUID, payload: AdjustIn, svc: Svc) -> JSONResponse:
    return svc.create(
        payload,
        lambda c: {
            "ajuste": ledger.adjust_balance(
                c,
                account_id,
                real_balance_cents=payload.real_balance_cents,
                on=payload.on,
                note=payload.note,
            ),
            "conta": ledger.get_account(c, account_id),
        },
    )


# --- categorias ------------------------------------------------------------------


class CategoryIn(Strict):
    name: Annotated[str, Field(min_length=1, max_length=40)]
    kind: Literal["receita", "despesa"]


class CategoryPatch(Strict):
    name: Annotated[str | None, Field(default=None, min_length=1, max_length=40)] = None
    is_archived: bool | None = None


@router.get("/categorias")
def categories_list(svc: Svc) -> list[dict[str, Any]]:
    return svc.run(ledger.list_categories)


@router.post("/categorias", status_code=201)
def categories_create(payload: CategoryIn, svc: Svc) -> JSONResponse:
    return svc.create(payload, lambda c: ledger.create_category(c, payload.name, payload.kind))


@router.patch("/categorias/{category_id}")
def categories_update(category_id: UUID, payload: CategoryPatch, svc: Svc) -> dict[str, Any]:
    return svc.run(
        lambda c: ledger.update_category(c, category_id, name=payload.name, archived=payload.is_archived)
    )


# --- lançamentos -----------------------------------------------------------------


class RepeatIn(Strict):
    frequency: Literal["mensal", "semanal", "anual"] = "mensal"
    end_date: date | None = None


class TransactionIn(Strict):
    kind: Literal["receita", "despesa", "reembolso"]
    account_id: UUID
    amount_cents: Cents
    tx_date: date
    description: Text120
    category_id: UUID | None = None
    expense_nature: Nature | None = None
    note: Note = None
    # Repete todo mês (ou semana, ou ano): as próximas vezes viram contas a pagar.
    repeat: RepeatIn | None = None


class TransactionPatch(Strict):
    account_id: UUID | None = None
    amount_cents: Cents | None = None
    tx_date: date | None = None
    description: Annotated[str | None, Field(default=None, min_length=1, max_length=120)] = None
    category_id: UUID | None = None
    expense_nature: Nature | None = None
    note: Note = None
    version: int | None = None


class TransferIn(Strict):
    from_account_id: UUID
    to_account_id: UUID
    amount_cents: Cents
    tx_date: date
    description: Annotated[str | None, Field(default=None, max_length=120)] = None
    note: Note = None


@router.get("/lancamentos")
def transactions_list(
    svc: Svc,
    inicio: date | None = None,
    fim: date | None = None,
    conta: UUID | None = None,
    tipo: str | None = None,
    categoria: UUID | None = None,
    busca: Annotated[str | None, Query(max_length=60)] = None,
    incluir_cancelados: bool = False,
    limite: Annotated[int, Query(ge=1, le=200)] = 50,
    pagina: Annotated[int, Query(ge=1, le=10000)] = 1,
) -> dict[str, Any]:
    return svc.run(
        lambda c: ledger.list_transactions(
            c,
            start=inicio,
            end=fim,
            account_id=conta,
            kind=tipo,
            category_id=categoria,
            search=busca,
            include_cancelled=incluir_cancelados,
            limit=limite,
            offset=(pagina - 1) * limite,
        )
    )


@router.post("/lancamentos", status_code=201)
def transactions_create(payload: TransactionIn, svc: Svc) -> JSONResponse:
    data = payload.model_dump()
    if payload.repeat is not None:
        return svc.create(payload, lambda c: bills.create_repeating_transaction(c, data))
    return svc.create(payload, lambda c: ledger.create_transaction(c, data))


@router.get("/lancamentos/{tx_id}")
def transactions_get(tx_id: UUID, svc: Svc) -> dict[str, Any]:
    return svc.run(lambda c: ledger.get_transaction(c, tx_id))


@router.patch("/lancamentos/{tx_id}")
def transactions_update(tx_id: UUID, payload: TransactionPatch, svc: Svc) -> dict[str, Any]:
    data = payload.model_dump(exclude_unset=True)
    return svc.run(lambda c: ledger.update_transaction(c, tx_id, data))


@router.post("/lancamentos/{tx_id}/cancelar")
def transactions_cancel(tx_id: UUID, svc: Svc) -> dict[str, Any]:
    return svc.run(lambda c: ledger.cancel_transaction(c, tx_id))


@router.post("/transferencias", status_code=201)
def transfers_create(payload: TransferIn, svc: Svc) -> JSONResponse:
    return svc.create(payload, lambda c: ledger.create_transfer(c, payload.model_dump()))


# --- contas a pagar e a receber ----------------------------------------------------


class BillIn(Strict):
    kind: Literal["pagar", "receber"] = "pagar"
    description: Text120
    amount_cents: Cents
    due_date: date
    category_id: UUID | None = None
    account_id: UUID | None = None
    expense_nature: Nature | None = None
    is_main_income: bool = False
    note: Note = None


class BillPatch(Strict):
    description: Annotated[str | None, Field(default=None, min_length=1, max_length=120)] = None
    amount_cents: Cents | None = None
    due_date: date | None = None
    category_id: UUID | None = None
    account_id: UUID | None = None
    expense_nature: Nature | None = None
    note: Note = None
    version: int | None = None


class PayIn(Strict):
    amount_cents: Cents | None = None
    account_id: UUID | None = None
    tx_date: date | None = None


class OccurrenceIn(Strict):
    rule_id: UUID
    occurrence_date: date


class RuleIn(Strict):
    kind: Literal["pagar", "receber"] = "pagar"
    description: Text120
    amount_cents: Cents
    category_id: UUID | None = None
    account_id: UUID | None = None
    expense_nature: Nature | None = None
    frequency: Literal["mensal", "semanal", "anual"] = "mensal"
    anchor_date: date
    end_date: date | None = None
    is_main_income: bool = False


class RulePatch(Strict):
    description: Annotated[str | None, Field(default=None, min_length=1, max_length=120)] = None
    amount_cents: Cents | None = None
    category_id: UUID | None = None
    account_id: UUID | None = None
    end_date: date | None = None
    is_active: bool | None = None
    version: int | None = None


@router.get("/contas-a-pagar")
def bills_list(
    svc: Svc,
    inicio: date,
    fim: date,
    tipo: Literal["pagar", "receber"] = "pagar",
    incluir_vencidas: bool = True,
) -> list[dict[str, Any]]:
    return svc.run(
        lambda c: bills.list_bills(c, kind=tipo, start=inicio, end=fim, include_overdue=incluir_vencidas)
    )


@router.post("/contas-a-pagar", status_code=201)
def bills_create(payload: BillIn, svc: Svc) -> JSONResponse:
    return svc.create(payload, lambda c: bills.create_bill(c, payload.model_dump()))


@router.post("/contas-a-pagar/ocorrencia", status_code=201)
def bills_materialize(payload: OccurrenceIn, svc: Svc) -> JSONResponse:
    """Grava uma ocorrência de recorrência para poder pagar, editar ou cancelar."""
    return svc.create(
        payload,
        lambda c: bills.get_bill(c, bills.materialize(c, payload.rule_id, payload.occurrence_date)),
    )


@router.get("/contas-a-pagar/{bill_id}")
def bills_get(bill_id: UUID, svc: Svc) -> dict[str, Any]:
    return svc.run(lambda c: bills.get_bill(c, bill_id))


@router.patch("/contas-a-pagar/{bill_id}")
def bills_update(bill_id: UUID, payload: BillPatch, svc: Svc) -> dict[str, Any]:
    data = payload.model_dump(exclude_unset=True)
    return svc.run(lambda c: bills.update_bill(c, bill_id, data))


@router.post("/contas-a-pagar/{bill_id}/pagar", status_code=201)
def bills_pay(bill_id: UUID, payload: PayIn, svc: Svc) -> JSONResponse:
    return svc.create(payload, lambda c: bills.pay_bill(c, bill_id, payload.model_dump()))


@router.post("/contas-a-pagar/{bill_id}/cancelar")
def bills_cancel(bill_id: UUID, svc: Svc) -> dict[str, Any]:
    return svc.run(lambda c: bills.cancel_bill(c, bill_id))


class InstallmentPlanIn(Strict):
    description: Text120
    total_cents: Cents
    installments_count: Annotated[int, Field(ge=2, le=72)]
    first_due_date: date
    category_id: UUID | None = None
    account_id: UUID | None = None
    expense_nature: Nature | None = None
    note: Note = None


@router.post("/parcelamentos", status_code=201)
def installment_plan_create(payload: InstallmentPlanIn, svc: Svc) -> JSONResponse:
    """Compra parcelada fora do cartão: uma conta a pagar por parcela."""
    return svc.create(payload, lambda c: bills.create_installment_plan(c, payload.model_dump()))


@router.get("/parcelamentos/{group_id}")
def installment_plan_get(group_id: UUID, svc: Svc) -> dict[str, Any]:
    return svc.run(lambda c: bills.installment_plan(c, group_id))


@router.post("/parcelamentos/{group_id}/cancelar")
def installment_plan_cancel(group_id: UUID, svc: Svc) -> dict[str, Any]:
    return svc.run(lambda c: bills.cancel_installment_plan(c, group_id))


@router.get("/recorrencias")
def rules_list(svc: Svc) -> list[dict[str, Any]]:
    return svc.run(bills.list_rules)


@router.post("/recorrencias", status_code=201)
def rules_create(payload: RuleIn, svc: Svc) -> JSONResponse:
    return svc.create(payload, lambda c: bills.create_rule(c, payload.model_dump()))


@router.patch("/recorrencias/{rule_id}")
def rules_update(rule_id: UUID, payload: RulePatch, svc: Svc) -> dict[str, Any]:
    data = payload.model_dump(exclude_unset=True)
    return svc.run(lambda c: bills.update_rule(c, rule_id, data))
