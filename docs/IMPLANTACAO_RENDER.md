# Implantação no Render + Neon (só pelo navegador)

Caminho escolhido porque não exige Docker, Ubuntu nem terminal no computador: tudo é
feito em sites. Os dois serviços têm plano grátis **sem cartão** (confira na tela de
cadastro: se algum pedir cartão, pare e avise).

| Peça | Onde | Plano grátis |
|---|---|---|
| App (site + API, um container Docker) | Render | 750 horas por mês; dorme após 15 minutos sem acesso e leva cerca de 1 minuto para acordar |
| Banco PostgreSQL | Neon | 0,5 GB e 100 horas de processamento por mês; dorme após 5 minutos sem uso |
| Manter o app acordado | UptimeRobot | Monitor a cada 5 minutos |
| Cópia de segurança diária, cifrada | GitHub Actions | Artefato guardado por 30 dias |

## O que acontece quando o app liga

O Render roda `python -m app.deploy_start`, que:

1. cria (ou ajusta) o papel `fin_app` no banco, **sem** superusuário e **sem** BYPASSRLS;
2. aplica as migrações com o dono do banco (o Neon não dá superusuário, e não precisa);
3. confere que `fin_app` não escapa da Row-Level Security; se escapar, o app **não sobe**;
4. troca o processo pelo servidor web já **sem** a senha do dono do banco no ambiente.

Testado em `backend/tests/db/test_deploy_start.py` com um dono de banco que imita o do
Neon (sem superusuário, com BYPASSRLS e CREATEROLE).

## Passo 1: banco no Neon

1. Entre em neon.tech → **Sign up** → continue com o GitHub ou o Google.
2. Crie o projeto:
   * Project name: `financas`
   * Postgres version: **16** (o backup usa as ferramentas da versão 16)
   * Region: **AWS US East 1 (N. Virginia)** (perto do Render, cada consulta fica rápida)
3. No painel do projeto, clique em **Connect**. Desligue **Connection pooling** e copie o
   endereço que começa com `postgresql://neondb_owner:...`. Esse é o
   `FIN_DATABASE_ADMIN_URL`. **Não cole em lugar nenhum além do Render e do GitHub.**

## Passo 2: app no Render

1. Entre em render.com → **Get Started** → continue com o GitHub.
2. **New** → **Blueprint** → escolha o repositório `Finan-as-pessoais-`. O Render lê o
   `render.yaml` e mostra o serviço `financas` (plano Free, região Virginia).
3. Ele pede o valor de `FIN_DATABASE_ADMIN_URL`: cole o endereço do Neon.
   `FIN_DB_APP_PASSWORD` e `FIN_SETUP_TOKEN` são gerados sozinhos.
4. **Apply**. A primeira construção leva de 5 a 10 minutos. No log, a sequência certa é:
   `Preparando o papel da API...`, `Aplicando migrações...`,
   `Conferindo o isolamento entre usuários...`, `Iniciando a API na porta ...`.

Se a tela do Blueprint pedir cartão, use o caminho manual: **New** → **Web Service** →
repositório → Language **Docker**, Branch `desenvolvimento`, Region **Virginia**,
Instance **Free**. Em *Advanced*: Docker Command `python -m app.deploy_start`, Health
Check Path `/api/health`. Variáveis: `FIN_DATABASE_ADMIN_URL` (o endereço do Neon),
`FIN_DB_APP_PASSWORD` e `FIN_SETUP_TOKEN` (botão **Generate**), `WEB_CONCURRENCY` = `1`.

## Passo 3: criar as 3 contas

1. Abra `https://SEU-APP.onrender.com/configurar/`.
2. O código fica no Render: serviço `financas` → **Environment** → `FIN_SETUP_TOKEN`.
3. Crie as contas (no máximo 3, o banco impõe). Entregue cada senha pessoalmente.
4. Depois de criar, **apague** a variável `FIN_SETUP_TOKEN` no Render: a página passa a
   dizer "Configuração desligada". Se alguém esquecer a senha, crie a variável de novo
   (Generate), troque a senha em /configurar e apague outra vez.

