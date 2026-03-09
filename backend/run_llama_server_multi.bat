@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

title Enigma LLaMA Server - Multi Model

echo ========================================
echo    Enigma LLaMA Server - Multi Model
echo ========================================
echo.

:: Auto unblock files
powershell -Command "Get-ChildItem 'C:\DDD\Codex\VSC_Enigma\Enigma\Models LLM\llama' -Recurse | Unblock-File -ErrorAction SilentlyContinue"

echo Available models:
echo.
echo   [1] Qwen2.5-7B   (DM, Default) - ~4GB VRAM
echo   [2] Qwen3.5-9B   (World Sim)   - ~5.5GB VRAM
echo   [3] Saiga-7B     (Rules,Memory)- ~4GB VRAM
echo   [4] YandexGPT-8B  (NPC Dialogs) - ~5GB VRAM
echo.
echo   [Q] Quit
echo.

set /p choice="Select model (1-4): "

set MODEL_PATH=
set MODEL_NAME=
set GPU_LAYERS=33

if "%choice%"=="1" (
    set "MODEL_PATH=C:\DDD\Codex\VSC_Enigma\Enigma\Models LLM\qwen2.5-7b-instruct-q4_k_m.gguf"
    set "MODEL_NAME=Qwen2.5-7B"
    set GPU_LAYERS=33
) else if "%choice%"=="2" (
    set "MODEL_PATH=C:\DDD\Codex\VSC_Enigma\Enigma\Models LLM\Qwen3.5-9B.gguf"
    set "MODEL_NAME=Qwen3.5-9B"
    set GPU_LAYERS=35
) else if "%choice%"=="3" (
    set "MODEL_PATH=C:\DDD\Codex\VSC_Enigma\Enigma\Models LLM\saiga_mistral_7b_model-q4_K.gguf"
    set "MODEL_NAME=Saiga-Mistral-7B"
    set GPU_LAYERS=33
) else if "%choice%"=="4" (
    set "MODEL_PATH=C:\DDD\Codex\VSC_Enigma\Enigma\Models LLM\YandexGPT-5-Lite-8B-instruct-Q4_K_M.gguf"
    set "MODEL_NAME=YandexGPT-8B-Lite"
    set GPU_LAYERS=35
) else if "%choice%"=="Q" (
    exit
) else (
    echo Invalid choice, using default Qwen2.5-7B
    set "MODEL_PATH=C:\DDD\Codex\VSC_Enigma\Enigma\Models LLM\qwen2.5-7b-instruct-q4_k_m.gguf"
    set "MODEL_NAME=Qwen2.5-7B"
    set GPU_LAYERS=33
)

echo.
echo Starting LLaMA Server...
echo   Model: %MODEL_NAME%
echo   Path:  %MODEL_PATH%
echo   GPU Layers: %GPU_LAYERS%
echo   Context: 4096
echo   Port: 8080
echo.

"C:\DDD\Codex\VSC_Enigma\Enigma\Models LLM\llama\llama-server.exe" ^
    -ngl %GPU_LAYERS% ^
    -m "%MODEL_PATH%" ^
    -c 4096 ^
    --port 8080 ^
    --host 127.0.0.1 ^
    --threads 8 ^
    --temp 0.7 ^
    --top-p 0.9 ^
    --repeat-penalty 1.1

pause

