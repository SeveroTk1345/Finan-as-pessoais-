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

## T1.3 a T6 · Aplicação completa · 15/10/2026

Ambiente: container Linux desta sessão; PostgreSQL 16.10 em Docker; Python 3.13; Node.js 22.22; Chromium 1194 com perfil de iPhone (Playwright 1.56.1). **Não é o Safari real.**

| Verificação | Resultado |
|---|---|
| `pytest` (backend, banco real) | **351 aprovados**, 0 falhas |
| `ruff check`, `ruff format --check`, `mypy --strict` | Sem problemas (72 arquivos) |
| `vitest` (frontend) em 3 fusos | **41 aprovados** em cada fuso |
| `eslint --max-warnings=0`, `tsc --noEmit` | Sem problemas |
| `next build` (export estático) | 33 telas geradas |
| Playwright (`scripts/e2e.sh`) | **16 aprovados**, 0 falhas |
| Backup + restauração dos dados criados pela interface (cenário 14) | Conteúdo idêntico (contas, lançamentos com soma, parcelas, dívidas, investimentos, metas, usuários) |
| `pip-audit` | Nenhuma vulnerabilidade conhecida |
| `npm audit --omit=dev` | 0 vulnerabilidades |
| `docker build` da imagem de produção | Construída |
| `docker compose up` de produção com `FIN_DOMAIN=localhost` | HTTPS/HTTP2, HSTS, CSP, cookie Secure/HttpOnly/SameSite=Strict, CSRF 403 de outra origem, docs desligadas, só 80/443 publicadas, dados e sessão mantidos após `down` + `up` |

### Cenários obrigatórios (missão, seção 11)
| # | Cenário | Onde | Resultado |
|---|---|---|---|
| 1 | Conta + receita | `e2e/fluxos.spec.ts` | Aprovado (saldo R$ 4.500,00) |
| 2 | Despesa e saldo | idem | Aprovado |
| 3 | Transferência entre contas | idem | Aprovado (receita do mês inalterada) |
| 4 | Compra parcelada no cartão | idem | Aprovado (limite usado R$ 1.200,00) |
| 5 | Pagar fatura sem duplicar despesa | idem | Aprovado (gasto do mês sem o pagamento) |
| 6 | Pagamento parcial de dívida | idem | Aprovado |
| 7 | Investimento + aporte | idem | Aprovado (aporte não é gasto) |
| 8 | Atualização manual do saldo | idem | Aprovado (ganho +R$ 50,00) |
| 9 | Relatórios e metas | idem | Aprovado |
| 10 | Acesso a dados de outra pessoa | idem + testes de API | Aprovado (404 pela API e pela tela) |
| 11 | Recarregar e dados salvos | idem | Aprovado |
| 12 | Tela pequena | `e2e/telas.spec.ts` (iPhone SE) | Aprovado (sem rolagem lateral, alvos ≥ 44 px, texto 18 px) |
| 13 | Sem internet | `e2e/fluxos.spec.ts` | Aprovado (aviso, botão bloqueado, resposta perdida sem duplicar) |
| 14 | Restaurar backup em ambiente separado | `scripts/e2e-backup-check.sh` e `tests/db/test_backup_restore.py` | Aprovado |

### Defeitos encontrados pelos testes e corrigidos
1. Simulação de dívidas estourava a precisão quando os juros superam a parcela: agora interrompe e avisa.
2. Saldo e somas saíam como texto (`numeric` do PostgreSQL): conversão explícita para inteiro e teste que varre todas as respostas.
3. Conta de outra pessoa em movimento de investimento: o banco recusava (chave composta), mas a API respondia 500; agora valida antes e qualquer violação de integridade vira 422.
4. Saldo do início do mês ignorava contas abertas no dia 1º.
5. Cancelamento depois de estorno parcial creditava em dobro (achado por teste de mutação).
6. O site não aceitava `HEAD`, usado pelo Next.js para pré-carregar páginas.
7. Na primeira visita, o service worker recarregava a página e apagava o que fora digitado.
8. Depois de falha de rede, o botão "Salvar" ficava bloqueado até 30 s; agora reverifica a cada 3 s.
9. Mensagem "Conta não encontrado" (concordância).
10. Fatura aberta já paga aparecia só como "Aberta"; agora mostra "Paga".

### Não testado
* Safari real, instalação na Tela de Início e VoiceOver no iPhone (roteiro em `VALIDACAO_IPHONE.md`).
* Teste com usuários reais (ver `ACESSIBILIDADE.md`).
* Publicação em provedor de nuvem e certificado Let's Encrypt real.
* Integração contínua no GitHub (o arquivo existe; a execução depende do GitHub).
