# v3.2 (вердикты Мастера 1/2, TZ-CC-01): -Threads (default 8 — байт-
#   неизменность исторических ног). ПРОТОКОЛЬНЫЙ ИНВАРИАНТ: все ноги после
#   H-BE ОБЯЗАНЫ идти с -t 1 (measurement configuration новых экспериментов;
#   исторические baseline-артефакты заморожены как есть, -t8 c известным
#   noise profile). Смена thread count после GO-2 — только новым
#   measurement-validation GO.
param(
  [Parameter(Mandatory=$true)][string]$ArtifactA,
  [Parameter(Mandatory=$true)][string]$ArtifactB,
  [string]$LegBSet = '',   # 'NAME=VAL[;...]' — env ТОЛЬКО плеча B (контрбаланс)
  [string]$LegBClear = '', # 'NAME[;...]' — снять в плече B
  [switch]$SkipIPTGate,
  # STAGE 2 Candidate Validation: второй backend (IQ3_M, выбор владельца).
  # Non-thinking = изолированная compatibility-правка (ТЗ §3/§4):
  # argv-элемент {"enable_thinking": false}; экранирование по правилам
  # CommandLineToArgvW задано ЗДЕСЬ (один место — не через границу командной
  # строки оркестратора). Think-тег-остаток в content задокументирован
  # STAGE 0b; production-регекс справляется (json 6/6).
  [switch]$Candidate,
  # Вердикт Мастера (i), TZ-CC-01: диагностика детерминизма IQ3_M — число
  # CPU-потоков сервера. Default 8 = историческое поведение (без флага
  # байт-неизменно); -Threads 1 = диагностическая нога локализации
  # A/A-шума. НЕ перекалибровка В-8: измерительный прибор, не контент.
  [int]$Threads = 8,
  # S342-v3.3 (вердикт Мастера): выделенный экспериментальный порт + двухрежимность.
  # Default 8181/SPAWN = байт-неизменность исторических ног.
  [int]$Port = 8181,
  [ValidateSet('SPAWN','REUSE')][string]$Mode = 'SPAWN'
)
 $ErrorActionPreference = 'Stop'
 $traceFile = Join-Path (Split-Path $ArtifactA -Parent) 'b2_health_trace.txt'
 $script:_owned = 0

function _probe {
  param([string]$tag, [switch]$CheckParent)
  $t = Get-Date -Format 'HH:mm:ss'
  $l = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
  $p = 0; if ($l) { $p = [int]$l.OwningProcess }
  $ppid = 0
  if ($p -ne 0) { $ppid = [int]((Get-CimInstance Win32_Process -Filter "ProcessId=$p" -ErrorAction SilentlyContinue).ParentProcessId) }
  $s = 'FAIL-NO-LISTENER'
  if ($p -ne 0) { try { $r = Invoke-RestMethod -Uri ('http://localhost:' + $Port + '/health') -TimeoutSec 10; $s = [string]$r.status } catch { $s = 'FAIL-' + $_.Exception.GetType().Name } }
  $line = "HEALTH-PROBE $tag t=$t listener_pid=$p ppid=$ppid status=$s"
  $line | Tee-Object -FilePath $traceFile -Append | Out-Null
  return [pscustomobject]@{ pid = $p; ppid = $ppid; status = $s }
}

