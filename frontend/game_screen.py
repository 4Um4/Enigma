"""
path: /frontend/game_screen.py

Экран игры — связывает player_cognition pipeline с scene_renderer.
Загружает состояние кампании, прогоняет pipeline каждый кадр, рендерит результат.

Назначение: Экран игры — загружает кампанию, прогоняет pipeline, рендерит карту, возвращает управление в меню по ESC
Зависимости: pygame, scene_renderer, player_cognition.pipeline, movement_system, intent_parser, json, pathlib
Основные сущности: GameScreen, _MoveState
"""

import contextlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pygame
import logging

logger = logging.getLogger(__name__)

from perceptual_momentum import PerceptualMomentum
from presentation_firewall import sanitize_perceptual_input

from scene_renderer import SceneRenderer
from text_input import TextInput
from game_types import (
    PerceptionConfig,
    PlayerFocus,
    PlayerMemory,
    EncounterHistory,
    PerceivedScene,
    PerceivedEntity,
    PerceivedEnvironment,
)
# Спринт 31: Локальная физика и парсер интентов удалены. Фронтенд — честный интерполятор.


def _build_perceived_scene(scene_state: dict, config: PerceptionConfig) -> PerceivedScene:
    """Локальная сборка PerceivedScene из scene_state (Закон 1.1: Фронтенд не лезет в бэкенд)."""
    entities: List[PerceivedEntity] = []
    
    # RUNTIME DATA ARCHEOLOGY: Проверяем совпадение npc_id
    _pp = scene_state.get("player_perception") or {}
    
    # Конвертируем NPC из scene_state
    for npc_id, npc_data in scene_state.get("npc_positions", {}).items():
        # БАГ D2 FIX: Player не рендерится как NPC
        if npc_id == "player":
            continue
        # ADR-019: Каузальный Lerp. Интерполируем позицию, если NPC в транзите.
        pos = _resolve_visual_xy(npc_id, scene_state)
        x, y = float(pos.get("x", 0)), float(pos.get("y", 0))
        # УБРАНО: render spam (диагностика ADR-0013 завершена, рендерер невиновен)
        # Рендер spam полностью удалён. Трассировка только при изменении позиции (TASK 4).
            
        # Спринт 30: извлекаем кинематику для непрерывной интерполяции в рендерере
        traversals = scene_state.get("active_traversals", [])
        trav = None
        if isinstance(traversals, list):
            trav = next((t for t in traversals if t.get("npc_id") == npc_id), None)
        elif isinstance(traversals, dict):
            trav = traversals.get(npc_id)

        entities.append(PerceivedEntity(
            entity_id=npc_id,
            entity_type="npc",
            x=x,
            y=y,
            visible=True,
            los=True,
            display_name=npc_data.get("display_name") or npc_data.get("name") or npc_id.split("_")[-1].capitalize(),
            in_attention=(config.player_focus.focus_entity_id == npc_id),
            # Спринт 30: Каузальная презентация. Передаем кинематику в рендерер для непрерывного lerp
            traversal_status=trav.get("status", "IDLE") if trav else "IDLE",
            path_waypoints=trav.get("path_waypoints", []) if trav else [],
            current_waypoint_idx=trav.get("current_waypoint_idx", 0) if trav else 0,
            traversal_progress=float(trav.get("progress", 0.0)) if trav else 0.0,
            traversal_speed=float(trav.get("speed", 1.5)) if trav else 1.5,
            # Спринт 30: Модель C — когнитивный паралич рвет моторику
            initiative_suppression=float(npc_data.get("initiative_suppression", 0.0)),
            # The Fool v2: Инъекция моторных следов и наблюдений
            is_frozen=next((t.get("is_frozen", False) for t in (scene_state.get("player_perception") or {}).get("embodied_traces") or [] if t.get("npc_id") == npc_id), False),
            is_shaking=next((t.get("is_shaking", False) for t in (scene_state.get("player_perception") or {}).get("embodied_traces") or [] if t.get("npc_id") == npc_id), False),
            instability=next((t.get("locomotion_instability", 0.0) for t in (scene_state.get("player_perception") or {}).get("embodied_traces") or [] if t.get("npc_id") == npc_id), 0.0),
            perception_cues=[c for c in (scene_state.get("player_perception") or {}).get("peripheral_cues", []) if c.get("npc_id") == npc_id]
        ))
        
    return PerceivedScene(
        location_id=scene_state.get("location_id", "unknown"),
        entities=entities,
        environment=PerceivedEnvironment(),
        attention_focus_id=config.player_focus.focus_entity_id
    )
# A2: npc_movement удалён — NPC двигает TransitTracker (backend, 1 шаг/тик)
# Плавная интерполяция между DTO-снимками — отдельная задача
from api_client import create_game_gateway, ActionQueue
from i18n import t, activity_ru, manifest_color
# Тайминги опроса backend из constants.py (frontend-side)
from constants import (
    IDLE_TICK_NEAR_MS, IDLE_TICK_MID_MS, IDLE_TICK_FAR_MS,
    IDLE_TICK_NEAR_RADIUS, IDLE_TICK_MID_RADIUS,
)


_SAVES_DIR = Path(__file__).resolve().parents[1] / "saves"
_CAMPAIGNS_DIR = Path(__file__).parent / "map_editor" / "campaigns"

_MOVE_INTERVAL = 0.08  # секунд между шагами


@dataclass
class _MoveState:
    """Разделение природ: Навигация, Кинетика, Эмбодимент (Устав Мастера Тая)"""
    # --- Навигация (Куда идём) ---
    target_npc_id: Optional[str] = None
    path: Optional[list] = None
    path_index: int = 0
    direction: Optional[str] = None  # Легаси

    # --- Кинетика (Как движемся) ---
    cooldown: float = 0.0
    walk_distance_accumulated: float = 0.0  # Накопленное расстояние (м) для расчёта времени

    # --- Эмбодимент / Внимание (Куда смотрим) ---
    facing_angle: float = -math.pi / 2  # Куда смотрит агент (рад). Изначально — вверх
    facing_mode: str = "VELOCITY"  # "VELOCITY" (по движению), "LOOK_TARGET" (на цель), "FREE" (зафиксирован)


# S85: Функции _load_campaign_state и _load_location_meta удалены.
# Чтение JSON-зеркал запрещено (Frontend Debt Cleanup).


def _player_xy(scene_state: dict) -> tuple[float, float]:
    """Извлекает координаты игрока"""
    ps = scene_state.get("player_spatial", {})
    lp = ps.get("local_position") or {}
    return float(lp.get("x", 5.0)), float(lp.get("y", 5.0))


def _set_player_xy(scene_state: dict, x: float, y: float) -> None:
    """Обновляет координаты игрока в scene_state"""
    scene_state["player_spatial"]["local_position"]["x"] = x
    scene_state["player_spatial"]["local_position"]["y"] = y


PLAYER_RADIUS = 0.25  # Радиус коллизии игрока (в метрах)


def _resolve_player_collisions(px: float, py: float, walls: list, obstacles: list) -> tuple[float, float]:
    """Выталкивает игрока из стен и препятствий (Push-out Resolution).
    Возвращает скорректированные координаты. Обеспечивает скольжение вдоль стен."""
    
    # 1. Стены (отрезки)
    for wall in walls:
        x1, y1 = wall.get("x1", 0), wall.get("y1", 0)
        x2, y2 = wall.get("x2", 0), wall.get("y2", 0)
        dx, dy = x2 - x1, y2 - y1
        if dx == 0 and dy == 0:
            proj_x, proj_y = x1, y1
        else:
            t = max(0, min(1, ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)))
            proj_x = x1 + t * dx
            proj_y = y1 + t * dy
            
        diff_x = px - proj_x
        diff_y = py - proj_y
        dist = math.hypot(diff_x, diff_y)
        
        if dist < PLAYER_RADIUS:
            if dist == 0:
                # Выталкиваем по перпендикуляру к стене
                nx, ny = -dy, dx
                norm = math.hypot(nx, ny)
                if norm > 0:
                    nx, ny = nx / norm, ny / norm
                else:
                    nx, ny = 0, 1
                px += nx * PLAYER_RADIUS
                py += ny * PLAYER_RADIUS
            else:
                push = PLAYER_RADIUS - dist
                px += (diff_x / dist) * push
                py += (diff_y / dist) * push

    # 2. Препятствия (AABB прямоугольники). Бэкенд отдаёт левый верхний угол (x, y) + (w, h)
    # S81-ФИКС: Проходимые объекты не блокируют движение
    # Data-driven: passability.walk=True → проходимо. Fallback: type в _PASSABLE_TYPES
    _PASSABLE_TYPES = {"door", "door_transition", "transition", "window"}
    for obj in obstacles:
        _passthrough = obj.get("passability", {}).get("walk", None)
        if _passthrough is True:
            continue
        if _passthrough is None and obj.get("type", "") in _PASSABLE_TYPES:
            continue
        left = obj.get("x", 0)
        top = obj.get("y", 0)
        right = left + obj.get("w", 0)
        bottom = top + obj.get("h", 0)
        
        # Ближайшая точка на прямоугольнике к игроку
        closest_x = max(left, min(px, right))
        closest_y = max(top, min(py, bottom))
        
        diff_x = px - closest_x
        diff_y = py - closest_y
        dist = math.hypot(diff_x, diff_y)
        
        if dist < PLAYER_RADIUS:
            if dist == 0:
                # Игрок внутри прямоугольника — выталкиваем по кратчайшей оси
                overlap_left = px - left
                overlap_right = right - px
                overlap_top = py - top
                overlap_bottom = bottom - py
                
                min_overlap = min(overlap_left, overlap_right, overlap_top, overlap_bottom)
                if min_overlap == overlap_left: px = left - PLAYER_RADIUS
                elif min_overlap == overlap_right: px = right + PLAYER_RADIUS
                elif min_overlap == overlap_top: py = top - PLAYER_RADIUS
                else: py = bottom + PLAYER_RADIUS
            else:
                push = PLAYER_RADIUS - dist
                px += (diff_x / dist) * push
                py += (diff_y / dist) * push
                
    return px, py


