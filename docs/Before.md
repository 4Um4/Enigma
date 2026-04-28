## Дорожная карта: что кроме твоих двух параллелей

Сопоставил текущий код с Уставом и твоими диаграммами. Вот что **блокирует** твою работу и что **не видно**, пока не упрёшься.

---

### Твои параллели — мои замечания к ним

| Параллель | Риск | Что учесть |
|-----------|------|------------|
| **Фронтенд** | Получит сломанный контракт или начнёт импортировать `app/` | Нужен `WorldSnapshotDTO` (Устав 6.3) как жесткая стена. Без него фронтенд так или иначе протянет руки в backend |
| **Память NPC** | STM есть, L2 есть, но **MemoryPromotionEngine не подключён** (Устав 4.1.3). Память = лог, не система | Promotion — это не "ещё один модуль", это клапан. Без него STM переполняется, L2 не заполняется, campaign пустой |

---

### Приоритеты: что НЕ в твоём списке, но блокирует всё

#### 🔴 БЛОКИРУЮЩИЕ (сделать до или параллельно с памятью)

**1. Баг ATTACK = 0% + Score floor = 0.0**
- Отложен на Днях 4-5. Не чинился.
- Последствие: NPC **никогда не атакуют**. Даже при `PLAYER_ATTACKED + stress=100`. Это не баланс — это сломанная механика.
- Объём: 1-2 часа с песочницей.
- **Почему блокирует:** Память NPC будет записывать "игрок атаковал", а NPC всегда отвечает диалогом. Память заполняется мусором.

**2. TopicExtractor → DecisionHub**
- Устав 3.2: `topic` заполняется на Фазе 4, ДО DecisionHub.
- Сейчас: `CommunicationIntent.topic` пустой → Verbalization угадывает → LLM галлюцинирует.
- Объём: полдня. TopicExtractor уже есть (`importance_engine.py` частично делает это), нужно вырезать `topic` до `DecisionHub.compute()` и протянуть в `CommunicationIntent`.
- **Почему блокирует:** Твоя чистка LLM-мусора бесполезна без темы — промпт чистый, но контекст размытый.

**3. SQLite как runtime truth**
- Устав 4.2.1: SQLite = атомарный коммит. YAML/JSON = экспорт.
- Сейчас: `scene_state_manager.py` пишет JSON-файлы. Нет транзакции. При краше — разорванная реальность.
- Объём: `PersistencePort` уже существует (стр. 2292 в файловом дереве). Нужна SQLite-реализация порта + замена в `scene_manager.commit()`.
- **Почему блокирует память:** Память пишет в JSON через `scene_manager`. Пока persistence не атомарна — память может потерять промоут-события при краше.

#### 🟡 ВАЖНЫЕ (после блокирующих)

**4. WorldSnapshotDTO на границе фронтенда**
- Устав 6.3: frontend получает только позиции, видимые NPC, текст событий, доступные действия. Не `trust`, не `fear`, не `secret_events`.
- Сейчас: `_PipelineState` уходит в `run_turn`/`stream_turn`, оттуда формируется `ChatTurnResponse`. Но нет гарантии, что внутренние поля не утекут.
- Объём: 1 dataclass + маппинг в `run_turn`.
- **Почему важно:** Ты делаешь фронтенд. Без жёсткого DTO он начнёт зависеть от внутренних моделей.

**5. EventBus как реальная шина**
- Устав 5.1: `EventBus.publish()` — единственная точка входа событий.
- Сейчас: EventBus существует, но NPC-решения идут напрямую через пайплайн, не через `publish()`. Подписчики (memory, social) вызываются руками.
- Объём: 2-3 дня на постепенную миграцию. Не переписывать всё — начать с NPC-событий.
- **Почему важно:** Без шины добавление нового обработчика = изменение `_run_pipeline`. Это то, от чего мы только что избавлялись с коммитами.

#### 🟢 ТЕХНИЧЕСКИЙ ДОЛГ (когда руки дойдут)

**6. Dead tests** — `test_decision_hub_commitment.py` и `test_dm_facade.py` импортируют `NPCStateL2` которого нет. Удалить или обновить.

**7. ResonanceEngine / ContradictionResolver lifecycle** — Устав 7.9 предупреждает: без hooks = мёртвый код. Проверить, вызываются ли.

**8. `_run_pipeline` — 1500 строк** — это всё ещё монолит. После Days 6-7 стало лучше (единый коммит, чистые флаги), но структура не соответствует 10 фазам из Устава 3. Не переписывать с нуля — постепенно выносить фазы в отдельные методы.

---

### Итоговая дорожная карта

```
СЕГОДНЯ        ──→ ATTACK баг + score floor (1-2 часа)
СЕГОДНЯ/ЗАВТРА ──→ TopicExtractor перед DecisionHub (полдня)
ПАРАЛЛЕЛЬНО    ──→ SQLite persistence port (подряд с памятью)
ПАРАЛЛЕЛЬНО    ──→ WorldSnapshotDTO (подряд с фронтендом)
ПАРАЛЛЕЛЬНО    ──→ MemoryPromotionEngine wiring (подряд с памятью)
ЧЕРЕЗ НЕДЕЛЮ   ──→ EventBus как реальная шина
ЧЕРЕЗ 2 НЕДЕЛИ ──→ Постепенная экстракция фаз из _run_pipeline
```

