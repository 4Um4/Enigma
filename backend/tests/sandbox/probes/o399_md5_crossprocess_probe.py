# path: backend/tests/sandbox/probes/o399_md5_crossprocess_probe.py
# Назначение: executable proof ADR-O-399 Iter2 — стабильный digest выбирает
# ОДИНАКОВЫЙ option из пула в ДВУХ отдельных Python-процессах (независимо
# от PYTHONHASHSEED). Временный зонд приёмки; удалить после кампании.
# Зависимости: stdlib. Запуск: cd backend; python tests/sandbox/probes/o399_md5_crossprocess_probe.py; cd ..
"""
Запуск: cd backend; python tests/sandbox/probes/o399_md5_crossprocess_probe.py; cd ..
"""

import hashlib
import subprocess
import sys

CODE = (
    "import hashlib\n"
    "p = 'текст промпта для проверки'\n"
    "opts = ['[Mock] А', '[Mock] Б', '[Mock] В', '[Mock] Г']\n"
    "i = int(hashlib.md5(p.encode('utf-8')).hexdigest(), 16) % len(opts)\n"
    "print(opts[i])\n"
)

results = []
for n in (1, 2):
    r = subprocess.run([sys.executable, "-c", CODE], capture_output=True, text=True)
    results.append(r.stdout.strip())
    print(f"process {n}: pick = {results[-1]}")

if results[0] == results[1] and results[0]:
    print("[PROBE-MD5] ✅ process-independent: оба процесса выбрали одинаковый option")
else:
    print("[PROBE-MD5] 🔴 РАЗНЫЙ выбор между процессами")
    raise SystemExit(1)