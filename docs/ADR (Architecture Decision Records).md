# ENIGMA ADR MASTER INDEX (Canonical Laws)

> **Статус:** ACTIVE | **Сессия:** S201 | **Инвариантов:** 39 (IPT 39/39)
> **Формат:** `L{N}: {Name}` = Immutable Law. Нарушение = архитектурный баг.
> **Детальные импакт-аудиты:** `docs/audits/ADR-*_IMPACT.md`
> **Path Alias Map:** `svc/`=backend/app/services/ | `dom/`=backend/app/domain/ | `mod/`=backend/app/models/

---

## 📌 ENIGMA ONTOLOGY (Context Anchor)
*   **Psyche Layers:** `L0`=Physics/Body, `L1`=Chronicle (append-only SQLite facts), `L2`=Identity/Beliefs (crystalized), `L3`=Drives (ephemeral, per-tick).
*   **Epistemic Boundary:** NPCs know ONLY what they physically perceive (radius/LOS). No telepathy.
*   **Triple Membrane:** Filters L1 facts into L2 beliefs (Physics, Personality, Social).
*   **Pure Reducer:** Tick pipeline MUST NOT mutate global state; it yields `TickMutation` (deltas).
*   **Projection Engine:** `apply_changes` = pure projection (zero computation). All physics computed by `EventCompiler`.

---

## DOM-01: FOUNDATION (Core Pipeline, Time, State)

**L1: State Mutation Law** (ADR-001, 013, 117)
Единственный путь мутации: `Phase8Result → delta_buffer → StateApplicator.apply_batch()`. Сериализация Round-Trip (`from_legacy ↔ write_to_legacy`).
- ❌ **Taboo:** Прямая мутация `all_npcs_raw`; Конструктор `NPCState(...)` в тестах.
     Runtime-мутация аватара игрока — только `AvatarStateApplicator` (whitelist: body_state/stress/emotion, S208); GameLoop — оркестратор, не писатель.
- 📁 `svc/state/delta_buffer.py`, `svc/state/state_applicator.py`, `mod/npc_state.py`

**L2: Runtime Purity Law** (ADR-O-302, TZ09-1, S83.1)
Тик — чистая функция (`TickState → TickMutation`). Ядро не знает 'player'/'dm_ctx'. Время (`game_time_seconds`) — единственный авторитет. `random.*` запрещён → `KernelRNG(tick, npc_id, salt)`.
- ❌ **Taboo:** `if dm_ctx` в ядре; `time.time()` в симуляции; `svc: Any` в `NpcTickPipeline`.
- 📁 `svc/tick_orchestrator.py`, `svc/npc/npc_tick_pipeline.py`, `svc/kernel_rng.py`

**L2.1: Causal Kernel & Projection Engine Law** (ADR-O-201, S80-S85)
`apply_changes` — чистая проекция (zero computation). Вся физика (pathfinding, RNG, geometry, traversal creation) вычисляется ЗАРАНЕЕ в `EventCompiler` и упаковывается в `ThickSceneChange`. `WorldSnapshot` immutable.
- ❌ **Taboo:** SpatialService query / RNG / Pathfinding / Traversal creation / Geometry compute внутри `apply_changes`.
- 📁 `svc/event_compiler.py`, `mod/thick_scene_change.py`, `svc/scene_state_manager.py`

**L2.2: Entity Birth Contract** (ADR-O-201, S85)
NPC ВСЕГДА рождается с `body_state` и `npc_id`. Все точки входа (`load_npcs_merged` × 3) нормализуют dict.
- ❌ **Taboo:** NPC dict без `body_state`/`npc_id`; Чтение JSON минуя нормализацию.
- 📁 `svc/npc/npc_loader.py`, `svc/npc/life_engine.py`

**L3: No Retro-Simulation Law** (ADR-047, 311)
Пропущенное время вычисляется через `reconcile_state()`. Ядро возвращает `final_scene_state` для коммита.
- ❌ **Taboo:** Циклы `tick()` для нагона времени; Коммит устаревшего `scene_state`.
- 📁 `svc/npc/life_engine.py`, `svc/tick_orchestrator.py`

**L4: Silent Failure Prohibition** (ADR-O-308)
Скрытые баги (`except Exception: pass`) — нарушение контракта. Падение симуляции = `SimulationIntegrityError`.
- ❌ **Taboo:** Пустые `except`; Тихий `None` на границе API; `# noqa` без причины.
- 📁 `svc/llm/dm_router.py`, `svc/errors.py`, `scripts/lint_enigma_ast.py`

**L4.1: Async Intent Compression Law** (ADR-159, S118)
`IntentCompressor` (async) вызывает LLM ДО ядра. Возвращает `IntentSemanticField`. Ядро не парсит текст.
- ❌ **Taboo:** Синхронный LLM в `phase_1_input.py`; `IntentCompressor(llm_client=None)` в prod.
- 📁 `svc/game_loop/input/intent_compressor.py`

---

## DOM-02: WILL, PRESSURE & DECISION

**L5: Will & Pressure Law** (ADR-031, O-146, 149)
Воля — инерция. `WillpowerGate` вызывается 1 раз за цикл. Решения = Utility Deformation. Needs (0.8) перезаписывают Schedule (0.6).
- ❌ **Taboo:** `WillpowerGate` >1 раза; RPG-матрицы `action × temperament`.
- 📁 `svc/will.py`, `svc/npc/decision_hub.py`

**L5.1: Drive Resolution Pipeline (DRP)** (ADR-O-208)
`EffectiveDrives = Projection(L0_Archetype, L1_Scars, Context)`. L3 эфемерны (живут 1 тик). `npc_raw["drives"]` уничтожен как SSOT.
- ❌ **Taboo:** Персистенция L3; Фоллбэк на L0 (`drives_base`) в `InterpretationEngine`.
- 📁 `svc/npc/drive_resolver.py`, `svc/npc/decision_hub.py`

**L5.2: Temporal Identity Formation (TIFL)** (ADR-TIFL-001)
Непрерывный дрейф `drives_base` на основе `prediction_error`. Мир постоянно неожидан → драйв растёт. Успех → привыкание.
- ❌ **Taboo:** Скалярная мутация личности; Игнорирование `prediction_error`.
- 📁 `svc/npc/break_progress_engine.py`, `svc/tick_orchestrator.py`

