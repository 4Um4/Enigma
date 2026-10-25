import logging, os, sys
logging.disable(logging.CRITICAL)
sys.path.insert(0, ".")
from tests.gameplay.harness import TavernGameplayHarness
from app.domain.control_source import ControlSource, resolve_control_source
h = TavernGameplayHarness(seed=42, location="tavern")
h.new_game()
h.advance_ticks(2)
_all = h.game_loop._load_npcs_with_runtime(h.campaign_id) or []
for n in _all:
    _nid = n.get("npc_id") or n.get("id") or "UNKNOWN"
    _life = n.get("body_state", {}).get("life_status", "MISSING") if isinstance(n.get("body_state"), dict) else "NO_BODY"
    _loc = n.get("location_id", "MISSING")
    _cs = resolve_control_source(_nid)
    print(f"{_nid}: life={_life} loc={_loc} control={_cs}")
h.dispose()
