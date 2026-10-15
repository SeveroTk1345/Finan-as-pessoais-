# Revisão da Etapa 0 · Parecer sobre `ETAPA0_AUDITORIA.md`

Data da revisão: 15/10/2026
Documento revisado: `docs/ETAPA0_AUDITORIA.md` (preservado sem alterações)
Escopo: revisão documental. Nenhum código foi criado ou alterado.

> **Aviso de independência.** Esta revisão foi feita pelo mesmo agente que escreveu a auditoria. Procurei falhas ativamente, comparando cada regra com o documento de requisitos e simulando casos numéricos. Ainda assim, isso não substitui a revisão do Codex prevista no fluxo da seção 9 dos requisitos. Recomendo que o Codex leia este parecer junto com a auditoria.

Legenda: **Aprovado** · **Aprovado com ressalvas** · **Reprovado** · **Decisão do usuário**

## Resumo dos pontos

| # | Ponto | Classificação |
|---|---|---|
| 1 | Arquitetura para iPhone/PWA | Aprovado com ressalvas |
| 2 | Livro razão evita dupla contagem | **Reprovado** (parcelamento de fatura e rotativo); demais casos aprovados com ressalvas |
| 3 | Consistência matemática (limite, parcelas, dívidas, saldos) | Aprovado com ressalvas |
| 4 | Centavos inteiros e datas | Aprovado com ressalvas |
| 5 | Tailscale como primeira opção | Aprovado com ressalvas + Decisão do usuário |
| 6 | Segurança, perda de dados, backups, dependências | Aprovado com ressalvas (backup insuficiente e tardio) |
| 7 | Decisões pendentes e as nove dúvidas | Insuficientes para Etapas 3 e 4; suficientes para T1.1 após ajustes |

---

## 1. Arquitetura · Aprovado com ressalvas

O que está correto:
* A mesma origem para frontend e `/api` resolve o problema real dos cookies entre domínios no Safari (ITP).
* O export estático do Next.js com o FastAPI como fonte de verdade é coerente com a regra "backend calcula, frontend apresenta".
* Separar `api / services / domain / db` atende à seção 7 dos requisitos.
* A política offline (só leitura, escrita bloqueada) é honesta e cumpre o requisito de não fingir edição offline.

### 1.1 Requisições de escrita sem idempotência (risco de lançamento duplicado)
* **Problema.** O cenário mais provável no iPhone é: o POST chega ao servidor e é confirmado, mas a resposta se perde (troca de Wi-Fi para 4G, VPN reconectando). O app mostra erro, o usuário toca em "Salvar" de novo e o lançamento fica duplicado. A auditoria trata "sem conexão", mas não "conexão que cai no meio".
* **Alternativa.** O cliente gera uma `Idempotency-Key` (UUID) por formulário e a envia em todo POST de criação. O backend guarda as chaves com o resultado por 24h, em tabela própria e dentro da mesma transação do lançamento. Reenvio com a mesma chave devolve o resultado original.
* **Teste.** Teste de integração: enviar o mesmo POST duas vezes com a mesma chave e verificar que existe 1 registro e que as duas respostas são idênticas. Com chaves diferentes, devem existir 2 registros. Teste E2E com Playwright: interromper a rota depois do commit (`route.abort` na resposta) e reenviar.

### 1.2 Detecção de "offline" no iOS
* **Problema.** No iOS, `navigator.onLine` é pouco confiável e, com Tailscale, o aparelho pode estar "online" com o servidor inacessível (VPN desligada, PC desligado).
* **Alternativa.** Basear o estado em `GET /api/health` com timeout curto, chamado ao abrir o app, ao voltar do segundo plano (`visibilitychange`) e depois de qualquer falha de rede. O botão "Salvar" fica habilitado só com o último health check bem sucedido.
* **Teste.** Playwright com `context.setOffline(true)` e com bloqueio só da rota `/api/*` (simula servidor desligado com internet ativa). Nos dois casos os formulários ficam desabilitados e aparece a faixa de dados em cache.

### 1.3 Proteção CSRF não especificada
* **Problema.** Autenticação por cookie exige defesa contra CSRF. `SameSite=Strict` reduz o risco, mas sozinho não é defesa em profundidade.
* **Alternativa.** Em métodos que alteram estado, o backend rejeita requisições cujo `Origin` não seja exatamente a origem configurada. Exigir também o cabeçalho `X-Requested-With`, que não pode ser enviado por formulário HTML entre sites.
* **Teste.** Teste de API: POST com `Origin` diferente deve dar 403; POST sem o cabeçalho deve dar 403; POST válido deve dar 201.

### 1.4 Cookies do PWA instalado são separados do Safari
* **Problema.** No iOS, o app aberto pela Tela de Início tem armazenamento e cookies separados do Safari. Quem fizer login no Safari e depois instalar o app vai precisar fazer login de novo. Isso não é bug, mas precisa estar documentado, senão vai parecer falha.
* **Alternativa.** Documentar no guia de instalação. A duração da sessão é **decisão do usuário** (ver D10).
* **Teste.** Roteiro manual da T6.1: login no Safari, instalação, abertura pela Tela de Início e conferência de que pede login; fechar e reabrir o app e conferir que a sessão foi mantida.

