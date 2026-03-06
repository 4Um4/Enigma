$ErrorActionPreference = 'Stop'

Set-Location (Join-Path $PSScriptRoot '..')

if (-not (Test-Path '.venv')) {
  python -m venv .venv
}

. .\.venv\Scripts\Activate.ps1

python -m pip install --upgrade pip
pip install -r requirements.txt
pip install pyinstaller

pyinstaller --clean --noconfirm pyinstaller.spec

Write-Host "Build complete: backend\dist\EnigmaDM.exe"
