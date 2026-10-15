# Finanças Pessoais

Aplicativo de controle financeiro pessoal para **três pessoas**, cada uma com dados privados e isolados. Uso principal no iPhone (Safari e Tela de Início, como PWA) e também no computador. Português do Brasil, valores em `R$ 1.234,56`, datas em `DD/MM/AAAA`, fuso de São Paulo.

**Estado:** aplicação completa e testada localmente. **Ainda não publicada** na internet (ver `docs/IMPLANTACAO.md`).

## O que faz
* **Início:** dinheiro disponível, o que já está comprometido, dinheiro livre, recebi e gastei no mês, contas que vencem, quanto devo, quanto tenho investido, patrimônio.
* **Contas e lançamentos:** contas, saldos, receitas, despesas, transferências (sem virar receita), ajustes, edição com histórico.
* **Contas a pagar:** vencimentos, recorrências, pagamento parcial; vencidas continuam aparecendo.
* **Cartões:** compras parceladas, faturas, pagamento integral ou parcial, limite, estornos, cancelamentos, renegociação de fatura, sem dupla contagem.
* **Dívidas:** saldo, parcelas, pagamentos, renegociação, comparação de estratégias.
* **Investimentos:** renda fixa, variável e outros, aportes, retiradas, rendimentos, preço médio, ganho estimado e rentabilidade (TIR).
* **Planejamento e relatórios:** metas com projeção e premissas, simulador "Posso comprar?", plano do mês (contas, investir, livre para gastar e projeção), gastos por categoria, evolução mensal.
* **Exportação** dos próprios dados (CSV e JSON) e **backup** automático do servidor.

## Arquitetura
```
backend/    FastAPI + motor financeiro (Python) + migrações Alembic
frontend/   Next.js + TypeScript, exportado como site estático (PWA)
deploy/     Docker Compose de produção (PostgreSQL, API, Caddy com HTTPS, backup)
scripts/    backup, restauração, testes com banco e ponta a ponta
docs/       decisões, modelo de dados, segurança, implantação, guias, registros de testes
```
A API e o site são servidos pelo mesmo endereço. Regras financeiras ficam só no backend; o banco reforça o isolamento entre usuários com Row-Level Security.

## Executar localmente (desenvolvimento)
Requisitos: Python 3.12+ com [uv](https://docs.astral.sh/uv/), Node.js 22+, Docker.

```bash
make install            # dependências
make test               # backend (sobe PostgreSQL descartável no Docker) e frontend
make lint               # ruff, mypy, eslint, tsc
make build              # site estático em frontend/out
make e2e                # testes ponta a ponta (perfil iPhone) + backup/restauração
```

Para usar o app no computador com dados de teste:
```bash
make build
scripts/stack-local.sh sh -c 'echo "Abra $FIN_E2E_URL  (usuários: ana, bruno, carla)"; sleep 3600'
```
As senhas de teste estão em `scripts/stack-local.sh` (dados sintéticos, banco descartável).

## Produção
`docs/IMPLANTACAO.md`: VM gratuita, domínio com HTTPS, criação das três contas, atualização sem perder dados.

## Documentos
| Arquivo | Conteúdo |
|---|---|
| `docs/GUIA_DO_USUARIO.md` | Guia simples para as três pessoas (inclui instalação no iPhone) |
| `docs/DECISOES.md` | Definições financeiras e todas as decisões |
| `docs/MODELO_DE_DADOS.md` | Tabelas e o princípio de origem única |
| `docs/BANCO_E_ISOLAMENTO.md` | Como o isolamento entre usuários funciona e é testado |
| `docs/PRIVACIDADE.md` | O que fica onde e quem vê o quê |
| `docs/BACKUP.md` | Backup e restauração |
| `docs/IMPLANTACAO.md` | Publicação e operação |
| `docs/VALIDACAO_IPHONE.md` | Roteiro de teste no iPhone físico |
| `docs/ACESSIBILIDADE.md` | Revisão de acessibilidade |
| `docs/PROGRESSO.md` / `docs/PLANO.md` | Situação e pendências |
| `docs/REGISTRO_TESTES.md` | Resultados reais de todos os testes |
| `docs/RELATORIO_FINAL.md` | Relatório de entrega |
| `docs/ETAPA0_*.md`, `docs/MUDANCAS_DE_ESCOPO.md` | Histórico de auditoria e escopo |
