# path: /project/scripts/block8_probe.py
# Назначение: BLOCK 8 — проверка после лечения Г2. (A) LIVE understanding по
# канону с живого сервера (= то, что покажет Ctrl+U в редакторе); (B) те же
# вердикты in-process (docs_from_dir + build_report + render_markdown);
# (C) исправленная проба сеялки из BLOCK 7: canonical_chronicle(npc_id) по
# настоящей сигнатуре (тогда вызвали без аргумента) + build_full_seed(npc_id) —
# что реально посеется в «новую игру».
import inspect
import json
import sys
import traceback
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT / "backend"), str(ROOT / "backend" / "app")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from app.core.config import BASE_DIR

CAMPAIGN = "silver_wolf"
CANON = BASE_DIR / "config" / "npc" / "chronicles"

print("### A. LIVE understanding по канону (живой сервер, как Ctrl+U)")
try:
    url = ("http://127.0.0.1:8000/api/chronicle/%s/understanding"
           "?source=canon&format=json" % CAMPAIGN)
    with urllib.request.urlopen(url, timeout=90) as r:
        data = json.loads(r.read().decode("utf-8"))
    print("LIVE: status=%s count=%s" % (data.get("status"), data.get("count")))
    rep = data.get("report")
    if isinstance(rep, str):
        try:
            rep = json.loads(rep)
        except Exception:
            rep = None
    if isinstance(rep, dict):
        print("report keys:", ", ".join(list(rep)[:14]))
        print("totals:", json.dumps(rep.get("totals"), ensure_ascii=False)[:400])
        per = rep.get("per_npc") or rep.get("npcs") or []
        for row in per:
            if isinstance(row, dict):
                nid = row.get("npc_id") or row.get("npc") or "?"
                print("  ", nid, ":", json.dumps(row.get("totals") or row.get("counts"), ensure_ascii=False)[:240])
    else:
        t = str(data.get("text") or "")
        print("text head:", t.replace("\n", " | ")[:600])
except Exception as exc:
    print("LIVE недоступен (не смертельно, in-process ниже):", repr(exc))

print()
print("### B. ВЕРДИКТЫ по канону in-process (docs_from_dir + build_report)")
from app.services.chronicle.understanding_report import build_report, docs_from_dir, render_markdown

docs, problems = docs_from_dir(CANON)
print("canon docs:", len(docs), "| problems:", len(problems))
if docs:
    rep = build_report(docs, CAMPAIGN)
    print("report keys:", ", ".join(list(rep)))
    print("totals:", str(rep.get("totals"))[:300])
    md = render_markdown(rep)
    lines = md.splitlines()
    print("--- markdown (первые 50 из %d строк) ---" % len(lines))
    for ln in lines[:50]:
        print(ln[:180])

print()
print("### C. СЕЯЛКА: что реально посеется (исправленная проба BLOCK 7)")
from app.services.chronicle.chronicle_seeder import build_full_seed, canonical_chronicle

print("sig canonical_chronicle:", inspect.signature(canonical_chronicle))
print("sig build_full_seed:", inspect.signature(build_full_seed))
for p in sorted(CANON.glob("*.json")):
    npc = p.stem
    try:
        doc = canonical_chronicle(npc)
        if doc is None:
            print("%s: canonical_chronicle -> None" % npc)
            continue
        if hasattr(doc, "entries"):
            print("%s: канон прочитан, entries=%d" % (npc, len(doc.entries)))
        else:
            print("%s: канон прочитан, тип %s" % (npc, type(doc).__name__))
        seed = build_full_seed(npc)
        if not seed:
            print("   build_full_seed -> пусто (сеялке нечего сеять!)")
            continue
        if isinstance(seed, dict):
            for k in sorted(seed):
                v = seed[k]
                if isinstance(v, (list, tuple)):
                    print("   %s: %d шт." % (k, len(v)))
                elif isinstance(v, dict):
                    print("   %s: %d ключей" % (k, len(v)))
                else:
                    print("   %s: %s" % (k, str(v)[:70]))
        else:
            print("   seed тип:", type(seed).__name__, str(seed)[:200])
    except Exception:
        print("%s: FAIL" % npc)
        print("   " + traceback.format_exc()[-500:].replace("\n", "\n   "))