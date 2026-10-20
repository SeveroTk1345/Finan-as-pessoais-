"""Modelo financeiro completo.

Revision ID: 0003
Revises: 0002
Create Date: 15/10/2026

Princípios (ver docs/DECISOES.md e docs/MODELO_DE_DADOS.md):
* ``transactions`` é o livro razão: cada entrada ou saída real de dinheiro em conta é
  exatamente uma linha. Saldos vêm só daqui.
* Contas a pagar, faturas, dívidas e investimentos referenciam o livro razão, nunca
  criam uma segunda despesa.
* Nada financeiro é apagado: cancelamentos mudam ``status`` e ficam no histórico.
* Toda tabela tem dono, RLS e chaves compostas (owner_id, ...).
"""

from __future__ import annotations

from alembic import op

from app.db.ownership import app_grant_statements, owner_rls_statements

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

MAX = "100000000000000"  # mesmo limite de app/domain/money.py

TABLES: list[tuple[str, str, str]] = []


def owned(name: str, body: str, grants: str = "SELECT, INSERT, UPDATE") -> None:
    TABLES.append((name, body, grants))


owned(
    "categories",
    """
    name text NOT NULL CHECK (char_length(btrim(name)) BETWEEN 1 AND 40),
    kind text NOT NULL CHECK (kind IN ('receita', 'despesa')),
    position integer NOT NULL DEFAULT 0,
    is_system boolean NOT NULL DEFAULT false,
    is_archived boolean NOT NULL DEFAULT false
    """,
)

owned(
    "recurring_rules",
    f"""
    kind text NOT NULL CHECK (kind IN ('pagar', 'receber')),
    description text NOT NULL CHECK (char_length(btrim(description)) BETWEEN 1 AND 120),
    amount_cents bigint NOT NULL CHECK (amount_cents > 0 AND amount_cents <= {MAX}),
    category_id uuid,
    account_id uuid,
    expense_nature text CHECK (expense_nature IN ('fixa', 'variavel', 'extraordinaria')),
    frequency text NOT NULL CHECK (frequency IN ('mensal', 'semanal', 'anual')),
    anchor_date date NOT NULL,
    end_date date,
    is_main_income boolean NOT NULL DEFAULT false,
    is_active boolean NOT NULL DEFAULT true,
    version integer NOT NULL DEFAULT 1,
    FOREIGN KEY (owner_id, category_id) REFERENCES categories (owner_id, id),
    FOREIGN KEY (owner_id, account_id) REFERENCES accounts (owner_id, id),
    CHECK (end_date IS NULL OR end_date >= anchor_date)
    """,
)

owned(
    "bills",
    f"""
    kind text NOT NULL CHECK (kind IN ('pagar', 'receber')),
    description text NOT NULL CHECK (char_length(btrim(description)) BETWEEN 1 AND 120),
    amount_cents bigint NOT NULL CHECK (amount_cents > 0 AND amount_cents <= {MAX}),
    due_date date NOT NULL,
    category_id uuid,
    account_id uuid,
    expense_nature text CHECK (expense_nature IN ('fixa', 'variavel', 'extraordinaria')),
    rule_id uuid,
    occurrence_date date,
    is_main_income boolean NOT NULL DEFAULT false,
    status text NOT NULL DEFAULT 'aberta' CHECK (status IN ('aberta', 'cancelada')),
    cancelled_at timestamptz,
    note text CHECK (note IS NULL OR char_length(note) <= 500),
    version integer NOT NULL DEFAULT 1,
    FOREIGN KEY (owner_id, category_id) REFERENCES categories (owner_id, id),
    FOREIGN KEY (owner_id, account_id) REFERENCES accounts (owner_id, id),
    FOREIGN KEY (owner_id, rule_id) REFERENCES recurring_rules (owner_id, id),
    CHECK ((rule_id IS NULL) = (occurrence_date IS NULL)),
    UNIQUE (owner_id, rule_id, occurrence_date)
    """,
)

owned(
    "cards",
    f"""
    name text NOT NULL CHECK (char_length(btrim(name)) BETWEEN 1 AND 60),
    institution text CHECK (institution IS NULL OR char_length(institution) <= 60),
    limit_cents bigint NOT NULL CHECK (limit_cents >= 0 AND limit_cents <= {MAX}),
    closing_day smallint NOT NULL CHECK (closing_day BETWEEN 1 AND 31),
    due_day smallint NOT NULL CHECK (due_day BETWEEN 1 AND 31),
    closing_day_goes_next boolean NOT NULL DEFAULT true,
    is_active boolean NOT NULL DEFAULT true,
    version integer NOT NULL DEFAULT 1
    """,
)

