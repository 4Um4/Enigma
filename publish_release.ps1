# publish_release.ps1
# Скрипт автоматической сборки и публикации релиза Bloodloom

# --- КОНФИГУРАЦИЯ ---
 $RepoOwner = "4Um4"
 $RepoName = "Enigma"
 $SetupScriptPath = "enigma_setup.iss"
# Корень проекта = папка, где лежит этот скрипт (абсолютные пути обязательны:
# PS-командлеты используют текущее расположение, а .NET-методы — каталог
# ПРОЦЕССА; они не совпадают, если скрипт запущен из другой папки).
 $RootDir = if ($PSScriptRoot) { $PSScriptRoot } else { (Get-Location).Path }
 $VersionFile = Join-Path $RootDir "version.txt"

Write-Host "🚀 Начинаем сборку и публикацию релиза Bloodloom..." -ForegroundColor Cyan

# 0. Очистка папки build (оставляем только установщик моделей)
Write-Host "🧹 Очистка папки build..." -ForegroundColor Cyan
if (Test-Path "build") {
    Get-ChildItem -Path "build" -File | Remove-Item -Force
    Get-ChildItem -Path "build" -Directory | Remove-Item -Recurse -Force
} else {
    New-Item -ItemType Directory -Path "build" | Out-Null
}

# 1. ВЕРСИЯ (фикс сломанной логики S210). version.txt — счётчик релизов из
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
 $NewVersion = "$versionPrefix.$([math]::Floor($counter / 100)).$([math]::Floor(($counter % 100) / 10)).$($counter % 10)"

Set-Content -Path $VersionFile -Value $NewVersion -NoNewline

# Синхронизация SSOT-файлов с новым значением version.txt.
# ВАЖНО: файлы в UTF-8 БЕЗ BOM и содержат кириллицу — читаем/пишем через .NET
# с явной кодировкой UTF8Encoding($false), иначе PS 5.1 (ANSI по умолчанию) их побьёт.
 $Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
 $ConstsPath = Join-Path $RootDir "frontend\constants.py"
 $consts = [System.IO.File]::ReadAllText($ConstsPath, $Utf8NoBom)
if ($consts -notmatch 'PROJECT_VERSION:\s*str\s*=\s*"v?(\d+)\.(\d+)\.(\d+)') {
    Write-Host "❌ PROJECT_VERSION не найден в $ConstsPath!" -ForegroundColor Red; exit
}
 $constsBase = "$($Matches[1]).$($Matches[2]).$($Matches[3])"
if ($constsBase -ne "$($parts[0]).$($parts[1]).$($parts[2])") {
    Write-Host "⚠️ База PROJECT_VERSION в $ConstsPath ($constsBase) расходится с $VersionFile ($versionPrefix.$($parts[2]).x) — синхронизирую по version.txt." -ForegroundColor Yellow
}
 $consts = $consts -replace 'PROJECT_VERSION:\s*str\s*=\s*"[^"]*"', "PROJECT_VERSION: str = `"v$NewVersion`""
[System.IO.File]::WriteAllText($ConstsPath, $consts, $Utf8NoBom)

 $PyProjectPath = Join-Path $RootDir "backend\pyproject.toml"
if (Test-Path $PyProjectPath) {
     $py = [System.IO.File]::ReadAllText($PyProjectPath, $Utf8NoBom)
     $py = $py -replace '(?m)^(\s*version\s*=\s*)"[^"]*"', "`$1`"$NewVersion`""
    [System.IO.File]::WriteAllText($PyProjectPath, $py, $Utf8NoBom)
}
Write-Host "Версия обновлена: v$NewVersion (счётчик: $versionPrefix + $($parts[2]).$($parts[3]).$($parts[4]) -> $([math]::Floor($counter / 100)).$([math]::Floor(($counter % 100) / 10)).$($counter % 10))" -ForegroundColor Yellow

# 2. Компиляция Bloodloom.exe и Splash Screen
Write-Host "🔨 Компиляция Bloodloom.exe и Splash Screen..." -ForegroundColor Cyan
python -m PyInstaller --onefile --noconsole --name Bloodloom_splash --icon=Bloodloom.ico splash.py
if ($LASTEXITCODE -ne 0) { Write-Host "❌ Ошибка splash.py!" -ForegroundColor Red; exit }
Move-Item -Path "dist\Bloodloom_splash.exe" -Destination "Bloodloom_splash.exe" -Force

