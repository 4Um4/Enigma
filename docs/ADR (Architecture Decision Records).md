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

**L8.2: PerceptualKernel Write Guard** (ADR-O-379, S243)
Caller-based замок субъективного состояния восприятия: prod-писатель ЕДИНСТВЕННЫЙ — `StateApplicator` (применение perception-дельт/директив, клампы [0..1], state_applicator.py:1186-1236) + сам модуль (`__init__`, `_pk_from_dict`); тест-исключения по цензусу E2.0-c (npc_sandbox, t06, authority_erosion ×2 `__name__`-варианта). Всё остальное → `ArchitecturalViolationError` — снаружи DeltaGate пути в психику нет (INV-LLM-NOT-SSOT). Рождён D2-атакой экзамена B0 (молчаливый DEBT-R9). Дубль `__setattr__` (артефакт двойного патча) устранён до терминального коммита. IMPACT: `docs/audits/ADR-O-379_IMPACT.md`.
- ❌ **Taboo:** Прямое присваивание PK-полей вне цензуса; расширение `_PK_ALLOWED_WRITERS` без цензуса писателей; внесение causal_state_test в исключения (D2 обязан падать).
- 📁 `mod/npc_state.py` (PerceptualKernel: `_PK_ALLOWED_WRITERS`, `__setattr__`), `svc/npc/state_applicator.py`

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

**L14.5: BeliefState Write Guard** (ADR-O-380, S243)
Caller-based замок L2/эпистемики: `BeliefState.update()` разрешён только цензусу — сам модуль; `npc_state` (загрузка psyche["beliefs"]); `npc_loader` (`_beliefs_from_persistence` — легальный писатель, найден замком round-trip); `belief_transition_engine` (R8-канал, генерирует BeliefDelta); `state_applicator` (apply_belief_delta — единственный физический write-path); `belief_aggregator` (CoherenceBeliefAggregator, pattern-based R8-канал). Всё остальное → `ArchitecturalViolationError`. Рождён D3-атакой экзамена B0 (запись мимо BTE/DeltaGate проходила молча — enforcement-дыра ADR-SSOT-EPISTEMIC). Мёрджа двух R8-каналов нет — guard фиксирует writer'ов, не семантику конфликта. IMPACT: `docs/audits/ADR-O-380_IMPACT.md`.
- ❌ **Taboo:** `state.beliefs.update()` вне цензуса; мутация убеждений без Cause/BeliefDelta; расширение `_UPDATE_ALLOWED_WRITERS` без цензуса; внесение causal_state_test в исключения (D3 обязан падать).
- 📁 `mod/npc/beliefs.py` (`_UPDATE_ALLOWED_WRITERS`, `update`), `svc/npc/belief_transition_engine.py`, `svc/npc/state_applicator.py`, `svc/memory/belief_aggregator.py`, `svc/npc/npc_loader.py

**L14.6: Conclusion Layer — Experience → Conclusion (BC-1, dormant)** (ADR-O-381, S243-вердикты / S247-реализация; ACTIVE: приёмка bc1_conclusion_test 6/6 GREEN, dormant default OFF)
Новый авторизованный переход состояния: пережитый опыт → машино-пригодный вывод. Триплет subject/predicate/object + confidence [0..1] + evidence[event_ids → L1] + source=DIRECT_EXPERIENCE — НЕ фразы, НЕ флаги поведения (фальсификатор: NPC меняет будущее поведение без флага поведения). Тропа (F1a): Фаза 9 при phase_2_events → ConclusionEngine (pure; вход — ТОЛЬКО новые дельты/трейсы тика) → ConclusionGate по образу DeltaGate (F2б: закрытый predicate-реестр, старт — ОДИН предикат IS_DANGEROUS; кламп confidence; идемпотентность (trace_id, subject, predicate) — перенос AG1-INV-TRACE-ONCE; Gate = аудит, НЕ писатель) → ConclusionStore.apply (единственный write-path) → CONCLUSION_FORMED (F2c: новый EventType, observation-only, Закон XI). SSOT-А: per-agent RAM + round-trip scene_state["conclusions"] → Фаза 10 atomic_commit_all (прецедент EpistemicStore S193: write tick_orchestrator:691 / read game_loop:447-453 / терминал SSM:555); собственная SQLite ЗАПРЕЩЕНА (анти-паттерн ExpectationStore). NO-VACUUM (владелец, вербатим): «BC-1 не имеет права создавать conclusion из отсутствия нового опыта» — без новых EXPERIENCE_DELTA нет CONCLUSION_FORMED и нет записи; вход ≠ текущее состояние. CONCLUSION ──X──> EXPECTATION закрыт до BC-2 (F3а; BC1_ENABLED default OFF = no-op, INV-BC1-NOOP; dormant M1a-класса). Anti-Bond (Р17-П1): уникальная работа — вывод-правило, derived из множества собственных ExperienceTrace, evidence-адресуемый (полная таблица: BC1_PRE_FLIGHT.md §3); Two-Domain-отклонение по мандату лестницы (потребители BC-2/BC-5 заявлены каноном). Досье: docs/audits/BC1_PRE_FLIGHT.md; IMPACT: docs/audits/ADR-O-381_IMPACT.md (оговорка №11: epistemic read-path хардкодит локацию «tavern» game_loop:448 — восстановление ConclusionStore хардкод НЕ наследует).
- ❌ **Taboo:** conclusion как флаг поведения (avoid_*); фразы/текст в триплете; расширение predicate-реестра без мини-ADR; write в Expectation/PK/beliefs/RelationshipStore/DecisionHub; запись мимо ConclusionGate; глобальный store; DELETE (append-only + confidence-decay по образцу MemoryCrystal); confidence = truth; TESTIMONY-ветка (BC-5); собственная SQLite-персистенция; bc1-сценарий в guard-исключения (D-группа = замок экзамена).
- 📁 (план BC-1-сессии) `dom/conclusions.py` (триплет + proposal + predicate), `svc/memory/conclusion_engine.py` (pure), `svc/memory/conclusion_gate.py` (мембрана), `svc/npc/conclusion_store.py` (SSOT), `svc/phases/integration.py` (Фаза 9, за флагом), `svc/tick_orchestrator.py` (store + pre-commit проекция), `svc/events/event_types.py` (CONCLUSION_FORMED), `tests/sandbox/SUPERBOX/scenarios/bc1_conclusion_test.py

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

ADR-O-366 [ONTOLOGY] OpportunityProducer: Production Wiring — _build_opportunity_context inline in npc_tick_pipeline; Phase 1 (proximity proxy + real distance + perceived_allies); weapon=False; invariant: producer=DATA only

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

