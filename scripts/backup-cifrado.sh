#!/usr/bin/env bash
# Cópia de segurança CIFRADA do banco gerenciado (ex.: Neon), feita pelo GitHub Actions.
#
# Como o repositório pode ser público, a cópia só sai daqui cifrada (AES-256, gpg
# simétrico). Sem a frase-senha, o arquivo não serve para nada.
#
# Uso: scripts/backup-cifrado.sh ARQUIVO_DE_SAIDA.dump.gpg
#
# FIN_DATABASE_ADMIN_URL  endereço do dono do banco (precisa ignorar a RLS, como o do Neon)
# FIN_BACKUP_PASSPHRASE   frase-senha da cifra, pelo menos 24 caracteres
#
# Gera ARQUIVO e ARQUIVO.sha256. A cópia só é cifrada depois de o pg_restore conseguir
# ler o índice completo dela; a versão aberta nunca sai da pasta temporária.
set -euo pipefail

out="${1:?informe o arquivo de saída (.dump.gpg)}"
url="${FIN_DATABASE_ADMIN_URL:?defina FIN_DATABASE_ADMIN_URL}"
pass="${FIN_BACKUP_PASSPHRASE:?defina FIN_BACKUP_PASSPHRASE}"
[ "${#pass}" -ge 24 ] || { echo "FIN_BACKUP_PASSPHRASE precisa ter pelo menos 24 caracteres" >&2; exit 1; }

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
{ read -r url; IFS= read -r PGPASSWORD; } < <(split_url "$url")
export PGPASSWORD

umask 077
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT INT TERM

pg_dump --dbname="$url" --format=custom --no-password --file="$work/fin.dump"
pg_restore --list "$work/fin.dump" > "$work/indice"
tables="$(grep -c ' TABLE DATA ' "$work/indice" || true)"
[ "$tables" -gt 0 ] || { echo "a cópia não tem dados de tabela; algo está errado" >&2; exit 1; }

# Frase-senha por descritor de arquivo: não aparece em ps nem no log.
gpg --batch --yes --quiet --pinentry-mode loopback --passphrase-fd 3 \
    --symmetric --cipher-algo AES256 --compress-algo none \
    --output "$work/fin.dump.gpg" "$work/fin.dump" 3<<<"$pass"

mv "$work/fin.dump.gpg" "$out"
( cd "$(dirname "$out")" && sha256sum "$(basename "$out")" > "$(basename "$out").sha256" )
echo "backup cifrado: $out ($tables tabelas com dados, $(stat -c %s "$out") bytes)"
