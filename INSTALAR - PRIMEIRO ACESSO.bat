@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
title Integrador SIGA x SGA - Instalar
echo =============================================
echo    INSTALACAO - INTEGRADOR SIGA x SGA
echo    Grupo Support
echo =============================================
set "PY=%~dp0sistema\python\python.exe"
if not exist "%PY%" goto erro_python
"%PY%" -c "import openpyxl, playwright, requests, google.auth; print('Dependencias Python OK')"
if errorlevel 1 goto erro_dependencias
if not exist "%~dp0sistema\configuracao.env" copy /Y "%~dp0sistema\configuracao.exemplo.env" "%~dp0sistema\configuracao.env" >nul
if not exist "%~dp0sistema\dados" mkdir "%~dp0sistema\dados"
if not exist "%~dp0sistema\logs" mkdir "%~dp0sistema\logs"
if not exist "%~dp0ENTRADA" mkdir "%~dp0ENTRADA"
if not exist "%~dp0RESULTADOS" mkdir "%~dp0RESULTADOS"
if not exist "%~dp0LOGS_SIGA_V3" mkdir "%~dp0LOGS_SIGA_V3"
if not exist "%~dp0siga_automacao-v2\siga_automacao\entrada" mkdir "%~dp0siga_automacao-v2\siga_automacao\entrada"
if not exist "%~dp0siga_automacao-v2\siga_automacao\logs" mkdir "%~dp0siga_automacao-v2\siga_automacao\logs"
echo.
echo Criando o icone "Grupo Support - Atualizar SIGA"...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0sistema\ferramentas\criar_atalho.ps1"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0sistema\ferramentas\criar_atalho.ps1" -AreaDeTrabalho
echo.
echo Preparacao concluida.
echo.
echo 1. Precisa do Microsoft Edge (ja vem no Windows). O Google Chrome e opcional:
echo    paineis e planilhas abrem nele quando instalado.
echo 2. Opcional - API do SGA: rode sistema\ferramentas\Configurar.bat e preencha
echo    SGA_TOKEN, SGA_USUARIO e SGA_SENHA. Teste com "Testar acesso ao SGA.bat".
echo 3. Abra pelo icone "Grupo Support - Atualizar SIGA" (Area de Trabalho ou
echo    pasta do Integrador), informe login e senha do SIGA e clique em
echo    "Conectar e atualizar".
echo.
pause
exit /b 0
:erro_python
echo ERRO: Python portatil nao encontrado. Extraia a pasta completa.
goto falha
:erro_dependencias
echo ERRO: Instalacao Python incompleta. Extraia a pasta completa.
:falha
pause
exit /b 1
