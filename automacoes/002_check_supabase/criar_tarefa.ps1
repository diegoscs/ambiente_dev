# =============================================
# AUTOR        : Diego Candido
# DATA CRIACAO : 21/09/2026
# DESCRICAO    : Cria a tarefa do robo 002 no Agendador do Windows.
#                EXIGE PowerShell como ADMINISTRADOR - criar tarefa com
#                RunLevel Highest devolve "Acesso negado" em sessao comum.
#
#   powershell -ExecutionPolicy Bypass -File criar_tarefa.ps1
#
# A configuracao repete a que consertou o robo 001 em 15/09/2026:
#   LogonType S4U        -> roda sem o usuario estar logado
#   StartWhenAvailable   -> execucao perdida e recuperada, nao descartada
# Sem esses dois, a tarefa fica em silencio no dia em que ela mais importa.
# =============================================

$ErrorActionPreference = "Stop"

$acao = New-ScheduledTaskAction `
    -Execute "D:\ambiente_dev\automacoes\002_check_supabase\002_check_supabase.bat" `
    -WorkingDirectory "D:\ambiente_dev\automacoes\002_check_supabase"

$gatilho = New-ScheduledTaskTrigger -Daily -At 08:00

$principal = New-ScheduledTaskPrincipal `
    -UserId "$env:COMPUTERNAME\$env:USERNAME" -LogonType S4U -RunLevel Highest

$config = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Hours 1) `
    -MultipleInstances IgnoreNew `
    -RestartInterval (New-TimeSpan -Minutes 10) `
    -RestartCount 3

Register-ScheduledTask `
    -TaskName "002 - Check_Supabase" `
    -Description "Keepalive do projeto Supabase financas-pipeline (plano free)" `
    -Action $acao -Trigger $gatilho -Principal $principal -Settings $config -Force

Get-ScheduledTask -TaskName "002 - Check_Supabase" |
    Select-Object TaskName, State,
        @{n="Logon";e={$_.Principal.LogonType}},
        @{n="StartWhenAvailable";e={$_.Settings.StartWhenAvailable}}
