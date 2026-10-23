# Cria (ou recria) a tarefa agendada do Windows que roda a ATUALIZACAO COMPLETA todos os dias as 08:00:
# SIGA (navegador oculto) + SGA + planilhas/Google Sheets + paineis + envio ao site (se configurado).
# Uso:  "Agendar atualizacao diaria.bat"  (ou este script, com -Hora 07:30 para outro horario)
# A tarefa aponta para esta pasta: rode de novo se o projeto mudar de lugar ou de computador.
#
# PRE-REQUISITOS para rodar sozinha, sem ninguem digitar:
#   - Credenciais do SIGA salvas uma vez (marque "Lembrar" na tela de atualizacao);
#   - API do SGA configurada em sistema\configuracao.env (ou relatorio do SGA na pasta ENTRADA);
#   - O computador ligado e com este usuario logado no horario marcado.

param([string]$Hora = "08:00")

$ErrorActionPreference = "Stop"
$sistema = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$raiz = Split-Path -Parent $sistema   # pasta "grupo support", onde fica integrar_atualizacao.py

# pythonw = sem janela; o resultado de cada execucao fica em sistema\logs.
$python = Join-Path $sistema "python\pythonw.exe"
if (-not (Test-Path $python)) {
    $python = (& py -c "import sys, os; print(os.path.join(os.path.dirname(sys.executable), 'pythonw.exe'))").Trim()
}
if (-not (Test-Path $python)) { throw "Python nao encontrado em sistema\python nem instalado na maquina." }

$acao = New-ScheduledTaskAction -Execute $python -Argument "integrar_atualizacao.py" -WorkingDirectory $raiz
$gatilho = New-ScheduledTaskTrigger -Daily -At $Hora
# StartWhenAvailable: se o computador estiver desligado no horario, roda assim que for ligado.
$opcoes = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Hours 2)

Register-ScheduledTask -TaskName "Sinistro - atualizar planilha" -Action $acao -Trigger $gatilho -Settings $opcoes `
    -Description "Atualizacao completa: SIGA + SGA, planilhas/Google Sheets, paineis e envio ao site." -Force | Out-Null

Write-Host "Tarefa agendada: todos os dias as $Hora (atualizacao completa SIGA + SGA)."
Write-Host "Programa: $python integrar_atualizacao.py"
Write-Host "Pasta:    $raiz"
Write-Host "Lembre-se: salve a senha do SIGA uma vez (marque 'Lembrar' na tela) para rodar sozinha."
Write-Host "O resultado de cada execucao fica em $sistema\logs e em $raiz\LOGS_SIGA_V3."
