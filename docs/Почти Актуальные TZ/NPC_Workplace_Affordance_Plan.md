# План: Действия NPC привязаны к точке мира

**Дата:** 2026-07-18  
**Проблема:** Действия NPC не связаны с их физической позицией в мире. Люся "протирает столы", но стоит у стойки и разговаривает. Борко "охраняет ворота", но пьёт в углу таверны. Тень должна быть "в тёмном углу", но часто стоит не там.

**Связь с ADR-O-323 / ADR-O-324:** Эти ADR **не решают проблему**. Они решают архитектурную гигиену (один автор traversal, геометрия стен), но не "семантическую привязку действия к точке мира". ADR-O-324 даже **усугубляет** видимость проблемы: если у NPC activity_map указывает на `corner_table`, а между ним и corner_table стена, MovementPlanner вернёт `GEOMETRIC_OBSTACLE` и NPC **вообще останется на месте**.

---

## 1. КОРНЕВАЯ ПРИЧИНА

В коде **уже есть** три слоя для связи "действие → точка мира", но они **несогласованы и содержат противоречия**:

### Слой A: `activity_map` (data-driven, в JSON NPC)

**Расположение:** `config/npc/individuals/*.json` → `activity_map`

**Пример (Люся):**
```json
"activity_map": {
  "working": {
    "location": "tavern_silver_wolf",
    "position": "bar_area",          // ⚠️ противоречит display
    "display": "serving_tables"       // ⚠️ "обслуживает столы"
  }
}
```

**Проблема:** `position="bar_area"` — это узел "У стойки". `display="serving_tables"` — это "обслуживает столы". NPC идёт к стойке, а потом фронтенд пишет "обслуживает столы". Игрок видит: стоит у бара, говорит, что протирает столы.

### Слой B: `_ACTIVITY_TO_ROLE_MAP` (хардкод в life_engine.py)

**Расположение:** `backend/app/services/npc/life_engine.py:2312-2327`

```python
_ACTIVITY_TO_ROLE_MAP = {
  "drinking": NodeRole.BAR,
  "serving_tables": NodeRole.BAR,        # ⚠️ обслуживание столов → бар?!
  "cleaning_tables": NodeRole.TABLE,
  "sleeping": NodeRole.BED,
  "working": NodeRole.WORKBENCH,
  "guarding_gate": NodeRole.ENTRANCE,
  ...
}
```

**Проблемы:**
1. `serving_tables` → `BAR`. Служанка идёт к стойке, не к столам
2. `cleaning_tables` → `TABLE`. К какому столу? Если в локации 3 стола, она выбирает **первый попавшийся** (через `resolve_node(role)` без указания origin_zone)
3. `guarding_gate` → `ENTRANCE`. Но `ENTRANCE` маппится на любой вход. В `city_gate` это узел `entrance` (Вход с площади), а не `guard_post` (Караульня). Борко идёт стоять у входа, как вышибала, а не в караульню
4. Нет `patrolling` (патруль — это **маршрут**, не точка)
5. Нет `dark_corner` для Тени — `observing` → `TABLE`, т.е. она идёт к "столу", а не к "тёмному углу"

### Слой C: `npc_defaults` (хардкод в scene_state_manager.py)

**Расположение:** `backend/app/services/scene_state_manager.py:983-1008`

Стартовые позиции NPC — отдельный хардкод, не связанный с `activity_map`:
```python
"maid_lusya": {"position": "bar_area", "activity": "serving_tables"},
"tavern_keeper_tornin": {"position": "behind_bar", "activity": "cleaning_tables"},
"guard_borko": {"position": "corner_table", "activity": "drinking"},
"thief_shadow": {"position": "corner_table", "activity": "observing"},
```

**Проблема:** Стартовое состояние NPC задаётся хардкодом, который **может противоречить** их `activity_map`. Тavern_keeper_tornin стартует `behind_bar` (за стойкой) с activity `cleaning_tables` (протирает столы) — он стоит за стойкой и "протирает столы"?

### Слой D: `role_resolver` (вывод NodeRole из label)

**Расположение:** `backend/app/services/spatial/role_resolver.py`

