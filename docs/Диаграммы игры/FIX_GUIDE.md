# FIX_GUIDE: Инструкция по починке игры ENIGMA

**Версия:** 1.0
**Дата:** 2026-07-06
**Проект:** ENIGMA V.0.5.3.3.8
**Статус:** Готов к исполнению
**Связанный документ:** `docs/Диаграммы игры/TZ-INFRA-1.md` (реестр багов)

---

## 0. КАК ПОЛЬЗОВАТЬСЯ ЭТОЙ ИНСТРУКЦИЕЙ

Эта инструкция — **пошаговое руководство** по исправлению всех найденных багов. Каждый баг имеет:
- **ID** — для отслеживания (BUG-P0-01, BUG-P1-01 и т.д.)
- **Файл** — где находится проблема
- **Симптом** — что видит игрок
- **Корневая причина** — почему это происходит
- **Исправление** — конкретный код для замены
- **Проверка** — как убедиться что баг закрыт

**Порядок исполнения:** строго по приоритетам (P0 → P1 → P2 → P3). P0 баги блокируют игру, без их исправления остальные не имеют смысла.

---

## ЧАСТЬ 1. P0 — КРИТИЧЕСКИЕ БАГИ (БЛОКИРУЮТ ИГРУ)

---

### BUG-P0-01: Время застывает на 12:02

**Файлы:**
- `backend/app/core/calendar.py`
- `backend/app/services/tick_orchestrator.py:982-1007`
- `backend/app/services/game_loop/scene_init.py:73-79`
- `backend/app/services/integration/world_snapshot_builder.py`
- `frontend/game_screen.py:780-783`

**Симптом:** Игровое время отображается как "12:02" и не меняется при idle_tick.

**Корневая причина:**
1. `Calendar.advance(total_seconds, delta)` может обрабатывать секунды корректно, но `format_time` обрезает до минут — `12:01:40` становится `12:01`, а `parse_hhmm("12:01")` теряет 40 секунд. При следующем тике: `12:01 + 60с = 12:02`, `format_time → "12:01"` (теряет 60 сек). Цикл.
2. `game_time_seconds` может не передаваться в `world_snapshot`.
3. Frontend не имеет fallback при отсутствии `game_time_seconds` в ответе.

**Исправление:**

**Шаг 1 — Проверить и исправить `backend/app/core/calendar.py`:**
```python
def advance(total_seconds: int, delta: int) -> int:
    """Продвигает время на delta секунд. НЕ обрезать!"""
    return total_seconds + delta

def format_time(total_seconds: int) -> str:
    """Формат HH:MM:SS для точности (или HH:MM если секунды = 0)."""
    if total_seconds < 0:
        total_seconds = 0
    h = (total_seconds // 3600) % 24
    m = (total_seconds // 60) % 60
    s = total_seconds % 60
    if s == 0:
        return f"{h:02d}:{m:02d}"
    return f"{h:02d}:{m:02d}:{s:02d}"

def parse_hhmm(time_str: str) -> int:
    """Парсит HH:MM или HH:MM:SS в секунды."""
    try:
        parts = time_str.strip().split(":")
        h = max(0, min(int(parts[0]), 23))
        m = max(0, min(int(parts[1]), 59))
        s = int(parts[2]) if len(parts) > 2 else 0
        return h * 3600 + m * 60 + s
    except (ValueError, IndexError):
        return 7 * 3600  # 07:00
```

**Шаг 2 — Гарантировать `game_time_seconds` в `world_snapshot`:**
```python
# backend/app/services/integration/world_snapshot_builder.py
# В методе build() — всегда включать game_time_seconds

def build(self, scene_state, tick, player_perception=None, all_npcs_raw=None, recent_dialogues=None):
    # ... существующий код ...
    
    # ГАРАНТИРОВАННОЕ время
    game_time_seconds = scene_state.get("game_time_seconds")
    if not game_time_seconds or game_time_seconds <= 0:
        # Fallback: парсим time_of_day
        _env = scene_state.get("environment", {}).get("time_of_day", "07:00")
        from app.core.calendar import Calendar
        game_time_seconds = Calendar.parse_hhmm(_env)
        scene_state["game_time_seconds"] = game_time_seconds
    
    ws.game_time_seconds = game_time_seconds
    # ...
```

**Шаг 3 — Frontend fallback при отсутствии `game_time_seconds`:**
```python
# frontend/game_screen.py:780-783 — заменить блок
_ws_gts = _ws.get("game_time_seconds")
if _ws_gts is not None and _ws_gts > 0:
    scene_state["game_time_seconds"] = _ws_gts
    self.game_time_seconds = _ws_gts
else:
    # FALLBACK: локально продвигаем время на GAME_TICK_INTERVAL_SECONDS (60 сек)
    from constants import SECONDS_PER_MINUTE
    _tick_interval_sec = 60  # GAME_TICK_INTERVAL_SECONDS
    self.game_time_seconds += _tick_interval_sec
    scene_state["game_time_seconds"] = self.game_time_seconds
    logger.warning("[TIME_FALLBACK] backend не прислал game_time_seconds, локальное продвижение +%dс", _tick_interval_sec)
```

**Шаг 4 — Добавить диагностику:**
```python
# frontend/game_screen.py — после обновления времени
logger.debug(f"[TIME] game_time_seconds={self.game_time_seconds} formatted={format_world_date(self.game_time_seconds)}")
```

**Проверка:**
1. Запустить игру
2. Подождать 10 idle_tick (примерно 20 секунд реального времени)
3. Игровое время должно увеличиться минимум на 10 минут (10 × 60 сек = 600 сек = 10 минут)

---

### BUG-P0-02: NPC не двигаются

**Файлы:**
- `backend/app/services/spatial/movement_engine.py`
- `frontend/scene_renderer.py:285-318`
- `frontend/game_screen.py:267-316`
- `backend/app/services/integration/world_snapshot_builder.py`

**Симптом:** NPC стоят на месте, не перемещаются по расписанию или при командах.

**Корневая причина:**
1. `entity.velocity` всегда `(0, 0)` — backend не отправляет velocity
2. `entity.traversal_status` всегда `"IDLE"` — нет `active_traversals`
3. `_resolve_visual_xy` возвращает snap к `local_position` — нет интерполяции

**Исправление:**

**Шаг 1 — Backend: гарантировать velocity в npc_positions:**
```python
# backend/app/services/spatial/movement_engine.py
# Добавить в конец process_intents() — вычислять velocity для каждого NPC

class MovementEngine:
    def __init__(self):
        self._prev_positions: dict = {}
    
    def process_intents(self, intents, tick, npc_positions, campaign_id=None, scene_state=None):
        # ... существующий код обработки intents ...
        
        # НОВОЕ: Вычислить velocity для каждого NPC на основе изменения позиции
        for npc_id, pos_data in npc_positions.items():
            curr_pos = pos_data.get("local_position", {})
            prev_pos = self._prev_positions.get(npc_id, {})
            
            if prev_pos and curr_pos:
                # dt = 1 тик = 60 секунд игрового времени
                dt = 60.0
                vx = (curr_pos.get("x", 0) - prev_pos.get("x", 0)) / dt
                vy = (curr_pos.get("y", 0) - prev_pos.get("y", 0)) / dt
                pos_data["velocity"] = [round(vx, 4), round(vy, 4)]
            else:
                pos_data.setdefault("velocity", [0.0, 0.0])
            
            self._prev_positions[npc_id] = dict(curr_pos)
        
        return changes
```

**Шаг 2 — WorldSnapshotBuilder: включить velocity:**
```python
# backend/app/services/integration/world_snapshot_builder.py
# Убедиться что NPCPositionDTO содержит velocity и сериализуется

@dataclass
class NPCPositionDTO:
    # ... существующие поля ...
    velocity: tuple[float, float] = (0.0, 0.0)
    exertion_level: float = 0.0
    
    @classmethod
    def from_position_data(cls, npc_id: str, data: dict):
        return cls(
            # ... существующие поля ...
            velocity=tuple(data.get("velocity", (0.0, 0.0))),
            exertion_level=float(data.get("exertion_level", 0.0)),
        )
```

