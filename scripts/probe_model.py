"""
path: scripts/probe_model.py
Назначение: прогон semantic_probe_corpus на произвольной модели.
            Спавнит llama-server на 8181, запускает corpus в том же процессе
            (через import + run_module), парсит метрики.
Запуск: python scripts/probe_model.py "Models LLM\<model>.gguf" "report_name"
"""
import sys, os, subprocess, time, re, io, contextlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODEL = sys.argv[1] if len(sys.argv) > 1 else None
REPORT = sys.argv[2] if len(sys.argv) > 2 else "probe_custom"

if not MODEL:
    print("Usage: python scripts/probe_model.py <path-to-gguf> [report_name]")
    sys.exit(1)

model_path = (ROOT / MODEL).resolve()
if not model_path.exists():
    print(f"Модель не найдена: {model_path}")
    sys.exit(1)

print(f"[PROBE] Модель: {model_path.name} ({model_path.stat().st_size / 1024**3:.2f} GB)")

# 1. Kill existing llama-server
try:
    subprocess.run(['taskkill', '/F', '/IM', 'llama-server.exe'], capture_output=True)
except Exception:
    pass
time.sleep(2)

# 2. Spawn llama-server on 8181
print("[PROBE] Запуск llama-server на 8181...")
proc = subprocess.Popen(
    [
        str(ROOT / "Models LLM" / "llama" / "llama-server.exe"),
        "--model", str(model_path),
        "--ctx-size", "8192",
        "--n-gpu-layers", "99",
        "--port", "8181",
        "--host", "127.0.0.1",
        "--jinja",
    ],
    stdout=subprocess.DEVNULL,
    stderr=subprocess.PIPE,
    creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0,
)
print(f"[PROBE] PID: {proc.pid}. Ждём загрузки (90 сек)...")
time.sleep(90)

if proc.poll() is not None:
    print("[PROBE] ПРОЦЕСС УПАЛ. stderr:")
    print(proc.stderr.read().decode('utf-8', errors='replace')[-3000:])
    sys.exit(1)

# 3. VRAM check
out = subprocess.run(['nvidia-smi', '--query-gpu=memory.used,memory.free', '--format=csv,noheader'],
                     capture_output=True, text=True)
print(f"[PROBE] VRAM: {out.stdout.strip()}")

# 4. Запуск corpus в ТОМ ЖЕ ПРОЦЕССЕ через import
# ENIGMA_DET_KEEP_SERVER=1 чтобы corpus не убил наш сервер
os.environ['ENIGMA_DET_KEEP_SERVER'] = '1'
sys.path.insert(0, str(ROOT / "backend"))
os.chdir(str(ROOT / "backend"))

# Захватываем stdout/stderr в буфер + дублируем в консоль
buf = io.StringIO()
print("[PROBE] Запуск semantic_probe_corpus (in-process)...")

# Импортируем как модуль — его код верхнего уровня выполнит start_llama_server + corpus
import importlib
corpus_mod = importlib.import_module('tests.sandbox.SUPERBOX.scenarios.semantic_probe_corpus')

# Сохраняем весь вывод (corpus пишет через print)
import builtins
_orig_print = builtins.print
def _tee(*args, **kwargs):
    _orig_print(*args, **kwargs)
    buf.write(' '.join(str(a) for a in args) + '\n')
builtins.print = _tee

# Корпус — async; нужен asyncio.run
import asyncio
if hasattr(corpus_mod, 'main'):
    try:
        asyncio.run(asyncio.run(corpus_mod.main()))
    except Exception as e:
        buf.write(f"main() EXCEPTION: {e}\n")

builtins.print = _orig_print

output = buf.getvalue()
# Добавляем stderr процесса (для диагностики)
if proc.poll() is not None:
    output += "\n[LLAMA-SERVER exited]\n" + proc.stderr.read().decode('utf-8', errors='replace')[-2000:]

# Save report
report_path = ROOT / "reports" / f"{REPORT}.txt"
report_path.parent.mkdir(parents=True, exist_ok=True)
report_path.write_text(output, encoding='utf-8')
print(f"[PROBE] Отчёт сохранён: {report_path}")

# VRAM after
out2 = subprocess.run(['nvidia-smi', '--query-gpu=memory.used,memory.free', '--format=csv,noheader'],
                      capture_output=True, text=True)
print(f"[PROBE] VRAM после corpus: {out2.stdout.strip()}")

# Cleanup
proc.terminate()
time.sleep(3)
try: proc.kill()
except: pass

# 5. Parse metrics
total = len(re.findall(r"EXPECTED:", output))
passed = len(re.findall(r"\*", output))
latencies = [float(m.group(1)) for m in re.finditer(r"latency: ([\d.]+)s", output)]
print(f"\n[PROBE] === МЕТРИКИ ===")
print(f"Total: {total}, Match (*): {passed}")
if total > 0:
    print(f"Accuracy: {passed/total*100:.1f}%")
if latencies:
    print(f"Latency: avg={sum(latencies)/len(latencies):.2f}s, max={max(latencies):.2f}s, min={min(latencies):.2f}s, count={len(latencies)}")
