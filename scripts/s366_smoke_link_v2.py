"""S366 smoke v2: link() на maid_lusya — через _get_store singleton."""
import sys
sys.path.insert(0, "backend")
from app.api.routes_chronicle import _get_store
from app.services.chronicle.causal_linker import CausalLinker

store = _get_store()
doc = store.load_canonical("maid_lusya")
if doc is None:
    print("maid_lusya not found")
    sys.exit(1)

linker = CausalLinker()
result = linker.link(doc)
print(f"entries_total: {result.stats['entries_total']}")
print(f"entries_with_causes: {result.stats['entries_with_causes']}")
print(f"candidates_new: {result.stats['candidates_new']}")
print(f"candidates_existing: {result.stats['candidates_existing']}")
print(f"validation_errors: {result.stats['validation_errors_count']}")
print(f"validation_warnings: {result.stats['validation_warnings_count']}")
for c in result.new_candidates[:3]:
    print(f"  [{c.basis.value}] {c.candidate_id}")
    print(f"    rationale: {c.rationale[:160]}...")
