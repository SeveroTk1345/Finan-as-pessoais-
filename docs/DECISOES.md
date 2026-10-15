# Decisões

Versão 4, de 15/10/2026 (inclui decisões tomadas durante a implementação). A versão anterior está no histórico do Git. As mudanças de escopo que motivaram cada alteração estão em `MUDANCAS_DE_ESCOPO.md`.

Origem: **Diogo** (decidido pelo dono do projeto) · **M3** (decidido pelo Claude com a autonomia dada na missão M3, pela alternativa mais segura) · **Técnica**.

Qualquer decisão M3 pode ser revista pelo Diogo. Mudar uma decisão financeira exige ajustar os testes correspondentes.

## 1. Definições financeiras (como cada número é calculado)

| Termo na tela | Definição |
|---|---|
| **Saldo da conta** | Saldo inicial + entradas realizadas − saídas realizadas da conta. Lançamentos cancelados não entram |
| **Dinheiro disponível** | Soma dos saldos das contas marcadas como "conta para o dia a dia" (padrão: corrente, poupança, dinheiro em espécie). Não inclui limite de cartão, investimentos nem metas |
| **Recebi no mês** | Receitas realizadas com data no mês. Não incluem transferências, resgates de investimento, entradas de empréstimo nem reembolsos |
| **Gastei no mês** | Despesas pagas em conta com data no mês + compras no cartão com data de compra no mês, menos estornos do mês. Não inclui pagamento de fatura, pagamento de dívida, transferências nem aportes. Assim cada gasto é contado uma única vez, no dia em que foi feito |
| **Ainda preciso pagar** (até o fim do mês) | Contas a pagar pendentes ou vencidas (inclusive de meses anteriores) + valor restante das faturas com vencimento até o fim do mês + parcelas de dívidas com vencimento até o fim do mês |
| **Comprometido** | O que "Ainda preciso pagar" mostra, nos próximos 30 dias |
| **Dinheiro livre estimado** | Dinheiro disponível − comprometido. Receitas previstas não entram. Limite de cartão não entra |
| **Quanto devo (dívidas)** | Saldo devedor das dívidas ativas + total ainda não pago das faturas e parcelas futuras dos cartões, sem contar duas vezes as parcelas de parcelamento de fatura (que já estão nas faturas) |
| **Limite usado do cartão** | Soma das parcelas e encargos ativos − estornos − pagamentos de fatura, em todas as faturas (abertas, fechadas e futuras) |
| **Limite disponível** | Limite total − limite usado. Se os pagamentos superarem o usado, o cartão tem crédito, mostrado à parte |
| **Valor investido (aportado)** | Aportes − retiradas de capital |
| **Valor atual do investimento** | Último saldo informado (renda fixa e outros) ou quantidade × último preço informado (renda variável). Sempre com a data da informação |
| **Ganho estimado** | Valor atual + retiradas + rendimentos recebidos em dinheiro − aportes. É estimado porque depende do valor informado |
| **Rentabilidade (TIR)** | Taxa interna de retorno anualizada dos fluxos (aportes, retiradas, rendimentos e valor atual na data informada). Só aparece com dados suficientes |
| **Patrimônio** | Dinheiro em todas as contas + valor atual dos investimentos − o que devo (dívidas e cartões) |

## 2. Decisões financeiras