`ADR-O-367` [ONTO] **Intervention Consequence Routing — Structured Semantics Branch (Phase 1)**
Суть: Вмешательства с каузальными дельтами (semantic_action ∈ HELP/BLACKMAIL/ACCUSE) маршрутизируются в _process_player_action на ActionConsequenceCompiler (ctx.mvp_controller) — тот же production write-path, что и DM-конвейер (game_loop:_execute_dm_and_intent_resolution → intent_to_player_action → process_action → RelationshipStore.update). Ядро текст НЕ парсит (L4.1 неприкосновенен): семантика обязана приходить структурированной в InterventionEvent.payload (semantic_action + target_reference/target_id; потребляется также конвертером tick_utils:350 → IntentDTO → WillpowerGate). action_id детерминирован (f"interv:{tick}:{ACTION}:{target}") — идемпотентность компилятора + replay. Кампания лаборатории инициализируется init_campaign (зеркало P-MVP-1 из new_game) — без него P2-мост дельт в SSOT мёртв. Диспетчеризация с DM-путём взаимоисключающая (payload с dm_ctx ≠ payload с semantic_action) — двойного применения нет. Расширение списка семантик — по одной мини-записи на действие (прецедент ADR-O-362).
❌ Taboo: парсинг текста в ядре; вмешательства без структурной семантики; вызов компилятора мимо _process_player_action; uuid4/nondeterministic action_id; init_campaign-обход lab-сессией при ожидаемых дельтах SSOT.
Status: ACTIVE (M1/S220; runtime: maid_lusya→player trust None→20.0, идемпотентность подтверждена)
Files: backend/app/services/tick_orchestrator.py (_process_player_action), backend/app/services/calibration/experiment_runner.py (start/step), backend/app/contracts/interventions.py (контракт фабрики), backend/tests/calibration_lab/test_m1_trust_intervention.py

`ADR-O-368` [ONTO] **Calibration Lab Frontend Isolation Exception (Dev Enclave)**
Суть: Calibration Lab (frontend/map_editor/ui/lab_screen.py, Вариант B — полноэкранный режим Pygame Map Editor) является изолированным developer/testing enclave и получает ограниченное исключение из frontend isolation policy (Устав §1.1) только для экспериментального чтения SSOT через прямые Python-импорты (ExperimentRunner start/step/stop). Исключение НЕ распространяется на production UI и не ослабляет INV-FRONTEND-ISOLATION: точечный allowlist в scripts/lint_frontend_isolation.py, расширение — только через новый ADR. Обоснование (S220, мастер-решение N2): лаборатория доказала статус потребителя production causal spine (ADR-O-366: InterventionEvent → TickOrchestrator → компилятор → RelationshipStore) — «не переписывать causal architecture ради лаборатории; лаборатория — потребитель production spine, а не второй production spine» (правило M1).
❌ Taboo: расширение allowlist без нового ADR; импорты backend в production UI (game_screen, settings_screen и др.); запись в ядро из lab_screen в обход ExperimentRunner/InterventionEvent (границы ADR-O-361 остаются в силе).
Status: ACTIVE (S220, N2 APPROVED)
Files: scripts/lint_frontend_isolation.py, frontend/map_editor/ui/lab_screen.py, backend/tests/IPT.py (INV-FRONTEND-ISOLATION через run_lint)

`ADR-O-369` [ONTO] **Relationship Engine — онтологический контракт фазы A (M0)**
Суть: ТЗ-RE-01 v1.9 зафиксирован как архитектурный контракт (architecture/relationship_engine.yaml): 36 строк онтологической классификации §5.0 (классы I–IV + TOMBSTONE + FORBIDDEN), 8 компонентов §4.1, владельцы/write-политика, запреты №1–№35 с картой enforcement (grep/schema/test_deferred/review/existing_ipt), tombstone-отрицательная онтология (Received, Bond, Infatuation, g, k_up/k_down/τ_n, η_s-ускоритель, β/T_half, H_i/ρ, σ, DeprivationHorizon), мораторий №35.2 (Class IV readout влюблённости до закрытия Р18), инвариант Р17-INV-1, COLLISION-решение frustration (владелец NeedLevel.frustration; §5.2-поле = read-only проекция; семантическая эскалация в GPT — в ТЗ v1.9 коллизия §5.1/§5.2 жива). Рантайм НЕ меняется. Enforcement — scripts/lint_relationship_engine.py (CI + pre-commit): канонический набор узлов закрыт (новый узел онтологии = вердикт GPT + ADR), scoped-греп запрещённых классов имён в backend/app/**/*.py (ядро имён захардкожено в линтере и сверяется с yaml — стена заморозки не разбирается изнутри), запретные рёбра (№26/матрица 9.10.7), контент-канон config/ вне зоны сканирования (граница механика/контент №35; allowlist: truth_state_tavern.json, lusya.json, village_relations.json). Кодовые аудиты M0: frustration — 0 writers; infatuation/агрегаторы — 0 следов в backend/app. YAML ≠ второй источник истины: формулы §6 и числа в контракт не переносятся (узел = класс/владелец/writable/фаза/инвариант/provenance/ref).
❌ Taboo: воскрешение tombstone-сущностей под любыми именами (№25/№28/№34/№35 — включая falling_in_love_score, romantic_attention, chemistry и линз-класс); формулы/коэффициенты §6 в yaml; расширение канонического набора узлов без вердикта GPT; Class IV readout влюблённости до закрытия Р18 (№35.2); второй writer/store домена RE (№5); удаление имён из forbidden-ядра линтера.
Status: ACTIVE (M0 закрыт; фазы B–K реализуют контракт по гейтам §10 ТЗ-RE-01)
Files: architecture/relationship_engine.yaml, scripts/lint_relationship_engine.py, docs/audits/ADR-O-369_IMPACT.md, "docs/Почти Актуальные TZ/ТЗ_RE-01_Relationship_Engine_v1.9.md"

