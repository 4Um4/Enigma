@echo off
chcp 65001 >nul

set "LLAMA=C:\DDD\Codex\VSC_Enigma\Enigma\Models LLM\llama\llama-server.exe"
set "MODEL=C:\DDD\Codex\VSC_Enigma\Enigma\Models LLM\gemma-3-12b-it-q4_k_m.gguf"

echo.
echo === ENIGMA Gemma-3-12B Test ===
echo.

if not exist "%LLAMA%" (
    echo ERROR: llama-server.exe not found
    echo Path: %LLAMA%
    pause
    exit /b 1
)
echo OK: llama-server.exe found

if not exist "%MODEL%" (
    echo ERROR: Model file not found
    echo Path: %MODEL%
    pause
    exit /b 1
)
echo OK: gemma-3-12b-it-q4_k_m.gguf found

echo.
echo Starting Gemma-3-12B... wait 60-120 sec
echo.

"%LLAMA%" --model "%MODEL%" --host 127.0.0.1 --port 8080 --n-gpu-layers 4 --threads 6 --ctx-size 2048 --n-predict 512 --temp 0.7 --log-disable

echo.
echo Exit code: %errorlevel%
pause