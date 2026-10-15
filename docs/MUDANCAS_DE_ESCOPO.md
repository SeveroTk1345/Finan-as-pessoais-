# Histórico de mudanças de escopo

Este arquivo registra cada mudança de escopo, o que ela altera em decisões anteriores e por quê. Os documentos `ETAPA0_AUDITORIA.md` e `ETAPA0_REVISAO.md` são preservados sem edição; quando algo deles deixa de valer, o registro fica aqui.

## M1 · Autorização de implementação (15/10/2026)

Origem: mensagem "AUTORIZAÇÃO DE IMPLEMENTAÇÃO" do Diogo.

| Item anterior | Novo | Motivo |
|---|---|---|
| Auditoria 5.2, Opção A: servidor em casa + Tailscale (recomendada) | **Descartada como arquitetura principal.** Hospedagem em nuvem gratuita | O computador do Diogo não fica ligado. Resolve a decisão D1 da revisão |
| Auditoria 5.2, Opção B: VM gratuita (Oracle) como alternativa | Passa a ser a primeira candidata, sujeita a investigação (decisão H1) | Mesma razão |
| Backup na T5.1 | Backup automático na T1.2 | Já previsto na revisão (item 6.1); confirmado pelo Diogo |
| Idempotência e CSRF | Obrigatórios na T1.3 | Já previsto na revisão (itens 1.1 e 1.3); confirmado |
| Repositório | `SeveroTk1345/financas-pessoais`, privado | Ver pendência G1 em `DECISOES.md` |

## M2 · Três usuários, privacidade e simplicidade (15/10/2026)

Origem: mensagem "COMPLEMENTO OBRIGATÓRIO DO ESCOPO" do Diogo. Passa a fazer parte do escopo oficial.

Resumo dos requisitos novos:
* Exatamente três usuários, cada um com conta própria e dados financeiros totalmente privados. Sem painel conjunto e sem conta administrativa com acesso às finanças dos outros.
* Isolamento verificado no servidor em toda operação, com testes automatizados de A contra B e B contra A, inclusive em cartões, faturas, parcelas, dívidas, investimentos, relatórios, exportações e operações indiretas.
* Avaliar Row-Level Security do PostgreSQL como camada extra.
* Contas criadas pelo dono do projeto, sem cadastro público; senhas com hash seguro; recuperação documentada.
* Duas pessoas com cerca de 60 anos: fonte-base de 18 px, botões com 48 px de altura mínima, contraste alto, linguagem simples, poucas ações por tela, confirmação e retorno visual claros.
* Navegação com até seis áreas: Início, Contas, Contas a pagar, Dívidas, Investimentos, Mais.
* Módulo de investimentos com aplicações, aportes, resgates, saldo manual e rendimentos.
* Dispositivo compartilhado: mostrar quem está conectado, sair fácil, sessão que expira, nada visível pelo botão "voltar" após sair, notificações sem valores.

### Conflitos com decisões anteriores