**Шаг 3 — Frontend: lerp-интерполяция в renderer (см. также BUG-P0-06):**
```python
# frontend/scene_renderer.py:285-318 — добавить lerp fallback

# Константа скорости lerp (такая же как у игрока)
_NPC_LERP_SPEED = 8.0  # м/сек

for entity in entities:
    if entity.entity_type != "npc" or not entity.visible:
        continue
    
    prev_x, prev_y = self._prev_npc_positions.get(entity.entity_id, (entity.x, entity.y))
    
    # Режим 1: Macro (TraversalState) — существующая логика
    if entity.traversal_status in ("PENDING", "MOVING") and entity.traversal_speed > 0:
        dx, dy = entity.x - prev_x, entity.y - prev_y
        dist = (dx**2 + dy**2)**0.5
        step = entity.traversal_speed * dt
        if dist <= step or dist < 0.01:
            render_x, render_y = entity.x, entity.y
        else:
            ratio = step / dist
            render_x, render_y = prev_x + dx * ratio, prev_y + dy * ratio
    
    # Режим 2: Micro (ETKE-IK velocity)
    elif entity.velocity is not None and (abs(entity.velocity[0]) > 0.01 or abs(entity.velocity[1]) > 0.01):
        _vx, _vy = entity.velocity
        render_x = entity.x + _vx * dt
        render_y = entity.y + _vy * dt
    
    # Режим 3: LERP к целевой позиции (НОВОЕ — унификация с игроком)
    else:
        dx, dy = entity.x - prev_x, entity.y - prev_y
        dist = (dx**2 + dy**2)**0.5
        if dist > 0.01:
            # Если расстояние большое (> 3м) — это телепортация, snap
            if dist > 3.0:
                render_x, render_y = entity.x, entity.y
            else:
                # Lerp к цели со скоростью как у игрока
                step = _NPC_LERP_SPEED * dt
                if step >= dist:
                    render_x, render_y = entity.x, entity.y
                else:
                    ratio = step / dist
                    render_x = prev_x + dx * ratio
                    render_y = prev_y + dy * ratio
        else:
            render_x, render_y = entity.x, entity.y
    
    sx, sy = self._w2s(render_x, render_y, cam_x, cam_y)
    # ... остальной рендер
```

**Проверка:**
1. Запустить игру
2. NPC в таверне должен перемещаться по расписанию (менять активность каждый час игрового времени)
3. Позиция NPC на экране должна меняться плавно

---

### BUG-P0-03: "Подойди ко мне" не работает

**Файлы:**
- `backend/app/services/tick_orchestrator.py:518-584`
- `backend/app/services/npc/npc_tick_pipeline.py:1080-1180`
- `backend/app/services/game_loop/scene_init.py:60-71`

**Симптом:** При команде "подойди ко мне" NPC не двигается к игроку.

**Корневая причина:**
1. В `_process_player_dm_action` проверяется `_is_npc_target` — является ли target NPC. Для "подойди ко мне" target="мне"/"player"/"" → `_is_npc_target = False`, Fast Path не срабатывает.
2. В `_resolve_reactive_movement` — `target_entry = _pos("player")` возвращает `{}` если player отсутствует в `npc_positions` (фронтенд фильтрует его).
3. `target_x = None`, `target_node_id = None`, `return None` — движение блокируется.

**Исправление:**

**Шаг 1 — Fast Path для "подойди ко мне" в tick_orchestrator:**
```python
# backend/app/services/tick_orchestrator.py:518-584
# Заменить блок проверки _is_npc_target

if _sem_action and _sem_action.upper() == "MOVE":
    _target_ref = (_sem_target or "").lower()
    
    # НОВОЕ: "подойди ко мне" / "иди сюда" / "подойди" — target=player
    _is_player_target = _target_ref in ("player", "мне", "сюда", "ко мне", "")
    _is_npc_target = any(
        _target_ref in n.get("name", "").lower() or _target_ref in n.get("npc_id", "").lower()
        for n in ctx.all_npcs_raw
    ) if ctx.all_npcs_raw else False
    
    if _is_player_target:
        # Найти ВСЕХ живых NPC и заставить их подойти к игроку
        _player_pos = ctx.scene_state.get("player_spatial", {}).get("local_position", {"x": 0, "y": 0})
        _player_xy = (_player_pos.get("x", 0), _player_pos.get("y", 0))
        
        for _npc in ctx.all_npcs_raw:
            _nid = _npc.get("npc_id") or _npc.get("id")
            if not _nid or _nid == "player":
                continue
            if _npc.get("body_state", {}).get("life_status") == "DEAD":
                continue
            # Инжектировать directive для каждого NPC
            _npc.setdefault("perceptual_kernel", {})["recent_directive"] = {
                "source": "player",
                "interrupts_routine": True,
                "salience": 0.9,
            }
        
        # Fast Path: создать LocalSteeringGoal для ближайших NPC
        from app.domain.movement import LocalSteeringGoal
        from app.services.spatial.movement_engine import MovementEngine
        _spatial_svc = self._resolve_spatial_service(ctx)
        if _spatial_svc:
            _fast_intents = []
            for _npc in ctx.all_npcs_raw:
                _nid = _npc.get("npc_id") or _npc.get("id")
                if not _nid or _nid == "player":
                    continue
                if _npc.get("body_state", {}).get("life_status") == "DEAD":
                    continue
                _fast_intents.append(LocalSteeringGoal(
                    npc_id=_nid,
                    local_target_xy=_player_xy,
                    reason="micro_snap:approach_player",
                    priority=0.9
                ))
            
            if _fast_intents:
                me = MovementEngine()
                me.set_spatial_service(_spatial_svc)
                _changes = me.process_intents(
                    _fast_intents, ctx.tick_number,
                    ctx.scene_state.get("npc_positions", {}),
                    campaign_id=ctx.campaign_id, scene_state=ctx.scene_state
                )
                if _changes and self._scene_manager:
                    self._apply_with_shadow_observation(ctx, _changes, phase_label="FAST_PATH_APPROACH_PLAYER")
                    logger.warning(f"[FAST_PATH] Applied approach-player for {len(_fast_intents)} NPCs")
    
    elif _is_npc_target:
        # ... существующий код для NPC target
```

**Шаг 2 — Гарантировать player в npc_positions:**
```python
# backend/app/services/game_loop/scene_init.py:60-71
def _update_player_position(scene_state: dict, player_position: tuple[float, float] | None) -> None:
    if player_position is None:
        return
    node = scene_state.setdefault("npc_positions", {}).setdefault("player", {})
    node["local_position"] = {"x": player_position[0], "y": player_position[1]}
    if not node.get("position"):
        _ps = scene_state.get("player_spatial", {})
        if _ps and _ps.get("position"):
            node["position"] = _ps["position"]
    # НОВОЕ: Гарантировать name для резолвера
    if not node.get("name"):
        node["name"] = "Игрок"
```

**Шаг 3 — Fallback на player_spatial в _resolve_reactive_movement:**
```python
# backend/app/services/npc/npc_tick_pipeline.py:1130-1156
# В блоке if intent == "approach":

if intent == "approach":
    target_entry = _pos(_target_id)
    lp = target_entry.get("local_position", {})
    target_x = lp.get("x")
    target_y = lp.get("y")
    
    # НОВОЕ: Fallback на player_spatial если player отсутствует в npc_positions
    if _target_id == "player" and (target_x is None or target_y is None):
        _ps = scene_state.get("player_spatial", {}).get("local_position", {})
        target_x = _ps.get("x")
        target_y = _ps.get("y")
        target_entry = {"local_position": _ps, "position": scene_state.get("location_id", "")}
        logger.info(f"[APPROACH_NAV] player recovered from player_spatial: ({target_x}, {target_y})")
    
    if target_x is None or target_y is None:
        logger.warning(f"[APPROACH_NAV] target={_target_id} has no coordinates! Movement blocked.")
        return None
    
    # ... остальной код (Путь 1: точное позиционирование через local_position)
```

**Шаг 4 — Семантический парсер должен распознавать "мне"/"сюда":**
```python
# Проверить intent_parser / dm_router — должен возвращать target_reference="player" для "мне"/"сюда"/"ко мне"
# Если используется LLM для парсинга — добавить примеры в few-shot prompt:
# "подойди ко мне" → {"semantic_action": "MOVE", "target_reference": "player"}
# "иди сюда" → {"semantic_action": "MOVE", "target_reference": "player"}
# "торнин подойди" → {"semantic_action": "MOVE", "target_reference": "торнин"}
```

**Проверка:**
1. Ввести "подойди ко мне" в чат
2. Ближайший живой NPC должен начать движение к игроку
3. В логах backend должно быть `[FAST_PATH] Applied approach-player for N NPCs`

---

### BUG-P0-04: Кнопки промотки времени не работают

