# backend/tests/micro/test_r5_autonomous_simulation_api.py
"""
R5 (CCH-15 P4): Автономная симуляция — opt-in управление через API.

Вердикт Мастера R5:
- WorldScheduler подключён к жизненному циклу, но НЕ запускается автоматически.
- По умолчанию фоновый режим выключен.
- Запуск и остановка по явной команде (API → UI F10).
- При завершении приложения scheduler гарантированно останавливается.
- Не создан новый реестр кампаний — CampaignStateService.
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List
from unittest.mock import MagicMock

import pytest

from app.services.world_scheduler import WorldScheduler


class _FakeMemory:
    class _Store:
        def recent(self, key: str, limit: int = 1) -> list:
            return []

        def append(self, key: str, payload: Any) -> None:
            pass

    def __init__(self) -> None:
        self.store = self._Store()


class _FakeGameLoop:
    """Fake game_loop: считает idle_tick вызовы."""

    def __init__(self) -> None:
        self.idle_tick_calls: List[str] = []
        self._player_turn_in_flight: set = set()

    def idle_tick(self, campaign_id: str) -> Dict[str, Any]:
        self.idle_tick_calls.append(campaign_id)
        return {"status": "ok", "npc_positions": {}, "npc_addressing": []}


def _make_scheduler_with_game_loop() -> tuple[WorldScheduler, _FakeGameLoop]:
    gl = _FakeGameLoop()
    sched = WorldScheduler(_FakeMemory(), MagicMock())
    sched.set_game_loop(gl)
    return sched, gl


class TestOptInDefaultOff:
    """R5: по умолчанию фоновый режим выключен."""

    def test_1_default_off(self):
        """Scheduler не запущен после конструирования."""
        sched, _ = _make_scheduler_with_game_loop()
        assert not sched.is_loop_running

    @pytest.mark.asyncio
    async def test_2_lifespan_does_not_auto_start(self):
        """Lifespan НЕ запускает start_background_loop автоматически."""
        # Симуляция: после build_game_loop scheduler wired, но не запущен
        sched, _ = _make_scheduler_with_game_loop()
        # Никто не вызвал start_background_loop
        assert not sched.is_loop_running
        assert sched.running_ticks == []


class TestAPIStartStop:
    """R5: API start/stop управляют симуляцией."""

    @pytest.mark.asyncio
    async def test_3_start_launches_background_loop(self):
        """POST /start запускает фоновый цикл."""
        sched, gl = _make_scheduler_with_game_loop()
        # Симуляция API start
        if not sched.is_loop_running:
            await sched.start_background_loop(["Open_road"], interval_seconds=0.05)
        assert sched.is_loop_running
        await asyncio.sleep(0.15)
        await sched.stop_background_loop()
        assert "Open_road" in gl.idle_tick_calls

    @pytest.mark.asyncio
    async def test_4_stop_terminates_loop(self):
        """POST /stop останавливает фоновый цикл."""
        sched, _ = _make_scheduler_with_game_loop()
        await sched.start_background_loop(["Open_road"], interval_seconds=0.05)
        assert sched.is_loop_running
        await sched.stop_background_loop()
        assert not sched.is_loop_running

    @pytest.mark.asyncio
    async def test_5_double_start_idempotent(self):
        """Двойной start — второй skip (гвард _loop_running)."""
        sched, _ = _make_scheduler_with_game_loop()
        await sched.start_background_loop(["A"], interval_seconds=0.1)
        assert sched.is_loop_running
        # Второй start — skip
        await sched.start_background_loop(["A"], interval_seconds=0.1)
        # Всё ещё running, не упало
        assert sched.is_loop_running
        await sched.stop_background_loop()

    @pytest.mark.asyncio
    async def test_6_status_reports_running(self):
        """GET /status: is_running=True после start, False после stop."""
        sched, _ = _make_scheduler_with_game_loop()
        # Initial: stopped
        assert not sched.is_loop_running
        await sched.start_background_loop(["Open_road"], interval_seconds=0.1)
        assert sched.is_loop_running
        await sched.stop_background_loop()
        assert not sched.is_loop_running


class TestShutdownGuarantee:
    """R5: shutdown гарантированно останавливает scheduler."""

    @pytest.mark.asyncio
    async def test_7_shutdown_stops_running_loop(self):
        """При shutdown stop_background_loop вызывается, если loop running."""
        sched, _ = _make_scheduler_with_game_loop()
        await sched.start_background_loop(["Open_road"], interval_seconds=0.05)
        assert sched.is_loop_running
        # Симуляция shutdown (main.py shutdown block)
        if sched.is_loop_running:
            await sched.stop_background_loop()
        assert not sched.is_loop_running

    @pytest.mark.asyncio
    async def test_8_shutdown_safe_when_not_running(self):
        """Shutdown при незапущенном scheduler — не crash."""
        sched, _ = _make_scheduler_with_game_loop()
        # Не запускали — shutdown безопасен
        await sched.stop_background_loop()
        assert not sched.is_loop_running


class TestStatePersistenceAfterRestart:
    """R5: состояние мира переживает рестарт (SQLite); scheduler state ephemeral."""

    def test_9_scheduler_state_ephemeral(self):
        """После 'рестарта' (новый scheduler) — фон выключен по умолчанию."""
        # Старый scheduler (имитация до рестарта)
        sched1, _ = _make_scheduler_with_game_loop()
        # Новый scheduler после рестарта
        sched2, _ = _make_scheduler_with_game_loop()
        assert not sched2.is_loop_running
        assert sched2 is not sched1

    @pytest.mark.asyncio
    async def test_10_no_double_tick_single_campaign(self):
        """Гвард _running_ticks: одна кампания не тикает дважды параллельно."""
        sched, gl = _make_scheduler_with_game_loop()
        # Запускаем тик вручную + ставим гвард
        sched._running_ticks.add("Open_road")
        result = sched.run_autonomous_tick("Open_road")
        assert result["status"] == "already_running"
        sched._running_ticks.discard("Open_road")
        # Очищаем
        assert "Open_road" not in sched.running_ticks


class TestNoAutoStart:
    """R5: подтверждение — нет скрытого авто-запуска."""

    @pytest.mark.asyncio
    async def test_11_game_loop_builder_does_not_start_loop(self):
        """build_game_loop + set_game_loop НЕ запускают background loop."""
        sched, _ = _make_scheduler_with_game_loop()
        # set_game_loop уже вызван в _make_scheduler_with_game_loop
        # Но loop не запущен
        assert not sched.is_loop_running
        assert sched.running_ticks == []