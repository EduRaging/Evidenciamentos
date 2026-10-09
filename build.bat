@echo off
rem Gera dist\CapturadorEvidencias.exe e, se o Inno Setup estiver instalado, o instalador.
setlocal
cd /d "%~dp0"
set VENV=.venv-build

if not exist "%VENV%\Scripts\python.exe" (
    echo [1/5] Criando ambiente de build...
    python -m venv "%VENV%" || goto erro
)
echo [1/5] Instalando dependencias...
"%VENV%\Scripts\python.exe" -m pip install --quiet --disable-pip-version-check -r requirements.txt pyinstaller || goto erro

echo [2/5] Rodando os testes...
"%VENV%\Scripts\python.exe" -m unittest discover -s tests -t . || goto erro

echo [3/5] Gerando o executavel...
"%VENV%\Scripts\python.exe" -m PyInstaller --noconfirm --clean Capturador.spec || goto erro

echo [4/5] Validando o executavel (autoteste)...
if exist "%TEMP%\autoteste_capturador.txt" del "%TEMP%\autoteste_capturador.txt"
start /wait "" "dist\CapturadorEvidencias.exe" --autoteste "%TEMP%\autoteste_capturador.txt"
if errorlevel 1 (
    echo O autoteste do executavel FALHOU:
    type "%TEMP%\autoteste_capturador.txt"
    goto erro
)
type "%TEMP%\autoteste_capturador.txt"

echo [5/5] Gerando o instalador...
set ISCC=
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if exist "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if not defined ISCC (
    echo Inno Setup 6 nao encontrado: so o executavel foi gerado.
    echo Instale em https://jrsoftware.org/isinfo.php e rode o build.bat de novo.
    goto fim
)
for /f %%v in ('"%VENV%\Scripts\python.exe" -c "from capturador import __version__; print(__version__)"') do set VERSAO=%%v
"%ISCC%" /Qp /DVersao=%VERSAO% installer\Capturador.iss || goto erro

:fim
echo.
echo Pronto. Executavel em dist\ e instalador em installer_output\ (se gerado).
exit /b 0

:erro
echo.
echo O build falhou. Veja as mensagens acima.
pause
exit /b 1
