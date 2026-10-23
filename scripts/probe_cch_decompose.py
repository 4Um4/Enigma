"""
path: scripts/probe_cch_decompose.py
Назначение: честный тест ВСЕХ моделей на CCH-задаче (FACT_EXTRACTION + нормализатор).
            Грузит реальный chronicle_decompose_system.txt + 3 тестовых фрагмента,
            отправляет на каждую модель, прогоняет через реальный ChronicleDecompositionNormalizer,
            считает: валидных items, ошибок нормализации.
Запуск: python scripts/probe_cch_decompose.py
"""
import sys, os, subprocess, time, json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODELS_DIR = ROOT / "Models LLM"
REPORT = ROOT / "reports" / "probe_cch_decompose.txt"
REPORT.parent.mkdir(parents=True, exist_ok=True)

FRAGMENTS = [
    ("simple", "В 8 лет Люся осталась сиротой, её приютил Торнин, хозяин трактира. Он был добр, но пил, и иногда бил её."),
    ("medium", "Горан рос в бедной семье кузнеца. Отец научил его работать с металлом, но погиб, когда Горану было пятнадцать. После этого Горан ушел из дома и стал наёмником. Он убил человека впервые в семнадцать лет — это было самообороной, но мучило его всю жизнь."),
    ("complex", "Торнин держит таверну «Серебряный Волк» уже двадцать лет. Жену свою он потерял десять лет назад — она заболела и умерла. С тех пор он пьёт. Дочь Люся ему не родная — он приютил её после того, как её родители погибли. Иногда, когда напьется, он поднимает на нее руку, а наутро не помнит. Борко работает у него вышибалой и закрывает глаза на это."),
]

def run_test(model_path, model_name):
    try: subprocess.run(['taskkill', '/F', '/IM', 'llama-server.exe'], capture_output=True)
    except: pass
    time.sleep(2)
    proc = subprocess.Popen(
        [str(MODELS_DIR / "llama" / "llama-server.exe"),
         "--model", str(model_path),
         "--ctx-size", "8192", "--n-gpu-layers", "99",
         "--port", "8181", "--host", "127.0.0.1", "--jinja"],
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0,
    )
    time.sleep(90)
    if proc.poll() is not None:
        return {"error": "process crashed"}
    import urllib.request
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        h = opener.open("http://127.0.0.1:8181/health", timeout=5)
    except Exception as e:
        return {"error": "health failed"}
    try:
        out = subprocess.run(['nvidia-smi', '--query-gpu=memory.used,memory.free', '--format=csv,noheader'], capture_output=True, text=True)
        vram = out.stdout.strip()
    except: vram = "N/A"
    sys_prompt = (ROOT / "backend" / "prompts" / "chronicle_decompose_system.txt").read_text(encoding='utf-8')
    sys.path.insert(0, str(ROOT / "backend"))
    os.chdir(str(ROOT / "backend"))
    from app.services.chronicle.decomposition_normalizer import ChronicleDecompositionNormalizer, DecompositionError
    total_valid = 0; total_errors = 0; total_latency = 0; details = []
    for frag_name, frag_text in FRAGMENTS:
        user_prompt = "ВОЗРАСТ: неизвестен\n\nФРАГМЕНТ:\n" + frag_text
        body = json.dumps({
            "messages": [{"role": "system", "content": sys_prompt}, {"role": "user", "content": user_prompt}],
            "max_tokens": 2048, "temperature": 0.0,
            "response_format": {"type": "json_object"},
        }).encode("utf-8")
        req = urllib.request.Request("http://127.0.0.1:8181/v1/chat/completions",
            data=body, headers={"Content-Type": "application/json"}, method="POST")
        t0 = time.time()
        try:
            with opener.open(req, timeout=120) as r:
                data = json.loads(r.read().decode("utf-8"))
            content = data["choices"][0]["message"]["content"]
            latency = time.time() - t0; total_latency += latency
            try:
                items = ChronicleDecompositionNormalizer.normalize(content, chronicle_id="test", fragment_ord=0)
                total_valid += len(items)
                details.append("  " + frag_name + ": OK (" + str(len(items)) + " items, " + str(round(latency,1)) + "s)")
            except DecompositionError as e:
                total_errors += 1
                details.append("  " + frag_name + ": DecompositionError: " + str(e)[:120] + " (" + str(round(latency,1)) + "s)")
        except Exception as e:
            total_latency += time.time() - t0; total_errors += 1
            details.append("  " + frag_name + ": LLM_ERROR: " + str(e)[:120])
    proc.terminate(); time.sleep(3)
    try: proc.kill()
    except: pass
    return {"vram": vram, "valid": total_valid, "errors": total_errors,
            "avg_lat": round(total_latency / len(FRAGMENTS), 2), "details": details}

models = sorted(MODELS_DIR.glob("*.gguf"))
models = [m for m in models if "llama" not in m.name.lower() or m.suffix == ".gguf" and "llama-server" not in m.name and "llama-cli" not in m.name]
print("=== CCH DECOMPOSE TEST: " + str(len(models)) + " models ===\n")
lines = ["# CCH DECOMPOSE TEST\n\n| # | Модель | Valid items | Errors | Avg latency (s) | VRAM | Вердикт |\n|---|---|---|---|---|---|---|\n"]
summary = []
for i, mp in enumerate(models, 1):
    name = mp.name; gb = round(mp.stat().st_size / 1024**3, 2)
    print("[" + str(i) + "/" + str(len(models)) + "] " + name + " (" + str(gb) + " GB)...")
    r = run_test(mp, name)
    if "error" in r:
        print("  ERROR: " + r["error"])
        lines.append("| " + str(i) + " | " + name + " | - | - | - | - | X " + r["error"][:40] + " |\n")
        summary.append((name, 0, 999, 0, "ERROR"))
    else:
        v = r["valid"]; e = r["errors"]; lat = r["avg_lat"]; vr = r["vram"]
        verdict = "OK" if v > 0 and e == 0 else ("WARN" if v > 0 else "FAIL")
        print("  valid=" + str(v) + " errors=" + str(e) + " latency=" + str(lat) + "s vram=" + vr)
        lines.append("| " + str(i) + " | " + name + " | " + str(v) + " | " + str(e) + " | " + str(lat) + " | " + vr + " | " + verdict + " |\n")
        for d in r["details"]: lines.append(d + "\n")
        lines.append("\n")
        summary.append((name, v, e, lat, verdict))
lines.append("\n## Сводка (sorted by valid items)\n\n| Модель | Valid | Errors | Latency | Вердикт |\n|---|---|---|---|---|\n")
for name, v, e, lat, verdict in sorted(summary, key=lambda x: (-x[1], x[2])):
    lines.append("| " + name + " | " + str(v) + " | " + str(e) + " | " + str(lat) + "s | " + verdict + " |\n")
REPORT.write_text("".join(lines), encoding='utf-8')
print("\n=== Отчёт: " + str(REPORT) + " ===")
print("\n=== СВОДКА ===")
for name, v, e, lat, verdict in sorted(summary, key=lambda x: (-x[1], x[2])):
    print("  " + verdict + " " + name + ": valid=" + str(v) + " errors=" + str(e) + " latency=" + str(lat) + "s")
