# 🔧 test_server_launch.ps1 — НЕ закрывается при ошибке!
# Запуск: из терминала VSCode: .\test_server_launch.ps1

# ❗ ВАЖНО: Не закрывать окно, даже если ошибка
$ErrorActionPreference = "Continue"
trap {
    Write-Host "❌ КРИТИЧЕСКАЯ ОШИБКА: $_" -ForegroundColor Red
    Write-Host "💡 Нажмите любую клавишу для выхода..." -ForegroundColor Yellow
    $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
    exit 1
}

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "🔍 Тест запуска llama-server" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Пути
$ServerExe = "C:\DDD\Codex\VSC_Enigma\Enigma\Models LLM\llama\llama-server.exe"
$ModelPath = "C:\DDD\Codex\VSC_Enigma\Enigma\Models LLM\qwen2.5-7b-instruct-q4_k_m.gguf"

# Автоматическая разблокировка файлов (если заблокированы Windows)
Write-Host "🔓 Автоматическая разблокировка файлов..." -ForegroundColor Yellow
Get-ChildItem "C:\DDD\Codex\VSC_Enigma\Enigma\Models LLM\llama" -Recurse | Unblock-File -ErrorAction SilentlyContinue
Write-Host "✅ Готово" -ForegroundColor Green
Write-Host ""

Write-Host "📁 Проверка путей:" -ForegroundColor Yellow
Write-Host "   EXE: $ServerExe"
Write-Host "   Модель: $ModelPath"
Write-Host ""

# Проверка 1: существует ли EXE?
if (-not (Test-Path $ServerExe)) {
    Write-Host "❌ ОШИБКА: Файл не найден: $ServerExe" -ForegroundColor Red
    Write-Host "💡 Проверьте путь или разблокируйте файл:" -ForegroundColor Gray
    Write-Host "   Unblock-File -Path '$ServerExe'" -ForegroundColor Gray
    Write-Host ""
    Write-Host "🔒 Нажмите любую клавишу для выхода (окно не закроется)..." -ForegroundColor Yellow
    $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
    exit 1
} else {
    Write-Host "✅ EXE найден" -ForegroundColor Green
}

# Проверка 2: существует ли модель?
if (-not (Test-Path $ModelPath)) {
    Write-Host "❌ ОШИБКА: Модель не найдена: $ModelPath" -ForegroundColor Red
    Write-Host ""
    Write-Host "🔒 Нажмите любую клавишу для выхода..." -ForegroundColor Yellow
    $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
    exit 1
} else {
    Write-Host "✅ Модель найдена" -ForegroundColor Green
}

# Проверка 3: разблокирован ли файл? (SmartScreen)
Write-Host ""
Write-Host "🔐 Проверка блокировки SmartScreen:" -ForegroundColor Yellow
$zone = Get-Item $ServerExe -Stream "Zone.Identifier" -ErrorAction SilentlyContinue
if ($zone) {
    Write-Host "⚠️ Файл ЗАБЛОКИРОВАН (скачан из интернета)" -ForegroundColor Red
    Write-Host "💡 Выполните в терминале:" -ForegroundColor Gray
    Write-Host "   Unblock-File -Path '$ServerExe'" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "🔒 Нажмите любую клавишу для выхода..." -ForegroundColor Yellow
    $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
    exit 1
} else {
    Write-Host "✅ Файл разблокирован" -ForegroundColor Green
}

# Проверка 4: порт 8080 свободен?
Write-Host ""
Write-Host "🌐 Проверка порта 8080:" -ForegroundColor Yellow
$listener = Get-NetTCPConnection -LocalPort 8080 -ErrorAction SilentlyContinue
if ($listener) {
    Write-Host "⚠️ Порт 8080 уже занят" -ForegroundColor Yellow
    Write-Host "💡 Завершите старый процесс или смените порт" -ForegroundColor Gray
} else {
    Write-Host "✅ Порт 8080 свободен" -ForegroundColor Green
}

# 🔧 Попытка запуска
Write-Host ""
Write-Host "🚀 Попытка запуска сервера..." -ForegroundColor Cyan
Write-Host ""

# Запуск через cmd /c start (обходит SmartScreen)
# Added -ngl 33 for GPU offload
$cmd = "start `"`" `"$ServerExe`" -ngl 33 -m `"$ModelPath`" -c 4096 --port 8080 --host 127.0.0.1 --threads 12 --no-warmup"
Write-Host "📦 Команда:" -ForegroundColor Gray
Write-Host "   $cmd" -ForegroundColor DarkGray
Write-Host ""

try {
    Invoke-Expression $cmd
    Write-Host "✅ Команда выполнена" -ForegroundColor Green
} catch {
    Write-Host "❌ Ошибка выполнения: $_" -ForegroundColor Red
    Write-Host "💡 Попробуйте запустить скрипт от имени администратора" -ForegroundColor Gray
}

# Финальная проверка: отвечает ли сервер?
Write-Host ""
Write-Host "🔄 Проверка ответа сервера (10 сек)..." -ForegroundColor Yellow
Start-Sleep -Seconds 5
try {
    $r = Invoke-WebRequest -Uri "http://127.0.0.1:8080/" -TimeoutSec 3 -UseBasicParsing
    if ($r.StatusCode -ge 200) {
        Write-Host "✅ СЕРВЕР РАБОТАЕТ! Ответ: $($r.StatusCode)" -ForegroundColor Green
        Write-Host "🌐 Откройте в браузере: http://127.0.0.1:8080/" -ForegroundColor Cyan
    }
} catch {
    Write-Host "⚠️ Сервер ещё не отвечает (это нормально, он грузится)" -ForegroundColor Yellow
    Write-Host "💡 Проверьте, появилось ли окно llama-server" -ForegroundColor Gray
}

# 🔒 ГЛАВНОЕ: окно НЕ закроется, пока вы не нажмёте клавишу
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "✅ Тест завершён" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "🔒 Нажмите ЛЮБУЮ клавишу для выхода..." -ForegroundColor Yellow
Write-Host "   (окно не закроется автоматически)" -ForegroundColor Gray
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")