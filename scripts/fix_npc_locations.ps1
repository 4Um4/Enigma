# Скрипт для обновления location_id в профилях NPC
 $targetDir = "config/npc/individuals"

if (-not (Test-Path $targetDir)) {
    Write-Host "❌ Директория не найдена: $targetDir" -ForegroundColor Red
    exit
}

 $files = Get-ChildItem -Path $targetDir -Filter "*.json"

foreach ($file in $files) {
    $content = Get-Content $file.FullName -Raw
    if ($content -match "tavern_silver_wolf") {
        # Заменяем tavern_silver_wolf на tavern
        $newContent = $content -replace "tavern_silver_wolf", "tavern"
        Set-Content -Path $file.FullName -Value $newContent -Encoding UTF8 -NoNewline
        Write-Host "[OK] Обновлён: $($file.Name)" -ForegroundColor Green
    } else {
        Write-Host "[SKIP] Пропущен (нет совпадений): $($file.Name)" -ForegroundColor Yellow
    }
}

Write-Host "`n✅ Замены завершены. Можно запускать тест." -ForegroundColor Cyan