Маппит label/type узла к NodeRole. Хорошая идея, но **не использует теги**. Узел `corner_table` с label "В тёмном углу" не получает роль `DARK_CORNER`, а получает `TABLE` (по подстроке "стол" в node_id). Узел `guard_post` с label "Караульня" не получает роль `GUARD_POST`, а попадает в `DEFAULT`.

### Слой E: Расписание (`routine.schedule`)

**Расположение:** `config/npc/individuals/*.json` → `routine.schedule`

```json
"schedule": {"08:00-22:00": "drinking", "22:00-08:00": "sleeping"}
```

**Проблема у Борко:** Расписание `"drinking"` 14 часов в сутки. `working`/`guarding_gate`/`on_duty` есть в `activity_map`, но **никогда не активируются** — schedule их не вызывает. Борко всегда пьяный в таверне.

---

## 2. ПОЧЕМУ ADR-O-323/324 НЕ РЕШАЮТ ЭТО

| Что делают ADR-O-323/324 | Что нужно пользователю |
|---|---|
| MovementPlanner — единый автор TraversalProposal | ✅ Нужен, но это транспорт. Куда идти — решает не MovementPlanner |
| EventCompiler валидирует source/target по node_id | ✅ Полезно, но не влияет на выбор точки |
| GraphCompiler извлекает spatial_walls / obstacles | ✅ Полезно для GEOMETRIC_OBSTACLE, но не для "куда идти" |
| SpatialService.is_segment_blocked(A, B) | ✅ Полезно, но не отвечает на "где стоит NPC во время работы" |

**Вывод:** ADR-O-323/324 — это **транспортный слой**. Они гарантируют, что если NPC решил идти к столу, он дойдёт и не пройдёт сквозь стену. Но **"к какому столу идти"** — это слой выше, который они не затрагивают. Эта работа осталась несделанной.

**Дополнительно:** ADR-O-324 сейчас **видимо ухудшает** ситуацию. Раньше NPC "телепортировались" к точке (DRIFT), а теперь они **остаются на месте** (GEOMETRIC_OBSTACLE → REJECTED → no-op). Если `activity_map` Люси указывает на `bar_area`, а между ней и `bar_area` стена, MovementPlanner отклонит путь, и Люся останется там, где стоит, продолжая "обслуживать столы".

---

## 3. КОНКРЕТНЫЙ ПЛАН ИСПРАВЛЕНИЯ

### Шаг 1: Ввести NodeRole для **рабочих точек** (а не только тип мебели)

**Файл:** `backend/app/models/spatial_contracts.py` — расширить enum `NodeRole`:

```python
class NodeRole(str, Enum):
    # Существующие
    DEFAULT = "default"
    ENTRANCE = "entrance"
    TRANSITION = "transition"
    BAR = "bar"
    BED = "bed"
    TABLE = "table"
    WORKBENCH = "workbench"
    MARKET = "market"
    
    # НОВЫЕ — функциональные роли (рабочие станции)
    GUARD_POST = "guard_post"           # Караульня (где стоит стражник на дежурстве)
    DARK_CORNER = "dark_corner"         # Тёмный угол (где прячется вор)
    PATROL_ROUTE = "patrol_route"       # Маршрут патруля (набор узлов)
    SERVING_STATION = "serving_station" # Точка обслуживания (где служанка раздаёт еду)
    KITCHEN_COUNTER = "kitchen_counter" # Кухонная стойка (где готовят/протирают)
    INN_DESK = "inn_desk"               # Стойка трактирщика (где встречают гостей)
```

**Файл:** `backend/app/services/spatial/role_resolver.py` — расширить keyword matching:

```python
NodeRole.GUARD_POST: {"караульн", "guard_post", "пост", "сторож", "watch"},
NodeRole.DARK_CORNER: {"тёмн", "темн", "угол", "dark", "corner_dark", "shadow"},
NodeRole.SERVING_STATION: {"раздаточ", "serving", "serving_station"},
NodeRole.KITCHEN_COUNTER: {"кухн", "kitchen", "разделоч"},
NodeRole.INN_DESK: {"стойк", "бар", "стойка трактирщика", "reception"},
```

**Важно:** `bar` сейчас маппится на `BAR`, что приводит к конфликтам (трактирщик, служанка и пьющие все идут к `bar_area`). Нужно разделить:
- `behind_bar` → `INN_DESK` (рабочее место трактирщика)
- `bar_area` → `BAR` (где пьют гости)
- `serving_station` → `SERVING_STATION` (где служанка берёт подносы)

