"""
Файл: backend/tests/test_p7_06_faction_alignment.py
Назначение: Проверка начисления репутации и её ограничений.

Запуск: cd backend; python -m pytest tests/test_p7_06_faction_alignment.py -v -s; cd ..
"""

import pytest
from app.models.faction import FactionAlignment
from app.services.social.faction_alignment_tracker import FactionAlignmentTracker


class TestP706FactionAlignment:
    """P7-06: Тесты трекера фракционной лояльности."""

    @pytest.fixture
    def tracker(self) -> FactionAlignmentTracker:
        t = FactionAlignmentTracker()
        t.set_initial("thieves_guild", alignment=0.0)
        t.set_initial("city_guard", alignment=0.0)
        return t

    def test_initial_state(self, tracker: FactionAlignmentTracker):
        """Проверка базового состояния."""
        assert tracker.get_alignment("thieves_guild").alignment == 0.0
        assert tracker.get_alignment("thieves_guild").known_to_faction == False
        with pytest.raises(ValueError):
            tracker.set_initial("thieves_guild", 10.0)

    def test_apply_delta_updates_alignment(self, tracker: FactionAlignmentTracker):
        """Дельта обновляет лояльность."""
        # Игрок сдал вора страже
        tracker.apply_delta("city_guard", delta=20.0)
        tracker.apply_delta("thieves_guild", delta=-40.0)
        
        assert tracker.get_alignment("city_guard").alignment == 20.0
        assert tracker.get_alignment("thieves_guild").alignment == -40.0
        # Действия известны фракциям
        assert tracker.get_alignment("city_guard").known_to_faction == True

    def test_alignment_clamps_at_100(self, tracker: FactionAlignmentTracker):
        """Значения ограничиваются 100 и -100."""
        tracker.apply_delta("city_guard", delta=150.0)
        assert tracker.get_alignment("city_guard").alignment == 100.0
        
        tracker.apply_delta("thieves_guild", delta=-150.0)
        assert tracker.get_alignment("thieves_guild").alignment == -100.0

    def test_unknown_actions_do_not_reveal_player(self, tracker: FactionAlignmentTracker):
        """Действия с known=False не раскрывают игрока фракции."""
        tracker.apply_delta("thieves_guild", delta=-10.0, known=False)
        assert tracker.get_alignment("thieves_guild").alignment == -10.0
        assert tracker.get_alignment("thieves_guild").known_to_faction == False

    def test_validation_ranges(self):
        """Валидация диапазонов в модели."""
        with pytest.raises(ValueError):
            FactionAlignment(faction_id="test", alignment=101.0, known_to_faction=False)
        with pytest.raises(ValueError):
            FactionAlignment(faction_id="test", alignment=-101.0, known_to_faction=False)