# Cria (ou recria) as tarefas do Agendador do monitor do Minecraft:
#  - "Monitor Minecraft (hub)": o monitor, a cada minuto, com pythonw (sem janela)
#  - "Minecraft Server (hub)":  sob demanda, abre o server quando o hub pede "Ligar"
# As duas so com o usuario logado, como o proprio server.
# Remover: Unregister-ScheduledTask -TaskName "Monitor Minecraft (hub)", "Minecraft Server (hub)" -Confirm:$false
$ErrorActionPreference = "Stop"

$nome    = "Monitor Minecraft (hub)"
$pythonw = "C:\Users\ferna\AppData\Local\Python\bin\pythonw.exe"
$script  = Join-Path $PSScriptRoot "monitor_minecraft.py"

$acao = New-ScheduledTaskAction -Execute $pythonw -Argument "`"$script`"" -WorkingDirectory $PSScriptRoot

# Comeca agora e repete a cada minuto; o gatilho de logon cobre o PC reiniciado.
$agora = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 1)
$logon = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$logon.Repetition = $agora.Repetition

$config = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable `
    -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 2)

Register-ScheduledTask -TaskName $nome -Action $acao -Trigger $agora, $logon -Settings $config `
    -Description "Status e chat do server de Minecraft para o hub (D:\ambiente_dev\apps\minecraft\monitor)" `
    -Force | Out-Null

# ─── tarefa sob demanda do server (botao "Ligar" do hub) ───
# Sem gatilho: so roda quando o monitor chama schtasks /run. Abre o start.bat
# na janela de sempre, com o usuario logado.
# - ExecutionTimeLimit zero: o padrao do Agendador mata a tarefa em 72 h.
# - Priority 4 (normal): o padrao de tarefa e 7, abaixo do normal, e o server
#   ficaria mais lento que aberto na mao.
$server = "Minecraft Server (hub)"
$bat    = (Resolve-Path (Join-Path $PSScriptRoot "..\local\server\start.bat")).Path

$acaoServer   = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c `"$bat`"" -WorkingDirectory (Split-Path $bat)
$configServer = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -MultipleInstances IgnoreNew -ExecutionTimeLimit ([TimeSpan]::Zero) -Priority 4

Register-ScheduledTask -TaskName $server -Action $acaoServer -Settings $configServer `
    -Description "Abre o server de Minecraft (start.bat). Disparada pelo botao Ligar do hub, via monitor_minecraft." `
    -Force | Out-Null

Get-ScheduledTask -TaskName $nome, $server | Select-Object TaskName, State