| ID | Decisão | Origem |
|---|---|---|
| F1 | Dinheiro em centavos inteiros; `float` proibido no domínio | Técnica (T1.1) |
| F2 | Resto da divisão em parcelas vai para a primeira parcela (R$ 100,00 em 3× = 33,34 + 33,33 + 33,33) | Auditoria |
| F3 | Recorrência mensal calculada a partir da data original | Técnica (T1.1) |
| F4 | Datas civis sem hora; "hoje" no fuso America/Sao_Paulo | Técnica (T1.1) |
| F5 | No formato BR, ponto é sempre separador de milhar | Técnica (T1.1) |
| F6 (A7) | Arredondamento meio para cima, só na geração de parcelas e no cálculo de juros. Somas nunca arredondam | M3 |
| F7 (A3) | Visão mensal de caixa (o que entrou e saiu das contas) e visão de gastos por categoria pela data do gasto. As duas aparecem em telas separadas e nunca somadas | M3 |
| F8 (D5) | Recorrências geram ocorrências calculadas na hora. Uma ocorrência só é gravada quando paga, editada ou cancelada | M3 |
| F9 (D6) | Lançamentos realizados podem ser editados; a edição guarda histórico (valores anteriores) e a exclusão vira cancelamento, que preserva o registro | M3 |
| F10 (D3) | Cada conta tem a marcação "conta para o dia a dia". Padrão: sim para corrente, poupança e espécie; não para "outra" | M3 |
| F11 (A8) | "Próximo recebimento" = próxima receita prevista marcada como principal; se não houver, 30 dias | M3 |
| F12 | Contas a pagar vencidas continuam pendentes até serem pagas ou canceladas. Nunca são marcadas como pagas automaticamente | Requisito |
| F13 | Pagamento de conta a pagar gera o lançamento de despesa; a conta a pagar em si não é despesa. Pagamentos parciais acumulam até o valor total | M3 |
| F14 | Transferência gera dois lançamentos ligados (saída e entrada) e fica fora de receitas e despesas | Requisito |
| F15 | Entrada de empréstimo e reembolso não são receita; resgate de investimento não é receita; aporte não é despesa | M3 |
| F16 (D8) | Compras em moeda estrangeira registradas em reais pelo valor cobrado; IOF como encargo do cartão | M3 |
| F17 | O saldo inicial vale para o começo do dia informado; lançamentos com data anterior são recusados | M3 (implementação) |
| F18 | Lançamentos realizados (receita, despesa, pagamento, compra, aporte) não aceitam data futura; o que vai acontecer fica em Contas a pagar | M3 (implementação) |
| F19 | Pagamento de fatura, conta a pagar ou dívida acima do que falta é recusado, com o valor restante na mensagem | M3 (implementação) |
| F20 | Pagamentos de fatura e de dívida não são editados: cancela-se e registra-se de novo, para as validações valerem outra vez | M3 (implementação) |
| F21 | Ao abrir uma ocorrência de recorrência para pagar, ela é gravada (sem pagamento). Isso não muda saldos nem totais | M3 (implementação) |
| F22 | "Gastei no mês" conta compras no cartão pela data da compra; compra cancelada sai do gasto; estorno reduz a categoria no mês do estorno; no parcelamento de fatura, só os juros entram como gasto | M3 (implementação) |

### Cartões
| ID | Decisão | Origem |
|---|---|---|
| F-CARTAO-1 | A fatura é identificada pela data de vencimento. Se o dia de vencimento for menor ou igual ao de fechamento, o vencimento cai no mês seguinte ao fechamento | M3 |
| F-CARTAO-2 (A1) | Compra no dia do fechamento vai para a próxima fatura (configurável por cartão) | M3 |
| F-CARTAO-3 (A2) | Dia de fechamento ou vencimento que não existe no mês vira o último dia do mês. Sem ajuste para dia útil | M3 |
| F-CARTAO-4 | A fatura de cada parcela é gravada na criação da compra. Mudar o dia de fechamento não mexe em compras antigas | M3 |
| F-CARTAO-5 (A5) | Pagamento parcial: o restante continua devido **na própria fatura** (situação "parcialmente paga" ou "vencida") até ser pago. Juros e IOF que o banco cobrar são lançados pelo usuário como encargo na fatura seguinte. Nada é transferido automaticamente, então o restante nunca aparece duas vezes | M3 |
| F-CARTAO-6 (A4) | Renegociação/parcelamento de fatura: o valor renegociado sai da fatura como crédito "transferido para renegociação"; cria-se uma dívida do tipo "parcelamento de fatura"; as parcelas do acordo entram nas faturas futuras como lançamentos do cartão ligados à dívida. A diferença entre o total do acordo e o valor renegociado é registrada como juros. A dívida não aceita pagamento direto (é paga pelas faturas) e não entra de novo no "Quanto devo" | M3 |
| F-CARTAO-7 | Cancelamento de compra: parcelas de faturas ainda não fechadas são canceladas; parcelas de faturas já fechadas geram crédito na fatura aberta. O histórico é preservado | M3 |
| F-CARTAO-8 (D2) | Estorno parcial: crédito na fatura aberta, no valor informado | M3 |
| F-CARTAO-9 | Encargos (anuidade, juros, IOF, tarifas) são lançamentos à vista do cartão, na categoria "Juros e tarifas" | M3 |

