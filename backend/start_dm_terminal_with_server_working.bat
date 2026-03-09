@echo off
chcp 65001 >nul
title Enigma DM Launcher
REM ============================================================
REM Enigma DM Terminal + llama-server: Final Version
REM One-click launch: server + chat terminal
REM Requirements:
REM   1. Unblock files: Unblock-File -Path "*.exe", "*.dll"
REM   2. Port 8080 must be free
REM   3. Valid Python venv in ..\.venv
REM ============================================================

cd /d "%~dp0"

REM === SETTINGS ===
set "LLAMA_DIR=C:\DDD\Codex\VSC_Enigma\Enigma\Models LLM\llama"
set "MODEL=C:\DDD\Codex\VSC_Enigma\Enigma\Models LLM\qwen2.5-7b-instruct-q4_k_m.gguf"
set "URL=http://127.0.0.1:8080"
set "LOG_FILE=%~dp0llama_server.log"
set "PYTHON_CMD=python"

REM Check virtual environment
if exist "%~dp0..\.venv\Scripts\python.exe" (
  set "PYTHON_CMD=%~dp0..\.venv\Scripts\python.exe"
)

REM === FIND SERVER ===
if exist "%LLAMA_DIR%\llama-server.exe" (
  set "SERVER=%LLAMA_DIR%\llama-server.exe"
) else if exist "%LLAMA_DIR%\server.exe" (
  set "SERVER=%LLAMA_DIR%\server.exe"
) else (
  echo [ERROR] llama-server not found in %LLAMA_DIR%
  pause
  exit /b 1
)

REM === CHECK MODEL ===
if not exist "%MODEL%" (
  echo [ERROR] Model not found: %MODEL%
  pause
  exit /b 1
)

REM === KILL OLD PROCESSES ===
echo [1/5] Cleaning old processes...
echo.
echo [2/5] Auto-unblocking files (if blocked by Windows)...
powershell -Command "Get-ChildItem '%LLAMA_DIR%' -Recurse | Unblock-File -ErrorAction SilentlyContinue"
echo [OK] Done

taskkill /F /IM llama-server.exe 2>nul
taskkill /F /IM server.exe 2>nul
timeout /t 1 /nobreak >nul

REM === START SERVER ===
echo [3/5] Starting llama-server...
echo Log: %LOG_FILE%

REM Start server in background (empty window name is CRITICAL)
REM Added -ngl 33 for GPU offload, -c 4096 for larger context
start "" cmd /c ""%SERVER%" -ngl 33 -m "%MODEL%" -c 4096 --port 8080 --host 127.0.0.1 --threads 12 > "%LOG_FILE%" 2>&1"

REM === WAIT FOR SERVER ===
echo [4/5] Waiting for server (max 90 sec)...
set "MAX_WAIT=30"
set "ATTEMPT=0"

:wait_loop
set /a ATTEMPT+=1
if %ATTEMPT% geq %MAX_WAIT% goto wait_timeout

REM Check if port is listening
netstat -an -p tcp | findstr "127.0.0.1:8080.*LISTENING" >nul
if errorlevel 1 (
  timeout /t 3 /nobreak >nul
  goto wait_loop
)

REM Check HTTP response
powershell -Command "try { $r = Invoke-WebRequest -Uri 'http://127.0.0.1:8080/' -TimeoutSec 2 -UseBasicParsing; if ($r.StatusCode -ge 200) { exit 0 } else { exit 1 } } catch { exit 1 }" >nul 2>&1
if errorlevel 1 (
  timeout /t 3 /nobreak >nul
  goto wait_loop
)

goto wait_success

:wait_timeout
echo [WARN] Timeout waiting for server. Check log: %LOG_FILE%
goto show_server_log

:wait_success
echo [OK] Server ready!
goto continue_launch

:show_server_log
echo.
echo === SERVER LOG (last 30 lines) ===
if exist "%LOG_FILE%" (
  powershell -Command "Get-Content '%LOG_FILE%' -Tail 30"
) else (
  echo [LOG FILE NOT CREATED]
)
echo ================================
echo.
echo [ERROR] Server failed to start. Press any key to exit.
pause >nul
exit /b 1

:continue_launch
REM === SET ENV VARIABLES ===
set LLAMA_CPP_SERVER_URL=%URL%
set LLAMA_CPP_EXECUTABLE=%LLAMA_DIR%\llama.exe
set LLAMA_CPP_MODEL=%MODEL%

echo.
echo [ENV] Variables set:
echo   URL: %LLAMA_CPP_SERVER_URL%
echo   Model: %LLAMA_CPP_MODEL%
echo.

REM === START PYTHON TERMINAL ===
echo [5/5] Starting DM Terminal...
echo Commands: /ingest ^| /state ^| /exit
echo Type /exit to quit.
echo.

REM Run Python and capture exit code
"%PYTHON_CMD%" run_terminal_dm.py
set "PY_EXIT_CODE=%ERRORLEVEL%"

REM === DONE ===
echo.
if %PY_EXIT_CODE%==0 (
  echo [DONE] Session ended.
) else (
  echo [WARN] Python exited with code %PY_EXIT_CODE%
)
echo [INFO] Server still running in background.
echo        To stop: taskkill /F /IM llama-server.exe
pause