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