@echo off
chcp 65001 >nul
title Enigma LLM Server (Stable)


:: ========================================
:: 1. Создание timestamped лог-файла
:: ========================================
powershell -Command "$dt = Get-Date -Format 'yyyyMMdd_HHmmss'; Write-Output $dt" > "%TEMP%\llm_timestamp.txt"
set /p dt=<"%TEMP%\llm_timestamp.txt"
del "%TEMP%\llm_timestamp.txt"

:: Убираем запрещённые символы
set "dt=%dt::=-%"
set "dt=%dt:/=-%"
set "dt=%dt: =_%"

:: ========================================
:: 2. Конфигурация (относительные пути)
:: ========================================
:: ROOT_DIR = Enigma
set "ROOT_DIR=%~dp0.."

:: LLM директория
set "LLM_DIR=%ROOT_DIR%\Models LLM\llama"
set "LLAMA_EXE=%LLM_DIR%\llama-server.exe"
set "MODEL_PATH=%ROOT_DIR%\Models LLM\Qwen3.5-9B.gguf"

:: Сервер
set "LLM_PORT=8080"
set "CONTEXT_SIZE=4096"
set "GPU_LAYERS=33"

:: Логи backend
set "LOG_DIR=%ROOT_DIR%\backend\logs"
set "LOGFILE=%LOG_DIR%\llm_%dt%.log"

:: ========================================
:: 4. Разблокировка exe
:: ========================================
echo [1/3] Unblocking files...
powershell -Command "Get-ChildItem '%LLM_DIR%' -Recurse -Filter '*.exe' | Unblock-File -ErrorAction SilentlyContinue"

:: ========================================
:: 5. Создание папки логов
:: ========================================
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

:: ========================================
:: 6. Старт LLM сервера в отдельном окне
:: ========================================
echo [2/3] Starting LLM Server...
echo [INFO] LLM server start >> "%LOGFILE%"


:: ===== Ключ: используем start с абсолютным путем и кавычками, без cmd /c =====
start "Enigma LLM" "%LLAMA_EXE%" ^
    --verbose ^
    -ngl %GPU_LAYERS% ^
    -m "%MODEL_PATH%" ^
    -c %CONTEXT_SIZE% ^
    --port %LLM_PORT% ^
    --host 127.0.0.1 ^
    --no-context-shift ^
    --n-predict 800 ^
    --threads 8 ^
    --temp 0.7 ^
    --top-p 0.9 ^
    --repeat-penalty 1.1 ^
    >> "%LOGFILE%" 2>&1

:: ========================================
:: 7. Tail логов
:: ========================================
echo [INFO] LLM server started in background
echo [INFO] Tail logs:
powershell -Command "Get-Content '%LOGFILE%' -Tail 50 -Wait"

pause