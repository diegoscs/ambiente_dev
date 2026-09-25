# =============================================
# AUTOR        : Diego Candido
# DATA CRIACAO : 25/09/2026
# DESCRICAO    : Cria a tarefa unica dos robos do ambiente_dev, disparada
#                no LOGON. Substitui as duas tarefas por horario
#                ("001 - Check_GitHub" e "002 - Check_Supabase").
#
#   powershell -ExecutionPolicy Bypass -File criar_tarefa_robos.ps1
#
# NAO exige administrador. Essa e' a vantagem do gatilho de logon: a tarefa
# roda dentro da sua propria sessao, entao dispensa o LogonType S4U, o
# RunLevel Highest e a senha armazenada que as tarefas por horario pediam.
#
# StartWhenAvailable nao aparece aqui de proposito: ele so vale para gatilho
# de horario (recuperar execucao perdida). Com logon nao existe execucao
# perdida - ou voce logou, ou a maquina estava desligada.
#
# O atraso de 3 min existe porque no logon a rede ainda esta subindo, e os
# dois robos falham sem ela (API do GitHub, pooler do Supabase).
# =============================================

$ErrorActionPreference = "Stop"

$NOME_NOVO    = "ambiente_dev - Robos"
$TAREFAS_VELHAS = @("001 - Check_GitHub", "002 - Check_Supabase")

# --- 1. remove as tarefas por horario -------------------------------------
foreach ($velha in $TAREFAS_VELHAS) {
    $t = Get-ScheduledTask -TaskName $velha -ErrorAction SilentlyContinue
    if ($t) {
        try {
            Unregister-ScheduledTask -TaskName $velha -Confirm:$false
            Write-Host "[OK]   tarefa removida: $velha"
        } catch {
            Write-Warning "nao consegui remover '$velha' ($($_.Exception.Message))."
            Write-Warning "Rode este script como ADMINISTRADOR ou desative a tarefa na mao,"
            Write-Warning "senao ela continua disparando no horario antigo junto com a nova."
        }
    } else {
        Write-Host "[--]   nao existe (nada a remover): $velha"
    }
}

# --- 2. cria a tarefa unica no logon ---------------------------------------
$acao = New-ScheduledTaskAction `
    -Execute "D:\ambiente_dev\automacoes\iniciar_robos.bat" `
    -WorkingDirectory "D:\ambiente_dev\automacoes"

$gatilho = New-ScheduledTaskTrigger -AtLogOn -User "$env:COMPUTERNAME\$env:USERNAME"
$gatilho.Delay = "PT3M"   # ISO 8601: 3 minutos depois do logon

$principal = New-ScheduledTaskPrincipal `
    -UserId "$env:COMPUTERNAME\$env:USERNAME" -LogonType Interactive -RunLevel Limited

$config = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Hours 1) `
    -MultipleInstances IgnoreNew `
    -RestartInterval (New-TimeSpan -Minutes 10) `
    -RestartCount 3

Register-ScheduledTask `
    -TaskName $NOME_NOVO `
    -Description "Roda os robos 001 (check GitHub) e 002 (keepalive Supabase) a cada logon, com 3 min de atraso." `
    -Action $acao -Trigger $gatilho -Principal $principal -Settings $config -Force | Out-Null

Write-Host "[OK]   tarefa criada: $NOME_NOVO"

# --- 3. confere o que ficou gravado ----------------------------------------
Get-ScheduledTask -TaskName $NOME_NOVO |
    Select-Object TaskName, State,
        @{n="Logon";      e={$_.Principal.LogonType}},
        @{n="RunLevel";   e={$_.Principal.RunLevel}},
        @{n="Gatilho";    e={$_.Triggers[0].CimClass.CimClassName}},
        @{n="Atraso";     e={$_.Triggers[0].Delay}},
        @{n="Acao";       e={$_.Actions[0].Execute}} |
    Format-List
