# Comandos do projeto. Requer: uv (Python) e Node.js 22+.
.PHONY: install test test-backend test-backend-sem-banco test-frontend lint lint-backend lint-frontend build dev-backend dev-frontend db-up db-down migrate backup-agora

install:
	cd backend && uv sync
	cd frontend && npm ci

test: test-backend test-frontend

# Sobe um PostgreSQL descartável no Docker para os testes de banco (requer Docker).
test-backend:
	cd backend && ../scripts/test-db.sh uv run pytest

# Só testes que não precisam de banco (os de banco aparecem como "skipped").
test-backend-sem-banco:
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

# --- Banco local (deploy/.env com as senhas) ---
db-up:
	cd deploy && docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d

db-down:
	cd deploy && docker compose down

migrate:
	cd backend && uv run alembic upgrade head

backup-agora:
	cd deploy && docker compose exec backup /scripts/backup.sh
