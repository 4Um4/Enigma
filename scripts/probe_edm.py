import logging, os, sys, copy
logging.disable(logging.WARNING)
sys.path.insert(0, ".")

from app.services.tick_orchestrator import TickOrchestrator
_orig_phase5 = TickOrchestrator._phase_5_decision

def _patched_phase5(self, ctx):
    _all = ctx.all_npcs_raw or []
    from app.services.npc.npc_loader import load_profile_from_legacy_json
    
    for n in _all:
        _nid = n.get("npc_id") or n.get("id") or "UNKNOWN"
        if _nid == "thief_shadow":
            _td = copy.deepcopy(dict(n))
            _pl0 = load_profile_from_legacy_json(_td)
            print(f"[THIEF] archetype={getattr(_pl0, 'archetype', 'MISSING')}")
            print(f"[THIEF] drives_base={getattr(_pl0, 'drives_base', 'MISSING')}")
    
    # Проверить effective_drives_map после assemble_preloaded_data
    # assemble_preloaded_data вызывается ВНУТРИ _orig_phase5
    _result = _orig_phase5(self, ctx)
    
    # После phase5 — effective_drives_map должен быть построен
    _edm = getattr(ctx, "effective_drives_map", None) or {}
    print(f"[EDM] keys: {list(_edm.keys())}")
    print(f"[EDM] thief_shadow in map: {'thief_shadow' in _edm}")
    if "thief_shadow" in _edm:
        _ed = _edm["thief_shadow"]
        print(f"[EDM] thief_shadow effective_drives: {_ed}")
    
    return _result

TickOrchestrator._phase_5_decision = _patched_phase5

from tests.gameplay.harness import TavernGameplayHarness
h = TavernGameplayHarness(seed=42, location="tavern")
h.new_game()
h.advance_ticks(1)
h.dispose()
