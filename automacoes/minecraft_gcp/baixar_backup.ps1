# Baixa para o PC o backup mais recente do mundo (Cloud Storage -> pasta local).
#   powershell -File automacoes\minecraft_gcp\baixar_backup.ps1
# Por que: os backups da VM ficam no mesmo projeto/conta de faturamento do
# servidor. Se a conta tiver problema (suspensao, fim do teste), eles vao
# junto. Uma copia no PC fica fora do Google. Guarda as 5 mais recentes.
$gcloud  = "$env:LOCALAPPDATA\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd"
$balde   = "gs://serverminecasaonly-backups"
$destino = (Resolve-Path (Join-Path $PSScriptRoot "..\minecraft-server")).Path + "\backups_nuvem"
$manter  = 5

New-Item -ItemType Directory -Force $destino | Out-Null
$ultimo = & $gcloud storage ls "$balde/world_*.tar.gz" 2>$null | Sort-Object | Select-Object -Last 1
if (-not $ultimo) { throw "nenhum backup encontrado em $balde" }
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

Get-ChildItem $destino -Filter "world_*.tar.gz" | Sort-Object Name | Select-Object -SkipLast $manter | Remove-Item
"Copias no PC: $destino"
Get-ChildItem $destino -Filter "world_*.tar.gz" | Sort-Object Name | ForEach-Object { "  {0}  {1:N1} MB" -f $_.Name, ($_.Length / 1MB) }
