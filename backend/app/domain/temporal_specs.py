"""
path: backend/app/domain/temporal_specs.py
Назначение: Временные контракты, специфичные для намерений.
    Каждый тип намерения (Intent) имеет: prediction (описание), validity_rule, success_rule, max_duration.
    Правила — это именованные строки, разрешаемые через реестр (НЕ лямбды, НЕ сериализованные вызываемые объекты).
    Безопасность при повторном проигрывании: одно и то же состояние + ID правила → один и тот же результат.
Зависимости: dataclasses, typing
Основные сущности: TemporalSpec, TemporalContext, TEMPORAL_SPECS,
    VALIDITY_RULES, SUCCESS_RULES
    ТРИ ВОПРОСА (закон Temporal Runtime):
        Opportunity: "Can this intention be selected?"  (OpportunityProducer)
        Validity:    "Can an already selected commitment continue?"  (temporal)
        Success:     "Did its intended outcome actually occur?"  (temporal)

    Validity НЕ перевычисляет Opportunity. Validity проверяет физические
    условия продолжения (conscious, alive). Player approach, target death —
    reactive preemption (Phase 4.5, checked BEFORE hold, NOT validity).

    Phase 4.5 check order (immutable):
        1. reactive preemption (hub_event ≠ WORLD_TICK) → CANCELLED
        2. success_check → COMPLETED
        3. validity_check → CANCELLED (if False)
        4. age >= max_duration_ticks → EXPIRED
        5. else → HOLD (skip proactive decision, reactive still passes)
Зависимости: dataclasses, typing
Основные сущности: TemporalSpec, TemporalContext, TEMPORAL_SPECS,
    VALIDITY_RULES, SUCCESS_RULES
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional


@dataclass(frozen=True)
class TemporalContext:
    """Lightweight pure-data context for temporal checks.
    No services — just data snapshots. Deterministic."""
    spatial_query: Optional[Any] = None  # SpatialQueryService (read-only)
    scene_state: Optional[dict] = None
    tick: int = 0


@dataclass(frozen=True)
class TemporalSpec:
    """Temporal contract for a specific Intent type.
    DecisionHub produces Intent → registry lookup → TemporalSpec →
    TemporalCommitment. Temporal layer does NOT invent predictions."""
    validity_rule: str        # named rule ID (resolved via VALIDITY_RULES)
    success_rule: str         # named rule ID (resolved via SUCCESS_RULES)
    max_duration_ticks: int   # calibratable (CalibrationProfile)
    prediction_description: str  # human-readable, NOT executed


# ── Named rule functions (pure, deterministic, replay-safe) ──
#
# Validity rules: "Can the commitment CONTINUE?" — physical conditions only.
# Does NOT re-check opportunity (that's OpportunityProducer's job).
# Reactive events (player approach, attack received) are handled by
# reactive preemption in Phase 4.5, NOT by validity rules.

def _steal_validity(npc_state: Any, ctx: TemporalContext) -> bool:
    """STEAL commitment valid while NPC is conscious (can continue acting).
    Player approach = reactive preemption (Phase 4.5), NOT validity.
    Opportunity score = OpportunityProducer's job, NOT duplicated here."""
    from app.domain.vital_state import is_conscious
    _body = getattr(npc_state, "body_state", None) or {}
    return is_conscious(_body)


def _steal_success(npc_state: Any, ctx: TemporalContext) -> bool:
    """STEAL success = theft materialized.
    Phase 1: ActionWindup (existing, 2-tick) handles STEAL execution;
    temporal success is wired to windup completion in Phase 2.
    Placeholder returns False — commitment EXPIRES after max_duration,
    which is correct (windup either completed or didn't)."""
    return False  # Phase 2: wire to windup WindupStatus.COMPLETED


def _eat_validity(npc_state: Any, ctx: TemporalContext) -> bool:
    """EAT commitment valid while hungry AND conscious.
    hunger > 0.3 = still needs food (hasn't eaten yet)."""
    from app.domain.vital_state import is_conscious
    _body = getattr(npc_state, "body_state", None) or {}
    _hunger = float(_body.get("hunger", 1.0))
    return _hunger > 0.3 and is_conscious(_body)


def _eat_success(npc_state: Any, ctx: TemporalContext) -> bool:
    """EAT success = hunger dropped below threshold (goal achieved)."""
    _body = getattr(npc_state, "body_state", None) or {}
    _hunger = float(_body.get("hunger", 1.0))
    return _hunger <= 0.3