O código errado conta no limite de 20 tentativas por endereço a cada 15 minutos.

## Passo 4: instalar no iPhone

Safari → endereço do app → **Compartilhar** → **Adicionar à Tela de Início**. Depois de
entrar com a senha, ative a digital ou o rosto em Mais → Perfil e segurança.

A digital/rosto fica presa ao endereço `...onrender.com`. Se um dia o endereço mudar,
cada pessoa ativa de novo (a senha continua valendo).

## Passo 5: manter acordado (opcional, recomendado)

Sem isso, o primeiro acesso depois de 15 minutos parados leva cerca de 1 minuto.

1. uptimerobot.com → cadastro grátis.
2. **New monitor** → HTTP(s) → URL `https://SEU-APP.onrender.com/api/health` →
   intervalo de 5 minutos.

Um serviço ligado o mês inteiro usa cerca de 744 horas, dentro das 750 grátis. O
`/api/health` **não consulta o banco**, e o app não deixa conexão parada aberta
(`FIN_DB_KEEP_CONNECTIONS=false`, colocado pelo `deploy_start`): o Neon continua
dormindo quando ninguém usa e não gasta a cota de 100 horas.

## Passo 6: backup diário cifrado

O Neon grátis só volta 6 horas no tempo. O workflow `.github/workflows/backup.yml` faz
uma cópia por dia (03:17 de Brasília), cifrada com AES-256, e guarda por 30 dias.

1. Gere uma frase-senha longa (pelo menos 24 caracteres) e **guarde fora do GitHub**
   (gerenciador de senhas ou papel). Sem ela, nenhuma cópia pode ser aberta.
2. GitHub → repositório → **Settings** → **Secrets and variables** → **Actions** →
   **New repository secret**:
   * `FIN_DATABASE_ADMIN_URL`: o mesmo endereço do Neon;
   * `FIN_BACKUP_PASSPHRASE`: a frase-senha.
3. O GitHub só roda agendamentos que estão na branch principal (`main`). Enquanto o
   código estiver só na `desenvolvimento`, o backup diário não dispara.
4. Primeiro teste: aba **Actions** → **Backup do banco** → **Run workflow**. Ao final,
   a execução mostra o artefato `backup-cifrado-NUMERO`.

O repositório é público: por isso a cópia só sai do job cifrada, e o script confere
que ela tem dados antes de cifrar. O GitHub desliga agendamentos de repositório
público depois de 60 dias sem nenhum envio; se isso acontecer, ele avisa por e-mail e
basta reativar na aba Actions.

### Restaurar

1. No Neon: **Databases** → **New database** → nome `restaurado` (fica vazio).
2. Copie o endereço desse banco e salve no segredo `FIN_RESTORE_DATABASE_URL`.
3. Actions → **Restaurar backup** → **Run workflow**: número da execução do backup
   (fica na URL: `.../actions/runs/NUMERO`) e a palavra `RESTAURAR`.
4. O log mostra só quantas linhas cada tabela recebeu. O script recusa o banco de
   produção e qualquer banco que já tenha tabelas.
5. Para colocar em uso: no Render, troque `FIN_DATABASE_ADMIN_URL` pelo endereço do
   banco restaurado e salve (o app reinicia apontando para ele).

Testado em `backend/tests/db/test_backup_cifrado.py`: ida e volta com conteúdo idêntico,
arquivo sem texto aberto, frase-senha errada recusada, destino com tabelas recusado,
banco de produção recusado.

## Limites e riscos conhecidos

* **IP de quem acessa**: o app usa o último valor do `X-Forwarded-For`, o que o proxy do
  Render acrescenta. Se o Render mudar isso, o limite por endereço fica menos preciso; o
  limite por usuário (5 erros em 15 minutos) continua protegendo cada senha.
* **Dados nos EUA**: Render e Neon guardam os dados na Virgínia. Ver `PRIVACIDADE.md`.
* **Plano grátis pode mudar**: os limites acima foram conferidos em outubro de 2026.
