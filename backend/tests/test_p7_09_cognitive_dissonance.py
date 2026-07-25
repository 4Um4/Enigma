"""
Файл: backend/tests/test_p7_09_cognitive_dissonance.py
Назначение: Проверка обнаружения противоречий.

Запуск: cd backend; python -m pytest tests/test_p7_09_cognitive_dissonance.py -v -s; cd ..
"""

import pytest
from app.models.player_action import ActionType, PlayerAction
from app.services.player_cognition.cognitive_dissonance_tracker import CognitiveDissonanceTracker


class TestP709CognitiveDissonance:
    """P7-09: Тесты трекера когнитивного диссонанса."""

    @pytest.fixture
    def tracker(self) -> CognitiveDissonanceTracker:
        return CognitiveDissonanceTracker()

    @pytest.fixture
    def base_actions(self) -> list:
        return [
            PlayerAction(action_id="act_1", tick=1, actor_id="player", action_type=ActionType.HELP, target_id="maid_lusya"),
            PlayerAction(action_id="act_2", tick=2, actor_id="player", action_type=ActionType.ATTACK, target_id="merchant_goran"),
            PlayerAction(action_id="act_3", tick=3, actor_id="player", action_type=ActionType.BLACKMAIL, target_id="guard_borko")
        ]

    def test_no_contradictions_in_consistent_actions(self, tracker):
        """Нет противоречий, если игрок последователен."""
        actions = [
            PlayerAction(action_id="a1", tick=1, actor_id="p", action_type=ActionType.HELP, target_id="npc1"),
            PlayerAction(action_id="a2", tick=2, actor_id="p", action_type=ActionType.HELP, target_id="npc2")
        ]
        contradictions = tracker.detect_contradictions(actions)
        assert len(contradictions) == 0
        assert not tracker.has_critical_dissonance

    def test_contradiction_detected_help_vs_attack(self, tracker, base_actions):
        """Обнаруживается противоречие HELP + ATTACK."""
        contradictions = tracker.detect_contradictions(base_actions)
        # HELP(Lusya) + ATTACK(Goran) -> 0.8
        # HELP(Lusya) + BLACKMAIL(Borko) -> 0.7
        assert len(contradictions) == 2
        assert contradictions[0].emotional_weight == 0.8

    def test_idempotency(self, tracker, base_actions):
        """Повторный анализ тех же действий не создаёт дублей."""
        tracker.detect_contradictions(base_actions)
        initial_count = len(tracker.get_all_contradictions())
        
        tracker.detect_contradictions(base_actions)
        assert len(tracker.get_all_contradictions()) == initial_count

    def test_critical_dissonance_threshold(self, tracker, base_actions):
        """3+ противоречий вызывают критический диссонанс."""
        # Добавим ещё одно действие для 3-го противоречия
        actions = base_actions + [
            PlayerAction(action_id="act_4", tick=4, actor_id="player", action_type=ActionType.BRIBE, target_id="tavern_keeper_tornin")
        ]
        # HELP + ATTACK (0.8)
        # HELP + BLACKMAIL (0.7)
        # ATTACK + BRIBE (0.5)
        tracker.detect_contradictions(actions)
        assert len(tracker.get_all_contradictions()) >= 3
        assert tracker.has_critical_dissonance

    def test_validation_emotional_weight(self):
        """Валидация веса противоречия."""
        from app.models.cognitive_dissonance import Contradiction
        with pytest.raises(ValueError):
            Contradiction(contradiction_id="c1", action_a_id="a", action_b_id="b", description="d", emotional_weight=1.5)