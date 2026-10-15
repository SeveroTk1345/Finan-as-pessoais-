# Progresso

Atualizado em 15/10/2026.

**Estado geral:** base técnica pronta. O app ainda não tem login, banco, telas financeiras nem publicação. **Não está disponível na internet.**

## Implementado e testado

| Item | Onde | Testes |
|---|---|---|
| Tipo `Money` em centavos, rejeita `float` e `bool`, limite de 1 trilhão de reais (abaixo do inteiro exato do JavaScript) | `backend/app/domain/money.py` | `tests/domain/test_money.py` |
| Leitura de valores no formato BR (`1.234,56`, `R$ 1.234,56`, espaço não separável), rejeição de formatos ambíguos | idem | idem, com teste de propriedade (formatar e ler de volta) |
| Divisão em parcelas sem perder centavos | idem | Teste de propriedade: soma = total para qualquer valor e 1 a 48 parcelas |
| Arredondamento com modo explícito (sem padrão até decisão A7) | idem | idem |
| Datas civis: dias do mês, limite de dia, soma de meses, mês de referência, leitura e formatação DD/MM/AAAA | `backend/app/domain/dates.py` | `tests/domain/test_dates.py` |
| Recorrência mensal a partir da data original (sem deslizar o dia 31) | idem | Teste de propriedade em 2000 a 2100 |
| Relógio injetável e "hoje" em America/Sao_Paulo, incluindo horário de verão histórico | `backend/app/core/clock.py` | `tests/core/test_clock.py` |
| Proibição de `float` e divisão `/` no domínio | `tests/domain/test_no_float.py` | Teste que analisa o código |
| API com `GET /api/health`; documentação desligada em produção | `backend/app/main.py`, `app/api/health.py` | `tests/api/test_health.py` e teste com servidor real |
| Formatação de reais e datas no frontend, sem `Date` | `frontend/src/lib/format.ts` | `format.test.ts` em 3 fusos |
| Máscara de valor estilo app de banco (dígitos entram pela direita) | idem | idem |
| Lint que proíbe `new Date(texto)`, `Date.parse` e `parseFloat` | `frontend/eslint.config.mjs` | Verificado com arquivo de prova |
| Base visual: fonte 18 px, botões 48 px, foco visível, áreas seguras do iPhone, zoom permitido | `frontend/src/app/globals.css`, `layout.tsx` | Build; validação visual no iPhone ainda não feita |

## Pendente
Ver `PLANO.md` (tarefas) e `DECISOES.md` (decisões em aberto).

## Limitações conhecidas
* Página inicial provisória, sem dados.
* Não há Docker ainda (entra na T1.2 com o PostgreSQL).
* `make` não existe por padrão no Windows; os comandos estão listados no `Makefile` para uso manual.
* A regra de lint de datas pega `new Date(x)` com um argumento; `new Date(ano, mes, dia)` continua permitido, porque não tem o problema de UTC.

## GitHub
* Repositório em uso: `SeveroTk1345/Finan-as-pessoais-` (público). Envio funcionando.
* Pendência G1: renomear para `financas-pessoais` e tornar privado.
