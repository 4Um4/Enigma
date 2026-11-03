# frontend/autonomous_simulation_controller.py
"""
R6 (CCH-15 P4): Контроллер автономной симуляции — state machine для F10.

Геймдизайнерское решение Мастера R6:
- F10 включает/выключает автономную симуляцию.
- При первом включении — предупреждение о продолжении симуляции
  и дополнительном потреблении ресурсов ПК.
- Включение требует явного подтверждения.
- Повторное нажатие F10 останавливает фоновую симуляцию.
- После перезапуска игры режим всегда выключен (не персистится).
- Если игрок не включал режим — никакой фоновой симуляции нет.

State machine (без pygame, тестируемая):
  INACTIVE → F10 → PENDING (предупреждение)
  PENDING → confirm → ACTIVE (API start)
  PENDING → cancel → INACTIVE
  ACTIVE → F10 → INACTIVE (API stop)

Не создаёт параллельный механизм управления scheduler.
Использует существующие API: start/stop/status.
"""
from __future__ import annotations

import logging
import threading
from enum import Enum
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


class AutonomousState(str, Enum):
    """Состояния контроллера автономной симуляции."""
    INACTIVE = "inactive"  # выключено (по умолчанию)
    PENDING = "pending"    # предупреждение показано, ждём подтверждения
    ACTIVE = "active"      # фоновая симуляция запущена


