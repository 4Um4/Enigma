# Exit: 0 прогоны завершены | 10-13 preflight (пары не начинались)
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
Write-Output "PREFLIGHT OK: ram=$_ram GB"

 $env:ENIGMA_DET_KEEP_SERVER = '1'; $env:ENIGMA_DET_TRACE = '1'  # плечи ожидают живой сервер (KEEP не убьёт)
 $env:ENIGMA_SEM_LIB = '1'; $env:ENIGMA_SEM_LIB_MODULES = 'dialogue_identity'
powershell -NoProfile -ExecutionPolicy Bypass -File backend\tests\sandbox\SUPERBOX\scenarios\b2_det_pair.ps1 -ArtifactA reports\e2r_i2a_a.txt -ArtifactB reports\e2r_i2a_b.txt -LegBClear 'ENIGMA_SEM_LIB;ENIGMA_SEM_LIB_MODULES'
Write-Output "pair1 I->A exit=$LASTEXITCODE (включает IPT-гейт)"
Remove-Item Env:ENIGMA_SEM_LIB -ErrorAction SilentlyContinue; # ФИКС pair4-бага (первый заход Э2 мерил B->B под именем BI->B): плечо A
# обязан быть BI = SEM_LIB=1 + полный CSV. LegBSet ниже перезапишет CSV плеча B.
 $env:ENIGMA_SEM_LIB_MODULES = 'dialogue_provenance,dialogue_identity'
powershell -NoProfile -ExecutionPolicy Bypass -File backend\tests\sandbox\SUPERBOX\scenarios\b2_det_pair.ps1 -ArtifactA reports\e2r_a2i_a.txt -ArtifactB reports\e2r_a2i_b.txt -LegBSet 'ENIGMA_SEM_LIB=1;ENIGMA_SEM_LIB_MODULES=dialogue_identity' -SkipIPTGate
Write-Output "pair2 A->I exit=$LASTEXITCODE"
 $env:ENIGMA_SEM_LIB = '1'; $env:ENIGMA_SEM_LIB_MODULES = 'dialogue_provenance'
powershell -NoProfile -ExecutionPolicy Bypass -File backend\tests\sandbox\SUPERBOX\scenarios\b2_det_pair.ps1 -ArtifactA reports\e2r_b2bi_a.txt -ArtifactB reports\e2r_b2bi_b.txt -LegBSet 'ENIGMA_SEM_LIB_MODULES=dialogue_provenance,dialogue_identity' -SkipIPTGate
Write-Output "pair3 B->BI exit=$LASTEXITCODE"
# ФИКС pair4-бага (первый заход Э2 мерил B->B под именем BI->B): плечо A
# обязан быть BI = SEM_LIB=1 + полный CSV. LegBSet ниже перезапишет CSV плеча B.
 $env:ENIGMA_SEM_LIB_MODULES = 'dialogue_provenance,dialogue_identity'
powershell -NoProfile -ExecutionPolicy Bypass -File backend\tests\sandbox\SUPERBOX\scenarios\b2_det_pair.ps1 -ArtifactA reports\e2r_bi2b_a.txt -ArtifactB reports\e2r_bi2b_b.txt -LegBSet 'ENIGMA_SEM_LIB_MODULES=dialogue_provenance' -SkipIPTGate
Write-Output "pair4 BI->B exit=$LASTEXITCODE"
Remove-Item Env:ENIGMA_SEM_LIB -ErrorAction SilentlyContinue; # ФИКС pair4-бага (первый заход Э2 мерил B->B под именем BI->B): плечо A
# обязан быть BI = SEM_LIB=1 + полный CSV. LegBSet ниже перезапишет CSV плеча B.
 $env:ENIGMA_SEM_LIB_MODULES = 'dialogue_provenance,dialogue_identity'
Remove-Item Env:ENIGMA_DET_KEEP_SERVER -ErrorAction SilentlyContinue; Remove-Item Env:ENIGMA_DET_TRACE -ErrorAction SilentlyContinue
Write-Output 'E2-RERUN DONE'
exit 0
