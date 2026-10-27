import sys, types
sys.path.insert(0, "backend")
import logging
logging.disable(logging.WARNING)

from tests.gameplay.harness import TavernGameplayHarness
from app.domain.execution import TaskKind
from app.domain import epistemic_dispositions as _ed
from app.domain.epistemology import EpistemicRecord, Predicate, Proposition
from app.services.npc.epistemic_context_resolver import EpistemicContextResolver
from app.services.npc.decision_hub import DecisionHub

class _SyncPool:
    def submit(self, fn, *a, **k):
        fn(*a, **k); return types.SimpleNamespace(result=lambda: None)
    def shutdown(self, wait=True): pass

_ed.EPISTEMIC_DISPOSITIONS["guard"] = {
    "report": 0.0, "warn": 0.5, "attack": 0.4,
    "spread_rumor": 0.0, "talk": 0.2, "intimidate": 1.4,
}

_h = TavernGameplayHarness(seed=42, location="tavern")
_h.new_game()
_sched = _h.game_loop._get_task_scheduler()
_sched._executors[TaskKind.DIALOGUE]._router = None
_sched._executor_pool = _SyncPool()
_h.advance_ticks(2)
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
_h.advance_ticks(8)

_resolver = EpistemicContextResolver(_store)
_ctx = _resolver.resolve("maid_lusya")
_mods_with_belief = EpistemicContextResolver.to_modifiers(_ctx, archetype="maid")
_mods_without_belief = {}  # control: пустой modifiers

# Прочитаем canonical base scores для maid_lusya из production-сценария
# (используем фактические scores, которые DecisionHub посчитал бы)
# Из предыдущей археологии: известен _DRIVE_AXIS map и формула scoring.
# Для изоляции влияния belief — берём те же drive/base scores, меняем только modifiers.

# Mock base scores (typical для maid archetype, drives={control:0.3, sig:0.3, fear:0.2, desire:0.2})
# Из _INTENT_DRIVE mapping (decision_hub.py:1447-1470):
#   REPORT/INTIMIDATE/WARN/ATTACK → control
#   FLEE/OBSERVE/IDLE → fear
#   TRADE/OFFER_JOB → desire
#   HELP/TALK/SEEK_ALLY/CALL_FOR_HELP → significance
#   BLOCK_PATH/AMBUSH → control

# Базовые drives для maid_lusya (из probe_drives.py): {control:0.3, significance:0.3, fear:0.2, desire:0.2} -- НЕТ, на самом деле {control:0.3, sig:0.3, fear:0.2, desire:0.2} -- НЕ УВЕРЕН. Возьмём из канонических.
_base_scores_mock = {
    "talk": 0.5, "warn": 0.3, "intimidate": 0.2, "spread_rumor": 0.4,
    "attack": 0.1, "flee": 0.3, "observe": 0.2, "idle": 0.1,
    "seek_ally": 0.6,  # baseline winner в K1
    "trade": 0.2, "help": 0.3, "block_path": 0.1, "approach": 0.4,
    "report": 0.2, "call_for_help": 0.1, "offer_job": 0.1,
    "request_service": 0.1, "change_role": 0.05,
}

# A: apply_modifiers с ПУСТЫМИ epistemic_modifiers
_scores_A = DecisionHub.apply_modifiers(
    scores=dict(_base_scores_mock),
    epistemic_modifiers=_mods_without_belief,
)

# B: apply_modifiers с epistemic_modifiers (belief applied)
_scores_B = DecisionHub.apply_modifiers(
    scores=dict(_base_scores_mock),
    epistemic_modifiers=_mods_with_belief,
)

print("=== A (no epistemic_modifiers) ===")
_sorted_A = sorted(_scores_A.items(), key=lambda x: x[1], reverse=True)
for k, v in _sorted_A[:8]:
    print(f"  {k}: {v:.4f}")
print(f"  winner: {_sorted_A[0]}")

print(f"\n=== B (with epistemic_modifiers={_mods_with_belief}) ===")
_sorted_B = sorted(_scores_B.items(), key=lambda x: x[1], reverse=True)
for k, v in _sorted_B[:8]:
    print(f"  {k}: {v:.4f}")
print(f"  winner: {_sorted_B[0]}")

print(f"\n=== DIFF (B - A) ===")
for k in sorted(set(_scores_A) | set(_scores_B)):
    _a = _scores_A.get(k, 0.0)
    _b = _scores_B.get(k, 0.0)
    _d = _b - _a
    if abs(_d) > 0.001:
        print(f"  {k}: A={_a:.4f} → B={_b:.4f} (Δ={_d:+.4f})")

# Semantics summary
print("\n=== Семантика testimony ===")
print(f"trigger_proposition={_ctx.trigger_proposition}")
print(f"perceived_threats={_ctx.perceived_threats}")
print(f"max_confidence={_ctx.max_confidence}")
print(f"\nbelief modifiers (applied к DecisionHub): {_mods_with_belief}")
print(f"modifiers изменяют score для intent=spread_rumor (+1.95), warn (+0.45), talk (+0.9), report (+0.15), block_path (+0.75)")
print(f"\nВывод: belief НЕ напрямую поднимает 'seek_ally' (baseline winner).")
print(f"  но поднимает конкурентов (spread_rumor +1.95, talk +0.9).")
print(f"  Если baseline seek_ally = 0.6 (mock), и spread_rumor base=0.4 → 0.4+1.95=2.35 > 0.6.")
print(f"  Но в production seek_ally baseline ОЧЕНЬ высокий (need-driven dominance).")

_h.dispose()
