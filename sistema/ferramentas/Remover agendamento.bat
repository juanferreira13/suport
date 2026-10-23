@echo off
rem Remove a tarefa agendada do Windows (use antes de apagar ou mover a pasta deste computador).
schtasks /Delete /TN "Sinistro - atualizar planilha" /F
echo.
pause
