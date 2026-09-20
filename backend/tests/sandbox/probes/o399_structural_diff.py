# path: backend/tests/sandbox/probes/o399_structural_diff.py
# Назначение: структурный диф снапшотов O399-CROSSDIFF (scene_A1 vs scene_B).
# Первый расходящийся JSON-path + агрегат по доменам. Временный; удалить с зонтом.
# Запуск: cd backend; python tests/sandbox/probes/o399_structural_diff.py A1 B; cd ..
import json
import sys
from pathlib import Path

base = Path(__file__).parent.parent / "SUPERBOX" / "reports" / "o399_snaps"

def load(tag):
    return json.loads((base / f"scene_{tag}.json").read_text(encoding="utf-8"))["scene_a"]

def walk(a, b, path, diffs, limit=5):
    if len(diffs) >= 200:
        return
    if type(a) is not type(b):
        diffs.append((path, "TYPE", str(type(a)), str(type(b))))
        return
    if isinstance(a, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a:
                diffs.append((f"{path}.{k}", "ADDED", "-", "..."))
            elif k not in b:
                diffs.append((f"{path}.{k}", "REMOVED", "...", "-"))
            else:
                walk(a[k], b[k], f"{path}.{k}", diffs, limit)
    elif isinstance(a, list):
        if len(a) != len(b):
            diffs.append((path, "LEN", len(a), len(b)))
        for i, (x, y) in enumerate(zip(a, b)):
            walk(x, y, f"{path}[{i}]", diffs, limit)
    elif a != b:
        diffs.append((path, "CHANGED", str(a)[:60], str(b)[:60]))

a, b = load(sys.argv[1]), load(sys.argv[2])
diffs = []
walk(a, b, "$", diffs)
print(f"total diff paths: {len(diffs)}")
buckets = {}
for p, kind, va, vb in diffs:
    dom = p.split(".")[1] if "." in p else p
    buckets.setdefault(dom, 0)
    buckets[dom] += 1
print("по верхним ключам:", json.dumps(buckets, ensure_ascii=False, indent=1))
for p, kind, va, vb in diffs[:12]:
    print(f"  {kind:8} {p}: {va} -> {vb[:40] if isinstance(vb,str) else vb}")