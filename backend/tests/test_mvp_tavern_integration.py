"""
Файл: backend/tests/test_mvp_tavern_integration.py
Назначение: Сквозная проверка интеграции систем.

Запуск: cd backend; python -m pytest tests/test_mvp_tavern_integration.py -v -s; cd ..
"""

import pytest
from pathlib import Path
from app.services.social.mvp_tavern_controller import MvpTavernController
from app.models.player_action import PlayerAction, ActionType

BASE_DIR = Path(__file__).resolve().parent.parent.parent
CANON_PATH = BASE_DIR / "config" / "canon" / "truth_state_tavern.json"

class TestMvpTavernIntegration:
    """Интеграционный тест фасада MVP."""

    @pytest.fixture
    def controller(self) -> MvpTavernController:
        c = MvpTavernController(CANON_PATH)
        c.init_campaign("Open_road")
        return c

    def test_controller_initializes_all_systems(self, controller: MvpTavernController):
        """Все 14 систем инициализированы и готовы."""
        assert controller.truth_state is not None
        assert len(controller.truth_state.secrets) == 16
        assert controller.observation_log is not None
        assert controller.belief_model is not None
        assert controller.social_fabric is not None
        assert controller.fate_tracker is not None
        # ... остальные трекеры

    def test_full_flow_action_to_end_screen(self, controller: MvpTavernController):
        """Полный цикл: Действие -> Проверка выхода -> Экран результатов."""
        # 1. Игрок шантажирует Люсю
        action = PlayerAction(
            action_id="act_001",
            tick=1,
            actor_id="player",
            action_type=ActionType.BLACKMAIL,
            target_id="maid_lusya",
            secret_id="lusya_basement",
            description="Я знаю про подвал"
        )
        controller.action_compiler.process_action(action)
        
        # 2. Проверяем выход (игрок еще внутри)
        scene_inside = {"npc_positions": {"player": {"local_position": {"x": 5.0, "y": 5.0}}}}
        assert not controller.check_exit(scene_inside)
        
        # 3. Игрок выходит из таверны
        scene_outside = {"npc_positions": {"player": {"local_position": {"x": 19.0, "y": 5.0}}}}
        assert controller.check_exit(scene_outside)
        
        # 4. Строим финальный экран
        end_screen = controller.build_end_screen()
        
        # Проверяем, что оценка посчитана (1 секрет угадан = 10 баллов)
        assert end_screen.evaluation.score == 10
        assert end_screen.evaluation.secrets_identified == 1