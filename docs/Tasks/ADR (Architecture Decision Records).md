# ADR — Архитектурный Атлас ENIGMA

> **Формат:** Домен → Текущая парадигма → Эволюция (ключевые ADR) → ✅ ВЕРИФИЦИРОВАННЫЕ ПОЧИНКИ → Убитые концепты → Архитектурные запреты.
> ИИ-ассистенту: ищи контекст по домену. Блоки `✅ ПОЧИНКИ` — это закрытые архитектурные баги, подтвержденные аудитом рантайма S50-53.

---

## 1. ФУНДАМЕНТ СИМУЛЯЦИИ И ВРЕМЯ (Core Pipeline & Time)
**Текущая парадигма:** Симуляция дискретна и каузально замкнута. Мутации проходят только через `DeltaBuffer`. Ретро-симуляция запрещена. 

**Эволюция (Ключевые ADR):**
- **ADR-001 (Delta Buffer):** Убита прямая мутация `all_npcs_raw`. Единственный путь: `Phase8Result → delta_buffer → StateApplicator.apply_batch()`.
- **ADR-002 (Time-driven vs Event-driven):** Разделение Фазы 0.5 (time-decay выполняется всегда) и Фазы 8 (event-driven, только при событиях).
- **ADR-013 (StateDeltas v2):** Плоский god-object заменен на `DeltaDomain` + типизированные frozen Payloads. Одна дельта = один домен.
- **ADR-047 (No Retro-simulation):** Убит `TICK_CATCHUP`. Пропущенное время не симулируется циклом `tick()`, а аналитически вычисляется через `reconcile_state(elapsed_seconds)`. Сложная причинность существует только в наблюдаемом времени.
- **ADR-059 (Dual-Time Ontology):** Транзиты привязаны к монотонному каузальному `scene_state["tick"]`, а не к реальному времени. Тик сохраняется при загрузке (`_preserved_tick`).
- **ADR-065 (Spatial Authority Consolidation):** Убита трехкратная ручная сборка `SpatialService.build_for_location()` в `TickOrchestrator`. Внедрен `_resolve_spatial_service()`.
- **ADR-066 (Single Movement Ownership):** Убит двойной вызов `process_intents()` в `npc_orchestration.py` и `TickOrchestrator`. Единственный владелец исполнения `MovementIntent` — `TickOrchestrator`. В доменную модель добавлен инвариант: повторная обработка интента с `processed=True` вызывает `RuntimeError`. Один Intent → один Executor → одно будущее.

**✅ ВЕРИФИЦИРОВАННЫЕ ПОЧИНКИ (Аудит S50-53):**
- **GAP1 (Когнитивный Оверлей):** УБИТ ADR-081. Темпоральная асимметрия устранена. Критический шок (`shock_impulse > 0.5`) инжектится в `all_npcs_raw` мгновенно (T+0) наравне с директивами. *Верифицировано: `tick_orchestrator.py:634`*.
- **NoneType finalize_result:** УБИТ ADR-085. `execute_player_finalize` не пробрасывал `player_result` в `_TickContext`, из-за чего метод возвращал `None` и крашил пайплайн. *Верифицировано: `tick_orchestrator.py:537`*.

**Убитые концепты:**
- *ADR-024 (Event-Sourced Global Reducer):* Идея глобального редюсера всех событий. Приводила к NP-hard проблеме. Заменена локальными кластерами CFRM.
- *Динамическая синхронизация `player_spatial` (S47):* Попытка обновлять `npc_positions["player"]` из `player_spatial` и внедрять точные координаты цели (`target_local_xy`). Откатана — ломала рантайм-конвейер движения и вызывала массовую телепортацию к `entrance`.

**Архитектурные запреты:**
- ❌ Прямая мутация стейта в обход `DeltaBuffer`.
- ❌ Циклы `tick()` для нагона времени (TICK_CATCHUP).
- ❌ Формирование ответа Фазы 8 через `List[dict]`.

---

## 2. ВОЛЯ, ДАВЛЕНИЕ И РЕШЕНИЯ (Will, Pressure & Decision)
**Текущая парадигма:** Решения NPC рождаются из искривленного пространства полезности (Utility Deformation). Воля — инерция, а не порог. Подчинение требует легитимности. Аватар игрока подчиняется тем же законам (декларативно).

