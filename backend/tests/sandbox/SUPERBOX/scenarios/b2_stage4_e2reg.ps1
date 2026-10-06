# STAGE 4 (Candidate Validation, GO Мастера): E2-REGRESSION на IQ3_M.
# Вопрос: воспроизводится ли интерференция модулей (Э2/SR-1) на кандидате?
# П1: CAND-BI -> CAND-ORC-FULL (решающее, same-instance); П2: контрбаланс.
# Референс: m2_cand_b / m2_cand_a (CAND-B/A, та же сессия). ∅-условие:
# замки router + [SLICE]/sys_md5 (byte_ok). Главный канал: prov-акты.
# Exit: 0 | 10-15 preflight | 2/3/5 harness
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
 $labels = "$PWD\reports\p0_oracle_labels.json"
if (-not (Test-Path $labels)) { Write-Output "PREFLIGHT FAIL: labels нет ($labels)"; exit 14 }
 $_cand = 'C:\DDD\Codex\VSC_Enigma\Enigma\Models LLM\Qwen3.5-9B-The-Defiant-Fable-Uncnr-Heretic-NEO-MAX-IQ3_M.gguf'
if (-not (Test-Path $_cand)) { Write-Output "PREFLIGHT FAIL: кандидат не найден"; exit 15 }
Write-Output "PREFLIGHT OK: ram=$_ram GB"

 $env:ENIGMA_DET_KEEP_SERVER = '1'; $env:ENIGMA_DET_TRACE = '1'
 $harness = 'backend\tests\sandbox\SUPERBOX\scenarios\b2_det_pair.ps1'

# ── П1: CAND-BI -> CAND-ORC-FULL ──
Remove-Item Env:ENIGMA_SEM_ROUTER -ErrorAction SilentlyContinue
Remove-Item Env:ENIGMA_SEM_ROUTER_ORACLE_LABELS -ErrorAction SilentlyContinue
Remove-Item Env:ENIGMA_SEM_ROUTER_ORACLE_FAMILIES -ErrorAction SilentlyContinue
 $env:ENIGMA_SEM_LIB = '1'; $env:ENIGMA_SEM_LIB_MODULES = 'dialogue_provenance,dialogue_identity'
powershell -NoProfile -ExecutionPolicy Bypass -File $harness -ArtifactA reports\m4_bi_a.txt -ArtifactB reports\m4_orc_b.txt -LegBClear 'ENIGMA_SEM_LIB_MODULES' -LegBSet "ENIGMA_SEM_ROUTER=oracle;ENIGMA_SEM_ROUTER_ORACLE_LABELS=$labels;ENIGMA_SEM_ROUTER_ORACLE_FAMILIES=PROV,ID" -Candidate -SkipIPTGate
Write-Output "P1 CAND-BI->ORC exit=$LASTEXITCODE"

# ── П2: CAND-ORC-FULL -> CAND-BI (контрбаланс) ──
 $env:ENIGMA_SEM_LIB = '1'
 $env:ENIGMA_SEM_ROUTER = 'oracle'; $env:ENIGMA_SEM_ROUTER_ORACLE_LABELS = $labels; $env:ENIGMA_SEM_ROUTER_ORACLE_FAMILIES = 'PROV,ID'
Remove-Item Env:ENIGMA_SEM_LIB_MODULES -ErrorAction SilentlyContinue
powershell -NoProfile -ExecutionPolicy Bypass -File $harness -ArtifactA reports\m4_orc_a.txt -ArtifactB reports\m4_bi_b.txt -LegBSet 'ENIGMA_SEM_LIB_MODULES=dialogue_provenance,dialogue_identity' -LegBClear 'ENIGMA_SEM_ROUTER;ENIGMA_SEM_ROUTER_ORACLE_LABELS;ENIGMA_SEM_ROUTER_ORACLE_FAMILIES' -Candidate -SkipIPTGate
Write-Output "P2 ORC->CAND-BI exit=$LASTEXITCODE"

Remove-Item Env:ENIGMA_DET_KEEP_SERVER -ErrorAction SilentlyContinue
Remove-Item Env:ENIGMA_DET_TRACE -ErrorAction SilentlyContinue
Remove-Item Env:ENIGMA_SEM_LIB -ErrorAction SilentlyContinue
Remove-Item Env:ENIGMA_SEM_ROUTER -ErrorAction SilentlyContinue
Remove-Item Env:ENIGMA_SEM_ROUTER_ORACLE_LABELS -ErrorAction SilentlyContinue
Remove-Item Env:ENIGMA_SEM_ROUTER_ORACLE_FAMILIES -ErrorAction SilentlyContinue
Remove-Item Env:ENIGMA_SEM_LIB_MODULES -ErrorAction SilentlyContinue
Write-Output 'STAGE 4 DONE'
exit 0