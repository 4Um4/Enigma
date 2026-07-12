"""
Этап 8 — затухание привязано к игровому времени.
Проверяет: decayed(game_days), apply_decay(game_days), run_decay_if_needed(game_days).

path: backend/tests/test_decay_game_days_stage8.py
Назначение: Тесты Этапа 8 — decay по игровым дням
Зависимости: EventMemory, WorkingMemory, MemoryManager
Основные сущности: decayed(game_days=...), apply_decay(game_days=...), run_decay_if_needed(game_days=...)
Задача: Убедиться, что decay теперь зависит от игровых дней, а не от тиков, и что контрактные события затухают медленнее.
Затухание по формуле: importance * exp(-decay_rate * game_days)

python -m pytest backend/tests/test_decay_game_days_stage8.py -v --tb=short 2>&1 | Select-Object -Last 20
"""

import math

import pytest
from app.models.npc_state import EventMemory
from app.services.memory.memory_manager import MemoryManager
from app.services.memory.working_memory import WorkingMemory


def _make_mem(importance: float = 0.9, decay_rate: float = 0.05) -> EventMemory:
    return EventMemory(
        event_type="theft",
        target_id="player",
        emotion_tag="angry",
        day=1,
        importance=importance,
        decay_rate=decay_rate,
        clarity=0.9,
        confidence=0.9,
    )


# ── 8.1-8.2: decayed(game_days) ──


def test_decayed_uses_game_days_not_ticks() -> None:
    """Формула: importance × exp(-decay_rate × game_days)."""
    mem = _make_mem(importance=0.8, decay_rate=0.05)
    decayed = mem.decayed(game_days=3.0)
    expected = round(0.8 * math.exp(-0.05 * 3.0), 4)
    assert decayed.importance == pytest.approx(expected, abs=1e-3)


def test_decayed_fractional_days() -> None:
    """Полдня — дробное значение."""
    mem = _make_mem(importance=0.9, decay_rate=0.1)
    decayed = mem.decayed(game_days=0.5)
    expected = round(0.9 * math.exp(-0.1 * 0.5), 4)
    assert decayed.importance == pytest.approx(expected, abs=1e-3)


def test_decayed_accessibility_decays_slower() -> None:
    """Accessibility затухает медленнее importance (×0.3 множитель)."""
    mem = _make_mem(importance=0.9, decay_rate=0.1)
    decayed = mem.decayed(game_days=1.0)
    # importance множитель: exp(-0.1)
    # accessibility множитель: exp(-0.1 * 0.3) = exp(-0.03)
    assert decayed.accessibility > decayed.importance


def test_decayed_100_days_heavy_decay() -> None:
    """100 игровых дней — событие почти забыто."""
    mem = _make_mem(importance=0.6, decay_rate=0.05)
    decayed = mem.decayed(game_days=100.0)
    assert decayed.importance < 0.05


# ── 8.3: run_decay_if_needed(game_days) ──


def _make_manager() -> MemoryManager:
    from unittest.mock import MagicMock

    mm = MemoryManager.__new__(MemoryManager)
    mm._working = WorkingMemory(maxlen=20)
    mm._layered = MagicMock()
    mm._relationship = MagicMock()
    mm._resonance = MagicMock()
    mm._dialogue = MagicMock()
    mm._tick_counters = {}
    return mm


def test_run_decay_passes_game_days() -> None:
    """run_decay_if_needed передаёт game_days в apply_decay."""
    mm = _make_manager()
    mem = _make_mem(importance=0.9, decay_rate=0.05)
    mm._working.push("camp_1:npc_01", mem)

    # DECAY_EVERY = 10, передаём tick=10 чтобы триггер сработал
    from app.services.memory.importance_engine import DECAY_EVERY

    mm.run_decay_if_needed("camp_1", current_tick=DECAY_EVERY, game_days=2.5)

    updated = mm._working.get("camp_1:npc_01")
    assert len(updated) == 1
    expected = round(0.9 * math.exp(-0.05 * 2.5), 4)
    assert updated[0].importance == pytest.approx(expected, abs=1e-3)


def test_run_decay_default_game_days_one() -> None:
    """game_days по умолчанию = 1.0 — backward-compatible."""
    mm = _make_manager()
    mem = _make_mem(importance=0.9, decay_rate=0.05)
    mm._working.push("camp_1:npc_01", mem)

    from app.services.memory.importance_engine import DECAY_EVERY

    mm.run_decay_if_needed("camp_1", current_tick=DECAY_EVERY)

    updated = mm._working.get("camp_1:npc_01")
    expected = round(0.9 * math.exp(-0.05 * 1.0), 4)
    assert updated[0].importance == pytest.approx(expected, abs=1e-3)


def test_run_decay_skips_before_interval() -> None:
    """До DECAY_EVERY тиков — decay не запускается."""
    mm = _make_manager()
    mem = _make_mem(importance=0.9, decay_rate=0.05)
    mm._working.push("camp_1:npc_01", mem)

    result = mm.run_decay_if_needed("camp_1", current_tick=5, game_days=10.0)
    assert result == []
    updated = mm._working.get("camp_1:npc_01")
    assert updated[0].importance == 0.9


# ── 8.4: контракты decay медленнее ──


def test_contract_decays_slower_than_normal() -> None:
    """Контрактное событие (decay_rate ×0.4) затухает медленнее обычного."""
    normal = _make_mem(importance=0.8, decay_rate=0.05)
    # Контракт: apply() умножает decay_rate на 0.4 → 0.02
    contract = _make_mem(importance=0.8, decay_rate=0.02)

    normal_decayed = normal.decayed(game_days=10.0)
    contract_decayed = contract.decayed(game_days=10.0)

    assert contract_decayed.importance > normal_decayed.importance
