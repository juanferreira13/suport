@echo off
rem Cria o atalho "Grupo Support - Atualizar SIGA" (icone oficial) na pasta acima de "grupo support".
rem Rode de novo sempre que a pasta do projeto mudar de lugar ou de computador.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0criar_atalho.ps1" %*
echo.
pause
