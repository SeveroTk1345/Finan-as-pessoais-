"""Teto de gasto mensal por categoria.

Revision ID: 0006
Revises: 0005
Create Date: 15/10/2026

Um teto por categoria de despesa e por pessoa. O gasto do mês é calculado na hora
(mesma regra dos relatórios); só o valor do teto é gravado.
"""

from __future__ import annotations

from alembic import op

from app.db.ownership import app_grant_statements, owner_rls_statements

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE category_budgets (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            owner_id uuid NOT NULL REFERENCES users (id) ON DELETE CASCADE,
            category_id uuid NOT NULL,
            monthly_limit_cents bigint NOT NULL
                CHECK (monthly_limit_cents > 0 AND monthly_limit_cents <= 100000000000000),
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT category_budgets_owner_id_unico UNIQUE (owner_id, id),
            CONSTRAINT category_budgets_categoria_unica UNIQUE (owner_id, category_id),
            FOREIGN KEY (owner_id, category_id) REFERENCES categories (owner_id, id) ON DELETE CASCADE
        )
        """
    )
    for stmt in owner_rls_statements("category_budgets"):
        op.execute(stmt)
    for stmt in app_grant_statements("category_budgets", "SELECT, INSERT, UPDATE, DELETE"):
        op.execute(stmt)


def downgrade() -> None:
    op.execute("DROP TABLE category_budgets")
