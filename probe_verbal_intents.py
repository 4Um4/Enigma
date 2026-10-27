import sys
sys.path.insert(0, "backend")
import logging
logging.disable(logging.WARNING)
from tests.gameplay.harness import TavernGameplayHarness
from app.domain.execution import TaskKind
import types
from app.services.npc.decision_hub import DecisionHub

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

# 1. _VERBAL_INTENTS — что в множестве?
_dh = DecisionHub()
_vi = getattr(_dh, "_VERBAL_INTENTS", None)
print(f"=== _VERBAL_INTENTS ===")
print(f"  {_vi}")
print(f"  'report' in set: {'report' in _vi if _vi else 'set missing'}")

# 2. Intent enum — есть ли REPORT?
from app.domain.intent import Intent
print(f"\n=== Intent enum values ===")
print(f"  {[i.value for i in Intent]}")

# 3. Seed belief
from app.domain.epistemology import EpistemicRecord, Predicate, Proposition
_store = _h.game_loop._tick_orch._epistemic_store
_store.upsert(EpistemicRecord(
    agent_id="guard_borko",
    proposition=Proposition(subject_id="thief_shadow",
                            predicate=Predicate.STOLE,
                            object_id="unknown", polarity=True),
    confidence=0.7, source_id="direct_observation",
    source_claim_id="fixture-gb-ts-stole",
    first_observed_tick=0, last_updated_tick=0,
))

# 4. Снапшот npc_states и relationship_store, чтобы проверить _build_communication вручную
_h.advance_ticks(3)
_scene = _h.get_scene_fresh() or {}
_ns = (_scene.get("npc_states", {}) or {}).get("guard_borko", {})
_intents = _scene.get("npc_intents", {}) or {}
_gb_intent = _intents.get("guard_borko")
print(f"\n=== guard_borko intent after tick+3 ===")
print(f"  {_gb_intent}")
print(f"\n=== guard_borko npc_state ===")
print(f"  perceptual_kernel={_ns.get('perceptual_kernel', {})}")
print(f"  drives={_ns.get('drives', {})}")

# 5. Hook на _build_communication — вызывается ли?
import app.services.npc.decision_hub as dh_mod
_orig = dh_mod.DecisionHub._build_communication
SPY_BUILT = []
def _hook(self, *a, **kw):
    _result = _orig(self, *a, **kw)
    SPY_BUILT.append({
        "npc_id": a[1] if len(a) > 1 else kw.get("npc_id"),
        "intent_value": a[2] if len(a) > 2 else kw.get("intent_value"),
        "returned": _result is not None,
        "proposition": getattr(_result, "proposition", None) if _result else None,
        "intent_type": getattr(_result, "intent_type", None) if _result else None,
    })
    return _result
dh_mod.DecisionHub._build_communication = _hook

# 6. Hook на post_decision.py — поиск where QueuedTask создаётся
import app.services.phases.post_decision as pd_mod
print(f"\n=== post_decision module: functions ===")
print(f"  {[n for n in dir(pd_mod) if not n.startswith('_')]}")

_h.advance_ticks(2)
print(f"\n=== _build_communication calls (last 5) ===")
for s in SPY_BUILT[-5:]:
    print(f"  npc={s['npc_id']} intent={s['intent_value']} returned={s['returned']} "
          f"prop={s['proposition']} intent_type={s['intent_type']}")

# 7. final pending_tasks
_pending = (_h.get_scene_fresh() or {}).get("pending_tasks", [])
print(f"\n=== final pending_tasks: {len(_pending)} ===")
for t in _pending:
    if isinstance(t, dict):
        _pl = t.get("payload", {})
        print(f"  owner={t.get('owner_id')} intent={_pl.get('intent_type')} "
              f"has_prop={bool(_pl.get('proposition'))}")

_h.dispose()