### Dívidas
| ID | Decisão | Origem |
|---|---|---|
| F-DIV-1 | O saldo devedor é ancorado: valor informado em uma data + encargos lançados − pagamentos de principal depois dessa data | Revisão 3.6 |
| F-DIV-2 | Pagamento pode informar juros; se não informar, o valor inteiro abate o saldo e o saldo aparece como "estimado" | Revisão 3.7 |
| F-DIV-3 | Taxa desconhecida fica vazia; nunca é tratada como zero sem aviso | Requisito |
| F-DIV-4 | Taxa anual → mensal por (1 + a)^(1/12) − 1 | Revisão 3.8 |
| F-DIV-5 (A6) | Estratégias: maior juros primeiro (dívidas sem taxa vão para o fim, com aviso), menor saldo primeiro, menor parcela primeiro e equilibrada | M3 |
| F-DIV-6 (A9) | Equilibrada: nota = 0,5 × (taxa ÷ maior taxa conhecida) + 0,5 × (parcela ÷ saldo) ÷ maior (parcela ÷ saldo). Sem taxa, só o segundo termo, com aviso | M3 |
| F-DIV-7 | Renegociação: a dívida antiga fica "renegociada" com saldo zero por evento sem saída de dinheiro; a nova guarda a ligação com a antiga | M3 |

### Investimentos e metas
| ID | Decisão | Origem |
|---|---|---|
| F-INV-1 | Aporte aumenta o capital investido; retirada diminui; nenhum dos dois é ganho ou perda | Requisito |
| F-INV-2 | Renda variável usa preço médio: compras somam quantidade e custo (com taxas); vendas reduzem o custo proporcionalmente | M3 |
| F-INV-3 | Valor atual sempre vem de informação manual com data. Mais de 30 dias sem atualizar: aviso "pode estar desatualizado" | M3 |
| F-INV-4 | Taxa real = (1 + nominal) ÷ (1 + inflação) − 1 | Revisão 3.8 |
| F-INV-5 | Movimento de investimento pode ser ligado a uma conta; aí gera o lançamento correspondente na conta (aporte = saída, retirada/rendimento recebido = entrada), fora de receitas e despesas | M3 |
| F-META-1 | Metas acumulam por contribuições registradas. Projeção usa só a contribuição mensal planejada; rendimento só se o usuário informar a taxa, com o aviso de estimativa | M3 |

### Simulador "Posso comprar?"
| ID | Decisão | Origem |
|---|---|---|
| F-SIM-1 | Ponto de partida: dinheiro disponível de hoje (contas do dia a dia, sem investimentos e sem limite de cartão). Soma receitas previstas e subtrai contas a pagar (inclusive vencidas, no mês atual), faturas em aberto e parcelas de dívidas cadastradas | Especificação 4.9, opção mais segura |
| F-SIM-2 | Granularidade mensal; gastos do dia a dia não cadastrados não entram, e a tela avisa para deixar folga | Opção mais segura documentada |
| F-SIM-3 | Compra no cartão segue o mesmo ciclo de fechamento e a mesma divisão de parcelas das compras reais (F-CARTAO-*) | Consistência |
| F-SIM-4 | Veredito: "Atenção" se algum mês fica negativo ou se o limite disponível do cartão não comporta a compra; "Cuidado" se o menor saldo previsto fica abaixo do valor mensal da compra; "cabe" só nos demais casos. Nunca diz "seguro" | Especificação 4.9 |
| F-SIM-5 | "Esperar" indica o primeiro mês a partir do próximo em que pagar à vista não deixa nenhum mês negativo | M3 |
| F-SIM-6 | A simulação só lê dados: nada é gravado (verificado por teste) | Requisito |

## 3. Decisões de infraestrutura, segurança e privacidade

