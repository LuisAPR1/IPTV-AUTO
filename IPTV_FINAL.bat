@echo off
title IPTV Fiesta Automatizador - Powered by LuisR
color 0A
echo.
echo  ============================================================
echo   IPTV Fiesta Automatizador - Powered by LuisR
echo   github.com/luisapr1
echo  ============================================================
echo.

:: Verificar Python
python --version >nul 2>&1
if errorlevel 1 (
    echo  [ERRO] Python nao encontrado!
    echo  Instala em: https://www.python.org/downloads/
    echo  IMPORTANTE: Marca "Add Python to PATH" durante a instalacao!
    pause
    exit /b 1
)

:: Ir para a pasta do script
cd /d "%~dp0iptv-automatizador"

:: Verificar se o .env existe
if not exist ".env" (
    echo  [ERRO] Ficheiro .env nao encontrado!
    echo  Copia o .env.example para .env e configura as credenciais.
    pause
    exit /b 1
)

:: Verificar dependencias
echo  A verificar dependencias...
pip show playwright >nul 2>&1
if errorlevel 1 (
    echo  A instalar dependencias...
    pip install -r requirements.txt
    if errorlevel 1 (
        echo  [ERRO] Falha ao instalar dependencias!
        pause
        exit /b 1
    )
    echo  A instalar browsers do Playwright...
    python -m playwright install chromium
)

echo  Tudo pronto! A iniciar...
echo.

:: Executar
python main.py

echo.
echo  Pressiona qualquer tecla para sair...
pause >nul
