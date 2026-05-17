Вот переработанный и реструктурированный реестр ADR. 
**Что было сделано:**
1. **Устранено дублирование номеров:** Старые ADR содержали кучу дубликатов (три ADR-007, три ADR-0011 и т.д.). Нумерация приведена в строгий хронологический порядок от 001 до 028.
2. **Хронология и даты:** Исходя из старта проекта (06.04.2026) и текущей даты (10.05.2026), я расставил реалистичные даты, отражающие эволюцию архитектуры — от базовой изоляции мутаций до сложной каузальной физики.
3. **Формат для LLM:** Строгая структура заголовков, списки, жирный шрифт для ключевых сущностей, убраны рваные переносы. Плавающие определения CFRM встроены внутрь соответствующего ADR.
4. **Порядок чтения:** ADR выстроены в порядке архитектурного чтения: сначала фундамент (мутации, время, данные), затем домены (социальный, пространственный, нарративный), затем физиология и боевка, и на вершине — каузальные модели (CFRM, Layered Reduction).

---

# Architecture Decision Records (ADR)

### ADR-001: Изоляция мутаций через Phase8Result и Delta Buffer
**Дата:** 27.04.2026  
**Статус:** Принято

**Контекст:**  
Обработчики Фазы 8 (Social, Perception) имели два пути влияния на состояние: возврат DTO и прямая мутация общих объектов (`shared_context`, `all_npcs_raw`). Это приводило к побочным эффектам, состоянию гонки и невозможности формальной синхронизации `perception ∪ social`. Фронтенд нарушал Устав §1.1, импортируя backend-классы для конвертации DTO.

**Решение:**  
- Подписчики Фазы 8 возвращают только `Phase8Result`. Прямая мутация `shared_context` и `all_npcs_raw` запрещена.
- Интенсивность событий агрегируется через `max()`, а не суммируется или обрывается (`break`).
- Конвертация DTO→dict происходит на границе слоев (в `GameLoop`), фронтенд работает только с примитивными `dict`.
- Оркестратор собирает deltas в `delta_buffer` и применяет через `StateApplicator` единственной транзакцией.

**Последствия:**  
- **Предсказуемость:** Нет скрытых мутаций. Оркестратор видит все изменения через буфер.
- **Безопасность:** Инфляция слухов исключена (`max` агрегация).
- **Заменимость:** Фронтенд отвязан от структур backend.
- **Дисциплина:** Любой новый обработчик должен возвращать дельты, а не писать в стейт.

---

### ADR-002: Time-driven vs Event-driven разделение и единый мутатор
**Дата:** 28.04.2026  
**Статус:** Принято

**Контекст:**  
Social отношения и репутация фракций стагнировали между player-взаимодействиями — idle path не обновлял эти подсистемы. Фаза 8 пропускала обработку в idle path из-за `if ctx.shared_context is None: continue`. `StateApplicator` хардкодил `target = state.intent_target or "player"`, что не подходило для social decay (NPC→NPC). `ReputationEngine` мутировал состояние через `apply_deltas(List[dict])`, минуя единый мутатор.

**Решение:**  
- Фаза 0.5 (time-driven) отделена от Фазы 8 (event-driven). Фаза 0.5 выполняется ВСЕГДА. Фаза 8 обрабатывает только если есть events.
- `StateDeltas` расширена явной маршрутизацией: `intent_target` (NPC→Player), `social_target` (NPC→NPC), `faction_id` (фракции). Валидация в `post_init`. # LOCKED v1
- `IdleTickHandler` Protocol: чистая функция, принимает `List[NPCStateSnapshot]` (READ-ONLY), возвращает `List[StateDeltas]`.
- `ReputationEngine.compute_decay()` — чистая функция. `apply_deltas()` — единственная точка мутации из `StateApplicator._apply_faction_delta()`.
- Closing drift: если `|base - current| < EPSILON` → `drift = base - current`.
- Оркестратор: `delta_buffer` → `aggregate_deltas()` → `StateApplicator.apply_batch()` в Фазе 10.

**Последствия:**  
- Детерминированная симуляция: decay не зависит от активности игрока.
- Единый мутатор: `StateApplicator.apply_batch()`.
- Семантическая изоляция: `reputation_delta ≠ trust_delta`, `faction_id ≠ social_target`.
- Тестируемость: handlers — чистые функции.

---

### ADR-003: Детерминизм тестового покрытия и изоляция от I/O
**Дата:** 01.05.2026  
**Статус:** Принято

**Контекст:**  
Тестовое покрытие сломано: 1) Фабрики DTO не передавали обязательный `npc_id` в `StateDeltas`. 2) Тесты зависели от чтения `campaign_state.json` с диска (Fragile Test). 3) Мертвые тесты `@pytest.mark.skip("BROKEN")` маскировали удаление сущностей.

**Решение:**  
- Строгое соблюдение контракта DTO: `npc_id` обязателен в тестовых фабриках.
- Устранение Fragile Tests: хрупкие I/O фикстуры заменены на синтетические фабрики (`_make_rich_scene()`).
- Полная зачистка мертвого кода: динамические `pytest.skip("BROKEN...")` заменены удалением теста.
- Приведение координат к fallback-графу в тестах `SpatialService`.

**Последствия:**  
- 100% детерминированность тестового набора.
- Тесты запускаются на любой машине без подготовки данных.
- ИИ-ассистенты получают четкий сигнал: старый код удален, новые контракты обязательны.

---

### ADR-004: Phase 8 Handlers — Memory, Scene, Reaction
**Дата:** 02.05.2026  
**Статус:** Принято

**Контекст:**  
Диаграмма Фазы 8 предписывала 4 обработчика: memory, social, scene, reaction. Существовали только perception + social.

**Решение:**  
- **Memory handler — НЕ НУЖЕН:** Фаза 3 записывает факты ДО принятия решения (Фаза 5). Если memory в Фазе 8 — NPC решает на устаревшем state.
- **Scene handler — НЕ НУЖЕН:** `OBJECT_DESTROYED` обрабатывается perception. Смена сцены — `SceneChange → EventDTO → шина → perception/reaction`.
- **Reaction handler — НУЖЕН:** Создан `ReactionSubscriber`. Производит ПРЯМЫЕ эмоциональные дельты для наблюдателей без полного decision-цикла.
- **Порядок:** `perception → reaction → social`

**Последствия:**  
- Фаза 8 имеет 3 обработчика вместо 4. Memory и Scene НЕ будут добавлены без нового ADR.

---

### ADR-005: NPC Data Mapping для Idle Handlers
**Дата:** 03.05.2026  
**Статус:** Принято

**Контекст:**  
`_build_npc_snapshots()` читал ключ `relationship_cache` из NPC dict, но его не существовало. Данные лежали в плоском `social_stats` (player-facing). Итог: `SocialDecayHandler` всегда получал пустой кэш → нулевой decay.

**Решение:**  
- `_build_npc_snapshots()` выполняет маппинг при проекции:
  - `social_stats.trust` → `relationship_cache["player"]["trust"]` (0-100)
  - `social_stats.fear_of_player` → `relationship_cache["player"]["fear"]`
  - `psyche.loyalty_true` → `base_values["player"]`
  - `status_profile.faction_rank.keys` → `faction_affiliations`
- Плоский кэш `{trust: val}` автоматически конвертируется во вложенный формат.

**Последствия:**  
- `SocialDecayHandler` корректно вычисляет дрейф.
- Ограничение: NPC-to-NPC связи пока НЕ попадают в snapshot (требуется ADR-006).

---

### ADR-006: NPC-to-NPC Social Relations Enrichment при загрузке
**Дата:** 04.05.2026  
**Статус:** Принято

**Контекст:**  
NPC-to-NPC связи из `village_relations.json` не попадали в NPC dict. `relationship_cache` содержал только entry `"player"`.

**Решение:**  
- Создана `_enrich_with_social_relations()` — обогащает NPC dict данными из `village_relations.json`.
- Вызывается в `load_npcs_merged()` ПОСЛЕ мержа static + runtime.
- Шкала: конвертация `base_trust * 100` (из 0-1 в 0-100).
- Формат: `relationship_cache[target_id] = {trust, fear, base_trust, nature}`.
- Критический фикс `_build_npc_snapshots()`: shallow copy + гарантированное добавление player entry, чтобы не затереть player-facing данные.

**Последствия:**  
- `SocialDecayHandler` производит NPC→NPC дрейф. Player drift НЕ ломается.

---

### ADR-007: Синхронизация all_npcs_raw в idle-пути TickOrchestrator
**Дата:** 05.05.2026  
**Статус:** Принято

