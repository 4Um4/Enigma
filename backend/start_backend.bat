@echo off
:: ========================================
:: Enigma Backend Server Launcher
:: Использует корневой .venv
:: ========================================

chcp 65001 >nul
title Enigma Backend Server (Logged)

:: ========================================
:: Настройка LOGFILE
:: ========================================
cd /d %~dp0
if "%~1"=="" (
    echo [WARN] No LOGFILE provided, using local backend.log
    set "LOGFILE=%~dp0logs\backend.log"
) else (
    echo [INFO] Using LOGFILE: %~1
    set "LOGFILE=%~1"
)

:: ========================================
:: Корневой venv
:: ========================================
set "PYTHON_CMD=%~dp0..\.venv\Scripts\python.exe"
set "VENV_PIP=%~dp0..\.venv\Scripts\pip.exe"
set "PYTHONPATH=%~dp0.."

if not exist "%PYTHON_CMD%" (
    echo [ERROR] Root .venv not found at %~dp0..\.venv
    pause
    exit /b 1
)

:: ========================================
:: Проверка Python версии
:: ========================================
for /f "tokens=2" %%i in ('"%PYTHON_CMD%" --version 2^>^&1') do set PYTHON_VER=%%i
echo [INFO] Python version in root venv: %PYTHON_VER%
"%PYTHON_CMD%" -c "import sys; exit(0) if sys.version_info[:2] == (3,11) else exit(1)"
if errorlevel 1 (
    echo [ERROR] Python 3.11 required, but found %PYTHON_VER%.
    pause
    exit /b 1
)

:: ========================================
:: Установка зависимостей
:: ========================================
echo [INFO] Installing dependencies from requirements.txt...
"%VENV_PIP%" install --upgrade pip >> "%LOGFILE%" 2>&1
"%VENV_PIP%" install -r "%~dp0requirements.txt" >> "%LOGFILE%" 2>&1
if errorlevel 1 (
    echo [ERROR] Failed to install dependencies. Check %LOGFILE%
    pause
    exit /b 1
)
echo [OK] Dependencies installed

:: ========================================
:: Запуск FastAPI сервера
:: ========================================
set "API_PORT=8000"
echo [INFO] Starting FastAPI Backend on port %API_PORT%...
echo Logging to: %LOGFILE%

"%PYTHON_CMD%" -X utf8 -m uvicorn app.main:app --host 127.0.0.1 --port %API_PORT% >> "%LOGFILE%" 2>&1

echo [INFO] Backend server stopped >> "%LOGFILE%"
pause