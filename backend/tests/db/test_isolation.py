"""Isolamento entre três usuários: leitura, alteração, exclusão, consultas e relações.

Cada camada é testada sozinha:
* RLS sem filtro da aplicação (SQL direto como fin_app);
* filtro da aplicação sem RLS (repositório usado por superusuário, que ignora RLS);
* as duas juntas (caminho real da API).
"""

from __future__ import annotations

import itertools
from collections.abc import Iterator
from datetime import date
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError, IntegrityError, ProgrammingError

from app.db.identity import user_transaction
from app.db.ownership import owner_rls_statements
from app.db.repositories.accounts import (
    Account,
    AccountRepository,
    IdentityMismatchError,
)
from app.domain.money import Money
from tests.db.conftest import Users

PAIRS = list(itertools.permutations(["ana", "bruno", "carla"], 2))


def _create_account(engine: Engine, owner: UUID, name: str, cents: int = 10000) -> Account:
    with user_transaction(engine, owner) as conn:
        return AccountRepository(conn, owner).create(
            name=name,
            kind="corrente",
            initial_balance=Money(cents),
            initial_balance_date=date(2026, 10, 1),
            institution="Banco Fictício",
        )


@pytest.fixture
def seeded(app_engine: Engine, users: Users) -> dict[str, Account]:
    """Uma conta por usuário, com valores diferentes (dados sintéticos)."""
    return {
        "ana": _create_account(app_engine, users.ana, "Conta da Ana", 111),
        "bruno": _create_account(app_engine, users.bruno, "Conta do Bruno", 222),
        "carla": _create_account(app_engine, users.carla, "Conta da Carla", 333),
    }


def _uid(users: Users, name: str) -> UUID:
    return getattr(users, name)  # type: ignore[no-any-return]


# --- camadas juntas (caminho real) ----------------------------------------------


def test_cada_usuario_lista_somente_as_proprias_contas(
    app_engine: Engine, users: Users, seeded: dict[str, Account]
) -> None:
    for name in ["ana", "bruno", "carla"]:
        uid = _uid(users, name)
        with user_transaction(app_engine, uid) as conn:
            listed = AccountRepository(conn, uid).list()
        assert [a.id for a in listed] == [seeded[name].id]
        assert all(a.owner_id == uid for a in listed)


@pytest.mark.parametrize(("attacker", "victim"), PAIRS)
def test_acesso_cruzado_por_id_e_negado(
    app_engine: Engine, users: Users, seeded: dict[str, Account], attacker: str, victim: str
) -> None:
    uid = _uid(users, attacker)
    target = seeded[victim]
    with user_transaction(app_engine, uid) as conn:
        repo = AccountRepository(conn, uid)
        assert repo.get(target.id) is None
        assert repo.rename(target.id, name="invadida", expected_version=1) is None
        assert repo.delete(target.id) is False

    # A conta da vítima continua intacta.
    vid = _uid(users, victim)
    with user_transaction(app_engine, vid) as conn:
        still = AccountRepository(conn, vid).get(target.id)
    assert still == target


def test_resposta_para_id_alheio_e_igual_a_id_inexistente(
    app_engine: Engine, users: Users, seeded: dict[str, Account]
) -> None:
    # Mesmo resultado para "não existe" e "é de outra pessoa": nada vaza.
    with user_transaction(app_engine, users.ana) as conn:
        repo = AccountRepository(conn, users.ana)
        assert repo.get(seeded["bruno"].id) == repo.get(uuid4()) is None
        assert repo.delete(seeded["bruno"].id) == repo.delete(uuid4()) is False


def test_dono_consegue_operar_normalmente(
    app_engine: Engine, users: Users, seeded: dict[str, Account]
) -> None:
    acc = seeded["ana"]
    with user_transaction(app_engine, users.ana) as conn:
        repo = AccountRepository(conn, users.ana)
        renamed = repo.rename(acc.id, name="Conta principal", expected_version=1)
        assert renamed is not None and renamed.version == 2
        # Versão antiga: bloqueio otimista recusa.
        assert repo.rename(acc.id, name="outra", expected_version=1) is None
        assert repo.delete(acc.id) is True
        assert repo.get(acc.id) is None


def test_repositorio_recusa_conexao_de_outro_usuario(app_engine: Engine, users: Users) -> None:
    with (
        user_transaction(app_engine, users.ana) as conn,
        pytest.raises(IdentityMismatchError),
    ):
        AccountRepository(conn, users.bruno)


# --- somente RLS (sem filtro da aplicação) ---------------------------------------


def test_rls_filtra_sql_sem_where(app_engine: Engine, users: Users, seeded: dict[str, Account]) -> None:
    for name in ["ana", "bruno", "carla"]:
        uid = _uid(users, name)
        with user_transaction(app_engine, uid) as conn:
            rows = conn.execute(text("SELECT id, owner_id FROM accounts")).all()
            total = conn.execute(text("SELECT count(*), sum(initial_balance_cents) FROM accounts")).one()
        assert [r.id for r in rows] == [seeded[name].id]
        # Agregações também só enxergam as próprias linhas.
        assert total[0] == 1
        assert total[1] == seeded[name].initial_balance.cents


