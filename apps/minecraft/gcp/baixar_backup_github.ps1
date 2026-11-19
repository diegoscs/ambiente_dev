# Baixa e abre o backup dos mundos que o workflow minecraft_fim_creditos.yml
# guardou num release do GitHub (fora do Google). Serve depois do fim dos
# creditos, quando o Cloud Storage fica sem acesso.
#   powershell -File apps\minecraft\gcp\baixar_backup_github.ps1
#   powershell -File apps\minecraft\gcp\baixar_backup_github.ps1 -Tag backup-minecraft-2027-01-17
# Os arquivos estao criptografados (o repositorio e publico e o backup leva as
# senhas do Login System). A senha e MINECRAFT_BACKUP_SENHA no .env da raiz.
param([string]$Tag)

$raiz    = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
$destino = (Resolve-Path (Join-Path $PSScriptRoot "..\local")).Path + "\backups_nuvem"
$gpg     = "$env:ProgramFiles\Git\usr\bin\gpg.exe"   # vem com o Git para Windows
if (-not (Test-Path $gpg)) { throw "gpg nao encontrado em $gpg (instale o Git para Windows)" }

$linha = Get-Content (Join-Path $raiz ".env") | Where-Object { $_ -match '^\s*MINECRAFT_BACKUP_SENHA\s*=' } | Select-Object -First 1
if (-not $linha) { throw "MINECRAFT_BACKUP_SENHA nao esta no .env da raiz" }
$senha = ($linha -split '=', 2)[1].Trim().Trim('"')

if (-not $Tag) {
    $Tag = gh release list --repo diegoscs/ambiente_dev --limit 100 --json tagName --jq '.[].tagName' |
        Where-Object { $_ -like "backup-minecraft-*" } | Sort-Object | Select-Object -Last 1
    if (-not $Tag) { throw "nenhum release backup-minecraft-* no GitHub" }
}
$pasta = Join-Path $destino $Tag
New-Item -ItemType Directory -Force $pasta | Out-Null
"Baixando $Tag para $pasta"
gh release download $Tag --repo diegoscs/ambiente_dev --dir $pasta --clobber
if ($LASTEXITCODE) { throw "download do release falhou" }

# Arquivo acima de 1,9 GB veio em partes (.gpg.parte00, .parte01...): junta antes.
Get-ChildItem $pasta -Filter "*.gpg.parte00" | ForEach-Object {
    $inteiro = $_.FullName -replace '\.parte00$', ''
    $partes = Get-ChildItem $pasta -Filter "$([IO.Path]::GetFileName($inteiro)).parte*" | Sort-Object Name
    $saida = [IO.File]::Create($inteiro)
    foreach ($p in $partes) { $entrada = [IO.File]::OpenRead($p.FullName); $entrada.CopyTo($saida); $entrada.Close() }
    $saida.Close()
    $partes | Remove-Item
}

# Senha por arquivo: o pipe do PowerShell 5.1 poe CR+LF no fim e o gpg leria o CR.
$arqSenha = Join-Path $env:TEMP "mc_backup_senha.txt"
[IO.File]::WriteAllText($arqSenha, $senha)
try {
  Get-ChildItem $pasta -Filter "*.tar.gz.gpg" | ForEach-Object {
    $tar = $_.FullName -replace '\.gpg$', ''
    & $gpg --batch --yes --quiet --pinentry-mode loopback --passphrase-file $arqSenha -o $tar --decrypt $_.FullName
    if ($LASTEXITCODE) { throw "nao abriu $($_.Name): senha errada ou arquivo incompleto" }
    tar -tzf $tar | Out-Null
    if ($LASTEXITCODE) { throw "arquivo corrompido: $(Split-Path $tar -Leaf)" }
    Remove-Item $_.FullName
    "Ok: {0} ({1:N1} MB)" -f (Split-Path $tar -Leaf), ((Get-Item $tar).Length / 1MB)
  }
} finally { Remove-Item $arqSenha -ErrorAction SilentlyContinue }
"Pronto: $pasta"
