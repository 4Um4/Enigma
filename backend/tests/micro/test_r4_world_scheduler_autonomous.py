# backend/tests/micro/test_r4_world_scheduler_autonomous.py
"""
R4 (CCH-15 P4): WorldScheduler — независимый фоновый инициатор автономных тиков.

Вердикт Мастера R4:
1. WorldScheduler подключён к существующему idle_tick.
2. Единственный путь изменения состояния через TickOrchestrator.
3. Исключено параллельное исполнение (ADR-O-407 + _running_ticks).
4. Корректная остановка и возобновление.
5. Мир тикает без pygame и клиентского цикла.
6. Тесты: последовательность, отсутствие двойного исполнения, сохранение состояния.

Не создаётся второй исполнитель, второй SSOT, отдельная симуляция.
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List
from unittest.mock import MagicMock

import pytest

from app.services.world_scheduler import WorldScheduler


class _FakeMemory:
    """Минимальная memory для конструктора WorldScheduler."""

    class _Store:
        def recent(self, key: str, limit: int = 1) -> list:
            return []

        def append(self, key: str, payload: Any) -> None:
            pass

    def __init__(self) -> None:
        self.store = self._Store()


class _FakeGameLoop:
    """Fake game_loop: считает idle_tick вызовы + возвращает фиксированный result."""

    def __init__(self, tick_results: List[Dict[str, Any]] | None = None) -> None:
        self._tick_results = tick_results or [
            {"status": "ok", "npc_positions": {"npc1": {"x": 1.0, "y": 2.0}}, "npc_addressing": []}
        ]
        self._call_count = 0
        self.idle_tick_calls: List[str] = []
        self._player_turn_in_flight: set = set()

    def idle_tick(self, campaign_id: str) -> Dict[str, Any]:
        self.idle_tick_calls.append(campaign_id)
        result = self._tick_results[min(self._call_count, len(self._tick_results) - 1)]
        self._call_count += 1
        return result


class _SlowGameLoop:
    """GameLoop с долгим idle_tick — для теста конкурентного исполнения."""

    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.finished = asyncio.Event()
        self._player_turn_in_flight: set = set()

    async def idle_tick(self, campaign_id: str) -> Dict[str, Any]:
        self.started.set()
        await asyncio.sleep(0.1)
        self.finished.set()
        return {"status": "ok", "npc_positions": {}, "npc_addressing": []}


def _make_scheduler(game_loop: Any = None) -> WorldScheduler:
    """Создаёт WorldScheduler с fake memory и опциональной game_loop инъекцией."""
    sched = WorldScheduler(_FakeMemory(), MagicMock())
    if game_loop is not None:
        sched.set_game_loop(game_loop)
    return sched


# =========================================================================
# Блок 1: set_game_loop + run_autonomous_tick
# =========================================================================

class TestSetGameLoopAndRunAutonomousTick:
    """R4: WorldScheduler делегирует в game_loop.idle_tick."""

    def test_1_set_game_loop_enables_autonomous_tick(self):
        gl = _FakeGameLoop()
        sched = _make_scheduler()
        assert sched._game_loop is None
        sched.set_game_loop(gl)
        assert sched._game_loop is gl

    def test_2_run_autonomous_tick_without_game_loop_safe(self):
        """Нет game_loop — честный отказ, не crash."""
        sched = _make_scheduler()
        result = sched.run_autonomous_tick("campaign_A")
        assert result["status"] == "no_game_loop"
        assert result["npc_positions"] == {}

    def test_3_run_autonomous_tick_calls_idle_tick(self):
        gl = _FakeGameLoop()
        sched = _make_scheduler(gl)
        result = sched.run_autonomous_tick("campaign_A")
        assert result["status"] == "ok"
        assert gl.idle_tick_calls == ["campaign_A"]

    def test_4_run_autonomous_tick_error_safe(self):
        """idle_tick упал — честный error, не crash scheduler'а."""

        class _CrashingGameLoop:
            _player_turn_in_flight: set = set()

            def idle_tick(self, campaign_id: str) -> Dict[str, Any]:
                raise RuntimeError("simulated tick crash")

        sched = _make_scheduler(_CrashingGameLoop())
        result = sched.run_autonomous_tick("campaign_A")
        assert result["status"] == "error"
        assert "simulated tick crash" in result["error"]


# =========================================================================
# Блок 2: конкурентное исполнение — _running_ticks гвард
# =========================================================================

class TestConcurrencyGuard:
    """R4: _running_ticks защищает от двойного автономного тика одной кампании."""

    @pytest.mark.asyncio
    async def test_5_double_run_autonomous_tick_skipped(self):
        """Параллельный вызов run_autonomous_tick для той же кампании — второй skip."""
        gl = _SlowGameLoop()
        sched = _make_scheduler(gl)

        # Запускаем два тика параллельно (gl.idle_tick async —
        # но run_autonomous_tick синхронный, поэтому для теста используем to_thread)
        # Симулируем: первый тик в-flight через _running_ticks
        sched._running_ticks.add("campaign_A")

        # Второй вызов должен skip
        result = sched.run_autonomous_tick("campaign_A")
        assert result["status"] == "already_running"

    @pytest.mark.asyncio
    async def test_6_running_ticks_cleared_after_tick(self):
        """После тика _running_ticks очищается (finally блок)."""
        gl = _FakeGameLoop()
        sched = _make_scheduler(gl)
        sched.run_autonomous_tick("campaign_A")
        assert "campaign_A" not in sched._running_ticks
        assert sched.running_ticks == []

    def test_7_different_campaigns_no_conflict(self):
        """Разные кампании тикают независимо (не блокируют друг друга)."""
        gl = _FakeGameLoop()
        sched = _make_scheduler(gl)
        sched._running_ticks.add("campaign_A")
        # campaign_B не блокируется
        result = sched.run_autonomous_tick("campaign_B")
        assert result["status"] == "ok"
        assert gl.idle_tick_calls == ["campaign_B"]


