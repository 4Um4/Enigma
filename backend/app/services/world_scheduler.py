# path: backend/app/services/world_scheduler.py
"""
WorldScheduler — независимый фоновый инициатор автономных тиков (R4, CCH-15 P4).

Вердикт Мастера R4 (вариант C — гибрид, продолжение R3):
- Один мир — один последовательный исполнитель изменений состояния.
- WorldScheduler делегирует в game_loop.idle_tick (существующий путь через
  TickOrchestrator), не создаёт параллельный исполнитель.
- ADR-O-407 (_player_turn_in_flight) защищает от конкурентного исполнения
  с ходом игрока.
- _running_ticks гвард защищает от двойного автономного тика одной кампании.
- Гибкий старт/стоп; корректная остановка asyncio-задач.

Назначение:
- maybe_tick — legacy совместимость (генерация метаданных для shared_context).
  НЕ вызывает idle_tick (запрещено — нет game_loop на этапе конструирования).
- run_autonomous_tick — единственная точка входа автономного тика в мир.
- start_background_loop / stop_background_loop — управление фоновым циклом.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set

from app.agents.world_sim_agent import WorldSimulationAgent
from app.services.memory import LayeredMemory

logger = logging.getLogger(__name__)

# Интервал автономного тика по умолчанию (секунды).
# CALIBRATION_CANDIDATE: placeholder, калибруется в config.py (settings.world_tick_minutes).
_DEFAULT_AUTONOMOUS_INTERVAL_SECONDS: float = 60.0


class WorldScheduler:
    """Независимый фоновый инициатор автономных тиков мира.

    R4: WorldScheduler получает ссылку на game_loop (set_game_loop) и
    делегирует автономные тики в game_loop.idle_tick — единственный путь
    изменения состояния через TickOrchestrator.
    """

    def __init__(
        self, memory: LayeredMemory, world_agent: WorldSimulationAgent
    ) -> None:
        self.memory = memory
        self.world_agent = world_agent
        # R4: ссылка на game_loop (устанавливается после конструирования GameLoop)
        self._game_loop: Optional[Any] = None
        # Гвард конкурентного исполнения: campaign_id -> bool (in-flight)
        self._running_ticks: Set[str] = set()
        # Фоновые asyncio-задачи
        self._background_tasks: Set[asyncio.Task] = set()
        self._loop_running: bool = False

    def set_game_loop(self, game_loop: Any) -> None:
        """R4: инъекция game_loop после конструирования (разрешает циклическую зависимость)."""
        self._game_loop = game_loop
        logger.info("[WORLD_SCHEDULER] game_loop injected — autonomous tick path active")

    # ─────────────────────────────────────────────────────────────────────
    # Legacy: maybe_tick (метаданные для shared_context, не вызывает idle_tick)
    # ─────────────────────────────────────────────────────────────────────

    def _last_tick_at(self, world_id: str) -> datetime | None:
        items = self.memory.store.recent(f"world_hidden_events_{world_id}", limit=1)
        if not items:
            return None
        raw = items[0].get("timestamp")
        if not raw:
            return None
        try:
            return datetime.fromisoformat(raw)
        except ValueError as e:
            logger.debug(f"World scheduler datetime parse error: {e}")
            return None

    def maybe_tick(self, world_id: str, every_minutes: int) -> dict:
        """Legacy: генерация метаданных для shared_context (не автономный тик).

        R4: сохранён для совместимости с _spawn_world_tick_task. НЕ вызывает
        idle_tick — автономный тик идёт через run_autonomous_tick.
        """
        now = datetime.now(timezone.utc)  # §15.2: Infrastructure scheduler interval check
        last_tick = self._last_tick_at(world_id)
        if last_tick and (now - last_tick) < timedelta(minutes=every_minutes):
            return {"triggered": False, "reason": "interval_not_elapsed", "events": []}

        _events = []
        try:
            _npcs = self.memory.store.recent(f"npcs_runtime_{world_id}", limit=10)
            for _npc in _npcs:
                if _npc.get("life_status") == "ALIVE":
                    _events.append({
                        "type": "idle_tick",
                        "actor": _npc.get("id", "unknown"),
                        "tick": now.isoformat()
                    })
        except Exception as e:
            logger.error(f"[WORLD_SCHEDULER] Failed to generate idle_tick events for {world_id}: {e}", exc_info=True)

        result = {"world_events": _events, "simulation_log": "offscreen_tick_ok"}

        event_payload = {
            "visibility": "hidden",
            "events": result.get("world_events", []),
        }
        self.memory.store.append(f"world_hidden_events_{world_id}", event_payload)
        return {
            "triggered": True,
            "reason": "ok",
            "events": result.get("world_events", []),
        }

    # ─────────────────────────────────────────────────────────────────────
    # R4: Autonomous tick — единственная точка входа автономного тика в мир
    # ─────────────────────────────────────────────────────────────────────

    def run_autonomous_tick(self, campaign_id: str) -> Dict[str, Any]:
        """R4: один автономный тик через game_loop.idle_tick.

        Контракт:
        - Единственный путь изменения состояния мира (через TickOrchestrator).
        - ADR-O-407 защищает от конкурентного исполнения с ходом игрока.
        - _running_ticks гвард защищает от двойного автономного тика.
        - game_loop.idle_tick синхронный; вызывается в asyncio.to_thread
          (не блокирует event loop фонового цикла).

        Возвращает dict как idle_tick (status, npc_positions, npc_addressing).
        Если game_loop не установлен — честный отказ (не crash).
        """
        if self._game_loop is None:
            logger.warning("[WORLD_SCHEDULER] run_autonomous_tick: game_loop not set — skip")
            return {"status": "no_game_loop", "npc_positions": {}, "npc_addressing": []}

        # Гвард конкурентного исполнения: не запускаем тик, если он уже идёт
        if campaign_id in self._running_ticks:
            logger.debug(f"[WORLD_SCHEDULER] {campaign_id}: tick already running — skip")
            return {"status": "already_running", "npc_positions": {}, "npc_addressing": []}

        self._running_ticks.add(campaign_id)
        try:
            # idle_tick синхронный — вызываем напрямую (run_autonomous_tick
            # уже в asyncio.to_thread от start_background_loop, либо из теста)
            result = self._game_loop.idle_tick(campaign_id)
            logger.info(
                f"[WORLD_SCHEDULER] autonomous tick {campaign_id}: "
                f"status={result.get('status') if result else 'None'}"
            )
            return result if result else {
                "status": "no_result",
                "npc_positions": {},
                "npc_addressing": [],
            }
        except Exception as e:
            logger.error(
                f"[WORLD_SCHEDULER] autonomous tick {campaign_id} failed: {e}",
                exc_info=True,
            )
            return {"status": "error", "error": str(e), "npc_positions": {}, "npc_addressing": []}
        finally:
            self._running_ticks.discard(campaign_id)

    # ─────────────────────────────────────────────────────────────────────
    # R4: Background loop — независимый фоновый цикл автономных тиков
    # ─────────────────────────────────────────────────────────────────────

    async def start_background_loop(
        self,
        campaign_ids: List[str],
        interval_seconds: float = _DEFAULT_AUTONOMOUS_INTERVAL_SECONDS,
    ) -> None:
        """R4: запуск независимого фонового цикла автономных тиков.

        - campaign_ids: список кампаний для тика.
        - interval_seconds: интервал между тиками (по умолчанию 60с).
        - Останавливается через stop_background_loop.
        - Каждый campaign_id тикает последовательно (не параллельно) —
          один исполнитель изменений состояния.
        """
        if self._loop_running:
            logger.warning("[WORLD_SCHEDULER] background loop already running — skip start")
            return
        if self._game_loop is None:
            logger.warning("[WORLD_SCHEDULER] cannot start background loop — game_loop not set")
            return

        self._loop_running = True
        logger.info(
            f"[WORLD_SCHEDULER] background loop started: campaigns={campaign_ids} "
            f"interval={interval_seconds}s"
        )

        async def _loop() -> None:
            try:
                while self._loop_running:
                    for cid in campaign_ids:
                        if not self._loop_running:
                            break
                        # idle_tick синхронный — оборачиваем в to_thread
                        # (не блокирует event loop; ADR-O-407 + _running_ticks
                        # защищают от конкурентного исполнения)
                        try:
                            await asyncio.to_thread(self.run_autonomous_tick, cid)
                        except Exception as e:
                            logger.error(
                                f"[WORLD_SCHEDULER] background tick {cid} failed: {e}",
                                exc_info=True,
                            )
                    # Ждём следующий интервал
                    await asyncio.sleep(interval_seconds)
            except asyncio.CancelledError:
                logger.info("[WORLD_SCHEDULER] background loop cancelled")
                raise
            finally:
                self._loop_running = False

        _task = asyncio.create_task(_loop())
        self._background_tasks.add(_task)
        _task.add_done_callback(self._background_tasks.discard)

    async def stop_background_loop(self) -> None:
        """R4: корректная остановка фонового цикла.

        - Устанавливает _loop_running = False (цикл выходит на следующей итерации).
        - Отменяет asyncio-задачи (cancel + await).
        - Ждёт завершения (with shield timeout).
        """
        self._loop_running = False
        if not self._background_tasks:
            return
        logger.info(f"[WORLD_SCHEDULER] stopping background loop ({len(self._background_tasks)} tasks)")
        for task in list(self._background_tasks):
            task.cancel()
        # Await all tasks with timeout
        try:
            await asyncio.wait_for(
                asyncio.gather(*self._background_tasks, return_exceptions=True),
                timeout=5.0,
            )
        except asyncio.TimeoutError:
            logger.warning("[WORLD_SCHEDULER] background loop stop timeout — tasks may still run")
        self._background_tasks.clear()
        logger.info("[WORLD_SCHEDULER] background loop stopped")

    @property
    def is_loop_running(self) -> bool:
        """R4: статус фонового цикла (для тестов и мониторинга)."""
        return self._loop_running

    @property
    def running_ticks(self) -> List[str]:
        """R4: список кампаний с in-flight тиками (для тестов)."""
        return list(self._running_ticks)
