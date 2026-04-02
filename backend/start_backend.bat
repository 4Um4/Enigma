:: C:\DDD\Codex\VSC_Enigma\Enigma\backend\start_backend.bat
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
:: Установка зависимостей (только если requirements.txt изменился)
:: ========================================
set "REQ_FILE=%~dp0requirements.txt"
set "MARKER_FILE=%~dp0..\.venv\.deps_marker"

:: Считаем хэш requirements.txt
for /f "skip=1 tokens=*" %%h in ('certutil -hashfile "%REQ_FILE%" SHA1 2^>nul') do (
    set "REQ_HASH=%%h"
    goto :hash_done
)
:hash_done

:: Читаем предыдущий хэш
set "OLD_HASH="
if exist "%MARKER_FILE%" set /p OLD_HASH=<"%MARKER_FILE%"

if "%REQ_HASH%"=="%OLD_HASH%" (
    echo [OK] Dependencies up-to-date, skipping install
) else (
    echo [INFO] requirements.txt changed, installing dependencies...
    "%VENV_PIP%" install -r "%REQ_FILE%" --timeout 15 --retries 1 >> "%LOGFILE%" 2>&1
    if errorlevel 1 (
        echo [WARN] Some dependencies failed to install. Game may still work if packages are cached.
    ) else (
        echo %REQ_HASH%> "%MARKER_FILE%"
        echo [OK] Dependencies installed
    )
)

:: ========================================
:: Запуск FastAPI сервера
:: ========================================
set "API_PORT=8000"
echo [INFO] Starting FastAPI Backend on port %API_PORT%...
echo Logging to: %LOGFILE%

"%PYTHON_CMD%" -X utf8 -m uvicorn app.main:app --host 127.0.0.1 --port %API_PORT% >> "%LOGFILE%" 2>&1

echo [INFO] Backend server stopped >> "%LOGFILE%"
pause