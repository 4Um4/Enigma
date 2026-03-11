@echo off
chcp 65001 >nul
title Enigma LLM Server

echo ========================================
echo    Enigma LLM Server
echo ========================================
echo.

:: Configuration
set LLM_DIR=C:\DDD\Codex\VSC_Enigma\Enigma\Models LLM\llama
set MODEL_PATH=C:\DDD\Codex\VSC_Enigma\Enigma\Models LLM\qwen2.5-7b-instruct-q4_k_m.gguf
set MODEL_NAME=Qwen2.5-7B
set PORT=8080
set CONTEXT_SIZE=4096
set GPU_LAYERS=33

:: Check if llama-server.exe exists
if not exist "%LLM_DIR%\llama-server.exe" (
    echo [ERROR] llama-server.exe not found at: %LLM_DIR%
    echo Please check your installation
    pause
    exit /b 1
)

:: Check if model exists
if not exist "%MODEL_PATH%" (
    echo [ERROR] Model not found at: %MODEL_PATH%
    echo Please check your model file
    pause
    exit /b 1
)

:: Unblock files (Windows security)
echo [1/3] Unblocking files...
powershell -Command "Get-ChildItem '%LLM_DIR%' -Recurse -Filter '*.exe' | Unblock-File -ErrorAction SilentlyContinue"

echo [2/3] Starting LLM Server...
echo   Model: %MODEL_NAME%
echo   Path:  %MODEL_PATH%
echo   Port:  %PORT%
echo   Context: %CONTEXT_SIZE%
echo   GPU Layers: %GPU_LAYERS%
echo.

"%LLM_DIR%\llama-server.exe" ^
    -ngl %GPU_LAYERS% ^
    -m "%MODEL_PATH%" ^
    -c %CONTEXT_SIZE% ^
    --port %PORT% ^
    --host 127.0.0.1 ^
    --threads 8 ^
    --temp 0.7 ^
    --top-p 0.9 ^
    --repeat-penalty 1.1 ^
    --log-disable

if errorlevel 1 (
    echo.
    echo [ERROR] LLM server failed to start
    pause
    exit /b 1
)

echo.
echo [INFO] LLM server stopped
pause

