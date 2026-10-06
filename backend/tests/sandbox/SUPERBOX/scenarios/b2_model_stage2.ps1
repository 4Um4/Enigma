# STAGE 2 (Candidate Validation, GO Мастера): P0-replay на замороженном корпусе.
# П1 baseline: legA=BASE-A (production OFF), legB=BASE-B (SEM_LIB=1 provenance).
# П2 кандидат (-Candidate: IQ3_M + enable_thinking=false): legA=CAND-A, legB=CAND-B.
# BASE-ноги = свежий контроль + РЕГРЕССИЯ патча харнесса (профиль обязан
# совпасть с известными штампами). Артефакты: reports/m2_*.txt.
# IPT-гейт: Skip (пре-ранговый ручной IPT — командой 1; волатильность
# параллельных сессий). RAM-гвард >=6 — в preflight.
 $ErrorActionPreference = 'Stop'
 $_zom = Get-Process llama-server -ErrorAction SilentlyContinue
if ($_zom) { Write-Output "PREFLIGHT FAIL: llama ($($_zom.Id -join ','))"; exit 10 }
 $_os = Get-CimInstance Win32_OperatingSystem
 $_ram = [math]::Round($_os.FreePhysicalMemory/1MB,2)
if ($_ram -lt 6) { Write-Output "PREFLIGHT FAIL: RAM=$_ram"; exit 11 }
 $_py = Get-Process python* -ErrorAction SilentlyContinue | Where-Object { $_.Id -ne $PID }
if ($_py) { Write-Output "PREFLIGHT FAIL: python ($($_py.Id -join ','))"; exit 12 }
 $_l0 = Get-NetTCPConnection -LocalPort 8181 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($_l0) { Write-Output "PREFLIGHT FAIL: порт (pid=$($_l0.OwningProcess))"; exit 13 }
 $_cand = 'C:\DDD\Codex\VSC_Enigma\Enigma\Models LLM\Qwen3.5-9B-The-Defiant-Fable-Uncnr-Heretic-NEO-MAX-IQ3_M.gguf'
if (-not (Test-Path $_cand)) { Write-Output "PREFLIGHT FAIL: кандидат не найден ($_cand)"; exit 14 }
Write-Output "PREFLIGHT OK: ram=$_ram GB"

 $env:ENIGMA_DET_KEEP_SERVER = '1'; $env:ENIGMA_DET_TRACE = '1'
 $harness = 'backend\tests\sandbox\SUPERBOX\scenarios\b2_det_pair.ps1'
Remove-Item Env:ENIGMA_SEM_LIB -ErrorAction SilentlyContinue
Remove-Item Env:ENIGMA_SEM_LIB_MODULES -ErrorAction SilentlyContinue
Remove-Item Env:ENIGMA_SEM_ROUTER -ErrorAction SilentlyContinue
Remove-Item Env:ENIGMA_SEM_ROUTER_ORACLE_LABELS -ErrorAction SilentlyContinue
Remove-Item Env:ENIGMA_SEM_ROUTER_ORACLE_FAMILIES -ErrorAction SilentlyContinue

# ── П1: BASELINE (Qwen2.5; default ModelPath — регрессия патча) ──
powershell -NoProfile -ExecutionPolicy Bypass -File $harness -ArtifactA reports\m2_base_a.txt -ArtifactB reports\m2_base_b.txt -LegBSet 'ENIGMA_SEM_LIB=1;ENIGMA_SEM_LIB_MODULES=dialogue_provenance' -SkipIPTGate
Write-Output "P1 BASELINE A/B exit=$LASTEXITCODE"

# ── П2: КАНДИДАТ (IQ3_M + non-thinking, switch харнесса) ──
Remove-Item Env:ENIGMA_SEM_LIB -ErrorAction SilentlyContinue
Remove-Item Env:ENIGMA_SEM_LIB_MODULES -ErrorAction SilentlyContinue
powershell -NoProfile -ExecutionPolicy Bypass -File $harness -ArtifactA reports\m2_cand_a.txt -ArtifactB reports\m2_cand_b.txt -LegBSet 'ENIGMA_SEM_LIB=1;ENIGMA_SEM_LIB_MODULES=dialogue_provenance' -Candidate -SkipIPTGate
Write-Output "P2 CANDIDATE A/B exit=$LASTEXITCODE"

Remove-Item Env:ENIGMA_DET_KEEP_SERVER -ErrorAction SilentlyContinue
Remove-Item Env:ENIGMA_DET_TRACE -ErrorAction SilentlyContinue
Write-Output 'STAGE 2 DONE'
exit 0