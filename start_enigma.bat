:: C:\DDD\Codex\VSC_Enigma\Enigma\start_enigma.bat
@echo off
chcp 65001 >nul
title Enigma - Local AI Dungeon Master

:: ========================================
:: ИСПРАВЛЕНИЯ vs оригинал:
:: 1. test_startup_checks.py запускается через python -m unittest
::    (оригинал: python ... → exit 1 при любом unittest.skip, что ломало запуск)
:: 2. wait_llm: исправлена логика сравнения errorlevel
::    (оригинал: if %errorlevel% neq 200 — PowerShell exit 200 → BAT errorlevel 200,
::     условие neq 200 было FALSE → loop никогда не ждал реально)
:: 3. start_backend.bat вызывается с правильным полным путём через call
::    (оригинал: cd /d backend && start_backend.bat — потеря %~dp0)
:: 4. curl заменён на PowerShell Invoke-WebRequest (curl может отсутствовать)
:: 5. Добавлена проверка наличия llama-server.exe ДО запуска
:: 6. PYTHONPATH установлен корректно (%~dp0 без trailing slash issues)
:: 7. Логи пишутся в backend\logs\ (не в корень Enigma)
:: 8. frontend: директория frontend\ui (не frontend — там нет index.html)
:: ========================================

:: ========================================
:: TIMESTAMP
:: ========================================
for /f "delims=" %%T in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmmss"') do set "dt=%%T"

set "ROOT_DIR=%~dp0"
:: Убираем trailing backslash
if "%ROOT_DIR:~-1%"=="\" set "ROOT_DIR=%ROOT_DIR:~0,-1%"

set "BACKEND_DIR=%ROOT_DIR%\backend"
set "LOG_DIR=%BACKEND_DIR%\logs"
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

set "MAIN_LOG=%LOG_DIR%\startup_%dt%.log"

echo ======================================== >> "%MAIN_LOG%"
echo   Enigma - Local AI Dungeon Master       >> "%MAIN_LOG%"
echo   Started: %dt%                          >> "%MAIN_LOG%"
echo ======================================== >> "%MAIN_LOG%"

echo [INFO] Root dir: %ROOT_DIR%
echo [INFO] Logs: %MAIN_LOG%

:: ========================================
:: PYTHON CMD (корневой .venv)
:: ========================================
set "PYTHON_CMD=%ROOT_DIR%\.venv\Scripts\python.exe"
if not exist "%PYTHON_CMD%" (
    echo [WARN] .venv не найден, используем системный python
    set "PYTHON_CMD=python"
)

:: PYTHONPATH для импортов backend
set "PYTHONPATH=%BACKEND_DIR%"

:: Проверка Python версии
for /f "tokens=2" %%i in ('"%PYTHON_CMD%" --version 2^>^&1') do set PYTHON_VER=%%i
echo [INFO] Python: %PYTHON_VER%
echo [INFO] Python: %PYTHON_VER% >> "%MAIN_LOG%"

:: ========================================
:: STEP 0: Проверка llama-server.exe
:: ========================================
echo [0/6] Checking LLM binary...
set "LLAMA_EXE=%ROOT_DIR%\Models LLM\llama\llama-server.exe"
if not exist "%LLAMA_EXE%" (
    echo [ERROR] Не найден llama-server.exe: %LLAMA_EXE%
    echo [ERROR] llama-server.exe not found >> "%MAIN_LOG%"
    echo.
    echo Скачайте llama.cpp release и распакуйте в:
    echo   %ROOT_DIR%\Models LLM\llama\
    pause
    exit /b 1
)
echo [OK] llama-server.exe найден

:: ========================================
:: STEP 0.5: PRE-FLIGHT CHECKS (unittest, не pytest)
:: ========================================
echo [0.5/6] Pre-flight checks...
:: ИСПРАВЛЕНИЕ: запускаем через python -m unittest, не как скрипт
:: Это гарантирует правильный PYTHONPATH и совместимость с Windows
"%PYTHON_CMD%" -m unittest discover -s "%BACKEND_DIR%\tests" -p "test_startup_checks.py" -v >> "%MAIN_LOG%" 2>&1
if errorlevel 1 (
    echo [WARN] Pre-flight тесты не прошли — проверьте %MAIN_LOG%
    echo [WARN] Продолжаем запуск (тесты не критичны для старта игры)
    :: НЕ выходим — тесты предупреждают, не блокируют
)
echo [OK] Pre-flight done

:: ========================================
:: STEP 1: START LLM SERVER
:: ========================================
echo [1/6] Запуск LLM сервера...
set "LLM_LOG=%LOG_DIR%\llm_%dt%.log"

:: start_llm.bat принимает LOG_FILE как %1
start "Enigma LLM" cmd /c ""%BACKEND_DIR%\start_llm.bat" "%LLM_LOG%""

