import logging, os, sys
logging.disable(logging.CRITICAL)
sys.path.insert(0, ".")
from tests.gameplay.harness import TavernGameplayHarness
h = TavernGameplayHarness(seed=42, location="tavern")
h.new_game()
h.advance_ticks(2)
for nid in ["guard_borko", "thief_shadow", "merchant_goran"]:
    _n = h.inspect_npc(nid) or {}
    _arch = _n.get("archetype")
    _db = _n.get("drives_base")
    _ws = _n.get("will_state")
    _ed = _n.get("effective_drives")
    print(f"{nid}: archetype={_arch} drives_base={_db} will_state={_ws} effective_drives={_ed}")
h.dispose()
