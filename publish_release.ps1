
param(
    [switch]$Publish,
    [switch]$CheckOnly
)

# publish_release.ps1
# Скрипт автоматической сборки и публикации релиза Bloodloom
# Порядок: версия (version.txt SSOT) → PyInstaller (один Bloodloom.exe;
# splash запускается этим же EXE через параметр --splash)
#          → чистый staging → установочник (Inno Setup, если установлен;
#          иначе portable-ZIP) → публикация на GitHub Releases.

# --- КОНФИГУРАЦИЯ ---
$RepoOwner = "4Um4"
$RepoName = "Enigma"
$SetupScriptPath = "enigma_setup.iss"
# Корень проекта = папка, где лежит этот скрипт (абсолютные пути обязательны:
# PS-командлеты используют текущее расположение, а .NET-методы — каталог
# ПРОЦЕССА; они не совпадают, если скрипт запущен из другой папки).
$RootDir = if ($PSScriptRoot) { $PSScriptRoot } else { (Get-Location).Path }
$VersionFile = Join-Path $RootDir "version.txt"
$StagingDir = Join-Path (Split-Path -Parent $RootDir) "RELIZZ"
$PythonExe = Join-Path $RootDir ".venv\Scripts\python.exe"
if (-not (Test-Path $PythonExe)) {
    $PythonExe = (Get-Command python -ErrorAction SilentlyContinue).Source
}
$GitHubLimit = 2147483648 # 2 ГБ — лимит одного ассета GitHub Releases
$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)

Write-Host "🚀 Начинаем сборку и публикацию релиза Bloodloom..." -ForegroundColor Cyan
Set-Location -LiteralPath $RootDir
if (-not $PythonExe -or -not (Test-Path $PythonExe)) {
    Write-Host "❌ Не найден Python для сборки. Ожидался .venv\Scripts\python.exe или python в PATH." -ForegroundColor Red
    exit 1
}

# --- Hygiene-гейт (P0-урок: NameError 'os' в незакоммиченном коде убил Фазу 5
# на 357 тиках; релиз из грязной копии везёт непроверенный код). Спрашиваем
# ДО инкремента version.txt — отказ не сжигает номер релиза.
$_dirty = git status --short
if ($_dirty) {
    Write-Host "⚠️  Рабочая копия ГРЯЗНАЯ ($(@($_dirty).Count) файлов). Релиз соберёт НЕЗАКОММИЧЕННЫЙ код (урок P0: NameError-os, 357 мёртвых тиков)." -ForegroundColor Yellow
    $ans = Read-Host "Продолжить всё равно? (y/N)"
    if ($ans -ne 'y') { Write-Host "Отменено."; exit }
}

# --- 0. Очистка папки build (оставляем только установщик моделей) ---
Write-Host "🧹 Очистка папки build..." -ForegroundColor Cyan
if (Test-Path "build") {
    Get-ChildItem -Path "build" -File | Remove-Item -Force
    Get-ChildItem -Path "build" -Directory | Remove-Item -Recurse -Force
} else {
    New-Item -ItemType Directory -Path "build" | Out-Null
}

# --- 1. ВЕРСИЯ (фикс сломанной логики S210). version.txt — счётчик релизов из
# 5 сегментов: первые два — фиксированный префикс (0.5), последние ТРИ катятся
# как десятичный счётчик с переносом:
#   0.5.3.9.6 → 0.5.3.9.7 → ... → 0.5.3.9.9 → 0.5.4.0.0 → 0.5.4.0.1 → ...
#   ... → 0.5.4.0.9 → 0.5.4.1.0 → ... (и далее 0.5.9.9.9 → 0.5.10.0.0).
# frontend/constants.py (PROJECT_VERSION) и backend/pyproject.toml синхронизируются.
if (-not (Test-Path $VersionFile)) {
    Write-Host "❌ Не найден $VersionFile — не от чего считать следующую версию!" -ForegroundColor Red; exit
}
$prev = (Get-Content $VersionFile -Raw).Trim().TrimStart('v').TrimStart('V')
$parts = $prev.Split('.')
if ($parts.Length -lt 5 -or ($parts | Where-Object { $_ -notmatch '^\d+$' })) {
    Write-Host "❌ $VersionFile содержит '$prev' — ожидается 5 числовых сегментов (например 0.5.3.9.6)!" -ForegroundColor Red; exit
}
$versionPrefix = "$($parts[0]).$($parts[1])"
$counter = [int]$parts[2] * 100 + [int]$parts[3] * 10 + [int]$parts[4]
$counter++
$NewVersion = if ($CheckOnly) { $prev } else { "$versionPrefix.$([math]::Floor($counter / 100)).$([math]::Floor(($counter % 100) / 10)).$($counter % 10)" }

