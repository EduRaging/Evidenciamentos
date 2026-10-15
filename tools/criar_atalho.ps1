# Cria o atalho "Capturador de Evidências" (com o ícone do app) para abrir o programa
# sem janela de console.
# Uso:  powershell -File tools\criar_atalho.ps1                 (cria na pasta do projeto)
#       powershell -File tools\criar_atalho.ps1 -AreaDeTrabalho (cria na Área de Trabalho)
# Este arquivo precisa ficar salvo em UTF-8 com BOM para os acentos saírem certos.
param([switch]$AreaDeTrabalho)

$raiz = Split-Path -Parent $PSScriptRoot
$pythonw = Join-Path $raiz ".venv\Scripts\pythonw.exe"
$exe = Join-Path $raiz "dist\CapturadorEvidencias.exe"
$icone = Join-Path $raiz "assets\icone.ico"

$pasta = if ($AreaDeTrabalho) { [Environment]::GetFolderPath("Desktop") } else { $raiz }
$caminho = Join-Path $pasta "Capturador de Evidências.lnk"

$atalho = (New-Object -ComObject WScript.Shell).CreateShortcut($caminho)
if (Test-Path $pythonw) {
    $atalho.TargetPath = $pythonw
    $atalho.Arguments = '"' + (Join-Path $raiz "main.py") + '"'
} elseif (Test-Path $exe) {
    $atalho.TargetPath = $exe
} else {
    Write-Error "Nao encontrei o ambiente (.venv) nem o executavel. Rode o Iniciar.bat ou o build.bat primeiro."
    exit 1
}
$atalho.WorkingDirectory = $raiz
$atalho.IconLocation = "$icone,0"
$atalho.Description = "Capturador de Evidências"
$atalho.Save()
Write-Host "Atalho criado: $caminho"
