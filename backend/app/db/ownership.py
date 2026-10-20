"""Convenções de isolamento por dono, compartilhadas entre migrações e testes.

Toda tabela com dados de um usuário ("tabela com dono"):
* tem ``owner_id uuid NOT NULL REFERENCES users(id)``;
* tem ``UNIQUE (owner_id, id)``, para servir de alvo de chaves estrangeiras compostas;
* referencia outras tabelas com dono por ``(owner_id, <fk>)``, nunca só por ``<fk>``.
  Assim o próprio banco recusa ligar um registro de A a um registro de B;
* tem Row-Level Security ativada e forçada, com a política gerada aqui.

``tests/db/test_schema_conventions.py`` verifica essas regras em todas as tabelas.
"""

from __future__ import annotations

import re

APP_ROLE = "fin_app"
IDENTITY_SETTING = "app.user_id"
POLICY_SUFFIX = "_owner_isolation"

_IDENT = re.compile(r"^[a-z_][a-z0-9_]*$")


def _check_ident(name: str) -> str:
    # Os nomes entram em DDL; aceitar só identificadores simples evita injeção.
    if not _IDENT.match(name):
        raise ValueError(f"identificador inválido: {name!r}")
    return name


# Função usada por todas as políticas. Configuração ausente ou vazia vira NULL,
# e owner_id = NULL nunca é verdadeiro: sem identidade, nenhuma linha aparece.
# NULLIF é necessário porque, depois de um SET LOCAL, o valor volta a '' (não NULL)
# na mesma conexão, e ''::uuid daria erro.
CURRENT_USER_FUNCTION_SQL = f"""
CREATE FUNCTION app_current_user_id() RETURNS uuid
LANGUAGE sql STABLE
AS $$ SELECT NULLIF(current_setting('{IDENTITY_SETTING}', true), '')::uuid $$
"""


def owner_rls_statements(table: str, *, owner_column: str = "owner_id") -> list[str]:
    """DDL que ativa RLS e cria a política de dono para uma tabela."""
    t = _check_ident(table)
    col = _check_ident(owner_column)
    return [
        f"ALTER TABLE {t} ENABLE ROW LEVEL SECURITY",
        # FORCE faz a política valer também para o dono da tabela.
        f"ALTER TABLE {t} FORCE ROW LEVEL SECURITY",
        f"CREATE POLICY {t}{POLICY_SUFFIX} ON {t} "
        f"USING ({col} = app_current_user_id()) "
        f"WITH CHECK ({col} = app_current_user_id())",
    ]


def app_grant_statements(table: str, privileges: str) -> list[str]:
    t = _check_ident(table)
    allowed = {"SELECT", "INSERT", "UPDATE", "DELETE"}
    privs = [p.strip().upper() for p in privileges.split(",")]
    if not privs or any(p not in allowed for p in privs):
        raise ValueError(f"privilégios inválidos: {privileges!r}")
    return [f"GRANT {', '.join(privs)} ON {t} TO {APP_ROLE}"]
