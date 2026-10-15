#!/usr/bin/env bash
# Instala e sobe o aplicativo numa VM Ubuntu nova (ex.: Oracle Cloud "Always Free").
#
# Uso (na VM, como o usuário padrão "ubuntu"):
#   curl -fsSL https://raw.githubusercontent.com/SeveroTk1345/Finan-as-pessoais-/desenvolvimento/scripts/instalar-servidor.sh -o instalar.sh
#   bash instalar.sh financas-ana.duckdns.org
#
# O que faz, nesta ordem (pode rodar de novo sem estragar nada):
#   1. instala Docker e Git (repositório oficial do Docker);
#   2. cria memória virtual (swap) se a máquina tiver menos de 2 GB de RAM;
#   3. libera as portas 80 e 443 no firewall interno da VM (as imagens da Oracle bloqueiam);
#   4. baixa o projeto (branch desenvolvimento) em ~/financas;
#   5. cria deploy/.env com senhas aleatórias (só na primeira vez; nunca sobrescreve);
#   6. confere se o domínio aponta para esta máquina;
#   7. constrói e sobe tudo e espera o https://DOMINIO/api/health responder.
set -euo pipefail

REPO="https://github.com/SeveroTk1345/Finan-as-pessoais-.git"
BRANCH="desenvolvimento"
DIR="$HOME/financas"

passo() { printf '\n\033[1m==> %s\033[0m\n' "$*"; }
falha() { printf '\n\033[1;31mERRO: %s\033[0m\n' "$*" >&2; exit 1; }

DOMAIN="${1:-}"
if [ -z "$DOMAIN" ]; then
  read -r -p "Domínio do app (ex.: financas-ana.duckdns.org): " DOMAIN
fi
DOMAIN="$(printf '%s' "$DOMAIN" | tr '[:upper:]' '[:lower:]' | tr -d '[:space:]')"
printf '%s' "$DOMAIN" | grep -Eq '^([a-z0-9]([a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,}$' \
  || falha "domínio inválido: '$DOMAIN'. Use só o nome, sem https:// e sem barra."

[ -r /etc/os-release ] && . /etc/os-release
[ "${ID:-}" = "ubuntu" ] || falha "este script foi feito para Ubuntu (encontrado: ${ID:-desconhecido})."

passo "1/7 Docker e Git"
if ! command -v docker > /dev/null 2>&1; then
  sudo apt-get update -y
  sudo apt-get install -y ca-certificates curl git openssl
  sudo install -m 0755 -d /etc/apt/keyrings
  sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  sudo chmod a+r /etc/apt/keyrings/docker.asc
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu ${UBUNTU_CODENAME:-$VERSION_CODENAME} stable" \
    | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
  sudo apt-get update -y
  sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
  sudo usermod -aG docker "$USER"
else
  echo "Docker já instalado."
  command -v git > /dev/null 2>&1 || sudo apt-get install -y git
fi

passo "2/7 Memória"
MEM_MB=$(awk '/MemTotal/ {print int($2/1024)}' /proc/meminfo)
if [ "$MEM_MB" -lt 2000 ] && ! swapon --show | grep -q '/swapfile'; then
  echo "RAM: ${MEM_MB} MB. Criando 2 GB de swap para a construção do site não faltar memória."
  sudo fallocate -l 2G /swapfile
  sudo chmod 600 /swapfile
  sudo mkswap /swapfile > /dev/null
  sudo swapon /swapfile
  grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab > /dev/null
else
  echo "RAM: ${MEM_MB} MB. Ok."
fi

passo "3/7 Portas 80 e 443 no firewall da VM"
if ! sudo iptables -C INPUT -p tcp -m multiport --dports 80,443 -m conntrack --ctstate NEW -j ACCEPT 2> /dev/null; then
  sudo iptables -I INPUT 1 -p tcp -m multiport --dports 80,443 -m conntrack --ctstate NEW -j ACCEPT
