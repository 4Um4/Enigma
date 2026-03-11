@echo off
chcp 65001 >nul
title Enigma Backend Server

echo ========================================
echo    Enigma Backend Server
echo ========================================
echo.

cd /d %~dp0

:: Check for existing .venv at project root FIRST
set "PYTHON_CMD=python"
set "VENV_PATH="
set "VENV_PIP="
if exist "%~dp0..\.venv\Scripts\python.exe" (
    echo [INFO] Found existing virtual environment at ..\.venv
    set "PYTHON_CMD=%~dp0..\.venv\Scripts\python.exe"
    set "VENV_PIP=%~dp0..\.venv\Scripts\pip.exe"
    set "VENV_PATH=%~dp0..\.venv"
    goto use_existing_venv
)

:: Check Python version (requires 3.11) - only if no venv
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found
    echo Please install Python 3.11 and add it to PATH
    pause
    exit /b 1
)

:: Get Python version for display
for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PYTHON_VER=%%i
echo Found Python: %PYTHON_VER%

python -c "import sys; exit(0) if sys.version_info[:2] == (3,11) else exit(1)"
if errorlevel 1 (
    echo [ERROR] Python 3.11 required, but found %PYTHON_VER%
    echo Please install Python 3.11 and add it to PATH
    echo Download: https://www.python.org/downloads/
    pause
    exit /b 1
)
echo [OK] Python 3.11 found

:: Delete old venv if exists (to fix corrupted installations)
if exist venv (
    echo Removing old virtual environment...
    rmdir /s /q venv
    echo [OK] Old venv removed
)

:: Create new venv
echo Creating virtual environment...
python -m venv venv
if errorlevel 1 (
    echo [ERROR] Failed to create virtual environment
    pause
    exit /b 1
)
echo [OK] Virtual environment created
set "VENV_PATH=%~dp0venv"
set "VENV_PIP=%~dp0venv\Scripts\pip.exe"

:use_existing_venv
echo [1/4] Using virtual environment at %VENV_PATH%

:: Check Python version in venv
for /f "tokens=2" %%i in ('%PYTHON_CMD% --version 2^>^&1') do set PYTHON_VER=%%i
echo Found Python: %PYTHON_VER%

%PYTHON_CMD% -c "import sys; exit(0) if sys.version_info[:2] == (3,11) else exit(1)"
if errorlevel 1 (
    echo [ERROR] Python 3.11 required, but found %PYTHON_VER%
    pause
    exit /b 1
)
echo [OK] Python 3.11 confirmed
echo [OK] Virtual environment ready

echo [2/4] Installing dependencies...
"%VENV_PIP%" install -r requirements.txt
if errorlevel 1 (
    echo [ERROR] Failed to install dependencies
    pause
    exit /b 1
)
echo [OK] Dependencies installed

echo [3/4] Starting FastAPI Backend...
echo.
echo Server will be available at:
echo   - API:       http://127.0.0.1:8000
echo   - Docs:      http://127.0.0.1:8000/docs
echo   - Health:    http://127.0.0.1:8000/api/health
echo.

"%PYTHON_CMD%" -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

echo.
echo [INFO] Backend server stopped
pause

