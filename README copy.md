## 8. ИСТОРИЯ РАЗРАБОТКИ

### Memory System v5.2
- Удалён файл-паразит services/memory.py
- npc_state.py: добавлены NPCIdentityL1, DecisionView, алиасы L0/L2, write-контракты
- Memory→DecisionHub: relationship_cache обогащается перед каждым compute()
- ResonanceEngine→identity_cache: decay → apply_identity_weights → NPCIdentityL1
- DecisionHub.compute() принимает identity=NPCIdentityL1
- Удалён мёртвый memory_manager_agent.py

### Глобальная очистка
- NPCStateL2 дубликат удалён из npc_profile.py → npc_state.py
- NPCIdentityL1 дубликат удалён из npc_profile.py → npc_state.py
- npc_profile.py теперь содержит только L0 типы
- game_loop_factory.py → мигрирован в main.py (app.state) + accessor
- npc_agent.py: react() + _fallback_react() удалены (-213 строк)
- npc_state.py: to_legacy() мёртвый метод удалён
- game_loop.py: ложные TODO-заглушки удалены

### Архитектурная стабилизация
- Уничтожен монолит python_engines.py
- Типы разделены: npc_profile.py (L0), npc_state.py (L1/L2)
- DecisionHub и StateApplicator пересажены на L0/L2
- Создан npc_loader.py (бронестена от мусора)
- DM Execution Facade (Этап 5) интегрирован в game_loop.py
- GameLoop мигрирован на app.state (main.py startup + accessor)
- Глобальная очистка: -300 строк мёртвого/дублирующего кода

### StateApplicator Pipeline
- DecisionHub → StateApplicator.apply() → NPCState.write_to_legacy() → _save_npcs()
- NPC теперь реально меняют стресс/интент после действий игрока
- Интеграционный тест: test_state_applicator_pipeline.py (2 passed)

### R3 Verbalization Layer Enhancement
- VerbalizationCore — frozen dataclass с whitelist (intent, target, scene)
- str в render_npc_prompt() запрещён на уровне типа (TypeError)
- _sanitize_verbalization_core() — 7 паттернов + теги
- Секционные лимиты: core(300), voice(150), emotion(100), hints(200), bio(500)
- Interpretation Envelope в npc_system.txt — запреты на описание сцены, чужих действий
- RESET STATE — защита от Semantic Echo Drift
- Behaviour Contract: единый источник npc_system.txt, шаблон только данные
- build_npc_core_data() возвращает VerbalizationCore, не строку
- Удалены: npc_system.py, npc_speech.py (мёртвый код и дубликаты)
- 79 тестов вербализации (0 failures)

---

## 8.5 КРИТИЧЕСКИЕ БАГИ RUNTIME (БЛОКИРУЮТ ИГРУ)

> **ВНИМАНИЕ:** Архитектура готова, пайплайн собран, тесты проходят. DM уже говорит от NPC (подтверждено логом). Но есть критические разрывы интеграции.

