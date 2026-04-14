@echo off
chcp 65001 >nul
title Enigma - Local AI Dungeon Master

echo [INIT] Cleaning stale processes...
taskkill /F /IM llama-server.exe >nul 2>&1
timeout /t 1 /nobreak >nul
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8000.*LISTENING" 2^>nul') do (
    taskkill /F /PID %%a >nul 2>&1
)
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":3000.*LISTENING" 2^>nul') do (
    taskkill /F /PID %%a >nul 2>&1
)

echo [INIT] Cleaning __pycache__...
cd /d "%~dp0backend"
del /s /q __pycache__ >nul 2>&1
for /d /r %%d in (__pycache__) do @if exist "%%d" rd /s /q "%%d" 2>nul
cd /d "%~dp0"

set "ROOT_DIR=%~dp0"
if "%ROOT_DIR:~-1%"=="\" set "ROOT_DIR=%ROOT_DIR:~0,-1%"
set "BACKEND_DIR=%ROOT_DIR%\backend"
set "LOG_DIR=%BACKEND_DIR%\logs"
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

for /f "delims=" %%T in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmmss"') do set "dt=%%T"
set "MAIN_LOG=%LOG_DIR%\startup_%dt%.log"

echo [INFO] Root: %ROOT_DIR%
echo [INFO] Logs: %LOG_DIR%

set "PYTHON_CMD=%ROOT_DIR%\.venv\Scripts\python.exe"
if not exist "%PYTHON_CMD%" (
    echo [WARN] .venv not found, using system python
    set "PYTHON_CMD=python"
)
set "PYTHONPATH=%BACKEND_DIR%"

for /f "tokens=2" %%i in ('"%PYTHON_CMD%" --version 2^>^&1') do set PYTHON_VER=%%i
echo [INFO] Python: %PYTHON_VER%

echo.
echo [0/5] Checking LLM binary...
set "LLAMA_EXE=%ROOT_DIR%\Models LLM\llama\llama-server.exe"
if not exist "%LLAMA_EXE%" (
    echo [ERROR] llama-server.exe not found: %LLAMA_EXE%
    pause
    exit /b 1
)
echo [OK] llama-server.exe found

echo.
echo [1/5] Starting LLM server...
set "LLM_LOG=%LOG_DIR%\llm_%dt%.log"

cd /d "%BACKEND_DIR%"
start "Enigma LLM" start_llm.bat %LLM_LOG%
cd /d "%ROOT_DIR%"

timeout /t 3 /nobreak >nul

echo [INFO] Waiting for LLM server (max 450 sec)...
set /a LLM_WAIT=0
:wait_llm

tasklist /FI "IMAGENAME eq llama-server.exe" 2>nul | findstr /I "llama-server.exe" >nul
if errorlevel 1 (
    echo [FATAL] llama-server.exe crashed! Log:
    type "%LLM_LOG%" 2>nul
    pause
    exit /b 1
)

powershell -NoProfile -Command "try { Invoke-WebRequest -Uri 'http://127.0.0.1:8080/v1/models' -UseBasicParsing -TimeoutSec 3 -ErrorAction Stop | Out-Null; exit 0 } catch { exit 1 }" >nul 2>&1
if %errorlevel% equ 0 goto llm_ready

set /a LLM_WAIT+=5
echo [INFO] LLM loading... %LLM_WAIT%/450 sec
if %LLM_WAIT% LSS 450 (
    timeout /t 5 /nobreak >nul
    goto wait_llm
)
echo [WARN] LLM timeout - offline mode
goto start_backend

:llm_ready
echo [OK] LLM ready (%LLM_WAIT% sec)

echo.
echo [1.5/5] Resetting campaign state...
set "CAMPAIGN_STATE=%BACKEND_DIR%\data\campaigns\demo-campaign\campaign_state.json"
set "SESSION_FILE=%BACKEND_DIR%\data\sessions\demo-campaign.json"

if exist "%CAMPAIGN_STATE%" (
    del "%CAMPAIGN_STATE%"
    echo [OK] Deleted: campaign_state.json
) else (
    echo [SKIP] campaign_state.json not found
)

if exist "%SESSION_FILE%" (
    del "%SESSION_FILE%"
    echo [OK] Deleted: session file
) else (
    echo [SKIP] session file not found
)

:start_backend
echo.
echo [2/5] Starting Backend...
set "BACKEND_LOG=%LOG_DIR%\backend_%dt%.log"

cd /d "%BACKEND_DIR%"
start "Enigma Backend" cmd /c ""%PYTHON_CMD%" -u -X utf8 -m uvicorn app.main:app --host 127.0.0.1 --port 8000 >> "%BACKEND_LOG%" 2>&1"
cd /d "%ROOT_DIR%"

set /a BACK_WAIT=0
:wait_backend
timeout /t 2 /nobreak >nul
powershell -NoProfile -Command "try { Invoke-WebRequest -Uri 'http://127.0.0.1:8000/api/health' -UseBasicParsing -TimeoutSec 3 -ErrorAction Stop | Out-Null; exit 0 } catch { exit 1 }" >nul 2>&1
if %errorlevel% equ 0 goto backend_ready

set /a BACK_WAIT+=2
if %BACK_WAIT% LSS 60 goto wait_backend
echo [ERROR] Backend failed to start! Log:
type "%BACKEND_LOG%" 2>nul
pause
exit /b 1

:backend_ready
echo [OK] Backend ready (%BACK_WAIT% sec)

echo.
echo [3/5] Starting Frontend...
set "FRONTEND_DIR=%ROOT_DIR%\frontend\ui"

if not exist "%FRONTEND_DIR%\index.html" (
    echo [WARN] frontend\ui\index.html not found - skipping
    goto open_browser
)

start "Enigma Frontend" cmd /c "%PYTHON_CMD%" -m http.server 3000 --directory "%FRONTEND_DIR%"
timeout /t 2 /nobreak >nul
echo [OK] Frontend started

:open_browser
echo.
echo [4/5] Opening browser...
powershell -NoProfile -Command "try { Invoke-WebRequest -Uri 'http://127.0.0.1:3000' -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop | Out-Null; Start-Process 'http://127.0.0.1:3000' } catch { Start-Process 'http://127.0.0.1:8000' }"

echo.
echo [5/5] ==================== ENIGMA LIVE ====================
echo    Frontend:  http://127.0.0.1:3000
echo    Backend:   http://127.0.0.1:8000
echo    API Docs:  http://127.0.0.1:8000/docs
echo    Debug:     http://127.0.0.1:8000/api/debug/vram
echo    Logs:      %LOG_DIR%
echo    ====================================================
echo.
echo    Tailing backend log (Ctrl+C to exit)...
echo.

powershell -NoProfile -Command "Get-Content '%BACKEND_LOG%' -Tail 30 -Wait"
pause >nul