`ADR-O-370` [ONTO] **Relationship Engine — Phase B / M1a: субстрат потребностей (RelationshipStateStore)**
Суть: Первый рантайм-слой RE (ТЗ-RE-01 v1.9 §10-B/§8.6 M1a): контракты NeedSlot (frozen, кодовые дефолты-плейсхолдеры, №15) / NeedLevel (три раздельных аккумулятора: давление/сатурация/фрустрация — №20/№21/№23) / PreferenceModel / HardConstraint / ExclusivityRequirement + RelationshipStateStore над scene_state["relationship_state"] (статический сервис по прецеденту CommitmentRegistry; persistence lifecycle принадлежит atomic_commit — Foundation Freeze, собственный диск запрещён). Слоты только sexual+intimacy (раунд 4); attachment отсутствует добровольно (гейт АТ-1..3, №17/№19 — пустых слотов «на будущее» нет). Красный инвариант M1a (Мастер): создано МЕСТО ХРАНЕНИЯ, не механизм изменения — стор не вызывается рантаймом (писатели M2/D, G/H), поведение тика байтово идентично (IPT 44/44 до==после). Write-цепочка: StateApplicator.update_needs (единственный runtime-writer, caller-guard по образцу _ALLOWED_WRITERS) → стор → scene_state; Read-контракт: только frozen DTO в свежих коллекциях, alias-мутация невозможна; чтение не мутирует scene_state (нет lazy-init на read); повреждённая структура — ContractValidationError, не дефолт. NPC-config-authoring секции needs НЕТ (параметризация — фаза M; порядок: ONTOLOGY→CONTRACT→RUNTIME→PARAMETERIZATION→CALIBRATION). Отклонение от PRE-FLIGHT по археологии: полная О1-интеграция Cause→causal_ledger отнесена к M2 (causal_ledger привязан к NPCState — ADR-CAUSAL-SPINE, RE-стор scene_state-backed; привязка была бы сменой владельца истины; в M1a cause принимается и структурно логируется). Попутная санация state_applicator (легаси в границах M1a-файла): F821 cause×2 (apply_physical/apply_deltas_only — сигнатуры дополнены; apply_physical внешне не вызывается, apply_deltas_only — путь восстановления стресса), F841×4 (мёртвые extraction-присваивания IdentityPayload), TYPE_CHECKING BeliefDelta, whitespace; инцидент-урок: патч с «условным применением» не выдаётся — сначала факт сигнатуры, потом патч (SyntaxError в ядре, пойман компиляцией, закрыт в той же сессии).
❌ Taboo: расширение закрытого реестра need_id без вердикта GPT+ADR (№17); второй writer/персистентный кэш/mutable read-проекции (№5, вердикт Мастера); собственный persistence-path стора; поля RE в NPCState; конфиг-авторинг needs до фазы M; поля адаптеров сверх §5.1.
Status: ACTIVE (M1a; M1b — миграция 5 скаляров RelationshipStore в v2-схему, отдельный ADR)
Files: backend/app/domain/relationship_contracts.py (новый), backend/app/services/social/relationship_state_store.py (новый), backend/app/services/npc/state_applicator.py, backend/app/services/scene_state_manager.py, backend/tests/test_relationship_state_store.py (новый)

`ADR-O-371` [ONTO] **W1 Spatial Topology — Object Relation Substrate (W-track Часть II §20)**
Суть: Реляционная нормализация мировой онтологии. Семь отношений ТЗ хранятся canonical single-side на WorldObject (LOCATED_AT = location_id+position; HELD_BY = holder; OCCUPIED_BY = occupancy; CONTAINED_BY = container_id; SUPPORTED_BY = supported_by; ATTACHED_TO = attachment(host_id, slot) — атомарно; USED_BY = used_by — независимая ось). CarrierMode (FREE | HELD | CONTAINED | ATTACHED) — онтология авторитета позиции: РОВНО один, позиция авторитетна только в FREE. МАТРИЦА КОНФЛИКТОВ СВЕРХ CARRIER-РЕЖИМОВ — КАЛИБРУЕМАЯ ПОЛИТИКА, НЕ ОНТОЛОГИЯ (вердикт Мастера, S230): W1 policy-правил не содержит. SSOT — scene_state["world_objects"]; WorldObjectStore — stateless статический фасад (прецеденты CommitmentRegistry / RelationshipStateStore): read без lazy-init (Pure Reducer Фазы 5), повреждённая структура — громкий OntologyViolationError; write — ТОЛЬКО типизированные операции (spawn / establish_relation / release_relation / relocate), generic update(**changes) отсутствует by construction; auto-release запрещён (явная цепочка release → establish); STRICT release; межобъектная валидация в сторе (существование object-целей, циклы связей, опора FREE+та же локация, relocate заблокирован позиционными SUPPORTED-зависимыми, содержимое следует владельцу). Persistence — ТОЛЬКО через существующий atomic_commit_all (Foundation Freeze, ноль специального кода), загрузка load_scene_at; DoD доказан реальным sqlite-адаптером (spawn → relation → commit → reload → тот же объект + второй мутационный цикл). Мост в тик: build_snapshot замораживает subtree deepcopy-полем WorldSnapshot.world_objects (паттерн active_commitments, S215); WorldSnapshotDTO/фронтенд — W7. ОТКЛОНЕНИЕ от буквы ТЗ §20.2 (по археологии): WorldTopologyProvider НЕ расширяется — tick-owned ETKE-IK поле не видит scene_state; канонический объектный API — WorldObjectStore; полевой мерж объектов в affordance — композиция W2. W0 CONTRACT CORRECTION (поглощено, вердикт Мастера): W0 был unconsumed PoC (0 потребителей, 0 тестов); удалены topology_relations (свободные строки), containment stored (→ inverse-запрос; mirror-поле = зомби-истина, урок S215), affordances stored (pure function по ТЗ §19.2 — вернётся W2 compute_affordances), WorldObjectRegistry (процесс-глобальный in-memory); миграция не требуется — subtree никогда не персистился. Runtime-writers: 0 (доктрина M1a — место хранения, не механизм изменения; поведение тика байтово идентично, IPT 44→45 без красных). Caller-guard отложен до W3 (появление легального causal writer → вопрос авторизации станет реальным; enforcement ради enforcement запрещён). Fixtures door/chair/container/carried_item — только тестовые; production-spawner вне W1.
❌ Taboo: прямая dict-хирургия scene_state["world_objects"] вне WorldObjectStore; второй runtime-источник объектов (in-memory registry/mirror-поля); presentation-поля в WorldObject; generic update(**changes); auto-release; policy-правила в W1 (валидация слотов attachment, вес, encumbrance — W2/W3/W4/W8); расширение WorldTopologyProvider объектными запросами; uuid4 object_id; собственный persistence-path стора; физика переноса в W1 (позиция производных carrier-режимов вычисляется владельцем — W3/W4); подключение W1 к TickOrchestrator/DecisionHub до W3/W4 causal writer.
Status: ACTIVE (S230; IPT 45/45, pytest 30/30, DoD-цикл Мастера GREEN)
Files: backend/app/domain/world_object.py (переписан), backend/app/services/world/world_object_store.py (новый), backend/app/services/world/__init__.py (новый), backend/app/models/world_snapshot.py (поле world_objects + мост), backend/tests/test_world_object_topology.py (новый, 30), backend/tests/IPT.py (INV-WORLD-OBJECT-TOPOLOGY, 45-й), architecture/world.yaml (новый, YAML-First), docs/audits/ADR-O-371_IMPACT.md

