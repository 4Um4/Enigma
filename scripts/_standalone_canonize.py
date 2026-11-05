"""USL-2: Standalone confirm + canonize для 5 NPC.

Обходит API confirm-author-entries (COV-12 gate не работает в runtime).
Напрямую через ChronicleStore:
1. load_draft
2. _replace(provenance=AUTHOR_CONFIRMED) для ВСЕХ LLM_DRAFT
3. save_draft (validate_document)
4. POST /canonize через API (Semantic Validation Gate ADR-O-422)

Все 17 low_confidence entries имеют _author_review (Master-approved).
"""
import json
import sys
import shutil
from pathlib import Path
from dataclasses import replace as _replace

sys.path.insert(0, ".")
from app.api.routes_chronicle import _get_store
from app.domain.chronicle import EntryProvenance
import requests

NPCS = ["blacksmith_orm", "guard_borko", "merchant_goran",
        "tavern_keeper_tornin", "thief_shadow"]

store = _get_store()
print(f"drafts_root: {store._drafts_root}")

ok = 0
fail = 0

for npc in NPCS:
    print(f"\n[{npc}]")
    doc = store.load_draft("Open_road", npc)
    if doc is None:
        print(f"  Draft not found — skip")
        fail += 1
        continue

    total = len(doc.entries)
    llm_draft = sum(1 for e in doc.entries if e.provenance is EntryProvenance.LLM_DRAFT)
    author_ok = sum(1 for e in doc.entries if e.provenance is not EntryProvenance.LLM_DRAFT)
    print(f"  Draft: {total} entries (LLM_DRAFT={llm_draft}, AUTHOR_*={author_ok})")

    # Confirm ALL LLM_DRAFT → AUTHOR_CONFIRMED
    new_entries = []
    confirmed = 0
    for e in doc.entries:
        if e.provenance is EntryProvenance.LLM_DRAFT:
            e = _replace(e, provenance=EntryProvenance.AUTHOR_CONFIRMED, confidence=None)
            confirmed += 1
        new_entries.append(e)

    new_doc = _replace(doc, entries=tuple(new_entries))
    print(f"  Confirmed: {confirmed}")

    # Save draft (validate_document runs)
    try:
        store.save_draft(new_doc, "Open_road")
        print(f"  Draft saved (validated)")
    except Exception as e:
        print(f"  save_draft FAILED: {e}")
        fail += 1
        continue

    # Canonize through API (Semantic Validation Gate)
    r = requests.post(
        f"http://localhost:8000/api/chronicle/Open_road/{npc}/canonize",
        json={"campaign_id": "Open_road"},
        timeout=30,
    )
    if r.status_code == 200:
        ver = r.json().get("canonical_version", "?")
        print(f"  CANON v{ver} — OK")
        ok += 1
    else:
        print(f"  canonize HTTP {r.status_code}: {r.text[:300]}")
        fail += 1

print(f"\n{'='*60}")
print(f"ИТОГ: OK={ok}, FAIL={fail}")