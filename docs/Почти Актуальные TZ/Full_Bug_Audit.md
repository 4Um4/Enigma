# Полный аудит багов NPC и логики игры

**Дата:** 2026-07-18  
**Метод:** статический анализ кода + проверка логов  
**Файлы проверены:** ~250 файлов в `backend/app/`, `frontend/`, `config/`

## Сводка найденных багов

| № | Баг | Серьёзность | Категория |
|---|---|---|---|
| 1 | Прямой write в `state.hp` минуя `body_state["current_hp"]` | 🔴 Критичный | Layer 0 violation |
| 2 | NPC без LoS всё равно получает события в память | 🔴 Критичный | Perception |
| 3 | `life_engine.update_position_from_schedule` не проверяет `life_status` | 🟠 Высокий | Zombie NPCs |
| 4 | LLM router глушит ошибки через `except: continue` | 🟠 Высокий | LLM integration |
| 5 | Захардкоженные `_builtin_templates()` конфликтуют с `activity_map` | 🟠 Высокий | Data integrity |
| 6 | Event bus теряет traceback при падении обработчика | 🟡 Средний | Observability |
| 7 | Fuzzy matching с порогом 0.6 — слишком мягкий для русского | 🟠 Высокий | Target resolution |
| 8 | SQLite без `check_same_thread=False` — race condition | 🔴 Критичный | Concurrency |
| 9 | `MacroMovementGoal` без `intent_id` — нет идемпотентности | 🟠 Высокий | Concurrency |
| 10 | `WorldScheduler` — заглушка, мир НЕ живёт между ходами | 🔴 Критичный | Core contract |
| 11 | `apply_perception_memory` вызывается для ВСЕХ nearby NPC | 🔴 Критичный | Perception |
| 12 | `combat_math.roll_initiative` использует global `random.randint` | 🔴 Критичный | ADR-O-301 violation |
| 13 | `save_scene` и `save_npcs` — НЕ атомарны (отдельные транзакции) | 🟠 Высокий | Savegame corruption |
| 14 | Двойной `rollback()` в `delete_campaign` — копипаста | 🟢 Низкий | Code quality |
| 15 | `_path_cache` растёт без LRU eviction | 🟡 Средний | Memory leak |

**Итого: 15 багов, из них 6 критичных, 6 высоких, 2 средних, 1 низкий.**

---

## Подробное описание каждого бага

### БАГ #1: Прямой write в `state.hp` (Layer 0 violation)

**Файл:** `backend/app/services/game_loop/__init__.py:1716`

```python
if _avatar_state.body_state:
    _avatar_state.body_state["current_hp"] = (
        _updated_avatar_dict.get("hp", _updated_avatar_dict.get("current_hp", 0))
    )
else:
    _avatar_state.hp = _updated_avatar_dict["hp"]  # ⚠️ ADR-HP-UNIFICATION violation
```

**Проблема:** Если `body_state` пустой (холодный старт, повреждённое состояние), код пишет в устаревшее поле `state.hp` напрямую. Это нарушает ADR-HP-UNIFICATION (HP SSOT = `body_state["current_hp"]`).

**Следствие:** Если позже body_state инициализируется, эффективный HP вернётся к значению из body_state, **а запись в `state.hp` потеряется**. Возможна "внезапная смерть" или "воскрешение" игрока.

**Фикс:** Если `body_state` пустой — инициализировать его из `BODY_STATE_DISABLED_DATA` ( sentinel), затем писать в `body_state["current_hp"]`.

---

### БАГ #2: NPC без Line-of-Sight всё равно получает события в память

**Файл:** `backend/app/services/npc/npc_tick_pipeline.py:154-155`

```python
if npc_id and (_is_player_turn and not (_los or _is_attack_target)):
    continue  # Пропускаем DecisionHub, но...
# ...ниже:
if state.hub_event:
    _mem_evt = apply_perception_memory(...)  # ⚠️ вызывается БЕЗ проверки LoS
    memory_events.append(_mem_evt)
```

**Проблема:** Цикл пропускает DecisionHub для NPC без LoS, но **`apply_perception_memory` вызывается до проверки LoS** — для всех NPC в `state.nearby_npcs`.

