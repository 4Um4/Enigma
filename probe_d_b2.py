import sys, types
sys.path.insert(0, "backend")
import logging
logging.disable(logging.WARNING)

from tests.gameplay.harness import TavernGameplayHarness
from app.domain.execution import TaskKind
from app.domain import epistemic_dispositions as _ed
from app.domain.epistemology import EpistemicRecord, Predicate, Proposition

# === Wiring как в K2 ===
class _SyncPool:
    def submit(self, fn, *a, **k):
        fn(*a, **k); return types.SimpleNamespace(result=lambda: None)
    def shutdown(self, wait=True): pass

_ed.EPISTEMIC_DISPOSITIONS["guard"] = {
    "report": 0.0, "warn": 0.5, "attack": 0.4,
    "spread_rumor": 0.0, "talk": 0.2, "intimidate": 1.4,
}

# Setup harness + K2 conditions
_h = TavernGameplayHarness(seed=42, location="tavern")
_h.new_game()
_sched = _h.game_loop._get_task_scheduler()
_sched._executors[TaskKind.DIALOGUE]._router = None
_sched._executor_pool = _SyncPool()
_h.advance_ticks(2)

# Seed belief (как в K2)
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

# Прогон для генерации testimony (maid_lusya получит belief)
_h.advance_ticks(8)

# === ЭТАП 1: maid_lusya EpistemicContext + epistemic_modifiers ===
print("=== ЭТАП 1: maid_lusya EpistemicContext ===")
from app.services.npc.epistemic_context_resolver import EpistemicContextResolver
_resolver = EpistemicContextResolver(_store)

# A — без belief (контроль: очистим EpistemicStore для maid_lusya)
_maid_records = [r for r in _store.to_dict() if r.get("agent_id") == "maid_lusya"]
print(f"maid_lusya records BEFORE clear: {len(_maid_records)}")
for r in _maid_records:
    print(f"  prop={r.get('proposition', {}).get('predicate')} subj={r.get('proposition', {}).get('subject_id')}")

# Snapshot A: epistemic_context без beliefs о thief_shadow
_ctx_A = _resolver.resolve("maid_lusya")
_mods_A = EpistemicContextResolver.to_modifiers(_ctx_A, archetype="maid")
print(f"\nA (current, с beliefs):")
print(f"  perceived_threats={_ctx_A.perceived_threats}")
print(f"  trigger_proposition={_ctx_A.trigger_proposition}")
print(f"  max_confidence={_ctx_A.max_confidence}")
print(f"  epistemic_modifiers: {_mods_A}")

# === ЭТАП 2: прямой вызов DecisionHub.compute() с A/B ===
print("\n=== ЭТАП 2: DecisionHub.compute() A/B comparison ===")
from app.services.npc.decision_hub import DecisionHub
_dh = DecisionHub()

# Подготовим одинаковые входы для A (без belief) и B (с belief)
_scene = _h.get_scene_fresh() or {}
_ns = (_scene.get("npc_states", {}) or {}).get("maid_lusya", {})
_drives = _ns.get("drives", {"control": 0.3, "significance": 0.3, "fear": 0.2, "desire": 0.2})
_kernel = _ns.get("perceptual_kernel", {"threat_gradient": 0.0})

# Mock event (need something for compute)
from app.domain.events import EventDTO
_mock_event = EventDTO.create(
    event_type="npc_spoke",
    source="guard_borko",
    payload={"target_id": "maid_lusya", "intent_type": "talk", "text": "..."},
    visibility="public", radius=10.0,
)

# A — без epistemic_modifiers (control)
try:
    _scores_A = _dh.compute(
        npc_id="maid_lusya",
        state=_ns,
        event=_mock_event,
        drives=_drives,
        epistemic_modifiers={},  # ПУСТО — нет влияния belief
        causal_modifiers=None,
    )
    print(f"\nA (no epistemic_modifiers):")
    print(f"  scores: {_scores_A}")
    if _scores_A:
        _winner_A = max(_scores_A.items(), key=lambda x: x[1])
        print(f"  winner: {_winner_A}")
except Exception as e:
    print(f"  A failed: {e}")

# B — с epistemic_modifiers (эксперимент)
try:
    _scores_B = _dh.compute(
        npc_id="maid_lusya",
        state=_ns,
        event=_mock_event,
        drives=_drives,
        epistemic_modifiers=_mods_A,  # С belief modifiers
        causal_modifiers=None,
    )
    print(f"\nB (with epistemic_modifiers={_mods_A}):")
    print(f"  scores: {_scores_B}")
    if _scores_B:
        _winner_B = max(_scores_B.items(), key=lambda x: x[1])
        print(f"  winner: {_winner_B}")
except Exception as e:
    print(f"  B failed: {e}")

# Diff
if _scores_A and _scores_B:
    print(f"\n=== DIFF A vs B ===")
    _all_intents = set(_scores_A.keys()) | set(_scores_B.keys())
    for intent in sorted(_all_intents):
        _a = _scores_A.get(intent, 0.0)
        _b = _scores_B.get(intent, 0.0)
        _delta = _b - _a
        if abs(_delta) > 0.001:
            print(f"  {intent}: A={_a:.4f} → B={_b:.4f} (Δ={_delta:+.4f})")

# === ЭТАП 3: проверка семантики testimony ===
print("\n=== ЭТАП 3: семантика testimony ===")
print("ADR-O-358 L14.3: 'Детерминированный fallback: intent_type → Proposition'")
print("  → ClaimEventSubscriber.on_npc_spoke fallback предусмотрен контрактом")
print()
print("Источник proposition в нашем тесте:")
print("  1. guard_borko.seed belief: {thief_shadow, STOLE, unknown} (test fixture)")
print("  2. EpistemicContextResolver.resolve(guard_borko).trigger_proposition = {thief_shadow, STOLE, unknown}")
print("  3. DecisionHub._build_communication: CommunicationIntent.proposition = trigger_proposition")
print("  4. post_decision: DialogueRequest.proposition = _prop_data")
print("  5. DialogueExecutor.execute: artifact.data['proposition'] = _proposition")
print("  6. DialogueMaterializer.materialize:")
print("     - NPC_SPOKE (БЕЗ proposition в payload, только intent_type)")
print("     - COMMUNICATION_CLAIM (С proposition = trigger_proposition)")
print("  7. ClaimEventSubscriber.on_npc_spoke: payload.proposition есть → return (НЕ использует fallback)")
print("  8. ClaimEventSubscriber.on_claim_event: prop={thief_shadow, STOLE}, source=guard_borko")
print("     → all listeners в радиусе (can_observe)")
print("     → для каждого listener: ClaimEvent(speaker=guard_borko, listener, prop)")
print("     → BeliefRevisionEngine.revise(listener, claim, existing)")

_h.dispose()
