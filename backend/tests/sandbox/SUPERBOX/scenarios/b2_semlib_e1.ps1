# path: /project/backend/tests/sandbox/SUPERBOX/scenarios/b2_semlib_e1.ps1
# Назначение: Э1 semantic library — same-instance контрбаланс LIB<->A (2 пары).
#   Preflight с исполнительной силой (урок r2: FAIL обязан обрывать, не печатать).
# Запуск ИЗ КОРНЯ: powershell -NoProfile -ExecutionPolicy Bypass -File backend\tests\sandbox\SUPERBOX\scenarios\b2_semlib_e1.ps1
# Exit: 0 прогоны завершены (валидность пар по кодам b2_det_pair) | 10 зомби | 11 RAM | 12 python | 13 порт
 $ErrorActionPreference = 'Stop'

 $_zom = Get-Process llama-server -ErrorAction SilentlyContinue
if ($_zom) { Write-Output "PREFLIGHT FAIL: llama-процесс жив (pid=$($_zom.Id -join ','))"; exit 10 }
 $_os = Get-CimInstance Win32_OperatingSystem
 $_ram = [math]::Round($_os.FreePhysicalMemory/1MB,2)
if ($_ram -lt 6) { Write-Output "PREFLIGHT FAIL: RAM=$_ram GB < 6"; exit 11 }
 $_py = Get-Process python* -ErrorAction SilentlyContinue | Where-Object { $_.Id -ne $PID }
if ($_py) { Write-Output "PREFLIGHT FAIL: python-процессы ($($_py.Id -join ','))"; exit 12 }
 $_l0 = Get-NetTCPConnection -LocalPort 8181 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($_l0) { Write-Output "PREFLIGHT FAIL: порт 8181 занят pid=$($_l0.OwningProcess)"; exit 13 }
Write-Output "PREFLIGHT OK: ram=$_ram GB, порт свободен, процессов чисто"

# Пара 1: LIB -> A (плечо A наследует SEM_LIB=1, плечо B очищено -> состояние A)
 $env:ENIGMA_DET_KEEP_SERVER = '1'; $env:ENIGMA_DET_TRACE = '1'
 $env:ENIGMA_SEM_LIB = '1'
powershell -NoProfile -ExecutionPolicy Bypass -File backend\tests\sandbox\SUPERBOX\scenarios\b2_det_pair.ps1 -ArtifactA reports\e1_lib2a_a.txt -ArtifactB reports\e1_lib2a_b.txt -LegBClear 'ENIGMA_SEM_LIB'
 $p1 = $LASTEXITCODE
Write-Output "pair1 LIB->A exit=$p1"

# Пара 2: A -> LIB (плечо A без флага, плечо B SEM_LIB=1)
Remove-Item Env:ENIGMA_SEM_LIB -ErrorAction SilentlyContinue
powershell -NoProfile -ExecutionPolicy Bypass -File backend\tests\sandbox\SUPERBOX\scenarios\b2_det_pair.ps1 -ArtifactA reports\e1_a2lib_a.txt -ArtifactB reports\e1_a2lib_b.txt -LegBSet 'ENIGMA_SEM_LIB=1'
 $p2 = $LASTEXITCODE
Write-Output "pair2 A->LIB exit=$p2"

Remove-Item Env:ENIGMA_SEM_LIB -ErrorAction SilentlyContinue
Remove-Item Env:ENIGMA_DET_KEEP_SERVER -ErrorAction SilentlyContinue
Remove-Item Env:ENIGMA_DET_TRACE -ErrorAction SilentlyContinue
Write-Output "E1 DONE: pair1=$p1 pair2=$p2 (0 = пара валидна; мёртвые пары не ретраятся)"
exit 0
