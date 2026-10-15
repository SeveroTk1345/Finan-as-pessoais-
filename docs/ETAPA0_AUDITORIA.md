# Etapa 0 · Auditoria e plano de implementação

Data da auditoria: 15/10/2026
Status: aguardando aprovação do Diogo e revisão do Codex. Nenhum código foi escrito.

## 1. Estrutura atual do repositório

Não existe repositório do app financeiro.

* `/home/user` (diretório de trabalho da sessão) estava vazio e não é um repositório git.
* Repositórios GitHub acessíveis na conta `SeveroTk1345`: Simulador-de-juros-compostos, Painel-de-fluxo-de-processos, Analise-de-desempenho-NBA, Analise-de-desempenho-Gremio, Mapeamento-de-lotes-rurais, Modelagem-relacional, Agregacao-cruzamento-por-identificador, Grafico-cenarios-de-renegociacao, Reconcilia-o-de-bases-divergentes. Nenhum corresponde ao app (Next.js + FastAPI + PostgreSQL).
* Se o código existir em outro lugar (outra conta, repositório privado não autorizado, máquina local), a auditoria precisa ser refeita sobre ele antes de qualquer implementação.

Ferramentas verificadas no ambiente:

| Ferramenta | Versão | Observação |
|---|---|---|
| Node.js | 22.22.0 | npm 10.9.4, pnpm 10.28.0 |
| Python | 3.13 | uv 0.11.32 |
| PostgreSQL | 16.15 | cluster local instalado, parado |
| Docker | 29.8.2 | disponível |
| Registro npm / PyPI | acessíveis | Next.js 16.x, Serwist 9.x, FastAPI |

## 2. Funcionalidades já implementadas

Nenhuma.

## 3. Regras financeiras encontradas

Nenhuma regra implementada. As regras do documento de requisitos são a única especificação e estão consolidadas na seção 5.3 (decisões propostas) e 5.4 (ambiguidades).

## 4. Testes existentes e resultados

Nenhum teste existe. Nada foi executado.

## 5. Problemas, riscos e decisões

### 5.1 Riscos técnicos

| # | Risco | Impacto | Mitigação proposta |
|---|---|---|---|
| R1 | Frontend e API em domínios diferentes (ex.: Vercel + Render) | Safari/ITP bloqueia cookies de terceiros: login quebra no iPhone | Servir frontend e `/api` na **mesma origem** via proxy reverso |
| R2 | Hospedagem gratuita com hibernação | Primeira requisição lenta (dezenas de segundos), timeouts no celular | Preferir acesso local via Tailscale; nuvem gratuita como opção documentada |
| R3 | Bancos gratuitos que expiram ou pausam por inatividade | Perda de dados | Backup JSON exportável + rotina de backup automático local |
| R4 | Ponto flutuante em dinheiro | Centavos errados acumulados | Centavos inteiros (`BIGINT`) no banco e na API; `Decimal` em cálculos de juros |
| R5 | Virada de mês e fuso | Lançamento no mês errado | Datas financeiras como `DATE` (sem hora); "hoje" sempre calculado em America/Sao_Paulo |
| R6 | Dupla contagem cartão/fatura/dívida | Saldos e limites errados | Modelo de origem única (seção 5.3) e testes de regressão específicos |
| R7 | PWA "offline" que perde dados | Lançamentos somem | V1: leitura em cache, escrita bloqueada offline com aviso explícito |
| R8 | Dados financeiros em cache no aparelho | Exposição se o iPhone for compartilhado | Logout limpa Cache Storage e IndexedDB; cache só de GET autenticado |
| R9 | Duas IAs editando os mesmos arquivos | Conflitos e regressões | Uma tarefa por vez, uma branch por tarefa, revisão cruzada do diff |

### 5.2 Arquitetura recomendada para acesso pelo iOS

**Opção A (recomendada): servidor em casa + Tailscale**

```
iPhone (Safari / PWA) ──HTTPS──> https://financas.<tailnet>.ts.net
                                   │  (tailscale serve: certificado TLS válido)
                                   ▼
                              Caddy (mesma origem)
                               ├── /      → Next.js (export estático, PWA)
                               └── /api/* → FastAPI (uvicorn)
                                              └── PostgreSQL 16 (rede interna Docker, sem porta pública)
```

