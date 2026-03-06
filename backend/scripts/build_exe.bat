@echo off
setlocal
cd /d %~dp0\..

if not exist .venv (
  python -m venv .venv
)

call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install pyinstaller
pyinstaller --clean --noconfirm pyinstaller.spec

echo Build complete: backend\dist\EnigmaDM.exe
endlocal
