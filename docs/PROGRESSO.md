# Progresso

Atualizado em 15/10/2026.

**Estado geral:** aplicação completa e testada em ambiente local. **Não publicada na internet** (depende de conta em provedor de nuvem, ver `IMPLANTACAO.md`).

## Implementado e testado

| Área | O que existe | Testes |
|---|---|---|
| Base | Dinheiro em centavos, datas civis, recorrência sem deslizar, relógio de São Paulo | Domínio (unitários e propriedades) |
| Banco | PostgreSQL 16, 3 migrações, 20 tabelas, RLS forçada, chaves compostas, papéis separados | Convenções no catálogo, migração ida e volta, mutação |
| Isolamento | Filtro na aplicação + RLS; identidade por transação; limpeza no pool | 3 usuários, 6 combinações de acesso cruzado em todas as rotas, pool de 1 conexão, concorrência |
| Autenticação | Login, sair, trocar senha, expiração, limite de tentativas, CSRF, cabeçalhos de segurança, linha de comando de usuários | API e linha de comando |
| Idempotência | Chave por operação em todas as criações | Reenvio, envios simultâneos, resposta perdida (API e navegador) |
| Contas e lançamentos | Contas, saldos, ajuste com histórico, categorias, receitas, despesas, reembolsos, transferências, edição com histórico, cancelamento | API + ponta a ponta |
| Contas a pagar | Avulsas e recorrentes, a receber, pagamento parcial, vencidas que permanecem, lista unificada com faturas e parcelas | API + ponta a ponta |
| Cartões | Compras à vista/parceladas, encargos, faturas derivadas, pagamento integral/parcial, limite, estorno, cancelamento, renegociação de fatura | Domínio + API (regressão contra dupla contagem) + ponta a ponta |
| Dívidas | Saldo ancorado, pagamentos com/sem juros, encargos, quitação, renegociação, entrada de empréstimo, 4 estratégias | Domínio + API + ponta a ponta |
| Investimentos | Renda fixa, variável e outros, aportes, retiradas, rendimentos, preço médio, valores informados, ganho estimado, TIR | Domínio + API + ponta a ponta |
| Metas | Contribuições, progresso, projeção com premissas | Domínio + API + ponta a ponta |
| Posso comprar? | Simula compra à vista ou no cartão: saldo previsto mês a mês com e sem a compra, efeito no limite, reserva de emergência, comprar agora × não comprar × esperar. Não grava nada | API (6 testes, incluindo isolamento e "nada é gravado") + ponta a ponta 9b |
| Início e relatórios | Resumo com definições explicadas, relatório mensal, evolução de 12 meses | API + ponta a ponta |
| Exportação | JSON completo e CSV de lançamentos, só do próprio usuário | API |
| Interface | 34 telas, preto e branco, acessível, celular e computador | Ponta a ponta (17 testes), tela pequena, rótulos |
| PWA | Manifesto, ícones iOS, service worker só da estrutura, aviso de versão | Build; uso offline nos testes ponta a ponta |
| Backup | Diário com rotação, SHA-256, restauração em banco novo | 12 testes + Compose real + restauração dos dados da interface |
| Implantação | Dockerfile, Compose com Caddy (HTTPS), migração separada, guia | Compose de produção local por HTTPS |

## Pendente
| Item | Motivo |
|---|---|
| Publicação na nuvem | Exige conta do Diogo no provedor (H1) |
| Cópia de backup fora do servidor e cifrada | Destino a decidir (D9) |
| Validação no iPhone físico | Exige publicação; roteiro pronto em `VALIDACAO_IPHONE.md` |
| Teste com usuários representativos | Não é possível neste ambiente (`ACESSIBILIDADE.md`) |
| Importação de CSV de extratos | Não implementada nesta versão (prevista na especificação original, item 4.11) |
| Revisão independente pelo Codex | Repositório disponível para isso |

## Limitações conhecidas
* Sem conexão, o app não salva (por decisão: não há fila de envio offline).
* Valores de investimentos dependem de atualização manual.
* Pagamento parcial de fatura: juros do rotativo são lançados pela pessoa na fatura seguinte (F-CARTAO-5).
* Ajuste de vencimento para dia útil não é feito (F-CARTAO-3).
* O "Posso comprar?" trabalha por mês e só enxerga o que está cadastrado: gastos do dia a dia não registrados não entram (F-SIM-2).
* A CSP permite scripts inline (exigência do site estático do Next.js).