@pytest.mark.parametrize(("attacker", "victim"), PAIRS)
def test_rls_bloqueia_update_e_delete_sem_where_de_dono(
    app_engine: Engine, users: Users, seeded: dict[str, Account], attacker: str, victim: str
) -> None:
    target = seeded[victim].id
    with user_transaction(app_engine, _uid(users, attacker)) as conn:
        upd = conn.execute(text("UPDATE accounts SET name='x' WHERE id=:i"), {"i": target})
        dele = conn.execute(text("DELETE FROM accounts WHERE id=:i"), {"i": target})
        assert upd.rowcount == 0
        assert dele.rowcount == 0


@pytest.mark.parametrize(("attacker", "victim"), PAIRS)
def test_rls_impede_inserir_em_nome_de_outro(
    app_engine: Engine, users: Users, attacker: str, victim: str
) -> None:
    with (
        pytest.raises(ProgrammingError, match="row-level security"),
        user_transaction(app_engine, _uid(users, attacker)) as conn,
    ):
        conn.execute(
            text(
                "INSERT INTO accounts (owner_id, name, kind, initial_balance_cents, "
                "initial_balance_date) VALUES (:o, 'falsa', 'corrente', 1, '2026-10-01')"
            ),
            {"o": _uid(users, victim)},
        )


def test_rls_impede_transferir_conta_para_outro_dono(
    app_engine: Engine, users: Users, seeded: dict[str, Account]
) -> None:
    with (
        pytest.raises(ProgrammingError, match="row-level security"),
        user_transaction(app_engine, users.ana) as conn,
    ):
        conn.execute(
            text("UPDATE accounts SET owner_id=:b WHERE id=:i"),
            {"b": users.bruno, "i": seeded["ana"].id},
        )


def test_sem_identidade_nada_e_visivel_nem_gravavel(
    app_engine: Engine, users: Users, seeded: dict[str, Account]
) -> None:
    with app_engine.begin() as conn:
        assert conn.execute(text("SELECT app_current_user_id()")).scalar() is None
        assert conn.execute(text("SELECT count(*) FROM accounts")).scalar() == 0
        assert conn.execute(text("SELECT count(*) FROM users")).scalar() == 0
    with pytest.raises(ProgrammingError, match="row-level security"), app_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO accounts (owner_id, name, kind, initial_balance_cents, "
                "initial_balance_date) VALUES (:o, 'x', 'corrente', 1, '2026-10-01')"
            ),
            {"o": users.ana},
        )


def test_tabela_users_mostra_so_o_proprio_usuario(app_engine: Engine, users: Users) -> None:
    for uid in users.all():
        with user_transaction(app_engine, uid) as conn:
            rows = conn.execute(text("SELECT id FROM users")).scalars().all()
        assert rows == [uid]


def test_papel_da_aplicacao_nao_cria_usuarios_nem_altera_esquema(app_engine: Engine, users: Users) -> None:
    forbidden = [
        "INSERT INTO users (username, display_name, password_hash) VALUES ('intruso','X','!')",
        "UPDATE users SET username='x'",
        "UPDATE users SET is_active=false",
        "DELETE FROM users",
        "TRUNCATE accounts",
        "ALTER TABLE accounts DISABLE ROW LEVEL SECURITY",
        "ALTER TABLE accounts NO FORCE ROW LEVEL SECURITY",
        "DROP POLICY accounts_owner_isolation ON accounts",
        "CREATE TABLE intrusa (id int)",
    ]
    for stmt in forbidden:
        with pytest.raises(ProgrammingError), user_transaction(app_engine, users.ana) as conn:
            conn.execute(text(stmt))


def test_desligar_row_security_nao_contorna_a_politica(
    app_engine: Engine, users: Users, seeded: dict[str, Account]
) -> None:
    # Para papéis sem BYPASSRLS, row_security=off faz a consulta falhar em vez de
    # mostrar tudo.
    with (
        pytest.raises(DBAPIError, match="row-level security"),
        user_transaction(app_engine, users.ana) as conn,
    ):
        conn.execute(text("SET LOCAL row_security = off"))
        conn.execute(text("SELECT * FROM accounts")).all()


# --- somente filtro da aplicação (sem RLS) ---------------------------------------


