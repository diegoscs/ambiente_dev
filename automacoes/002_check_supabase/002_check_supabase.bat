@echo off
cd /d D:\ambiente_dev\automacoes\002_check_supabase
SET mypath=%cd%

REM A chamada do pythonw.exe tem que ser a ULTIMA linha: qualquer comando depois
REM dela (REM inclusive) zera o ERRORLEVEL, e o Agendador passa a marcar como
REM sucesso uma execucao que terminou em erro.
REM
REM A saida vai para NUL porque o log da lib_dscs fica em memoria e so vira
REM arquivo quando a execucao falha (temp\erro_002_check_supabase_*.txt). Para
REM guardar TODA execucao em arquivo, troque a linha abaixo por:
REM
REM   C:\Users\ferna\AppData\Local\Python\bin\python.exe %mypath%\002_check_supabase.py %% >> %mypath%\temp\execucoes.txt 2>&1
REM
REM (python.exe, nao pythonw.exe - o pythonw nao tem stdout para redirecionar.)

C:\Users\ferna\AppData\Local\Python\bin\pythonw.exe %mypath%\002_check_supabase.py %* > NUL 2>&1
