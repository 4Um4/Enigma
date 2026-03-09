@echo off
chcp 65001 >nul
title Enigma - Local AI Dungeon Master

echo ========================================
echo    Enigma - Local AI Dungeon Master
echo ========================================
echo.
echo Starting Enigma Game...
echo.

:: Check if Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Please install Python 3.10+
    pause
    exit /b 1
)

:: Start LLaMA server in background
echo [1/4] Starting LLaMA Server...
start "LLaMA Server" cmd /k "cd /d C:\DDD\Codex\VSC_Enigma\Enigma && backend\run_llama_server_multi.bat"

:: Wait a bit for server to start
timeout /t 5 /nobreak >nul

:: Start FastAPI backend
echo [2/4] Starting FastAPI Backend...
start "Enigma Backend" cmd /k "cd /d C:\DDD\Codex\VSC_Enigma\Enigma\backend && python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000"

:: Wait for backend to start
timeout /t 3 /nobreak >nul

:: Start HTTP server for frontend
echo [3/4] Starting Frontend HTTP Server...
start "Enigma Frontend" cmd /k "cd /d C:\DDD\Codex\VSC_Enigma\Enigma\frontend && python -m http.server 8081"

:: Wait for HTTP server
timeout /t 2 /nobreak >nul

:: Open Game Interface in browser
echo [4/4] Opening Game Interface...
start "" "http://127.0.0.1:8081/ui/index.html"

echo.
echo ========================================
echo    Game Ready!
echo ========================================
echo.
echo Servers running:
echo   - LLaMA Server:    http://127.0.0.1:8080
echo   - FastAPI:        http://127.0.0.1:8000
echo   - API Docs:       http://127.0.0.1:8000/docs
echo   - Game Interface: http://127.0.0.1:8081/ui/index.html
echo.
echo ========================================
echo Press any key to exit...
pause >nul

