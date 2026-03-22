@echo off
rem start_llm.bat - Launch llama-server for Gemma-3-12B on RTX 3070 Ti
rem Called by start_enigma.bat: start "Enigma LLM" cmd /c ""%BACKEND_DIR%\start_llm.bat" "%LLM_LOG%""

rem === Paths ===
set "BACKEND_DIR=%~dp0"
if "%BACKEND_DIR:~-1%"=="\" set "BACKEND_DIR=%BACKEND_DIR:~0,-1%"
set "ROOT_DIR=%BACKEND_DIR%\.."

set "LLAMA_EXE=%ROOT_DIR%\Models LLM\llama\llama-server.exe"
set "MODEL=%ROOT_DIR%\Models LLM\gemma-3-12b-it-q4_k_m.gguf"
set "PORT=8080"

rem === VRAM tuning for RTX 3070 Ti 8GB + Gemma-3-12B Q4_K_M ===
rem
rem IMPORTANT: Flash Attention (FA) dramatically affects speed:
rem   FA enabled:  7-9 tok/s   <- WANT THIS
rem   FA disabled: 1-2 tok/s   <- BAD
rem
rem FA requires KV cache in f16 format. Using q8_0 KV disables FA.
rem So: keep KV in f16, limit GPU layers to what fits in VRAM.
rem
rem VRAM budget:
rem   Model weights (28 layers): ~4250 MB
rem   KV cache (f16, ctx=8192):  ~1952 MB
rem   Compute buffer:             ~560 MB
rem   Total:                     ~6762 MB  fits in 7091 MB free
rem
rem Result: 28 layers, FA enabled, ~7-9 tok/s

set "NGPU=28"
set "CTX=8192"
set "THREADS=9"
set "NPRED=512"

rem === Log file ===
if not "%~1"=="" (
    set "LOG_FILE=%~1"
) else (
    set "LOG_FILE=%BACKEND_DIR%\logs\llm_manual.log"
)
for %%F in ("%LOG_FILE%") do set "LOG_DIR_=%%~dpF"
if not exist "%LOG_DIR_%" mkdir "%LOG_DIR_%"

rem === Validation ===
if not exist "%LLAMA_EXE%" (
    echo [ERROR] llama-server.exe not found
    echo Path: %LLAMA_EXE%
    pause & exit /b 1
)
if not exist "%MODEL%" (
    echo [ERROR] Model not found
    echo Path: %MODEL%
    pause & exit /b 1
)

echo.
echo Gemma-3-12B-IT Q4_K_M  ^|  RTX 3070 Ti 8GB
echo GPU layers: %NGPU% (Flash Attention: enabled)
echo Context:    %CTX% tokens
echo Log:        %LOG_FILE%
echo.

"%LLAMA_EXE%" ^
    --model        "%MODEL%" ^
    --host         127.0.0.1 ^
    --port         %PORT% ^
    --n-gpu-layers %NGPU% ^
    --threads      %THREADS% ^
    --ctx-size     %CTX% ^
    --n-predict    %NPRED% ^
    --temp         0.75 ^
    --top-p        0.92 ^
    --repeat-penalty 1.10 ^
    --min-p        0.05 ^
    --no-warmup ^
    >> "%LOG_FILE%" 2>&1

echo.
echo llama-server exited: %errorlevel%
pause