**L6: Cognitive Contour Law (PE Active Inference)** (ADR-S93.2, TZ08-3)
Ожидания (T-1) → `drive_modifiers` (T0) через `tanh` + `Clamp(0.25)`. PE не доминирует над DRF.
- ❌ **Taboo:** EMA вне `StateApplicator`; Асинхронный LLM до применения состояния.
- 📁 `svc/memory/expectation_store.py`, `svc/npc/pe_modifier_resolver.py`

**L7: LLM & Narrative Exile Law** (ADR-TZ05-1, O-313)
Тяжёлые I/O в `TaskScheduler`. Ядро не формирует промпты. DM читает `observed_state`, не сырые поля (`stress`, `fear`).
- ❌ **Taboo:** LLM внутри `TickOrchestrator`; Чтение `psyche` в вербализации.
- 📁 `svc/game_loop/task_scheduler.py`, `agents/dm_agent.py`

**L7.1: Proactive Intent & Aggression Triggers** (ADR-163, 165)
NPC инициируют `TALK` в idle_tick. `threat_gradient > 0.5` → превентивный `ATTACK`.
- ❌ **Taboo:** Хардкод запрета на ATTACK в idle; Игнорирование `threat_gradient`.
- 📁 `svc/npc/decision_hub.py`, `svc/npc/life_engine.py`

---

## DOM-03: PERCEPTION & PHENOMENOLOGY (CFRM)

**L8: CFRM & Somatic Gate Law** (ADR-025, O-139, O-147)
Объективных фактов нет — есть `FieldDisturbance`. Тело = фильтр. Боль/шок через `PerceptualKernel.somatic_urgency` ДО семантики. Эмоции → только `ManifestationDTO.tags`.
- ❌ **Taboo:** `EventDTO` в `EventBuffer`; Инъекция `pain` в psyche; Скрытые эмоции в UI.
- 📁 `svc/perception/local_causal_solver.py`, `svc/perception/perceptual_kernel.py`

**L8.1: Emotional Residue Isolation** (ADR-O-206)
`EmotionTag` убит как причина. Память/вес = `surprise_delta` (`abs(affective_load - prev)`). Скорость забывания = каузальная глубина.
- ❌ **Taboo:** `EmotionTag` в `ImportanceEngine` или `MemoryManager`; Влияние тега на `decay_rate`.
- 📁 `svc/memory/importance_engine.py`, `svc/memory/memory_manager.py`

---

## DOM-04: SPATIAL & LOCOMOTION

**L9: Spatial SSOT & Factory Law** (ADR-008, O-314)
`SpatialFactory.build_for_campaign()` — единственный сборщик. Чтение позиций через `SpatialQueryService`. `player_spatial` мёртв → `npc_positions["player"]`.
- ❌ **Taboo:** Прямая сборка `SpatialService`; Чтение `player_distances` из `scene_state`.
- 📁 `svc/spatial/spatial_factory.py`, `svc/spatial/spatial_query_service.py`

**L9.1: EventDTO Default Radius Sentinel** (ADR-148)
Дефолтный `radius=999.0` в `EventDTO.create` пробивает слуховые мембраны (`_can_hear`). Замена на `PERCEPTION_RADIUS["major"]` только при runtime-баге.
- ❌ **Taboo:** Слепое использование `radius=999.0` для аудио-событий.
- 📁 `dom/events.py`, `svc/npc/perception_filter.py`

**L10: Traversal FSM Law** (ADR-TRAV-FSM, 130.1)
`SceneStateManager` — единственный владелец lifecycle. Движение = результат решения. Фронтенд рендерит `velocity` или `active_traversals`.
- ❌ **Taboo:** Перезапись `status="MOVING"`; Создание `TraversalState` при `traversal_complete`.
- 📁 `svc/scene_state_manager.py`, `svc/spatial/movement_engine.py`

**L11: Spatial Agency Law** (ADR-O-330)
NPC формирует `SpatialTargetIntent`. `SpatialTargetResolver` разрешает в `NAV_NODE` или `LOCAL_POSITION`. Decision Layer НЕ генерирует `target_node_id`.
- ❌ **Taboo:** `spatial_service.resolve_node()` из `LifeEngine`; Передача координат в `SpatialTargetIntent`.
- 📁 `dom/spatial_target.py`, `svc/spatial/spatial_target_resolver.py`

**L11.1: Hybrid Geometry & Stigmergy Law** (ADR-S90.1, O-324)
Микро = `DriveVector` (ETKE-IK), макро = `MovementIntent`. `DynamicAffordanceField` хранит деформации. Маршрутизация валидирует сегменты.
- ❌ **Taboo:** `MovementIntent` для микро; Очистка стигмергии при смене локации.
- 📁 `svc/spatial/motion_pipeline.py`, `svc/spatial/world_topology_provider.py`

---

## DOM-05: PHYSIOLOGY & COMBAT

**L12: Physiology & Death Lock Law** (ADR-015, 127, HP-UNIFICATION)
`body_state["current_hp"]` — SSOT. Смерть = `evaluate_vital_state()`. Мёртвые (`life_status="DEAD"`) исключаются до Фазы 1. Боевые кубики через `KernelRNG`.
- ❌ **Taboo:** Запись в `state.hp`; `hp <= 0` как смерть; Decay для мёртвых; `random.*` в `combat_math`.
- 📁 `dom/vital_state.py`, `svc/combat/impact_engine.py`

**L12.1: Vital State Axes & Injury Bridge** (ADR-123)
Три независимые оси: `LifeStatus` (ALIVE/DEAD), `is_conscious()`, `is_capable()`. `InjuryProcessor` = физика раны (зона, тип, глубина), не строковые теги.
- ❌ **Taboo:** Смешивание осей в enum; `shock_impulse >= 0.95` как смерть; `"dead"` в `body_state["statuses"]`; Строковые флаги в `InjuryProcessor`.
- 📁 `dom/vital_state.py`, `svc/combat/injury_processor.py`

**L12.2: D&D 5e Combat Math Law** (ADR-164, S118)
`ImpactEngine._resolve_contact` → `attack_roll` из `combat_math.py`. Hit/Miss/Crit → `ContactLevel`. `KernelRNG` изолирован.
- ❌ **Taboo:** Вычисление попадания в `impact_engine.py`; Legacy-формулы урона.
- 📁 `svc/combat/impact_engine.py`, `svc/combat/combat_math.py`

---

## DOM-06 & 09: SOCIAL, MEMORY & AFFECTIVE

