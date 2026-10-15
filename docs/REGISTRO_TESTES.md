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

## T1.2 · Banco, isolamento e backup · 15/10/2026

Ambiente: PostgreSQL 16.10 (imagem `postgres:16.10-alpine`) em container descartável via `scripts/test-db.sh`; cliente `pg_dump` 16.15; SQLAlchemy 2.1.4, psycopg 3.3.6, Alembic 1.20.0.

| Comando | Resultado |
|---|---|
| `make test-backend` | **193 aprovados**, 0 falhas (121 da T1.1 + 72 novos de banco) |
| `ruff check .`, `ruff format --check .`, `mypy` estrito | Sem problemas (34 arquivos) |
| `docker compose config` sem senhas no ambiente | Recusado com "defina FIN_DB_ADMIN_PASSWORD no .env" (esperado) |

Testes novos (todos contra PostgreSQL real):
* `test_isolation.py`: três usuários; leitura, alteração e exclusão cruzadas por ID nas 6 combinações (A→B, A→C, B→A, B→C, C→A, C→B); RLS sozinha (SQL sem `WHERE`, agregações, UPDATE/DELETE, INSERT e mudança de dono); filtro da aplicação sozinho (superusuário); relação pai/filho entre usuários recusada pela chave composta, inclusive para o superusuário; papel `fin_app` sem poder alterar esquema, desligar RLS, criar usuários ou truncar tabelas; `row_security = off` não contorna a política.
* `test_identity_pool.py`: pool de **uma** conexão (mesmo `pg_backend_pid` comprovado) alternando A, B, C; conexão sem identidade após COMMIT e após ROLLBACK por erro; `SET` de sessão feito por engano limpo na próxima retirada do pool; identidade só aceita `UUID`; 4 threads × 75 transações sobre 2 conexões sem nenhuma leitura cruzada.
* `test_schema_conventions.py`: RLS ativa e forçada, política padrão, `UNIQUE (owner_id, id)` e chaves compostas verificadas no catálogo para todas as tabelas.
* `test_migrations.py`: upgrade → downgrade → upgrade em banco vazio; restrições de nome, tipo, limite de valor e usuário.
* `test_backup_restore.py`: 12 testes descritos em `docs/BACKUP.md`.

### Testes de mutação (proteção desligada de propósito)
| Mutação | Resultado da suíte de banco |
|---|---|
| Sem filtro `owner_id` no repositório | 6 falhas |
| Sem `FORCE ROW LEVEL SECURITY` | 1 falha |
| Sem `ENABLE ROW LEVEL SECURITY` | 23 falhas |
| Sem limpeza de identidade no pool | 1 falha |
| Identidade com escopo de sessão e sem limpeza | 4 falhas |
| Código original | 53 aprovados |

### Docker Compose real
1. `docker compose up -d` com senhas aleatórias em `deploy/.env` (temporário, apagado depois): banco `healthy`.
2. `alembic upgrade head` como `fin_admin`: aplicado.
3. Papéis: `fin_admin` superusuário; `fin_app` sem superusuário e sem BYPASSRLS; `PUBLIC` sem CONNECT.
4. Serviço `backup` criou uma cópia ao subir e outra com `docker compose exec backup /scripts/backup.sh`; arquivos com permissão 600 e `.sha256`.
5. `restore.sh` restaurou em `fin_restaurado`, com RLS ativa em `users` e `accounts`.
6. `docker compose down -v`: ambiente removido.
