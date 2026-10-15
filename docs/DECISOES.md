# Decisões

Atualizado em 15/10/2026, depois da T1.1.

Legenda de situação: **Aberta** (depende do Diogo) · **Proposta técnica** (posso decidir, mas está registrada para revisão do Codex) · **Tomada**.

Regra: nenhuma decisão aberta é tratada como tomada no código. Funcionalidades bloqueadas não serão implementadas de forma definitiva antes da resposta.

## Resumo

| ID | Tema | Situação | Bloqueia |
|---|---|---|---|
| H1 | Hospedagem em nuvem gratuita | Aberta | T1.6 (publicação) |
| G1 | Nome e visibilidade do repositório | Aberta | Nada técnico |
| P1 | Cache de dados no aparelho | Aberta | T1.5 |
| P2 | Backups individuais | Aberta | T1.2 (parte individual), T5.1 |
| P3 | Transparência sobre acesso do administrador do servidor | Aberta | Uso real pelas três pessoas |
| D10 | Prazos de sessão | Aberta (parcial) | T1.3 (valores, não a estrutura) |
| A1 | Compra no dia do fechamento | Aberta | T3.1 |
| A2 | Dia inexistente e fim de semana | Aberta | T3.1, T3.2 |
| A3 | Regime de caixa ou competência | Aberta | T4.1 |
| A4 | Parcelamento de fatura | Aberta | T3.3 |
| A5 / D7 | Pagamento parcial e rotativo | Aberta | T3.3 |
| A6 | Avalanche sem taxa | Aberta | T4.2 |
| A7 | Regra de arredondamento | Aberta | T3.5, T4.2, T4.3 |
| A8 | Próximo recebimento | Aberta | T4.5 |
| A9 | Pesos da estratégia Equilibrada | Aberta | T4.2 |
| D2 | Estorno parcial de compra parcelada | Aberta | T3.4 |
| D3 | Contas que contam como "dinheiro disponível" | Aberta | T2.7, T4.5 |
| D4 | Fórmula do dinheiro livre | Aberta | T4.5 |
| D5 | Recorrências virtuais | Proposta técnica | T2.4 |
| D6 | Edição de lançamentos realizados | Aberta | T2.2 |
| D8 | Compras internacionais | Aberta | T3.1 |
| D9 | Destino da cópia externa do backup | Aberta | T1.2 (parte externa) |
| T-ISO | Isolamento entre usuários no banco | Proposta técnica | T1.2, T1.3 |
| T-SES | Formato da sessão | Proposta técnica | T1.3 |

---

## Decisões abertas de infraestrutura e privacidade

### H1 · Hospedagem gratuita em nuvem
* **Pergunta.** Onde publicar frontend, API e PostgreSQL sem custo, com HTTPS, sem o computador do Diogo ligado?
* **Alternativas.**
  1. VM "Always Free" da Oracle Cloud com Docker Compose (Caddy + API + PostgreSQL). Um único endereço, banco sem porta pública. O cadastro pede cartão para verificação de identidade, e a disponibilidade de máquinas gratuitas varia por região.
  2. Combinação de serviços gratuitos separados (site estático, API e banco gerenciado em provedores diferentes). Costuma ter hibernação, bancos que expiram ou pausam e origens diferentes, o que quebra cookies no Safari.
  3. Outras VMs gratuitas de grandes nuvens. Em geral também exigem cartão e conta de faturamento.
* **Recomendação.** Investigar a opção 1 na T1.6. Pela regra de custo do Diogo, se o cadastro exigir cartão com risco de cobrança, **paro e apresento as alternativas antes de qualquer cadastro**. Nenhuma conta será criada por mim.
* **Consequências.** Opção 1: arquitetura igual à de desenvolvimento, porém com manutenção do sistema operacional e risco de o plano gratuito mudar. Opção 2: menos manutenção, mas mais pontos de falha e problemas de sessão no iPhone.
* **Bloqueia.** T1.6. Não bloqueia desenvolvimento local.
* **Observação.** Os limites e condições atuais dos provedores ainda não foram verificados nesta sessão. Serão conferidos nas páginas oficiais na T1.6, e o resultado será registrado aqui.

### G1 · Nome e visibilidade do repositório
* **Pergunta.** O repositório real é `SeveroTk1345/Finan-as-pessoais-` e está **público**. O pretendido é `financas-pessoais`, privado.
* **Alternativas.** Renomear e tornar privado (feito pelo Diogo no GitHub) ou manter.
* **Recomendação.** Renomear e tornar privado antes da T1.2, que vai descrever a infraestrutura de produção.
* **Consequências.** Renomear não perde nada: o GitHub redireciona o nome antigo. Depois disso, ajusto o `remote` local.
* **Bloqueia.** Nada técnico.

### P1 · Cache de dados financeiros no aparelho
* **Pergunta.** Com três pessoas podendo usar o mesmo aparelho, o app deve guardar dados financeiros para leitura sem conexão?
* **Alternativas.**
  1. Não guardar dados financeiros no aparelho. Só a estrutura do app fica em cache. Sem conexão, aparece "Sem conexão com o servidor".
  2. Guardar por usuário, apagar ao sair e ao expirar a sessão, com a faixa "Dados de DD/MM/AAAA HH:MM".