owned(
    "debts",
    f"""
    creditor text NOT NULL CHECK (char_length(btrim(creditor)) BETWEEN 1 AND 80),
    description text CHECK (description IS NULL OR char_length(description) <= 120),
    kind text NOT NULL CHECK (kind IN ('emprestimo', 'financiamento', 'parcelamento',
        'renegociacao', 'parcelamento_fatura', 'outra')),
    original_amount_cents bigint NOT NULL CHECK (original_amount_cents > 0
        AND original_amount_cents <= {MAX}),
    start_date date NOT NULL,
    anchor_balance_cents bigint NOT NULL CHECK (anchor_balance_cents >= 0
        AND anchor_balance_cents <= {MAX}),
    anchor_date date NOT NULL,
    interest_rate numeric(12, 6) CHECK (interest_rate IS NULL OR interest_rate >= 0),
    rate_period text CHECK (rate_period IN ('mensal', 'anual')),
    installments_total integer CHECK (installments_total IS NULL OR installments_total
        BETWEEN 1 AND 600),
    installments_paid_before integer NOT NULL DEFAULT 0 CHECK (installments_paid_before >= 0),
    installment_amount_cents bigint CHECK (installment_amount_cents IS NULL
        OR (installment_amount_cents > 0 AND installment_amount_cents <= {MAX})),
    first_due_date date,
    status text NOT NULL DEFAULT 'ativa' CHECK (status IN ('ativa', 'quitada', 'renegociada',
        'cancelada')),
    renegotiated_from_id uuid,
    card_id uuid,
    card_invoice_due_date date,
    note text CHECK (note IS NULL OR char_length(note) <= 500),
    version integer NOT NULL DEFAULT 1,
    FOREIGN KEY (owner_id, renegotiated_from_id) REFERENCES debts (owner_id, id),
    FOREIGN KEY (owner_id, card_id) REFERENCES cards (owner_id, id),
    CHECK ((interest_rate IS NULL) = (rate_period IS NULL)),
    CHECK ((kind = 'parcelamento_fatura') = (card_id IS NOT NULL)),
    CHECK (installments_total IS NULL OR installments_paid_before <= installments_total)
    """,
)

owned(
    "card_purchases",
    f"""
    card_id uuid NOT NULL,
    kind text NOT NULL CHECK (kind IN ('compra', 'encargo', 'parcelamento_fatura')),
    description text NOT NULL CHECK (char_length(btrim(description)) BETWEEN 1 AND 120),
    category_id uuid,
    purchase_date date NOT NULL,
    total_cents bigint NOT NULL CHECK (total_cents > 0 AND total_cents <= {MAX}),
    installments_count integer NOT NULL CHECK (installments_count BETWEEN 1 AND 72),
    financed_principal_cents bigint CHECK (financed_principal_cents IS NULL
        OR financed_principal_cents > 0),
    debt_id uuid,
    status text NOT NULL DEFAULT 'ativa' CHECK (status IN ('ativa', 'cancelada')),
    cancelled_at timestamptz,
    note text CHECK (note IS NULL OR char_length(note) <= 500),
    FOREIGN KEY (owner_id, card_id) REFERENCES cards (owner_id, id),
    FOREIGN KEY (owner_id, category_id) REFERENCES categories (owner_id, id),
    FOREIGN KEY (owner_id, debt_id) REFERENCES debts (owner_id, id),
    CHECK ((kind = 'parcelamento_fatura') = (debt_id IS NOT NULL)),
    CHECK ((kind = 'parcelamento_fatura') = (financed_principal_cents IS NOT NULL)),
    CHECK (financed_principal_cents IS NULL OR financed_principal_cents <= total_cents)
    """,
)

owned(
    "card_installments",
    f"""
    purchase_id uuid NOT NULL,
    card_id uuid NOT NULL,
    number integer NOT NULL CHECK (number >= 1),
    amount_cents bigint NOT NULL CHECK (amount_cents > 0 AND amount_cents <= {MAX}),
    invoice_due_date date NOT NULL,
    status text NOT NULL DEFAULT 'ativa' CHECK (status IN ('ativa', 'cancelada')),
    FOREIGN KEY (owner_id, purchase_id) REFERENCES card_purchases (owner_id, id),
    FOREIGN KEY (owner_id, card_id) REFERENCES cards (owner_id, id),
    UNIQUE (purchase_id, number)
    """,
)