`ADR-O-372` [ONTO] **W2 Affordances — Semantic Action Resolution (W-track Часть II §21)**
Суть: Pure resolver `(WorldObject, BodyStateView, npc_position) → Tuple[SemanticAction, ...]` — возвращает действия, чьи предусловия выполнены СЕЙЧАС; precondition-кортежи сохранены на каждом действии для W3-ревалидации (гейты живут в кортежах, скрытые гейты резолвера запрещены — вердикт В9). Stored-поля affordances на WorldObject нет и не будет (производная не хранится, ADR-O-371). `WorldActionType` — закрытый enum, 19 значений ТЗ §19.2 (расширение = мини-ADR, класс ADR-O-349); INSERT_ITEM/REMOVE_ITEM зарезервированы до W3 (compound — в SemanticAction нет поля второго объекта, вердикт Мастера). Реестр предикатов v1 закрыт (7): IS_ALIVE/IS_CONSCIOUS/IS_CAPABLE — делегация доменному vital_state (ADR-123, ноль дублирования), STATE_IS, IS_ADJACENT_TO (евклид ≤ 1.5 м, calibration v1; вычисляется ТОЛЬКО в CarrierMode.FREE — в HELD/CONTAINED/ATTACHED позиция неавторитетна, ADR-O-371), HOLDER_IS, OCCUPANT_IS. BodyStateView — frozen read-model (npc_id-носитель идентичности, В2; falsy body → ValueError: L2.2 гарантирует body_state, §ENIGMA-003). effective_state: door/container — state-поле (FSM §22.1), chair — деривация из нормализованных полей W1 (BROKEN > HELD > OCCUPIED > AVAILABLE). В10-правка Мастера: пара OPEN+CLOSE выдаётся в состоянии OPEN для архетипов, чей FSM допускает оба перехода (door, container) — физическая доступность ≠ FSM-легальность, легальность решает W3. Substrate-only: 0 runtime-потребителей (доктрина M1a); wiring и первый легальный writer — W3 (тогда caller-guard по образцу M1a и live-часть INV-WORLD-OBJECT-TOPOLOGY).
❌ Taboo: stored affordances на WorldObject; LLM/IO/мутации в resolver и предикатах; расширение WorldActionType/реестра предикатов без мини-ADR; скрытые гейты вне precondition-кортежей; чтение body_state в предикатах мимо BodyStateView; импорт WorldTopologyProvider из W2-кода; @dataclass поверх enum-классов (инцидент S232: zero-field __eq__ схлопывает множества членов).
Status: ACTIVE (substrate-only; W3 = transition_object + первый writer + wiring)
Files: backend/app/domain/semantic_action.py (коррекция W0-остатка: +WorldActionType, STAND→STAND_UP), backend/app/domain/body_state_view.py (новый), backend/app/services/world/affordance_resolver.py (новый), backend/app/domain/constants.py (+AFFORDANCE_ADJACENCY_RADIUS_M), backend/tests/test_affordance_resolver.py (новый, 24), architecture/world.yaml (узел + edge + constraint), docs/audits/ADR-O-372_IMPACT.md

`ADR-O-373` [ONTO] **Body Idle-Projection Contract + Fatigue Consolidation + Delta-Policy Enum Unification (Stage 2B / S2B.5)**
Суть: (1) FLAT-контракт Phase 0.5: NPCStateSnapshot расширен плоскими READ-ONLY полями BodyEngine (velocity/activity/coupling_mode/body_mass), билдеры (tick_utils + combat_subscriber ×2) заполняют единый shape; до S2B.5 S2B.1–2B.4 были production-мёртвыми (unit-фикстуры = «объекты мечты», raw-форма в рантайме не существует); активация S2B.2–2B.4 — intended consequence. (2) ONE POLICY TYPE / ONE POLICY REGISTRY / ONE ENUM IDENTITY (вердикт Мастера): дубль ReductionPolicy+DELTA_POLICY_REGISTRY в dto.py УДАЛЁН, владелец — models/state_delta.py, dto.py ре-экспортирует (X as X, PEP 484), tick_utils импортирует из одного источника; Enum Identity Split ломал policy-сравнение в aggregate_deltas → PHYSIOLOGY молча падала в algebraic last-wins, вклад продюсера терялся. PHYSICS_COMPOSITE = PASS-THROUGH политика агрегации: физиологические дельты не редуцируются, сохраняются как отдельные StateDeltas и применяются последовательно единым StateApplicator (clamp); аддитивность — на слое применения, не агрегации. Generic additive-fallback для PhysiologyPayload в _reduce_additive ЗАПРЕЩЁН (маскирует рецидив split). (3) Fatigue-консолидация: BodyEngine — единственная per-tick fatigue-проекция (two-way износ 0→100 «плохо вверх», инверсия energy; wear 0.25×load×mass − recovery 0.1×(1−load), сон ×SLEEP_RECOVERY_MULTIPLIER; износ медленнее топлива — отдельный инвариант); legacy-писатели dormant: decay-ветка, сон-восстановление SleepLifecycle (прямая запись), reconcile LifeEngine (+8/тик; skip = S2B.6/2B.8). Модель: два payload-продюсера допустимы (combat event + BodyEngine per-tick), два per-tick physiological engines — НЕТ.
❌ Taboo: вторая per-tick fatigue-проекция; прямые записи body_state["fatigue"] мимо StateApplicator; duplicate enum/registry (Enum Identity Split); generic PhysiologyPayload-ветка в _reduce_additive; raw-фикстуры BodyEngine в тестах (объекты мечты); mutable-ссылки на body_state в снапшоте; расширение fatigue в S2B.5 за пределы физиологии (sleep_pressure-мост = S2B.6, давление = S2B.10/11).
Status: ACTIVE (S2B.5/S232 закрыт: прицельные 164/0, IPT 45/0, полный базлайн 12 known/0 новых; поведенческий гейт: n=6, e/h/nut≠0, fat=+0.075, snap_fat 0→3.0 монотонно)
Files: backend/app/models/idle_tick.py, backend/app/models/state_delta.py, backend/app/services/dto.py, backend/app/services/tick_utils.py, backend/app/services/body/body_engine.py, backend/app/services/combat/physiology_decay_handler.py, backend/app/services/combat/combat_subscriber.py, backend/app/services/npc/sleep_lifecycle_service.py, backend/app/services/npc/life_engine.py, backend/tests/test_action_commitment.py, backend/tests/test_physiology_decay_handler.py, backend/tests/sandbox/system/test_temporal_reconciliation.py, docs/audits/ADR-O-373_IMPACT.md