**Файлы:**
- `frontend/api_client.py:121-125, 527-534`
- `frontend/game_screen.py:520-529, 558-565`

**Симптом:** Нажатие клавиш 1, 2, 3, 4 не проматывает время.

**Корневая причина:**
1. `FallbackGateway.skip_time` определён ВНУТРИ docstring другого метода — не становится атрибутом класса
2. `HttpGameGateway` не имеет метода `skip_time`
3. `DirectGameGateway` не имеет метода `skip_time`
4. `BackendContract` имеет `skip_time`, но `HttpGameGateway` не делегирует

**Исправление:**

**Шаг 1 — Добавить `skip_time` в `HttpGameGateway`:**
```python
# frontend/api_client.py — в класс HttpGameGateway (после load_campaign)

def skip_time(self, campaign_id: str, ticks: int) -> dict:
    """Промотка времени через HTTP."""
    return self._contract.skip_time(campaign_id, ticks)
```

**Шаг 2 — Добавить `skip_time` в `DirectGameGateway`:**
```python
# frontend/api_client.py — в класс DirectGameGateway (после load_campaign)

def skip_time(self, campaign_id: str, ticks: int) -> dict:
    """Промотка времени через прямой вызов GameLoop."""
    from game_loop_bridge import get_game_loop_bridge
    _bridge = get_game_loop_bridge()
    if not _bridge.ready:
        _bridge.initialize()
    if not hasattr(_bridge._loop, 'skip_time'):
        logger.error("[DIRECT_GATEWAY] GameLoop has no skip_time method")
        return {"status": "error", "error": "skip_time not implemented"}
    return _bridge._loop.skip_time(campaign_id, ticks)
```

**Шаг 3 — Исправить `FallbackGateway.skip_time` (вынести из docstring):**
```python
# frontend/api_client.py — класс FallbackGateway
# УДАЛИТЬ строки 525-535 (метод внутри docstring)
# ДОБАВИТЬ правильный метод внутри тела класса после __init__:

class FallbackGateway:
    """HTTP приоритет, Direct fallback при обрыве."""
    
    _retry_interval: int = 5
    
    def __init__(self, primary: GameGateway, fallback: GameGateway) -> None:
        self._primary = primary
        self._fallback = fallback
        self._primary_healthy: bool | None = None
        self._requests_since_fail: int = 0
    
    def skip_time(self, campaign_id: str, ticks: int) -> dict:
        """FIX-2: FallbackGateway skip_time через primary или fallback."""
        if self._primary_healthy is not False:
            try:
                if hasattr(self._primary, 'skip_time'):
                    return self._primary.skip_time(campaign_id, ticks)
            except Exception as e:
                logger.warning(f"[FALLBACK] primary skip_time failed: {e}")
                self._primary_healthy = False
        if hasattr(self._fallback, 'skip_time'):
            return self._fallback.skip_time(campaign_id, ticks)
        logger.warning("[FALLBACK_GATEWAY] skip_time not available on either gateway")
        return {"status": "skipped", "ticks": 0}
    
    # ... остальные методы
```

**Шаг 4 — Логировать результат skip_time в game_screen:**
```python
# frontend/game_screen.py:520-529 — заменить _do_skip_time

def _do_skip_time(ticks: int):
    _idle_tick_running[0] = True
    try:
        result = _gateway.skip_time(campaign_folder, ticks)
        logger.info(f"[SKIP_TIME] result={result.get('status')} ticks_skipped={result.get('ticks_skipped')}")
        _idle_tick_result.clear()
        _idle_tick_result.append(result)
    except Exception as e:
        import traceback
        logger.error(f"[SKIP_TIME] ERROR: {e}\n{traceback.format_exc()}")
    _idle_tick_running[0] = False
```

**Шаг 5 — Обновить время из результата skip_time:**
```python
# frontend/game_screen.py — в обработке _idle_tick_result, добавить проверку skip_time

if _tick_data:
    # Если это результат skip_time (есть stop_reason)
    if _tick_data.get("stop_reason") or _tick_data.get("ticks_skipped"):
        _ws_skip = _tick_data.get("world_snapshot")
        if _ws_skip:
            _ws_gts = _ws_skip.get("game_time_seconds")
            if _ws_gts and _ws_gts > 0:
                self.game_time_seconds = _ws_gts
                scene_state["game_time_seconds"] = _ws_gts
                logger.info(f"[SKIP_TIME] time updated to {format_world_date(_ws_gts)}")
            # Обновить npc_positions
            _skip_positions = _ws_skip.get("npc_positions", {})
            if _skip_positions:
                import copy
                for npc_id, new_data in _skip_positions.items():
                    scene_state.setdefault("npc_positions", {})[npc_id] = copy.deepcopy(new_data)
```

**Проверка:**
1. Нажать `1` → время должно прыгнуть на 10 тиков (10 минут)
2. Нажать `4` → время должно прыгнуть на 2000 тиков (~33 часа)
3. В логах должно быть `[SKIP_TIME] time updated to ...`

---

### BUG-P0-05: LLM генерирует текст за NPC и автора с системными маркерами

**Файлы:**
- `frontend/game_screen.py:1050-1132`
- `backend/app/services/verbalization/response_validator.py`

**Симптом:** DM ответ содержит `(whisper)`, `[internal]`, `*thought*` и другие английские маркеры. NPC речь дублируется в message_log и облачке.

**Корневая причина:**
1. LLM (Qwen 7B) генерирует markdown-теги, которые проходят валидацию
2. RCE извлекает NPC речь из DM ответа → попадает в облачко
3. Парсер game_screen также добавляет строки в message_log → дубль
4. Валидатор `_contains_non_russian` пропускает короткие английские маркеры

**Исправление:**

**Шаг 1 — Фильтровать системные маркеры в DM response:**
```python
# frontend/game_screen.py — добавить функцию перед использованием

import re

def _clean_dm_response(text: str) -> str:
    """Удаляет системные маркеры LLM."""
    # Удалить markdown-теги в скобках: (whisper), (shout), [internal], [narrator], etc.
    text = re.sub(
        r'\s*[\(\[]\s*(whisper|shout|internal|narrator|thought|action|ooc|system|idle|approach|flee|combat|description|narration)\s*[\)\]]\s*',
        ' ',
        text,
        flags=re.IGNORECASE
    )
    # Удалить markdown-звёздочки: *текст*
    text = re.sub(r'\*([^*]+)\*', r'\1', text)
    # Удалить двойные кавычки-обёртки
    text = re.sub(r'^["\「](.+?)["\」]$', r'\1', text.strip())
    # Удалить дублирующиеся пустые строки
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()

# Использование в game_screen.py:1050:
if resp and resp != t("ui:nothing_happened"):
    resp = _clean_dm_response(resp)
    # ... дальнейший парсинг
```

**Шаг 2 — Не дублировать NPC речь в message_log:**
```python
# frontend/game_screen.py — в цикле парсинга строк (после строки 1067)

_seen_npc_reactions = set()
for npc_r in (result.response.npc_reactions or []):
    if isinstance(npc_r, dict):
        _rtext = npc_r.get("reaction", "").strip()
    elif isinstance(npc_r, str) and ":" in npc_r:
        _rtext = npc_r.split(":", 1)[1].strip()
    else:
        _rtext = ""
    if _rtext:
        _seen_npc_reactions.add(_rtext[:80].lower())

for line in raw_lines:
    line_stripped = line.strip()
    if not line_stripped:
        continue
    
    # НОВОЕ: Проверяем, не является ли строка уже извлечённой NPC реакцией
    _is_npc_reaction = False
    for _rtext_key in _seen_npc_reactions:
        if _rtext_key in line_stripped.lower() or line_stripped.lower() in _rtext_key:
            _is_npc_reaction = True
            break
    
    if _is_npc_reaction:
        continue  # Уже в облачке, не дублируем в message_log
    
    # ... дальнейший парсинг спикера (существующий код)
```

