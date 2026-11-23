@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo.
    echo ERRO: ambiente virtual nao encontrado em .venv\Scripts\python.exe
    echo Consulte o README.md para preparar o ambiente.
    echo.
    pause
    exit /b 1
)

echo Iniciando Victorique...
".venv\Scripts\python.exe" run.py %*

if errorlevel 1 (
    echo.
    echo O assistente terminou com erro. Veja as mensagens acima.
    pause
)
endlocal
