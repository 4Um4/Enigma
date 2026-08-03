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

# 1. Читаем и инкрементируем версию
if (Test-Path $VersionFile) {
    $Version = Get-Content $VersionFile -Raw
} else {
    $Version = "0.0.0.0"
}
 $Version = $Version.Trim().TrimStart('v').TrimStart('V')

 $parts = $Version.Split('.')
if ($parts.Length -gt 0) {
    $lastPart = [int]$parts[-1]
    $lastPart++
    $parts[-1] = $lastPart.ToString()
    $NewVersion = $parts -join '.'
} else {
    $NewVersion = "0.0.0.1"
}

Set-Content -Path $VersionFile -Value $NewVersion -NoNewline
Write-Host "Версия обновлена: v$NewVersion" -ForegroundColor Yellow

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

robocopy . $StagingDir /E /XD .venv .git build logs reports __pycache__ /XF *.pyc *.log *.spec > $null

Write-Host "✅ Исходный код скопирован во временную папку" -ForegroundColor Green

# 3. Компиляция основного установщика
Write-Host "🔨 Компиляция основного установочника..." -ForegroundColor Cyan
 $ISCCPath = "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if (-not (Test-Path $ISCCPath)) { Write-Host "❌ Ошибка: Не найден Inno Setup (ISCC.exe)." -ForegroundColor Red; exit }

& $ISCCPath /DAppVersion=$NewVersion $SetupScriptPath /Qp
if ($LASTEXITCODE -ne 0) { Write-Host "❌ Ошибка компиляции Inno Setup!" -ForegroundColor Red; exit }

# 4. Установщик моделей больше не собираем (модели будут скачиваться по ссылкам из настроек игры)
 $SetupFiles = Get-ChildItem -Path "build" -File | Where-Object { $_.Name -like "Bloodloom_setup_v*" } | Select-Object -ExpandProperty FullName
if (-not $SetupFiles) { Write-Host "❌ Ошибка: Не найдены скомпилированные файлы в папке build!" -ForegroundColor Red; exit }
Write-Host "✅ Установочники собраны: $($SetupFiles -join ', ')" -ForegroundColor Green

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

gh release create $TagName $SetupFiles `
    --repo "$RepoOwner/$RepoName" `
    --title "$ReleaseTitle" `
    --notes "$ReleaseNotes" `
    --latest

if ($LASTEXITCODE -eq 0) {
    Write-Host "🎉 Релиз $TagName успешно опубликован на GitHub!" -ForegroundColor Green
} else {
    Write-Host "❌ Ошибка публикации релиза." -ForegroundColor Red
}