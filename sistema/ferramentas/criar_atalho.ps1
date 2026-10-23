# Cria o atalho "Grupo Support - Atualizar SIGA" (icone oficial) na pasta acima de "grupo support".
# Uso: "Criar atalho.bat"  (ou este script, com -Destino "C:\outra\pasta")
# Rode de novo se a pasta do projeto mudar de lugar: o atalho guarda o caminho completo.

param([string]$Destino = "", [switch]$AreaDeTrabalho)

$ErrorActionPreference = "Stop"
$sistema = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$raiz = Split-Path -Parent $sistema
if ($AreaDeTrabalho) { $Destino = [Environment]::GetFolderPath("Desktop") }  # inclui Area de Trabalho no OneDrive
if (-not $Destino) { $Destino = Split-Path -Parent $raiz }

$pythonw = Join-Path $sistema "python\pythonw.exe"
$tela = Join-Path $raiz "atualizar_tela.py"
$icone = Join-Path $sistema "grupo_support.ico"
foreach ($f in $pythonw, $tela, $icone) { if (-not (Test-Path -LiteralPath $f)) { throw "Nao encontrei $f" } }

$atalho = Join-Path $Destino "Grupo Support - Atualizar SIGA.lnk"
$shell = New-Object -ComObject WScript.Shell
$lnk = $shell.CreateShortcut($atalho)
# O atalho chama o cmd do Windows, que abre o pythonw: com o "Controle Inteligente de Aplicativos"
# ligado, o Windows bloqueia atalho que aponta direto para um .exe extraido de um ZIP da internet.
$lnk.TargetPath = Join-Path $env:SystemRoot "System32\cmd.exe"
$lnk.Arguments = '/c start "" "' + $pythonw + '" "' + $tela + '"'
$lnk.WindowStyle = 7  # minimizado: o cmd fecha na hora, so a tela aparece
$lnk.WorkingDirectory = $raiz
$lnk.IconLocation = "$icone,0"
$lnk.Description = "Grupo Support - baixa os relatorios do SIGA e atualiza planilhas e paineis"
$lnk.Save()

Write-Host "Atalho criado: $atalho"
