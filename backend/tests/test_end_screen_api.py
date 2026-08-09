"""
Файл: backend/tests/test_end_screen_api.py
Назначение: Тест контракта EndScreenData для фронтенд-рендерера.
Запуск: cd backend; python -m pytest tests/test_end_screen_api.py -v; cd ..
"""

import pytest
from pathlib import Path
from app.services.social.mvp_tavern_controller import MvpTavernController
from app.models.player_action import PlayerAction, ActionType

BASE_DIR = Path(__file__).resolve().parent.parent.parent
CANON_PATH = BASE_DIR / "config" / "canon" / "truth_state_tavern.json"

class TestEndScreenApiContract:
    """Проверяет, что бэкенд отдаёт JSON-структуру, ожидаемую фронтендом."""

    @pytest.fixture
    def controller(self) -> MvpTavernController:
        c = MvpTavernController(CANON_PATH)
        c.init_campaign("Open_road")
        return c

    def test_end_screen_contract_fields(self, controller: MvpTavernController):
        """Тест: EndScreenData содержит все поля, нужные для отрисовки UI."""
        # Симулируем действие игрока (шантаж Люси подвалом)
        action = PlayerAction(
            action_id="test_act_01",
            tick=1,
            actor_id="player",
            action_type=ActionType.BLACKMAIL,
            target_id="maid_lusya",
            secret_id="lusya_basement",
            description="Я знаю про подвал"
        )
        controller.action_compiler.process_action(action)
        
        # Выходим из таверны
        scene_outside = {"npc_positions": {"player": {"local_position": {"x": 5.0, "y": 15.0}}}}
        assert controller.check_exit(scene_outside)
        
        # Вызываем метод, который отдаёт routes.py
        end_screen = controller.build_end_screen()
        ev = end_screen.evaluation
        
        # Проверяем поля, которые routes.py сереализует в JSON для фронтенда
        assert isinstance(ev.score, int)
        assert 0 <= ev.score <= 100
        assert ev.secrets_total == 17
        assert ev.secrets_identified == 1
        assert ev.secrets_misidentified == 0
        assert ev.secrets_missed == 16
        assert "blackmail" in ev.methods_used
        assert ev.methods_used["blackmail"] == 1
