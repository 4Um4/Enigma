# Отчёт сравнения: V.0.5.1.4_Начал_чинить_GAME_LOOP vs текущее состояние рабочей ветки

## Сводка

| Метрика | Значение |
|---------|----------|
| **Файлов изменено** | 31 (+ ~25 новых, −3 удалённых) |
| **Строк добавлено** | ~1 166 (в tracked файлах) |
| **Строк удалено** | ~2 226 (в tracked файлах) |
| **Чистый прирост** | −1 060 строк (рефакторинг + удаление мёртвого кода) |
| **Новые файлы** | `topic_extractor.py`, `sqlite_persistence_adapter.py`, `movement_engine.py`, `movement.py`, `snapshot.py`, `world_snapshot_builder.py`, `world_routes.py`, `intent.py`, `integration/` и др. |
| **Удалённые файлы** | `test_decision_hub_commitment.py`, `test_dm_facade.py`, `backend/app/core/sprite_resolver.py`, `ROAD_MAP_ТИК-ТАК.md` |

---

## Что было добавлено (архитектурно значимое)

### 1. Исправление ATTACK = 0% (критический баг)
**Файлы:** `decision_hub.py`, `constants.py`

| Провод | Было | Стало |
|--------|------|-------|
| Опечатка в провокации | `"player_attacked"` — мёртвая строка, `is_provoked` всегда `False` | `"player_attacks"` — совпадает с реальным `event_type` из `dm_router` |
| Константа порога | `_THREAT_THRESHOLD = 0.3` — локальная в теле метода | `PROVOCATION_THREAT_THRESHOLD` в `constants.py` |
| Контекстная релевантность | `"player_attacks"` не давал бонус к агрессии | Добавлен в `_context_relevance` триггер рядом с `"combat"` и `"capture"` |

**Почему важно:** NPC **никогда не атаковали** игрока, даже при `PLAYER_ATTACKED + stress=100`. Это была не балансировка — это сломанная механика. Теперь нейтральный NPC при прямой атаке получает `total ≈ 0.25 > MIN_INTENT_SCORE (0.15)` и может выбрать `ATTACK`.

---

### 2. TopicExtractor → DM Prompt (устранение галлюцинаций LLM)
**Файлы:** `topic_extractor.py` (новый), `verbalization_context.py`, `scene_outcome_builder.py`, `game_loop.py`

| Провод | Было | Стало |
|--------|------|-------|
| `TopicExtractor` | Не существовал | `topic_extractor.py` — Python-маппинг `event_type` + ключевые слова |
| `VerbalizationContext` | Нет поля `topic` | Добавлено `topic: str = ""` |
| `NpcOutcome` / `SceneOutcomeBuilder.build()` | Нет параметра `topics` | Добавлен `topics: Optional[Dict[str, str]]` |
| DM prompt | Topic не попадал в промпт | Выводится как `[тема: торговля]` |
| `game_loop.py` | Topic не извлекался | `extract_topic()` → `VerbalizationContext` → `_npc_topics` → `build()` |

**Почему важно:** `CommunicationIntent.topic` был пустым → Verbalization угадывала → LLM галлюцинировала. Теперь тема извлекается до DecisionHub (Фаза 4 по Уставу) и передаётся в DM промпт. **Провод подключён от начала до конца.**

---

### 3. SQLite как runtime truth (атомарная персистентность)
**Файлы:** `sqlite_persistence_adapter.py` (новый), `persistence_port.py`, `json_persistence_adapter.py`, `scene_state_manager.py`, `game_loop_builder.py`

| Провод | Было | Стало |
|--------|------|-------|
| `SqlitePersistenceAdapter` | Не существовал | SQLite с WAL mode, `save_all()` — атомарная транзакция |
| `PersistencePort` | Нет `load_scene()` | Добавлен `load_scene()` |
| `JsonPersistenceAdapter` | Нет `load_scene()` | Добавлен для обратной совместимости |
| `scene_state_manager.py` | Пишет JSON-файлы напрямую | `save_scene_state()` и `get_scene_state()` перенаправлены через порт |
| `commit()` | Нет атомарности | Использует `save_all()` (сцена + NPC вместе) |
| `game_loop_builder.py` | JSON persistence | Переключён на SQLite |

