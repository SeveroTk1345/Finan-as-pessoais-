# Sobe o aplicativo no seu PC com Windows, para testar antes da nuvem.
# Requisitos: Docker Desktop aberto (ícone da baleia verde) e Git.
#
# Uso, no PowerShell, dentro da pasta do projeto:
#   powershell -ExecutionPolicy Bypass -File scripts\rodar-no-pc.ps1
#
# Pode rodar de novo quando quiser (por exemplo, depois de um "git pull"):
# os dados e as senhas são mantidos.
# Endereço: https://localhost (só neste computador).

function Passo([string]$texto) { Write-Host "`n==> $texto" -ForegroundColor Cyan }
function Falha([string]$texto) { Write-Host "`nERRO: $texto" -ForegroundColor Red; exit 1 }

$raiz = Split-Path -Parent $PSScriptRoot
$deploy = Join-Path $raiz "deploy"

Passo "1/5 Docker"
docker version --format "{{.Server.Version}}" *> $null
if ($LASTEXITCODE -ne 0) {
  Falha "o Docker não está rodando. Abra o Docker Desktop, espere aparecer 'Engine running' e rode de novo."
}
Write-Host "Docker ok."

Passo "2/5 Arquivos do projeto"
$initdb = Join-Path $deploy "initdb\01-papeis.sh"
if (-not (Test-Path $initdb)) { Falha "rode este script de dentro da pasta do projeto (financas)." }
if ([IO.File]::ReadAllText($initdb).Contains("`r")) {
  Falha "os scripts estão com fim de linha do Windows. Apague a pasta e clone de novo com: git clone -c core.autocrlf=false -b desenvolvimento https://github.com/SeveroTk1345/Finan-as-pessoais-.git financas"
}
Write-Host "Ok."

Passo "3/5 Configuração (deploy\.env)"
$arquivoEnv = Join-Path $deploy ".env"
function NovaSenha {
  # Hexadecimal: a senha entra no endereço do banco, onde / + = quebrariam.
  $bytes = New-Object byte[] 24
  $gerador = [Security.Cryptography.RandomNumberGenerator]::Create()
  $gerador.GetBytes($bytes)
  $gerador.Dispose()
  return -join ($bytes | ForEach-Object { $_.ToString("x2") })
}
if (Test-Path $arquivoEnv) {
  Write-Host "Já existe: mantido (as senhas do banco não podem mudar depois de criado)."
} else {
  $linhas = @(
    "FIN_DOMAIN=localhost",
    "FIN_DB_ADMIN_PASSWORD=$(NovaSenha)",
    "FIN_DB_APP_PASSWORD=$(NovaSenha)",
    "FIN_BACKUP_KEEP=14",
    "FIN_BACKUP_INTERVAL_SECONDS=86400",
    "FIN_BACKUP_HOST_DIR=./backups"
  )
  # Sem BOM e com LF: o Docker Compose lê melhor assim.
  [IO.File]::WriteAllText($arquivoEnv, (($linhas -join "`n") + "`n"), (New-Object Text.UTF8Encoding $false))
  Write-Host "Criado com senhas aleatórias (ninguém precisa saber delas)."
}
New-Item -ItemType Directory -Force (Join-Path $deploy "backups") | Out-Null

Passo "4/5 Construindo e subindo (a primeira vez leva de 5 a 15 minutos)"
Push-Location $deploy
docker compose up -d --build
$codigo = $LASTEXITCODE
if ($codigo -ne 0) {
  Pop-Location
  Falha "o Docker não conseguiu subir (veja a mensagem acima). Se ela fala da porta 80 ou 443, outro programa está usando (Skype, IIS): feche-o e rode de novo."
}

Passo "5/5 Esperando o site responder"
$pronto = $false
for ($i = 0; $i -lt 60; $i++) {
  curl.exe -fsSk --max-time 5 https://localhost/api/health *> $null
  if ($LASTEXITCODE -eq 0) { $pronto = $true; break }
  Start-Sleep -Seconds 5
}
if (-not $pronto) {
  docker compose ps
  Pop-Location
  Falha "o site não respondeu em 5 minutos. Veja os erros com: cd deploy; docker compose logs --tail 50 app caddy"
}
Pop-Location

Write-Host "`nPronto! Abra https://localhost no navegador." -ForegroundColor Green
Write-Host @"

O navegador vai avisar 'conexão não particular': é o certificado de teste deste PC.
Clique em Avançado e depois em Continuar para localhost.

Crie a sua conta (a senha é pedida sem aparecer na tela; mínimo 10 caracteres):
  cd deploy
  docker compose run --rm migrate python -m app.cli criar-usuario --usuario diogo --nome "Diogo"

Para desligar (os dados ficam guardados):  cd deploy; docker compose stop
Para ligar de novo:                          cd deploy; docker compose start
NUNCA use 'docker compose down -v': o -v apaga o banco.
"@
