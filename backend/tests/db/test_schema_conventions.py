"""Verifica no catálogo do PostgreSQL as convenções de isolamento em TODAS as tabelas.

Tabelas novas criadas em tarefas futuras são verificadas automaticamente: se alguém
esquecer RLS, política ou chave composta, estes testes falham.
"""

from __future__ import annotations

from sqlalchemy import Engine, text

from app.db.ownership import POLICY_SUFFIX


def _owned_tables(engine: Engine) -> list[str]:
    with engine.connect() as conn:
        return list(
            conn.execute(
                text(
                    """SELECT c.table_name FROM information_schema.columns c
                       JOIN information_schema.tables t
                         ON t.table_schema = c.table_schema AND t.table_name = c.table_name
                       WHERE c.table_schema = 'public' AND c.column_name = 'owner_id'
                         AND t.table_type = 'BASE TABLE'
                       ORDER BY 1"""
                )
            ).scalars()
        )


def test_existe_ao_menos_uma_tabela_com_dono(admin_engine: Engine) -> None:
    assert "accounts" in _owned_tables(admin_engine)


def test_toda_tabela_publica_tem_rls_ativa_e_forcada(admin_engine: Engine) -> None:
    with admin_engine.connect() as conn:
        rows = conn.execute(
            text(
                """SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity
                   FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
                   WHERE n.nspname = 'public' AND c.relkind = 'r'
                     AND c.relname <> 'alembic_version'"""
            )
        ).all()
    assert rows, "nenhuma tabela encontrada"
    problems = [r.relname for r in rows if not (r.relrowsecurity and r.relforcerowsecurity)]
    assert problems == []


def test_toda_tabela_com_dono_tem_a_politica_padrao(admin_engine: Engine) -> None:
    with admin_engine.connect() as conn:
        for table in _owned_tables(admin_engine):
            policies = conn.execute(
                text(
                    "SELECT policyname, cmd, qual, with_check FROM pg_policies "
                    "WHERE schemaname='public' AND tablename=:t"
                ),
                {"t": table},
            ).all()
            assert len(policies) == 1, f"{table}: esperada exatamente 1 política"
            p = policies[0]
            assert p.policyname == f"{table}{POLICY_SUFFIX}"
            assert p.cmd == "ALL"
            assert p.qual == "(owner_id = app_current_user_id())"
            assert p.with_check == "(owner_id = app_current_user_id())"


def test_toda_tabela_com_dono_tem_unique_owner_id_id(admin_engine: Engine) -> None:
    with admin_engine.connect() as conn:
        for table in _owned_tables(admin_engine):
            found = conn.execute(
                text(
                    """SELECT 1 FROM pg_constraint con
                       JOIN pg_class c ON c.oid = con.conrelid
                       WHERE c.relname = :t AND con.contype IN ('u', 'p')
                         AND (SELECT array_agg(a.attname::text ORDER BY a.attname)
                              FROM unnest(con.conkey) k
                              JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum = k)
                             = ARRAY['id', 'owner_id']"""
                ),
                {"t": table},
            ).scalar()
            assert found, f"{table}: falta UNIQUE (owner_id, id)"


def test_chaves_entre_tabelas_com_dono_sao_compostas(admin_engine: Engine) -> None:
    owned = set(_owned_tables(admin_engine))
    with admin_engine.connect() as conn:
        fks = conn.execute(
            text(
                """SELECT src.relname AS src, dst.relname AS dst, con.conname,
                          (SELECT array_agg(a.attname::text) FROM unnest(con.conkey) k
                           JOIN pg_attribute a ON a.attrelid = con.conrelid AND a.attnum = k)
                          AS cols
                   FROM pg_constraint con
                   JOIN pg_class src ON src.oid = con.conrelid
                   JOIN pg_class dst ON dst.oid = con.confrelid
                   JOIN pg_namespace n ON n.oid = src.relnamespace
                   WHERE con.contype = 'f' AND n.nspname = 'public'"""
            )
        ).all()
    problems = [
        f"{fk.src}.{fk.conname}"
        for fk in fks
        if fk.src in owned and fk.dst in owned and "owner_id" not in fk.cols
    ]
    assert problems == []


def test_papel_da_aplicacao_e_restrito(admin_engine: Engine) -> None:
    with admin_engine.connect() as conn:
        role = conn.execute(
            text(
                "SELECT rolsuper, rolbypassrls, rolcreatedb, rolcreaterole "
                "FROM pg_roles WHERE rolname='fin_app'"
            )
        ).one()
        owns = conn.execute(
            text(
                """SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                   WHERE n.nspname='public' AND pg_get_userbyid(c.relowner)='fin_app'"""
            )
        ).scalar()
    assert tuple(role) == (False, False, False, False)
    # Dono de tabela poderia desligar a RLS; fin_app não é dono de nada.
    assert owns == 0