**Шаг 3 — Усилить валидатор:**
```python
# backend/app/services/verbalization/response_validator.py
# Добавить в класс ResponseValidator

_SYSTEM_MARKERS = [
    "(whisper)", "(shout)", "(internal)", "(narrator)", "(thought)",
    "(action)", "(ooc)", "(system)", "(idle)", "(approach)", "(flee)",
    "(combat)", "(description)", "(narration)",
    "[internal]", "[narrator]", "[ooc]", "[system]", "[action]",
    "[description]", "[narration]",
]

def _contains_system_markers(self, text: str) -> bool:
    lower = text.lower()
    return any(marker in lower for marker in self._SYSTEM_MARKERS)

def _strip_system_markers(self, text: str) -> str:
    import re
    for marker in self._SYSTEM_MARKERS:
        text = text.replace(marker, "")
    # Очистка от markdown-звёздочек
    text = re.sub(r'\*([^*]+)\*', r'\1', text)
    # Очистка от двойных пробелов
    text = re.sub(r'  +', ' ', text)
    return text.strip()

# В методе validate() — добавить после проверки 4-й стены (строка 73):
if self._contains_system_markers(text):
    text = self._strip_system_markers(text)
    if not text:
        return self._fallback("system_markers_only")
```

**Шаг 4 — Дедупликация message_log:**
```python
# frontend/game_screen.py — перед добавлением NarrativeBeat

_seen_texts = set()
for beat in message_log:
    _seen_texts.add(beat.text[:50].lower())

# При добавлении:
if text[:50].lower() not in _seen_texts:
    message_log.append(NarrativeBeat(...))
    _seen_texts.add(text[:50].lower())
```

**Проверка:**
1. Ввести любой диалог
2. DM ответ НЕ должен содержать `(whisper)`, `[internal]`, `*thought*`
3. NPC речь должна быть ТОЛЬКО в облачке над NPC, НЕ в message_log
4. Не должно быть дублей в message_log

---

### BUG-P0-06: NPC телепортируются

**Файлы:**
- `frontend/scene_renderer.py:285-318`
- `frontend/game_screen.py:678-728`
- `frontend/constants.py`

**Симптом:** NPC мгновенно перемещаются между позициями, в то время как игрок (стрелка) движется плавно.

**Корневая причина:**
- Игрок движется локально через WASD: `speed = 8.0 * dt` каждый кадр (60 FPS)
- NPC обновляется только через idle_tick (раз в 2–30 секунд) → snap к новой позиции
- Нет lerp-интерполяции между обновлениями

**Исправление:**

**Шаг 1 — Lerp-интерполяция для NPC (см. BUG-P0-02 Шаг 3):**
Режим 3 в `_draw_npcs` — lerp к целевой позиции со скоростью как у игрока.

**Шаг 2 — Унифицировать скорость:**
```python
# frontend/constants.py — добавить (или обновить если есть)

# Единая скорость для игрока и NPC
PLAYER_SPEED = 8.0  # м/сек
NPC_LERP_SPEED = 8.0  # м/сек — такая же как у игрока
NPC_TELEPORT_THRESHOLD = 3.0  # м — если расстояние > 3м, snap (не lerp)
```

**Шаг 3 — Использовать константы в game_screen.py:**
```python
# frontend/game_screen.py:688 — заменить хардкод
# Было: speed = 8.0 * dt
# Стало:
from constants import PLAYER_SPEED
speed = PLAYER_SPEED * dt
```

**Шаг 4 — Использовать константы в scene_renderer.py:**
```python
# frontend/scene_renderer.py — в начале файла
from constants import NPC_LERP_SPEED, NPC_TELEPORT_THRESHOLD

# В _draw_npcs — Режим 3:
else:
    dx, dy = entity.x - prev_x, entity.y - prev_y
    dist = (dx**2 + dy**2)**0.5
    if dist > 0.01:
        if dist > NPC_TELEPORT_THRESHOLD:
            render_x, render_y = entity.x, entity.y
        else:
            step = NPC_LERP_SPEED * dt
            if step >= dist:
                render_x, render_y = entity.x, entity.y
            else:
                ratio = step / dist
                render_x = prev_x + dx * ratio
                render_y = prev_y + dy * ratio
    else:
        render_x, render_y = entity.x, entity.y
```

**Шаг 5 — Увеличить частоту idle_tick (опционально):**
```python
# frontend/constants.py — более плавное движение
# Было:
IDLE_TICK_NEAR_MS = 2_000  # 2 сек
IDLE_TICK_MID_MS = 8_000   # 8 сек
IDLE_TICK_FAR_MS = 30_000  # 30 сек

# Стало (более плавное):
IDLE_TICK_NEAR_MS = 500    # 0.5 сек
IDLE_TICK_MID_MS = 1_500   # 1.5 сек
IDLE_TICK_FAR_MS = 5_000   # 5 сек
```

**Проверка:**
1. Игрок (стрелка) и NPC (спрайты) должны двигаться с одинаковой плавностью
2. NPC не должен телепортироваться при смене позиции (если расстояние < 3м)
3. При большом скачке (> 3м — смена локации) — snap допустим

---

### BUG-P0-07: Баг в `_point_near_line`

**Файл:** `frontend/map_editor/editor_core.py:1838`

**Симптом:** Невозможно выделить стену кликом мыши в редакторе карт.

**Корневая причина:**
```python
t = max(0, min(1, ((px - x1) * (x2 - x1) + (py - y1) * (py - y1)) / (line_len ** 2)))
```
Должно быть `(py - y1) * (y2 - y1)`, а не `(py - y1) * (py - y1)`. Проекция Y вычисляется неверно.

**Исправление:**
```python
# frontend/map_editor/editor_core.py:1838
# Было:
t = max(0, min(1, ((px - x1) * (x2 - x1) + (py - y1) * (py - y1)) / (line_len ** 2)))

# Стало:
t = max(0, min(1, ((px - x1) * (x2 - x1) + (py - y1) * (y2 - y1)) / (line_len ** 2)))
```

**Проверка:**
1. Открыть редактор карт
2. Кликнуть по стене — она должна выделиться жёлтой рамкой

---

### BUG-P0-08: QUIT-баг в редакторе

**Файл:** `frontend/map_editor/editor_core.py:913`

**Симптом:** Закрытие окна редактора через крестик не останавливает процесс.

**Корневая причина:**
```python
if event.type == pygame.QUIT:
    running = False  # локальная переменная, не self._running
```
Главный цикл `while self._running:` не останавливается.

**Исправление:**
```python
# frontend/map_editor/editor_core.py:913
# Было:
if event.type == pygame.QUIT:
    running = False

# Стало:
if event.type == pygame.QUIT:
    self._running = False
```

**Проверка:**
1. Открыть редактор карт
2. Закрыть окно через крестик — процесс должен завершиться

---

### BUG-P0-09: NameError в `data_manager.py`

**Файл:** `frontend/map_editor/data_manager.py:455`

**Симптом:** При `_next_id` с неожиданным форматом ID → `NameError: logger` вместо логирования.

**Корневая причина:** `logger` используется, но не определён в модуле.

**Исправление:**
```python
# frontend/map_editor/data_manager.py — добавить в начало файла (после импортов)

import logging
logger = logging.getLogger(__name__)
```

**Проверка:**
1. `python -c "from data_manager import DataManager; dm = DataManager(); dm._next_id([], 'obj_')"` не должен вызывать NameError

---

### BUG-P0-10: NameError в `dm_agent.py`

**Файл:** `backend/app/agents/dm_agent.py`

**Симптом:** При ошибках в `run()`, `narrate()` → `NameError: logger` маскирует реальные баги.

**Корневая причина:** `logger` используется (строки 92, 605, 619, 681, 714), но не определён на уровне модуля.

**Исправление:**
```python
# backend/app/agents/dm_agent.py — добавить после импортов (после строки 21)

import logging
logger = logging.getLogger(__name__)
```

**Проверка:**
1. `python -c "from app.agents.dm_agent import DmAgent; a = DmAgent(); a.run('', [], {}, {}, {}, False, None)"` не должен вызывать NameError

---

### BUG-P0-11: Hex-цвет в `pygame.draw.circle`

**Файл:** `frontend/map_editor/editor_core.py:2407`

**Симптом:** Проходы (двери, окна) не рисуются в редакторе.

**Корневая причина:**
```python
color = {"door": "#FFD700", "window": "#87CEEB", "gap": "#AAAAAA"}.get(ptype, "#FFD700")
pygame.draw.circle(self.screen, color, (sx, sy), 6)
```
`pygame.draw.circle` не принимает hex-строку, нужен `(R, G, B)` tuple.

**Исправление:**
```python
# frontend/map_editor/editor_core.py:2407
# Было:
color = {"door": "#FFD700", "window": "#87CEEB", "gap": "#AAAAAA"}.get(ptype, "#FFD700")

# Стало:
color = {
    "door": (255, 215, 0),    # Gold
    "window": (135, 206, 235), # Sky Blue
    "gap": (170, 170, 170),    # Gray
}.get(ptype, (255, 215, 0))
```