**L13: Relationship SSOT & Affective Hysteresis** (ADR-121, O-206)
`RelationshipStore` (0-100) — SSOT. Аффективная нагрузка = интеграл с гистерезисом. `integrate_affective_pressure` — Single Writer.
- ❌ **Taboo:** `relationship_cache` в `NPCState`; Утечка в `affective_load`.
- 📁 `svc/social/relationship_store.py`, `svc/affective/affective_integrator.py`

**L13.1: Causal Field Layer (CFL) Law** (ADR-O-209, O-210, S118)
Социальная физика = **поле**, не граф. NPC излучает `CausalEmissionPacket` → CFL Spatial Grid (суперпозиция + Cap) → `S_env` в точке. `Trait = Metric Commit` (неизменный сдвиг базиса).
- ❌ **Taboo:** Прямая интерференция метрик агентов; CFL как персистентное состояние; Чтение L1 другого агента.
- 📁 `svc/social/causal_field_layer.py`, `dom/causal_state_vector.py`

**L14: Epistemic Memory Law** (ADR-S86.7, O-325)
Память не генерирует идентичность без каузального входа. Труба NPC фильтруется через `perception_filter` (запрет телепатии).
- ❌ **Taboo:** L2.5 кристаллизация в idle без `phase_2_events`; Запись не-услышанных реплик.
- 📁 `svc/memory/memory_manager.py`, `svc/npc/perception_filter.py`

**L14.1: Epistemic Core Law (Proposition Layer)** (ADR-O-354, O-355, S188)
`Proposition` (STOLE, HELPED) → `ClaimEvent` → `EpistemicRecord` в `EpistemicStore`. `DecisionHub` изолирован от Store (принимает `Dict[str, float]` модификаторов). Modifier Contract: аддитивность, изоляция, коммутативность.
- ❌ **Taboo:** `DecisionHub` читает `EpistemicStore`; Убеждение без `source_id`; Прямая мутация `confidence`.
- 📁 `dom/epistemology.py`, `svc/npc/epistemic_store.py`, `svc/npc/belief_revision_engine.py`

**L14.2: Trust-Based Reliability Law** (ADR-O-357, S199)
Надёжность убеждений зависит от `trust` (из `RelationshipStore`). `trust < -30` → обратный эффект (confidence падает). Слова врага не убеждают.
- ❌ **Taboo:** Фиксированная reliability; Игнорирование отрицательного trust.
- 📁 `svc/npc/trust_based_reliability_provider.py` (единственная реализация; инлайн в подписчике удалён, S205)

**L14.3: Player Epistemic Closure Law** (ADR-O-358, S200-S201)
Игрок — полноправный наблюдатель в `EpistemicStore`. `ClaimEventSubscriber` подписан на `NPC_SPOKE`. Детерминированный fallback: `intent_type` → `Proposition`.
- ❌ **Taboo:** `if _nid == "player": continue` в подписчике; Отрицательный `confidence` (защита `max(0.0)`).
- 📁 `svc/events/claim_event_subscriber.py`, `svc/npc/belief_revision_engine.py`

**L14.4: Source-Weighted Reliability & Observation Channel** (ADR-O-360, S207)
Убеждения поступают по двум каналам: `testimony` (trust-функция ADR-O-357) и `direct_observation` (`DIRECT_OBSERVATION_RELIABILITY`, калибруемый параметр < 1.0). `ObservationSubscriber` слушает мировые события (THEFT), фильтрует свидетелей мембраной LOS+дистанция через `SpatialQueryService`. Наблюдение = `ClaimEvent(witness→witness)` — движок ревизии един для обоих каналов.
- ❌ **Taboo:** `event.radius` как контракт наблюдения (DEBT-R1); наблюдение без LOS/дистанции; `DIRECT_OBSERVATION_RELIABILITY >= 1.0`; расширение `_OBSERVABLE_EVENT_PREDICATES` без детерминированного маппинга на Predicate.
- 📁 `svc/events/observation_subscriber.py`, `svc/npc/trust_based_reliability_provider.py`

**L19.1: NPC Action Materialization: Steal** (ADR-O-362, S209)Первое эмерджентное действие NPC: Intent.STEAL — windowed (2 тика), unlockable (OpportunityEngine R6.3: score ≥ порога), archetype-weighted (_steal_affinity: thief→0.8, прочие→0.08 × desire; ЗАПРЕЩЁН npc_id-хардкод). Материализация: _INTENT_EVENT_MAP["steal"] → EventType.THEFT (source=вор, radius из ExposureLevel.from_semantic("whisper") — честная мембрана). Windup-релиз: объектная цель (_gate_type_is_object_action) минует сущностную валидацию. Эпистемика — только через ObservationSubscriber (produces_claim=False).

