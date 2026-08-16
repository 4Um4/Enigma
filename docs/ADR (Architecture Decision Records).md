# ENIGMA ADR MASTER INDEX (Canonical Laws)
> Скомпилировано из 150+ хронологических ADR. 
> Содержит только актуальные архитектурные законы, инварианты и запреты.
> Нарушение любого пункта = архитектурный баг.

---

## DOM-01: FOUNDATION (Core Pipeline, Time, State)

**L1: State Mutation Law** (ADR-001, 013, 117)
Единственный путь мутации: `Phase8Result → delta_buffer → StateApplicator.apply_batch()`. Сериализация обязана быть Round-Trip (`from_legacy ↔ write_to_legacy`).
- Taboo: ❌ Прямая мутация `all_npcs_raw` в обход `DeltaBuffer`. ❌ Конструктор `NPCState(...)` в тестах (использовать `from_legacy`).
- Files: delta_buffer.py, state_applicator.py, npc_state.py

**L2: Runtime Purity Law** (ADR-O-302, TZ09-1, TZ10-1, S83.1)
Тик — чистая функция (`TickState → TickMutation`). Ядро не знает 'player' или 'dm_ctx', только `InterventionEvent`. Время симуляции (`game_time_seconds`) — единственный авторитет. `random.*` запрещён, используется `KernelRNG(tick, npc_id, salt)`.
- Taboo: ❌ Ветвление `if dm_ctx` в ядре. ❌ `time.time()`/`datetime.now()` в симуляции. ❌ Параметр `svc: Any` в `NpcTickPipeline.run()`.
- Files: tick_orchestrator.py, npc_tick_pipeline.py, kernel_rng.py, contracts/interventions.py

**L3: No Retro-Simulation Law** (ADR-047, 311)
Пропущенное время аналитически вычисляется через `reconcile_state()`. Ядро обязано возвращать `final_scene_state` для коммита, чтобы не терять мутации.
- Taboo: ❌ Циклы `tick()` для нагона времени. ❌ Коммит устаревшего `scene_state` из `idle_tick`.
- Files: life_engine.py, tick_orchestrator.py, game_loop/__init__.py

**L4: Silent Failure Prohibition** (ADR-O-308)
Скрытые баги (`except Exception: pass`) — нарушение контракта. Опциональные зависимости (pymorphy3) работают в Degraded Mode с логированием. Падение симуляции должно быть громким (`SimulationIntegrityError`).
- Taboo: ❌ Пустые `except`. ❌ Возврат тихого `None` на границе API.
- Files: dm_router.py, intent_compressor.py, errors.py

**L4.1: Async Intent Compression Law** (ADR-159, S118)
Внедрён асинхронный `IntentCompressor` в `GameLoop`. Метод `compress()` (async) вызывает LLM (Slow-Path) или Fast-Path ДО того, как ядро получит текст. Возвращает `IntentSemanticField`. Ядро больше не парсит текст.
- Taboo: ❌ Синхронный вызов LLM в `phase_1_input.py`. ❌ Создание `IntentCompressor(llm_client=None)` в production.
- Files: game_loop/__init__.py, input/intent_compressor.py

**L4.2: GameActionResponse Contract Law** (ADR-161, S118)
`GameActionResponse` (результат `GameLoop.run_turn`) возвращается как `dict`, а не несуществующий класс. Содержит `dm_response`, `world_snapshot`, `will_conflict_data`.
- Taboo: ❌ Возврат инстанса кастомного класса `GameActionResponse` из API-роута. ❌ Отсутствие `world_snapshot` в ответе.
- Files: game_loop/__init__.py, api/routes.py

---

## DOM-02: WILL, PRESSURE & DECISION

**L5: Will & Pressure Law** (ADR-031, 036, 088, O-146, 149)
Воля — инерция, а не порог. `WillpowerGate` вызывается 1 раз за цикл. Решения рождаются из искривленного давления (Utility Deformation), а не скриптов. Приказ игрока перекрывает решения хаба. Needs (priority=0.8) перезаписывают Schedule (priority=0.6).
- Taboo: ❌ Вызов `WillpowerGate` более 1 раза. ❌ RPG-матрицы `action × temperament`. ❌ Дефолтный `EmotionalVector` для ATTACK.
- Files: will.py, decision_hub.py, life_engine.py, affect.py

**L6: Cognitive Contour Law (PE Active Inference)** (ADR-S93.2, TZ08-3, 152)
Ожидания (T-1) преобразуются в `drive_modifiers` (T0) через `tanh` и `Clamp` (MAX 0.25). PE не может доминировать над DRF. `StateApplicator` — Single Writer для EMA.
- Taboo: ❌ Вычисление EMA вне `StateApplicator`. ❌ Асинхронные LLM/Rules внутри `game_loop` до применения состояния.
- Files: expectation_store.py, pe_modifier_resolver.py, rules_subscriber.py

