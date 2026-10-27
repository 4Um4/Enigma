import sys, types
sys.path.insert(0, "backend")
import logging
logging.disable(logging.WARNING)
from tests.gameplay.harness import TavernGameplayHarness
from app.domain.execution import TaskKind

class _SyncPool:
    def submit(self, fn, *a, **k):
        fn(*a, **k); return types.SimpleNamespace(result=lambda: None)
    def shutdown(self, wait=True): pass

_h = TavernGameplayHarness(seed=42, location="tavern")
_h.new_game()
_sched = _h.game_loop._get_task_scheduler()
_sched._executors[TaskKind.DIALOGUE]._router = None
_sched._executor_pool = _SyncPool()

print("\n=== Tick 0 (after new_game, before any idle_tick) ===")
_scene = _h.get_scene_fresh() or {}
_np = _scene.get("npc_positions", {}) or {}
print(f"scene_state.location_id: {_scene.get('location_id')}")
print(f"npc_positions keys: {list(_np.keys())}")
for nid in ["thief_shadow", "guard_borko", "maid_lusya", "player"]:
    _entry = _np.get(nid, "MISSING")
    print(f"  {nid}: {_entry}")

# Tick 1
_h.advance_ticks(1)
print("\n=== After tick 1 ===")
_scene = _h.get_scene_fresh() or {}
_np = _scene.get("npc_positions", {}) or {}
print(f"npc_positions keys: {list(_np.keys())}")
for nid in ["thief_shadow", "guard_borko", "maid_lusya"]:
    _entry = _np.get(nid, "MISSING")
    print(f"  {nid}: {_entry}")

# Tick 4 (до boundary_arrival на тике 5)
_h.advance_ticks(3)
print("\n=== After tick 4 (pre-boundary) ===")
_scene = _h.get_scene_fresh() or {}
_np = _scene.get("npc_positions", {}) or {}
print(f"npc_positions keys: {list(_np.keys())}")
for nid in ["thief_shadow", "guard_borko", "maid_lusya"]:
    _entry = _np.get(nid, "MISSING")
    print(f"  {nid}: {_entry}")

# Tick 6 (после boundary_arrival на тике 5)
_h.advance_ticks(2)
print("\n=== After tick 6 (post-boundary) ===")
_scene = _h.get_scene_fresh() or {}
_np = _scene.get("npc_positions", {}) or {}
print(f"npc_positions keys: {list(_np.keys())}")
for nid in ["thief_shadow", "guard_borko", "maid_lusya"]:
    _entry = _np.get(nid, "MISSING")
    print(f"  {nid}: {_entry}")

# Также проверим ctx.all_npcs_raw (через LifeEngine) на каждом шаге
print("\n=== ctx.all_npcs_raw thief_shadow state per tick ===")
for tick_idx in range(8):
    _le_states = _h.game_loop._get_life_engine().get_npc_states("Open_road")
    _ts = next((s for s in _le_states if s.get("npc_id") == "thief_shadow"), None)
    if _ts:
        print(f"  tick~{tick_idx}: loc={_ts.get('location_id')} pos={_ts.get('position')}")
    if tick_idx < 7:
        _h.advance_ticks(1)

_h.dispose()