* **Recomendação.** Opção 1 na V1. É mais simples para usuários pouco técnicos e elimina o risco de outra pessoa ver dados em cache. A opção 2 pode vir depois, com testes de troca de usuário.
* **Consequências.** Opção 1: sem leitura offline. Opção 2: leitura offline, com risco residual se a sessão não for encerrada.
* **Bloqueia.** T1.5.

### P2 · Backups individuais
* **Pergunta.** Além da cópia automática do banco inteiro (infraestrutura), cada usuário poderá exportar e restaurar apenas os próprios dados?
* **Alternativas.**
  1. Sim: exportação JSON individual e restauração individual que só substitui os dados do próprio usuário.
  2. Só exportação individual (CSV/JSON); restauração apenas pelo administrador, a partir da cópia do banco inteiro.
* **Recomendação.** Exportação individual na T5.1 e restauração individual com confirmação em duas etapas. Restaurar o banco inteiro fica só como recuperação de desastre.
* **Consequências.** Restauração individual exige testes de isolamento extras (não pode tocar dados de outra pessoa).
* **Bloqueia.** Parte individual da T1.2 e T5.1. A cópia do banco inteiro na T1.2 não fica bloqueada.

### P3 · Acesso técnico do administrador do servidor
* **Pergunta.** A aplicação não terá conta com acesso às finanças dos outros. Mas quem administra o servidor (o Diogo) tem acesso técnico ao banco e às cópias de segurança. Como tratar isso?
* **Alternativas.**
  1. Informar as outras duas pessoas por escrito e manter cópias de segurança cifradas.
  2. Criptografia de ponta a ponta no aparelho. Isso impede os cálculos no servidor, contradiz "backend como fonte de verdade" e torna a recuperação de senha impossível sem perder dados.
* **Recomendação.** Opção 1, documentada em `docs/PRIVACIDADE.md` (a criar na T1.3): o que fica no servidor, quem tem acesso técnico e o compromisso de não consultar o banco diretamente.
* **Consequências.** A opção 2 exigiria refazer a arquitetura.
* **Bloqueia.** Uso real pelas três pessoas, não o desenvolvimento.

### D9 · Destino da cópia de segurança fora do servidor
* **Pergunta.** Para onde vai a cópia cifrada do banco, para sobreviver à perda da VM?
* **Alternativas.** Download periódico pelo Diogo; armazenamento gratuito em nuvem com arquivo cifrado; outro provedor gratuito de objetos.
* **Recomendação.** Arquivo cifrado com chave que só o Diogo tem, enviado para um armazenamento gratuito, com consentimento explícito das três pessoas.
* **Bloqueia.** A parte externa da T1.2. A cópia local automática não fica bloqueada.

### D10 · Prazos de sessão
* **Situação.** Parcialmente decidida pelo complemento: a sessão expira.
* **Pergunta em aberto.** Quanto tempo de inatividade até sair, e qual o prazo máximo?
* **Alternativas.** (a) 30 minutos de inatividade e 12 horas no máximo; (b) 7 dias, com opção "este aparelho é só meu" para 30 dias; (c) outro.
* **Recomendação.** (b): em uso pessoal no próprio iPhone, pedir senha toda hora faz as pessoas desistirem do app. No aparelho compartilhado, o padrão é a sessão curta.
* **Bloqueia.** Só os valores na T1.3. A estrutura (expiração no servidor, revogação ao sair) independe.

## Decisões financeiras abertas

Detalhes, exemplos numéricos e testes propostos estão em `ETAPA0_REVISAO.md`, seções 2, 3 e 7.

