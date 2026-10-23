@echo off
rem Testa as credenciais da API do SGA e mostra o que ela devolve. Nao grava planilhas.
chcp 65001 >nul
title Sinistro - teste de acesso ao SGA
call "%~dp0..\rodar.bat" atualizar_sga.py --diagnostico
echo.
pause