**L7: LLM & Narrative Exile Law** (ADR-TZ05-1, TZ08-7, O-313)
Тяжёлые I/O (диалоги, LLM-парсинг) вынесены в `TaskScheduler` (`game_loop`). Ядро не формирует промпты и не читает ментальные объекты. DM-контур использует символическую интерпретацию наблюдаемых действий (`observed_state`), а не сырые поля (`stress`, `fear`).
- Taboo: ❌ Вызов LLM внутри `TickOrchestrator`/`DecisionHub`. ❌ Чтение `psyche`/`social_stats` в слое вербализации.
- Files: game_loop/task_scheduler.py, dm_agent.py, verbal_stance.py, npc_tick_pipeline.py

**L7.1: Proactive Intent & Aggression Triggers Law** (ADR-163, ADR-165, S118)
`DecisionHub.PROACTIVE_INTENTS` расширена: NPC могут инициировать диалог (`Intent.TALK`) в idle_tick. Триггер превентивной агрессии: если `perceptual_kernel.threat_gradient > 0.5`, NPC может выбрать `ATTACK` даже в `WORLD_TICK` без прямой провокации.
- Taboo: ❌ Хардкод запрета на ATTACK в idle_tick. ❌ Игнорирование `threat_gradient` при генерации proactive интентов.
- Files: services/npc/decision_hub.py, life_engine.py

---

## DOM-03: PERCEPTION & PHENOMENOLOGY (CFRM)

**L8: CFRM & Somatic Gate Law** (ADR-025, O-139, O-143, O-147)
Объективных фактов нет — есть возмущения поля (`FieldDisturbance`). Тело — фильтр восприятия. Боль/шок проходят через `PerceptualKernel.somatic_urgency` ДО семантического парсинга. Эмоции конвертируются только в моторные проявления (`ManifestationDTO.tags`).
- Taboo: ❌ Хранение `EventDTO` в `EventBuffer`. ❌ Инъекция `pain`/`shock` напрямую в psyche. ❌ Показ скрытых эмоций (fearful) в UI — только физика (tense, rigid).
- Files: local_causal_solver.py, perceptual_kernel.py, behavior_manifestation_service.py

---

## DOM-04: SPATIAL & LOCOMOTION

**L9: Spatial SSOT & Factory Law** (ADR-008, 048, S82.0, TZ04-4, O-314)
`SpatialFactory.build_for_campaign()` — единственный сборщик графа. Чтение позиций только через `SpatialQueryService`. `player_spatial` мёртв, истина в `npc_positions["player"]`. Актор движения определяется Слоем Интерпретации (`MovementRequest`), а не гаданием в ядре.
- Taboo: ❌ Прямая сборка `SpatialService` в обход фабрики. ❌ Чтение `player_distances` из `scene_state`. ❌ Парсинг текста игрока в `TickOrchestrator` для вычисления актора.
- Files: spatial_factory.py, spatial_query_service.py, domain/movement.py

**L10: Traversal FSM Law** (ADR-TRAV-FSM, 130.1/2, S90.4)
`SceneStateManager` — единственный владелец lifecycle перемещений. Движение = результат решения, а не триггер. Фронтенд рендерит либо `velocity` (ETKE-IK микро-перемещения), либо `active_traversals` (FSM макро-пути).
- Taboo: ❌ Перезапись активного транзита (`status="MOVING"`). ❌ Создание нового `TraversalState` при `traversal_complete` (нужен snap `local_position`). ❌ Прямая мутация `status` в обход FSM.
- Files: scene_state_manager.py, movement_engine.py, event_compiler.py

**L11.1: Spatial Agency Law** (ADR-O-330)
NPC формирует семантическое намерение достижения цели (`SpatialTargetIntent`). Spatial Kernel независимо разрешает это намерение в физическую цель (`ResolvedSpatialTarget`). Ни один NPC Goal не обязан ссылаться на заранее существующий навигационный узел.
- SA-1: Decision Layer (LifeEngine/Pipeline) НЕ ИМЕЕТ ПРАВА генерировать `target_node_id` или вызывать `resolve_node()`.
- SA-2: Только `SpatialTargetResolver` (через `MovementBridge`) разрешает намерение в координаты/узел. Поддерживает полиморфный результат: `NAV_NODE` (макро) или `LOCAL_POSITION` (микро).
- SA-3: `target_node_id` в `MacroMovementGoal` является временной compatibility projection, а не источником истины.
- SA-4: Ошибка разрешения (`UNAVAILABLE`) не маскируется пустой строкой — интент исключается из исполнения и логируется.
- SA-5: Семантическое намерение остаётся первичным контрактом. Физический узел — лишь проекция.
- Taboo: ❌ Прямой вызов `spatial_service.resolve_node()` или `get_furthest()` из `LifeEngine` или `NpcTickPipeline`. ❌ Передача точных координат внутри `SpatialTargetIntent`.
- Files: domain/spatial_target.py, services/spatial/spatial_target_resolver.py, services/phases/movement_bridge.py

**L11: Hybrid Geometry & Stigmergy Law** (ADR-S90.1, S91, O-324, O-329)
Микро-движение использует `DriveVector` (ETKE-IK), макро — `MovementIntent`. Динамическое поле возможностей (`DynamicAffordanceField`) хранит структурные деформации и поведенческие следы. Маршрутизация геометрически валидирует сегменты пути (Dynamic Doorway Routing), не доверяя слепо графу.
- Taboo: ❌ `MovementIntent` для микро-перемещений. ❌ Очистка стигмергии при смене локации. ❌ Доверие графу без проверки `is_path_blocked`.
- Files: motion_pipeline.py, world_topology_provider.py, motion_core.py

