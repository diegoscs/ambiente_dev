#!/bin/bash
# Monta o servidor Pixelmon do zero numa VM Ubuntu 24.04 nova (rodado uma vez,
# em 28/10/2026, na VM "pixelmon"). Roda com sudo, depois de enviar para /tmp:
#   /tmp/mods_pixelmon.tar   os mods de servidor (iguais aos do TLauncher)
# O Pixelmon (400 MB) vem direto do CurseForge, conferido pelo SHA-1 do jar
# que o TLauncher instalou. Depois disso, monitor e servicos sao os mesmos da
# VM do Create: publicar_vm.ps1 -Servidor pixelmon.
set -e

NEOFORGE=21.1.248          # o do "The Pixelmon Modpack 9.4.1" do TLauncher
PIXELMON_URL="https://mediafilez.forgecdn.net/files/8894/160/Pixelmon-1.21.1-9.4.1-universal.jar"
PIXELMON_SHA1=21ee5b13cfb5e387069dfc9d9f3772125471a820
LOGIN_URL="https://cdn.modrinth.com/data/S4Tu3Hn2/versions/dgFHnrmv/loginsystem-2.2.jar"
LOGIN_SHA1=959c4fbe8825561065595985f78513c85540d66e
GALERA="digoscs Marllonx12 Xxkadu03xX darak2610 watinha socasoca"
SRV=/opt/minecraft/server

export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq openjdk-21-jre-headless tmux python3-psycopg > /dev/null
id minecraft >/dev/null 2>&1 || useradd -r -m -d /opt/minecraft -s /bin/bash minecraft
install -d -o minecraft -g minecraft $SRV $SRV/mods /opt/minecraft/backups

cd $SRV
baixar() {  # url destino sha1
  curl -fsSL -o "$2" "$1"
  echo "$3  $2" | sha1sum -c --quiet
}
if [ ! -f "libraries/net/neoforged/neoforge/$NEOFORGE/unix_args.txt" ]; then
  curl -fsSL -o /tmp/neoforge-installer.jar \
    "https://maven.neoforged.net/releases/net/neoforged/neoforge/$NEOFORGE/neoforge-$NEOFORGE-installer.jar"
  java -jar /tmp/neoforge-installer.jar --installServer $SRV > /tmp/neoforge-install.log
  rm -f /tmp/neoforge-installer.jar run.bat
fi
[ -f mods/Pixelmon-1.21.1-9.4.1-universal.jar ] || baixar "$PIXELMON_URL" mods/Pixelmon-1.21.1-9.4.1-universal.jar $PIXELMON_SHA1
[ -f mods/loginsystem-2.2.jar ] || baixar "$LOGIN_URL" mods/loginsystem-2.2.jar $LOGIN_SHA1
tar -xf /tmp/mods_pixelmon.tar -C mods && rm -f /tmp/mods_pixelmon.tar

# 16 GB de maquina (e2-standard-4): 10 GB para o Java, o resto para o sistema.
cat > user_jvm_args.txt <<'EOF'
-Xms6G
-Xmx10G
-XX:+UseG1GC
-XX:MaxGCPauseMillis=130
-XX:+ParallelRefProcEnabled
-XX:+DisableExplicitGC
-XX:+AlwaysPreTouch
EOF
echo "eula=true" > eula.txt

# server.properties: so na primeira vez (a senha do RCON nao muda depois).
if [ ! -f server.properties ]; then
  cat > server.properties <<EOF
motd=Pixelmon da Galera
online-mode=false
white-list=true
enforce-whitelist=true
max-players=10
difficulty=normal
gamemode=survival
force-gamemode=true
allow-flight=true
spawn-protection=0
view-distance=8
simulation-distance=6
player-idle-timeout=10
enable-rcon=true
rcon.port=25575
rcon.password=$(openssl rand -hex 16)
broadcast-rcon-to-ops=false
enable-status=true
server-port=25565
EOF
fi

# whitelist/ops com o UUID offline (v3, md5 de "OfflinePlayer:"+nick), o que o
# TLauncher usa. "whitelist add" pegaria o UUID da conta original da Mojang.
python3 - $GALERA <<'EOF'
import hashlib, json, sys, uuid
def offline(nick):
    h = bytearray(hashlib.md5(f"OfflinePlayer:{nick}".encode()).digest())
    h[6] = (h[6] & 0x0F) | 0x30
    h[8] = (h[8] & 0x3F) | 0x80
    return str(uuid.UUID(bytes=bytes(h)))
galera = [{"uuid": offline(n), "name": n} for n in sys.argv[1:]]
json.dump(galera, open("whitelist.json", "w"), indent=2)
json.dump([{**galera[0], "level": 4, "bypassesPlayerLimit": False}], open("ops.json", "w"), indent=2)
EOF

chown -R minecraft:minecraft /opt/minecraft
echo "--- pronto"
ls mods
grep -c . whitelist.json
