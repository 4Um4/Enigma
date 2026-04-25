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

path: /backend/api_client.py
Назначение: Слой связи Pygame ↔ Backend. Три уровня: Protocol (что знает Pygame) → Contract (маппинг) → Transport (HTTP). Плюс неблокирующая очередь.
Зависимости: urllib.request, json, threading, queue (stdlib)
Основные сущности: GameGateway, GameActionResponse, HttpClient, BackendContract, HttpGameGateway, ActionQueue
"""

from __future__ import annotations

import json
import threading
import time
import uuid
import urllib.request
import urllib.error
from dataclasses import dataclass
from typing import Protocol
from queue import Queue


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


# ═══════════════════════════════════════════════════════════════════════
# УРОВЕНЬ 2: Protocol (знает Pygame — через typing.Protocol)
# ═══════════════════════════════════════════════════════════════════════

class GameGateway(Protocol):
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
    ) -> GameActionResponse:
        """Отправить действие игрока. Блокирующий — вызывать из worker thread."""
        ...
    
    def health(self) -> dict:
        """Проверка здоровья backend."""
        ...
    
    def create_player_session(
        self, campaign_id: str, player_name: str
    ) -> dict:
        """Создать/активировать сессию игрока."""
        ...
    
    def get_session_state(self, campaign_id: str) -> dict:
        """Получить состояние сессии."""
        ...
    
    def get_characters(self, campaign_id: str) -> list[dict]:
        """Получить список персонажей."""
        ...
    
    def idle_tick(self, campaign_id: str) -> dict:
        """
        Тик мира без действия игрока.
        Pygame вызывает по таймеру пока игрок думает.
        Неблокирующий — вызывать из worker thread.
        """
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
            except Exception:
                pass  # не удалось прочитать тело ошибки HTTP
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
    ) -> GameActionResponse:
        """Маппинг: доменные аргументы → JSON payload → JSON response → доменный объект."""
        raw = self._t.post("/api/game/action", {
            "campaign": campaign_id,
            "player": player_name,
            "action": action_text,
            "player_x": player_x,
            "player_y": player_y,
            "is_telegraph": getattr(action_text, '_is_telegraph', False),
        })
        return self._map_action_response(raw)
    
    def health(self) -> dict:
        return self._t.get("/api/health")
    
    def create_player_session(
        self, campaign_id: str, player_name: str
    ) -> dict:
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

    def load_campaign(self, campaign_id: str, world_id: str = "default") -> dict:
        return self._t.post(
            f"/api/campaign/load",
            {"campaign_id": campaign_id, "world_id": world_id},
        )
    
    @staticmethod
    def _map_action_response(raw: dict) -> GameActionResponse:
        """Маппинг JSON → доменный объект. Единственное место с полями ответа."""
        return GameActionResponse(
            dm_response=raw.get("response", ""),
            npc_reactions=raw.get("npc_reactions", []),
            world_changes=raw.get("world_changes", []),
            journal_entry_id=raw.get("journal_entry_id"),
            game_time_seconds=raw.get("game_time_seconds", 0),
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
    ) -> GameActionResponse:
        return self._contract.send_action(campaign_id, player_name, action_text, player_x, player_y)
    
    def health(self) -> dict:
        return self._contract.health()
    
    def create_player_session(
        self, campaign_id: str, player_name: str
    ) -> dict:
        return self._contract.create_player_session(campaign_id, player_name)
    
    def get_session_state(self, campaign_id: str) -> dict:
        return self._contract.get_session_state(campaign_id)
    
    def get_characters(self, campaign_id: str) -> list[dict]:
        return self._contract.get_characters(campaign_id)
    
    def idle_tick(self, campaign_id: str) -> dict:
        return self._contract.idle_tick(campaign_id)

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
        # Инициализация ModelPool в pygame процессе — без этого пул пустой
        from app.services.llm.provider_manager import initialize_model_pool
        initialize_model_pool()
        from game_loop_bridge import get_game_loop_bridge
        self._bridge = get_game_loop_bridge()
        self._last_player_pos: tuple[float, float] | None = None
    
    def send_action(
        self,
        campaign_id: str,
        player_name: str,
        action_text: str,
        player_x: float = 0.0,
        player_y: float = 0.0,
    ) -> GameActionResponse:
        # Инициализируем при первом вызове (долго — загружает модели)
        if not self._bridge.ready:
            self._bridge.initialize()
        
        # TODO: передать player_x, player_y в bridge.turn() для локального режима
        result = self._bridge.turn(
            campaign_id=campaign_id,
            player_name=player_name,
            action_text=action_text,
        )
        
        if result.error:
            raise BackendError(result.error)
        
        return GameActionResponse(
            dm_response=result.dm_text,
            npc_reactions=result.npc_reactions,
            world_changes=[],
            journal_entry_id=None,
            game_time_seconds=result.game_time_seconds,
        )
    
    def health(self) -> dict:
        return {"status": "ok", "mode": "direct"}
    
    def _advance_time_by_movement(self, campaign_id: str, distance: float) -> None:
        """Удалено: время продвигается в game_screen.py при каждом шаге через Calendar."""
        pass
    
    def create_player_session(
        self, campaign_id: str, player_name: str
    ) -> dict:
        # Инициализируем при первом вызове (долго — загружает модели)
        if not self._bridge.ready:
            self._bridge.initialize()
        # Компилируем scene_state из editor JSON — чтобы Pygame рендерил до первого хода
        self._bridge.ensure_scene_initialized(campaign_id)
        return {"campaign_id": campaign_id, "player": player_name, "active": True}
    
    def get_session_state(self, campaign_id: str) -> dict:
        return {"campaign_id": campaign_id}
    
    def get_characters(self, campaign_id: str) -> list[dict]:
        # Читаем напрямую из characters.json
        from pathlib import Path
        char_file = Path("data/campaigns") / campaign_id / "characters.json"
        if not char_file.exists():
            return []
        try:
            import json
            with open(char_file, "r", encoding="utf-8-sig") as f:
                return json.load(f)
        except Exception:
            return []
    
    def idle_tick(self, campaign_id: str) -> dict:
        """Прямой вызов life_engine + DecisionHub — без LLM, без action."""
        try:
            from app.services.npc.life_engine import get_life_engine
            from game_loop_bridge import get_game_loop_bridge
            _bridge = get_game_loop_bridge()
            if not _bridge.ready:
                print("[IDLE_TICK_CLIENT] bridge not ready, skipping")
                return {"status": "not_ready"}

            _engine = get_life_engine()
            _runtime_path = _bridge._loop._get_npc_runtime_path(campaign_id)
            _scene = _bridge._loop.scene_manager.get_scene_state(campaign_id, "")

            # LifeEngine: расписание, стресс, случайные события
            changes = _engine.tick(campaign_id, _scene, runtime_path=_runtime_path)
            if changes:
                _bridge._loop.scene_manager.apply_changes(campaign_id, changes, _scene)

            # DecisionHub: NPC думают, давление накапливается
            decision_events = _engine.tick_decisions(campaign_id, _scene, runtime_path=_runtime_path)
            significant_events = list(decision_events)

            # Фильтруем life_engine события по расстоянию до игрока
            if _scene:
                _player_pos = _scene.get("player_spatial", {}).get("local_position", {})
                _px, _py = _player_pos.get("x", 0), _player_pos.get("y", 0)
                for _ch in changes:
                    if not _ch.cause or not _ch.cause.startswith("life_engine"):
                        continue
                    _npc_pos = _scene.get("npc_positions", {}).get(_ch.target, {})
                    _nx, _ny = _npc_pos.get("x", 0), _npc_pos.get("y", 0)
                    _dist = ((_nx - _px)**2 + (_ny - _py)**2) ** 0.5
                    if _dist < 20:
                        significant_events.append({
                            "cause": _ch.cause,
                            "type": _ch.type.value,
                            "target": _ch.target,
                            "field": _ch.field,
                            "value": str(_ch.value),
                        })

            return {
                "status": "ok",
                "changes": len(changes),
                "npc_positions": _scene.get("npc_positions", {}) if _scene else {},
                "events": significant_events,
            }
        except Exception as e:
            import traceback
            print(f"[IDLE_TICK_CLIENT] ERROR: {e}\n{traceback.format_exc()}")
            return {"status": "error", "error": str(e)}

    def load_campaign(self, campaign_id: str, world_id: str = "default") -> dict:
        # Direct mode: GameLoop загружает лор при первом turn()
        return {"campaign_id": campaign_id, "world_id": world_id, "status": "ok", "loaded_files": []}


# ═══════════════════════════════════════════════════════════════════════
# УРОВЕНЬ 5.5: FallbackGateway — HTTP с fallback на Direct
# ═══════════════════════════════════════════════════════════════════════

class FallbackGateway:
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
    ) -> GameActionResponse:
        # Если HTTP помечен мёртвым — пробуем заново каждые _retry_interval запросов
        if self._primary_healthy is False:
            self._requests_since_fail += 1
            if self._requests_since_fail >= self._retry_interval:
                self._requests_since_fail = 0
                if self._try_primary_health():
                    self._primary_healthy = True
            if self._primary_healthy is False:
                return self._fallback.send_action(campaign_id, player_name, action_text, player_x, player_y)
        
        try:
            result = self._primary.send_action(campaign_id, player_name, action_text, player_x, player_y)
            self._primary_healthy = True
            self._requests_since_fail = 0
            return result
        except BackendError:
            self._primary_healthy = False
            self._requests_since_fail = 0
            return self._fallback.send_action(campaign_id, player_name, action_text, player_x, player_y)
    
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
    
    def create_player_session(
        self, campaign_id: str, player_name: str
    ) -> dict:
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
    player_x: float = 0.0  # координаты для синхронизации с бэкендом
    player_y: float = 0.0
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
    ) -> str:
        """
        Добавить действие в очередь. Неблокирующий — возвращает сразу.
        
        Returns:
            action_id для сопоставления с результатом
        """
        action_id = uuid.uuid4().hex[:8]
        self._input.put(_PendingAction(
            action_id=action_id,
            campaign_id=campaign_id,
            player_name=player_name,
            action_text=action_text,
            submitted_at=time.monotonic(),
            player_x=player_x,
            player_y=player_y,
        ))
        return action_id
    
    def poll(self) -> CompletedAction | None:
        """
        Проверить готовый результат. Неблокирующий.
        Вызывать каждый кадр из Pygame main loop.
        
        Returns:
            CompletedAction если есть, иначе None
        """
        try:
            return self._output.get_nowait()
        except Exception:
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
        action_text: str | None = None,
    ) -> str:
        """
        Автономный ход мира — NPC действуют пока игрок думает.
        Telegraph отменяется если игрок нажал Enter раньше.
        """
        action_id = uuid.uuid4().hex[:8]
        self._telegraph_id = action_id
        self._input.put(_PendingAction(
            action_id=action_id,
            campaign_id=campaign_id,
            player_name=player_name,
            action_text=action_text or "[TELEGRAPH: мир живёт, опиши что делают NPC]",
            submitted_at=time.monotonic(),
            player_x=player_x,
            player_y=player_y,
            is_telegraph=True,
        ))
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
                )
                self._output.put(CompletedAction(
                    action_id=pending.action_id,
                    response=response,
                    error=None,
                    completed_at=time.monotonic(),
                ))
            except BackendError as e:
                self._output.put(CompletedAction(
                    action_id=pending.action_id,
                    response=None,
                    error=e,
                    completed_at=time.monotonic(),
                ))
            except Exception as e:
                self._output.put(CompletedAction(
                    action_id=pending.action_id,
                    response=None,
                    error=BackendError(str(e)),
                    completed_at=time.monotonic(),
                ))


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