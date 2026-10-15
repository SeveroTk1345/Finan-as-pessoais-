#!/bin/sh
# Cenário 14: faz backup do banco usado nos testes ponta a ponta, restaura em um
# banco separado e compara o conteúdo tabela por tabela. Chamado por scripts/e2e.sh.
set -eu
C="${FIN_E2E_DB_CONTAINER:?}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
docker cp "$ROOT/scripts/backup.sh" "$C:/tmp/backup.sh"
docker cp "$ROOT/scripts/restore.sh" "$C:/tmp/restore.sh"
docker exec -e PGUSER=fin_admin -e PGDATABASE=financas -e FIN_BACKUP_DIR=/tmp/backups "$C" sh /tmp/backup.sh
DUMP="$(docker exec "$C" sh -c 'ls /tmp/backups/fin_*.dump | head -1')"
docker exec -e PGUSER=fin_admin -e PGDATABASE=postgres "$C" sh /tmp/restore.sh "$DUMP" financas_restaurado
Q="SELECT string_agg(t || '=' || n, ' ' ORDER BY t) FROM (
  SELECT 'transactions' t, count(*) || ':' || coalesce(sum(amount_cents),0) n FROM transactions
  UNION ALL SELECT 'accounts', count(*)::text FROM accounts
  UNION ALL SELECT 'card_installments', count(*) || ':' || coalesce(sum(amount_cents),0) FROM card_installments
  UNION ALL SELECT 'debts', count(*)::text FROM debts
  UNION ALL SELECT 'investment_movements', count(*)::text FROM investment_movements
  UNION ALL SELECT 'goals', count(*)::text FROM goals
  UNION ALL SELECT 'users', count(*)::text FROM users) x"
A="$(docker exec "$C" psql -U fin_admin -d financas -tAc "$Q")"
B="$(docker exec "$C" psql -U fin_admin -d financas_restaurado -tAc "$Q")"
echo "original:   $A"
echo "restaurado: $B"
[ "$A" = "$B" ] || { echo "FALHOU: conteúdo diferente" >&2; exit 1; }
case "$A" in *"transactions=0:"*) echo "FALHOU: banco sem lançamentos" >&2; exit 1 ;; esac
echo "OK: backup restaurado em banco separado com conteúdo idêntico"
