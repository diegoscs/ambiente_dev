#!/bin/bash
# Instala/atualiza o monitor na VM. Roda com sudo, depois de enviar:
#   /tmp/monitor.tar.gz  lib_dscs + apps/minecraft/monitor + apps/minecraft/gcp/vm (estrutura do repo)
#   /tmp/monitor.env     (opcional) SUPABASE_URL, SUPABASE_KEY, DUCKDNS_TOKEN
# Quem envia e o publicar_vm.ps1 do PC.
set -e

if ! python3 -c "import psycopg" 2>/dev/null; then
  apt-get update -qq
  DEBIAN_FRONTEND=noninteractive apt-get install -y -qq python3-psycopg > /dev/null
fi

mkdir -p /opt/monitor
tar -xzf /tmp/monitor.tar.gz -C /opt/monitor
if [ -f /tmp/monitor.env ]; then
  install -m 600 -o root -g root /tmp/monitor.env /opt/monitor/.env
  rm -f /tmp/monitor.env
fi
chown -R root:root /opt/monitor
chmod 700 /opt/monitor
rm -f /tmp/monitor.tar.gz

VM=/opt/monitor/apps/minecraft/gcp/vm
install -m 755 -o minecraft -g minecraft "$VM/iniciar.sh" /opt/minecraft/iniciar.sh
install -m 644 "$VM/minecraft.service" /etc/systemd/system/minecraft.service
install -m 644 "$VM/monitor-minecraft.service" /etc/systemd/system/monitor-minecraft.service
install -m 644 "$VM/monitor-minecraft.timer" /etc/systemd/system/monitor-minecraft.timer
# Atualizacao automatica nao pode reiniciar o servidor no meio do jogo.
install -d /etc/needrestart/conf.d
install -m 644 "$VM/needrestart-minecraft.conf" /etc/needrestart/conf.d/minecraft.conf
systemctl daemon-reload
systemctl enable --now monitor-minecraft.timer
# Estrutura antiga do repo (ate 02/11/2026); os servicos ja apontam para apps/.
rm -rf /opt/monitor/automacoes

echo "--- instalado"
ls -la /opt/monitor/.env | awk '{print $1, $3, $NF}'
systemctl is-enabled minecraft monitor-minecraft.timer
python3 -c "import psycopg; print('psycopg', psycopg.__version__)"
perl -c /etc/needrestart/conf.d/minecraft.conf 2>&1 | sed 's/^/needrestart: /'
grep -h 'Automatic-Reboot "' /etc/apt/apt.conf.d/*unattended* 2>/dev/null | sed 's/^/reboot automatico: /'
