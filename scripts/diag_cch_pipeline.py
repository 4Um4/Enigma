# path: /project/scripts/diag_cch_pipeline.py
# Назначение: BLOCK 7 — диагноз разрыва «канон есть — записей 0» (BLOCK 6:
# guard_borko: 28 пунктов author_text, entries=0, все «не поняла», сеялке
# нечего сеять). Смотрим: (1) структуру КАНОНА, (2) все ЧЕРНОВИКИ — есть ли
# записи (разбор Ctrl+G/decompose) и какой провенанс, (3) пробу сеялки
# canonical_chronicle + build_full_seed (что реально посеется), (4) вердикт
# Г1/Г2/Г3. Печать данных как есть (кириллица проходила чисто в BLOCK 5-6).
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT / "backend"), str(ROOT / "backend" / "app")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from app.core.config import BASE_DIR

CANON = BASE_DIR / "config" / "npc" / "chronicles"
DRAFTS = BASE_DIR / "saves" / "silver_wolf" / "chronicle_drafts"


def prov(e):
    p = e.get("provenance") if isinstance(e, dict) else getattr(e, "provenance", None)
    return str(getattr(p, "value", p))


def kind(e):
    k = e.get("kind") if isinstance(e, dict) else getattr(e, "kind", None)
    return str(getattr(k, "value", k))


def brief(path, label):
    print("=" * 12, label)
    try:
        doc = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except Exception as exc:
        print("  NOT READABLE:", exc)
        return None
    if not isinstance(doc, dict):
        print("  not a dict")
        return None
    entries = doc.get("entries") or []
    at = doc.get("author_text") or ""
    items = [ln for ln in at.splitlines() if ln.strip() and ln.strip()[:1].isdigit()]
    print("  keys:", ", ".join(list(doc)[:16]))
    print("  author_text: %d chars, пунктов-строк: %d" % (len(at), len(items)))
    print("  entries:", len(entries))
    if entries:
        print("  provenance:", dict(Counter(prov(e) for e in entries)))
        print("  kinds:", dict(Counter(kind(e) for e in entries)))
        for e in entries[:2]:
            if isinstance(e, dict):
                blob = " ".join(str(v) for v in e.values() if isinstance(v, (str, int, float)))
                print("   [%s/%s] %s" % (kind(e), prov(e), blob[:110]))
    for k in ("game_start_age", "npc_ref", "chronicle_id", "npc_id", "name", "title"):
        if k in doc:
            print("  %s: %s" % (k, str(doc[k])[:80]))
    return doc


print("### 1. КАНОН:", CANON)
canon_docs = {}
for p in sorted(CANON.glob("*.json")):
    canon_docs[p.stem] = brief(p, p.name)
if canon_docs:
    p0 = sorted(CANON.glob("*.json"))[0]
    print("  raw head:", p0.read_text(encoding="utf-8-sig")[:400].replace("\n", " | "))

print()
print("### 2. ЧЕРНОВИКИ:", DRAFTS)
draft_docs = {}
for p in sorted(DRAFTS.glob("*.json")):
    draft_docs[p.stem] = brief(p, p.name)

print()
print("### 3. СЕЯЛКА: что реально посеется прямо сейчас")
try:
    from app.services.chronicle.chronicle_seeder import build_full_seed, canonical_chronicle
    docs = canonical_chronicle()
    print("canonical_chronicle():", list(docs) if docs else "пусто")
    for npc_id in sorted(docs):
        try:
            seed = build_full_seed(npc_id)
        except Exception as exc:
            print("  %s: build_full_seed RAISED: %r" % (npc_id, exc))
            continue
        if not seed:
            print("  %s: seed = None/пусто (сеялке нечего сеять)" % npc_id)
            continue
        print("  %s: seed keys: %s" % (npc_id, ", ".join(list(seed))))
        for k, v in sorted(seed.items()):
            if isinstance(v, (list, tuple)):
                print("     %s: %d шт." % (k, len(v)))
            elif isinstance(v, dict):
                print("     %s: %d ключей" % (k, len(v)))
except Exception as exc:
    print("SEEDER PROBE FAILED:", repr(exc))

print()
print("### 4. ВЕРДИКТ (Г1/Г2/Г3)")
for stem, doc in canon_docs.items():
    n = len((doc or {}).get("entries") or [])
    d = draft_docs.get(stem) or {}
    dn = len(d.get("entries") or [])
    dpc = dict(Counter(prov(e) for e in (d.get("entries") or [])))
    if n == 0 and dn == 0:
        print("  %s: Г1 — записей нет НИ в каноне, НИ в черновике: разбор (Ctrl+G / decompose) не делался или падал. Вот причина «0 записей» и «не поняла» по всем пунктам." % stem)
    elif n == 0 and dn > 0:
        print("  %s: Г2 — в черновике %d записей (%s), но в каноне 0: записи не доехали через canonize — смотреть раздел 2 блока." % (stem, dn, dpc))
    elif n > 0:
        print("  %s: канон имеет %d записей; сеялка скажет своё в разделе 3." % (stem, n))