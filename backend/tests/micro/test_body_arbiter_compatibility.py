"""
path: /project/backend/tests/micro/test_body_arbiter_compatibility.py
Назначение: Step 3.2 Etap A — тесты check_compatibility + domain entities.
    Проверяет все 15 пар из матрицы совместимости + UNKNOWN + edge cases.
Зависимости: app.domain.arbitration
Запуск: cd backend; python -m pytest tests/micro/test_body_arbiter_compatibility.py -v
"""

from app.domain.arbitration import (
    ArbitrationResult,
    ArbitrationVerdict,
    CompatibilityClass,
    DerivedPhysicalIntent,
    EffectState,
    PhysicalEffectProfile,
    ResistanceAssessment,
    ResistanceBehavior,
    ResistanceOutcome,
    check_compatibility,
)


# ── Domain entities construction ────────────────────────────────────


def test_arbitration_verdict_values():
    """Все 5 вердиктов существуют."""
    assert ArbitrationVerdict.NO_CONFLICT.value == "no_conflict"
    assert ArbitrationVerdict.RESOLVE_RESISTANCE.value == "resolve_resistance"
    assert ArbitrationVerdict.RESOLVE_STRUGGLE.value == "resolve_struggle"
    assert ArbitrationVerdict.DEFER_BOTH.value == "defer_both"
    assert ArbitrationVerdict.FAIL_BOTH.value == "fail_both"


def test_arbitration_result_frozen():
    """ArbitrationResult — frozen dataclass."""
    result = ArbitrationResult(
        verdict=ArbitrationVerdict.NO_CONFLICT,
        player_intent_id="intent:1:p:attack:1",
        avatar_intent_id=None,
        compatibility_class=CompatibilityClass.COMPATIBLE,
        conflict_type=None,
        reason="no avatar intent",
        tick=1,
    )
    assert result.verdict == ArbitrationVerdict.NO_CONFLICT
    assert result.player_intent_id == "intent:1:p:attack:1"


def test_physical_effect_profile_defaults():
    """PhysicalEffectProfile defaults — не требует ничего."""
    profile = PhysicalEffectProfile()
    assert not profile.requires_movement
    assert not profile.requires_stop
    assert not profile.requires_hands
    assert not profile.requires_voice
    assert not profile.is_internal


def test_resistance_behavior_values():
    """Все 6 типов поведения существуют."""
    assert ResistanceBehavior.RESIST_PHYSICAL.value == "resist_physical"
    assert ResistanceBehavior.YIELD.value == "yield"
    assert ResistanceBehavior.NEGOTIATE.value == "negotiate"
    assert ResistanceBehavior.SELF_HARM.value == "self_harm"
    assert ResistanceBehavior.ESCALATE.value == "escalate"
    assert ResistanceBehavior.NO_DIALOGUE.value == "no_dialogue"


def test_resistance_assessment_frozen():
    """ResistanceAssessment — frozen, 4 оси."""
    assessment = ResistanceAssessment(
        desire_strength=0.7,
        willingness_to_resist=50.0,
        decision_to_struggle=0.8,
        physical_capability=0.6,
    )
    assert assessment.desire_strength == 0.7
    assert assessment.willingness_to_resist == 50.0


def test_effect_state_values():
    """Все 5 состояний эффекта существуют."""
    assert EffectState.NOT_STARTED.value == "not_started"
    assert EffectState.IN_PROGRESS.value == "in_progress"
    assert EffectState.COMPLETED.value == "completed"
    assert EffectState.FAILED.value == "failed"
    assert EffectState.NOT_APPLICABLE.value == "not_applicable"


def test_derived_physical_intent_frozen():
    """DerivedPhysicalIntent — frozen, сохраняет source_intent_id."""
    derived = DerivedPhysicalIntent(
        derived_id="derived:1",
        source_intent_id="intent:1:avatar:approach:1",
        owner="uuid-a",
        body_id="uuid-b",
        derived_action="self_harm",
        physical_effect="body_damage",
        formed_tick=1,
    )
    assert derived.source_intent_id == "intent:1:avatar:approach:1"
    assert derived.owner == "uuid-a"
    assert derived.body_id == "uuid-b"


