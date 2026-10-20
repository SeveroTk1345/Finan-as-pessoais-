#!/usr/bin/env bash
# Restaura uma cópia cifrada (de backup-cifrado.sh) em um banco VAZIO.
# Nunca grava no banco em uso: recusa se o destino for o mesmo endereço de produção
# ou se já tiver tabelas.
#
# Uso: scripts/restaurar-cifrado.sh ARQUIVO.dump.gpg
#
# FIN_RESTORE_DATABASE_URL  banco de destino, vazio (ex.: um banco "restaurado" criado
#                           no painel do Neon). O papel fin_app precisa existir no servidor.
# FIN_BACKUP_PASSPHRASE     a mesma frase-senha usada no backup
# FIN_DATABASE_ADMIN_URL    opcional: se definido, o destino não pode ser igual a ele
#
# Mostra só a contagem de linhas por tabela, nunca o conteúdo.
set -euo pipefail

file="${1:?informe o arquivo .dump.gpg}"
target="${FIN_RESTORE_DATABASE_URL:?defina FIN_RESTORE_DATABASE_URL}"
pass="${FIN_BACKUP_PASSPHRASE:?defina FIN_BACKUP_PASSPHRASE}"

# Separa a senha do endereço: o endereço sem senha vai como argumento e a senha só
# pela variável PGPASSWORD (argumentos aparecem para outros processos; o ambiente não).
split_url() {
  U="$1" python3 -c '
import os, urllib.parse as p
u = p.urlsplit(os.environ["U"].replace("postgresql+psycopg:", "postgresql:", 1).replace("postgres:", "postgresql:", 1))
host = u.hostname or ""
host = "[" + host + "]" if ":" in host else host
netloc = (p.quote(p.unquote(u.username or ""), safe="") + "@" if u.username else "") + host + (f":{u.port}" if u.port else "")
print(p.urlunsplit((u.scheme, netloc, u.path, u.query, "")))
print(p.unquote(u.password or ""))'
}
{ read -r target; IFS= read -r PGPASSWORD; } < <(split_url "$target")
export PGPASSWORD
if [ -n "${FIN_DATABASE_ADMIN_URL:-}" ] && [ "$target" = "$(split_url "$FIN_DATABASE_ADMIN_URL" | head -n 1)" ]; then
  echo "o destino é o banco de produção; crie um banco vazio para restaurar" >&2
  exit 1
fi

[ -f "$file" ] || { echo "arquivo não encontrado: $file" >&2; exit 1; }
if [ -f "$file.sha256" ]; then
  ( cd "$(dirname "$file")" && sha256sum -c "$(basename "$file").sha256" > /dev/null ) || {
    echo "SHA-256 não confere: arquivo corrompido ou alterado" >&2
    exit 1
  }
fi

q() { psql -X -tA -v ON_ERROR_STOP=1 --dbname="$target" -c "$1"; }

used="$(q "SELECT count(*) FROM pg_tables WHERE schemaname = 'public'")"
[ "$used" = "0" ] || { echo "o banco de destino já tem tabelas; use um banco vazio" >&2; exit 1; }
[ -n "$(q "SELECT 1 FROM pg_roles WHERE rolname = 'fin_app'")" ] || {
  echo "papel fin_app não existe no servidor de destino" >&2
  exit 1
}

umask 077
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT INT TERM

gpg --batch --quiet --pinentry-mode loopback --passphrase-fd 3 \
    --output "$work/fin.dump" --decrypt "$file" 3<<<"$pass" || {
  echo "não foi possível abrir a cópia: frase-senha errada ou arquivo danificado" >&2
  exit 1
}

pg_restore --no-password --exit-on-error --single-transaction --no-owner \
  --dbname="$target" "$work/fin.dump"

db="$(q "SELECT current_database()")"
psql -X -v ON_ERROR_STOP=1 -q --dbname="$target" -c "REVOKE ALL ON DATABASE \"$db\" FROM PUBLIC" \
  -c "GRANT CONNECT ON DATABASE \"$db\" TO fin_app"

echo "restaurado em $db. Linhas por tabela:"
psql -X -v ON_ERROR_STOP=1 -q --dbname="$target" -c "
  SELECT relname AS tabela,
         (xpath('/row/n/text()', query_to_xml(format('SELECT count(*) AS n FROM public.%I', relname), false, true, '')))[1]::text::bigint AS linhas
    FROM pg_class WHERE relkind IN ('r', 'p') AND relnamespace = 'public'::regnamespace
   ORDER BY relname"