`ADR-O-374` [ONTO] **Canonical Sleep-Coupling Predicates + Sleep Inversion Diagnostics (Stage 2B / S2B.6 Phase A)**
Суть: (1) is_sleep_coupling в domain/body.py — единственный источник семантики «coupling-режим = физиологический сон» (SLEEP/DEEP_SLEEP/REM; DROWSY — не сон). Причина: string-identity split — продюсер (CouplingResolver) пишет литералы enum, потребители (BodyEngine ×3, sleep-зеркало S203.4) сверялись с фантомными "SLEEPING" из doc-drift (Causal Contract §5.2 + idle_tick:56) → сон-физиология ×3 и sleep-ownership были мертвы в production с рождения; S233-гейт фикстурно-зелёный (объект мечты: литерал, который резолвер не производит). (2) Диагностика (не калибровка): инверсия двух снов — поведенческий сон (routine.current) выжимает sleep_pressure → coupling FULL_WAKE (без ×3); бессонница накапливает sp → SLEEP/DEEP_SLEEP coupling на ногах с ×3-физиологией. Зонды отреверсированы; A/B-данные reports/DIAG_S2B6_*. (3) Фикстуры/сценарии канонизированы; гварды-вечники (truth-table, membership-pin, grep-гвард). Расширение множества sleep-coupling-режимов или новый член enum — через предикат (гвард упадёт первым).
❌ Taboo: строковые свитчи по coupling-литералам вне domain/body.py; фантомные литералы "SLEEPING"/"AWAKE" в коде/фикстурах/доках; обход is_sleep_coupling для семантики сна; второй per-tick physiological engine (закон №17); калибровка sleep-констант до DUAL-TIME (Q3); fatigue→sleep_pressure как прямой мультипликатор (Q2-A: homeostatic-модель, вход в B/D).
Status: ACTIVE (Phase A: прицельные 122/0, IPT 45/0, полный 20:10–20:13: 12 known + 1 атрибутированный чужой (bridge_3 — WIP трека памяти/психики, закон №15) / 0 моих; домен-6 167/0; П1–П8 подтверждены)
Files: backend/app/domain/body.py, backend/app/services/body/body_engine.py, backend/app/services/action/commitment_registry.py, backend/app/models/idle_tick.py, backend/tests/test_action_commitment.py, backend/tests/sandbox/SUPERBOX/scenarios/action_integrity_test.py, docs/00_CAUSAL_CONTRACT_v3.0.md

`ADR-O-375` [ONTO] **Physiological Sleep Onset Machine: sleep_onset_tick / wake_duration / SleepOnsetEligibility (Stage 2B / S2B.6 Phase B)**
Суть: (1) Сон = цепочка фактов, не строка: schedule-intent → SleepOnsetEligibility (чистое УСЛОВИЕ: intent ∧ NodeRole.BED-позиция ∧ settled ∧ alive ∧ ¬GAP9-блоки; резолвер не пишет состояние) → ФАКТ body_state["sleep_onset_tick"] (int|None, строго is not None — тик 0 валиден; единственный писатель — Phase 0.6 SleepLifecycleService) → coupling-сон-семейство (двусторонний гейт резолвера: без факта потолок DROWSY; факт жив → переживает decay pressure — ×3-окно = эпизод) → BodyEngine ×3 / sleep-ownership S203.4. Eligibility ≠ fact; no-BED ≠ resting. (2) wake_duration — первичный незажатый homeostatic аккумулятор (awake +1; onset/wake → 0; «40 часов без сна» представимы); sleep_pressure = bounded derived pressure: base × fatigue-модулятор (1 + fatigue/100 × FATIGUE_PRESSURE_MOD_COEFF, v1=1.0) — НЕ sp+=fatigue: оси независимы («устал, но выспался» представим). (3) Wake: arousal-гейт (без редизайна, Q5) ∨ intent-withdrawal; общий эффект _wake_from_sleep; sleep_end-SSOT НЕТ (история — будущий SleepEpisode в memory). (4) routine._sleep_start_tick девальвирован (writer — кандидат удаления). (5) Production-дифференциал: машина+граф верифицированы (смоук: beds резолвятся), доставка тел к кроватям — эскалация (кросс-локационные цели thief/borko; lusya 129/129 no_bed при валидной цели; elig=True=0/1200).
❌ Taboo: второй писатель sleep_onset_tick/wake_duration; вывод факта из coupling (обратная причинность); сон-режимы/×3 без факта; routine-строка как источник сон-физиологии; калибровка sleep-констант/×3 до DUAL-TIME и до доказанной доставки; W4-skip-физиология (S2B.8); awake stress recovery (В5a); прямая свзязь sp+=fatigue.
Status: ACTIVE (Phase B: прицельные 172/0, домен-6 190/0, IPT 45/0; production-дифференциал: отрицательная половина зондом, положительная — цепным тестом)
Files: backend/app/domain/body.py, backend/app/services/npc/sleep_onset_resolver.py, backend/app/services/npc/coupling_resolver.py, backend/app/services/npc/sleep_lifecycle_service.py, backend/app/services/tick_orchestrator.py, backend/tests/test_action_commitment.py, backend/tests/system/test_sleep_routing.py

