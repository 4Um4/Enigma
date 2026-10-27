import sys, types
sys.path.insert(0, "backend")
import logging
logging.disable(logging.WARNING)
from tests.gameplay.harness import TavernGameplayHarness
from app.domain.execution import TaskKind
from app.domain.control_source import ControlSource, resolve_control_source

class _SyncPool:
    def submit(self, fn, *a, **k):
        fn(*a, **k); return types.SimpleNamespace(result=lambda: None)
    def shutdown(self, wait=True): pass

_h = TavernGameplayHarness(seed=42, location="tavern")
_h.new_game()
_sched = _h.game_loop._get_task_scheduler()
_sched._executors[TaskKind.DIALOGUE]._router = None
_sched._executor_pool = _SyncPool()

# Monkey-patch build_tick_state для покадровой фиксации
import app.services.pipeline_runner as pr_mod
import app.services.tick_orchestrator as to_mod

_orig_bts = pr_mod.build_tick_state
SPY_FRAMES = []

def _spy_bts(ctx, alive_npcs, **kw):
    _ctx_all = getattr(ctx, "all_npcs_raw", None) or []
    _ctx_ids = [(n.get("npc_id") or n.get("id") or "?") for n in _ctx_all if isinstance(n, dict)]
    _alive_ids = [(n.get("npc_id") or n.get("id") or "?") for n in (alive_npcs or []) if isinstance(n, dict)]
    _scene_loc = ctx.scene_state.get("location_id", "") if isinstance(ctx.scene_state, dict) else ""
    _ts = _orig_bts(ctx, alive_npcs, **kw)
    _ts_ids = [(n.get("npc_id") or n.get("id") or "?") for n in (_ts.all_npcs_raw or []) if isinstance(n, dict)]
    
    # Thief_shadow-specific snapshot
    _ts_in_ctx = "thief_shadow" in _ctx_ids
    _ts_in_alive = "thief_shadow" in _alive_ids
    _ts_in_TickState = "thief_shadow" in _ts_ids
    
    # Найдём thief_shadow в ctx.all_npcs_raw для inspection
    _ts_record = None
    for n in _ctx_all:
        if isinstance(n, dict) and (n.get("npc_id") or n.get("id")) == "thief_shadow":
            _ts_record = n
            break
    
    _ts_loc = ""
    _ts_life = ""
    _ts_control = ""
    if _ts_record:
        _ts_loc = _ts_record.get("location_id", _ts_record.get("location", ""))
        _ts_life = _ts_record.get("body_state", {}).get("life_status", "")
        _ts_id = _ts_record.get("npc_id") or _ts_record.get("id") or ""
        try:
            _cs = resolve_control_source(_ts_id)
            _ts_control = _cs.value if hasattr(_cs, "value") else str(_cs)
        except Exception:
            _ts_control = "?"
    
    SPY_FRAMES.append({
        "tick": ctx.tick_number,
        "scene_loc": _scene_loc,
        "ctx_count": len(_ctx_ids),
        "alive_count": len(_alive_ids),
        "ts_count": len(_ts_ids),
        "ts_in_ctx": _ts_in_ctx,
        "ts_in_alive": _ts_in_alive,
        "ts_in_TickState": _ts_in_TickState,
        "ts_loc": _ts_loc,
        "ts_life": _ts_life,
        "ts_control": _ts_control,
    })
    return _ts

pr_mod.build_tick_state = _spy_bts
if hasattr(to_mod, "build_tick_state"):
    to_mod.build_tick_state = _spy_bts

# Прогон 12 тиков
_h.advance_ticks(12)

# Покадровый отчёт
print("\n=== LC-IMPL-3 D3: thief_shadow frame-by-frame ===")
print(f"{'tick':<5}{'scene_loc':<12}{'ts_loc':<18}{'ts_life':<12}{'ts_control':<14}{'ctx':<5}{'alive':<7}{'TickSt':<7}{'ts_in_ctx':<10}{'ts_alive':<10}{'ts_TS':<8}")
print("-" * 110)
for f in SPY_FRAMES:
    print(f"{f['tick']:<5}{f['scene_loc']:<12}{f['ts_loc']:<18}{f['ts_life']:<12}{f['ts_control']:<14}{f['ctx_count']:<5}{f['alive_count']:<7}{f['ts_count']:<7}{str(f['ts_in_ctx']):<10}{str(f['ts_in_alive']):<10}{str(f['ts_in_TickState']):<8}")

# Анализ
print("\n=== ANALYSIS ===")
_lost_ticks = [f for f in SPY_FRAMES if not f["ts_in_alive"]]
print(f"Ticks where thief_shadow LOST from _alive_npcs: {len(_lost_ticks)}")
for f in _lost_ticks:
    print(f"  tick={f['tick']}: ts_loc={f['ts_loc']}, scene_loc={f['scene_loc']}, "
          f"ts_life={f['ts_life']}, ts_control={f['ts_control']}")

# Дополнительно: прочие NPC positions и их locations на каждом тике
print("\n=== NPC positions per tick (from scene_state) ===")
# Перечитаем сцену через get_scene_fresh в конце
_final_scene = _h.get_scene_fresh() or {}
_np_positions = _final_scene.get("npc_positions", {}) or {}
print(f"Final scene location_id: {_final_scene.get('location_id', '?')}")
for nid, pos in _np_positions.items():
    if isinstance(pos, dict):
        print(f"  {nid}: loc={pos.get('location_id')} pos={pos.get('position')}")

_h.dispose()
