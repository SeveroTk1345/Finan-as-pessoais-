"""Configuração pelo navegador (/configurar): criar contas e redefinir senha com código."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI
from sqlalchemy import Engine, text
from sqlalchemy.exc import ProgrammingError

from tests.db.api_helpers import SAFE_HEADERS, Api, build_app

CODE = "codigo-de-configuracao-de-teste-1234567890"


@pytest.fixture
def clean(admin_engine: Engine) -> None:
    with admin_engine.begin() as conn:
        conn.execute(text("TRUNCATE users, login_attempts CASCADE"))


@pytest.fixture
def app(app_engine: Engine, clean: None) -> FastAPI:
    return build_app(app_engine, setup_token=CODE)


def _create(
    api: Api, usuario: str, senha: str = "uma-senha-forte-123", code: str = CODE, nome: str = "Pessoa"
) -> Any:
    return api.client.post(
        "/api/configuracao/contas",
        json={"codigo": code, "usuario": usuario, "nome": nome, "senha": senha},
        headers=SAFE_HEADERS,
    )


def test_sem_codigo_configurado_fica_desligada(app_engine: Engine, clean: None) -> None:
    api = Api(build_app(app_engine))
    assert api.get("/api/configuracao").json() == {"habilitada": False, "contas": None, "maximo": 3}
    assert _create(api, "ana").status_code == 404


def test_cria_conta_que_entra_e_ja_tem_categorias(app: FastAPI) -> None:
    api = Api(app)
    assert api.get("/api/configuracao").json() == {"habilitada": True, "contas": 0, "maximo": 3}
    r = _create(api, " Ana ", nome="Ana")
    assert r.status_code == 201, r.text
    assert r.json() == {"usuario": "ana", "nome": "Ana"}
    assert api.login("ana", "uma-senha-forte-123").status_code == 200
    names = [c["name"] for c in api.get("/api/categorias").json()]
    assert "Mercado" in names and "Salário" in names
    assert api.get("/api/configuracao").json()["contas"] == 1


def test_codigo_errado_nao_cria_e_conta_tentativas(app: FastAPI, admin_engine: Engine) -> None:
    api = Api(app)
    r = _create(api, "ana", code="chute")
    assert r.status_code == 403
    assert api.get("/api/configuracao").json()["contas"] == 0
    with admin_engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM login_attempts WHERE NOT success")).scalar() == 1


def test_bloqueia_depois_de_muitos_codigos_errados(app_engine: Engine, clean: None) -> None:
    api = Api(build_app(app_engine, setup_token=CODE, login_max_failures_per_ip=3))
    for _ in range(3):
        assert _create(api, "ana", code="chute").status_code == 403
    assert _create(api, "ana").status_code == 429  # nem o código certo passa durante o bloqueio


def test_no_maximo_tres_contas_e_sem_repetir(app: FastAPI) -> None:
    api = Api(app)
    assert _create(api, "ana").status_code == 201
    r = _create(api, "ana")
    assert r.status_code == 409 and "já existe" in r.json()["detail"]
    assert _create(api, "bruno").status_code == 201
    assert _create(api, "carla").status_code == 201
    r = _create(api, "diogo")
    assert r.status_code == 409 and "3 contas" in r.json()["detail"]


def test_validacoes(app: FastAPI) -> None:
    api = Api(app)
    assert _create(api, "ana maria").status_code == 422
    assert _create(api, "ana", senha="curta").status_code == 422
    assert _create(api, "ana", senha="ana-ana-ana-ana").status_code == 422  # contém o usuário


def test_redefinir_senha_troca_e_derruba_sessoes(app: FastAPI) -> None:
    api = Api(app)
    _create(api, "ana")
    assert api.login("ana", "uma-senha-forte-123").status_code == 200
    assert api.get("/api/auth/eu").status_code == 200
    other = Api(app)
    r = other.client.post(
        "/api/configuracao/redefinir-senha",
        json={"codigo": CODE, "usuario": "ana", "nova_senha": "outra-senha-forte-456"},
        headers=SAFE_HEADERS,
    )
    assert r.status_code == 204, r.text
    assert api.get("/api/auth/eu").status_code == 401  # sessão antiga encerrada
    assert other.login("ana", "uma-senha-forte-123").status_code == 401
    assert other.login("ana", "outra-senha-forte-456").status_code == 200
    r = other.client.post(
        "/api/configuracao/redefinir-senha",
        json={"codigo": CODE, "usuario": "ninguem", "nova_senha": "outra-senha-forte-456"},
        headers=SAFE_HEADERS,
    )
    assert r.status_code == 404
    r = other.client.post(
        "/api/configuracao/redefinir-senha",
        json={"codigo": "chute", "usuario": "ana", "nova_senha": "terceira-senha-789"},
        headers=SAFE_HEADERS,
    )
    assert r.status_code == 403


def test_exige_protecao_csrf(app: FastAPI) -> None:
    r = Api(app).client.post(
        "/api/configuracao/contas",
        json={"codigo": CODE, "usuario": "ana", "nome": "Ana", "senha": "uma-senha-forte-123"},
        headers={"Origin": "https://golpe.exemplo", "X-Requested-With": "fetch"},
    )
    assert r.status_code == 403


def test_api_continua_sem_inserir_contas_diretamente(app_engine: Engine, clean: None) -> None:
    with app_engine.connect() as conn, pytest.raises(ProgrammingError, match="permission denied"):
        conn.execute(text("INSERT INTO users (username, display_name, password_hash) VALUES ('x', 'X', 'h')"))