@pytest.mark.parametrize(("attacker", "victim"), PAIRS)
def test_filtro_da_aplicacao_isola_mesmo_sem_rls(
    admin_engine: Engine, users: Users, seeded: dict[str, Account], attacker: str, victim: str
) -> None:
    # O administrador é superusuário e ignora RLS: só o WHERE owner_id protege aqui.
    uid = _uid(users, attacker)
    with admin_engine.begin() as conn:
        conn.execute(text("SELECT set_config('app.user_id', :u, true)"), {"u": str(uid)})
        assert conn.execute(text("SELECT count(*) FROM accounts")).scalar() == 3
        repo = AccountRepository(conn, uid)
        assert [a.id for a in repo.list()] == [seeded[attacker].id]
        assert repo.get(seeded[victim].id) is None
        assert repo.rename(seeded[victim].id, name="x", expected_version=1) is None
        assert repo.delete(seeded[victim].id) is False
        assert conn.execute(text("SELECT count(*) FROM accounts")).scalar() == 3


# --- relações entre entidades (chave estrangeira composta) -------------------------


@pytest.fixture
def probe_tables(admin_engine: Engine) -> Iterator[None]:
    """Par pai/filho com a mesma convenção das tabelas reais.

    A primeira relação real entre tabelas com dono chega na T2.2 (lançamentos ->
    contas) e será coberta por test_schema_conventions. Aqui a convenção é provada
    com tabelas descartáveis em um esquema separado.
    """
    ddl = [
        "CREATE SCHEMA probe",
        "GRANT USAGE ON SCHEMA probe TO fin_app",
        """CREATE TABLE probe.parent (
             id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
             owner_id uuid NOT NULL REFERENCES users(id),
             UNIQUE (owner_id, id))""",
        """CREATE TABLE probe.child (
             id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
             owner_id uuid NOT NULL REFERENCES users(id),
             parent_id uuid NOT NULL,
             FOREIGN KEY (owner_id, parent_id) REFERENCES probe.parent (owner_id, id))""",
        "GRANT SELECT, INSERT, UPDATE, DELETE ON probe.parent, probe.child TO fin_app",
    ]
    with admin_engine.begin() as conn:
        for stmt in ddl:
            conn.execute(text(stmt))
        for table in ["parent", "child"]:
            for stmt in owner_rls_statements(table):
                conn.execute(text("SET LOCAL search_path = probe, public"))
                conn.execute(text(stmt))
    try:
        yield
    finally:
        with admin_engine.begin() as conn:
            conn.execute(text("DROP SCHEMA probe CASCADE"))


@pytest.mark.parametrize(("attacker", "victim"), PAIRS)
def test_relacao_com_registro_de_outro_usuario_e_recusada_pelo_banco(
    app_engine: Engine,
    admin_engine: Engine,
    users: Users,
    probe_tables: None,
    attacker: str,
    victim: str,
) -> None:
    vid, aid = _uid(users, victim), _uid(users, attacker)
    with user_transaction(app_engine, vid) as conn:
        victim_parent = conn.execute(
            text("INSERT INTO probe.parent (owner_id) VALUES (:o) RETURNING id"), {"o": vid}
        ).scalar_one()

    # Pelo caminho normal (RLS + chave composta): o filho de A não aponta para o pai de B.
    with pytest.raises(IntegrityError), user_transaction(app_engine, aid) as conn:
        conn.execute(
            text("INSERT INTO probe.child (owner_id, parent_id) VALUES (:o, :p)"),
            {"o": aid, "p": victim_parent},
        )

    # Mesmo ignorando RLS (superusuário), a chave composta sozinha recusa a ligação.
    with pytest.raises(IntegrityError), admin_engine.begin() as conn:
        conn.execute(
            text("INSERT INTO probe.child (owner_id, parent_id) VALUES (:o, :p)"),
            {"o": aid, "p": victim_parent},
        )

    # Mover o filho legítimo para outro dono também é recusado.
    with user_transaction(app_engine, aid) as conn:
        own_parent = conn.execute(
            text("INSERT INTO probe.parent (owner_id) VALUES (:o) RETURNING id"), {"o": aid}
        ).scalar_one()
        conn.execute(
            text("INSERT INTO probe.child (owner_id, parent_id) VALUES (:o, :p)"),
            {"o": aid, "p": own_parent},
        )
    with pytest.raises(IntegrityError), admin_engine.begin() as conn:
        conn.execute(
            text("UPDATE probe.child SET parent_id = :p WHERE owner_id = :o"),
            {"o": aid, "p": victim_parent},
        )


def test_relacao_dentro_do_mesmo_dono_funciona(app_engine: Engine, users: Users, probe_tables: None) -> None:
    with user_transaction(app_engine, users.carla) as conn:
        parent = conn.execute(
            text("INSERT INTO probe.parent (owner_id) VALUES (:o) RETURNING id"),
            {"o": users.carla},
        ).scalar_one()
        conn.execute(
            text("INSERT INTO probe.child (owner_id, parent_id) VALUES (:o, :p)"),
            {"o": users.carla, "p": parent},
        )
        assert conn.execute(text("SELECT count(*) FROM probe.child")).scalar() == 1
    with user_transaction(app_engine, users.ana) as conn:
        assert conn.execute(text("SELECT count(*) FROM probe.child")).scalar() == 0