* Custo R$ 0. Roda em um PC, notebook ou Raspberry Pi com Docker Compose.
* HTTPS real com certificado confiável pelo iOS, sem abrir porta no roteador e sem expor o banco.
* Dados ficam na sua casa. Nenhum terceiro armazena dados financeiros.
* Limitações: o computador precisa estar ligado; o iPhone precisa do app Tailscale conectado; sem o servidor, só o cache de leitura funciona.
* Autenticação própria continua obrigatória (senha com hash Argon2, cookie de sessão `HttpOnly; Secure; SameSite=Strict`), porque a rede privada não substitui login.

**Opção B (alternativa): nuvem gratuita**

* VM "Always Free" (ex.: Oracle Cloud) rodando o mesmo Docker Compose. Mesma arquitetura, disponível 24h. Exige cadastro com cartão para verificação e não há garantia de permanência do plano gratuito.
* Evitar a combinação Vercel + Render + Neon/Supabase: origens diferentes (R1), hibernação (R2) e pausas por inatividade (R3).
* Dados ficam em servidor de terceiro: exige consentimento explícito.

**Opção C (descartada para V1): local first puro no navegador (IndexedDB)**

* Seria a única forma de edição offline real, mas move o motor financeiro para o frontend (contradiz "backend é fonte de verdade") e o Safari pode apagar armazenamento local. Fica registrada como evolução futura.

**Por que export estático do Next.js:** o backend é a fonte de verdade; não há necessidade de SSR. Um SPA estático é mais simples de cachear no service worker, roda atrás de qualquer servidor e elimina um processo Node em produção.

**Política offline da V1 (explícita):**

| Situação | Comportamento |
|---|---|
| Visualização sem conexão | Mostra último dado carregado com faixa "Dados de DD/MM/AAAA HH:MM, sem conexão" |
| Criar ou editar sem conexão | Bloqueado, botão desabilitado, mensagem clara. Nada é enfileirado |
| Sincronização | Não existe na V1 |
| Atualização do app | Service worker com aviso "Nova versão disponível · Atualizar" |

### 5.3 Decisões de modelagem financeira propostas (precisam de aprovação)

1. **Dinheiro**: inteiro em centavos em todo o sistema; JSON trafega `amount_cents: 12345`. Valores sempre positivos com direção dada pelo tipo do registro (evita sinal invertido por erro de formulário).
2. **Livro razão de caixa (`ledger_entries`)**: toda movimentação **realizada** de dinheiro em conta gera exatamente uma linha com `origin_type` e `origin_id`. Saldo da conta = saldo inicial + soma das linhas. Previstos nunca entram aqui.
3. **Transferência**: um registro `transfer` gera duas linhas de razão (saída e entrada) marcadas `origin_type=transfer`, excluídas de receitas e despesas no consolidado.
4. **Previsto vs realizado**: receitas e despesas previstas são `scheduled_items`. Elas só viram realizadas quando o usuário confirma, o que cria a linha de razão vinculada. Vencimento passado gera status "atrasado", nunca "pago".
5. **Cartão**: a compra (`card_purchase`) é a única origem. Gera `card_installments` (divisão determinística do total; centavos residuais na primeira parcela) atribuídas a uma fatura pela regra de fechamento. A fatura é um **agrupamento**, não um novo valor.
   * Limite comprometido = soma das parcelas não canceladas − pagamentos de fatura aplicados.
   * Limite disponível = limite total − limite comprometido.
   * Pagamento de fatura gera linha de razão `origin_type=card_payment` classificada como **liquidação**, não consumo.
   * Estorno gera crédito na fatura aberta; cancelamento cancela parcelas futuras ainda não faturadas.
   * Status da fatura derivado: aberta (antes do fechamento), fechada, paga (pagamentos ≥ total), parcialmente paga.
6. **Dívida**: entidade própria com plano de parcelas. Não pode ser vinculada a cartão. Pagamento gera linha de razão `origin_type=debt_payment` (liquidação).
7. **Juros**: taxa armazenada com período explícito (`mensal` ou `anual`) em `NUMERIC`. Taxa desconhecida = `NULL`, nunca zero.
8. **Visão mensal em regime de caixa**: calculada sob demanda a partir das origens, nada de projeção salva como dado real. Cartão entra pelo vencimento da fatura; a compra não é contada de novo.
9. **Dívidas e simulações**: o motor recebe uma cópia imutável dos dados e retorna o cenário; nenhum caminho de simulação tem acesso de escrita ao banco.