**Проверка:**
1. Открыть редактор, создать проход в стене
2. Дверь должна рисоваться жёлтым кругом, окно — голубым

---

### BUG-P0-12: Body state в неверной позиции

**Файл:** `frontend/scene_renderer.py:591`

**Симптом:** Body state игрока (стресс, раны) рендерится за пределами экрана.

**Корневая причина:**
```python
y = sw - 10 - len(scene.player_body_state) * 18 - 20
```
Используется `sw` (ширина экрана) для Y-координаты. Должно быть `sh` (высота).

**Исправление:**
```python
# frontend/scene_renderer.py:591
# Было:
y = sw - 10 - len(scene.player_body_state) * 18 - 20

# Стало:
sh = self.screen.get_height()
y = sh - 10 - len(scene.player_body_state) * 18 - 20
```

**Проверка:**
1. Body state должен отображаться в нижнем левом углу экрана

---

## ЧАСТЬ 2. P1 — ВЫСОКИЕ БАГИ

---

### BUG-P1-01: Направление взгляда не работает

**Файлы:**
- `frontend/game_screen.py:42-106, 634`
- `frontend/scene_renderer.py:435-458`

**Симптом:** Жёлтая линия взгляда от NPC к игроку не появляется.

**Корневая причина:**
1. `is_looking_at_player = is_focused or any(inf.type == "communication" for inf in entity.inferences)`
2. `is_focused` = `entity.entity_id == focus_id`, фокус устанавливается через `_handle_click`, но клик отключён (`and False`)
3. `entity.inferences` всегда пустой — `_build_perceived_scene` не заполняет это поле

**Исправление:**

**Шаг 1 — Восстановить клик по NPC:**
```python
# frontend/game_screen.py:634
# Было:
elif event.type == pygame.MOUSEBUTTONDOWN and False:

# Стало:
elif event.type == pygame.MOUSEBUTTONDOWN:
    clicked_npc = self._handle_click(
        event.pos, scene_state, focus, walls,
    )
    if clicked_npc:
        move.target_npc_id = clicked_npc
        move.direction = None
        text_input.clear()
        system_log.append(t("ui:going_to", npc=clicked_npc))
```

**Шаг 2 — Заполнять `inferences` в `_build_perceived_scene`:**
```python
# frontend/game_screen.py:42-106 — в цикле создания PerceivedEntity

import math

_px, _py = _player_xy(scene_state)
_perc = scene_state.get("player_perception") or {}

for npc_id, npc_data in scene_state.get("npc_positions", {}).items():
    if npc_id == "player":
        continue
    
    # ... существующий код создания entity ...
    
    # НОВОЕ: Заполнить inferences
    _inferences = []
    
    # Источник 1: embodied_traces (если backend шлёт)
    for _trace in _perc.get("embodied_traces") or []:
        if _trace.get("npc_id") == npc_id:
            if _trace.get("is_looking_at_player"):
                _inferences.append({
                    "inference_type": "communication",
                    "confidence": 0.8,
                    "description": "смотрит на игрока"
                })
    
    # Источник 2: proximity (fallback если traces пустые)
    if not _inferences:
        lp = npc_data.get("local_position") or {}
        if lp:
            _dist = math.hypot(lp.get("x", 0) - _px, lp.get("y", 0) - _py)
            if _dist < 5.0:  # NPC в радиусе 5м
                _is_frozen = next(
                    (t.get("is_frozen", False) for t in _perc.get("embodied_traces") or []
                     if t.get("npc_id") == npc_id),
                    False
                )
                if not _is_frozen:
                    _inferences.append({
                        "inference_type": "communication",
                        "confidence": 0.6,
                        "description": "внимание на игроке"
                    })
    
    entities.append(PerceivedEntity(
        # ... существующие поля ...
        inferences=_inferences,
    ))
```

**Шаг 3 — Проверить структуру PerceivedEntity.inferences:**
```python
# frontend/game_types.py — убедиться что inferences имеет правильный тип
# Если PerceivedEntity использует dataclass с типом List[Inference]:
@dataclass
class Inference:
    inference_type: str
    confidence: float
    description: str = ""

# В _build_perceived_scene:
from game_types import Inference
_inferences = [Inference(inference_type="communication", confidence=0.8, description="смотрит на игрока")]
```

**Проверка:**
1. Кликнуть по NPC — он должен стать focused (белый контур)
2. При наведении на NPC или близости (< 5м) — жёлтая линия со стрелкой от NPC к игроку

---

### BUG-P1-02: Logs не попадают в GitHub

**Файл:** `.gitignore`

**Симптом:** Папка `backend/logs/` пустая в репозитории (заархивирована в `logs.rar`).

**Исправление:**

**Шаг 1 — Обновить `.gitignore`:**
```gitignore
# Было:
*.log
*.jsonl
backend/data/logs/

# Стало:
# Runtime logs — kept for debugging, but ignore sensitive data
!backend/logs/
backend/logs/*.db
backend/logs/*.db-shm
backend/logs/*.db-wal
!backend/data/logs/
backend/data/logs/*.db
backend/data/logs/*.db-shm
backend/data/logs/*.db-wal
```

**Шаг 2 — Распаковать logs.rar:**
```bash
cd backend/
unrar x logs.rar
# или если unrar недоступен:
# 7z x logs.rar
```

**Шаг 3 — Создать .gitkeep для пустых папок:**
```bash
touch backend/logs/.gitkeep
touch backend/data/logs/.gitkeep
```

**Шаг 4 — Закоммитить:**
```bash
git add backend/logs/ backend/data/logs/ .gitignore
git commit -m "B.3: Include logs in Git repository (BUG-P1-02)"
```

**Проверка:**
1. `git status` показывает файлы в `backend/logs/`
2. `git log --oneline -1` показывает коммит
3. На GitHub файлы видны в репозитории

---

### BUG-P1-03: Дублирование констант в `constants.py`

**Файл:** `frontend/constants.py:87-207`

**Симптом:** Все цветовые константы (`COLOR_TEXT_*`, `RENDER_COLORS`, `AGGRESSION_COLORS`, `FONT_*`) определены дважды. Второе определение перекрывает первое.

**Исправление:**
```bash
# Удалить строки 148-207 (второй блок)
# Оставить первое определение (строки 82-145)
```

**Проверка:**
```bash
grep -c "COLOR_TEXT_DEFAULT" frontend/constants.py
# Должно вернуть 1
```

---

### BUG-P1-04: Дублирование `ENTITY_SPRITE_MAP`

**Файл:** `frontend/map_editor/sprite_registry.py:113-218`

**Симптом:** `ENTITY_SPRITE_MAP` и `get_entity_sprite` определены дважды.

**Исправление:**
```bash
# Удалить строки 168-218 (второй блок)
# Оставить первый блок (строки 113-166)
```

**Проверка:**
```bash
grep -c "ENTITY_SPRITE_MAP" frontend/map_editor/sprite_registry.py
# Должно вернуть 1 (определение) + 1 (использование в get_entity_sprite) = 2
```

---

### BUG-P1-05: `FallbackGateway.skip_time` вне тела класса

**Файл:** `frontend/api_client.py:525-535`

**Симптом:** Метод `skip_time` определён перед docstring класса, фактически вне тела класса. Не становится методом `FallbackGateway`.

**Исправление:** См. BUG-P0-04 Шаг 3.

---

### BUG-P1-06: Дубликат `confirmed_location_id`

**Файл:** `frontend/game_loop_bridge.py:51-53`

**Симптом:**
```python
confirmed_location_id: Optional[str] = None
# S82: Backend подтверждает spatial truth. Frontend reconciles при расхождении.
confirmed_location_id: Optional[str] = None
```

**Исправление:**
```python
# frontend/game_loop_bridge.py:51-53
# Удалить дубликат (строки 52-53)
# Оставить:
confirmed_location_id: Optional[str] = None
```

**Проверка:**
```bash
grep -c "confirmed_location_id" frontend/game_loop_bridge.py
# Должно вернуть 2 (определение + комментарий)
```

---

### BUG-P1-07: Парсер спикеров ломается на NPC без name

**Файл:** `frontend/game_screen.py:1062-1065`

**Симптом:** NPC без `name` и `display_name` не попадают в `known_names`, парсер не находит спикера.

