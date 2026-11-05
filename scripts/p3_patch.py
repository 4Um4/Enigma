import sys
from pathlib import Path

file = Path("backend/app/services/npc/npc_loader.py")
content = file.read_text(encoding="utf-8")

old = '_restored_beliefs = _beliefs_from_persistence(psyche.get("beliefs"))'
new = '_restored_beliefs = _beliefs_from_persistence(psyche.get("beliefs"))\n    print(f"[P3-DIAG] npc={raw_data.get(\'id\')} beliefs_raw={psyche.get(\'beliefs\')} restored={_restored_beliefs} all={_restored_beliefs.all() if _restored_beliefs else None}")'

if old in content:
    content = content.replace(old, new)
    file.write_text(content, encoding="utf-8")
    print("PATCHED")
else:
    print("ERROR: old not found")
