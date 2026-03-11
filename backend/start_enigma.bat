@echo off
chcp 65001 >nul
title Enigma - Local AI Dungeon Master

echo ========================================
echo    Enigma - Local AI Dungeon Master
echo ========================================
echo.

:: Set Python command - use venv if exists, otherwise use system python
set "PYTHON_CMD=python"
if exist "%~dp0..\.venv\Scripts\python.exe" (
    set "PYTHON_CMD=%~dp0..\.venv\Scripts\python.exe"
)

:: Check Python version (requires 3.11)
%PYTHON_CMD% --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found
    echo Please install Python 3.11 and add it to PATH
    pause
    exit /b 1
)

:: Get Python version for display
for /f "tokens=2" %%i in ('%PYTHON_CMD% --version 2^>^&1') do set PYTHON_VER=%%i
echo Found Python: %PYTHON_VER%

%PYTHON_CMD% -c "import sys; exit(0) if sys.version_info[:2] == (3,11) else exit(1)"
if errorlevel 1 (
    echo [ERROR] Python 3.11 required, but found %PYTHON_VER%
    echo Please install Python 3.11 and add it to PATH
    echo Download: https://www.python.org/downloads/
    pause
    exit /b 1
)
echo [OK] Python 3.11 found

set LLM_MAX_WAIT=120
set BACKEND_MAX_WAIT=30
set FRONTEND_MAX_WAIT=10

:: ========================================
:: STEP 1: Start LLM Server
:: ========================================
echo [1/5] Starting LLM Server...
start "Enigma LLM" cmd /k "cd /d C:\DDD\Codex\VSC_Enigma\Enigma\backend && start_llm.bat"

:: Wait for LLM to be ready (check /health endpoint - more reliable than /v1/models)
echo.
echo      Waiting for LLM model to load...
set LLM_WAIT_COUNT=0
:wait_llm
curl -s http://127.0.0.1:8080/health >nul 2>nul
if %errorlevel% neq 0 (
    set /a LLM_WAIT_COUNT+=2
    if %LLM_WAIT_COUNT% LSS %LLM_MAX_WAIT% (
        echo      Loading... %LLM_WAIT_COUNT%s
        timeout /t 2 /nobreak >nul
        goto wait_llm
    ) else (
        echo [ERROR] LLM server did not start in time
        echo         Please check the LLM window for errors
        pause
        exit /b 1
    )
)
echo      [OK] LLM Server ready on port 8080

:: ========================================
:: STEP 2: Start Backend
:: ========================================
echo [2/5] Starting Backend Server...
start "Enigma Backend" cmd /k "cd /d C:\DDD\Codex\VSC_Enigma\Enigma\backend && start_backend.bat"

:: Wait for backend to be ready
echo      Waiting for backend server...
set BACKEND_WAIT_COUNT=0

:wait_backend
timeout /t 2 /nobreak >nul
curl -s http://127.0.0.1:8000/docs >nul 2>nul

if %errorlevel%==0 (
    echo      [OK] Backend ready on port 8000
    goto verify_backend
)

set /a BACKEND_WAIT_COUNT+=2
if %BACKEND_WAIT_COUNT% LSS %BACKEND_MAX_WAIT% (
    echo      Backend not ready, waiting... (%BACKEND_WAIT_COUNT%/%BACKEND_MAX_WAIT%)
    goto wait_backend
) else (
    echo [ERROR] Backend server did not start in time
    echo         Please check the Backend window for errors
    pause
    exit /b 1
)

:verify_backend

:: Verify backend health (LLM connection)
curl -s http://127.0.0.1:8000/api/health
echo.

:: ========================================
:: STEP 3: Start Frontend HTTP Server
:: ========================================
echo [3/5] Starting Frontend HTTP Server...
start "Enigma Frontend" cmd /k "cd /d C:\DDD\Codex\VSC_Enigma\Enigma\frontend && %PYTHON_CMD% -m http.server 3000"

:: Wait for frontend server
echo      Waiting for frontend server...
set FRONTEND_WAIT_COUNT=0
:wait_frontend
timeout /t 1 /nobreak >nul
curl -s http://127.0.0.1:3000 >nul 2>nul
if %errorlevel% neq 0 (
    set /a FRONTEND_WAIT_COUNT+=1
    if %FRONTEND_WAIT_COUNT% LSS %FRONTEND_MAX_WAIT% (
        goto wait_frontend
    )
)
echo      [OK] Frontend ready on port 3000

:: ========================================
:: STEP 4: Open Game Interface
:: ========================================
echo [4/5] Opening Game Interface...
start "" "http://127.0.0.1:3000"

:: ========================================
:: STEP 5: Summary
:: ========================================
echo [5/5] All services started successfully!
echo.
echo ========================================
echo    Enigma Ready!
echo ========================================
echo.
echo Servers running:
echo   - LLM Server:    http://127.0.0.1:8080
echo   - FastAPI:      http://127.0.0.1:8000
echo   - API Docs:     http://127.0.0.1:8000/docs
echo   - Game UI:      http://127.0.0.1:3000
echo.
echo ========================================
echo Press any key to exit this window...
echo (Services will continue running in background)
pause >nul

