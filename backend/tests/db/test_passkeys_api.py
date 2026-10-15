"""Entrar com digital ou rosto (passkeys): fluxo completo, ataques e isolamento."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI
from sqlalchemy import Engine, text
from sqlalchemy.exc import ProgrammingError

from tests.db.api_helpers import ORIGIN, SAFE_HEADERS, Api, build_app, logged_in
from tests.db.conftest import Users
from tests.db.soft_authenticator import SoftAuthenticator, unb64u


@pytest.fixture
def app(app_engine: Engine, admin_engine: Engine) -> FastAPI:
    with admin_engine.begin() as conn:
        conn.execute(text("DELETE FROM login_attempts"))
    return build_app(app_engine)


def _activate(api: Api, device: SoftAuthenticator, *, user_verified: bool = True) -> Any:
    r = api.post("/api/auth/digital/cadastro/opcoes", key=None)
    assert r.status_code == 200, r.text
    body = r.json()
    cred = device.create(body["opcoes"], user_verified=user_verified)
    return api.post(
        "/api/auth/digital/cadastro",
        {"desafio_id": body["desafio_id"], "credencial": cred, "nome_aparelho": "iPhone"},
        key=None,
    )


def _login_options(api: Api) -> dict[str, Any]:
    r = api.post("/api/auth/digital/entrar/opcoes", key=None)
    assert r.status_code == 200, r.text
    return dict(r.json())


def _login(api: Api, challenge: dict[str, Any], credential: dict[str, Any], remember: bool = False) -> Any:
    return api.post(
        "/api/auth/digital/entrar",
        {"desafio_id": challenge["desafio_id"], "credencial": credential, "manter_conectado": remember},
        key=None,
    )


@pytest.fixture
def ana_device(app: FastAPI, admin_engine: Engine, users: Users) -> SoftAuthenticator:
    device = SoftAuthenticator(ORIGIN)
    r = _activate(logged_in(app, admin_engine, users.ana, "ana"), device)
    assert r.status_code == 201, r.text
    return device


def test_ativa_e_entra_sem_digitar_usuario_nem_senha(
    app: FastAPI, admin_engine: Engine, users: Users
) -> None:
    api = logged_in(app, admin_engine, users.ana, "ana")
    opts = api.post("/api/auth/digital/cadastro/opcoes", key=None).json()["opcoes"]
    # Sensor do próprio aparelho, credencial guardada nele e biometria obrigatória.
    assert opts["rp"]["id"] == "localhost"
    assert opts["authenticatorSelection"] == {
        "authenticatorAttachment": "platform",
        "residentKey": "required",
        "requireResidentKey": True,
        "userVerification": "required",
    }
    device = SoftAuthenticator(ORIGIN)
    r = _activate(api, device)
    assert r.status_code == 201, r.text
    assert r.json()["nome"] == "iPhone"
    assert [p["nome"] for p in api.get("/api/auth/digital").json()] == ["iPhone"]

    fresh = Api(app)  # outro navegador, ninguém conectado
    ch = _login_options(fresh)
    assert ch["opcoes"]["userVerification"] == "required"
    assert ch["opcoes"].get("allowCredentials", []) == []  # não revela quem tem digital
    r = _login(fresh, ch, device.get(ch["opcoes"]), remember=True)
    assert r.status_code == 200, r.text
    assert r.json()["usuario"] == "ana"
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie and "max-age=2592000" in cookie
    assert fresh.get("/api/auth/eu").json()["usuario"] == "ana"
    assert api.get("/api/auth/digital").json()[0]["usada_em"] is not None


def test_banco_guarda_so_a_chave_publica(
    admin_engine: Engine, users: Users, ana_device: SoftAuthenticator
) -> None:
    with admin_engine.connect() as conn:
        row = conn.execute(text("SELECT credential_id, public_key FROM passkeys")).one()
    assert bytes(row.credential_id) == ana_device.credentials[0].id
    # Chave COSE pública (sem o "d" privado da curva elíptica).
    import cbor2

    assert -4 not in cbor2.loads(bytes(row.public_key))


def test_sem_confirmar_digital_ou_rosto_nao_ativa(app: FastAPI, admin_engine: Engine, users: Users) -> None:
    api = logged_in(app, admin_engine, users.ana, "ana")
    r = _activate(api, SoftAuthenticator(ORIGIN), user_verified=False)
    assert r.status_code == 400
    assert api.get("/api/auth/digital").json() == []


def test_sem_confirmar_digital_ou_rosto_nao_entra(app: FastAPI, ana_device: SoftAuthenticator) -> None:
    fresh = Api(app)
    ch = _login_options(fresh)
    r = _login(fresh, ch, ana_device.get(ch["opcoes"], user_verified=False))
    assert r.status_code == 401
    assert "set-cookie" not in r.headers


def test_desafio_e_de_uso_unico(app: FastAPI, ana_device: SoftAuthenticator) -> None:
    fresh = Api(app)
    ch = _login_options(fresh)
    cred = ana_device.get(ch["opcoes"])
    assert _login(fresh, ch, cred).status_code == 200
    # Quem capturasse a resposta não conseguiria reutilizá-la.
    assert _login(Api(app), ch, cred).status_code == 401


def test_desafio_expirado(app: FastAPI, admin_engine: Engine, ana_device: SoftAuthenticator) -> None:
    fresh = Api(app)
    ch = _login_options(fresh)
    with admin_engine.begin() as conn:
        conn.execute(text("UPDATE webauthn_challenges SET expires_at = now() - interval '1 second'"))
    r = _login(fresh, ch, ana_device.get(ch["opcoes"]))
    assert r.status_code == 401
    assert "expirou" in r.json()["detail"]


def test_site_falso_nao_consegue_usar_a_resposta(app: FastAPI, ana_device: SoftAuthenticator) -> None:
    fresh = Api(app)
    ch = _login_options(fresh)
    r = _login(fresh, ch, ana_device.get(ch["opcoes"], origin="https://golpe.exemplo"))
    assert r.status_code == 401


def test_contador_que_volta_indica_copia_e_e_recusado(app: FastAPI, ana_device: SoftAuthenticator) -> None:
    ch = _login_options(Api(app))
    assert _login(Api(app), ch, ana_device.get(ch["opcoes"], sign_count=5)).status_code == 200
    ch = _login_options(Api(app))
    assert _login(Api(app), ch, ana_device.get(ch["opcoes"], sign_count=5)).status_code == 401


def test_identificador_de_outra_pessoa_e_recusado(
    app: FastAPI, users: Users, ana_device: SoftAuthenticator
) -> None:
    ch = _login_options(Api(app))
    r = _login(Api(app), ch, ana_device.get(ch["opcoes"], user_handle=users.bruno.bytes))
    assert r.status_code == 401


def test_credencial_malformada_nao_quebra(app: FastAPI) -> None:
    ch = _login_options(Api(app))
    for bad in [{}, {"id": "x", "rawId": "x", "type": "public-key", "response": {}}]:
        r = _login(Api(app), ch, bad)
        assert r.status_code == 401, r.text


def test_aparelho_removido_nao_entra_mais(
    app: FastAPI, admin_engine: Engine, users: Users, ana_device: SoftAuthenticator
) -> None:
    api = logged_in(app, admin_engine, users.ana, "ana")
    pid = api.get("/api/auth/digital").json()[0]["id"]
    assert api.delete(f"/api/auth/digital/{pid}").status_code == 204
    ch = _login_options(Api(app))
    r = _login(Api(app), ch, ana_device.get(ch["opcoes"]))
    assert r.status_code == 401
    assert "não está ativado" in r.json()["detail"]


def test_usuario_desativado_nao_entra(
    app: FastAPI, admin_engine: Engine, users: Users, ana_device: SoftAuthenticator
) -> None:
    with admin_engine.begin() as conn:
        conn.execute(text("UPDATE users SET is_active = false WHERE id = :u"), {"u": users.ana})
    ch = _login_options(Api(app))
    assert _login(Api(app), ch, ana_device.get(ch["opcoes"])).status_code == 401


def test_cada_pessoa_so_ve_e_remove_os_proprios_aparelhos(
    app: FastAPI, admin_engine: Engine, users: Users, ana_device: SoftAuthenticator
) -> None:
    ana = logged_in(app, admin_engine, users.ana, "ana")
    bruno = logged_in(app, admin_engine, users.bruno, "bruno")
    ana_pid = ana.get("/api/auth/digital").json()[0]["id"]
    assert bruno.get("/api/auth/digital").json() == []
    r = bruno.delete(f"/api/auth/digital/{ana_pid}")
    assert r.status_code == 404
    assert r.json()["detail"] == "Aparelho não encontrado."
    assert len(ana.get("/api/auth/digital").json()) == 1

    # Bruno não consegue prender uma credencial na conta da Ana usando o desafio dela.
    ana_ch = ana.post("/api/auth/digital/cadastro/opcoes", key=None).json()
    cred = SoftAuthenticator(ORIGIN).create(ana_ch["opcoes"])
    r = bruno.post(
        "/api/auth/digital/cadastro",
        {"desafio_id": ana_ch["desafio_id"], "credencial": cred, "nome_aparelho": "Intruso"},
        key=None,
    )
    assert r.status_code == 400
    assert bruno.get("/api/auth/digital").json() == []
    assert len(ana.get("/api/auth/digital").json()) == 1


def test_cadastro_nao_repete_aparelho_ja_ativado(
    app: FastAPI, admin_engine: Engine, users: Users, ana_device: SoftAuthenticator
) -> None:
    ana = logged_in(app, admin_engine, users.ana, "ana")
    opts = ana.post("/api/auth/digital/cadastro/opcoes", key=None).json()["opcoes"]
    excluded = [unb64u(c["id"]) for c in opts["excludeCredentials"]]
    assert excluded == [ana_device.credentials[0].id]


def test_cadastro_exige_estar_conectado(app: FastAPI) -> None:
    r = Api(app).post("/api/auth/digital/cadastro/opcoes", key=None)
    assert r.status_code == 401


def test_tentativas_erradas_bloqueiam_por_ip(
    app_engine: Engine, admin_engine: Engine, ana_device: SoftAuthenticator
) -> None:
    with admin_engine.begin() as conn:
        conn.execute(text("DELETE FROM login_attempts"))
    strict = build_app(app_engine, login_max_failures_per_ip=2)
    for _ in range(2):
        ch = _login_options(Api(strict))
        assert _login(Api(strict), ch, ana_device.get(ch["opcoes"], user_verified=False)).status_code == 401
    r = Api(strict).post("/api/auth/digital/entrar/opcoes", key=None)
    assert r.status_code == 429


def test_aplicacao_nao_le_desafios_nem_digitais_sem_identidade(
    app_engine: Engine, ana_device: SoftAuthenticator
) -> None:
    with app_engine.connect() as conn:
        # Sem identidade na transação, a RLS esconde as digitais de todo mundo.
        assert conn.execute(text("SELECT count(*) FROM passkeys")).scalar() == 0
    # Desafios: nem permissão de leitura; só pelas funções de login.
    with app_engine.connect() as conn, pytest.raises(ProgrammingError, match="permission denied"):
        conn.execute(text("SELECT count(*) FROM webauthn_challenges"))


def test_entrar_exige_protecao_csrf(app: FastAPI) -> None:
    r = Api(app).client.post("/api/auth/digital/entrar/opcoes", headers={"Origin": "https://golpe.exemplo"})
    assert r.status_code == 403
    assert SAFE_HEADERS["Origin"] == ORIGIN
