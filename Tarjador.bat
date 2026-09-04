@echo off
title Tarjador de PDFs
cd /d "%~dp0"

python -c "import pymupdf, PIL" 2>nul
if errorlevel 1 (
    echo Instalando dependencias ^(so na primeira vez^)...
    python -m pip install --disable-pip-version-check -r requirements.txt
    if errorlevel 1 (
        echo.
        echo Falhou ao instalar. Verifique se o Python esta instalado.
        pause
        exit /b 1
    )
)

start "" pythonw tarjador.py