### 1.5 Rotas dinâmicas no export estático e compatibilidade do service worker
* **Problema.** O export estático não aceita rotas como `/cartoes/[id]` sem `generateStaticParams`. Além disso, a integração `@serwist/next` historicamente depende do webpack. A compatibilidade com o build padrão do Next 16 não foi verificada; a auditoria assumiu.
* **Alternativa.** Usar parâmetros de consulta (`/cartoes?id=...`) em vez de segmentos dinâmicos. Validar o Serwist na T1.5. Se for incompatível, gerar o service worker depois do build (injeção de manifesto via CLI) ou escrevê-lo à mão; ele é pequeno porque a política é só leitura.
* **Teste.** Na T1.1, o `next build` com `output: 'export'` precisa passar. Na T1.5, conferir que `out/sw.js` existe e que a lista de pré-cache contém os arquivos do build.

### 1.6 Edição concorrente em dois dispositivos
* **Problema.** O uso será no iPhone e no computador. Editar o mesmo registro nos dois sobrescreve silenciosamente uma das edições.
* **Alternativa.** Coluna `version` em registros editáveis (bloqueio otimista). Um PUT com versão antiga recebe 409 e a interface pede para recarregar.
* **Teste.** Dois PUTs com a mesma versão: o primeiro dá 200 e o segundo dá 409.

---

## 2. Livro razão e dupla contagem · Reprovado em dois casos

Conferência caso a caso:

| Caso | Resultado | Comentário |
|---|---|---|
| Transferência | Aprovado | Duas linhas com a mesma origem, excluídas do resultado; soma líquida no consolidado = 0 |
| Compra parcelada | Aprovado com ressalva | Origem única correta; falta compra com juros (ver 3.3) |
| Fatura como agrupamento | Aprovado | Não cria valor novo |
| Pagamento de fatura | Aprovado com ressalva | "Liquidação" correta; falta definir como a visão mensal usa previsto vs realizado (ver 2.3) |
| Estorno | Aprovado com ressalva | Falta crédito maior que a fatura e estorno parcial (ver 2.4) |
| Cancelamento | Reprovado como escrito | Regra incompleta (ver 2.5) |
| Parcelamento de fatura (A4) | **Reprovado** | Gera dupla contagem (ver 2.1) |
| Pagamento parcial / rotativo (A5) | **Reprovado** | Saldo pode ser contado duas vezes (ver 2.2) |
| Empréstimo recebido | Ausente | Pode virar receita indevidamente (ver 2.6) |
| Reembolso de despesa em conta | Ausente | Pode inflar receitas (ver 2.7) |

### 2.1 Parcelamento de fatura como "dívida nova" gera dupla contagem
* **Problema.** No parcelamento de fatura dos emissores brasileiros, as parcelas do acordo **são cobradas nas faturas seguintes do próprio cartão** e o saldo parcelado continua ocupando limite. Com a regra A4:
  * Fatura de R$ 1.000,00, entrada de R$ 200,00 e R$ 800,00 parcelados em 10× R$ 100,00.
  * O módulo de dívidas espera 10 pagamentos de R$ 100,00 (`debt_payment`).
  * As faturas seguintes também trazem R$ 100,00 cada, pagos via `card_payment`.
  * Resultado: R$ 1.000,00 de saída prevista contada duas vezes nas projeções, e limite disponível superestimado em R$ 800,00, porque a fatura original aparece como "liquidada".
* **Alternativa.** Criar o parcelamento de fatura como **origem do próprio cartão** (`card_invoice_financing`):
  1. A fatura original recebe um crédito "transferido para parcelamento" de R$ 800,00, sem saída de caixa.
  2. São geradas 10 parcelas de R$ 100,00 nas faturas futuras, como as de uma compra.
  3. A diferença entre o total parcelado (R$ 1.000,00) e o principal (R$ 800,00), ou seja R$ 200,00, é classificada como **juros/encargos**, não como consumo novo.
  4. A tela de Dívidas **exibe** o acordo como visão derivada, somente leitura, sem obrigação própria.
* **Teste.** Teste de regressão com os números acima. Esperado:
  * limite comprometido logo após o acordo = R$ 1.000,00 (10 parcelas futuras);
  * saída de caixa prevista nos 10 meses = R$ 1.000,00 no total (uma vez só);
  * consumo por categoria = R$ 1.000,00 da compra original + R$ 200,00 de encargos;
  * soma das obrigações no Dashboard = soma das faturas, sem parcela extra de dívida.

### 2.2 Pagamento parcial e rotativo indefinidos
* **Problema.** A5 diz que "o saldo restante fica pendente", mas não diz **onde**. Se o restante continuar como pendência na fatura antiga **e** o emissor o lançar como "saldo anterior" na fatura seguinte (prática comum), o valor é contado duas vezes.
* **Alternativa.** Escolher um único modelo:
  * **(a) recomendado:** o restante é transferido para a próxima fatura por uma linha `carryover` de mesmo valor. A fatura antiga fica "parcialmente paga · saldo transferido" com pendência zero. Juros e IOF do rotativo entram como lançamentos de encargo do cartão (ver 3.4).
  * **(b)** o restante fica só na fatura antiga e nada é lançado na seguinte.
