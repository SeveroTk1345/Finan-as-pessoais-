"""Login, sessão, saída, troca de senha, limite de tentativas, CSRF e cabeçalhos."""

from __future__ import annotations

import subprocess
import sys

import pytest
from fastapi import FastAPI
from sqlalchemy import Engine, text

from app.core.security import hash_token
from tests.db.api_helpers import (
    ORIGIN,
    PASSWORD,
    SAFE_HEADERS,
    Api,
    build_app,
    logged_in,
    set_password,
)
from tests.db.conftest import BACKEND_DIR, DbInfo, Users


@pytest.fixture
def app(app_engine: Engine, admin_engine: Engine) -> FastAPI:
    with admin_engine.begin() as conn:
        conn.execute(text("DELETE FROM login_attempts"))
    return build_app(app_engine)


def test_login_cria_sessao_e_eu_retorna_o_usuario(
    app: FastAPI, admin_engine: Engine, users: Users
) -> None:
    api = logged_in(app, admin_engine, users.ana, "ana")
    r = api.get("/api/auth/eu")
    assert r.status_code == 200
    assert r.json() == {"id": str(users.ana), "usuario": "ana", "nome": "Ana"}


def test_cookie_de_sessao_e_seguro(app: FastAPI, admin_engine: Engine, users: Users) -> None:
    set_password(admin_engine, users.ana)
    r = Api(app).login("ana")
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie
    assert "samesite=strict" in cookie
    assert "path=/api" in cookie
    assert "max-age" not in cookie  # sem "manter conectado": some ao fechar o navegador
    r = Api(app).login("ana", remember=True)
    assert "max-age=2592000" in r.headers["set-cookie"].lower()


def test_cookie_secure_em_producao(app_engine: Engine, admin_engine: Engine, users: Users) -> None:
    set_password(admin_engine, users.ana)
    prod = build_app(app_engine, environment="production")
    r = Api(prod).login("ana")
    assert "secure" in r.headers["set-cookie"].lower()
    assert "strict-transport-security" in {k.lower() for k in r.headers}


def test_banco_guarda_so_o_hash_do_token(app: FastAPI, admin_engine: Engine, users: Users) -> None:
    api = logged_in(app, admin_engine, users.ana, "ana")
    token = api.client.cookies.get("fin_sessao")
    assert token
    with admin_engine.connect() as conn:
        hashes = conn.execute(text("SELECT token_hash FROM sessions")).scalars().all()
    assert [bytes(h) for h in hashes] == [hash_token(token)]
    assert token.encode() not in [bytes(h) for h in hashes]


@pytest.mark.parametrize(
    ("usuario", "senha"),
    [("ana", "senha-errada-123"), ("ninguem", PASSWORD), ("ANA ", "x")],
)
def test_login_invalido_tem_mensagem_unica(
    app: FastAPI, admin_engine: Engine, users: Users, usuario: str, senha: str
) -> None:
    set_password(admin_engine, users.ana)
    r = Api(app).login(usuario, senha)
    assert r.status_code == 401
    assert r.json() == {"detail": "Usuário ou senha incorretos."}
    assert "set-cookie" not in r.headers


def test_usuario_normalizado_aceita_maiusculas_e_espacos(
    app: FastAPI, admin_engine: Engine, users: Users
) -> None:
    set_password(admin_engine, users.ana)
    assert Api(app).login(" ANA ").status_code == 200


def test_usuario_desativado_nao_entra(app: FastAPI, admin_engine: Engine, users: Users) -> None:
    set_password(admin_engine, users.ana)
    with admin_engine.begin() as conn:
        conn.execute(text("UPDATE users SET is_active=false WHERE id=:u"), {"u": users.ana})
    assert Api(app).login("ana").status_code == 401


def test_sem_sessao_rotas_protegidas_respondem_401(app: FastAPI) -> None:
    r = Api(app).get("/api/auth/eu")
    assert r.status_code == 401
    assert r.json()["detail"] == "Sua sessão terminou. Entre novamente."
    api = Api(app)
    api.client.cookies.set("fin_sessao", "token-inventado", path="/api")
    assert api.get("/api/auth/eu").status_code == 401


