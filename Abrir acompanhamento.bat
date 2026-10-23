@echo off
rem Abre no navegador a pagina de acompanhamento dos analistas.
set "PAGINA=%~dp0RESULTADOS\ACOMPANHAMENTO ANALISTAS.html"
if not exist "%PAGINA%" goto sempagina
start "" "%PAGINA%"
exit /b 0

:sempagina
echo A pagina de acompanhamento ainda nao foi gerada.
echo Rode "Atualizar agora" e abra de novo.
echo.
pause
exit /b 1
