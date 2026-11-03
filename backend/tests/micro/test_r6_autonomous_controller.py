# backend/tests/micro/test_r6_autonomous_controller.py
"""
R6 (CCH-15 P4): Контроллер автономной симуляции — state machine для F10.

Тестирует state machine БЕЗ pygame (pure logic).
Вердикт Мастера R6:
- F10 включает/выключает.
- Первое включение — предупреждение + подтверждение.
- Повторное F10 в PENDING = отмена.
- После рестарта — всегда INACTIVE (не персистится).
- Без F10 — никакой фоновой симуляции.
"""
from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

# Добавляем frontend в path (frontend — не пакет, но файлы там)
import sys
from pathlib import Path
_FRONTEND = Path(__file__).resolve().parents[3] / "frontend"
if str(_FRONTEND) not in sys.path:
    sys.path.insert(0, str(_FRONTEND))

from autonomous_simulation_controller import (
    AutonomousSimulationController,
    AutonomousState,
)


class _FakeGateway:
    """Fake GameGateway для тестов state machine."""
    def __init__(self) -> None:
        self.start_calls: list[str] = []
        self.stop_calls: list[str] = []
        self.status_returns: dict[str, dict] = {}

    def start_autonomous_simulation(self, campaign_id: str) -> dict:
        self.start_calls.append(campaign_id)
        return {"status": "started", "is_running": True}

    def stop_autonomous_simulation(self, campaign_id: str) -> dict:
        self.stop_calls.append(campaign_id)
        return {"status": "stopped", "is_running": False}

    def get_autonomous_simulation_status(self, campaign_id: str) -> dict:
        return self.status_returns.get(campaign_id, {"is_running": False})


