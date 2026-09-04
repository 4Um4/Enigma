# path: /project/backend/tests/gameplay/harness.py
# Назначение: TavernGameplayHarness — канонический harness §5a.2.
#   Единственная входная точка gameplay-тестов в production runtime.
#   Запреты: моки зависимостей (§13.4), второй engine (§5a.2), прямые
#   вызовы внутренних writers. Тики — только game_loop.idle_tick();
#   player-действия — только run_turn() (REST-путь, PROBE 9.7).
# Зависимости: game_loop_builder, scene_init, player_session_service, EventBus.
# Основные сущности: TavernGameplayHarness, GameplayCounters.
import logging
import os
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("gameplay.harness")

_CAMPAIGN = "Open_road"
_LOCATION = "tavern_silver_wolf"  # по player-прецеденту; DriftLab "tavern" — расхождение, диагностируется
_PLAYER = "Tester"

# Пассивный tap-набор (зеркало ObservabilityTap; getattr-фильтр защищает
# от отсутствующих членов EventType). Отказ наблюдателя не роняет поток.
_TAP_EVENT_NAMES = (
    "NPC_SPOKE", "NPC_MOVED", "NPC_PROXIMITY_CLOSE", "NPC_PROXIMITY_LEAVE",
    "SOCIAL_ACTION", "COMMUNICATION_CLAIM", "OFFER_JOB", "REQUEST_SERVICE",
    "SPREAD_RUMOR", "CALL_FOR_HELP", "CHANGE_ROLE", "WARN", "TRADE",
    "REPORT", "THEFT", "COMBAT", "FATE_EVENT",
)


@dataclass
class GameplayCounters:
    """Пассивные счётчики живости (паттерн ObservabilityTap, локальная копия).
    Отказ наблюдателя не роняет поток (CDS §11)."""

    ticks: int = 0
    game_time_seconds: float = 0.0
    events_by_type: Dict[str, int] = field(default_factory=dict)
    decision_events: int = 0
    npc_spoke: int = 0
    npc_moved: int = 0
    traversals_created: int = 0
    pending_tasks_tail: List[int] = field(default_factory=list)
    last_event: str = ""

    def on_event(self, event: Any) -> None:
        try:
            _t = getattr(event, "type", "")
            _t = _t if isinstance(_t, str) else getattr(_t, "value", str(_t))
            self.events_by_type[_t] = self.events_by_type.get(_t, 0) + 1
            self.last_event = f"{_t}:{getattr(event, 'source', '')}"
            if _t == "npc_spoke":
                self.npc_spoke += 1
            if _t == "npc_moved":
                self.npc_moved += 1
        except Exception:  # noqa: S110
            pass

    def observe_scene(self, scene_state: dict) -> None:
        try:
            self.pending_tasks_tail.append(len(scene_state.get("pending_tasks", []) or []))
            self.traversals_created = len(scene_state.get("active_traversals", {}) or {})
        except Exception:  # noqa: S110
            pass