class AutonomousSimulationController:
    """R6: state machine для F10 — управление автономной симуляцией.

    Потокобезопасная (F10 из main thread, API в worker thread).
    Не зависит от pygame — тестируется в unit-тестах.
    """

    def __init__(self, gateway_provider: Callable[[], Any]) -> None:
        """gateway_provider: возвращает GameGateway (Protocol) для API вызовов."""
        self._get_gateway = gateway_provider
        self._state = AutonomousState.INACTIVE
        self._campaign_id: Optional[str] = None
        self._lock = threading.Lock()
        self._on_state_change: Optional[Callable[[AutonomousState], None]] = None

    @property
    def state(self) -> AutonomousState:
        with self._lock:
            return self._state

    @property
    def is_active(self) -> bool:
        with self._lock:
            return self._state == AutonomousState.ACTIVE

    @property
    def is_pending(self) -> bool:
        with self._lock:
            return self._state == AutonomousState.PENDING

    @property
    def campaign_id(self) -> Optional[str]:
        with self._lock:
            return self._campaign_id

    def set_on_state_change(self, callback: Callable[[AutonomousState], None]) -> None:
        """Регистрация callback для обновления UI индикатора."""
        self._on_state_change = callback

    def _notify_state_change(self) -> None:
        if self._on_state_change:
            try:
                self._on_state_change(self._state)
            except Exception as _e:
                logger.warning(f"[AUTOSIM] state change callback failed: {_e}")

    # ── F10 handling ──────────────────────────────────────────────────

    def handle_f10(self, campaign_id: str) -> None:
        """R6: обработка нажатия F10.

        INACTIVE → PENDING (показать предупреждение, ждать подтверждения).
        PENDING → INACTIVE (отмена — повторный F10 = отмена).
        ACTIVE → INACTIVE + API stop (выключение симуляции).
        """
        with self._lock:
            _prev = self._state
            if self._state == AutonomousState.INACTIVE:
                self._state = AutonomousState.PENDING
                self._campaign_id = campaign_id
                logger.info(f"[AUTOSIM] F10: INACTIVE → PENDING (campaign={campaign_id})")
            elif self._state == AutonomousState.PENDING:
                # Повторный F10 в PENDING = отмена
                self._state = AutonomousState.INACTIVE
                self._campaign_id = None
                logger.info("[AUTOSIM] F10: PENDING → INACTIVE (cancelled)")
            elif self._state == AutonomousState.ACTIVE:
                # F10 в ACTIVE = выключение
                self._state = AutonomousState.INACTIVE
                self._campaign_id = None
                logger.info("[AUTOSIM] F10: ACTIVE → INACTIVE (stopping)")
        self._notify_state_change()
        # Если перешли в INACTIVE из ACTIVE — вызываем API stop в worker thread
        if _prev == AutonomousState.ACTIVE:
            self._call_api_stop(campaign_id)

    def confirm(self) -> None:
        """R6: явное подтверждение включения (после предупреждения).

        PENDING → ACTIVE + API start.
        В любом другом состоянии — no-op.
        """
        with self._lock:
            if self._state != AutonomousState.PENDING:
                return
            self._state = AutonomousState.ACTIVE
            _cid = self._campaign_id
            logger.info(f"[AUTOSIM] confirm: PENDING → ACTIVE (campaign={_cid})")
        self._notify_state_change()
        if _cid:
            self._call_api_start(_cid)

    def cancel(self) -> None:
        """R6: явная отмена из PENDING.

        PENDING → INACTIVE.
        """
        with self._lock:
            if self._state != AutonomousState.PENDING:
                return
            self._state = AutonomousState.INACTIVE
            self._campaign_id = None
            logger.info("[AUTOSIM] cancel: PENDING → INACTIVE")
        self._notify_state_change()

    # ── API calls (worker thread, не блокируют UI) ────────────────────

    def _call_api_start(self, campaign_id: str) -> None:
        """Вызывает POST /autonomous-simulation/{campaign_id}/start в worker thread."""
        def _worker() -> None:
            try:
                _gw = self._get_gateway()
                if _gw is None:
                    logger.warning("[AUTOSIM] gateway unavailable — start skipped")
                    return
                _gw.start_autonomous_simulation(campaign_id)
                logger.info(f"[AUTOSIM] API start OK (campaign={campaign_id})")
            except Exception as _e:
                logger.error(f"[AUTOSIM] API start failed: {_e}", exc_info=True)
                # Откат состояния при ошибке API
                with self._lock:
                    self._state = AutonomousState.INACTIVE
                    self._campaign_id = None
                self._notify_state_change()
        threading.Thread(target=_worker, daemon=True).start()

    def _call_api_stop(self, campaign_id: str) -> None:
        """Вызывает POST /autonomous-simulation/{campaign_id}/stop в worker thread."""
        def _worker() -> None:
            try:
                _gw = self._get_gateway()
                if _gw is None:
                    logger.warning("[AUTOSIM] gateway unavailable — stop skipped")
                    return
                _gw.stop_autonomous_simulation(campaign_id)
                logger.info(f"[AUTOSIM] API stop OK (campaign={campaign_id})")
            except Exception as _e:
                logger.error(f"[AUTOSIM] API stop failed: {_e}", exc_info=True)
        threading.Thread(target=_worker, daemon=True).start()

    # ── Синхронизация с backend (при смене кампании / рестарте) ────────

    def on_campaign_change(self, new_campaign_id: str) -> None:
        """R6: при смене кампании — остановить симуляцию старой.

        Предотвращает продолжение симуляции не той кампании.
        """
        with self._lock:
            _old = self._campaign_id
            _was_active = self._state == AutonomousState.ACTIVE
            self._state = AutonomousState.INACTIVE
            self._campaign_id = None
        self._notify_state_change()
        if _was_active and _old and _old != new_campaign_id:
            self._call_api_stop(_old)

    def on_app_shutdown(self) -> None:
        """R6: при закрытии приложения — гарантированная остановка.

        Backend сам вызывает stop_background_loop в lifespan shutdown,
        но frontend дублирует для надёжности.
        """
        with self._lock:
            _was_active = self._state == AutonomousState.ACTIVE
            _cid = self._campaign_id
            self._state = AutonomousState.INACTIVE
            self._campaign_id = None
        self._notify_state_change()
        if _was_active and _cid:
            self._call_api_stop(_cid)

    def sync_status_from_backend(self, campaign_id: str) -> None:
        """R6: синхронизация состояния с backend через GET /status.

        Используется при старте игры и периодически для надёжности.
        """
        try:
            _gw = self._get_gateway()
            if _gw is None:
                return
            _status = _gw.get_autonomous_simulation_status(campaign_id)
            _is_running = _status.get("is_running", False)
            with self._lock:
                if _is_running and self._state != AutonomousState.ACTIVE:
                    self._state = AutonomousState.ACTIVE
                    self._campaign_id = campaign_id
                elif not _is_running and self._state == AutonomousState.ACTIVE:
                    self._state = AutonomousState.INACTIVE
                    self._campaign_id = None
            self._notify_state_change()
        except Exception as _e:
            logger.warning(f"[AUTOSIM] sync_status failed: {_e}")
