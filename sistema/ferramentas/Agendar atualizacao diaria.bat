@echo off
rem Cria (ou recria) a tarefa do Windows que atualiza tudo todos os dias as 08:00.
rem Rode de novo sempre que a pasta do projeto mudar de lugar ou de computador.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0agendar_tarefa.ps1" %*
echo.
pause
