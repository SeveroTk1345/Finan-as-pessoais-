"""Entrar com digital ou rosto (passkeys, padrão WebAuthn).

Revision ID: 0004
Revises: 0003
Create Date: 15/10/2026

O servidor guarda só a CHAVE PÚBLICA de cada aparelho. A biometria nunca sai do
celular: o aparelho confirma a digital ou o rosto e assina um desafio com a chave
privada, que fica nele. Login acontece antes de existir identidade na transação,
então, como na migração 0002, a API usa funções SECURITY DEFINER mínimas.
"""

from __future__ import annotations

from alembic import op

from app.db.ownership import APP_ROLE, app_grant_statements, owner_rls_statements

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

FUNCTIONS = [
    "auth_challenge_new(text, uuid, bytea, integer)",
    "auth_challenge_take(uuid, text)",
    "auth_passkey_lookup(bytea)",
    "auth_passkey_used(uuid, bigint)",
]


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE passkeys (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            owner_id uuid NOT NULL REFERENCES users (id) ON DELETE CASCADE,
            credential_id bytea NOT NULL,
            public_key bytea NOT NULL,
            sign_count bigint NOT NULL DEFAULT 0 CHECK (sign_count >= 0),
            device_name text NOT NULL CHECK (char_length(device_name) BETWEEN 1 AND 60),
            created_at timestamptz NOT NULL DEFAULT now(),
            last_used_at timestamptz,
            CONSTRAINT passkeys_owner_id_unico UNIQUE (owner_id, id),
            CONSTRAINT passkeys_credencial_unica UNIQUE (credential_id),
            CONSTRAINT passkeys_credencial_tamanho CHECK (octet_length(credential_id) BETWEEN 16 AND 1023)
        )
        """
    )
    op.execute("CREATE INDEX passkeys_owner_idx ON passkeys (owner_id)")
    for stmt in owner_rls_statements("passkeys"):
        op.execute(stmt)
    for stmt in app_grant_statements("passkeys", "SELECT, INSERT, DELETE"):
        op.execute(stmt)

    # Desafios de uso único. Sem owner_id e sem política: com RLS forçada, fin_app só
    # chega aqui pelas funções abaixo. user_id fica preenchido no cadastro (pessoa já
    # conectada) e vazio no login (ainda não se sabe quem é).
    op.execute(
        """
        CREATE TABLE webauthn_challenges (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            purpose text NOT NULL CHECK (purpose IN ('cadastro', 'entrar')),
            user_id uuid REFERENCES users (id) ON DELETE CASCADE,
            challenge bytea NOT NULL CHECK (octet_length(challenge) >= 32),
            expires_at timestamptz NOT NULL
        )
        """
    )
    op.execute("CREATE INDEX webauthn_challenges_expira_idx ON webauthn_challenges (expires_at)")
    op.execute("ALTER TABLE webauthn_challenges ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE webauthn_challenges FORCE ROW LEVEL SECURITY")

    op.execute(
        """
        CREATE FUNCTION auth_challenge_new(p_purpose text, p_user uuid, p_challenge bytea, p_ttl integer)
        RETURNS uuid
        LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public
        AS $$
        DECLARE
            new_id uuid;
        BEGIN
            DELETE FROM public.webauthn_challenges WHERE expires_at <= now();
            -- Teto contra enchimento da tabela por pedidos anônimos de desafio.
            DELETE FROM public.webauthn_challenges WHERE id IN (
                SELECT id FROM public.webauthn_challenges ORDER BY expires_at DESC OFFSET 1000);
            INSERT INTO public.webauthn_challenges (purpose, user_id, challenge, expires_at)
            VALUES (p_purpose, p_user, p_challenge, now() + make_interval(secs => p_ttl))
            RETURNING id INTO new_id;
            RETURN new_id;
        END
        $$
        """
    )
    # Consome o desafio (uso único): apagado mesmo que a verificação depois falhe.
    op.execute(
        """
        CREATE FUNCTION auth_challenge_take(p_id uuid, p_purpose text)
        RETURNS TABLE (challenge bytea, user_id uuid)
        LANGUAGE sql SECURITY DEFINER SET search_path = pg_catalog, public
        AS $$
            DELETE FROM public.webauthn_challenges
             WHERE id = p_id AND purpose = p_purpose AND expires_at > now()
            RETURNING challenge, user_id
        $$
        """
    )
    op.execute(
        """
        CREATE FUNCTION auth_passkey_lookup(p_credential_id bytea)
        RETURNS TABLE (passkey_id uuid, user_id uuid, public_key bytea, sign_count bigint, is_active boolean)
        LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public
        AS $$
            SELECT p.id, p.owner_id, p.public_key, p.sign_count, u.is_active
              FROM public.passkeys p JOIN public.users u ON u.id = p.owner_id
             WHERE p.credential_id = p_credential_id
        $$
        """
    )
    op.execute(
        """
        CREATE FUNCTION auth_passkey_used(p_passkey_id uuid, p_sign_count bigint)
        RETURNS void
        LANGUAGE sql SECURITY DEFINER SET search_path = pg_catalog, public
        AS $$
            UPDATE public.passkeys SET sign_count = greatest(sign_count, p_sign_count), last_used_at = now()
             WHERE id = p_passkey_id
        $$
        """
    )
    for fn in FUNCTIONS:
        op.execute(f"REVOKE ALL ON FUNCTION {fn} FROM PUBLIC")
        op.execute(f"GRANT EXECUTE ON FUNCTION {fn} TO {APP_ROLE}")


def downgrade() -> None:
    for fn in reversed(FUNCTIONS):
        op.execute(f"DROP FUNCTION {fn}")
    op.execute("DROP TABLE webauthn_challenges")
    op.execute("DROP TABLE passkeys")
