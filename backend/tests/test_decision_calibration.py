# backend/tests/test_decision_calibration.py
"""
R4.2 — Калибровочные тесты формулы score().

Проверяет поведенческие инварианты DecisionHub:
  - Правильный intent при заданных условиях
  - Предсказуемость без детерминированности (seed фиксирован)
  - Влияние drives, traits, relationships на выбор
  - Не структурные тесты (что возвращается), а поведенческие (что выбирается).
  - Каждый тест = один сценарий с ожидаемым поведением NPC.

Эти тесты — "живая документация" формулы.
Если тест падает — изменились веса, нужна рекалибровка.
"""

import pytest
from app.domain.identity_events import EffectiveDrives

_MOCK_DRIVES = EffectiveDrives.from_dict({"control": 0.5, "significance": 0.5, "fear": 0.5, "desire": 0.5})

from app.models.npc_state import (
    EmotionTag,
    Intent,
    NPCIdentityL1,
    NPCPersonality,
    NPCState,
    NPCTier,
    WillState,
)
from app.services.npc.decision_hub import DecisionHub, EventContext

# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def hub() -> DecisionHub:
    """Фиксированный seed — детерминированные результаты калибровки."""
    return DecisionHub(seed=0)


@pytest.fixture
def control_personality() -> NPCPersonality:
    """NPC с доминирующим drive: control (трактирщик, стражник)."""
    return NPCPersonality(
        npc_id="control_npc",
        tier=NPCTier.MAJOR,
        drives_base={"control": 0.55, "significance": 0.25, "fear": 0.10, "desire": 0.10},
        willpower=70.0,
        breakpoint=85.0,
        loyalty_base=50.0,
    )


@pytest.fixture
def fear_personality() -> NPCPersonality:
    """NPC с доминирующим drive: fear (крестьянин, слуга)."""
    return NPCPersonality(
        npc_id="fear_npc",
        tier=NPCTier.MINOR,
        drives_base={"control": 0.10, "significance": 0.10, "fear": 0.65, "desire": 0.15},
        willpower=25.0,
        breakpoint=55.0,
        loyalty_base=30.0,
    )


@pytest.fixture
def desire_personality() -> NPCPersonality:
    """NPC с доминирующим drive: desire (торговец)."""
    return NPCPersonality(
        npc_id="desire_npc",
        tier=NPCTier.MINOR,
        drives_base={"control": 0.15, "significance": 0.15, "fear": 0.10, "desire": 0.60},
        willpower=40.0,
        breakpoint=75.0,
        loyalty_base=40.0,
    )


@pytest.fixture
def close_combat_event() -> EventContext:
    """Близкое боевое событие — максимальное давление."""
    return EventContext(
        event_type="combat",
        actor_id="player",
        success=True,
        intensity=1.0,
        distance=1.5,
        witness_count=4,
        visible_threat_markers=["weapon_melee", "heavy_armor"],
    )


