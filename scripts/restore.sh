#!/bin/sh
# Restaura uma cópia em um banco NOVO. Nunca sobrescreve o banco em uso.
#
# Uso: scripts/restore.sh ARQUIVO.dump NOME_DO_BANCO_NOVO
#
# Conexão pelas variáveis padrão (PGHOST, PGPORT, PGUSER, PGPASSWORD); PGDATABASE
# deve apontar para um banco existente de manutenção (ex.: postgres).
# O papel fin_app precisa existir no servidor de destino.
#
# Etapas: confere o SHA-256, confere que o banco novo não existe, cria o banco,
# restaura em transação única e apaga o banco novo se algo falhar.
set -eu

dump="${1:?informe o arquivo .dump}"
target="${2:?informe o nome do banco novo}"

case "$target" in
  *[!a-z0-9_]*|'') echo "nome de banco inválido: use a-z, 0-9 e _" >&2; exit 1 ;;
esac

[ -f "$dump" ] || { echo "arquivo não encontrado: $dump" >&2; exit 1; }
[ -f "$dump.sha256" ] || { echo "falta $dump.sha256" >&2; exit 1; }

dumpdir="$(dirname "$dump")"
( cd "$dumpdir" && sha256sum -c "$(basename "$dump").sha256" > /dev/null ) || {
  echo "SHA-256 não confere: arquivo corrompido ou alterado" >&2
  exit 1
}

exists="$(psql -X -tA -v ON_ERROR_STOP=1 -c "SELECT 1 FROM pg_database WHERE datname = '$target'")"
[ -z "$exists" ] || { echo "o banco $target já existe; escolha outro nome" >&2; exit 1; }

has_role="$(psql -X -tA -v ON_ERROR_STOP=1 -c "SELECT 1 FROM pg_roles WHERE rolname = 'fin_app'")"
[ -n "$has_role" ] || { echo "papel fin_app não existe no servidor de destino" >&2; exit 1; }

createdb "$target"
if ! pg_restore --no-password --exit-on-error --single-transaction --no-owner \
     --dbname="$target" "$dump"; then
  echo "restauração falhou; removendo o banco $target" >&2
  dropdb "$target" || true
  exit 1
fi

# Mesmo controle de acesso do banco original: só fin_app conecta (além do admin).
psql -X -v ON_ERROR_STOP=1 -q -c "REVOKE ALL ON DATABASE $target FROM PUBLIC" \
  -c "GRANT CONNECT ON DATABASE $target TO fin_app"

echo "restaurado em $target. Confira os dados antes de apontar a aplicação para ele."
