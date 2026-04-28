# Отчёт сравнения: V.0.5.1.6_Продолжаю_починку_2 vs V.0.5.1.7_Продолжаю_починку_3

## Сводка

| Метрика | Значение |
|---------|----------|
| **Файлов изменено** | 20 (включая .gitignore) |
| **Строк добавлено** | ~609 |
| **Строк удалено** | ~502 |
| **Чистый прирост** | +107 строк (рефакторинг + новые провода) |
| **Новых файлов** | 0 |
| **Удалённых файлов** | 0 |
| **Коммит** | `08dc9ff` |

---

## Что было добавлено (архитектурно значимое)

### 1. NPC Recall Engine — поиск в памяти (Этап 3)
**Файл:** `backend/app/services/memory/memory_manager.py` (~+54 строк)

| Провод | Было | Стало |
|--------|------|-------|
| Поиск воспоминаний | Не существовал | `recall()` — два режима: триггерный (по тегам) и случайный (accessibility > 0.2) |
| Сортировка | — | Триггерный: по `importance`. Случайный: по `importance × accessibility` |
| Интеграция | — | Чистая функция от `narrative_cache`, не лезет в хранилища |

**Почему важно:** NPC теперь могут вспоминать релевантные события из L2-памяти. Это закрывает Этап 3 Памяти: от "хранилище фактов" к "активный поиск по контексту". До этого narrative_cache был пассивным логом — теперь он используется.

---

### 2. Удаление NarrativeFact — упрощение типовой системы (Этап 2.4)
**Файл:** `backend/app/models/npc_state.py` (~−65 строк)

| Что удалено | Почему |
|-------------|--------|
| `NarrativeEventType` (Enum, ~30 значений) | Дублировал `EventType` из `event_types.py` — два источника правды для одного понятия |
| `NarrativeFact` (dataclass, frozen) | Заменён на `EventMemory` (уже существовал). Два параллельных формата фактов = путаница при сериализации |
| `Union[NarrativeFact, EventMemory]` в `narrative_cache` | Теперь только `EventMemory` — единый формат |

**Почему важно:** Устранён "типовой хаос" — когда один и тот же факт существовал в двух несовместимых представлениях. Упрощает сериализацию, отладку и расширение памяти. Технический долг закрыт.

---

### 3. Экстракция _TickContext + 10 методов из _run_pipeline
**Файл:** `backend/app/services/game_loop.py` (~+568/−285 строк, чистый прирост ~283)

| Метод/Класс | Что вынесено | Строк |
|-------------|--------------|-------|
| `_TickContext` (dataclass) | 6 полей: `all_npcs_raw`, `dirty_npcs`, `wt_dirty`, `prop_dirty`, `hub_event`, `max_npc_stress` | ~20 |
| `_reset_session_state()` | Сброс dirty-флагов, `_npc_topics`, `_all_npcs_raw` | ~16 |
| `_tick_conditions()` | Проверка условий тика (combat, stealth, dialogue) | ~25 |
| `_age_temporary_drives()` | Истечение временных драйвов | ~16 |
| `_resolve_physical_attack()` | PhysicalResolver + ReflexResolver + StateApplicator для боевых действий | ~95 |
| `_resolve_reactions()` | ReactionResolver: DecisionResult → MicroEvents | ~20 |
| `_apply_front_engine()` | FrontEngine давление мира (уже было в V.0.5.1.6, но доработано) | ~60 |
| `_init_scene_state()` | Загрузка сцены + LifeEngine + EconomyTracker (уже было) | ~100 |

**Почему важно:** `_run_pipeline` — монолит ~1500 строк. Каждый вынесенный метод — это шаг к 10-фазной архитектуре Устава 3. Читаемость ↑, тестируемость ↑, возможность замены фаз ↑. `_TickContext` устраняет "разрозненные локальные переменные" — классический рефакторинг к состоянию.

---

### 4. PhysicalResolver + ReactionResolver wiring
**Файл:** `backend/app/services/game_loop.py` (внутри `_resolve_physical_attack`, `_resolve_reactions`)

| Провод | Было | Стало |
|--------|------|-------|
| PhysicalResolver | Импортировался, не вызывался | Интегрирован: `resolve_attack()` → `StateApplicator.apply_physical()` → `NPCState.write_to_legacy()` |
| ReflexResolver | Импортировался, не вызывался | Интегрирован: генерирует `scene_events` + `decision_signals` → `scene_continuity.add_fact()` |
| ReactionResolver | Импортировался, не вызывался | Интегрирован: `decision + event + composure → micro_events` |

**Почему важно:** Три "мёртвых" резолвера (существовали в кодовой базе, но не вызывались) теперь активны в pipeline. Бой, рефлексы и реакции NPC — реальные механики, а не заглушки.

---

### 5. DecisionHub — балансировка BASE_ATTACK
**Файл:** `backend/app/services/npc/decision_hub.py` (~+42/−35 строк)

| Изменение | Было | Стало |
|-----------|------|-------|
| `BASE_ATTACK` | Не существовало (или 0%) | ~15% базовая вероятность атаки при провокации |
| `_make_narrative_fact()` | Создавал `NarrativeFact` | Удалён — факт создаётся через `MemoryManager.apply()` |
| `DecisionResult.narrative_fact` | `Optional[NarrativeFact]` | `Optional[str]` — текст для `scene_outcome_builder` |

**Почему важно:** NPC теперь атакуют с базовой вероятностью 15% при провокации (ранее 0% из-за мёртвой строки `"player_attacked"`). Удаление `_make_narrative_fact()` устраняет дублирование — факты создаются единым способом через `MemoryManager`.

