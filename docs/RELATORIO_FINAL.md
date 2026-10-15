# Relatório final de entrega (missão M3)

Data: 15/10/2026. Branch `desenvolvimento`. Todos os números abaixo vêm de execuções reais registradas em `REGISTRO_TESTES.md`.

## 1. Funcionalidades efetivamente implementadas
| Área | Conteúdo |
|---|---|
| Início | Dinheiro disponível, comprometido, livre; recebi e gastei no mês; contas que vencem; quanto devo; investido; patrimônio. Cada número tem a definição explicada |
| Contas | Corrente, poupança, dinheiro, carteira digital; saldo inicial; ajuste com histórico; arquivar |
| Receitas e despesas | Receitas, despesas, reembolsos, transferências (não viram receita nem gasto), categorias, edição com histórico, cancelamento |
| Contas a pagar | Avulsas e recorrentes (sem deslizar o dia: 31/01, 28/02, 31/03), a receber, pagamento parcial, vencidas permanecem visíveis; lista única com faturas e parcelas |
| Cartões | Compras à vista e parceladas, encargos, faturas derivadas do razão (nunca gravadas), pagamento integral ou parcial, limite, estorno, cancelamento, renegociação de fatura, crédito excedente levado para a fatura seguinte, sem dupla contagem |
| Dívidas | Saldo ancorado, pagamentos com e sem juros, encargos, quitação, renegociação, empréstimo com entrada na conta, 4 estratégias comparadas |
| Investimentos | Renda fixa, variável e outros; aportes, retiradas, rendimentos; preço médio; valor informado com data e aviso de desatualizado; ganho estimado; TIR |
| Planejamento | Metas com contribuições, progresso e projeção; simulador "Posso comprar?" (à vista ou no cartão, 6 meses, comparar agora × não comprar × esperar, nada é gravado) |
| Relatórios | Gastos por categoria no mês, evolução de 12 meses |
| Mais | Categorias, perfil e troca de senha, exportação (JSON completo e CSV), ajuda |
| Segurança | Login com Argon2id, sessão no banco, cookie HttpOnly/SameSite=Strict/Secure, CSRF, limite de tentativas, CSP, HSTS, `no-store` na API, idempotência em toda criação |
| PWA | Manifesto, ícones iOS, service worker só da estrutura (nunca dados), aviso de nova versão, aviso sem internet com botão de salvar bloqueado |
| Operação | Linha de comando para criar, redefinir senha, desativar e listar usuários; backup diário com rotação e SHA-256; restauração em banco separado |

Interface: 34 telas em preto e branco com Inter, texto base 18 px, botões de 48 px, alto contraste, 8 áreas no computador e 5 na barra inferior do celular.

**Não implementado:** importação de CSV de extratos (especificação original, item 4.11).

## 2. Funcionalidades testadas
Todas as do item 1, em três camadas: regras financeiras puras (unitários e propriedades com Hypothesis), API com PostgreSQL real e três usuários, e ponta a ponta no Chromium com perfil de iPhone. Os 14 cenários obrigatórios estão mapeados um a um em `REGISTRO_TESTES.md`. A força dos testes de isolamento foi conferida por mutação: remover o filtro por dono, a RLS forçada ou a limpeza do pool faz testes falharem.

## 3. Resultados reais dos testes
| Verificação | Resultado |
|---|---|
| pytest (backend, banco real) | 357 aprovados, 0 falhas |
| ruff, ruff format, mypy strict | Sem problemas |
| vitest em 3 fusos (São Paulo, UTC, Tóquio) | 43 aprovados em cada |
| eslint, tsc | Sem problemas |
| next build | 34 telas |
| Playwright (14 cenários + extras) | 17 aprovados, 0 falhas |
| Backup e restauração dos dados criados pela interface | Conteúdo idêntico |
| pip-audit, npm audit | 0 vulnerabilidades |
| GitHub Actions | Sucesso na execução 38674544887 (commit d7ce0e5) |

Ambiente: container Linux, PostgreSQL 16 em Docker, Chromium com perfil de iPhone. **Não é o Safari real**; a validação no aparelho físico está pendente.

