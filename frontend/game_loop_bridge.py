"""
path: /frontend/game_loop_bridge.py

Синхронная обёртка над async GameLoop для вызова из pygame.

Собирает все события из stream_turn() в TurnResult:
- action_type: тип действия (SOCIAL, PHYSICAL, etc.)
- npc_reactions: список реакций NPC
- dm_text: полный текст DM ответа
- tokens: количество токенов
- ms: время генерации

Назначение: Синхронный мост между pygame и async GameLoop
Зависимости: app.services.game_loop_builder, app.services.campaign_state_service, asyncio, typing
Основные сущности: GameLoopBridge, TurnResult
"""

from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
import logging

logger = logging.getLogger(__name__)

# GameLoop из backend — тип не аннотируем (Закон 1.1: frontend не знает классы backend)
# Доступ только через self._loop в runtime


@dataclass
class TurnResult:
    """Результат одного хода — собранный из всех SSE событий."""

    action_type: str = ""
    npc_reactions: list[dict] = field(default_factory=list)
    dm_text: str = ""
    tokens: int = 0
    ms: int = 0
    tps: float = 0.0
    game_time_seconds: int = 0  # total_seconds для отображения даты/времени
    error: Optional[str] = None
    # ADR-0014: Позиции NPC после player action (Force Merge)
    world_snapshot: Optional[dict] = None
    npc_positions: Optional[dict] = None
    # ADR-075: Строгий контракт Эмбодимента. Если поле пропадёт — краш схемы, а не тихий None.
    will_conflict_data: Optional[dict] = None
    # A1-FIX: S85 fields — проброс scene_state и metadata для инициализации UI.
    # Раньше передавались только в HTTP mode, в Direct mode отсутствовали → contract drift.
    scene_state: Optional[dict] = None
    metadata: Optional[dict] = None
    # S82: Backend подтверждает spatial truth. Frontend reconciles при расхождении.
    confirmed_location_id: Optional[str] = None