function _cleanup {
  if ($script:_owned -ne 0) {
    Stop-Process -Id $script:_owned -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
    $gone = -not (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
    $line = "CLEANUP owned_pid=$($script:_owned) listener_gone=$gone t=$(Get-Date -Format 'HH:mm:ss')"
    $line | Tee-Object -FilePath $traceFile -Append | Out-Null
    $script:_owned = 0
  }
}

try {
  $pre = _probe 'PRE'
  # S342-v3.3-fix: стопы занятого порта / осиротевшего llama — ТОЛЬКО SPAWN-режим.
  # REUSE обязан НАЙТИ занятый порт (внешний сервер, verify ниже); безусловный
  # гвард убивал положительный REUSE-путь до ветки (негативный смоук слеп к этому).
  if ($Mode -ne 'REUSE') {
  if ($pre.pid -ne 0) { Write-Output "ABORT: порт занят (pid=$($pre.pid))"; exit 2 }
  $_ll = Get-Process llama-server -ErrorAction SilentlyContinue
  if ($_ll) { Write-Output "ABORT: llama без listener ($($_ll.Id -join ','))"; exit 2 }
  }
  # S342-v3.3: REUSE-режим — verify чужого сервера, не спавнить, не убивать
  if ($Mode -eq 'REUSE') {
    if ($pre.status -ne 'ok') { Write-Output "ABORT: REUSE без живого сервера (port=$Port)"; exit 2 }
    $rp = Get-CimInstance Win32_Process -Filter "ProcessId=$($pre.pid)"
    $rc = $rp.CommandLine
    if ($rc -notmatch 'IQ3_M' -or $rc -notmatch '-t 1' -or $rc -notmatch 'enable_thinking') { Write-Output "ABORT: REUSE чужой сервер (cmd=$($rc.Substring(0,[Math]::Min(120,$rc.Length))))"; exit 2 }
    Write-Output "REUSE OK: pid=$($pre.pid) cmd verified (IQ3_M + -t 1 + thinking-off)"
  }

  $exe   = 'C:\DDD\Codex\VSC_Enigma\Enigma\Models LLM\llama\llama-server.exe'
  $model = 'C:\DDD\Codex\VSC_Enigma\Enigma\Models LLM\Qwen2.5-7B-Instruct-abliterated-v2.Q4_K_M.gguf'
  $serverExtra = ''
  if ($Candidate) {
    $model = 'C:\DDD\Codex\VSC_Enigma\Enigma\Models LLM\Qwen3.5-9B-The-Defiant-Fable-Uncnr-Heretic-NEO-MAX-IQ3_M.gguf'
    $serverExtra = '--chat-template-kwargs "{\"enable_thinking\": false}"'
  }
  # PS 5.1 Start-Process НЕ квотит аргументы с пробелами: 'Models LLM' рвался
  # на два токена -> сервер умирал на старте молча (smoke exit 3, lesson).
  # ProcessStartInfo + UseShellExecute=$false: явное квотирование, прямой
  # child (PPID-инвариант by construction), stderr-захват (L4, громкий отказ).
  $proc = $null; $_ok = $true
  if ($Mode -ne 'REUSE') {
  $psi = New-Object System.Diagnostics.ProcessStartInfo
  $psi.FileName = $exe
  $psi.Arguments = "-m `"$model`" --port $port --host localhost -ngl 99 -c 8192 -t $Threads $serverExtra"
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
    try { $r = Invoke-RestMethod -Uri ('http://localhost:' + $Port + '/health') -TimeoutSec 5; if ([string]$r.status -eq 'ok') { $_ok = $true; break } } catch {}
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
  Write-Output "HARNESS OWN: llama_pid=$($proc.Id) ppid=$PID t=$Threads verified"
  }
  # S342-v3.3: REUSE — $proc=$null; гварды ниже переключаются на $pre.pid

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
  $exp = if ($proc) { $proc.Id } else { $pre.pid }
  $expP = if ($proc) { $PID } else { $exp }
  if ($mid.pid -ne $exp -or $mid.status -ne 'ok') {
    Write-Output "INVALID: плечо A (pid=$($mid.pid) exp=$exp)"; _cleanup; exit 5
  }
  $preB = _probe 'PRE-B' -CheckParent
  if ($preB.pid -ne $exp -or $preB.status -ne 'ok') {
    Write-Output "INVALID: до B (pid=$($preB.pid) exp=$exp)"; _cleanup; exit 5
  }
  # leg-env: правки ТОЛЬКО плеча B (контрбаланс состояний на owned-сервере);
  # ПОСЛЕ PRE-B-пробы, до запуска плеча B
  foreach ($kv in ($LegBSet -split ';' | Where-Object { $_ })) { $n, $v = $kv -split '=', 2; Set-Item -Path "env:$n" -Value $v }
  foreach ($n in ($LegBClear -split ';' | Where-Object { $_ })) { Remove-Item -Path "env:$n" -ErrorAction SilentlyContinue }
  cmd /c "cd /d backend && python -B -m tests.sandbox.SUPERBOX.scenarios.semantic_probe_corpus > ..\$ArtifactB 2>&1"
  $post = _probe 'POST-B' -CheckParent
  $expP = if ($proc) { $PID } else { $exp }
  if ($post.pid -ne $exp -or $post.status -ne 'ok') {
    Write-Output "INVALID: плечо B (pid=$($post.pid) exp=$exp)"; _cleanup; exit 5
  }
  # Id захватывается ДО cleanup: после Stop-Process дескриптор процесса
  # освобождён — .Id на exited/disposed Process кидает InvalidCast (PS 5.1).
  # S342-v3.3-fix: REUSE — $proc=$null → exp-модель PID (PS 5.1 молчит на
  # null-property: пустой owned_pid в PAIR OK); teardown — только SPAWN-владение.
  $ownedPid = if ($proc) { $proc.Id } else { $pre.pid }
  _cleanup
  if ($Mode -eq 'REUSE') {
    Write-Output "PAIR OK: reuse_pid=$ownedPid alive (external ownership, no teardown)"
  } else {
    Write-Output "PAIR OK: owned_pid=$ownedPid teardown verified"
  }
  exit 0
}
finally {
  _cleanup
}
