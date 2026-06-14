# ADR-303: Coordinate Truth & Physical World Unification

> **Статус:** ACCEPTED (Частично реализовано — S81)
> **Тип:** ONTOLOGY (ADR-O)
> **Затронутые домены:** spatial, movement, rendering, collision
> **Предшественники:** ADR-S80 (Spatial Registry), ADR-S81 (Coordinate Truth)

---

## 1. Контекст и проблема

Система имела три критических разрыва между редактором карт и рантаймом игры:

### 1.1 Координатная двойственность (БАГ Y — КРИТИЧЕСКИЙ)

**Симптом:** Игрок не мог ходить. Камера была замершей.

**Корень:** Два слоя жили в разных системах координат:
- `game_screen._player_xy()` читал `local_position` (локальные координаты чанка)
- `ContextResolver` отдавал `collidable_walls` и `collidable_obstacles` в мировых координатах
- `_resolve_player_collisions()` сравнивал локальную позицию игрока с мировыми стенами
- Камера рендерилась по `_world_ctx.world_player_x/y` — вычислялось ОДИН РАЗ перед циклом

**Для таверны (origin=0,0)** это случайно совпадало. Для city_gate (origin=19.9, 0.04) — нет.

### 1.2 Center vs Top-Left (растянутые объекты)

**Симптом:** Объекты растянуты и смещены в рантайме.

**Корень:** Редактор хранит `position` как **center** объекта. Бэкенд (`scene_state_manager:709-710`) конвертировал center→top-left: `pos["x"] - w/2`. SpatialDataLoader **не конвертировал** — рендерил center-координату как top-left угол. Результат: сдвиг на пол-объекта.

Дополнительно: `_draw_entities` рендерил с center-offset (`ox - ow/2`), а `_draw_obstacles` — как top-left. Двойной рендер = наложение + растяжение.

### 1.3 Стены без проёмов (непроходимые двери)

**Симптом:** Двери блокировали проход.

**Корень:** Бэкенд резал стены проёмами через `_split_wall_by_openings()` (учитывая `passability.walk=True` и `rotation` = wall_id). SpatialDataLoader загружал стены **как есть** — сплошными линиями через дверные проёмы. Коллизия с непрерывной стеной блокировала проход.

---

## 2. Принятое решение

### 2.1 Единый пространственный поток (Coordinate Truth)

**Принцип:** Все пространственные операции в рантайме работают в МИРОВЫХ координатах. Конверсия local↔world происходит ТОЛЬКО на границе хранения (`_set_player_xy` / `_player_xy`).

```
Целевой поток:
local px,py → convert to WORLD → collision vs WORLD walls/obstacles → convert back to LOCAL → store
                                                                            ↓
                                                              render: local → world for camera
```

**Изменения:**
- Движение: `_world_px = _resolver.local_to_world(px, py, location_id)` → collision → `_resolver.world_to_local()`
- Камера: `_resolver.local_to_world(px, py, location_id)` вместо статичного `_world_ctx.world_player_x`
- `_world_ctx` остаётся для загрузки стен/объектов чанков, но не для позиции камеры

### 2.2 Center→Top-Left в SpatialDataLoader

**Принцип:** SpatialDataLoader — единственный источник пространственных данных для фронтенда. Его контракт = бэкендовский контракт.

**Изменения:**
- `pos.get("x") - ow / 2` для x и y (center→top-left)
- Добавлены поля `passability` и `blocks_los` (data-driven фильтрация)
- `_draw_entities` заменён на `pass` — все объекты рендерятся через `_draw_obstacles` (top-left)

### 2.3 Вырезание проёмов в стенах

**Принцип:** SpatialDataLoader режет стены проёмами так же, как бэкенд.

**Изменения:**
- Port `_split_wall_by_openings()` из `scene_state_manager` в `SpatialDataLoader`
- Двери с `passability.walk=True` и `rotation` = wall_id создают проём
- Стена превращается в 2-3 сегмента вокруг проёма

### 2.4 Data-driven коллизии

**Принцип:** Проходимость определяется `passability.walk`, а не хардкодом типов.

**Изменения:**
- `_resolve_player_collisions`: `passability.walk=True` → skip
- Fallback: `_PASSABLE_TYPES` для объектов без passability
- `_draw_obstacles`: passable объекты рендерятся полупрозрачными

---

## 3. Архитектурный вектор: Walls are Obstacles (ADR-S82)

### 3.1 Проблема текущей модели

Текущая модель разделяет стены и объекты:
```
SpatialRegistry → walls[] + obstacles[]
```

Это создаёт архитектурный долг:
- Дверь существует **дважды**: как объект и как дырка в стене
- Разрушаемые объекты требуют пересчёта стен
- `blocks_movement`, `blocks_vision`, `blocks_sound` — отдельные системы
- Мебель как "soft cost" (ДОЛГ 10) требует ещё одного слоя