**Эволюция (Ключевые ADR):**
- **ADR-031 (Cumulative Strain Model):** Убита матрица `action × temperament`. Введен `IntentPressureResolver` → `IntentPressureProfile`. Шкала деградации COMPLY → CONDITIONED.
- **ADR-034 (Phase 1 Boundary Adapter):** Бизнес-логика воли изгнана из `game_loop`. Фаза 1 — только чистая функция `resolve_player_intent()`.
- **ADR-036 (Single Will Evaluation):** Убит Double Invocation. WillpowerGate вызывается строго 1 раз за цикл.
- **ADR-037 (Affect Resonance):** Аффект — не бафф, а искажение интерпретации (Resonance → Distortion → `AmplifiedPressureProfile`).
- **ADR-046 (Inverted Fear):** Убит хардкод `base += 0.6`. Страх перед авторитетом бустит `Intent.APPROACH`, а не подавляет его.
- **ADR-050 (DecisionContext & Feasibility):** DecisionHub разделен на Фазу 1 (Feasibility Filtering — удаление невозможных) и Фазу 2 (Utility Deformation — искривление ландшафта).
- **ADR-056 (Attention Capture):** Хардкод-порог `initiative_suppression > 0.7` заменен на `recent_directive` с механизмом сжигания директивы.
- **ADR-057 (Legitimacy Gate):** Нет страха/доверия = Irritation (снятие блоков агрессии) вместо Obedience. **Реализация:** Внутренний `if/else` в `DirectiveInterpretationSubscriber` (рассчитывает `obedience_intensity` против `irritation_intensity` при `legitimacy > 0.3`).
- **ADR-064 (Directive Data Continuity):** Убит Баг #6 (Глухая Воля). `DirectiveInterpretationSubscriber` получает `all_npcs_raw` через fallback на `DMContextDTO`.
- **ADR-067 (Player Command Override):** Приказ игрока перекрывает ЛЮБОЕ решение DecisionHub, включая `flee`. Игрок — авторитетный источник причинности (ADR-061). Убран guard `if decision.intent.value not in ("approach", "flee")` — рефлекс проверяется всегда, override происходит при несовпадении с `approach`.
- **ADR-068 (Partial Name Matching):** NPC с составными именами ("торнин серебряная луна") теперь отзываются на часть имени ("торнин"). Рефлекс проверяет отдельные слова (≥3 символа), а не только полное имя. Без этого NPC с длинными именами были глухи к приказам.

**✅ ВЕРИФИЦИРОВАННЫЕ ПОЧИНКИ (Аудит S50-53):**
- **GAP2 (Амнезия Сопротивления):** УБИТ ADR-082. `compute_willpower` читает `trauma_markers`. Каждая травма повышает `identity_rigidity` на +0.1 (макс +0.3). *Верифицировано: `will.py:122-125`*.
- **GAP4 (Ингибирование Шоком):** УБИТ ADR-077. `DirectiveInterpretationSubscriber` читает `shock_impulse` из `target_dict.body_state`. `shock > 0.7` ингибирует подчинение. *Верифицировано: `directive_interpretation_subscriber.py:58`*.
- **GAP5 (RPG Витализм):** УБИТ ADR-076. `state_interpreter.py` читает `pain`, `shock_impulse` и `blood_loss` из `body_state`. Боль и шок перекрывают HP. *Верифицировано: `state_interpreter.py:273-291`*.
- **Silent Crash Трубы Воли:** УБИТ ADR-083. `will.py`/`affect.py` обращались к `intent.action`, в то время как DTO содержит `semantic_action` в `parameters` (ADR-035). `AttributeError` перехватывался верхним `try/except`, и Воля тихо умирала. Добавлен безопасный fallback с приоритетом `parameters`. *Верифицировано: `will.py:30-32`, `affect.py:56-60`*.

**Убитые концепты:**
- *ADR-030 (RPG Will Matrix):* Бинарная модель `action × temperament`.

**Архитектурные запреты:**
- ❌ Вызов WillpowerGate более 1 раза за цикл.
- ❌ Использование RPG-матриц поведения как онтологии.
- ❌ Передача сырых дельт давления из текущего тика в DecisionHub (только T-1) — *НАРУШЕНО хаком COGNITIVE_OVERLAY (см. Раздел 1)*.

---

## 3. ВОСПРИЯТИЕ И ФЕНОМЕНОЛОГИЯ (CFRM & Perception)
**Текущая парадигма:** Объективных фактов нет. Есть возмущения поля (`FieldDisturbance`), которые проецируются в субъективные феномены. Perception обновляется ДО Emotion.