def test_sair_invalida_a_sessao_no_servidor(
    app: FastAPI, admin_engine: Engine, users: Users
) -> None:
    api = logged_in(app, admin_engine, users.ana, "ana")
    token = api.client.cookies.get("fin_sessao")
    assert token
    assert api.post("/api/auth/sair", key=None).status_code == 204
    # Mesmo reapresentando o token antigo (ex.: botão voltar, cópia do cookie), nada feito.
    replay = Api(app)
    replay.client.cookies.set("fin_sessao", token, path="/api")
    assert replay.get("/api/auth/eu").status_code == 401


def test_sair_de_um_usuario_nao_afeta_os_outros(
    app: FastAPI, admin_engine: Engine, users: Users
) -> None:
    ana = logged_in(app, admin_engine, users.ana, "ana")
    bruno = logged_in(app, admin_engine, users.bruno, "bruno")
    carla = logged_in(app, admin_engine, users.carla, "carla")
    assert ana.post("/api/auth/sair", key=None).status_code == 204
    assert bruno.get("/api/auth/eu").json()["usuario"] == "bruno"
    assert carla.get("/api/auth/eu").json()["usuario"] == "carla"


def test_sessao_expira_por_inatividade_e_por_prazo(
    app: FastAPI, admin_engine: Engine, users: Users
) -> None:
    api = logged_in(app, admin_engine, users.ana, "ana")
    with admin_engine.begin() as conn:
        conn.execute(text("UPDATE sessions SET last_seen_at = now() - interval '31 minutes'"))
    assert api.get("/api/auth/eu").status_code == 401
    with admin_engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM sessions")).scalar() == 0

    api = logged_in(app, admin_engine, users.ana, "ana")
    with admin_engine.begin() as conn:
        conn.execute(text("UPDATE sessions SET expires_at = now() - interval '1 second'"))
    assert api.get("/api/auth/eu").status_code == 401


def test_sessao_manter_conectado_dura_mais(
    app: FastAPI, admin_engine: Engine, users: Users
) -> None:
    set_password(admin_engine, users.ana)
    api = Api(app)
    api.login("ana", remember=True)
    with admin_engine.begin() as conn:
        conn.execute(text("UPDATE sessions SET last_seen_at = now() - interval '2 days'"))
    assert api.get("/api/auth/eu").status_code == 200


def test_limite_de_tentativas_por_usuario(app: FastAPI, admin_engine: Engine, users: Users) -> None:
    set_password(admin_engine, users.ana)
    api = Api(app)
    for _ in range(5):
        assert api.login("ana", "senha-errada-xyz").status_code == 401
    # Bloqueado mesmo com a senha certa.
    r = api.login("ana")
    assert r.status_code == 429
    assert "15 minutos" in r.json()["detail"]
    # Outros usuários não são afetados pelo bloqueio da Ana.
    set_password(admin_engine, users.bruno)
    assert api.login("bruno").status_code == 200


def test_troca_de_senha(app: FastAPI, admin_engine: Engine, users: Users) -> None:
    api = logged_in(app, admin_engine, users.ana, "ana")
    other_device = logged_in(app, admin_engine, users.ana, "ana")
    bruno = logged_in(app, admin_engine, users.bruno, "bruno")

    r = api.post(
        "/api/auth/trocar-senha",
        {"senha_atual": "errada-errada", "nova_senha": "nova-senha-forte-1"},
        key=None,
    )
    assert r.status_code == 400
    assert r.json()["campos"] == {"senha_atual": "Senha incorreta."}

    r = api.post(
        "/api/auth/trocar-senha", {"senha_atual": PASSWORD, "nova_senha": "curta"}, key=None
    )
    assert r.status_code == 400
    assert "10 caracteres" in r.json()["detail"]

    r = api.post(
        "/api/auth/trocar-senha",
        {"senha_atual": PASSWORD, "nova_senha": "nova-senha-forte-1"},
        key=None,
    )
    assert r.status_code == 204
    assert api.get("/api/auth/eu").status_code == 200  # sessão atual continua
    assert other_device.get("/api/auth/eu").status_code == 401  # outras da Ana encerradas
    assert bruno.get("/api/auth/eu").status_code == 200  # Bruno não é afetado
    assert Api(app).login("ana", "nova-senha-forte-1").status_code == 200
    assert Api(app).login("ana", PASSWORD).status_code == 401


