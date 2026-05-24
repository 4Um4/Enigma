# ADR — Архитектурный Атлас ENIGMA

> **Формат:** Домен → Текущая парадигма → Эволюция (ключевые ADR) → Убитые концепты → Архитектурные запреты.
> ИИ-ассистенту: ищи контекст по домену, а не по номеру ADR.

---

## 1. ФУНДАМЕНТ СИМУЛЯЦИИ И ВРЕМЯ (Core Pipeline & Time)
**Текущая парадигма:** Симуляция дискретна и каузально замкнута. Мутации проходят только через `DeltaBuffer`. Ретро-симуляция запрещена. 

**Эволюция (Ключевые ADR):**
- **ADR-001 (Delta Buffer):** Убита прямая мутация `all_npcs_raw`. Единственный путь: `Phase8Result → delta_buffer → StateApplicator.apply_batch()`.
- **ADR-002 (Time-driven vs Event-driven):** Разделение Фазы 0.5 (time-decay выполняется всегда) и Фазы 8 (event-driven, только при событиях).
- **ADR-013 (StateDeltas v2):** Плоский god-object заменен на `DeltaDomain` + типизированные frozen Payloads. Одна дельта = один домен.
- **ADR-047 (No Retro-simulation):** Убит `TICK_CATCHUP`. Пропущенное время не симулируется циклом `tick()`, а аналитически вычисляется через `reconcile_state(elapsed_seconds)`. Сложная причинность существует только в наблюдаемом времени.
- **ADR-065 (Spatial Authority Consolidation):** Убита трехкратная ручная сборка `SpatialService.build_for_location()` в `TickOrchestrator`. Внедрен `_resolve_spatial_service()`, гарантирующий приоритет инъекции из `GameLoop` над сборкой на лету.

**Убитые концепты:**
- *ADR-024 (Event-Sourced Global Reducer):* Идея глобального редюсера всех событий. Приводила к NP-hard проблеме. Заменена локальными кластерами CFRM.
- *Динамическая синхронизация `player_spatial` (S47):* Попытка обновлять `npc_positions["player"]` из `player_spatial` и внедрять точные координаты цели (`target_local_xy`). Откатана — ломала рантайм-конвейер движения и вызывала массовую телепортацию к `entrance`.

**Архитектурные запреты:**
- ❌ Прямая мутация стейта в обход `DeltaBuffer`.
- ❌ Циклы `tick()` для нагона времени (TICK_CATCHUP).
- ❌ Формирование ответа Фазы 8 через `List[dict]`.

---

## 2. ВОЛЯ, ДАВЛЕНИЕ И РЕШЕНИЯ (Will, Pressure & Decision)
**Текущая парадигма:** Решения NPC рождаются из искривленного пространства полезности (Utility Deformation). Воля — инерция, а не порог. Подчинение требует легитимности. Аватар игрока подчиняется тем же законам.

**Эволюция (Ключевые ADR):**
- **ADR-031 (Cumulative Strain Model):** Убита матрица `action × temperament`. Введен `IntentPressureResolver` → `IntentPressureProfile`. Шкала деградации COMPLY → CONDITIONED.
- **ADR-034 (Phase 1 Boundary Adapter):** Бизнес-логика воли изгнана из `game_loop`. Фаза 1 — только чистая функция `resolve_player_intent()`.
- **ADR-036 (Single Will Evaluation):** Убит Double Invocation. WillpowerGate вызывается строго 1 раз за цикл.
- **ADR-037 (Affect Resonance):** Аффект — не бафф, а искажение интерпретации (Resonance → Distortion → `AmplifiedPressureProfile`).
- **ADR-046 (Inverted Fear):** Убит хардкод `base += 0.6`. Страх перед авторитетом бустит `Intent.APPROACH`, а не подавляет его.
- **ADR-050 (DecisionContext & Feasibility):** DecisionHub разделен на Фазу 1 (Feasibility Filtering — удаление невозможных) и Фазу 2 (Utility Deformation — искривление ландшафта).
- **ADR-056 (Attention Capture):** Хардкод-порог `initiative_suppression > 0.7` заменен на `recent_directive` с механизмом сжигания директивы.
- **ADR-057 (Legitimacy Gate):** Нет страха/доверия = Irritation (снятие блоков агрессии) вместо Obedience.
- **ADR-064 (Directive Data Continuity):** Убит Баг #6 (Глухая Воля). `DirectiveInterpretationSubscriber` получает `all_npcs_raw` через fallback на `DMContextDTO` при холодном кэше `LifeEngine`. Труба Воли больше не обрывается на последней миле.