**Эволюция (Ключевые ADR):**
- **ADR-025 (CFRM Core):** Глобального World нет. Введены `ClusterGraph`, `EventBuffer`, `MembraneField`. NPC хранит `PerceptualKernel`.
- **ADR-029 (CFRM Layer 1):** Spatial Index для O(1) поиска. Классификация событий по осям (PHYSICAL, COGNITIVE, SOCIAL).
- **ADR-033 (Deobjectification P2):** Смерть объективных событий. `EventDTO` превращается в `FieldDisturbance`. Восприятие вычисляется локально `LocalCausalSolver`.
- **ADR-040 (Epistemic Classification):** Введен `ClassificationResult` с `confidence`. Фallback-события имеют вес 0.2.
- **ADR-042 (Perception Domain):** Реальность течет в восприятие (`PerceptionPayload`), а не напрямую в эмоции.

**✅ ВЕРИФИЦИРОВАННЫЕ ПОЧИНКИ (Аудит S50-53):**
- **GAP6 (Синдром Глухого Общества):** Убит [S50]. Проблема была в потере семантики (GAP8).
- **GAP7 (Слепота Аватара):** Убит [S53]. Игрок парсится как наблюдатель в `_extract_observer_state`. Аватар получает давление от паники толпы. *Верифицировано: `local_causal_solver.py:320-324`*.

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
- **ADR-061 (Player Position Authority):** `player_spatial` — мёртвый источник (запись запрещена ADR-048 Phase 3). Фикс: `npc_positions.player` — единственный источник, `player_spatial` — только fallback при отсутствии.
- **ADR-069 (target_local_xy Propagation):** При `reactive:approach` координаты цели (позиция игрока) пробрасываются через `MacroMovementGoal.target_local_xy` → `SceneChange.target_local_xy` → `scene_state_manager`. Ранее координаты вычислялись в `_resolve_reactive_movement`, но терялись при создании `MacroMovementGoal` → NPC шли к центру узла вместо точной позиции.
- **ADR-070 (Ghost Position Interpolation):** При создании нового транзита, если NPC уже в активном транзите, `from_xy` вычисляется интерполяцией текущего прогресса по waypoints старого транзита. Без этого новый транзит начинался с устаревшей `local_position` → визуальная телепортация назад.
- **ADR-071 (Bridge Traversal Propagation):** `game_loop_bridge.py` пробрасывает `active_traversals` в `world_snapshot`. Без этого фронтенд не мог интерполировать движение — `_resolve_visual_xy` не находил waypoints и рисовал по `local_position` (старая позиция).
- **ADR-072 (Enrichment LOD0 Guard):** `_enrich_local_positions` больше не перетирает `local_position` для сдвинувшихся NPC. Если позиция уже валидна (установлена пайплайном), enrichment пропускает. Ранее NPC, получивший `micro_snap`, при следующей загрузке `scene_state` перетирался на центр узла из графа.

**✅ ВЕРИФИЦИРОВАННЫЕ ПОЧИНКИ (Аудит S50-53):**
- **GAP12 (Парадокс Призрачной Позиции):** Убит [S50]. `_enrich_local_positions` вычисляет интерполированную позицию для NPC в активном транзите. *Верифицировано: `scene_state_manager.py:1145,1585`*.
- **GAP9 (Конфликт Транзитов):** Убит [S51]. Сон блокируется непрерывными скалярами `threat_gradient > 0.3` и `stress > 50`. *Верифицировано: `life_engine.py:1179-1182`*.
- **GAP10 (Незваные NPC):** Убит [S52]. `EventContext` обогащён `target_id`. DecisionHub фильтрует бонус `APPROACH`. *Верифицировано: `decision_hub.py:916`*.

✅ ВЕРИФИЦИРОВАННЫЕ ПОЧИНКИ (Аудит S50-54):

GAP11 (Хардкод Глаголов): УБИТ S54. Хардкод _MOVE_VERBS удалён. IntentCompressor распознаёт наречия/местоимения 1-го лица ("сюда", "мне") и устанавливает target_reference='player'. Semantic Bridge пробрасывает MOVE + player в пайплайн. Верифицировано: intent_compressor.py:93-98, npc_tick_pipeline.py:467-472.