def _nearest_npc_distance(scene_state: dict) -> float:
    """Минимальное расстояние от игрока до ближайшего NPC с координатами."""
    px, py = _player_xy(scene_state)
    min_dist = 999.0
    for npc_data in scene_state.get("npc_positions", {}).values():
        lp = npc_data.get("local_position") or {}
        if not lp:
            continue
        nx, ny = float(lp.get("x", 0)), float(lp.get("y", 0))
        dist = math.hypot(nx - px, ny - py)
        if dist < min_dist:
            min_dist = dist
    return min_dist


def _idle_tick_interval_ms(nearest_dist: float) -> int:
    """Фаза 2.1 — интервал тика зависит от расстояния до ближайшего NPC."""
    if nearest_dist <= IDLE_TICK_NEAR_RADIUS:
        return IDLE_TICK_NEAR_MS
    elif nearest_dist <= IDLE_TICK_MID_RADIUS:
        return IDLE_TICK_MID_MS
    else:
        return IDLE_TICK_FAR_MS


def _resolve_visual_xy(npc_id: str, scene_state: dict) -> dict:
    """ADR-019 + ETKE-IK: MotionRenderRouter.
    Выбирает источник интерполяции: VelocityRenderer (ETKE-IK) или WaypointRenderer (FSM).
    """
    traversals = scene_state.get("active_traversals", [])
    trav = None

    if isinstance(traversals, list):
        for t in traversals:
            if t.get("npc_id") == npc_id:
                trav = t
                break
    elif isinstance(traversals, dict):
        trav = traversals.get(npc_id)

    # 1. ETKE-IK VelocityRenderer: если есть velocity — прогнозируем позицию (инерция)
    npc_data = scene_state.get("npc_positions", {}).get(npc_id, {})
    vel = npc_data.get("velocity", (0.0, 0.0))
    if isinstance(vel, (list, tuple)) and (abs(vel[0]) > 0.01 or abs(vel[1]) > 0.01):
        lp = npc_data.get("local_position", {"x": 0.0, "y": 0.0})
        _target_x = lp.get("x", 0.0) + vel[0] * 0.1
        _target_y = lp.get("y", 0.0) + vel[1] * 0.1
        return {"x": _target_x, "y": _target_y}

    # 2. Traversal FSM WaypointRenderer: если есть active_traversals — интерполируем по графу
    if trav and trav.get("status") in ("PENDING", "MOVING"):
        wp = trav.get("path_waypoints", [])
        started_tick = int(trav.get("started_tick", 0))
        duration_ticks = max(1, int(trav.get("duration_ticks", 1)))

        if wp and len(wp) >= 2 and duration_ticks > 0:
            current_tick = int(scene_state.get("tick", 0))
            progress = min(1.0, max(0.0, (current_tick - started_tick) / duration_ticks))
            # CEI-3b: Multi-waypoint интерполяция — маршрут через промежуточные узлы графа
            num_segments = len(wp) - 1
            segment_progress = progress * num_segments
            segment_idx = min(int(segment_progress), num_segments - 1)
            segment_frac = segment_progress - segment_idx
            return _extracted_from__resolve_visual_xy_(segment_idx, wp, segment_frac)

    # 3. Fallback: Каузальная Истина (нет движения)
    lp = npc_data.get("local_position")
    if isinstance(lp, dict) and isinstance(lp.get("x"), (int, float)):
        return lp
    # CEI-3b: Fallback — destination traversal вместо (0,0)
    if trav:
        wp = trav.get("path_waypoints", [])
        if len(wp) >= 1:
            return {"x": float(wp[-1][0]), "y": float(wp[-1][1])}
    return {"x": 0, "y": 0}  # Абсолютный fallback — не должен достигаться при корректных данных


# TODO Rename this here and in `_resolve_visual_xy`
def _extracted_from__resolve_visual_xy_(idx, wp, progress):
    if idx >= len(wp) - 1:
        return {"x": float(wp[-1][0]), "y": float(wp[-1][1])}      


    from_xy = wp[idx]
    to_xy = wp[idx + 1]
    x = float(from_xy[0]) + (float(to_xy[0]) - float(from_xy[0])) * progress
    y = float(from_xy[1]) + (float(to_xy[1]) - float(from_xy[1])) * progress
    return {"x": x, "y": y}


def _check_transition_trigger(scene_state: dict, px: float, py: float, system_log: list) -> None:
    """Проверяет, наступил ли игрок на триггер перехода (door_transition)."""
    for obj_id, obj_data in scene_state.get("objects", {}).items():
        if obj_data.get("type") != "door_transition":
            continue
        pos = obj_data.get("position", {})
        size = obj_data.get("size", {})
        ox, oy = pos.get("x", 0), pos.get("y", 0)
        ow, oh = size.get("w", 1), size.get("h", 1)

        # Проверка попадания в прямоугольник объекта
        if (ox - ow / 2 <= px <= ox + ow / 2) and (oy - oh / 2 <= py <= oy + oh / 2):
            props = obj_data.get("properties", {})
            target_file = props.get("target_file", "")
            target_portal = props.get("target_portal", "")

            if target_file:
                # TODO: будет удалено после: реализации полноценной смены локации через scene_state_manager
                system_log.append(f"> Переход в {target_file} (портал: {target_portal})...")
            elif not system_log or "Привязка" not in system_log[-1]:
                system_log.append("> Дверь никуда не ведёт (не привязана в редакторе)")