**Следствие:** NPC, который не видит игрока (за стеной, спиной), всё равно записывает в память `"player → maid_lusya: ..."`. Это и есть причина **массового дублирования в memory**, которое я видел в апрельских логах (4 NPC писали одну и ту же реплику).

**Фикс:** Перенести `apply_perception_memory` **после** проверки LoS, или добавить hearing-radius проверку (звук может проходить сквозь стены, но на ограниченное расстояние).

---

### БАГ #3: `life_engine` не проверяет `life_status` перед генерацией schedule

**Файл:** `backend/app/services/npc/life_engine.py:2087-2141`

```python
def update_position_from_schedule(self, npc, current_time, ...):
    npc_id = npc.get("id", "unknown")
    schedule = npc.get("routine", {}).get("schedule", {})
    if not schedule:
        return [], None
    # ⚠️ НЕТ проверки npc.get("body_state", {}).get("life_status") == "DEAD"
    
    # ADR-052: Cognitive Override Guard — есть
    # ADR-081: Physical Urgency Wake — есть
    # ADR-130: Movement Lock — есть
    # ❌ Death Lock — НЕТ
```

**Проблема:** Мёртвый NPC всё равно получает schedule tick, генерирует `MacroMovementGoal`, ходит по локации.

**Смягчение:** На верхнем уровне `tick_orchestrator.py:1147` есть `_alive_npcs = [n for n in ctx.all_npcs_raw if n.get("body_state", {}).get("life_status") != "DEAD"]`. Но если NPC **умирает в середине тика** (например, от раны во время боя), LifeEngine в этом же тике может запланировать ему движение.

**Следствие:** "Зомби-NPC" — мёртвый, но ходит. Это уже само по себе жутко, и нарушает ADR-123 (Death Lock).

**Фикс:** Добавить в начале `update_position_from_schedule`:
```python
if npc.get("body_state", {}).get("life_status") == "DEAD":
    return [], None
```

---

### БАГ #4: LLM router глушит ошибки через `except Exception: continue`

**Файл:** `backend/app/services/llm/router.py:366-374, 386-387`

```python
for model_key in preferred_keys:
    if pool.is_model_available(model_key):
        try:
            result = model_provider.provider.complete(prompt, params, system_prompt)
            return result
        except Exception as e:
            logger.debug(f"ModelRouter: Model {model_key} failed: {e}")  # ⚠️ только debug
            logger.debug(f"[ROUTER_TRACEBACK]\n{traceback.format_exc()}")  # ⚠️ только debug
            continue

# Fallback: try any available model from pool
for model_key in pool_configs.keys():
    try:
        return model_provider.provider.complete(prompt, params, system_prompt)
    except Exception:
        continue  # ⚠️ ПОЛНОСТЬЮ МЕЛКАЯ ОШИБКА — нет даже лога!
```

**Проблема:** Все ошибки LLM-провайдера логируются на `debug` уровне (в production не видны), а fallback loop вообще не логирует. Если LLM падает с критической ошибкой (OOM, JSON parse error, таймаут), никаких следов не остаётся.

**Следствие:** "Тихие" падения генерации. DM не отвечает, реплика NPC не генерируется, но логи чисты. Я видел это в `cds_session_20260718_121932.log` — 0 ERROR, но игрок не получает ответа.

**Фикс:** Заменить `logger.debug` на `logger.error` для первого except, добавить `logger.warning` для fallback.

---

### БАГ #5: Захардкоженные `_builtin_templates()` конфликтуют с `activity_map`

**Файл:** `backend/app/services/scene_state_manager.py:930-1111`

```python
@staticmethod
def _builtin_templates() -> dict:
    """Встроенные шаблоны на случай отсутствия файла."""
    return {
        "tavern_silver_wolf": {
            "name": "Таверна «Серебряный Волк»",
            "type": "tavern",
            "default_objects": {...},
            "npc_defaults": {
                "tavern_keeper_tornin": {
                    "position": "behind_bar",
                    "activity": "cleaning_tables",  # ⚠️ противоречие!
                },
                "maid_lusya": {
                    "position": "bar_area",          # ⚠️ служанка у стойки?
                    "activity": "serving_tables",     # ⚠️ обслуживает столы?
                },
                "thief_shadow": {
                    "position": "corner_table",
                    "activity": "observing",
                    "visible": False,
                },
                "guard_borko": {
                    "position": "corner_table",       # ⚠️ стражник в таверне?
                    "activity": "drinking",
                },
                ...
            }
        }
    }
```