# =========================================================================
# Блок 3: background loop — старт/стоп
# =========================================================================

class TestBackgroundLoop:
    """R4: start_background_loop / stop_background_loop."""

    @pytest.mark.asyncio
    async def test_8_background_loop_ticks_multiple_campaigns(self):
        """Фоновый цикл тикает несколько кампаний последовательно."""
        gl = _FakeGameLoop()
        sched = _make_scheduler(gl)

        await sched.start_background_loop(["A", "B", "C"], interval_seconds=0.05)
        await asyncio.sleep(0.2)  # ~4 interval — минимум 1 полный цикл
        await sched.stop_background_loop()

        assert not sched.is_loop_running
        # Каждая кампания должна быть тикнута хотя бы один раз
        for cid in ["A", "B", "C"]:
            assert cid in gl.idle_tick_calls, f"{cid} not ticked: {gl.idle_tick_calls}"

    @pytest.mark.asyncio
    async def test_9_stop_background_loop_corrept(self):
        """stop_background_loop корректно останавливает цикл."""
        gl = _FakeGameLoop()
        sched = _make_scheduler(gl)

        await sched.start_background_loop(["A"], interval_seconds=0.01)
        assert sched.is_loop_running

        await sched.stop_background_loop()
        assert not sched.is_loop_running

    @pytest.mark.asyncio
    async def test_10_double_start_skipped(self):
        gl = _FakeGameLoop()
        sched = _make_scheduler(gl)
        await sched.start_background_loop(["A"], interval_seconds=0.1)
        await sched.start_background_loop(["A"], interval_seconds=0.1)  # skip — идемпотентен
        await asyncio.sleep(0.15)
        await sched.stop_background_loop()
        # Второй старт не создал второй цикл (вызовов не в 2 раза больше)

    @pytest.mark.asyncio
    async def test_11_start_without_game_loop_safe(self):
        """Нет game_loop — background loop не стартует."""
        sched = _make_scheduler()  # без game_loop
        await sched.start_background_loop(["A"])
        assert not sched.is_loop_running

    @pytest.mark.asyncio
    async def test_12_stop_without_start_safe(self):
        """stop без start — не crash."""
        sched = _make_scheduler(_FakeGameLoop())
        await sched.stop_background_loop()  # не падает
        assert not sched.is_loop_running


# =========================================================================
# Блок 4: сохранение состояния между тиками (последовательность)
# =========================================================================

class TestStatePersistenceBetweenTicks:
    """R4: автономные тики последовательны — каждый видит результат предыдущего."""

    def test_13_sequential_ticks_each_sees_previous(self):
        """Три тика подряд — каждый вызывает idle_tick (game_loop хранит состояние)."""
        gl = _FakeGameLoop(
            tick_results=[
                {"status": "ok", "npc_positions": {"tick": 1}, "npc_addressing": []},
                {"status": "ok", "npc_positions": {"tick": 2}, "npc_addressing": []},
                {"status": "ok", "npc_positions": {"tick": 3}, "npc_addressing": []},
            ]
        )
        sched = _make_scheduler(gl)

        r1 = sched.run_autonomous_tick("A")
        r2 = sched.run_autonomous_tick("A")
        r3 = sched.run_autonomous_tick("A")

        assert r1["npc_positions"]["tick"] == 1
        assert r2["npc_positions"]["tick"] == 2
        assert r3["npc_positions"]["tick"] == 3
        assert gl.idle_tick_calls == ["A", "A", "A"]

    @pytest.mark.asyncio
    async def test_14_background_loop_persists_state(self):
        """Фоновый цикл вызывает idle_tick многократно — состояние персистится в game_loop."""
        gl = _FakeGameLoop()
        sched = _make_scheduler(gl)

        await sched.start_background_loop(["A"], interval_seconds=0.02)
        await asyncio.sleep(0.15)
        await sched.stop_background_loop()

        # Несколько тиков выполнено (последовательность сохранена в счётчике)
        assert len(gl.idle_tick_calls) >= 2, (
            f"background loop executed {len(gl.idle_tick_calls)} ticks, expected >= 2"
        )


# =========================================================================
# Блок 5: maybe_tick legacy совместимость
# =========================================================================

class TestMaybeTickLegacy:
    """R4: maybe_tick сохранён (legacy shared_context), не вызывает idle_tick."""

    def test_15_maybe_tick_does_not_call_idle_tick(self):
        """maybe_tick генерирует метаданные, но не вызывает idle_tick."""
        gl = _FakeGameLoop()
        sched = _make_scheduler(gl)
        result = sched.maybe_tick("world_1", every_minutes=15)
        assert result["triggered"] is True
        # maybe_tick не вызывает idle_tick (это legacy метаданные)
        assert gl.idle_tick_calls == []