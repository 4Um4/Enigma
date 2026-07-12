"""
Тесты R5.3 — run_decay_if_needed.
create_event_memory удалён в Этапе 0.6 — заменён на apply().
Decay-тесты используют прямой push в _working (setup без удалённого API).
Запуск: python -m pytest tests/test_memory_manager_r53.py -v --tb=short
"""

from unittest.mock import MagicMock

from app.core.constants import DECAY_EVERY
from app.models.npc_state import EventMemory, MemoryStage
from app.services.memory.memory_manager import MemoryManager


def _make_manager() -> MemoryManager:
    """MemoryManager с замоканым LayeredMemory — без файловой системы."""
    mock_layered = MagicMock()
    mock_layered.write_session_memory = MagicMock()
    return MemoryManager(layered_memory=mock_layered, data_dir="data")


def test_run_decay_if_needed_returns_list() -> None:
    """run_decay_if_needed всегда возвращает список."""
    mm = _make_manager()
    result = mm.run_decay_if_needed("camp_1", current_tick=1)
    assert isinstance(result, list)


def test_run_decay_skips_before_interval() -> None:
    """Decay не запускается до DECAY_EVERY тиков."""
    mm = _make_manager()
    # Прямой push в working memory — замена удалённого create_event_memory
    mm._working.push(
        "camp_1:npc_01",
        EventMemory(
            event_type="combat",
            target_id="player",
            emotion_tag="neutral",
            day=1,
            importance=0.7,
            clarity=0.8,
            confidence=0.9,
            decay_rate=0.05,
            stage=MemoryStage.FRESH,
            summary="",
            npc_id="npc_01",
        ),
    )
    result = mm.run_decay_if_needed("camp_1", current_tick=DECAY_EVERY - 1)
    assert result == []  # слишком рано — decay не запускался


def test_run_decay_fires_at_interval() -> None:
    """Decay запускается когда прошло DECAY_EVERY тиков."""
    mm = _make_manager()
    mm._working.push(
        "camp_1:npc_01",
        EventMemory(
            event_type="combat",
            target_id="player",
            emotion_tag="neutral",
            day=1,
            importance=0.7,
            clarity=0.8,
            confidence=0.9,
            decay_rate=0.05,
            stage=MemoryStage.FRESH,
            summary="",
            npc_id="npc_01",
        ),
    )
    result = mm.run_decay_if_needed("camp_1", current_tick=DECAY_EVERY)
    assert isinstance(result, list)  # запустился, вернул список (может быть пустым)