`ADR-O-376` [ONTO] **W3 Object FSM — Execution Substrate + Shadow Discovery Gate (W-track Часть II §22)**
Суть: W3 = «ЧТО ПРОИЗОШЛО», не «FSM объектов». Домен: transition_object/damage_object — ЧИСТЫЕ переходы (FSM-семантика не знает стор/IO); стор: apply_transition/apply_damage — коммит в scene_state («FSM определяет семантический переход; Store определяет, где переход становится World State» — вердикт Мастера). TransitionResult (PASS | NO_OP | REJECT + reason, О7; не bool — L4) несёт old_state + topology_effect (О8: door-PASS помечает потенциальное изменение проходимости; spatial invalidation — W5, W3 граф не перестраивает — контракт зафиксирован в W3, реализация позже). О1: OPEN-in-OPEN = легальный NO_OP (В10-наследие: физическая доступность ≠ FSM-легальность). О2: chair — ПОЛИТИКА над операциями отношений W1 (SIT→OCCUPIED_BY establish и т.д.), не state-хирургия; предусловия проверяются ДО доменного вызова, расхождение policy/domain = громкий баг (except→REJECT запрещён — INV-SILENT-FAILURE поймал). О3: MOVED — legacy, перемещение = relocate. О4: bed — честный UNKNOWN_ARCHETYPE до W4. О6: damage_object — доменный закон над-FSM: damage>=1.0 → терминальное состояние АРХЕТИПА (door/chair BROKEN, container DESTROYED — терминален, не ремонтопригоден), без рекурсии в transition_object. Спавнер (production): editor objects → WorldObject через SpawnMapping-реестр (door+door_transition→door — graph_compiler подтверждает единый механизм wall-opening; chair; расширение = мини-запись); object_id = wo_<md5(campaign:spawn_loc:editor_id)> — IDENTITY ≠ LOCATION (immutable identity мира; spawn_loc — provenance; uuid4 запрещён); state-проекция locked→LOCKED/open→OPEN/иначе CLOSED; presentation/spatial-поля отбрасываются (W0); fault isolation per-object (прецедент BUG-SPATIAL-006a); вызов только в initialize_scene (сейв выигрывает — идемпотентность). Live-результат: INV-WORLD-OBJECT-TOPOLOGY live=0→18 (production-контур build_game_loop подтверждён повторно). GATE-1 SHADOW (реализовано): discovery-тень AffordanceResolver — World-object projection (мост W1→W2, заменимое представление — вердикт Q1a) → resolver → [W3_SHADOW] log/metric; точка: после заморозки снапшота, ДО PRE-TICK/Фаз 0+ (affordances существуют ДО решения — Q2: post-decision = validation, не discovery); discovery читает ТОЛЬКО фотографию тика (snapshot.npc_positions/world_objects); флаг W3_SHADOW_ENABLED (env, default OFF = no-op); ноль writers/decisions/events; ShadowMetrics = discovery-метрики (available/blocked/failed_predicates), стат. не смешиваются с execution-причинами (stale_commitment/precondition_failure/transition_rejection — зона G3). GORAN β G1 = GREEN + AMBIENT QUALIFICATION: 4 AB-пары {2,6,2,2} vs фон AC {4,7}, без выхода за фоновый максимум, медиана AB=2 < AC=5.5, структурный профиль дрейфа идентичен фону (S216-паттерн: терминалы стабильны, варьирует COMPLETED/INTERRUPTED-пропорция + микропозиции), structural guards зелёные во всех 10 профилях (crash=0, errors=0, terminals инвариантны), юнит-гварды доказали отсутствие mutation/decision-input/writer-канала. Ambient qualification — квалификация РЕЗУЛЬТАТА при текущем async-фоне (DEBT-QUIESCE, чужая зона), не архитектурная уступка. КОНТРАКТ G2/G3 (НЕ РЕАЛИЗОВАНО — следующие гейты): G2 = AffordanceSet как read-only вход DecisionHub/Arbiter (DecisionHub не содержит object-specific логики; STEAL = W5+-интерпретация TAKE в социально-правовом контексте, НЕ физическая механика — WorldActionType не расширяется); G3 = исполнение: commitment → ревалидация precondition-кортежей W2 против текущего мира → transition → атомарная мутация → MutationRecord/Fact (семантическое представление, отделённое от мутации — в L1Chronicle/interaction_history_ref, spatial invalidation, W5 epistemic). FUTURE-ЗАКОНЫ: TRANSFER(object, src, dst, carrier) — атомарный примитив W6 (не последовательность, прерываемая между тиками); ownership/territory/personal — relation-domains W5+ (OWNED_BY/CLAIMED_BY, не поля WorldObject — god-object запрещён); possession ≠ ownership ≠ territorial control (три независимые оси; holder=Goran + owner=player — моделируемо уже в W1). W-законы: W1=WHAT EXISTS, W2=WHAT IS POSSIBLE, W3=WHAT HAPPENS, W4=WHAT THE BODY CAN DO, W5+=WHAT IT MEANS.
❌ Taboo: доменный переход вызывает стор / стор содержит FSM-логику; except→REJECT (тихая конверсия доменного исключения); resolver/предикаты читают живой scene_state (только проекция снапшота); AffordanceResolver лезет в storage сам; discovery/decision мутируют объекты; исполнение в обход ревалидации precondition-кортежей; DecisionHub object-specific ветки; поля owner/territory/personal/history в WorldObject; STEAL как механика в WorldActionType; скриптовые цепочки («после кражи Горан идёт за стулом»); identity содержит локацию как семантику; спавн вне initialize_scene / перезапись сейва статикой; except:pass в тени (INV-SILENT-FAILURE); расширение SpawnMapping без мини-записи.
Status: ACTIVE (G1 shadow ✅ GREEN+ambient; G2/G3 — контракт, не реализовано)
Files: backend/app/domain/object_fsms.py (новый: FSM-таблицы §22.1 ТЗ-точные, transition_object, damage_object, TransitionResult), backend/app/services/world/world_object_store.py (+apply_transition/apply_damage, модульные импорты), backend/app/services/world/world_object_spawner.py (новый: SpawnMapping, wo_-identity, state-проекция, fault isolation), backend/app/services/world/world_objects_projection.py (новый: мост W1→W2), backend/app/services/world/affordance_shadow.py (новый: G1-тень + ShadowMetrics + env-флаг), backend/app/services/tick_orchestrator.py (врезка G1 после build_snapshot), backend/app/services/scene_state_manager.py (world_objects-корень + спавн-вызов в initialize_scene), backend/tests/test_object_fsms.py (30), backend/tests/test_world_object_spawner.py (10), backend/tests/test_affordance_shadow.py (8), scripts/w3_shadow_simple.py (GORAN β G1-харнесс, процесс-изоляция), docs/audits/ADR-O-376_IMPACT.md