**Исправление:**
```python
# frontend/game_screen.py:1062-1065
# Было:
for npc_id, npc_data in scene_state.get("npc_positions", {}).items():
    name = npc_data.get("name") or npc_data.get("display_name")
    if name:
        known_names[name.lower()] = name

# Стало:
from npc_name_resolver import npc_id_to_display
for npc_id, npc_data in scene_state.get("npc_positions", {}).items():
    if npc_id == "player":
        continue
    name = npc_data.get("name") or npc_data.get("display_name") or npc_id_to_display(npc_id)
    if name:
        known_names[name.lower()] = name
```

---

### BUG-P1-08: Парсер спикеров ломается на составных именах

**Файл:** `frontend/game_screen.py:1100-1106`

**Симптом:** `startswith` не находит "Торнин" в "Торнин Серебряная Луна".

**Исправление:**
```python
# frontend/game_screen.py:1100-1106
# Сортировать по длине (длинные первыми) + проверка первого слова

sorted_names = sorted(known_names.items(), key=lambda x: len(x[0]), reverse=True)
for name_lower, name_orig in sorted_names:
    if line_stripped.lower().startswith(name_lower):
        rest = line_stripped[len(name_orig):]
        if rest and rest[0] in (':', ',', '-'):
            speaker = name_orig
            text = rest.lstrip(':, - ').strip()
            break
    # Fallback: проверить первое слово
    first_word = line_stripped.lower().split()[0] if line_stripped else ""
    if first_word and len(first_word) >= 3 and first_word in name_lower:
        rest = line_stripped[len(first_word):]
        if rest and rest[0] in (':', ',', '-'):
            speaker = name_orig
            text = rest.lstrip(':, - ').strip()
            break
```

---

### BUG-P1-09: Эхо-фильтр слишком агрессивен

**Файл:** `frontend/game_screen.py:1086-1091`

**Симптом:** `similarity > 0.60` ложно отфильтровывает валидные ответы.

**Исправление:**
```python
# frontend/game_screen.py:1086-1091
# Было:
if similarity > 0.60:
    is_echo_line = True
elif not is_short_input and (p_clean in l_clean or l_clean in p_clean):
    is_echo_line = True

# Стало:
if similarity > 0.80:
    is_echo_line = True
elif p_clean == l_clean:
    is_echo_line = True
```

---

### BUG-P1-10: 4-я стена слишком агрессивна

**Файл:** `backend/app/services/verbalization/response_validator.py:109-114`

**Симптом:** "Старик смотрит на игроков в зале" → fallback (слово "игроков" слишком широко).

**Исправление:**
```python
# backend/app/services/verbalization/response_validator.py:109-114
import re

# Было:
_FOURTH_WALL_WORDS = ["игрок", "игроки", "симуляция", "система", "механика", "интерфейс"]

def _breaks_fourth_wall(self, text: str) -> bool:
    lower = text.lower()
    return any(word in lower for word in self._FOURTH_WALL_WORDS)

# Стало:
_FOURTH_WALL_PATTERNS = [
    r'\bигрок\b.*\b(должен|нажми|выбери|кликни|кнопк)',
    r'\bсимуляци\w*\b.*\b(остановлен|пауз|выключен)',
    r'\bмеханик\w*\b.*\b(игры|системы)',
    r'\bинтерфейс\w*\b',
    r'\b(ooc|out of character)\b',
]

def _breaks_fourth_wall(self, text: str) -> bool:
    lower = text.lower()
    return any(re.search(pattern, lower) for pattern in self._FOURTH_WALL_PATTERNS)
```

---

### BUG-P1-11: TEXTINPUT фильтрация WASD неполная

**Файл:** `frontend/game_screen.py:621-631`

**Симптом:** При русской раскладке WASD генерирует 'ц','ф','ы','в' — не фильтруются.

**Исправление:**
```python
# frontend/game_screen.py:621-631
# Было:
_WASD_KEY_TEXT = {pygame.K_w: 'w', pygame.K_a: 'a', pygame.K_s: 's', pygame.K_d: 'd'}

# Стало:
_WASD_KEY_TEXT = {
    pygame.K_w: ('w', 'ц'),
    pygame.K_a: ('a', 'ф'),
    pygame.K_s: ('s', 'ы'),
    pygame.K_d: ('d', 'в'),
}

# В проверке:
_skip = False
if held_keys and len(event.text) == 1:
    for k in held_keys:
        if event.text.lower() in _WASD_KEY_TEXT.get(k, ('',)):
            _skip = True
            break
```

---

### BUG-P1-12: `_draw_nodes()` никогда не вызывается

**Файл:** `frontend/map_editor/editor_core.py:2540-2573`

**Симптом:** Метод существует, но не вызывается. Навигационные узлы не отображаются.

**Исправление:**
```python
# frontend/map_editor/editor_core.py — в _draw_local() после _draw_walls()
def _draw_local(self):
    # ... существующий код ...
    
    # Стены
    if self.show_walls:
        self._draw_walls()
    
    # НОВОЕ: Навигационные узлы (если включены)
    self._draw_nodes()  # Добавить эту строку
    
    # Проходы
    self._draw_passages()
    # ...
```

---

### BUG-P1-13: `_show_view_menu()` вводит в заблуждение

**Файл:** `frontend/map_editor/editor_core.py:634`

**Симптом:** Метод просто переключает `show_grid`, не показывая меню.

**Исправление (вариант 1 — переименовать):**
```python
# Было:
def _show_view_menu(self):
    """Переключает видимость элементов"""
    self.show_grid = not self.show_grid
    self._show_toast(f"Сетка: {'вкл' if self.show_grid else 'выкл'}")

# Стало:
def _toggle_grid(self):
    """Переключает видимость сетки"""
    self.show_grid = not self.show_grid
    self._show_toast(f"Сетка: {'вкл' if self.show_grid else 'выкл'}")
```

**Исправление (вариант 2 — реализовать меню):**
```python
def _show_view_menu(self):
    """Показывает выпадающее меню View"""
    items = [
        {"label": f"Сетка: {'✓' if self.show_grid else '✗'}", "action": lambda: setattr(self, 'show_grid', not self.show_grid)},
        {"label": f"Стены: {'✓' if self.show_walls else '✗'}", "action": lambda: setattr(self, 'show_walls', not self.show_walls)},
        {"label": f"Объекты: {'✓' if self.show_objects else '✗'}", "action": lambda: setattr(self, 'show_objects', not self.show_objects)},
        {"label": f"Комнаты: {'✓' if self.show_rooms else '✗'}", "action": lambda: setattr(self, 'show_rooms', not self.show_rooms)},
    ]
    btn_rect = self.btn_view.rect
    self.dialog = DropDownMenu(btn_rect.x, btn_rect.bottom, items)
```

---

### BUG-P1-14: Мёртвый код `and False`

**Файл:** `frontend/game_screen.py:634`

**Симптом:** Клик по NPC отключён через `and False`.

**Исправление:** См. BUG-P1-01 Шаг 1 (убрать `and False`).

---

### BUG-P1-15: `PgUp/PgDn` не реализованы

**Файл:** `frontend/map_editor/editor_core.py`

**Симптом:** Статус-бар показывает `[PgUp/PgDn] Этаж`, но клавиши не работают.

**Исправление:**
```python
# frontend/map_editor/editor_core.py — в _handle_event, в блоке KEYDOWN
# Добавить после K_0:

elif event.key == pygame.K_PAGEUP:
    self.current_z = min(self.current_z + 1, 5)
    self._show_toast(f"Этаж: {self.current_z}")

elif event.key == pygame.K_PAGEDOWN:
    self.current_z = max(self.current_z - 1, -2)
    self._show_toast(f"Этаж: {self.current_z}")
```

---

### BUG-P1-16: `infect` без автофокуса

**Файл:** `frontend/text_input.py:148-180`

**Симптом:** Игрок может не видеть заражённый текст если поле не в фокусе.

**Исправление:**
```python
# frontend/text_input.py:148-180
def infect(self, impulse_text: str, origin_layer: str = "will_conflict") -> None:
    """Заражает поле ввода навязанным импульсом аватара."""
    self._is_possessed = True
    self._intrusive_text = impulse_text
    self._focused = True  # НОВОЕ: Автофокус чтобы игрок видел заражение
    self._rejection_flash_end = pygame.time.get_ticks() + 500
```

---

### BUG-P1-17: `_select_at` дублирует `_try_select_existing`

**Файл:** `frontend/map_editor/editor_core.py:1671-1732`

**Симптом:** Мёртвый код, нигде не вызывается.

**Исправление:**
```bash
# Удалить метод _select_at (строки 1671-1732)
# Он дублирует _try_select_existing без циклического выбора комнат
```