| ID | Pergunta | Alternativas | Recomendação técnica | Consequência |
|---|---|---|---|---|
| A1 | Compra feita no dia do fechamento entra em qual fatura? | Próxima fatura; fatura atual; configurável por cartão | Configurável por cartão, padrão "próxima", com opção de mover a compra manualmente | Opção fixa erra para alguns emissores |
| A2 | Dia de fechamento ou vencimento inexistente no mês, ou em fim de semana | Último dia do mês e sem ajuste de dia útil; ajuste para dia útil | Último dia do mês, sem ajuste na V1; o realizado usa a data real do pagamento | Projeção pode ficar 1 ou 2 dias adiantada |
| A3 | Visão mensal em caixa ou competência? | Caixa; competência; as duas em telas diferentes | Visão mensal em caixa; relatório de categorias em competência | Somar as duas na mesma tela gera dupla contagem |
| A4 | Parcelamento de fatura | Dívida separada (proposta original, **reprovada** na revisão); lançamento do próprio cartão, com a dívida só para consulta | Lançamento do cartão | Dívida separada conta as parcelas duas vezes |
| A5 / D7 | Pagamento parcial de fatura | (a) restante transferido para a próxima fatura; (b) restante fica na fatura antiga | (a), com juros e IOF como encargos do cartão | Sem uma escolha, o restante pode ser contado duas vezes |
| A6 | Avalanche com taxa desconhecida | Dívidas sem taxa no fim, com aviso; excluir da estratégia | No fim, com aviso de informação incompleta | Nenhuma taxa é inventada |
| A7 | Arredondamento | Meio para cima; meio para o par | Meio para cima, só na geração de parcelas e no cálculo de juros | O código atual exige o modo explicitamente (`round_to_cents`) |
| A8 | "Próximo recebimento" | Receita marcada como principal; 30 dias corridos se não houver | As duas: principal, com 30 dias como alternativa | Sem receita marcada, o cálculo não pode falhar |
| A9 | Pesos da estratégia Equilibrada | Fórmula da revisão 3.11; outra | Fórmula da revisão com peso 0,5 editável | Pesos aparecem na tela |
| D2 | Estorno parcial de compra parcelada | Crédito integral na fatura aberta; reduzir parcelas restantes | Crédito integral como padrão, opção de reduzir | Os dois modelos terão testes |
| D3 | Quais contas contam como "dinheiro disponível"? | Só corrente e dinheiro em espécie; também poupança; também reserva | Marcação por conta, padrão: corrente, espécie e poupança | Investimentos e reserva nunca somados sem aviso |
| D4 | Fórmula do dinheiro livre | Revisão 3.9 | Revisão 3.9 | É o número principal do Início |
| D6 | Lançamentos realizados podem ser editados? | Edição livre com histórico; só por estorno/ajuste | Edição livre com histórico de alterações (mais simples para os usuários) | Histórico obrigatório para auditoria |
| D8 | Compras em moeda estrangeira | Só em reais pelo valor da fatura, IOF como encargo; multimoeda | Só em reais na V1 | Multimoeda fica fora da V1 |

## Propostas técnicas (para revisão do Codex)

### T-ISO · Isolamento entre usuários no banco
* **Proposta.**
  1. Toda tabela financeira tem `owner_id NOT NULL` referenciando `users`.
  2. **Chaves estrangeiras compostas** `(owner_id, id)`. Exemplo: uma compra referencia `(owner_id, card_id)` do cartão. Assim o próprio banco impede que a compra de A aponte para o cartão de B, mesmo com bug na aplicação.
  3. Repositórios recebem sempre o usuário autenticado e filtram por `owner_id`. O `owner_id` nunca vem do corpo ou da URL.
  4. Registro de outro usuário responde **404**, igual a um registro inexistente, para não revelar que ele existe.
  5. **Row-Level Security** como segunda camada: a aplicação conecta com um papel sem `BYPASSRLS` e que não é dono das tabelas; cada transação define `SET LOCAL app.user_id`; políticas `USING (owner_id = current_setting('app.user_id')::uuid)`. Migrações rodam com outro papel.
  6. Testes de isolamento gerados para **todas** as rotas: para cada rota que recebe um ID, A tenta ler, editar e excluir o registro de B, e vice-versa.
* **Consequência.** Pequena complexidade extra nas migrações e na conexão. Com o pool de conexões, o `SET LOCAL` precisa ficar dentro da transação, e haverá teste que comprova isso.

### T-SES · Formato da sessão
* **Proposta.** Sessões guardadas no banco (tabela `sessions`), com identificador aleatório em cookie `HttpOnly; Secure; SameSite=Strict` e apenas o hash do identificador salvo no banco. Sem JWT.
* **Motivo.** Permite sair de verdade, expirar no servidor e encerrar a sessão de um usuário sem afetar os outros. JWT não pode ser revogado sem uma tabela, e aí perde a vantagem.

### D5 · Recorrências
* **Proposta.** Ocorrências calculadas sob demanda a partir da regra e da data original (`monthly_occurrence`, já implementada). Uma ocorrência só é gravada quando confirmada, editada ou paga. Isso atende ao requisito de não salvar projeções como se fossem lançamentos.

## Decisões tomadas

| ID | Decisão | Origem |
|---|---|---|
| D1 | Hospedagem em nuvem; servidor em casa descartado | M1 (Diogo) |
| U1 | Três usuários isolados, sem conta administrativa com acesso financeiro | M2 (Diogo) |
| U2 | Navegação: Início, Contas, Contas a pagar, Dívidas, Investimentos, Mais | M2 (Diogo) |
| U3 | Fonte-base 18 px, botões com 48 px, contraste alto | M2 (Diogo) |
| F1 | Dinheiro em centavos inteiros; `float` proibido no domínio | Auditoria 5.3, implementado na T1.1 |
| F2 | Resto da divisão em parcelas vai para a primeira parcela | Auditoria 5.3, implementado na T1.1 |
| F3 | Recorrência mensal calculada a partir da data original | Revisão 4.1, implementado na T1.1 |
| F4 | Datas civis sem hora e sem UTC; "hoje" em America/Sao_Paulo | Auditoria 5.3, implementado na T1.1 |
| F5 | No formato BR, o ponto é sempre separador de milhar (`"1.234"` = R$ 1.234,00) | T1.1. Arquivos em formato americano serão declarados na importação |