owned(
    "card_credits",
    f"""
    card_id uuid NOT NULL,
    purchase_id uuid,
    debt_id uuid,
    kind text NOT NULL CHECK (kind IN ('estorno', 'cancelamento', 'renegociacao', 'credito')),
    description text NOT NULL CHECK (char_length(btrim(description)) BETWEEN 1 AND 120),
    credit_date date NOT NULL,
    invoice_due_date date NOT NULL,
    amount_cents bigint NOT NULL CHECK (amount_cents > 0 AND amount_cents <= {MAX}),
    FOREIGN KEY (owner_id, card_id) REFERENCES cards (owner_id, id),
    FOREIGN KEY (owner_id, purchase_id) REFERENCES card_purchases (owner_id, id),
    FOREIGN KEY (owner_id, debt_id) REFERENCES debts (owner_id, id),
    CHECK ((kind = 'renegociacao') = (debt_id IS NOT NULL))
    """,
)

owned(
    "investments",
    """
    asset_class text NOT NULL CHECK (asset_class IN ('renda_fixa', 'renda_variavel', 'outros')),
    product_type text NOT NULL CHECK (char_length(btrim(product_type)) BETWEEN 1 AND 40),
    name text NOT NULL CHECK (char_length(btrim(name)) BETWEEN 1 AND 80),
    institution text CHECK (institution IS NULL OR char_length(institution) <= 60),
    ticker text CHECK (ticker IS NULL OR ticker ~ '^[A-Z0-9.]{1,12}$'),
    indexer text CHECK (indexer IN ('CDI', 'IPCA', 'Selic', 'Prefixado', 'Outro')),
    rate_description text CHECK (rate_description IS NULL OR char_length(rate_description) <= 60),
    maturity_date date,
    liquidity text CHECK (liquidity IS NULL OR char_length(liquidity) <= 60),
    is_active boolean NOT NULL DEFAULT true,
    note text CHECK (note IS NULL OR char_length(note) <= 500),
    version integer NOT NULL DEFAULT 1,
    CHECK (asset_class <> 'renda_variavel' OR ticker IS NOT NULL)
    """,
)

owned(
    "investment_movements",
    f"""
    investment_id uuid NOT NULL,
    movement_date date NOT NULL,
    kind text NOT NULL CHECK (kind IN ('aporte', 'retirada', 'rendimento', 'dividendo', 'juros',
        'amortizacao', 'taxa', 'compra', 'venda')),
    amount_cents bigint NOT NULL CHECK (amount_cents > 0 AND amount_cents <= {MAX}),
    fees_cents bigint NOT NULL DEFAULT 0 CHECK (fees_cents >= 0 AND fees_cents <= {MAX}),
    quantity numeric(24, 8) CHECK (quantity IS NULL OR quantity > 0),
    paid_to_account boolean NOT NULL DEFAULT false,
    account_id uuid,
    status text NOT NULL DEFAULT 'ativo' CHECK (status IN ('ativo', 'cancelado')),
    note text CHECK (note IS NULL OR char_length(note) <= 300),
    FOREIGN KEY (owner_id, investment_id) REFERENCES investments (owner_id, id),
    FOREIGN KEY (owner_id, account_id) REFERENCES accounts (owner_id, id),
    CHECK ((kind IN ('compra', 'venda')) = (quantity IS NOT NULL))
    """,
)

owned(
    "investment_valuations",
    f"""
    investment_id uuid NOT NULL,
    valuation_date date NOT NULL,
    value_cents bigint CHECK (value_cents IS NULL OR (value_cents >= 0 AND value_cents <= {MAX})),
    unit_price_cents bigint CHECK (unit_price_cents IS NULL
        OR (unit_price_cents >= 0 AND unit_price_cents <= {MAX})),
    note text CHECK (note IS NULL OR char_length(note) <= 300),
    FOREIGN KEY (owner_id, investment_id) REFERENCES investments (owner_id, id),
    CHECK ((value_cents IS NULL) <> (unit_price_cents IS NULL))
    """,
    grants="SELECT, INSERT, UPDATE, DELETE",
)

