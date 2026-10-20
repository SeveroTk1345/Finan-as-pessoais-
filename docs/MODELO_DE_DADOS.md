# Modelo de dados

Migrações: `backend/migrations/versions/0001` a `0003`. Todas as tabelas com dados de usuário têm `owner_id`, `UNIQUE (owner_id, id)`, chaves compostas e Row-Level Security (ver `BANCO_E_ISOLAMENTO.md`).

## Princípio central: origem única
Cada fato financeiro é registrado uma vez, na tabela que é a sua origem. Telas e relatórios são calculados a partir das origens; nenhum total é gravado.

| Fato | Origem | Não é contado de novo em |
|---|---|---|
| Dinheiro que entrou ou saiu de uma conta | `transactions` (livro razão) | — |
| Gasto no cartão | `card_purchases` + `card_installments` | pagamento da fatura (`transactions.kind = pagamento_fatura` é liquidação) |
| Fatura | calculada a partir de parcelas, `card_credits` e pagamentos | não existe tabela de faturas |
| Conta a pagar | `bills` (o previsto) | o pagamento é uma `transaction` ligada por `bill_id` |
| Recorrência | `recurring_rules` (ocorrências calculadas; gravadas em `bills` só quando usadas) | — |
| Dívida | `debts` (saldo âncora) + `debt_events` + pagamentos em `transactions` | — |
| Parcelamento de fatura | `debts` (para acompanhamento) + parcelas do cartão | pagamento direto da dívida é bloqueado |
| Investimento | `investments`, `investment_movements`, `investment_valuations` | aporte não é despesa; resgate não é receita |
| Meta | `goals` + `goal_contributions` | não movimenta contas |

## Tabelas
| Tabela | Função |
|---|---|
| `users` | Três usuários; senha em hash Argon2 |
| `sessions`, `login_attempts`, `idempotency_keys` | Sessões, limite de tentativas e repetição segura de operações |
| `passkeys`, `webauthn_challenges` | Chave pública de cada aparelho com digital ou rosto ativado; desafios de uso único (acessíveis só por funções de login) |
| `accounts` | Contas (saldo inicial + data, marcação "dia a dia") |
| `categories` | Categorias de receita e despesa |
| `transactions` | Livro razão: `kind` ∈ receita, despesa, transferencia, ajuste, pagamento_fatura, pagamento_divida, entrada_emprestimo, reembolso, investimento; `status` ativo/cancelado |
| `recurring_rules`, `bills` | Contas a pagar e a receber. Parcelas de carnê ou boleto são contas ligadas por `installment_group`, com `installment_number` e `installments_total` (migração 0005) |
| `cards`, `card_purchases`, `card_installments`, `card_credits` | Cartões, compras (compra, encargo, parcelamento_fatura), parcelas com a fatura gravada, estornos/cancelamentos/renegociação |
| `debts`, `debt_events` | Dívidas e encargos, descontos, baixa por renegociação |
| `investments`, `investment_movements`, `investment_valuations` | Carteira, movimentos e valores informados |
| `goals`, `goal_contributions` | Metas |
| `category_budgets` | Teto mensal por categoria de despesa (migração 0006); o gasto é calculado na hora |
| (funções `setup_*`) | Migração 0007: contar contas, criar conta (no máximo 3, com trava na tabela) e redefinir senha encerrando as sessões. SECURITY DEFINER, executáveis só por `fin_app`, usadas pela página /configurar protegida por código |
| `audit_log` | Histórico de edições e cancelamentos |

## Restrições importantes no banco
* Valores sempre positivos em centavos (`bigint`), com limite de 1 trilhão de reais; a direção vem do tipo.
* `receita` só entra; `despesa` só sai; pagamento de fatura exige cartão e vencimento; pagamento de dívida exige dívida.
* Juros da dívida não podem passar do valor pago.
* Parcelamento de fatura tem obrigatoriamente cartão e dívida ligados.
* Taxa de juros e período andam juntos (os dois ou nenhum).
