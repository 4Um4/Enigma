import sys
sys.path.insert(0, '.')
from app.api.routes_chronicle import _get_store
from app.services.chronicle.chronicle_store import validate_document

store = _get_store()
print(f"canonical_dir: {store._canonical_dir}")
print(f"drafts_root: {store._drafts_root}")

doc = store.load_draft("Open_road", "blacksmith_orm")
print(f"load_draft result: {type(doc).__name__ if doc else 'None'}")
if doc is None:
    print("doc is None — draft not found")
    drafts_dir = store._drafts_root / "Open_road" / "chronicle_drafts"
    print(f"expected dir: {drafts_dir}")
    print(f"dir exists: {drafts_dir.exists()}")
    if drafts_dir.exists():
        files = list(drafts_dir.glob("*.json"))
        print(f"files: {[f.name for f in files]}")
    sys.exit(1)

print(f"entries: {len(doc.entries)}")

# Validate
try:
    validate_document(doc, require_canonical_clean=False)
    print("VALIDATE: OK")
except ValueError as e:
    print(f"VALIDATE FAILED: {e}")
    sys.exit(1)

# Check the fixed entry
target_id = "aaabe6ecd6b33576641e21b62d5430f8"
for e in doc.entries:
    if e.entry_id == target_id:
        print(f"Fixed entry object_id: {e.object_id}")
        break