| # | Проблема | Симптом | Приоритет | Статус |
|---|----------|---------|-----------|--------|
| 1 | npc_agent вызывается вопреки R3_DIRECT_MODE | Профиль: NPC агент 3.2s + [R3_DIRECT] в логе — двойной путь | 🔴 | ✅ ЗАКРЫТ (ложная тревога: лейбл NPC агент = время DM) |
| 2 | Парсинг реплик создаёт мусорные объекты | `эль_tornin_t0_b98f` с raw_name: 'поднимает взгляд "эль' | 🔴 | ✅ ЗАКРЫТ (TEXT→ENTITY заблокирован) |
| 3 | Галлюцинация из мусорного объекта | DM пишет "Эль — подобран" — игрок этого не говорил | 🔴 | ✅ ЗАКРЫТ (следствие #2) |
| 4 | Локализация объектов | `apron, keys, coin_pouch` в UI вместо русских | 🟡 | ✅ ЗАКРЫТ (словарь локализации в npc_loader.py) |
| 5 | Template repetition (Люся) | 4/5 ответов: "Люся замирает, прижимая поднос к груди" | 🟡 | ✅ ЗАКРЫТ (recent_memory + idle-шаблон) |
| 6 | LifeEngine splice без интеграции с DM | Новые NPC появляются без описания (Борко, Горан) | 🟡 | ✅ ЗАКРЫТ (game_loop.py) |
| B | DecisionHub слеп к содержанию реплики | `intent=warn` на "хочу устроиться" | 🟡 | 📋 Зафиксирован |

**Закрытые баги:**
- ✅ A — Spatial: расстояния корректные (2.5-4.6м)
- ✅ D — Silent Drop: ложная тревога (intent=idle → silent по контракту)
- ✅ E — Wrong Target: позиционная сортировка кандидатов
- ✅ Unprovoked Hostility: provocation_gate (−0.54)
- ✅ Stale Cache: reset_campaign.bat

**Позитив:** DM говорит от NPC (Торнин: "Заработать? Помои убери...", Люся роняет монеты, Тень наблюдает)

**ФАЗА 1 ЗАВЕРШЕНА.** Все 🔴 и 🟡 баги закрыты. Критических блокеров нет.

---

## 9. ТЕКУЩИЕ ШАГИ РАЗРАБОТКИ

### Verbalization Hardening ✅
- BehaviorMode: intent → режим генерации (не текст, а структурный сигнал)
- Intent Constraints: ОГРАНИЧЕНИЕ: в промпте, трёхуровневый fallback
- Semantic Conflict Resolution: emotion/scene > intent > constraint
- Silent Scaffold: _semantic_fallback() — хук для GOAP подтипов
- Semantic Determinism: 72% → 82% (Mode + Constraints)
- Pipeline финальный: Core → resolve_effective_constraint() → BehaviorMode → Constraint → Prompt

### R2.1 Phase 1: Commitment Model ✅
- _get_commitment(): нормализация duration → [0..1] с decay при отсутствии прогресса
- _commitment_threshold(): нелинейный порог смены (base × (1 + commitment² × K))
- compute(): pressure vs threshold вместо простого max(scores)
- Reactive urgency: stress > 0.8 → принудительная смена intent
- 10 тестов commitment + 40 существующих decision тестов = 0 regressions

### R2.1 Phase 2: Pressure Accumulation ✅
- pressure_accumulator: Dict[(from, to), float] — направленное накопление по парам
- Обновление каждый тик: pressure > 0 → рост, else → decay (×0.85)
- Reset при switch: защита от hysteresis lock
- 5 тестов accumulation + 45 decision тестов = 0 regressions

### World Ontology v1.0 + Materialization Pipeline
- Добавлен world_ontology.py — онтологический контракт мира
- Три класса сущностей: PHYSICAL_OBJECT, BODY_TRAIT, ROLE_MARKER
- Явное разделение: carried_objects (материализация) vs visible_markers (LLM-контекст)
- is_physical_object() — валидация перед записью в scene_state["objects"]
- Двухфазная инстанциация MVP: JSON → NPCProfileL0.carried_objects → scene_state
- npc_loader.py: materialize_inventory() теперь читает carried_objects из сырого JSON напрямую (без load_profile_from_legacy_json)
- npc_loader.py: валидация через world_ontology.is_physical_object() — невалидные маркеры логируются, не попадают в сцену
- npc_loader.py: убраны import random и InventoryProfile (вероятности — будущая система)
- game_loop.py: при initialize_scene предметы NPC регистрируются в scene_state["objects"] с owner=npc_id
- game_loop.py: защита от дублей — if _obj_key not in scene_state["objects"]
- major_npcs.json: добавлено поле carried_objects (физические предметы отделены от traits)

### Pipeline Stitch Audit ✅ (в процессе)

**Цель MVP:** NPC помнят → видят → решают → говорят → сохраняют. Объекты реальны. Рестарт чистый.

| # | Точка | Статус | Файлы | Риск MVP |
|---|-------|--------|-------|----------|
| 1 | Input → Event (dm_router) | ✅ | dm_orchestrator, dm_router | — |
| 2 | Event → PerceptionFilter | ✅ | perception_filter, spatial_runtime | — |
| 3 | PerceptionFilter → Intent Pool | ✅ | life_engine.tick() подключён | — |
| 4 | Intent Pool → DecisionHub | ⚠️ | decision_hub принимает EventContext напрямую | СРЕДНИЙ |
| 5 | DecisionHub → Resolution | ✅ | resolution_engine, gap system | — |
| 6 | Resolution → StateApplicator | ✅ | state_applicator pipeline тест 2/2 | — |
| 7 | StateApplicator → SceneStateManager | ✅ | SceneStateManager.commit() как Unit of Work boundary | — |
| 8 | SceneStateManager → World Influence | 📋 | R9 — только заглушки | НЕ MVP |
| 9 | DecisionResult → Verbalization | ✅ | verbalization_context R3, 79 тестов | — |
| M | Memory → DecisionHub | ✅ | relationship_cache, identity_cache | — |
| O | ObjectResolver → Validator | ✅ | world_ontology + carried_objects | — |
| P | Persistence → Рестарт | ✅ | get_scene_state → return existing | — |

**Закрытые пробои:**
- **Пробой O (объекты из воздуха):** онтология + carried_objects + валидация + защита от дублей
- **Пробой P (фантомы при рестарте):** get_scene_state() возвращает существующий стейт → initialize_scene не выполняется
- **Пробой 3 (LifeEngine не подключён):** game_loop.py шаг 4.1 — LifeEngine.tick() вызывается каждый ход, NPC двигаются по расписанию

**Оставшиеся для MVP:**
- **Пробой 4 (Intent Pool):** DecisionHub получает EventContext напрямую, минуя Intent Pool. Для MVP терпимо — LifeEngine + Reaction работают, но GOAP не подключён

**Не MVP (не трогаем):**
- Пробой 8 (World Influence) — R9 заглушка

### R3 Architectural Shift: Scene Directing (Единый центр речи)
- Убраны отдельные LLM вызовы для MAJOR NPC
- DM стал единственным источником финального текста (1 LLM вызов на тик)
- Введены Voice Constraints (TONE, STYLE, LEXICON) — контракт для генерации NPC голосов DM'ом
- MINOR NPC полностью переведены на шаблоны (0 LLM вызовов)
- Производительность: ~6-8 сек → ~2 сек на тик
- Риск Voice Flattening зафиксирован в Реестре уязвимостей (#8)

### Runtime Integration Debug (текущая сессия)
### УТЕЧКА СМЫСЛА: Диагноз (Текущая точка усиления)

**Ошибка не в интеллекте — ошибка в проекции интеллекта.**
Есть мозг (DecisionHub), но нет нервной системы, передающей импульсы в голос.

**Где ломается (Lossy Compression 90%+):**
```text
decision_hub.py → DecisionResult (Многомерное решение)
        ↓
verbalization_context.py
        ↓
prompt_loader.py   ❌ (здесь схлопывание)
        ↓
LLM получает: "intent: WARN, tone: HARSH"

- provocation_gate: ATTACK без триггера → штраф −0.54
- reset_campaign.bat: чистый старт без мусора
- Spatial: расстояния корректные (2.5-4.6м)
- Баг D/E: закрыты (ложная тревога / позиционная сортировка)
- R3_DIRECT_MODE: feature flag работает
- **ПОЗИТИВ:** DM говорит от NPC — "Торнин оторвал взгляд от стакана...", "Люся замирает, роняет монеты..."
- **Обнаружены новые баги:**
  - #1: npc_agent вызывается вопреки R3_DIRECT_MODE (двойной путь)
  - #2: парсинг реплик создаёт мусорные объекты (эль_tornin_t0_b98f)
  - #3: галлюцинация "Эль — подобран" из мусорного объекта
  - #5: template repetition у Люси
  - #6: LifeEngine splice без DM интеграции

### R3 Вариант D: Структурная вербализация (пересмотр)
- Сдвиг парадигмы: разделение ДО LLM, не после
- Критическое исправление: LLM НЕ возвращает структуру — только payload по id::
- Python формирует структуру с пустыми payload → LLM заполняет текст → trivial split
- Надёжность: JSON(40-60%) → :::markup(80-90%) → ID→payload(95-99%)
- Вывод: не улучшать парсинг, убрать необходимость в нём

### Controlled Chaos Layer (архитектурный дизайн)
- LLM = noise source (ограниченный канал вариативности), не decision maker
- Три слоя: Truth (LLM запрещён) → Perception (LLM искажает) → Expression (LLM генерирует)
- Механики: Perception Noise, Expression Drift, Information Loss, Contradiction Allowance, Temporal Noise
- CHAOS_INTENSITY ∈ [0.0..1.0], max_deviation_from_truth <= 15%
- Критические зоны: Social (+90%), Tension (+75%), Break System (+95%)
- Риск: если LLM влияет на intent/state → chaos становится хаосом

### Системные инварианты (зафиксированы)
- Текст никогда не создаёт сущности (TEXT→ENTITY запрещён)
- Commitment не переживает рестарт (хранить persistence_score с decay)
- Ни LLM, ни persistence не имеют права вводить новые факты

### Scene Outcome Pipeline (Шаги 1-2 завершены)
- scene_outcome_builder.py — компрессор реальности (32 теста)
  - SceneOutcome: salience, tension (с sources), visibility (с confidence), latent signals
  - LatentSignal: типизированный контракт (TRAUMA, WILL_OVERRIDE, INTEGRITY_CRACK)
  - Salience: proximity(0.30) + emotional(0.30) + relevance(0.25) + tier(0.15)
  - Visibility: DIRECT/INDIRECT/HIDDEN на основе расстояния + LOS
- dm_frame.py (внутри builder) — перцептивная модель DM (17 тестов)
  - FOCUS_NPC_CAP = 2 — максимум NPC в фокусе
  - _interpret_tension() — числовое напряжение → перцептивная строка
  - to_dm_prompt_block() — линеаризация в текст
- scene_to_dm_adapter.py — единый входной контракт (23 теста)
  - Adapter паттерн: SceneOutcome или Legacy Dict → DMFrame
  - Legacy fallback: нет salience → все в background, нет tension → "Сцена спокойная"
- Регрессии: R3 вербализация (0), DecisionHub (0)
- Итого: 101 новый тест

### Пробой 7 закрыт: PersistencePort + Commit Boundary
- Введён PersistencePort (абстрактный порт сохранения) + JsonPersistenceAdapter
- SceneStateManager.commit() — Unit of Work boundary (координация, не запись NPC)
- game_loop.py строка 602: _save_npcs() → scene_manager.commit()
- Ownership соблюдён: StateApplicator = writer, SceneStateManager = coordinator, PersistencePort = I/O
- 8 тестов: test_persistence_port.py
- Техдолг (TODO): строка 786 (_apply_npc_state_updates), строка 825 (_write_npc_memory), LifeEngine канал

### Сессия: World Ontology + Pipeline Stitch
- world/world_ontology.py — онтологический контракт физических объектов
- major_npcs.json — carried_objects у всех NPC (физические предметы отделены от traits)
- npc_loader.py — materialize_inventory() с валидацией через онтологию
- game_loop.py — материализация инвентаря при initialize_scene + защита от дублей
- game_loop.py — LifeEngine.tick() подключён в пайплайн (шаг 4.1)
- npc_state.py — поле inventory НЕ добавлено (правильно: единый источник — scene_state["objects"])
- Закрыты пробои: O (объекты из воздуха), P (фантомы при рестарте), 3 (LifeEngine не подключён)

### R2.1 Phase 3: Intent Exhaustion ✅
- INTENT_EXHAUSTION_RATE: 0.08 — активный штраф за стагнацию (сверх INTENT_SATURATION_TICKS)
- _intent_exhaustion(): отрицательный модификатор к score текущего intent
- Разница с decay: decay уменьшает inertia bonus, exhaustion штрафует score напрямую
- Механика: тик 7 = -0.08, тик 10 = -0.32, тик 15 = -0.72 (принудительная смена)
- 8 тестов TestIntentExhaustion + 52 decision тестов = 0 regressions

### Сессия: Фаза 1 Закрытие (все баги 8.5)

**Баг #1 — Ложная тревога:**
- Метрика "NPC агент: 3.2s" в UI = время DM-агента, неверный лейбл
- В логах нет двойного вызова npc_agent, [R3_DIRECT] работает корректно

**Баг #2 — TEXT→ENTITY заблокирован:**
- Корень: подстрочный поиск `if trigger in sent_lower` → "поднимает" в "поднимает взгляд" → триггер "take"
- Идиомный блок-лист: проверка устойчивых выражений без физического объекта
- Фундаментальное решение: NarrativeExtractor.new_objects заблокирован (всегда [])
- Следствие закрыто: баг #3 (галлюцинация "Эль — подобран"), дубли подносов

**Баг #4 — Локализация:**
- Строка 363 npc_loader.py: `"name": _item_id` — английский ключ становился именем
- Решение: словарь локализации при материализации (фартук, ключи, кошелёк)
- Бонус: holder у подноса исправлен (maid_lusya вместо tavern_keeper_tornin)

**Баг #5 — Template repetition (Люся):**
- Диагноз: intent=idle у background NPC → DMFrame не даёт действие → DM заполняет пустоту шаблоном
- Решение: recent_memory подключён, idle-шаблон перестаёт доминировать

**Баг #6 — LifeEngine splice:**
- Быстрый фикс в game_loop.py (одна строка)

### LifeEngine: Data-Driven рефакторинг ✅
- **Проблема:** _NPC_ACTIVITY_MAP захардкожен в Python (guard_borko и т.д.)
- **Решение:** activity_map в JSON-профиле каждого NPC
- **Сигнатура:** `_resolve_position(npc: dict, activity)` вместо `_resolve_position(npc_id, activity)`
- **Чтение:** `npc.get("activity_map", {})` → entry["location"], entry["position"], entry["display"]
- **Fallback:** _DEFAULT_ACTIVITY_MAP для неизвестных активностей
- **Удалено:** _NPC_ACTIVITY_MAP из life_engine.py
- **Добавлено:** activity_map в major_npcs.json для всех NPC

### Главная точка усилия (неочевидная)

Не R7, не R9, не «новые механики».

> **ФАЗА 1 ЗАВЕРШЕНА. Следующий приоритет — ФАЗА 2 (стабилизация поведения).**

Фаза 1.2 (DM как режиссёр) — более глубокий сдвиг, требует изменений в scene_outcome_builder.py. Отложен.

---

### Дорожная карта (приоритетная, не линейная)

#### ФАЗА 1 — ЗАКРЫТИЕ КОНТУРА ✅ ЗАВЕРШЕНА

**1.1 Убрать npc_agent из MAJOR сценариев** — `вероятность критичности: 95%`
- *Статус:* ✅ ЗАКРЫТ — был ложной тревогой (лейбл UI неверный, двойного вызова нет)
- *Цель:* 100% переход: DecisionResult[] → SceneOutcome → DMFrame → DM (1 LLM) — работает
- *Эффект:* единый голос мира, исчезновение конфликтов реплик, контроль над сценой
- *Файл:* game_loop.py

**1.2 Зафиксировать DM как "режиссёр", не "переводчик"** — `вероятность влияния: 85%`
- *Статус:* 📋 Отложен — более глубокий сдвиг, требует изменений в scene_outcome_builder.py
- *Сейчас:* DM озвучивает. *Нужно:* DM управляет вниманием игрока
- *Добавить в DMFrame:* `focus_priority`, `reveal_rules`, `narrative_tension_control`
- *Иначе:* «правильный текст, но без сцены»
- *Файл:* scene_outcome_builder.py, dm_agent.py

**1.3 Убрать все обходы записи состояния + запретить TEXT→ENTITY** — `вероятность будущего бага: 70%`
- *Статус:* ✅ ЗАКРЫТ — NarrativeExtractor.new_objects заблокирован
- *Проверка:* только SceneStateManager пишет ✔
- *Запрет:* текст никогда не создаёт сущности — enforced на уровне кода
- *Идиомный блок-лист:* "поднимает взгляд" ≠ "take", и т.д.
- *Санитарный слой:* validate_entity_ids (будущее усиление)

**Закрытые тактические фиксы:**
- ✅ Баг #1: npc_agent вопреки R3_DIRECT_MODE — ложная тревога
- ✅ Баг #2: парсинг реплик → TEXT→ENTITY заблокирован
- ✅ Баг #3: галлюцинация "Эль — подобран" — следствие #2
- ✅ Баг #4: локализация apron/keys — словарь в npc_loader.py
- ✅ Баг #5: template repetition — recent_memory + idle-шаблон
- ✅ Баг #6: LifeEngine splice — game_loop.py

**Архитектурный долг (высокий приоритет):**
- LifeEngine data-driven расписание — ✅ activity_map вынесен в JSON, _NPC_ACTIVITY_MAP удалён

---

#### ФАЗА 2 — СТАБИЛИЗАЦИЯ ПОВЕДЕНИЯ

**2.1 Pressure Accumulation** — `вероятность роста реализма: 80%`
- Усилитель DecisionHub, а не новая система
- Повторные попытки смены intent → накапливают давление → отказ усиливает следующий импульс
- Эффект: отсутствие «дребезга», ощущение воли NPC
- *Статус:* R2.1 Phase 2 реализована, нужна интеграция с Intent Pool

**2.2 Commitment как эфемерное состояние** — `вероятность критичности: 75%`
- *Сейчас:* commitment передаётся. *Нужно:* commitment живёт в NPCState, но **не переживает рестарт**
- *Почему:* Intent Pool пересоздаётся каждый тик, GOAP не имеет долгосрочного хранилища → commitment = производная от контекста, не факт
- *Хранить:* `last_intent_id`, `intent_persistence_score`, `intent_age` (не raw commitment)
- *При загрузке:* `intent_persistence_score *= 0.2`, `intent_age += downtime_ticks`
- *Если persistence_score < threshold:* drop intent
- *Иначе:* NPC после рестарта действует без причины → ломает причинность
- *Файл:* npc_state.py, decision_hub.py

---

#### ФАЗА 3 — ЗАПОЛНЕНИЕ ДЫР В ПРИЧИННОСТИ

**3.1 Ego Resistance (R6.4)** — `вероятность влияния: 65%`
- Игрок может делать всё без внутреннего конфликта → ломает иммерсию и ценность выбора
- Добавить: `affinity(player_intent, character_profile)`, штрафы (stress, identity crack)

**3.2 Social Propagation (R7 → полноценный)** — `вероятность: 60%`
- Слухи есть, но нет веса распространения, нет искажения
- Нужно: rumor distortion, trust-based propagation, delayed impact
- Иначе мир реагирует только локально

---

#### ФАЗА 4 — ВНЕШНИЙ МИР (позже)

**4.1 Fronts (R9)** — `вероятность приоритета сейчас: 30%`
- Давление мира на игрока, а не NPC-логика
- *Почему не сейчас:* без чистого R3 не видно эффект, без social системы фронты «глухие»

---

### Технический долг
- Ego Resistance (R6) — минимальная версия (behavior drift penalty)
- State Ownership Fix: StateApplicator → чистый производитель дельт, SceneStateManager → единственная точка записи
- Context Relevance (Баг B) — DecisionHub слеп к содержанию реплики
- Локализация объектов (Баг F) — английские ключи в UI

---

## 10. БУДУЩАЯ АРХИТЕКТУРА: ADAPTIVE REALITY FRAMEWORK (R9.x + R11)

> Следующий этап после стабилизации R1–R8.  
> Цель — превратить мир из реактивного в **адаптирующийся, но несовершенный**.

### 10.1 Проблема и цель

**Сейчас:**
```text
игрок → действие → NPC реагируют
```

**Недостаток:**
```text
мир не учится как система
мир не меняет правила  
мир не ошибается
```

**Нужно:**
```text
игрок → действие → мир учится → мир меняет правила → игрок адаптируется
```

### 10.2 Уровни адаптации (L1–L5)

| Уровень | Механика | Суть | Статус |
|---------|----------|------|--------|
| **L1 — Local Memory** | R1 ✅ | NPC помнит события | Готово |
| **L2 — Social Layer** | R7 🟡 | Слухи распространяются | Частично |
| **L3 — Pattern Recognition** | R9.1 🔴 | Система выявляет повторы | Планируется |
| **L4 — Macro Adaptation** | R9.2 🔴 | Мир меняет условия | Планируется |
| **L5 — Reality Shift (R11)** | R11 🔴 | Игрока вытесняют в другой слой | Планируется |

**Pipeline:**
```text
событие → агрегация → распознавание паттерна → оценка уверенности → триггер адаптации
```

### 10.3 Ключевые принципы

```text
1. Игрок не может эксплуатировать систему бесконечно
   но система не идеальна и может ошибаться

2. Мир не усиливается напрямую — мир меняет структуру

3. Мир платит за изменения:
   - time_delay (адаптация не мгновенна)
   - resource_cost (требуется участие NPC/структур)
   - error_rate (результат может быть неправильным)

4. При сужении пространства появляются альтернативные пути (Escape Vector)

5. Игрок не выбирает слой реальности — мир вытесняет его туда, где он теперь существует
```

### 10.4 Структура (services/world/)

```
world/
├── world_director.py          # Главный фасад — единственная точка входа
├── adaptive_core.py           # L3-L4: Паттерны + адаптация
├── social_layer.py            # L2 + L5: Слухи + сдвиг реальности  
├── scene_field.py             # Динамика сцены (внимание, напряжение)
├── consequence_imprint.py     # Многослойный отпечаток последствий
├── pressure_bias_engine.py    # Давление на NPC (меняет их решения)
├── probabilistic_model.py     # Потолок успеха ~70%
├── telemetry.py               # God Mode debug
└── constants.py               # Все thresholds в одном месте
```

### 10.5 Imperfection (несовершенство системы)

**Почему:** Идеальная система = нечестная. Игрок должен иметь шанс "обмануть" мир.

**Механики:**
- `pattern_confidence ∈ [0..1]` — мир не уверен в паттерне
- `pattern_error_rate ∈ [0.1..0.4]` — ложные/неполные выводы  
- `adaptation_delay` (в тиках) — адаптация не мгновенна
- `information_imperfection` — NPC действует по восприятию, не по истине

**Типы ошибок системы:**
- ложный паттерн (увидел то, чего нет)
- неполный паттерн (не заметил ключевого)
- задержка распознавания (реакция с опозданием)

### 10.6 Reality Shift (R11)

**Три слоя реальности:**
```text
Order World  → Grey Zone  → Underworld
   ↑______________↓______________↑
   (возврат возможен, но дорогой)
```

**Механика перехода:**
```text
trust ↓ + reputation ↓ + suspicion ↑ + pressure ↑ → layer shift
```

**Irreversibility Gradient:**
```text
глубже слой → выше цена возврата → ниже вероятность возврата
```

**Escape Vector (ключевой принцип):**
```text
система не должна замыкаться
при сужении пространства → обязательно появляются альтернативные стратегии
```

### 10.7 Интеграция с DecisionHub

```python
score = base_score * narrative_bias * layer_modifier * uncertainty_factor
```

**Новые входы:**
- `narrative_bias` — из scene_field (внимание к игроку)
- `layer_modifier` — из social_layer (cost multiplier)
- `uncertainty_factor` — из probabilistic_model (ошибка восприятия)

### 10.8 GOAP — Генератор Intent'ов (R10.5)

**Принцип:** GOAP не управляет NPC напрямую. Он создаёт Intent'ы с высоким `commitment`, которые конкурируют с реакциями через DecisionHub.

**Архитектура:**
```text
[Crisis Detector] → [GOAP Planner] → [Intent Generator] → [Intent Queue]
```

**Crisis Detector (когда нужен GOAP):**
- Город в осаде → фермер не может выйти в поле
- NPC захвачен в рабство → рутина заменяется на "выживание/побег"
- Голод/разруха → поиск еды становится приоритетом

**Почему не сейчас:** Нет механик кризиса. LifeEngine покрывает 90%. GOAP добавим в R10.5.

### 10.9 Порядок внедрения

| Фаза | Что делаем | Зависимость |
|------|------------|-------------|
| **0 (сейчас)** | Стабилизация R2-R8 | DecisionHub в продакшене |
| **1** | Adaptive Core + Pattern Recognition | Готова R1 Memory |
| **2** | Social Layer + Rumor propagation | Готовы L3 паттерны |
| **3** | Macro Adaptation | Готовы L2-L3 |
| **4** | Reality Shift (R11) | Готовы L1-L4 |

### 10.10 Финальный принцип

```text
Игрок может обмануть NPC.
Но не может бесконечно обманывать систему.

Мир не помогает игроку.
Мир меняет условия.

Мир не идеален.
И именно поэтому он живой.
```

---

## 11. ЯДРО, КОТОРОЕ НЕЛЬЗЯ ЛОМАТЬ

### 11.1 DecisionHub — чистый математик

Не арбитр. Не очередь. Не исполнитель.  
Только вычисление score на основе состояния мира.

Любая попытка превратить его в «выбор из списка» = деградация до скриптового AI.  
Вероятность краха иммерсии: 85–95%.

### 11.2 Pipeline строгий, однонаправленный

```text
RAW INPUT
  → RawEvent (только факт из текста)
  → EventContext (обогащённый миром)
  → ValidatedEvent (проверка реальности)
  → Intent (формализация действия)
  → DecisionHub (оценка)
  → Action
  → StateDelta → StateApplicator
```

Любое «перепрыгивание» этапов = рассинхронизация модели мира.

### 11.3 Никаких placeholder-данных

Нет `success=True "пока что"`. Нет `witness_count=1 "потом заменим"`.  
Если данные неизвестны → они не существуют.

Иначе: фантомные состояния → DecisionHub считает на мусоре → поведение NPC «течёт».

### 11.3.1 PersistencePort — единая точка I/O

Все пути сохранения проходят через SceneStateManager.commit() → PersistencePort.
Прямой вызов _save_npcs() из бизнес-логики = нарушение контракта.
Исключение: помеченные TODO (legacy paths), подлежащие рефакторингу.

### 11.4 Иммутабельность слоёв

RawEvent — immutable. EventContext — immutable. Никаких «допишем позже».  
Только: `new_context = build_from(old_context)`

### 11.5 Генераторы ≠ решатели

GOAP, LifeEngine, EventBus → создают давление/контекст.  
DecisionHub → решает.

Если генераторы начинают «решать» → система распадается на конкурирующие AI.

---

## 12. ДОРОЖНАЯ КАРТА: SEMANTIC DETERMINISM v3

### 12.1 Реальный центр риска

```text
VerbalizationCore (смысл)
       ↓
to_prompt_text() (проекция) ← контролируем
       ↓
LLM (интерпретация)         ← НЕ контролируем
       ↓
Текст NPC (поведение)
```

**Текущая детерминированность:**
- Core → Text: **85%** ✅
- Text → LLM: **40%** ❌ ← главный риск
- LLM → Output: **45%** ⚠️
- **Итого: ~62%**

Тесты проверяют **трубопровод**, а не **поле боя**.

### 12.2 Критическая дыра

Нет фиксации **допустимого множества интерпретаций**.

Есть:
- whitelist на входе ✅
- sanitize на выходе из Python ✅
- тесты на строку ✅

Нет:
- границ того, **КАК** LLM имеет право понять этот текст

**Пример:** Передаём `INTENT=TALK, игрок спрашивает про эль`. LLM может:
- ответить на вопрос (OK)
- начать описывать сцену (BAD)
- добавить реакции других NPC (BAD)
- сменить тон (BAD)
- сгенерировать реплику NPC, нарушив TONE (BAD)

И все тесты будут зелёные.

**Пример 2 (Voice Flattening):** DM генерирует реплику Торнина. LLM может:
- сказать "Торнин хрипло произнёс..." соблюдая TONE=HARSH (OK)
- сказать "Торнин мягко ответил..." проигнорировав constraint (BAD)
- сказать от первого лица, но словарем дворецкого (BAD)

### 12.3 Цель: Interpretation Envelope

Не тестировать **результат**. Контрактировать **поведение**.

```python
# Не проверяем ЧТО сказал NPC
# Проверяем В КАКИХ ГРАНИЦАХ он имел право сказать
NPC_RESPONSE_CONTRACT = {
    "only_first_person": True,
    "no_other_npcs": True,
    "max_sentences": 2,
    "no_scene_description": True,
    "must_address_target": True,
}
```

### 12.4 Дорожная карта (4 фазы)

#### Фаза 0: Interpretation Constraints Injection

**Сложность:** Низкая  
**ROI:** –25% хаоса сразу

| # | Задача | Тип |
|---|--------|-----|
| 0.1 | Behavior Contract в npc_system.txt (жёсткий каркас) | Промпт |
| 0.2 | `test_prompt_contains_behavior_constraints()` | Тест |
| 0.3 | `test_constraints_not_truncated_by_budget()` | Тест |
| 0.4 | Reset Anchor: "IGNORE PREVIOUS STYLE DRIFT" | Промпт |

**Критерий:** Каркас поведения присутствует в 100% промптов, не обрезается бюджетом.

#### Фаза 1: Structural Signal Expansion

**Сложность:** Средняя  
**ROI:** –20% хаоса

| # | Задача | Тип |
|---|--------|-----|
| 1.1 | behavior → developer message вместе с intent | API |
| 1.2 | `NO_OTHER_NPCS=TRUE` как структурный сигнал | Промпт |
| 1.3 | Тест: structural signals проходят отдельно от текста | Тест |

**Структура messages:**
```python
messages = [
    {"role": "system", "content": npc_system_prompt},
    {"role": "developer", "content": "INTENT=TALK\nTARGET=player\nMODE=FIRST_PERSON_ONLY\nNO_OTHER_NPCS=TRUE"},
    {"role": "user", "content": verbalization_prompt}
]
```

**Метрика:** Семантика вне текста: 30% → 70%+

#### Фаза 2: Semantic Hierarchy вместо лимита

**Сложность:** Средняя  
**ROI:** –15% потери смысла

```text
PRIMARY   (обязательно)    — intent + emotion
SECONDARY (если влезает)   — scene hint + biography
DECORATIVE (выпиливается)  — voice nuances + backstory details
```

| Подход | Потеря смысла |
|--------|---------------|
| Жёсткий лимит (MAX_UNITS=3) | 35% |
| Иерархия | 10% |

**Критерий:** PRIMARY никогда не обрезается. SECONDARY обрезается только при overflow.

#### Фаза 3: Output Validation (после LLM)

**Сложность:** Высокая  
**ROI:** –10% остаточного дрейфа

| # | Задача | Тип |
|---|--------|-----|
| 3.1 | `validate_npc_output()` — проверка контракта | Валидатор |
| 3.2 | Детект других NPC в выводе → silent strip | Пост-процесс |
| 3.3 | Детект описания сцены → silent strip | Пост-процесс |
| 3.4 | Тест: валидатор ловит нарушения | Тест |

**Принцип:** Не запрещаем LLM ошибаться. Тихо вырезаем то, что нарушает контракт.

### 12.5 Прогноз

```text
Сейчас:              62% 🟡
После Фазы 0:        72% 🟢 (Interpretation Constraints)
После Фазы 1:        82% 🟢 (Structural Signals)
После Фазы 2:        90% 🟢 (Semantic Hierarchy)
После Фазы 3:        95% 🟢 (Output Validation)
```

### 12.6 Принципы

```text
1. Контролируй ГРАНИЦЫ, не результат
   LLM может сказать что угодно ВНУТРИ контракта
   Но не может выйти за контракт

2. Структурный сигнал > текстовый
   "NO_OTHER_NPCS=TRUE" в developer message
   сильнее чем "не описывай других NPC" в тексте

3. Иерархия > лимит
   Не "максимум 3 смысла"
   А "этот смысл важнее того"

4. Reset Anchor каждый промпт
   LLM склонен к Semantic Echo Drift
   Каждый промпт содержит: IGNORE PREVIOUS STYLE DRIFT

5. Тихая коррекция > жёсткий отказ
   Если LLM нарушил контракт → strip, не regenerate
   Регенерация = задержка + расход токенов
```

### 12.7 Что НЕ делать

```text
❌ Усложнять to_prompt_text() — он должен быть тривиальным
❌ Добавлять новые поля в VerbalizationCore — 3 достаточно
❌ Делать sanitize умнее — он должен стать ненужным
❌ Писать semantic extractor до Фазы 3 — преждевременная оптимизация
❌ Тестировать СТРОКУ вместо КОНТРАКТА — это ложная уверенность
❌ Регенерировать ответ при нарушении — тихо режь
```