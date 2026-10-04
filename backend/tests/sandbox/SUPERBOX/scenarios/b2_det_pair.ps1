# v3.1: (a) PPID-инвариант — реальное родительство llama->harness проверяется
#   в каждой пробе (MID/PRE-B/POST: живой родитель = харнесс жив);
#   (b) cleanup-path: любой ABORT/INVALID гасит owned-PID и верифицирует
#   отсутствие listener (не рожаем новый orphan).
# Exit: 0 OK | 2 занято | 3 spawn/PPID FAIL | 4 IPT-гейт | 5 плечо умерло
param(
  [Parameter(Mandatory=$true)][string]$ArtifactA,
  [Parameter(Mandatory=$true)][string]$ArtifactB,
  [string]$LegBSet = '',   # 'NAME=VAL[;...]' — env ТОЛЬКО плеча B (контрбаланс)
  [string]$LegBClear = '', # 'NAME[;...]' — снять в плече B
  [switch]$SkipIPTGate
)
 $ErrorActionPreference = 'Stop'
 $traceFile = Join-Path (Split-Path $ArtifactA -Parent) 'b2_health_trace.txt'
 $script:_owned = 0

function _probe {
  param([string]$tag, [switch]$CheckParent)
  $t = Get-Date -Format 'HH:mm:ss'
  $l = Get-NetTCPConnection -LocalPort 8181 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
  $p = 0; if ($l) { $p = [int]$l.OwningProcess }
  $ppid = 0
  if ($p -ne 0) { $ppid = [int]((Get-CimInstance Win32_Process -Filter "ProcessId=$p" -ErrorAction SilentlyContinue).ParentProcessId) }
  $s = 'FAIL-NO-LISTENER'
  if ($p -ne 0) { try { $r = Invoke-RestMethod -Uri 'http://localhost:8181/health' -TimeoutSec 10; $s = [string]$r.status } catch { $s = 'FAIL-' + $_.Exception.GetType().Name } }
  $line = "HEALTH-PROBE $tag t=$t listener_pid=$p ppid=$ppid status=$s"
  $line | Tee-Object -FilePath $traceFile -Append | Out-Null
  return [pscustomobject]@{ pid = $p; ppid = $ppid; status = $s }
}

function _cleanup {
  if ($script:_owned -ne 0) {
    Stop-Process -Id $script:_owned -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
    $gone = -not (Get-NetTCPConnection -LocalPort 8181 -State Listen -ErrorAction SilentlyContinue)
    $line = "CLEANUP owned_pid=$($script:_owned) listener_gone=$gone t=$(Get-Date -Format 'HH:mm:ss')"
    $line | Tee-Object -FilePath $traceFile -Append | Out-Null
    $script:_owned = 0
  }
}

