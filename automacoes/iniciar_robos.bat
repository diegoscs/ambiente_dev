@echo off
REM =============================================
REM AUTOR        : Diego Candido
REM DATA CRIACAO : 25/09/2026
REM DESCRICAO    : Ponto de entrada unico dos robos do ambiente_dev.
REM                Chamado pela tarefa "ambiente_dev - Robos" no logon.
REM
REM Roda os robos em sequencia. Cada um e' independente: se o 001 falhar,
REM o 002 roda do mesmo jeito. O codigo de saida do .bat e' 1 se QUALQUER
REM um deles falhou, 0 se todos terminaram bem - e' o que o Agendador mostra
REM na coluna "Resultado da ultima execucao".
REM
REM Os argumentos sao repassados aos dois robos (%*), o que permite testar a
REM cadeia inteira na mao sem efeito colateral:  iniciar_robos.bat --dry-run
REM
REM Os .bat filhos fazem o proprio "cd /d", por isso as chamadas aqui usam
REM caminho absoluto: depois do primeiro CALL o diretorio atual ja mudou.
REM =============================================

setlocal
set ERRO=0

call D:\ambiente_dev\automacoes\001_check_github\001_check_github.bat %*
if errorlevel 1 set ERRO=1

call D:\ambiente_dev\automacoes\002_check_supabase\002_check_supabase.bat %*
if errorlevel 1 set ERRO=1

endlocal & exit /b %ERRO%
