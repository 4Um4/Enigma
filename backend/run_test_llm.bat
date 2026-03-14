@echo off
chcp 65001 >nul
title Enigma LLM Test
cd /d "%~dp0"
echo ========================================
echo    Running LLM Test (new structure)
echo ========================================
echo.

:: Use project venv if exists
if exist "..\.venv\Scripts\python.exe" (
    set PYTHON_CMD=..\.venv\Scripts\python.exe
) else if exist "venv\Scripts\python.exe" (
    set PYTHON_CMD=venv\Scripts\python.exe
) else (
    set PYTHON_CMD=python
)

echo Using Python: %PYTHON_CMD%
echo Running: tests\test_llm.py

%PYTHON_CMD% tests\test_llm.py

echo.
echo [INFO] Test complete
pause
