#!/bin/bash
# Equivalente do start.bat na VM: sobe o server e, se cair, reinicia em 15 s.
# Parado com "stop" (codigo 0) -> sai, e o servico termina.
# Roda dentro do tmux (sessao "mc") com o usuario minecraft; quem chama e o
# minecraft.service. O backup sai quando o servidor para (ExecStopPost do
# servico), com o mundo ja salvo, e vai para o Cloud Storage.
cd /opt/minecraft/server || exit 1
# A versao do NeoForge muda por servidor (Create 21.1.229, Pixelmon 21.1.248):
# vale a que estiver instalada (a mais nova, se houver mais de uma).
ARGS=$(ls -d libraries/net/neoforged/neoforge/*/unix_args.txt | sort -V | tail -1)

while true; do
  echo "[$(date '+%F %T')] Iniciando servidor..."
  java @user_jvm_args.txt "@$ARGS" nogui
  codigo=$?

  if [ "$codigo" -eq 0 ]; then
    echo "[$(date '+%F %T')] Servidor parado com stop. Saindo."
    exit 0
  fi
  echo "[$(date '+%F %T')] Servidor caiu (codigo $codigo). Reiniciando em 15 s... (Ctrl+B e depois D para sair do console)"
  sleep 15
done
