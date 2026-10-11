# path: /project/reports/w3_native5.ps1
# Назначение: цикл фазы D (адд.5): сторожа -> SPAWN 28184 -> W3 REUSE -> native5 REUSE -> STOP; FAIL -> exit 1.
# Зависимости: b2_det_pair.ps1 v3.3+fix; IQ3_M; git. Сущности: _verify/_pair/_set_leg_env/_snapshot.
 $ErrorActionPreference = 'Stop'

 $PORT    = 28184
 $URL     = "http://localhost:$PORT"
 $ROOT    = 'C:\DDD\Codex\VSC_Enigma\Enigma'
 $HARNESS = "$ROOT\backend\tests\sandbox\SUPERBOX\scenarios\b2_det_pair.ps1"
 $MODULE  = "$ROOT\backend\app\services\input\semantic_library\dialogue_identity.md"
 $SHA_PIN = 'E93E62E46A908EC9F9FC5DBCE8DC347640C5935E36A048CD1398AFE72EB664A2'
 $EXE     = "$ROOT\Models LLM\llama\llama-server.exe"
 $MODEL   = "$ROOT\Models LLM\Qwen3.5-9B-The-Defiant-Fable-Uncnr-Heretic-NEO-MAX-IQ3_M.gguf"

 $SRV   = "$ROOT\reports\h_id_w3_server_env.txt"
 $W3ENV = "$ROOT\reports\h_id_w3_env.txt"
 $N5ENV = "$ROOT\reports\h_id_native5_env.txt"
 $W3LOG = "$ROOT\reports\h_id_w3_run.log"
 $N5LOG = "$ROOT\reports\h_id_native5_run.log"
 $W3A = 'reports\h_id_w3_a.txt';      $W3B = 'reports\h_id_w3_b.txt'
 $N5A = 'reports\h_id_native5_a.txt'; $N5B = 'reports\h_id_native5_b.txt'

 $script:srvPid = 0
 $script:srvCt  = $null

function _fail([string]$m) { Write-Output "FAIL: $m"; exit 1 }
function _cts { if ($script:srvCt) { $script:srvCt.ToString('yyyy-MM-dd HH:mm:ss') } else { '<null>' } }
function _srv([string]$line) { Add-Content -LiteralPath $SRV -Value $line -Encoding utf8 }

function _verify([string]$stage) {
  # REUSE-дисциплина адд.5: PID + CreationTime + cmd + health (до/между/после)
  $l = Get-NetTCPConnection -LocalPort $PORT -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
  if (-not $l) { _fail "$stage : нет listener на $PORT" }
  $p = [int]$l.OwningProcess
  if ($p -ne $script:srvPid) { _fail "$stage : PID изменился (exp=$($script:srvPid) got=$p) — PID-reuse" }
  $gp = Get-Process -Id $p -ErrorAction SilentlyContinue
  if (-not $gp) { _fail "$stage : процесс $p мёртв" }
  if ([string]$gp.StartTime -ne [string]$script:srvCt) { _fail "$stage : StartTime изменился (PID-reuse)" }
  try { $r = Invoke-RestMethod -Uri "$URL/health" -TimeoutSec 10; if ([string]$r.status -ne 'ok') { _fail "$stage : health=$($r.status)" } }
  catch { _fail "$stage : health EXC $($_.Exception.GetType().Name)" }
  $rc = (Get-CimInstance Win32_Process -Filter "ProcessId=$p").CommandLine
  if ($rc -notmatch 'IQ3_M' -or $rc -notmatch '-t 1' -or $rc -notmatch 'enable_thinking') { _fail "$stage : cmd перестал совпадать" }
  _srv "stage=$stage pid=$p ct_ok=True cmd_ok=True health=ok"
  Write-Output "$stage OK: pid=$p ct/cmd/health verified"
}

