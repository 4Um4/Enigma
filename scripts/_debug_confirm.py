import sys, json, dataclasses
sys.path.insert(0, ".")
from app.api.routes_chronicle import _get_store
from app.domain.chronicle import EntryProvenance
from dataclasses import replace as _replace

store = _get_store()
doc = store.load_draft("Open_road", "guard_borko")
print(f"Draft: {len(doc.entries)} entries")

# Симулировать confirm-author-entries логику
confirmed = 0
skipped_open_questions = 0
skipped_low_confidence = 0
skipped_already_confirmed = 0

for e in doc.entries:
    if e.provenance is EntryProvenance.LLM_DRAFT:
        if e.open_questions:
            skipped_open_questions += 1
            continue
        if e.confidence is not None and e.confidence < 0.5:
            # USL-2 AUTHOR_REVIEW_OVERRIDE
            _ar = (e.payload or {}).get("_author_review") or {}
            if not _ar.get("reviewed"):
                skipped_low_confidence += 1
                print(f"  SKIPPED (no _author_review): {e.entry_id[:12]} conf={e.confidence}")
                continue
            else:
                print(f"  WOULD CONFIRM (_author_review): {e.entry_id[:12]} conf={e.confidence}")
                print(f"    payload keys: {list(e.payload.keys())}")
                print(f"    _author_review: {_ar}")
                confirmed += 1
        else:
            confirmed += 1
    elif e.provenance in (EntryProvenance.AUTHOR_CONFIRMED, EntryProvenance.AUTHOR_AUTHORED):
        skipped_already_confirmed += 1

print(f"\nResult: confirmed={confirmed}, skipped_low={skipped_low_confidence}, "
      f"skipped_open_q={skipped_open_questions}, already_confirmed={skipped_already_confirmed}")