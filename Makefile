# Comandos do projeto. Requer: uv (Python) e Node.js 22+.
.PHONY: install test test-backend test-frontend lint lint-backend lint-frontend build dev-backend dev-frontend

install:
	cd backend && uv sync
	cd frontend && npm ci

test: test-backend test-frontend

test-backend:
	cd backend && uv run pytest

test-frontend:
	cd frontend && npm test

lint: lint-backend lint-frontend

lint-backend:
	cd backend && uv run ruff check . && uv run ruff format --check . && uv run mypy

lint-frontend:
	cd frontend && npm run lint && npm run typecheck

build:
	cd frontend && npm run build

# Rode cada um em um terminal; acesse http://localhost:3000 (o /api é encaminhado ao FastAPI).
dev-backend:
	cd backend && uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

dev-frontend:
	cd frontend && npm run dev