### 5.4 Ambiguidades para decisão (não serão inventadas)

| # | Dúvida | Proposta padrão |
|---|---|---|
| A1 | Compra feita exatamente no dia do fechamento entra em qual fatura? | Entra na próxima fatura (comportamento mais comum), com configuração por cartão |
| A2 | Fechamento/vencimento em dia inexistente (31 em fevereiro) ou fim de semana | Usar o último dia do mês; não ajustar para dia útil na V1 |
| A3 | Despesas por categoria: caixa ou competência? | Visão mensal em caixa; relatório de categorias em competência (data da compra), sinalizado na tela |
| A4 | Parcelamento da fatura do cartão pelo banco | Vira dívida nova que liquida a fatura sem saída de caixa |
| A5 | Pagamento parcial de fatura: o restante gera juros? | Saldo restante fica pendente; juros/rotativo são lançados manualmente pelo usuário |
| A6 | Estratégia avalanche com taxa desconhecida | Dívidas sem taxa vão para o fim e a tela avisa "estratégia baseada em informação incompleta" |
| A7 | Arredondamento | Meio para cima (ROUND_HALF_UP), padrão usual em contratos brasileiros |
| A8 | "Próximo recebimento" no dinheiro livre | Próxima receita prevista marcada como principal (ex.: salário) |
| A9 | Pesos da estratégia "Equilibrada" | Pontuação = 50% taxa normalizada + 50% parcela/saldo; pesos editáveis e exibidos |

## 6. Estrutura proposta do repositório

```
financas/
├── backend/
│   ├── app/
│   │   ├── api/            # rotas FastAPI e schemas Pydantic (contratos)
│   │   ├── services/       # casos de uso, transações de banco
│   │   ├── domain/         # motor financeiro puro (sem I/O)
│   │   ├── db/             # modelos SQLAlchemy, repositórios
│   │   └── core/           # config, auth, tempo (America/Sao_Paulo)
│   ├── migrations/         # Alembic
│   └── tests/              # unit (domain), integração (API + Postgres)
├── frontend/               # Next.js, TypeScript, export estático, PWA
├── deploy/                 # docker-compose, Caddyfile, guia Tailscale
├── docs/                   # auditoria, decisões, limitações, registro de testes
└── Makefile                # make test, make lint, make build, make dev
```

Stack: FastAPI, SQLAlchemy 2, Alembic, Pydantic 2, pytest, ruff, mypy; Next.js com TypeScript estrito, React Hook Form + Zod (validação de formato apenas; regra de negócio no backend), Serwist para service worker, Playwright com perfil iPhone para testes de interface.

## 7. Plano de implementação

Cada tarefa: uma branch, um PR, revisão cruzada, testes + lint + build registrados em `docs/REGISTRO_TESTES.md`.

**Etapa 1 · Base técnica**
* T1.1 Esqueleto do monorepo, ferramentas e primitivas de dinheiro/data (detalhada na seção 8)
* T1.2 Banco: Alembic, Postgres via Docker Compose, testes de integração com banco descartável
* T1.3 Autenticação de usuário único, sessão por cookie, rate limit no login
* T1.4 Frontend: Next.js, layout mobile-first, safe areas, navegação inferior com 5 abas
* T1.5 PWA: manifesto, ícones iOS, service worker, política offline, aviso de atualização
* T1.6 Deploy: Caddy + Compose + guia Tailscale; teste real no iPhone

**Etapa 2 · Operações essenciais**
* T2.1 Contas (CRUD, ativo/inativo, saldo inicial com data)
* T2.2 Livro razão e cálculo de saldo
* T2.3 Transferências
* T2.4 Receitas previstas/recebidas e recorrência
* T2.5 Despesas, obrigações, categorias personalizadas
* T2.6 Tela de Movimentações com lançamento rápido (≤ 3 toques até o formulário)
* T2.7 Dashboard inicial (saldo, mês, contas a vencer)

**Etapa 3 · Cartões e dívidas**
* T3.1 Cartões, regra de fechamento e geração de parcelas
* T3.2 Faturas derivadas e status
* T3.3 Pagamento integral/parcial de fatura e limite disponível
* T3.4 Estornos e cancelamentos
* T3.5 Dívidas, plano de parcelas, pagamentos, renegociação
* T3.6 Suíte de regressão contra dupla contagem