❌ Taboo: npc_id-хардкоды affinity; steal в диалоговом слое (TaskScheduler); THEFT-payload без target_id; расширение object-action списка без mini-ADR.
📁 svc/npc/decision_hub (_steal_affinity, unlock-ветка), svc/phases/post_decision (маршрутизатор, gate, Фаза 7), svc/events/intent_event_adapter, models/npc_state (Intent.STEAL), `dom/intent_profiles

---

## DOM-07: FRONTEND, PRESENTATION & INPUT

**L15: Frontend Authority Law** (ADR-TZ03-1, 156)
Backend — SSOT. Фронтенд = pure renderer. DTO канонизированы.
- ❌ **Taboo:** `game_time_seconds +=` в FE; Восстановление `player_spatial`; Вычисление manifestations в FE.
- 📁 `fe/api_client.py`, `fe/game_screen.py`

**L16: Epistemic Boundary Law** (ADR-TZ08-4, 093)
DM — локальный наблюдатель. Читает `observed_state` и `embodied_traces`. Нарратив из наблюдаемых действий. `WorldProjectionBuffer` = pure function.
- ❌ **Taboo:** Чтение `stress_delta`, `real_state` в DM; Возврат `dm_frame` из ядра.
- 📁 `agents/dm_agent.py`, `svc/scene/r3_direct_builder.py`

**L16.1: Three-Channel Presentation & Body Topology** (ADR-O-331, S147)
`WorldSnapshotDTO` → независимые `VisualDTO`, `AudibleDTO`, `NarrativeDTO` из `PerceivedSignals`. Запрет `Visual First`. Инвентарь = `BodyTopology` (D&D 5e Encumbrance).
- ❌ **Taboo:** Чтение `player_inventory_snapshot`; Генерация `VisualDTO` из `NarrativeDTO`.
- 📁 `dom/body.py`, `dom/presentation.py`, `svc/perception/presentation_assembler.py`

**L16.2: Projection Layer System** (ADR-O-205)
`EmotionTag` убит как универсальное состояние. Заменён на 3 несовместимые проекции:
1.  **Motor:** `rigidity` от `threat_gradient` (тело не знает о разуме).
2.  **Narrative:** текст от `redirect` (разум рационализирует победу драйва).
3.  **Memory:** важность от `error_vector` (Surprise).
- ❌ **Taboo:** Cross-projection leakage (Motor читает `redirect`); Свитчи `if emotion == "fearful"`.
- 📁 `svc/perception/behavior_manifestation_service.py`, `svc/verbalization/verbal_stance.py`

---

## DOM-10: IDENTITY & ONTOLOGY

**L17: Identity Pipeline Law** (ADR-O-208, 211, TIFL-001)
L1Chronicle — append-only. L3 эфемерны. `CalibrationEngine` не мутирует L0. Убеждения = линзы (модификаторы), не гены.
- ❌ **Taboo:** Удаление из `L1Chronicle`; Кэширование L3; Мутация `drives_runtime` минуя Belief Layer.
- 📁 `svc/npc/l1_chronicle.py`, `svc/npc/drive_resolver.py`

**L17.1: Identity Stability Kernel (ISK)** (ADR-O-211)
Фазовая устойчивость личности: `CRYSTAL` (устойчив), `PLASTIC` (адаптивен), `BRITTLE` (хрупок), `CHAOTIC`. Измеряется через `run_perturbation_test` (микро-шум → `delta_g_norm`).
- ❌ **Taboo:** Мгновенная смена метрик; Игнорирование `identity_rigidity`.
- 📁 `svc/npc/calibration_engine.py`, `tests/sandbox/calibration/isk.py`

**L18: Belief Crystallization Law (L2.5)** (ADR-O-305, 306, 307)
L1 (Факты) → L1.5 (PatternDetector) → L2.5 (Belief Engine). Асимметричная травма (x6 для опровержений). Тройная Мембрана фильтрует L1.
- ❌ **Taboo:** `trait`/`emotion` в PatternDetector; Скалярный страх; Чтение L1 из Belief Engine.
- 📁 `svc/npc/pattern_detector.py`, `svc/npc/belief_crystallization_engine.py`

**L19: Channel Topology & Task Layer** (ADR-O-312, 313)
Классификация по физике: Field (EMA), Reservoir, Structural, Cognitive. Тяжёлые процессы: `Need → Intent → Task → Materializer → Event`.
- ❌ **Taboo:** Прямой вызов материализации из `TickOrchestrator`; Блокирующее I/O в ядре.
- 📁 `svc/homeostasis/homeostasis_projector.py`, `svc/game_loop/task_scheduler.py`

**L20: LifeProject & Agency Model** (ADR-O-315, 320)
L0 (`CoreOrientation`) неизменен. L2.7 (`life_project`) — FSM, управляемый Identity Pressure Vector. Anti-Script Constraint.
- ❌ **Taboo:** Мгновенная смена `life_project`; Бусты в `LOST`/`SEARCHING`; Скалярный `identity_crisis`.
- 📁 `mod/npc_state.py`, `svc/npc/life_project_resolver.py`

---

## DOM-08: OBSERVABILITY & ENFORCEMENT

**L21: Invariant Defense Law** (ADR-INV-DEF, IMMUNE-001)
Двухслойная защита: IPT (pre-commit) + InvariantHealthChecker (post-mortem). Ошибки онтологии (`NaN`, `sum(drives)!=1.0`) → `OntologyViolationError`. `ruff check .` обязателен.
- ❌ **Taboo:** Перехват `SimulationIntegrityError`; Коммит с нарушением bounds; `print()` в prod.
- 📁 `tests/IPT.py`, `diagnostics/invariant_health.py`

**L21.1: Real-Time Causal Probes & PBT** (ADR-O-342, S149)
**PBT:** `hypothesis` генерирует edge-cases для `NPCState` round-trip. **Probes:** `ProbeRunner` после Фазы 10. `SpatialCoherenceProbe` (SC-1: запрет `0.0, 0.0`).
- ❌ **Taboo:** Запуск `IPT.py` без `INV-PBT-ROUNDTRIP`; Игнорирование `[PROBE_FAIL]` в prod.
- 📁 `tests/pbt/`, `svc/probes/probe_runner.py`

**L21.2: Sleep Lifecycle Routing** (ADR-O-353, S189)
Логика физиологического восстановления (стресс, усталость, Arousal Gate) вынесена из `LifeEngine` в `SleepLifecycleService` (Фаза 0.6). `TimeSkipExecutor` прерывается событиями сна.
- ❌ **Taboo:** Логика пробуждения в `LifeEngine`; Игнорирование `sleep_end` в `TimeSkipExecutor`.
- 📁 `svc/npc/sleep_lifecycle_service.py`, `svc/game_loop/time_skip_executor.py`

---

## 📜 STANDALONE ADR (Specific Architectural Decisions)

### ADR-O-328/341: Dual Rail Boundary Consistency [ONTO]
**Статус:** ACTIVE | **Сессия:** S148/S149
**Суть:** При `cross_loc_materialize` вычисление `is_boundary` основывается на `SceneChange.cause`, а не на мутированном `location_id`. `EventCompiler` гарантирует `is_boundary=True`. `MovementEngine` не создаёт `SceneChange` без `target_location_id`.
- ❌ **Taboo:** `legacy_is_boundary` из мутированного state; `cross_loc_materialize` без `target_location_id`.

### ADR-O-344: WorldTick Temporal Ownership [ONTO]
**Статус:** ACTIVE | **Сессия:** S176
**Суть:** `TickOrchestrator` — единственный владелец `game_time_seconds` и `tick`. `GameLoop.idle_tick` вызывает `execute()` ровно 1 раз. Запрет множественных коммитов в `execute()`.
- ❌ **Taboo:** `GameLoop` меняет время; `TickOrchestrator` продвигает время в цикле по сценам.

### ADR-O-345: TickState Mutation Debt [DEBT]
**Статус:** ACCEPTED (DEBT) | **Сессия:** S178
**Суть:** `NpcTickPipeline.run()` нарушал ADR-TZ09-1, вызывая `StateApplicator`, который мутировал `TickState`. Устранено в S179 (ADR-O-346).

### ADR-O-346: Pure Reducer Enforcement & Hash Isolation [ONTO]
**Статус:** ACTIVE | **Сессия:** S179
**Суть:** `StateApplicator` удалён из `NpcTickPipeline.run()`. Дельты из `DecisionResult`. Хэш `TickState` изолирован от сервисных объектов (кэши LRU). Проверка слуха через `copy.deepcopy`.
- ❌ **Taboo:** Возврат `StateApplicator` в Pipeline; Хэширование сервисов; Мутация оригинальных dict.

### ADR-O-347: Entity Cardinality & Scene Isolation [ONTO]
**Статус:** ACTIVE | **Сессия:** S180
**Суть:** `all_npcs_raw` фильтруется по `location_id` ДО сборки `TickState`. NPC из других локаций исключаются. Устранён O(N²) дрейф.
- ❌ **Taboo:** Передача полного `all_npcs_raw` без фильтрации; Обработка NPC с чужим `location_id`.

### ADR-O-348: Causal Ordering & Event Cardinality [ONTO]
**Статус:** ACTIVE | **Сессия:** S181
**Суть:** `INV-EVENT-CARDINALITY` (нет дублирования `NPC_MOVED`). `NpcTickPipeline` = Pure Reducer (структурная независимость от порядка NPC). Порядок мутаций детерминирован в Фазе 8.
- ❌ **Taboo:** Мутация общего состояния в цикле NPC; Зависимость Фазы 8 от порядка `npc_deltas`.

### ADR-O-349: Semantic Pipeline & Intent-Event Mapping [ONTO]
**Статус:** ACTIVE | **Сессия:** S182
**Суть:** `EventType` расширен (OFFER_JOB, TRADE). `IntentEventAdapter._INTENT_EVENT_MAP` = детерминированный мост. `INV-INTENT-EVENT-COMPLETENESS`.
- ❌ **Taboo:** Сырые строки для `event_type`; Новые `CommunicationIntent` без маппинга; `unknown`/`npc_spoke` fallback.

### ADR-O-350: Dialogue & Travel FSM Terminality [ONTO]
**Статус:** ACTIVE | **Сессия:** S183
**Суть:** `INV-TRAV-TERMINALITY` (транзиты не виснут > `duration_ticks + 2`). `INV-DIALOGUE-LIVENESS` (`pending_tasks` ≤ 20).
- ❌ **Taboo:** `TraversalState` с `duration_ticks=0`; Блокировка `TaskScheduler` без rate limit.

### ADR-O-351: Replay Determinism Infrastructure [ONTO]
**Статус:** ACTIVE | **Сессия:** S184
**Суть:** `INV-REPLAY-DETERMINISM` (WARNING). `ReplayRecorder` подключён. Полный A/B тест через `DriftLaboratory` (LLM-кэш). `INV-KERNEL-RNG` гарантирует детерминизм RNG.
- ❌ **Taboo:** Реплей без LLM-кэша; Wall-clock время в симуляции.

### ADR-O-352: Save/Load Integrity [ONTO]
**Статус:** ACTIVE | **Сессия:** S185
**Суть:** `INV-SAVE-LOAD-INTEGRITY`. `SqlitePersistenceAdapter.load_scene_at` (не legacy `load_scene()`). Проверка `tick`, `game_time_seconds`, `npc_positions`.
- ❌ **Taboo:** `load_scene()` для конкретной локации; Запись мимо `SceneStateManager.commit()`.

### ADR-O-356: Sleep as Bodily Coupling Mode [ONTO]
**Статус:** ACTIVE | **Сессия:** S189
**Суть:** Сон = эмерджентное свойство телесной архитектуры. `CouplingResolver` (множители `external_vision_mult`, `motor_output_mult`). `Sleep Onset` (arousal от стимулов). `DreamSignal` → `DreamResidue` (affective_load).
- ❌ **Taboo:** Скриптовые флаги `is_sleeping`; Игнорирование стимулов во сне.

`ADR-O-359` [ONTO] **LLM Few-Shot Intent Grounding** — Для стабилизации `qwen_7b` в задаче извлечения `social_intent` запрещено использовать хардкод keyword-matching.
  Taboo: ❌ Хардкод `if action == FLIRT: social_intent = FLIRT`; Keyword hell в `intent_compressor.py`.
  Status: ACTIVE
  Files: `backend/app/services/input/llm_compressor_client.py`, `backend/app/services/player_cognition/legacy_bridge.py`, `backend/tests/sandbox/SUPERBOX/scenarios/semantic_torture_test.py

