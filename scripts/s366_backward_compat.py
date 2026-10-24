"""S366 — backward compat: старые канон-документы (без npc_beliefs/cause_candidates) загружаются."""
import sys
from pathlib import Path
sys.path.insert(0, "backend")

from app.services.chronicle.chronicle_store import ChronicleStore

store = ChronicleStore()
for npc_id in ("maid_lusya", "blacksmith_orm", "guard_borko"):
    try:
        doc = store.load_canonical(npc_id)
        if doc is None:
            print(f"  {npc_id}: NOT FOUND (skip)")
            continue
        print(f"  {npc_id}: entries={len(doc.entries)}, npc_beliefs={len(doc.npc_beliefs)} (expected 0), cause_candidates={len(doc.cause_candidates)} (expected 0)")
    except Exception as e:
        print(f"  {npc_id}: FAILED: {type(e).__name__}: {e}")
        sys.exit(1)
print("OK backward compat")