| # | Decisão anterior | Conflito | Como fica |
|---|---|---|---|
| C1 | Auditoria 5.2 e T1.3: "autenticação de usuário único" | Agora são três usuários isolados | T1.3 passa a ser autenticação multiusuário. Toda tabela financeira terá dono (`owner_id`). Proposta técnica em `DECISOES.md` (T-ISO) |
| C2 | Auditoria 5.2: Tailscale | Já descartado em M1 | Sem mudança adicional |
| C3 | Requisitos originais seção 5 e auditoria: navegação com Início, Movimentações, Cartões, Dívidas, Planejamento | Nova navegação com seis áreas | Adotada a nova navegação. Cartões e Planejamento vão para "Mais" |
| C4 | Auditoria T4.3: "Reserva e investimentos" só como simulação | Agora há registro real de aplicações, aportes e resgates | Nova tarefa T4.6 (registro de investimentos). T4.3 continua para as simulações |
| C5 | Auditoria 5.2: "Dashboard" com muitos indicadores (requisitos 4.1) | Simplicidade para usuários de ~60 anos | O Início responde às seis perguntas da seção 7 do complemento. Indicadores extras (orçamento x realizado, próximos 30 dias detalhados) vão para telas secundárias |
| C6 | Revisão D10: duração da sessão em aberto | Sessão não pode ficar aberta indefinidamente em dispositivo compartilhado | D10 fica parcialmente resolvida: haverá expiração. Os prazos continuam em aberto |
| C7 | Política offline da auditoria: leitura em cache no aparelho | Em dispositivo compartilhado, cache de dados pode expor um usuário ao próximo | Nova decisão P1 em `DECISOES.md`. Recomendação: na V1, não guardar dados financeiros em cache no aparelho, só a estrutura do app |
| C8 | Backup só como cópia do banco inteiro (revisão 6.1) | Exportações e backups individuais precisam respeitar o isolamento | Dois níveis: cópia do banco inteiro (infraestrutura, cifrada) e exportação individual feita pelo próprio usuário. Ver P2 |
| C9 | Implícito: quem administra o servidor pode ler o banco | "Nenhuma conta administrativa com acesso irrestrito" | A aplicação não terá essa conta. Mas quem administra o servidor tem acesso técnico ao banco. Isso precisa ser dito às três pessoas. Ver P3 |
| C10 | Requisitos 4.4: lembretes | Notificações não podem mostrar valores | V1: só destaques dentro do app. Notificações push ficam para depois e, se existirem, sem valores |

Nenhuma regra financeira aprovada foi alterada por M2.

## M3 · Missão de desenvolvimento completo (15/10/2026)

Origem: mensagem "MISSÃO: DESENVOLVER O APLICATIVO FINANCEIRO COMPLETO" do Diogo.

Principais pontos:
* Autonomia para decisões técnicas e para regras financeiras ambíguas, escolhendo a alternativa mais segura e documentando. As decisões antes "abertas" foram tomadas com base nas recomendações da revisão e estão registradas em `DECISOES.md` com a marca **M3**.
* Identidade visual preto e branco, minimalista, fonte Inter, valores grandes.
* Áreas: Início, Contas, Receitas e despesas, Contas a pagar, Dívidas e parcelas, Investimentos, Planejamento, Mais (com cartões, relatórios, categorias, perfil, exportação, ajuda).
* Investimentos com renda fixa, renda variável, outros, movimentações e rentabilidade (TIR/XIRR quando houver dados).
* Cartões com regras rigorosas e renegociação de fatura transferindo a obrigação para a estrutura de dívida sem duplicar saldo.
* Testes ponta a ponta com 14 cenários obrigatórios.
* O repositório pode continuar público (resolve G1).

### Conflitos com decisões anteriores
| # | Antes | Agora | Como fica |
|---|---|---|---|
| C11 | M2: no máximo seis áreas na navegação | M3: oito áreas sugeridas | Computador: barra lateral com as oito áreas. Celular: barra inferior com cinco itens (Início, Lançamentos, A pagar, Investimentos, Mais); as demais ficam em "Mais" com botões grandes e rótulos. Assim o celular respeita o limite de M2 |
| C12 | Revisão 2.1: parcelamento de fatura como lançamento do próprio cartão, com a dívida só para consulta | M3 item 5.8: transferir a obrigação para a estrutura de dívida | As duas coisas: a renegociação cria uma **dívida** (visível e acompanhada no módulo de dívidas) e a fatura recebe o crédito do valor renegociado. As parcelas do acordo são cobradas nas faturas futuras do cartão, que é como os bancos fazem, e a dívida mostra quanto falta a partir dessas parcelas. Não existe pagamento direto da dívida nesse caso, então nada é contado duas vezes. Ver F-CARTAO-6 |
| C13 | P2: restauração individual | M3: exportação dos próprios dados | Exportação individual (JSON e CSV). Restauração só do banco inteiro, pelo administrador. Ver P2 |
