"""Compra parcelada fora do cartão (carnê, boleto, crediário).

Revision ID: 0005
Revises: 0004
Create Date: 15/10/2026

Cada parcela é uma conta a pagar comum (a despesa nasce quando a parcela é paga,
F13), ligada às demais por ``installment_group``, com o número e o total de
parcelas. Assim cada parcela aparece em Contas a pagar como "Parcela 3 de 10".
"""

from __future__ import annotations

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE bills
            ADD COLUMN installment_group uuid,
            ADD COLUMN installment_number smallint,
            ADD COLUMN installments_total smallint,
            ADD CONSTRAINT bills_parcela_completa CHECK (
                (installment_group IS NULL AND installment_number IS NULL AND installments_total IS NULL)
                OR (installment_group IS NOT NULL AND installments_total BETWEEN 2 AND 72
                    AND installment_number BETWEEN 1 AND installments_total)
            ),
            ADD CONSTRAINT bills_parcela_unica UNIQUE (owner_id, installment_group, installment_number)
        """
    )
    op.execute(
        "CREATE INDEX bills_parcelamento_idx ON bills (owner_id, installment_group) "
        "WHERE installment_group IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX bills_parcelamento_idx")
    op.execute(
        "ALTER TABLE bills DROP CONSTRAINT bills_parcela_unica, DROP CONSTRAINT bills_parcela_completa, "
        "DROP COLUMN installments_total, DROP COLUMN installment_number, DROP COLUMN installment_group"
    )
