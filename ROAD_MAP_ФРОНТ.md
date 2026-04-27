Все caller-ы обновлены. Теперь дорожная карта.

---

## ДОРОЖНАЯ КАРТА ENIGMA

### Что сделано (эта сессия)

**Frontend ↔ Backend граница:**
- `sprite_resolver.py` → перемещён из `app/core/` в `backend/`
- `npc_name_resolver.py` → создан, `intent_parser.py` больше не импортирует `app/`
- `IDLE_TICK_*` константы → перемещены из `app/core/constants.py` в `backend/constants.py`
- `domain/snapshot.py` → `WorldSnapshotDTO`, `NPCPositionDTO`, `VisibleEventDTO`
- `domain/intent.py` → `IntentDTO`
- `WorldSnapshotBuilder` → маппер `scene_state dict → WorldSnapshotDTO`
- `world_routes.py` → `GET /api/world_state` эндпоинт
- `api_client.get_world_state()` → read-only запрос снимка

**Movement архитектура (Диаграмма 9):**
- `domain/movement.py` → `MovementIntent` (целевой узел, location, reason, priority, movement_mode)
- `MovementEngine` (Слой 2) → `MovementIntent → SceneChange(local_position={x,y})`
- LifeEngine: need-driven → `MovementIntent` (вместо прямого `SceneChange`)
- LifeEngine: schedule → `MovementIntent` (вместо прямого `SceneChange`)
- LifeEngine: random events → `MovementIntent` (вместо прямого `SceneChange`)
- **ARCH GUARD** → `SceneChange(field="position")` вызывает `RuntimeError`

**Ключевой момент:** все 3 источника движения (schedule, needs, random) проходят через MovementEngine. Строковые позиции больше не проникают в scene_state.

---

### Что осталось — полная картина

#### БЛОК A: Frontend чистый (Диаграмма 4)

| Шаг | Что | Зависит от |
|---|---|---|
| A1 | `game_screen.py` рендерит из `WorldSnapshotDTO` вместо `scene_state` | Блок B |
| A2 | `npc_movement.py` — удалить (frontend не двигает NPC) | Блок B |
| A3 | `player_cognition/` — вынести perceived scene в backend (WorldSnapshotBuilder) | Блок B |
| A4 | `game_loop_bridge.py` → переписать через `WorldSnapshotDTO` | Блок B |

**Почему заблокирован:** `WorldSnapshotDTO` пока не содержит perceived_scene (только сырые позиции). Frontend не переключится пока не увидит те же данные.

#### БЛОК B: Backend → Frontend мост рабочий

| Шаг | Что | Зависит от |
|---|---|---|
| B1 | `WorldSnapshotBuilder` заполняет `perceived_scene` из pipeline | Блок C |
| B2 | `WorldSnapshotBuilder` получает NPC из `scene_state["npc_positions"]` | Блок D |
| B3 | `/api/world_state` вызывается из `idle_tick` ответа | B2 |
| B4 | `304 Not Modified` работает | B3 |

**Почему заблокирован:** `npc_positions` в scene_state пустые (NPC не получают `{x,y}`).

#### БЛОК C: NPC Brain — единый цикл (Диаграмма 1)

| Шаг | Что | Зависит от |
|---|---|---|
| C1 | `TickOrchestrator` скелет (10 фаз) | — |
| C2 | Фаза 3: MemoryProcessor | C1 |
| C3 | Фаза 4: TopicExtractor | C1 |
| C4 | Фаза 5: DecisionHub | C3 |
| C5 | Фаза 6: IntentEventAdapter | C4 |
| C6 | Фаза 8: Handlers (spatial events) | C5 |
| C7 | Фаза 9: WorldSnapshotBuilder | C6 |
| C8 | Фаза 10: PersistencePort (atomic commit) | C7 |

#### БЛОК D: Movement — NPC двигаются (Диаграмма 9)

| Шаг | Что | Зависит от |
|---|---|---|
| D1 | **Фикс: графы содержат узлы из activity_map** | — |
| D2 | Schedule → MovementEngine → `{x,y}` в scene_state | D1 |
| D3 | Need-driven → MovementEngine → `{x,y}` в scene_state | D1 |
| D4 | Spatial events (Слой 4): детекция переходов | D2 |
| D5 | Pathing: `movement_mode="path"` в MovementEngine | D4 |
| D6 | Приоритеты intent-ов (flee > combat > needs > schedule) | D5 |
| D7 | Прерывание движения | D6 |
| D8 | Flee, follow, patrol — новые intent-источники | D6 |

#### БЛОК E: Production-Grade (Диаграмма 1)

| Шаг | Что | Зависит от |
|---|---|---|
| E1 | PersistencePort: SQLite atomic commit | C8 |
| E2 | YAML dump из SQLite (для человека) | E1 |
| E3 | MemoryPromotionEngine (session → campaign) | C2 |
| E4 | ResonanceEngine + ContradictionResolver | C6 |

---

### Порядок выполнения (критический путь)

```
СЕССИЯ СЕЙЧАС:
  D1 → D2 → D3

СЛЕДУЮЩАЯ:
  B2 (NPC в scene_state) → B3 (idle_tick возвращает snapshot)

ПОТОМ:
  A1 (game_screen по DTO) → A2 (удалить npc_movement.py)

ПОТОМ:
  C1 (TickOrchestrator) → C7 (snapshot в фазе 9) → A3 (player_cognition в backend)

ПОТОМ:
  D4 (spatial events) → D5 (pathing) → D6-D8 (приоритеты, прерывание, новые источники)

ПОТОМ:
  E1-E4 (production)
```

---

### Когда придём к чистой архитектуре

| Цель | После каких шагов |
|---|---|
| **NPC видны на экране из WorldSnapshotDTO** | D1 + D2 + B2 + B3 + A1 |
| **Frontend не импортирует app/** | Выше + A2 + A3 |
| **NPC двигаются по потребностям** | Выше + D3 |
| **NPC идут по пути (не телепорт)** | Выше + D5 |
| **10-фазный тик** | Выше + C1-C8 |
| **Чистая архитектура (Диаграмма 1)** | Выше + E1-E4 |

---

Итого за шаг — что исправлено (D1 с дорожной карты):

Проблема
Файл
Суть
not enough values to unpack	life_engine.py	update_routine возвращал [] вместо [], None
Узел gate_post/stall_3/bed не найден	location_templates.json	Графы city_gate, market_square, inn_rooms отсутствовали
Узел near_bar не найден	location_templates.json + life_engine.py	Узел отсутствовал + event не фильтровался по локации
fallback-граф для tavern	location_graph.py + game_screen.py	Путь data_dir зависел от CWD; game_screen передавал путь к map_editor
list has no attribute items	game_loop.py	drives_base мог быть list вместо dict
str has no attribute get	game_loop.py	scene_state мог быть str вместо dict
Таверна Серебряный Волк в saves	routes.py + saves	Русское имя вместо ID
BOM в JSON	game_screen.py	Set-Content -Encoding UTF8 добавлял BOM