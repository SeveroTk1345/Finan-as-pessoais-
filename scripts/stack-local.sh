#!/bin/sh
# Sobe a aplicação completa para testes ponta a ponta, com dados SINTÉTICOS:
# PostgreSQL descartável no Docker, migrações, três usuários de teste e a API
# servindo o site estático na mesma origem.
#
# Uso: scripts/stack-local.sh COMANDO...   (o comando roda com FIN_E2E_URL definido)
# Requer: Docker, uv, frontend já compilado (make build).
set -eu

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PORT="${FIN_E2E_PORT:-8765}"
DBPORT="${FIN_E2E_DB_PORT:-55433}"
NAME="fin-e2e-db-$$"
ADMIN_PW="$(head -c 18 /dev/urandom | od -An -tx1 | tr -d ' \n')"
APP_PW="$(head -c 18 /dev/urandom | od -An -tx1 | tr -d ' \n')"

[ -d "$ROOT/frontend/out" ] || { echo "rode make build antes" >&2; exit 1; }

docker run -d --rm --name "$NAME" -e POSTGRES_USER=fin_admin -e POSTGRES_PASSWORD="$ADMIN_PW" \
  -e POSTGRES_DB=financas -e FIN_DB_APP_PASSWORD="$APP_PW" \
  -v "$ROOT/deploy/initdb:/docker-entrypoint-initdb.d:ro" \
  -p "127.0.0.1:${DBPORT}:5432" postgres:16.10-alpine > /dev/null
API_PID=""
cleanup() {
  [ -n "$API_PID" ] && kill "$API_PID" 2> /dev/null || true
  docker rm -f "$NAME" > /dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

i=0
until docker exec "$NAME" pg_isready -U fin_admin -d financas -h 127.0.0.1 > /dev/null 2>&1; do
  i=$((i + 1)); [ "$i" -lt 60 ] || { echo "banco não respondeu" >&2; exit 1; }; sleep 1
done

export FIN_DATABASE_ADMIN_URL="postgresql+psycopg://fin_admin:${ADMIN_PW}@127.0.0.1:${DBPORT}/financas"
cd "$ROOT/backend"
uv run alembic upgrade head > /dev/null
# Senhas sintéticas, só para testes (as mesmas de frontend/e2e/helpers.ts).
for pair in "ana:Ana:abacate-verde-2026" "bruno:Bruno:bicicleta-azul-2026" "carla:Carla:castelo-rosa-2026"; do
  u="${pair%%:*}"; rest="${pair#*:}"; nome="${rest%%:*}"; pw="${rest#*:}"
  echo "$pw" | uv run python -m app.cli criar-usuario --usuario "$u" --nome "$nome" --senha-stdin > /dev/null
done

FIN_ENVIRONMENT=test \
FIN_DATABASE_URL="postgresql+psycopg://fin_app:${APP_PW}@127.0.0.1:${DBPORT}/financas" \
FIN_ALLOWED_ORIGINS="http://127.0.0.1:${PORT},http://localhost:${PORT}" \
FIN_STATIC_DIR="$ROOT/frontend/out" \
  uv run uvicorn app.main:app --host 127.0.0.1 --port "$PORT" --log-level warning &
API_PID=$!

i=0
until curl -fs "http://127.0.0.1:${PORT}/api/health" > /dev/null 2>&1; do
  i=$((i + 1)); [ "$i" -lt 60 ] || { echo "API não respondeu" >&2; exit 1; }; sleep 1
done

cd "$ROOT"
FIN_E2E_URL="http://127.0.0.1:${PORT}" FIN_E2E_DB_CONTAINER="$NAME" "$@"
