# Назначение: Э2 — composable modules interference gate. 4 same-instance пары.
#   A<->I (identity single vs base) и B<->BI (provenance vs provenance+identity).
#   Hard preflight (зомби/RAM/python/порт — FAIL обрывает, exit 10-13).
#   Артефакты: reports/e2_i2a_*.txt, reports/e2_a2i_*.txt, reports/e2_b2bi_*.txt, reports/e2_bi2b_*.txt
# Запуск ИЗ КОРНЯ. Exit: 0 прогоны завершены | 10-13 preflight | пары по кодам b2_det_pair.
 $ErrorActionPreference = 'Stop'

 $_zom = Get-Process llama-server -ErrorAction SilentlyContinue
if ($_zom) { Write-Output "PREFLIGHT FAIL: llama-процесс жив ($($_zom.Id -join ','))"; exit 10 }
 $_os = Get-CimInstance Win32_OperatingSystem
 $_ram = [math]::Round($_os.FreePhysicalMemory/1MB,2)
if ($_ram -lt 6) { Write-Output "PREFLIGHT FAIL: RAM=$_ram GB < 6"; exit 11 }
 $_py = Get-Process python* -ErrorAction SilentlyContinue | Where-Object { $_.Id -ne $PID }
if ($_py) { Write-Output "PREFLIGHT FAIL: python-процессы ($($_py.Id -join ','))"; exit 12 }
 $_l0 = Get-NetTCPConnection -LocalPort 8181 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($_l0) { Write-Output "PREFLIGHT FAIL: порт 8181 занят pid=$($_l0.OwningProcess)"; exit 13 }
Write-Output "PREFLIGHT OK: ram=$_ram GB"

 $env:ENIGMA_DET_KEEP_SERVER = '1'; $env:ENIGMA_DET_TRACE = '1'

# Пара 1: I -> A (плечо A = identity single, плечо B = A)
 $env:ENIGMA_SEM_LIB = '1'; $env:ENIGMA_SEM_LIB_MODULES = 'dialogue_identity'
powershell -NoProfile -ExecutionPolicy Bypass -File backend\tests\sandbox\SUPERBOX\scenarios\b2_det_pair.ps1 -ArtifactA reports\e2_i2a_a.txt -ArtifactB reports\e2_i2a_b.txt -LegBClear 'ENIGMA_SEM_LIB;ENIGMA_SEM_LIB_MODULES'
Write-Output "pair1 I->A exit=$LASTEXITCODE"

# Пара 2: A -> I
Remove-Item Env:ENIGMA_SEM_LIB -ErrorAction SilentlyContinue; Remove-Item Env:ENIGMA_SEM_LIB_MODULES -ErrorAction SilentlyContinue
powershell -NoProfile -ExecutionPolicy Bypass -File backend\tests\sandbox\SUPERBOX\scenarios\b2_det_pair.ps1 -ArtifactA reports\e2_a2i_a.txt -ArtifactB reports\e2_a2i_b.txt -LegBSet 'ENIGMA_SEM_LIB=1;ENIGMA_SEM_LIB_MODULES=dialogue_identity'
Write-Output "pair2 A->I exit=$LASTEXITCODE"

# Пара 3: B -> BI (плечо A = provenance only, плечо B = +identity)
 $env:ENIGMA_SEM_LIB = '1'; $env:ENIGMA_SEM_LIB_MODULES = 'dialogue_provenance'
powershell -NoProfile -ExecutionPolicy Bypass -File backend\tests\sandbox\SUPERBOX\scenarios\b2_det_pair.ps1 -ArtifactA reports\e2_b2bi_a.txt -ArtifactB reports\e2_b2bi_b.txt -LegBSet 'ENIGMA_SEM_LIB_MODULES=dialogue_provenance,dialogue_identity'
Write-Output "pair3 B->BI exit=$LASTEXITCODE"

# Пара 4: BI -> B
Remove-Item Env:ENIGMA_SEM_LIB_MODULES -ErrorAction SilentlyContinue
powershell -NoProfile -ExecutionPolicy Bypass -File backend\tests\sandbox\SUPERBOX\scenarios\b2_det_pair.ps1 -ArtifactA reports\e2_bi2b_a.txt -ArtifactB reports\e2_bi2b_b.txt -LegBSet 'ENIGMA_SEM_LIB_MODULES=dialogue_provenance'
Write-Output "pair4 BI->B exit=$LASTEXITCODE"

Remove-Item Env:ENIGMA_SEM_LIB -ErrorAction SilentlyContinue; Remove-Item Env:ENIGMA_SEM_LIB_MODULES -ErrorAction SilentlyContinue
Remove-Item Env:ENIGMA_DET_KEEP_SERVER -ErrorAction SilentlyContinue; Remove-Item Env:ENIGMA_DET_TRACE -ErrorAction SilentlyContinue
Write-Output 'E2 DONE (валидность пар по exit-кодам; мёртвые не ретраятся)'
exit 0