---

### BUG-P1-18: Хардкод кампании "Open_road"

**Файл:** `frontend/map_editor/editor_core.py:166-170`

**Симптом:** При запуске редактора автоматически открывается кампания "Open_road".

**Исправление:**
```python
# frontend/map_editor/editor_core.py:166-170
# Было:
ok, err = self.cm.open_campaign("Open_road")
if ok:
    self._show_toast("Кампания: Open_road")
else:
    self._show_toast("Добро пожаловать! Создайте кампанию через меню File")

# Стало:
# Не открывать кампанию автоматически — пусть пользователь выберет
self._show_toast("Добро пожаловать! Откройте кампанию через меню File")
```

---

## ЧАСТЬ 3. P2 — СРЕДНИЕ БАГИ

> Для P2 багов приведены краткие исправления. Полный контекст — в анализе.

### BUG-P2-01: Дубликат `self.current_z` в `_copy_selection`
**Файл:** `editor_core.py:852-853`
**Исправление:** Удалить обе строки `self.current_z: int = 0`.

### BUG-P2-02: Шрифт создаётся в цикле
**Файл:** `scene_renderer.py:473`
**Исправление:** Добавить в `__init__`: `self.font_tooltip = pygame.font.SysFont(FONT_NAME_UI, FONT_SIZE_TOOLTIP)`, использовать `self.font_tooltip` вместо `pygame.font.SysFont(...)`.

### BUG-P2-03: `format_world_date` каждый кадр
**Файл:** `game_screen.py:1371-1374`
**Исправление:**
```python
# В __init__:
self._cached_time_str = ""
self._cached_time_seconds = -1

# В рендере:
if self.game_time_seconds != self._cached_time_seconds:
    self._cached_time_str = format_world_date(self.game_time_seconds)
    self._cached_time_seconds = self.game_time_seconds
time_surf = self.renderer.font_small.render(self._cached_time_str, True, COLOR_TEXT_MUTED)
```

### BUG-P2-04: Мёртвый код после `return`
**Файл:** `api_client.py:437-441`
**Исправление:** Перенести диагностику до `return` или удалить.

### BUG-P2-05, P2-06: Реализация в Protocol
**Файл:** `api_client.py:103-105, 121-125`
**Исправление:** Заменить тело на `...` (ellipsis).

### BUG-P2-07: `_time_scale` не используется
**Файл:** `game_screen.py:495`
**Исправление:** Удалить переменную или реализовать переключение.

### BUG-P2-08: `walk_distance_accumulated` без эффекта
**Файл:** `game_screen.py:730-739`
**Исправление:** Удалить как мёртвый код.

### BUG-P2-09: `_prev_npc_positions` не очищается при смене локации
**Файл:** `scene_renderer.py:41`
**Исправление:**
```python
def __init__(self, screen):
    # ...
    self._last_location_id = None

def render(self, scene, ...):
    if scene.location_id != self._last_location_id:
        self._prev_npc_positions.clear()
        self._last_location_id = scene.location_id
```

### BUG-P2-10: `npc_speech_bubbles` не очищается при выходе
**Файл:** `game_screen.py:367`
**Исправление:** В обработчике ESC:
```python
if event.key == pygame.K_ESCAPE:
    self.npc_speech_bubbles.clear()
    self.player_speech_bubble = None
    self.npc_manifest_indicators.clear()
    action_queue.stop()
    running = False
    return
```

### BUG-P2-11: Дубликат проверки cache
**Файл:** `life_engine.py:596-603`
**Исправление:** Удалить второй блок (строки 597-603).

### BUG-P2-12: J/О конфликтует с TEXTINPUT
**Файл:** `game_screen.py:546`
**Исправление:** Убрать `event.unicode == 'о'`, оставить только `event.key == pygame.K_j`.

### BUG-P2-13: `save_scene_state` блокирует основной цикл
**Файл:** `game_screen.py:881-884`
**Исправление:**
```python
def _save_async():
    try:
        _gateway.save_scene_state(campaign_folder, scene_state)
    except Exception as e:
        logger.warning(f"save_scene_state failed: {e}")

# В основном цикле:
if (_now - _last_idle_tick >= _tick_interval and ...):
    threading.Thread(target=_save_async, daemon=True).start()
    # ...
```

### BUG-P2-14: `BODY_STATE_HEALTHY` для всех NPC
**Файл:** `game_loop/__init__.py:496-501`
**Исправление:** Проверять persistence перед инъекцией HEALTHY.

### BUG-P2-15: `PerceptionConfig` с хардкод-значениями
**Файл:** `game_screen.py:1191-1196`
**Исправление:**
```python
_av = scene_state.get("avatar_state", {})
_hp = _av.get("hp", 100)
_max_hp = _av.get("max_hp", 100)
_stress = _av.get("stress", 10.0)
config = PerceptionConfig(
    player_focus=focus,
    player_stress=_stress,
    player_hp=_hp,
    player_max_hp=_max_hp,
)
```

### BUG-P2-16: `_build_perceived_scene` каждый кадр
**Файл:** `game_screen.py:1197`
**Исправление:** Кэшировать с хэшем scene_state.

---

## ЧАСТЬ 4. P3 — НИЗКИЕ БАГИ (DEBUG SPAM)

### BUG-P3-01 — P3-06: Заменить print на logger

**Файлы и строки:**
- `tick_orchestrator.py:428` — `print(f"[DEBUG_TICK_ORCH]...")`
- `life_engine.py:1296` — `if npc_id == "guard_borko": print(...)`
- `game_screen.py:766` — `print(f"[FRAME_RENDER]...")`
- `game_screen.py:787` — `print(f"[TICK_SYNC]...")`
- `game_screen.py:917` — `print(f"[TRACE][ACTION_RESP]...")`
- `game_screen.py:862` — `print(f"[TELEGRAPH]...")`
- `game_screen.py:997-1004` — `print(f"[PIPELINE][MOVEMENT]...")`
- `game_loop/__init__.py:856` — `print(f"[TRAV_CHECK_P2]...")`
- `game_loop/__init__.py:967` — `print(f"[DIAG_MERGE]...")`
- `game_screen.py:1228` — `self.screen.fill((200, 0, 0))`
- `integration.py:56,75` — `logger.warning` на хот-пути

**Исправление (шаблон):**
```python
# Было:
print(f"[FRAME_RENDER] npc={npc_id} new_xy=({_new_lp.get('x')}, {_new_lp.get('y')})")

# Стало:
logger.debug(f"[FRAME_RENDER] npc={npc_id} new_xy=({_new_lp.get('x')}, {_new_lp.get('y')})")
```

**Для red fill:**
```python
# game_screen.py:1228 — УДАЛИТЬ строку
# self.screen.fill((200, 0, 0))  # ЯРКО-КРАСНЫЙ — debug ассерт
```

**Для logger.warning на хот-пути:**
```python
# integration.py:56,75
# Было: logger.warning(...)
# Стало: logger.debug(...)
```

---

### BUG-P3-07: Хардкод `duration_ticks=2`

**Файл:** `backend/app/services/phases/post_decision.py:117`

**Исправление:**
```python
# Было:
duration_ticks=2,

# Стало (вынести в конфиг оружия или NPC):
def _get_attack_duration(intent) -> int:
    """Длительность подготовки атаки в тиках."""
    _weapon = getattr(intent, 'weapon', None)
    if _weapon == "dagger":
        return 1
    elif _weapon == "two_handed":
        return 4
    return 2  # default

duration_ticks=_get_attack_duration(intent),
```

---

### BUG-P3-08: `move.target_npc_id` сбрасывается после submit

**Файл:** `game_screen.py:665-668`

**Исправление:**
```python
# Сохранять цель до подтверждения от backend
if move.target_npc_id and move.target_npc_id in npc_positions:
    move.pending_target = move.target_npc_id
    action_queue.submit(campaign_folder, player_name, f"подойти к {name}", ...)
    move.target_npc_id = None

# В обработке результата: если ошибка — восстановить
if result.error and move.pending_target:
    move.target_npc_id = move.pending_target
    move.pending_target = None
    system_log.append(f"[!] Не удалось подойти: {result.error}")
```

---

### BUG-P3-09: Фильтр `resp != "Ничего не произошло"` хрупкий

**Файл:** `game_screen.py:1050`