def _approach_validity(npc_state: Any, ctx: TemporalContext) -> bool:
    """APPROACH commitment valid while NPC conscious.
    Destination reachability = existing TraversalState (Phase 7 checks).
    If traversal fails (blocked, target gone) → existing CANCELLED path."""
    from app.domain.vital_state import is_conscious
    _body = getattr(npc_state, "body_state", None) or {}
    return is_conscious(_body)


def _approach_success(npc_state: Any, ctx: TemporalContext) -> bool:
    """APPROACH success = NPC reached target.
    Phase 1: TraversalState.COMPLETED (existing) handles this;
    temporal success wired to traversal completion in Phase 2."""
    return False  # Phase 2: wire to TraversalStatus.COMPLETED


def _attack_validity(npc_state: Any, ctx: TemporalContext) -> bool:
    """ATTACK commitment valid while NPC conscious.
    Target alive = Phase 7 Stale Intent Validation (existing).
    Temporal validity does NOT duplicate target-alive check."""
    from app.domain.vital_state import is_conscious
    _body = getattr(npc_state, "body_state", None) or {}
    return is_conscious(_body)


def _attack_success(npc_state: Any, ctx: TemporalContext) -> bool:
    """ATTACK success = COMBAT_HIT on bus.
    Phase 1: ActionWindup handles ATTACK execution; temporal success
    wired to windup completion in Phase 2."""
    return False  # Phase 2: wire to windup WindupStatus.COMPLETED


# ── Registries ──

VALIDITY_RULES: Dict[str, Callable[[Any, TemporalContext], bool]] = {
    "steal_validity": _steal_validity,
    "eat_validity": _eat_validity,
    "approach_validity": _approach_validity,
    "attack_validity": _attack_validity,
}

SUCCESS_RULES: Dict[str, Callable[[Any, TemporalContext], bool]] = {
    "steal_success": _steal_success,
    "eat_success": _eat_success,
    "approach_success": _approach_success,
    "attack_success": _attack_success,
}

# ── Temporal Specifications per Intent type ──

TEMPORAL_SPECS: Dict[str, TemporalSpec] = {
    "steal": TemporalSpec(
        validity_rule="steal_validity",
        success_rule="steal_success",
        max_duration_ticks=3,  # windup(2) + execution(1) — existing
        prediction_description="player remains outside intervention range",
    ),
    "attack": TemporalSpec(
        validity_rule="attack_validity",
        success_rule="attack_success",
        max_duration_ticks=3,
        prediction_description="target remains in range and alive",
    ),
    "approach": TemporalSpec(
        validity_rule="approach_validity",
        success_rule="approach_success",
        max_duration_ticks=10,
        prediction_description="destination remains reachable",
    ),
    "eat": TemporalSpec(
        validity_rule="eat_validity",
        success_rule="eat_success",
        max_duration_ticks=10,
        prediction_description="hunger will continue rising without food",
    ),
}


def get_temporal_spec(intent_type: str) -> Optional[TemporalSpec]:
    """Registry lookup. Returns None if intent has no temporal contract
    (reactive intents, IDLE, etc. — no commitment created)."""
    return TEMPORAL_SPECS.get(intent_type)


def check_validity(rule_id: str, npc_state: Any, ctx: TemporalContext) -> bool:
    """Resolve named rule → pure function → execute. Fail-safe: unknown rule → False."""
    fn = VALIDITY_RULES.get(rule_id)
    if fn is None:
        return False
    return fn(npc_state, ctx)


def check_success(rule_id: str, npc_state: Any, ctx: TemporalContext) -> bool:
    fn = SUCCESS_RULES.get(rule_id)
    if fn is None:
        return False
    return fn(npc_state, ctx)

# ── Reactive preemption events ──
# NOT all non-WORLD_TICK — only physical threats, player intervention,
# proximity changes. NPC_SPOKE, NPC_MOVED, COMMUNICATION_CLAIM — do NOT.
# Extension requires explicit ADR.
REACTIVE_PREEMPTION_EVENTS: frozenset[str] = frozenset({
    "combat", "actor_attacks",
    "player_attacks", "player_attack", "player_interacts",
    "player_threatens", "player_insults", "player_used_item",
    "player_cast_spell", "player_moved",
    "npc_proximity_close", "proximity_close",
})


def is_reactive_preemption(event_type: str) -> bool:
    """Specific events only — NOT blanket 'non-WORLD_TICK'."""
    return event_type in REACTIVE_PREEMPTION_EVENTS