import sys, json
sys.path.insert(0, '.')
from app.api.routes_chronicle import _get_store

store = _get_store()
doc = store.load_draft("Open_road", "guard_borko")
if doc is None:
    print("doc is None")
    sys.exit(1)

# Найти entry 6f087a311a7d
for e in doc.entries:
    if e.entry_id.startswith("6f087a311a7d"):
        print(f"entry_id: {e.entry_id}")
        print(f"provenance: {e.provenance}")
        print(f"confidence: {e.confidence}")
        print(f"payload type: {type(e.payload)}")
        print(f"payload keys: {list(e.payload.keys())}")
        ar = e.payload.get("_author_review")
        print(f"_author_review: {ar}")
        if ar:
            print(f"reviewed: {ar.get('reviewed')}")
        break