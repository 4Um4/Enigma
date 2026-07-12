"""
Слой связи Pygame ↔ Backend.

Архитектура (три уровня):
  1. GameGateway (Protocol) — чистый интерфейс, знает только домен
  2. BackendContract — маппинг JSON ↔ доменные объекты, знает структуру API
  3. HttpClient — чистый транспорт, знает только URL/методы/таймауты

Плюс:
  4. ActionQueue — неблокирующая очередь (LLM latency 1-10s не замораживает Pygame)

Pygame знает ТОЛЬКО GameGateway и ActionQueue.
При смене транспорта (WebSocket, gRPC) — меняется только HttpGameGateway.
При смене контракта API — меняется только BackendContract.

path: /frontend/api_client.py

Назначение: Слой связи Pygame ↔ Backend. Три уровня: Protocol (что знает Pygame) → Contract (маппинг) → Transport (HTTP). Плюс неблокирующая очередь.
Зависимости: urllib.request, json, threading, queue (stdlib)
Основные сущности: GameGateway, GameActionResponse, HttpClient, BackendContract, HttpGameGateway, ActionQueue

TODO:
"""

from __future__ import annotations

import json
import logging
import threading

logger = logging.getLogger(__name__)
import time  # noqa: E402
import uuid  # noqa: E402
import urllib.request  # noqa: E402
import urllib.error  # noqa: E402
from dataclasses import dataclass  # noqa: E402
from typing import Protocol  # noqa: E402
from queue import Queue  # noqa: E402


# ═══════════════════════════════════════════════════════════════════════
# УРОВЕНЬ 1: Доменные типы (знает Pygame)
# ═══════════════════════════════════════════════════════════════════════