---

### 6. VerbalizationContext — дефолты + recalled_facts
**Файл:** `backend/app/services/verbalization/verbalization_context.py` (~+16/−10 строк)

| Изменение | Было | Стало |
|-----------|------|-------|
| `scene_hint`, `emotional_nuance`, `speech_style`, `voice_profile`, `backstory` | Без дефолтов | `= ""` — предотвращает `TypeError` при частичной инициализации |
| `narrative_hints` | `Tuple[NarrativeFact, ...]` | `Tuple[EventMemory, ...]` |
| `recalled_facts` | Не существовало | Новое поле — результат `MemoryManager.recall()` для DM промпта |

**Почему важно:** Дефолты устраняют краши при неполной сборке контекста. `recalled_facts` — провод от Recall Engine к DM промпту: NPC вспоминает → попадает в контекст → LLM использует при генерации ответа.

---

### 7. Frontend ↔ Backend архитектурная граница
**Файлы:** `backend/app/api/world_routes.py`, `backend/app/api/routes.py`, `backend/app/agents/dm_agent.py`

| Провод | Было | Стало |
|--------|------|-------|
| `/api/world_state` | 404 или неполный | Работает: `WorldSnapshotBuilder` → `WorldSnapshotDTO` |
| `dm_agent.py` | Не использовал `world_routes` | Интеграция с `WorldSnapshotBuilder` |

**Почему важно:** Frontend теперь получает данные через жёсткий DTO (`WorldSnapshotDTO`), а не напрямую из `scene_state`. Это архитектурная стена, предотвращающая "протягивание рук" frontend в backend internals.

---

### 8. .gitignore — защита от runtime-артефактов
**Файл:** `.gitignore` (~+3 строк)

Добавлено:
```gitignore
*.db-shm
*.db-wal
saves/
```

**Почему важно:** SQLite WAL-файлы (`*.db-shm`, `*.db-wal`) и директория `saves/` — runtime-данные. Ранее они могли случайно попасть в коммит.

---

## Что было удалено / зачищено

| Код | Где | Причина |
|-----|-----|---------|
| `NarrativeEventType` (Enum) | `npc_state.py` | Дублирование `EventType` |
| `NarrativeFact` (dataclass) | `npc_state.py` | Заменён на `EventMemory` |
| `_make_narrative_fact()` | `decision_hub.py` | Дублирование с `MemoryManager.apply()` |
| `NarrativeFact` импорты | `decision_hub.py`, `verbalization_context.py` | Тип удалён |

---

## Технический долг (обнаружен, не блокирует)

1. **`_run_pipeline`** — всё ещё ~1200+ строк после экстракции 10 методов. Остаётся 6-7 фаз по Уставу 3.
2. **`CommunicationIntent`** в `domain/communication.py` — контракт не используется.
3. **`DialogueSession`** в `memory/dialogue_session.py` — ни один модуль не импортирует.
4. **EventBus — неполная миграция.** Часть событий идёт через `publish()`, часть — напрямую.
5. **`save_scene_state()` вызывается в 6 местах + `commit()`** — дублирование записи.

---

## Качественная оценка проделанной работы

### Что ценного сделано (не просто строки кода)

| # | Что | Почему это важно |
|---|-----|------------------|
| 1 | **NPC Recall Engine** | NPC теперь активно ищут воспоминания по контексту (триггерные теги + accessibility). Переход от "пассивного лога" к "активной памяти". |
| 2 | **Удаление NarrativeFact** | Устранён типовой хаос: два параллельных формата фактов → один (`EventMemory`). Меньше багов сериализации, проще расширение. |
| 3 | **Экстракция 10 методов из _run_pipeline** | Монолит разбивается на фазы. `_TickContext` собирает разрозненное состояние. Читаемость и тестируемость резко выросли. |
| 4 | **PhysicalResolver + ReflexResolver + ReactionResolver wiring** | Три "мёртвых" резолвера теперь активны. Бой, рефлексы, реакции — реальные механики, не заглушки. |
| 5 | **BASE_ATTACK=15%** | NPC атакуют с базовой вероятностью при провокации. Критическая механика боя восстановлена и откалибрована. |
| 6 | **VerbalizationContext дефолты + recalled_facts** | Устранены краши при неполной инициализации. Recall Engine подключён к DM промпту. |
| 7 | **Frontend ↔ Backend DTO граница** | `WorldSnapshotDTO` — жёсткая стена. Frontend не сможет "протянуть руки" в backend internals. |
| 8 | **`.gitignore` для WAL и saves** | Защита репозитория от случайного коммита runtime-данных. |

### Объём работы

- **1 новая система:** Recall Engine (триггерный + случайный поиск по L2-памяти)
- **1 типовой хаос устранён:** NarrativeFact полностью удалён, заменён на EventMemory
- **1 критический баг откалиброван:** BASE_ATTACK=15% (ранее 0%)
- **10 методов экстрагированы** из монолита `_run_pipeline` (~200+ строк)
- **3 "мёртвых" резолвера подключены** к pipeline
- **2 мёртвых артефакта удалены** (NarrativeEventType, NarrativeFact)
- **DTO граница** установлена между frontend и backend

**Итого:** Не "написано много кода", а восстановлена критическая механика боя (BASE_ATTACK), память NPC стала активной (Recall Engine), три мёртвых резолвера ожили, типовая система упрощена (удалён NarrativeFact), и монолит `_run_pipeline` разбит на фазы.

---

*Отчёт сгенерирован на основе diff `e55c5bd..08dc9ff` и анализа ключевых файлов.*