## 4. Banco de dados e migrações
PostgreSQL 16, migrações Alembic 0001 a 0004, 22 tabelas. Valores em centavos inteiros, datas civis. Testes de ida e volta das migrações e de convenções no catálogo (toda tabela com dono tem `owner_id`, chave composta e RLS forçada). Detalhes em `MODELO_DE_DADOS.md`.

## 5. Autenticação e isolamento
Três usuários independentes, sem conta administradora que veja finanças alheias. Entrada com usuário e senha ou, depois de ativar no aparelho, com digital ou rosto (passkeys; o servidor guarda só a chave pública). A identidade vem só da sessão validada; o backend ignora qualquer `owner_id` enviado. Isolamento em duas camadas: filtro na aplicação e Row-Level Security forçada, com o papel `fin_app` sem superusuário e sem BYPASSRLS. Identidade definida por transação e limpa a cada retirada do pool. Testado com as 6 combinações de acesso cruzado em todas as rotas, pela API e pela tela (404 sem vazar conteúdo). Ver `BANCO_E_ISOLAMENTO.md`.

## 6. Backups e restauração
Serviço de backup no Compose: cópia diária com `pg_dump`, rotação, permissão 600 e SHA-256. Restauração testada em banco separado (teste automatizado, Compose real e dados criados pela interface), com conteúdo idêntico. **Pendente:** cópia fora do servidor e cifrada, cujo destino depende de decisão do Diogo (D9). Ver `BACKUP.md`.

## 7. Implantação
**Não publicado. Não há URL real.** A publicação exige criar conta em provedor de nuvem, o que a missão proíbe fazer sem autorização, e o cadastro de VM gratuita normalmente pede cartão (risco de cobrança, ver `IMPLANTACAO.md`). Está pronto e verificado localmente: imagem Docker, Compose de produção com Caddy (HTTPS automático), migração em serviço separado, só portas 80 e 443 expostas, dados e sessão mantidos após reiniciar.

## 8. Como iniciar e usar
* Desenvolvimento: `make install`, `make test`, `make e2e` (README).
* Usar localmente com dados sintéticos: `make build` e `scripts/stack-local.sh` (README).
* Produção: `IMPLANTACAO.md`, passo a passo na VM, criação das três contas com `criar-usuario --senha-stdin`.
* Uso diário: `GUIA_DO_USUARIO.md`, inclusive instalação na Tela de Início do iPhone.

## 9. Limitações, riscos e pendências
| Item | Tipo |
|---|---|
| Publicar (VM gratuita + domínio) | Depende do Diogo (H1) |
| Cópia externa cifrada do backup | Depende do Diogo (D9) |
| Validação no iPhone físico (`VALIDACAO_IPHONE.md`) | Após publicação |
| Teste com usuários representativos (~60 anos) | Não possível neste ambiente |
| Importação de CSV | Não implementada |
| Revisão independente pelo Codex | Pendente |
| Sem internet o app não salva (sem fila offline) | Decisão de segurança |
| Valores de investimentos são manuais (sem cotações) | Decisão: não inventar integrações |
| Juros do rotativo lançados pela pessoa (F-CARTAO-5); vencimento não ajustado para dia útil (F-CARTAO-3) | Limitação documentada |
| "Posso comprar?" é mensal e só vê o que está cadastrado (F-SIM-2) | Limitação documentada |
| CSP permite scripts inline (exigência do export estático do Next.js) | Risco baixo, documentado |
| Repositório público | Escolha do Diogo; contém só código, documentação e configuração sem segredos |

## 10. Commit, branch e arquivos relevantes
* Branch: `desenvolvimento` (a `main` segue só com a documentação inicial; mesclar somente após revisão).
* Último commit de código: `4206432` (simulador "Posso comprar?"); este relatório vem no commit seguinte.
* Backend: `backend/app/domain/` (regras), `backend/app/services/`, `backend/app/api/`, `backend/migrations/`, `backend/tests/`.
* Frontend: `frontend/src/app/`, `frontend/src/lib/`, `frontend/e2e/`.
* Implantação: `Dockerfile`, `deploy/`, `scripts/`, `.github/workflows/ci.yml`.
* Decisões: `docs/DECISOES.md`; testes: `docs/REGISTRO_TESTES.md`.