| ID | Decisão | Origem |
|---|---|---|
| D1 | Hospedagem em nuvem; servidor em casa descartado | Diogo |
| G1 | Repositório pode continuar público, sem dados pessoais nem segredos | Diogo |
| H1 | Primeira candidata: VM gratuita (Oracle Cloud Always Free) com Docker Compose. **Nenhuma conta será criada pelo Claude.** Se o cadastro exigir cartão com risco de cobrança, a decisão volta ao Diogo | Diogo + M3 |
| U1 | Três usuários isolados, sem conta administrativa com acesso às finanças | Diogo |
| U3 | Fonte-base 18 px, alvos de toque 48 px, alto contraste, preto e branco | Diogo |
| P1 | Nenhum dado financeiro em cache no aparelho. O service worker guarda só a estrutura do app. Sem conexão, o app avisa e bloqueia o envio | M3 |
| P2 | Exportação individual (JSON e CSV) pelo próprio usuário. Restauração só do banco inteiro, pelo administrador | M3 |
| P3 | As três pessoas serão informadas, em `docs/PRIVACIDADE.md`, de que quem administra o servidor tem acesso técnico ao banco | M3 |
| D9 | Cópia externa do backup: **pendente**. Não será habilitado nenhum serviço pago ou que exija cartão sem autorização | Pendente (Diogo) |
| D10 | Sessão: com "Manter conectado neste aparelho", 30 dias no máximo e 7 dias sem uso; sem a opção, 12 horas no máximo e 30 minutos sem uso | M3 |
| T-ISO | Isolamento: `owner_id` + chaves compostas + RLS + filtro na aplicação | Técnica (T1.2) |
| T-SES | Sessões no banco, cookie `HttpOnly; Secure; SameSite=Strict`, só o hash do token salvo | Técnica |
| T-IDEM | Toda criação financeira aceita `Idempotency-Key`; repetição devolve o resultado original | Técnica |
| T-CSRF | Métodos que alteram dados exigem `Origin` igual ao do app e o cabeçalho `X-Requested-With` | Técnica |
| T-SPA | O FastAPI serve o site estático e a API na mesma origem; em produção, o Caddy faz HTTPS na frente | Técnica |
| T-HORA | Horários de sessão vêm só do relógio do banco (`now()`), o mesmo usado para conferir validade. O relógio da aplicação (São Paulo) fica para as datas financeiras | Técnica (defeito encontrado: sessão "expirava" ao nascer quando os relógios divergiam) |

### Entrar com digital ou rosto (M4)
| ID | Decisão | Origem |
|---|---|---|
| A-DIG-1 | Passkeys (WebAuthn). O aparelho confirma a digital, o rosto ou o PIN dele e assina um desafio; o servidor guarda só a chave pública. Nenhum dado biométrico sai do aparelho | M4 |
| A-DIG-2 | A senha continua: é o primeiro acesso em cada aparelho e a reserva se o sensor falhar ou o aparelho for trocado. Remover a senha deixaria a conta inacessível ao perder o celular | Opção mais segura |
| A-DIG-3 | Só o sensor do próprio aparelho (`platform`), credencial guardada nele (`residentKey: required`) e verificação do usuário obrigatória (`userVerification: required`). Sem QR code nem chave física, para não confundir | M4 + simplicidade (M2) |
| A-DIG-4 | Entrar não pede o usuário: o aparelho oferece as credenciais que tem. O servidor não revela quem tem digital ativada (`allowCredentials` vazio) | Privacidade |
| A-DIG-5 | Desafio aleatório de uso único, válido por 5 minutos, apagado ao ser usado mesmo se a verificação falhar. Origem conferida; identificador do usuário conferido; contador que volta é recusado (indício de cópia) | Segurança |
| A-DIG-6 | Falhas contam no mesmo limite por endereço do login com senha (20 em 15 minutos), sem bloquear a senha de nenhuma pessoa em particular | Segurança |
| A-DIG-7 | "Manter conectado neste aparelho" vale também para a digital. Sem a opção, a sessão é curta, mas entrar de novo é só tocar no sensor | Opção mais segura |
| A-DIG-8 | A credencial fica presa ao domínio do app. **Se o domínio mudar, cada pessoa precisa ativar de novo** (a senha continua funcionando) | Limitação do padrão |

## 4. Pendências que dependem do Diogo
| ID | O que falta | Bloqueia |
|---|---|---|
| H1 | Criar a conta no provedor de nuvem e liberar a VM (o Claude não cria contas) | Publicação |
| D9 | Escolher o destino da cópia externa do backup | Proteção contra perda do servidor |
| P3 | Comunicar às outras duas pessoas o que está em `PRIVACIDADE.md` | Uso real pelas três pessoas |
