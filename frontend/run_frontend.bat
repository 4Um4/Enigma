@echo off
chcp 65001 >nul
title Enigma - Frontend Server

echo ========================================
echo    Enigma - Frontend HTTP Server
echo ========================================
echo.
echo Starting HTTP server for frontend...
echo.

:: Set Python command - use venv if exists, otherwise use system python
set "PYTHON_CMD=python"
if exist "%~dp0..\.venv\Scripts\python.exe" (
    set "PYTHON_CMD=%~dp0..\.venv\Scripts\python.exe"
)

:: Check if Python is available
%PYTHON_CMD% --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Please install Python 3.10+
    pause
    exit /b 1
)

echo Opening game interface in browser...
start "" "http://127.0.0.1:8081/ui/index.html"

:: Start HTTP server
cd /d C:\DDD\Codex\VSC_Enigma\Enigma\frontend
%PYTHON_CMD% -m http.server 8081

pause

