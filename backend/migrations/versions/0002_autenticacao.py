"""Sessões, tentativas de login e chaves de idempotência.

Revision ID: 0002
Revises: 0001
Create Date: 15/10/2026

Funções SECURITY DEFINER: login e validação de sessão acontecem antes de existir
identidade na transação, então a API não consegue ler essas tabelas diretamente.
As funções expõem só o mínimo necessário e têm search_path fixo.
"""

from __future__ import annotations

from alembic import op

from app.db.ownership import APP_ROLE, app_grant_statements, owner_rls_statements

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE users ADD COLUMN password_changed_at timestamptz")
    # Cada usuário pode trocar a própria senha e o próprio nome (política users_self).
    op.execute(f"GRANT UPDATE (password_hash, password_changed_at, display_name) ON users TO {APP_ROLE}")

    op.execute(
        """
        CREATE TABLE sessions (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            owner_id uuid NOT NULL REFERENCES users (id) ON DELETE CASCADE,
            token_hash bytea NOT NULL,
            remember boolean NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            last_seen_at timestamptz NOT NULL DEFAULT now(),
            expires_at timestamptz NOT NULL,
            idle_timeout_seconds integer NOT NULL CHECK (idle_timeout_seconds > 0),
            CONSTRAINT sessions_owner_id_unico UNIQUE (owner_id, id),
            CONSTRAINT sessions_token_unico UNIQUE (token_hash),
            CONSTRAINT sessions_token_tamanho CHECK (octet_length(token_hash) = 32)
        )
        """
    )
    op.execute("CREATE INDEX sessions_owner_idx ON sessions (owner_id)")
    for stmt in owner_rls_statements("sessions"):
        op.execute(stmt)
    for stmt in app_grant_statements("sessions", "SELECT, INSERT, DELETE"):
        op.execute(stmt)

    # Sem owner_id e sem política: com RLS forçada, fin_app não lê nem grava direto.
    op.execute(
        """
        CREATE TABLE login_attempts (
            id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            username text NOT NULL,
            client_ip text NOT NULL,
            success boolean NOT NULL,
            attempted_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX login_attempts_user_idx ON login_attempts (username, attempted_at)")
    op.execute("CREATE INDEX login_attempts_ip_idx ON login_attempts (client_ip, attempted_at)")
    op.execute("ALTER TABLE login_attempts ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE login_attempts FORCE ROW LEVEL SECURITY")

    op.execute(
        """
        CREATE TABLE idempotency_keys (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            owner_id uuid NOT NULL REFERENCES users (id) ON DELETE CASCADE,
            key text NOT NULL,
            fingerprint text NOT NULL,
            status_code integer,
            response_body jsonb,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT idempotency_keys_owner_id_unico UNIQUE (owner_id, id),
            CONSTRAINT idempotency_keys_chave_unica UNIQUE (owner_id, key),
            CONSTRAINT idempotency_keys_formato CHECK (key ~ '^[A-Za-z0-9_-]{16,100}$')
        )
        """
    )
    for stmt in owner_rls_statements("idempotency_keys"):
        op.execute(stmt)
    for stmt in app_grant_statements("idempotency_keys", "SELECT, INSERT, UPDATE"):
        op.execute(stmt)

    op.execute(
        """
        CREATE FUNCTION auth_login_lookup(p_username text)
        RETURNS TABLE (user_id uuid, password_hash text, is_active boolean)
        LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public
        AS $$ SELECT id, password_hash, is_active FROM public.users WHERE username = p_username $$
        """
    )
    op.execute(
        """
        CREATE FUNCTION auth_session_user(p_token_hash bytea)
        RETURNS uuid
        LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public
        AS $$
        DECLARE
            s public.sessions%ROWTYPE;
        BEGIN
            SELECT * INTO s FROM public.sessions WHERE token_hash = p_token_hash;
            IF NOT FOUND THEN
                RETURN NULL;
            END IF;
            IF s.expires_at <= now()
               OR s.last_seen_at + make_interval(secs => s.idle_timeout_seconds) <= now() THEN
                DELETE FROM public.sessions WHERE id = s.id;
                RETURN NULL;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM public.users WHERE id = s.owner_id AND is_active) THEN
                RETURN NULL;
            END IF;
            -- Atualiza o "último uso" no máximo a cada minuto, para não gravar a cada clique.
            IF s.last_seen_at < now() - interval '1 minute' THEN
                UPDATE public.sessions SET last_seen_at = now() WHERE id = s.id;
            END IF;
            RETURN s.owner_id;
        END
        $$
        """
    )
    op.execute(
        """
        CREATE FUNCTION auth_register_attempt(p_username text, p_ip text, p_success boolean)
        RETURNS void
        LANGUAGE sql SECURITY DEFINER SET search_path = pg_catalog, public
        AS $$
            INSERT INTO public.login_attempts (username, client_ip, success)
            VALUES (left(p_username, 100), left(p_ip, 64), p_success);
            DELETE FROM public.login_attempts WHERE attempted_at < now() - interval '1 day';
        $$
        """
    )
    op.execute(
        """
        CREATE FUNCTION auth_recent_failures(p_username text, p_ip text, p_window_seconds integer)
        RETURNS TABLE (by_username bigint, by_ip bigint)
        LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public
        AS $$
            SELECT
              (SELECT count(*) FROM public.login_attempts
                WHERE username = left(p_username, 100) AND NOT success
                  AND attempted_at > now() - make_interval(secs => p_window_seconds)),
              (SELECT count(*) FROM public.login_attempts
                WHERE client_ip = left(p_ip, 64) AND NOT success
                  AND attempted_at > now() - make_interval(secs => p_window_seconds))
        $$
        """
    )
    for fn in [
        "auth_login_lookup(text)",
        "auth_session_user(bytea)",
        "auth_register_attempt(text, text, boolean)",
        "auth_recent_failures(text, text, integer)",
    ]:
        op.execute(f"REVOKE ALL ON FUNCTION {fn} FROM PUBLIC")
        op.execute(f"GRANT EXECUTE ON FUNCTION {fn} TO {APP_ROLE}")


def downgrade() -> None:
    for fn in [
        "auth_recent_failures(text, text, integer)",
        "auth_register_attempt(text, text, boolean)",
        "auth_session_user(bytea)",
        "auth_login_lookup(text)",
    ]:
        op.execute(f"DROP FUNCTION {fn}")
    op.execute("DROP TABLE idempotency_keys")
    op.execute("DROP TABLE login_attempts")
    op.execute("DROP TABLE sessions")
    op.execute(f"REVOKE UPDATE (password_hash, password_changed_at, display_name) ON users FROM {APP_ROLE}")
    op.execute("ALTER TABLE users DROP COLUMN password_changed_at")
