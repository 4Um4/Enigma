import logging, os, sys
logging.disable(logging.CRITICAL)
sys.path.insert(0, ".")
from tests.gameplay.harness import TavernGameplayHarness
h = TavernGameplayHarness(seed=42, location="tavern")
h.new_game()

# _npc_runtime_locations до первого тика
_to = h.game_loop._tick_orch
_rtl = getattr(_to, "_npc_runtime_locations", {})
print(f"_npc_runtime_locations before tick: {dict(_rtl)}")

# position поле каждого NPC из _load_npcs_with_runtime
_all = h.game_loop._load_npcs_with_runtime(h.campaign_id) or []
for n in _all:
    _nid = n.get("npc_id") or n.get("id") or "UNKNOWN"
    _pos = n.get("position", "MISSING")
    _loc = n.get("location_id", "MISSING")
    print(f"{_nid}: position={_pos!r} location_id={_loc}")

# Проверить npc_positions во ВСЕХ сценах (не только tavern)
from app.services.spatial.spatial_registry import SpatialRegistry
_reg = SpatialRegistry.get_or_load(h.campaign_id)
_all_locs = _reg.get_all_location_ids() if _reg else []
print(f"all locations: {_all_locs}")

for _loc in _all_locs:
    _scene = h.game_loop.scene_manager.get_scene_state(h.campaign_id, _loc)
    if _scene:
        _npcs = _scene.get("npc_positions", {})
        _ids = list(_npcs.keys())
        if "thief_shadow" in _ids:
            _ts = _npcs["thief_shadow"]
            _ts_pos = _ts.get("position", "MISSING") if isinstance(_ts, dict) else "NOT_DICT"
            print(f"thief_shadow in scene {_loc}: position={_ts_pos!r}")

# После 1 тика — проверить _npc_runtime_locations снова
h.advance_ticks(1)
_rtl_after = getattr(_to, "_npc_runtime_locations", {})
print(f"_npc_runtime_locations after 1 tick: {dict(_rtl_after)}")

h.dispose()