**Убитые концепты:**
- *ADR-030 (RPG Will Matrix):* Бинарная модель `action × temperament`.

**Архитектурные запреты:**
- ❌ Вызов WillpowerGate более 1 раза за цикл.
- ❌ Использование RPG-матриц поведения как онтологии.
- ❌ Передача сырых дельт давления из текущего тика в DecisionHub (только T-1).

---

## 3. ВОСПРИЯТИЕ И ФЕНОМЕНОЛОГИЯ (CFRM & Perception)
**Текущая парадигма:** Объективных фактов нет. Есть возмущения поля (`FieldDisturbance`), которые проецируются в субъективные феномены. Perception обновляется ДО Emotion.

**Эволюция (Ключевые ADR):**
- **ADR-025 (CFRM Core):** Глобального World нет. Введены `ClusterGraph`, `EventBuffer`, `MembraneField`. NPC хранит `PerceptualKernel`.
- **ADR-029 (CFRM Layer 1):** Spatial Index для O(1) поиска. Классификация событий по осям (PHYSICAL, COGNITIVE, SOCIAL).
- **ADR-033 (Deobjectification P2):** Смерть объективных событий. `EventDTO` превращается в `FieldDisturbance`. Восприятие вычисляется локально `LocalCausalSolver`.
- **ADR-040 (Epistemic Classification):** Введен `ClassificationResult` с `confidence`. Фallback-события имеют вес 0.2.
- **ADR-042 (Perception Domain):** Реальность течет в восприятие (`PerceptionPayload`), а не напрямую в эмоции.

**Архитектурные запреты:**
- ❌ Хранение `EventDTO` в `EventBuffer` (только `FieldDisturbance`).
- ❌ Мутация состояния из CausalObserver.
- ❌ Прямая генерация эмоций из боевых событий (только через Perception).

---

## 4. ПРОСТРАНСТВО И ЛОКОМОЦИЯ (Spatial & Movement)
**Текущая парадигма:** `SpatialQueryService` — единственный авторитет координат. Движение — *результат* давления. Жесткое разделение макро-навигации (LOD1) и микро-рулежки (LOD0). Жизненный цикл движения отделен от личности.

**Эволюция (Ключевые ADR):**
- **ADR-008 (Spatial Centralization):** Убит глобальный `_connections_data` и кэш `_graphs`. Единственный источник — `SpatialService`.
- **ADR-010 (Macro/Micro Zones):** Архетипы переведены на макро-зоны. Убита парализация из-за микро-зон.
- **ADR-019 (Traversal State):** Диагноз телепортации. Введен `TraversalState` как презентационный артефакт.
- **ADR-048 (Single Spatial Authority):** Чтение `scene_state["player_distances"]` запрещено. Внедрен `SpatialQueryService`.
- **ADR-051 (LifeEngine De-godification):** LifeEngine лишен права прямой мутации позиции.
- **ADR-052 (LOD0/LOD1 Split):** Нормализация префиксов. Починка Silent Data Loss с интентами.
- **ADR-060 (Movement Ontology Split):** `MovementIntent` объединяет LOD0 и LOD1. `LocalSteeringIntent` отвергнут.
- **ADR-061 (Player Position Authority):** `player_spatial` — мёртвый источник (запись запрещена ADR-048 Phase 3). `npc_orchestration` перезаписывал `npc_positions.player.local_position` из протухшего `player_spatial`, убивая актуальные координаты от фронтенда. Фикс: `npc_positions.player` — единственный источник, `player_spatial` — только fallback при отсутствии.

**Архитектурные запреты:**
- ❌ Прямая мутация `npc["position"]` или `npc["location"]`.
- ❌ Чтение позиций из `scene_state` (только `SpatialQueryService`).
- ❌ Вызов `scene_manager.apply_changes()` из подписчиков.
- ❌ Использование `TraversalState` без `MovementEngine`.

---

## 5. ФИЗИОЛОГИЯ И БОЙ (Physiology & Combat)
**Текущая парадигма:** Тело — инерционная система. Бой — не режим, а давление на физику. Удар порождает каскад: Сила → Боль → Шок → Эмоция.

**Эволюция (Ключевые ADR):**
- **ADR-015 (Physiology Domain):** Убиты RPG Hit Roll и AC. Введены `body_profile`, `InjuryDTO`, ImpactEngine (Pure Function).
- **ADR-020 (DRSL):** Введен `ReductionPolicy`. Тело не складывается (`ADDITIVE`), оно эволюционирует (`PHYSICS_COMPOSITE`).
- **ADR-021 (CombatSubscriber):** Мост `EventDTO → ImpactEngine`. Возвращает ТОЛЬКО Physiology-дельты.
- **ADR-022 (Leaky Integrator):** Физиология затухает по экспоненте `S_t = S_{t-1} * exp(-lambda * dt)`.
- **ADR-027 (Layered Reduction):** Каскад в рамках одного тика: Physical → Materialization → Cognitive → Social.
- **ADR-028 (Config Migration):** `combat_stats` удалены из JSON.

