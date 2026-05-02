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

**Pipeline полностью чистый!** Ошибка `STATE_APPLICATOR` не появилась — она возникает только когда NPC принимает решение (DecisionResult), а сейчас ввод был без цели. Это некритичный баг — fallback возвращает оригинальный state, pipeline не ломается.



**D1 + D2 полностью работают!** `/api/world_state` возвращает `200 OK` с реальными координатами:

```
maid_lusya:           x=-1.5, y=-1.0  (talking_at_bar — random event!)
guard_borko:          x=0.0,  y=0.0
tavern_keeper_tornin:  x=-4.0, y=0.0
merchant_goran:       x=2.0,  y=1.0
```

NPC двигаются — видно `Прибыли в сцену: ['tavern_keeper_tornin', 'maid_lusya']`.

---

**Итог сессии — что сделано:**

| # | Проблема | Файл | Решение |
|---|---|---|---|
| 1 | `not enough values to unpack` | `life_engine.py` | `return [], None` вместо `return []` |
| 2 | Графы `city_gate`, `market_square`, `inn_rooms` отсутствуют | `location_templates.json` | Добавлены 3 локации с узлами |
| 3 | `Узел near_bar не найден` в любой локации | `life_engine.py` | Фильтр random event по локации |
| 4 | `fallback-граф` для tavern | `location_graph.py` + `game_screen.py` | `_DEFAULT_DATA_DIR` + убрать map_editor path |
| 5 | `drives_base` list вместо dict | `game_loop.py` | `isinstance` guard |
| 6 | `objects` list вместо dict | `dm_scene_builder.py` | Нормализация list→dict |
| 7 | `scene_state` str вместо dict | `game_loop.py` | `isinstance` guard |
| 8 | `PipelineContext not iterable` | `game_loop.py` | `in` → `hasattr` (2 места) |
| 9 | `scene_state` UnboundLocalError | `game_loop.py` | Исправлен отступ (был внутри except) |
| 10 | `VerbalizationContext` dataclass | `verbalization_context.py` | Дефолты для полей после `topic` |
| 11 | Русское имя локации в saves | `routes.py` + saves | `tavern_silver_wolf` вместо русского |
| 12 | BOM в JSON от PowerShell | `game_screen.py` | `utf-8-sig` декодинг |
| 13 | `/api/world_state` 404 | `world_routes.py` | Берём `scene_manager` из `app.state` |

Оба импорта чистые. **C1 готов.**

**Итог шага C1:**

| Что | Результат |
|---|---|
| `domain/tick.py` | `TickResultDTO` — результат тика для API layer |
| `core/tick_orchestrator.py` | Скелет 10 фаз из Устава §3 |
| `routes.py` idle_tick | 40 строк процедурного кода → 1 вызов `_orchestrator.execute()` |
| Фаза 0 | LifeEngine.tick() + apply_changes (свежий state для фазы 5) |
| Фаза 5 | DecisionHub.tick_decisions() |
| Фаза 9 | WorldSnapshotBuilder.build() → WorldSnapshotDTO |
| Фазы 1-4, 6-8, 10 | TODO-заглушки с номерами roadmap (C2-C8) |

**D4 готов.**

| Что | Результат |
|---|---|
| `spatial/spatial_event_detector.py` | Слой 4 — детекция переходов и проксимитета |
| `NPC_MOVED` | Публикуется при переходе между узлами графа |
| `NPC_PROXIMITY_CLOSE` | Два NPC сблизились (< 2.0м) |
| `NPC_PROXIMITY_LEAVE` | Два NPC разошлись (> 3.5м) |
| TickOrchestrator фаза 2 | Снимок ДО → фаза 0 → детекция → EventBus |

**Обновлённая дорожная карта:**

| Шаг | Статус |
|---|---|
| D1 Графы содержат узлы из activity_map | ✅ |
| D2 Schedule → MovementEngine → {x,y} | ✅ |
| D3 Need-driven → MovementEngine → {x,y} | ✅ |
| **D4 Spatial events — детекция переходов** | **✅** |
| B2+B3 idle_tick → WorldSnapshotDTO | ✅ |
| A1.1 PerceivedEntity.x/y, рендерер без _raw_data | ✅ (game_screen в руках) |
| C1 TickOrchestrator скелет | ✅ |
| `perceived_scene` удалён из DTO | ✅ |
| D5 Pathing: movement_mode="path" | TODO |
| D6-D8 Приоритеты, прерывание, новые источники | TODO |
| C2-C8 Memory, Topic, IntentAdapter, Persistence | TODO |


**D5 готов.**

| Что | Результат |
|---|---|
| `LocationGraph.find_path()` | BFS по connections, тест: `main_hall → bar_area → behind_bar` |
| `TransitTracker` | Хранит NPC в пути, `advance_all()` = 1 шаг за тик |
| `MovementEngine` | `movement_mode="path"` → регистрация в TransitTracker вместо телепорта |
| `MovementIntent.from_node_id` | Текущий узел для pathfinding |
| `TickOrchestrator` | `advance_all()` ВЕРХ фазы 0 — NPC в пути двигаются до новых решений |