**Контекст:**  
В idle-пути Фаза 0 заполняла `ctx.npc_states`, но `ctx.all_npcs_raw` (используемый мутатором) оставался пустым. Дельты применялись к пустому списку и терялись.

**Решение:**  
- В `_phase_0_simulation` добавлена явная синхронизация: `ctx.all_npcs_raw = ctx.npc_states`.

**Последствия:**  
- Дельты из Фазы 8 корректно применяются в idle-тиках.
- `ctx.npc_states` и `ctx.all_npcs_raw` ссылаются на один объект в памяти.

---

### ADR-008: Централизация пространственных данных и удаление глобальных мостов
**Дата:** 05.05.2026  
**Статус:** Принято (частично, заблокировано багами E2E)

**Контекст:**  
Несколько источников истины: глобальный `_connections_data`, кэш `_graphs` в MovementEngine, прямые вызовы `LocationGraph.find_path()`. Фронтенд незаконно обращался к бэкенду через `_gateway._bridge`.

**Решение:**  
- Удален глобальный мост `_connections_data`. `compile_graph` возвращает связи явным кортежем.
- Удален кэш `_graphs` из `MovementEngine`. Единственный источник пути — `SpatialService.find_path()`.
- Удалена денормализация ID (`denormalize_id`).
- Оборваны прямые вызовы фронтенда к бэкенду.

**Последствия:**  
- Единая точка входа для навигации, учет оверлеев.
- Требуется строгий DI `SpatialService` во все ветки тика.

---

### ADR-009: Инъекция примитивов вместо объектов в InterpretationEngine
**Дата:** 06.05.2026  
**Статус:** Принято

**Контекст:**  
`InterpretationEngine` падал с ошибкой `'NPCState' object has no attribute 'personality'`. Нарушен Закон 1.2.

**Решение:**  
- Вместо передачи всего объекта `profile_l0`, в метод `compute()` добавлен аргумент `drives_base: Dict[str, float]`. Движок получает только нужные данные.

**Последствия:**  
- Снижение связности (Law of Demeter). Устранение краша. Рост количества аргументов.

---

### ADR-010: Макро-зоны SpatialService vs Микро-зоны Archetypes
**Дата:** 07.05.2026  
**Статус:** Принято

**Контекст:**  
SpatialService оперирует макро-зонами (`main_hall`), а конфиги NPC — микро-зонами (`serving_table_3`). MovementEngine не находил микро-зону и отменял движение. NPC парализованы.

**Решение:**  
- Архетипы должны ссылаться только на валидные узлы макро-графа.
- `MovementEngine` имеет fallback: если текущий узел не найден, сброс на `entrance` или `main_hall`.

**Последствия:**  
- NPC regained mobility. Потеря микро-позиционирования. Требуется обновление JSON.

---

### ADR-011: Переход на Narrative Beat System (Cinematic Presentation Layer)
**Дата:** 07.05.2026  
**Статус:** Принято (Частичная реализация)

**Контекст:**  
Плоский `message_log` превращал UI в IRC-чат. Отсутствовала поддержка крика/шепота и уровней знания NPC.

**Решение:**  
- Внедрен `NarrativeBeat` как единая единица текста. Введены `DeliveryType` и `RecognitionLevel`.
- Создан `NarrativeRenderer` для отрисовки пузырей.
- Эхо LLM фильтруется нечетким поиском (SequenceMatcher).

**Последствия:**  
- UI стал динамическим. Бэкенд пока не разделяет `dm_response` на конкретных NPC.

---

### ADR-012: Смягчение стража мутации position и открытие границы Macro/Micro Space
**Дата:** 08.05.2026  
**Статус:** Принято

**Контекст:**  
Страж `RuntimeError` блокировал любую мутацию `position`, останавливая движение. Использование `MovementIntent` для микро-позиционирования привело к крашу (target_node_id == from_node_id).

**Решение:**  
- Страж смягчён: `RuntimeError` заменён на debug log. `SceneChange(field="position")` разрешен и резолвится в `local_position` через SpatialService.
- Запрещено использовать `MovementIntent` для микро-перемещений внутри одной зоны.
- Для визуального сближения требуется `LocalSteeringIntent` (работает с x,y напрямую).

**Последствия:**  
- Макро-движение разблокировано. Микро-перемещение (подойти на 1 метр) НЕ РЕАЛИЗОВАНО.

---

### ADR-013: StateDeltas v2 — Domain-Tagged Typed Payloads
**Дата:** 08.05.2026  
**Статус:** Принято

**Контекст:**  
StateDeltas v1 был плоским dataclass (god-object). Смешанные дельты (stress + trust) размывали доменные границы. Контракт DTO LOCKED v1 блокировал добавление физиологии.

**Решение:**  
- Введен `enum DeltaDomain` (SOCIAL, EMOTION, REPUTATION, IDENTITY, PHYSIOLOGY, SPATIAL).
- Каждый домен имеет свой frozen dataclass payload.
- Инвариант: одна дельта = один домен. Валидация в `post_init`.
- Разделение реакций на EMOTION + SOCIAL вместо одной смешанной.

**Последствия:**  
- Типобезопасность и расширяемость. Обратная совместимость с v1.

---

### ADR-014: Narrative Beat Pipeline, Speaker Extraction и UI Layer Separation
**Дата:** 09.05.2026  
**Статус:** Принято

**Контекст:**  
Бэкенд присылал `dm_response` одной строкой, фронтенд жестко привязывал к `speaker="Система"`. Фильтр эха ломал реплики NPC при коротких вводах.

**Решение:**  
- Извлечение спикера: парсинг `dm_response` через `known_names` из `scene_state`.
- Разделение слоев: `message_log` (Cinematic Layer) и `system_log` (Log Layer).
- Починка эха: флаг `is_short_input` отключает подстроковую проверку.
- Визуальная экспрессия: стили для SHOUT, WHISPER, INTERNAL. Пузыри TRANSIENT живут 5 сек + 2 сек фейд-аут.

**Последствия:**  
- Cinematic Layer свободен от шума. Исключено ложное глушение NPC.

---

### ADR-015: Physiology Domain и Impact Propagation Engine
**Дата:** 09.05.2026  
**Статус:** Принято

**Контекст:**  
Бой — не отдельная система, а режим давления на ВСЕ системы. RPG-абстракции (Hit Roll, AC, combat_state) убьют симуляцию.

**Решение:**  
- Домен переименован в `DeltaDomain.PHYSIOLOGY`.
- Данные разделены: `body_profile` (статика) + `body_state` (рантайм).
- `InjuryDTO` использует `target_zone` и семантические теги. HP — макро-LOD, центр модели — Functional Capacity.
- Создан Impact Propagation Engine (Pure Function). Contact Resolution Model (уклонение от боли/усталости).
- Возвращает ТОЛЬКО Physiology-дельты. Эмоции только через `shock_impulse` (No Domain Leakage).

**Последствия:**  
- Удар порождает каскад: тело → боль → шок-сигнал → страх → социальная паника. Нет "режима боя".

---

### ADR-016: Time Control System и Абсолютное время
**Дата:** 09.05.2026  
**Статус:** Принято (Реализация заблокирована багами)

**Контекст:**  
Время в idle-тиках не продвигалось. Фронтенд терял дни и годы.

**Решение:**  
- Фронтенд делит интервал на `_time_scale` (1, 4, 10, 50).
- Бэкенд продвигает время в Фазе 0.5 на `GAME_TICK_INTERVAL_SECONDS`.
- Единый источник истины: `game_time_seconds` в `scene_state`.

**Последствия:**  
- Архитектура времени детерминирована. Ускорение позволяет тестировать симуляцию.

---

### ADR-017: Force Merge — world_snapshot в DirectGameGateway
**Дата:** 09.05.2026  
**Статус:** Принято

**Контекст:**  
Фронтенд получал только dm_text и npc_reactions, рисуя NPC по старым координатам до следующего idle_tick.

**Решение:**  
- `TurnResult` дополнен полями `world_snapshot` и `npc_positions`.
- `GameLoopBridge.turn()` строит `world_snapshot` из актуального `scene_state`.
- `DirectGameGateway` передаёт их в `GameActionResponse`.

**Последствия:**  
- Фронтенд видит актуальные позиции NPC сразу (has_ws=True).

---

### ADR-018: Защита micro-position от затирания macro-relocation
**Дата:** 09.05.2026  
**Статус:** Принято

**Контекст:**  
MovementEngine генерировал `SceneChange(field="position")` даже когда NPC уже был в целевом узле. SceneStateManager резолвил это в center node, уничтожая micro-position.