if (-not $CheckOnly) { Set-Content -Path $VersionFile -Value $NewVersion -NoNewline }

# Синхронизация SSOT-файлов с новым значением version.txt.
# ВАЖНО: файлы в UTF-8 БЕЗ BOM и содержат кириллицу — читаем/пишем через .NET
# с явной кодировкой UTF8Encoding($false), иначе PS 5.1 (ANSI по умолчанию) их побьёт.
$ConstsPath = Join-Path $RootDir "frontend\constants.py"
$consts = [System.IO.File]::ReadAllText($ConstsPath, $Utf8NoBom)
if ($consts -notmatch 'PROJECT_VERSION:\s*str\s*=\s*"v?(\d+)\.(\d+)\.(\d+)') {
    Write-Host "❌ PROJECT_VERSION не найден в $ConstsPath!" -ForegroundColor Red; exit
}
$constsBase = "$($Matches[1]).$($Matches[2]).$($Matches[3])"
if ($constsBase -ne "$($parts[0]).$($parts[1]).$($parts[2])") {
    Write-Host "⚠️ База PROJECT_VERSION в $ConstsPath ($constsBase) расходится с $VersionFile ($versionPrefix.$($parts[2]).x) — синхронизирую по version.txt." -ForegroundColor Yellow
}
if (-not $CheckOnly) {
    $consts = $consts -replace 'PROJECT_VERSION:\s*str\s*=\s*"[^"]*"', "PROJECT_VERSION: str = `"$NewVersion`""
    [System.IO.File]::WriteAllText($ConstsPath, $consts, $Utf8NoBom)
}

$PyProjectPath = Join-Path $RootDir "backend\pyproject.toml"
if (Test-Path $PyProjectPath) {
    $py = [System.IO.File]::ReadAllText($PyProjectPath, $Utf8NoBom)
    if (-not $CheckOnly) {
        $py = $py -replace '(?m)^(\s*version\s*=\s*)"[^"]*"', "`$1`"$NewVersion`""
        [System.IO.File]::WriteAllText($PyProjectPath, $py, $Utf8NoBom)
    }
}
$CitationPath = Join-Path $RootDir "CITATION.cff"
if (-not $CheckOnly -and (Test-Path $CitationPath)) {
    $citation = [System.IO.File]::ReadAllText($CitationPath, $Utf8NoBom)
    $citation = $citation -replace '(?m)^version:\s*[^\r\n]+', "version: $NewVersion"
    [System.IO.File]::WriteAllText($CitationPath, $citation, $Utf8NoBom)
}
$ReadmePath = Join-Path $RootDir "README.md"
if (-not $CheckOnly -and (Test-Path $ReadmePath)) {
    $readme = [System.IO.File]::ReadAllText($ReadmePath, $Utf8NoBom)
    $readme = $readme -replace 'version-[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+-orange', "version-$NewVersion-orange"
    $readme = $readme -replace 'version\s*=\s*\{[0-9.]+\}', "version      = {$NewVersion}"
    $readme = $readme -replace '(?i)(Version\s+)[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+', "`${1}$NewVersion"
    [System.IO.File]::WriteAllText($ReadmePath, $readme, $Utf8NoBom)
}
Write-Host "Версия обновлена: v$NewVersion (счётчик: $versionPrefix + $($parts[2]).$($parts[3]).$($parts[4]) -> $([math]::Floor($counter / 100)).$([math]::Floor(($counter % 100) / 10)).$($counter % 10))" -ForegroundColor Yellow
# --- 2. Компиляция единственного Bloodloom.exe ---
Write-Host "🔨 Компиляция единственного Bloodloom.exe..." -ForegroundColor Cyan
& $PythonExe -m PyInstaller --onefile --noconsole --name Bloodloom --icon=Bloodloom.ico updater.py
if ($LASTEXITCODE -ne 0) { Write-Host "❌ Ошибка updater.py!" -ForegroundColor Red; exit }
Move-Item -Path "dist\Bloodloom.exe" -Destination "Bloodloom.exe" -Force
Remove-Item -Path "Bloodloom_splash.exe" -Force -ErrorAction SilentlyContinue

