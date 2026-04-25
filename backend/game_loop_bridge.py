"""
backend/game_loop_bridge.py
Синхронная обёртка над async GameLoop для вызова из pygame.

Собирает все события из stream_turn() в TurnResult:
- action_type: тип действия (SOCIAL, PHYSICAL, etc.)
- npc_reactions: список реакций NPC
- dm_text: полный текст DM ответа
- tokens: количество токенов
- ms: время генерации

path: /backend/game_loop_bridge.py
Назначение: Синхронный мост между pygame и async GameLoop
Зависимости: app.services.game_loop_builder, app.services.campaign_state_service, asyncio, typing
Основные сущности: GameLoopBridge, TurnResult
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from app.services.game_loop import GameLoop


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


class GameLoopBridge:
    """
    Синхронная обёртка над async GameLoop.
    
    Инициализация происходит один раз (долго — загружает модели).
    Вызов turn() — блокирующий, собирает все события.
    """

    def __init__(self, data_dir: str = "data") -> None:
        self._data_dir = Path(data_dir)
        self._loop: Optional[GameLoop] = None
        self._ready = False

    @property
    def ready(self) -> bool:
        return self._ready

    def initialize(self) -> None:
        """
        Инициализирует GameLoop. Блокирующий вызов — вызывать при старте
        или в фоновом потоке. Можно вызывать повторно — не пересоздаёт.
        """
        if self._ready:
            return

        from app.services.game_loop_builder import build_game_loop
        self._loop = build_game_loop(self._data_dir)
        self._ready = True

    def turn(
        self,
        campaign_id: str,
        player_name: str,
        action_text: str,
        location: str = "tavern_silver_wolf",
    ) -> TurnResult:
        """
        Синхронный вызов хода. Собирает все события из stream_turn().
        
        Возвращает TurnResult с полным текстом DM и реакциями NPC.
        """
        if not self._ready or self._loop is None:
            return TurnResult(error="GameLoop не инициализирован")

        result = TurnResult()
        dm_parts: list[str] = []

        # Получаем campaign_state для location
        campaign_state = self._get_campaign_state(campaign_id)
        if campaign_state:
            saved = campaign_state.metadata.get("current_location")
            if saved:
                location = saved

        async def _collect() -> None:
            async for event in self._loop.stream_turn(
                campaign_id=campaign_id,
                player=player_name,
                action_text=action_text,
                location=location,
                campaign_state=campaign_state,
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
                    result.game_time_seconds = event.get("game_time_seconds", 0),
                elif etype == "error":
                    result.error = event.get("text", "неизвестная ошибка")

        # Запускаем async код в новом event loop (безопасно для pygame)
        try:
            asyncio.run(_collect())
        except RuntimeError:
            # Если уже есть running loop (pytest, etc.) — используем его
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Создаём отдельный поток для async
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    future = pool.submit(asyncio.run, _collect())
                    future.result()
            else:
                loop.run_until_complete(_collect())

        result.dm_text = "".join(dm_parts)
        return result

    def ensure_scene_initialized(self, campaign_id: str) -> dict:
        """Инициализирует scene_state из editor JSON если нужно."""
        if not self._ready or self._loop is None:
            return {}
        return self._loop.ensure_scene_initialized(campaign_id)

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