---

## DOM-05: PHYSIOLOGY & COMBAT

**L12: Physiology & Death Lock Law** (ADR-015, 123, 127, HP-UNIFICATION)
Убиты RPG Hit Roll и AC. `body_state["current_hp"]` — единственный SSOT для HP. Смерть — необратимый процесс (`evaluate_vital_state()`). Мёртвые NPC (`life_status="DEAD"`) исключаются из пайплайна до Фазы 1. Боевые кубики изолированы через `KernelRNG`.
- Taboo: ❌ Прямая запись в `state.hp`. ❌ `hp <= 0` как источник смерти. ❌ Decay для мёртвых. ❌ Использование `random.*` в `combat_math.py`.
- Files: vital_state.py, impact_engine.py, state_applicator.py, combat_math.py

**L12.1: D&D 5e Combat Math Law** (ADR-164, S118)
`ImpactEngine._resolve_contact` переведён на вызов `attack_roll` из `combat_math.py`. Результаты (Hit/Miss/Crit) маппятся на `ContactLevel` (MISS, GLANCING, PARTIAL, SOLID, PERFECT). Сохранилась изоляция `KernelRNG`.
- Taboo: ❌ Вычисление попадания внутри `impact_engine.py`. ❌ Использование legacy-формул урона в обход `combat_math.py`.
- Files: services/combat/impact_engine.py, combat_math.py

---

## DOM-06 & 09: SOCIAL, MEMORY & AFFECTIVE

**L13: Relationship SSOT & Affective Hysteresis Law** (ADR-121, 138, O-206, S96.2)
`RelationshipStore` (0-100) — единственный SSOT отношений. Аффективная нагрузка вычисляется как интеграл с гистерезисом (асимметричный аттрактор), изолирована от логики памяти и физиологии. `integrate_affective_pressure` — единственный владелец Active Inference.
- Taboo: ❌ Персистенция `relationship_cache` внутри `NPCState`. ❌ Интегратор с утечкой для `affective_load`. ❌ Воскрешение `pressure_derivation.py`.
- Files: relationship_store.py, affective_integrator.py, state_applicator.py

**L14: Epistemic Memory Law** (ADR-S86.7, O-325)
Память не генерирует идентичность без каузального входа. NPC-NPC взаимодействия порождают социальные дельты. Труба памяти NPC фильтруется через `perception_filter` (запрет телепатии).
- Taboo: ❌ Запуск L2.5 кристаллизации в idle без `phase_2_events`. ❌ Запись в память реплик, не услышанных NPC.
- Files: memory_manager.py, state_applicator.py, pipeline_runner.py

---

## DOM-07: FRONTEND, PRESENTATION & INPUT

**L15: Frontend Authority Law** (ADR-TZ03-1, 156, MANIFEST)
Backend — единственный источник истины. Фронтенд — pure renderer, лишён права генерировать время, аватара и журнал. DTO канонизированы.
- Taboo: ❌ `game_time_seconds +=` во фронтенде. ❌ Восстановление `player_spatial`. ❌ Вычисление manifestations на фронтенде.
- Files: frontend/api_client.py, game_screen.py, scene_renderer.py

**L16: Epistemic Boundary Law** (ADR-TZ08-4/6, 093, O-147)
DM-агент — строгий локальный наблюдатель. Читает только `observed_state` и `embodied_traces`. Нарратив рождается из наблюдаемых действий, а не сырых ментальных полей. `WorldProjectionBuffer` (оффскрин-симуляция) — pure function, не мутирует мир.
- Taboo: ❌ Чтение `stress_delta`, `real_state`, `recalled_facts` в DM-слое. ❌ Возврат `dm_frame` из ядра симуляции.
- Files: agents/dm_agent.py, scene/r3_direct_builder.py, world_projection_buffer.py

**L16.1: Three-Channel Presentation & Body Topology Law** (ADR-O-331, S147)
`WorldSnapshotDTO` расширен независимыми каналами `VisualDTO` и `AudibleDTO`, рождёнными из `PerceivedSignals` в `PresentationAssembler`. Запрет `Visual First`: DTO не зависят друг от друга и от `NarrativeDTO`. Инвентарь игрока переведён со строковых списков на `BodyTopology` (D&D 5e Encumbrance + Bulk System). `scene_state["player_body_topology"]` — единственный SSOT.
- Taboo: ❌ Чтение `player_inventory_snapshot` (legacy). ❌ Генерация `VisualDTO` на основе `NarrativeDTO`. ❌ Использование `Item` без учёта `weight` и `bulk`.
- Files: domain/body.py, domain/presentation.py, services/body/body_topology_service.py, services/perception/presentation_assembler.py

---

## DOM-10: IDENTITY & ONTOLOGY

