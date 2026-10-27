@echo off
REM Abre o console do server na nuvem, como a janela do start.bat.
REM   - Comandos normais: whitelist add NICK, list, say oi, stop...
REM   - Sair do console SEM desligar o server: Ctrl+B, solta, e depois D.
REM     (Fechar esta janela no X tambem so sai do console; o server continua.)
REM   - Ctrl+C aqui DERRUBA o server (ele reinicia sozinho em 15 s).
REM A VM precisa estar ligada (botao Ligar do hub).
title Console - Minecraft na nuvem
set GCLOUD="%LOCALAPPDATA%\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd"
call %GCLOUD% compute ssh minecraft --project=serverminecasaonly --zone=southamerica-east1-b --tunnel-through-iap --strict-host-key-checking=no -- -t "sudo -u minecraft tmux attach -t mc"
pause
