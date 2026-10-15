"""Backup e restauração reais com scripts/backup.sh e scripts/restore.sh.

Critério: não basta o arquivo existir. A cópia precisa ser restaurada em um banco
novo, com conteúdo idêntico ao original (tabela por tabela), políticas de RLS e
permissões preservadas, e isolamento funcionando no banco restaurado.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Iterator
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import URL

from app.db.engine import make_engine
from app.db.identity import user_transaction
from app.db.repositories.accounts import AccountRepository
from app.domain.money import Money
from tests.db.conftest import DbInfo, Users

REPO_DIR = Path(__file__).resolve().parents[3]
BACKUP = REPO_DIR / "scripts" / "backup.sh"
RESTORE = REPO_DIR / "scripts" / "restore.sh"
TOOLS = ["pg_dump", "pg_restore", "psql", "createdb", "dropdb", "sha256sum"]

pytestmark = pytest.mark.skipif(
    any(shutil.which(t) is None for t in TOOLS),
    reason="ferramentas do cliente PostgreSQL 16 não encontradas no PATH",
)

TABLES = ["users", "accounts", "sessions", "idempotency_keys", "alembic_version"]


def _pg_env(url: URL, database: str) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith("PG")}
    env.update(
        PGHOST=url.host or "127.0.0.1",
        PGPORT=str(url.port or 5432),
        PGUSER=url.username or "",
        PGPASSWORD=str(url.password or ""),
        PGDATABASE=database,
    )
    return env


def _run(cmd: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, env=env, capture_output=True, text=True, check=False)  # noqa: S603


def _fingerprint(engine: Engine) -> dict[str, tuple[int, str]]:
    """Contagem e hash MD5 de todas as linhas de cada tabela, em ordem estável."""
    result: dict[str, tuple[int, str]] = {}
    with engine.connect() as conn:
        for table in TABLES:
            count, digest = conn.execute(
                text(
                    f"SELECT count(*), coalesce(md5(string_agg(t::text, '|' ORDER BY t::text)), '') "
                    f"FROM {table} t"
                )
            ).one()
            result[table] = (count, digest)
    return result


def _database_exists(admin: Engine, name: str) -> bool:
    with admin.connect() as conn:
        return bool(
            conn.execute(text("SELECT 1 FROM pg_database WHERE datname=:n"), {"n": name}).scalar()
        )


@pytest.fixture
def server_admin(test_db: DbInfo) -> Iterator[Engine]:
    engine = create_engine(test_db.admin_url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    yield engine
    engine.dispose()


@pytest.fixture
def restored_names(server_admin: Engine) -> Iterator[list[str]]:
    names: list[str] = []
    yield names
    with server_admin.connect() as conn:
        for name in names:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))


@pytest.fixture
def populated(app_engine: Engine, users: Users) -> Users:
    """Dados sintéticos para os três usuários, incluindo texto com acentos e aspas."""
    data = {
        users.ana: [("Carteira", "especie", 5025), ("Conta 'principal' ção", "corrente", -1999)],
        users.bruno: [("Poupança", "poupanca", 100000000)],
        users.carla: [("Outra", "outra", 0), ("Reserva", "poupanca", 1)],
    }
    for uid, accounts in data.items():
        with user_transaction(app_engine, uid) as conn:
            repo = AccountRepository(conn, uid)
            for name, kind, cents in accounts:
                repo.create(
                    name=name,
                    kind=kind,  # type: ignore[arg-type]
                    initial_balance=Money(cents),
                    initial_balance_date=date(2026, 10, 1),
                )
    return users


def _backup(test_db: DbInfo, backup_dir: Path, keep: int = 14) -> Path:
    env = _pg_env(test_db.admin_url, test_db.name)
    env.update(FIN_BACKUP_DIR=str(backup_dir), FIN_BACKUP_KEEP=str(keep))
    proc = _run(["sh", str(BACKUP)], env)
    assert proc.returncode == 0, proc.stderr
    dumps = sorted(backup_dir.glob("fin_*.dump"))
    assert dumps, "nenhum backup criado"
    return dumps[-1]


def test_backup_e_restauracao_completa(
    test_db: DbInfo,
    admin_engine: Engine,
    server_admin: Engine,
    populated: Users,
    restored_names: list[str],
    tmp_path: Path,
) -> None:
    dump = _backup(test_db, tmp_path)
    assert dump.stat().st_size > 0
    assert (tmp_path / f"{dump.name}.sha256").exists()
    # Permissão só do dono: a cópia contém dados financeiros.
    assert oct(dump.stat().st_mode & 0o777) == "0o600"
    assert not list(tmp_path.glob(".*parcial"))

    target = "fin_restaurado_teste"
    restored_names.append(target)
    proc = _run(["sh", str(RESTORE), str(dump), target], _pg_env(test_db.admin_url, "postgres"))
    assert proc.returncode == 0, proc.stderr

    restored_admin = create_engine(test_db.admin_url.set(database=target))
    try:
        # 1. Conteúdo idêntico, tabela por tabela.
        original = _fingerprint(admin_engine)
        restored = _fingerprint(restored_admin)
        assert restored == original
        assert original["accounts"][0] == 5
        assert original["users"][0] == 3

        # 2. RLS e políticas preservadas.
        with restored_admin.connect() as conn:
            rls = conn.execute(
                text(
                    "SELECT relname, relrowsecurity, relforcerowsecurity FROM pg_class "
                    "WHERE relname IN ('users','accounts') ORDER BY relname"
                )
            ).all()
            policies = (
                conn.execute(text("SELECT policyname FROM pg_policies ORDER BY policyname"))
                .scalars()
                .all()
            )
            public_connect = conn.execute(
                text("SELECT has_database_privilege('public', current_database(), 'CONNECT')")
            ).scalar()
        assert [tuple(r) for r in rls] == [("accounts", True, True), ("users", True, True)]
        assert policies == [
            "accounts_owner_isolation",
            "idempotency_keys_owner_isolation",
            "sessions_owner_isolation",
            "users_self",
        ]
        assert public_connect is False
    finally:
        restored_admin.dispose()

    # 3. Isolamento funcionando no banco restaurado, com o papel da aplicação.
    restored_app = make_engine(test_db.app_url.set(database=target).render_as_string(False))
    try:
        for uid, expected in [(populated.ana, 2), (populated.bruno, 1), (populated.carla, 2)]:
            with user_transaction(restored_app, uid) as conn:
                owners = conn.execute(text("SELECT owner_id FROM accounts")).scalars().all()
            assert len(owners) == expected
            assert set(owners) == {uid}
    finally:
        restored_app.dispose()


def test_restauracao_recusa_arquivo_corrompido_sem_criar_banco(
    test_db: DbInfo, server_admin: Engine, populated: Users, tmp_path: Path
) -> None:
    dump = _backup(test_db, tmp_path)
    data = bytearray(dump.read_bytes())
    data[len(data) // 2] ^= 0xFF
    dump.write_bytes(bytes(data))

    proc = _run(
        ["sh", str(RESTORE), str(dump), "fin_nao_deve_existir"],
        _pg_env(test_db.admin_url, "postgres"),
    )
    assert proc.returncode != 0
    assert "SHA-256" in proc.stderr
    assert not _database_exists(server_admin, "fin_nao_deve_existir")


def test_restauracao_recusa_sem_arquivo_de_hash(
    test_db: DbInfo, server_admin: Engine, populated: Users, tmp_path: Path
) -> None:
    dump = _backup(test_db, tmp_path)
    (tmp_path / f"{dump.name}.sha256").unlink()
    proc = _run(
        ["sh", str(RESTORE), str(dump), "fin_sem_hash"], _pg_env(test_db.admin_url, "postgres")
    )
    assert proc.returncode != 0
    assert not _database_exists(server_admin, "fin_sem_hash")


def test_restauracao_nunca_sobrescreve_banco_existente(
    test_db: DbInfo, admin_engine: Engine, populated: Users, tmp_path: Path
) -> None:
    dump = _backup(test_db, tmp_path)
    before = _fingerprint(admin_engine)
    proc = _run(
        ["sh", str(RESTORE), str(dump), test_db.name], _pg_env(test_db.admin_url, "postgres")
    )
    assert proc.returncode != 0
    assert "já existe" in proc.stderr
    assert _fingerprint(admin_engine) == before


@pytest.mark.parametrize("bad", ["Maiuscula", "com-hifen", "x;DROP DATABASE postgres", ""])
def test_restauracao_recusa_nome_de_banco_invalido(
    test_db: DbInfo, populated: Users, tmp_path: Path, bad: str
) -> None:
    dump = _backup(test_db, tmp_path)
    proc = _run(["sh", str(RESTORE), str(dump), bad], _pg_env(test_db.admin_url, "postgres"))
    assert proc.returncode != 0


def test_restauracao_que_falha_no_meio_remove_o_banco_parcial(
    test_db: DbInfo, server_admin: Engine, populated: Users, tmp_path: Path
) -> None:
    # Arquivo com hash válido, mas que não é um dump: passa no SHA-256 e falha no pg_restore.
    fake = tmp_path / "fin_20260101T000000Z_1.dump"
    fake.write_bytes(b"isto nao e um dump do postgres")
    subprocess.run(  # noqa: S603
        ["sha256sum", fake.name],  # noqa: S607
        cwd=tmp_path,
        check=True,
        stdout=(tmp_path / f"{fake.name}.sha256").open("w"),
    )
    proc = _run(
        ["sh", str(RESTORE), str(fake), "fin_parcial"], _pg_env(test_db.admin_url, "postgres")
    )
    assert proc.returncode != 0
    assert not _database_exists(server_admin, "fin_parcial")


def test_backup_com_falha_de_conexao_nao_deixa_arquivo(test_db: DbInfo, tmp_path: Path) -> None:
    env = _pg_env(test_db.admin_url, test_db.name)
    env.update(PGPASSWORD="senha-errada", FIN_BACKUP_DIR=str(tmp_path))
    proc = _run(["sh", str(BACKUP)], env)
    assert proc.returncode != 0
    assert list(tmp_path.iterdir()) == []


def test_rotacao_mantem_somente_as_mais_recentes(
    test_db: DbInfo, populated: Users, tmp_path: Path
) -> None:
    old = [
        "fin_20200101T000000Z_1.dump",
        "fin_20200102T000000Z_2.dump",
        "fin_20200103T000000Z_3.dump",
    ]
    for name in old:
        (tmp_path / name).write_bytes(b"antigo")
        (tmp_path / f"{name}.sha256").write_text("x")
    unrelated = tmp_path / "anotacoes.txt"
    unrelated.write_text("não apagar")

    newest = _backup(test_db, tmp_path, keep=2)

    remaining = sorted(p.name for p in tmp_path.glob("fin_*.dump"))
    assert remaining == ["fin_20200103T000000Z_3.dump", newest.name]
    assert not (tmp_path / "fin_20200101T000000Z_1.dump.sha256").exists()
    assert unrelated.exists()


def test_backup_recusa_keep_invalido(test_db: DbInfo, tmp_path: Path) -> None:
    for keep in ["0", "abc", "-1"]:
        env = _pg_env(test_db.admin_url, test_db.name)
        env.update(FIN_BACKUP_DIR=str(tmp_path), FIN_BACKUP_KEEP=keep)
        assert _run(["sh", str(BACKUP)], env).returncode != 0
