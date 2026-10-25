import logging, os, sys
logging.disable(logging.CRITICAL)
sys.path.insert(0, ".")

# Monkey-patch TickOrchestrator._phase_1_input_merge для перехвата ctx
from app.services.tick_orchestrator import TickOrchestrator
_orig = TickOrchestrator._phase_1_input_merge

def _patched(self, ctx):
    _npcs = ctx.all_npcs_raw or []
    _ids = [(n.get("npc_id") or n.get("id"), n.get("location_id"), n.get("location")) for n in _npcs]
    print(f"[PROBE] _phase_1_input_merge: count={len(_npcs)} ids={_ids}")
    return _orig(self, ctx)

TickOrchestrator._phase_1_input_merge = _patched

from tests.gameplay.harness import TavernGameplayHarness
h = TavernGameplayHarness(seed=42, location="tavern")
h.new_game()
h.advance_ticks(1)
h.dispose()
