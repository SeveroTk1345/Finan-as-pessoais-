"""Backup cifrado do banco gerenciado e restauração em banco vazio, com bancos reais.

Os scripts rodam como no GitHub Actions: endereço do dono do banco (estilo Neon, sem
superusuário) e frase-senha por variável de ambiente.
"""

from __future__ import annotations

import os
import secrets
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL

from app.deploy_start import ensure_app_role, run_migrations
from app.services.user_setup import seed_user_defaults
from tests.db.conftest import BACKEND_DIR, DbInfo

SCRIPTS = BACKEND_DIR.parent / "scripts"
MARCA = "marcador-sintetico-do-backup"

pytestmark = pytest.mark.skipif(
    not all(shutil.which(t) for t in ("pg_dump", "pg_restore", "psql", "gpg")),
    reason="precisa de pg_dump, pg_restore, psql e gpg",
)


def _url(u: URL) -> str:
    return u.render_as_string(hide_password=False)


def _run(script: str, *args: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    base = {"PATH": os.environ["PATH"], "HOME": os.environ.get("HOME", ""), "LANG": "C.UTF-8"}
    return subprocess.run(  # noqa: S603 - scripts do próprio repositório
        [str(SCRIPTS / script), *args], env={**base, **env}, capture_output=True, text=True, check=False
    )


def _counts(url: str) -> dict[str, int]:
    engine = create_engine(url)
    with engine.connect() as conn:
        names = conn.execute(
            text("SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY 1")
        ).scalars()
        out = {n: int(conn.execute(text(f'SELECT count(*) FROM public."{n}"')).scalar_one()) for n in names}
    engine.dispose()
    return out


@pytest.fixture
def producao(test_db: DbInfo, neon_like_factory: Callable[[], URL]) -> str:
    """Banco "de produção" migrado, com duas contas sintéticas e suas categorias."""
    url = _url(neon_like_factory())
    ensure_app_role(url, test_db.app_password)
    run_migrations(url)
    engine = create_engine(url.replace("postgresql://", "postgresql+psycopg://", 1))
    with engine.begin() as conn:
        for nome in ("ana", "bruno"):
            uid = conn.execute(
                text(
                    "INSERT INTO users (username, display_name, password_hash) VALUES (:u, :d, 'x') RETURNING id"
                ),
                {"u": nome, "d": f"{nome} {MARCA}"},
            ).scalar_one()
            seed_user_defaults(conn, uid)
    engine.dispose()
    return url


def test_ida_e_volta_cifrada(
    tmp_path: Path, test_db: DbInfo, neon_like_factory: Callable[[], URL], producao: str
) -> None:
    frase = secrets.token_hex(20)
    arquivo = tmp_path / "fin.dump.gpg"
    r = _run(
        "backup-cifrado.sh",
        str(arquivo),
        env={"FIN_DATABASE_ADMIN_URL": producao, "FIN_BACKUP_PASSPHRASE": frase, "HOME": str(tmp_path)},
    )
    assert r.returncode == 0, r.stderr
    assert frase not in r.stdout + r.stderr
    dados = arquivo.read_bytes()
    assert MARCA.encode() not in dados  # cifrado: o conteúdo não aparece
    assert (tmp_path / "fin.dump.gpg.sha256").exists()
    assert sorted(p.name for p in tmp_path.iterdir() if not p.name.startswith(".")) == [
        "fin.dump.gpg",
        "fin.dump.gpg.sha256",
    ]  # nenhuma cópia aberta ficou para trás

    destino = _url(neon_like_factory())
    env = {
        "FIN_RESTORE_DATABASE_URL": destino,
        "FIN_BACKUP_PASSPHRASE": frase,
        "FIN_DATABASE_ADMIN_URL": producao,
        "HOME": str(tmp_path),
    }
    errada = _run("restaurar-cifrado.sh", str(arquivo), env={**env, "FIN_BACKUP_PASSPHRASE": "x" * 30})
    assert errada.returncode != 0 and "frase-senha errada" in errada.stderr

    r = _run("restaurar-cifrado.sh", str(arquivo), env=env)
    assert r.returncode == 0, r.stderr
    assert MARCA not in r.stdout  # só contagens, nunca conteúdo
    original = _counts(producao.replace("postgresql://", "postgresql+psycopg://", 1))
    assert original["users"] == 2 and original["categories"] > 0
    assert _counts(destino.replace("postgresql://", "postgresql+psycopg://", 1)) == original

    # Restaurado continua isolado: a API (fin_app) sem identidade não vê ninguém.
    api = create_engine(
        destino.replace("postgresql://", "postgresql+psycopg://", 1).replace(
            destino.split("//", 1)[1].split("@", 1)[0], f"fin_app:{test_db.app_password}", 1
        )
    )
    with api.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM users")).scalar() == 0
    api.dispose()

    # De novo no mesmo banco: já tem tabelas, recusa.
    again = _run("restaurar-cifrado.sh", str(arquivo), env=env)
    assert again.returncode != 0 and "já tem tabelas" in again.stderr


def test_restauracao_recusa_o_banco_de_producao(tmp_path: Path, producao: str) -> None:
    arquivo = tmp_path / "x.dump.gpg"
    arquivo.write_bytes(b"qualquer")
    r = _run(
        "restaurar-cifrado.sh",
        str(arquivo),
        env={
            "FIN_RESTORE_DATABASE_URL": producao.replace("postgresql://", "postgresql+psycopg://", 1),
            "FIN_DATABASE_ADMIN_URL": producao,
            "FIN_BACKUP_PASSPHRASE": "y" * 30,
        },
    )
    assert r.returncode != 0 and "produção" in r.stderr


def test_backup_recusa_frase_curta(tmp_path: Path) -> None:
    r = _run(
        "backup-cifrado.sh",
        str(tmp_path / "a.gpg"),
        env={"FIN_DATABASE_ADMIN_URL": "postgresql://a:b@127.0.0.1:1/c", "FIN_BACKUP_PASSPHRASE": "curta"},
    )
    assert r.returncode != 0 and "24 caracteres" in r.stderr
    assert not (tmp_path / "a.gpg").exists()
