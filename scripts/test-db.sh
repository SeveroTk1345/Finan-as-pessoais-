#!/bin/sh
# Sobe um PostgreSQL descartável no Docker, roda o comando informado com
# FIN_TEST_ADMIN_URL definido e remove o container no fim.
# Uso: scripts/test-db.sh uv run pytest
set -eu

image="postgres:16.10-alpine"
name="fin-test-db-$$"
port="${FIN_TEST_DB_PORT:-55432}"
pw="$(head -c 18 /dev/urandom | od -An -tx1 | tr -d ' \n')"

docker run -d --rm --name "$name" -e POSTGRES_USER=fin_admin -e POSTGRES_PASSWORD="$pw" \
  -e POSTGRES_DB=postgres -p "127.0.0.1:${port}:5432" "$image" > /dev/null
trap 'docker rm -f "$name" > /dev/null 2>&1 || true' EXIT INT TERM

i=0
until docker exec "$name" pg_isready -U fin_admin -h 127.0.0.1 > /dev/null 2>&1; do
  i=$((i + 1))
  [ "$i" -lt 60 ] || { echo "PostgreSQL não respondeu" >&2; exit 1; }
  sleep 1
done

FIN_TEST_ADMIN_URL="postgresql+psycopg://fin_admin:${pw}@127.0.0.1:${port}/postgres" "$@"