**L17: Identity Pipeline Law** (ADR-O-208, 211, TIFL-001)
L1Chronicle — append-only SQLite-история деформаций. L3 (`EffectiveDrives`) — строго эфемерная проекция (L0 + L1). `CalibrationEngine` не мутирует L0. Убеждения (Beliefs) — это линзы (модификаторы весов), а не гены (скаляры). 
- Taboo: ❌ Удаление из `L1Chronicle`. ❌ Кэширование L3. ❌ Фоллбэк на L0 (`drives_base`) в `InterpretationEngine`. ❌ Мутация `drives_runtime` минуя Belief Layer.
- Files: l1_chronicle.py, drive_resolver.py, calibration_engine.py

**L18: Belief Crystallization Law (L2.5)** (ADR-O-305, 306, 307)
Трёхслойная модель: L1 (Факты) → L1.5 (PatternDetector: чистая статистика) → L2.5 (Belief Engine: психологическая проекция). Асимметричная травма (x6 множитель для опровержений). L1Chronicle фильтруется Тройной Мембраной (Физика, Личность, Социум).
- Taboo: ❌ Поля `trait`/`emotion` в PatternDetector. ❌ Скалярный страх (убеждение без `source_id`). ❌ Чтение L1Chronicle напрямую из Belief Engine.
- Files: pattern_detector.py, belief_crystallization_engine.py, crystallized_belief_store.py

**L19: Channel Topology & Task Layer Law** (ADR-O-312, 313)
Все процессы классифицируются по физике: Field (EMA), Reservoir (уровень), Structural (накопитель), Cognitive (убеждения). Тяжёлые процессы (диалоги) отделены: `Need → Intent → Task → Materializer → Event`.
- Taboo: ❌ Определение класса канала по реализации. ❌ Прямой вызов материализации из `TickOrchestrator`. ❌ Блокирующее I/O в ядре.
- Files: homeostasis_projector.py, domain/execution.py, task_scheduler.py

**L20: LifeProject & Agency Model Law** (ADR-O-315, 316, 317, 320, 321)
L0 (`CoreOrientation`) неизменен. L2.7 (`life_project`) — динамический FSM, управляемый Identity Pressure Vector. Anti-Script Constraint: сценарии не могут напрямую задавать решения агента, если есть внутренняя причинная цепь.
- Taboo: ❌ Мгновенная смена `life_project`. ❌ Бусты `life_project` в стадиях `LOST`/`SEARCHING`. ❌ Скалярный `identity_crisis` вместо Pressure Vector.
- Files: npc_state.py, life_project_resolver.py, break_progress_engine.py, docs/ENTITY_CONTINUITY_CONTRACT.md

---

## DOM-08: OBSERVABILITY & ENFORCEMENT

**L21: Invariant Defense Law** (ADR-INV-DEF, IMMUNE-001)
Двухслойная защита: IPT (до коммита) и InvariantHealthChecker (post-mortem). CDS — пассивный аудитор. Ошибки онтологии (`NaN`, `sum(drives)!=1.0`) убивают тик громко (`OntologyViolationError`). Линтер `ruff check .` обязателен.
- Taboo: ❌ Перехват `SimulationIntegrityError` через `try/except`. ❌ Коммит с нарушением bounds. ❌ Использование `print()` в production (только `logger.debug`).
- Files: backend/tests/IPT.py, diagnostics/invariant_health.py, ruff.toml

## ADR-O-328: Dual Rail Boundary Consistency [ONTO]
> **Статус:** ACTIVE
> **Домен:** DOM-04 (Spatial & Locomotion), DOM-08 (Observability)
> **Сессия:** S148

**Контекст:** 
При `cross_loc_materialize` возникал Causal Drift (Class D), так как `EquivalenceValidator` сравнивал мутированное состояние Legacy (где локация уже обновлена) со снимком Shadow (где локация старая). Это приводило к `True != False` и блокировало ФАЗУ 3.

**Решение:**
1. Вычисление `is_boundary` в `validation.py` основывается на `SceneChange.cause` (`"cross_loc_materialize" in cause`), а не на сравнении мутированного state с snapshot.
2. `EventCompiler` гарантирует `is_boundary=True` для `cross_loc_materialize`.
3. `MovementEngine` не создаёт `SceneChange` с `cross_loc_materialize` без `target_location_id`.
4. `DriftLaboratory` внедряет *Ground Truth Validator* и *Valid Comparisons Tracking* для честной оценки готовности ФАЗЫ 3.

**Taboo:**
- ❌ Вычисление `legacy_is_boundary` на основе `scene_state["npc_positions"][npc_id]["location_id"]` (мутированное состояние).
- ❌ Создание `SceneChange` с `cause="cross_loc_materialize"` без `target_location_id`.
- ❌ Объявление ФАЗЫ 3 готовой при наличии крашнувшихся тиков или < 100k comparisons.


## ADR-O-341: Dual Rail Boundary Consistency [ONTO]
> **Статус:** ACTIVE
> **Домен:** DOM-04 (Spatial & Locomotion), DOM-08 (Observability)
> **Сессия:** S149

