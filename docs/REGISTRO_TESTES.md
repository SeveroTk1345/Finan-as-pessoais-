# Registro de testes

Cada entrada registra comandos realmente executados e o resultado obtido. Nada aqui é estimado.

## T1.1 · Base técnica · 15/10/2026

Ambiente: container Linux da sessão do Claude Code, Python 3.13.16, Node.js 22.22.0, FastAPI 0.143.1, Pydantic 2.14.1, Next.js 16.4.1, React 19.3.1, TypeScript 6.0.3, Vitest 5.0.4.

| Comando | Resultado |
|---|---|
| `make test-backend` (pytest) | 121 testes coletados, **121 aprovados**, 0 falhas, 0 avisos |
| `make test-frontend` (vitest, 3 execuções com `TZ=America/Sao_Paulo`, `TZ=UTC` e `TZ=Asia/Tokyo`) | **36 aprovados** em cada fuso (108 execuções) |
| `ruff check .` | Sem problemas |
| `ruff format --check .` | 21 arquivos já formatados |
| `mypy` (modo estrito, `app` e `tests`) | Sem problemas em 21 arquivos |
| `npm run lint` (ESLint, `--max-warnings=0`) | Sem problemas |
| `npm run typecheck` (`tsc --noEmit`) | Sem problemas |
| `npm run build` (`output: export`) | Compilado; páginas `/` e `/_not-found` geradas como estáticas em `frontend/out` |
| `uvicorn app.main:app` + `curl /api/health` | `HTTP/1.1 200 OK` e corpo `{"status":"ok"}` |
| ESLint sobre arquivo de prova com `new Date("2026-10-15")`, `parseFloat("1,5")` e `new Date()` | 2 erros esperados (os dois primeiros); `new Date()` permitido. Arquivo removido em seguida |

### Falhas encontradas e corrigidas durante a tarefa
1. `test_parcelas_casos[99999-12]`: o **valor esperado no teste** estava errado (8341). O correto é 99999 = 12 × 8333 + 3, ou seja, primeira parcela 8336. O código estava certo; o teste foi corrigido.
2. Ruff `RUF001`: espaço não separável literal no código. Trocado pelo escape ` `, comportamento idêntico.
3. Aviso de depreciação do cliente de testes do Starlette com `httpx`. Dependência de desenvolvimento trocada para `httpx2`; aviso eliminado.

### Não testado nesta tarefa
* Banco de dados, autenticação, isolamento entre usuários (não existem ainda: T1.2 e T1.3).
* PWA, service worker e instalação no iPhone (T1.5 e T6.1).
* Publicação na internet (T1.6). O app **não está publicado**.
