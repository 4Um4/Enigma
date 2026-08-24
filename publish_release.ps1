# publish_release.ps1
# Скрипт автоматической сборки и публикации релиза Bloodloom

# --- КОНФИГУРАЦИЯ ---
 $RepoOwner = "4Um4"
 $RepoName = "Enigma"
 $SetupScriptPath = "enigma_setup.iss"
 $VersionFile = "version.txt"

Write-Host "🚀 Начинаем сборку и публикацию релиза Bloodloom..." -ForegroundColor Cyan

# 0. Очистка папки build (оставляем только установщик моделей)
Write-Host "🧹 Очистка папки build..." -ForegroundColor Cyan
if (Test-Path "build") {
    Get-ChildItem -Path "build" -File | Remove-Item -Force
    Get-ChildItem -Path "build" -Directory | Remove-Item -Recurse -Force
} else {
    New-Item -ItemType Directory -Path "build" | Out-Null
}

# 1. S210: версия. SSOT = frontend/constants.py (PROJECT_VERSION): первые
# три сегмента. version.txt — ТОЛЬКО счётчик билдов (4-й сегмент); при смене
# базы SSOT счётчик сбрасывается в 1. Фикс дрейфа «v0.5.3.7.15» при проекте 0.5.3.8.x.
 $consts = Get-Content "frontend\constants.py" -Raw
if ($consts -notmatch 'PROJECT_VERSION:\s*str\s*=\s*"v?(\d+)\.(\d+)\.(\d+)') {
    Write-Host "❌ SSOT версии не найден в frontend\constants.py (PROJECT_VERSION)!" -ForegroundColor Red; exit
}
 $ssotBase = "$($Matches[1]).$($Matches[2]).$($Matches[3])"

 $buildNum = 0
if (Test-Path $VersionFile) {
    $prev = (Get-Content $VersionFile -Raw).Trim().TrimStart('v').TrimStart('V')
    $prevParts = $prev.Split('.')
    if ($prevParts.Length -ge 4 -and (($prevParts[0..2] -join '.') -eq $ssotBase)) {
        $buildNum = [int]$prevParts[3]
    }
}
 $buildNum++
 $NewVersion = "$ssotBase.$buildNum"

Set-Content -Path $VersionFile -Value $NewVersion -NoNewline
Write-Host "Версия обновлена: v$NewVersion (SSOT: $ssotBase, билд: $buildNum)" -ForegroundColor Yellow

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

# /XD "Models LLM": модели (24 ГБ) в staging не нужны — enigma_setup.iss берёт
# llama-бинарники из корня, а модели доставляются внутриигровым загрузчиком.
robocopy . $StagingDir /E /XD .venv .git build logs reports __pycache__ "Models LLM" /XF *.pyc *.log *.spec > $null

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