**Архитектурные запреты:**
- ❌ Прямая мутация HP аватара в обход `ImpactEngine`.
- ❌ `CombatSubscriber` пишет в Emotion (Domain Leakage).
- ❌ Использование RPG-абстракций (Hit Roll, AC).

---

## 6. СОЦИАЛЬНАЯ ФИЗИКА И ПАМЯТЬ (Social & Memory)
**Текущая парадигма:** Социальные акты (приказы) искривляют utility-space цели. Память многослойна и управляется строго через MemoryManager.

**Эволюция (Ключевые ADR):**
- **ADR-005/006 (NPC Social Mapping):** Маппинг `social_stats` в `relationship_cache`. Обогащение из `village_relations.json`.
- **ADR-007 (Idle Sync):** Синхронизация `all_npcs_raw` в idle-пути.
- **ADR-043 (Social Physics):** Приказ генерирует `directive_obedience` (давление), а не `MovementIntent`.

**Архитектурные запреты:**
- ❌ Публикация в память в обход `MemoryManager`.
- ❌ `DirectiveInterpretationSubscriber` генерирует `MovementIntent`.
- ❌ Вызов директивы без инъекции `all_npcs_raw`.

---

## 7. ФРОНТЕНД, ПРЕЗЕНТАЦИЯ И ВВОД (UI & Embodiment)
**Текущая парадигма:** Фронтенд — сенсорный орган, искажающийся вместе с аватаром. Ввод проходит через моторное сопротивление и семантическое сжатие.

**Эволюция (Ключевые ADR):**
- **ADR-011/014 (Narrative Beats):** Убран плоский чат. Введены пузыри, спикеры, фильтрация эха.
- **ADR-035 (Intent Compression):** Русская морфология (pymorphy3 Fast Path + LLM Slow Path). Галлюцинации LLM отсекаются Pydantic.
- **ADR-038 (Embodied Perception DTO):** Бэкенд присылает скаляры давления и моторные импульсы, а не RPG-статы.
- **ADR-039 (Resistance Medium):** Конфликт воли = инфекция поля ввода (`text_input.infect()`). Феноменологический рендеринг (S-curve инерция).
- **ADR-041 (Will Conflict Data):** Проброс конфликта воли через API.

**Архитектурные запреты:**
- ❌ Импорт `backend/app/` во фронтенд (Устав §1.1).
- ❌ Передача Игроку внутренних метрик NPC (HP, fear).
- ❌ Использование `asdict()` на границе API без валидации.

---

## 8. НАБЛЮДАЕМОСТЬ И ДИАГНОСТИКА (CDS & Sandbox)
**Текущая парадигма:** Наблюдение не создает причинность. Тестирование каузальных цепей через изолированные Осциллографы.

**Эволюция (Ключевые ADR):**
- **ADR-003 (Test Determinism):** Убраны I/O фикстуры, введены синтетические фабрики.
- **ADR-004 (Phase 8 Handlers):** Memory/Scene обработчики признаны ненужными.
- **ADR-009 (DI Primitives):** В `InterpretationEngine` передаются примитивы, а не объекты.
- **ADR-045 (Causal Oscilloscope):** Создан `DeterministicClock` и `CausalTrace` для верификации причинности.
- **CDS Integration (S39):** Интеграция пассивной системы диагностики.

**Архитектурные запреты:**
- ❌ Обратная связь из CDS в рантайм симуляции.
- ❌ Прерывание каузального потока при падении CDS.

---

### Почему этот формат спасает проект:
1. **Поиск по смыслу:** Разработчик, сталкивающийся с тем, что NPC не двигается, открывает секцию **4. ПРОСТРАНСТВО И ЛОКОМОЦИЯ** и видит всю историю: от запрета мутации позиции (ADR-008) до De-godification (ADR-051) и разделения физик (ADR-060).
2. **Контраст эволюции:** Четко видны "Убитые концепты". ИИ больше не предложит вернуть глобальный Reducer или RPG-матрицу воли.
3. **Синхронизация с Уставом:** Формат зеркалит доменную структуру Каузального Контракта v2.0 и Архитектурного Устава, создавая единое поле семантики.