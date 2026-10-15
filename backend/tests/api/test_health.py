from __future__ import annotations

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


def test_health_ok() -> None:
    client = TestClient(create_app(Settings(environment="test")))
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_so_aceita_get() -> None:
    client = TestClient(create_app(Settings(environment="test")))
    # Sem Origin, a proteção CSRF recusa antes (403); com Origin válido, 405.
    assert client.post("/api/health").status_code == 403
    headers = {"Origin": "http://localhost:3000", "X-Requested-With": "fetch"}
    assert client.post("/api/health", headers=headers).status_code == 405


def test_rota_inexistente_404() -> None:
    client = TestClient(create_app(Settings(environment="test")))
    assert client.get("/api/nao-existe").status_code == 404


def test_docs_desligada_em_producao() -> None:
    prod = TestClient(create_app(Settings(environment="production")))
    assert prod.get("/api/docs").status_code == 404
    assert prod.get("/api/openapi.json").status_code == 404
    dev = TestClient(create_app(Settings(environment="development")))
    assert dev.get("/api/openapi.json").status_code == 200
