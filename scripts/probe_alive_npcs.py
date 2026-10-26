import logging, os, sys, copy
logging.disable(logging.WARNING)
sys.path.insert(0, ".")

from app.services.tick_orchestrator import TickOrchestrator
from app.domain.control_source import ControlSource, resolve_control_source

_orig_phase5 = TickOrchestrator._phase_5_decision

def _patched_phase5(self, ctx):
    import inspect
    _src = inspect.getsource(_orig_phase5)
    for i, line in enumerate(_src.splitlines()):
        if "_current_loc" in line and "=" in line and "for" not in line:
            print(f"[SRC] L{i}: {line.strip()}")
    
    _source_list = ctx.all_npcs_raw or ctx.npc_states or []
    _current_loc = ctx.scene_state.get("location_id", "") if isinstance(ctx.scene_state, dict) else ""
    print(f"[FILTER] _current_loc: {_current_loc!r}")
    print(f"[FILTER] source_list count: {len(_source_list)}")
    
    for n in _source_list:
        _nid = n.get("npc_id") or n.get("id") or "UNKNOWN"
        _loc_id = n.get("location_id", "")
        _loc_legacy = n.get("location", "")
        _life = n.get("body_state", {}).get("life_status", "MISSING") if isinstance(n.get("body_state"), dict) else "NO_BODY"
        _cs = resolve_control_source(_nid)
        _cond1 = _cs is ControlSource.NPC_DECISION
        _cond2 = (_loc_id == _current_loc or _loc_legacy == _current_loc)
        _cond3 = _life not in ("DEAD", "UNCONSCIOUS", "COMA")
        _pass = _cond1 and _cond2 and _cond3
        print(f"[NPC] {_nid}: cs={_cs.name} loc_id={_loc_id!r} loc={_loc_legacy!r} life={_life} | NPC_DEC={_cond1} loc_match={_cond2} alive={_cond3} => PASS={_pass}")
    
    return _orig_phase5(self, ctx)

TickOrchestrator._phase_5_decision = _patched_phase5

from tests.gameplay.harness import TavernGameplayHarness
h = TavernGameplayHarness(seed=42, location="tavern")
h.new_game()
h.advance_ticks(1)
h.dispose()
