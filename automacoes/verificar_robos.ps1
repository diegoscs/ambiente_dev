# =============================================
# AUTOR        : Diego Candido
# DATA CRIACAO : 25/09/2026
# DESCRICAO    : Responde "os robos rodaram, e como terminaram?" numa tela so.
#
#   powershell -ExecutionPolicy Bypass -File verificar_robos.ps1
#
# Existe por causa da licao que se repetiu nos dois robos: robo que NAO roda
# nao escreve log, nao muda status e nao dispara alerta - o silencio dele e
# identico ao do sucesso. Por isso aqui nada e' deduzido de "nao ha erro":
# cada linha mostra um carimbo de hora, e o veredito compara esses carimbos
# com a ultima execucao da tarefa.
# =============================================

$TAREFA = "ambiente_dev - Robos"
$PY     = "C:\Users\ferna\AppData\Local\Python\bin\python.exe"
$BASE   = "D:\ambiente_dev"

$problemas = @()

# --- 1. o Agendador chamou? ------------------------------------------------
Write-Host "`n=== AGENDADOR ===" -ForegroundColor Cyan
$tarefa = Get-ScheduledTask -TaskName $TAREFA -ErrorAction SilentlyContinue
if (-not $tarefa) {
    Write-Host "  tarefa '$TAREFA' NAO EXISTE" -ForegroundColor Red
    $problemas += "tarefa ausente"
    $ultimaExec = $null
} else {
    # pelo pipe do objeto: "Get-ScheduledTaskInfo -TaskName" nao acha a tarefa
    # quando ela esta na raiz sem TaskPath explicito.
    $info = $tarefa | Get-ScheduledTaskInfo
    $boot = (Get-CimInstance Win32_OperatingSystem).LastBootUpTime
    $ultimaExec = $info.LastRunTime

    Write-Host ("  boot da maquina : {0}" -f $boot)
    Write-Host ("  ultima execucao : {0}" -f $ultimaExec)
    Write-Host ("  resultado       : {0}" -f $info.LastTaskResult)
    Write-Host ("  estado          : {0}" -f $tarefa.State)

    if ($info.LastTaskResult -ne 0) {
        Write-Host "  -> o .bat terminou em ERRO" -ForegroundColor Red
        $problemas += "LastTaskResult = $($info.LastTaskResult)"
    }
    # execucao anterior ao boot = o gatilho de logon nao disparou nesta sessao
    if ($ultimaExec -lt $boot) {
        Write-Host "  -> NAO rodou nesta sessao (ultima execucao e' anterior ao boot)" -ForegroundColor Yellow
        Write-Host "     se voce logou ha menos de 3 min, e' so o atraso do gatilho - espere e rode de novo"
        $problemas += "sem execucao apos o boot"
    }
}

# --- 2. o que os robos gravaram na tabela de controle ----------------------
Write-Host "`n=== CONTROLE DE CARGAS (Postgres local) ===" -ForegroundColor Cyan
$sql = @"
import sys
sys.path.insert(0, r'$BASE')
from lib_dscs.banco import conexao
with conexao() as c:
    cur = c.cursor()
    cur.execute('select id_carga, nome_carga, status, dta_fim, now() - dta_fim from dbo.controle_cargas order by id_carga')
    for id_carga, nome, status, fim, idade in cur.fetchall():
        h = idade.total_seconds() / 3600 if idade else -1
        alerta = '  <-- ATRASADO' if h > 48 or h < 0 else ''
        quando = f'{fim:%d/%m %H:%M:%S}' if fim else 'nunca'
        print(f'  id={id_carga}  {nome:22s} {status or \"-\":8s} fim={quando}{alerta}')
"@
& $PY -c $sql
if ($LASTEXITCODE -ne 0) {
    Write-Host "  nao consegui ler a tabela (o Postgres local esta no ar?)" -ForegroundColor Red
    $problemas += "leitura da controle_cargas falhou"
}

# --- 3. a trava diaria do 001 ---------------------------------------------
Write-Host "`n=== ROBO 001 - trava do dia (UTC) ===" -ForegroundColor Cyan
$estado = Join-Path $BASE "automacoes\001_check_github\temp\estado.json"
if (Test-Path $estado) {
    $e = Get-Content $estado -Raw | ConvertFrom-Json
    $hojeUtc = (Get-Date).ToUniversalTime().ToString("yyyy-MM-dd")
    Write-Host ("  ultimo dia processado : {0}" -f $e.ultima_execucao)
    Write-Host ("  commits naquele dia   : {0}" -f $e.commits)
    Write-Host ("  hoje em UTC           : {0}" -f $hojeUtc)
    if ($e.ultima_execucao -eq $hojeUtc) {
        Write-Host "  -> o dia de hoje ja foi preenchido" -ForegroundColor Green
    } else {
        Write-Host "  -> hoje ainda NAO foi preenchido (roda no proximo logon)" -ForegroundColor Yellow
    }
} else {
    Write-Host "  estado.json ausente - o robo nunca rodou" -ForegroundColor Yellow
}

# --- 4. arquivo de erro mais novo que a ultima execucao -------------------
Write-Host "`n=== ARQUIVOS DE ERRO ===" -ForegroundColor Cyan
$padrao = Join-Path $BASE "automacoes\*\temp\erro_*.txt"
$todos = @(Get-ChildItem $padrao -ErrorAction SilentlyContinue)
if ($ultimaExec) {
    $novos = @($todos | Where-Object { $_.LastWriteTime -ge $ultimaExec })
} else {
    $novos = $todos
}
$antigos = @($todos | Where-Object { $novos -notcontains $_ })

if ($novos.Count -gt 0) {
    foreach ($f in $novos) {
        Write-Host ("  {0}  {1}" -f $f.LastWriteTime, $f.Name) -ForegroundColor Red
    }
    $problemas += "$($novos.Count) arquivo(s) de erro nesta execucao"
} else {
    Write-Host "  nenhum nesta execucao" -ForegroundColor Green
}
if ($antigos.Count -gt 0) {
    Write-Host ("  ({0} antigo(s), de falhas ja resolvidas - nao contam como problema)" -f $antigos.Count) -ForegroundColor DarkGray
}

# --- 5. veredito -----------------------------------------------------------
Write-Host "`n=== VEREDITO ===" -ForegroundColor Cyan
if ($problemas.Count -eq 0) {
    Write-Host "  tudo certo`n" -ForegroundColor Green
    exit 0
} else {
    foreach ($p in $problemas) { Write-Host "  - $p" -ForegroundColor Red }
    Write-Host ""
    exit 1
}