**Контекст:** 
При `cross_loc_materialize` возникал Causal Drift (Class D), так как `EquivalenceValidator` сравнивал мутированное состояние Legacy со снимком Shadow.

**Решение:**
1. Вычисление `is_boundary` в `validation.py` основывается на `SceneChange.cause` (`"cross_loc_materialize" in cause`), а не на сравнении мутированного state с snapshot.
2. `DriftLaboratory` внедряет *Ground Truth Validator* и *Valid Comparisons Tracking* для честной оценки готовности ФАЗЫ 3.

**Taboo:**
- ❌ Вычисление `legacy_is_boundary` на основе мутированного `location_id`.
- ❌ Объявление ФАЗЫ 3 готовой при наличии крашнувшихся тиков или < 100k comparisons.

## ADR-O-344: WorldTick Temporal Ownership & Execution Cardinality [ONTO]
**Статус:** Принято
**Домен:** L2 (Runtime Purity), Время, Исполнение
**Табу:** 
- `GameLoop` не имеет права изменять `game_time_seconds` или `tick`.
- `TickOrchestrator.execute` не имеет права вызывать фазы (кроме симуляции конкретной сцены) или продвигать время внутри цикла по сценам.
- Запрет на множественные коммиты в рамках одного `execute()`.

## ADR-O-342: Real-Time Causal Probes & PBT [ONTO]
> **Статус:** ACTIVE
> **Домен:** DOM-01 (Foundation), DOM-08 (Observability)
> **Сессия:** S149

**Контекст:**
Инварианты проверялись только post-mortem (CausalObserver) или вручную (IPT). Баги сериализации и пространства ускользали в production.

**Решение:**
1. **PBT (Подсистема 1):** `hypothesis` генерирует 100+ edge-cases для `NPCState` round-trip (§12.2) при каждом запуске `IPT.py`.
2. **Causal Probes (Подсистема 3):** `ProbeRunner` запускается после Фазы 10 в `TickOrchestrator` в production. `SpatialCoherenceProbe` проверяет SC-1 (запрет `0.0, 0.0`) в реальном времени.

**Taboo:**
- ❌ Запуск `IPT.py` без прохождения `INV-PBT-ROUNDTRIP`.
- ❌ Игнорирование `[PROBE_FAIL]` в production логах.
## ADR-O-345: TickState Mutation Debt (Pure Reducer Violation) [ONTO]
**Статус:** ACCEPTED (DEBT)
**Домен:** L2 (Runtime Purity)
**Сессия:** S178

**Контекст:** INV-TEMPORAL-ISOLATION падает в IPT. Археология показала, что NpcTickPipeline.run() нарушает ADR-TZ09-1 (Pure Reducer), вызывая StateApplicator и MemoryManager, которые мутируют переданный им TickState (в частности, scene_state и ll_npcs_raw).

**Решение:**
1. Долг задокументирован. Симптом (PROBE_FAIL в логах) не крашит симуляцию, но инвариант остаётся красным.
2. Устранение планируется в Sprint S1 (Snapshot / Mutation): полное удаление StateApplicator и MemoryManager из NpcTickPipeline.run(). Все мутации должны возвращаться через TickMutation.

**Taboo:**
- ❌ Добавление новых вызовов StateApplicator или MemoryManager внутри NpcTickPipeline.run().
- ❌ Маскировка PROBE_FAIL через 	ry/except.

## ADR-O-346: Pure Reducer Enforcement & Hash Isolation [ONTO]
**Статус:** ACTIVE
**Домен:** L2 (Runtime Purity), DOM-08 (Observability)
**Сессия:** S179

**Контекст:** INV-TEMPORAL-ISOLATION падал в IPT. Археология выявила две причины:
1. NpcTickPipeline.run() нарушал ADR-TZ09-1, вызывая StateApplicator, который мутировал 
elationship_store и l1_chronicle. Также мутация происходила при load_l2_state_from_runtime_dict(npc) для проверки слуха.
2. TemporalIsolationProbe хэшировал весь TickState, включая сервисные объекты. Их внутренние кэши (LRU) обновлялись при чтении, что ложно меняло хэш.

**Решение:**
1. StateApplicator полностью удалён из NpcTickPipeline.run(). Дельты собираются напрямую из DecisionResult. Все данные для create_memory_event берутся из pre-decision state.
2. Проверка слуха использует copy.deepcopy(dict(npc)) для предотвращения мутации оригинала.
3. Расчёт хэша в 	ick_orchestrator.py теперь применяется только к data-полям (scene_state, ll_npcs_raw, etc.), исключая сервисы.

**Taboo:**
- ❌ Возврат StateApplicator или MemoryManager внутрь NpcTickPipeline.run().
- ❌ Использование оригинальных словарей из state.all_npcs_raw без deepcopy для любых операций, способных мутировать состояние.
- ❌ Хэширование сервисных объектов внутри TickState для инвариантов изоляции.

## ADR-O-347: Entity Cardinality & Scene Isolation [ONTO]
**Статус:** ACTIVE
**Домен:** L2 (Runtime Purity), DOM-04 (Spatial & Locomotion)
**Сессия:** S180

