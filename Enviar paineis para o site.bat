@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
set "PY=%~dp0sistema\python\python.exe"
title Grupo Support - Enviar paineis para o site
if exist "%PY%" goto rodar
rem Sem o Python da pasta: tenta o instalado na maquina.
where py >nul 2>nul && ( set "PY=py" & goto rodar )
where python >nul 2>nul && ( set "PY=python" & goto rodar )
echo ERRO: Python nao encontrado. Extraia o ZIP inteiro (pasta sistema\python).
pause
exit /b 9
:rodar
echo.
echo ================================================
echo   ENVIANDO OS PAINEIS PARA O SITE (VERCEL)
echo ================================================
"%PY%" "%~dp0enviar_para_vercel.py" %*
set "CODIGO=%errorlevel%"
echo.
if not "%CODIGO%"=="0" echo (terminou com erro - veja as mensagens acima)
pause
exit /b %CODIGO%