* **Teste.** Fatura de R$ 500,00 com pagamento de R$ 300,00. Esperado: total de pendências do cartão = R$ 200,00 (não R$ 400,00); limite comprometido = parcelas − pagamentos; ao somar as faturas, a linha `carryover` se anula com o crédito de origem.

### 2.3 Visão mensal em caixa sem definição de previsto vs realizado para cartão
* **Problema.** "Cartão entra pelo vencimento da fatura" não diz se o mês mostra o **total da fatura** ou os **pagamentos**. Somar os dois duplica.
* **Alternativa.** Previsto do mês = total das faturas com vencimento no mês. Realizado do mês = soma das linhas `card_payment` no mês. Saldo projetado = realizado + (previsto ainda não realizado), nunca previsto + realizado.
* **Teste.** Fatura de R$ 800,00 com vencimento em 10/11/2026 e pagamento integral em 08/11/2026. Na visão de novembro: previsto 800, realizado 800 e impacto no saldo projetado de 800, não 1.600.

### 2.4 Estornos
* **Problema.** "Crédito na fatura aberta" não cobre:
  * crédito maior que o total da fatura aberta;
  * estorno parcial de compra parcelada (o emissor pode creditar tudo de uma vez ou reduzir as parcelas restantes);
  * estorno de compra paga em conta.
* **Alternativa.** O crédito excedente é transportado para a próxima fatura. O total da fatura pode ficar negativo e a interface mostra "crédito de R$ X". Para estorno parcial de parcelada, o padrão é crédito integral na fatura aberta, com opção "reduzir parcelas restantes". Qual dos dois vira padrão é **decisão do usuário** (D2).
* **Teste.** Compra de R$ 300,00 em 3×, estorno total depois de a 1ª parcela (R$ 100,00) estar em fatura fechada. Os dois modelos são testados separadamente:
  * **Crédito integral:** a fatura aberta recebe crédito de R$ 300,00 e as parcelas 2 e 3 continuam. Comprometido = 300 − 300 = 0. A fatura aberta fica em −R$ 200,00 (parcela 2 de R$ 100,00 menos o crédito) e o crédito é absorvido pela parcela 3 na fatura seguinte, sobrando R$ 100,00 de crédito, que corresponde à parcela 1 já cobrada.
  * **Redução das parcelas:** as parcelas 2 e 3 são canceladas e a fatura aberta recebe crédito de R$ 100,00, referente à parcela 1. Comprometido = 100 − 100 = 0.
  * Nos dois modelos, o consumo líquido da compra é 0 e o saldo credor final é de R$ 100,00.

### 2.5 Cancelamento incompleto
* **Problema.** "Cancela parcelas futuras ainda não faturadas" ignora as parcelas **já faturadas** de uma compra cancelada. Com essa regra, o usuário fica cobrando a si mesmo por algo que o lojista devolveu.
* **Alternativa.** O cancelamento faz duas coisas: (1) cancela parcelas não faturadas e (2) gera crédito de estorno no valor das parcelas já faturadas, na fatura aberta. Um cancelamento sem devolução (por exemplo, uma disputa perdida) não existe: aí é só "estorno parcial".
* **Teste.** Compra de R$ 600,00 em 6×, cancelada depois de 2 parcelas faturadas. Esperado: 4 parcelas canceladas, crédito de R$ 200,00, consumo líquido da compra = 0 e limite comprometido = 0 depois da fatura atual.

### 2.6 Entrada de empréstimo não pode ser receita
* **Problema.** A auditoria cobre pagamentos de dívida, mas não o dinheiro **recebido** de um empréstimo. Se for lançado como receita, a renda fica inflada e o "% da renda comprometida" sai errado.
* **Alternativa.** Linha de razão `origin_type=debt_disbursement`, classificada como "entrada de financiamento", fora das receitas.
* **Teste.** Empréstimo de R$ 5.000,00 creditado em conta: saldo da conta +5.000, receitas do mês inalteradas, saldo devedor +5.000.

### 2.7 Reembolso de despesa
* **Problema.** O requisito 4.7 cita reembolsos, mas a auditoria não os modela. Um amigo devolvendo R$ 50,00 de um jantar pago pelo usuário não é receita.
* **Alternativa.** Linha `origin_type=refund` com vínculo opcional à despesa original; nos relatórios por categoria ela reduz a categoria original.
* **Teste.** Despesa de R$ 200,00 em "Alimentação" e reembolso de R$ 50,00: categoria = R$ 150,00, receitas inalteradas, saldo da conta −150.

### 2.8 Ajustes de saldo e "valores sempre positivos"
* **Problema.** A regra "valor positivo, direção pelo tipo" não funciona para ajuste de saldo, que pode ser nos dois sentidos.
* **Alternativa.** Campo `direction` (`in`/`out`) obrigatório para `adjustment`, com valor sempre positivo. Ajustes ficam fora de receitas e despesas.
* **Teste.** Ajuste de saída de R$ 10,00: saldo −10, receitas e despesas inalteradas; valor negativo rejeitado com 422.

---

## 3. Consistência matemática · Aprovado com ressalvas