### Шаг 2: Ввести **Workplace** как отдельный концепт в графе локации

**Файл:** `frontend/map_editor/campaigns/*/locations/*.json` — помечать узлы тегами:

```json
"nodes": {
  "guard_post": {
    "label": "Караульня",
    "x": 5.0, "y": 3.0,
    "tags": ["workplace:guard", "workplace:borko"]   // ← НОВОЕ
  },
  "corner_table": {
    "label": "В тёмном углу",
    "x": 6.0, "y": 3.0,
    "tags": ["workplace:thief", "dark_corner", "isolated"]  // ← НОВОЕ
  },
  "behind_bar": {
    "label": "За стойкой",
    "x": 4.0, "y": 4.0,
    "tags": ["workplace:tavern_keeper", "inn_desk"]
  },
  "kitchen_counter": {
    "label": "Раздаточная",
    "x": 3.5, "y": 2.5,
    "tags": ["workplace:maid", "serving_station"]
  },
  "right_table": {
    "label": "За правым столом",
    "x": 5.5, "y": 5.0,
    "tags": ["table", "cleanable"]   // ← NPC могут приходить сюда убирать
  }
}
```

**В `role_resolver.py`** — приоритет tags над keywords:

```python
def resolve_role(node_label, editor_type, editor_tags=None, ...):
    # 0. НОВЫЙ ПРИОРИТЕТ: editor_tags — явно указанные рабочие точки
    if editor_tags:
        for tag in editor_tags:
            if tag in _TAG_ROLE_MAP:           # "workplace:guard" → GUARD_POST
                return _TAG_ROLE_MAP[tag]
            if tag.startswith("workplace:"):
                # Любой workplace:XXX → GUARD_POST-семейство
                return _WORKPLACE_ROLE_MAP.get(tag, NodeRole.DEFAULT)
    # ... остальное как было
```

### Шаг 3: Исправить `activity_map` в JSON NPC

**Файлы:** `config/npc/individuals/*.json`

**Люся (`lusya.json`):**
```json
"activity_map": {
  "working": {
    "location": "tavern_silver_wolf",
    "position": "kitchen_counter",   // ← было "bar_area"
    "display": "serving_tables"
  },
  "cleaning_tables": {                // ← НОВАЯ активность
    "location": "tavern_silver_wolf",
    "position": "right_table",         // ← конкретный стол
    "display": "cleaning_tables"
  },
  ...
}
```

**Борко (`borko.json`):**
```json
"routine": {
  "schedule": {
    "08:00-12:00": "guarding_gate",   // ← УТРОМ — на воротах
    "12:00-14:00": "eating",
    "14:00-20:00": "guarding_gate",   // ← ДНЁМ — на воротах
    "20:00-22:00": "drinking",        // ← ВЕЧЕРОМ — пьёт в таверне
    "22:00-08:00": "sleeping"
  }
},
"activity_map": {
  "guarding_gate": {
    "location": "city_gate",
    "position": "guard_post",          // ← было "entrance"
    "display": "guarding_gate"
  },
  "drinking": {
    "location": "tavern_silver_wolf",
    "position": "bar_area",
    "display": "drinking"
  },
  "sleeping": {
    "location": "city_gate",           // ← спит в караульне, не в таверне
    "position": "guard_post",
    "display": "sleeping"
  }
}
```

**Тень (`shadow.json`):**
```json
"activity_map": {
  "observing": {
    "location": "tavern_silver_wolf",
    "position": "corner_table",        // ← уже верно, но узел нужно пометить
    "display": "observing"
  }
}
```

Узел `corner_table` в JSON локации:
```json
"corner_table": {
  "label": "В тёмном углу",
  "x": 6.0, "y": 3.0,
  "tags": ["workplace:thief", "dark_corner"]
}
```

### Шаг 4: Расширить `_ACTIVITY_TO_ROLE_MAP` в life_engine.py

**Файл:** `backend/app/services/npc/life_engine.py:2312-2327`

