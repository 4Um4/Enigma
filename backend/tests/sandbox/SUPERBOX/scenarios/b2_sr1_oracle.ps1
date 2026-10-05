# SR-1 Phase 1 (GO Мастера, A): ORACLE ISOLATION — 5 пар по v3-харнессу.
# П1/П2: CTRL-BI <-> ORC-FULL — решающее сравнение, оба порядка (same-instance).
# П3/П4: CTRL-B <-> ORC-B — B-профиль + non-family -> A; оба порядка.
# П5: ORC-I <-> ORC-I — identity-ось (A/A-детерминизм руки).
# Обязательное условие Мастера: пустой срез = ноль модулей = байт-A
# (замки test_semlib_router; [SLICE]/sys_md5 в артефактах; runtime-проверка —
# анализатором p0_phase1_metrics).
# IPT-гейт: SkipIPTGate во всех парах. Пре-ранговый ручной IPT зафиксирован
# ЗЕЛЁНЫМ (51/51); Skip — защита от волатильности параллельных сессий
# (чужой красный в середине окна = exit 4 = потеря 40-60 мин).
# Exit: 0 DONE | 10-14 preflight | 2/3/5 от харнесса (4 исключён Skip-ом)
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
Write-Output "PREFLIGHT OK: ram=$_ram GB"

 $env:ENIGMA_DET_KEEP_SERVER = '1'; $env:ENIGMA_DET_TRACE = '1'
 $harness = 'backend\tests\sandbox\SUPERBOX\scenarios\b2_det_pair.ps1'

# ── П1: CTRL-BI -> ORC-FULL (решающее) ──
Remove-Item Env:ENIGMA_SEM_ROUTER -ErrorAction SilentlyContinue
Remove-Item Env:ENIGMA_SEM_ROUTER_ORACLE_LABELS -ErrorAction SilentlyContinue
Remove-Item Env:ENIGMA_SEM_ROUTER_ORACLE_FAMILIES -ErrorAction SilentlyContinue
 $env:ENIGMA_SEM_LIB = '1'; $env:ENIGMA_SEM_LIB_MODULES = 'dialogue_provenance,dialogue_identity'
powershell -NoProfile -ExecutionPolicy Bypass -File $harness -ArtifactA reports\sr1_p1_bi_a.txt -ArtifactB reports\sr1_p1_orcfull_b.txt -LegBClear 'ENIGMA_SEM_LIB_MODULES' -LegBSet "ENIGMA_SEM_ROUTER=oracle;ENIGMA_SEM_ROUTER_ORACLE_LABELS=$labels;ENIGMA_SEM_ROUTER_ORACLE_FAMILIES=PROV,ID" -SkipIPTGate
Write-Output "P1 BI->ORC-FULL exit=$LASTEXITCODE"

# ── П2: ORC-FULL -> CTRL-BI (контрбаланс решающего) ──
 $env:ENIGMA_SEM_ROUTER = 'oracle'; $env:ENIGMA_SEM_ROUTER_ORACLE_LABELS = $labels; $env:ENIGMA_SEM_ROUTER_ORACLE_FAMILIES = 'PROV,ID'
Remove-Item Env:ENIGMA_SEM_LIB_MODULES -ErrorAction SilentlyContinue
powershell -NoProfile -ExecutionPolicy Bypass -File $harness -ArtifactA reports\sr1_p2_orcfull_a.txt -ArtifactB reports\sr1_p2_bi_b.txt -LegBSet 'ENIGMA_SEM_LIB_MODULES=dialogue_provenance,dialogue_identity' -LegBClear 'ENIGMA_SEM_ROUTER;ENIGMA_SEM_ROUTER_ORACLE_LABELS;ENIGMA_SEM_ROUTER_ORACLE_FAMILIES' -SkipIPTGate
Write-Output "P2 ORC-FULL->BI exit=$LASTEXITCODE"

# ── П3: CTRL-B -> ORC-B ──
Remove-Item Env:ENIGMA_SEM_ROUTER -ErrorAction SilentlyContinue
Remove-Item Env:ENIGMA_SEM_ROUTER_ORACLE_LABELS -ErrorAction SilentlyContinue
Remove-Item Env:ENIGMA_SEM_ROUTER_ORACLE_FAMILIES -ErrorAction SilentlyContinue
 $env:ENIGMA_SEM_LIB = '1'; $env:ENIGMA_SEM_LIB_MODULES = 'dialogue_provenance'
powershell -NoProfile -ExecutionPolicy Bypass -File $harness -ArtifactA reports\sr1_p3_b_a.txt -ArtifactB reports\sr1_p3_orcb_b.txt -LegBClear 'ENIGMA_SEM_LIB_MODULES' -LegBSet "ENIGMA_SEM_ROUTER=oracle;ENIGMA_SEM_ROUTER_ORACLE_LABELS=$labels;ENIGMA_SEM_ROUTER_ORACLE_FAMILIES=PROV" -SkipIPTGate
Write-Output "P3 B->ORC-B exit=$LASTEXITCODE"

# ── П4: ORC-B -> CTRL-B (контрбаланс) ──
 $env:ENIGMA_SEM_ROUTER = 'oracle'; $env:ENIGMA_SEM_ROUTER_ORACLE_LABELS = $labels; $env:ENIGMA_SEM_ROUTER_ORACLE_FAMILIES = 'PROV'
Remove-Item Env:ENIGMA_SEM_LIB_MODULES -ErrorAction SilentlyContinue
powershell -NoProfile -ExecutionPolicy Bypass -File $harness -ArtifactA reports\sr1_p4_orcb_a.txt -ArtifactB reports\sr1_p4_b_b.txt -LegBSet 'ENIGMA_SEM_LIB_MODULES=dialogue_provenance' -LegBClear 'ENIGMA_SEM_ROUTER;ENIGMA_SEM_ROUTER_ORACLE_LABELS;ENIGMA_SEM_ROUTER_ORACLE_FAMILIES' -SkipIPTGate
Write-Output "P4 ORC-B->B exit=$LASTEXITCODE"

# ── П5: ORC-I -> ORC-I (A/A; identity-ось) ──
 $env:ENIGMA_SEM_ROUTER = 'oracle'; $env:ENIGMA_SEM_ROUTER_ORACLE_LABELS = $labels; $env:ENIGMA_SEM_ROUTER_ORACLE_FAMILIES = 'ID'
Remove-Item Env:ENIGMA_SEM_LIB_MODULES -ErrorAction SilentlyContinue
powershell -NoProfile -ExecutionPolicy Bypass -File $harness -ArtifactA reports\sr1_p5_orci_a.txt -ArtifactB reports\sr1_p5_orci_b.txt -SkipIPTGate
Write-Output "P5 ORC-I A/A exit=$LASTEXITCODE"

Remove-Item Env:ENIGMA_DET_KEEP_SERVER -ErrorAction SilentlyContinue
Remove-Item Env:ENIGMA_DET_TRACE -ErrorAction SilentlyContinue
Remove-Item Env:ENIGMA_SEM_LIB -ErrorAction SilentlyContinue
Remove-Item Env:ENIGMA_SEM_ROUTER -ErrorAction SilentlyContinue
Remove-Item Env:ENIGMA_SEM_ROUTER_ORACLE_LABELS -ErrorAction SilentlyContinue
Remove-Item Env:ENIGMA_SEM_ROUTER_ORACLE_FAMILIES -ErrorAction SilentlyContinue
Remove-Item Env:ENIGMA_SEM_LIB_MODULES -ErrorAction SilentlyContinue
Write-Output 'SR-1 PHASE 1 DONE'
exit 0