**Контекст:** TickOrchestrator.execute() перебирал все локации, но передавал один и тот же all_npcs_raw (всех NPC) в TickState для каждой локации. NpcTickPipeline.run() обрабатывал их повторно, что нарушало Entity Cardinality и приводило к O(N²) дрейфу.

**Решение:**
1. all_npcs_raw и npc_states фильтруются по location_id ДО сборки TickState. NPC из других локаций полностью исключаются из reasoning pipeline.
2. Внедрён инвариант INV-SCENE-ENTITY-ISOLATION, проверяющий, что npc_positions локации не содержит NPC с чужим location_id.

**Taboo:**
- ❌ Передача полного all_npcs_raw (всех NPC кампании) в TickState без фильтрации по текущей локации.
- ❌ Обработка NPC в NpcTickPipeline.run(), если их location_id не совпадает с scene_state["location_id"].

## ADR-O-348: Causal Ordering & Event Cardinality [ONTO]
**Статус:** ACTIVE
**Домен:** L2 (Runtime Purity), DOM-08 (Observability)
**Сессия:** S181

**Контекст:**
Требовалось гарантировать, что события не дублируются при множественных локациях (Event Cardinality), и что порядок обработки независимых субъектов не влияет на финальное состояние (Causal Order Independence).

**Решение:**
1. Внедрён инвариант `INV-EVENT-CARDINALITY`, проверяющий отсутствие дублирования событий `NPC_MOVED` при тике нескольких локаций.
2. `NpcTickPipeline.run()` является Pure Reducer (ADR-O-346): все данные читаются из иммутабельного `TickState`, результаты собираются в локальные списки. Это структурно гарантирует `INV-CAUSAL-ORDER-INDEPENDENCE`.
3. Порядок применения мутаций детерминирован в Фазе 8 (Combat → Reaction → Social), что исключает влияние порядка NPC на финальный стейт.

**Taboo:**
- ❌ Мутация общего состояния (например, `relationship_store` или `scene_state`) напрямую внутри цикла обработки NPC в `NpcTickPipeline.run()`.
- ❌ Зависимость логики Фазы 8 от порядка элементов в `npc_deltas`.

## ADR-O-349: Semantic Pipeline & Intent-Event Mapping [ONTO]
**Статус:** ACTIVE
**Домен:** DOM-02 (Will, Pressure & Decision), DOM-06 (Social, Memory & Affective)
**Сессия:** S182

**Контекст:**
`IntentEventAdapter` маппил только 4 интента (attack, help, theft, intimidate), остальные падали в дефолтный `npc_spoke`. Это означало потерю семантики для `offer_job`, `request_service` и других действий при публикации в `EventBus`. Также использовались сырые строки вместо `EventType` enum, что приводило к дублированию определений.

**Решение:**
1. `EventType` расширен недостающими социальными и экономическими событиями.
2. В `IntentEventAdapter` внедрён `_INTENT_EVENT_MAP` — словарь, обеспечивающий детерминированный мост между `intent_type` и `EventType`.
3. Внедрён инвариант `INV-INTENT-EVENT-COMPLETENESS`, проверяющий, что каждый коммуникативный интент имеет явный маппинг.

**Taboo:**
- ❌ Использование сырых строк для event_type вместо `EventType` enum.
- ❌ Добавление новых `CommunicationIntent` типов без регистрации в `IntentEventAdapter._INTENT_EVENT_MAP`.
- ❌ Возврат `unknown` или неявного `npc_spoke` для известных коммуникативных интентов.

## ADR-O-350: Dialogue & Travel FSM Terminality [ONTO]
**Статус:** ACTIVE
**Домен:** DOM-04 (Spatial & Locomotion), DOM-09 (Social, Memory & Affective)
**Сессия:** S183

**Контекст:**
Требовалось гарантировать, что перемещения завершаются за конечное число тиков (INV-TRAV-TERMINALITY), и что очередь диалогов не переполняется (INV-DIALOGUE-LIVENESS). Существующие инварианты INV-TRAV-ZOMBIE и INV-DEATH-LOCK покрывали только терминальные статусы и смерть, но не зависание в активных состояниях.

**Решение:**
1. Внедрён инвариант `INV-TRAV-TERMINALITY`, проверяющий, что транзиты не зависают в `PENDING` или `MOVING` дольше `duration_ticks + 2` (grace period).
2. Внедрён инвариант `INV-DIALOGUE-LIVENESS`, проверяющий, что `pending_tasks` не превышает 20 задач (TaskScheduler успевает обрабатывать очередь).

**Taboo:**
- ❌ Создание `TraversalState` с `duration_ticks=0` или без `started_tick`.
- ❌ Блокировка `TaskScheduler` без rate limit, приводящая к переполнению `pending_tasks`.
- ❌ Изменение статуса транзита в обход `transition_traversal()` FSM.

## ADR-O-351: Replay Determinism Infrastructure [ONTO]
**Статус:** ACTIVE
**Домен:** DOM-08 (Observability), DOM-10 (Identity & Ontology)
**Сессия:** S184