function _set_leg_env {
  # prereg §3: перед КАЖДЫМ вызовом harness; native-нога — MODULES/SEM_LIB сняты ЯВНО
  Set-Item env:ENIGMA_DET_KEEP_SERVER '1'
  Set-Item env:ENIGMA_DET_TRACE '1'
  # wrongsrv-урок: Settings читает env с префиксом (env_prefix="AIDM_",
  # config.py:188) — рабочее имя AIDM_LLAMA_CPP_SERVER_URL; непрефиксное
  # выставляем тоже (буква адд.5 / прямые os.environ-читатели, если есть).
  Set-Item env:AIDM_LLAMA_CPP_SERVER_URL $URL
  Set-Item env:LLAMA_CPP_SERVER_URL $URL
  Remove-Item env:MODULES, env:ENIGMA_SEM_LIB -ErrorAction SilentlyContinue
}

function _snapshot([string]$path, [string]$pair, [string]$note) {
  $m  = if ($env:MODULES) { $env:MODULES } else { '<>' }
  $sl = if ($env:ENIGMA_SEM_LIB) { $env:ENIGMA_SEM_LIB } else { '<>' }
  $line = "ts=$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') head=$(git -C $ROOT rev-parse --short HEAD) pair=$pair KEEP_SERVER=$($env:ENIGMA_DET_KEEP_SERVER) DET_TRACE=$($env:ENIGMA_DET_TRACE) MODULES=$m ENIGMA_SEM_LIB=$sl AIDM_LLAMA_CPP_SERVER_URL=$($env:AIDM_LLAMA_CPP_SERVER_URL) mode=NATIVE-arbiter=goldenA warmup_pid=$($script:srvPid) ct=$(_cts) note=$note"
  Add-Content -LiteralPath $path -Value $line -Encoding utf8
}

function _pair([string]$a, [string]$b, [string]$log, [string]$label) {
  Write-Output "=== $label : harness REUSE port=$PORT ==="
  & powershell -NoProfile -ExecutionPolicy Bypass -File $HARNESS -ArtifactA $a -ArtifactB $b -Candidate -Threads 1 -Port $PORT -Mode REUSE -SkipIPTGate *> $log
  $code = $LASTEXITCODE
  if (-not (Test-Path -LiteralPath $log)) { _fail "$label : лог отсутствует $log" }
  $logTxt = Get-Content -LiteralPath $log
  $bad = $logTxt | Select-String -Pattern 'ABORT|INVALID|IPT-GATE FAIL' | Select-Object -First 1
  if ($code -ne 0) { _fail "$label : harness exit=$code; $(if ($bad) { $bad.Line } else { 'нет ABORT-строки' })" }
  if (-not ($logTxt | Select-String -Pattern "REUSE OK: pid=$($script:srvPid) cmd verified")) { _fail "$label : REUSE OK не подтверждает наш pid (лог: $log)" }
  if (-not ($logTxt | Select-String -Pattern "PAIR OK: reuse_pid=$($script:srvPid)")) { _fail "$label : PAIR OK не подтверждает reuse_pid (лог: $log)" }
  foreach ($f in @($a, $b)) {
    if (-not (Test-Path -LiteralPath "$ROOT\$f")) { _fail "$label : артефакт отсутствует $f (Test-Path)" }
    $envLine = Select-String -Path "$ROOT\$f" -Pattern '\[DET-ENV\]' | Select-Object -First 1
    if (-not $envLine) { _fail "$label : нет [DET-ENV] в $f" }
    # getenvfail-урок (писатель прочитан — scripts/llm_server_manager.py): [DET-ENV]
    # model = ФАКТИЧЕСКАЯ модель сервера, к которому менеджер подключился; mode =
    # attach/spawn МЕНЕДЖЕРА; port/owner_pid = учёт на дефолтном порту менеджера
    # (8181) — при attach на 28184 дают port=8181/owner_pid=unknown (артефакт
    # отображения, не рассинхрон). Сцепка доказывается: модель IQ3_M + attach
    # (mode=REUSE) + 8181 пуст после пары + наш сервер на 28184 (пробы+_verify).
    if ($envLine.Line -notmatch 'IQ3_M') { _fail "$label : [DET-ENV] модель не IQ3_M (чужой сервер): $($envLine.Line)" }
    if ($envLine.Line -notmatch 'mode=REUSE') { _fail "$label : [DET-ENV] не attach (spawn = менеджер спавнил своего): $($envLine.Line)" }
    if (Get-NetTCPConnection -LocalPort 8181 -State Listen -ErrorAction SilentlyContinue) { _fail "$label : 8181 занят после пары — параллельный spawn" }
    $n = @(Select-String -Path "$ROOT\$f" -Pattern '\[DET-TRACE\]').Count
    Write-Output "$label : $f [DET-ENV] ok, traces=$n"
    if ($n -eq 0) { _fail "$label : 0 трасс в $f — транспортная смерть" }
  }
  Write-Output "$label : PAIR OK (pid=$($script:srvPid) подтверждён)"
}

