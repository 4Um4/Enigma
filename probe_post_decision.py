import sys
sys.path.insert(0, "backend")
import logging
logging.disable(logging.WARNING)
from tests.gameplay.harness import TavernGameplayHarness
from app.domain.execution import TaskKind
import types

class _SyncPool:
    def submit(self, fn, *a, **k):
        fn(*a, **k); return types.SimpleNamespace(result=lambda: None)
    def shutdown(self, wait=True): pass

_h = TavernGameplayHarness(seed=42, location="tavern")
_h.new_game()
_sched = _h.game_loop._get_task_scheduler()
_sched._executors[TaskKind.DIALOGUE]._router = None
_sched._executor_pool = _SyncPool()

# Трассировка CommunicationIntent construction
import app.services.phases.post_decision as pd_mod
_orig_build = None
SPY_INTENT = []
SPY_TASK = []

# Hook на TickState чтобы видеть scene_state mutations
import app.services.tick_orchestrator as to_mod
_orig_execute = to_mod.TickOrchestrator.execute if hasattr(to_mod.TickOrchestrator, "execute") else None

# Трассируем pending_tasks на каждом тике
def _trace_pending():
    _sc = _h.get_scene_fresh() or {}
    _pt = _sc.get("pending_tasks", []) or []
    print(f"  pending_tasks count={len(_pt)}")
    for t in _pt:
        if isinstance(t, dict):
            _pl = t.get("payload", {})
            if t.get("owner_id") == "guard_borko":
                print(f"    [GB] task_id={t.get('task_id')} intent={_pl.get('intent_type')} "
                      f"has_prop={bool(_pl.get('proposition'))}")

_h.advance_ticks(2)
# Seed belief
from app.domain.epistemology import EpistemicRecord, Predicate, Proposition
_store = _h.game_loop._tick_orch._epistemic_store
_store.upsert(EpistemicRecord(
    agent_id="guard_borko",
    proposition=Proposition(subject_id="thief_shadow",
                            predicate=Predicate.STOLE,
                            object_id="unknown", polarity=True),
    confidence=0.7,
    source_id="direct_observation",
    source_claim_id="fixture-gb-ts-stole",
    first_observed_tick=0, last_updated_tick=0,
))
print(f"After 2 ticks + seed:")
_trace_pending()

# Tick-by-tick trace
for _i in range(5):
    _r = _h.game_loop.idle_tick("Open_road")
    _sc = _h.get_scene_fresh() or {}
    _pt = _sc.get("pending_tasks", []) or []
    _gi = (_sc.get("npc_intents", {}) or {}).get("guard_borko")
    _gb_pos = (_sc.get("npc_positions", {}) or {}).get("guard_borko", {}).get("position")
    print(f"\nTick+{_i+3}: guard_borko intent={_gi} pos={_gb_pos} pending={len(_pt)}")
    _trace_pending()
    # Проверим final_state TickResult
    _fs = _r.get("final_state") if isinstance(_r, dict) else getattr(_r, "final_state", None)
    if _fs:
        _fs_pt = _fs.get("pending_tasks", []) or []
        if _fs_pt:
            print(f"  [FS] final_state.pending_tasks count={len(_fs_pt)}")
            for t in _fs_pt:
                if isinstance(t, dict) and t.get("owner_id") == "guard_borko":
                    _pl = t.get("payload", {})
                    print(f"    [FS-GB] task_id={t.get('task_id')} intent={_pl.get('intent_type')} has_prop={bool(_pl.get('proposition'))}")

# Финальное состояние
print("\n=== FINAL guard_borko EpistemicRecords ===")
for r in _store.to_dict():
    if r.get("agent_id") == "guard_borko":
        _p = r.get("proposition", {})
        print(f"  prop={_p.get('predicate')} subj={_p.get('subject_id')} "
              f"conf={r.get('confidence')} source={r.get('source_id')}")

_h.dispose()
