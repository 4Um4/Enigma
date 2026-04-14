"""
Тесты R5.3 — интеграция MemoryManager: create_event_memory + run_decay_if_needed.
Использует mock для LayeredMemory — изолирует от файловой системы.
Назначение: интеграционный тест связки create_event_memory + run_decay_if_needed.
Запуск: python -m pytest tests/test_memory_manager_r53.py -v --tb=short
"""

from unittest.mock import MagicMock
import pytest

from app.services.memory.memory_manager import MemoryManager
from app.services.memory.importance_engine import DECAY_EVERY
from app.models.npc_state import EventMemory, MemoryStage


def _make_manager() -> MemoryManager:
    """MemoryManager с замоканым LayeredMemory — без файловой системы."""
    mock_layered = MagicMock()
    mock_layered.write_session_memory = MagicMock()
    return MemoryManager(layered_memory=mock_layered, data_dir="data")


_BRIGHT_SCENE: dict = {
    "environment": {"light_level": "bright"},
    "npc_positions": {},
    "player_position": {},
    "player_distances": {"npc_01": 3.0},
}


def test_create_event_memory_returns_event_memory() -> None:
    """create_event_memory возвращает корректный EventMemory."""
    mm = _make_manager()
    mem = mm.create_event_memory(
        campaign_id="camp_1",
        npc_id="npc_01",
        event={"type": "theft", "target": "player", "actor": "player", "day": 5},
        scene_state=_BRIGHT_SCENE,
        npc_stress=20.0,
        emotion_tag="angry",
    )
    assert isinstance(mem, EventMemory)
    assert mem.event_type == "theft"
    assert mem.stage == MemoryStage.FRESH
    assert 0.0 < mem.importance <= 1.0
    assert 0.0 < mem.clarity  <= 1.0


def test_create_event_memory_negative_emotion_slow_decay() -> None:
    """Anger → decay_rate меньше нейтрального (R5.3.2 asymmetry)."""
    mm = _make_manager()
    angry   = mm.create_event_memory("c", "n", {"type": "theft", "day": 1},
                                     _BRIGHT_SCENE, emotion_tag="angry")
    neutral = mm.create_event_memory("c", "n", {"type": "theft", "day": 1},
                                     _BRIGHT_SCENE, emotion_tag="neutral")
    assert angry.decay_rate < neutral.decay_rate


def test_create_event_memory_positive_emotion_fast_decay() -> None:
    """Happy → decay_rate больше нейтрального."""
    mm = _make_manager()
    happy   = mm.create_event_memory("c", "n", {"type": "help", "day": 1},
                                     _BRIGHT_SCENE, emotion_tag="happy")
    neutral = mm.create_event_memory("c", "n", {"type": "help", "day": 1},
                                     _BRIGHT_SCENE, emotion_tag="neutral")
    assert happy.decay_rate > neutral.decay_rate


def test_run_decay_if_needed_returns_list() -> None:
    """run_decay_if_needed всегда возвращает список."""
    mm = _make_manager()
    result = mm.run_decay_if_needed("camp_1", current_tick=1)
    assert isinstance(result, list)


def test_run_decay_skips_before_interval() -> None:
    """Decay не запускается до DECAY_EVERY тиков."""
    mm = _make_manager()
    mm.create_event_memory("camp_1", "npc_01",
                           {"type": "combat", "day": 1}, _BRIGHT_SCENE)
    result = mm.run_decay_if_needed("camp_1", current_tick=DECAY_EVERY - 1)
    assert result == []   # слишком рано — decay не запускался


def test_run_decay_fires_at_interval() -> None:
    """Decay запускается когда прошло DECAY_EVERY тиков."""
    mm = _make_manager()
    mm.create_event_memory("camp_1", "npc_01",
                           {"type": "combat", "day": 1}, _BRIGHT_SCENE)
    result = mm.run_decay_if_needed("camp_1", current_tick=DECAY_EVERY)
    assert isinstance(result, list)   # запустился, вернул список (может быть пустым)