### ADR-O-361: Calibration Laboratory Boundary [ONTO]
**Статус:** ACTIVE | **Сессия:** S213
**Суть:** Лаборатория калибровки психики — надстройка над ядром на двух границах. (1) overlay_constants() — identity-патч ссылок на константы (app.core.constants + все from-import биндинги загруженных модулей; decision_hub.py:27-43 биндит имена напрямую — патч только модуля констант = тихая ложь эксперимента). Verify на входе и выходе, полный откат, запрет вложенности. (2) ObservabilityTap — единственный пассивный наблюдатель (sync-подписчик EventBus + post-commit диффы сторов); отказ наблюдателя не роняет тик. Per-NPC параметры — НЕ константы: npc_overrides материализуются патчем NPC JSON во временной копии кампании. Вмешательства — только InterventionEvent → TickOrchestrator.execute (ADR-TZ08-1). LLM исключён из прогонов (MockProvider, environment != production). Метрическое время — детерминированная проекция тиков (tick / ticks_per_real_minute); wall-clock — только метаданные (§15.2). Параллельные эксперименты — только изоляция процессами. Зоны: MANNEQUIN / CHAOS / ENIGMA / WARNING / BROKEN (NaN|инварианты → BROKEN). Калибруемый параметр эпистемики ADR-O-360 (DIRECT_OBSERVATION_RELIABILITY < 1.0) регистрируется в схеме пресетов с его taboo.
❌ Taboo: overlay без verify; вложенные overlay; параллельные overlay в одном процессе; фейковая реализация [PLAN]-параметров; I/O или проброс исключений из Tap в каузальный поток; мутация NPCState/констант в обход границ лаборатории; wall-clock/global random в симуляционном контуре runner'а; silent except в путях патча (урок S207 / DEBT-R5).
📁 backend/app/services/calibration/config_overlay.py, backend/app/services/calibration/__init__.py, backend/tests/calibration_lab/test_m0_config_overlay.py, docs/audits/ADR-O-361_IMPACT.md, architecture/calibration.yaml (M0), config/calibration/ (M0)