**Главный принцип:** не добавлять фич, пока не починены провода. ATTACK=0% — это не баланс, это оборванный провод. Пустой topic — не промпт-инжиниринг, это отсутствие провода. SQLite — не оптимизация, это изоляция провода.

Строка 1177 — насилие **от других источников** (combat, intimidation рядом). `player_attacks` уже обработан на строке 1128 с теми же дельтами. Дублировать не нужно.

---

**Итого починено в рамках ATTACK бага:**

| Шаг | Что | Файл |
|-----|-----|------|
| 1 | `"player_attacked"` → `"player_attacks"` в `_PROVOCATION_TYPES` | decision_hub.py:654 |
| 2 | `_THREAT_THRESHOLD` → `PROVOCATION_THREAT_THRESHOLD` вынесена в constants.py | constants.py:91, decision_hub.py:52 |
| 3 | `"player_attacks"` добавлен в `context_relevance` — бонус к агрессии при прямой атаке | decision_hub.py:734 |

**Арифметика после фикса** (нейтральный NPC, без масок, без ранений):
- `context_relevance` = 0.5 + 0.5 × intensity = **до 1.0**
- `drive_relevance` = 0.25 × 1.0 = **0.25**
- `emotion_mod` = 0.0 (NEUTRAL)
- `rel_mod` = 0.0 (fear=0, trust=0)
- `risk_penalty` = 0.0 (provocation_gate=1.0, fear=0)
- `trait_mod` = 0.0
- **total ≈ 0.25 > MIN_INTENT_SCORE (0.15)** ✓

**`DialogueSession` — мёртвый код.** Никто не импортирует его. Провода от STM к topic нет.

Останавливаюсь и планирую. Реальный pipeline:
- `DecisionResult` → `VerbalizationContext` → промпт
- `CommunicationIntent` — мёртвый контракт
- `DialogueSession` — мёртвый модуль

**Минимальный провод:**
1. Добавить `topic` в `VerbalizationContext`
2. Создать `TopicExtractor` — простая Python-функция из event_type + scene_facts
3. Протянуть в game_loop при сборке `VerbalizationContext`

**42 passed.** Провод `topic` подключен от начала до конца.

---

## Итого сессия: 2 провода починены

### Шаг 1: ATTACK = 0% ✅

| Провод | Было | Стало |
|--------|------|-------|
| Опечатка в провокации | `"player_attacked"` — мёртвая строка, `is_provoked` всегда `False` | `"player_attacks"` — совпадает с реальным event_type из dm_router |
| Константа порога | `_THREAT_THRESHOLD = 0.3` — локальная в теле метода | `PROVOCATION_THREAT_THRESHOLD` в constants.py |
| Контекстная релевантность | `"player_attacks"` не давал бонус к агрессии в `_context_relevance` | Добавлен в триггер рядом с `"combat"` и `"capture"` |

### Шаг 2: TopicExtractor → VerbalizationContext → DM prompt ✅

| Провод | Было | Стало |
|--------|------|-------|
| TopicExtractor | Не существовал | `topic_extractor.py` — Python-маппинг event_type + ключевые слова |
| VerbalizationContext | Нет поля `topic` | Добавлено `topic: str = ""` |
| NpcOutcome | Нет поля `topic` | Добавлено `topic: str = ""` |
| SceneOutcomeBuilder.build() | Нет параметра `topics` | Добавлен `topics: Optional[Dict[str, str]]` |
| to_dm_prompt_block() | Topic не попадал в промпт | Выводится как `[тема: торговля]` |
| game_loop.py | Topic не извлекался | `extract_topic()` → `VerbalizationContext` → `_npc_topics` → `build()` |

### Мёртвый код обнаружен (технический долг, не блокирует):
- `CommunicationIntent` в `domain/communication.py` — контракт не используется
- `DialogueSession` в `memory/dialogue_session.py` — ни один модуль не импортирует
- `test_decision_hub_commitment.py` — импортирует несуществующий `NPCStateL2`

---

**50 passed.** SQLite провод подключен — единый источник правды через порт.

---

## Итого сессия: 3 провода починены

### 1. ATTACK = 0% ✅
- `"player_attacked"` → `"player_attacks"` (мёртвая строка в провокации)
- `_THREAT_THRESHOLD` → `PROVOCATION_THREAT_THRESHOLD` в constants.py
- `"player_attacks"` добавлен в `_context_relevance` триггер

### 2. TopicExtractor → DM prompt ✅
- Создан `topic_extractor.py` — Python-маппинг event_type + ключевые слова
- `topic` добавлен в `VerbalizationContext`, `NpcOutcome`, `SceneOutcomeBuilder.build()`
- Выводится в DM prompt как `[тема: торговля]`
- Протянут через game_loop: `extract_topic()` → `verb_ctx` → `_npc_topics` → `build()`