**Проблема:** Если файл локации `tavern_silver_wolf.json` не найден (битый путь, удалён), используется **захардкоженный fallback** с противоречиями:
- `maid_lusya` стоит у `bar_area` (стойка), но `activity="serving_tables"` (обслуживает столы)
- `tavern_keeper_tornin` стоит `behind_bar` (за стойкой), но `activity="cleaning_tables"` (протирает столы)
- `guard_borko` (стражник) в таверне с `drinking`, хотя должен быть на воротах

**Следствие:** LLM получает в промпт эти данные и галлюцинирует: "Кузнец Орм работает за стойкой" (видел в апрельских логах).

**Фикс:** Удалить `_builtin_templates()` или синхронизировать с `config/npc/individuals/*.json` `activity_map`.

---

### БАГ #6: Event bus теряет traceback при падении обработчика

**Файл:** `backend/app/services/events/event_bus.py:114-122`

```python
for handler in handlers:
    try:
        result = handler(event)
        if isinstance(result, EventDTO):
            results.append(result)
    except Exception as e:
        logger.error(
            f"[EVENT_BUS] Обработчик упал: {handler.__qualname__} → {e}"
        )  # ⚠️ НЕТ traceback!
```

**Проблема:** Логируется только `e` (сообщение), но не `traceback`. Для сложных обработчиков (PerceptionSubscriber, ReactionSubscriber) это бесполезно — нет ни файла, ни строки, ни стека вызовов.

**Следствие:** Невозможно отладить почему обработчик упал. Видел в логах `[EVENT_BUS] npc_spoke от 'Люся' → 2 обработчиков, 0 результатов` — но если 0 результатов из-за падения, это невидимо.

**Фикс:** Добавить `logger.error(..., exc_info=True)`.

---

### БАГ #7: Fuzzy matching с порогом 0.6 — слишком мягкий для русского

**Файл:** `backend/app/services/game_loop/phase_1_input.py:60-62`

```python
# Fuzzy matching (порог 0.6 — терпим к опечаткам и падежам)
matches = get_close_matches(ref, npc_name_map.keys(), n=1, cutoff=0.6)
return npc_name_map[matches[0]] if matches else ""
```

**Проблема:** `difflib.get_close_matches` с cutoff=0.6 для русского с падежами:
- "Люсю" (винительный) → "Люся" — совпадение ~0.83 ✅
- "людям" → "Люся" — совпадение ~0.6 ⚠️ может попасть
- "любую" → "Люся" — совпадение ~0.55 (не пройдёт, но близко)

**Следствие:** Игрок может напечатать "подойди к людям" — и цель станет "Люся" (NPC, а не группа людей).

**Фикс:** 
1. Использовать `pymorphy3` (уже установлен!) для лемматизации перед fuzzy matching
2. Поднять cutoff до 0.75
3. Использовать `rapidfuzz` (быстрее и точнее, чем `difflib`)

---

### БАГ #8: SQLite без `check_same_thread=False`

**Файл:** `backend/app/services/state/sqlite_persistence_adapter.py:48`

```python
self._conn = sqlite3.connect(
    ...
)  # ⚠️ нет check_same_thread=False
```

**Проблема:** По умолчанию SQLite `check_same_thread=True` — connection можно использовать только в потоке создания. Если:
- GameLoop работает в main thread
- `DialogueExecutor` использует `concurrent.futures.ThreadPoolExecutor` (см. `dialogue_executor.py:9`)
- И TaskScheduler записывает в SQLite из worker thread

→ `ProgrammingError: SQLite objects created in a thread can only be used in that same thread`

