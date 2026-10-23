@echo off
rem Abre o arquivo de configuracao (credenciais do SGA e caminhos) no Bloco de Notas.
start "" notepad "%~dp0..\configuracao.env"
