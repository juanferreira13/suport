@echo off
rem Roda um script de sistema\app com o Python que acompanha a pasta.
rem Uso:  rodar.bat executar.py [opcoes]
setlocal
set "SIS=%~dp0"
set "PY=%SIS%python\python.exe"
if exist "%PY%" goto rodar

rem Sem o Python da pasta: tenta o instalado na maquina (precisa do pacote openpyxl).
where py >nul 2>nul
if not errorlevel 1 ( set "PY=py" & goto rodar )
where python >nul 2>nul
if not errorlevel 1 ( set "PY=python" & goto rodar )
echo.
echo Nao encontrei o Python. A pasta "sistema\python" deveria acompanhar o projeto.
echo Copie de novo a pasta inteira do projeto, incluindo os itens ocultos.
exit /b 9

:rodar
cd /d "%SIS%app"
"%PY%" %*
exit /b %errorlevel%
