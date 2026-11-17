@echo off
setlocal

cd /d "%~dp0"

ollama list >nul 2>&1
if errorlevel 1 (
    echo Ollama baslatiliyor...
    start "Ollama" /min ollama serve
    timeout /t 3 /nobreak >nul
)

docker compose up -d --build
if errorlevel 1 (
    echo HATA: Docker baslatilamadi. Docker Desktop'i acip tekrar deneyin.
    exit /b 1
)

echo.
echo Proje baslatildi: http://127.0.0.1:5173
