# Envia o monitor para a VM e instala (ou atualiza). A VM precisa estar ligada.
#   powershell -File automacoes\minecraft_gcp\publicar_vm.ps1
# Leva: lib_dscs, monitor_minecraft.py, a pasta vm\ e um .env so com o que a
# VM usa (Supabase e DuckDNS). O .env fica em /opt/monitor/.env, legivel so
# pelo root.
# Sem $ErrorActionPreference = "Stop": no PowerShell 5.1 qualquer linha que o
# gcloud escreve no stderr (ele escreve muitas, normais) viraria erro fatal.
# O que vale e o codigo de saida de cada comando.
$raiz  = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$gcloud = "$env:LOCALAPPDATA\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd"
$alvo   = @("minecraft", "--zone=southamerica-east1-b", "--project=serverminecasaonly")
$ssh    = @("--tunnel-through-iap", "--quiet", "--strict-host-key-checking=no")
$tmp    = Join-Path $env:TEMP "publicar_vm"

New-Item -ItemType Directory -Force $tmp | Out-Null
try {
    Push-Location $raiz
    tar -czf "$tmp\monitor.tar.gz" --exclude=__pycache__ --exclude=temp `
        lib_dscs automacoes/monitor_minecraft/monitor_minecraft.py automacoes/minecraft_gcp/vm
    Pop-Location
    Get-Content (Join-Path $raiz ".env") |
        Where-Object { $_ -match '^(SUPABASE_URL|SUPABASE_KEY|DUCKDNS_TOKEN)=' } |
        Set-Content "$tmp\monitor.env" -Encoding ascii

    & $gcloud compute scp "$tmp\monitor.tar.gz" "$tmp\monitor.env" `
        (Join-Path $raiz "automacoes\minecraft_gcp\vm\instalar_monitor.sh") "$($alvo[0]):/tmp/" @($alvo[1..2]) @ssh 2>&1 |
        Where-Object { $_ -match "100%" }
    if ($LASTEXITCODE) { throw "envio para a VM falhou (codigo $LASTEXITCODE)" }
    & $gcloud compute ssh @alvo @ssh --command="sudo bash /tmp/instalar_monitor.sh" 2>&1 |
        ForEach-Object { "$_" } | Where-Object { $_ -notmatch "^\s*$|NativeCommandError" }
    if ($LASTEXITCODE) { throw "instalacao na VM falhou (codigo $LASTEXITCODE)" }
}
finally {
    Remove-Item -Recurse -Force $tmp   # o .env temporario nao fica no PC
}