class BackendError(Exception):
    """Ошибка взаимодействия с backend."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        self.status_code = status_code
        super().__init__(message)


@dataclass
class GameActionResponse:
    """Доменный объект ответа на действие игрока."""

    dm_response: str
    npc_reactions: list[dict]
    world_changes: list[dict]
    journal_entry_id: str | None
    game_time_seconds: int = 0  # total_seconds для HUD
    # TASK 1: Force Merge — world_snapshot из player action tick (ADR-0014)
    world_snapshot: dict | None = None
    npc_positions: dict | None = None
    # Resistance Medium: Данные конфликта воли для заражения UI
    will_conflict_data: dict | None = None
    # S82: Backend подтверждает spatial truth. Frontend reconciles при расхождении.
    confirmed_location_id: str | None = None
    # A1-FIX: S85 fields — проброс scene_state и metadata для инициализации UI.
    # Раньше передавались в _map_action_response, но отсутствовали в dataclass → TypeError.
    scene_state: dict | None = None
    metadata: dict | None = None


# ═══════════════════════════════════════════════════════════════════════
# УРОВЕНЬ 2: Protocol (знает Pygame — через typing.Protocol)
# ═══════════════════════════════════════════════════════════════════════


class GameGateway(Protocol):
    """B3-FIX: Протокол расширен методами send_action_stream и get_world_state.
    Заготовка для будущей миграции на SSE и автономный бэкенд.
    """

    """
    Чистый интерфейс шлюза к backend.
    Pygame вызывает ТОЛЬКО эти методы.
    Не знает про HTTP, endpoints, JSON структуру.
    """

    def send_action(
        self,
        campaign_id: str,
        player_name: str,
        action_text: str,
        player_x: float = 0.0,
        player_y: float = 0.0,
        world_x: float | None = None,
        world_y: float | None = None,
    ) -> GameActionResponse:
        """Отправить действие игрока. Блокирующий — вызывать из worker thread."""
        ...

    def health(self) -> dict:
        """Проверка здоровья backend."""
        ...

    def new_game(self, campaign_id: str) -> dict:
        """ADR-O-146: Сброс runtime мира к чистому static."""
        ...

    def create_player_session(self, campaign_id: str, player_name: str) -> dict:
        """Создать/активировать сессию игрока."""
        ...

    def get_session_state(self, campaign_id: str) -> dict:
        """Получить состояние сессии."""
        ...

    def get_characters(self, campaign_id: str) -> list[dict]:
        """Получить список персонажей."""
        ...

    def skip_time(self, campaign_id: str, ticks: int) -> dict:
        """
        Промотка времени (Time Skip).
        """
        ...

    def idle_tick(self, campaign_id: str) -> dict:
        """
        Тик мира без действия игрока.
        Pygame вызывает по таймеру пока игрок думает.
        Неблокирующий — вызывать из worker thread.
        """
        ...

    def save_scene_state(self, campaign_id: str, scene_state: dict) -> None:
        """Push updated scene_state to backend."""
        ...

    def load_campaign(self, campaign_id: str, world_id: str = "default") -> dict:
        """Загрузить кампанию (скопировать исходники в saves при первом запуске)."""
        ...


# ═══════════════════════════════════════════════════════════════════════
# УРОВЕНЬ 3: Transport — чистый HTTP, без знания домена
# ═══════════════════════════════════════════════════════════════════════


class HttpClient:
    """
    Чистый транспортный слой.
    Знает только: URL, метод, timeout, JSON encode/decode.
    Не знает про GameActionResponse, campaign_id, player_name.
    """

    def __init__(self, base_url: str, timeout_sec: int = 30) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_sec = timeout_sec

    def post(self, path: str, payload: dict | None = None) -> dict:
        """POST запрос → распарсенный JSON."""
        url = self.base_url + path
        data = json.dumps(payload).encode("utf-8") if payload else b"{}"
        headers = {"Content-Type": "application/json"}
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        return self._execute(req)

    def get(self, path: str) -> dict:
        """GET запрос → распарсенный JSON."""
        url = self.base_url + path
        req = urllib.request.Request(url, method="GET")
        return self._execute(req)

    def _execute(self, req: urllib.request.Request) -> dict:
        """Выполняет запрос, возвращает dict. При ошибке — BackendError."""
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_sec) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = e.read().decode("utf-8", errors="replace")
            except Exception as e:
                logger.warning(
                    f"[B5-FIX] silent failure suppressed: {e}"
                )  # не удалось прочитать тело ошибки HTTP
            raise BackendError(
                f"HTTP {e.code}: {body}",
                status_code=e.code,
            ) from e
        except urllib.error.URLError as e:
            raise BackendError(
                f"Backend недоступен ({self.base_url}): {e.reason}"
            ) from e


# ═══════════════════════════════════════════════════════════════════════
# УРОВЕНЬ 4: Contract — маппинг JSON ↔ домен
# ═══════════════════════════════════════════════════════════════════════


class BackendContract:
    """
    Знает структуру API: какие endpoints, какие поля в JSON.
    Склеивает HttpClient ↔ GameGateway.
    При изменении API — меняется только этот класс.
    """

    def __init__(self, transport: HttpClient) -> None:
        self._t = transport

    def send_action(
        self,
        campaign_id: str,
        player_name: str,
        action_text: str,
        player_x: float = 0.0,
        player_y: float = 0.0,
        world_x: float | None = None,
        world_y: float | None = None,
    ) -> GameActionResponse:
        """Маппинг: доменные аргументы → JSON payload → JSON response → доменный объект."""
        payload = {
            "campaign": campaign_id,
            "player": player_name,
            "action": action_text,
            "player_x": player_x,
            "player_y": player_y,
            "is_telegraph": getattr(action_text, "_is_telegraph", False),
        }
        # S82: Мировые координаты — PRIMARY spatial input. Отправляем только если есть.
        if world_x is not None and world_y is not None:
            payload["world_x"] = world_x
            payload["world_y"] = world_y
        raw = self._t.post("/api/game/action", payload)
        return self._map_action_response(raw)

    def health(self) -> dict:
        return self._t.get("/api/health")

    def create_player_session(self, campaign_id: str, player_name: str) -> dict:
        return self._t.post(
            f"/api/player/session/{campaign_id}",
            {"player": player_name},
        )

    def get_session_state(self, campaign_id: str) -> dict:
        return self._t.get(f"/api/session/state/{campaign_id}")

    def get_characters(self, campaign_id: str) -> list[dict]:
        result = self._t.get(f"/api/characters/{campaign_id}")
        return result.get("characters", [])

    def idle_tick(self, campaign_id: str) -> dict:
        return self._t.post(f"/api/game/idle_tick/{campaign_id}", {})

    def skip_time(self, campaign_id: str, ticks: int) -> dict:
        """Промотка времени (Time Skip)."""
        return self._t.post(f"/api/game/skip_time/{campaign_id}?ticks={ticks}", {})

    def save_scene_state(self, campaign_id: str, scene_state: dict) -> None:
        """B1.4-FIX: push scene_state to backend via HTTP."""
        try:
            self._t.post(f"/api/game/{campaign_id}/scene_state", scene_state)
        except Exception as e:
            logger.warning(f"[HTTP_GATEWAY] save_scene_state failed: {e}")
            raise

    def load_campaign(self, campaign_id: str, world_id: str = "default") -> dict:
        return self._t.post(
            "/api/campaign/load",
            {"campaign_id": campaign_id, "world_id": world_id},
        )

    def new_game(self, campaign_id: str) -> dict:
        """ADR-O-146: Сброс runtime мира к чистому static."""
        ...

    @staticmethod
    def _map_action_response(raw: dict) -> GameActionResponse:
        """Маппинг JSON → доменный объект. Единственное место с полями ответа."""
        return GameActionResponse(
            dm_response=raw.get("response", ""),
            npc_reactions=raw.get("npc_reactions", []),
            world_changes=raw.get("world_changes", []),
            journal_entry_id=raw.get("journal_entry_id"),
            game_time_seconds=raw.get("game_time_seconds", 0),
            # TASK 1: Force Merge — пробрасываем snapshot позиций (ADR-0014)
            world_snapshot=raw.get("world_snapshot"),
            npc_positions=raw.get("npc_positions"),
            # Resistance Medium: Проброс конфликта воли
            will_conflict_data=raw.get("will_conflict_data"),
            # S85: Проброс scene_state и metadata для инициализации UI
            scene_state=raw.get("scene_state", {}),
            metadata=raw.get("metadata", {}),
            # S82: Backend подтверждает spatial truth. Frontend reconciles при расхождении.
            confirmed_location_id=raw.get("confirmed_location_id"),
        )


# ═══════════════════════════════════════════════════════════════════════
# УРОВЕНЬ 5: Реализация Gateway (склеивает Contract)
# ═══════════════════════════════════════════════════════════════════════


class HttpGameGateway:
    """
    Реализация GameGateway через HTTP.
    При смене транспорта — создаём другой Gateway (WebSocketGameGateway и т.д.)
    """

    def __init__(self, contract: BackendContract) -> None:
        self._contract = contract

    def send_action(
        self,
        campaign_id: str,
        player_name: str,
        action_text: str,
        player_x: float = 0.0,
        player_y: float = 0.0,
        world_x: float | None = None,
        world_y: float | None = None,
    ) -> GameActionResponse:
        return self._contract.send_action(
            campaign_id, player_name, action_text, player_x, player_y, world_x, world_y
        )

    def health(self) -> dict:
        return self._contract.health()

    def new_game(self, campaign_id: str) -> dict:
        """ADR-O-146: Сброс runtime мира к чистому static."""
        return self._contract.new_game(campaign_id)

    def create_player_session(self, campaign_id: str, player_name: str) -> dict:
        return self._contract.create_player_session(campaign_id, player_name)

    def get_session_state(self, campaign_id: str) -> dict:
        return self._contract.get_session_state(campaign_id)

    def get_characters(self, campaign_id: str) -> list[dict]:
        return self._contract.get_characters(campaign_id)

    def idle_tick(self, campaign_id: str) -> dict:
        return self._contract.idle_tick(campaign_id)

    def skip_time(self, campaign_id: str, ticks: int) -> dict:
        """Промотка времени через HTTP."""
        return self._contract.skip_time(campaign_id, ticks)

    def send_action_stream(
        self,
        campaign_id: str,
        player_name: str,
        action_text: str,
        player_x: float = 0.0,
        player_y: float = 0.0,
        world_x: float | None = None,
        world_y: float | None = None,
    ):
        """B3-FIX: SSE streaming заглушка. Делегирует в contract, если поддерживается.
        Возвращает генератор токенов DM-ответа.
        """
        if hasattr(self._contract, "send_action_stream"):
            return self._contract.send_action_stream(
                campaign_id,
                player_name,
                action_text,
                player_x,
                player_y,
                world_x,
                world_y,
            )
        raise NotImplementedError("SSE streaming is not supported by this contract.")

    def get_world_state(
        self, campaign_id: str, after_tick: int | None = None
    ) -> dict | None:
        """B3-FIX: Read-only запрос состояния мира для polling'а.
        Не продвигает симуляцию (не выполняет tick).
        """
        return get_world_state(
            campaign_id, after_tick, base_url=self._contract._base_url
        )

    def save_scene_state(self, campaign_id: str, scene_state: dict) -> None:
        return self._contract.save_scene_state(campaign_id, scene_state)

    def load_campaign(self, campaign_id: str, world_id: str = "default") -> dict:
        return self._contract.load_campaign(campaign_id, world_id)


# ═══════════════════════════════════════════════════════════════════════
# УРОВЕНЬ 5: DirectGameGateway — прямой вызов GameLoop без HTTP
# ═══════════════════════════════════════════════════════════════════════


class DirectGameGateway:
    """
    Реализация GameGateway через прямой вызов GameLoop.
    НЕ требует запущенного FastAPI — GameLoop вызывается напрямую.

    Используется в pygame режиме для локальной работы без HTTP.
    """

    def __init__(self) -> None:
        # Инициализация ModelPool через bridge (Закон 1.1 — frontend не импортирует backend)
        from game_loop_bridge import get_game_loop_bridge

        self._bridge = get_game_loop_bridge()
        self._bridge.initialize_model_pool()
        self._last_player_pos: tuple[float, float] | None = None

    def send_action(
        self,
        campaign_id: str,
        player_name: str,
        action_text: str,
        player_x: float = 0.0,
        player_y: float = 0.0,
        world_x: float | None = None,
        world_y: float | None = None,
    ) -> GameActionResponse:
        # Инициализируем при первом вызове (долго — загружает модели)
        if not self._bridge.ready:
            self._bridge.initialize()

        # Координаты игрока передаются в GameLoop для пространственных интентов (APPROACH и др.)
        # S82: world_x/y пробрасываются для Spatial Oracle (если bridge поддерживает)
        result = self._bridge.turn(
            campaign_id=campaign_id,
            player_name=player_name,
            action_text=action_text,
            player_x=player_x,
            player_y=player_y,
            world_x=world_x,
            world_y=world_y,
        )

        if result.error:
            raise BackendError(result.error)

        return GameActionResponse(
            dm_response=result.dm_text,
            npc_reactions=result.npc_reactions,
            world_changes=[],
            journal_entry_id=None,
            game_time_seconds=result.game_time_seconds,
            # ADR-0014: Force Merge — пробрасываем позиции NPC на фронтенд
            world_snapshot=result.world_snapshot,
            npc_positions=result.npc_positions,
            # ADR-075: Строгий контракт Эмбодимента. Никаких getattr. Если поля нет — значит схема мертва.
            will_conflict_data=result.will_conflict_data,
            # A1-FIX: Проброс S85 fields и spatial truth. Contract parity with HTTP mode.
            scene_state=result.scene_state,
            metadata=result.metadata,
            confirmed_location_id=result.confirmed_location_id,
        )
        # ADR-075 DIAG: Диагностический след. Показывает, дошли ли данные до шлюза.
        if hasattr(result, "will_conflict_data"):
            logger.debug(
                f"[PIPELINE][EMBODIMENT] gateway received={result.will_conflict_data is not None}"
            )
        else:
            logger.debug("[EMBODIMENT_PIPELINE] field missing on result")

    def health(self) -> dict:
        return {"status": "ok", "mode": "direct"}

    def new_game(self, campaign_id: str) -> dict:
        """ADR-O-146: Сброс runtime мира к чистому static."""
        try:
            from game_loop_bridge import get_game_loop_bridge

            _bridge = get_game_loop_bridge()
            if (
                _bridge.ready
                and hasattr(_bridge, "_loop")
                and hasattr(_bridge._loop, "new_game")
            ):
                return _bridge._loop.new_game(campaign_id)
            return {"reset": True, "campaign_id": campaign_id, "files_removed": []}
        except Exception as e:
            return {"reset": False, "campaign_id": campaign_id, "error": str(e)}

    def create_player_session(self, campaign_id: str, player_name: str) -> dict:
        # Инициализируем при первом вызове (долго — загружает модели)
        if not self._bridge.ready:
            self._bridge.initialize()
        # Инициализация сцены теперь происходит на backend при /player/select (routes.py)
        return {"campaign_id": campaign_id, "player": player_name, "active": True}

    def get_session_state(self, campaign_id: str) -> dict:
        return {"campaign_id": campaign_id}

    def get_characters(self, campaign_id: str) -> list[dict]:
        # ADR-O-146: Через bridge, не через файлы. Law 1.1 — frontend не читает backend данные напрямую.
        if not self._bridge.ready:
            return []
        return self._bridge.get_characters(campaign_id)

    def idle_tick(self, campaign_id: str) -> dict:
        """Idle tick через TickOrchestrator (10 фаз, Устав §3).

        Делегирует в GameLoopBridge.idle_tick() → GameLoop → TickOrchestrator.
        Все фазы (0-10) выполняются внутри orchestrator, включая
        LifeEngine, DecisionHub, EventBus, Memory, WorldSnapshotBuilder.
        """
        try:
            from game_loop_bridge import get_game_loop_bridge

            _bridge = get_game_loop_bridge()
            if not _bridge.ready:
                logger.debug("[IDLE_TICK_CLIENT] bridge not ready, skipping")
                return {"status": "not_ready"}

            return _bridge.idle_tick(campaign_id)
        except Exception as e:
            import traceback

            logger.debug(f"[IDLE_TICK_CLIENT] ERROR: {e}\n{traceback.format_exc()}")
            return {"status": "error", "error": str(e), "npc_positions": {}}

    def send_action_stream(self, *args, **kwargs):
        """B3-FIX: SSE не поддерживается в Direct mode (нет HTTP-сервера)."""
        raise NotImplementedError("SSE streaming is not supported in Direct mode.")

    def get_world_state(
        self, campaign_id: str, after_tick: int | None = None
    ) -> dict | None:
        """B3-FIX: Возвращает текущий WorldSnapshot из GameLoop без выполнения тика."""
        from game_loop_bridge import get_game_loop_bridge

        _bridge = get_game_loop_bridge()
        if not _bridge.ready or not _bridge._loop:
            return None
        # Возвращаем кэшированный снапшот
        return _bridge._loop.get_world_snapshot(campaign_id)

    def save_scene_state(self, campaign_id: str, scene_state: dict) -> None:
        """B1.4-FIX: push scene_state to backend via Direct bridge."""
        from game_loop_bridge import get_game_loop_bridge

        _bridge = get_game_loop_bridge()
        if not _bridge.ready:
            _bridge.initialize()
        _bridge.save_scene_state(campaign_id, scene_state)

    def load_campaign(self, campaign_id: str, world_id: str = "default") -> dict:
        # Direct mode: GameLoop загружает лор при первом turn()
        return {
            "campaign_id": campaign_id,
            "world_id": world_id,
            "status": "ok",
            "loaded_files": [],
        }


# ═══════════════════════════════════════════════════════════════════════
# УРОВЕНЬ 5.5: FallbackGateway — HTTP с fallback на Direct
# ═══════════════════════════════════════════════════════════════════════


class FallbackGateway:
    def skip_time(self, campaign_id: str, ticks: int) -> dict:
        """FIX-2: FallbackGateway не имел skip_time — вызывало AttributeError."""
        # Делегируем в primary gateway, если есть
        if self._primary and hasattr(self._primary, "skip_time"):
            return self._primary.skip_time(campaign_id, ticks)
        # Если нет — заглушка (возвращаем пустой результат)
        logger.warning("[FALLBACK_GATEWAY] skip_time not available, returning empty")
        return {"status": "skipped", "ticks": 0}

    """
    HTTP приоритет, Direct fallback при обрыве.
    
    Логика:
    - send_action: пробует HTTP, при ошибке — Direct
    - Каждые _retry_interval запросов — перепроверяет HTTP
    - health: пробует HTTP, если упал — возвращает статус degraded
    """

    # Каждые N запросов пробуем HTTP снова (backend мог перезапуститься)
    _retry_interval: int = 5

    def __init__(self, primary: GameGateway, fallback: GameGateway) -> None:
        self._primary = primary
        self._fallback = fallback
        self._primary_healthy: bool | None = None  # None = ещё не проверяли
        self._requests_since_fail: int = 0

    def send_action(
        self,
        campaign_id: str,
        player_name: str,
        action_text: str,
        player_x: float = 0.0,
        player_y: float = 0.0,
        world_x: float | None = None,
        world_y: float | None = None,
    ) -> GameActionResponse:
        # Если HTTP помечен мёртвым — пробуем заново каждые _retry_interval запросов
        if self._primary_healthy is False:
            self._requests_since_fail += 1
            if self._requests_since_fail >= self._retry_interval:
                self._requests_since_fail = 0
                if self._try_primary_health():
                    self._primary_healthy = True
            if self._primary_healthy is False:
                return self._fallback.send_action(
                    campaign_id,
                    player_name,
                    action_text,
                    player_x,
                    player_y,
                    world_x,
                    world_y,
                )

        try:
            result = self._primary.send_action(
                campaign_id,
                player_name,
                action_text,
                player_x,
                player_y,
                world_x,
                world_y,
            )
            self._primary_healthy = True
            self._requests_since_fail = 0
            return result
        except BackendError:
            self._primary_healthy = False
            self._requests_since_fail = 0
            return self._fallback.send_action(
                campaign_id,
                player_name,
                action_text,
                player_x,
                player_y,
                world_x,
                world_y,
            )

    def _try_primary_health(self) -> bool:
        """Тихая проверка — не бросает исключение."""
        try:
            result = self._primary.health()
            return result.get("status") == "ok"
        except Exception:
            return False

    def health(self) -> dict:
        try:
            result = self._primary.health()
            self._primary_healthy = True
            return result
        except Exception:
            self._primary_healthy = False
            return {"status": "degraded", "mode": "direct_fallback"}

    def new_game(self, campaign_id: str) -> dict:
        """ADR-O-146: Сброс runtime мира к чистому static."""
        try:
            result = self._primary.new_game(campaign_id)
            self._primary_healthy = True
            return result
        except Exception:
            self._primary_healthy = False
            return self._fallback.new_game(campaign_id)

    def create_player_session(self, campaign_id: str, player_name: str) -> dict:
        try:
            result = self._primary.create_player_session(campaign_id, player_name)
            self._primary_healthy = True
            return result
        except Exception:
            self._primary_healthy = False
            return self._fallback.create_player_session(campaign_id, player_name)

    def get_session_state(self, campaign_id: str) -> dict:
        if self._primary_healthy is False:
            return self._fallback.get_session_state(campaign_id)
        try:
            return self._primary.get_session_state(campaign_id)
        except Exception:
            self._primary_healthy = False
            return self._fallback.get_session_state(campaign_id)

    def get_characters(self, campaign_id: str) -> list[dict]:
        if self._primary_healthy is False:
            return self._fallback.get_characters(campaign_id)
        try:
            return self._primary.get_characters(campaign_id)
        except Exception:
            self._primary_healthy = False
            return self._fallback.get_characters(campaign_id)

    def idle_tick(self, campaign_id: str) -> dict:
        # idle_tick некритичен — при ошибке молча игнорируем
        try:
            if self._primary_healthy is not False:
                return self._primary.idle_tick(campaign_id)
            return self._fallback.idle_tick(campaign_id)
        except Exception:
            return {"status": "error"}

    def save_scene_state(self, campaign_id: str, scene_state: dict) -> None:
        try:
            if self._primary_healthy is not False:
                self._primary.save_scene_state(campaign_id, scene_state)
            else:
                self._fallback.save_scene_state(campaign_id, scene_state)
        except Exception as e:
            logger.debug(f"[RETRY_GATEWAY] save_scene_state failed: {e}")

    def load_campaign(self, campaign_id: str, world_id: str = "default") -> dict:
        if self._primary_healthy is False:
            return self._fallback.load_campaign(campaign_id, world_id)
        try:
            return self._primary.load_campaign(campaign_id, world_id)
        except Exception:
            self._primary_healthy = False
            return self._fallback.load_campaign(campaign_id, world_id)


# ═══════════════════════════════════════════════════════════════════════
# УРОВЕНЬ 6: ActionQueue — неблокирующая очередь для Pygame
# ═══════════════════════════════════════════════════════════════════════


class _TelegraphText(str):
    """Строка с меткой — телеграф NPC, не действие игрока."""

    _is_telegraph: bool = True


@dataclass
class _PendingAction:
    """Внутреннее представление запроса в очереди."""

    action_id: str
    campaign_id: str
    player_name: str
    action_text: str
    submitted_at: float
    player_x: float = 0.0  # локальные координаты (legacy)
    player_y: float = 0.0
    # S82: Мировые координаты — PRIMARY spatial input для backend oracle.
    # Backend вычисляет actual_chunk НЕЗАВИСИМО. Никаких prediction-подсказок.
    world_x: float | None = None
    world_y: float | None = None
    is_telegraph: bool = False  # NPC телеграф — не действие игрока


@dataclass
class CompletedAction:
    """Результат обработки действия. Pygame читает это."""

    action_id: str
    response: GameActionResponse | None
    error: BackendError | None
    completed_at: float


class ActionQueue:
    """
    Неблокирующая очередь: Pygame main thread → Worker thread → Pygame main thread.

    LLM latency 1-10 секунд — без этого Pygame заморозится на каждый запрос.

    Использование:
        queue = ActionQueue(gateway)
        queue.start()  # запускает worker daemon thread

        # В Pygame main thread (при вводе):
        action_id = queue.submit("бью гоблина")

        # В Pygame main loop (каждый кадр):
        result = queue.poll()  # None если ещё не готово
        if result:
            if result.error:
                message_log.append(f"[Ошибка] {result.error}")
            else:
                message_log.append(result.response.dm_response)

    def stop(self) при завершении.
    """

    def __init__(self, gateway: GameGateway) -> None:
        self._gateway = gateway
        self._input: Queue[_PendingAction | None] = Queue()
        self._output: Queue[CompletedAction] = Queue()
        self._worker: threading.Thread | None = None
        self._running = False
        # Telegraph: id текущего автономного хода (None = нет активного)
        self._telegraph_id: str | None = None

    def start(self) -> None:
        """Запускает worker thread. Потоко-безопасно."""
        if self._running:
            return
        self._running = True
        self._worker = threading.Thread(target=self._worker_loop, daemon=True)
        self._worker.start()

    def stop(self) -> None:
        """Останавливает worker thread."""
        self._running = False
        self._input.put(None)  # Сигнал завершения
        if self._worker:
            self._worker.join(timeout=5)
            self._worker = None

    def submit(
        self,
        campaign_id: str,
        player_name: str,
        action_text: str,
        player_x: float = 0.0,
        player_y: float = 0.0,
        world_x: float | None = None,
        world_y: float | None = None,
    ) -> str:
        """
        Добавить действие в очередь. Неблокирующий — возвращает сразу.

        Returns:
            action_id для сопоставления с результатом
        """
        action_id = uuid.uuid4().hex[:8]
        self._input.put(
            _PendingAction(
                action_id=action_id,
                campaign_id=campaign_id,
                player_name=player_name,
                action_text=action_text,
                submitted_at=time.monotonic(),
                player_x=player_x,
                player_y=player_y,
                world_x=world_x,
                world_y=world_y,
            )
        )
        return action_id

    def poll(self) -> CompletedAction | None:
        """
        Проверить готовый результат. Неблокирующий.
        Вызывать каждый кадр из Pygame main loop.

        Returns:
            CompletedAction если есть, иначе None
        """
        # B7-FIX: ловит только queue.Empty, не KeyboardInterrupt.
        import queue

        try:
            return self._output.get_nowait()
        except queue.Empty:
            return None
        except Exception as e:
            logger.error(f"[ACTION_QUEUE] poll failed: {e}")
            return None

    def pending_count(self) -> int:
        """Количество действий в очереди (для UI индикатора)."""
        return self._input.qsize()

    def submit_telegraph(
        self,
        campaign_id: str,
        player_name: str,
        player_x: float = 0.0,
        player_y: float = 0.0,
        world_x: float | None = None,
        world_y: float | None = None,
        action_text: str | None = None,
    ) -> str:
        """
        Автономный ход мира — NPC действуют пока игрок думает.
        Telegraph отменяется если игрок нажал Enter раньше.
        """
        action_id = uuid.uuid4().hex[:8]
        self._telegraph_id = action_id
        self._input.put(
            _PendingAction(
                action_id=action_id,
                campaign_id=campaign_id,
                player_name=player_name,
                action_text=action_text
                or "[TELEGRAPH: мир живёт, опиши что делают NPC]",
                submitted_at=time.monotonic(),
                player_x=player_x,
                player_y=player_y,
                world_x=world_x,
                world_y=world_y,
                is_telegraph=True,
            )
        )
        return action_id

    def cancel_telegraph(self) -> None:
        """
        Игрок нажал Enter — отменяем telegraph.
        Результат будет проигнорирован по telegraph_id.
        """
        self._telegraph_id = None

    def is_telegraph_result(self, result: "CompletedAction") -> bool:
        """Возвращает True если result — это завершённый telegraph (не отменённый)."""
        return result.action_id == self._telegraph_id

    def _worker_loop(self) -> None:
        """Цикл worker thread — берёт из input, вызывает gateway, кладёт в output."""
        while self._running:
            pending = self._input.get()
            if pending is None:
                # Сигнал завершения
                break

            try:
                # Помечаем action_text флагом для передачи в payload
                _text = pending.action_text
                if pending.is_telegraph:
                    _text = _TelegraphText(_text)
                response = self._gateway.send_action(
                    campaign_id=pending.campaign_id,
                    player_name=pending.player_name,
                    action_text=_text,
                    player_x=pending.player_x,
                    player_y=pending.player_y,
                    world_x=pending.world_x,
                    world_y=pending.world_y,
                )
                self._output.put(
                    CompletedAction(
                        action_id=pending.action_id,
                        response=response,
                        error=None,
                        completed_at=time.monotonic(),
                    )
                )
            except BackendError as e:
                self._output.put(
                    CompletedAction(
                        action_id=pending.action_id,
                        response=None,
                        error=e,
                        completed_at=time.monotonic(),
                    )
                )
            except Exception as e:
                self._output.put(
                    CompletedAction(
                        action_id=pending.action_id,
                        response=None,
                        error=BackendError(str(e)),
                        completed_at=time.monotonic(),
                    )
                )


# ═══════════════════════════════════════════════════════════════════════
# ФАБРИКА — вместо singleton
# ═══════════════════════════════════════════════════════════════════════


def create_game_gateway(
    base_url: str = "http://127.0.0.1:8000",
    timeout_sec: int = 30,
) -> tuple[GameGateway, ActionQueue]:
    """
    Создаёт gateway с fallback: HTTP приоритет, Direct при обрыве.

    Pygame вызывает только этот метод — не знает про транспорт.

    Returns:
        (gateway, action_queue)
    """
    # Primary — HTTP через FastAPI
    transport = HttpClient(base_url=base_url, timeout_sec=timeout_sec)
    contract = BackendContract(transport)
    http_gateway = HttpGameGateway(contract)

    # Fallback — прямой вызов GameLoop без сети
    direct_gateway = DirectGameGateway()

    # Обёртка с автоматическим переключением
    gateway: GameGateway = FallbackGateway(http_gateway, direct_gateway)
    queue = ActionQueue(gateway)
    return gateway, queue


# ── Read-only запросы состояния (не через gateway) ────────────────────


def get_world_state(
    campaign_id: str,
    after_tick: int | None = None,
    base_url: str = "http://127.0.0.1:8000",
) -> dict | None:
    """Запрос снимка мира. Read-only, не идёт через GameGateway.

    Frontend вызывает для рендера NPC из WorldSnapshotDTO.
    Возвращает None при ошибке или 304 — frontend отрендерит без обновления.
    """
    try:
        client = HttpClient(base_url=base_url)
        params = f"campaign_id={campaign_id}"
        if after_tick is not None:
            params += f"&after_tick={after_tick}"
        return client.get(f"/api/world_state?{params}")
    except Exception:
        return None
