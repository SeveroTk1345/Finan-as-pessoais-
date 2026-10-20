#!/bin/sh
# Executado pelo container do PostgreSQL só na primeira inicialização (volume vazio).
# Cria o papel usado pela API: sem superusuário, sem BYPASSRLS, sem criar bancos ou papéis.
set -eu

if [ -z "${FIN_DB_APP_PASSWORD:-}" ]; then
  echo "FIN_DB_APP_PASSWORD não definida" >&2
  exit 1
fi

# A senha entra como variável do psql (:'pw'), que faz o escape; nunca por concatenação.
psql -v ON_ERROR_STOP=1 -v pw="$FIN_DB_APP_PASSWORD" \
  --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<'SQL'
CREATE ROLE fin_app LOGIN PASSWORD :'pw'
  NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOINHERIT;
REVOKE ALL ON DATABASE :"DBNAME" FROM PUBLIC;
GRANT CONNECT ON DATABASE :"DBNAME" TO fin_app;
SQL