A fórmula central está correta: **comprometido = Σ parcelas ativas − Σ pagamentos** conta cada centavo uma única vez, seja a fatura aberta, fechada ou futura, porque a fatura é só um agrupamento. Verifiquei com um exemplo: compra de R$ 1.200,00 em 12×, duas faturas pagas. Comprometido = 1.200 − 200 = 1.000, igual à soma das 10 parcelas restantes. ✔

### 3.1 Datas de fechamento e vencimento ambíguas
* **Problema.**
  * Não está definido como uma fatura é identificada. Com fechamento no dia 25 e vencimento no dia 5, o vencimento cai no mês seguinte.
  * A alteração do dia de fechamento pelo usuário não pode realocar compras antigas.
* **Alternativa.** A fatura é identificada pelo **mês de vencimento**. Se o dia de vencimento for menor ou igual ao de fechamento, o vencimento é no mês seguinte ao fechamento. A atribuição parcela→fatura é **gravada** na criação. Mudanças de ciclo valem a partir de uma data de vigência. Também deve ser possível mover manualmente uma compra para outra fatura, porque a data de processamento do emissor pode diferir da data da compra.
* **Teste.** Cartão com fechamento 25 e vencimento 5:
  * compra em 24/12/2026 → fatura com vencimento em 05/01/2027;
  * compra em 25/12/2026 → vencimento em 05/02/2027 (aplicando A1).
  * Mudar o fechamento para 20 não altera as faturas existentes.

### 3.2 Status de fatura incompletos
* **Problema.** Faltam os status "futura" (parcelas de meses ainda não abertos) e "vencida" (fechada, sem pagamento integral, com vencimento passado).
* **Alternativa.** Status derivados em ordem de precedência: futura → aberta → fechada → vencida → parcialmente paga → paga → com crédito.
* **Teste.** Tabela parametrizada com `hoje` injetado (relógio da T1.1) para cada status.

### 3.3 Compra parcelada com juros
* **Problema.** `split_installments(total, n)` pressupõe parcelas sem juros. Em compras "parceladas com juros", o total cobrado = n × parcela informada, e esse total é maior que o preço.
* **Alternativa.** O formulário aceita "valor total" **ou** "valor da parcela". No segundo caso, a diferença entre total cobrado e preço à vista vai para "juros/encargos".
* **Teste.** Preço de R$ 1.000,00 em 10× R$ 110,00: limite comprometido = R$ 1.100,00, consumo = R$ 1.000,00 e encargos = R$ 100,00.

### 3.4 Lançamentos do cartão que não são compras
* **Problema.** Anuidade, IOF, juros do rotativo e tarifas não têm origem no modelo. Sem isso, a fatura do app não bate com a do banco.
* **Alternativa.** Origem `card_charge` com tipo (anuidade, IOF, juros, tarifa, outro), à vista, atribuída a uma fatura.
* **Teste.** Fatura com compras de R$ 500,00 + IOF de R$ 3,50: total R$ 503,50; comprometido inclui o IOF.

### 3.5 Pagamento acima da fatura (saldo credor)
* **Problema.** Se os pagamentos superarem as parcelas, o comprometido fica negativo e o limite disponível passa do limite total.
* **Alternativa.** Guardar o crédito como saldo credor do cartão, abatido da próxima fatura. Exibir o limite disponível como `min(limite total, limite total − comprometido)` e mostrar o crédito separadamente.
* **Teste.** Fatura de R$ 100,00 paga com R$ 150,00: crédito de R$ 50,00, disponível = limite total, próxima fatura reduzida em R$ 50,00.

### 3.6 Saldo devedor com duas fontes de verdade
* **Problema.** A dívida tem "valor original", "saldo devedor atual" e "histórico de pagamentos". Se o saldo atual for editável **e** também calculado a partir dos pagamentos, os dois divergem.
* **Alternativa.** O saldo é **ancorado**: `saldo_informado` em DD/MM/AAAA + movimentos posteriores (pagamentos de principal, encargos lançados). A renegociação cria uma nova âncora e encerra a anterior, sem apagar o histórico.
* **Teste.** Âncora de R$ 10.000,00 em 01/10/2026 e pagamento de principal de R$ 500,00 em 10/10/2026: saldo = R$ 9.500,00. Renegociação para R$ 9.800,00 em 15/10/2026: saldo = R$ 9.800,00 e histórico preservado.

### 3.7 Pagamento de dívida: principal vs juros
* **Problema.** Na visão de caixa, o pagamento inteiro é saída. Para o saldo devedor, só o principal reduz a dívida. A auditoria não diz como dividir, e sem taxa conhecida não é possível calcular.
* **Alternativa.** O pagamento tem `principal_cents` e `interest_cents` opcionais. Se não forem informados e a taxa for desconhecida, o valor inteiro abate o saldo e a dívida recebe a marca "saldo estimado". Nada é inventado.
* **Teste.** Pagamento de R$ 500,00 com R$ 50,00 de juros informados: saldo −450; caixa −500.

