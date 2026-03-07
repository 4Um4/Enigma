@echo off
REM One-click launcher for Local AI DM terminal mode (Windows)

if "%LLAMA_CPP_EXECUTABLE%"=="" (
  echo [WARN] LLAMA_CPP_EXECUTABLE is not set.
)
if "%LLAMA_CPP_MODEL%"=="" (
  echo [WARN] LLAMA_CPP_MODEL is not set.
)

python run_terminal_dm.py
