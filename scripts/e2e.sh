#!/bin/sh
# Testes ponta a ponta completos: build do site, pilha local com dados sintéticos,
# Playwright (perfil iPhone) e verificação de backup/restauração.
set -eu
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
(cd "$ROOT/frontend" && npm run build > /dev/null)
"$ROOT/scripts/stack-local.sh" sh -c 'cd frontend && npx playwright test "$@" && cd .. && scripts/e2e-backup-check.sh' sh "$@"
