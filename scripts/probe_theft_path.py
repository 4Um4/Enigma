import logging, os, sys
logging.disable(logging.CRITICAL)
os.environ.pop("W3_G3_ENABLED", None)

from tests.gameplay.harness import TavernGameplayHarness
h = TavernGameplayHarness(seed=42, location="tavern")
h.new_game()

_scene = h.get_scene_fresh() or {}
_npcs = _scene.get("npc_positions", {})
_ts = _npcs.get("thief_shadow", {})
_lp = _ts.get("local_position", {}) if isinstance(_ts, dict) else {}
_tx = _lp.get("x", 5.0)
_ty = _lp.get("y", 5.0)
print(f"thief_shadow at ({_tx}, {_ty})")

_ok = h.spawn_world_object("wo_probe_coin", "bowl", (_tx + 0.5, _ty + 0.5))
print(f"spawn wo_probe_coin: {_ok}")

_scene = h.get_scene_fresh() or {}
_objs_before = list((_scene.get("world_objects") or {}).keys())
print(f"world_objects before: {_objs_before}")

_all_causes = set()
_all_events = []
for i in range(30):
    result = h.game_loop.idle_tick(h.campaign_id)
    _evts = result.get("events") or []
    for e in _evts:
        if isinstance(e, dict):
            _all_causes.add(e.get("cause"))
            _all_events.append(e)

print(f"events count: {len(_all_events)}")
print(f"causes: {sorted(_all_causes)}")

_theft_events = [e for e in _all_events if e.get("cause") == "theft"]
print(f"THEFT events: {len(_theft_events)}")
for te in _theft_events[:3]:
    print(f"  THEFT: {te}")

_scene = h.get_scene_fresh() or {}
_objs_after = list((_scene.get("world_objects") or {}).keys())
print(f"world_objects after: {_objs_after}")
_coin_exists = "wo_probe_coin" in _objs_after
print(f"wo_probe_coin still exists: {_coin_exists}")

h.dispose()