fi
if command -v netfilter-persistent > /dev/null 2>&1; then
  sudo netfilter-persistent save > /dev/null
else
  echo "iptables-persistent iptables-persistent/autosave_v4 boolean true" | sudo debconf-set-selections
  echo "iptables-persistent iptables-persistent/autosave_v6 boolean true" | sudo debconf-set-selections
  sudo apt-get update -y > /dev/null
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y iptables-persistent > /dev/null
  sudo netfilter-persistent save > /dev/null
fi
echo "Liberadas. Lembre: na Oracle também é preciso liberar 80 e 443 na 'Security List' da rede."

passo "4/7 Projeto"
if [ -d "$DIR/.git" ]; then
  git -C "$DIR" fetch --quiet origin "$BRANCH"
  git -C "$DIR" checkout --quiet "$BRANCH"
  git -C "$DIR" pull --quiet --ff-only origin "$BRANCH"
else
  git clone --quiet -b "$BRANCH" "$REPO" "$DIR"
fi
echo "Versão: $(git -C "$DIR" log --oneline -1)"

passo "5/7 Configuração (deploy/.env)"
ENV_FILE="$DIR/deploy/.env"
if [ -f "$ENV_FILE" ]; then
  echo "Já existe: mantido (as senhas do banco não podem mudar depois de criado)."
  grep -q "^FIN_DOMAIN=$DOMAIN\$" "$ENV_FILE" || {
    sed -i "s/^FIN_DOMAIN=.*/FIN_DOMAIN=$DOMAIN/" "$ENV_FILE"
    echo "Domínio atualizado para $DOMAIN."
  }
else
  umask 077
  # Hexadecimal: as senhas entram em URLs do banco, onde "/", "+" e "=" quebrariam.
  cat > "$ENV_FILE" << EOF
FIN_DOMAIN=$DOMAIN
FIN_DB_ADMIN_PASSWORD=$(openssl rand -hex 24)
FIN_DB_APP_PASSWORD=$(openssl rand -hex 24)
FIN_BACKUP_KEEP=14
FIN_BACKUP_INTERVAL_SECONDS=86400
FIN_BACKUP_HOST_DIR=./backups
EOF
  chmod 600 "$ENV_FILE"
  echo "Criado com senhas aleatórias (ninguém precisa saber delas)."
fi
mkdir -p "$DIR/deploy/backups"

passo "6/7 O domínio aponta para esta máquina?"
MY_IP="$(curl -fsS --max-time 10 https://api.ipify.org || true)"
DNS_IP="$(getent ahostsv4 "$DOMAIN" | awk 'NR==1 {print $1}' || true)"
echo "IP desta máquina: ${MY_IP:-desconhecido} · $DOMAIN aponta para: ${DNS_IP:-nada}"
if [ -n "$MY_IP" ] && [ "$MY_IP" != "$DNS_IP" ]; then
  falha "o domínio ainda não aponta para esta máquina. No DuckDNS, coloque o IP $MY_IP em '$DOMAIN', espere 1 minuto e rode de novo."
fi

passo "7/7 Construindo e subindo (a primeira vez leva de 5 a 15 minutos)"
cd "$DIR/deploy"
sudo docker compose up -d --build
echo "Esperando o HTTPS ficar pronto..."
for _ in $(seq 1 60); do
  if curl -fsS --max-time 5 "https://$DOMAIN/api/health" > /dev/null 2>&1; then
    printf '\n\033[1;32mPronto! O app está no ar em https://%s\033[0m\n' "$DOMAIN"
    cat << EOF

Próximo passo: criar as contas (a senha é pedida sem aparecer na tela):
  cd ~/financas/deploy
  sudo docker compose run --rm migrate python -m app.cli criar-usuario --usuario ana --nome "Ana"
EOF
    exit 0
  fi
  sleep 5
done
sudo docker compose ps
falha "o site não respondeu em 5 minutos. Veja: sudo docker compose logs --tail 50 caddy app"