owned(
    "transactions",
    f"""
    account_id uuid NOT NULL,
    direction text NOT NULL CHECK (direction IN ('entrada', 'saida')),
    amount_cents bigint NOT NULL CHECK (amount_cents > 0 AND amount_cents <= {MAX}),
    tx_date date NOT NULL,
    kind text NOT NULL CHECK (kind IN ('receita', 'despesa', 'transferencia', 'ajuste',
        'pagamento_fatura', 'pagamento_divida', 'entrada_emprestimo', 'reembolso',
        'investimento')),
    description text NOT NULL CHECK (char_length(btrim(description)) BETWEEN 1 AND 120),
    category_id uuid,
    expense_nature text CHECK (expense_nature IN ('fixa', 'variavel', 'extraordinaria')),
    note text CHECK (note IS NULL OR char_length(note) <= 500),
    bill_id uuid,
    transfer_id uuid,
    card_id uuid,
    invoice_due_date date,
    debt_id uuid,
    debt_payment_type text CHECK (debt_payment_type IN ('parcela', 'amortizacao', 'quitacao')),
    debt_interest_cents bigint CHECK (debt_interest_cents IS NULL OR debt_interest_cents >= 0),
    investment_movement_id uuid,
    status text NOT NULL DEFAULT 'ativo' CHECK (status IN ('ativo', 'cancelado')),
    cancelled_at timestamptz,
    version integer NOT NULL DEFAULT 1,
    FOREIGN KEY (owner_id, account_id) REFERENCES accounts (owner_id, id),
    FOREIGN KEY (owner_id, category_id) REFERENCES categories (owner_id, id),
    FOREIGN KEY (owner_id, bill_id) REFERENCES bills (owner_id, id),
    FOREIGN KEY (owner_id, card_id) REFERENCES cards (owner_id, id),
    FOREIGN KEY (owner_id, debt_id) REFERENCES debts (owner_id, id),
    FOREIGN KEY (owner_id, investment_movement_id) REFERENCES investment_movements (owner_id, id),
    CHECK (kind <> 'receita' OR direction = 'entrada'),
    CHECK (kind <> 'despesa' OR direction = 'saida'),
    CHECK (kind NOT IN ('entrada_emprestimo', 'reembolso') OR direction = 'entrada'),
    CHECK ((kind = 'transferencia') = (transfer_id IS NOT NULL)),
    CHECK ((kind = 'pagamento_fatura') = (card_id IS NOT NULL AND invoice_due_date IS NOT NULL)),
    CHECK (kind <> 'pagamento_fatura' OR direction = 'saida'),
    CHECK ((kind = 'pagamento_divida') = (debt_payment_type IS NOT NULL)),
    CHECK (kind NOT IN ('pagamento_divida', 'entrada_emprestimo') OR debt_id IS NOT NULL),
    CHECK (kind <> 'pagamento_divida' OR direction = 'saida'),
    CHECK (debt_interest_cents IS NULL OR debt_interest_cents <= amount_cents),
    CHECK ((kind = 'investimento') = (investment_movement_id IS NOT NULL)),
    CHECK (bill_id IS NULL OR kind IN ('receita', 'despesa'))
    """,
)

owned(
    "debt_events",
    f"""
    debt_id uuid NOT NULL,
    event_date date NOT NULL,
    kind text NOT NULL CHECK (kind IN ('encargo', 'desconto', 'renegociacao_baixa')),
    amount_cents bigint NOT NULL CHECK (amount_cents > 0 AND amount_cents <= {MAX}),
    description text NOT NULL CHECK (char_length(btrim(description)) BETWEEN 1 AND 120),
    status text NOT NULL DEFAULT 'ativo' CHECK (status IN ('ativo', 'cancelado')),
    FOREIGN KEY (owner_id, debt_id) REFERENCES debts (owner_id, id)
    """,
)