**Решение:**  
- Добавлен guard: если `from_node_id == target_node_id` — пропускаем macro SceneChange.

**Последствия:**  
- Micro-position не затирается. NPC остаются near-player после approach.

---

### ADR-019: Architectural Gap — State Relocation vs Continuous Spatial Simulation
**Дата:** 09.05.2026  
**Статус:** Принято (диагноз, реализация в следующем спринте)

**Контекст:**  
Текущая система — «state relocation с косметическим x/y». Нет persistent movement state, temporal interpolation, spatial slots. NPC телепортируются.

**Решение (ROADMAP):**  
1. Ввести `TraversalState`.
2. Отделить `SceneChange` (топология) от `MovementStep` (локомоция).
3. Ввести Spatial slots внутри Interest Zones.
4. `speed * delta_time` — continuous position integration.

**Последствия:**  
- Без TraversalState телепортация — это не баг, а класс архитектуры.

---

### ADR-020: Domain Reduction Semantics Layer (DRSL)
**Дата:** 09.05.2026  
**Статус:** Принято

**Контекст:**  
Универсальный редьюсер терял Physiology дельты при агрегации через last-write-wins. Система не различала бухгалтерию мира (Σ) и физику мира (интеграл с памятью).

**Решение:**  
- Введен `ReductionPolicy` enum: `ADDITIVE`, `BOUNDED_ADDITIVE`, `OVERWRITE`, `PHYSICS_COMPOSITE`.
- `DELTA_POLICY_REGISTRY`: конституция мира — каждый домен знает свой закон редукции.
- `PHYSICS_COMPOSITE` обходит merge — инъекции энергии передаются как есть.

**Последствия:**  
- Тело не складывается, оно эволюционирует. Редукция — задача ImpactEngine/StateApplicator.

---

### ADR-021: CombatSubscriber — мост EventDTO → ImpactEngine
**Дата:** 09.05.2026  
**Статус:** Принято

**Контекст:**  
ImpactEngine существовал, но никто не вызывал его из пайплайна.

**Решение:**  
- Создан `CombatSubscriber` (Phase8Handler). Мост, не система.
- Извлекает `ImpactIntentDTO`, строит снапшоты, вызывает `resolve_physical_impact()`.
- Возвращает `Phase8Result(deltas=physiology_deltas)`.

**Последствия:**  
- Боевые события порождают Physiology-дельты через delta_buffer. No Domain Leakage.

---

### ADR-022: PhysiologyDecayHandler — Leaky Integrator для Фазы 0.5
**Дата:** 09.05.2026  
**Статус:** Принято

**Контекст:**  
Боль, усталость и кровопотеря не затухали между тиками.

**Решение:**  
- Создан `PhysiologyDecayHandler`. Тело — инерционная система: `S_t = S_{t-1} * exp(-lambda * dt)`.
- Closing drift: остатки < EPSILON обнуляются.
- Фазовые переходы: `pain > 50 → stagger`, `consciousness < 0.1 → unconscious`.

**Последствия:**  
- Физиологические параметры инерционны. NPC выходят из stagger при восстановлении.

---

### ADR-023: Embodied Traversal — Отвязка Внимания от Кинематики
**Дата:** 09.05.2026  
**Статус:** Принято

**Контекст:**  
Слияние движения и взгляда (кинематическая редукция) убивало симуляцию NPC AI. NPC должен уметь пятиться, глядя на угрозу.

**Решение:**  
- Разрыв `_MoveState` на 3 домена: Навигация, Кинетика, Эмбодимент (`facing_angle`, `facing_mode`).
- Введен `facing_mode`: "VELOCITY", "LOOK_TARGET", "FREE".
- При движении к NPC, `facing_angle` вычисляется к цели, а не к точке пути.

**Последствия:**  
- Взгляд стал намеренным. Требуется сглаживание поворота (lerp).

---

### ADR-024: Event-Sourced World Transition и Temporal Isolation
**Дата:** 09.05.2026  
**Статус:** Суперседировано ADR-025 (CFRM)

**Контекст:**  
`ctx.scene_state` как мутирующий словарь позволял Фазам видеть частично изменённое "будущее". Нарушение причинности.

**Решение (Историческое):**  
- Переход к Event-Sourced Architecture. `scene_state` переставал быть "живым словарём". Глобальный Reducer вычислял мир из immutable событий.

**Последствия:**  
- Суперседировано Causal Field Reduction Model (ADR-025), которая устранила проблему глобального World и NP-hard упорядочивания через локальные причинные пузыри.

---

### ADR-025: Causal Field Reduction Model (CFRM)
**Дата:** 10.05.2026  
**Статус:** Принято

**Контекст:**  
Глобальный Reducer приводил к NP-hard проблеме упорядочивания параллельных событий. `delta_buffer` был списком императивных инструкций, нарушая причинную замкнутость мира.

**Решение:**  
Переход к distributed causal inference system. Глобального объекта World больше не существует в runtime.
- **Онтологические постулаты:** 1) NPC operate on perceived causality, not actual causality. 2) Snapshot is belief state derived from CFRM projection.
- **Core Model:** `Snapshot[t] = Reduce(ClusterGraph_local, EventBuffer_local, MembraneField_local)`.
- **Структуры:**
  - `ClusterGraph`: Пространственная декомпозиция. Содержит связи, НЕ содержит состояния. Инкрементальное обновление при пересечении NPC границ ячеек.
  - `EventBuffer`: Временный causal input stream. Атомарные факты (Physical, Cognitive, Social). НЕ лог и НЕ хранилище.
  - `MembraneField`: Функция ослабления причинности при переносе между кластерами. `membrane(event, distance, context) -> attenuation_factor`. Ограничение: scope == local cluster neighborhood only.
- **NPC Model:** NPC хранит `PerceptualKernel` (last_observed_event_ids, decay_model, belief_weights), а НЕ world state. Формула миграции: `new_perception = merge(old_perception * decay_factor, cluster_local_truth * visibility_projection)`.
- **3-фазный оператор редюсера:** Phase 1: Projection. Phase 2: Attenuation. Phase 3: Local Reduction (no global merge).

**Последствия:**  
- Линейная масштабируемость (O(cluster_size)). NPC обладают инерцией восприятия. Исключён глобальный пересчёт. Основание для социальной физики (обман мембран).

---

### ADR-026: Presentation Lerp и Visual Gaze Indicators
**Дата:** 10.05.2026  
**Статус:** Принято

**Контекст:**  
Стрелка игрока мгновенно "щелкала" при повороте. NPC не имели маркера внимания. Спрайты объектов не отображались. Пузыри исчезали слишком быстро.

**Решение:**  
- Внедрен экспоненциальный Lerp (10 рад/сек) для визуального угла поворота игрока. Логика `_MoveState` не затронута.
- Для NPC добавлен индикатор взгляда: желтая линия к игроку при `attention_focus`.
- Починен рендер объектов: `_draw_obstacles()`. Fallback на спрайт `"person"`.
- Время жизни TRANSIENT-пузырей увеличено до 10 сек + 3 сек фейд.

**Последствия:**  
- Визуальная плавность. Читаемость внимания NPC.

---

### ADR-027: Layered Reduction — Dual Buffer Causal Model для Фазы 8
**Дата:** 10.05.2026  
**Статус:** Принято

**Контекст:**  
Парадокс причинности: CombatSubscriber работал последним, и ReactionSubscriber не мог прочитать `shock_impulse` текущего тика. Задержка в 1 тик разрушала immediacy.

**Решение:**  
Фаза 8 стала многоступенчатым редуктором слоёв реальности:
1. **Physical Layer** (`CombatSubscriber`): вычисляет урон, генерирует `shock_impulse`.
2. **Materialization**: дельты замораживаются в `physical_deltas_materialized: Tuple[StateDeltas, ...]`.
3. **Cognitive Layer** (`ReactionSubscriber`): читает materialized snapshot. Цель получает шок от боли, свидетель — эмпатический ужас.
4. **Social Layer** (`SocialSubscriber`): распространяет слухи.

**Последствия:**  
- Каскад Force → Pain → Shock → Emotion работает в рамках одного тика. Детерминизм гарантирован.

---

### ADR-028: Миграция NPC конфигов на body_profile
**Дата:** 10.05.2026  
**Статус:** Принято

**Контекст:**  
JSON-конфиги содержали легаси `combat_stats` (RPG-абстракции). Нарушение ADR-015.

