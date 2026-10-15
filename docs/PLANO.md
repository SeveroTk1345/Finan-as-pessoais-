# Plano de implementação

Versão 3, de 15/10/2026, depois da missão M3. A numeração anterior está no histórico do Git; aqui o plano segue as 12 etapas da missão.

Situação: ✅ concluída e testada · ⏳ pendente · ⛔ depende de ação externa

| # | Etapa | Situação | Evidência |
|---|---|---|---|
| 1 | Auditoria e consolidação das decisões | ✅ | `ETAPA0_*.md`, `DECISOES.md` v4 |
| 2 | Banco, migrações e persistência | ✅ | Migrações 0001–0003; testes de migração e convenções |
| 3 | Autenticação e isolamento | ✅ | `test_auth_api.py`, `test_isolation.py`, `test_identity_pool.py`, testes cruzados por módulo |
| 4 | Motor financeiro | ✅ | `app/domain/*`, testes de domínio com propriedades |
| 5 | Contas, receitas e despesas | ✅ | `test_core_api.py`, ponta a ponta 1–3 |
| 6 | Contas a pagar, cartões, faturas, dívidas | ✅ | `test_core_api.py`, `test_cards_debts_api.py`, ponta a ponta 4–6 |
| 7 | Investimentos | ✅ | `test_planning_api.py`, ponta a ponta 7–8 |
| 8 | Metas, planejamento e relatórios | ✅ | `test_planning_api.py`, ponta a ponta 9 |
| 9 | Interface completa e responsiva | ✅ | 33 telas; ponta a ponta 12 e rótulos |
| 10 | PWA, segurança, backup e restauração | ✅ | Service worker, cabeçalhos, `test_backup_restore.py`, cenário 14 |
| 11 | Testes integrados e ponta a ponta | ✅ | 351 + 41×3 + 16 testes (`REGISTRO_TESTES.md`) |
| 12 | Implantação e documentação | ✅ preparada / ⛔ publicação | Dockerfile, Compose com Caddy testado localmente; publicação exige conta do Diogo |

## Pendências
| Item | Tipo |
|---|---|
| Criar a VM gratuita e o domínio; publicar | ⛔ Diogo (H1) |
| Destino da cópia externa e cifrada do backup | ⛔ Diogo (D9) |
| Validar no iPhone físico | ⏳ após publicação |
| Teste com usuários representativos | ⏳ |
| Importação de CSV de extratos | ⏳ (especificação original 4.11) |
| Simulador "Posso comprar?" | ⏳ (especificação original 4.9) |
| Revisão do Codex | ⏳ |