python -m PyInstaller --onefile --noconsole --name Bloodloom --icon=Bloodloom.ico updater.py
if ($LASTEXITCODE -ne 0) { Write-Host "❌ Ошибка updater.py!" -ForegroundColor Red; exit }
Move-Item -Path "dist\Bloodloom.exe" -Destination "Bloodloom.exe" -Force

Remove-Item -Path "build\Bloodloom_splash" -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -Path "build\Bloodloom" -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -Path "Bloodloom.spec" -Force -ErrorAction SilentlyContinue
Remove-Item -Path "Bloodloom_splash.spec" -Force -ErrorAction SilentlyContinue
Write-Host "✅ Bloodloom.exe и Splash Screen собраны" -ForegroundColor Green

# 2.5 Подготовка копии кода (Staging)
Write-Host "📦 Подготовка кода (копирование исходников)..." -ForegroundColor Cyan
 $StagingDir = "build\staging"
if (Test-Path $StagingDir) { Remove-Item -Recurse -Force $StagingDir }
New-Item -ItemType Directory -Path $StagingDir | Out-Null

# /XD — личные данные и мусор в staging не нужны: saves/ и saves_census/ —
# персональные сохранения разработчика, НИКОГДА не должны попадать в релиз;
# dist, runtime_cache, кэши тестов/линтеров, диагностика — dev-артефакты.
# /XF *.db* —-runtime БД (в т.ч. saves корневые) не пакуем даже по ошибке пути.
robocopy . $StagingDir /E `
    /XD .venv .git .github .vscode .githooks .hypothesis .pytest_cache .mypy_cache .ruff_cache `
        build dist logs reports __pycache__ "Models LLM" payload `
        saves saves_census runtime_cache test_data diagnostics _archive `
        docs architecture scripts tests Tests lint `
    /XF *.pyc *.log *.spec *.db *.db-shm *.db-wal *_crash.log `
        arch_out*.txt refs_report.txt deps_*.json drift_logs*.txt `
        *.iss *.ps1 mypy.ini ruff.toml pytest.ini pyproject.toml `
        .gitignore .gitattributes .pre-commit-config.yaml > $null

Write-Host "✅ Исходный код скопирован во временную папку" -ForegroundColor Green

# 2.7 S210 (BUILD-P1): payload-звено — портативный Python для установщика.
# enigma_setup.iss требует payload\python\*, но оркестратор его никогда не
# создавал (prepare_python.ps1 существовал, но не вызывался). Кэшируется:
# повторные сборки пропускают скачивание.
if (-not (Test-Path "payload\python\python.exe")) {
    Write-Host "🐍 Подготовка payload (портативный Python; первый запуск качает ~15 МБ + зависимости)..." -ForegroundColor Cyan
    & powershell -ExecutionPolicy Bypass -File prepare_python.ps1
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path "payload\python\python.exe")) {
        Write-Host "❌ prepare_python.ps1 не создал payload\python\python.exe — сборка прервана." -ForegroundColor Red; exit
    }
} else {
    Write-Host "✅ payload/python найден (кэш прошлой сборки)" -ForegroundColor Green
}

# 3. Компиляция основного установщика
Write-Host "🔨 Компиляция основного установочника..." -ForegroundColor Cyan
 $ISCCPath = "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if (-not (Test-Path $ISCCPath)) { Write-Host "❌ Ошибка: Не найден Inno Setup (ISCC.exe)." -ForegroundColor Red; exit }

& $ISCCPath /DAppVersion=$NewVersion $SetupScriptPath /Qp
if ($LASTEXITCODE -ne 0) { Write-Host "❌ Ошибка компиляции Inno Setup!" -ForegroundColor Red; exit }

# 4. Установщик моделей больше не собираем (модели будут скачиваться по ссылкам из настроек игры)
 $SetupFiles = Get-ChildItem -Path "build" -File | Where-Object { $_.Name -like "Bloodloom_setup_v*" } | Select-Object -ExpandProperty FullName
if (-not $SetupFiles) { Write-Host "❌ Ошибка: Не найдены скомпилированные файлы в папке build!" -ForegroundColor Red; exit }

# Проверка лимита GitHub (2 ГБ) и сжатие при превышении
 $GitHubLimit = 2147483648
 $FilesToUpload = @()

# Ищем WinRAR (Rar.exe предпочтительнее для консоли)
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
Write-Host "✅ Установочники собраны: $($FilesToUpload -join ', ')" -ForegroundColor Green

# 5. Публикация на GitHub
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