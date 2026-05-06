"""
Тесты SceneOutcomeBuilder — компрессора реальности для DM.

cd backend; python -m pytest tests/test_scene_outcome_builder.py -v

path: backend/tests/test_scene_outcome_builder.py
Назначение: Покрытие SceneOutcomeBuilder — salience, tension, visibility, latent
Зависимости: scene_outcome_builder.py, decision_hub.py, npc_state.py

Покрытие:
- Salience calculation (близкий > дальний, эмоциональный > спокойный)
- Tension (spike при травме, rising при стрессе, sources)
- Visibility (расстояние + LOS)
- Latent extraction (травма, will_override, integrity)
- Сортировка actors по salience
- Edge cases (пустой вход)
"""

import pytest
from typing import Dict, Optional

from app.services.verbalization.scene_outcome_builder import (
    SceneOutcomeBuilder,
    SceneContext,
    LatentSignalType,
    Visibility,
    TensionTrend,
)
from app.services.npc.decision_hub import DecisionResult, StateDeltas
from app.models.npc_state import EmotionTag, Intent, WillState


# ─────────────────────────────────────────────────────────────────────────────
# Фикстуры — фабрики для быстрого создания тестовых данных
# ─────────────────────────────────────────────────────────────────────────────

def make_deltas(
    npc_id: str = "test_npc",
    stress: float = 0.0,
    fear: float = 0.0,
    emotion_tag: Optional[EmotionTag] = None,
    trust: float = 0.0,
    new_trauma: Optional[str] = None,
    will_state_override: Optional[WillState] = None,
    identity_integrity_delta: float = 0.0,
) -> StateDeltas:
    """Быстрая фабрика StateDeltas."""
    return StateDeltas(
        npc_id=npc_id,
        stress_delta=stress,
        stress_delta_effective=stress,
        emotion_delta=0.0,
        emotion_tag=emotion_tag,
        trust_delta=trust,
        fear_delta=fear,
        trait_updates={},
        new_trauma=new_trauma,
        identity_integrity_delta=identity_integrity_delta,
        pressure_resistance_delta=0.0,
        will_state_override=will_state_override,
    )


def make_decision(
    npc_id: str = "npc_1",
    intent: Intent = Intent.IDLE,
    intent_target: Optional[str] = None,
    score: float = 0.5,
    deltas: Optional[StateDeltas] = None,
    narrative_fact: Optional[str] = None,
) -> DecisionResult:
    """Быстрая фабрика DecisionResult."""
    return DecisionResult(
        npc_id=npc_id,
        intent=intent,
        intent_target=intent_target,
        score=score,
        scores_trace={},
        deltas=deltas or make_deltas(),
        narrative_fact=narrative_fact,
        explanation_mode=False,
    )


