# Banco de dados e isolamento entre usuários

## Papéis do PostgreSQL
| Papel | Uso | Privilégios |
|---|---|---|
| `fin_admin` | Migrações, backups, criação de usuários (linha de comando) | Superusuário do container. Nunca usado pela API |
| `fin_app` | API | Sem superusuário, sem `BYPASSRLS`, sem criar bancos ou papéis, não é dono de nenhuma tabela. Só `SELECT/INSERT/UPDATE/DELETE` concedidos tabela a tabela |

O banco não publica porta em produção. Em desenvolvimento, `docker-compose.dev.yml` publica apenas em `127.0.0.1`.

## Duas camadas de isolamento
1. **Aplicação.** Repositórios recebem o usuário autenticado e filtram `owner_id` em toda consulta. O `owner_id` nunca vem do corpo ou da URL da requisição. Registro de outra pessoa é tratado como inexistente (a API responderá 404).
2. **Banco (Row-Level Security).** Toda tabela com dono tem RLS ativada e forçada, com a política `owner_id = app_current_user_id()` para leitura e escrita.

Cada camada foi testada **sozinha**: RLS sem filtro da aplicação (SQL sem `WHERE`) e filtro da aplicação sem RLS (superusuário).

## Identidade por transação
`app.db.identity.user_transaction(engine, user_id)`:
* exige `UUID` (texto não é aceito);
* define `app.user_id` com `set_config(..., true)`, equivalente a `SET LOCAL`, que termina com o `COMMIT` ou o `ROLLBACK`.

Barreira extra em `app.db.engine.make_engine`: toda vez que uma conexão sai do pool, `app.user_id` é apagado com escopo de sessão. Mesmo um `SET` de sessão feito por engano não passa para o próximo usuário.

Sem identidade, `app_current_user_id()` é `NULL` e nenhuma linha aparece ou pode ser gravada.

## Chaves estrangeiras compostas
Tabelas com dono têm `UNIQUE (owner_id, id)`. Referências entre tabelas com dono usam `(owner_id, <fk>)`. Assim o próprio banco recusa ligar um registro de A a um de B, mesmo se a aplicação tiver um bug e mesmo para o superusuário.

## Verificação automática de convenções
`tests/db/test_schema_conventions.py` lê o catálogo do PostgreSQL e falha se qualquer tabela pública:
* não tiver RLS ativada e forçada;
* tendo `owner_id`, não tiver exatamente a política padrão ou não tiver `UNIQUE (owner_id, id)`;
* referenciar outra tabela com dono sem incluir `owner_id` na chave.

Também confere que `fin_app` não é superusuário, não tem `BYPASSRLS` e não é dono de tabelas. Tabelas criadas no futuro são verificadas automaticamente.

## Prova de que os testes detectam falhas
Cada proteção foi desligada de propósito e a suíte foi executada (resultados em `REGISTRO_TESTES.md`):
| Proteção removida | Testes que falharam |
|---|---|
| Filtro `owner_id` no repositório | 6 |
| `FORCE ROW LEVEL SECURITY` | 1 (convenções). Sem efeito prático hoje, pois as tabelas pertencem ao superusuário |
| `ENABLE ROW LEVEL SECURITY` | 23 |
| Limpeza de identidade no pool | 1 |
| Identidade com escopo de sessão + sem limpeza no pool | 4 |
| Exigência de digital/rosto confirmados no login por passkey | 2 |
| Conferência do identificador do usuário na passkey | 1 |

## Digital ou rosto (passkeys)
* `passkeys` é uma tabela com dono como as outras (RLS, chave composta); cada pessoa lista e remove só as próprias.
* `webauthn_challenges` não tem `owner_id` nem política: `fin_app` **nem tem permissão** de leitura (testado). A API só chega lá por quatro funções `SECURITY DEFINER` com `search_path` fixo: criar desafio, consumir desafio (apaga e devolve numa só operação), localizar a credencial pelo identificador e registrar o uso. Mesmo padrão do login por senha (migração 0002).
* O desafio de cadastro guarda quem o pediu; outra pessoa não consegue usá-lo para prender uma credencial na conta alheia (testado).

## Limites conhecidos
* A RLS protege contra **erros de programação** (consulta sem filtro). Ela **não** protege contra injeção de SQL arbitrário, porque qualquer sessão pode mudar `app.user_id`. A defesa contra injeção é o uso exclusivo de consultas parametrizadas (SQLAlchemy) e a revisão de segurança.
* Quem administra o servidor tem acesso técnico ao banco (decisão P3).