**Etapa 4 · Planejamento**
* T4.1 Visão mensal (caixa) com navegação e previsto vs realizado
* T4.2 Estratégias de quitação e comparação
* T4.3 Reserva e investimentos (nominal vs real, três cenários)
* T4.4 Simulador "Posso comprar?"
* T4.5 Dashboard completo (dinheiro livre, próximos 30 dias, comprometido)

**Etapa 5 · Dados e robustez**
* T5.1 Backup JSON versionado e restauração com validação
* T5.2 Exportação CSV
* T5.3 Importação CSV com mapeamento, pré-visualização e duplicatas
* T5.4 Revisão de segurança (headers, CORS, logs, dependências)

**Etapa 6 · Validação no iPhone**
* T6.1 Roteiro de teste manual no Safari e na Tela de Início, com registro dos resultados
* T6.2 Teste de perda de conexão e documentação de limitações

## 8. Primeira tarefa concreta: T1.1

**Objetivo:** criar o esqueleto do projeto e as duas primitivas das quais todo o resto depende: dinheiro em centavos e data no fuso de São Paulo. Sem banco, sem telas, sem regra de negócio.

Arquivos:

| Arquivo | Conteúdo |
|---|---|
| `README.md` | Visão geral, pré-requisitos, comandos |
| `Makefile` | `install`, `test`, `lint`, `build`, `dev` |
| `.gitignore`, `.editorconfig`, `.env.example` | Sem segredos reais |
| `backend/pyproject.toml` | FastAPI, pytest, ruff, mypy estrito |
| `backend/app/main.py` | App FastAPI com `GET /api/health` |
| `backend/app/core/config.py` | Configuração via variáveis de ambiente (pydantic-settings) |
| `backend/app/core/clock.py` | `today_sp()`, `now_sp()`, relógio injetável para testes |
| `backend/app/domain/money.py` | Tipo `Money` (centavos `int`), parsing de "1.234,56", formatação BRL, divisão em parcelas sem perder centavos |
| `backend/app/domain/dates.py` | `month_bounds()`, `clamp_day()`, `add_months()` |
| `backend/tests/domain/test_money.py` | Testes de dinheiro |
| `backend/tests/domain/test_dates.py` | Testes de datas e virada de mês |
| `backend/tests/api/test_health.py` | Teste da API |
| `frontend/` | Next.js + TypeScript estrito, página placeholder, ESLint, `next build` com export estático |
| `frontend/src/lib/format.ts` | Apenas formatação de exibição (BRL e DD/MM/AAAA), sem regra financeira |
| `docs/DECISOES.md` | Decisões 5.3 e ambiguidades 5.4 com status |
| `docs/REGISTRO_TESTES.md` | Resultado real dos comandos executados |

Critérios de aceitação:

1. `make test` executa pytest com sucesso, incluindo:
   * `Money.parse_brl("1.234,56") == 123456`; rejeita texto inválido, mais de 2 casas decimais e valor negativo onde não permitido.
   * `split_installments(10000, 3) == [3334, 3333, 3333]` e a soma das parcelas é sempre igual ao total (teste de propriedade com Hypothesis).
   * `add_months(31/01/2026, 1) == 28/02/2026` e `clamp_day(2028, 2, 31) == 29/02/2028`.
   * `today_sp()` retorna 14/10/2026 quando o relógio UTC marca 15/10/2026 02:00.
2. Nenhum `float` aparece em `domain/` (verificado por teste ou regra de lint).
3. `make lint` passa: ruff, mypy estrito, ESLint, `tsc --noEmit`.
4. `make build` gera o export estático do frontend sem erros.
5. `GET /api/health` retorna 200 com `{"status": "ok"}`.
6. Nenhum segredo no repositório; `.env.example` só com valores fictícios.
7. Saídas reais dos comandos registradas em `docs/REGISTRO_TESTES.md`.

## 9. Pendências antes de começar

1. Confirmar que não há código existente em outro lugar.
2. Escolher onde criar o repositório (novo repositório GitHub privado, por exemplo `SeveroTk1345/financas-pessoais`).
3. Aprovar as decisões 5.3 ou indicar alterações.
4. Responder às ambiguidades 5.4 (ou aceitar as propostas padrão).
5. Escolher opção de hospedagem (A recomendada).
6. Codex revisar este documento antes da T1.1.
