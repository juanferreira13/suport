# Cria (ou recria) a tarefa agendada do Windows que roda a rotina todos os dias as 08:00.
# Uso:  "Agendar atualizacao diaria.bat"  (ou este script, com -Hora 07:30 para outro horario)
# A tarefa aponta para esta pasta: rode de novo se o projeto mudar de lugar ou de computador.

param([string]$Hora = "08:00")

$ErrorActionPreference = "Stop"
$sistema = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$app = Join-Path $sistema "app"

# pythonw = sem janela; o resultado de cada execucao fica em sistema\logs.
$python = Join-Path $sistema "python\pythonw.exe"
if (-not (Test-Path $python)) {
    $python = (& py -c "import sys, os; print(os.path.join(os.path.dirname(sys.executable), 'pythonw.exe'))").Trim()
}
if (-not (Test-Path $python)) { throw "Python nao encontrado em sistema\python nem instalado na maquina." }

$acao = New-ScheduledTaskAction -Execute $python -Argument "executar.py" -WorkingDirectory $app
$gatilho = New-ScheduledTaskTrigger -Daily -At $Hora
# StartWhenAvailable: se o computador estiver desligado no horario, roda assim que for ligado.
$opcoes = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Hours 2)

Register-ScheduledTask -TaskName "Sinistro - atualizar planilha" -Action $acao -Trigger $gatilho -Settings $opcoes `
    -Description "Atualiza as planilhas do sinistro e o painel com os dados do SGA e do SIGA." -Force | Out-Null

Write-Host "Tarefa agendada: todos os dias as $Hora."
Write-Host "Programa: $python"
Write-Host "Pasta:    $app"
Write-Host "O resultado de cada execucao fica em $sistema\logs."