class TavernGameplayHarness:
    """§5a.2: все операции — обёртки production-путей."""

    def __init__(self, seed: int = 42, location: str = _LOCATION) -> None:
        self.seed = seed
        self.location = location
        self._tmpdir: Optional[Path] = None
        self.game_loop: Any = None
        self.counters = GameplayCounters()
        self._subscribed = False
        self._last_tick_scene: Optional[dict] = None

    def new_game(self) -> None:
        """Собирает production runtime через build_game_loop; temp-saves изоляция."""
        from app.services.game_loop_builder import build_game_loop

        self._tmpdir = Path(tempfile.mkdtemp(prefix="gc00_"))
        _data_dir = Path(os.environ.get("ENIGMA_DATA_DIR", "backend/data"))
        _saves_backup = os.environ.get("ENIGMA_SAVES_DIR")
        os.environ["ENIGMA_SAVES_DIR"] = str(self._tmpdir)
        try:
            self.game_loop = build_game_loop(_data_dir)
        finally:
            if _saves_backup is None:
                os.environ.pop("ENIGMA_SAVES_DIR", None)
            else:
                os.environ["ENIGMA_SAVES_DIR"] = _saves_backup
        self._attach_counters()
        self._init_player_precedent()

    def _attach_counters(self) -> None:
        try:
            from app.services.events.event_bus import get_event_bus
            from app.services.events.event_types import EventType

            _bus = get_event_bus()
            self._tap_events = [
                _et for _et in
                (getattr(EventType, _n, None) for _n in _TAP_EVENT_NAMES)
                if _et is not None
            ]
            for _et in self._tap_events:
                _bus.subscribe(_et, self.counters.on_event)
            self._subscribed = True
        except Exception as e:
            logger.warning(f"[GC00] counters attach failed: {e}")

    def _init_player_precedent(self) -> None:
        """Прецедент test_player_turn_headless: campaign → scene → аватар."""
        from app.services.game_loop.scene_init import ensure_scene_initialized
        from app.services.player_session_service import player_session_service

        self.game_loop.load_campaign(_CAMPAIGN, _CAMPAIGN)
        ensure_scene_initialized(self.game_loop, _CAMPAIGN)
        player_session_service.select_player(_CAMPAIGN, _PLAYER)
        self._init_avatar_body()



    def _init_avatar_body(self) -> None:
        """Аватар через production-фабрику avatar_service.load_state (§13.4:
        фабрика вместо конструктора-мечты; пишет канонический объект с
        каноническими дефолтами; ADR-WRITE-GUARD не задет — writing не нужен)."""
        _avatar = self.game_loop.avatar_service.load_state(_CAMPAIGN, _PLAYER)
        logger.info(
            f"[GC00-SETUP] avatar loaded: id={_avatar.npc_id} "
            f"hp={_avatar.body_state.get('current_hp', 'MISSING')}"
        )
        # Тестовый слой не мутирует NPCState (guard). Характер/дефолты
        # поставляет сама фабрика; специфичные профили — через штатные
        # services при появлении такой потребности в GC-сценариях.

    def advance_ticks(self, n: int) -> List[dict]:
        """Прогон n тиков ЧЕРЕЗ production idle_tick (commit → execute_pending →
        unlock). Возвращает список tick-словарей для детерминизм-сравнения."""
        _results: List[dict] = []
        for _ in range(n):
            _r = self.game_loop.idle_tick(_CAMPAIGN)
            self.counters.ticks += 1
            _scene = self._scene_after_tick(_r)
            if _scene is not None:
                self.counters.observe_scene(_scene)
                self._last_tick_scene = _scene
                self.counters.game_time_seconds = _scene.get("game_time_seconds", 0.0) or 0.0
            _results.append(self._tick_fingerprint(_r))
        return _results

    def _scene_after_tick(self, tick_result: Any) -> Optional[dict]:
        """Авторитетная сцена после тика: final_state / final_scene_state /
        shared_context.scene_state; None — если ни один путь не дал dict."""
        _candidates: list = []
        if isinstance(tick_result, dict):
            _candidates = [tick_result.get("final_state"), tick_result.get("final_scene_state")]
        else:
            _candidates = [
                getattr(tick_result, "final_state", None),
                getattr(tick_result, "final_scene_state", None),
            ]
        for _s in _candidates:
            if isinstance(_s, dict):
                return _s
        _sc = getattr(tick_result, "shared_context", None)
        _s = getattr(_sc, "scene_state", None) if _sc else None
        if isinstance(_s, dict):
            return _s
        # Fallback: авторитетный post-commit слот (тот же, что сам idle_tick
        # использует для execute_pending) — read-only, CDS §11
        try:
            _scenes = getattr(self.game_loop.scene_manager, "_tick_scenes", None) or {}
            if _scenes:
                _loc_key = self.location if self.location in _scenes else next(iter(_scenes))
                return _scenes.get(_loc_key)
        except Exception:  # noqa: S110
            pass
        return None

    def _tick_fingerprint(self, tick_result: Any) -> dict:
        """Компактный отпечаток тика для A/B-сравнения детерминизма."""
        _scene = self._scene_after_tick(tick_result)
        if _scene is None:
            return {"tick": None, "time": None, "npc": None, "pending": None}
        return {
            "tick": _scene.get("tick"),
            "time": _scene.get("game_time_seconds"),
            "npc": len(_scene.get("npc_positions", {}) or {}),
            "pending": len(_scene.get("pending_tasks", []) or []),
        }

    def player_action(self, action_text: str) -> Any:
        """Player-ход ЧЕРЕЗ production REST-путь run_turn (PROBE 9.7-контур)."""
        from app.models.schemas import ChatTurnRequest, PlayerAction

        _req = ChatTurnRequest(
            actions=[PlayerAction(player_name=_PLAYER, action=action_text)],
            campaign_id=_CAMPAIGN,
            world_id=_CAMPAIGN,
            location=self.location,
        )
        _resp = __import__("asyncio").run(self.game_loop.run_turn(_req))
        self.counters.ticks += 0  # REST-ход не тик; счётчик не растёт
        return _resp

    def inspect_npc(self, npc_id: str) -> Optional[dict]:
        """Read-only: слепок NPC из авторитетного runtime (LifeEngine-кэш)."""
        for _n in self.game_loop._resolve_npcs_snapshot(_CAMPAIGN) or []:
            if _n.get("id") == npc_id or _n.get("npc_id") == npc_id:
                return _n
        return None

    def get_scene_fresh(self) -> Optional[dict]:
        """Read-only: живая post-commit сцена scene_manager._tick_scenes
        (для проверок ПОСЛЕ player_action — run_turn коммитит сам, S128)."""
        try:
            _scenes = getattr(self.game_loop.scene_manager, "_tick_scenes", None) or {}
            if _scenes:
                _loc_key = self.location if self.location in _scenes else next(iter(_scenes))
                return _scenes.get(_loc_key)
        except Exception:  # noqa: S110
            pass
        return None

    def get_scene(self) -> Optional[dict]:
        """Read-only: текущая сцена (последний тик или из scene_manager)."""
        if self._last_tick_scene is not None:
            return self._last_tick_scene
        try:
            return self.game_loop.scene_manager.get_scene_state(_CAMPAIGN, self.location)
        except Exception:
            return None

    def dispose(self) -> None:
        """Остановка: отписка наблюдателя + чистка temp-saves."""
        if self._subscribed:
            try:
                from app.services.events.event_bus import get_event_bus

                _bus = get_event_bus()
                for _et in getattr(self, "_tap_events", []):
                    _bus.unsubscribe(_et, self.counters.on_event)
            except Exception as e:
                logger.warning(f"[GC00] unsubscribe failed: {e}")
        if self._tmpdir is not None:
            try:
                shutil.rmtree(self._tmpdir, ignore_errors=True)
            except Exception as e:
                logger.warning(f"[GC00] tmpdir cleanup failed: {e}")
        self.game_loop = None

    def __enter__(self) -> "TavernGameplayHarness":
        self.new_game()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.dispose()