### 3.8 Conversão de taxas
* **Problema.** A auditoria guarda o período da taxa, mas não fixa a conversão. Usar 12%/12 = 1% ao mês está **errado** para juros compostos.
* **Alternativa.** Taxa mensal equivalente = (1 + a)^(1/12) − 1. Taxa real (Fisher) = (1 + nominal)/(1 + inflação) − 1, nunca nominal − inflação.
* **Teste.** 12% a.a. ≈ 0,9489% a.m.; nominal de 10% com inflação de 4% ≈ 5,7692% real (com `Decimal` e tolerância definida).

### 3.9 "Dinheiro livre estimado" sem fórmula
* **Problema.** É o número mais visível do Dashboard e não tem definição. Também não está definido quais tipos de conta contam como "disponível" (corrente, carteira, poupança, reserva, investimento).
* **Alternativa (proposta para o usuário confirmar):**
  `dinheiro livre = saldo das contas marcadas como disponíveis − obrigações não realizadas com vencimento até o próximo recebimento (despesas previstas, faturas, parcelas de dívida, **incluindo atrasadas de meses anteriores**)`.
  Receitas previstas não entram. Limite de cartão não entra.
* **Teste.** Saldo de 2.000, fatura de 800 a vencer, conta atrasada de 150 do mês anterior, salário previsto de 3.000 e limite livre de 5.000: dinheiro livre = 1.050.

### 3.10 Obrigações atrasadas somem das projeções
* **Problema.** Se a visão mensal só olha o mês, uma conta de setembro não paga desaparece em outubro.
* **Alternativa.** Toda visão futura inclui uma linha "atrasados não pagos" com as pendências anteriores.
* **Teste.** Despesa prevista de 20/09/2026 não paga: aparece em "atrasados" na visão de outubro e entra no dinheiro livre.

### 3.11 Percentual da renda comprometida e estratégia "Equilibrada"
* **Problema.** Faltam o denominador do percentual (receita prevista ou realizada?) e a normalização dos pesos da A9.
* **Alternativa.** Percentual = obrigações previstas do mês ÷ receitas previstas do mês, com receitas realizadas também exibidas. Para a Equilibrada: `score = w × (taxa_mensal / maior_taxa_conhecida) + (1 − w) × (parcela / saldo) / max(parcela / saldo)`. Dívidas sem taxa ficam só com o segundo termo e recebem aviso.
* **Teste.** Três dívidas com valores fixos e ordem esperada calculada à mão para w = 0, 0,5 e 1.

---

## 4. Centavos inteiros e datas · Aprovado com ressalvas

Correto: `BIGINT` em centavos, `Decimal` para juros, `DATE` sem hora, "hoje" em São Paulo, `clamp_day` para os dias 29, 30 e 31, teste de propriedade na divisão de parcelas. O exemplo da T1.1 está certo: 02:00 UTC de 15/10/2026 corresponde a 23:00 do dia 14/10 em São Paulo.

### 4.1 Recorrência mensal encadeada perde o dia
* **Problema.** Aplicar `add_months` em cadeia desloca o dia: 31/01 → 28/02 → 28/03 → 28/04 …
* **Alternativa.** Ocorrência k = `âncora + k meses`, sempre calculada a partir da data original.
* **Teste.** Âncora 31/01/2026: ocorrências 28/02, 31/03, 30/04 e 31/05. Em ano bissexto, 29/02/2028.

### 4.2 Bug clássico de data no JavaScript
* **Problema.** `new Date("2026-10-15")` é interpretado como meia noite **UTC**, que no Brasil é 21:00 do dia 14. A tela mostraria 14/10/2026.
* **Alternativa.** No frontend, datas financeiras trafegam e são formatadas como texto `AAAA-MM-DD` → `DD/MM/AAAA`, sem objeto `Date`. Proibir `new Date(string)` por regra de lint.
* **Teste.** `formatDate("2026-10-15") === "15/10/2026"` executado com `TZ=America/Sao_Paulo` e com `TZ=UTC`.

### 4.3 Fuso dentro do banco e da imagem Docker
* **Problema.**
  * `CURRENT_DATE` e `now()` no PostgreSQL usam o fuso da sessão, que costuma ser UTC no Docker.
  * Imagens Python "slim" podem não ter a base de fusos do sistema, e aí `ZoneInfo("America/Sao_Paulo")` falha.
* **Alternativa.** Proibir `CURRENT_DATE` em consultas de negócio; a data "hoje" sempre vem do relógio da aplicação. Adicionar o pacote `tzdata` às dependências Python.
* **Teste.** Teste com o relógio injetado em 15/10/2026 02:00 UTC e a sessão do banco em UTC: o lançamento criado como "hoje" recebe 14/10/2026.

### 4.4 Entrada de valores no iPhone
* **Problema.** `inputmode="decimal"` exibe vírgula ou ponto conforme a região do aparelho, e "1.234" é ambíguo (mil duzentos e trinta e quatro, ou um vírgula duzentos e trinta e quatro?).
* **Alternativa.** Campo com **máscara de centavos**, como nos apps de banco: o usuário digita só números (`123456` → R$ 1.234,56), com `inputmode="numeric"`. Some a ambiguidade e o teclado é o numérico grande do iOS. `parse_brl` continua existindo para CSV, com formato declarado no mapeamento.
* **Teste.** Componente: digitar "1", "2", "3", "4", "5", "6" exibe R$ 1.234,56 e envia 123456; apagar um dígito volta a R$ 123,45.

