@echo off
setlocal

cd /d "%~dp0"

ollama list >nul 2>&1
if errorlevel 1 (
    echo Ollama baslatiliyor...
    start "Ollama" /min ollama serve
    timeout /t 3 /nobreak >nul
)

rem Model zaten varsa pull hemen biter; ilk sefer birkac GB indirir.
ollama pull bge-m3 || goto :ollama_error
ollama pull qwen3:8b || goto :ollama_error

docker compose up -d --build
if errorlevel 1 (
    echo HATA: Docker baslatilamadi. Docker Desktop'i acip tekrar deneyin.
    exit /b 1
)

echo.
echo Uygulama hazir: http://127.0.0.1:5173  (API: http://127.0.0.1:8000/docs)
start "" http://127.0.0.1:5173
exit /b 0

:ollama_error
echo HATA: Ollama bulunamadi veya model indirilemedi. https://ollama.com adresinden kurup tekrar deneyin.
exit /b 1
