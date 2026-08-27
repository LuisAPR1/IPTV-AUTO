@echo off
title IPTV Trial Web App - Powered by LuisR
color 0B
echo.
echo  ============================================================
echo   ⚡ IPTV Trial Mobile Web App - Powered by LuisR
echo   github.com/luisapr1
echo  ============================================================
echo.

:: Ir para a pasta do script
cd /d "%~dp0iptv-automatizador"

:: Verificar se o .env existe
if not exist ".env" (
    echo  [AVISO] Ficheiro .env nao encontrado na pasta local.
    echo  A tentar iniciar...
)

echo  A iniciar servidor Web...
echo  📱 Abrir no browser: http://localhost:5000
echo.

start "" "http://localhost:5000"
python app.py

pause