### 4.5 Formatos de importação CSV
* **Problema.** Exportações de bancos usam `R$ 1.234,56`, `-1.234,56`, `1,234.56`, `(1.234,56)` e sinal no final.
* **Alternativa.** No mapeamento de colunas, o usuário escolhe o formato numérico (BR ou US) e a convenção de sinal. Linha ambígua vai para "requer revisão", nunca é adivinhada.
* **Teste.** Tabela parametrizada com cada formato e o valor esperado em centavos; entradas ambíguas retornam erro de validação.

### 4.6 Vencimento em fim de semana atravessando o mês
* **Problema.** A2 não ajusta para dia útil. Um vencimento no sábado 31/10/2026 pode ser pago na segunda 02/11/2026, e a saída real cai em outro mês.
* **Alternativa.** Aceitar A2 na V1, mas o realizado sempre usa a data real do pagamento; a diferença entre previsto e realizado aparece na visão mensal, não é escondida.
* **Teste.** Fatura com vencimento em 31/10/2026 paga em 02/11/2026: previsto em outubro, realizado em novembro, sem duplicação no consolidado dos dois meses.

### 4.7 Pontos de arredondamento
* **Problema.** A7 define a regra (meio para cima), mas não **onde** arredondar. Arredondar dentro de somas gera diferenças acumuladas.
* **Alternativa.** Arredondar só em três pontos: geração de parcelas, cálculo de juros por período e conversão de entrada. Somas são sempre de inteiros. Em tabelas de amortização, a última parcela absorve o resíduo.
* **Teste.** Hypothesis: para qualquer total e qualquer n entre 1 e 48, Σ parcelas == total; em tabelas Price, Σ principal == valor financiado.

---

## 5. Hospedagem com Tailscale · Aprovado com ressalvas + Decisão do usuário

Avaliação comparativa:

| Critério | Tailscale + servidor em casa | VM gratuita na nuvem | Túnel público (ex.: Cloudflare Tunnel) |
|---|---|---|---|
| Custo | R$ 0 | R$ 0 com cartão para verificação | R$ 0 |
| Privacidade | Melhor: TLS termina na sua máquina; o tráfego é cifrado de ponta a ponta | Dados em terceiro | O provedor termina o TLS e vê o conteúdo |
| Exposição à internet | Nenhuma | Pública | Pública |
| Disponibilidade | Depende do PC ligado | 24h, sem garantia de permanência | Depende do PC ligado |
| Manutenção | Baixa | Média (SO, firewall, atualizações) | Baixa |
| Atrito no iPhone | App Tailscale precisa estar conectado | Nenhum | Nenhum |

Conclusão: é a melhor primeira opção **em segurança e privacidade**, mas não em disponibilidade. Ressalvas:

### 5.1 Depende de uma máquina sempre ligada
* **Problema.** O app é usado principalmente no iPhone. Sem um computador ligado em casa, o usuário não registra gastos na rua. A auditoria não perguntou se essa máquina existe.
* **Alternativa.** **Decisão do usuário** (D1): (a) PC ou notebook que já fica ligado, (b) mini computador barato ou Raspberry Pi (custo de hardware, não de uso), (c) VM gratuita na nuvem aceitando o risco de terceiros.
* **Teste.** T1.6: com o PC desligado, abrir o PWA no iPhone; deve mostrar dados em cache e bloquear a edição com mensagem clara.

### 5.2 Nome do tailnet em logs públicos de certificados
* **Problema.** Ao ativar HTTPS no Tailscale, o nome da máquina e do tailnet aparece em logs públicos de transparência de certificados. Não vaza dados financeiros, mas revela que o serviço existe.
* **Alternativa.** Usar nome de máquina neutro (não "financas-diogo") e documentar o comportamento.
* **Teste.** Revisão manual do nome configurado na T1.6.

### 5.3 VPN desconectada no iPhone
* **Problema.** Se o Tailscale estiver desligado, o app parece "quebrado".
* **Alternativa.** Ativar a VPN sob demanda no app Tailscale do iOS e mostrar uma mensagem específica: "Servidor inacessível. Verifique se o Tailscale está conectado."
* **Teste.** Desligar a VPN e abrir o app: aparece a mensagem correta, não um erro genérico.

### 5.4 Dependência externa da Tailscale
* **Problema.** O plano gratuito e o servidor de coordenação são de terceiros. Se a empresa mudar o plano, o acesso remoto cai (os dados não se perdem).
* **Alternativa.** Documentar o plano B (VM gratuita ou acesso só na rede local). A arquitetura com Compose + Caddy é portátil e não depende da Tailscale no código.
* **Teste.** O app roda e passa no smoke test em `http://localhost` sem Tailscale.

---

## 6. Segurança, perda de dados e dependências · Aprovado com ressalvas

### 6.1 Backup insuficiente e tardio (prioridade máxima)
* **Problema.**
  * O backup só chega na T5.1, mas dados reais começam a ser lançados na Etapa 2.
  * O plano prevê apenas exportação manual em JSON.
  * Tudo fica em um único disco em casa.
