@echo off
setlocal
title Reelwala - WhatsApp AI Reel Studio
cd /d "%~dp0"

echo =====================================================
echo           REELWALA (CreatorOps)
echo   WhatsApp-first AI Video Ad Creator
echo =====================================================
echo.

if exist .venv\Scripts\python.exe goto check_env
echo [ERROR] Virtual environment (.venv) not found!
echo Please create it first:
echo   python -m venv .venv
echo   .venv\Scripts\pip install -e .
echo.
pause
exit /b 1

:check_env
if exist .env goto check_db
if exist .env.example (
    echo [INFO] .env not found. Creating from .env.example...
    copy .env.example .env >nul
    echo [INFO] Created .env file.
)

:check_db
echo [INFO] Checking database migrations...
call .venv\Scripts\alembic.exe upgrade head >nul 2>&1
echo [OK] Database ready.
echo.

echo -----------------------------------------------------
echo Choose an option:
echo   [1] Start Reelwala Server (FastAPI + Uvicorn)
echo   [2] Start Server + ngrok Tunnel (for WhatsApp Testing)
echo   [3] Start ngrok Tunnel Only (port 8000)
echo   [4] Run Automated Tests (pytest)
echo   [5] Exit
echo -----------------------------------------------------
echo.

choice /C 12345 /T 5 /D 1 /M "Select an option [1-5] (Auto-starts [1] in 5s): "
set OPTION=%ERRORLEVEL%

if "%OPTION%"=="1" goto start_server
if "%OPTION%"=="2" goto start_both
if "%OPTION%"=="3" goto start_ngrok
if "%OPTION%"=="4" goto run_tests
if "%OPTION%"=="5" goto end

:start_both
echo.
echo [INFO] Launching ngrok tunnel in a new window...
start "Reelwala - ngrok Tunnel" cmd /k "echo Starting ngrok on port 8000... & ngrok http 8000"
timeout /t 2 >nul
goto start_server

:start_server
echo.
echo =====================================================
echo [INFO] Starting Reelwala Server on http://127.0.0.1:8000
echo [INFO] Health check: http://127.0.0.1:8000/health
echo [INFO] Admin dashboard: http://127.0.0.1:8000/admin/jobs?token=change-me
echo Press Ctrl+C in this window to stop the server.
echo =====================================================
echo.
call .venv\Scripts\uvicorn.exe app.main:app --host 0.0.0.0 --port 8000 --reload
goto end

:start_ngrok
echo.
echo [INFO] Starting ngrok on port 8000...
ngrok http 8000
goto end

:run_tests
echo.
echo =====================================================
echo [INFO] Running pytest test suite...
echo =====================================================
call .venv\Scripts\pytest.exe -q
echo.
pause
goto end

:end
exit /b 0