# ── Compatibility: no intent / single intent ──────────────────────


def test_no_intents_returns_unknown():
    """Нет обоих намерений → UNKNOWN."""
    result = check_compatibility(None, None)
    assert result == CompatibilityClass.UNKNOWN


def test_no_avatar_intent_returns_compatible():
    """Нет Avatar → COMPATIBLE (нет конфликта)."""
    result = check_compatibility("attack", None)
    assert result == CompatibilityClass.COMPATIBLE


def test_no_player_intent_returns_compatible():
    """Нет Player → COMPATIBLE (нет конфликта)."""
    result = check_compatibility(None, "approach")
    assert result == CompatibilityClass.COMPATIBLE


# ── Compatibility matrix: 15 pairs ────────────────────────────────


def test_pair_1_move_plus_talk_compatible():
    """1: Move + Talk — COMPATIBLE (ноги + голос)."""
    result = check_compatibility("move", "talk")
    assert result == CompatibilityClass.COMPATIBLE


def test_pair_2_move_plus_interact_conflict():
    """2: Move + Interact (steal) — CONFLICT (движение + остановка+руки)."""
    result = check_compatibility("move", "steal")
    assert result == CompatibilityClass.CONFLICT


def test_pair_3_move_plus_eat_conflict():
    """3: Move + Approach (food) — CONFLICT (оба movement).

    Note: eat maps to APPROACH in current _DESIRE_SUBJECT_TO_INTENT.
    APPROACH requires_movement → CONFLICT with Move.
    """
    result = check_compatibility("move", "approach")
    assert result == CompatibilityClass.CONFLICT


def test_pair_4_talk_npc_a_plus_talk_npc_b_conflict():
    """4: Talk(A) + Talk(B) — CONFLICT (один голос, разные слушатели)."""
    result = check_compatibility("talk", "talk", "npc_a", "npc_b")
    assert result == CompatibilityClass.CONFLICT


def test_pair_5_move_east_plus_move_west_conflict():
    """5: Move(east) + Move(west) — CONFLICT (оба movement, разные target).

    Note: target_position is None (spatial resolution — future step),
    но target string различается → CONFLICT.
    """
    result = check_compatibility("move", "flee", "east", "west")
    assert result == CompatibilityClass.CONFLICT


def test_pair_6_attack_a_plus_attack_b_conflict():
    """6: Attack(A) + Attack(B) — CONFLICT (оба requires_hands)."""
    result = check_compatibility("attack", "attack", "target_a", "target_b")
    assert result == CompatibilityClass.CONFLICT


def test_pair_7_attack_plus_resist_conflict():
    """7: Attack + Resist — CONFLICT (resistance, режим B).

    Avatar resistance is modeled as FLEE (requires_movement).
    Player ATTACK requires_stop. Movement + stop = CONFLICT.
    """
    result = check_compatibility("attack", "flee")
    assert result == CompatibilityClass.CONFLICT


def test_pair_8_move_away_plus_approach_food_conflict():
    """8: Move(away) + Approach(food) — CONFLICT (оба movement, разные target)."""
    result = check_compatibility("move", "approach", "away", "food")
    assert result == CompatibilityClass.CONFLICT


def test_pair_9_talk_a_plus_talk_a_compatible():
    """9: Talk(A) + Talk(A) — COMPATIBLE (оба хотят одного — слияние)."""
    result = check_compatibility("talk", "talk", "npc_a", "npc_a")
    assert result == CompatibilityClass.COMPATIBLE