**Исправление:**
```python
# Было:
if resp and resp != t("ui:nothing_happened"):

# Стало:
_resp_norm = resp.strip().rstrip('.').lower()
_nothing_norm = t("ui:nothing_happened").strip().rstrip('.').lower()
if resp and _resp_norm != _nothing_norm:
```

---

### BUG-P3-10: `_idle_tick_result` как list

**Файл:** `game_screen.py:488`

**Исправление:**
```python
import threading

_idle_tick_result = None
_idle_tick_lock = threading.Lock()

# В _do_idle_tick:
with _idle_tick_lock:
    _idle_tick_result = result

# В main loop:
with _idle_tick_lock:
    if _idle_tick_result:
        _tick_data = _idle_tick_result
        _idle_tick_result = None
    else:
        _tick_data = {}
```

---

### BUG-P3-11: `_w2s` не использует zoom

**Файл:** `scene_renderer.py:179`

**Исправление:** Документировать (камера всегда без zoom) или добавить zoom параметр.

---

### BUG-P3-12: Приоритет NPC перед стенами

**Файл:** `editor_core.py:1610-1618`

**Исправление:**
```python
# Проверяем NPC только если не зажат Alt
if not (pygame.key.get_mods() & pygame.KMOD_ALT):
    for npc in loc.get("npcs", []):
        # ... проверка NPC
```

---

## ЧАСТЬ 5. ПОРЯДОК ИСПОЛНЕНИЯ

### Этап 1 — P0 (3-4 сессии)

1. BUG-P0-10 — NameError в dm_agent (1 минута)
2. BUG-P0-09 — NameError в data_manager (1 минута)
3. BUG-P0-08 — QUIT-баг в редакторе (1 минута)
4. BUG-P0-07 — Баг в _point_near_line (1 минута)
5. BUG-P0-11 — Hex-цвет в pygame.draw.circle (1 минута)
6. BUG-P0-12 — Body state позиция (1 минута)
7. BUG-P0-01 — Время застывает (30 минут)
8. BUG-P0-04 — Кнопки промотки времени (30 минут)
9. BUG-P0-03 — "Подойди ко мне" (1 час)
10. BUG-P0-02 — NPC не двигаются (1 час)
11. BUG-P0-06 — NPC телепортируются (30 минут)
12. BUG-P0-05 — Дублирование текста LLM (1 час)

### Этап 2 — P1 (3-4 сессии)

13. BUG-P1-02 — Logs в Git (15 минут)
14. BUG-P1-03 — Дублирование констант (5 минут)
15. BUG-P1-04 — Дублирование ENTITY_SPRITE_MAP (5 минут)
16. BUG-P1-05 — FallbackGateway.skip_time (в P0-04)
17. BUG-P1-06 — Дубликат confirmed_location_id (1 минута)
18. BUG-P1-01 — Направление взгляда (1 час)
19. BUG-P1-07, P1-08, P1-09 — Парсер спикеров (30 минут)
20. BUG-P1-10 — 4-я стена (15 минут)
21. BUG-P1-11 — TEXTINPUT фильтрация (15 минут)
22. BUG-P1-12 — _draw_nodes (5 минут)
23. BUG-P1-13 — _show_view_menu (15 минут)
24. BUG-P1-14 — Мёртвый код (в P1-01)
25. BUG-P1-15 — PgUp/PgDn (5 минут)
26. BUG-P1-16 — infect автофокус (5 минут)
27. BUG-P1-17 — _select_at (5 минут)
28. BUG-P1-18 — Хардкод Open_road (5 минут)

### Этап 3 — P2 (2-3 сессии)

29. BUG-P2-01 — P2-16 (по 5-15 минут каждый)

### Этап 4 — P3 (1-2 сессии)

30. BUG-P3-01 — P3-06 — print → logger (30 минут)
31. BUG-P3-07 — P3-12 (по 5-15 минут каждый)

---

## ЧАСТЬ 6. КРИТЕРИИ ПРИЁМКИ

После завершения всех этапов:

### P0 (критические — игра работает):
- [ ] Время идёт: 60 idle_tick → +60 минут игрового времени
- [ ] Кнопки 1–4 проматывают время
- [ ] "Подойди ко мне" двигает ближайшего NPC к игроку
- [ ] NPC плавно движутся (без скачков > 3м за кадр)
- [ ] DM ответ не содержит `(whisper)`, `[internal]`, `*thought*`
- [ ] NPC речь только в облачке, не в message_log
- [ ] Клик по стене в редакторе выделяет стену
- [ ] Закрытие редактора через крестик завершает процесс
- [ ] Проходы (двери, окна) рисуются в редакторе
- [ ] Body state виден в нижнем левом углу

### P1 (высокие — UX):
- [ ] Направление взгляда работает (жёлтая линия от NPC к игроку)
- [ ] Logs коммитятся в Git
- [ ] Нет дублирования констант
- [ ] skip_time работает во всех gateway
- [ ] Парсер находит NPC по частичному имени
- [ ] Эхо-фильтр не отсеивает валидные ответы
- [ ] Русская раскладка WASD фильтруется
- [ ] Навигационные узлы видны в редакторе
- [ ] PgUp/PgDn меняют этаж
- [ ] infect автофокусирует поле ввода

### P2 (средние — производительность):
- [ ] Шрифты кэшируются
- [ ] format_world_date кэшируется
- [ ] save_scene_state в отдельном потоке
- [ ] _build_perceived_scene кэшируется
- [ ] Нет мёртвого кода после return

### P3 (низкие — полировка):
- [ ] Нет print spam в stdout при игре
- [ ] Нет красного fill debug
- [ ] Нет logger.warning на хот-путях
- [ ] duration_ticks зависит от оружия

---

## ЧАСТЬ 7. ПРОВЕРОЧНЫЕ СЦЕНАРИИ

### Сценарий 1: Базовый gameplay
1. Запустить игру: `python game_launcher.py`
2. Выбрать "Новая игра" → кампания → персонаж
3. **Проверка времени:** Подождать 30 секунд → время должно измениться
4. **Проверка NPC:** NPC должны перемещаться по таверне
5. **Проверка диалога:** Ввести "привет" → DM ответ без английских маркеров
6. **Проверка промотки:** Нажать `1` → время должно прыгнуть на 10 минут

### Сценарий 2: Команды движения
1. Ввести "подойди ко мне" → ближайший NPC должен подойти
2. Ввести "торнин подойди" → Торнин должен подойти
3. NPC должен двигаться плавно (не телепортироваться)

### Сценарий 3: Редактор карт
1. Открыть редактор: Menu → "Редактор карт"
2. Кликнуть по стене → должна выделиться
3. Создать проход → должен нарисоваться (жёлтый круг)
4. Нажать PgUp → этаж должен измениться
5. Закрыть окно через крестик → процесс должен завершиться

### Сценарий 4: Направление взгляда
1. Кликнуть по NPC → он должен стать focused (белый контур)
2. Жёлтая линия со стрелкой должна идти от NPC к игроку
3. При удалении NPC > 5м — линия должна исчезнуть

### Сценарий 5: Logs в Git
1. `git status` → файлы в `backend/logs/` видны
2. `git log --oneline -1` → коммит "B.3: Include logs" присутствует
3. На GitHub файлы видны в репозитории

---

## ЧАСТЬ 8. ОТКАТ ИЗМЕНЕНИЙ

Если исправление вызывает регрессию:

1. **Git revert:** `git revert <commit-hash>`
2. **Проверка:** запустить тесты `pytest backend/tests/`
3. **Лог:** записать в `reports/` причину отката
4. **Альтернатива:** реализовать минимальный фикс вместо полного исправления

---

## ЧАСТЬ 9. СВЯЗАННЫЕ ДОКУМЕНТЫ

- `docs/Диаграммы игры/TZ-INFRA-1.md` — Реестр всех багов (v2.0)
- `docs/audits/ADR-DRIFT-D` — Causal Drift D
- `docs/audits/ADR-LEGACY-IMPACT.md` — Legacy inventory
- `docs/QUICKSTART.md` — Архитектурный QUICKSTART
- `docs/Tasks/ТЗ/03_KNOWN_ISSUES_AND_BUGS.md` — Баг-реестр
- `reports/LAST_SESSION.md` — Текущее состояние симуляции

---

**FIX_GUIDE v1.0 готов к исполнению.**

**Порядок:** Этап 1 (P0) → Этап 2 (P1) → Этап 3 (P2) → Этап 4 (P3)

**После каждого бага:** commit на named branch, проверка по критериям.

**Итого:** ~58 багов, ~10-15 сессий полного исполнения.
