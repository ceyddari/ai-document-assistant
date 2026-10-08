@echo off
setlocal

cd /d "%~dp0"

echo [1/5] PostgreSQL baslatiliyor...
docker compose up -d --wait db
if errorlevel 1 goto :docker_error

echo [2/5] Ollama kontrol ediliyor...
ollama list >nul 2>&1
if errorlevel 1 (
    echo Ollama baslatiliyor...
    start "AI Document Assistant - Ollama" /min ollama serve
    timeout /t 3 /nobreak >nul
)

echo [3/5] Veritabani migrationlari calistiriliyor...
".venv\Scripts\python.exe" -m alembic -c apps/api/alembic.ini upgrade head
if errorlevel 1 goto :migration_error

echo [4/5] Backend baslatiliyor...
start "AI Document Assistant - Backend" cmd /k ".venv\Scripts\python.exe -m uvicorn app.main:app --app-dir apps/api --reload"

echo [5/5] Frontend baslatiliyor...
start "AI Document Assistant - Frontend" cmd /k "npm.cmd --prefix apps\web run dev"

echo.
echo Proje baslatildi: http://127.0.0.1:5173
exit /b 0

:docker_error
echo.
echo HATA: Docker veritabani baslatilamadi. Docker Desktop'i acip tekrar deneyin.
exit /b 1

:migration_error
echo.
echo HATA: Veritabani migrationlari tamamlanamadi.
exit /b 1
