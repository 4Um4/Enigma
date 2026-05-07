"""
path: /frontend/game_screen.py

Экран игры — связывает player_cognition pipeline с scene_renderer.
Загружает состояние кампании, прогоняет pipeline каждый кадр, рендерит результат.

Назначение: Экран игры — загружает кампанию, прогоняет pipeline, рендерит карту, возвращает управление в меню по ESC
Зависимости: pygame, scene_renderer, player_cognition.pipeline, movement_system, intent_parser, json, pathlib
Основные сущности: GameScreen, _MoveState
"""
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pygame

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
from movement_system import try_move, move_towards
from intent_parser import parse_movement_intent
from pathfinding import find_path


def _build_perceived_scene(scene_state: dict, config: PerceptionConfig) -> PerceivedScene:
    """Локальная сборка PerceivedScene из scene_state (Закон 1.1: Фронтенд не лезет в бэкенд)."""
    entities: List[PerceivedEntity] = []
    
    # Конвертируем NPC из scene_state
    for npc_id, npc_data in scene_state.get("npc_positions", {}).items():
        pos = npc_data.get("local_position") or npc_data.get("position")
        x, y = 0.0, 0.0
        if isinstance(pos, dict):
            x, y = float(pos.get("x", 0)), float(pos.get("y", 0))
            
        entities.append(PerceivedEntity(
            entity_id=npc_id,
            entity_type="npc",
            x=x,
            y=y,
            visible=True,
            los=True,
            display_name=npc_data.get("display_name") or npc_data.get("name") or npc_id.split("_")[-1].capitalize(),
            in_attention=(config.player_focus.focus_entity_id == npc_id)
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
    """Мутабельное состояние перемещения — передаётся по ссылке"""
    target_npc_id: Optional[str] = None
    direction: Optional[str] = None
    cooldown: float = 0.0
    path: Optional[list] = None
    walk_distance_accumulated: float = 0.0  # накопленное расстояние (метры) для расчёта времени
    path_index: int = 0


def _load_campaign_state(campaign_folder: str) -> Optional[dict]:
    """Загружает campaign_state.json: приоритет saves/, fallback campaigns/"""
    state_file = _SAVES_DIR / campaign_folder / "campaign_state.json"
    if not state_file.exists():
        state_file = _CAMPAIGNS_DIR / campaign_folder / "campaign_state.json"
    if not state_file.exists():
        return None
    with open(state_file, "r", encoding="utf-8") as f:
        data = json.loads(f.read().encode().decode("utf-8-sig"))
    scene = data.get("scene_state")
    if scene is None:
        return None
    if "npc_positions" in data and "npc_positions" not in scene:
        scene["npc_positions"] = data["npc_positions"]
    return scene


def _load_location_meta(campaign_folder: str, location_id: str) -> dict:
    """Загружает метаданные локации (размер комнаты)"""
    locations_dir = _CAMPAIGNS_DIR / campaign_folder / "locations"
    if not locations_dir.exists():
        return {"size": {"w": 20, "h": 15}}
    for json_file in locations_dir.glob("*.json"):
        try:
            with open(json_file, "r", encoding="utf-8") as f:
                loc_data = json.load(f)
            if loc_data.get("filename", "").replace(".json", "") in location_id:
                return loc_data
            for room in loc_data.get("rooms", []):
                if room.get("id") == location_id:
                    return loc_data
        except Exception:
            continue
    return {"size": {"w": 20, "h": 15}}


def _player_xy(scene_state: dict) -> tuple[float, float]:
    """Извлекает координаты игрока"""
    ps = scene_state.get("player_spatial", {})
    lp = ps.get("local_position") or {}
    return float(lp.get("x", 5.0)), float(lp.get("y", 5.0))


def _set_player_xy(scene_state: dict, x: float, y: float) -> None:
    """Обновляет координаты игрока в scene_state"""
    scene_state["player_spatial"]["local_position"]["x"] = x
    scene_state["player_spatial"]["local_position"]["y"] = y


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


def _check_transition_trigger(scene_state: dict, px: float, py: float, message_log: list) -> None:
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
                message_log.append(f"> Переход в {target_file} (портал: {target_portal})...")
            else:
                # Защита от спама в лог при каждом тике движения на клетке
                if not message_log or "Привязка" not in message_log[-1]:
                    message_log.append("> Дверь никуда не ведёт (не привязана в редакторе)")


class GameScreen:
    """Экран игры — владеет своим циклом, возвращает управление по ESC"""

    def __init__(self, screen: pygame.Surface, clock: pygame.time.Clock):
        self.screen = screen
        self.clock = clock
        self.renderer = SceneRenderer(screen)

    def run(self, campaign_folder: str, player_name: str = "") -> None:
        """Запускает игровой экран для выбранной кампании"""
        message_log: list[str] = []

        # Неблокирующая очередь к backend — LLM не замораживает Pygame
        _gateway, action_queue = create_game_gateway()
        action_queue.start()

        # Активируем сессию игрока на backend — это ALSO инициализирует сцену из editor JSON
        if player_name:
            try:
                _gateway.create_player_session(campaign_folder, player_name)
            except Exception as e:
                message_log.append(f"[!] Backend session: {e}")

        # Загружаем состояние ПОСЛЕ сессии — теперь scene_state уже скомпилирован
        scene_state = _load_campaign_state(campaign_folder)
        print(f"[GAME_SCREEN] scene_state loaded: {scene_state is not None}, loc={scene_state.get('location_id') if scene_state else 'N/A'}")
        if scene_state is None:
            return

        # Игровое время — total_seconds от начала эпохи
        # При старте парсим из scene_state, дальше обновляем из ответов backend и движения
        from constants import TIME_DELTA_WALK_INDOOR, parse_hhmm, format_game_time
        _env_time_str = scene_state.get("environment", {}).get("time_of_day", "07:00")
        self.game_time_seconds: int = parse_hhmm(_env_time_str)


        location_id = scene_state.get("location_id", "unknown")
        loc_meta = _load_location_meta(campaign_folder, location_id)
        scene_w = loc_meta.get("size", {}).get("w", 20)
        scene_h = loc_meta.get("size", {}).get("h", 15)
        walls = scene_state.get("spatial_walls", [])
        obstacles = scene_state.get("spatial_obstacles", [])

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
        text_input.focused = False  # По умолчанию фокус на игре, а не на чате
        message_log: list[str] = [] # Временный адаптер, пока бэкенд не шьет NarrativeBeat
        
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
        _last_idle_tick = pygame.time.get_ticks()
        _idle_tick_result: list = []   # потокобезопасный буфер результата
        _idle_tick_running = [False]   # флаг активного запроса
        _last_telegraph_ms = 0         # cooldown между телеграфами
        _TELEGRAPH_COOLDOWN_MS = 30_000  # 30 сек между телеграфами
        # Маппинг npc_id → имя для телеграфа
        _npc_name_map: dict[str, str] = {}
        try:
            import json
            _npc_dir = Path("config/npc/individuals")
            if _npc_dir.exists():
                for _f in _npc_dir.glob("*.json"):
                    _data = json.loads(_f.read_text(encoding="utf-8"))
                    _npc_name_map[_data.get("id", "")] = _data.get("name", "")
        except Exception:
            pass

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

        print(f"[GAME_SCREEN] entering main loop, walls={len(walls)}, obstacles={len(obstacles)}")
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
                        return
                    elif event.key == pygame.K_TAB:
                        # Переключение фокуса: игра <-> консоль общения
                        text_input.focused = not text_input.focused
                        if text_input.focused:
                            # Открыли консоль — ждём ввода игрока
                            print("[CONSOLE] opened — waiting for player input")
                        else:
                            # Закрыли консоль — убираем пузыри с экрана, чтобы не загораживали игру
                            message_log.clear()
                    # TextInput обрабатывает всё кроме WASD (pass_through)
                    handled = text_input.handle_event(event)
                    # RETURN обрабатывается отдельно — TextInput намеренно возвращает False
                    if event.key == pygame.K_RETURN and not text_input.empty:
                        # Игрок успел напечатать — отменяем telegraph
                        action_queue.cancel_telegraph()
                        print("[TELEGRAPH] cancelled — player acted first")
                        
                        # Создаем сценическое событие для пузыря игрока (ТЗ 3 + Мастер тай)
                        from narrative_beat import NarrativeBeat, DeliveryType, RecognitionLevel
                        player_beat = NarrativeBeat(
                            speaker=player_name,
                            text=text_input.text.strip(),
                            is_player=True,
                            delivery=DeliveryType.NORMAL,
                            recognition=RecognitionLevel.KNOWN_NAME,
                            is_active=True
                        )
                        message_log.append(player_beat)
                        
                        self._handle_text_input(
                            text_input.text.strip(), scene_state, focus,
                            walls, obstacles, move, message_log,
                            scene_w, scene_h,
                            action_queue, campaign_folder, player_name,
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
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    clicked_npc = self._handle_click(
                        event.pos, scene_state, focus, walls,
                    )
                    if clicked_npc:
                        move.target_npc_id = clicked_npc
                        move.direction = None
                        text_input.clear()
                        # Строим путь при клике
                        px, py = _player_xy(scene_state)
                        lp = (scene_state.get("npc_positions", {})
                              .get(clicked_npc, {}).get("local_position") or {})
                        tx, ty = lp.get("x", px), lp.get("y", py)
                        move.path = find_path(
                            px, py, tx, ty, scene_w, scene_h, walls, obstacles,
                        )
                        move.path_index = 0
                        if move.path:
                            message_log.append(f"Идёшь к {clicked_npc} ({len(move.path)} точек)")
                        else:
                            message_log.append("Путь не найден")
                            move.target_npc_id = None
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
                px, py = _player_xy(scene_state)
                npc_positions = scene_state.get("npc_positions", {})

                # Приоритет 1: идём по pathfinding-пути
                if move.path is not None and move.path_index < len(move.path):
                    target = move.path[move.path_index]
                    dx = target[0] - px
                    dy = target[1] - py
                    dist = math.hypot(dx, dy)
                    if dist < 0.3:
                        move.path_index += 1
                        if move.path_index >= len(move.path):
                            move.path = None
                            if move.target_npc_id:
                                from npc_name_resolver import npc_id_to_display
                                name = npc_id_to_display(move.target_npc_id)
                                message_log.append(f"Ты подошёл к {name}")
                                move.target_npc_id = None
                    else:
                        result = try_move(
                            px, py, dx, dy, walls, obstacles, npc_positions,
                            step_size=0.3,
                        )
                        if result.success:
                            moved = True
                        else:
                            move.path = None
                elif move.target_npc_id and move.target_npc_id in npc_positions:
                    lp = npc_positions[move.target_npc_id].get("local_position") or {}
                    result, arrived = move_towards(
                        px, py, lp.get("x", 0), lp.get("y", 0),
                        walls, obstacles, npc_positions,
                    )
                    if arrived:
                        from npc_name_resolver import npc_id_to_display
                        name = npc_id_to_display(move.target_npc_id)
                        message_log.append(f"Ты подошёл к {name}")
                        move.target_npc_id = None
                    elif result.success:
                        moved = True
                    elif result.blocked_by:
                        move.target_npc_id = None

                # Приоритет 2: WASD
                elif held_keys:
                    dx, dy = 0.0, 0.0
                    for key in held_keys:
                        if key in _WASD_MAP:
                            kx, ky = _WASD_MAP[key]
                            dx += kx
                            dy += ky
                    if dx != 0 or dy != 0:
                        result = try_move(
                            px, py, dx, dy, walls, obstacles, npc_positions,
                        )
                        if result.success:
                            moved = True
                        move.target_npc_id = None
                        move.direction = None

                if moved:
                    _set_player_xy(scene_state, result.new_x, result.new_y)
                    _check_transition_trigger(scene_state, result.new_x, result.new_y, message_log)
                    move.cooldown = _MOVE_INTERVAL
                    # Накопительное время: 10 сек за каждый полный метр (а не за микро-шаг 0.3)
                    move.walk_distance_accumulated += 0.3  # step_size
                    meters_walked = int(move.walk_distance_accumulated)
                    if meters_walked > 0:
                        self.game_time_seconds += TIME_DELTA_WALK_INDOOR * meters_walked
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
                for npc_id, new_data in _new_positions.items():
                    if npc_id in scene_state.get("npc_positions", {}):
                        existing = scene_state["npc_positions"][npc_id]
                        for k, v in new_data.items():
                            existing[k] = v
                    else:
                        scene_state.setdefault("npc_positions", {})[npc_id] = new_data

            if _new_positions:
                print(f"[IDLE_TICK] merged: {list(_new_positions.keys())}")

            # Синхронизация player_position и environment из world_snapshot
            if _ws:
                _pp = _ws.get("player_position")
                if _pp and len(_pp) == 2:
                    _set_player_xy(scene_state, float(_pp[0]), float(_pp[1]))
                _ws_tod = _ws.get("time_of_day")
                if _ws_tod:
                    scene_state.setdefault("environment", {})["time_of_day"] = _ws_tod
                    self.game_time_seconds = parse_hhmm(_ws_tod)
                _ws_weather = _ws.get("weather")
                if _ws_weather:
                    scene_state.setdefault("environment", {})["weather"] = _ws_weather

            # Pressure-driven: если idle_tick принёс proactive события → запускаем телеграф
            _events = _tick_data.get("events", [])
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
                    action_text=_telegraph_text,
                )
                print(f"[TELEGRAPH] event-driven: {_telegraph_text}")

                # Фаза 2.1 — distance-based интервал: в чате = частый, при ходьбе = редкий
                if not text_input.focused:
                    # WASD: чат не в фокусе → NPC двигаются по расстоянию
                    _nearest = _nearest_npc_distance(scene_state)
                    _tick_interval = _idle_tick_interval_ms(_nearest)
                else:
                    # Диалог: NPC стоят и разговаривают, не "летают" по комнате
                    _tick_interval = 30_000
                # Запускаем новый idle_tick если пора и предыдущий завершён
                if (_now - _last_idle_tick >= _tick_interval
                        and not _idle_tick_running[0]
                        and action_queue.pending_count() == 0):
                    # Фаза 4 — сохраняем позицию на бэкенд перед idle_tick
                    try:
                        _bridge = _gateway._bridge
                        if _bridge.ready:
                            _bridge.save_scene_state(campaign_folder, scene_state)
                    except Exception:
                        pass
                    _idle_tick_running[0] = True
                    _last_idle_tick = _now
                    print(f"[IDLE_TICK] fired at {_now}ms")
                    threading.Thread(target=_do_idle_tick, daemon=True).start()

            # === Poll backend responses ===
            result = action_queue.poll()
            if result is not None:
                if result.error:
                    message_log.append(f"[Ошибка] {result.error}")
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
                    from narrative_beat import NarrativeBeat, DeliveryType, RecognitionLevel
                    
                    # Получаем последний введенный текст игрока для фильтрации эха
                    last_player_text = ""
                    if message_log and isinstance(message_log[-1], NarrativeBeat) and message_log[-1].is_player:
                        last_player_text = message_log[-1].text.strip()

                    resp = result.response.dm_response
                    if resp and resp != "Ничего не произошло.":
                        import re
                        display_resp = resp.strip()
                        
                        # Умная фильтрация эха LLM
                        if last_player_text:
                            # 1. Снимаем эхо формата "Имя Игрока: текст" (LLM часто так делает)
                            if display_resp.lower().startswith(player_name.lower()):
                                prefix_len = len(player_name)
                                if prefix_len < len(display_resp) and display_resp[prefix_len] in (':', ',', ' '):
                                    display_resp = display_resp[prefix_len+1:].strip(' ,.-!:;')
                            
                            # 2. Пословное сравнение для обрезки неполного эха (игнорируем регистр и пунктуацию)
                            player_words = re.sub(r'[^\w\s]', '', last_player_text).lower().split()
                            resp_words = re.sub(r'[^\w\s]', '', display_resp).lower().split()
                            
                            match_count = 0
                            for pw, rw in zip(player_words, resp_words):
                                if pw == rw:
                                    match_count += 1
                                else:
                                    break
                            
                            # Если совпало больше половины слов ввода — это эхо, отрезаем
                            if match_count > 0 and match_count >= len(player_words) // 2:
                                # Считаем сколько символов занимает эхо с пробелами
                                echo_len = len(' '.join(display_resp.split()[:match_count]))
                                display_resp = display_resp[echo_len:].strip(' ,.-!:;')
                        
                        # Добавляем только если после отсечения эха остался нарратив
                        if display_resp:
                            message_log.append(NarrativeBeat(
                                speaker="Система",
                                text=display_resp,
                                is_player=False,
                                delivery=DeliveryType.NORMAL,
                                recognition=RecognitionLevel.KNOWN_NAME,
                                is_active=False
                            ))
                        
                    for npc_r in result.response.npc_reactions:
                        npc_name = npc_r.get("npc_name", "NPC")
                        npc_text = npc_r.get("reaction", "")
                        if npc_text:
                            # Реплика NPC становится полноценным пузырем
                            message_log.append(NarrativeBeat(
                                speaker=npc_name,
                                text=npc_text,
                                is_player=False,
                                delivery=DeliveryType.NORMAL,
                                recognition=RecognitionLevel.KNOWN_NAME, # TODO: уровень знакомства из сцены
                                is_active=False
                            ))

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

            # === Рендер ===
            px, py = _player_xy(scene_state)
            self.screen.fill((200, 0, 0))  # ЯРКО-КРАСНЫЙ — если видно, цикл работает
            self.renderer.render(
                scene=perceived,
                scene_w=scene_w,
                scene_h=scene_h,
                walls=walls,
                obstacles=obstacles,
                player_xy=(px, py),
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
            self._draw_message_log(message_log, narrative_renderer, player_name)

            # HUD: FPS + игровое время
            fps_surf = self.renderer.font_small.render(
                f"FPS: {int(self.clock.get_fps())}", True, (80, 80, 80)
            )
            self.screen.blit(fps_surf, (self.screen.get_width() - 70, 4))
            
            time_surf = self.renderer.font_small.render(
                format_game_time(self.game_time_seconds), True, (140, 140, 140)
            )
            self.screen.blit(time_surf, (self.screen.get_width() - 280, 4))

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

    def _draw_message_log(self, log: list, renderer: 'NarrativeRenderer', player_name: str) -> None:
        """Cinematic Layer: Рисует сценические пузыри вместо плоского чата"""
        from narrative_beat import NarrativeBeat, RecognitionLevel, DeliveryType
        
        sh = self.screen.get_height()
        sw = self.screen.get_width()
        
        visible = log[-5:] # Берем последние 5 событий
        
        # Адаптер: конвертируем строки в NarrativeBeat на лету
        beats = []
        for msg in visible:
            if isinstance(msg, str):
                is_player = msg.startswith(player_name)
                # Грубая нарезка "Имя: Текст"
                if ": " in msg:
                    speaker, text = msg.split(": ", 1)
                else:
                    speaker, text = "Система", msg
                
                # Определяем уровень знания (ТЗ 1)
                recognition = RecognitionLevel.KNOWN_NAME
                if not is_player and speaker in ("Мужчина", "Женщина", "???"):
                    recognition = RecognitionLevel.UNKNOWN_MALE if speaker == "Мужчина" else RecognitionLevel.UNKNOWN_FEMALE
                
                # Создаем Beat
                beat = NarrativeBeat(
                    speaker=speaker.strip(),
                    text=text.strip(),
                    is_player=is_player,
                    recognition=recognition,
                    delivery=DeliveryType.NORMAL,
                    is_active=(msg == visible[-1]) # Активен только последний
                )
                beats.append(beat)
            elif isinstance(msg, NarrativeBeat):
                msg.is_active = (msg == visible[-1])
                beats.append(msg)

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
            if beat.is_player:
                bx = sw // 2 + 20
            else:
                bx = 20
                
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
        campaign_id: str = "",
        player_name: str = "",
    ) -> None:
        """Парсит текст: movement — локально, остальное — через backend"""
        npc_ids = list(scene_state.get("npc_positions", {}).keys())
        intent = parse_movement_intent(text, npc_ids)

        if intent is None:
            # Не movement — отправляем на backend (LLM обработка)
            px, py = _player_xy(scene_state)
            action_queue.submit(campaign_id, player_name, text, px, py)
            message_log.append(f"⟳ {text}")
            return

        if intent.target_npc_id:
            focus.focus_entity_id = intent.target_npc_id
            move.target_npc_id = intent.target_npc_id
            move.direction = None
            px, py = _player_xy(scene_state)
            lp = (scene_state.get("npc_positions", {})
                  .get(intent.target_npc_id, {}).get("local_position") or {})
            tx, ty = lp.get("x", px), lp.get("y", py)
            move.path = find_path(
                px, py, tx, ty, scene_w, scene_h, walls, obstacles,
            )
            move.path_index = 0
            if move.path:
                message_log.append(f"Идёшь к {intent.target_display_name}")
            else:
                message_log.append("Путь не найден")
                move.target_npc_id = None
        elif intent.direction:
            move.direction = intent.direction
            move.target_npc_id = None
            names = {
                "north": "север", "south": "юг",
                "east": "восток", "west": "запад",
            }
            message_log.append(f"Идёшь на {names.get(intent.direction, intent.direction)}")

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