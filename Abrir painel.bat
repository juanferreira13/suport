@echo off
rem Abre o painel da conferencia de finalizados no navegador.
set "PAINEL=%~dp0RESULTADOS\CONFERENCIA FINALIZADOS.html"
if not exist "%PAINEL%" goto sempainel
start "" "%PAINEL%"
exit /b 0

:sempainel
echo O painel ainda nao foi gerado.
echo Rode "Atualizar agora" e abra de novo.
echo.
pause
exit /b 1
