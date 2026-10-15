@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
    echo Preparando o ambiente na primeira execucao...
    python -m venv .venv || goto erro
)
".venv\Scripts\python.exe" -m pip install --quiet --disable-pip-version-check -r requirements.txt || goto erro
rem Cria o atalho com o icone do app (uma vez). Falha aqui nao impede de abrir o programa.
if not exist "Capturador de Evid*.lnk" powershell -NoProfile -ExecutionPolicy Bypass -File "tools\criar_atalho.ps1" >nul 2>&1
start "" ".venv\Scripts\pythonw.exe" main.py
exit /b 0

:erro
echo.
echo Falha ao preparar o ambiente. Verifique se o Python esta instalado e se ha acesso a internet.
pause
exit /b 1