owned(
    "goals",
    f"""
    name text NOT NULL CHECK (char_length(btrim(name)) BETWEEN 1 AND 80),
    kind text NOT NULL CHECK (kind IN ('reserva_emergencia', 'carro', 'imovel', 'viagem',
        'quitar_dividas', 'outro')),
    target_cents bigint NOT NULL CHECK (target_cents > 0 AND target_cents <= {MAX}),
    target_date date,
    planned_monthly_cents bigint CHECK (planned_monthly_cents IS NULL
        OR (planned_monthly_cents > 0 AND planned_monthly_cents <= {MAX})),
    assumed_annual_rate numeric(8, 4) CHECK (assumed_annual_rate IS NULL
        OR assumed_annual_rate BETWEEN 0 AND 100),
    is_active boolean NOT NULL DEFAULT true,
    note text CHECK (note IS NULL OR char_length(note) <= 500),
    version integer NOT NULL DEFAULT 1
    """,
)

owned(
    "goal_contributions",
    f"""
    goal_id uuid NOT NULL,
    contribution_date date NOT NULL,
    direction text NOT NULL CHECK (direction IN ('deposito', 'retirada')),
    amount_cents bigint NOT NULL CHECK (amount_cents > 0 AND amount_cents <= {MAX}),
    note text CHECK (note IS NULL OR char_length(note) <= 300),
    FOREIGN KEY (owner_id, goal_id) REFERENCES goals (owner_id, id)
    """,
    grants="SELECT, INSERT, UPDATE, DELETE",
)

owned(
    "audit_log",
    """
    entity text NOT NULL,
    entity_id uuid NOT NULL,
    action text NOT NULL,
    before_data jsonb,
    after_data jsonb
    """,
    grants="SELECT, INSERT",
)

INDEXES = [
    "CREATE UNIQUE INDEX categories_nome_unico ON categories (owner_id, kind, lower(name))",
    "CREATE INDEX bills_due_idx ON bills (owner_id, due_date)",
    "CREATE INDEX transactions_account_date_idx ON transactions (owner_id, account_id, tx_date)",
    "CREATE INDEX transactions_date_idx ON transactions (owner_id, tx_date)",
    "CREATE INDEX transactions_bill_idx ON transactions (bill_id) WHERE bill_id IS NOT NULL",
    "CREATE INDEX transactions_card_idx ON transactions (card_id, invoice_due_date)"
    " WHERE card_id IS NOT NULL",
    "CREATE INDEX transactions_debt_idx ON transactions (debt_id) WHERE debt_id IS NOT NULL",
    "CREATE INDEX transactions_transfer_idx ON transactions (transfer_id) WHERE transfer_id IS NOT NULL",
    "CREATE INDEX card_installments_invoice_idx ON card_installments (card_id, invoice_due_date)",
    "CREATE INDEX card_purchases_card_idx ON card_purchases (card_id, purchase_date)",
    "CREATE INDEX card_credits_invoice_idx ON card_credits (card_id, invoice_due_date)",
    "CREATE INDEX investment_movements_idx ON investment_movements (investment_id, movement_date)",
    "CREATE INDEX investment_valuations_idx ON investment_valuations (investment_id, valuation_date)",
    "CREATE INDEX debt_events_idx ON debt_events (debt_id, event_date)",
    "CREATE INDEX goal_contributions_idx ON goal_contributions (goal_id, contribution_date)",
    "CREATE INDEX audit_log_entity_idx ON audit_log (owner_id, entity, entity_id)",
]


def upgrade() -> None:
    op.execute("ALTER TABLE accounts ADD COLUMN daily_use boolean NOT NULL DEFAULT true")
    op.execute("ALTER TABLE accounts ADD COLUMN note text CHECK (note IS NULL OR char_length(note) <= 500)")
    for name, body, grants in TABLES:
        op.execute(
            f"""
            CREATE TABLE {name} (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                owner_id uuid NOT NULL REFERENCES users (id) ON DELETE RESTRICT,
                created_at timestamptz NOT NULL DEFAULT now(),
                updated_at timestamptz NOT NULL DEFAULT now(),
                {body.strip().rstrip(",")},
                CONSTRAINT {name}_owner_id_unico UNIQUE (owner_id, id)
            )
            """
        )
        op.execute(f"CREATE INDEX {name}_owner_idx ON {name} (owner_id)")
        for stmt in owner_rls_statements(name):
            op.execute(stmt)
        for stmt in app_grant_statements(name, grants):
            op.execute(stmt)
    for stmt in INDEXES:
        op.execute(stmt)


def downgrade() -> None:
    for name, _, _ in reversed(TABLES):
        op.execute(f"DROP TABLE {name}")
    op.execute("ALTER TABLE accounts DROP COLUMN note")
    op.execute("ALTER TABLE accounts DROP COLUMN daily_use")
