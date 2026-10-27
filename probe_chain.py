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
_h.advance_ticks(2)

# Seed belief как в тесте
from app.domain.epistemology import EpistemicRecord, Predicate, Proposition
_store = _h.game_loop._tick_orch._epistemic_store
_prop = Proposition(subject_id="thief_shadow", predicate=Predicate.STOLE,
                    object_id="unknown", polarity=True)
_store.upsert(EpistemicRecord(
    agent_id="guard_borko", proposition=_prop, confidence=0.7,
    source_id="direct_observation",
    source_claim_id="fixture-guard_borko-thief_shadow-stole",
    first_observed_tick=0, last_updated_tick=0,
))

_h.advance_ticks(3)

# 1. Все beliefs guard_borko (полные)
print("=== guard_borko EpistemicRecords (full) ===")
for r in _store.to_dict():
    if r.get("agent_id") == "guard_borko":
        _p = r.get("proposition", {})
        print(f"  prop={_p.get('predicate')} subj={_p.get('subject_id')} "
              f"obj={_p.get('object_id')} conf={r.get('confidence')} "
              f"source={r.get('source_id')}")

# 2. EpistemicContextResolver — что возвращает?
from app.services.npc.epistemic_context_resolver import EpistemicContextResolver
_resolver = _h.game_loop._tick_orch._epistemic_resolver if hasattr(_h.game_loop._tick_orch, "_epistemic_resolver") else EpistemicContextResolver(_store)
_ctx = _resolver.resolve("guard_borko")
print("\n=== EpistemicContext for guard_borko ===")
print(f"  perceived_threats={_ctx.perceived_threats}")
print(f"  trigger_proposition={_ctx.trigger_proposition}")
print(f"  max_confidence={_ctx.max_confidence}")

# 3. pending_tasks — есть ли report-задача?
_scene = _h.get_scene_fresh() or {}
_pending = _scene.get("pending_tasks", []) or []
print(f"\n=== pending_tasks ({len(_pending)} total) ===")
for t in _pending:
    _pl = t.get("payload", {}) if isinstance(t, dict) else {}
    print(f"  task_id={t.get('task_id')} owner={t.get('owner_id')} "
          f"kind={t.get('kind')} intent_type={_pl.get('intent_type')} "
          f"has_proposition={bool(_pl.get('proposition'))} target_id={_pl.get('target_id')}")

# 4. npc_intents — какой intent у guard_borko
_intents = _scene.get("npc_intents", {}) or {}
print(f"\n=== npc_intents guard_borko ===")
print(f"  {_intents.get('guard_borko')}")

_h.dispose()
