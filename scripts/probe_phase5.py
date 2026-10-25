import logging, os, sys, copy
logging.disable(logging.WARNING)
sys.path.insert(0, ".")

# Monkey-patch TickOrchestrator._phase_5_decision (Фаза 5 — где строится TickState)
from app.services.tick_orchestrator import TickOrchestrator
_orig_phase5 = TickOrchestrator._phase_5_decision

def _patched_phase5(self, ctx):
    _all = ctx.all_npcs_raw or []
    print(f"[PHASE5] all_npcs_raw count: {len(_all)}")
    for n in _all:
        _nid = n.get("npc_id") or n.get("id") or "UNKNOWN"
        _life = n.get("body_state", {}).get("life_status", "MISSING") if isinstance(n.get("body_state"), dict) else "NO_BODY"
        _loc = n.get("location_id", "MISSING")
        print(f"[PHASE5] {_nid}: life={_life} loc={_loc}")
    
    # effective_drives_map строится в assemble_preloaded_data (pipeline_runner)
    # Проверим drives_base через load_profile_from_legacy_json
    from app.services.npc.npc_loader import load_profile_from_legacy_json
    for n in _all:
        _nid = n.get("npc_id") or n.get("id") or "UNKNOWN"
        _td = copy.deepcopy(dict(n))
        try:
            _pl0 = load_profile_from_legacy_json(_td)
            if _pl0:
                _arch = getattr(_pl0, "archetype", "MISSING")
                _db = getattr(_pl0, "drives_base", "MISSING")
                print(f"[PHASE5_PROFILE] {_nid}: archetype={_arch} drives_base={_db}")
            else:
                print(f"[PHASE5_PROFILE] {_nid}: profile_l0=None")
        except Exception as e:
            print(f"[PHASE5_PROFILE] {_nid}: error={e}")
    
    return _orig_phase5(self, ctx)

TickOrchestrator._phase_5_decision = _patched_phase5

from tests.gameplay.harness import TavernGameplayHarness
h = TavernGameplayHarness(seed=42, location="tavern")
h.new_game()
h.advance_ticks(1)
h.dispose()
