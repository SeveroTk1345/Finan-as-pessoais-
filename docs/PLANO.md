# Plano de implementação

Versão 2, de 15/10/2026. Atualiza a seção 7 de `ETAPA0_AUDITORIA.md` com a revisão e as mudanças de escopo M1 e M2 (`MUDANCAS_DE_ESCOPO.md`). A numeração original foi preservada; tarefas novas recebem números novos no fim de cada etapa.

Regras de trabalho:
* Uma branch e um PR por tarefa, com revisão do Codex quando o repositório estiver acessível a ele.
* Uma tarefa só é concluída com testes, lint e build registrados em `REGISTRO_TESTES.md`.
* **Toda tarefa que cria uma rota com dados financeiros inclui testes de isolamento A contra B e B contra A.**
* Toda tela segue o padrão de acessibilidade do escopo M2 (18 px, 48 px, contraste, rótulos, confirmação).

Situação: ✅ concluída e testada · 🔄 em andamento · ⏳ a fazer · ⛔ bloqueada por decisão

## Etapa 1 · Base técnica
| Tarefa | Situação | Observação |
|---|---|---|
| T1.1 Esqueleto, dinheiro, datas, recorrência, lint, testes, build | ✅ | Ver `REGISTRO_TESTES.md` |
| T1.2 PostgreSQL via Docker Compose, Alembic, tabela `users`, papéis do banco (migração e aplicação), RLS (T-ISO), backup automático do banco inteiro com rotação e teste de restauração | ⏳ | Parte individual de backup bloqueada por P2; cópia externa por D9 |
| T1.3 Autenticação multiusuário: criação das três contas por comando no servidor, Argon2, sessões no banco (T-SES), sair, trocar senha, limite de tentativas, CSRF por `Origin`, idempotência, `Cache-Control: no-store`, `docs/PRIVACIDADE.md` | ⏳ | Prazos de sessão dependem de D10 (estrutura não) |
| T1.4 Frontend: layout acessível, navegação com seis áreas, tela de login, indicação de quem está conectado | ⏳ | |
| T1.5 PWA: manifesto, ícones iOS, service worker, aviso de nova versão | ⛔ parcial | Política de cache depende de P1 |
| T1.6 Publicação em nuvem gratuita e teste real no iPhone | ⛔ | Depende de H1 |
| T1.7 (nova) Teste de isolamento genérico: varre todas as rotas com ID e verifica que A não acessa B | ⏳ | Criado junto com a T1.3 e reutilizado em todas as tarefas |

## Etapa 2 · Operações essenciais
| Tarefa | Situação | Observação |
|---|---|---|
| T2.1 Contas (dinheiro em espécie, corrente, poupança, outras) | ⏳ | |
| T2.2 Livro razão e cálculo de saldo | ⏳ | Edição de realizados depende de D6 |
| T2.3 Transferências | ⏳ | |
| T2.4 Receitas previstas e recebidas, recorrência | ⏳ | D5 (proposta técnica) |
| T2.5 Despesas, contas a pagar (pendente, vencida, paga, cancelada, pagamento parcial), categorias | ⏳ | Corresponde à área "Contas a pagar" |
| T2.6 Lançamento rápido nas áreas principais | ⏳ | Ações visíveis da seção 5 de M2 |
| T2.7 Início simples com as seis perguntas de M2 | ⏳ | "Dinheiro disponível" depende de D3 |

## Etapa 3 · Cartões e dívidas
| Tarefa | Situação | Observação |
|---|---|---|
| T3.1 Cartões, ciclo de fechamento, parcelas | ⛔ | A1, A2, D8 |
| T3.2 Faturas derivadas e situações | ⛔ | A2 |
| T3.3 Pagamento integral e parcial, limite disponível | ⛔ | A4, A5 |
| T3.4 Estornos e cancelamentos | ⛔ | D2 |
| T3.5 Dívidas, pagamentos, renegociação, histórico | ⛔ parcial | Cadastro e pagamentos simples podem começar; juros dependem de A7 |
| T3.6 Testes de regressão contra dupla contagem | ⏳ | Junto com cada tarefa acima |

## Etapa 4 · Planejamento
| Tarefa | Situação | Observação |
|---|---|---|
| T4.1 Visão mensal | ⛔ | A3 |
| T4.2 Estratégias de quitação | ⛔ | A6, A7, A9 |
| T4.3 Simulação de reserva e investimentos (nominal x real, três cenários) | ⛔ parcial | A7 |
| T4.4 Simulador "Posso comprar?" | ⛔ | D4 |
| T4.5 Início completo (dinheiro livre) | ⛔ | D3, D4, A8 |
| T4.6 (nova) Registro de investimentos: aplicações, aportes, resgates, saldo informado manualmente, rendimentos, separação entre aportado e rendimento | ⏳ | Não depende de decisões financeiras abertas |

## Etapa 5 · Dados e robustez
| Tarefa | Situação | Observação |
|---|---|---|
| T5.1 Exportação e restauração individual em JSON | ⛔ | P2 |
| T5.2 Exportação CSV (com proteção contra fórmulas no Excel) | ⏳ | Somente dados do próprio usuário |
| T5.3 Importação CSV com mapeamento, prévia e duplicatas | ⏳ | |
| T5.4 Revisão de segurança | ⏳ | |
| T5.5 (nova) Teste ponta a ponta de isolamento com três usuários (roteiro da seção 9 de M2) | ⏳ | |

## Etapa 6 · Validação
| Tarefa | Situação | Observação |
|---|---|---|
| T6.1 Roteiro no Safari do iPhone e na Tela de Início | ⛔ | Depende de T1.6 |
| T6.2 Perda de conexão e limitações | ⛔ | Depende de T1.6 e P1 |
| T6.3 (nova) Teste com usuários representativos (pessoas de ~60 anos) realizando tarefas comuns sem instruções | ⏳ | Registro das dificuldades e ajustes |
| T6.4 (nova) Dispositivo compartilhado: troca de usuário, botão voltar após sair, sessão expirada | ⏳ | |
