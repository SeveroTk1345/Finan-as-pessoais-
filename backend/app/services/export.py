"""Exportação dos dados do próprio usuário (P2).

Só lê tabelas com ``owner_id`` do usuário da sessão (e RLS garante o mesmo no banco).
O CSV protege contra fórmulas ao abrir no Excel.
"""

from __future__ import annotations

import csv
import io
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from app.domain.dates import format_br_date
from app.domain.money import Money, format_brl
from app.services.base import Ctx, row_dict

EXPORT_VERSION = 1

TABLES = [
    "accounts",
    "categories",
    "transactions",
    "recurring_rules",
    "bills",
    "cards",
    "card_purchases",
    "card_installments",
    "card_credits",
    "debts",
    "debt_events",
    "investments",
    "investment_movements",
    "investment_valuations",
    "goals",
    "goal_contributions",
]


def _plain(value: Any) -> Any:
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return value


def export_json(ctx: Ctx) -> dict[str, Any]:
    user = ctx.one("SELECT username, display_name FROM users WHERE id=:o")
    data: dict[str, Any] = {}
    for table in TABLES:
        rows = ctx.all(f"SELECT * FROM {table} WHERE owner_id=:o ORDER BY created_at, id")  # noqa: S608
        data[table] = [{k: _plain(v) for k, v in row_dict(r).items() if k != "owner_id"} for r in rows]
    return {
        "format": "financas-pessoais",
        "version": EXPORT_VERSION,
        "exported_at": datetime.now().astimezone().isoformat(),
        "user": {"username": user.username, "display_name": user.display_name} if user else None,
        "data": data,
    }


_FORMULA_START = ("=", "+", "-", "@", "\t", "\r")


def safe_cell(value: str) -> str:
    """Impede que o Excel interprete texto como fórmula (=, +, -, @ no início)."""
    if value and value.startswith(_FORMULA_START):
        return "'" + value
    return value


KIND_LABELS = {
    "receita": "Receita",
    "despesa": "Despesa",
    "transferencia": "Transferência",
    "ajuste": "Ajuste de saldo",
    "pagamento_fatura": "Pagamento de fatura",
    "pagamento_divida": "Pagamento de dívida",
    "entrada_emprestimo": "Entrada de empréstimo",
    "reembolso": "Reembolso",
    "investimento": "Investimento",
}


def export_transactions_csv(ctx: Ctx) -> str:
    rows = ctx.all(
        """SELECT t.tx_date, t.kind, t.direction, t.amount_cents, t.description, t.status, t.note,
                  a.name AS account, c.name AS category
           FROM transactions t
           JOIN accounts a ON a.id=t.account_id AND a.owner_id=t.owner_id
           LEFT JOIN categories c ON c.id=t.category_id AND c.owner_id=t.owner_id
           WHERE t.owner_id=:o ORDER BY t.tx_date, t.created_at"""
    )
    buf = io.StringIO()
    # Ponto e vírgula: separador que o Excel em português abre corretamente.
    writer = csv.writer(buf, delimiter=";", lineterminator="\r\n")
    writer.writerow(["Data", "Tipo", "Conta", "Categoria", "Descrição", "Valor", "Situação", "Observação"])
    for r in rows:
        cents = r.amount_cents if r.direction == "entrada" else -r.amount_cents
        writer.writerow(
            [
                format_br_date(r.tx_date),
                KIND_LABELS.get(r.kind, r.kind),
                safe_cell(r.account),
                safe_cell(r.category or ""),
                safe_cell(r.description),
                # Valor numérico com vírgula decimal, sem "R$", para somar no Excel.
                format_brl(Money(cents)).replace("R$ ", ""),
                "Cancelado" if r.status == "cancelado" else "Ativo",
                safe_cell(r.note or ""),
            ]
        )
    # BOM para o Excel reconhecer UTF-8 (acentos).
    return "\ufeff" + buf.getvalue()