`ADR-O-377` [ONTO] **Non-Blocking Intelligence — Two-Speed World (LLM ≠ условие жизни мира)**
Суть: Быстрый мир (движение/решения/память/отношения/время) НИКОГДА не ждёт медленного интеллекта (LLM: реплики/экстракции/суммаризации). LLM-результат — консультация постфактум, применяется когда готов и только если ещё актуален. Три правила: (1) запрет шлагбаума — ни один sync-путь тика не содержит блокирующего LLM-ожидания (`future.result(timeout)` в стеке `idle_tick/execute` = нарушение; TaskScheduler исполняет LLM-задачи в worker-потоках, результат — через outbox/очередь, дренируемую следующим тиком — прецедент `drain_commitment_outbox` S203.4); (2) актуальность при применении — stale-валидация (акторы живы, интент активен, тик-возраст ≤ N), протухшее отбрасывается наблюдаемо; (3) деградация без интеллекта — отсутствие LLM-ответа не останавливает быстрые следствия (сырой текст в память пишется без экстракции — доказано Фазой A). Инвариант-сопутствующий: жизненный цикл мира ≠ жизненный цикл интеллекта — сброс/рестарт мира (new_game/restart) не управляет LLM-сервером; health-чек — часть протокола восстановления (cockpit: new/restart поднимают мёртвый llama-server). Первый живой потребитель закона: `EXPERIENCE_DELTA_COMMITTED` (DeltaGate, E2.0-b) — трасса причинности для Chronicaler, observation-only.
Текущая реализация: **cockpit-форма** (terminal_cockpit.py: класс-отцепление DialogueUpdateExtractor на время wait — быстрый мир без LLM-шлагбаума; восстановление в finally). **Production-форма (план, не реализована):** перенос LLM-вызовов `_process_tasks_async` в executor + результат в outbox + stale-дренаж; зона координации — S203.4 (владелец TaskScheduler).
❌ Taboo: `future.result()` в стеке тика; мир ждёт агента; применение консультации без stale-проверки; удаление быстрых последствий при LLM-таймауте; «убрать LLM из диалогов» как реакция на медленность (меняется роль, не присутствие); bypass outbox для «быстрого» применения LLM-результата.
Status: ACTIVE (cockpit-форма; production-план открыт, IMPACT-файл создан)
Files: backend/tests/sandbox/terminal_cockpit.py (cockpit-режим wait), backend/app/services/game_loop/task_scheduler.py (production-цель, _process_tasks_async:187/362), backend/app/services/game_loop/__init__.py:1239 (execute_pending), backend/app/services/memory/delta_gate.py (первый потребитель события), docs/audits/ADR-O-377_IMPACT.md

`ADR-O-378` [ONTO] **W-Track G2 v1 — Affordance Producer-Facts: первый живой мост W2→решение (W-track, гейт G2)**
Суть: G2 из трёх гейтов W3 (G1 закрыт ADR-O-376; G3 — контракт, не реализован). Канал b1′ (вердикт PRE-FLIGHT): AffordanceSet НЕ становится параметром DecisionHub (hub остаётся object-agnostic; интерфейс под несуществующего потребителя запрещён) — продюсер превращает W2-факты в производный каузальный факт для СУЩЕСТВУЮЩЕГО канала: OpportunityContext.weapon_access (документированный DATA-стаб ADR-O-366; DEBT-OPP-PRODUCER закрыт). v1-факт weapon_access = holder==npc_id ∨ (CarrierMode.FREE ∧ IS_ADJACENT_TO): предикат переиспользуется из закрытого реестра W2 (lockstep 1.5м/FREE), W2-резолвер оружием НЕ расширяется (unknown-archetype=KeyError by design; weapon-факты не зависят от W3-FSM). WEAPON_ARCHETYPES — калибруемая policy (класс S211; расширение=мини-запись; npc_id-хардкоды запрещены). Контур: run_affordance_facts_guarded (env W3_G2_ENABLED, default OFF=no-op; отказ=пустая карта, §11) в оркестраторе ДО build_tick_state, вход=замороженный снапшот (INV-III) → TickState.affordance_facts_map (frozen, preloaded-паттерн) → NpcTickPipeline: weapon_access=факт (пустая карта=честный False=байт-идентично легаси-литералу; сигнатуры DecisionHub не менялись). GORAN β G2 (критерии Мастера: production-ON honest-zero=sanity/integration-gate; каузальное доказательство=ТОЛЬКО controlled-scene): GREEN — 7×200 изолированных профилей: honest-zero (диффы ≤ OFF/OFF-фона, ambient DEBT-QUIESCE), B-молчание (продюсер молчит без оружий), W1/W2 hits=199/199 пригодных тиков + weapon_persisted; engine-флип 0.50→0.70 (Δ=W_WEAPON=0.20, порог 0.65) юнит-доказан; steal-флип условен по will-гейту (заявлен честно; цели STEAL — W5/W6, WorldActionType не расширялся). Методология-хроника (4 честных отказа, все пойманы гвардами, ноль ложных GREEN): bootstrap-квант дочерних процессов; H1 (get_scene_state вне тика перезаливает из persistence — инъекция только через save-контур); H5 (build_game_loop читает saves_dir из ГЛОБАЛЬНЫХ settings, data_dir его НЕ задаёт — прогоны мутировали общий ROOT/saves/enigma_runtime.db = production-store; weapon-артефакт устранён перезаписью живой сессии; эволюция чужого мира невосстановима — эскалация); H6 (stale-парсинг при диагностике). Лечение: settings.saves_dir=str(temp) до build в дочернем — полная изоляция; terminal-дрейф 65→42 = артефакт общего store (канонический S237-класс восстановлен), НЕ регрессия ядра. G1-методологическая оговорка (S237): w3_shadow_simple.py имел тот же дефект — 10 G1-профилей эволюционировали один общий мир; вердикт G1 валиден (тень=ноль writers, каузально разойтись не могла), семантика изоляции — нет; все будущие A/B-харнессы обязаны патчить settings.saves_dir.
❌ Taboo: AffordanceSet как параметр DecisionHub до W5-потребителя; object-specific ветки в DecisionHub; расширение W2-реестра предикатов/SpawnMapping/WorldActionType ради weapon-фактов; второй producer per-tick факта; writers/IO/LLM в affordance_facts; чтение живой scene_state (только замороженный снапшот); A/B-харнесс без патча settings.saves_dir (мутация production-store); npc_id-хардкоды в WEAPON_ARCHETYPES; тихий except в guarded-обёртке; G3-семантика в G2-коде.
Status: ACTIVE (G2 v1 закрыт GREEN; G3 — следующий гейт)
Files: backend/app/services/world/affordance_facts.py (новый), backend/app/domain/tick.py (+affordance_facts_map), backend/app/services/pipeline_runner.py (+pass-through), backend/app/services/tick_orchestrator.py (продюсер до build_tick_state), backend/app/services/npc/npc_tick_pipeline.py (weapon_access=факт), backend/tests/test_affordance_facts.py (новый, 23), scripts/w3_g2_simple.py (GORAN β G2, изоляция), reports/w3g2_*.json + reports/w3g2_run_history/ (доказательная база), docs/audits/ADR-O-378_IMPACT.md

