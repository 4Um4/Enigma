# prepare_python.ps1
# Скачивает портативный Python и устанавливает зависимости игры

 $PythonVersion = "3.12.3"
 $PythonZip = "python-$PythonVersion-embed-amd64.zip"
 $PythonUrl = "https://www.python.org/ftp/python/$PythonVersion/$PythonZip"
 $PayloadDir = "payload"
 $PythonDir = "$PayloadDir\python"

Write-Host "🐍 Подготовка портативного Python $PythonVersion..." -ForegroundColor Cyan

# 1. Создаем папку payload
if (-not (Test-Path $PayloadDir)) {
    New-Item -ItemType Directory -Path $PayloadDir | Out-Null
}

# 2. Скачиваем Embeddable Python
if (-not (Test-Path $PythonZip)) {
    Write-Host "Скачивание $PythonZip..." -ForegroundColor Yellow
    Invoke-WebRequest -Uri $PythonUrl -OutFile $PythonZip
}

# 3. Распаковываем
if (Test-Path $PythonDir) { Remove-Item -Recurse -Force $PythonDir }
Expand-Archive -Path $PythonZip -DestinationPath $PythonDir -Force

# 4. Разблокируем import site (нужно для pip)
 $PthFile = Get-ChildItem -Path $PythonDir -Filter "python*._pth"
if ($PthFile) {
    $content = Get-Content $PthFile.FullName
    $content = $content -replace '#import site', 'import site'
    Set-Content -Path $PthFile.FullName -Value $content
    Write-Host "✅ Файл ._pth настроен" -ForegroundColor Green
}

# 5. Скачиваем get-pip.py
 $GetPipPath = "$PythonDir\get-pip.py"
if (-not (Test-Path $GetPipPath)) {
    Write-Host "Скачивание get-pip.py..." -ForegroundColor Yellow
    Invoke-WebRequest -Uri "https://bootstrap.pypa.io/get-pip.py" -OutFile $GetPipPath
}

# 6. Устанавливаем pip
Write-Host "Установка pip..." -ForegroundColor Yellow
& "$PythonDir\python.exe" "$GetPipPath" --no-warn-script-location

# 7. Устанавливаем зависимости игры
if (Test-Path "backend\requirements.txt") {
    Write-Host "📦 Установка зависимостей из backend\requirements.txt (это может занять время)..." -ForegroundColor Yellow
    & "$PythonDir\python.exe" -m pip install -r backend\requirements.txt --no-warn-script-location
} else {
    Write-Host "⚠️ Файл backend\requirements.txt не найден!" -ForegroundColor Red
}

# 8. Устанавливаем AppAgent зависимости (если есть)
if (Test-Path "backend\AppAgent\requirements.txt") {
    Write-Host "📦 Установка зависимостей из AppAgent..." -ForegroundColor Yellow
    & "$PythonDir\python.exe" -m pip install -r backend\AppAgent\requirements.txt --no-warn-script-location
}

# 9. Удаляем временные файлы
Remove-Item -Path $PythonZip -Force
Remove-Item -Path $GetPipPath -Force
Remove-Item -Path "$PythonDir\Logs" -Recurse -Force -ErrorAction SilentlyContinue

Write-Host "🎉 Портативный Python готов в папке: $PythonDir" -ForegroundColor Green