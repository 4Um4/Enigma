# path: /project/backend/tests/sandbox/SUPERBOX/scenarios/b2_det_pair.ps1
# v2: + LegBSet/LegBClear — env-правки ТОЛЬКО плеча B (контрбаланс B2<->A
#   на одном тёплом PID). Харнесс = child-процесс: правки умирают с ним,
#   env вызывающего не затрагивается. Плечо A наследует env вызывающего.
# Exit-коды: 0 пара валидна | 2 порт занят | 3 сервер мёртв после A | 4 identity FAIL | 5 B умер
param(
  [Parameter(Mandatory=$true)][string]$ArtifactA,
  [Parameter(Mandatory=$true)][string]$ArtifactB,
  [string]$LegBSet = '',   # 'NAME=VAL[;NAME=VAL]' — выставить в плече B
  [string]$LegBClear = ''  # 'NAME[;NAME]' — снять в плече B
)
 $ErrorActionPreference = 'Stop'
 $traceFile = Join-Path (Split-Path $ArtifactA -Parent) 'b2_health_trace.txt'

function _probe {
  param([string]$tag)
  $t = Get-Date -Format 'HH:mm:ss'
  $l = Get-NetTCPConnection -LocalPort 8181 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
  $p = 0
  if ($l) { $p = [int]$l.OwningProcess }
  $s = 'FAIL-NO-LISTENER'
  if ($p -ne 0) {
    try { $r = Invoke-RestMethod -Uri 'http://localhost:8181/health' -TimeoutSec 10; $s = [string]$r.status } catch { $s = 'FAIL-' + $_.Exception.GetType().Name }
  }
  $line = "HEALTH-PROBE $tag t=$t listener_pid=$p status=$s"
  $line | Tee-Object -FilePath $traceFile -Append | Out-Null
  return [pscustomobject]@{ pid = $p; status = $s }
}

 $pre = _probe 'PRE'
if ($pre.pid -ne 0) { Write-Output "ABORT: порт 8181 занят (pid=$($pre.pid))"; exit 2 }

cmd /c "cd /d backend && python -B -m tests.sandbox.SUPERBOX.scenarios.semantic_probe_corpus > ..\$ArtifactA 2>&1"

 $mid = _probe 'MID-A'
if ($mid.pid -eq 0 -or $mid.status -ne 'ok') { Write-Output "ABORT: сервер мёртв после A ($($mid.status))"; exit 3 }
 $spawnPid = $mid.pid

 $preB = _probe 'PRE-B'
if ($preB.pid -ne $spawnPid -or $preB.status -ne 'ok') { Write-Output "ABORT: identity FAIL на PRE-B ($($preB.pid)/$($preB.status) vs $spawnPid)"; exit 4 }

# v2: leg-специфичный env ДО плеча B (правки живут только внутри child-процесса)
foreach ($kv in ($LegBSet -split ';' | Where-Object { $_ })) { $n, $v = $kv -split '=', 2; Set-Item -Path "env:$n" -Value $v }
foreach ($n in ($LegBClear -split ';' | Where-Object { $_ })) { Remove-Item -Path "env:$n" -ErrorAction SilentlyContinue }

cmd /c "cd /d backend && python -B -m tests.sandbox.SUPERBOX.scenarios.semantic_probe_corpus > ..\$ArtifactB 2>&1"

 $post = _probe 'POST-B'
if ($post.pid -ne $spawnPid -or $post.status -ne 'ok') { Write-Output "INVALID: B умер/сменён ($($post.pid)/$($post.status) vs $spawnPid)"; exit 5 }

Stop-Process -Id $spawnPid -Force -ErrorAction SilentlyContinue
Write-Output "PAIR OK: spawn_pid=$spawnPid teardown=done"
exit 0