* **Alternativa.**
  1. Na T1.2: `pg_dump` automático diário com rotação (por exemplo, 7 diários e 4 semanais) em um volume separado.
  2. Cópia fora da máquina **cifrada** com uma chave que só o usuário tem. O destino é **decisão do usuário** (D9): pendrive, outro computador ou serviço de nuvem com consentimento explícito.
  3. Backup automático **antes** de toda restauração e migração.
  4. JSON com `schema_version` e checksum SHA-256; restauração em uma única transação, que é desfeita por inteiro em caso de erro.
* **Teste.**
  * Teste automatizado: popular o banco → dump → restaurar em banco temporário → comparar contagens e somas por tabela.
  * Restaurar JSON corrompido: falha sem alterar nada.
  * Restaurar JSON de versão futura: rejeitado com mensagem.

### 6.2 Erro do próprio usuário é a perda de dados mais provável
* **Problema.** Excluir um lançamento por engano não tem volta, e a auditoria não prevê histórico.
* **Alternativa.** Exclusão lógica (`deleted_at`) em registros financeiros, com "Desfazer" por alguns segundos e uma tabela de auditoria (quem, quando, valor antes e depois). Exclusão definitiva só por limpeza explícita.
* **Teste.** Excluir e restaurar um lançamento: saldo volta ao valor anterior; o registro de auditoria contém os dois estados.

### 6.3 Credenciais iniciais e recuperação de senha
* **Problema.** Não está definido como criar o primeiro usuário nem como recuperar a senha.
* **Alternativa.** Comando de linha `python -m app.cli create-user` e `reset-password` executados no servidor. O app recusa iniciar sem `SESSION_SECRET` forte. Não existe usuário padrão.
* **Teste.** Iniciar sem segredo dá erro de configuração; o login falha antes do `create-user`.

### 6.4 Injeção de fórmula na exportação CSV
* **Problema.** Você usa Excel. Uma descrição como `=HYPERLINK(...)` vira fórmula ativa ao abrir o CSV.
* **Alternativa.** Na exportação, prefixar com `'` os campos de texto que comecem com `=`, `+`, `-`, `@`, tab ou retorno de carro. Campos numéricos não são alterados.
* **Teste.** Descrição `=1+1` exportada como `'=1+1`; valor `-150,00` exportado sem prefixo.

### 6.5 Cache no aparelho depois de expirar a sessão
* **Problema.** Com a sessão expirada, os dados em cache continuam legíveis offline no iPhone. A proteção real passa a ser o bloqueio do aparelho.
* **Alternativa.** O logout limpa caches (como previsto) e a expiração da sessão também limpa na próxima abertura com conexão. O risco residual deve ser documentado e aceito pelo usuário (D10).
* **Teste.** E2E: login → navegar → logout → `caches.keys()` vazio e IndexedDB vazio.

### 6.6 Itens de segurança não citados
* **Problema.** A auditoria não cita: cabeçalhos de segurança, limite de tamanho de upload, travamento de versões das dependências e auditoria delas, e o comando `docker compose down -v`, que apaga o volume do banco.
* **Alternativa.**
  * Cabeçalhos de segurança via Caddy: CSP restrita, `X-Content-Type-Options`, `frame-ancestors 'none'`, HSTS.
  * Limite de upload (por exemplo, 5 MB para CSV e JSON).
  * Arquivos de lock (`uv.lock`, `pnpm-lock.yaml`) e `pip-audit` e `pnpm audit` no `make lint`.
  * Imagens Docker fixadas por versão.
  * Fontes servidas pelo próprio app, sem CDN.
  * Aviso em destaque no README sobre `docker compose down -v`.
* **Teste.** Teste de integração com os cabeçalhos esperados; upload de 6 MB rejeitado com 413; auditoria de dependências registrada no `REGISTRO_TESTES.md`.

### 6.7 Dados em logs
* **Problema.** Logs de acesso registram URLs completas.
* **Alternativa.** Nenhum dado financeiro em query string (filtros por mês tudo bem; descrições e valores não). O log da aplicação registra só IDs, nunca valores ou descrições.
* **Teste.** Teste que captura os logs de uma criação de lançamento e verifica que não contêm a descrição nem o valor.

---

## 7. Decisões pendentes · Insuficientes para Etapas 3 e 4

Avaliação das nove dúvidas:

| # | Avaliação | Situação |
|---|---|---|
| A1 Compra no dia do fechamento | Adequada, com ressalva: permitir mover a compra manualmente para outra fatura | Decisão do usuário (padrão proposto razoável) |
| A2 Dia inexistente e fim de semana | Adequada para V1 com a regra 4.6 | Decisão do usuário |
| A3 Caixa vs competência | Bem formulada, mas depende de preferência | **Decisão do usuário** |
| A4 Parcelamento de fatura | **Reprovada**: gera dupla contagem | Substituir pela alternativa 2.1 |
| A5 Pagamento parcial | **Reprovada**: subespecificada | Escolher modelo (a) ou (b) da seção 2.2 |
| A6 Avalanche sem taxa | Adequada | Decisão do usuário (padrão razoável) |
| A7 Arredondamento | Incompleta | Acrescentar os pontos de arredondamento (4.7) |
| A8 Próximo recebimento | Incompleta: falta fallback se nenhuma receita for marcada como principal | Proposta: 30 dias corridos. Decisão do usuário |
| A9 Equilibrada | Incompleta: normalização indefinida | Adotar a fórmula de 3.11 ou outra escolhida |