```python
_ACTIVITY_TO_ROLE_MAP = {
  # Питьё/еда — социальные точки
  "drinking": NodeRole.BAR,
  "eating": NodeRole.TABLE,
  
  # Рабочие точки (конкретные)
  "serving_tables": NodeRole.SERVING_STATION,    # ← было BAR
  "cleaning_tables": NodeRole.TABLE,             # но с указанием origin_zone
  "guarding_gate": NodeRole.GUARD_POST,          # ← было ENTRANCE
  "observing": NodeRole.DARK_CORNER,             # ← было TABLE
  "innkeeping": NodeRole.INN_DESK,               # для трактирщика
  
  # Базовые
  "sleeping": NodeRole.BED,
  "resting": NodeRole.BED,
  "working": NodeRole.WORKBENCH,
  "haggling": NodeRole.MARKET,
  ...
}
```

### Шаг 5: Удалить хардкод `npc_defaults` в scene_state_manager.py

**Файл:** `backend/app/services/scene_state_manager.py:983-1008`

**Сейчас:** стартовые позиции NPC хардкожены, могут противоречить `activity_map`.  
**Нужно:** инициализировать стартовые позиции **из `activity_map`** по первому слоту schedule:

```python
def _initial_npc_position(npc_data: dict) -> tuple[str, str, str]:
    """Возвращает (location, position, activity) для старта NPC.
    
    Источник истины — npc_data["activity_map"][first_schedule_activity].
    Хардкод npc_defaults удалён (ADR-XXX).
    """
    schedule = npc_data.get("routine", {}).get("schedule", {})
    activity_map = npc_data.get("activity_map", {})
    
    # Берём первую активность из schedule
    if schedule and activity_map:
        first_activity = next(iter(schedule.values()))
        entry = activity_map.get(first_activity)
        if entry:
            return entry["location"], entry["position"], entry["display"]
    
    # Fallback: первая запись в activity_map
    if activity_map:
        first = next(iter(activity_map.values()))
        return first["location"], first["position"], first["display"]
    
    return "tavern_silver_wolf", "main_hall", "idle"
```

### Шаг 6: Ввести **PatrolRoute** для патрулирующих NPC

Сейчас `guarding_gate` — статическая точка. Но стражник должен **ходить по маршруту**. Нужно:

**В JSON локации:**
```json
"patrol_routes": {
  "city_gate_perimeter": {
    "nodes": ["entrance", "gate_arch", "guard_post", "gate_courtyard"],
    "cycle": true
  }
}
```

**В JSON NPC:**
```json
"activity_map": {
  "patrolling": {
    "location": "city_gate",
    "position": "patrol:city_gate_perimeter",   // ← префикс patrol: указывает на маршрут
    "display": "patrolling"
  }
}
```

**В `life_engine._resolve_position`:**
- Если `position` начинается с `patrol:`, взять следующий узел из маршрута (по индексу тика)
- Создавать `MacroMovementGoal` к следующему узлу маршрута

### Шаг 7: SpatialService.resolve_node должен уважать **npc_id**

Сейчас `resolve_node(role=TABLE, origin_zone=...)` возвращает **любой** стол. Нужно:

**В `SpatialService`:**
```python
def resolve_workplace(self, npc_id: str, activity: str, location_id: str) -> Optional[NodeRef]:
    """Возвращает конкретное рабочее место NPC.
    
    1. Ищет узлы с tag=f"workplace:{npc_id}" в location_id
    2. Если не найдено — fallback на _ACTIVITY_TO_ROLE_MAP
    3. Если не найдено — NodeRole.DEFAULT
    """
    # 1. Поиск по tag
    for node_id, ref in self._graph.items():
        tags = getattr(ref, "tags", []) or []
        if f"workplace:{npc_id}" in tags:
            return ref
    
    # 2. Fallback на роль
    role = _ACTIVITY_TO_ROLE_MAP.get(activity, NodeRole.DEFAULT)
    return self.resolve_node(role=role, origin_zone=location_id)
```

### Шаг 8: Проверить, что NPC **не блокируется** ADR-O-324 у своей рабочей точки

**Проблема:** Если `activity_map` указывает на узел через стену, MovementPlanner вернёт `GEOMETRIC_OBSTACLE`, и NPC останется на месте.

**Решение:** MovementPlanner должен использовать `find_path` (A* по графу) — это **уже реализовано** в `movement_engine.py:72-94`. Главное условие: **граф локации должен содержать валидные passages**, обходящие стены.

