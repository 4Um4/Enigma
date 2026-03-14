@echo off
REM Enigma Backend Full Tests - Fixed Imports + Editable Install
echo === Enigma Backend Tests - Fixed Imports ===
echo.

REM Activate venv (relative to Enigma root)
pushd "%~dp0.."
call .venv\Scripts\activate.bat
if %ERRORLEVEL% neq 0 (
    echo .venv not found. Create: python -m venv .venv ^&^& .venv\Scripts\activate ^&^& pip install -r requirements.txt
    pause
    exit /b 1
)

REM Editable install
echo [Install] pip install -e .
pip install -e .

echo [Smoke Test] pytest tests/test_package.py -v
pytest tests/test_package.py -v

echo [Startup Checks] pytest tests/test_startup_checks.py -v
pytest tests/test_startup_checks.py -v

echo [Full Suite] pytest tests/ -v --tb=short
pytest tests/ -v --tb=short

echo [Check logs] dir data\logs\*.jsonl
echo === Tests complete! No more NameError/ModuleNotFoundError ===
echo Run uvicorn app.main:app --reload to test API.
pause

