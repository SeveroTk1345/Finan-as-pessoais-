"""Usuários, contas e isolamento por Row-Level Security.

Revision ID: 0001
Revises:
Create Date: 15/10/2026
"""

from __future__ import annotations

from alembic import op
from sqlalchemy import text

from app.db.ownership import (
    APP_ROLE,
    CURRENT_USER_FUNCTION_SQL,
    app_grant_statements,
    owner_rls_statements,
)

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    exists = bind.execute(
        text("SELECT 1 FROM pg_roles WHERE rolname = :r"), {"r": APP_ROLE}
    ).scalar()
    if not exists:
        raise RuntimeError(
            f"o papel {APP_ROLE} não existe; crie-o antes (deploy/initdb ou scripts de teste)"
        )

    op.execute(f"GRANT USAGE ON SCHEMA public TO {APP_ROLE}")
    op.execute(CURRENT_USER_FUNCTION_SQL)
    op.execute(f"GRANT EXECUTE ON FUNCTION app_current_user_id() TO {APP_ROLE}")

    op.execute(
        """
        CREATE TABLE users (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            username text NOT NULL,
            display_name text NOT NULL,
            password_hash text NOT NULL,
            is_active boolean NOT NULL DEFAULT true,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT users_username_formato CHECK (username ~ '^[a-z0-9._-]{3,40}$'),
            CONSTRAINT users_display_name_tamanho
                CHECK (char_length(btrim(display_name)) BETWEEN 1 AND 60)
        )
        """
    )
    op.execute("CREATE UNIQUE INDEX users_username_unico ON users (username)")
    # Cada usuário só enxerga a própria linha. O login (T1.3) usará uma função
    # SECURITY DEFINER própria, porque acontece antes de existir identidade.
    op.execute("ALTER TABLE users ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE users FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY users_self ON users "
        "USING (id = app_current_user_id()) WITH CHECK (id = app_current_user_id())"
    )
    for stmt in app_grant_statements("users", "SELECT"):
        op.execute(stmt)

    op.execute(
        """
        CREATE TABLE accounts (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            owner_id uuid NOT NULL REFERENCES users (id) ON DELETE RESTRICT,
            name text NOT NULL,
            institution text,
            kind text NOT NULL,
            initial_balance_cents bigint NOT NULL,
            initial_balance_date date NOT NULL,
            is_active boolean NOT NULL DEFAULT true,
            version integer NOT NULL DEFAULT 1,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT accounts_owner_id_unico UNIQUE (owner_id, id),
            CONSTRAINT accounts_name_tamanho CHECK (char_length(btrim(name)) BETWEEN 1 AND 80),
            CONSTRAINT accounts_institution_tamanho
                CHECK (institution IS NULL OR char_length(institution) <= 80),
            CONSTRAINT accounts_kind_valido
                CHECK (kind IN ('corrente', 'poupanca', 'especie', 'outra')),
            -- Mesmo limite de app/domain/money.py (MAX_ABS_CENTS), fixado aqui porque
            -- migrações não podem mudar quando o código muda.
            CONSTRAINT accounts_saldo_limite
                CHECK (abs(initial_balance_cents) <= 100000000000000),
            CONSTRAINT accounts_version_positiva CHECK (version >= 1)
        )
        """
    )
    op.execute("CREATE INDEX accounts_owner_idx ON accounts (owner_id)")
    for stmt in owner_rls_statements("accounts"):
        op.execute(stmt)
    for stmt in app_grant_statements("accounts", "SELECT, INSERT, UPDATE, DELETE"):
        op.execute(stmt)


def downgrade() -> None:
    op.execute("DROP TABLE accounts")
    op.execute("DROP TABLE users")
    op.execute("DROP FUNCTION app_current_user_id()")
    op.execute(f"REVOKE USAGE ON SCHEMA public FROM {APP_ROLE}")
