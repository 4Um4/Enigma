Get-ChildItem -Path "backend/" -Filter "__pycache__" -Recurse -Directory |
Remove-Item -Recurse -Force

Get-ChildItem -Path "frontend/" -Filter "__pycache__" -Recurse -Directory |
Remove-Item -Recurse -Force

python -m compileall backend
python -m compileall frontend

Write-Host "CACHE CLEANED"