`ADR-FOUNDATION-FREEZE` [ONTO] **Foundation Freeze (Stage 0)** — Упразднена двойная истина состояния (State Double Truth). Whitelist `_RUNTIME_TOP_LEVEL_KEYS` удалён, мерж выполняется рекурсивно через `_deep_merge`. `JsonPersistenceAdapter` bypass закрыт, всё идёт через `atomic_commit_all`. Параллельный WorldTick-путь (`phase_2_world_tick.py`) упразднён (превращён в stub), флаг `wt_dirty` удалён. `write_to_legacy` переименован в `to_persistence_dict` (используется только в persistence layer).
  Taboo: ❌ Расширение whitelist'ов для починки потери поля; Прямой вызов `save_scene` в обход `atomic_commit`; Использование `wt_dirty`; Вызов `write_to_legacy` в runtime.
  Status: ACTIVE
  Files: `svc/npc/npc_loader.py`, `svc/scene_state_manager.py`, `svc/game_loop/phase_2_world_tick.py`, `svc/npc/state_applicator.py`

`ADR-WRITE-GUARD` [ONTO] **NPCState Write Guard** — Внедрён guard `__setattr__` в `NPCState`. Прямая мутация полей `NPCState` вне `StateApplicator` (и других авторизованных модулей SSOT) поднимает `ArchitecturalViolationError`. Прямые мутации в persistence layer (`npc_loader.py`, `memory_manager.py`) переведены на `object.__setattr__`.
  Taboo: ❌ Прямое присваивание `state.field = value` вне `StateApplicator`; Обход guard через `object.__setattr__` в runtime-слое (только в persistence).
  Status: ACTIVE
  Files: `mod/npc_state.py`, `svc/npc/state_applicator.py`, `app/errors.py`

`ADR-SSOT-EPISTEMIC` [ONTO] **Epistemic SSOT & Belief Delta** — `BeliefTransitionEngine` больше не мутирует `state.beliefs` напрямую. Метод `commit` генерирует `BeliefDelta` (frozen dataclass), который затем применяется через `StateApplicator.apply_belief_delta` — единственный физический write-path. Введена структура `Cause` для прокидки provenance.
  Taboo: ❌ Вызов `state.beliefs.update()` вне `StateApplicator.apply_belief_delta`; Мутация убеждений без `Cause`.
  Status: ACTIVE
  Files: `svc/npc/belief_transition_engine.py`, `svc/npc/state_applicator.py`, `mod/npc/beliefs.py`, `mod/psychological.py`

`ADR-SSOT-ECONOMIC` [ONTO] **Economic SSOT & Avatar Ownership** — Игрок обрабатывается как `avatar NPC` (id="player") в `StateApplicator.apply_batch`. Прямые мутации `_avatar.body_state["money"]` в `game_loop` и `phase_2_world_tick` устранены. Дельты экономики применяются через `StateDeltas(domain=ECONOMY)`. Введён `StateApplicator.update_relationships` как единый write-API для `RelationshipStore`.
  Taboo: ❌ Прямая мутация `_avatar.body_state["money"]`; Обновление `RelationshipStore` в обход `StateApplicator`.
  Status: ACTIVE
  Files: `svc/npc/state_applicator.py`, `svc/game_loop/__init__.py`

`ADR-CAUSAL-SPINE` [ONTO] **Causal Spine (Stage 1)** — Внедрена причинная цепочка и детерминированный реплей. `TickOrchestrator` создаёт замороженный `WorldSnapshot` (deep copy) в начале тика и передаёт его в `EventCompiler`. `StateApplicator.apply` требует `cause: Cause` и пишет `CausalEntry` в `causal_ledger`. Добавлены методы `NPCState.query_ledger` и `trace_causal_chain` для программного построения цепочки. `MissingProvenanceError` поднимается при отсутствии cause.
  Taboo: ❌ `StateApplicator.apply` без `cause`; Мутация `WorldSnapshot` после создания; Прямая мутация `causal_ledger` в обход `StateApplicator`.
  Status: ACTIVE
  Files: `svc/tick_orchestrator.py`, `svc/npc/state_applicator.py`, `mod/npc_state.py`, `mod/psychological.py`

`ADR-EVENT-VISIBILITY` [ONTO] **Event Visibility Filter** — Внедрён метод `PerceptualKernel.can_observe(event, distance, observer_id, target_id)`, который проверяет `event.radius` и `event.visibility` (public, private, whisper) для фильтрации телепатии. `ClaimEventSubscriber` использует этот метод вместо жестко заданного `HEARING_RADIUS`.
  Taboo: ❌ Использование констант радиуса вместо `event.radius`; Игнорирование `event.visibility` при рассылке событий.
  Status: ACTIVE
  Files: `mod/npc_state.py`, `svc/events/claim_event_subscriber.py`

---

`ADR-O-364` [ONTO] **LLM Task Execution Boundary — Strict Reconstruction, Causal Backpressure & Per-Task Timeout (022, 027, 038)**
Суть: Восстановление контракта ADR-O-343 для пула LLM-задач. (1) Строгая реконструкция (038): Canonical reconstruction failure → FAILED / drop + structured diagnostic, НИКОГДА не raw dict / ambient. (2) Causal Backpressure (027): Ambient overflow → DROP, Canonical overflow → PRESERVE (вытесняет ambient). Запрещена деградация canonical → ambient. Источник causal class — `task_type`, а не `priority`. (3) Per-Task Timeout (022): Исполнение LLM-задачи оборачивается в `threading.Timer`, который по истечении срока вызывает `_abort_generation()` у `router.py`. Это гарантирует освобождение воркера `ThreadPoolExecutor(max_workers=1)` без блокировки главного потока.
  Taboo: ❌ Silent fallback на `payload_dict` в реконструкции; ❌ Drop canonical задач при переполнении очереди; ❌ Деградация canonical до ambient; ❌ Использование `priority` (int) для causal классификации (только `task_type`); ❌ `future.result(timeout)` без отмены реального LLM-запроса; ❌ Введение `TaskState.FAILED` без отдельного ADR (пока используем drop + `FINISHED` с error artifact).
  Status: ACTIVE
  Files: `backend/app/services/game_loop/task_scheduler.py`, `backend/app/services/execution/dialogue_queue.py`, `backend/app/services/execution/dialogue_executor.py`

