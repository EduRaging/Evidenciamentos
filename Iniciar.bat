@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
    echo Preparando o ambiente na primeira execucao...
    python -m venv .venv || goto erro
    ".venv\Scripts\python.exe" -m pip install --quiet -r requirements.txt || goto erro
)
start "" ".venv\Scripts\pythonw.exe" main.py
exit /b 0

:erro
echo.
echo Falha ao preparar o ambiente. Verifique se o Python esta instalado e se ha acesso a internet.
pause
exit /b 1