# --- CSRF e cabeçalhos -----------------------------------------------------------


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Origin": ORIGIN},  # sem X-Requested-With
        {"X-Requested-With": "fetch"},  # sem Origin
        {"Origin": "https://site-malicioso.example", "X-Requested-With": "fetch"},
        {"Origin": "null", "X-Requested-With": "fetch"},
    ],
)
def test_csrf_recusa_origem_ou_cabecalho_ausente(
    app: FastAPI, admin_engine: Engine, users: Users, headers: dict[str, str]
) -> None:
    api = logged_in(app, admin_engine, users.ana, "ana")
    r = api.client.post("/api/auth/sair", headers=headers)
    assert r.status_code == 403
    # A sessão não foi encerrada pela requisição forjada.
    assert api.get("/api/auth/eu").status_code == 200


def test_login_tambem_exige_origem(app: FastAPI, admin_engine: Engine, users: Users) -> None:
    set_password(admin_engine, users.ana)
    r = Api(app).client.post("/api/auth/entrar", json={"usuario": "ana", "senha": PASSWORD})
    assert r.status_code == 403


def test_cabecalhos_de_seguranca(app: FastAPI, admin_engine: Engine, users: Users) -> None:
    api = logged_in(app, admin_engine, users.ana, "ana")
    r = api.get("/api/auth/eu")
    assert r.headers["cache-control"] == "no-store"
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert "frame-ancestors 'none'" in r.headers["content-security-policy"]
    assert r.headers["referrer-policy"] == "no-referrer"


def test_erro_de_validacao_em_portugues(app: FastAPI) -> None:
    r = Api(app).client.post("/api/auth/entrar", json={"usuario": ""}, headers=SAFE_HEADERS)
    assert r.status_code == 422
    body = r.json()
    assert body["detail"] == "Confira os campos destacados."
    assert body["campos"]["usuario"] == "Preencha este campo."
    assert body["campos"]["senha"] == "Preencha este campo."


# --- linha de comando ------------------------------------------------------------


def _cli(test_db: DbInfo, *args: str, stdin: str = "") -> subprocess.CompletedProcess[str]:
    env = {
        "FIN_DATABASE_ADMIN_URL": test_db.admin_url.render_as_string(False),
        "PATH": "/usr/bin:/bin",
    }
    return subprocess.run(  # noqa: S603
        [sys.executable, "-m", "app.cli", *args],
        input=stdin,
        capture_output=True,
        text=True,
        cwd=BACKEND_DIR,
        env=env,
        check=False,
    )


def test_cli_cria_usuario_que_consegue_entrar(
    test_db: DbInfo, app: FastAPI, admin_engine: Engine, users: Users
) -> None:
    r = _cli(
        test_db,
        "criar-usuario",
        "--usuario",
        "Diana",
        "--nome",
        "Diana",
        "--senha-stdin",
        stdin="minha-senha-forte-1\n",
    )
    assert r.returncode == 0, r.stderr
    assert Api(app).login("diana", "minha-senha-forte-1").status_code == 200

    dup = _cli(
        test_db,
        "criar-usuario",
        "--usuario",
        "diana",
        "--nome",
        "D",
        "--senha-stdin",
        stdin="outra-senha-123\n",
    )
    assert dup.returncode != 0
    assert "já existe" in dup.stderr

    weak = _cli(
        test_db,
        "criar-usuario",
        "--usuario",
        "eva",
        "--nome",
        "Eva",
        "--senha-stdin",
        stdin="curta\n",
    )
    assert weak.returncode != 0

    listed = _cli(test_db, "listar-usuarios")
    assert "diana\tDiana\tativo" in listed.stdout


def test_cli_redefinir_senha_encerra_sessoes_so_do_usuario(
    test_db: DbInfo, app: FastAPI, admin_engine: Engine, users: Users
) -> None:
    ana = logged_in(app, admin_engine, users.ana, "ana")
    bruno = logged_in(app, admin_engine, users.bruno, "bruno")
    r = _cli(
        test_db,
        "redefinir-senha",
        "--usuario",
        "ana",
        "--senha-stdin",
        stdin="senha-redefinida-1\n",
    )
    assert r.returncode == 0, r.stderr
    assert ana.get("/api/auth/eu").status_code == 401
    assert bruno.get("/api/auth/eu").status_code == 200
    assert Api(app).login("ana", "senha-redefinida-1").status_code == 200