**Следствие:** Тихие падения при параллельной записи. Видел "0 ERRORs" в логах — возможно, потому что SQLite-ошибка ловится где-то в `except: pass` (БАГ #4).

**Фикс:** `sqlite3.connect(..., check_same_thread=False)` + добавить `threading.Lock` для защиты записей.

---

### БАГ #9: `MacroMovementGoal` без `intent_id` — нет идемпотентности

**Файл:** `backend/app/domain/movement.py:35-45`

```python
@dataclass
class MacroMovementGoal:
    actor_id: str
    target_node_id: str
    from_node_id: str = ""
    location_id: str = ""
    reason: str = ""
    domain: IntentDomain = IntentDomain.ROUTINE
    priority: float = 0.5
    target_local_xy: Optional[tuple[float, float]] = None
    processed: bool = field(default=False, init=False)
    processor: Optional[str] = field(default=None, init=False)
    # ❌ НЕТ intent_id!
```

**Проблема:** Если один и тот же intent случайно попадёт в две очереди (например, schedule + decision hub), MovementEngine увидит `processed=True` и поднимет `RuntimeError` — но **нет способа узнать, кто первым обработал** и какой `intent_id` дублируется.

**Следствие:** Невозможно отладить "почему NPC телепортировался" — нет trail.

**Фикс:** Добавить `intent_id: str = field(default_factory=lambda: str(uuid.uuid4()))`.

---

### БАГ #10: `WorldScheduler` — заглушка, мир НЕ живёт между ходами

**Файл:** `backend/app/services/world_scheduler.py:35-37`

```python
def maybe_tick(self, world_id: str, every_minutes: int) -> dict:
    ...
    # TODO: временная заглушка
    # будет удалено после: ФАЗА 6 — WorldTickEngine (Python-based, без LLM)
    result = {"world_events": [], "simulation_log": "disabled_pending_phase6"}
    ...
```

**Проблема:** `WorldScheduler.maybe_tick()` **всегда возвращает пустой список событий**. Это значит, что **мировые события между ходами игрока НЕ генерируются** — NPC существуют только в момент хода игрока.

**Следствие:** Прямое нарушение контракта игры "Мир живёт, даже когда игрок не действует":
- NPC не двигаются по расписанию между ходами
- Экономика не работает (нет торговцев, нет странников)
- Время не идёт, погода не меняется
- Скрытые события не происходят

Это **фундаментальный пробел** — игра статична между ходами игрока.

**Фикс:** Реализовать `WorldTickEngine` (Python-based, без LLM). См. `docs/ARCHIVE/2026-06-19/ТЕХЗАДАНИЕ ПРЕЕМНИКУ SIMULATION SCHEDULER И НОВАЯ АРХИТЕКТУРА GAME LOOP.md`.

---

### БАГ #11: `apply_perception_memory` вызывается для ВСЕХ nearby NPC

**Файл:** `backend/app/services/npc/npc_tick_pipeline.py:221-234`

```python
# TZ-10: Сборка memory_events для отложенного применения (без I/O внутри run)
if state.hub_event:
    try:
        _mem_evt = apply_perception_memory(
            None,
            state_l2,
            state.hub_event,
            npc_id,
            state.player_target_id,
            state.raw_input,
            state.campaign_id,
            spatial_query=state.spatial_query,
        )
        if _mem_evt:
            memory_events.append(_mem_evt)
```

**Проблема:** Этот код в цикле `for npc in _npcs_to_process` (где `_npcs_to_process = state.nearby_npcs`). `nearby_npcs` строится в `dm_scene_builder.py:54` как **все NPC в радиусе 20 метров** — это вся таверна!

`apply_perception_memory` создаёт `summary = f"{_evt_actor} → {player_target_id}: {player_text[:60]}"` и пишет в memory этого NPC.

**Следствие (подтверждено апрельскими логами):**
- Игрок говорит "Люся, займи денег"
- В memory **4 NPC** (Борко, кузнец, Торнин, Горан) появляется запись `"player → maid_lusya: Люся займи денег"`
- Только Люся должна это запомнить — остальные либо не слышали (за стеной), либо слышали обрывок

Это **корневая причина "каши" в логах NPC** — все знают всё, что происходит в таверне.

**Фикс:** 
1. В `apply_perception_memory` добавить проверку `sound_reach` — NPC за пределами hearing radius не пишет полный текст в память
2. Для NPC в радиусе hearing, но не target — писать обобщённый summary (`"player → maid_lusya: что-то про деньги"`, не точный текст)
3. Подключить `perception_filter.py` (сейчас мёртвый код)

---

### БАГ #12: `combat_math.roll_initiative` использует global `random.randint`

**Файл:** `backend/app/services/game/combat_math.py:277, 377, 401, 426`

```python
def roll_initiative(character: Dict) -> int:
    dex_mod = ability_modifier(character.get("abilities", {}).get("dexterity", 10))
    d20 = random.randint(1, 20)  # ⚠️ ADR-O-301 violation
    total = d20 + dex_mod
    _log_roll("initiative", [d20], total, {"character": character.get("name", "?")})
    return total
```

**Проблема:** ADR-O-301 требует, чтобы **все** броски кубиков были детерминированными через `KernelRNG(tick, npc_id, salt)`. Функция `roll_initiative` (и ещё 3 функции в файле) использует **глобальный `random.randint`** без передачи `rng`.

**Следствие:**
- Бой **недетерминирован** — при реплее инициатива будет другой
- Это нарушает `KernelRNG Isolation` (контракт Layer 1)
- Тесты боя **flaky** — могут падать случайно

ADR-159 зафиксировал этот фикс для `roll`, `roll_advantage`, `roll_disadvantage`, `attack_roll` — но **`roll_initiative` пропустили**.

**Фикс:** Добавить `rng: Optional[random.Random] = None` параметр, использовать `rng.randint(1, 20) if rng else random.randint(1, 20)`.

---

### БАГ #13: `save_scene` и `save_npcs` — НЕ атомарны

**Файл:** `backend/app/services/state/sqlite_persistence_adapter.py:106-124`

```python
def save_scene(self, campaign_id: str, scene_state: Dict[str, Any]) -> None:
    try:
        self._upsert(f"scene:{campaign_id}", scene_state)
        self._get_conn().commit()  # ⚠️ отдельная транзакция
        ...
    except sqlite3.Error as e:
        self._get_conn().rollback()

def save_npcs(self, npc_dicts: List[Dict[str, Any]]) -> None:
    try:
        self._upsert("npcs:major", npc_dicts)
        self._get_conn().commit()  # ⚠️ отдельная транзакция
        ...
    except sqlite3.Error as e:
        self._get_conn().rollback()
```

**Проблема:** `save_scene` и `save_npcs` — **две отдельные транзакции**. Если `save_scene` успешно, а `save_npcs` падает (например, диск заполнен) — сцена сохранена, NPC нет → **несогласованное состояние**.

В файле есть `atomic_commit` (строка 180), но **он не используется** в `save_scene`/`save_npcs`.

**Следствие:** Нарушение "Устав 4.2.1: SQLite = runtime truth. Atomic commit. Всё или ничего" (см. комментарий в начале файла).

**Фикс:** Использовать `atomic_commit` для записи scene + NPC runtime + events вместе.

---

### БАГ #14: Двойной `rollback()` в `delete_campaign`

**Файл:** `backend/app/services/state/sqlite_persistence_adapter.py:158-160`

```python
except sqlite3.Error as e:
    logger.error(
        f"[SQLITE_PERSISTENCE] Error deleting campaign {campaign_id}: {e}"
    )
    self._get_conn().rollback()
    self._get_conn().rollback()  # ⚠️ копипаста
```

**Проблема:** Двойной `rollback()` — копипаста. После первого `rollback` транзакция уже откачена, второй может поднять `sqlite3.Error` (хотя в текущей версии sqlite3 это безопасно — no-op).

**Следствие:** Code smell, не критично.

**Фикс:** Удалить вторую строку.

---

### БАГ #15: `_path_cache` растёт без LRU eviction

**Файл:** `backend/app/services/spatial/spatial_service.py:120, 439`

```python
self._path_cache: Dict[Tuple[str, str, str, Urgency], List[NodeRef]] = {}
...
# В find_path:
self._path_cache[cache_key] = path  # ⚠️ только добавление, нет удаления
```

**Проблема:** `_path_cache` растёт без ограничений. Каждый уникальный `(source, target, mode, urgency)` добавляет запись. Только `clear()` при смене overlay.

**Следствие:** В долгой сессии (часы) при множестве перемещений NPC cache может вырасти до тысяч записей. Memory leak.

**Фикс:** Использовать `functools.lru_cache` или `collections.OrderedDict` с max_size=128.

---

## Дополнительные проблемы (не баги, но code smell)

### 193 TODO/FIXME маркера в коде

В `backend/app/` найдено **193 маркера** TODO/FIXME/XXX/HACK/BUG/DEPRECATED:
- `perception_filter.py` — 22 (самый загрязнённый)
- `life_engine.py` — 8
- `game_loop/__init__.py` — 8
- `scene_state_manager.py` — 7
- `tick_orchestrator.py` — 6

Это индикатор **незавершённой работы**. Каждый TODO — потенциальный баг.

### 10+ глобальных синглтонов

```
main.py:27            global _llama_server_proc, _llama_started_by_us
event_bus.py:200      global _bus
error_interpreter.py  global _interpreter_instance
world_state.py:263    global _world_state
router.py:657         global _router
object_resolver.py    global _morph
health.py:27          global _cache, _cache_time
```

Глобальное состояние усложняет тестирование и создаёт race conditions.

### Мёртвый код: `perception_filter.py`

Perception Filter существует (220 строк), но **не вызывается** в `npc_tick_pipeline.py`. Это и есть причина БАГА #11.

### `time.sleep` в LLM layer

8 `time.sleep()` вызовов в `llm/router.py` и `llama_cpp_provider.py` — блокируют симуляцию при ожидании LLM. Нужно использовать async/await.

---

## Оценка состояния кода

| Метрика | Значение | Оценка |
|---|---|---|
| Total Python LoC (backend/app/) | ~85,000 | Большой проект |
| Файлов | ~250 | Зрелость |
| Тестов | 842 passing | Хорошее покрытие |
| TODO/FIXME маркеров | 193 | ⚠️ Выше среднего |
| Критических багов | 6 | 🔴 Много |
| Высоких багов | 6 | 🟠 Много |
| Архитектурных контрактов | 110+ ADR | Отличная документация |
| Реализованных контрактов | ~70% | Хорошее соответствие |

### Серьёзность по доменам

| Домен | Серьёзность | Главная проблема |
|---|---|---|
| **Perception** | 🔴 Критическая | БАГ #2, #11 — все NPC видят всё |
| **LLM Integration** | 🟠 Высокая | БАГ #4 — тихие падения |
| **Concurrency** | 🔴 Критическая | БАГ #8 — SQLite threading |
| **Combat** | 🔴 Критическая | БАГ #12 — недетерминированность |
| **Persistence** | 🟠 Высокая | БАГ #13 — неатомарные сохранения |
| **Movement** | 🟠 Высокая | БАГ #9 — нет intent_id |
| **Scheduler** | 🔴 Критическая | БАГ #10 — мир статичен между ходами |
| **Memory** | 🔴 Критическая | БАГ #11 — массовое дублирование |

---

## Итоговый вердикт

**Код забагован существенно.** Не "немного забагован", а **фундаментально** — 6 критических багов, из которых 4 (perception, scheduler, combat determinism, SQLite threading) **блокируют нормальную работу игры**.

### Топ-3 приоритета для фикса

1. **БАГ #11** (Perception duplication) — самая частая причина "каши" в логах NPC. Фикс: подключить `perception_filter` + hearing radius.
2. **БАГ #10** (WorldScheduler stub) — без него игра не "живёт". Фикс: реализовать WorldTickEngine.
3. **БАГ #12** (Combat RNG) — без него бой недетерминирован. Фикс: добавить `rng` параметр.

### Что говорит о проекте

Проект находится в состоянии **"архитектура есть, реализация — нет"**:
- 110+ ADR-документов с детальными контрактами
- 842 теста, 5/5 IPT инвариантов
- **Но 6 критических багов**, которые делают игру неиграбельной

Это типичная "**долина разочарования**" — документация опережает реализацию на 30-40%. ADR написаны для систем, которые **не работают** (perception filter, world scheduler, atomic commit).

### Можно ли это починить?

**Да, но потребуется 2-3 недели работы без новых фич:**

| Неделя | Что делать |
|---|---|
| 1 | БАГ #11 (perception), #2 (LoS), #5 (builtin_templates), #7 (fuzzy matching) |
| 2 | БАГ #10 (WorldScheduler), #12 (combat RNG), #8 (SQLite threading) |
| 3 | БАГ #1 (HP), #3 (death lock), #4 (LLM logging), #13 (atomic commit), #9 (intent_id), #15 (cache LRU) |

После этого игра **может стать играбельной**. Без этого — продолжать разработку новых фич бессмысленно, баги будут копиться быстрее фиксов.

---

*Аудит сохранён в `/home/z/my-project/download/Full_Bug_Audit.md`*