**Контекст:**
Требовалось гарантировать, что повторный прогон из записанного состояния даёт тот же результат (INV-REPLAY-DETERMINISM). Полный A/B тест (T0→T3 == Replay(T3)) требует кэширования всех LLM-вызовов и полного восстановления TickState, что выходит за рамки 5-секундного IPT.

**Решение:**
1. Внедрён инвариант `INV-REPLAY-DETERMINISM` (WARNING уровень), проверяющий готовность инфраструктуры: ReplayRecorder подключён, БД доступна, тики записываются.
2. Полный детерминизм верифицируется через `DriftLaboratory` (Спринты S3/S7), который имеет доступ к LLM-кэшу и полному восстановлению состояния.
3. Детерминизм RNG уже гарантирован `INV-KERNEL-RNG` (ADR-O-301).

**Taboo:**
- ❌ Запуск реплея без активации LLM-кэша (`settings.replay_playback = True`).
- ❌ Использование wall-clock времени в симуляции при реплее (нарушает §15).
- ❌ Изменение порядка событий или мутаций между записью и воспроизведением.

## ADR-O-352: Save/Load Integrity [ONTO]
**Статус:** ACTIVE
**Домен:** DOM-01 (Foundation), DOM-08 (Observability)
**Сессия:** S185

**Контекст:**
Требовалось гарантировать, что система может пережить множество тиков, save, load, и продолжить симуляцию без потери данных или рассинхронизации. Цикл Save/Load является критическим для долговременной устойчивости мира.

**Решение:**
1. Внедрён инвариант `INV-SAVE-LOAD-INTEGRITY`, проверяющий, что после нескольких тиков состояние, сохранённое в SQLite (`SqlitePersistenceAdapter.load_scene_at`), совпадает с состоянием в памяти по ключевым полям: `tick`, `game_time_seconds`, `npc_positions` (ID NPC).
2. Тест использует `load_scene_at(campaign_id, location_id)` для корректной загрузки конкретной локации, в отличие от legacy-метода `load_scene()`, который возвращает default-сцену.

**Taboo:**
- ❌ Использование `load_scene()` для загрузки конкретной локации (он возвращает только default).
- ❏ Отсутствие проверки `tick` и `game_time_seconds` после цикла Save/Load.
- ❏ Запись состояния в обход `SceneStateManager.commit()` или `unlock_tick()`.

## ADR-O-356: Sleep as Bodily Coupling Mode (Topological Phase) [ONTO]
> **Статус:** ACTIVE
> **Домен:** DOM-01 (Foundation), DOM-05 (Physiology & Combat), DOM-03 (Perception & Phenomenology)
> **Сессия:** S189

**Контекст:**
Сон реализовывался как скриптовый переключатель (флаг `is_sleeping`). Это не позволяло моделировать эмерджентное пробуждение от стимулов и искажение восприятия во сне.

**Решение:**
1. **Phase B (CouplingResolver):** Внедрён `CouplingProfile` (DTO) и `CouplingResolver` (сервис). Профиль вычисляется каждый тик из `sleep_pressure` и `arousal` (в `body_state`), заменяя хардкод-флаги. Содержит множители: `external_vision_mult`, `external_hearing_mult`, `motor_output_mult`, `memory_activation_mult`, `imagination_mult` и метку `CouplingMode`.
2. **Phase E.0 (Perception Modulation):** В `phases/integration.py` входящие стимулы модулируются множителями связанности. Спящие NPC хуже воспринимают угрозы и аномалии.
3. **Phase D (Sleep Onset):** В `SleepLifecycleService` создан метод `_accumulate_arousal_from_stimuli`, который динамически накапливает `arousal` в `body_state` от стимулов `PerceptualKernel` (даже во сне). Пробуждение опирается на чистый `arousal`.
4. **Phase C (ActiveCommitment):** В `pressure_translator.py` внедрён параметр `has_active_commitment`. Если NPC в активном транзите, проактивные интенты блокируются (feasibility = 0.0).

**Taboo:**
- ❌ Возврат к скриптовым флагам `is_sleeping` в логике сна.
- ❌ Игнорирование `CouplingProfile` при модуляции восприятия в `phases/integration.py`.
- ❌ Использование композитных формул `wake_pressure` вместо чистого `arousal` для проверки пробуждения.
- ❌ Генерация проактивных интентов для NPC в активном транзите.

## ADR-O-353: Sleep Lifecycle Extraction & TimeSkip Events [ONTO]
**Статус:** ACTIVE
**Домен:** DOM-01 (Foundation), DOM-05 (Physiology & Combat)
**Сессия:** S187

**Контекст:**
Логика сна (пробуждение от стимулов, восстановление стресса/усталости) была захардкожена внутри `LifeEngine` (`_arousal_gate`, `recover_stress_tick`). Это нарушало Separation of Concerns и делало невозможным расширение сна (кошмары, сны) без засорения `LifeEngine`. Кроме того, `TimeSkipExecutor` игнорировал события сна, что приводило к потере нарратива (кошмары, пророчества) при ускорении времени (BUG-SLEEP-007, BUG-SLEEP-012).