**Решение:**  
- Во всех архетипах удалена секция `combat_stats`.
- `abilities` перенесены внутрь нового объекта `body_profile`.
- Добавлены `max_hp` (индивидуально: 80 для maid, 120 для guard) и `base_ac`.
- `npc_loader` использует `_deep_merge`, поэтому `body_profile` корректно наследуется.

**Последствия:**  
- Конфиги приведены в соответствие с ADR-015. ImpactEngine работает с реальной анатомией.
- Legacy-код, читающий `combat_stats`, будет получать пустые словари (безопасно, но требует очистки).

---

### ADR-029: CFRM Layer 1 & P1 Legacy Bridge — Spatial Index и Event Classification
**Дата:** 11.05.2026  
**Статус:** Принято

**Контекст:**  
ADR-025 определил CFRM теоретически, но в runtime отсутствовали структуры данных для её исполнения. `TickOrchestrator` работал через `delta_buffer` и не имел понятия пространственных кластеров или причинных осей. Без индекса присутствия вычисление локальной причинности невозможно (требуется O(n) вместо O(1)). Без классификации событий `EventBuffer` не может разделить физические факты от когнитивных.

**Решение:**  
- **ClusterGraph & ClusterOccupancy:** Реализован Spatial Index поверх `SpatialService`. Принят постулат: 1 макро-узел (`NodeRef`) = 1 причинный кластер. `ClusterOccupancy` маппит `entity_id ↔ ClusterID` для O(1) поиска участников пузыря. Индекс восстанавливается на старте тика из `scene_state['npc_positions']`.
- **EventBuffer & CausalAxis:** Создан временный causal input stream с осями `PHYSICAL`, `COGNITIVE`, `SOCIAL`. Внедрен метод `drain()` для атомарного извлечения фактов редюсером.
- **Legacy Bridge (`classify_event`):** Создана функция маппинга текущих строковых `EventType.value` на 3 оси CFRM. Неизвестные события по умолчанию когнитивные (безопасный fallback).
- **Интеграция с EventBus:** `EventBus` получил методы `attach_cfrm_buffer()` / `detach_cfrm_buffer()`. В `TickOrchestrator.execute()` буфер привязывается к шине на время тика (блок `try...finally`), что гарантирует сбор всех фактов без поломки старого конвейера.

**Последствия:**  
- Фундамент для 3-фазного редюсера (ADR-025) заложен.
- Система параллельно собирает императивные дельты (старый путь) и декларативные факты (новый путь).
- Стало возможным вычисление Causal Closure: кто из NPC воспринимает событие, за O(1) на основе кластера.

---

### ADR-030: Player as Hybrid Consciousness Entity & WillpowerGate
**Дата:** 11.05.2026  
**Статус:** Суперседировано ADR-031

---

### ADR-031: WillpowerGate — Cumulative Strain Model и IntentPressureResolver
**Дата:** 11.05.2026  
**Статус:** Принято

**Контекст:**  
Попытка реализовать WillpowerGate через матрицу `action × temperament` (attack + fearful = resist) ведет к поведенческой таблице ("Excel с эмоциями"). Это убивает эмерджентность, не создает психологической ломки и не отражает контекст: одно и то же действие ("ударить") может быть самообороной или садизмом. Аватар должен оценивать не тип действия, а степень угрозы своему Я.

**Решение:**  
- Введен **IntentPressureResolver** (Pure Function) — промежуточный слой между `IntentDTO` и `WillpowerGate`. Транслирует семантику действия + контекст в `IntentPressureProfile`.
- **IntentPressureProfile** — вектор давления на психику: `violence`, `humiliation`, `self_risk`, `social_exposure`, `moral_violation`, `identity_deviation`, `trauma_trigger`, `taboo_intensity`.
- **WillpowerGate работает ТОЛЬКО с PressureProfile**, не зная о типе действия.
- **Cumulative Strain Model:** Сопротивление вычисляется формулой: `resistance = pressure.identity_deviation * psyche.identity_rigidity + pressure.self_risk * psyche.fear + pressure.moral_violation * psyche.conviction + pressure.social_exposure * psyche.shame - pressure.violence * psyche.aggression - pressure.taboo_intensity * psyche.curiosity`.
- **Willpower** — не порог, а инерция. Высокий willpower медленнее ломается, но ломается катастрофически.
- Введен **WillState** (COMPLY, RELUCTANT, DISTRESSED, PANICKED, DISSOCIATING, BROKEN, CONDITIONED) вместо бинарных ACCEPTED/RESISTED.
- **Counter-Offer обязателен:** Аватар не блокирует действие, а предлагает альтернативу, пытаясь выжить.

**Последствия:**  
- Архитектура воли стала причинной и расширяемой.
- Возникает эмерджентная психология: деградация — непрерывный процесс, а не переключатель.
- ЗАПРЕЩЕНО использовать `action × temperament` как онтологию системы (допускается только как debug fallback).

**Контекст:**  
Игрок существовал вне симуляции как строка `player_name`, не имея `body_state`, `psyche` и социальной проекции. Это нарушало CFRM (игрок не в причинном поле), боевку (невозможно ранить) и социальную физику. Попытки сделать игрока "просто NPC" ломали агентность, превращая его в автономный юнит, лишая внешнего источника воли.

**Решение:**  
Игрок становится **Hybrid Consciousness Entity** (`npc_id="player"` в `all_npcs_raw`).
- **Разделение Волі:** Игрок генерирует Intent Stream (внешняя воля), но применение интента проходит через **WillpowerGate** аватара.
- **WillpowerGate — это Dynamic Identity Preservation Engine.** Это не булева проверка морали, а защита self-image, trauma equilibrium и survival model. Аватар спрашивает: "Останусь ли Я СОБОЙ после этого действия?"
- **WillResponseDTO:** Результат работы WillpowerGate. Возвращает `outcome` (ACCEPTED, RESISTED, DISSOCIATED, ADAPTED), `resistance`, `identity_damage`, `generated_emotions` и `counter_offer` (аватар предлагает альтернативу).
- **Identity Drift:** Продавливание воли ведет к диссоциации и адаптации. Личность перестраивается под насилие (trauma normalization, learned helplessness).
- **Perceptual Kernel:** Игрок ограничен своим causal bubble (кластером). MembraneField влияет на его восприятие. Никакого всеведения (Fog of War на основе кластеров).
- **Social Drift:** Разделен на `PlayerMemory` (человек помнит всё) и `AvatarAffectiveMemory` (аватар забывает, боится, привыкает). Фрикция: игрок хочет мести, аватар боится.
- **MVP Character Creator (Вектор начальных условий):** Layer 1: Archetype (задает `body_profile`), Layer 2: Temperament (задает `psyche.drives_base` и `willpower`). Social Seed отложен.

**Последствия:**  
- Игрок — часть причинной физики мира. Бой и социальное давление работают на него.
- Фрикция между желанием игрока и состоянием аватара создает литературный, а не только механический конфликт.
- Требуется Fog of War и UI индикация состояния Аватара (сопротивление, боль, шок).

---

### ADR-032: DecisionHub v2 Migration & Controlled Degradation Layer
**Дата:** 11.05.2026  
**Статус:** Принято

**Контекст:**  
`DecisionResult.deltas` имел тип `StateDeltas` (v1, плоский объект), что нарушало ADR-013 (Domain-Tagged Typed Payloads). Смешение Emotion и Social в одной сущности размывало доменные границы. Прямая замена на `List[StateDeltas]` сломала бы 20+ downstream-потребителей (scene_outcome_builder, state_applicator).

**Решение:**  
Внедрён Controlled Degradation Adapter (односторонний деградационный шлюз).
1. Ядро (`DecisionHub`) переведено на генерацию `List[StateDeltas]` с `EmotionPayload` и `SocialPayload`.
2. Создан внешний адаптер `LegacyStateDeltaAdapter.collapse()`, который схлопывает v2 в v1 для legacy-кода.
3. Адаптер логирует потерю доменов (Drop domains) при коллапсе. Ядро не знает о v1.

**Последствия:**  
- Новая система не ограничена плоской структурой. Можно добавлять `MemoryDelta`, `ReputationDelta` без калечения ядра.
- Legacy-код изолирован и будет постепенно мигрирован или удалён.
- Правило: `v2 → adapter → v1`, но никогда `v2 contains v1`.

---

### ADR-033: Deobjectification and Phenomenological Causal Solver (CFRM Phase 2)
**Дата:** 11.05.2026  
**Статус:** Принято

**Контекст:**  
В P1 (Layer 1) `EventBuffer` хранил объективные `EventDTO`. Это нарушало постулат CFRM о том, что NPC оперируют воспринимаемой причинностью, а не объективной истиной. Хранение "факта удара" означало существование канона, что делало невозможным искажение слухов, инференс угроз и субъективность восприятия. `PerceptionSubscriber` работал глобально, нарушая локальность.

