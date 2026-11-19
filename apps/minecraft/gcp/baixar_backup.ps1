# Baixa para o PC o backup mais recente de cada mundo (Create e Pixelmon),
# do Cloud Storage para a pasta local.
#   powershell -File apps\minecraft\gcp\baixar_backup.ps1
# Por que: os backups da VM ficam no mesmo projeto/conta de faturamento do
# servidor. Se a conta tiver problema (suspensao, fim do teste), eles vao
# junto. Uma copia no PC fica fora do Google. Guarda as 5 mais recentes de cada.
# Depois do encerramento (16/01/2027) o balde fica sem acesso: use o
# baixar_backup_github.ps1.
$gcloud   = "$env:LOCALAPPDATA\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd"
$balde    = "gs://serverminecasaonly-backups"
$destino  = (Resolve-Path (Join-Path $PSScriptRoot "..\local")).Path + "\backups_nuvem"
$manter   = 5
# Prefixo dos arquivos de cada servidor (PREFIXO_BACKUP do monitor_vm.py).
$prefixos = @("world", "pixelmon_world")

New-Item -ItemType Directory -Force $destino | Out-Null
foreach ($prefixo in $prefixos) {
    $ultimo = & $gcloud storage ls "$balde/${prefixo}_*.tar.gz" 2>$null | Sort-Object | Select-Object -Last 1
    if (-not $ultimo) { throw "nenhum backup ${prefixo}_* em $balde" }
    $nome = Split-Path $ultimo -Leaf
    $arquivo = Join-Path $destino $nome

    if (Test-Path $arquivo) {
        "Ja estava no PC: $nome"
    } else {
        & $gcloud storage cp $ultimo $arquivo 2>&1 | Out-Null
        if ($LASTEXITCODE -or -not (Test-Path $arquivo)) { throw "download falhou: $nome" }
        "Baixado: $nome ({0:N1} MB)" -f ((Get-Item $arquivo).Length / 1MB)
    }
    # Confere se o arquivo abre (lista o conteudo sem extrair).
    tar -tzf $arquivo | Out-Null
    if ($LASTEXITCODE) { throw "arquivo corrompido: $nome" }
    "Integridade ok: $((tar -tzf $arquivo | Measure-Object).Count) arquivos dentro"

    Get-ChildItem $destino -Filter "${prefixo}_*.tar.gz" | Sort-Object Name | Select-Object -SkipLast $manter | Remove-Item
}
"Copias no PC: $destino"
Get-ChildItem $destino -Filter "*.tar.gz" | Sort-Object Name | ForEach-Object { "  {0}  {1:N1} MB" -f $_.Name, ($_.Length / 1MB) }
