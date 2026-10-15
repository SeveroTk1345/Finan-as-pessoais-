# Implantação

**Situação atual:** a aplicação **não está publicada**. Tudo o que depende de uma conta externa (provedor de nuvem e domínio) precisa ser feito pelo Diogo; o Claude não cria contas nem aceita termos de serviços. O que já foi testado de verdade está no fim deste documento.

## Arquitetura de produção

```
iPhone / computador ──HTTPS──> Caddy (portas 80 e 443, certificado Let's Encrypt)
                                 └── app: FastAPI + site estático (mesma origem)
                                       └── db: PostgreSQL 16 (sem porta pública)
                                 backup: pg_dump diário com rotação
```

Tudo roda com `deploy/docker-compose.yml` em uma única máquina Linux.

## Opções de hospedagem gratuita

As condições dos provedores mudam com frequência. Antes de criar qualquer conta, leia as regras atuais na página oficial. Não habilite nada pago.

| Opção | Custo | Prós | Contras e riscos |
|---|---|---|---|
| **VM "Always Free" (ex.: Oracle Cloud)** — recomendada | R$ 0 dentro dos limites gratuitos | Máquina Linux completa, roda o Compose como está, 24h por dia | Cadastro pede cartão para verificação; regiões podem ficar sem capacidade gratuita; contas gratuitas inativas podem ter recursos recuperados pelo provedor; você cuida das atualizações do sistema |
| Outras nuvens com VM gratuita | R$ 0 dentro dos limites | Semelhante | Também pedem conta de faturamento com cartão; limites menores |
| Serviços gerenciados separados (site + API + banco em provedores diferentes) | R$ 0 com limitações | Menos manutenção | Origens diferentes quebram o login no Safari; serviços gratuitos costumam hibernar e alguns bancos gratuitos expiram ou pausam. **Não recomendado** |

**Regra de custo:** se o cadastro exigir cartão com risco de cobrança, configure alertas de orçamento em zero, não crie nada fora do "Always Free" e, em caso de dúvida, pare. A decisão de seguir é do Diogo.

## Domínio gratuito com HTTPS

O Caddy obtém o certificado sozinho; ele só precisa de um nome que aponte para o IP da VM:
* **Subdomínio gratuito** de um serviço de DNS dinâmico (ex.: `financas.duckdns.org`), ou
* **Nome baseado no IP** (ex.: `203-0-113-10.sslip.io`), sem cadastro.

Coloque o nome em `FIN_DOMAIN` no `.env`.

## Passo a passo na VM

1. Crie a VM (Ubuntu 24.04 ou equivalente) na camada gratuita. Libere **só** as portas 80 e 443 no firewall do provedor (e a 22 para SSH, de preferência só do seu IP).
2. Instale Docker e o plugin Compose (instruções oficiais do Docker para a distribuição).
3. Copie o projeto: `git clone https://github.com/SeveroTk1345/Finan-as-pessoais-.git financas && cd financas`
4. Configure:
   ```bash
   cd deploy
   cp ../.env.example .env
   nano .env   # troque FIN_DOMAIN e TODAS as senhas (openssl rand -base64 24)
   chmod 600 .env
   ```
5. Suba: `docker compose up -d --build`
6. Confira: `docker compose ps` (tudo `Up`/`healthy`) e abra `https://SEU_DOMINIO/api/health` (deve responder `{"status":"ok"}`).
7. Crie as três contas (a senha é pedida sem aparecer na tela):
   ```bash
   docker compose run --rm migrate python -m app.cli criar-usuario --usuario ana --nome "Ana"
   ```
   Repita para as outras duas pessoas. Entregue cada senha pessoalmente; peça que troquem em **Mais → Perfil e segurança**.
8. No iPhone, abra o endereço no Safari e siga o `GUIA_DO_USUARIO.md` para adicionar à Tela de Início.

## Operação

| Tarefa | Comando (dentro de `deploy/`) |
|---|---|
| Ver estado | `docker compose ps` |
| Ver erros da API | `docker compose logs --tail 100 app` |
| Backup agora | `docker compose exec backup /scripts/backup.sh` |
| Restaurar | ver `docs/BACKUP.md` |
| Redefinir senha de alguém | `docker compose run --rm migrate python -m app.cli redefinir-senha --usuario ana` |
| Desativar usuário | `docker compose run --rm migrate python -m app.cli desativar-usuario --usuario ana` |

**Nunca use `docker compose down -v`**: o `-v` apaga o volume do banco.

## Atualizar o sistema sem perder dados

1. Faça um backup: `docker compose exec backup /scripts/backup.sh`
2. Baixe a versão nova: `git pull`
3. Reconstrua e suba: `docker compose up -d --build`
   O serviço `migrate` aplica as migrações novas antes de a API subir. Se a migração falhar, a API antiga não é substituída.
4. Confira `https://SEU_DOMINIO/api/health` e entre no aplicativo.
5. Em problema: volte para a versão anterior (`git checkout <commit anterior>` e `docker compose up -d --build`) e, se necessário, restaure o backup do passo 1.

Os usuários veem o aviso "Nova versão disponível · Atualizar" no app.

## Cópia de segurança fora do servidor (pendente, D9)

Hoje os backups ficam em `deploy/backups/` na própria VM, fora do volume do banco. Para proteger contra a perda da VM, copie periodicamente para outro lugar. Opção sem custo e sem terceiros: baixar para o seu computador com
`scp usuario@SEU_IP:financas/deploy/backups/fin_*.dump* ./`
Antes de enviar para qualquer armazenamento em nuvem, cifre o arquivo (ex.: `age` ou `gpg`) e obtenha o consentimento das três pessoas.

## O que foi testado de verdade (neste ambiente de desenvolvimento)

Registrado em `REGISTRO_TESTES.md`:
* imagem Docker de produção construída;
* `docker compose up` com `FIN_DOMAIN=localhost` (certificado local do Caddy): HTTPS com HTTP/2, HSTS, CSP, cookie `Secure; HttpOnly; SameSite=Strict`, CSRF recusando outra origem, documentação da API desligada, apenas portas 80 e 443 publicadas;
* criação de usuário pela linha de comando, login e consulta pela API;
* dados e sessão preservados após `docker compose down` + `up`;
* backup automático gerado a cada subida.

**Não testado:** certificado real do Let's Encrypt (exige domínio público), funcionamento em VM de provedor de nuvem e uso no iPhone físico.