### 3.2 Целевая модель

```
SpatialRegistry → world_obstacles[]
    ├── WallObstacle (blocks_movement=1.0, blocks_vision=1.0, durability=∞)
    ├── DoorObstacle (blocks_movement=0.0/1.0, blocks_vision=0.2, durability=50)
    ├── WindowObstacle (blocks_movement=1.0, blocks_vision=0.0, durability=10)
    ├── FurnitureObstacle (blocks_movement=0.7, durability=20, movable=True)
    └── ...
```

Единый интерфейс:
```python
@dataclass
class WorldObstacle:
    id: str
    geometry: Geometry       # line segment | AABB | polygon
    blocks_movement: float   # 0.0 = проходимо, 1.0 = непроходимо, 0.5 = замедляет
    blocks_vision: float     # 0.0 = прозрачно, 1.0 = непрозрачно
    blocks_sound: float      # 0.0 = слышно, 1.0 = глухо
    durability: float        # ∞ = неразрушимо
    movable: bool            # можно ли сдвинуть
    state: dict              # open/closed/broken/locked
```

### 3.3 Эволюционный путь

| Фаза | Что | Когда |
|------|-----|-------|
| S81 (текущая) | walls + obstacles с проёмами | Сейчас |
| S82 | WorldObstacle как абстракция, walls/obstacles = views | После Active Chunk Resolution |
| S83 | Полная унификация, walls[] исчезает | После ADR-301 (SemanticIndex) |

**Критерий перехода S81→S82:** Второй потребитель geometry помимо коллизий (например, LOS для ADR-301 или sound propagation).

### 3.4 Правило ENIGMA-002 (Two-Domain Rule)

Переход к S82 невозможен пока:
1. Есть только один домен, страдающий от разделения walls/obstacles
2. Нет runtime-бага, который требует WorldObstacle для починки

Сегодня: коллизии + рендер — два домена, но оба решены текущим фиксом. Переход преждевременен.

---

## 4. Запреты (Taboos)

| # | Запрет | Причина |
|---|--------|---------|
| 301 | Локальные координаты в коллизиях при origin ≠ (0,0) | Двойная истина |
| 302 | Камера по статичному _world_ctx | Замершая камера |
| 303 | Рендер объектов без center→top-left конверсии | Смещение на пол-объекта |
| 304 | Двойной рендер (entities + obstacles) | Растяжение |
| 305 | Стены без вырезания проёмов | Непроходимые двери |
| 306 | Хардкод _PASSABLE_TYPES без passability.walk | Не data-driven |
| 307 | Преждевременный переход к WorldObstacle (S82) | ENIGMA-002: нужен второй домен |

---

## 5. Downstream Consumers

| Потребитель | Влияние |
|-------------|---------|
| `_resolve_player_collisions` | Теперь в мировых координатах |
| `scene_renderer._draw_obstacles` | Top-left координаты, passability |
| `scene_renderer._draw_entities` | Отключён (pass) |
| `ContextResolver` | Источник конверсии, не источник камеры |
| `SpatialDataLoader` | Center→top-left + проёмы + passability |
| `_set_player_xy` / `_player_xy` | Единственная граница local↔world |

---

## 6. Runtime Impact

- **RAM:** Без изменений — те же данные, другая интерпретация
- **Latency:** +1 вызов `local_to_world`/`world_to_local` на кадр (O(1), пренебрежимо)
- **Стены:** Больше сегментов (проёмы), но всё равно O(N) collision check

---

## 7. Sandbox Tests

| Тест | Что проверяет |
|------|---------------|
| `test_coordinate_truth_tavern` | Игрок ходит в origin=(0,0) |
| `test_coordinate_truth_city_gate` | Игрок ходит в origin=(19.9, 0.04) |
| `test_center_to_top_left` | Объекты не растянуты |
| `test_door_passability` | Двери с walk=True проходимы |
| `test_wall_openings` | Стена режется проёмами |
| `test_camera_follows_player` | Камера не замершая |

---

## 8. Rollback

1. Вернуть `_player_xy` позицию в коллизии (локальную вместо мировой)
2. Вернуть `_world_ctx.world_player_x/y` для камеры
3. Убрать center→top-left конверсию в SpatialDataLoader
4. Убрать `_split_wall_by_openings` из SpatialDataLoader
5. Раскомментировать `_draw_entities`

---

## 9. Файлы изменены

| Файл | Изменение |
|------|-----------|
| `frontend/game_screen.py` | Движение в мировых координатах, камера следует за игроком, passability в коллизиях |
| `frontend/world_context.py` | center→top-left, проёмы в стенах, passability в obstacles |
| `frontend/scene_renderer.py` | `_draw_entities` = pass, passability в _draw_obstacles |

---

*Версия: 1.0*
*Дата: 2026-05-27*
*Автор: S81 (преемник S80)*