`ADR-O-382` [ONTO] **Intelligence Queue — Non-Blocking Dialogue Extraction (production-форма ADR-O-377; закрытие DEBT-RE-D2A)**
Суть: Разрыв сцепки «момент события ↔ момент LLM-интерпретации» для dialogue-экстракции. Единственный LLM-вызов домена — `DialogueUpdateExtractor.extract` (npc_dialogue_subscriber.py:131), исполняемый сегодня в потоке публикатора NPC_SPOKE (три контекста: pool-worker — сериализует единственный воркер на 3.3–4.3с; event-loop — RE-D2 guard → пустой DialogueUpdate = семантическая смерть player-диалогов; тик-стек fast-path S216). При `D8P_ENABLED=1` (default OFF = байт-идентично, INV-D8P-NOOP): подписчик enqueue'ит IntelligenceTask (event_id, campaign_id, speaker/listener, text, stm_before, parent_tick; task_id детерминированный, uuid4 запрещён) неблокирующе + немедленный STM-ход с placeholder intent="dialogue" (существующая семантика деградации); исполнение — FIFO через СУЩЕСТВУЮЩИЙ max_workers=1 executor-рельс (второго LLM execution domain НЕТ: multiple producers → Intelligence FIFO → TaskScheduler executor → Router serialization); результат DialogueUpdate → STALE-гейт → применение ТОЛЬКО через MemoryManager session API (Закон 4.1.2). Вердикты владельца (досье D8P_PRE_FLIGHT.md §13): Q1 = extraction decoupling ONLY (генерация/R4A не трогаются); Q2 = скользящее окно N=3 стартово (calibration, не онтология; STALE = age > N ∨ session отсутствует ∨ actor invalid/dead/out-of-world; строго >); Q3 = **D8P — time bridge, НЕ state authority** (DeltaGate не расширяется: psyche/causal state → DeltaGate, session dialogue semantics → MemoryManager; «LLM → Proposal → DeltaGate» — доктринальная интуиция, не топология этого домена; искусственный междоменный мост запрещён); Q4 = FIFO, v1 без retry (retry — отдельная политика); Class A/B/C наследуется из доктрины, не изобретается (operational mapping: A = значимый intelligence work, B = canonical по существующему правилу, C = ambient/без extraction; запрет A=player-origin как закона до канонического классификатора); Q5 = one event.id → ≤1 IntelligenceTask → ≤1 applied DialogueUpdate; lifecycle ENQUEUED/EXECUTED/APPLIED/STALE_DISCARDED/FAILED — собственный наблюдаемый реестр очереди, НЕ TaskState (O-364-taboo не трогается); история исполнения ≠ инвариант состояния. Baseline-оси (гейт ДО кода): R1 time (`wait 20` ≤10с в живом uvicorn без отцепления экстрактора; R1-зелёный НЕ опровергает D8P) × R2 semantic (loop-LLM → деградация; исторически красный — S248/DEBT-RE-D2A). Четыре границы: router.py NO TOUCH (forensic-соседи) / DeltaGate NO TOUCH / MemoryManager legal application authority / TaskScheduler pool existing execution rail. W-track-коллизия 6ad6e819 — задокументирована coordination-якорем (история не переписывается). REBASE отложен §ENIGMA-002.
❌ Taboo: `future.result` на loop-потоке; применение STALE; тихий discard; расширение DeltaGate.WHITELIST под session-семантику (междоменный мост); второй LLM execution domain / executor в обход router-сериализации; retry в v1; `A = player-origin` как архитектурный закон; uuid4 task_id; применение мимо MemoryManager session API; ON по умолчанию; «увеличить таймаут» вместо архитектуры; правка router.py/AST-tombstone соседа; слияние lifecycle IntelligenceTask с TaskState.
Status: ACTIVE (контракт ратифицирован владельцем — вердикты Q1–Q5 зафиксированы до кода; реализация НЕ начата: гейт = красный baseline R1+R2 ДО кода; D8P_ENABLED default OFF)
Files: backend/app/services/events/npc_dialogue_subscriber.py (enqueue-точка, :131), backend/app/services/game_loop/task_scheduler.py (executor-рельс, без изменения сигнатур), backend/app/services/memory/dialogue_update_extractor.py (исполняемый контракт), backend/app/services/memory/memory_manager.py (legal application authority), docs/audits/D8P_PRE_FLIGHT.md (досье + вердикты §13), docs/audits/ADR-O-382_IMPACT.md (план приёмки: SUPERBOX-сценарий d8p — по методологии causal_state_test/bc1)

`ADR-O-383` [ONTO] **Embodied Constraint — Chronic Body Axes → Feasibility (V1)**
Суть: замыкает causal edge, доказанный отсутствующим RED-оракулом GC-09B (S249): острые телесные оси (pain/shock/blood_loss) уже ветоируют действия через живой production-контур pressure_translator → ActionSpaceCompression → _score_all-feasibility (decision_hub:565); хронические оси выносливости в словарь veto не входят, availability-тракт тела не читает вовсе (ранний тракт — отдельный слепой контур, оригинальный RED-зонд — immutable evidence). V1 = расширение существующего словаря veto хроническими осями fatigue/energy (v1-минимум; hydration/sleep_pressure — CALIBRATION_CANDIDATE-оси вне v1: sleep имеет отдельный SLEEP_GUARD, семантика не доказана). Action-set = семантический прецедент acute blood_loss: FLEE/ATTACK/APPROACH/MANIPULATE; INTIMIDATE исключён — социально-поведенческое, расширение Body→Social-угла без отдельного доказательства запрещено (вердикт Мастера Q2). Форма: cap 0.3 = «существенно затруднено» (не «невозможно» — chronic, не острый incaps; прецедент blood_loss-формы). Пороги — CALIBRATION_CANDIDATE (Calibration Lab), НЕ игровые истины: ADR отвечает «может ли Body ограничивать Action», калибровка — «при каком значении и насколько». Oracle: GC-09B-full — переключение на полный compute-вызов с decision_ctx: "Original GC-09B RED remains immutable evidence of the early availability-path blind spot. The post-implementation oracle is upgraded to observe the complete production decision contour because V1 intentionally operates in the feasibility layer. The oracle upgrade is therefore an observation-scope correction, not a relaxation of the acceptance criterion." Границы (V1 НЕ утверждает): ранний availability-тракт не читает тело; motor_output_mult (orphaned derived state — §4b D-MOM, отдельная находка) не оживает; все body-оси не обязаны стать veto; sleep-семантика не решена; hard locomotion constraint не доказан. V2 (BodyStateView→availability) преждевременен — архитектурное удвоение при живом контуре.
❌ Taboo: жёсткие пороги в коде как игровые истины; INTIMIDATE в chronic-наборе; смешение с motor_output_mult-находкой; автоматическое расширение на все 4 оси без доказанной семантики; второй параллельный body-путь (V2/V3) до доказательства потребности.
Status: ACTIVE (PRE-FLIGHT 2026-09-05, вердикты Q-A/Q-B/Q-C/Q-D/Q2 Мастера; IMPLEMENT)
Files: backend/app/services/cfrm/pressure_translator.py, backend/tests/gameplay/test_gc09_body_causality.py

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
