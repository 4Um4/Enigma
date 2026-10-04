# Назначение: pathspec-коммит измерительного контура B/B2/Э0/Э1 (вердикт Мастера, Anti-Race).
# Запуск ИЗ КОРНЯ. Exit: 0 OK | 20 нет файла | 21 staged-коллизия | 22 add | 23 commit | 24 состав
 $ErrorActionPreference = 'Stop'
 $mine = @(
  'backend/app/services/input/llm_compressor_client.py',
  'backend/app/services/input/semantic_library/__init__.py',
  'backend/app/services/input/semantic_library/dialogue_provenance.md',
  'backend/app/services/input/semantic_library/_schema.md',
  'backend/tests/micro/test_prov_b.py',
  'backend/tests/micro/test_prov_b2.py',
  'backend/tests/micro/test_semlib_loader.py',
  'backend/tests/micro/test_semlib_on.py',
  'backend/tests/micro/test_semlib_off.py',
  'backend/tests/micro/golden_production_system_prompt_A.txt',
  'backend/tests/micro/golden_production_system_prompt_B.txt',
  'backend/tests/sandbox/SUPERBOX/scenarios/b2_det_pair.ps1',
  'backend/tests/sandbox/SUPERBOX/scenarios/b2_semlib_e1.ps1',
  'reports/b2_det_check_a.txt','reports/b2_det_check_b.txt',
  'reports/b2_det_check2_a.txt','reports/b2_det_check2_b.txt',
  'reports/b2_det_check3_a.txt',
  'reports/b2_det4_a.txt','reports/b2_det4_b.txt',
  'reports/b2_health_trace.txt',
  'reports/b2_same_a.txt','reports/b2_same_b.txt',
  'reports/b2_cbal_b2a_a.txt','reports/b2_cbal_b2a_b.txt',
  'reports/b2_cbal_a2b_a.txt','reports/b2_cbal_a2b_b.txt',
  'reports/b2_same_a_r2.txt','reports/b2_same_b_r2.txt',
  'reports/b2_cbal_b2a_a_r2.txt','reports/b2_cbal_b2a_b_r2.txt',
  'reports/b2_cbal_a2b_a_r2.txt','reports/b2_cbal_a2b_b_r2.txt',
  'reports/e1_lib2a_a.txt','reports/e1_lib2a_b.txt',
  'reports/e1_a2lib_a.txt','reports/e1_a2lib_b.txt',
  'reports/prov_b_s1.txt','reports/prov_b_s2.txt',
  'reports/prov_b_b2a_A.txt','reports/prov_b_b2a_B.txt',
  'reports/prov_b_a2b_A.txt','reports/prov_b_a2b_B.txt'
)
 $missing = $mine | Where-Object { -not (Test-Path $_) }
if ($missing) { Write-Output "ABORT: отсутствуют файлы: $($missing -join ', ')"; exit 20 }

 $staged = @(git diff --cached --name-only)
 $clash = $staged | Where-Object { $mine -contains $_ }
if ($clash) { Write-Output "ABORT: staged-коллизия с моими путями: $($clash -join ', ')"; exit 21 }

git add -- $mine
if ($LASTEXITCODE -ne 0) { Write-Output 'ABORT: git add'; exit 22 }

 $msg = 'understanding: B/B2/B2-RED + semantic library Э0/Э1 измерительный контур — B-пара relation transfer доказан (PROVENANCE[2] 4/4, 3 SPAWN, оба порядка); B2 = RED: вторая контрастная пара АННИГИЛИРОВАЛА provenance-канонизацию (GEN-3RD/IND/EDGE 0 живых, same-instance контрбаланс оба порядка, order-эффект исключён; dormant ENIGMA_PROV_B2); health-gated harness (identity по PID+/health, урок REUSE-лжи det_check2; serving-смерти -> F5 отдельный ownership); Э0 semantic library: модульная md-библиотека + closed-schema loader + golden-lock (OFF байт=production A, ON байт=состояние B, 14 замков); Э1 transfer-without-interference: LIB поведенчески=B (0/90 строк), PROVENANCE[2] жив в обоих порядках, FP_ORD/FP_3RD=0; вердикты Мастера: D1/D2/Э0/Э1 closed, Э2 GO (interference gate обязателен), production migration/router HOLD; типизационная гигиена _sync_compress (явный urllib.error, content pre-bound); micro 192, IPT 51/0'
git commit -m $msg -- $mine
if ($LASTEXITCODE -ne 0) { Write-Output "ABORT: git commit ($LASTEXITCODE)"; exit 23 }

 $committed = @(git show --name-only --format= HEAD | Where-Object { $_ })
 $extra = $committed | Where-Object { $mine -notcontains $_ }
 $absent = $mine | Where-Object { $committed -notcontains $_ }
if ($extra -or $absent) { Write-Output "FAIL-VERIFY: extra=[$($extra -join ',')] absent=[$($absent -join ',')]"; exit 24 }

 $stagedAfter = @(git diff --cached --name-only)
Write-Output "COMMIT OK: файлов=$($committed.Count), состав = ожидаемому 1:1"
Write-Output "чужие staged не тронуты: $($stagedAfter -join ', ')"
git status --porcelain | Select-Object -First 12
exit 0