**Почему важно:** Раньше при краше JSON-файлы могли оказаться в разорванном состоянии (сцена записана, NPC — нет). Теперь `save_all()` гарантирует "всё или ничего" (Устав 4.2.1). JSON остался только для человекочитаемого экспорта.

---

### 4. Spatial System — Execution Layer (R4)
**Файлы:** `movement.py` (новый), `movement_engine.py` (новый), `snapshot.py` (новый), `world_snapshot_builder.py` (новый)

- **`MovementIntent`** — frozen dataclass: `npc_id`, `target_node_id`, `location_id`, `reason`
- **`MovementEngine`** — слой Execution: `MovementIntent` → `SceneChange` с `{x, y}`. Ленивая загрузка графа, кэширование.
- **`WorldSnapshotDTO`** — единственное, что пересекает границу backend → frontend. Не содержит `trust`, `fear`, `secret_events`.
- **`WorldSnapshotBuilder`** — чистый маппер: `scene_state dict` → `WorldSnapshotDTO`. Без побочных эффектов.

**Почему важно:** Раньше фронтенд мог протянуть руки в backend и получить внутренние модели. Теперь жёсткая стена DTO гарантирует, что клиент видит только позиции, видимых NPC, текст событий и доступные действия (Устав 6.3).

---

### 5. Game Loop — масштабная интеграция новых систем
**Файл:** `game_loop.py` (~+285/−285 строк)

Добавлены и интегрированы:

| Система | Что делает |
|---------|-----------|
| `PhysicalResolver` + `ReflexResolver` | Физическое разрешение атак ДО DecisionHub. Генерирует `SceneEvents` + `DecisionSignals` (constraint). |
| `ConditionEngine` | Тик состояний (горение, яд, etc.) — применяет урон/изменения каждый ход. |
| `SceneContinuity` | Эпизодическая фиксация сцены: факты, флаги, emotional vector, tension. NPC видят МИР, не только текущее действие. |
| `NarrativeExtractor` (R2.1) | Извлекает объекты/события/состояния из текста DM и применяет к `scene_state`. |
| `PerceptionFilter` | Фильтрует NPC по восприятию: адресат + свидетели. Только воспринимающие получают вербализацию. |
| `SocialEngine` propagation | Слухи доходят до непрямо воспринимающих NPC через граф связей. |
| `EconomyTracker` + `NeedEngine` | Дневные проверки потребностей NPC (INCOME/SOCIAL). Влияет на стресс и модификаторы DecisionHub. |
| `WorldTickEngine` | Проактивные действия major NPC (без игрока): блокировка пути, засады, поиск союзников. |
| `ReputationEngine` | Репутация фракций. Модификаторы DecisionHub + влияние действий на фракции. |
| `CharacterFilter` + `FrontEngine` | Сопротивление персонажа действиям против traits (Ego Resistance). Маски и давление мира на игрока. |
| `CognitiveDistortionEngine` | Модификаторы score на основе искажений NPC. Реализм сохраняется: NPC ведёт себя искажённо через score, вербализуется через bias. |
| `PlayerTargetExtractor` (исправлен) | Убран неверный путь `scene_state["npcs"]`. Дистанции считаются из `npc_positions` + `player_spatial` через spatial runtime. |

---

### 6. EventBus как реальная шина (частично)
**Файлы:** `event_bus.py`, `event_types.py`, `game_loop.py`

- События публикуются через `EventBus.publish()` — NPC-решения и spatial events идут через шину.
- `EventType` расширен: `PROXIMITY_CLOSE`, `PROXIMITY_LEAVE`.
- Подписчики (memory, social) вызываются руками — полная миграция на шину в процессе.

---

### 7. Memory Manager — расширение интеграции
**Файл:** `memory_manager.py` (~+217/−... строк)