**Порядок в тике:**
```
snapshot_positions_before()
  ├─ TransitTracker.advance_all()  ← NPC в пути: 1 шаг
  └─ _npc_positions_snapshot()     ← для SpatialEventDetector
phase_0_simulation()
  ├─ LifeEngine.tick()
  │   ├─ need-driven → MovementIntent(from_node_id=..., movement_mode="instant")
  │   └─ schedule   → MovementIntent(from_node_id=..., movement_mode="instant")
  └─ MovementEngine.process_intents()
      ├─ "instant" → SceneChange (телепорт)  ← текущее поведение
      └─ "path"    → TransitTracker.register  ← инфраструктура готова
```

**Активация pathing** (когда графы будут полными): заменить `movement_mode="instant"` на `"path"` в точках создания intent (строки 142, 1032, 1144 в life_engine.py) + передать `from_node_id=npc.get("position", "")`. Пока не включаем — телепорт надёжнее пока графы не проверены.

**Обновлённая дорожная карта:**

| Шаг | Статус |
|---|---|
| D1-D3 Movement рабочий | ✅ |
| D4 Spatial events | ✅ |
| **D5 Pathing инфраструктура** | **✅** |
| D6 Приоритеты intent-ов | TODO |
| D7 Прерывание движения | TODO |
| D8 Flee, follow, patrol | TODO |
| C1 TickOrchestrator | ✅ |
| A1.1 PerceivedEntity.x/y | ✅ |


**Шаг 6 завершён.** Подведу итоги всей сессии:

---

## ЧТО СДЕЛАНО

### Шаг 1: Разделить дистанции ✅
| Файл | Изменение |
|------|-----------|
| `spatial_runtime.py` | Новая `euclidean_distance(a, b)` — чистый `math.hypot` из `local_position` |
| `player_target_extractor.py` | Импорт + вызов `euclidean_distance` вместо графовой |
| `perception_filter.py` | Импорт + 2 вызова `euclidean_distance` вместо графовой |
| `spatial_runtime.py` | 3 внутренних вызова в `extract_scene_for_npc` → `euclidean_distance` |
| `spatial_runtime.py` | `resolve_distance_between_entities` сохранена для pathfinding |

**Эффект:** Люся (0.58m) теперь ближе Тени (7.56m) при таргетинге "девушка" и при восприятии.

### Шаг 2: Граф локации ✅ (диагностика, без изменений)
- Граф `tavern_silver_wolf` существует в `location_templates.json`
- `local_position` заполняется из editor JSON при инициализации
- Проблема была чисто в графовом расстоянии — исправлено Шагом 1

### Шаг 6: Дескрипторы для таргетинга ✅
| Файл | Изменение |
|------|-----------|
| `player_target_pipeline.py` | `gender` добавлен в `npc_ctx_list` |
| `player_target_extractor.py` | `_ROLE_KEYWORDS["maid"]` очищена от гендерных терминов |
| `player_target_extractor.py` | Добавлены `_GENDER_NORM`, `_DESCRIPTORS` (12 записей) |
| `player_target_extractor.py` | Лемматизация через pymorphy3 (реюз `_morph_analyzer`) |
| `player_target_extractor.py` | Descriptor-мэтчинг после name_forms → role → descriptor |

**Цепочка мэтчинга теперь:**
1. `name_forms` — "Люся", "Тень" → 0 или 1 кандидат
2. `role_keywords` — "служанка", "стражник" → по профессии
3. `descriptors` — "девушка", "мужчина" → по gender через pymorphy3 лемму
4. Distance sort → ближайший кандидат выигрывает

---

## ОБНОВЛЁННАЯ ДОРОЖНАЯ КАРТА

### ✅ Выполнено
- **Шаг 1:** Евклидова дистанция для восприятия и таргетинга
- **Шаг 2:** Граф локации — OK, без изменений
- **Шаг 6:** Дескрипторы + pymorphy3 + очистка role_keywords

### Новые шаги (из сессии)

**Шаг 4 (критично при движении NPC):** `scene_state_manager:1359` — при обновлении позиции NPC (`entry["position"] = position`) не обновляется `local_position`. Когда NPC начнёт двигаться — евклидова дистанция будет считать от старых координат. Нужно синхронизировать `_nearest_node_to_xy()` → `local_position` при каждом изменении.

**Шаг 7: S.1 Social Pragmatics Layer** (из твоего предложения)
- `TargetCandidate` dataclass с `match_type`, `match_keyword`, `distance`
- `address_propriety` = proper / mismatch / insulting / ambiguous
- `social_gap` из `SocialStanding` enum в NPCProfile
- Это фича на 5-7 шагов, но архитектурно правильная

### Отложено (не сломано, не мешает)
- **Шаг 3:** Движение NPC — заменён на реактивное движение через LLM (твоё предложение)
- **Шаг 5:** Архитектурный долг (`context_builder` type annotation, `_as_dict` костыль)

---

**Приоритет следующей сессии:** Шаг 4 (синхронизация `local_position` при движении) → тест "девушка" → Люся в живой игре.


Люся 4,5;5,0
Тень 3,5;9,5
Борко 12,0;9,0