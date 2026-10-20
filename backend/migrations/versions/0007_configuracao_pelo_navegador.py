"""Criar contas e redefinir senha pelo navegador (plataformas sem terminal).

Revision ID: 0007
Revises: 0006
Create Date: 20/10/2026

A API (fin_app) não pode inserir em ``users`` nem ver as contas dos outros. Para a
página /configurar, que é protegida por um código só do administrador, três funções
SECURITY DEFINER fazem o mínimo necessário. O limite de 3 contas (escopo M2) fica no
próprio banco, com trava na tabela para dois pedidos simultâneos não passarem juntos.
"""

from __future__ import annotations

from alembic import op

from app.db.ownership import APP_ROLE

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

MAX_USERS = 3  # repetido no SQL de setup_create_user
FUNCTIONS = [
    "setup_user_count()",
    "setup_create_user(text, text, text)",
    "setup_reset_password(text, text)",
]


def upgrade() -> None:
    op.execute(
        """
        CREATE FUNCTION setup_user_count() RETURNS integer
        LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public
        AS $$ SELECT count(*)::integer FROM public.users $$
        """
    )
    # Limite de 3 contas: escrito direto no SQL (o mesmo valor de MAX_USERS).
    op.execute(
        """
        CREATE FUNCTION setup_create_user(p_username text, p_display_name text, p_password_hash text)
        RETURNS uuid
        LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public
        AS $$
        DECLARE
            new_id uuid;
        BEGIN
            LOCK TABLE public.users IN SHARE ROW EXCLUSIVE MODE;
            IF (SELECT count(*) FROM public.users) >= 3 THEN
                RAISE EXCEPTION 'limite de contas' USING ERRCODE = 'P0001';
            END IF;
            IF EXISTS (SELECT 1 FROM public.users WHERE username = p_username) THEN
                RAISE EXCEPTION 'conta existente' USING ERRCODE = 'P0002';
            END IF;
            INSERT INTO public.users (username, display_name, password_hash, password_changed_at)
            VALUES (p_username, p_display_name, p_password_hash, now())
            RETURNING id INTO new_id;
            RETURN new_id;
        END
        $$
        """
    )
    # Troca a senha e encerra todas as sessões abertas daquela conta.
    op.execute(
        """
        CREATE FUNCTION setup_reset_password(p_username text, p_password_hash text) RETURNS boolean
        LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public
        AS $$
        DECLARE
            uid uuid;
        BEGIN
            UPDATE public.users SET password_hash = p_password_hash, password_changed_at = now()
             WHERE username = p_username RETURNING id INTO uid;
            IF uid IS NULL THEN
                RETURN false;
            END IF;
            DELETE FROM public.sessions WHERE owner_id = uid;
            RETURN true;
        END
        $$
        """
    )
    for fn in FUNCTIONS:
        op.execute(f"REVOKE ALL ON FUNCTION {fn} FROM PUBLIC")
        op.execute(f"GRANT EXECUTE ON FUNCTION {fn} TO {APP_ROLE}")


def downgrade() -> None:
    for fn in reversed(FUNCTIONS):
        op.execute(f"DROP FUNCTION {fn}")