Remove-Item -Path "build\Bloodloom" -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -Path "Bloodloom.spec" -Force -ErrorAction SilentlyContinue
Write-Host "✅ Единственный Bloodloom.exe собран; splash встроен и запускается через --splash" -ForegroundColor Green

# --- 2.5 Подготовка чистой копии кода (Staging) ---
Write-Host "📦 Подготовка кода (копирование исходников)..." -ForegroundColor Cyan
# Staging ВНЕ корня проекта: build/ внутри корня копил 1.3 ГБ мусора
# между сборками, попадал в поле git/robocopy и распухал бэкапы.
if (Test-Path $StagingDir) { Remove-Item -Recurse -Force $StagingDir }
New-Item -ItemType Directory -Path $StagingDir | Out-Null

# /XD — личные данные и мусор в staging не нужны: saves/ и saves_census/ —
# персональные сохранения разработчика, НИКОГДА не должны попадать в релиз;
# dist, runtime_cache, кэши тестов/линтеров, диагностика — dev-артефакты.
# /XF *.db* — runtime БД (в т.ч. saves корневые) не пакуем даже по ошибке пути.
robocopy . $StagingDir /E `
    /XD .venv .git .github .vscode .githooks .hypothesis .pytest_cache .mypy_cache .ruff_cache .pytest_tmp `
        build dist logs reports __pycache__ "Models LLM" payload .venv311 `
        saves saves_census runtime_cache test_data diagnostics _archive `
        download scripts tests Tests lint archaeology_reports docs `
        backup_s256 backup_s259 "backend\tests" `
    /XF *.pyc *.log *.spec *.db *.db-shm *.db-wal *_crash.log *.bak eatlog_out*.txt Math_GAME.md TODO.md `
        arch_out*.txt refs_report.txt deps_*.json drift_logs*.txt `
        *.iss *.ps1 mypy.ini ruff.toml pytest.ini pyproject.toml gc05_full.txt pyrightconfig.json splash.py updater.py `
        .gitignore .gitattributes .pre-commit-config.yaml replay.db > $null

# Сантификация staging: дочищаем разработческий мусор корня, который
# robocopy не ловит масками (отчётливые отладочные дампы и служебные скрипты).
Write-Host "🧽 Сантификация staging (удаляем дев-мусор из корня)..." -ForegroundColor Cyan
$JunkFiles = @(
    "apply_patch.py", "apply_r4_handoff.py", "apply_r4_*.py", "build_graph.py",
    "r4_debug_idle.py",
    "deps_compressed.json", "deps_stats.json",
    "g4_regression.txt", "g4_test_output.txt", "g5_reg.txt",
    "h1_arch.txt", "h1_q1.txt", "h2_arch.txt", "h_arch.txt", "k2_full.txt",
    "mypy_check_run.txt", "vram_test_err.log", "vram_test_out.log"
)
Get-ChildItem -Path $StagingDir -File |
    Where-Object { $JunkFiles -contains $_.Name -or $_.Name -like "R4_*.txt" -or $_.Name -like "apply_r4_*.py" } |
    Remove-Item -Force
Get-ChildItem -Path "$StagingDir\archaeology_reports" -Directory -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
Get-ChildItem -Path "$StagingDir\download" -Directory -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
Get-ChildItem -Path "$StagingDir\tmp_test_*" -Directory -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
Get-ChildItem -Path "$StagingDir\_archive" -Directory -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
# Content-gate (аудит релиза, BUG-04): архитектурные YAML-контракты
# обязательны в релизе — runtime читает их (signal_causes.yaml и др.).
# Пустая architecture/ = сборка запрещена.
$ArchYaml = Get-ChildItem "$StagingDir\architecture" -Filter "*.yaml" -Recurse -ErrorAction SilentlyContinue
if (-not $ArchYaml -or @($ArchYaml).Count -eq 0) {
    Write-Host "❌ Content-gate: architecture/*.yaml отсутствует в staging — сборка прервана!" -ForegroundColor Red; exit
}
Write-Host "✅ Content-gate: architecture/$(@($ArchYaml).Count) yaml в staging" -ForegroundColor Green

# 2.7 S210 (BUILD-P1): payload-звено — портативный Python для установщика.
# updater.py ожидает портативный Python в {app}\_internal\python\ (см.
# prepare_python.ps1). Кэшируется: повторные сборки пропускают скачивание.
if (-not (Test-Path "payload\python\python.exe")) {
    Write-Host "🐍 Подготовка payload (портативный Python; первый запуск качает ~15 МБ + зависимости)..." -ForegroundColor Cyan
    & powershell -ExecutionPolicy Bypass -File prepare_python.ps1
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path "payload\python\python.exe")) {
        Write-Host "❌ prepare_python.ps1 не создал payload\python\python.exe — сборка прервана." -ForegroundColor Red; exit
    }
} else {
    Write-Host "✅ payload/python найден (кэш прошлой сборки)" -ForegroundColor Green
}

# Кладём портативный Python в staging именно там, где его ждёт updater.py
# (_internal\python\) — иначе на чужом ПК игра не запустится без системного Python.
$PyPayload = Join-Path $RootDir "payload\python"
if (Test-Path $PyPayload) {
    $DestPy = Join-Path $StagingDir "_internal\python"
    New-Item -ItemType Directory -Path $DestPy -Force | Out-Null
    robocopy $PyPayload $DestPy /E /XD __pycache__ /XF *.pyc *.log > $null
    Write-Host "✅ Портативный Python скопирован в staging\_internal\python" -ForegroundColor Green
} else {
    Write-Host "⚠️ payload\python не найден — установщик будет без встроенного Python (требуется системный Python 3.13 на целевом ПК)." -ForegroundColor Yellow
}

# --- 2.8 Копирование llama-server.exe (или main.exe) в staging ---
# Этот файл нужен для запуска LLM-сервера. Если его нет в исходной папке,
# скрипт пытается скачать его с официального репозитория llama.cpp (GitHub).
Write-Host "🔧 Копируем llama-server.exe в staging..." -ForegroundColor Cyan
$LlamaSource = Join-Path $RootDir "Models LLM\llama"
$LlamaExe = Get-ChildItem -Path $LlamaSource -Filter "*.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
if ($LlamaExe) {
    $DestLlamaExe = Join-Path $StagingDir "Models LLM\llama\llama-server.exe"
    New-Item -ItemType Directory -Path (Split-Path $DestLlamaExe -Parent) -Force | Out-Null
    Copy-Item -Path $LlamaExe.FullName -Destination $DestLlamaExe -Force
    Write-Host "✅ Скопирован llama-server.exe в staging." -ForegroundColor Green
} else {
    Write-Host "⚠️ llama-server.exe не найден в $LlamaSource — пытаемся скачать с GitHub..." -ForegroundColor Yellow
    $LlamaUrl = "https://github.com/ggml-org/llama.cpp/releases/latest/download/llama-server.exe"
    $DestLlamaExe = Join-Path $StagingDir "Models LLM\llama\llama-server.exe"
    New-Item -ItemType Directory -Path (Split-Path $DestLlamaExe -Parent) -Force | Out-Null
    try {
        Invoke-WebRequest -Uri $LlamaUrl -OutFile $DestLlamaExe -UseBasicParsing -ErrorAction Stop
        Write-Host "✅ Скачан llama-server.exe из GitHub." -ForegroundColor Green
    } catch {
        Write-Host "❌ Не удалось скачать llama-server.exe: $($_.Exception.Message)" -ForegroundColor Red
    }
}

# --- 3. Компиляция установочника (Inno Setup) ИЛИ portable-ZIP ---
Write-Host "🔨 Компиляция установочника..." -ForegroundColor Cyan
Write-Host "🔨 Компиляция установочника..." -ForegroundColor Cyan
$ISCCPath = "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if (-not (Test-Path $ISCCPath)) { $ISCCPath = "C:\Program Files\Inno Setup 6\ISCC.exe" }
if (-not (Test-Path $ISCCPath)) { $ISCCPath = (Get-Command ISCC.exe -ErrorAction SilentlyContinue).Source }

if ($ISCCPath -and (Test-Path $ISCCPath)) {
    Write-Host "✅ Inno Setup найден: $ISCCPath" -ForegroundColor Green
    & $ISCCPath /DAppVersion=$NewVersion $SetupScriptPath /Qp
    if ($LASTEXITCODE -ne 0) { Write-Host "❌ Ошибка компиляции Inno Setup!" -ForegroundColor Red; exit }
    Write-Host "✅ Инсталлятор Inno Setup собран" -ForegroundColor Green
} else {
    Write-Host "⚠️  Inno Setup (ISCC.exe) не найден в системе." -ForegroundColor Yellow
    Write-Host "   (поставить: https://jrsoftware.org/is.php — или используйте portable-ZIP ниже)" -ForegroundColor Yellow
    Write-Host "   Собираем portable-выпуск (ZIP) вместо инсталлятора..." -ForegroundColor Yellow

    $SevenZip = (Get-Command 7z -ErrorAction SilentlyContinue).Source
    $ZipDest = Join-Path (Resolve-Path "build").Path "Bloodloom_portable_v$NewVersion.zip"
    if ($SevenZip) {
        & $SevenZip a -tzip -mx=9 "$ZipDest" "$StagingDir\*" > $null
    } else {
        Compress-Archive -Path "$StagingDir\*" -DestinationPath $ZipDest -CompressionLevel Optimal -Force
    }
    if ($LASTEXITCODE -ne 0) { Write-Host "❌ Ошибка создания portable-ZIP!" -ForegroundColor Red; exit }
    Write-Host "✅ Portable-выпуск собран: $ZipDest" -ForegroundColor Green
}

$SetupFiles = Get-ChildItem -Path "build" -File |
    Where-Object { $_.Name -like "Bloodloom_setup_v*" -or $_.Name -like "Bloodloom_portable_v*" } |
    Select-Object -ExpandProperty FullName
if (-not $SetupFiles) {
    Write-Host "❌ Ошибка: Не найдены скомпилированные файлы в папке build!" -ForegroundColor Red; exit
}
Write-Host "✅ Установочники готовы: $($SetupFiles -join ', ')" -ForegroundColor Green

# --- 4. Проверка лимита GitHub (2 ГБ) и сжатие при превышении ---
$FilesToUpload = @()
$ArchiverPath = @(
    "C:\Program Files\WinRAR\Rar.exe",
    "C:\Program Files (x86)\WinRAR\Rar.exe",
    "$env:ProgramFiles\WinRAR\Rar.exe",
    "${env:ProgramFiles(x86)}\WinRAR\Rar.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1

if (-not $ArchiverPath) {
    $ArchiverPath = (Get-Command Rar.exe -ErrorAction SilentlyContinue).Source
    if (-not $ArchiverPath) {
        $ArchiverPath = (Get-Command WinRAR.exe -ErrorAction SilentlyContinue).Source
    }
}

foreach ($file in $SetupFiles) {
    $fileSize = (Get-Item $file).Length
    if ($fileSize -ge $GitHubLimit) {
        Write-Host "🗜️ Файл $file превышает лимит GitHub ($fileSize байт). Сжатие через WinRAR..." -ForegroundColor Yellow
        if (-not $ArchiverPath) { Write-Host "❌ Ошибка: WinRAR (Rar.exe) не найден в системе!" -ForegroundColor Red; exit }

        $ArchivePath = [System.IO.Path]::ChangeExtension($file, ".rar")
        # a - создать архив, -m5 - макс. сжатие, -v2048m - тома по 2 ГБ, -ep - исключить пути из имен
        & $ArchiverPath a -m5 -v2048m -ep $ArchivePath $file
        if ($LASTEXITCODE -ne 0) { Write-Host "❌ Ошибка сжатия WinRAR!" -ForegroundColor Red; exit }

        $ArchiveBaseName = [System.IO.Path]::GetFileNameWithoutExtension($ArchivePath)
        $SplitArchives = Get-ChildItem -Path ([System.IO.Path]::GetDirectoryName($file)) -Filter "$ArchiveBaseName*.rar*"
        $FilesToUpload += $SplitArchives.FullName
    } else {
        $FilesToUpload += $file
    }
}
Write-Host "✅ Файлы к публикации: $($FilesToUpload -join ', ')" -ForegroundColor Green

# --- 5a. Проверка и установка CUDA (если нужно) ---
Write-Host "🔍 Проверка наличия CUDA..." -ForegroundColor Cyan
$nvidiaSmi = Get-Command nvidia-smi -ErrorAction SilentlyContinue
if ($nvidiaSmi) {
    Write-Host "✅ CUDA обнаружен: $($nvidiaSmi.Source)" -ForegroundColor Green
} else {
    Write-Host "⚠️ CUDA не найден. Сборка продолжится; автоматическая установка драйвера запрещена." -ForegroundColor Yellow
}

# --- 5. Публикация на GitHub (только с -Publish) ---
if (-not $Publish) {
    Write-Host "✅ Проверка сборки завершена. Публикация пропущена (для публикации используйте -Publish)." -ForegroundColor Green
    exit 0
}
Write-Host "☁️ Публикация релиза на GitHub..." -ForegroundColor Cyan
try {
    gh auth status 2>&1 | Out-Null
} catch {
    Write-Host "❌ Вы не авторизованы в GitHub CLI. Выполните: gh auth login" -ForegroundColor Red
    exit
}

$TagName = "v$NewVersion"
$ReleaseTitle = "Bloodloom Update $TagName"
$ReleaseNotes = "Ежедневное обновление MVP. Версия $TagName."

Write-Host "🧹 Очистка старых релизов (оставляем 3 последние)..." -ForegroundColor Cyan
$releasesJson = gh api repos/$RepoOwner/$RepoName/releases --paginate 2>$null | ConvertFrom-Json
if ($releasesJson) {
    $sortedReleases = $releasesJson | Sort-Object -Property created_at -Descending
    $releasesToDelete = $sortedReleases | Select-Object -Skip 3
    foreach ($rel in $releasesToDelete) {
        Write-Host "  Удаление старого релиза: $($rel.tag_name)..." -ForegroundColor Yellow
        gh release delete $rel.tag_name --repo "$RepoOwner/$RepoName" --yes 2>$null
    }
}
Write-Host "✅ Очистка завершена." -ForegroundColor Green

# Конфликт тегов: version.txt может отставать от реальных тегов в репо
# (наблюдалось: существовал v0.5.3.15 при счётчике 10). Перед публикацией
# удаляем релиз и тег с тем же именем, если они есть.
$existingRelease = gh release view $TagName --repo "$RepoOwner/$RepoName" 2>$null
if ($existingRelease) {
    Write-Host "Тег $TagName уже существует — удаляю старый релиз и тег..." -ForegroundColor Yellow
    gh release delete $TagName --repo "$RepoOwner/$RepoName" --yes 2>$null
    git push --delete origin $TagName 2>$null
}

gh release create $TagName $FilesToUpload `
    --repo "$RepoOwner/$RepoName" `
    --title "$ReleaseTitle" `
    --notes "$ReleaseNotes" `
    --latest

if ($LASTEXITCODE -eq 0) {
    Write-Host "🎉 Релиз $TagName успешно опубликован на GitHub!" -ForegroundColor Green
} else {
    Write-Host "❌ Ошибка публикации релиза." -ForegroundColor Red
}
