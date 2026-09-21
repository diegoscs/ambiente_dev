@echo off
cd /d D:\ambiente_dev\automacoes\001_check_github
SET mypath=%cd%

REM A chamada do pythonw.exe tem que ser a ULTIMA linha: qualquer comando depois
REM dela (REM inclusive) zera o ERRORLEVEL, e o Agendador passa a marcar como
REM sucesso uma execucao que terminou em erro.

C:\Users\ferna\AppData\Local\Python\bin\pythonw.exe %mypath%\001_check_github.py %* > NUL 2>&1