@pytest.fixture
def theft_failed_event() -> EventContext:
    """Провальная попытка кражи — NPC заметил."""
    return EventContext(
        event_type="theft",
        actor_id="player",
        success=False,
        intensity=0.8,
        distance=2.0,
        witness_count=2,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Боевое давление
# ─────────────────────────────────────────────────────────────────────────────


class TestCombatCalibration:
    def test_high_stress_combat_no_talk_or_trade(
        self,
        hub: DecisionHub,
        control_personality: NPCPersonality,
        close_combat_event: EventContext,
    ) -> None:
        """
        При стрессе >80 и близком бою — NPC не разговаривает и не торгует.
        Только примитивные реакции: FLEE, WARN, OBSERVE.
        """
        state = NPCState(
            npc_id="control_npc",
            stress=82.0,
            will_state=WillState.FREE,
            emotion=EmotionTag.FEARFUL,
        )
        result = hub.compute(state, control_personality, close_combat_event, effective_drives=_MOCK_DRIVES)
        assert result.intent not in (Intent.TALK, Intent.TRADE, Intent.HELP), (
            f"При стрессе >80 NPC не должен разговаривать/торговать: {result.intent}"
        )

    def test_fear_drive_flees_from_combat(
        self,
        hub: DecisionHub,
        fear_personality: NPCPersonality,
        close_combat_event: EventContext,
    ) -> None:
        """
        NPC с fear drive > 0.6 при близком бою → FLEE или OBSERVE.
        Никогда не ATTACK.
        """
        state = NPCState(npc_id="fear_npc", emotion=EmotionTag.FEARFUL)
        result = hub.compute(state, fear_personality, close_combat_event, effective_drives=_MOCK_DRIVES)
        assert result.intent != Intent.ATTACK, "Трусливый NPC не атакует при близком бою"
        assert result.intent in (Intent.FLEE, Intent.OBSERVE, Intent.WARN, Intent.IDLE, Intent.TALK), (
            f"Трусливый NPC должен избегать, не атаковать: {result.intent}"
        )

    def test_control_npc_warns_with_witnesses(
        self,
        hub: DecisionHub,
        control_personality: NPCPersonality,
    ) -> None:
        """
        NPC с control drive при краже с свидетелями → WARN или REPORT.
        Социальное давление (witness_count) активирует control-реакции.
        """
        state = NPCState(npc_id="control_npc")
        event = EventContext(
            event_type="theft",
            actor_id="player",
            success=False,
            intensity=0.9,
            distance=2.0,
            witness_count=5,
        )
        result = hub.compute(state, control_personality, event, effective_drives=_MOCK_DRIVES)
        # WARN, REPORT — ожидаемые реакции control-drive при публичном нарушении
        assert result.intent in (Intent.WARN, Intent.REPORT, Intent.INTIMIDATE, Intent.OBSERVE), (
            f"Control NPC при краже с свидетелями: ожидали WARN/REPORT, получили {result.intent}"
        )

    def test_scores_trace_attack_negative_for_fear_npc(
        self,
        hub: DecisionHub,
        fear_personality: NPCPersonality,
        close_combat_event: EventContext,
    ) -> None:
        """
        Для трусливого NPC score ATTACK должен быть ≤ 0 (early exit в формуле).
        """
        state = NPCState(npc_id="fear_npc")
        _fear_drives = EffectiveDrives.from_dict(fear_personality.drives_base)
        result = hub.compute(state, fear_personality, close_combat_event, effective_drives=_fear_drives)
        attack_score = result.scores_trace.get(Intent.ATTACK.value, -1.0)
        assert attack_score <= 0.0, f"Трусливый NPC: score ATTACK должен быть ≤ 0, получили {attack_score}"

    def test_scores_within_reasonable_bounds(
        self,
        hub: DecisionHub,
        fear_personality: NPCPersonality,
        close_combat_event: EventContext,
    ) -> None:
        """
        При экстремальных значениях (fear=100) scores остаются в bounds.
        Защита от overflow в формуле при граничных условиях.
        """
        extreme_state = NPCState(
            npc_id="fear_npc",
            stress=99.0,
            emotion=EmotionTag.FEARFUL,
            relationship_cache={"trust": 0.0, "fear": 100.0, "debt": 0.0},
        )
        result = hub.compute(extreme_state, fear_personality, close_combat_event, effective_drives=_MOCK_DRIVES)

        for intent_name, score in result.scores_trace.items():
            assert -2.0 <= score <= 3.0, f"Score '{intent_name}' вышел за пределы [-2, 3]: {score}"


# ─────────────────────────────────────────────────────────────────────────────
# Влияние отношений (relationship_modifier)
# ─────────────────────────────────────────────────────────────────────────────


class TestRelationshipCalibration:
    def test_high_trust_boosts_help_score(
        self,
        hub: DecisionHub,
        control_personality: NPCPersonality,
    ) -> None:
        """
        Trust = 80 → score HELP выше чем при trust = 0.
        relationship_modifier работает корректно.
        """
        event = EventContext(
            event_type="help",
            actor_id="player",
            intensity=0.8,
        )
        state_trusted = NPCState(npc_id="control_npc")
        state_neutral = NPCState(npc_id="control_npc")
        # M1b.3.1: fallback удалён. ПАРАМЕТРЫ compute — единственный прод-путь
        # (:425-426: relationship_store/campaign_id при вызове; pipeline:624
        # так и передаёт). Trusted = 80.0 в V2; Neutral = Vacuum (reset).
        from app.services.social.v2_relationship_backend import V2RelationshipBackend

        _v2 = V2RelationshipBackend(lambda: {})
        _v2.bind("test_calib")
        _v2.update("test_calib", "control_npc", "player", {"trust": 80.0})
        result_trusted = hub.compute(
            state_trusted, control_personality, event,
            effective_drives=_MOCK_DRIVES,
            relationship_store=_v2, campaign_id="test_calib",
        )
        # neutral-прогон: Vacuum (запись удалена — reset-семантика)
        _v2.reset_campaign("test_calib")
        result_neutral = hub.compute(
            state_neutral, control_personality, event,
            effective_drives=_MOCK_DRIVES,
            relationship_store=_v2, campaign_id="test_calib",
        )

        trusted_help = result_trusted.scores_trace.get(Intent.HELP.value, 0.0)
        neutral_help = result_neutral.scores_trace.get(Intent.HELP.value, 0.0)

        assert trusted_help > neutral_help, (
            f"Высокий trust должен повышать score HELP: {trusted_help} vs {neutral_help}"
        )

    def test_fear_in_relationship_boosts_flee(
        self,
        hub: DecisionHub,
        fear_personality: NPCPersonality,
        close_combat_event: EventContext,
    ) -> None:
        """
        Высокий fear в relationship → score FLEE ещё выше.
        """
        state_scared = NPCState(
            npc_id="fear_npc",
            relationship_cache={"trust": 0.0, "fear": 70.0, "debt": 0.0},
        )
        state_neutral = NPCState(
            npc_id="fear_npc",
            relationship_cache={"trust": 0.0, "fear": 0.0, "debt": 0.0},
        )
        r_scared = hub.compute(state_scared, fear_personality, close_combat_event, effective_drives=_MOCK_DRIVES)
        r_neutral = hub.compute(state_neutral, fear_personality, close_combat_event, effective_drives=_MOCK_DRIVES)

        flee_scared = r_scared.scores_trace.get(Intent.FLEE.value, 0.0)
        flee_neutral = r_neutral.scores_trace.get(Intent.FLEE.value, 0.0)

        assert flee_scared >= flee_neutral, f"Высокий fear должен повышать score FLEE: {flee_scared} vs {flee_neutral}"


# ─────────────────────────────────────────────────────────────────────────────
# Влияние трейтов (trait_modifier)
# ─────────────────────────────────────────────────────────────────────────────


class TestTraitCalibration:
    def test_suspicious_trait_boosts_observe(
        self,
        hub: DecisionHub,
        desire_personality: NPCPersonality,
    ) -> None:
        """
        Трейт suspicious > 0.6 → score OBSERVE выше, чем без трейта.
        """
        event = EventContext(
            event_type="dialogue",
            actor_id="player",
            intensity=0.5,
        )
        identity_suspicious = NPCIdentityL1(npc_id="desire_npc", active_traits={"suspicious": 0.8})
        state_suspicious = NPCState(npc_id="desire_npc")
        state_clean = NPCState(npc_id="desire_npc")

        r_suspicious = hub.compute(state_suspicious, desire_personality, event, identity=identity_suspicious, effective_drives=_MOCK_DRIVES)
        r_clean = hub.compute(state_clean, desire_personality, event, effective_drives=_MOCK_DRIVES)

        obs_suspicious = r_suspicious.scores_trace.get(Intent.OBSERVE.value, 0.0)
        obs_clean = r_clean.scores_trace.get(Intent.OBSERVE.value, 0.0)

        assert obs_suspicious > obs_clean, f"Suspicious trait должен повышать OBSERVE: {obs_suspicious} vs {obs_clean}"

    def test_grateful_trait_reduces_attack(
        self,
        hub: DecisionHub,
        control_personality: NPCPersonality,
        close_combat_event: EventContext,
    ) -> None:
        """
        Трейт grateful → score ATTACK ниже, чем без трейта.
        """
        identity_grateful = NPCIdentityL1(npc_id="control_npc", active_traits={"grateful": 0.9})
        state_grateful = NPCState(npc_id="control_npc")
        state_neutral = NPCState(npc_id="control_npc")

        r_grateful = hub.compute(state_grateful, control_personality, close_combat_event, identity=identity_grateful, effective_drives=_MOCK_DRIVES)
        r_neutral = hub.compute(state_neutral, control_personality, close_combat_event, effective_drives=_MOCK_DRIVES)

        atk_grateful = r_grateful.scores_trace.get(Intent.ATTACK.value, -1.0)
        atk_neutral = r_neutral.scores_trace.get(Intent.ATTACK.value, -1.0)

        assert atk_grateful <= atk_neutral, f"Grateful trait должен снижать ATTACK: {atk_grateful} vs {atk_neutral}"

    def test_intent_inertia_favors_current_intent(
        self,
        hub: DecisionHub,
        control_personality: NPCPersonality,
    ) -> None:
        """
        NPC держит WARN 8 тиков С ПРОГРЕССОМ → inertia даёт WARN буст.
        Без прогресса exhaustion штрафует intent — это отдельный тест.
        """
        event = EventContext(
            event_type="theft",
            actor_id="player",
            intensity=0.7,
            witness_count=2,
        )
        state_inertia = NPCState(
            npc_id="control_npc",
            intent=Intent.WARN,
            intent_target="player",
            intent_duration=8,
            intent_progress_ticks=8,  # Есть прогресс → нет exhaustion
        )
        state_fresh = NPCState(
            npc_id="control_npc",
            intent=None,
            intent_duration=0,
        )

        r_inertia = hub.compute(state_inertia, control_personality, event, effective_drives=_MOCK_DRIVES)
        r_fresh = hub.compute(state_fresh, control_personality, event, effective_drives=_MOCK_DRIVES)

        warn_inertia = r_inertia.scores_trace.get(Intent.WARN.value, 0.0)
        warn_fresh = r_fresh.scores_trace.get(Intent.WARN.value, 0.0)

        assert warn_inertia > warn_fresh, (
            f"Инерция должна повышать score текущего intent: {warn_inertia} vs {warn_fresh}"
        )