**Архитектурные запреты:**
- ❌ Прямая мутация `npc["position"]` или `npc["location"]`.
- ❌ Чтение позиций из `scene_state` (только `SpatialQueryService`).
- ❌ Вызов `scene_manager.apply_changes()` из подписчиков.
- ❌ Использование `TraversalState` без `MovementEngine`.
- ❌ Вызов `process_intents()` или `apply_changes()` из `npc_orchestration.py` (единственный владелец — `TickOrchestrator`).
- ❌ Повторная обработка `MovementIntent` (инвариант `processed=True`).
- ❌ `_enrich_local_positions` перетирает `local_position`, установленный пайплайном (LOD0 guard).
- ❌ Хардкод языковых глаголов в `npc_tick_pipeline.py` (после починки Semantic Bridge).

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

**✅ ВЕРИФИЦИРОВАННЫЕ ПОЧИНКИ (Аудит S54):**
- **NameError blood_loss_delta:** УБИТ ADR-084. `state_applicator.py` использовал переменную без извлечения из `PhysiologyPayload`. Добавлена строка экстракции. *Верифицировано: `state_applicator.py:427`*.

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

**✅ ВЕРИФИЦИРОВАННЫЕ ПОЧИНКИ (Аудит S50-53):**
- **GAP8 (IntentEventAdapter Data Loss):** Убит [S50]. `CommunicationIntent` обогащен `semantic_action` и `target_id`. `IntentEventAdapter` пробрасывает их в payload `NPC_SPOKE`. *Верифицировано: `intent_event_adapter.py:46`*.
- **GAP13 (Player-Only Social Physics):** УБИТ ADR-080. `DirectiveInterpretationSubscriber` вычисляет легитимность по `source_id`. NPC-to-NPC власть жива. *Верифицировано: `directive_interpretation_subscriber.py:77-92`*.

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
- **ADR-068 (Avatar Flesh Injection & API Suturing):** Труба Эмбодимента (Воля и Физиология) была оборвана на 3 уровнях: 1) Бэкенд собирал словарь аватара без `body_state` и `psyche` (сборка трупа), из-за чего ассемблер всегда возвращал `stability=1.0`. 2) API маршрутизатор `routes.py` выбрасывал `will_conflict_data` для Action-тиков. 3) Фронтенд не извлекал эти данные из ответа. Решение: инъекция живого стейта из `avatar_service` в `all_npcs_raw`, проброс `will_conflict_data` в API и вызов `infect()` на фронтенде.

**✅ ВЕРИФИЦИРОВАННЫЕ ПОЧИНКИ (Аудит S50-53):**
- **Эмбодимент Отключен (Embodiment Unwired):** Убит [S48/S53]. `GameScreen` извлекает `will_conflict_data` и вызывает `text_input.infect()`. `avatar_state` обновляется, передаваясь в `PresentationFirewall` и `PerceptualMomentum`. Аватар получает давление от паники толпы (GAP7).
- **Труба Эмбодимента Замкнута:** УБИТ ADR-086. `will_conflict_data` проверенно доходит от `tick_orchestrator` через `shared_context` (та же ссылка `id()`) до `text_input.infect()` на фронтенде. Поле ввода заражается моторным импульсом ("Замереть..."). *Верифицировано: рантайм-аудит `[EMBODIMENT_TRACE]` показывает `{'state': 'reluctant', 'resistance': 0.15, 'embodied_vector': 'freeze', 'counter_offer_text': 'Замереть...'}`*.
- **Расширение Fast Path словаря:** УБИТ ADR-087. `IntentCompressor._ACTION_LEMMAS` расширен приставочными глаголами (`выбить`, `откусить`, `укусить`, `душить`, `пнуть` и т.д.). pymorphy3 даёт лемму приставочного глагола как есть, не сворачивая к корню. *Верифицировано: `intent_compressor.py:32`*.

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
1. **Поиск по смыслу:** Разработчик, сталкивающийся с тем, что NPC подчиняется в нокауте, открывает секцию **2. ВОЛЯ** и сразу видит `Shock Inhibition Gap`.
2. **Контраст эволюции:** Четко видны "Убитые концепты" и живые "Разрывы". ИИ больше не предложит вернуть RPG-матрицу, но будет знать, что нужно починить мост `Physiology -> DecisionContext` или `IntentEventAdapter payload`.
3. **Синхронизация с рантаймом:** Формат отражает не желаемое состояние, а **исполняемую правду**, подтвержденную аудитом терминала, вплоть до конкретных строк кода и потерянных полей DTO.