class GameScreen:
    """Экран игры — владеет своим циклом, возвращает управление по ESC"""

    def __init__(self, screen: pygame.Surface, clock: pygame.time.Clock):
        self.screen = screen
        self.show_obs_console = False  # Консоль наблюдений (клавиша Ё)
        self.show_journal = False      # ADR-JOURNAL: Журнал диалогов (клавиша J / О)
        # B1.3-FIX: dialog_journal — из backend world_snapshot, не локальный.
        # Раньше: self.dialog_journal = [] → двойное хранение, рассинхрон на Continue.
        # Теперь: читаем из _ws["dialog_journal"] при каждом sync.
        self._dialog_journal_backend: list = [] # cache из backend
        self.npc_speech_bubbles = {}   # ADR-SPEECH: Речевые облачка над NPC {name: {text, tick}}
        self.player_speech_bubble = None  # ADR-SPEECH: Облачко над головой игрока
        self.npc_manifest_indicators = {}  # ADR-MANIFEST: Наблюдаемые физические проявления
        self.clock = clock
        self.renderer = SceneRenderer(screen)
        self._resistance_visual_intensity = 0.0 # B1.2-FIX: визуальный интенсити для тремора

    def run(self, campaign_folder: str, player_name: str = "") -> None:
        """Запускает игровой экран для выбранной кампании"""
        message_log: list = []  # Cinematic Layer: Только NarrativeBeat
        self._dialog_journal_backend = []       # B1.3-FIX: Сброс кэша журнала при новой сессии
        self.npc_speech_bubbles = {}   # ADR-SPEECH: Сброс облачек при новой сессии
        self.player_speech_bubble = None  # ADR-SPEECH: Сброс облачка игрока
        self.npc_manifest_indicators = {}  # ADR-MANIFEST: Сброс проявлений
        system_log: list[str] = []  # Log Layer: Системные сообщения, движение, ошибки

        # Неблокирующая очередь к backend — LLM не замораживает Pygame
        _gateway, action_queue = create_game_gateway()
        action_queue.start()

        # Активируем сессию игрока на backend — это ALSO инициализирует сцену из editor JSON
        if player_name:
            try:
                _gateway.create_player_session(campaign_folder, player_name)
            except Exception as e:
                system_log.append(f"[!] Backend session: {e}")

        # S85: Загружаем состояние через API (SSOT — SceneStateManager на бэкенде)
        _session_data = _gateway.get_session_state(campaign_folder)
        scene_state = _session_data.get("scene_state", {})
        logger.debug(f"[GAME_SCREEN] scene_state loaded: {bool(scene_state)}, loc={scene_state.get('location_id', 'N/A')}")
        if not scene_state:
            return

        # Игровое время — total_seconds от начала эпохи
        from constants import TIME_DELTA_WALK_INDOOR, parse_hhmm, format_game_time, format_world_date
        _gts = scene_state.get("game_time_seconds")
        if _gts is not None and _gts > 0:
            self.game_time_seconds: int = _gts
        else:
            _env_time_str = scene_state.get("environment", {}).get("time_of_day", "07:00")
            self.game_time_seconds: int = parse_hhmm(_env_time_str)

        location_id = scene_state.get("location_id", "unknown")
        
        # S85: Размеры комнаты берем из SpatialCompilationGateway (а не из JSON)
        scene_w, scene_h = 20.0, 15.0  # Fallback по умолчанию

        # S80.3b: Multi-chunk контекст — стены всех видимых локаций
        _world_ctx = None
        _floor_rects = None
        # S82: Инициализация ДО первого использования (ранее была на строке 499 → UnboundLocalError при доступе в строке 438)
        _last_world_pos: list[float | None] = [None, None]
        try:
            from spatial_compilation_gateway import SpatialCompilationGateway
            from world_context import SpatialDataLoader, ContextResolver
            _registry = SpatialCompilationGateway.get_registry(campaign_folder)
            if _registry is not None:
                _loader = SpatialDataLoader()
                _resolver = ContextResolver(_registry, _loader)
                _px, _py = _player_xy(scene_state)
                _world_px, _world_py = _resolver.local_to_world(_px, _py, location_id)
                # S82: Сохраняем мировые координаты для Spatial Oracle (отправляются в API)
                _last_world_pos[0] = _world_px
                _last_world_pos[1] = _world_py
                _world_ctx = _resolver.resolve(_world_px, _world_py, campaign_id=campaign_folder)
                walls = list(_world_ctx.collidable_walls)
                obstacles = list(_world_ctx.collidable_obstacles)
                _floor_rects = [vc.spatial.floor_rect for vc in _world_ctx.visible_chunks]
                # S85: Извлекаем размеры комнаты из первого видимого чанка
                if _floor_rects:
                    _r = _floor_rects[0]
                    scene_w, scene_h = _r[2], _r[3]
                logger.debug(f"[PIPELINE][INPUT] multi-chunk: {len(_world_ctx.visible_chunks)} chunks, {len(walls)} walls")
                logger.debug(f"[WORLD_CTX] location_id={location_id} walls={len(walls)} obstacles={len(obstacles)} visible_chunks={[vc.descriptor.location_id for vc in _world_ctx.visible_chunks]} scene=({scene_w},{scene_h})")
            else:
                walls = scene_state.get("spatial_walls", [])
                obstacles = scene_state.get("spatial_obstacles", [])
        except Exception as e:
            logger.warning(f"[PIPELINE][INPUT] spatial context fallback: {e}")
            walls = scene_state.get("spatial_walls", [])
            obstacles = scene_state.get("spatial_obstacles", [])

        logger.debug(f"[PIPELINE][INPUT] entering main loop, walls={len(walls)}, obstacles={len(obstacles)}")

        # Состояние восприятия
        memory = PlayerMemory()
        encounters = EncounterHistory()
        focus = PlayerFocus()

        # Состояние перемещения
        move = _MoveState()

        # Текстовый ввод — виджет с кириллицей и историей
        sw, sh = self.screen.get_size()
        _WASD_KEYS = {pygame.K_w, pygame.K_a, pygame.K_s, pygame.K_d}
        text_input = TextInput(
            rect=pygame.Rect(4, sh - 36, sw - 8, 32),
            font=self.renderer.font_small,
            pass_through_keys=_WASD_KEYS,
        )
        self.text_input = text_input # ADR-041 FIX: Привязка к self для Embodiment
        self.text_input.focused = False  # По умолчанию фокус на игре, а не на чате
        _last_player_input: str = "" # Надежная память последнего ввода для фильтра эха

        # Инициализация Сценического Рендерера (Устав §10)
        from narrative_renderer import NarrativeRenderer
        narrative_renderer = NarrativeRenderer(
            font_normal=self.renderer.font_small,
            font_bold=self.renderer.font_small # Используем font_small как жирный
        )

        # WASD → направляющий вектор
        _WASD_MAP = {
            pygame.K_w: (0.0, -1.0),
            pygame.K_s: (0.0, 1.0),
            pygame.K_a: (-1.0, 0.0),
            pygame.K_d: (1.0, 0.0),
        }
        held_keys: set[int] = set()

        # Idle tick: тикаем мир пока игрок не делает действие
        # Фаза 2.1 — интервал зависит от расстояния до NPC (см. _idle_tick_interval_ms)
        _last_idle_tick = 0  # Немедленный первый idle_tick — мир стартует сразу
        _idle_tick_result: list = []   # потокобезопасный буфер результата
        _idle_tick_running = [False]   # флаг активного запроса
        _last_telegraph_ms = 0         # cooldown между телеграфами
        # S82: Мировые координаты для Spatial Oracle. Обновляются каждый кадр.
        # Backend использует как PRIMARY spatial input — вычисляет actual_chunk НЕЗАВИСИМО.
        # _last_world_pos инициализирован выше (перед try-блоком SpatialRegistry)
        _TELEGRAPH_COOLDOWN_MS = 30_000  # 30 сек между телеграфами
        _time_scale = 1                # Множитель скорости симуляции (1, 4, 10, 50)
        # Маппинг npc_id → имя для телеграфа
        _npc_name_map: dict[str, str] = {}
        with contextlib.suppress(Exception):
            import json
            _npc_dir = Path("config/npc/individuals")
            if _npc_dir.exists():
                for _f in _npc_dir.glob("*.json"):
                    _data = json.loads(_f.read_text(encoding="utf-8"))
                    _npc_name_map[_data.get("id", "")] = _data.get("name", "")
        import threading

        def _do_idle_tick():
            try:
                result = _gateway.idle_tick(campaign_folder)
                _idle_tick_result.clear()
                _idle_tick_result.append(result)
            except Exception as e:
                import traceback
                print(f"[IDLE_TICK] ERROR: {e}\n{traceback.format_exc()}")
            _idle_tick_running[0] = False

        def _do_skip_time(ticks: int):
            _idle_tick_running[0] = True
            try:
                result = _gateway.skip_time(campaign_folder, ticks)
                _idle_tick_result.clear()
                _idle_tick_result.append(result)
            except Exception as e:
                import traceback
                print(f"[SKIP_TIME] ERROR: {e}\n{traceback.format_exc()}")
            _idle_tick_running[0] = False

        logger.debug(f"[PIPELINE][INPUT] entering main loop, walls={len(walls)}, obstacles={len(obstacles)}")
        running = True
        _frame = 0
        while running:
            _frame += 1
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    action_queue.stop()
                    return
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        action_queue.stop()
                        running = False
                        return
                    # ADR-JOURNAL: Переключение журнала (J / Русская О), только если консоль НЕ в фокусе
                    elif not text_input.focused and (event.key == pygame.K_j or event.unicode == 'о'):
                        self.show_journal = not self.show_journal
                    elif event.key == pygame.K_TAB:
                        # Переключение фокуса: игра <-> консоль общения
                        text_input.focused = not text_input.focused
                        if text_input.focused:
                            # Открыли консоль — ждём ввода игрока
                            print("[CONSOLE] opened — waiting for player input")
                        else:
                            # Закрыли консоль — убираем пузыри с экрана, чтобы не загораживали игру
                            message_log.clear()
                    # Time Controls: ускорение симуляции (Приоритет 1)
                    elif event.key == pygame.K_1 and not text_input.focused:
                        threading.Thread(target=lambda: _do_skip_time(10), daemon=True).start()
                    elif event.key == pygame.K_2 and not text_input.focused:
                        threading.Thread(target=lambda: _do_skip_time(100), daemon=True).start()
                    elif event.key == pygame.K_3 and not text_input.focused:
                        threading.Thread(target=lambda: _do_skip_time(500), daemon=True).start()
                    elif event.key == pygame.K_4 and not text_input.focused:
                        threading.Thread(target=lambda: _do_skip_time(2000), daemon=True).start()
                    elif not text_input.focused and (event.key == pygame.K_BACKQUOTE or getattr(event, 'unicode', '') in ('ё', 'Ё')):
                        self.show_obs_console = not self.show_obs_console
                    # TextInput обрабатывает всё кроме WASD (pass_through)
                    handled = text_input.handle_event(event)
                    # RETURN обрабатывается отдельно — TextInput намеренно возвращает False
                    if event.key == pygame.K_RETURN and not text_input.empty:
                        # Игрок успел напечатать — отменяем telegraph
                        action_queue.cancel_telegraph()
                        # ADR-039: Сброс Resistance Medium после успешного ввода
                        text_input.exorcise()
                        print("[TELEGRAPH] cancelled — player acted first")

                        # Создаем сценическое событие для пузыря игрока (ТЗ 3 + Мастер тай)
                        from narrative_beat import NarrativeBeat, DeliveryType, RecognitionLevel, BeatLifetime

                        # Сохраняем текст для фильтрации эха от LLM
                        _last_player_input = text_input.text.strip()

                        player_beat = NarrativeBeat(
                            speaker=player_name,
                            text=text_input.text.strip(),
                            is_player=True,
                            delivery=DeliveryType.NORMAL,
                            recognition=RecognitionLevel.KNOWN_NAME,
                            is_active=True,
                            creation_tick=pygame.time.get_ticks()
                        )
                        message_log.append(player_beat)
                        # B1.3-FIX: НЕ добавляем локально. Backend вернёт обновлённый
                        # journal в следующем world_snapshot.
                        pass
                        # ADR-SPEECH: Облачко над головой игрока
                        self.player_speech_bubble = {"text": text_input.text.strip(), "tick": pygame.time.get_ticks()}

                        self._handle_text_input(
                            text_input.text.strip(), scene_state, focus,
                            walls, obstacles, move, message_log,
                            scene_w, scene_h,
                            action_queue, campaign_folder, player_name,
                            last_world_pos=_last_world_pos,
                        )
                        text_input.push_history(text_input.text.strip())
                        text_input.clear() # Очищаем пузырь ввода после отправки
                    elif event.key in _WASD_MAP:
                        # WASD двигает персонажа только если чат не в фокусе
                        if not text_input.focused:
                            held_keys.add(event.key)
                            move.target_npc_id = None
                            move.direction = None
                elif event.type == pygame.KEYUP:
                    # Обязательно передаем отпускание клавиш в TextInput,
                    # иначе инерция (зажатие стрелок/backspace) зависает навсегда
                    text_input.handle_event(event)
                    # Сброс флага зажатия WASD для движения персонажа
                    held_keys.discard(event.key)
                elif event.type == pygame.TEXTINPUT:
                    # WASD при зажатии генерирует TEXTINPUT с буквой — фильтруем
                    _WASD_KEY_TEXT = {pygame.K_w: 'w', pygame.K_a: 'a', pygame.K_s: 's', pygame.K_d: 'd'}
                    _skip = False
                    if held_keys and len(event.text) == 1:
                        for k in held_keys:
                            if _WASD_KEY_TEXT.get(k) == event.text.lower():
                                _skip = True
                                break
                    if not _skip:
                        text_input.handle_event(event)
                elif event.type == pygame.TEXTEDITING:
                    text_input.handle_event(event)
                elif event.type == pygame.MOUSEBUTTONDOWN and False:  # Отключено перемещение кликом мыши
                    clicked_npc = self._handle_click(
                        event.pos, scene_state, focus, walls,
                    )
                    if clicked_npc:
                        move.target_npc_id = clicked_npc
                        move.direction = None
                        text_input.clear()
                        # Спринт 30: Запрет локальной симуляции. Путь ищет бэкенд.
                        # Фронтенд только фиксирует цель, локальный pathfinding удален.
                        system_log.append(f"Идёшь к {clicked_npc}")
                elif event.type == pygame.VIDEORESIZE:
                    self.screen = pygame.display.set_mode(
                        (event.w, event.h), pygame.RESIZABLE
                    )
                    self.renderer = SceneRenderer(self.screen)

            # === Перемещение ===
            dt = self.clock.get_time() / 1000.0
            move.cooldown -= dt
            # Обновление физики инерционного повтора курсора в TextInput
            text_input.update(dt)
            moved = False

            if move.cooldown <= 0:
                # Спринт 31: Elastic Time. Движение — это Intent, подтвержденный бэкендом.
                npc_positions = scene_state.get("npc_positions", {})
                px, py = _player_xy(scene_state)

                # Движение к NPC: отправляем намерение, бэкенд строит маршрут
                if move.target_npc_id and move.target_npc_id in npc_positions:
                    from npc_name_resolver import npc_id_to_display
                    name = npc_id_to_display(move.target_npc_id)
                    action_queue.submit(campaign_folder, player_name, f"подойти к {name}", px, py, _last_world_pos[0], _last_world_pos[1])
                    move.target_npc_id = None  # Бэкенд взял управление

                # WASD: транслируем вектор в семантическую команду (SemanticBridge на бэкенде)
                elif held_keys:
                    dx, dy = 0.0, 0.0
                    for key in held_keys:
                        if key in _WASD_MAP:
                            kx, ky = _WASD_MAP[key]
                            dx += kx
                            dy += ky
                    if dx != 0 or dy != 0:
                        # Нормализация вектора (устранение бага диагонального ускорения)
                        length = math.hypot(dx, dy)
                        if length > 0:
                            dx /= length
                            dy /= length
                        
                        move.facing_angle = math.atan2(dy, dx)
                        move.facing_mode = "VELOCITY"
                        
                        # Физика: скольжение вдоль стен через Push-out Resolution
                        speed = 8.0 * dt
                        
                        # S81-ФИКС: Координатная истина — движение в МИРОВЫХ координатах
                        # walls/obstacles из SpatialDataLoader уже мировые.
                        # Конвертируем локальную позицию в мировую, двигаем, коллизии в мировых,
                        # конвертируем обратно в локальную для хранения.
                        _world_px, _world_py = px, py  # default: local = world
                        if _world_ctx is not None:
                            _world_px, _world_py = _resolver.local_to_world(px, py, location_id)
                        
                        pred_wx = _world_px + dx * speed
                        pred_wy = _world_py + dy * speed
                        
                        # Коллизии в мировых координатах
                        pred_wx, pred_wy = _resolve_player_collisions(pred_wx, pred_wy, walls, obstacles)
                        
                        # S82: Обновляем мировые координаты для Spatial Oracle
                        _last_world_pos[0] = pred_wx
                        _last_world_pos[1] = pred_wy
                        
                        # Конвертируем обратно в локальные для хранения
                        if _world_ctx is not None:
                            pred_lx, pred_ly = _resolver.world_to_local(pred_wx, pred_wy, location_id)
                        else:
                            pred_lx, pred_ly = pred_wx, pred_wy
                        
                        _set_player_xy(scene_state, pred_lx, pred_ly)

                        _DIR_MAP = {
                            (0, -1): "север", (0, 1): "юг", (-1, 0): "запад", (1, 0): "восток",
                            (-1, -1): "северо-запад", (1, -1): "северо-восток",
                            (-1, 1): "юго-запад", (1, 1): "юго-восток",
                        }
                        dir_name = _DIR_MAP.get((int(dx), int(dy)))
                        # WASD — локальная физика игрока. DM не вызывается.
                        # Бэкенд узнаёт о позиции игрока при следующем диалоге/действии.
                        
                        move.target_npc_id = None
                        move.direction = None
                    move.cooldown = _MOVE_INTERVAL
                    # Накопительное время: 10 сек за каждый полный метр (а не за микро-шаг 0.3)
                    move.walk_distance_accumulated += 0.3  # step_size
                    meters_walked = int(move.walk_distance_accumulated)
                    if meters_walked > 0:
                        # B1.1-FIX: frontend НЕ конструирует время.
                        # Absolute time authority = backend (Устав §3).
                        # Раньше: self.game_time_seconds += ... → dual truth.
                        # Теперь: только backend продвигает время (через advance_game_time).
                        # Frontend отображает значение из world_snapshot.
                        pass # время обновится из world_snapshot при следующем sync
                        move.walk_distance_accumulated -= meters_walked

            # === Idle tick: применяем результат прошлого idle_tick если готов ===
            _now = pygame.time.get_ticks()
            _tick_data = {}
            _new_positions = {}
            _ws = None
            if _idle_tick_result:
                _tick_data = _idle_tick_result.pop()
                # Канонический источник: world_snapshot.npc_positions (Устав §3, фаза 9)
                _ws = _tick_data.get("world_snapshot")
                if _ws and "npc_positions" in _ws:
                    _new_positions = _ws["npc_positions"]
                else:
                    # Fallback на deprecated поле для совместимости
                    _new_positions = _tick_data.get("npc_positions", {})
            if _new_positions:
                import copy
                for npc_id, new_data in _new_positions.items():
                    # ADR-0014: Атомарная замена вместо shallow merge.
                    # Shallow merge убивал движение: если бэкенд не присылал local_position,
                    # старые координаты оставались навсегда, и рендерер рисовал призраков.
                    scene_state.setdefault("npc_positions", {})[npc_id] = copy.deepcopy(new_data)
                    # TASK 2: Visual Revision Counter — логируем только если координаты реально изменились
                    _old_lp = scene_state.get("npc_positions", {}).get(npc_id, {}).get("local_position", {})
                    _new_lp = new_data.get("local_position", {})
                    if _old_lp != _new_lp:
                        print(f"[FRAME_RENDER] npc={npc_id} new_xy=({_new_lp.get('x')}, {_new_lp.get('y')})")

            if _new_positions:
                logger.info(f"[IDLE_TICK] merged: {list(_new_positions.keys())}")

            # Синхронизация player_position и environment из world_snapshot
            if _ws:
                # ADR-019: Frontend — авторитет визуальной позиции игрока.
                # Не перезаписываем локальную позицию из world_snapshot при idle_tick,
                # иначе мгновенная телепортация на старые координаты бэкенда убьет плавность.
                # _pp = _ws.get("player_position")
                # if _pp and len(_pp) == 2:
                #     _set_player_xy(scene_state, float(_pp[0]), float(_pp[1]))
                # ЗАКОН: Фронтенд НЕ конструирует время. Absolute time authority = backend.
                _ws_gts = _ws.get("game_time_seconds")
                if _ws_gts is not None and _ws_gts > 0:
                    scene_state["game_time_seconds"] = _ws_gts
                    self.game_time_seconds = _ws_gts
                # ADR-019 FIX: Синхронизация tick для traversal интерполяции.
                # Без этого _resolve_visual_xy всегда видит progress=0 → NPC стоят.
                _ws_tick = _ws.get("tick")
                print(f"[TICK_SYNC] idle_ws.tick={_ws_tick} scene_tick_before={scene_state.get('tick')}")
                if _ws_tick is not None:
                    scene_state["tick"] = _ws_tick

                # ADR-035: Извлечение феноменологической проекции аватара (Визуальное искажение)
                if "avatar_state" in _ws:
                    scene_state["avatar_state"] = _ws["avatar_state"]
                # ТЗ EMBODIED UI PERCEPTION: Извлечение наблюдений игрока
                if "player_perception" in _ws:
                    scene_state["player_perception"] = _ws["player_perception"]
                # B1.3-FIX: синхронизируем journal из backend (строгая обработка, без спама логов)
                if "dialog_journal" in _ws:
                    self._dialog_journal_backend = _ws["dialog_journal"]
                else:
                    logger.debug("[GAME_SCREEN] dialog_journal missing in world_snapshot (idle_ws)")
                # time_of_day — только визуальный срез для рендера, не источник истины
                _ws_tod = _ws.get("time_of_day")
                if _ws_tod:
                    scene_state.setdefault("environment", {})["time_of_day"] = _ws_tod
                _ws_weather = _ws.get("weather")
                if _ws_weather:
                    scene_state.setdefault("environment", {})["weather"] = _ws_weather

            # Pressure-driven: если idle_tick принёс proactive события → запускаем телеграф
            _events = _tick_data.get("events") or [] if _tick_data else []
            # Фильтруем только proactive (не life_engine позиционные)
            _proactive_events = [e for e in _events if e.get("cause") == "idle_pressure"]
            _now_ms = pygame.time.get_ticks()
            if _proactive_events and action_queue.pending_count() == 0 and (_now_ms - _last_telegraph_ms >= _TELEGRAPH_COOLDOWN_MS):
                # Берём самое приоритетное событие
                _ev = _proactive_events[0]
                _npc_name = ""
                _npc_id = _ev.get("target", "")
                # Имя из маппинга конфигов, или из scene_state, или fallback на id
                _npc_name = _npc_name_map.get(_npc_id, "")
                if not _npc_name:
                    _npc_data = scene_state.get("npc_positions", {}).get(_npc_id, {})
                    _npc_name = _npc_data.get("name") or _npc_data.get("display_name") or _npc_id
                _last_telegraph_ms = _now_ms
                _ev_desc = _ev.get("value", "")
                # Человекочитаемый текст для DM (без технических деталей)
                _intent_map = {
                    "observe": "присматривается",
                    "talk": "хочет поговорить",
                    "warn": "хочет предупредить",
                    "report": "хочет что-то сообщить",
                    "trade": "хочет предложить сделку",
                    "help": "хочет помочь",
                    "flee": "пытается уйти",
                }
                _readable = _intent_map.get(_ev_desc, "проявляет инициативу")
                _telegraph_text = f"{_npc_name} {_readable}"
                _px, _py = _player_xy(scene_state)
                action_queue.submit_telegraph(
                    campaign_folder, player_name,
                    _px,
                    _py,
                    world_x=_last_world_pos[0],
                    world_y=_last_world_pos[1],
                    action_text=_telegraph_text,
                )
                print(f"[TELEGRAPH] event-driven: {_telegraph_text}")

            # Фаза 2.1 — distance-based интервал: в чате = частый, при ходьбе = редкий
            _now = pygame.time.get_ticks()
            if not text_input.focused:
                # WASD: чат не в фокусе → NPC двигаются по расстоянию
                _nearest = _nearest_npc_distance(scene_state)
                # Ускорение: делим интервал на time_scale (минимум 500мс чтобы не DDOSить бэкенд)
                _tick_interval = max(500, _idle_tick_interval_ms(_nearest) // _time_scale)
            else:
                # Диалог: NPC стоят и разговаривают, не "летают" по комнате
                _tick_interval = 30_000
            # Запускаем новый idle_tick если пора и предыдущий завершён
            if (_now - _last_idle_tick >= _tick_interval
                    and not _idle_tick_running[0]
                    and action_queue.pending_count() == 0):
                # Фаза 4 — сохраняем позицию на бэкенд перед idle_tick
                with contextlib.suppress(Exception):
                    _bridge = _gateway._bridge
                    if _bridge.ready:
                        _bridge.save_scene_state(campaign_folder, scene_state)
                _idle_tick_running[0] = True
                _last_idle_tick = _now
                logger.info(f"[IDLE_TICK] fired at {_now}ms")
                threading.Thread(target=_do_idle_tick, daemon=True).start()

            # === Poll backend responses ===
            result = action_queue.poll()
            if result is not None:
                if result.error:
                    system_log.append(f"[Ошибка] {result.error}")
                else:
                    # Обновляем время из ответа backend
                    _gts = result.response.game_time_seconds
                    # Защита от tuple (существующий баг сериализации)
                    if isinstance(_gts, tuple):
                        _gts = _gts[0] if _gts else 0
                    if isinstance(_gts, (int, float)) and _gts > 0:
                        self.game_time_seconds = _gts
                    # Пауза idle tick: NPC не двигаются пока игрок читает ответ
                    _last_idle_tick = pygame.time.get_ticks() + 1000
                    from narrative_beat import NarrativeBeat, DeliveryType, RecognitionLevel, BeatLifetime

                    resp = result.response.dm_response
                    # TASK 1: Force Merge — применяем snapshot из player action немедленно (ADR-0014)
                    _action_ws = None
                    if hasattr(result.response, 'world_snapshot') and result.response.world_snapshot:
                        _action_ws = result.response.world_snapshot
                    elif isinstance(result.response, dict) and result.response.get("world_snapshot"):
                        _action_ws = result.response.get("world_snapshot")

                    # Диагностика: что реально пришло в ответе?
                    if isinstance(result.response, dict):
                        print(f"[TRACE][ACTION_RESP] has_ws={bool(_action_ws)} ws_type={type(_action_ws).__name__} top_keys={list(result.response.keys())[:5]}")
                    else:
                        print(f"[TRACE][ACTION_RESP] resp_type={type(result.response).__name__} has_ws={bool(_action_ws)}")

                    # S82: Spatial Oracle reconciliation.
                    # Backend подтверждает actual_chunk. Если отличается — обновляем location_id.
                    # Backend НИКОГДА не перемещает игрока. Только обновляет simulation scope.
                    _confirmed_loc = getattr(result.response, 'confirmed_location_id', None)
                    if _confirmed_loc is None and isinstance(result.response, dict):
                        _confirmed_loc = result.response.get("confirmed_location_id")
                    if _confirmed_loc and _confirmed_loc != location_id:
                        logger.info(
                            f"[SPATIAL_RECONCILE] location_id corrected: "
                            f"{location_id} → {_confirmed_loc}"
                        )
                        location_id = _confirmed_loc
                        scene_state["location_id"] = _confirmed_loc
                        logger.info(f"[WORLD_CTX] RECONCILE location_id={location_id} walls={len(walls)} obstacles={len(obstacles)} scene=({scene_w},{scene_h})")
                        # S82.1: Пересчитываем local_position с новым origin.
                        # Без этого local_position остаётся вычисленным от старого origin,
                        # и на следующем кадре local_to_world даст неверный world_position.
                        if _world_ctx is not None and _last_world_pos[0] is not None and _last_world_pos[1] is not None:
                            new_lx, new_ly = _resolver.world_to_local(
                                _last_world_pos[0], _last_world_pos[1], _confirmed_loc
                            )
                            _set_player_xy(scene_state, new_lx, new_ly)
                            logger.info(
                                f"[SPATIAL_RECONCILE] local_position recalculated: "
                                f"world=({_last_world_pos[0]:.2f},{_last_world_pos[1]:.2f}) "
                                f"→ local=({new_lx:.2f},{new_ly:.2f}) via origin({_confirmed_loc})"
                            )

                    if _action_ws and isinstance(_action_ws, dict) and "npc_positions" in _action_ws:
                        import copy
                        for npc_id, new_data in _action_ws["npc_positions"].items():
                            # ADR-092: Каузальная труба движения. Если NPC в транзите, 
                            # не перезаписываем local_position — рендерер интерполирует его через TraversalState.
                            _old_entry = scene_state.get("npc_positions", {}).get(npc_id, {})
                            _old_lp = _old_entry.get("local_position", {})
                            _travs = _action_ws.get("active_traversals", {})
                            _in_transit = npc_id in _travs and _travs[npc_id].get("status") == "MOVING"
                            # CEI-3a SMART MERGE: Overlay вместо replace — partial DTO не убивает старые поля
                            # Атомарность ADR-0014 сохраняется: новые поля перезаписывают старые
                            # Но отсутствующие поля в new_data НЕ удаляют существующие
                            _merged = copy.deepcopy(_old_entry)
                            for _mk, _mv in new_data.items():
                                if _mv is not None:
                                    _merged[_mk] = copy.deepcopy(_mv) if isinstance(_mv, (dict, list)) else _mv
                            # CEI-3a: При транзите или если local_position невалидна — сохраняем старую
                            if not isinstance(_merged.get("local_position", {}).get("x"), (int, float)):
                                if _old_lp and isinstance(_old_lp, dict) and isinstance(_old_lp.get("x"), (int, float)):
                                    _merged["local_position"] = _old_lp
                            scene_state.setdefault("npc_positions", {})[npc_id] = _merged
                            _new_lp = _merged.get("local_position", {})
                            if _old_lp != _new_lp:
                                print(f"[FRAME_RENDER][ACTION] npc={npc_id} new_xy=({_new_lp.get('x')}, {_new_lp.get('y')})")
                        # ADR-019: Сохраняем активные транзиты для визуальной интерполяции (Lerp)
                        if "active_traversals" in _action_ws:
                            scene_state["active_traversals"] = _action_ws["active_traversals"]
                            # CEI-2 FIX: active_traversals теперь всегда Dict[npc_id, data]
                            _trav_data = _action_ws['active_traversals']
                            if isinstance(_trav_data, dict):
                                _trav_keys = list(_trav_data.keys())
                                print(f"[PIPELINE][MOVEMENT] traversals_received: keys={_trav_keys} count={len(_trav_keys)}")
                                for _tid, _tdata in _trav_data.items():
                                    print(f"[PIPELINE][TRAVERSAL] npc={_tid} status={_tdata.get('status')} from={_tdata.get('from_node')} to={_tdata.get('target_node')} wp_count={len(_tdata.get('path_waypoints', []))}")
                            elif isinstance(_trav_data, list):
                                # Legacy fallback: list → конвертируем в dict
                                _trav_dict = {t.get("npc_id"): t for t in _trav_data if t.get("npc_id")}
                                scene_state["active_traversals"] = _trav_dict
                                print(f"[PIPELINE][MOVEMENT] traversals_received (list→dict): keys={list(_trav_dict.keys())} count={len(_trav_dict)}")
                            else:
                                print(f"[PIPELINE][MOVEMENT] active_traversals unexpected type: {type(_trav_data).__name__}")
                        else:
                            print(f"[PIPELINE][MOVEMENT] NO active_traversals in action_ws! keys={list(_action_ws.keys())[:10]}")
                        # ADR-035: Обновление феноменологической проекции аватара при действии
                        if "avatar_state" in _action_ws:
                            scene_state["avatar_state"] = _action_ws["avatar_state"]
                        # ADR-019 FIX: Синхронизация tick для traversal интерполяции.
                        # Без этого _resolve_visual_xy всегда видит progress=0 → NPC стоят.
                        _ws_tick = _action_ws.get("tick")
                        print(f"[TICK_SYNC] action_ws.tick={_ws_tick} scene_tick_before={scene_state.get('tick')}")
                        if _ws_tick is not None:
                            scene_state["tick"] = _ws_tick
                        # ТЗ EMBODIED UI PERCEPTION: Извлечение наблюдений игрока
                        if "player_perception" in _action_ws:
                            scene_state["player_perception"] = _action_ws["player_perception"]
                        # B1.3-FIX: синхронизируем journal из backend (action response path)
                        if "dialog_journal" in _action_ws:
                            self._dialog_journal_backend = _action_ws["dialog_journal"]
                        else:
                            logger.debug("[GAME_SCREEN] dialog_journal missing in action response")
                    elif isinstance(result.response, dict) and "npc_positions" in result.response:
                        # Fallback: deprecated top-level npc_positions
                        import copy
                        for npc_id, new_data in result.response["npc_positions"].items():
                            scene_state.setdefault("npc_positions", {})[npc_id] = copy.deepcopy(new_data)
                        # ADR-019: Сохраняем активные транзиты (fallback)
                        if "active_traversals" in result.response:
                            scene_state["active_traversals"] = result.response["active_traversals"]
                        # B1.3-FIX: синхронизируем journal из backend (fallback path)
                        if "dialog_journal" in result.response:
                            self._dialog_journal_backend = result.response["dialog_journal"]
                        else:
                            logger.debug("[GAME_SCREEN] dialog_journal missing in action response (fallback)")
                        # ADR-035: Обновление феноменологической проекции аватара (fallback)
                        if "avatar_state" in result.response:
                            scene_state["avatar_state"] = result.response["avatar_state"]
                        # ADR-019 FIX: Синхронизация tick для traversal интерполяции (fallback)
                        _resp_tick = result.response.get("tick")
                        if _resp_tick is not None:
                            scene_state["tick"] = _resp_tick
                        # ТЗ EMBODIED UI PERCEPTION: Извлечение наблюдений игрока (fallback)
                        if "player_perception" in result.response:
                            scene_state["player_perception"] = result.response["player_perception"]

                    if resp and resp != "Ничего не произошло.":
                        import re
                        from difflib import SequenceMatcher

                        # Отладка DM ответа
                        print(f"[ECHO_DEBUG_DM] DMResp: '{resp.strip()[:80]}...'")

                        # Разбиваем ответ на строки и фильтруем каждую от эха
                        raw_lines = resp.strip().split('\n')

                        # Извлекаем имена NPC из scene_state для парсинга спикера
                        known_names = {}
                        for npc_id, npc_data in scene_state.get("npc_positions", {}).items():
                            name = npc_data.get("name") or npc_data.get("display_name")
                            if name:
                                known_names[name.lower()] = name

                        for line in raw_lines:
                            line_stripped = line.strip()
                            if not line_stripped:
                                continue

                            is_echo_line = False
                            if _last_player_input:
                                p_clean = re.sub(r'[^\w\s]', '', _last_player_input).lower()
                                l_clean = re.sub(r'[^\w\s]', '', line_stripped).lower()

                                # Убираем имя игрока в начале строки для корректного comparison
                                if l_clean.startswith(player_name.lower()):
                                    prefix_len = len(player_name)
                                    if prefix_len < len(line_stripped) and line_stripped[prefix_len] in (':', ',', ' '):
                                        l_clean = re.sub(r'[^\w\s]', '', line_stripped[prefix_len+1:].strip(' ,.-!:;')).lower()

                                similarity = SequenceMatcher(None, p_clean, l_clean).ratio()

                                # Если строка похожа на ввод — это эхо
                                # Защита от ложных срабатываний: не используем in-проверку для коротких фраз (имена NPC)
                                is_short_input = len(p_clean) < 10
                                if similarity > 0.60:
                                    is_echo_line = True
                                elif not is_short_input and (p_clean in l_clean or l_clean in p_clean):
                                    is_echo_line = True

                            if not is_echo_line:
                                # Извлечение спикера (Приоритет 0: починка "Системы")
                                speaker = "Система"
                                text = line_stripped
                                recognition = RecognitionLevel.KNOWN_NAME
                                delivery = DeliveryType.NORMAL

                                for name_lower, name_orig in known_names.items():
                                    if line_stripped.lower().startswith(name_lower):
                                        rest = line_stripped[len(name_orig):]
                                        if rest and rest[0] in (':', ',', '-'):
                                            speaker = name_orig
                                            text = rest.lstrip(':, - ').strip()
                                            break

                                # Определение RecognitionLevel для неизвестных
                                if speaker in ("Мужчина", "Женщина", "???"):
                                    recognition = RecognitionLevel.UNKNOWN_FEMALE if speaker == "Женщина" else RecognitionLevel.UNKNOWN_MALE

                                # Определение DeliveryType по маркерам текста (Приоритет 1: Experiential Architecture)
                                text_lower = text.lower()
                                if text_lower.startswith("(") and text_lower.endswith(")"):
                                    delivery = DeliveryType.WHISPER
                                elif text_lower.startswith("*") and text_lower.endswith("*"):
                                    delivery = DeliveryType.INTERNAL
                                elif text.endswith("!!!") or text.isupper():
                                    delivery = DeliveryType.SHOUT

                                message_log.append(NarrativeBeat(
                                    speaker=speaker,
                                    text=text,
                                    is_player=False,
                                    delivery=delivery,
                                    recognition=recognition,
                                    is_active=False,
                                    creation_tick=pygame.time.get_ticks()
                                ))
                                # B1.3-FIX: НЕ добавляем локально. Backend вернёт обновлённый
                                # journal в следующем world_snapshot.
                                pass

                    # ADR-041: Resistance Medium — инфекция поля ввода при конфликте воли
                    _wc_data = getattr(result.response, 'will_conflict_data', None)
                    # ADR-039/075: Resistance Medium — замыкание трубы воли в UI
                    logger.debug(f"[PIPELINE][EMBODIMENT] Will Conflict Data: {_wc_data}")
                    if _wc_data:
                        _impulse = _wc_data.get("counter_offer_text") or str(_wc_data.get("embodied_vector", ""))
                        if _impulse and hasattr(self, 'text_input') and self.text_input:
                            logger.debug(f"[PIPELINE][EMBODIMENT] Infecting input with: '{_impulse}'")
                            self.text_input.infect(impulse_text=str(_impulse), origin_layer="will_conflict")
                        
                        # ADR-084: Embodiment Vision Suturing. Конфликт воли искажает визуал (тремор, виньетка).
                        _res = _wc_data.get("resistance", 0)
                        # B1.2-FIX: frontend НЕ перезаписывает avatar_state полностью.
                        # Backend avatar_presentation_assembler уже посчитал базовые скаляры.
                        # Но конфликт воли (_res) — это локальный фронтенд-эвент, который бэкенд
                        # может не успеть отразить в motor_disruption. Поэтому мы МЕРДЖИМ
                        # _res в motor_disruption, не перетирая другие поля.
                        if _res > 0:
                            self._resistance_visual_intensity = _res
                            _av = scene_state.get("avatar_state")
                            if not isinstance(_av, dict):
                                _av = {}
                                scene_state["avatar_state"] = _av
                            _base_motor = float(_av.get("motor_disruption", 0.0))
                            _av["motor_disruption"] = max(_base_motor, _res * 5.0)
                            _base_noise = float(_av.get("sensory_noise", 0.0))
                            _av["sensory_noise"] = max(_base_noise, _res * 3.0)
                            logger.debug(f"[PIPELINE][EMBODIMENT] merged will_conflict: res={_res:.2f}, motor={_av['motor_disruption']:.2f}")
                        else:
                            self._resistance_visual_intensity = 0.0

                    # npc_reactions → речевые облачка над головой NPC (не в чат!)
                    for npc_r in (result.response.npc_reactions or []):
                        if isinstance(npc_r, dict):
                            npc_name = npc_r.get("npc_name", "NPC")
                            npc_text = npc_r.get("reaction", "")
                        elif isinstance(npc_r, str) and ":" in npc_r:
                            _parts = npc_r.split(":", 1)
                            npc_name = _parts[0].strip()
                            npc_text = _parts[1].strip()
                        else:
                            npc_name = "NPC"
                            npc_text = str(npc_r) if npc_r else ""

                        print(f"[ECHO_DEBUG_NPC] Name: '{npc_name}' | Text: '{npc_text}' | LastInput: '{_last_player_input}'")

                        if npc_text:
                            # Речь NPC → облачко над головой (не дублируем в message_log и журнал)
                            self.npc_speech_bubbles[npc_name] = {"text": npc_text, "tick": pygame.time.get_ticks()}

                # Telegraph завершился — запускаем следующий если консоль открыта
                # Telegraph завершился — НЕ перезапускаем автоматически
                # Следующий Telegraph запустится при следующем Tab
                if action_queue.is_telegraph_result(result):
                    print("[TELEGRAPH] completed")

            # === Pipeline ===
            config = PerceptionConfig(
                player_focus=focus,
                player_stress=10.0,
                player_hp=100,
                player_max_hp=100,
                encounter_history=encounters,
                player_memory=memory,
            )
            perceived = _build_perceived_scene(scene_state, config)

            # === ADR-037: Феноменологический рендеринг ===
            # Рендерер сам применяет Файрвол и Импульс (sanitize + momentum).
            # GameScreen только инжектит скаляры Воли в сырой dict.
            avatar_state = scene_state.get("avatar_state")

            # === Рендер ===
            px, py = _player_xy(scene_state)
            # ADR-SPEECH: Истечение речевых облачек
            _now_sp = pygame.time.get_ticks()
            self.npc_speech_bubbles = {k: v for k, v in self.npc_speech_bubbles.items() if _now_sp - v["tick"] < 6000}
            if self.player_speech_bubble and _now_sp - self.player_speech_bubble["tick"] > 4000:
                self.player_speech_bubble = None

            # ADR-MANIFEST: Читаем наблюдаемые проявления из perception data (бэкенд — источник истины)
            _manifest_indicators = {}
            _perc = scene_state.get("player_perception") or {}
            # API отдаёт manifestations как list[ManifestationDTO], конвертируем в dict
            _raw_manifests = _perc.get("manifestations", [])
            if isinstance(_raw_manifests, list):
                for _m in _raw_manifests:
                    _nid = _m.get("npc_id", "") if isinstance(_m, dict) else getattr(_m, "npc_id", "")
                    _tags = _m.get("tags", []) if isinstance(_m, dict) else getattr(_m, "tags", [])
                    if _nid and _nid != "player" and _tags:
                        _texts = [t(f"manifest:{_tag.replace('MANIFEST_', '').lower()}") for _tag in _tags]
                        _first_key = f"manifest:{_tags[0].replace('MANIFEST_', '').lower()}" if _tags else None
                        _color = manifest_color(_first_key) if _first_key else (160, 160, 160)
                        _manifest_indicators[_nid] = {"tags": _tags, "text": ", ".join(_texts), "color": _color}

            self.npc_manifest_indicators = _manifest_indicators
            self.screen.fill((200, 0, 0))  # ЯРКО-КРАСНЫЙ — если видно, цикл работает
            # S81-ФИКС: Камера следует за ИГРОКОМ, а не за статичным _world_ctx
            # Конвертируем ТЕКУЩУЮ локальную позицию в мировую для камеры
            _render_px, _render_py = px, py
            if _world_ctx is not None:
                _render_px, _render_py = _resolver.local_to_world(px, py, location_id)

            self.renderer.render(
                scene=perceived,
                scene_w=scene_w,
                scene_h=scene_h,
                walls=walls,
                obstacles=obstacles,
                player_xy=(_render_px, _render_py),
                player_facing=move.facing_angle,
                dt=dt,
                avatar_state=avatar_state,
                ambient_state=scene_state.get("ambient_phenomenology"),
                speech_bubbles=self.npc_speech_bubbles,
                player_speech=self.player_speech_bubble,
                mood_indicators=self.npc_manifest_indicators,
                floor_rects=_floor_rects,
            )

            # HUD
            # Пузырь ввода игрока (ТЗ 3) — правый нижний угол
            input_bubble_x = self.screen.get_width() // 2 + 20
            input_bubble_max_w = self.screen.get_width() // 2 - 40
            if text_input.focused or not text_input.empty:
                narrative_renderer.draw_input_bubble(
                    self.screen, player_name, text_input.text, text_input._cursor_pos,
                    x=input_bubble_x, y=self.screen.get_height() - 150, max_width=input_bubble_max_w
                )
            # Bubble Lifetime: обновление возраста и растворение TRANSIENT (Пункт 4)
            _now = pygame.time.get_ticks()
            for beat in message_log:
                if isinstance(beat, NarrativeBeat) and beat.lifetime == BeatLifetime.TRANSIENT:
                    age_ms = _now - beat.creation_tick
                    if age_ms > 10000:  # Живет 10 секунд, затем начинает таять
                        beat.is_fading = True
                        fade_progress = (age_ms - 10000) / 3000.0  # 3 секунды на фейд-аут
                        beat.alpha = max(0.0, 255.0 * (1.0 - fade_progress))
                        if beat.alpha <= 0:
                            beat.is_active = False
                    else:
                        beat.alpha = 255.0
                        beat.is_fading = False

            # Удаление полностью растворившихся пузырей из памяти
            message_log[:] = [b for b in message_log if b.alpha > 0]

            self._draw_message_log(message_log, system_log, narrative_renderer, player_name, _time_scale)

            # ТЗ EMBODIED UI PERCEPTION: Слои 2-3 (Атмосфера и Центральное внимание)
            # Рендерим активные восприятия по центру экрана с затуханием (intensity -> alpha)
            _perception_data = scene_state.get("player_perception")
            if _perception_data and _perception_data.get("active_perceptions"):
                _center_x = self.screen.get_width() // 2
                _start_y = int(self.screen.get_height() * 0.35) # Немного выше центра
                
                for p in _perception_data["active_perceptions"]:
                    _text = p.get("text", "")
                    _intensity = p.get("intensity", 0.0)
                    if not _text or _intensity <= 0.0:
                        continue
                    
                    # Размер шрифта зависит от значимости (крупнее = важнее)
                    _font_size = 36 if _intensity > 0.7 else 28
                    _font = pygame.font.Font(None, _font_size)
                    _alpha = int(max(0, min(255, _intensity * 255)))
                    
                    _text_surf = _font.render(_text, True, (220, 220, 220))
                    _text_surf.set_alpha(_alpha)
                    
                    _text_rect = _text_surf.get_rect(center=(_center_x, _start_y))
                    self.screen.blit(_text_surf, _text_rect)
                    _start_y += _text_rect.height + 5 # Сдвиг вниз для следующего восприятия

            # Консоль наблюдений (клавиша Ё): что аватар видит/слышит/чувствует
            if self.show_obs_console:
                _obs_lines = []
                _obs_npc_pos = scene_state.get("npc_positions", {})
                _obs_perception = (scene_state.get("player_perception") or {})
                _obs_cues = _obs_perception.get("peripheral_cues", [])
                _obs_traces = _obs_perception.get("embodied_traces", [])
                # Строим маппинг npc_id → наблюдаемые симптомы (через i18n)
                _obs_symptoms = {}
                for _c in _obs_cues:
                    _nid = _c.get("npc_id", "???")
                    _ck = _c.get("cue_key", "")
                    _sym_ru = t(f"sym:{_ck.lower()}", _ck)
                    _obs_symptoms.setdefault(_nid, []).append(_sym_ru)
                for _tr in _obs_traces:
                    _nid = _tr.get("npc_id", "")
                    if _nid and _nid != "player":
                        if _tr.get("is_frozen"): _obs_symptoms.setdefault(_nid, []).append(t("sym:frozen"))
                        if _tr.get("is_shaking"): _obs_symptoms.setdefault(_nid, []).append(t("sym:shaking"))
                        if _tr.get("locomotion_instability", 0) > 0.3: _obs_symptoms.setdefault(_nid, []).append(t("sym:uneven_stance"))
                        if _tr.get("posture_rigidity", 0) > 0.4: _obs_symptoms.setdefault(_nid, []).append(t("sym:tense_posture"))
                        if _tr.get("action_interruption", 0) > 0.6: _obs_symptoms.setdefault(_nid, []).append(t("sym:abrupt_stop"))
                        if _tr.get("micro_pause_density", 0) > 0.5: _obs_symptoms.setdefault(_nid, []).append(t("sym:frequent_pauses"))
                # Собираем строки для каждого видимого NPC
                for _nid, _ndata in _obs_npc_pos.items():
                    if _nid == "player": continue
                    _nloc = _ndata.get("location_id") or _ndata.get("location", "")
                    _cur_loc = scene_state.get("location_id", "")
                    if _nloc and _cur_loc and _nloc != _cur_loc: continue
                    _nname = _ndata.get("name") or _ndata.get("display_name") or _nid
                    _nact = _ndata.get("activity", "")
                    _sym_str = ", ".join(_obs_symptoms.get(_nid, []))
                    # Наблюдаемые физические проявления из бэкенда
                    _manif_info = self.npc_manifest_indicators.get(_nid)
                    _manif_text = ""
                    if _manif_info and _manif_info.get("text"):
                        _manif_text = f" [{_manif_info.get('text', '')}]"
                    if _sym_str:
                        _obs_lines.append(f"{_nname}: {_sym_str}{_manif_text}")
                    elif _nact:
                        _obs_lines.append(f"{_nname}: {activity_ru(_nact)}{_manif_text}")
                    else:
                        _obs_lines.append(f"{_nname}{_manif_text}")
                # Рендерим панель
                if _obs_lines:
                    _box_h = len(_obs_lines) * 20 + 30
                    _box_w = 400
                    _obs_bg = pygame.Surface((_box_w, _box_h), pygame.SRCALPHA)
                    _obs_bg.fill((0, 0, 0, 200))
                    self.screen.blit(_obs_bg, (10, 10))
                    _title_s = self.renderer.font_small.render(t("ui:obs_title"), True, (160, 170, 220))
                    self.screen.blit(_title_s, (15, 15))
                    _obs_y = 35
                    for _oline in _obs_lines:
                        _obs_s = self.renderer.font_small.render(f"  {_oline}", True, (200, 200, 200))
                        self.screen.blit(_obs_s, (15, _obs_y))
                        _obs_y += 20

            # HUD: FPS + игровое время
            fps_surf = self.renderer.font_small.render(
                f"FPS: {int(self.clock.get_fps())}", True, (80, 80, 80)
            )
            self.screen.blit(fps_surf, (self.screen.get_width() - 70, 4))

            # Выводим полную дату мира (Год, День, Час:Минута)
            time_surf = self.renderer.font_small.render(
                format_world_date(self.game_time_seconds), True, (140, 140, 140)
            )
            self.screen.blit(time_surf, (self.screen.get_width() - 380, 4))

            # === ADR-127: DEATH OVERLAY (P2) — фронтенд видит смерть ===
            _av = scene_state.get("avatar_state")
            if _av and _av.get("life_status") == "DEAD":
                _death_surf = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA)
                _death_surf.fill((0, 0, 0, 180))
                self.screen.blit(_death_surf, (0, 0))
                _dfont = pygame.font.Font(None, 64)
                _dtxt = _dfont.render("ВЫ МЕРТВЫ", True, (180, 0, 0))
                _drect = _dtxt.get_rect(center=(self.screen.get_width() // 2, self.screen.get_height() // 2))
                self.screen.blit(_dtxt, _drect)
                _subfont = pygame.font.Font(None, 28)
                _subtxt = _subfont.render("Смерть необратима. Мир продолжает жить без вас.", True, (140, 140, 140))
                _subrect = _subtxt.get_rect(center=(self.screen.get_width() // 2, self.screen.get_height() // 2 + 50))
                self.screen.blit(_subtxt, _subrect)

            # === ADR-JOURNAL: VN-стиль журнал (клавиша J) ===
            if self.show_journal and isinstance(scene_state, dict):
                _panel_width = self.screen.get_width() // 3
                _journal_surf = pygame.Surface((_panel_width, self.screen.get_height()), pygame.SRCALPHA)
                _journal_surf.fill((20, 20, 30, 220))
                
                _font_title = pygame.font.Font(None, 32)
                _title_surf = _font_title.render("--- Журнал Диалогов (J) ---", True, (218, 165, 32))
                _journal_surf.blit(_title_surf, (15, 15))
                
                # B1.3-FIX: читаем из backend cache
                _journal_data = self._dialog_journal_backend
                _y_offset = 45
                
                if not _journal_data:
                    _font_text = pygame.font.Font(None, 22)
                    _empty_surf = _font_text.render("(Журнал пуст. Сначала поговорите с NPC)", True, (140, 140, 140))
                    _journal_surf.blit(_empty_surf, (15, _y_offset))
                else:
                    _font_name = pygame.font.Font(None, 26)
                    _font_text = pygame.font.Font(None, 22)
                    
                    # Отрисовка снизу вверх (новые реплики внизу)
                    for _entry in reversed(_journal_data):
                        _speaker = _entry.get("speaker", "???")
                        _text = _entry.get("text", "")
                        
                        # Цветовая кодировка
                        if _speaker == "Рассказчик": _color = (218, 165, 32)   # Золотой
                        elif _speaker == "NPC": _color = (100, 149, 237)       # Голубой
                        else: _color = (200, 200, 200)                         # Нейтральный
                        
                        _name_surf = _font_name.render(f"{_speaker}:", True, _color)
                        _journal_surf.blit(_name_surf, (15, _y_offset))
                        _y_offset += 24
                        
                        # Перенос текста по ширине панели
                        _words = _text.split(' ')
                        _lines = []
                        _current_line = ""
                        for _word in _words:
                            _test_line = _current_line + _word + " "
                            if _font_text.size(_test_line)[0] < _panel_width - 30:
                                _current_line = _test_line
                            else:
                                _lines.append(_current_line)
                                _current_line = _word + " "
                        _lines.append(_current_line)
                        
                        for _line in _lines:
                            _text_surf = _font_text.render(_line, True, (220, 220, 220))
                            _journal_surf.blit(_text_surf, (15, _y_offset))
                            _y_offset += 20
                        
                        _y_offset += 10
                        if _y_offset > self.screen.get_height() - 40:
                            break
                            
                self.screen.blit(_journal_surf, (self.screen.get_width() - _panel_width, 0))

            pygame.display.flip()
            self.clock.tick(60)

    # ── UI методы ──────────────────────────────────────────────────────

    def _draw_input_bar(self, text_input: TextInput) -> None:
        """Рисует строку ввода через TextInput виджет"""
        # Обновляем rect на случай ресайза
        sw = self.screen.get_width()
        sh = self.screen.get_height()
        text_input.rect = pygame.Rect(4, sh - 36, sw - 8, 32)
        text_input.draw(self.screen)

    def _draw_message_log(self, log: list, system_log: list, renderer: 'NarrativeRenderer', player_name: str, time_scale: int = 1) -> None:
        """Cinematic Layer: Рисует сценические пузыри вместо плоского чата"""
        from narrative_beat import NarrativeBeat, RecognitionLevel, DeliveryType
        
        sh = self.screen.get_height()
        sw = self.screen.get_width()
        
        visible = log[-5:] # Берем последние 5 событий
        
        # Конвертация строк больше не нужна — message_log содержит только NarrativeBeat
        beats = []
        for msg in visible:
            msg.is_active = (msg == visible[-1])
            beats.append(msg)
            
        # === Time Scale Indicator (Приоритет 1) ===
        scale_texts = {1: "▶ 1x", 4: "▶▶ 4x", 10: "▶▶▶ 10x", 50: "⏩ 50x"}
        scale_str = scale_texts.get(time_scale, f"▶ {time_scale}x")
        sys_font = renderer.font_normal
        scale_surf = sys_font.render(scale_str, True, (255, 220, 100)) # Желтый цвет для внимания
        scale_bg = pygame.Surface((scale_surf.get_width() + 8, scale_surf.get_height() + 4), pygame.SRCALPHA)
        scale_bg.fill((0, 0, 0, 150))
        scale_x = sw - scale_surf.get_width() - 18
        scale_bg.blit(scale_surf, (4, 2))
        self.screen.blit(scale_bg, (scale_x, 10))

        # === Log Layer: Системные сообщения (сдвиг вниз под Time Scale) ===
        if system_log:
            visible_sys = system_log[-5:] # Последние 5 системных сообщений
            sys_y = 10 + scale_surf.get_height() + 6 # Отступаем ниже индикатора скорости
            for sys_msg in reversed(visible_sys):
                sys_surf = sys_font.render(sys_msg, True, (180, 180, 180))
                # Полупрозрачный фон
                sys_bg = pygame.Surface((sys_surf.get_width() + 8, sys_surf.get_height() + 4), pygame.SRCALPHA)
                sys_bg.fill((0, 0, 0, 120))
                sys_x = sw - sys_surf.get_width() - 18
                sys_bg.blit(sys_surf, (4, 2))
                self.screen.blit(sys_bg, (sys_x, sys_y))
                sys_y += sys_surf.get_height() + 6

        # Правильный расчет позиций Y (снизу вверх, без наложений)
        # 1. Сначала вычисляем высоту каждого пузыря
        heights = []
        max_w = sw // 2 - 40
        for beat in beats:
            # Приблизительный расчет высоты (совпадает с логикой NarrativeRenderer)
            font = renderer.font_normal
            lines = renderer._wrap_text(beat.text, font, max_w - 24)
            line_h = font.get_linesize()
            text_h = len(lines) * line_h
            bubble_h = text_h + 24
            name_h = renderer.font_bold.get_linesize() + 6
            total_h = name_h + bubble_h
            heights.append(total_h)

        # 2. Рисуем снизу вверх
        # Отступ снизу для пузыря ввода игрока
        y_cursor = sh - 170 
        
        for i in range(len(beats) - 1, -1, -1):
            beat = beats[i]
            h = heights[i]
            
            # Рисуем пузырь
            bx = sw // 2 + 20 if beat.is_player else 20
                
            # Сдвигаем курсор вверх на высоту текущего пузыря и рисуем
            y_cursor -= h
            renderer.draw_beat(self.screen, beat, bx, y_cursor, max_w)
            
            # Отступ между пузырями
            y_cursor -= 8

    # ── Обработчики ввода ─────────────────────────────────────────────

    def _handle_text_input(
        self,
        text: str,
        scene_state: dict,
        focus: PlayerFocus,
        walls: list,
        obstacles: list,
        move: _MoveState,
        message_log: list,
        scene_w: float = 20.0,
        scene_h: float = 15.0,
        action_queue: ActionQueue | None = None,
        campaign_folder: str = "",
        player_name: str = "",
        last_world_pos: list | None = None,
    ) -> None:
        """Спринт 31: Все текстовые команды — напрямую в бэкенд через Intent"""
        px, py = _player_xy(scene_state)
        _wx = last_world_pos[0] if last_world_pos else None
        _wy = last_world_pos[1] if last_world_pos else None
        action_queue.submit(campaign_folder, player_name, text, px, py, _wx, _wy)

    def _handle_click(
        self,
        pos: tuple[int, int],
        scene_state: dict,
        focus: PlayerFocus,
        walls: list,
    ) -> Optional[str]:
        """Обрабатывает клик. Возвращает npc_id если клик по NPC"""
        px, py = _player_xy(scene_state)
        cam_x = px * 40 - self.screen.get_width() // 2
        cam_y = py * 40 - self.screen.get_height() // 2

        world_x = (pos[0] + cam_x) / 40
        world_y = (pos[1] + cam_y) / 40

        best_npc = None
        best_dist = 1.5

        for npc_id, npc_data in scene_state.get("npc_positions", {}).items():
            lp = npc_data.get("local_position") or {}
            nx, ny = lp.get("x", 0), lp.get("y", 0)
            dist = ((world_x - nx) ** 2 + (world_y - ny) ** 2) ** 0.5
            if dist < best_dist:
                best_dist = dist
                best_npc = npc_id

        if best_npc and focus.focus_entity_id == best_npc:
            focus.focus_entity_id = None
            return None
        elif best_npc:
            focus.focus_entity_id = best_npc
            return best_npc
        return None