`ADR-O-363` [ONTO] **Unified Behavioral Ownership — Commitment Registry & Arbitration (Stage 2A / S203.1, S215)**
Суть: Один NPC — один активный поведенческий владелец. Любая система может породить candidate; материализовать поведение может только executor под активным commitment. Реестр: `scene_state["active_commitments"]` (только активные) + `commitment_history` (retained, cap 10/NPC) + `commitment_ordinals` (монотонные, не переиспользуются). Единственный писатель — `CommitmentRegistry`. Четыре несводимые семантики арбитража: COMMIT / CONTINUE / REJECT / INTERRUPT; INTERRUPT — не флаг, а контракт через interrupt-интерфейс исполнителя (вводится в S203.3/4). `cause` (почему возник) ≠ `interrupt_reason` (почему прекращён); универсальное поле reason запрещено. `commitment_id = H(tick, npc_id, action, ordinal)` — детерминированный (uuid4 запрещён, INV-REPLAY-DETERMINISM); `parent_commitment_id` — каузальная цепочка (новое обязательство ПРОИЗОШЛО из прерванного, не «продолжает» его). REJECT не пишет в реестр (candidate lifecycle ≠ commitment lifecycle → telemetry S203.2). INTERRUPTED терминален (резюм = новый commitment с parent); CANCELLED доступен из любой активной фазы. TaskState / TraversalState / CommitmentState — три несводимых FSM-слоя. SSM не классифицирует behavioral-семантику: cause verbatim от upstream, пустой → `UNKNOWN_LEGACY_SOURCE`. Зеркало материализации ровно в ДВУХ точках: ProjectionEngine._apply_position (primary — первый писатель traversals в dual-rail, ADR-O-204) / SSM.apply_change (fallback для не-скомпилированных изменений); guard in-flight — детерминист между ними (двойной commit исключён). Владение lifecycle: Executor — статусные переходы; SSM — terminal-GC; обходные pop traversal — долг S203.4 (легализуются INTERRUPT-контрактом; as-is: PENDING виртуален/born-MOVING Н-50; CANCELLED без продюсера Н-45). Поглощает плейсхолдеры ADR-XXX (scene_state_manager:1399, phases/traversal.py:124, projection_engine:127). Shadow S203.1: зеркалит факты исполнителей, не меняет поведение (`COMMITMENT_REGISTRY_ENABLED=False` = полный no-op; A/B DriftLab: поведенческий diff=0). Baseline v2 (200 тиков, tavern): terminals=42 (COMPLETED 38/INTERRUPTED 4), SUPERSEDED ~9%; 64% движений — проактивные социальные интенты DecisionHub (random wander 0%) + DLG_QUEUE OVERFLOW (Н-56) в том же прогоне. Разделение сторон: S203.2 = producer-side (REJECT режет производство задач), ADR-O-364 = queue-side (backpressure) — комплементарны, не дублируются.
  Taboo: ❌ Прямая мутация реестра вне CommitmentRegistry; uuid4-ID; INTERRUPTED без причины; переиспользование/уменьшение ordinal; классификация cause слоем проекции; REJECT в реестре; слияние трёх FSM-слоёв; enforcement/INTERRUPT до S203.2/S203.4; обход traversal-FSM (прямой pop) без зеркала реестра; третье зеркало материализации (разрешены только две точки: ProjectionEngine primary / SSM fallback).
  Status: ACTIVE (S203.1 shadow ✅; S203.2 arbitration ✅; S203.3 traversal ownership ✅ — interrupt_traversal: атомарный interrupt ДВУХ рельсов (prepare-then-commit, preview обеих FSM; частичный interrupt запрещён — закон Мастера; причины из реестра _INTERRUPT_TRAVERSAL_REASONS, расширение=мини-ADR); легализация bypass'ов Н-46a/Н-46c (ME:330 + ORCH:967 → interrupt_traversal за флагом TRAVERSAL_OWNERSHIP_ENFORCEMENT, env, default OFF); Ц1: SSM.gc_traversals — ЕДИНСТВЕННЫЙ GC-владелец (TES самоудаление устранено; гарантированный GC-проход за тик после Фазы 0.5 — INV-TRAV-ZOMBIE зелёный); доменная чистота: commit-фаза без импортов services (§1.2); G6 cross-scene continuity — юнит-закреплён — CommitmentArbiter: PASS|REJECT(reason ∈ DUPLICATE/INCUMBENT), один арбитр / два invocation points (simulation.py Гейт① + movement_bridge.py Гейт②), read-only, INTERRUPT≡нет до S203.3/4; ARBITER_ENFORCEMENT env-флаг (default False); A/B 200 тиков: SUPERSEDED 4–16→0, COMPLETED 62–90%→100% (42/42), движение живо (200/200 тиков, real_errors=0) — «один владелец → предсказуемое исполнение» доказано; ACTIVE={PROPOSED,COMMITTED,EXECUTING,BLOCKED}, миграция has_active_commitment на реестр с legacy-fallback; traversal/task ownership + INTERRUPT — S203.3/4)
  Files: `dom/action_commitment.py`, `svc/action/commitment_registry.py`, `svc/action/commitment_arbiter.py`, `svc/phases/simulation.py`, `svc/phases/movement_bridge.py`, `svc/npc/npc_tick_pipeline.py`, `svc/projection_engine.py`, `svc/scene_state_manager.py`, `svc/spatial/traversal_execution_system.py`, `svc/spatial/movement_engine.py`, `svc/tick_orchestrator.py`, `mod/world_snapshot.py`, `dom/traversal_schema.py`, `tests/test_action_commitment.py`, `tests/test_commitment_ssm_integration.py`

**`ADR-O-365` [ONTO] Task/Windup/Sleep Ownership + Arbiter-INTERRUPT (Stage 2A / S203.4)**
Суть: Единое поведенческое владение распространяется на всех исполнителей: dialogue-task (только canonical-класс: `produces_claim(intent) ∨ has_proposition`), windup, sleep. Единственный ownership-источник — `active_commitments` (писатель CommitmentRegistry); `has_behavioral_owner` — строго проекция реестра: структуры исполнителей (active_traversals, pending_tasks, _windup_registry, coupling_profile) — только liveness-сигналы reconciliation, никогда не решают «занят ли NPC» напрямую; traversal-legacy-fallback (Н-35) не расширяется, смерть — решение Мастера после S203.7. Арбитр получает четвёртую семантику: INTERRUPT(PRIORITY_SUPERSEDE) при `candidate_priority > incumbent_priority + INTERRUPT_THRESHOLD(=3)`; приоритет — результат доменной policy (`resolve_candidate_priority`, шкала `s203.4.v1`: EXPLORATION=1, ROUTINE=2, SOCIAL=3, SLEEP=6, SURVIVAL=6, WINDOWED=7 — calibration policy, не онтология), сохраняется в commitment вместе с `PRIORITY_POLICY_VERSION`; приоритет НЕ входит в `commitment_id`; смена версии политики без мини-ADR с миграцией replay-семантики запрещена. REJECT(INCUMBENT_PROTECTED) — отдельная семантика «механизму запрещено прерывать» (executor-boundary: task/windup/sleep; policy: EXECUTING при отсутствии emergency-продюсера — POLICY, не онтология) против «проиграл конкуренцию» (INCUMBENT); множество вердиктов закрыто. INTERRUPT исполняется только в invocation points через `interrupt_traversal(PRIORITY_SUPERSEDE)` (атомарность двух рельсов, закон №14); арбитр read-only; parent нового commitment — history-lookup (`terminal_tick==tick ∧ interrupt_reason==PRIORITY_SUPERSEDE`), fallback None (ложная каузальная связь хуже разрыва). Зеркала созданий — non-superseding commit: коллизия с инкумбентом → skip + телеметрия `*_MIRROR_COLLISION` (auto-supersede в зеркалах = зомби: мёртвый commitment при живой физике). Терминальные зеркала task — через outbox: async-воркер НИКОГДА не пишет реестр; исходы → thread-safe outbox TaskScheduler; дренаж sync в двух точках (вход `execute_pending` + `idle_tick` между `execute_pending` и `unlock_tick`) — тихие тики не создают backlog. Сон — state-based reconciliation после Фазы 0.6 (coupling∈{SLEEPING,REM} ∧ нет владельца → commit executor='sleep'; wake → COMPLETED; NPC исчез → INTERRUPTED(SLEEP_VANISHED)); B2-конфликт «сон при живом traversal-инкумбенте» → телеметрия, разрешение — S203.6 (закон №19). Terminal-mapping: reconstruction-drop/no-executor/DEDUP → CANCELLED; M-29-purge/player-turn-смерть → EXPIRED; artifact-fail → FAILED(TASK_ERROR); crash-исполнения → FAILED(TASK_CRASH); BLOCKED-таймаут (BLOCKED_TIMEOUT_TICKS) → FAILED(BLOCKED_TIMEOUT); grace safety-net sweep → INTERRUPTED(TASK_VANISHED); windup stale → INTERRUPTED(WINDUP_STALE_INTENT). Новый контракт `fail_reason` — симметрия закона №7 (cause ≠ interrupt_reason ≠ fail_reason). Приоритет очереди (TaskPriority, ADR-O-364) ≠ приоритет арбитража — развёдены контрактом. Н-42: `domain/tasks.py` УДАЛЯЕТСЯ (глобально ноль ссылок backend/scripts/frontend; uuid4 в фабрике task_id — нарушение закона №4, причина смерти; compatibility shim запрещён). Н-40: `_windup_registry` (кортеж-ключ → строковый `"{campaign}::{actor}"`, round-trip §12) + `_pending_intents` (+`_pending_transfers`) → scene_state. Гейты: HARD (stale_commitment_rate=0 как жёсткий инвариант; атомарность = 0 частичных прерываний; детерминизм INV-REPLAY-DETERMINISM; RED=0 в повторе SUPERBOX-ACTION-INTEGRITY включая закрытие Y6; p95 tick +≤10%) vs CALIBRATION (thrash / interrupt-rate / REJECT-профиль / completion-distribution / длительность commitment — диагностика, не истина; 10% — ориентир, не закон мира). A/B двухстадийный: Stage A (mirrors ON, policy OFF — ловля over-locking до включения прерываний) → Stage B (+policy). Флаги каскадом: `S203.4_OWNERSHIP_MIRRORS` (default OFF), `S203.4_ARBITER_INTERRUPT` (default OFF; активен только при ARBITER_ENFORCEMENT=True).
Taboo: ❌ Новый ownership-источник кроме active_commitments; ❌ task/windup/sleep-fallback в has_behavioral_owner; ❌ priority в commitment_id; ❌ смена PRIORITY_POLICY_VERSION без мини-ADR; ❌ новые ВЕРДИКТЫ-классификаторы (только reason-константы по прецеденту №16); ❌ auto-supersede в зеркалах; ❌ запись реестра из async-воркера; ❌ ambient-речь как commitment-продюсер; ❌ compatibility shim для domain/tasks.py; ❌ третий invocation point / третья точка зеркала материализации; ❌ EXECUTING-uninterruptible как онтология; ❌ emergency-причины без живого продюсера.
Status: ACTIVE (S203.4: контракт утверждён Мастером, вердикты D-1…D-9; реализация Э2–Э10).
Files: `dom/action_commitment.py`, `dom/action_priority.py` (NEW), `dom/traversal_schema.py`, `svc/action/commitment_registry.py`, `svc/action/commitment_arbiter.py`, `svc/phases/post_decision.py`, `svc/game_loop/task_scheduler.py`, `svc/game_loop/__init__.py`, `svc/tick_orchestrator.py`, `svc/npc/sleep_lifecycle_service.py`, `dom/tasks.py` (DELETE), `tests/test_action_commitment.py`, `tests/sandbox/commitment_baseline.py`, `tests/sandbox/SUPERBOX/scenarios/action_integrity_test.py`

## 🧬 EQUIVALENCE VALIDATOR (Drift Measurement)

**Уровни сравнения:**
| Уровень | Что сравниваем | Провал = |
|---------|---------------|----------|
| L0 Identity | npc_id, alive, location_id | FATAL |
| L1 Topology | location_id, node_id | ERROR |
| L2 Causality | cause, event_type, transition_chain | CRITICAL |
| L3 Presentation | local_position, rotation | WARNING |

**Классы drift:**
| Класс | Пример | Вердикт |
|-------|--------|---------|
| A Косметический | x=10.1 vs x=10.2 (deterministic jitter) | WARNING |
| B Проекционный | same node, different coords | WARNING+ |
| C Топологический | node_A vs node_B | ERROR |
| D Каузальный | traversal_exists: legacy=True vs shadow=False | CRITICAL |
| E Онтологический | NPC exists vs NPC missing | FATAL |

**Критерий переключения власти (ФАЗА 3):**
1. 0 Ontological Drift (E=0)
2. 0 Causal Drift (D=0)
3. 0 Topological Drift (C=0)
4. Replay determinism = 100%
5. N ≥ 100,000 comparisons

---

*Версия: 7.0 (Unified & Expanded)*
*Сессия: S201 | Инвариантов: 39 | DriftLab: 99k comparisons*