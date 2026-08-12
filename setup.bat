@echo off
title IPTV Setup - Verificacao de Requisitos
color 0B
echo.
echo  ============================================================
echo   IPTV Fiesta - Verificacao de Requisitos
echo  ============================================================
echo.

set ERRORS=0

:: 1. Python
echo  [1/5] Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo        FALHOU - Python nao encontrado!
    echo        Instala em: https://www.python.org/downloads/
    echo        MARCA "Add Python to PATH"!
    set /a ERRORS+=1
) else (
    for /f "tokens=*" %%i in ('python --version 2^>^&1') do echo        OK - %%i
)

:: 2. pip
echo  [2/5] pip...
pip --version >nul 2>&1
if errorlevel 1 (
    echo        FALHOU - pip nao encontrado!
    set /a ERRORS+=1
) else (
    echo        OK
)

:: 3. Dependencias Python
echo  [3/5] Dependencias Python...
cd /d "%~dp0iptv-automatizador"

pip show playwright >nul 2>&1
if errorlevel 1 (
    echo        A instalar dependencias...
    pip install -r requirements.txt
    if errorlevel 1 (
        echo        FALHOU - Erro ao instalar!
        set /a ERRORS+=1
    ) else (
        echo        OK - Instaladas
    )
) else (
    echo        OK - Ja instaladas
)

:: 4. Playwright browsers
echo  [4/5] Playwright Chromium...
python -c "from playwright.sync_api import sync_playwright; p=sync_playwright().start(); b=p.chromium.launch(headless=True); b.close(); p.stop(); print('OK')" >nul 2>&1
if errorlevel 1 (
    echo        A instalar browser...
    python -m playwright install chromium
    if errorlevel 1 (
        echo        FALHOU - Erro ao instalar Chromium!
        set /a ERRORS+=1
    ) else (
        echo        OK - Instalado
    )
) else (
    echo        OK
)

:: 5. Ficheiro .env
echo  [5/5] Configuracao (.env)...
if not exist ".env" (
    echo        FALHOU - Ficheiro .env nao encontrado!
    echo        Copia .env.example para .env e configura.
    set /a ERRORS+=1
) else (
    echo        OK - Encontrado
)

echo.
echo  ============================================================
if %ERRORS% EQU 0 (
    color 0A
    echo   TUDO OK! Podes executar: IPTV_Automatizador.bat
) else (
    color 0C
    echo   %ERRORS% ERRO(S) encontrados. Corrige antes de executar.
)
echo  ============================================================
echo.
pause