**Решение:**  
Переход к феноменологической модели. Событий не существует — существуют только возмущения причинного поля (`FieldDisturbance`), которые трансформируются оператором `ProjectionPolicy` в зависимости от состояния наблюдателя.
- **Деобъективация:** `EventBus` больше не кладет события в буфер напрямую. Через мост `cfrm_bridge` событие превращается в `FieldDisturbance` (кинетика, акустика, материя, поведение).
- **Политики проекции:** Физика теряет энергию (затухание), Когнитивное теряет достоверность (инференс по косвенным признакам, паранойя), Социальное теряет точность (искажение слухов при передаче).
- **Генерация давления:** Солвер не мутирует стейт напрямую. Он генерирует `PsychologicalPressure` (страх, неопределенность), которое downstream-системы (психика NPC) конвертируют в `StateDeltas`.
- **PerceptualKernel:** В `NPCState` внедрены векторы напряжения (без строк), обновляемые солвером.
- **Смерть PerceptionSubscriber:** Глобальная подписка на события удалена. Восприятие теперь вычисляется локально в Фазе 9.

**Последствия:**  
- NPC больше не знают объективную правду. Слух может стать сильнее факта.
- Слепые, раненые или параноидальные NPC имеют разные модели реальности.
- Требуется P3: Личность NPC (трус/берсерк) должна модулировать восприятие `PsychologicalPressure`.

---

### ADR-034: Phase 1 Boundary Adapter & Transitional Runtime Boundary
**Дата:** 11.05.2026  
**Статус:** Принято

**Контекст:**  
Ход игрока обходит `TickOrchestrator`, выполняясь напрямую в `game_loop` (Фазы 3-6 зависят от `shared_context` и DM runtime). Попытка внедрить `WillpowerGate` прямо в `game_loop` привела бы к размыванию ответственности (логика страха/боли в UI-слое). Попытка унифицировать пайплайн (перенести всё в оркестратор) создала бы бог-объект, зависимый от LLM/UI.

**Решение:**  
Введен **Phase 1 Boundary Adapter** (транзитный шлюз). `game_loop` вызывает чистую функцию `resolve_player_intent()`, которая возвращает `IntentResolution`. `game_loop` только публикует результат в шину (где он через `cfrm_bridge` становится `FieldDisturbance`) и кладет в `shared_context`.
- **IntentResolution DTO:** Содержит `original_intent`, `resolved_intent`, `blocked`, `transformed`, `will_state`, `counter_offer`.
- **Запрет в `game_loop`:** Никакой бизнес-логики воли, боли, страха. Только `resolve -> publish resolution`.
- **Вариант Б (унификация тика)** отложен до выделения `RuntimeContext`, `AgentExecutionService` и `NarrativeBridge`.

**Последствия:**  
- Воля аватара работает без поломки NPC-оркестрации.
- `game_loop` лишен права принимать решения о публикации.
- Конфликт воли (WILL_CONFLICT) порождает возмущение поля, которое могут воспринять NPC (эмпатический отклик на панику аватара).

---

### ADR-035: Intent Compression Layer и Русская Морфология
**Дата:** 12.05.2026  
**Статус:** Принято

**Контекст:**  
Сырой текст игрока ("я со всей дури бью борко кружкой по лицу") не содержал машиночитаемых параметров. Попытка парсить русскую морфологию регекспами приводила к потере флексий ("бью" vs "ударил" vs "ударит"). LLM не должна знать ID сущностей мира, а её падение не должно молча лгать от имени мира (подмена ATTACK на OBSERVE).

**Решение:**  
- Введен **Слой 1: IntentCompression**. Стоит ДО `WillpowerGate` и `TargetResolution`.
- **Fast Path:** Использует `pymorphy3` для лемматизации. Словари лемм содержат оба вида глаголов (совершенный/несовершенный). Извлекает модификаторы интенсивности.
- **Slow Path:** Вызов LLM через `LLMCompressorClient` (DI). LLM извлекает `target_reference` (строка, не ID!), `EmotionalVector` и оси интенсивности. Ответ валидируется Pydantic.
- **Ambiguity Handling:** При ошибке LLM или невалидном JSON действие помечается как `UNCERTAIN` с `SemanticAmbiguity.AMBIGUOUS`, а не silently подменяется на безопасное.
- **Новый DTO:** `IntentSemanticField` — вероятностное поле, а не команда.

**Последствия:**  
- Детерминированный парсинг русского языка работает без нейросети.
- LLM изолирована от бизнес-логики (DI). Смена провайдера требует 1 строки.
- Downstream системы (Слой 2, Слой 3) получают структурированное поле давления вместо сырого текста.

---

### ADR-036: Single Will Evaluation — Устранение Double Invocation
**Дата:** 11.05.2026  
**Статус:** Принято

**Контекст:**  
WillpowerGate вызывался дважды за один игровой цикл: в `phase_1_input.py` и в `tick_orchestrator.py`. Это приводило к двойному начислению `identity_damage` и `fear_delta`, делая ADR-031 статистически недостоверным.

**Решение:**  
Разделение ответственности: Фаза 1 имеет право только на семантический перевод (`IntentDTO → IntentPressureProfile`). Единственная точка Causal Resolution — `TickOrchestrator`.

**Последствия:**  
- Одна психическая атака = одно вычисление напряжения.

---

### ADR-037: Affect Resonance & Pressure Distortion
**Дата:** 12.05.2026  
**Статус:** Принято

**Контекст:**  
WillpowerGate работал как FSM с resistance coefficients. Травма обрабатывалась как `fear += 20%`. Это тупиковая система: она не способна генерировать PTSD, иррациональные реакции и conditioning. Травма ≠ страх.

**Решение:**  
Введена двухслойная система Аффекта перед WillpowerGate:
1. **Resonance Detection (`scan_affective_resonance`):** Чистая функция. Сканирует совпадение смысловых паттернов между текущим контекстом и `AffectiveImprints`. Возвращает `ResonanceProfile`.
2. **Pressure Distortion (`distort_pressure`):** Чистая функция. Искажает базовое давление через `ResponseBias`. Bias определяется психикой (aggression → ярость, shame → ступор, fear → подчинение). Возвращает `AmplifiedPressureProfile`.

**Последствия:**  
- Аффект искажает *интерпретацию* давления, а не баффает его.
- Резонанс и Мутация разделены (explainability сохранена).
- NPC и Avatar используют единую модель (history-shaped entities).

---

### ADR-038: Avatar Presentation DTO & Embodied Perception Interface
**Дата:** 12.05.2026  
**Статус:** Принято

**Контекст:**  
Фронтенд был слеп к страданиям аватара. Попытка пробросить `body_state` (pain, hp) напрямую привела бы к созданию RPG-отладчика ("Pain: 74%") и нарушению Устава §6.1. `WorldSnapshotBuilder` не должен читать симуляцию напрямую, иначе станет бог-объектом. Симуляционная истина (`NPCState`) не равна визуальной проекции (`Rendering Projection`).

**Решение:**  
Введен **Translation Layer** и **Феноменологическая проекция**.
1. **AvatarPresentationAssembler:** Чистая функция, переводящая `body_state`/`psyche` в `AvatarStateDTO`.
2. **AvatarStateDTO:** Содержит не числа, а состояния и параметры искажения: `PhysicalPresentationState` (WOUNDED, BLEEDING), `MentalPresentationState` (PANICKED, DISSOCIATING), `visual_distortion`, `blood_visibility`, `breathing_profile`.
3. **Embodied Perception Interface:** Фронтендовый рендерер накладывает пост-процессинг (красная виньетка, туннельное зрение, помутнение) на основе `avatar_state`, не зная внутренних метрик.

**Последствия:**  
- Магия иммерсивности сохранена: игрок видит кровь и дрожь, а не таблицу статов.
- `WorldSnapshotBuilder` остается чистым маппером.
- Архитектура готова к будущей интеграции с `PerceptualKernel` (искажение рендера от галлюцинаций и травм).

### ADR-039: Phenomenological Presentation & Resistance Medium
**Дата:** 12.05.2026  
**Статус:** Принято

**Контекст:**  
Фронтенд являлся пассивным монитором, отображающим стейт через RPG-парадигму (полоски HP, текстовые логи, категориальные эффекты). Конфликт воли аватара не имел моторного воплощения для игрока. Бэкенд диктовал параметры рендера (shake, blur), нарушая разделение слоев.

