# path: /project/scripts/fix_confirm_and_canonize.py
# Назначение: BLOCK 8 — лечение Г2. Действие автора «принять разложение»:
# все LLM_DRAFT записи черновика -> AUTHOR_CONFIRMED (ровно тот перевод, который
# по докстрингу canonize обязан делать фронтенд ДО вызова; accept-UI из handoff
# S347 не построен — массовое подтверждение как MVP-замена). Затем канонизация
# 1:1 логике POST /chronicle/{c}/{npc}/canonize: replace(canonical=True,
# canonical_version+1) + store.save_canonical с валидацией «Save = Contract»
# (LLM_DRAFT в каноне запрещён; открытый вопрос без selected_option; dangling).
# Печать: сводка по kind/provenance до, состав white_spots, результат по каждому
# NPC, канон до/после. Откат — .bak-block8 рядом с каждым файлом.
import json
import sys
import traceback
from collections import Counter
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT / "backend"), str(ROOT / "backend" / "app")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from app.core.config import BASE_DIR
from app.domain.chronicle import EntryProvenance
from app.services.chronicle.chronicle_store import ChronicleStore

CAMPAIGN = "silver_wolf"
CANON = BASE_DIR / "config" / "npc" / "chronicles"
DRAFTS = BASE_DIR / "saves" / CAMPAIGN / "chronicle_drafts"


def prov(e):
    p = getattr(e, "provenance", None)
    return str(getattr(p, "value", p))


def kind(e):
    k = getattr(e, "kind", None)
    return str(getattr(k, "value", k))


print("CANON dir :", CANON)
print("DRAFTS dir:", DRAFTS)

store = None
try:
    from app.api.routes_chronicle import _get_store
    store = _get_store()
    print("store: взят из routes_chronicle._get_store() (те же корни, что у живого сервера)")
except Exception as exc:
    print("routes _get_store недоступен (%r) — ручная сборка ChronicleStore" % (exc,))
    store = ChronicleStore(CANON, BASE_DIR / "saves")
print("canonical_path(guard_borko):", store.canonical_path("guard_borko"))
print("draft_path(silver_wolf, guard_borko):", store.draft_path(CAMPAIGN, "guard_borko"))

print()
print("--- канон ДО:")
for p in sorted(CANON.glob("*.json")):
    try:
        d = json.loads(p.read_text(encoding="utf-8-sig"))
        print("  %s: entries=%d canonical=%s version=%s" % (
            p.name, len(d.get("entries") or []), d.get("canonical"), d.get("canonical_version")))
    except Exception as exc:
        print("  %s: ERR %r" % (p.name, exc))

ok, failed = [], []
print()
print("--- обработка черновиков:")
for p in sorted(DRAFTS.glob("*.json")):
    npc = p.stem
    print("=== %s" % npc)
    try:
        doc = store.load_draft(CAMPAIGN, npc)
        if doc is None:
            print("    draft не читается (None) — пропуск")
            failed.append(npc)
            continue
        c_prov = Counter(prov(e) for e in doc.entries)
        c_kind = Counter(kind(e) for e in doc.entries)
        print("    entries=%d | provenance=%s" % (len(doc.entries), dict(c_prov)))
        print("    kinds=%s" % dict(c_kind))
        ws = doc.white_spots or []
        if ws:
            ws_states = Counter(str(getattr(w, "resolution_state", "?")) for w in ws)
            print("    white_spots=%d | states=%s" % (len(ws), dict(ws_states)))
        else:
            print("    white_spots=0")
        if not doc.entries:
            print("    записей нет — канонизировать нечего, пропуск")
            failed.append(npc)
            continue
        flipped = 0
        new_entries = []
        for e in doc.entries:
            if getattr(e, "provenance", None) == EntryProvenance.LLM_DRAFT:
                new_entries.append(replace(e, provenance=EntryProvenance.AUTHOR_CONFIRMED))
                flipped += 1
            else:
                new_entries.append(e)
        doc2 = replace(doc, entries=new_entries)
        p2 = store.save_draft(doc2, CAMPAIGN)
        print("    draft сохранён: %d LLM_DRAFT -> AUTHOR_CONFIRMED (%s)" % (flipped, p2))
        canon = replace(doc2, canonical=True, canonical_version=(doc2.canonical_version or 0) + 1)
        try:
            cp = store.save_canonical(canon)
            print("    CANON OK: %s (version=%s, entries=%d)" % (cp, canon.canonical_version, len(canon.entries)))
            ok.append(npc)
        except ValueError as exc:
            print("    CANON BLOCKED (Save=Contract, это 422 в API):")
            print("      " + str(exc)[:600])
            failed.append(npc)
    except Exception:
        print("    FAIL:")
        print("      " + traceback.format_exc()[-700:].replace("\n", "\n      "))
        failed.append(npc)

print()
print("--- канон ПОСЛЕ:")
for p in sorted(CANON.glob("*.json")):
    try:
        d = json.loads(p.read_text(encoding="utf-8-sig"))
        c_prov2 = Counter(str(e.get("provenance")) for e in (d.get("entries") or []))
        print("  %s: entries=%d (%s) canonical=%s version=%s" % (
            p.name, len(d.get("entries") or []), dict(c_prov2), d.get("canonical"), d.get("canonical_version")))
    except Exception as exc:
        print("  %s: ERR %r" % (p.name, exc))

print()
print("ИТОГ: canonized=%s" % ok)
if failed:
    print("      blocked/failed=%s — см. сообщения выше (Save=Contract или трейсбек)" % failed)
else:
    print("      блокировок нет")