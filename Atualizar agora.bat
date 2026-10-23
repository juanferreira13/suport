@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
set "PY=%~dp0sistema\python\python.exe"
set "PYW=%~dp0sistema\python\pythonw.exe"
title Grupo Support - Atualizar agora
if not exist "%PY%" goto falta_python
if not exist "%~dp0sistema\configuracao.env" goto falta_config
rem Padrao: abre a tela de atualizacao (login + barra de progresso), sem janela preta.
rem "Atualizar agora.bat --texto" roda no modo antigo, so neste terminal.
if /i "%~1"=="--texto" goto texto
start "" "%PYW%" "%~dp0atualizar_tela.py"
exit /b 0
:texto
echo.
echo ===========================================
echo   GRUPO SUPPORT - ATUALIZACAO SIGA V3
echo ===========================================
shift
"%PY%" "%~dp0integrar_atualizacao.py" %1 %2 %3 %4
set "CODIGO=%errorlevel%"
if not "%CODIGO%"=="0" goto falha
echo.
echo ATUALIZACAO CONCLUIDA.
pause
exit /b 0
:falta_python
echo ERRO: Python portatil ausente. Extraia o ZIP inteiro.
goto falha
:falta_config
echo ERRO: Execute INSTALAR - PRIMEIRO ACESSO.bat primeiro.
goto falha
:falha
echo.
echo FALHA: Confira as mensagens acima.
pause
exit /b 1