try {
  # ===== 0. Сторожа (адд.4/адд.5) =====
  if ((Get-Location).Path -ne $ROOT) { _fail "запуск из корня репо (сейчас $(Get-Location).Path)" }
  foreach ($f in @($SRV, $W3ENV, $N5ENV, $W3LOG, $N5LOG, "$ROOT\$W3A", "$ROOT\$W3B", "$ROOT\$N5A", "$ROOT\$N5B")) {
    if (Test-Path -LiteralPath $f) { _fail "имя занято: $f" }
  }
  if (Get-NetTCPConnection -LocalPort 8181 -State Listen -ErrorAction SilentlyContinue) { _fail "порт 8181 занят (IPT/production)" }
  if (Get-NetTCPConnection -LocalPort $PORT -State Listen -ErrorAction SilentlyContinue) { _fail "порт $PORT занят (до spawn должен быть пуст)" }
  if (Get-Process llama-server -ErrorAction SilentlyContinue) { _fail "llama-server уже жив — останови/эскалация до цикла" }
  $fp = Get-Process python* -ErrorAction SilentlyContinue | Where-Object { $_.Id -ne $PID }
  if ($fp) { _fail "чужие python: $($fp.Id -join ',') — окно тишины §3.12" }
  if (-not (Test-Path -LiteralPath $HARNESS)) { _fail "harness отсутствует: $HARNESS" }
  $h = (Get-FileHash -LiteralPath $MODULE -Algorithm SHA256).Hash
  if ($h -ne $SHA_PIN) { _fail "SHA256 модуля ≠ пин: $h" }
  # wrongsrv-урок: сцепку env->settings->URL проверяем ДО цикла — 5 сек вместо
  # 35 мин «молча не туда» (механизм префикса AIDM_).
  Set-Item env:AIDM_LLAMA_CPP_SERVER_URL $URL
  $_cu = (cmd /c "cd /d backend && python -c `"from app.core.config import settings; print(settings.llama_cpp_server_url)`" 2>&1") | Out-String
  Remove-Item env:AIDM_LLAMA_CPP_SERVER_URL -ErrorAction SilentlyContinue
  if ($_cu -notmatch [regex]::Escape($URL)) {
    $_last = (($_cu -split "`r?`n") | Where-Object { $_ } | Select-Object -Last 1)
    _fail "сцепка env->settings: settings -> $_last (ожидалось $URL)"
  }
  Write-Output "COUPLING OK: settings.llama_cpp_server_url = $URL"
  Write-Output "GUARDS OK: имена/порты/llama/python/SHA/сцепка чисты; head=$(git -C $ROOT rev-parse --short HEAD)"

  # ===== 1. SPAWN 28184 (квотирование вербатимом из прибора; доказано дважды) =====
  $serverExtra = '--chat-template-kwargs "{\"enable_thinking\": false}"'
  $psi = New-Object System.Diagnostics.ProcessStartInfo
  $psi.FileName = $EXE
  $psi.Arguments = "-m `"$MODEL`" --port $PORT --host localhost -ngl 99 -c 8192 -t 1 $serverExtra"
  $psi.UseShellExecute = $false
  $psi.CreateNoWindow = $true
  $psi.RedirectStandardOutput = $true
  $psi.RedirectStandardError = $true
  $proc = [System.Diagnostics.Process]::Start($psi)
  $stdoutTask = $proc.StandardOutput.ReadToEndAsync()
  $stderrTask = $proc.StandardError.ReadToEndAsync()
  $script:srvPid = $proc.Id
  # Краш-цикл 1: у System.Diagnostics.Process нет .CreationTime (тихий null
  # в PS 5.1) — свойство называется .StartTime; лог-метка оставлена 'ct=':
  # молча отдаёт null, ToString на null валит скрипт. Retry + гвард.
  $script:srvCt = $null
  for ($i = 0; $i -lt 10 -and -not $script:srvCt; $i++) {
    Start-Sleep -Milliseconds 300
    $_g = Get-Process -Id $proc.Id -ErrorAction SilentlyContinue
    if ($_g) { try { $script:srvCt = $_g.StartTime } catch { $script:srvCt = $null } }
  }
  if (-not $script:srvCt) { _fail "CreationTime недоступен (pid=$($proc.Id)); сервер будет остановлен finally" }
  _srv "ts=$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') head=$(git -C $ROOT rev-parse --short HEAD) stage=SPAWN server_pid=$($script:srvPid) ct=$(_cts) port=$PORT"
  Write-Output "SPAWN: pid=$($script:srvPid) ct=$(_cts)"

  $_ok = $false
  for ($i = 0; $i -lt 24; $i++) {
    Start-Sleep -Seconds 5
    if ($proc.HasExited) { break }
    try { $r = Invoke-RestMethod -Uri "$URL/health" -TimeoutSec 5; if ([string]$r.status -eq 'ok') { $_ok = $true; break } } catch {}
  }
  if (-not $_ok) {
    $_err = ''
    if ($proc.HasExited) { try { if ($stderrTask.Wait(3000)) { $_err = $stderrTask.Result } } catch {} }
    _fail "SPAWN health FAIL (exited=$($proc.HasExited)); stderr: $($_err)"
  }
  _verify 'SPAWN_VERIFY'

  # ===== 2. W3 — прогрев корпусной парой (в гейты не входит) =====
  _set_leg_env
  _snapshot $W3ENV 'h_id_w3' 'procedure-W3-not-measurement'
  _pair $W3A $W3B $W3LOG 'W3'
  _verify 'W3_POST'

  # ===== 3. native5 — измерительная пара =====
  _set_leg_env
  _snapshot $N5ENV 'h_id_native5' 'measurement-I-native5'
  _pair $N5A $N5B $N5LOG 'NATIVE5'
  _verify 'NATIVE5_POST'

  Write-Output "NATIVE5 DONE"
  _srv "stage=NATIVE5_DONE ts=$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"

  # ===== 4. Явная остановка (адд.5) =====
  Stop-Process -Id $script:srvPid -Force -ErrorAction SilentlyContinue
  Start-Sleep -Seconds 2
  $gone = -not (Get-NetTCPConnection -LocalPort $PORT -State Listen -ErrorAction SilentlyContinue)
  _srv "stage=STOP pid=$($script:srvPid) listener_gone=$gone ts=$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
  if (-not $gone) { _fail "сервер не остановился" }
  Write-Output "STOP OK: pid=$($script:srvPid) listener_gone=True"
  exit 0
}
finally {
  # Ни один FAIL не оставляет осиротевшего IQ3_M (~5.5 ГБ RAM)
  if ($script:srvPid -ne 0) {
    if (Get-Process -Id $script:srvPid -ErrorAction SilentlyContinue) {
      Stop-Process -Id $script:srvPid -Force -ErrorAction SilentlyContinue
      Start-Sleep -Seconds 2
      $g = -not (Get-NetTCPConnection -LocalPort $PORT -State Listen -ErrorAction SilentlyContinue)
      _srv "stage=FINALLY_STOP pid=$($script:srvPid) listener_gone=$g ts=$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
      Write-Output "FINALLY STOP: pid=$($script:srvPid) gone=$g"
    }
  }
  Remove-Item env:LLAMA_CPP_SERVER_URL, env:AIDM_LLAMA_CPP_SERVER_URL, env:ENIGMA_DET_KEEP_SERVER, env:ENIGMA_DET_TRACE -ErrorAction SilentlyContinue
}
