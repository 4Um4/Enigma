"""
End-to-end canary: симулирует действия игрока и проверяет End-Screen.
Ловит M-04 (пустой End-Screen), M-02 (discovered_secrets), M-07/M-08 (evidence).

path: /project/backend/tests/canary/test_full_playthrough.py
Назначение: End-to-end canary тест MVP-цикла (§3.1 ENIGMA_SELF_HEALING_SYSTEM).
Зависимости: pytest, MvpTavernController.
Основные сущности: test_full_playthrough_end_screen_non_empty

Запуск: cd backend; python -m pytest tests/canary/test_full_playthrough.py -v; cd ..
"""
import pytest
from pathlib import Path
from app.core.config import BASE_DIR
from app.services.social.mvp_tavern_controller import MvpTavernController
from app.models.player_action import PlayerAction, ActionType
from app.services.events.event_bus import EventBus

@pytest.fixture
def mvp_controller():
    canon_path = BASE_DIR / "config" / "canon" / "truth_state_tavern.json"
    if not canon_path.exists():
        pytest.skip(f"Canon file not found at {canon_path}")
    
    bus = EventBus()
    controller = MvpTavernController(canon_path, event_bus=bus)
    controller.init_campaign("test_canary")
    return controller

def test_full_playthrough_end_screen_non_empty(mvp_controller):
    """Симулируем 5 тиков и 2 действия с секретами, проверяем End-Screen."""
    mvp = mvp_controller
    
    # 1. Симулируем 5 тиков
    # (В реальном тесте здесь был бы idle_tick, но мы тестируем логику MVP напрямую)
    
    # 2. Игрок раскрывает секрет Борко через шантаж
    action_bribe = PlayerAction(
        action_id="act_1",
        tick=1,
        actor_id="player",
        action_type=ActionType.BLACKMAIL,
        target_id="guard_borko",
        secret_id="borko_voyeur",
        description="Я знаю, что ты подглядываешь."
    )
    mvp.action_compiler.process_action(action_bribe)
    
    # 3. Игрок помогает Орму
    action_help = PlayerAction(
        action_id="act_2",
        tick=2,
        actor_id="player",
        action_type=ActionType.HELP,
        target_id="blacksmith_orm",
        description="Вот тебе денег на долг."
    )
    mvp.action_compiler.process_action(action_help)

    # V8-MVP-7: Игрок говорит без target, но с ключевым словом секрета
    action_dialogue = PlayerAction(
        action_id="act_3",
        tick=3,
        actor_id="player",
        action_type=ActionType.DIALOGUE,
        target_id="", # БЕЗ TARGET!
        secret_id="tornin_debt",
        description="Торнин, у тебя долги перед гильдией?"
    )
    mvp.action_compiler.process_action(action_dialogue)
    
    # 4. Проверяем End-Screen
    end_screen = mvp.build_end_screen()
    
    # M-04: End-Screen должен существовать
    assert end_screen is not None, "End-Screen is None"
    
    # M-02: Должен быть раскрыт хотя бы 1 секрет
    # (В текущей реализации это может быть пусто, если M-02 не реализован)
    # Ожидаем, что тест упадёт, если M-02 не починен.
    assert mvp.truth_state is not None, "TruthState is None"
    assert len(mvp.truth_state.discovered_secrets) >= 2, (
        f"Expected >=2 discovered secrets, got {len(mvp.truth_state.discovered_secrets)}. "
        "Check M-02 (discovered_secrets Set), M-07/M-08 (evidence), V8-MVP-7 (dialogue without target)."
    )
    
    # M-03: Fate tracker должен иметь состояния (обновляется через TICK_COMPLETED)
    # В этом тесте мы не запускали тики, поэтому проверяем только наличие трекера
    assert mvp.fate_tracker is not None, "FateTracker is None"
    
    print(f"[CANARY] End-Screen built. Secrets discovered: {len(mvp.truth_state.discovered_secrets)}")