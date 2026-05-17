# start_dev.ps1 - Multimodel LLM support
$ErrorActionPreference = "Continue"

# Load configuration
$configPath = Join-Path $PSScriptRoot "config.json"
if (-not (Test-Path $configPath)) {
    Write-Host "ERROR: config.json not found at $configPath" -ForegroundColor Red
    pause
    exit 1
}

$config = Get-Content $configPath | ConvertFrom-Json

$Root = $config.project.root
$ServerExe = $config.model.server_exe
$Model = $config.model.path
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$Url = "http://127.0.0.1:8080"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Enigma - Multimodel AI Dungeon Master" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Root: $Root" -ForegroundColor Gray

# Show available models
Write-Host ""
Write-Host "Available Models:" -ForegroundColor Yellow
Write-Host "  1) Qwen2.5-7B  (DM Agent - основной)" -ForegroundColor White
Write-Host "  2) Qwen3.5-9B  (World Agent - большой)" -ForegroundColor White
Write-Host "  3) Saiga-7B    (Rules/Memory - быстрый)" -ForegroundColor White
Write-Host "  4) YandexGPT-8B (NPC Agent - диалоги)" -ForegroundColor White
Write-Host ""

# Model selection
$modelOption = Read-Host "Select model [1-4] or press Enter for default (Qwen2.5-7B)"
$modelPath = switch ($modelOption) {
    "1" { "$Root\Models LLM\qwen2.5-7b-instruct-q4_k_m.gguf" }
    "2" { "$Root\Models LLM\Qwen3.5-9B.gguf" }
    "3" { "$Root\Models LLM\saiga_mistral_7b_model-q4_K.gguf" }
    "4" { "$Root\Models LLM\YandexGPT-5-Lite-8B-instruct-Q4_K_M.gguf" }
    default { "$Root\Models LLM\qwen2.5-7b-instruct-q4_k_m.gguf" }
}

$modelName = (Split-Path $modelPath -Leaf)
Write-Host "Selected: $modelName" -ForegroundColor Green
Write-Host ""

# Check files
@($ServerExe, $modelPath, $Python) | ForEach-Object {
    if (-not (Test-Path $_)) {
        Write-Host "ERROR: Not found: $_" -ForegroundColor Red
        pause
        exit 1
    }
}
Write-Host "Files OK" -ForegroundColor Green

# Auto-unblock files
Write-Host "Auto-unblocking files..."
Get-ChildItem (Split-Path $ServerExe -Parent) -Recurse | Unblock-File -ErrorAction SilentlyContinue
Write-Host "Done" -ForegroundColor Green

# Kill old processes
Write-Host "Killing old llama-server..."
Get-Process -Name "llama-server" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 1

# Start llama-server
Write-Host "Starting llama-server with GPU offload (-ngl $($config.server.gpu_layers))..."
$psCmd = "& '$ServerExe' -ngl $($config.server.gpu_layers) -m '$modelPath' -c $($config.server.context_size) --port 8080 --host 127.0.0.1 --threads $($config.server.threads) -b $($config.server.batch_size) --no-warmup"
$server = Start-Process -FilePath "powershell.exe" -ArgumentList "-Command", $psCmd -PassThru -NoNewWindow

# Wait for server
Write-Host "Waiting for server..."
$ready = $false
for ($i = 0; $i -lt 30; $i++) {
    try {
        $r = Invoke-WebRequest -Uri "$Url/" -TimeoutSec 2 -UseBasicParsing
        if ($r.StatusCode -ge 200) { $ready = $true; break }
    } catch {}
    Start-Sleep -Seconds 2
    Write-Host "   ... $($i*2)s" -NoNewline
}
Write-Host ""
if ($ready) {
    Write-Host "Server ready!" -ForegroundColor Green
} else {
    Write-Host "Warning: Server may still be loading..." -ForegroundColor Yellow
}

# Set environment variables
$env:LLAMA_CPP_SERVER_URL = $Url
$env:LLAMA_CPP_EXECUTABLE = $config.model.client_exe
$env:LLAMA_CPP_MODEL = $modelPath

# Start DM Terminal
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Starting DM Terminal..." -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Commands:" -ForegroundColor Yellow
Write-Host "  /model <1-4>  - переключить модель" -ForegroundColor White
Write-Host "  /ingest       - импортировать PDF" -ForegroundColor White
Write-Host "  /state        - состояние памяти" -ForegroundColor White
Write-Host "  /campaign     - состояние кампании" -ForegroundColor White
Write-Host "  /exit         - выход" -ForegroundColor White
Write-Host ""

& $Python "$Root\backend\run_terminal_dm.py"

# Cleanup
Write-Host ""
Write-Host "Shutting down server..."
if ($server -and -not $server.HasExited) {
    Stop-Process -Id $server.Id -Force -ErrorAction SilentlyContinue
}
Write-Host "Done."
pause