### 3. SQLite runtime truth ✅
- Создан `SqlitePersistenceAdapter` с WAL mode и `save_all()` (атомарная транзакция)
- `PersistencePort` расширен: добавлен `load_scene()`
- `JsonPersistenceAdapter` получил `load_scene()` для обратной совместимости
- `scene_state_manager.py`: `save_scene_state()` и `get_scene_state()` перенаправлены через порт
- `commit()` использует `save_all()` когда доступен (атомарный коммит сцена + NPC)
- `game_loop_builder.py` переключен на SQLite

### Технический долг обнаружен:
- `save_scene_state()` вызывается в 6 местах + `commit()` — дублирование записи (не рассинхрон, но избыточность)
- `CommunicationIntent` — мёртвый контракт
- `DialogueSession` — мёртвый модуль
- `test_decision_hub_commitment.py` — импортирует несуществующий `NPCStateL2`

### Следующие по приоритету (не блокируют память/фронтенд):
- **EventBus как реальная шина** — NPC-решения идут напрямую через пайплайн, не через `publish()`
- **Dead tests cleanup** — удалить или обновить
- **Экстракция фаз из `_run_pipeline`** — 1500 строк монолит

Хватит экстракции на этой сессии. Дальше — NPC loop (623 строк), который глубоко переплетён с `_all_npcs_raw`, `_dirty_npcs`, `_wt_dirty`, `_prop_dirty`, `hub_event`. Выносить без рефакторинга thread-state = методы с 10+ параметрами, что хуже монолита.

---

## Итого сессии

### Выполнено

| Шаг | Что | Результат |
|-----|-----|-----------|
| 1 | Dead tests cleanup | `test_decision_hub_commitment.py` + `test_dm_facade.py` удалены (импортировали несуществующий `NPCStateL2`) |
| 2 | `_init_scene_state()` экстракция | ~100 строк: SceneState + LifeEngine + EconomyTracker → отдельный метод |
| 3 | `_apply_front_engine()` экстракция | ~60 строк: FrontEngine давление мира → отдельный метод |
| 4 | `fake_req` мёртвый код | Создавался на 811, нигде не использовался — удалён |

### `_run_pipeline`: 1594 → 1472 строк (−122)

---

## Итого сессии

### Выполнено

| Шаг | Что | Строки out of loop |
|-----|-----|-------------------|
| 1 | **Баг аватара** — вынос из `else:` | ~67 строк теперь на правильном уровне |
| 2 | `EventDTO` топлевел импорт | Убран `UnboundLocalError` |
| 3 | `update_routine` сигнатура + 3 early returns | Починен `blacksmith_orm` в проде |
| 4 | `_simulate_minor` сигнатура | `tuple` → `list` |
| 5 | Тесты `test_life_engine.py` — 5 фиксов | 26 passed |
| 6 | **`_TickContext` dataclass** | 6 полей, заменил 5+ локальных переменных |
| 7 | Массовая миграция: `hub_event`, `_all_npcs_raw`, `_dirty_npcs`, `_wt_dirty`, `_prop_dirty`, `_max_npc_stress` | ~40 вхождений |
| 8 | **`_reset_session_state()`** | 16 строк → статический метод |
| 9 | **`_tick_conditions()`** | 25 строк → статический метод |
| 10 | **`_age_temporary_drives()`** | 16 строк → статический метод |
| 11 | **`_resolve_physical_attack()`** | 95 строк → метод с возвратом `(state_l2, constraints)` |
| 12 | **`_resolve_reactions()`** | 20 строк → статический метод |



### Баг в проде `blacksmith_orm` — тоже починен

`update_routine` возвращал `[]` вместо `([], None)` → `_simulate_minor` на строке 1046 делал `routine_changes, routine_intent = []` → `ValueError: not enough values to unpack (expected 2, got 0)`. Мой фикс строки 1086/1090/1095 закрывает это.

Предсуществующие баги (не чинил)
| Тест | Причина |
|------|---------|
| `test_ingest_txt_to_world` | `persist_world_canon` не существует |
| `test_run_pipeline_returns_pipeline_state` | Мок возвращает coroutine |
| `test_empty_social_modifiers_no_effect` | Загрязнение состояния между тестами (проходит в изоляции) |

Экстрагированные методы (новые):
_TickContext                    — dataclass, 6 полей
_reset_session_state()          — static, 3 параметра
_tick_conditions()              — static, 4 параметра
_age_temporary_drives()         — static, 3 параметра
_resolve_physical_attack()      — method, 9 параметров (но заменяет 100 строк inline)
_resolve_reactions()            — static, 5 параметров


Следующая сессия
Продолжить экстракцию из NPC loop. Кандидаты:

Memory event creation (~50 строк) — создание EventDTO + memory_manager.apply()
VerbalizationContext packing (~30 строк) — сборка контекста для LLM
WorldTick proactive block (~80 строк) — уже частично изолирован после NPC loop