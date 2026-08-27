# Скан внешних ссылок на имена файлов из scripts\ (чистка папки)
 $ErrorActionPreference = "SilentlyContinue"
 $root = Split-Path -Parent $PSScriptRoot
Set-Location $root

"=== ИНВЕНТАРЬ scripts ===" | Tee-Object refs_report.txt
Get-ChildItem scripts -File |
    Sort-Object Name |
    Format-Table Name, @{n='KB';e={[math]::Round($_.Length/1KB,1)}}, LastWriteTime -AutoSize |
    Out-String -Width 120 | Tee-Object refs_report.txt -Append

"=== ВНЕШНИЕ ССЫЛКИ ===" | Tee-Object refs_report.txt -Append
 $names = (Get-ChildItem scripts -File).Name |
    ForEach-Object { [regex]::Escape([IO.Path]::GetFileNameWithoutExtension($_)) }
if ($names) {
    $pattern = $names -join '|'
    $targets = Get-ChildItem -Recurse -Include *.py,*.md,*.yaml,*.yml,*.json,*.toml,*.bat,*.ps1,*.cfg -File |
        Where-Object { $_.FullName -notmatch '\\(\.venv|\.git|build|scripts)(\\|$)' }
    Select-String -Path ($targets.FullName) -Pattern $pattern |
        ForEach-Object { "$($_.Path.Replace($root,''))::$($_.LineNumber)| $($_.Line.Trim())" } |
        Tee-Object refs_report.txt -Append
}
"=== ГОТОВО: отчёт в scripts\refs_report.txt ==="