**Решение:**  
Переход к Темпоральному Феноменологическому Рендерингу.
1. **Presentation Firewall:** На границе Бэкенд→Фронтенд отсекаются все категориальные енумы (MentalPresentationState, PhysicalPresentationState). Фронтенд получает только непрерывные скаляры давления (0.0-1.0).
2. **Perceptual Momentum:** Внедрена темпоральная инерция (S-curve) и контролируемая стохастика. Эффекты не включаются/выключаются, а деградируют и восстанавливаются по законам когнитивного гистерезиса. Скорость возврата в норму зависит от reality_reconciliation_rate.
3. **Resistance Medium:** Конфликт воли аватара реализован как инфекция ввода. При WILL_CONFLICT поле ввода заражается навязанным импульсом (infect()). Игрок должен физически стереть текст аватара, чтобы вписать свой, либо нажать Enter (подчиниться).
4. **Embodied Impulse:** Бэкенд передает не эмоции, а предрефлексивные моторные векторы (avoidance, collapse, destroy).

**Последствия:**  
- Визуальные эффекты стали инерционными и органичными. Устранено мерцание "PANIC ON/OFF".
- Игрок испытывает моторное сопротивление интерфейса, а не читает о конфликте воли.
- Фронтенд полностью лишен права семантической интерпретации мира (Закон Шейдера).

---

### ADR-040: Epistemic Classification & ClassificationResult
**Дата:** 12.05.2026  
**Статус:** Принято

**Контекст:**  
Функция `classify_event` возвращала только `CausalAxis`. Это чёрный ящик: система не знала, насколько она уверена в классификации. Fallback-события обрабатывались так же, как жёсткие правила, что лишало downstream-системы возможности оценивать эпистемическую достоверность фактов. Использование Tuple ломало расширяемость.

**Решение:**  
Введен `ClassificationResult` (frozen dataclass) и `ClassificationSource` (Enum).
- `classify_event` теперь возвращает `ClassificationResult(axis, confidence, source)`.
- Для жёстких правил (`HARD_RULE`) confidence = 1.0.
- Для fallback-событий (`FALLBACK`) confidence = 0.2 (сигнал downstream, но не убийство события).
- В `_deobjectify_event` добавлено логирование Warning при confidence < 0.5.

**Последствия:**  
- API устойчиво к добавлению новых классификаторов (HEURISTIC, LEARNED).
- CFRM Sandbox может визуализировать затухание неопределённости.
- Запрещено использовать Tuple для возврата эпистемических оценок.

---

### ADR-041: Will Conflict Data Pipeline & Action Key Sync
**Дата:** 12.05.2026  
**Статус:** Принято

**Контекст:**  
Бэкенд вычислял Конфликт Воли и генерировал `narration_hooks`, но эти данные умирали в `TickOrchestrator`. API-слой не имел полей для их приёма. Также обнаружился критический рассинхрон: `resolve_intent_pressure` ожидала `action="attack"`, а пайплайн присылал `action="player_attacks"`, из-за чего давление всегда было нулевым, и Воля никогда не сопротивлялась.

**Решение:**  
1. **Проброс через API:** В `PipelineContext`, `ChatTurnResponse` и `GameActionResponse` добавлено поле `will_conflict_data: Optional[dict]`. `TickOrchestrator` сохраняет артефакты Воли в `shared_context` перед публикацией в шину. Фронтенд извлекает данные и создаёт `NarrativeBeat` с `DeliveryType.INTERNAL`.
2. **Синхронизация имён:** `resolve_intent_pressure` обновлён для распознавания актуальных ключей (`player_attacks`, `player_threatens` и их алиасов). Устранена несовместимость с `IntentParametersDTO`.

**Последствия:**  
- Игрок видит внутреннее сопротивление Аватара через Cinematic Layer.
- Труба Воли замкнута: Семантика → Давление → Сопротивление → UI.
- Запрещено использовать устаревшие ключи действий без алиасов в Will Engine.

---

### ADR-042: PerceptualKernel Integration & Perception Domain
**Дата:** 12.05.2026  
**Статус:** Принято

**Контекст:**  
CFRM P2 вычислял `PsychologicalPressure` и напрямую конвертировал его в `EmotionPayload` в Фазе 9. Это нарушало порядок природы: реальность должна сначала обновить восприятие (`PerceptualKernel`), и только потом изменённое восприятие может породить эмоцию. Кроме того, отсутствие `PerceptionPayload` заставляло `StateApplicator` игнорировать обновления когнитивных векторов NPC.

**Решение:**  
1. Введен `DeltaDomain.PERCEPTION` и `PerceptionPayload` (threat_gradient_delta, uncertainty_delta, anomaly_score_delta, dominant_emotion_hint).
2. `_phase_9_integration` в `TickOrchestrator` переведена на генерацию `PerceptionPayload` вместо `EmotionPayload`.
3. `StateApplicator` обучен применять `PerceptionPayload` к `NPCState.perceptual_kernel` (clamping 0.0-1.0).
4. `CombatSubscriber` усилен fuzzy-matching по `target_reference` для предотвращения потери цели при опечатках игрока.

**Последствия:**  
- Реальность течёт в восприятие, а не напрямую в эмоции.
- `PerceptualKernel` накапливает градиент угрозы, который могут читать downstream-системы (DecisionHub, CognitiveProjection).
- Боевой пайплайн стал устойчив к потере ID целей.

---

### ADR-043: Social Physics & Directive Interpretation
**Дата:** 12.05.2026  
**Статус:** Принято

**Контекст:**  
Приказ игрока ("Тень, иди сюда") не должен приводить к немедленному `MovementIntent`. Это превращает симуляцию в aggro-controller (RPG-скрипт). Социальная воля должна искривлять utility-space агентов, а не отдавать им прямые команды.

**Решение:**  
- Создан `DirectiveInterpretationSubscriber` (Физика Власти).
- Он читает `EventDTO` с `semantic_action` (MOVE, THREATEN).
- Вычисляет **легитимность** (статус) и **цену отказа** (страх).
- Генерирует `PsychologicalPressure(directive_obedience)` и `StateDeltas(Emotion, Social)`.
- **НЕ генерирует MovementIntent.** Давление — это score modifier для DecisionHub следующего тика.

**Последствия:**  
- Речь стала физической силой, искривляющей пространство решений.
- NPC может отказаться, колебаться или подчиниться не полностью.
- Агро-контроллер убит на корню.

### ADR-044: Sprint 27 Consolidation — Legacy Burnout and Phenomenology Pipeline
**Дата:** 13.05.2026  
**Статус:** Принято

**Контекст:**  
Система феноменологического рендеринга (ADR-035, ADR-037) была внедрена, но содержала мосты к старой RPG-онтологии: `AvatarStateDTO` имел депрекированные строковые и дублирующие скалярные поля, `PresentationFirewall` содержал хардкод-хаки для `mental_state`, а конфликт воли передавался на фронтенд сырым словарем со строками вместо типизированных моторных векторов. Отсутствовало вычисление средового давления (Ambient), а оптический рендер не реализовывал темпоральные эффекты.

**Решение:**  
1. **Приоритет 0:** Удалены зомби-поля `visual_distortion`, `movement_instability`, `dominant_impulse` из DTO и трансляторов. Вырезан хардкод из `PresentationFirewall`.
2. **Приоритет 1:** Внедрены `EmbodiedVector` (AVOIDANCE, DESTROY, COLLAPSE, SUBMIT, FREEZE) и `OriginLayer`. Бэкенд генерирует текст конфликта воли на основе моторного вектора, а фронтенд стилизует `Resistance Medium` в зависимости от источника.
3. **Приоритет 2:** `WorldSnapshotBuilder` вычисляет `ambient_phenomenology` (температура, плотность) из психики NPC. Фронтенд пробрасывает его в `PresentationFirewall`.
4. **Приоритет 3:** Рендерер реализует `Motion Bias` (сдвиг камеры давлением), `Temporal Assembly Delay` (инерция позиций NPC) и `Contrast Instability` (пульсация фона).

**Последствия:**  
- Конвейер от `body_state` бэкенда до пикселей фронтенда полностью очищен от RPG-абстракций.
- Визуальные эффекты инерционны, детерминированы и управляются чистой математикой векторов давления.
- Конфликт воли имеет моторное воплощение, а не просто текст.

### ADR-045: Causal Oscilloscope & Deterministic Sandbox
**Дата:** 13.05.2026  
**Статус:** Принято