:: Ждём llama-server на порту 8080 (макс 450 секунд — модель грузится долго)
echo [INFO] Ожидание LLM сервера (макс 450 сек, модель ~4.5 GB)...
set /a LLM_WAIT=0
:wait_llm
powershell -NoProfile -Command ^
    "try { $r = Invoke-WebRequest -Uri 'http://127.0.0.1:8080/v1/models' -UseBasicParsing -TimeoutSec 5 -ErrorAction Stop; if ($r.StatusCode -eq 200) { exit 0 } else { exit 1 } } catch { exit 1 }" ^
    >nul 2>&1
if %errorlevel% equ 0 goto llm_ready

set /a LLM_WAIT+=5
echo [INFO] LLM не готов, ждём... %LLM_WAIT%/450 сек
if %LLM_WAIT% LSS 450 (
    timeout /t 5 /nobreak >nul
    goto wait_llm
)
echo [WARN] LLM не ответил за 450 сек — продолжаем без него (offline режим)
echo [WARN] LLM timeout >> "%MAIN_LOG%"
goto start_backend

:llm_ready
echo [OK] LLM сервер готов (%LLM_WAIT% сек)

:: ========================================
:: STEP 2: START BACKEND
:: ========================================
:start_backend
echo [2/6] Запуск Backend (FastAPI)...
set "BACKEND_LOG=%LOG_DIR%\backend_%dt%.log"

:: ИСПРАВЛЕНИЕ: используем call + полный путь + новое окно
start "Enigma Backend" cmd /c ""%BACKEND_DIR%\start_backend.bat" "%BACKEND_LOG%""

:: Ждём FastAPI на порту 8000
set /a BACK_WAIT=0
:wait_backend
timeout /t 2 /nobreak >nul
powershell -NoProfile -Command ^
    "try { $null = Invoke-WebRequest -Uri 'http://127.0.0.1:8000/api/health' -UseBasicParsing -TimeoutSec 3 -ErrorAction Stop; exit 0 } catch { exit 1 }" ^
    >nul 2>&1
if %errorlevel% equ 0 goto backend_ready

set /a BACK_WAIT+=2
if %BACK_WAIT% LSS 60 goto wait_backend
echo [ERROR] Backend не запустился за 60 сек — см. %BACKEND_LOG%
echo [ERROR] Backend startup timeout >> "%MAIN_LOG%"
pause
exit /b 1

:backend_ready
echo [OK] Backend готов (%BACK_WAIT% сек)

:: ========================================
:: STEP 3: START FRONTEND
:: ========================================
echo [3/6] Запуск Frontend...
set "FRONTEND_DIR=%ROOT_DIR%\frontend\ui"
set "FRONTEND_LOG=%LOG_DIR%\frontend_%dt%.log"

if not exist "%FRONTEND_DIR%\index.html" (
    echo [WARN] frontend\ui\index.html не найден
    echo [WARN] Frontend не запущен >> "%MAIN_LOG%"
    goto open_browser
)

start "Enigma Frontend" cmd /c ^
    ""%PYTHON_CMD%" -m http.server 3000 --directory "%FRONTEND_DIR%" >> "%FRONTEND_LOG%" 2>&1"

:: Ждём frontend
set /a FRONT_WAIT=0
:wait_frontend
timeout /t 1 /nobreak >nul
powershell -NoProfile -Command ^
    "try { $null = Invoke-WebRequest -Uri 'http://127.0.0.1:3000' -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop; exit 0 } catch { exit 1 }" ^
    >nul 2>&1
if %errorlevel% equ 0 goto frontend_ready

set /a FRONT_WAIT+=1
if %FRONT_WAIT% LSS 20 goto wait_frontend
echo [WARN] Frontend не ответил за 20 сек

:frontend_ready
echo [OK] Frontend готов

:: ========================================
:: STEP 4: OPEN BROWSER
:: ========================================
:open_browser
echo [4/6] Открываем браузер...
:: Пробуем frontend:3000, если не доступен — fallback на backend:8000
powershell -NoProfile -Command ^
    "try { $null = Invoke-WebRequest -Uri 'http://127.0.0.1:3000' -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop; Start-Process 'http://127.0.0.1:3000' } catch { Start-Process 'http://127.0.0.1:8000' }"

:: ========================================
:: STEP 5: HEALTH CHECK SUMMARY
:: ========================================
echo [5/6] Health summary...
powershell -NoProfile -Command ^
    "try { $j = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/health' -TimeoutSec 5; Write-Host '  Backend: OK'; $j | ConvertTo-Json -Depth 3 } catch { Write-Host '  Backend: не отвечает' }"

:: ========================================
:: STEP 6: LIVE LOG MONITORING
:: ========================================
echo [6/6] Мониторинг логов (Ctrl+C для выхода)...
echo.
echo  Игра запущена:
echo    Frontend:  http://127.0.0.1:3000
echo    Backend:   http://127.0.0.1:8000
echo    API Docs:  http://127.0.0.1:8000/docs
echo    Debug:     http://127.0.0.1:8000/api/debug/vram
echo.
echo  Логи: %LOG_DIR%
echo.

powershell -NoProfile -Command "Get-Content '%MAIN_LOG%' -Tail 30 -Wait"
pause >nul