Decisões que **faltam** na auditoria e dependem do usuário:

| # | Decisão |
|---|---|
| D1 | Onde o servidor vai rodar (PC sempre ligado, mini PC ou VM na nuvem) |
| D2 | Estorno parcial de parcelada: crédito integral ou redução das parcelas restantes |
| D3 | Quais tipos de conta contam como "dinheiro disponível" (reserva e investimentos entram?) |
| D4 | Fórmula do dinheiro livre (proposta em 3.9) |
| D5 | Recorrências: ocorrências virtuais geradas sob demanda e materializadas só ao confirmar ou editar (recomendado, atende ao requisito 4.8) |
| D6 | Lançamentos já realizados podem ser editados livremente ou só via estorno/ajuste |
| D7 | Rotativo: modelo (a) ou (b) da seção 2.2 |
| D8 | Compras internacionais: registro só em BRL pelo valor da fatura, com IOF como encargo (recomendado para V1) |
| D9 | Destino da cópia de backup fora da máquina |
| D10 | Duração da sessão e aceitação do risco de cache no aparelho |

**A T1.1 não depende de nenhuma dessas decisões**, porque trata só de esqueleto, dinheiro e datas. Ela pode começar assim que os ajustes de prioridade alta abaixo forem incorporados ao seu escopo. As Etapas 3 e 4 não devem começar sem A4, A5, D2, D3, D4 e D7 resolvidas.

---

## Parecer final

A auditoria acerta no essencial: livro razão de caixa, fatura como agrupamento, centavos inteiros, mesma origem para PWA e API, política offline honesta e prioridade à privacidade. A fórmula de limite comprometido está matematicamente correta.

Ela **não pode ser aprovada sem alterações** por quatro motivos:
1. A regra A4 (parcelamento de fatura como dívida) produz dupla contagem nas projeções e superestima o limite.
2. A regra A5 (pagamento parcial) e o cancelamento estão subespecificados a ponto de permitir dupla contagem ou cobrança indevida.
3. O backup chega tarde demais e em um único disco, quando os dados reais já estão sendo lançados.
4. Faltam idempotência nas escritas, que é o risco mais provável de lançamento duplicado no iPhone, e a fórmula do dinheiro livre, que é o número principal do Dashboard.

**Parecer: aprovada com ressalvas para iniciar a T1.1 após os ajustes de prioridade alta; reprovada para as Etapas 3 e 4 até a resolução de A4, A5 e das decisões D1 a D10.**

## Alterações priorizadas antes da T1.1

**Prioridade alta (alteram o escopo da T1.1 ou de tarefas da Etapa 1)**
1. Incluir na T1.1 a recorrência por âncora (`occurrence(anchor, k)`) e o teste 31/01 → 28/02 → 31/03 (4.1).
2. Incluir na T1.1 a formatação de datas no frontend sem `new Date(string)`, com teste em dois fusos e regra de lint (4.2).
3. Incluir na T1.1 a dependência `tzdata` e o relógio da aplicação como única fonte de "hoje" (4.3).
4. Mover para a T1.2 o backup automático com `pg_dump`, a rotação e o teste de restauração (6.1).
5. Acrescentar idempotência de escrita e verificação de `Origin` (CSRF) à T1.3 (1.1 e 1.3).
6. Registrar na auditoria que A4 está reprovada e A5 é insuficiente, com as alternativas 2.1 e 2.2, sem adotá-las até a aprovação do usuário.

**Prioridade média (antes da Etapa 2)**
7. Exclusão lógica e trilha de auditoria nos registros financeiros (6.2).
8. Bloqueio otimista com coluna `version` (1.6).
9. Health check como base do estado offline (1.2).
10. Campo de valor com máscara de centavos (4.4).
11. Origens `debt_disbursement`, `refund` e `adjustment` com direção (2.6 a 2.8).
12. Comando de criação de usuário, sem credenciais padrão (6.3).

**Prioridade para Etapas 3 e 4 (depois das decisões do usuário)**
13. Respostas a D1 a D10 e às dúvidas reformuladas A1 a A9.
14. Modelo de fatura: identificação pelo vencimento, atribuição gravada, status completos, `card_charge`, saldo credor (3.1 a 3.5).
15. Saldo devedor ancorado e divisão entre principal e juros (3.6 e 3.7).
16. Fórmulas de conversão de taxa, taxa real, dinheiro livre, renda comprometida e Equilibrada (3.8 a 3.11).
17. Cabeçalhos de segurança, limites de upload, auditoria de dependências, proteção contra injeção de fórmula em CSV (6.4 e 6.6).

## Próximo passo sugerido
1. Diogo responde D1 a D10 e confirma ou ajusta as alternativas de A4 e A5.
2. Codex revisa este parecer e a auditoria.
3. A auditoria recebe uma versão 2 com as decisões registradas em `docs/DECISOES.md`.
4. A T1.1 começa com o escopo ampliado dos itens 1 a 3.