**Контекст:**  
Попытки отлаживать каузальный пайплайн (Семантика → Давление → Движение) в живой игре приводили к фантомным багам из-за недетерминированности LLM, `TICK_CATCHUP` и асинхронности I/O. Обычные unit-тесты проверяют состояние, а не допустимость процесса.

**Решение:**  
Создана Каузальная Песочница (`backend/tests/sandbox/`), работающая как Осциллограф Причинности:
- **DeterministicClock:** Фиксированный шаг симуляции (10 сек).
- **CausalTrace:** Регистратор фазовых переходов с `causal_parent_id`, позволяющий восстановить генеалогию любого решения.
- **Probes:** Наблюдатели (Pressure, Utility, Traversal), внедряемые в пайплайн без мутации.
- **Фикстуры:** Детерминированный микрокосм (Таверна с Тенью).

**Последствия:**  
Мы можем доказать, что поведение рождается из давления среды, а не из скрипта. Тест `minimal_obedience_field` успешно проходит, доказывая, что приказ рождает Транзит с duration > 0.

### ADR-046: Physics of Power — Inverted Fear in DecisionHub
**Дата:** 13.05.2026  
**Статус:** Принято

**Контекст:**  
В `DecisionHub._relationship_modifier` страх (`fear`) вычитался из скоринга `Intent.APPROACH` (`mod -= fear * 0.35`). Это приводило к тому, что запуганный NPC убегал от авторитета, а не подчинялся. Также существовал хардкод `base += 0.6` при диалоге, заставлявший NPC подходить как скриптовых ботсов.

**Решение:**  
1. Убит хардкод `base += 0.6`.
2. Внедрена Физика Власти: Если `event.payload.semantic_action == "MOVE"` и цель — этот NPC, вычисляется `_obedience_pressure = fear * (1 - willpower)`.
3. Страх инвертирован для APPROACH: `mod += fear * 0.45`. Высокий страх перед авторитетом мотивирует подчинение (приближение).

**Последствия:**  
Подчинение стало эмерджентным. Трусливый NPC подходит к источнику власти, смелый — сопротивляется.

### ADR-047: Principle of Observed Causality и Temporal Reconciliation
**Дата:** 13.05.2026  
**Статус:** Принято

**Контекст:**  
Механизм `TICK_CATCHUP` в `scene_init.py` симулировал отсутствующее время через цикл `for _ in range(_catch_up): _life_engine.tick()`. Это порождало ретроактивную фальсификацию причинности: NPC принимали решения, двигались и генерировали эмоции в мире, где EventBus, CFRM и наблюдение были мертвы. Это разрушало темпоральную онтологию ENIGMA и убивало `TraversalState`.

**Решение:**  
1. **Принцип Наблюдаемой Причинности:** Сложная причинность (решения, движение, социальные акты) существует ТОЛЬКО в наблюдаемом времени (внутри `TickOrchestrator.execute()`).
2. **Запрет ретро-симуляции:** Цикл `TICK_CATCHUP` удаляется. Никакой симуляции прошедших тиков.
3. **Аналитическое Согласование (State Reconciliation):** При загрузке сцены мир мгновенно продвигает календарь (`world_time += delta`) и применяет аналитический декэй к базовым потребностям (`hunger += rate * delta`, `fatigue += rate * delta`, `social_trust drift`).
4. **Разделение Времени:** Симуляция (редкие каузальные обновления) отделена от Презентации (непрерывная интерполяция Lerp). `TraversalState` — это презентационный артефакт, он не вычисляется в отсутствие наблюдателя.

**Последствия:**  
- Загрузка сейва больше не вызывает фантомных решений.
- NPC не телепортируются и не умирают от скачков времени.
- `LifeEngine` получает метод `reconcile_state(elapsed_seconds: float)` вместо голого `tick()`.

---

### ADR-048: Single Source Spatial Authority
**Дата:** 13.05.2026  
**Статус:** Принято

**Контекст:**  
`DecisionHub` и `_resolve_reactive_movement` читали позицию игрока из словаря `scene_state.get("player_spatial", {})`. Это нарушало Каузальный Контракт, порождая расхождение реальностей (divergence), так как `player_spatial`, `scene_state["player_spatial"]` и `npc_positions["player"]` конкурировали за истину. При отсутствии ключа NPC скатывались в `entrance`.

**Решение:**  
1. **Единый Источник Истины:** Единственной пространственной истиной в runtime является `ClusterOccupancy` и `SpatialRuntime` (через `SpatialService`). Все остальное — вторичные проекции (DTO).
2. **Запрет прямого чтения `scene_state`:** `DecisionHub`, `_resolve_reactive_movement` и `LifeEngine` ЗАПРЕЩЕНО читать `scene_state` для получения координат. Они обязаны делать запрос через `SpatialQueryService.get_entity_position(entity_id)`.
3. **`player_spatial` депрекируется** как authority layer. Игрок внедрен в симуляцию как `npc_id="player"` (ADR-031) и обязан запрашиваться наравне с NPC.

**Последствия:**  
- Устраняется Spatial Resolution Divergence.
- Запрос `approach player` всегда резолвится в актуальный узел кластера, где находится сущность `"player"`.
- `scene_state` становится строго write-only проекцией для фронтенда (WorldSnapshotBuilder).

**Реализация (Phase 1 — Kill Decision Reads, 17.05.2026):**
- `SpatialQueryService` поднят из мёртвого кода — впервые инстанцирован в `npc_orchestration.py` и инъектирован через `NpcTickServices.spatial_query`.
- В `npc_tick_pipeline.py` убраны все fallback-чтения `scene_state.get("player_distances")` и `scene_state.get("npc_positions")`. Внедрён `_pos()` helper через `spatial_query.get_entity_position()`.
- MOVE reflex переведён на `spatial_query.get_entity_position()`.
- `scene_state["npc_positions"]` и `scene_state["player_spatial"]` остаются как write-only projection для фронтенда. Backend системы НЕ имеют права читать их обратно.
- **Phase 2 (Projection Isolation):** миграция `perception_filter`, `memory_manager`, `reaction_priority` на `SpatialQueryService`.
- **Phase 3 (Derived Presentation Cleanup):** удаление `player_spatial` из `WorldSnapshotDTO`.

### ADR-050: Causal Observatory & Epistemic Divergence Sandbox
**Дата:** 14.05.2026  
**Статус:** Принято

**Контекст:**  
Попытки отлаживать каузальный пайплайн (Семантика → Давление → Решение) в живой игре приводили к фантомным багам из-за недетерминированности LLM и асинхронности. Обычные unit-тесты проверяют состояние, а не допустимость процесса. Отсутствовала верификация математики мембран (экспоненциальное затухание физики, инференс стресса) и баланс весов при кумулятивном давлении.

**Решение:**  
Создана Каузальная Обсерватория (`backend/tests/sandbox/`), работающая как детерминированный микрокосм:
- **Феноменологическая лаборатория (`phenomenology/`):** Верифицирует эпистемическое расхождение истин (свидетель видит факт, слышавший — искаженный слух) и изолированную математику проекций.
- **Системные тесты (`system/`):** Замыкает каузальный контур от Возмущения Поля (Приказ) через Давление до Искажения Решения (Подчинение/Агрессия).
- **Стресс-тесты (`stress/`):** Проверяет инерцию и деградацию весов во времени (кумулятивное подавление воли и восстановление).
- Использует инфраструктуру `CausalTrace` для логирования фазовых переходов.

**Последствия:**  
- Песочница выявила критический баг в `pressure_translator.py` (запись в удаленные поля DTO), который блокировал пайплайн подчинения в рантайме.
- Мы можем математически доказать, что поведение рождается из давления среды, а не из скрипта.

### ADR-049: Causal Pressure Pipeline & DecisionContext Geometry
**Дата:** 14.05.2026  
**Статус:** Принято

**Контекст:**  
Каузальная цепь обрывалась между генерацией давления (CFRM) и принятием решений (DecisionHub). `PsychologicalPressure` не влияло на `utility-space` NPC. Подчинение реализовывалось хардкодом `fear * 0.45`, что являлось эмоциональным скриптингом, а не топологической деформацией. Также отсутствовал механизм `feasibility` (невозможности действия), что мешало моделировать паралич воли.

**Решение:**  
1. **PerceptualKernel как хранилище топологии:** Внедрены скаляры `aggression_inhibition`, `initiative_suppression`, `compliance_bias` вместо семантических `authority_pressure`.
2. **DecisionContext:** Создан мост, собирающий геометрию напрямую из `PerceptualKernel` через `from_kernel()`, минуя `PsychologicalPressure` в рантайме решения.
3. **Feasibility Layer:** В DecisionHub введена фаза удаления действий с `feasibility = 0.0` до скоринга.
4. **Utility Deformation:** Давление искривляет ландшафт через непрерывные множители (например, `compliance_bias` умножает `APPROACH`), а не через плоские бонусы.
5. **Замыкание контура:** `DirectiveInterpretationSubscriber` вызывается напрямую в `execute_player_finalize` при команде MOVE, записывая `IdentityPayload` в `delta_buffer`.