- `get_weights_for_decision()` — обогащение `relationship_cache` из MemoryManager перед DecisionHub (Разрыв #1 закрыт).
- `run_decay_if_needed()` — decay каждые 10 ходов → identity weights.
- `detect_resonance()` + `apply_identity_weights()` — ResonanceEngine для формирования черт из паттернов.
- Запись в Working Memory: `player_action`, `npc_speech`, `dialogue` буфер.

---

### 8. Verbalization Pipeline — усиление контекста
**Файлы:** `scene_outcome_builder.py`, `response_validator.py`, `verbalization_context.py`

- `SceneOutcomeBuilder` получает `_npc_profiles` (voice_profile, backstory, author_notes, gender).
- `NpcOutcome` получает `topic` для DM prompt.
- `response_validator.py` — обновлённая валидация ответов.
- `verbalization_context.py` — добавлено поле `topic`.

---

## Что было удалено / зачищено

| Файл | Причина |
|------|---------|
| `test_decision_hub_commitment.py` | Импортировал несуществующий `NPCStateL2`. Мёртвый тест. |
| `test_dm_facade.py` | Устарел после рефакторинга DM фасада. |
| `backend/app/core/sprite_resolver.py` | Перенесён в `backend/sprite_resolver.py`. |
| `ROAD_MAP_ТИК-ТАК.md` | Устарел, заменён на актуальные roadmap-файлы. |

---

## Технический долг (обнаружен, не блокирует)

1. **`save_scene_state()` вызывается в 6 местах + `commit()`** — дублирование записи. Не рассинхрон, но избыточность.
2. **`CommunicationIntent`** в `domain/communication.py` — контракт не используется. Мёртвый код.
3. **`DialogueSession`** в `memory/dialogue_session.py` — ни один модуль не импортирует.
4. **`_run_pipeline`** — всё ещё ~1500 строк. Структура не соответствует 10 фазам из Устава 3. Нужна постепенная экстракция фаз в отдельные методы.
5. **EventBus — неполная миграция.** NPC-решения часть идёт напрямую через пайплайн, часть через `publish()`.

---

## Качественная оценка проделанной работы

### Что ценного сделано (не просто строки кода)

| # | Что | Почему это важно |
|---|-----|------------------|
| 1 | **Починен ATTACK = 0%** | NPC теперь могут атаковать. Восстановлена критическая игровая механика. |
| 2 | **TopicExtractor** | LLM больше не галлюцинирует без темы. Промпт чистый, контекст конкретный. |
| 3 | **SQLite atomic commit** | Защита от крашей. Runtime truth = база данных, не JSON. Фундамент для кампаний. |
| 4 | **WorldSnapshotDTO** | Жёсткая граница backend → frontend. Защита от утечки внутренних состояний. |
| 5 | **PhysicalResolver + ReflexResolver** | Разделение физики и психологии. Урон считается ДО DecisionHub, NPC реагирует на результат. |
| 6 | **SceneContinuity** | NPC видят МИР, не только текущее действие. Устранён эффект "золотой рыбки". |
| 7 | **PerceptionFilter** | Экономия VRAM: далёкие/слепые NPC не вызывают LLM. |
| 8 | **Social Propagation** | Мир живёт без игрока. Слухи течёт через связи NPC-NPC. |
| 9 | **CognitiveDistortion + CharacterFilter** | Глубина психологической симуляции. NPC и игрок подчиняются тем же законам. |
| 10 | **NarrativeExtractor** | DM текст → структурированные факты в сцене. Закрывает цикл "текст → состояние". |

### Объём работы

- **3 критических провода починены:** ATTACK, Topic, SQLite.
- **7+ новых систем интегрированы** в Game Loop.
- **2 мёртвых теста удалены**, 1 дублирующий файл зачищен.
- **DTO-граница** установлена для фронтенда.
- **Атомарность** персистентности обеспечена.

**Итого:** Не просто "написано много кода", а восстановлены сломанные механики, установлены архитектурные границы, и интегрированы системы, делающие мир живым и предсказуемым.

---

*Отчёт сгенерирован автоматически на основе diff и анализа ключевых файлов.*

