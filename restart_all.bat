@echo off
echo ========================================
echo  ПОЛНАЯ ПЕРЕЗАГРУЗКА ENIGMA
echo ========================================

echo.
echo [1/4] Убиваем все процессы...
taskkill /F /IM llama-server.exe 2>nul
taskkill /F /IM python.exe /FI "WINDOWTITLE eq *uvicorn*" 2>nul
taskkill /F /IM python.exe /FI "WINDOWTITLE eq *frontend*" 2>nul
timeout /t 2 >nul

echo.
echo [2/4] Чистим кэш Python...
cd /d "%~dp0backend"
del /s /q __pycache__ 2>nul
for /d /r %%d in (__pycache__) do @if exist "%%d" rd /s /q "%%d"

echo.
echo [3/4] Ждём освобождения портов...
timeout /t 3 >nul

echo.
echo [4/4] Запускаем заново...
start "ENIGMA" cmd /k "%~dp0start_enigma.bat"

echo.
echo ========================================
echo  Готово! Новое окно открыто.
echo  Закройте это окно.
echo ========================================
pause