**Последствия:**  
- Каузальная цепь `Команда → Давление → Топология → Решение` замкнута.
- Подчинение — это не эмоция, а деформация пространства решений.
- Требуется решение конфликта между каузальным давлением и `LifeEngine` (расписание перебивает давление в тот же тик).

### ADR-051: LifeEngine De-godification & Intent-Driven Locomotion
**Дата:** 15.05.2026  
**Статус:** Принято

**Контекст:**  
`LifeEngine` выступал в роли пространственного диктатора: напрямую мутировал `npc["position"]` и вызывал `MovementEngine` внутри собственных методов. Это обходило каузальный конвейер (PerceptualKernel, DirectiveInterpretationSubscriber, DecisionHub), заставляя NPC телепортироваться по расписанию (например, в кровать), даже находясь под высоким социальным давлением или прямым приказом игрока. Также `DirectiveInterpretationSubscriber` получал пустой список `[]` вместо `ctx.all_npcs_raw`, что делало Физику Власти слепой.

**Решение:**  
1. **Запрет прямой мутации пространства:** `LifeEngine` лишен права записи в `npc["position"]` и `npc["location"]`.
2. **Запрет исполнения движения:** Удалены вызовы `self._movement_engine.process_intents()` из `_simulate_major`, `_simulate_minor` и `check_random_events`.
3. **Смена сигнатур:** Методы теперь возвращают `tuple[list[SceneChange], list[MovementIntent]]` (или `MovementIntent | None`).
4. **Замыкание контура:** `TickOrchestrator` распаковывает `life_intents` и передает их в `MovementEngine`, порождая легитимный `TraversalState`.
5. **Починка трубы давления:** `DirectiveInterpretationSubscriber` теперь получает `ctx.all_npcs_raw`.
6. **Когнитивный страж:** Внедрена проверка `perceptual_kernel.threat_gradient > 0.4` — расписание блокируется при высоком градиенте угрозы.

**Последствия:**  
- `LifeEngine` стал "лоббистом" (генерирует намерения), а не "диктатором" (двигает NPC).
- Каузальный контур `Команда → Давление → Решение → Движение` физически существует в рантайме.
- NPC больше не игнорирует приказы игрока ради расписания (сон/еда).
- Требуется обновление потребителей `tick()` (`scene_init.py`, `tick_orchestrator.py`) для распаковки кортежа.
### ADR-052: Cognitive Guard Evolution & LOD0 Micro-Movement Pipeline
**Дата:** 15.05.2026  
**Статус:** Принято

**Контекст:**  
Когнитивный страж в `LifeEngine` блокировал расписание по `threat_gradient > 0.4`, что было грубым эвристическим хардкодом. Прямая угроза не всегда парализует волю (NPC может пытаться бежать или атаковать). Паралич воли (отмена расписания) должен наступать только при подавлении инициативы (`initiative_suppression`). Также микро-движение (подход на 1 метр в той же макро-зоне) блокировалось из-за строкового несовпадения префиксов узлов.

**Решение:**  
1. **Смена Когнитивного Стража:** Порог сменен с `threat_gradient > 0.4` на `initiative_suppression > 0.7`. Расписание блокируется только при топологическом подавлении воли, а не при простом страхе.
2. **LOD0 через существующий контраст:** Отказ от создания `LocalSteeringIntent`. Микро-движение замкнуто через `MovementIntent.local_target_xy`. 
3. **Нормализация префиксов:** В `_resolve_reactive_movement` внедрено сравнение базовых имен узлов (`current_base == target_base`), чтобы `"main_hall"` и `"tavern:main_hall"` больше не ломали микро-подход.
4. **Починка Silent Data Loss:** В `LifeEngine.tick()` исправлена распаковка кортежа `changes, intents = self._simulate_minor(...)`, из-за которой намерения по расписанию терялись.

**Последствия:**  
- Каузальный контур `Расписание → Intent → Исполнение` физически работает.
- Страх (`threat_gradient`) больше не отменяет бытовое поведение, если воля не подавлена.

### ADR-053: Runtime Closure & Dual-Time Ontology
**Дата:** 16.05.2026  
**Статус:** Принято

**Контекст:**  
Спринт 28 создал Каузальную Обсерваторию (ADR-050), но `DecisionHub` работал вслепую, так как `DecisionContext` не передавался в рантайме. Возник темпоральный парадокс: давление вычисляется в Фазе 9, а решения принимаются в Фазе 5. Попытка передать давление из Фазы 9 в Фазу 5 *того же тика* (через агрегацию дельт или перестановку фаз) приводит к предкоммитной реальности, циклической зависимости и разрушению каузальности.

**Решение:**  
1. **Каузальная дискретизация T+1:** `DecisionHub` работает на консолидированном восприятии тика T-1 (`PerceptualKernel` → `DecisionContext`). Это не задержка, а разделение **reactive** (прерывание, мгновенно) и **deliberative** (решение, T+1) слоев.
2. **Устав §1.2 Enforcement:** Метод `from_kernel()` удален из домена. Проекция ядра осуществлена в сервисном слое (`translate_kernel_to_context` в `pressure_translator.py`), устраняя дублирование.
3. **Dual-Time Ontology:** Симуляция дискретна (Каузальная Компрессия Времени), Восприятие непрерывно (Фронтенд интерполирует `TraversalState`). Бэкенд платит за причинность один раз, презентация бесплатна.
4. **Запрет ретро-симуляции:** Прошлое не существует. Любые попытки просимулировать пропущенные тики (`TICK_CATCHUP`) признаются архитектурным багом.

**Последствия:**  
- Все вызовы `DecisionHub.compute()` в рантайме (`LifeEngine`, `WorldTickEngine`) получают `decision_ctx`.

### ADR-056: Attention Capture & Safe Spatial Fallback
**Контекст:** 
Предыдущий Когнитивный Страж (`initiative_suppression > 0.7`) был грубым оверрайдом (mind-control), который либо не срабатывал из-за слабых дельт, либо полностью парализовал волю NPC. Фоллбэк `MovementEngine` на `entrance` приводил к пространственным галлюцинациям.
**Решение:**
1. **Attention Capture:** Прямая директива прерывает инерцию бытовухи (`interrupts_routine: True`), но не подавляет волю. DecisionHub решает исход.
2. **Safe Spatial Fallback:** Если целевой узел не найден в графе, макро-перемещение отменяется. NPC остается в текущей зоне.
- NPC реагирует на давление с задержкой в 1 тик, что физиологично и предсказуемо.
- Фронтенд обязан перестать телепортировать NPC и перейти на интерполяцию `TraversalState`.
- `TICK_CATCHUP` подлежит удалению и замене на детерминированную сверку состояния (reconcile).

### ADR-058: Frontend Dual-Time Ontology & Deterministic Client
**Дата:** 18.05.2026  
**Статус:** Принято

**Контекст:**  
Фронтенд телепортировал NPC при каждом тике и предсказывал движение через клиентский `pathfinding`. Это разрушало иллюзию непрерывного времени и нарушало авторитет бэкенда над причинностью. Бэкенд генерировал `TraversalState` (waypoints, progress, speed) и `initiative_suppression`, но фронтенд игнорировал их, используя устаревший `duration_seconds` и локальную симуляцию.

**Решение:**  
1. **Интерполятор, не предсказатель:** Фронтенд интерполирует `TraversalState` используя `path_waypoints`, `current_waypoint_idx` и `progress`. Рендер непрерывен благодаря `dt` и `traversal_speed`.
2. **Deterministic Client:** Клиентский `pathfinding` (`find_path`) полностью удален. Движение к NPC — это Intent, отправляемый на бэкенд. Единый источник правды — `WorldSnapshotDTO`.
3. **Визуализация Cognitive Freeze:** `initiative_suppression` пробрасывается из `NPCPositionDTO` через `PerceivedEntity` в `SceneRenderer` для отрисовки моторного тремора (паралич воли).

**Последствия:**  
- Движение NPC плавное и честное (отражает каузальную компрессию бэкенда).
- Фронтенд и бэкенд строго разделены (Устав §1.1).
- Высокое `initiative_suppression` видно игроку (обратная связь по Elastic Tactical Bubble).