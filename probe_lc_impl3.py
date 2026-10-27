import sys, types, json
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

# Monkey-patch: перехват build_tick_state и записать составы до/после
import app.services.pipeline_runner as pr_mod
_orig_bts = pr_mod.build_tick_state
SPY_TRACES = []

def _spy_bts(ctx, alive_npcs, **kw):
    _ctx_ids = set()
    _ctx_all = getattr(ctx, "all_npcs_raw", None) or []
    for n in _ctx_all:
        if isinstance(n, dict):
            _ctx_ids.add(n.get("npc_id") or n.get("id") or "?")
    _alive_ids = set()
    for n in (alive_npcs or []):
        if isinstance(n, dict):
            _alive_ids.add(n.get("npc_id") or n.get("id") or "?")
    _ts = _orig_bts(ctx, alive_npcs, **kw)
    _ts_ids = set()
    for n in (_ts.all_npcs_raw or []):
        if isinstance(n, dict):
            _ts_ids.add(n.get("npc_id") or n.get("id") or "?")
    SPY_TRACES.append({
        "tick": ctx.tick_number,
        "ctx_all_npcs_raw": sorted(_ctx_ids),
        "alive_npcs (input)": sorted(_alive_ids),
        "TickState.all_npcs_raw": sorted(_ts_ids),
        "ctx_all_count": len(_ctx_ids),
        "alive_count": len(_alive_ids),
        "ts_count": len(_ts_ids),
    })
    return _ts

pr_mod.build_tick_state = _spy_bts
# Также patch импорт в tick_orchestrator, если он импортировал функцию ранее
import app.services.tick_orchestrator as to_mod
if hasattr(to_mod, "build_tick_state"):
    to_mod.build_tick_state = _spy_bts

# Прогон 3 тиков для верификации
_h.advance_ticks(3)

print(f"\n=== LC-IMPL-3 Шаг 2: traces ({len(SPY_TRACES)} тиков) ===")
for t in SPY_TRACES:
    print(f"\n--- tick={t['tick']} ---")
    print(f"  ctx.all_npcs_raw ({t['ctx_all_count']}): {t['ctx_all_npcs_raw']}")
    print(f"  alive_npcs input ({t['alive_count']}): {t['alive_npcs (input)']}")
    print(f"  TickState.all_npcs_raw ({t['ts_count']}): {t['TickState.all_npcs_raw']}")
    _ts = set(t['TickState.all_npcs_raw'])
    _ctx = set(t['ctx_all_npcs_raw'])
    _alive = set(t['alive_npcs (input)'])
    _lost_alive = _alive - _ts
    _lost_ctx = _ctx - _ts
    if _lost_alive:
        print(f"  ❌ LOST between alive_npcs → TickState.all_npcs_raw: {sorted(_lost_alive)}")
    if _lost_ctx:
        print(f"  ⚠️  in ctx.all_npcs_raw but not in TickState: {sorted(_lost_ctx)}")
    if 'thief_shadow' in _ctx or 'thief_shadow' in _alive:
        print(f"  ✅ thief_shadow tracked")
    else:
        print(f"  ❌ thief_shadow NOT in any list")

_h.dispose()
