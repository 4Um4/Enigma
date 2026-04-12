@echo off
chcp 65001 >nul
title ENIGMA — Reset Campaign State

set "CAMPAIGN=demo-campaign"
set "STATE_FILE=%~dp0backend\data\campaigns\%CAMPAIGN%\campaign_state.json"
set "SESSION_FILE=%~dp0backend\data\sessions\%CAMPAIGN%.json"

echo [RESET] Сброс состояния кампании: %CAMPAIGN%

if exist "%STATE_FILE%" (
    del "%STATE_FILE%"
    echo [OK] Удалён: campaign_state.json
) else (
    echo [SKIP] campaign_state.json не найден
)

if exist "%SESSION_FILE%" (
    del "%SESSION_FILE%"
    echo [OK] Удалён: demo-campaign.json (сессия)
) else (
    echo [SKIP] session файл не найден
)

echo.
echo [DONE] NPC профили сохранены. Сцена будет пересоздана при следующем запуске.
pause