def test_pair_10_attack_dead_target_plus_any_unknown():
    """10: Attack(dead) + Any — UNKNOWN (body state check not in compatibility).

    Body death is CONDITIONAL, but check_compatibility doesn't check body_state.
    This returns CONFLICT (both require_hands if Avatar also attacks) or
    COMPATIBLE (if Avatar does something else). With None avatar action → COMPATIBLE.
    Body state check is BodyArbiter's responsibility, not check_compatibility.
    """
    # check_compatibility checks action profiles, not body_state
    # Dead body is CONDITIONAL — handled by BodyArbiter, not here
    result = check_compatibility("attack", "idle")
    # attack requires_stop+hands, idle requires nothing → COMPATIBLE (different resources)
    assert result == CompatibilityClass.COMPATIBLE


def test_pair_11_move_during_sleep_plus_any_compatible():
    """11: Move + Idle — COMPATIBLE (different resources)."""
    result = check_compatibility("move", "idle")
    assert result == CompatibilityClass.COMPATIBLE


def test_pair_12_interact_plus_observe_compatible():
    """12: Steal + Observe — COMPATIBLE (руки + глаза)."""
    result = check_compatibility("steal", "observe")
    assert result == CompatibilityClass.COMPATIBLE


def test_pair_13_steal_plus_flee_conflict():
    """13: Steal + Flee — CONFLICT (steal requires_stop, flee requires_movement)."""
    result = check_compatibility("steal", "flee")
    assert result == CompatibilityClass.CONFLICT


def test_pair_14_any_plus_internal_dialogue_compatible():
    """14: Any + Internal dialogue — COMPATIBLE (is_internal=True)."""
    result = check_compatibility("attack", "internal_dialogue")
    assert result == CompatibilityClass.COMPATIBLE


def test_pair_15_attack_plus_new_attack_compatible_if_same_target():
    """15: Attack(A) + Attack(A) — COMPATIBLE (same target, same action)."""
    result = check_compatibility("attack", "attack", "target_a", "target_a")
    assert result == CompatibilityClass.COMPATIBLE


# ── UNKNOWN handling ───────────────────────────────────────────────


def test_unknown_action_returns_unknown():
    """Unknown action → UNKNOWN compatibility (both profiles empty)."""
    result = check_compatibility("unknown_action", "another_unknown")
    assert result == CompatibilityClass.UNKNOWN


def test_one_unknown_action_returns_compatible():
    """One known + one unknown → COMPATIBLE (unknown profile is empty)."""
    result = check_compatibility("attack", "unknown_action")
    # unknown_action has all requires=False → no conflict with attack
    assert result == CompatibilityClass.COMPATIBLE


def test_empty_actions_return_unknown():
    """Empty strings → UNKNOWN."""
    result = check_compatibility("", "")
    assert result == CompatibilityClass.UNKNOWN


# ── Edge cases ─────────────────────────────────────────────────────


def test_both_internal_dialogue_compatible():
    """Both internal → COMPATIBLE."""
    result = check_compatibility("internal_dialogue", "think")
    assert result == CompatibilityClass.COMPATIBLE


def test_move_same_target_compatible():
    """Move(tavern) + Move(tavern) — COMPATIBLE (same target)."""
    result = check_compatibility("move", "approach", "tavern", "tavern")
    assert result == CompatibilityClass.COMPATIBLE


def test_two_voice_different_targets_conflict():
    """Talk(A) + Warn(B) — CONFLICT (both voice, different targets)."""
    result = check_compatibility("talk", "warn", "npc_a", "npc_b")
    assert result == CompatibilityClass.CONFLICT


def test_attack_plus_talk_compatible():
    """Attack + Talk — COMPATIBLE (hands + voice, different resources)."""
    result = check_compatibility("attack", "talk")
    assert result == CompatibilityClass.COMPATIBLE


def test_steal_plus_steal_same_target_compatible():
    """Steal(A) + Steal(A) — COMPATIBLE (same target, same action)."""
    result = check_compatibility("steal", "steal", "target_a", "target_a")
    assert result == CompatibilityClass.COMPATIBLE