try {
  $pre = _probe 'PRE'
  if ($pre.pid -ne 0) { Write-Output "ABORT: порт занят (pid=$($pre.pid))"; exit 2 }
  $_ll = Get-Process llama-server -ErrorAction SilentlyContinue
  if ($_ll) { Write-Output "ABORT: llama без listener ($($_ll.Id -join ','))"; exit 2 }

  $exe   = 'C:\DDD\Codex\VSC_Enigma\Enigma\Models LLM\llama\llama-server.exe'
  $model = 'C:\DDD\Codex\VSC_Enigma\Enigma\Models LLM\Qwen2.5-7B-Instruct-abliterated-v2.Q4_K_M.gguf'
  # PS 5.1 Start-Process НЕ квотит аргументы с пробелами: 'Models LLM' рвался
  # на два токена -> сервер умирал на старте молча (smoke exit 3, lesson).
  # ProcessStartInfo + UseShellExecute=$false: явное квотирование, прямой
  # child (PPID-инвариант by construction), stderr-захват (L4, громкий отказ).
  $psi = New-Object System.Diagnostics.ProcessStartInfo
  $psi.FileName = $exe
  $psi.Arguments = "-m `"$model`" --port 8181 --host localhost -ngl 99 -c 8192 -t 8"
  $psi.UseShellExecute = $false
  $psi.CreateNoWindow = $true
  $psi.RedirectStandardOutput = $true
  $psi.RedirectStandardError = $true
  $proc = [System.Diagnostics.Process]::Start($psi)
  $script:_owned = $proc.Id
  $stdoutTask = $proc.StandardOutput.ReadToEndAsync()
  $stderrTask = $proc.StandardError.ReadToEndAsync()

  $_ok = $false
  for ($i=0; $i -lt 24; $i++) {
    Start-Sleep -Seconds 5
    if ($proc.HasExited) { break }
    try { $r = Invoke-RestMethod -Uri 'http://localhost:8181/health' -TimeoutSec 5; if ([string]$r.status -eq 'ok') { $_ok = $true; break } } catch {}
  }
  $h = _probe 'HARNESS-SPAWN'
  # LOCK-1: родительство + громкая диагностика мёртвого spawn (stderr в вывод)
  if (-not $_ok -or $h.pid -ne $proc.Id -or $h.ppid -ne $PID) {
    $_err = ''; $ec = 'running'
    if ($proc.HasExited) { $ec = $proc.ExitCode }
    try { if ($stderrTask.Wait(3000)) { $_err = $stderrTask.Result } } catch {}
    if ($_err) { $_err = (($_err -split "`r?`n" | Where-Object { $_ }) | Select-Object -Last 5) -join ' | '; if ($_err.Length -gt 400) { $_err = '...' + $_err.Substring($_err.Length - 400) } }
    Write-Output "ABORT: spawn/PPID FAIL (listener=$($h.pid) ppid=$($h.ppid) harness=$PID exited=$($proc.HasExited) code=$ec stderr=$_err)"
    _cleanup; exit 3
  }
  Write-Output "HARNESS OWN: llama_pid=$($proc.Id) ppid=$PID verified"

  if (-not $SkipIPTGate) {
    $_ipt = cmd /c "python backend\tests\IPT.py 2>&1" | Out-String
    $_m = [regex]::Match($_ipt, 'ИТОГО: (\d+) passed / (\d+) failed')
    if (-not $_m.Success -or [int]$_m.Groups[2].Value -ne 0 -or [int]$_m.Groups[1].Value -lt 51) {
      Write-Output "IPT-GATE FAIL: $($_m.Value)"; _cleanup; exit 4
    }
    Write-Output "IPT-GATE OK: $($_m.Groups[1].Value)/$($_m.Groups[2].Value)"
  }

  cmd /c "cd /d backend && python -B -m tests.sandbox.SUPERBOX.scenarios.semantic_probe_corpus > ..\$ArtifactA 2>&1"
  $mid = _probe 'MID-A' -CheckParent
  if ($mid.pid -ne $proc.Id -or $mid.status -ne 'ok' -or $mid.ppid -ne $PID) {
    Write-Output "INVALID: плечо A (pid=$($mid.pid) ppid=$($mid.ppid))"; _cleanup; exit 5
  }
  $preB = _probe 'PRE-B' -CheckParent
  if ($preB.pid -ne $proc.Id -or $preB.status -ne 'ok' -or $preB.ppid -ne $PID) {
    Write-Output "INVALID: до B"; _cleanup; exit 5
  }
  # leg-env: правки ТОЛЬКО плеча B (контрбаланс состояний на owned-сервере);
  # ПОСЛЕ PRE-B-пробы, до запуска плеча B
  foreach ($kv in ($LegBSet -split ';' | Where-Object { $_ })) { $n, $v = $kv -split '=', 2; Set-Item -Path "env:$n" -Value $v }
  foreach ($n in ($LegBClear -split ';' | Where-Object { $_ })) { Remove-Item -Path "env:$n" -ErrorAction SilentlyContinue }
  cmd /c "cd /d backend && python -B -m tests.sandbox.SUPERBOX.scenarios.semantic_probe_corpus > ..\$ArtifactB 2>&1"
  $post = _probe 'POST-B' -CheckParent
  if ($post.pid -ne $proc.Id -or $post.status -ne 'ok' -or $post.ppid -ne $PID) {
    Write-Output "INVALID: плечо B (pid=$($post.pid) ppid=$($post.ppid))"; _cleanup; exit 5
  }
  # Id захватывается ДО cleanup: после Stop-Process дескриптор процесса
  # освобождён — .Id на exited/disposed Process кидает InvalidCast (PS 5.1).
  $ownedPid = $proc.Id
  _cleanup
  Write-Output "PAIR OK: owned_pid=$ownedPid teardown verified"
  exit 0
}
finally {
  _cleanup
}