**Проверить:** в JSON локации `tavern.json` должны быть passages между всеми рабочими узлами. Сейчас в `tavern_silver_wolf.json` passages есть, но в `Open_road/locations/tavern.json` нужно проверить, что passages соответствуют дверным проёмам в стенах.

---

## 4. ADR-O-326 — РЕГИСТРАЦИЯ ПЛАНА В РЕЕСТРЕ

**Новый ADR:** `ADR-O-326` [ONTO] **Workplace Affordance Contract** — каждый узел графа локации может быть помечен тегом `workplace:<npc_id>` или `workplace:<role>`. LifeEngine резолвит рабочую точку NPC через:

1. `npc.activity_map[activity].position` (data-driven, приоритет 1)
2. `SpatialService.resolve_workplace(npc_id, activity, location_id)` (по тегу)
3. `_ACTIVITY_TO_ROLE_MAP` (семантический fallback)
4. `NodeRole.DEFAULT` (последний шанс)
5. Текущая позиция (no-op)

**Taboo:**
- ❌ Хардкод `npc_defaults` в `scene_state_manager.py`
- ❌ `serving_tables` → `NodeRole.BAR` (это противоречие — обслуживает столы, идёт к бару)
- ❌ `guarding_gate` → `NodeRole.ENTRANCE` (стражник не стоит у входа, он в караульне)
- ❌ Расписание, не вызывающее `working`/`guarding_gate` (Борко пьёт 14 часов)
- ❌ Противоречие `position` и `display` (стоит у стойки, "протирает столы")

**Files:**
- `backend/app/models/spatial_contracts.py` — расширить NodeRole
- `backend/app/services/spatial/role_resolver.py` — приоритет tags
- `backend/app/services/spatial/spatial_service.py` — `resolve_workplace`
- `backend/app/services/npc/life_engine.py:2312-2327` — исправить _ACTIVITY_TO_ROLE_MAP
- `backend/app/services/scene_state_manager.py:983-1008` — удалить хардкод
- `config/npc/individuals/*.json` — исправить activity_map
- `frontend/map_editor/campaigns/*/locations/*.json` — добавить tags к узлам

---

## 5. ОЧЕРЁДНОСТЬ И ОБЪЁМ РАБОТЫ

| Шаг | Объём | Критичность |
|---|---|---|
| 1. NodeRole + role_resolver | 1 час | Высокая |
| 2. tags в JSON локаций (5 узлов) | 30 мин | Высокая |
| 3. activity_map в JSON NPC (5 NPC) | 30 мин | Высокая |
| 4. _ACTIVITY_TO_ROLE_MAP | 15 мин | Высокая |
| 5. Удалить npc_defaults хардкод | 30 мин | Средняя (легаси) |
| 6. resolve_workplace в SpatialService | 1 час | Высокая |
| 7. PatrolRoute (опционально) | 2 часа | Низкая (патруль — фича, не фикс) |
| 8. Тесты | 2 часа | Высокая |

**Итого:** ~8 часов работы для базового решения (шаги 1-6 + 8), ~10 часов с патрулём.

---

## 6. ЧТО ДАДУТ ADR-O-323/324 ПОСЛЕ ЭТОГО ПЛАНА

После реализации Workplace Affordance:

- **ADR-O-323** (MovementPlanner — единый автор TraversalProposal) останется **полезным**: он строит маршрут к рабочей точке, валидирует геометрию, авторизует перемещение
- **ADR-O-324** (Geometric Obstacle Resolution) **станет критичным**: NPC будет ходить к `guard_post` через коридоры, а не сквозь стены. Сейчас это создаёт `GEOMETRIC_OBSTACLE` REJECTED, но после того как passages в JSON локации станут консистентны со стенами, MovementPlanner найдёт обход через A* и пропустит путь

**Вывод:** ADR-O-323/324 — это **необходимый, но не достаточный** слой. Без Workplace Affordance они работают "в пустоту" — строят маршруты к случайно выбранным узлам. С Workplace Affordance они начнут строить маршруты к **осмысленным** точкам.

---

*План подготовлен на основе анализа исходного кода, JSON-конфигов NPC и локаций из архива `Enigma-V.0.5.3.4.8_drift.zip`.*
