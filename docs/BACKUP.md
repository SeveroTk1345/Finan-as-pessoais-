# Backup e restauração

## O que é copiado
O banco inteiro (dados das três pessoas, esquema, políticas de RLS e permissões), com `pg_dump` em formato custom. Os papéis do servidor (`fin_admin`, `fin_app`) **não** fazem parte da cópia: são recriados pelo `deploy/initdb/01-papeis.sh` em um servidor novo.

## Como funciona
* O serviço `backup` do `deploy/docker-compose.yml` faz uma cópia ao subir e depois a cada `FIN_BACKUP_INTERVAL_SECONDS` (padrão: 86400 s, 1 dia).
* Cada cópia gera `fin_AAAAMMDDTHHMMSSZ_PID.dump` e um `.sha256`. A hora é UTC.
* A cópia só é gravada com o nome final depois de o `pg_restore --list` conseguir ler o arquivo inteiro. Arquivo incompleto não fica na pasta.
* Ficam as `FIN_BACKUP_KEEP` cópias mais recentes (padrão 14). As mais antigas são apagadas.
* Os arquivos são criados com permissão 600 (só o dono lê).

Cópia manual a qualquer momento:
```bash
cd deploy && docker compose exec backup /scripts/backup.sh
```

## Restauração
A restauração **sempre cria um banco novo**. Ela nunca sobrescreve o banco em uso.

```bash
cd deploy
docker compose exec -e PGDATABASE=postgres backup \
  /scripts/restore.sh /backups/fin_20261015T013634Z_20.dump financas_restaurado
```

O script:
1. confere o SHA-256 (arquivo alterado ou corrompido é recusado);
2. recusa se o banco de destino já existir;
3. confere se o papel `fin_app` existe;
4. restaura em transação única e, se falhar, apaga o banco parcial;
5. aplica as mesmas permissões de conexão do banco original.

### Colocar o banco restaurado em uso
1. Confira os dados no banco restaurado (contagem de registros, últimos lançamentos).
2. Pare a API.
3. Renomeie os bancos com o administrador:
   ```sql
   ALTER DATABASE financas RENAME TO financas_antigo;
   ALTER DATABASE financas_restaurado RENAME TO financas;
   ```
4. Suba a API e confira o acesso.
5. Mantenha `financas_antigo` até ter certeza de que está tudo certo.

### Recuperação em um servidor novo
1. Suba o `docker compose` com as mesmas variáveis do `.env` (isso cria `fin_app`).
2. Copie o `.dump` e o `.sha256` para a pasta de backups.
3. Rode o `restore.sh` como acima, apontando para um nome novo, e siga os passos de "Colocar em uso".

## Testes que comprovam o funcionamento
Em `backend/tests/db/test_backup_restore.py`, executados contra um PostgreSQL 16 real:
* cópia completa e restauração com **conteúdo idêntico** (contagem e hash MD5 de todas as linhas de cada tabela), RLS e políticas preservadas, e isolamento entre os três usuários funcionando no banco restaurado;
* arquivo corrompido recusado sem criar banco;
* falta do `.sha256` recusada;
* banco existente nunca sobrescrito;
* nomes de banco inválidos recusados;
* falha no meio da restauração remove o banco parcial;
* falha de conexão no backup não deixa arquivo;
* rotação mantém só as cópias mais recentes e não apaga outros arquivos.

Além disso, o fluxo completo foi executado com o `docker compose` real (registrado em `REGISTRO_TESTES.md`).

## No Render + Neon
Cópia diária cifrada (AES-256) pelo GitHub Actions, guardada por 30 dias, e restauração em banco vazio por workflow manual: `scripts/backup-cifrado.sh`, `scripts/restaurar-cifrado.sh`, `.github/workflows/backup.yml` e `restaurar.yml`. Passo a passo em `IMPLANTACAO_RENDER.md` (passo 6). Isso resolve a cópia externa e a cifra para esse caminho.

## Pendências (servidor próprio)
* **Cópia fora do servidor (D9).** Hoje as cópias ficam no mesmo servidor do banco, em pasta separada do volume do banco. Isso protege contra erro humano e corrupção do banco, mas **não** contra perda do servidor. Falta escolher o destino externo; nada pago será habilitado sem autorização.
* **Criptografia da cópia.** Será aplicada junto com o destino externo.
* **Exportação individual por usuário (P2)** entra na etapa de exportação de dados.
