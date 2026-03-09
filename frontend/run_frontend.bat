@echo off
chcp 65001 >nul
title Enigma - Frontend Server

echo ========================================
echo    Enigma - Frontend HTTP Server
echo ========================================
echo.
echo Starting HTTP server for frontend...
echo.

:: Check if Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Please install Python 3.10+
    pause
    exit /b 1
)

echo Opening game interface in browser...
start "" "http://127.0.0.1:8081/ui/index.html"

:: Start HTTP server
cd /d C:\DDD\Codex\VSC_Enigma\Enigma\frontend
python -m http.server 8081

pause

