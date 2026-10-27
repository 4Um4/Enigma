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

# === Включим ERROR-level логирование для scene_state_manager ===
logging.getLogger("app.services.scene_state_manager").setLevel(logging.ERROR)

# Monkey-patch: перехват SceneChange применений для thief_shadow
SPY_CHANGES = []
import app.services.scene_state_manager as ssm_mod
if hasattr(ssm_mod, "SceneStateManager"):
    _orig_apply = ssm_mod.SceneStateManager.apply_changes if hasattr(ssm_mod.SceneStateManager, "apply_changes") else None
    # Также MovementEngine boundary_arrival
import app.services.spatial.movement_engine as me_mod
_orig_move = me_mod.MovementEngine.update if hasattr(me_mod.MovementEngine, "update") else None

# Проще: перехватим SceneChange через SSM apply_changes
import app.services.scene_change as sc_mod
_orig_ssm_apply_changes = None
if hasattr(ssm_mod.SceneStateManager, "apply_changes"):
    _orig_ssm_apply_changes = ssm_mod.SceneStateManager.apply_changes
    def _spy_apply(self, scene_state, changes, *a, **kw):
        for ch in (changes or []):
            _tgt = getattr(ch, "target", None) or (ch.get("target") if isinstance(ch, dict) else None)
            if _tgt == "thief_shadow":
                _fld = getattr(ch, "field", None) or (ch.get("field") if isinstance(ch, dict) else None)
                _cause = getattr(ch, "cause", None) or (ch.get("cause") if isinstance(ch, dict) else None)
                _val = getattr(ch, "value", None) or (ch.get("value") if isinstance(ch, dict) else None)
                _ct = getattr(ch, "change_type", None) or (ch.get("change_type") if isinstance(ch, dict) else None)
                SPY_CHANGES.append({
                    "tick": getattr(scene_state, "tick", "?"),
                    "field": _fld,
                    "cause": _cause,
                    "value": _val,
                    "change_type": str(_ct),
                })
        return _orig_ssm_apply_changes(self, scene_state, changes, *a, **kw)
    ssm_mod.SceneStateManager.apply_changes = _spy_apply

# Прогон 8 тиков (thief_shadow теряется на тике 7)
_h.advance_ticks(8)

print("\n=== ADR-O-323 Этап 2: thief_shadow SceneChange trace ===")
print(f"Total changes for thief_shadow: {len(SPY_CHANGES)}")
print(f"\n{'tick':<6}{'field':<18}{'cause':<45}{'change_type':<25}{'value'}")
print("-" * 130)
for c in SPY_CHANGES:
    _v = str(c["value"])[:50] if c["value"] else "None"
    print(f"{str(c['tick']):<6}{str(c['field']):<18}{str(c['cause']):<45}{str(c['change_type']):<25}{_v}")

# Финальное состояние thief_shadow
_scene = _h.get_scene_fresh() or {}
_np = _scene.get("npc_positions", {}) or {}
_ts = _np.get("thief_shadow", {})
print(f"\n=== thief_shadow FINAL state ===")
print(f"  location_id: {_ts.get('location_id')}")
print(f"  position: {_ts.get('position')}")
print(f"  local_position: {_ts.get('local_position')}")

# Состояние в scene_state[location_id]
print(f"\n=== scene_state.location_id: {_scene.get('location_id')}")

# Дополнительно: проверим, есть ли в scene_state активные traversals
_travs = _scene.get("active_traversals", {}) or {}
print(f"\n=== active_traversals в scene_state ===")
for k, v in _travs.items():
    print(f"  {k}: {v}")

_h.dispose()
