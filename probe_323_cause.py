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

# Monkey-patch: перехват всех SceneChange для thief_shadow + state evolution
SPY_STATE_FRAMES = []
import app.services.scene_state_manager as ssm_mod

_orig_apply = ssm_mod.SceneStateManager.apply_changes
def _spy_apply(self, scene_state, changes, *a, **kw):
    _ts_before = {}
    _np = scene_state.get("npc_positions", {}) if isinstance(scene_state, dict) else {}
    _ts_entry = _np.get("thief_shadow", {})
    if isinstance(_ts_entry, dict):
        _ts_before = {
            "location_id": _ts_entry.get("location_id"),
            "position": _ts_entry.get("position"),
            "local_position": _ts_entry.get("local_position"),
        }
    _active = scene_state.get("active_traversals", {}) if isinstance(scene_state, dict) else {}
    _ts_in_active = "thief_shadow" in _active
    
    _changes_for_ts = []
    for ch in (changes or []):
        _tgt = getattr(ch, "target", None)
        if _tgt == "thief_shadow":
            _changes_for_ts.append({
                "field": getattr(ch, "field", None),
                "cause": getattr(ch, "cause", None),
                "value": str(getattr(ch, "value", None))[:60],
                "traversal_proposal": getattr(ch, "traversal_proposal", "MISSING"),
            })
    
    _result = _orig_apply(self, scene_state, changes, *a, **kw)
    
    # State after
    _np_after = scene_state.get("npc_positions", {}) if isinstance(scene_state, dict) else {}
    _ts_after_entry = _np_after.get("thief_shadow", {})
    _ts_after = {}
    if isinstance(_ts_after_entry, dict):
        _ts_after = {
            "location_id": _ts_after_entry.get("location_id"),
            "position": _ts_after_entry.get("position"),
            "local_position": _ts_after_entry.get("local_position"),
        }
    _active_after = scene_state.get("active_traversals", {}) if isinstance(scene_state, dict) else {}
    _ts_in_active_after = "thief_shadow" in _active_after
    
    SPY_STATE_FRAMES.append({
        "tick": scene_state.get("tick", "?") if isinstance(scene_state, dict) else "?",
        "ts_before": _ts_before,
        "ts_in_active_before": _ts_in_active,
        "changes": _changes_for_ts,
        "ts_after": _ts_after,
        "ts_in_active_after": _ts_in_active_after,
    })
    return _result

ssm_mod.SceneStateManager.apply_changes = _spy_apply

# Прогон 8 тиков
_h.advance_ticks(8)

print(f"\n=== ADR-O-323 FIX-01: state evolution trace ({len(SPY_STATE_FRAMES)} frames) ===")
for f in SPY_STATE_FRAMES:
    if not f["changes"]:
        continue
    print(f"\n--- tick={f['tick']} ---")
    print(f"  BEFORE: thief_shadow={f['ts_before']}, in_active_traversals={f['ts_in_active_before']}")
    print(f"  CHANGES for thief_shadow:")
    for c in f["changes"]:
        print(f"    field={c['field']} cause={c['cause']} value={c['value'][:40]} traversal_proposal={c['traversal_proposal']}")
    print(f"  AFTER:  thief_shadow={f['ts_after']}, in_active_traversals={f['ts_in_active_after']}")

# Дополнительно: scene_state[npc_positions][thief_shadow] в конце
_scene = _h.get_scene_fresh() or {}
_np = _scene.get("npc_positions", {}) or {}
print(f"\n=== FINAL npc_positions[thief_shadow] ===")
print(f"  {_np.get('thief_shadow', 'MISSING')}")

# Где thief_shadow фигурирует (check ctx.all_npcs_raw for current scene)
print(f"\n=== scene_state.location_id: {_scene.get('location_id')}")

_h.dispose()
