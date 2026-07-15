"""
path: backend/tests/sandbox/invariants/test_temporal_invariants.py
Назначение: Защита Закона Единичного Времени (§14) и Изоляции Реального Времени (§15).
Статус: Обязательный барьер безопасности.

Запуск: cd backend; python -m pytest tests/sandbox/invariants/test_temporal_invariants.py -v; cd ..
"""

from unittest.mock import MagicMock, patch

import pytest
from app.domain.identity_events import EffectiveDrives

_MOCK_DRIVES = EffectiveDrives.from_dict({"control": 0.5, "significance": 0.5, "fear": 0.5, "desire": 0.5})

from app.core.constants import GAME_TICK_INTERVAL_SECONDS
from app.domain.tick import TickResultDTO
from app.services.world.time_skip_executor import TimeSkipExecutor


@pytest.fixture
def initial_scene_state():
    return {"tick": 0, "game_time_seconds": 0, "prev_game_time_seconds": 0, "environment": {"time_of_day": "00:00"}}


@pytest.fixture
def time_skip_executor():
    """TimeSkipExecutor с замоканным ядром, которое только продвигает время."""
    kernel = MagicMock()

    def mock_execute(campaign_id, scene_state, tick_number, spatial_service, npc_services):
        # Эмуляция _advance_time из TickOrchestrator
        current_time = scene_state.get("game_time_seconds", 0)
        new_time = current_time + GAME_TICK_INTERVAL_SECONDS
        scene_state["game_time_seconds"] = new_time
        scene_state["prev_game_time_seconds"] = current_time

        # Возвращаем пустой результат
        return TickResultDTO(status="OK", world_snapshot={}, npc_contexts={}, significant_events=[])

    kernel.execute.side_effect = mock_execute
    return TimeSkipExecutor(kernel)


def get_npcs_callback(campaign_id):
    """Заглушка SSOT-колбэка для TimeSkipExecutor."""
    return []


def test_time_skip_policy_a_determinism(time_skip_executor, initial_scene_state):
    """
    Policy A (клавиша 1): Headless batch.
    Время должно продвинуться строго на N * GAME_TICK_INTERVAL_SECONDS.
    """
    ticks_to_skip = 5
    result = time_skip_executor.skip(
        campaign_id="test",
        scene_state=initial_scene_state,
        ticks=ticks_to_skip,
        policy="A",
        get_npcs_callback=get_npcs_callback,
    )

    expected_time = ticks_to_skip * GAME_TICK_INTERVAL_SECONDS
    assert result.final_state["game_time_seconds"] == expected_time, (
        f"Policy A Time drift! Expected {expected_time}, got {result.final_state['game_time_seconds']}"
    )


def test_time_skip_policy_b_determinism(time_skip_executor, initial_scene_state):
    """
    Policy B (клавиша 2): Stop on significance.
    Даже если полисик остановится раньше, время должно соответствовать количеству пройденных тиков.
    """
    # Policy B может остановиться раньше. Прогоняем 10 тиков.
    # Детектор значимости пуст, поэтому пройдёт все 10.
    ticks_to_skip = 10
    result = time_skip_executor.skip(
        campaign_id="test",
        scene_state=initial_scene_state,
        ticks=ticks_to_skip,
        policy="B",
        get_npcs_callback=get_npcs_callback,
    )

    expected_time = result.ticks_skipped * GAME_TICK_INTERVAL_SECONDS
    assert result.final_state["game_time_seconds"] == expected_time, (
        f"Policy B Time drift! Expected {expected_time}, got {result.final_state['game_time_seconds']}"
    )


def test_time_skip_policy_c_determinism(time_skip_executor, initial_scene_state):
    """
    Policy C (клавиша 3): Milestone sampling.
    Время должно продвинуться на запрошенное количество тиков.
    """
    ticks_to_skip = 3
    result = time_skip_executor.skip(
        campaign_id="test",
        scene_state=initial_scene_state,
        ticks=ticks_to_skip,
        policy="C",
        get_npcs_callback=get_npcs_callback,
        context={"child_id": "test_child"},  # Policy C требует контекст
    )

    expected_time = result.ticks_skipped * GAME_TICK_INTERVAL_SECONDS
    assert result.final_state["game_time_seconds"] == expected_time, (
        f"Policy C Time drift! Expected {expected_time}, got {result.final_state['game_time_seconds']}"
    )


def test_wall_clock_isolation_under_extreme_drift(time_skip_executor, initial_scene_state):
    """
    §15.1 Инвариант: Издевательства над wall-clock (time.time) НЕ должны влиять на game_time_seconds.
    """
    # Подменяем time.time на функцию, которая возвращает хаотичные огромные значения
    with patch("time.time", side_effect=[10**9, 10**10, 10**11, 10**12, 10**13, 10**14]):
        ticks_to_skip = 5
        result = time_skip_executor.skip(
            campaign_id="test",
            scene_state=initial_scene_state,
            ticks=ticks_to_skip,
            policy="A",
            get_npcs_callback=get_npcs_callback,
        )

        expected_time = ticks_to_skip * GAME_TICK_INTERVAL_SECONDS
        assert result.final_state["game_time_seconds"] == expected_time, (
            "Wall-clock leak detected! game_time_seconds changed due to time.time() manipulation."
        )