class TestR6StateMachine:
    """R6: state machine transitions."""

    def test_1_default_inactive(self):
        """После создания — INACTIVE (opt-in, не персистится)."""
        gw = _FakeGateway()
        ctrl = AutonomousSimulationController(lambda: gw)
        assert ctrl.state == AutonomousState.INACTIVE
        assert not ctrl.is_active
        assert not ctrl.is_pending

    def test_2_f10_inactive_to_pending(self):
        """F10 из INACTIVE → PENDING (предупреждение)."""
        gw = _FakeGateway()
        ctrl = AutonomousSimulationController(lambda: gw)
        ctrl.handle_f10("Open_road")
        assert ctrl.state == AutonomousState.PENDING
        assert ctrl.is_pending
        assert ctrl.campaign_id == "Open_road"

    def test_3_f10_pending_to_inactive_cancel(self):
        """F10 из PENDING → INACTIVE (отмена)."""
        gw = _FakeGateway()
        ctrl = AutonomousSimulationController(lambda: gw)
        ctrl.handle_f10("Open_road")  # → PENDING
        ctrl.handle_f10("Open_road")  # → INACTIVE
        assert ctrl.state == AutonomousState.INACTIVE

    def test_4_confirm_pending_to_active(self):
        """confirm из PENDING → ACTIVE (API start вызывается)."""
        gw = _FakeGateway()
        ctrl = AutonomousSimulationController(lambda: gw)
        ctrl.handle_f10("Open_road")  # → PENDING
        ctrl.confirm()  # → ACTIVE
        assert ctrl.state == AutonomousState.ACTIVE
        assert ctrl.is_active
        # API start вызван (в worker thread — даём время)
        import time
        time.sleep(0.1)
        assert "Open_road" in gw.start_calls

    def test_5_cancel_pending_to_inactive(self):
        """cancel из PENDING → INACTIVE."""
        gw = _FakeGateway()
        ctrl = AutonomousSimulationController(lambda: gw)
        ctrl.handle_f10("Open_road")
        ctrl.cancel()
        assert ctrl.state == AutonomousState.INACTIVE

    def test_6_f10_active_to_inactive_stop(self):
        """F10 из ACTIVE → INACTIVE (API stop вызывается)."""
        gw = _FakeGateway()
        ctrl = AutonomousSimulationController(lambda: gw)
        ctrl.handle_f10("Open_road")
        ctrl.confirm()  # → ACTIVE
        ctrl.handle_f10("Open_road")  # → INACTIVE + stop
        assert ctrl.state == AutonomousState.INACTIVE
        import time
        time.sleep(0.1)
        assert "Open_road" in gw.stop_calls

    def test_7_confirm_in_inactive_noop(self):
        """confirm в INACTIVE — no-op."""
        gw = _FakeGateway()
        ctrl = AutonomousSimulationController(lambda: gw)
        ctrl.confirm()
        assert ctrl.state == AutonomousState.INACTIVE

    def test_8_no_api_calls_without_f10(self):
        """Без F10 — никакой фоновой симуляции (никаких API вызовов)."""
        gw = _FakeGateway()
        AutonomousSimulationController(lambda: gw)
        # Ничего не делаем
        assert gw.start_calls == []
        assert gw.stop_calls == []

    def test_9_campaign_change_stops_active(self):
        """При смене кампании — активная симуляция останавливается."""
        gw = _FakeGateway()
        ctrl = AutonomousSimulationController(lambda: gw)
        ctrl.handle_f10("Open_road")
        ctrl.confirm()  # ACTIVE
        ctrl.on_campaign_change("other_campaign")
        assert ctrl.state == AutonomousState.INACTIVE
        import time
        time.sleep(0.1)
        assert "Open_road" in gw.stop_calls

    def test_10_app_shutdown_stops_active(self):
        """При закрытии приложения — гарантированная остановка."""
        gw = _FakeGateway()
        ctrl = AutonomousSimulationController(lambda: gw)
        ctrl.handle_f10("Open_road")
        ctrl.confirm()
        ctrl.on_app_shutdown()
        assert ctrl.state == AutonomousState.INACTIVE
        import time
        time.sleep(0.1)
        assert "Open_road" in gw.stop_calls

    def test_11_state_change_callback(self):
        """Callback вызывается при смене состояния."""
        gw = _FakeGateway()
        ctrl = AutonomousSimulationController(lambda: gw)
        _states: list = []
        ctrl.set_on_state_change(lambda s: _states.append(s))
        ctrl.handle_f10("Open_road")  # → PENDING
        ctrl.confirm()  # → ACTIVE
        assert AutonomousState.PENDING in _states
        assert AutonomousState.ACTIVE in _states

    def test_12_api_error_rolls_back_to_inactive(self):
        """Ошибка API start → откат в INACTIVE."""
        class _ErrorGateway(_FakeGateway):
            def start_autonomous_simulation(self, campaign_id: str) -> dict:
                raise RuntimeError("backend unavailable")
        gw = _ErrorGateway()
        ctrl = AutonomousSimulationController(lambda: gw)
        ctrl.handle_f10("Open_road")
        ctrl.confirm()  # → ACTIVE, но API упадёт
        import time
        time.sleep(0.1)
        assert ctrl.state == AutonomousState.INACTIVE  # откат

    def test_13_sync_status_from_backend_running(self):
        """sync_status: если backend running, контроллер становится ACTIVE."""
        gw = _FakeGateway()
        gw.status_returns["Open_road"] = {"is_running": True}
        ctrl = AutonomousSimulationController(lambda: gw)
        ctrl.sync_status_from_backend("Open_road")
        assert ctrl.state == AutonomousState.ACTIVE

    def test_14_sync_status_from_backend_stopped(self):
        """sync_status: если backend stopped, контроллер становится INACTIVE."""
        gw = _FakeGateway()
        gw.status_returns["Open_road"] = {"is_running": False}
        ctrl = AutonomousSimulationController(lambda: gw)
        ctrl.sync_status_from_backend("Open_road")
        assert ctrl.state == AutonomousState.INACTIVE

    def test_15_gateway_none_safe(self):
        """gateway_provider возвращает None — нет crash."""
        ctrl = AutonomousSimulationController(lambda: None)
        ctrl.handle_f10("Open_road")
        ctrl.confirm()  # не падает
        assert ctrl.state == AutonomousState.ACTIVE  # state сменился, API skip