**Решение:**
1. Создан `SleepLifecycleService` (`backend/app/services/npc/sleep_lifecycle_service.py`), отвечающий за проверку пробуждения (Arousal Gate), применение восстановления во сне и публикацию событий сна (`sleep_end`, `dream`, и т.д.).
2. Внедрена явная Фаза 0.6 (`_phase_0_6_sleep_lifecycle`) в `TickOrchestrator`, вызываемая между Фазой 0 (Simulation) и Фазой 0.5 (Idle Services).
3. `LifeEngine` больше не содержит методов `_arousal_gate` и `recover_stress_tick` — они перенесены в `SleepLifecycleService`.
4. `TimeSkipExecutor.SIGNIFICANT_EVENT_TYPES` расширен событиями: `sleep_start`, `sleep_end`, `dream`, `nightmare`, `sleepwalk`, `prophecy_vision`.

**Taboo:**
- ❌ Возврат логики проверки пробуждения (`_arousal_gate`) или восстановления сна в `LifeEngine`.
- ❌ Прямая мутация `_sleep_start_tick` или `routine["current"]` в обход `SleepLifecycleService`.
- ❌ Игнорирование событий сна в `TimeSkipExecutor` при пропуске времени (Policy B).

`ADR-O-354` [ONTO] **Epistemic Core Foundation** — Proposition Layer: Claim ≠ Truth, Belief ≠ Truth, Communication → ClaimEvent → Proposition → BeliefRevisionEngine → EpistemicStore → EpistemicContextResolver → EpistemicContext → epistemic_modifiers → DecisionHub
  Taboo: ❌ ClaimEvent напрямую мутирует RelationshipStore; ❌ DecisionHub импортирует EpistemicStore; ❌ L1 Chronicle хранит субъективные убеждения; ❌ confidence интерпретируется как truth probability
  Status: VERIFIED (SUPERBOX-002 — SUPERBOX-013)
  Files: backend/app/domain/epistemology.py, backend/app/services/npc/epistemic_store.py, backend/app/services/npc/belief_revision_engine.py, backend/app/services/npc/epistemic_context_resolver.py, backend/app/services/events/claim_event_subscriber.py

`ADR-O-355` [ONTO] **Modifier Contract v1** — DecisionHub принимает независимые числовые деформации (Dict[str, float]). Модификаторы аддитивны, детерминированы, коммутативны и не мутируют исходный score-space. apply_modifiers — pure function.
  Taboo: ❌ Модификаторы с побочными эффектами; ❌ Мутация входного scores; ❌ Некоммутативные операции (multiplier, cap, override) без нового контракта v2
  Status: VERIFIED (SUPERBOX-011, S012, S013)
  Files: backend/app/services/npc/decision_hub.py

### ADR-O-357: Trust-Anchored Belief Revision & Social Semantics Law
**Статус:** PROPOSED
**Домен:** epistemic, social, fate, ui
**Files:** backend/app/services/npc/trust_based_reliability_provider.py, backend/app/services/npc/belief_revision_engine.py, backend/app/services/events/social_subscriber.py, backend/app/services/social/fate_tracker.py, backend/app/services/social/mvp_tavern_controller.py, backend/app/services/integration/world_snapshot_builder.py, backend/app/domain/snapshot.py, frontend/analysis_renderer.py, frontend/game_screen.py, backend/app/models/pipeline_context.py, backend/app/services/state/context_builder.py, backend/app/services/game_loop/__init__.py, backend/tests/IPT.py
**Суть:** Надёжность источника убеждений зависит от доверия (trust). Введены детерминированные fallback'и для социальных интентов. NPC могут сойти с ума (BROKEN) после 5 тиков в CRITICAL. Добавлена вкладка "Мои убеждения" в UI.


## ADR-O-358: Epistemic Player Integration (Фаза 8.3)

**Статус:** Принято  
**Домен:** Epistemology, Social  
**Связанные ADR:** ADR-O-354 (Epistemic Core), ADR-O-306 (Epistemic Heterogeneity)  

### Контекст
EpistemicStore для игрока оставался пустым в рантайме с LLM. Игрок слышал реплики, но они не превращались в его убеждения. TrustBasedReliabilityProvider не мог вызвать падение confidence, так как reliability была ограничена `max(0.0, ...)`.

### Решение
1. `ClaimEventSubscriber` подписан на `NPC_SPOKE` для детерминированного fallback: `intent_type` маппится на `Proposition` (accuse → STOLE, praise → HELPED, intimidate/attack → ATTACKED).
2. Игрок больше не исключается из списка слушателей `COMMUNICATION_CLAIM`.
3. `RelationshipReliabilityProvider` возвращает `-0.5` при `trust < -30`, что заставляет `confidence` убывать.
4. `BeliefRevisionEngine` защищён `max(0.0, ...)` от ухода в отрицательные значения.

### Табу
- Запрещено исключать игрока из перцептивной мембраны (он полноправный наблюдатель).
- Запрет `max(0.0, min(1.0, ...))` в `get_reliability` — отрицательные значения нужны для моделирования недоверия врагам.

### Files
- `backend/app/services/events/claim_event_subscriber.py`
- `backend/app/services/npc/belief_revision_engine.py`
- `backend/app/services/game_loop/__init__.py