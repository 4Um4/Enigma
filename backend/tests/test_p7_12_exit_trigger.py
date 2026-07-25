"""
Файл: backend/tests/test_p7_12_exit_trigger.py
Назначение: Проверка срабатывания триггера.

Запуск: cd backend; python -m pytest tests/test_p7_12_exit_trigger.py -v -s; cd ..
"""

import pytest
from app.services.social.exit_trigger import ExitTrigger


class TestP712ExitTrigger:
    """P7-12: Тесты триггера выхода."""

    @pytest.fixture
    def trigger(self) -> ExitTrigger:
        return ExitTrigger()

    def test_no_exit_inside_tavern(self, trigger):
        """Игрок внутри — триггер не срабатывает."""
        scene = {"npc_positions": {"player": {"local_position": {"x": 5.0, "y": 5.0}}}}
        assert not trigger.check_exit(scene)

    def test_exit_boundary_exact_threshold(self, trigger):
        """Граничное условие: x = 18.0 (>= threshold) даёт True."""
        scene = {"npc_positions": {"player": {"local_position": {"x": 18.0, "y": 5.0}}}}
        assert trigger.check_exit(scene)

    def test_exit_triggered_outside(self, trigger):
        """Игрок снаружи — триггер срабатывает."""
        scene = {"npc_positions": {"player": {"local_position": {"x": 19.0, "y": 5.0}}}}
        assert trigger.check_exit(scene)

    def test_no_exit_missing_player(self, trigger):
        """Нет игрока в сцене — триггер не падает."""
        scene = {"npc_positions": {}}
        assert not trigger.check_exit(scene)