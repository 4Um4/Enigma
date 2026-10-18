# path: /project/scripts/canon_verdicts_report.py
# Назначение: BLOCK 6 — вердикты «поняла / частично / не поняла» по каждому
# пункту КАНОНА (source=canon = то, что сеялка грузит в игру). Печать:
# doc-список, totals, разбивка per_npc (ключи отчёта — интроспекция,
# имена полей не хардкодим) + markdown-вид (как в редакторе по Ctrl+U).
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT / "backend"), str(ROOT / "backend" / "app")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from app.core.config import BASE_DIR
from app.services.chronicle.understanding_report import build_report, docs_from_dir, render_markdown

CANON = BASE_DIR / "config" / "npc" / "chronicles"
DRAFTS = BASE_DIR / "saves" / "silver_wolf" / "chronicle_drafts"

_docs, _prob = docs_from_dir(CANON)
print("canon dir :", CANON)
print("canon docs:", len(_docs), "| problems:", len(_prob))
for _d in _docs:
    print("  -", str(_d)[:130])

_dd, _dp = docs_from_dir(DRAFTS)
print("drafts docs:", len(_dd), "| problems:", len(_dp))

if not _docs:
    print("CANON EMPTY: F9 ещё ничего не принял — вердикты пока по черновикам (Ctrl+U, source=drafts)")
    sys.exit(0)

_rep = build_report(_docs, "silver_wolf")
print("report keys:", ", ".join(list(_rep)))
print("totals:", str(_rep.get("totals"))[:300])

_per = _rep.get("per_npc") or _rep.get("npcs") or []
print("per_npc records:", len(_per))
for _r in _per:
    if isinstance(_r, dict):
        _id = _r.get("npc_id") or _r.get("npc") or _r.get("name") or "?"
        print("--- npc:", _id, "| keys:", ", ".join(list(_r)[:14]))
        for _k in ("totals", "counts", "summary", "verdicts"):
            if _k in _r:
                print("     ", _k, "=", str(_r[_k])[:240])

_md = render_markdown(_rep)
_lines = _md.splitlines()
print("--- markdown: первые 80 из", len(_lines), "строк ---")
for _ln in _lines[:80]:
    print(_ln[:200])