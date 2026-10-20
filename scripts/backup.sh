#!/bin/sh
# Cópia de segurança do banco inteiro em formato custom do pg_dump.
#
# Conexão pelas variáveis padrão do PostgreSQL: PGHOST, PGPORT, PGUSER, PGPASSWORD,
# PGDATABASE. O usuário precisa ignorar RLS (superusuário do container), senão o
# pg_dump recusa tabelas com política ativa.
#
# FIN_BACKUP_DIR   pasta de destino (obrigatória)
# FIN_BACKUP_KEEP  quantas cópias manter (padrão 14)
#
# Cada cópia gera NOME.dump e NOME.dump.sha256. Só é considerada válida depois de
# o pg_restore conseguir ler o índice completo do arquivo.
set -eu

dir="${FIN_BACKUP_DIR:?defina FIN_BACKUP_DIR}"
keep="${FIN_BACKUP_KEEP:-14}"
case "$keep" in ''|*[!0-9]*) echo "FIN_BACKUP_KEEP inválido" >&2; exit 1 ;; esac
[ "$keep" -ge 1 ] || { echo "FIN_BACKUP_KEEP deve ser >= 1" >&2; exit 1; }

umask 077
mkdir -p "$dir"

stamp="$(date -u +%Y%m%dT%H%M%SZ)"
# O PID evita colisão se duas cópias forem feitas no mesmo segundo.
name="fin_${stamp}_$$.dump"
tmp="$dir/.${name}.parcial"

cleanup() { rm -f "$tmp"; }
trap cleanup EXIT INT TERM

pg_dump --format=custom --no-password --file="$tmp"
pg_restore --list "$tmp" > /dev/null

mv "$tmp" "$dir/$name"
( cd "$dir" && sha256sum "$name" > "$name.sha256" )

# Rotação: mantém as $keep cópias mais recentes (o nome ordena por data).
count=0
for f in $(ls -1 "$dir" | grep -E '^fin_[0-9]{8}T[0-9]{6}Z_[0-9]+\.dump$' | sort -r); do
  count=$((count + 1))
  if [ "$count" -gt "$keep" ]; then
    rm -f "$dir/$f" "$dir/$f.sha256"
  fi
done

echo "backup criado: $dir/$name"
