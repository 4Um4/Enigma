"""
Файл: backend/tests/test_p7_05_fate_tracker.py
Назначение: Проверка вычисления траекторий и триггеринга событий.
"""

import pytest
from app.models.fate import FateOutcome, FateTrajectory
from app.services.social.fate_tracker import FateTracker


class TestP705FateTracker:
    """P7-05: Тесты движка судеб."""

    @pytest.fixture
    def tracker(self) -> FateTracker:
        return FateTracker()

    def test_stable_trajectory(self, tracker: FateTracker):
        """Стабильное состояние: stability > 0.7, threat < 0.3."""
        state = tracker.update_state("maid_lusya", stability=0.8, threat=0.1)
        assert state.fate_trajectory == FateTrajectory.STABLE

    def test_critical_trajectory(self, tracker: FateTracker):
        """Критическое состояние: threat > 0.8, stability < 0.2."""
        state = tracker.update_state("maid_lusya", stability=0.1, threat=0.9)
        assert state.fate_trajectory == FateTrajectory.CRITICAL

    def test_deteriorating_trajectory(self, tracker: FateTracker):
        """Ухудшение: threat > 0.5."""
        state = tracker.update_state("maid_lusya", stability=0.5, threat=0.6)
        assert state.fate_trajectory == FateTrajectory.DETERIORATING

    def test_trigger_fate_requires_critical_state(self, tracker: FateTracker):
        """Смерть возможна только из критического состояния."""
        tracker.update_state("maid_lusya", stability=0.8, threat=0.1)
        with pytest.raises(ValueError, match="non-CRITICAL"):
            tracker.trigger_fate("maid_lusya", FateOutcome.DEATH, tick=1, cause="test", description="test")

    def test_trigger_fate_success(self, tracker: FateTracker):
        """Успешный триггер судьбы."""
        tracker.update_state("maid_lusya", stability=0.1, threat=0.9)
        event = tracker.trigger_fate("maid_lusya", FateOutcome.ESCAPE, tick=10, cause="guild_hunt", description="Люся сбегает")
        
        assert event.event_type == FateOutcome.ESCAPE
        assert event.tick == 10
        
        state = tracker.get_state("maid_lusya")
        assert state.resolved_fate == FateOutcome.ESCAPE
        assert state.fate_tick == 10

    def test_fate_is_irreversible(self, tracker: FateTracker):
        """Инвариант: Судьба необратима, нельзя триггерить повторно."""
        tracker.update_state("maid_lusya", stability=0.1, threat=0.9)
        tracker.trigger_fate("maid_lusya", FateOutcome.ESCAPE, tick=10, cause="test", description="test")
        
        with pytest.raises(ValueError, match="already resolved"):
            tracker.trigger_fate("maid_lusya", FateOutcome.DEATH, tick=15, cause="test2", description="test2")

    def test_validation_ranges(self, tracker: FateTracker):
        """Валидация диапазонов stability и threat."""
        with pytest.raises(ValueError):
            tracker.update_state("npc", stability=-0.1, threat=0.5)
        with pytest.raises(ValueError):
            tracker.update_state("npc", stability=0.5, threat=1.5)