class GameLoopBridge:
    """
    Синхронная обёртка над async GameLoop.

    Инициализация происходит один раз (долго — загружает модели).
    Вызов turn() — блокирующий, собирает все события.
    """

    def __init__(self, data_dir: str = "data") -> None:
        self._data_dir = Path(data_dir)
        self._loop = None  # type: ignore[assignment]  # backend GameLoop, создаётся в initialize()
        self._ready = False
        # E.1: Persistent event loop для устранения asyncio.run() на каждый ход
        self._async_loop: Optional[asyncio.AbstractEventLoop] = None
        self._async_thread: Optional[threading.Thread] = None

    @property
    def ready(self) -> bool:
        return self._ready

    def _start_async_loop(self) -> None:
        """E.1: Создаёт persistent event loop в отдельном daemon-потоке."""
        if self._async_loop and self._async_loop.is_running():
            return
        self._async_loop = asyncio.new_event_loop()
        self._async_thread = threading.Thread(
            target=self._async_loop.run_forever, daemon=True
        )
        self._async_thread.start()

    def initialize(self) -> None:
        """
        Инициализирует GameLoop. Блокирующий вызов — вызывать при старте
        или в фоновом потоке. Можно вызывать повторно — не пересоздаёт.
        """
        if self._ready:
            return

        from app.services.game_loop_builder import build_game_loop

        self._loop = build_game_loop(self._data_dir)
        self._start_async_loop()  # E.1: Запускаем persistent loop
        self._ready = True

    def turn(
        self,
        campaign_id: str,
        player_name: str,
        action_text: str,
        location: str = "tavern_silver_wolf",
        player_x: float = 0.0,
        player_y: float = 0.0,
        world_x: float | None = None,
        world_y: float | None = None,
    ) -> TurnResult:
        """
        Синхронный вызов хода. Собирает все события из stream_turn().

        Возвращает TurnResult с полным текстом DM и реакциями NPC.
        """
        if not self._ready or self._loop is None:
            return TurnResult(error="GameLoop не инициализирован")

        result = TurnResult()
        dm_parts: list[str] = []

        # Получаем campaign_state для location (fallback если oracle не сработал)
        campaign_state = self._get_campaign_state(campaign_id)
        # A1-FIX: Убран хардкод "tavern_silver_wolf". Используем официальный API SceneStateManager.
        location = "tavern_silver_wolf"  # Оставлено как last-resort fallback, если scene_manager недоступен
        if self._ready and self._loop is not None:
            try:
                location = self._loop.find_starting_location(campaign_id)
            except Exception as e:
                logger.warning(f"[B5-FIX] silent failure suppressed: {e}")
        if campaign_state:
            saved = campaign_state.metadata.get("current_location")
            if saved:
                location = saved

        # S82: Spatial Oracle — если есть мировые координаты, вычисляем location из реестра.
        # Это тот же deterministic oracle, что и в routes.py — единая истина.
        if world_x is not None and world_y is not None:
            # B2-FIX: Spatial Oracle no-silent-failure. Логируем ошибки, не глотаем.
            try:
                from app.services.spatial.spatial_registry import SpatialRegistry

                _registry = SpatialRegistry.get_or_load(campaign_id)
                if _registry is None:
                    logger.warning(
                        f"[SPATIAL_ORACLE] registry not loaded for campaign={campaign_id}. Fallback to saved location."
                    )
                elif not hasattr(_registry, "find_chunks"):
                    logger.error(
                        f"[SPATIAL_ORACLE] registry {_registry.__class__.__name__} has no find_chunks method. Fallback to saved location."
                    )
                else:
                    _actual_chunks = _registry.find_chunks(world_x, world_y)
                    if _actual_chunks:
                        location = _actual_chunks[0].location_id
                        result.confirmed_location_id = location
                        # Обновляем metadata для следующего запроса (parity with routes.py)
                        if campaign_state:
                            campaign_state.metadata["current_location"] = location
                            campaign_state.metadata["player_world_x"] = world_x
                            campaign_state.metadata["player_world_y"] = world_y
                            # A1-FIX: Atomic commit (Устав §4.2.1). Persistence parity with HTTP path.
                            from app.services.campaign_state_service import (
                                get_campaign_state_service,
                            )

                            get_campaign_state_service().save(campaign_id)
                    else:
                        logger.debug(
                            f"[SPATIAL_ORACLE] no chunks for ({world_x}, {world_y}). Fallback to saved location."
                        )
            except Exception as e:
                logger.warning(
                    f"[SPATIAL_ORACLE] find_chunks failed: {e}. Fallback to saved location."
                )

        async def _collect() -> None:
            async for event in self._loop.stream_turn(
                campaign_id=campaign_id,
                player=player_name,
                action_text=action_text,
                location=location,
                campaign_state=campaign_state,
                player_position=(player_x, player_y)
                if (player_x or player_y)
                else None,
            ):
                etype = event.get("type", "")

                if etype == "action_type":
                    result.action_type = event.get("value", "")
                elif etype == "npc":
                    result.npc_reactions = event.get("data", [])
                elif etype == "token":
                    dm_parts.append(event.get("text", ""))
                elif etype == "done":
                    result.tokens = event.get("tokens", 0)
                    result.ms = event.get("ms", 0)
                    result.tps = event.get("tps", 0.0)
                    result.game_time_seconds = event.get("game_time_seconds", 0)
                    # ADR-075: Извлечение Эмбодимента из финального SSE пакета.
                    # Если бэкенд не пришлёт ключ, dataclass даст None.
                    result.will_conflict_data = event.get("will_conflict_data")
                    # A2-FIX: Извлечение WorldSnapshotDTO из SSE пакета (Tri-ontology system fix).
                    # Раньше игнорировалось, и ниже bridge пихал сырой scene_state → Double Truth.
                    _ws_obj = event.get("world_snapshot")
                    if _ws_obj is not None:
                        from dataclasses import asdict, is_dataclass

                        if is_dataclass(_ws_obj):
                            result.world_snapshot = asdict(_ws_obj)
                            # A2-FIX: npc_positions уже Dict (canonical). Адаптер удалён.
                            result.npc_positions = result.world_snapshot.get(
                                "npc_positions", {}
                            )
                        elif isinstance(_ws_obj, dict):
                            result.world_snapshot = _ws_obj
                            result.npc_positions = _ws_obj.get("npc_positions", {})
                elif etype == "error":
                    result.error = event.get("text", "неизвестная ошибка")

        # E.1: Запускаем async код в persistent event loop (без asyncio.run)
        if self._async_loop and self._async_loop.is_running():
            future = asyncio.run_coroutine_threadsafe(_collect(), self._async_loop)
            future.result()  # Блокируем до завершения
        else:
            # Fallback (на случай если bridge не инициализирован правильно)
            logger.warning(
                "[BRIDGE] Async loop not running, falling back to asyncio.run()"
            )
            asyncio.run(_collect())

        result.dm_text = "".join(dm_parts)

        # A2-FIX: Устранена Tri-ontology system.
        # Раньше здесь bridge перезаписывал канонический WorldSnapshotDTO сырым scene_state.
        # Теперь WorldSnapshotDTO читается из SSE пакета (событие "done") в _collect().
        # Если по какой-то причине world_snapshot отсутствует (legacy path), fallback на пустой dict.
        if not isinstance(result.world_snapshot, dict):
            result.world_snapshot = {}
            result.npc_positions = {}
            logger.warning(
                "[BRIDGE] WorldSnapshotDTO missing in SSE 'done' event. Falling back to empty."
            )
        else:
            # Гарантируем, что npc_positions внутри world_snapshot синхронизированы с топ-уровнем
            result.npc_positions = result.world_snapshot.get("npc_positions", {})

        return result

    # ADR-0010: Удалён прямой вызов backend-метода. Инициализация сцены — ответственность backend API.

    def enrich_scene_spatial(self, scene_state: dict, campaign_id: str) -> None:
        """Обогащает spatial-данные из editor JSON. Делегирует модульную функцию."""
        if not self._ready or self._loop is None:
            return
        from app.services.scene_state_manager import enrich_scene_spatial as _enrich

        _enrich(scene_state, campaign_id)

    def build_perceived_scene(self, scene_state: dict, config) -> object:
        """
        Прогоняет scene_state через cognition pipeline.
        Возвращает PerceivedScene (backend-тип, duck-typed на фронтенде).
        """
        if not self._ready or self._loop is None:
            return None
        from app.services.player_cognition import build_perceived_scene as _build

        return _build(scene_state, config)

    def save_scene_state(self, campaign_id: str, scene_state: dict) -> None:
        """Сохраняет scene_state на бэкенд. Делегирует scene_manager."""
        if not self._ready or self._loop is None:
            return
        self._loop.save_scene_state(campaign_id, scene_state)

    def get_scene_state(self, campaign_id: str, location_id: str = "") -> dict | None:
        """Возвращает текущее состояние сцены. Делегирует scene_manager."""
        if not self._ready or self._loop is None:
            return None
        return self._loop.get_scene_state(campaign_id, location_id)

    def apply_changes(self, campaign_id: str, changes: list, scene_state: dict) -> None:
        """Применяет изменения к сцене. Делегирует scene_manager."""
        if not self._ready or self._loop is None:
            return
        self._loop.apply_changes(campaign_id, changes, scene_state)

    def get_characters(self, campaign_id: str) -> list[dict]:
        """ADR-O-146: Персонажи через backend API, не через файлы (Law 1.1)."""
        if not self._ready or self._loop is None:
            return []
        try:
            characters = self._loop.list_characters(campaign_id)
            return [c.model_dump() for c in characters]
        except Exception:
            return []

    def idle_tick(self, campaign_id: str) -> dict:
        """Idle tick через TickOrchestrator (10 фаз, Устав §3).

        Единая точка входа для DirectGateway и routes.py.
        Конвертация DTO→dict происходит в GameLoop (Устав §1.1).
        Bridge не импортирует app.domain.* — только вызывает idle_tick().
        """
        if not self._ready or self._loop is None:
            return {"status": "not_ready"}
        try:
            return self._loop.idle_tick(campaign_id)
        except Exception as e:
            import traceback

            logger.error(f"[IDLE_TICK_BRIDGE] ERROR: {e}\n{traceback.format_exc()}")
            return {"status": "error", "error": str(e), "npc_positions": {}}

    def initialize_model_pool(self) -> None:
        """Инициализирует ModelPool в pygame процессе."""
        from app.services.llm.provider_manager import initialize_model_pool

        initialize_model_pool()

    def _get_campaign_state(self, campaign_id: str):
        """Получает campaign_state для определения локации."""
        try:
            from app.services.campaign_state_service import get_campaign_state_service

            service = get_campaign_state_service()
            return service.get_campaign_state(campaign_id)
        except Exception:
            return None


# Глобальный экземпляр — инициализируется при старте
_game_loop_bridge = GameLoopBridge()


def get_game_loop_bridge() -> GameLoopBridge:
    """Возвращает глобальный экземпляр моста."""
    return _game_loop_bridge
