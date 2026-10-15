# Finanças Pessoais

Aplicativo financeiro pessoal para três pessoas, cada uma com dados privados e isolados. Uso principal no iPhone (Safari e Tela de Início, como PWA) e também no computador.

**Estado atual:** T1.1 (base técnica). Ainda não há login, banco de dados nem telas financeiras. O app **não está publicado** na internet. Veja `docs/PROGRESSO.md`.

## Estrutura

```
backend/    API FastAPI + motor financeiro (Python)
  app/domain/   regras puras: dinheiro em centavos, datas civis
  app/core/     configuração e relógio (fuso America/Sao_Paulo)
  app/api/      rotas HTTP
  tests/        testes automatizados
frontend/   Next.js + TypeScript, exportado como site estático (PWA)
docs/       auditoria, revisão, decisões, plano, progresso, registro de testes
```

## Pré-requisitos

* Python 3.12 ou mais recente e [uv](https://docs.astral.sh/uv/)
* Node.js 22 ou mais recente
* `make` (no Windows, use os comandos de dentro do `Makefile` manualmente ou o WSL)

## Como executar localmente

```bash
cp .env.example .env   # opcional nesta etapa
make install           # instala dependências do backend e do frontend
make test              # testes do backend (pytest) e do frontend (vitest em 3 fusos)
make lint              # ruff, mypy estrito, eslint e tsc
make build             # gera o site estático em frontend/out
```

Para desenvolver, em dois terminais:

```bash
make dev-backend    # API em http://127.0.0.1:8000  (saúde: /api/health)
make dev-frontend   # app em http://localhost:3000  (/api é encaminhado para a API)
```

## Regras que o código já garante

* Dinheiro é sempre inteiro em centavos. `float` é rejeitado e um teste impede seu uso em `app/domain`.
* Datas financeiras são datas civis (`AAAA-MM-DD`), sem conversão para UTC. "Hoje" é calculado em America/Sao_Paulo por um relógio injetável.
* Recorrências mensais partem sempre da data original: 31/01 → 28/02 → 31/03.
* No frontend, uma regra de lint proíbe `new Date(texto)`, `Date.parse` e `parseFloat`.

## Documentos

| Arquivo | Conteúdo |
|---|---|
| `docs/ETAPA0_AUDITORIA.md` | Auditoria inicial (preservada) |
| `docs/ETAPA0_REVISAO.md` | Revisão crítica da auditoria (preservada) |
| `docs/MUDANCAS_DE_ESCOPO.md` | Histórico de mudanças de escopo e conflitos com decisões anteriores |
| `docs/DECISOES.md` | Decisões em aberto e decisões tomadas |
| `docs/PLANO.md` | Plano de tarefas atualizado |
| `docs/PROGRESSO.md` | O que está implementado, testado e pendente |
| `docs/REGISTRO_TESTES.md` | Comandos executados e resultados reais |