def make_context(
    distances: Optional[Dict[str, float]] = None,
    visible_npcs: Optional[set] = None,
    npc_tiers: Optional[Dict[str, str]] = None,
    player_action: str = "поговорить",
    player_success: bool = True,
) -> SceneContext:
    """Быстрая фабрика SceneContext."""
    return SceneContext(
        distances=distances or {},
        visible_npcs=visible_npcs or set(),
        npc_tiers=npc_tiers or {},
        player_action_text=player_action,
        player_success=player_success,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Тесты Salience
# ─────────────────────────────────────────────────────────────────────────────

class TestSalienceCalculation:
    """Salience определяет приоритет внимания DM в сцене."""

    def test_close_npc_has_higher_salience_than_far(self):
        """Близкий NPC должен иметь выше salience, чем далёкий."""
        builder = SceneOutcomeBuilder()
        
        close_decision = make_decision(
            npc_id="close_npc",
            deltas=make_deltas(),  # без эмоций
        )
        far_decision = make_decision(
            npc_id="far_npc",
            deltas=make_deltas(),
        )
        
        context = make_context(
            distances={"close_npc": 1.0, "far_npc": 12.0},
            visible_npcs={"close_npc", "far_npc"},
        )
        
        outcome = builder.build([close_decision, far_decision], context)
        
        close_outcome = next(a for a in outcome.actors if a.npc_id == "close_npc")
        far_outcome = next(a for a in outcome.actors if a.npc_id == "far_npc")
        
        assert close_outcome.salience > far_outcome.salience

    def test_emotional_npc_has_higher_salience(self):
        """NPC с сильной эмоцией должен иметь выше salience."""
        builder = SceneOutcomeBuilder()
        
        calm_decision = make_decision(
            npc_id="calm_npc",
            deltas=make_deltas(stress=0.0, fear=0.0),
        )
        emotional_decision = make_decision(
            npc_id="emotional_npc",
            deltas=make_deltas(stress=0.4, fear=0.3),
        )
        
        context = make_context(
            distances={"calm_npc": 3.0, "emotional_npc": 3.0},  # одинаковое расстояние
            visible_npcs={"calm_npc", "emotional_npc"},
        )
        
        outcome = builder.build([calm_decision, emotional_decision], context)
        
        calm_outcome = next(a for a in outcome.actors if a.npc_id == "calm_npc")
        emotional_outcome = next(a for a in outcome.actors if a.npc_id == "emotional_npc")
        
        assert emotional_outcome.salience > calm_outcome.salience

    def test_targeting_player_increases_salience(self):
        """NPC, направляющий intent на игрока, имеет выше salience."""
        builder = SceneOutcomeBuilder()
        
        neutral_decision = make_decision(
            npc_id="neutral_npc",
            intent=Intent.IDLE,
            intent_target=None,
        )
        hostile_decision = make_decision(
            npc_id="hostile_npc",
            intent=Intent.ATTACK,
            intent_target="player",
        )
        
        context = make_context(
            distances={"neutral_npc": 3.0, "hostile_npc": 3.0},
            visible_npcs={"neutral_npc", "hostile_npc"},
        )
        
        outcome = builder.build([neutral_decision, hostile_decision], context)
        
        neutral_outcome = next(a for a in outcome.actors if a.npc_id == "neutral_npc")
        hostile_outcome = next(a for a in outcome.actors if a.npc_id == "hostile_npc")
        
        assert hostile_outcome.salience > neutral_outcome.salience

    def test_major_tier_gets_bonus(self):
        """MAJOR NPC получает бонус к salience."""
        builder = SceneOutcomeBuilder()
        
        minor_decision = make_decision(npc_id="minor_npc")
        major_decision = make_decision(npc_id="major_npc")
        
        context = make_context(
            distances={"minor_npc": 3.0, "major_npc": 3.0},
            visible_npcs={"minor_npc", "major_npc"},
            npc_tiers={"minor_npc": "minor", "major_npc": "major"},
        )
        
        outcome = builder.build([minor_decision, major_decision], context)
        
        minor_outcome = next(a for a in outcome.actors if a.npc_id == "minor_npc")
        major_outcome = next(a for a in outcome.actors if a.npc_id == "major_npc")
        
        assert major_outcome.salience > minor_outcome.salience

    def test_salience_is_bounded_0_to_1(self):
        """Salience всегда в диапазоне [0, 1]."""
        builder = SceneOutcomeBuilder()
        
        # Экстремальный случай: близко + эмоциональный + направлен на игрока + MAJOR
        extreme_decision = make_decision(
            npc_id="extreme_npc",
            intent=Intent.ATTACK,
            intent_target="player",
            deltas=make_deltas(stress=0.5, fear=0.5),
        )
        
        context = make_context(
            distances={"extreme_npc": 0.0},
            visible_npcs={"extreme_npc"},
            npc_tiers={"extreme_npc": "major"},
        )
        
        outcome = builder.build([extreme_decision], context)
        
        assert 0.0 <= outcome.actors[0].salience <= 1.0


# ─────────────────────────────────────────────────────────────────────────────
# Тесты Tension
# ─────────────────────────────────────────────────────────────────────────────

class TestTensionCalculation:
    """Tension определяет уровень напряжения сцены."""

    def test_empty_decisions_gives_zero_tension(self):
        """Пустой список решений → нулевое напряжение."""
        builder = SceneOutcomeBuilder()
        
        outcome = builder.build([], make_context())
        
        assert outcome.tension.level == 0.0
        assert outcome.tension.trend == TensionTrend.STABLE
        assert outcome.tension.focus == "environment"

    def test_stress_increases_tension(self):
        """Стресс NPC увеличивает уровень tension."""
        builder = SceneOutcomeBuilder()
        
        low_stress = make_decision(
            npc_id="calm",
            deltas=make_deltas(stress=0.05),
        )
        high_stress = make_decision(
            npc_id="stressed",
            deltas=make_deltas(stress=0.3),
        )
        
        low_outcome = builder.build([low_stress], make_context())
        high_outcome = builder.build([high_stress], make_context())
        
        assert high_outcome.tension.level > low_outcome.tension.level

    def test_trauma_causes_spike(self):
        """Новая травма вызывает TensionTrend.SPIKE."""
        builder = SceneOutcomeBuilder()
        
        trauma_decision = make_decision(
            npc_id="traumatized",
            deltas=make_deltas(stress=0.1, new_trauma="видел смерть"),
        )
        
        outcome = builder.build([trauma_decision], make_context())
        
        assert outcome.tension.trend == TensionTrend.SPIKE

    def test_will_override_causes_spike(self):
        """Смена воли (will_state_override) вызывает TensionTrend.SPIKE."""
        builder = SceneOutcomeBuilder()
        
        override_decision = make_decision(
            npc_id="broken",
            deltas=make_deltas(will_state_override=WillState.BROKEN),
        )
        
        outcome = builder.build([override_decision], make_context())
        
        assert outcome.tension.trend == TensionTrend.SPIKE

    def test_sources_contains_contributors(self):
        """Tension.sources содержит только NPC с вкладом > 0.01."""
        builder = SceneOutcomeBuilder()
        
        contributor = make_decision(
            npc_id="contributor",
            deltas=make_deltas(stress=0.2, fear=0.1),
        )
        silent = make_decision(
            npc_id="silent",
            deltas=make_deltas(stress=0.0, fear=0.0),
        )
        
        outcome = builder.build([contributor, silent], make_context())
        
        assert "contributor" in outcome.tension.sources
        assert "silent" not in outcome.tension.sources
        assert outcome.tension.sources["contributor"] == pytest.approx(0.3, abs=0.01)

    def test_tension_focus_is_highest_contributor(self):
        """Tension.focus = NPC с максимальным вкладом."""
        builder = SceneOutcomeBuilder()
        
        low = make_decision(npc_id="low", deltas=make_deltas(stress=0.05))
        high = make_decision(npc_id="high", deltas=make_deltas(stress=0.3))
        
        outcome = builder.build([low, high], make_context())
        
        assert outcome.tension.focus == "high"

    def test_low_stress_gives_falling_trend(self):
        """Минимальный стресс → FALLING trend."""
        builder = SceneOutcomeBuilder()
        
        minimal = make_decision(npc_id="minimal", deltas=make_deltas(stress=0.01))
        
        outcome = builder.build([minimal], make_context())
        
        assert outcome.tension.trend == TensionTrend.FALLING


# ─────────────────────────────────────────────────────────────────────────────
# Тесты Visibility
# ─────────────────────────────────────────────────────────────────────────────

class TestVisibilityMapping:
    """Visibility определяет, как NPC виден игроку."""

    def test_close_visible_npc_is_direct(self):
        """Близкий видимый NPC → DIRECT."""
        builder = SceneOutcomeBuilder()
        
        decision = make_decision(npc_id="near")
        context = make_context(
            distances={"near": 2.0},
            visible_npcs={"near"},
        )
        
        outcome = builder.build([decision], context)
        
        assert outcome.actors[0].visibility == Visibility.DIRECT

    def test_far_visible_npc_is_indirect(self):
        """Далёкий видимый NPC → INDIRECT."""
        builder = SceneOutcomeBuilder()
        
        decision = make_decision(npc_id="far")
        context = make_context(
            distances={"far": 10.0},
            visible_npcs={"far"},
        )
        
        outcome = builder.build([decision], context)
        
        assert outcome.actors[0].visibility == Visibility.INDIRECT

    def test_hidden_npc_is_hidden(self):
        """NPC вне LOS → HIDDEN."""
        builder = SceneOutcomeBuilder()
        
        decision = make_decision(npc_id="hidden")
        context = make_context(
            distances={"hidden": 5.0},
            visible_npcs=set(),  # не в LOS
        )
        
        outcome = builder.build([decision], context)
        
        assert outcome.actors[0].visibility == Visibility.HIDDEN

    def test_very_far_npc_is_hidden(self):
        """NPC дальше HIDDEN_DISTANCE → HIDDEN."""
        builder = SceneOutcomeBuilder()
        
        decision = make_decision(npc_id="distant")
        context = make_context(
            distances={"distant": 20.0},
            visible_npcs={"distant"},
        )
        
        outcome = builder.build([decision], context)
        
        assert outcome.actors[0].visibility == Visibility.HIDDEN


# ─────────────────────────────────────────────────────────────────────────────
# Тесты Latent
# ─────────────────────────────────────────────────────────────────────────────

class TestLatentExtraction:
    """Latent — скрытые сигналы для DM (не для игрока)."""

    def test_trauma_creates_latent_signal(self):
        """Травма создаёт LatentSignal с типом TRAUMA."""
        builder = SceneOutcomeBuilder()
        
        decision = make_decision(
            npc_id="wounded",
            deltas=make_deltas(stress=0.3, new_trauma="ранение"),
        )
        
        outcome = builder.build([decision], make_context())
        
        trauma_signals = [s for s in outcome.latent if s.signal_type == LatentSignalType.TRAUMA]
        assert len(trauma_signals) == 1
        assert trauma_signals[0].source == "wounded"
        assert "ранение" in trauma_signals[0].description

    def test_will_override_creates_latent_signal(self):
        """Смена воли создаёт LatentSignal с типом WILL_OVERRIDE."""
        builder = SceneOutcomeBuilder()
        
        decision = make_decision(
            npc_id="broken",
            deltas=make_deltas(will_state_override=WillState.BROKEN),
        )
        
        outcome = builder.build([decision], make_context())
        
        will_signals = [s for s in outcome.latent if s.signal_type == LatentSignalType.WILL_OVERRIDE]
        assert len(will_signals) == 1
        assert will_signals[0].intensity == 0.9  # всегда критично

    def test_integrity_crack_creates_latent_signal(self):
        """Трещины в личности (integrity < -0.2) создают LatentSignal."""
        builder = SceneOutcomeBuilder()
        
        decision = make_decision(
            npc_id="cracking",
            deltas=make_deltas(identity_integrity_delta=-0.4),
        )
        
        outcome = builder.build([decision], make_context())
        
        crack_signals = [s for s in outcome.latent if s.signal_type == LatentSignalType.INTEGRITY_CRACK]
        assert len(crack_signals) == 1
        assert crack_signals[0].source == "cracking"

    def test_small_integrity_drop_no_signal(self):
        """Маленькое падение integrity (> -0.2) НЕ создаёт сигнал."""
        builder = SceneOutcomeBuilder()
        
        decision = make_decision(
            npc_id="stable",
            deltas=make_deltas(identity_integrity_delta=-0.1),
        )
        
        outcome = builder.build([decision], make_context())
        
        crack_signals = [s for s in outcome.latent if s.signal_type == LatentSignalType.INTEGRITY_CRACK]
        assert len(crack_signals) == 0

    def test_no_latent_for_calm_npc(self):
        """Спокойный NPC без травм → пустой latent."""
        builder = SceneOutcomeBuilder()
        
        decision = make_decision(
            npc_id="calm",
            deltas=make_deltas(),
        )
        
        outcome = builder.build([decision], make_context())
        
        assert len(outcome.latent) == 0


# ─────────────────────────────────────────────────────────────────────────────
# Тесты сортировки
# ─────────────────────────────────────────────────────────────────────────────

class TestActorsSorting:
    """Actors должны быть отсортированы по salience (высокие первые)."""

    def test_actors_sorted_by_salience_descending(self):
        """Список actors отсортирован по salience (убывание)."""
        builder = SceneOutcomeBuilder()
        
        low_salience = make_decision(npc_id="low")
        mid_salience = make_decision(
            npc_id="mid",
            intent=Intent.ATTACK,
            deltas=make_deltas(stress=0.2),
            intent_target="player",
        )
        high_salience = make_decision(
            npc_id="high",
            intent=Intent.ATTACK,
            deltas=make_deltas(stress=0.4),
            intent_target="player",
        )
        
        context = make_context(
            distances={"low": 10.0, "mid": 3.0, "high": 1.0},
            visible_npcs={"low", "mid", "high"},
            npc_tiers={"low": "minor", "mid": "minor", "high": "major"},
        )
        
        outcome = builder.build([low_salience, mid_salience, high_salience], context)
        
        saliences = [a.salience for a in outcome.actors]
        assert saliences == sorted(saliences, reverse=True)

    def test_first_actor_has_highest_salience(self):
        """Первый элемент actors имеет максимальный salience."""
        builder = SceneOutcomeBuilder()
        
        decisions = [
            make_decision(npc_id=f"npc_{i}", deltas=make_deltas(stress=i * 0.1))
            for i in range(5)
        ]
        
        context = make_context(
            distances={f"npc_{i}": 5.0 - i for i in range(5)},
            visible_npcs={f"npc_{i}" for i in range(5)},
        )
        
        outcome = builder.build(decisions, context)
        
        max_salience = max(a.salience for a in outcome.actors)
        assert outcome.actors[0].salience == max_salience


# ─────────────────────────────────────────────────────────────────────────────
# Тесты Player Outcome
# ─────────────────────────────────────────────────────────────────────────────

class TestPlayerOutcome:
    """PlayerOutcome отражает действие игрока."""

    def test_success_outcome_on_true(self):
        """player_success=True → outcome='success'."""
        builder = SceneOutcomeBuilder()
        
        outcome = builder.build([], make_context(player_success=True))
        
        assert outcome.player.outcome == "success"

    def test_fail_outcome_on_false(self):
        """player_success=False → outcome='fail'."""
        builder = SceneOutcomeBuilder()
        
        outcome = builder.build([], make_context(player_success=False))
        
        assert outcome.player.outcome == "fail"

    def test_player_action_text_preserved(self):
        """Текст действия игрока сохраняется в PlayerOutcome."""
        builder = SceneOutcomeBuilder()
        
        outcome = builder.build([], make_context(player_action="ударить гоблина"))
        
        assert outcome.player.intent == "ударить гоблина"


# ─────────────────────────────────────────────────────────────────────────────
# Тесты Scene Changes
# ─────────────────────────────────────────────────────────────────────────────

class TestSceneChanges:
    """SceneChanges извлекаются из narrative_facts."""

    def test_narrative_fact_becomes_scene_change(self):
        """narrative_fact из DecisionResult → scene_changes."""
        builder = SceneOutcomeBuilder()
        
        decision = make_decision(
            npc_id="actor",
            narrative_fact="стул опрокинут",
        )
        
        outcome = builder.build([decision], make_context())
        
        assert "стул опрокинут" in outcome.scene_changes

    def test_no_fact_no_change(self):
        """Без narrative_fact → пустой scene_changes."""
        builder = SceneOutcomeBuilder()
        
        decision = make_decision(npc_id="actor", narrative_fact=None)
        
        outcome = builder.build([decision], make_context())
        
        assert len(outcome.scene_changes) == 0


# ─────────────────────────────────────────────────────────────────────────────
# Edge Cases
# ─────────────────────────────────────────────────────────────────────────────

class TestEdgeCases:
    """Граничные случаи."""

    def test_empty_decisions_gives_empty_actors(self):
        """Пустой список решений → пустой actors."""
        builder = SceneOutcomeBuilder()
        
        outcome = builder.build([], make_context())
        
        assert len(outcome.actors) == 0

    def test_npc_not_in_context_distances_gets_default(self):
        """NPC без записи в distances не падает, получает дефолт."""
        builder = SceneOutcomeBuilder()
        
        decision = make_decision(npc_id="unknown_npc")
        context = make_context(distances={}, visible_npcs=set())
        
        # Не должно упасть
        outcome = builder.build([decision], context)
        
        assert len(outcome.actors) == 1
        assert outcome.actors[0].npc_id == "unknown_npc"

    def test_immutable_output(self):
        """SceneOutcome и вложенные структуры — frozen (иммутабельны)."""
        builder = SceneOutcomeBuilder()
        
        decision = make_decision(npc_id="test")
        outcome = builder.build([decision], make_context())
        
        # Попытка изменения должна вызвать FrozenInstanceError
        with pytest.raises(AttributeError):
            outcome.player.outcome = "hacked"
        
        with pytest.raises(AttributeError):
            outcome.tension.level = 999.0

    def test_visibility_confidence_default_is_1(self):
        """visibility_confidence по умолчанию = 1.0."""
        builder = SceneOutcomeBuilder()
        
        decision = make_decision(npc_id="test")
        outcome = builder.build([decision], make_context())
        
        assert outcome.actors[0].visibility_confidence == 1.0