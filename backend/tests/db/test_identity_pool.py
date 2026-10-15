"""A identidade nunca sobrevive à transação nem passa de um usuário para outro
através de uma conexão reutilizada do pool."""

from __future__ import annotations

import threading
from collections.abc import Iterator
from datetime import date
from uuid import UUID

import pytest
from sqlalchemy import Engine, text

from app.db.engine import make_engine
from app.db.identity import user_transaction
from app.db.repositories.accounts import AccountRepository
from app.domain.money import Money
from tests.db.conftest import DbInfo, Users


@pytest.fixture
def single_conn_engine(test_db: DbInfo) -> Iterator[Engine]:
    """Pool com UMA conexão: toda transação reutiliza a mesma sessão do PostgreSQL."""
    engine = make_engine(test_db.app_url.render_as_string(False), pool_size=1, max_overflow=0)
    yield engine
    engine.dispose()


def _seed(engine: Engine, users: Users) -> None:
    for uid, name in [(users.ana, "A"), (users.bruno, "B"), (users.carla, "C")]:
        with user_transaction(engine, uid) as conn:
            AccountRepository(conn, uid).create(
                name=name,
                kind="especie",
                initial_balance=Money(100),
                initial_balance_date=date(2026, 10, 1),
            )


def _visible(engine: Engine, uid: UUID) -> tuple[int, list[UUID]]:
    with user_transaction(engine, uid) as conn:
        pid = conn.execute(text("SELECT pg_backend_pid()")).scalar_one()
        owners = conn.execute(text("SELECT owner_id FROM accounts")).scalars().all()
    return pid, list(owners)


def test_mesma_conexao_alternando_usuarios(single_conn_engine: Engine, users: Users) -> None:
    _seed(single_conn_engine, users)
    pids = set()
    for uid in [users.ana, users.bruno, users.carla, users.ana, users.carla, users.bruno]:
        pid, owners = _visible(single_conn_engine, uid)
        pids.add(pid)
        assert owners == [uid]
    # Prova de que foi realmente a mesma sessão do servidor o tempo todo.
    assert len(pids) == 1


def test_apos_commit_a_conexao_volta_sem_identidade(single_conn_engine: Engine, users: Users) -> None:
    _seed(single_conn_engine, users)
    _visible(single_conn_engine, users.ana)
    with single_conn_engine.begin() as conn:
        assert conn.execute(text("SELECT app_current_user_id()")).scalar() is None
        assert conn.execute(text("SELECT count(*) FROM accounts")).scalar() == 0


def test_apos_erro_e_rollback_a_identidade_nao_vaza(single_conn_engine: Engine, users: Users) -> None:
    _seed(single_conn_engine, users)
    with pytest.raises(RuntimeError), user_transaction(single_conn_engine, users.ana) as conn:
        conn.execute(text("SELECT 1"))
        raise RuntimeError("falha no meio da operação")
    with single_conn_engine.begin() as conn:
        assert conn.execute(text("SELECT app_current_user_id()")).scalar() is None
    _, owners = _visible(single_conn_engine, users.bruno)
    assert owners == [users.bruno]


def test_set_de_sessao_feito_por_engano_e_limpo_ao_reutilizar(
    single_conn_engine: Engine, users: Users
) -> None:
    _seed(single_conn_engine, users)
    # Simula um bug: identidade definida com escopo de SESSÃO (false), não de transação.
    with single_conn_engine.begin() as conn:
        conn.execute(text("SELECT set_config('app.user_id', :u, false)"), {"u": str(users.ana)})
        pid_bug = conn.execute(text("SELECT pg_backend_pid()")).scalar_one()
    # Próxima retirada do pool: mesma sessão, mas a identidade foi apagada no checkout.
    with single_conn_engine.begin() as conn:
        assert conn.execute(text("SELECT pg_backend_pid()")).scalar_one() == pid_bug
        assert conn.execute(text("SELECT app_current_user_id()")).scalar() is None
        assert conn.execute(text("SELECT count(*) FROM accounts")).scalar() == 0


def test_identidade_precisa_ser_uuid(single_conn_engine: Engine, users: Users) -> None:
    for bad in [str(users.ana), None, 1]:
        with (
            pytest.raises(TypeError),
            user_transaction(single_conn_engine, bad),  # type: ignore[arg-type]
        ):
            pass


def test_concorrencia_com_tres_usuarios_em_paralelo(test_db: DbInfo, users: Users) -> None:
    """Várias threads alternando usuários sobre um pool pequeno, conferindo a cada
    transação que só as próprias linhas aparecem."""
    engine = make_engine(test_db.app_url.render_as_string(False), pool_size=2, max_overflow=0)
    try:
        _seed(engine, users)
        errors: list[str] = []
        pids: set[int] = set()
        lock = threading.Lock()

        def worker(order: list[UUID]) -> None:
            for _ in range(25):
                for uid in order:
                    pid, owners = _visible(engine, uid)
                    with lock:
                        pids.add(pid)
                        if owners != [uid]:
                            errors.append(f"{uid} viu {owners}")

        orders = [
            [users.ana, users.bruno, users.carla],
            [users.carla, users.ana, users.bruno],
            [users.bruno, users.carla, users.ana],
            [users.ana, users.carla, users.bruno],
        ]
        threads = [threading.Thread(target=worker, args=(o,)) for o in orders]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert errors == []
        # 4 threads disputando 2 conexões: as conexões foram de fato reutilizadas.
        assert len(pids) <= 2
    finally:
        engine.dispose()
