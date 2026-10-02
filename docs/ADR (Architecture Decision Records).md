# ENIGMA ADR MASTER INDEX (Canonical Laws)

> **Статус:** ACTIVE | **Сессия:** S310 | **Инвариантов:** 49 (IPT 49/49)
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

> **Формат един (шаблон без бэктиков, чтобы парсер не породил фантомный узел):** ADR-X [TYPE] **Title** (сессии) → Суть → Taboo → Status → Files. Парсер ADR-Net читает заголовок и Files; полный Files-список и детали решения — `docs/audits/ADR-X_IMPACT.md` (перекрывает Files атласа). Полный архив решений (вкл. не развёрнутые здесь) — 159 файлов audits; конвенция IMPACT-шапок: ADR-X [STANDARD] **IMPACT** (без бэктиков — иначе парсер рождает фантомный узел ADR-X в графе). Решениям эпохи до S204 (введение Устава §11.4) IMPACT не создаётся — историческое. Различай namespace: `ADR-408` [FIX] ≠ `ADR-O-408` [ONTO]. O-379/380/381 задокументированы как DOM-законы L8.2/L14.5/L14.6 — в STANDALONE не дублируются.

`ADR-O-328/341` [ONTO] **Dual Rail Boundary Consistency** (S148/S149)
Суть: при `cross_loc_materialize` вычисление `is_boundary` основывается на `SceneChange.cause`, а не на мутированном `location_id`; `EventCompiler` гарантирует `is_boundary=True`; `MovementEngine` не создаёт `SceneChange` без `target_location_id`.
❌ Taboo: `legacy_is_boundary` из мутированного state; `cross_loc_materialize` без `target_location_id`.
Status: ACTIVE

`ADR-O-344` [ONTO] **WorldTick Temporal Ownership** (S176)
Суть: `TickOrchestrator` — единственный владелец `game_time_seconds` и `tick`; `GameLoop.idle_tick` вызывает `execute()` ровно 1 раз; множественные коммиты в `execute()` запрещены.
❌ Taboo: `GameLoop` меняет время; `TickOrchestrator` продвигает время в цикле по сценам.
Status: ACTIVE

`ADR-O-345` [DEBT] **TickState Mutation Debt** (S178)
Суть: `NpcTickPipeline.run()` нарушал ADR-TZ09-1, вызывая `StateApplicator`, мутирующий `TickState`. Устранено в S179 (ADR-O-346).
Status: ACCEPTED (DEBT) — закрыт O-346

`ADR-O-346` [ONTO] **Pure Reducer Enforcement & Hash Isolation** (S179)
Суть: `StateApplicator` удалён из `NpcTickPipeline.run()`; дельты из `DecisionResult`; хэш `TickState` изолирован от сервисных объектов (LRU-кэши); проверка слуха через `copy.deepcopy`.
❌ Taboo: возврат `StateApplicator` в Pipeline; хэширование сервисов; мутация оригинальных dict.
Status: ACTIVE

`ADR-O-347` [ONTO] **Entity Cardinality & Scene Isolation** (S180)
Суть: `all_npcs_raw` фильтруется по `location_id` ДО сборки `TickState`; NPC из других локаций исключены; устранён O(N²) дрейф.
❌ Taboo: полный `all_npcs_raw` без фильтрации; обработка NPC с чужим `location_id`.
Status: ACTIVE

`ADR-O-348` [ONTO] **Causal Ordering & Event Cardinality** (S181)
Суть: `INV-EVENT-CARDINALITY` (нет дублирования `NPC_MOVED`); `NpcTickPipeline` = Pure Reducer (структурная независимость от порядка NPC); порядок мутаций детерминирован в Фазе 8.
❌ Taboo: мутация общего состояния в цикле NPC; зависимость Фазы 8 от порядка `npc_deltas`.
Status: ACTIVE

`ADR-O-349` [ONTO] **Semantic Pipeline & Intent-Event Mapping** (S182)
Суть: `EventType` расширен (OFFER_JOB, TRADE); `IntentEventAdapter._INTENT_EVENT_MAP` — детерминированный мост; `INV-INTENT-EVENT-COMPLETENESS`.
❌ Taboo: сырые строки для `event_type`; новые `CommunicationIntent` без маппинга; `unknown`/`npc_spoke` fallback.
Status: ACTIVE

`ADR-O-350` [ONTO] **Dialogue & Travel FSM Terminality** (S183)
Суть: `INV-TRAV-TERMINALITY` (транзиты не виснут > `duration_ticks + 2`); `INV-DIALOGUE-LIVENESS` (`pending_tasks` ≤ 20).
❌ Taboo: `TraversalState` с `duration_ticks=0`; блокировка `TaskScheduler` без rate limit.
Status: ACTIVE

`ADR-O-351` [ONTO] **Replay Determinism Infrastructure** (S184)
Суть: `INV-REPLAY-DETERMINISM` (WARNING); `ReplayRecorder` подключён; полный A/B через `DriftLaboratory` (LLM-кэш); `INV-KERNEL-RNG`.
❌ Taboo: реплей без LLM-кэша; wall-clock в симуляции.
Status: ACTIVE

`ADR-O-352` [ONTO] **Save/Load Integrity** (S185)
Суть: `INV-SAVE-LOAD-INTEGRITY`; `SqlitePersistenceAdapter.load_scene_at` (не legacy `load_scene()`); проверка `tick`, `game_time_seconds`, `npc_positions`.
❌ Taboo: `load_scene()` для конкретной локации; запись мимо `SceneStateManager.commit()`.
Status: ACTIVE

`ADR-O-356` [ONTO] **Sleep as Bodily Coupling Mode** (S189)
Суть: сон = эмерджентное свойство телесной архитектуры; `CouplingResolver` (множители `external_vision_mult`, `motor_output_mult`); Sleep Onset (arousal от стимулов); `DreamSignal` → `DreamResidue` (affective_load).
❌ Taboo: скриптовые флаги `is_sleeping`; игнорирование стимулов во сне.
Status: ACTIVE

`ADR-O-359` [ONTO] **LLM Few-Shot Intent Grounding** (S205)
Суть: для стабилизации `qwen_7b` в извлечении `social_intent` запрещён хардкод keyword-matching; промпт усилен 26 Few-Shot Examples.
❌ Taboo: хардкод `if action == FLIRT: social_intent = FLIRT`; keyword hell в `intent_compressor.py`.
Status: ACTIVE
Files: `backend/app/services/input/llm_compressor_client.py`, `backend/app/services/player_cognition/legacy_bridge.py`, `backend/tests/sandbox/SUPERBOX/scenarios/semantic_torture_test.py`

`ADR-O-361` [ONTO] **Calibration Laboratory Boundary** (S213)
Суть: лаборатория — надстройка над ядром на двух границах. (1) `overlay_constants()` — identity-патч ссылок на константы (app.core.constants + все from-import биндинги загруженных модулей; патч только модуля = тихая ложь эксперимента); verify на входе/выходе, полный откат, вложенность запрещена. (2) `ObservabilityTap` — единственный пассивный наблюдатель; отказ наблюдателя не роняет тик. Per-NPC параметры — НЕ константы: npc_overrides материализуются патчем NPC JSON во временной копии кампании. Вмешательства — только InterventionEvent → TickOrchestrator.execute (ADR-TZ08-1). LLM исключён (MockProvider, environment != production). Метрическое время — детерминированная проекция тиков; wall-clock — только метаданные (§15.2). Параллельные эксперименты — изоляция процессами. Зоны: MANNEQUIN / CHAOS / ENIGMA / WARNING / BROKEN (NaN|инварианты → BROKEN). Калибруемый параметр ADR-O-360 (DIRECT_OBSERVATION_RELIABILITY < 1.0) регистрируется в схеме пресетов с его taboo.
❌ Taboo: overlay без verify; вложенные/параллельные overlay в одном процессе; фейковая реализация [PLAN]-параметров; I/O или проброс исключений из Tap в каузальный поток; мутация NPCState/констант в обход границ; wall-clock/global random в контуре runner'а; silent except в путях патча (урок S207 / DEBT-R5).
Status: ACTIVE

`ADR-FOUNDATION-FREEZE` [ONTO] **Foundation Freeze (Stage 0)** (S212)
Суть: упразднена двойная истина состояния. Whitelist `_RUNTIME_TOP_LEVEL_KEYS` удалён, мерж рекурсивный `_deep_merge`; `JsonPersistenceAdapter` bypass закрыт — всё через `atomic_commit_all`; параллельный WorldTick-путь (`phase_2_world_tick.py`) превращён в stub, `wt_dirty` удалён; `write_to_legacy` → `to_persistence_dict` (только persistence layer).
❌ Taboo: расширение whitelist'ов для починки потери поля; прямой `save_scene` в обход `atomic_commit`; использование `wt_dirty`; вызов `write_to_legacy` в runtime.
Status: ACTIVE
Files: `svc/npc/npc_loader.py`, `svc/scene_state_manager.py`, `svc/game_loop/phase_2_world_tick.py`, `svc/npc/state_applicator.py`

`ADR-WRITE-GUARD` [ONTO] **NPCState Write Guard** (S212)
Суть: guard `__setattr__` в `NPCState` — прямая мутация полей вне `StateApplicator` и авторизованных SSOT-модулей поднимает `ArchitecturalViolationError`; прямые мутации persistence layer (`npc_loader.py`, `memory_manager.py`) переведены на `object.__setattr__`.
❌ Taboo: прямое присваивание `state.field = value` вне `StateApplicator`; обход guard через `object.__setattr__` в runtime-слое (только persistence).
Status: ACTIVE
Files: `mod/npc_state.py`, `svc/npc/state_applicator.py`, `app/errors.py`

`ADR-SSOT-EPISTEMIC` [ONTO] **Epistemic SSOT & Belief Delta** (S212)
Суть: `BeliefTransitionEngine` не мутирует `state.beliefs` напрямую: `commit` генерирует `BeliefDelta` (frozen), применяется через `StateApplicator.apply_belief_delta` — единственный физический write-path; структура `Cause` для provenance.
❌ Taboo: `state.beliefs.update()` вне `apply_belief_delta`; мутация убеждений без `Cause`.
Status: ACTIVE
Files: `svc/npc/belief_transition_engine.py`, `svc/npc/state_applicator.py`, `mod/npc/beliefs.py`, `mod/psychological.py`

`ADR-SSOT-ECONOMIC` [ONTO] **Economic SSOT & Avatar Ownership** (S212)
Суть: игрок = `avatar NPC` (id="player") в `StateApplicator.apply_batch`; прямые мутации `_avatar.body_state["money"]` устранены; дельты экономики через `StateDeltas(domain=ECONOMY)`; `StateApplicator.update_relationships` — единый write-API `RelationshipStore`.
❌ Taboo: прямая мутация `_avatar.body_state["money"]`; обновление `RelationshipStore` в обход `StateApplicator`.
Status: ACTIVE
Files: `svc/npc/state_applicator.py`, `svc/game_loop/__init__.py`

`ADR-CAUSAL-SPINE` [ONTO] **Causal Spine (Stage 1)** (S212)
Суть: причинная цепочка и детерминированный реплей. `TickOrchestrator` создаёт замороженный `WorldSnapshot` (deep copy) в начале тика → `EventCompiler`; `StateApplicator.apply` требует `cause: Cause` и пишет `CausalEntry` в `causal_ledger`; `NPCState.query_ledger`/`trace_causal_chain`; `MissingProvenanceError` при отсутствии cause.
❌ Taboo: `StateApplicator.apply` без `cause`; мутация `WorldSnapshot` после создания; прямая мутация `causal_ledger`.
Status: ACTIVE
Files: `svc/tick_orchestrator.py`, `svc/npc/state_applicator.py`, `mod/npc_state.py`, `mod/psychological.py`

`ADR-EVENT-VISIBILITY` [ONTO] **Event Visibility Filter** (S212)
Суть: `PerceptualKernel.can_observe(event, distance, observer_id, target_id)` проверяет `event.radius` и `event.visibility` (public/private/whisper); `ClaimEventSubscriber` использует его вместо жёсткого `HEARING_RADIUS`.
❌ Taboo: константы радиуса вместо `event.radius`; игнорирование `event.visibility`.
Status: ACTIVE
Files: `mod/npc_state.py`, `svc/events/claim_event_subscriber.py`

`ADR-O-364` [ONTO] **LLM Task Execution Boundary — Strict Reconstruction, Causal Backpressure & Per-Task Timeout** (S223-эра)
Суть: восстановление контракта ADR-O-343 для пула LLM-задач. (1) Строгая реконструкция: canonical failure → FAILED/drop + structured diagnostic, никогда raw dict/ambient. (2) Causal Backpressure: ambient overflow → DROP, canonical overflow → PRESERVE (вытесняет ambient); деградация canonical → ambient запрещена; causal class — из `task_type`, не `priority`. (3) Per-Task Timeout: `threading.Timer` вызывает `_abort_generation()` у router — освобождение воркера `ThreadPoolExecutor(max_workers=1)` без блокировки главного потока.
❌ Taboo: silent fallback на `payload_dict`; drop canonical при переполнении; деградация canonical до ambient; `priority` (int) для causal-классификации; `future.result(timeout)` без отмены реального LLM-запроса; `TaskState.FAILED` без отдельного ADR.
Status: ACTIVE
Files: `backend/app/services/game_loop/task_scheduler.py`, `backend/app/services/execution/dialogue_queue.py`, `backend/app/services/execution/dialogue_executor.py`

`ADR-O-363` [ONTO] **Unified Behavioral Ownership — Commitment Registry & Arbitration** (S215/S216; Stage 2A S203.1–S203.3)
Суть: один NPC — один активный поведенческий владелец; любая система порождает candidate, материализует только executor под активным commitment. Реестр `scene_state["active_commitments"]` (писатель — `CommitmentRegistry`) + `commitment_history` (cap 10/NPC) + `commitment_ordinals` (монотонные). Семантики COMMIT/CONTINUE/REJECT/INTERRUPT; INTERRUPT — контракт через `interrupt_traversal` (атомарен на двух рельсах, причины из закрытого реестра, расширение = мини-ADR); `commitment_id = H(tick, npc_id, action, ordinal)` — uuid4 запрещён; `cause ≠ interrupt_reason ≠ fail_reason`; три несводимых FSM-слоя (Task/Traversal/Commitment); SSM не классифицирует behavioral-семантику (cause verbatim, пустой → `UNKNOWN_LEGACY_SOURCE`); зеркало материализации ровно в ДВУХ точках (ProjectionEngine._apply_position primary / SSM.apply_change fallback); arbiter read-only (PASS|REJECT(DUPLICATE/INCUMBENT)), два invocation points (simulation.py Гейт① / movement_bridge.py Гейт②); `has_behavioral_owner` — строго проекция реестра; SSM.gc_traversals — единственный GC-владелец (INV-TRAV-ZOMBIE).
❌ Taboo: мутация реестра вне Registry; uuid4-ID; INTERRUPTED без причины; переиспользование/уменьшение ordinal; REJECT в реестре; слияние трёх FSM; третье зеркало/третий invocation point; auto-supersede в зеркалах; запись реестра из async-воркера; обход traversal-FSM без зеркала.
Status: ACTIVE (S203.1–S203.3 закрыты; A/B: SUPERSEDED→0, COMPLETED→100%; флаги COMMITMENT_REGISTRY_ENABLED/ARBITER_ENFORCEMENT/TRAVERSAL_OWNERSHIP_ENFORCEMENT default OFF)
Files (full: ADR-O-363_IMPACT.md): `dom/action_commitment.py`, `svc/action/commitment_registry.py`, `svc/action/commitment_arbiter.py`

`ADR-O-365` [ONTO] **Task/Windup/Sleep Ownership + Arbiter-INTERRUPT** (S223; Stage 2A S203.4)
Суть: владение распространено на всех исполнителей (dialogue-task — только canonical-класс `produces_claim ∨ has_proposition`, windup, sleep). Четвёртая семантика арбитра: INTERRUPT(PRIORITY_SUPERSEDE) при `candidate_priority > incumbent + INTERRUPT_THRESHOLD(=3)`; приоритет — доменная policy (`s203.4.v1`: EXPLORATION=1…WINDOWED=7), хранится с `PRIORITY_POLICY_VERSION`, в commitment_id не входит; REJECT(INCUMBENT_PROTECTED) ≠ INCUMBENT; терминальные зеркала task — через outbox (async-воркер никогда не пишет реестр; дренаж sync в двух точках); сон — state-based reconciliation после Фазы 0.6; terminal-mapping полный (CANCELLED/EXPIRED/FAILED(TASK_ERROR|TASK_CRASH|BLOCKED_TIMEOUT)/INTERRUPTED(TASK_VANISHED|WINDUP_STALE_INTENT)); `fail_reason` — симметрия закона №7; `domain/tasks.py` удалён (uuid4 в фабрике task_id — причина смерти, shim запрещён); Н-40: `_windup_registry`/`_pending_intents` → scene_state.
❌ Taboo: новый ownership-источник кроме active_commitments; executor-fallback в `has_behavioral_owner`; priority в commitment_id; смена PRIORITY_POLICY_VERSION без мини-ADR; auto-supersede в зеркалах; запись реестра из async-воркера; compatibility shim для domain/tasks.py; EXECUTING-uninterruptible как онтология; emergency-причины без живого продюсера.
Status: ACTIVE (контракт утверждён Мастером, вердикты D-1…D-9; флаги S203.4_OWNERSHIP_MIRRORS / S203.4_ARBITER_INTERRUPT default OFF)
Files (full: ADR-O-365_IMPACT.md): `dom/action_priority.py`, `svc/action/commitment_arbiter.py`, `svc/game_loop/task_scheduler.py`

`ADR-O-367` [ONTO] **Intervention Consequence Routing — Structured Semantics Branch** (S220; Lab M1)
Суть: вмешательства с каузальными дельтами (semantic_action ∈ HELP/BLACKMAIL/ACCUSE) маршрутизируются в `_process_player_action` на ActionConsequenceCompiler — тот же production write-path, что DM-конвейер. Ядро текст не парсит (L4.1): семантика приходит структурированной в InterventionEvent.payload; `action_id = f"interv:{tick}:{ACTION}:{target}"` — идемпотентность + replay; кампания лаборатории — init_campaign (зеркало P-MVP-1); диспетчеризация с DM-путём взаимоисключающая; расширение семантик — мини-запись на действие (прецедент O-362).
❌ Taboo: парсинг текста в ядре; вмешательства без структурной семантики; вызов компилятора мимо `_process_player_action`; недетерминированный action_id; init_campaign-обход при ожидаемых дельтах SSOT.
Status: ACTIVE (M1/S220; runtime: maid_lusya→player trust None→20.0)
Files: `backend/app/services/tick_orchestrator.py`, `backend/app/services/calibration/experiment_runner.py`, `backend/app/contracts/interventions.py`, `backend/tests/calibration_lab/test_m1_trust_intervention.py`

`ADR-O-368` [ONTO] **Calibration Lab Frontend Isolation Exception (Dev Enclave)** (S220)
Суть: Calibration Lab (frontend/map_editor/ui/lab_screen.py, Вариант B) — изолированный developer enclave с ограниченным исключением из frontend isolation policy (Устав §1.1) только для экспериментального чтения SSOT через прямые импорты (ExperimentRunner start/step/stop); точечный allowlist в `scripts/lint_frontend_isolation.py`. Обоснование (S220, N2): лаборатория — потребитель production causal spine (O-366), «не переписывать causal architecture ради лаборатории» (правило M1).
❌ Taboo: расширение allowlist без нового ADR; импорты backend в production UI; запись в ядро из lab_screen в обход ExperimentRunner/InterventionEvent (границы O-361 в силе).
Status: ACTIVE (S220, N2 APPROVED; IMPACT: отсутствует — создать stub)
Files: `scripts/lint_frontend_isolation.py`, `frontend/map_editor/ui/lab_screen.py`, `backend/tests/IPT.py`

`ADR-O-369` [ONTO] **Relationship Engine — онтологический контракт фазы A (M0)** (S224)
Суть: ТЗ-RE-01 v1.9 зафиксирован как контракт (`architecture/relationship_engine.yaml`): онтологическая классификация §5.0 (классы I–IV + TOMBSTONE + FORBIDDEN), 8 компонентов §4.1, владельцы/write-политика, запреты №1–35 с картой enforcement, tombstone-отрицательная онтология (Received, Bond, Infatuation, g, k_up/k_down/τ_n, η_s, β/T_half, H_i/ρ, σ, DeprivationHorizon), мораторий №35.2 (Class IV readout влюблённости до Р18), COLLISION-решение frustration (владелец NeedLevel.frustration; §5.2-поле = read-only проекция). Рантайм не менялся. Enforcement — `scripts/lint_relationship_engine.py` (CI + pre-commit): канонический набор узлов закрыт, scoped-греп запрещённых имён, запретные рёбра; контент-канон config/ вне сканирования. YAML ≠ второй источник истины: формулы §6 в контракт не переносятся.
❌ Taboo: воскрешение tombstone-сущностей под любыми именами (вкл. falling_in_love_score, romantic_attention, chemistry); формулы/коэффициенты §6 в yaml; расширение узлов без вердикта GPT; второй writer/store домена RE; удаление имён из forbidden-ядра линтера.
Status: ACTIVE (M0 закрыт; фазы B–K — по гейтам §10 ТЗ)
Files: `architecture/relationship_engine.yaml`, `scripts/lint_relationship_engine.py`, `docs/audits/ADR-O-369_IMPACT.md`

`ADR-O-370` [ONTO] **Relationship Engine — Phase B / M1a: субстрат потребностей** (S228)
Суть: контракты NeedSlot/NeedLevel (три раздельных аккумулятора: давление/сатурация/фрустрация)/PreferenceModel/HardConstraint + `RelationshipStateStore` над `scene_state["relationship_state"]` (статический сервис, прецедент CommitmentRegistry; persistence — только atomic_commit). Слоты sexual+intimacy; attachment отсутствует добровольно (гейты АТ-1..3). Красный инвариант M1a: создано МЕСТО ХРАНЕНИЯ, не механизм изменения — стор не вызывается рантаймом, поведение тика байтово идентично. Write-цепочка: `StateApplicator.update_needs` (единственный runtime-writer, caller-guard) → стор → scene_state; чтение — только frozen DTO, не мутирует scene_state; повреждённая структура — ContractValidationError.
❌ Taboo: расширение реестра need_id без вердикта GPT+ADR; второй writer/персистентный кэш/mutable read-проекции; собственный persistence-path; поля RE в NPCState; конфиг-авторинг needs до фазы M.
Status: ACTIVE (M1a; M1b — отдельный ADR-цикл O-371-серия)
Files: `backend/app/domain/relationship_contracts.py`, `backend/app/services/social/relationship_state_store.py`, `backend/app/services/npc/state_applicator.py`, `backend/tests/test_relationship_state_store.py`

`ADR-O-371` [ONTO] **W1 Spatial Topology — Object Relation Substrate** (S230)
Суть: реляционная нормализация мировой онтологии: 7 отношений canonical single-side на WorldObject (LOCATED_AT/HELD_BY/OCCUPIED_BY/CONTAINED_BY/SUPPORTED_BY/ATTACHED_TO/USED_BY); CarrierMode (FREE|HELD|CONTAINED|ATTACHED) — онтология авторитета позиции (позиция авторитетна только в FREE); матрица конфликтов сверх carrier-режимов — КАЛИБРУЕМАЯ ПОЛИТИКА, не онтология (вердикт S230). SSOT — `scene_state["world_objects"]`; `WorldObjectStore` — stateless фасад: read без lazy-init, повреждённая структура — громкий OntologyViolationError, write — только типизированные операции (spawn/establish/release/relocate), generic update(**changes) отсутствует by construction; auto-release запрещён; межобъектная валидация в сторе. Persistence — только через atomic_commit_all; снапшот — deepcopy-поле `WorldSnapshot.world_objects` (паттерн S215). W0 CONTRACT CORRECTION: topology_relations/containment stored/affordances stored/WorldObjectRegistry удалены (unconsumed PoC). Runtime-writers: 0 → первый — G3 (ADR-O-410).
❌ Taboo: dict-хирургия world_objects вне стора; второй источник объектов; presentation-поля в WorldObject; auto-release; policy-правила в W1; uuid4 object_id; собственный persistence-path; физика переноса в W1; подключение к TickOrchestrator/DecisionHub до causal writer.
Status: ACTIVE (S230; IPT 45/45, pytest 30/30, DoD GREEN)
Files (full: ADR-O-371_IMPACT.md): `backend/app/domain/world_object.py`, `backend/app/services/world/world_object_store.py`, `architecture/world.yaml`

`ADR-O-372` [ONTO] **W2 Affordances — Semantic Action Resolution** (S232)
Суть: pure resolver `(WorldObject, BodyStateView, npc_position) → SemanticAction[]` — действия с выполненными предусловиями СЕЙЧАС; precondition-кортежи сохранены на каждом действии для W3-ревалидации (скрытые гейты резолвера запрещены). `WorldActionType` — закрытый enum (19 значений; расширение = мини-ADR); INSERT_ITEM/REMOVE_ITEM зарезервированы; реестр предикатов v1 закрыт (7: IS_ALIVE/IS_CONSCIOUS/IS_CAPABLE — делегация vital_state ADR-123, STATE_IS, IS_ADJACENT_TO ≤1.5 м только в FREE, HOLDER_IS, OCCUPANT_IS). `BodyStateView` — frozen read-model (falsy body → ValueError). effective_state: door/container — state-поле FSM, chair — деривация (BROKEN>HELD>OCCUPIED>AVAILABLE). Пара OPEN+CLOSE в состоянии OPEN — для FSM-архетипов с обоими переходами (легальность решает W3). Substrate-only: 0 runtime-потребителей до G2.
❌ Taboo: stored affordances; LLM/IO/мутации в resolver; расширение enum/реестра предикатов без мини-ADR; скрытые гейты вне кортежей; чтение body_state мимо BodyStateView; @dataclass поверх enum-классов (инцидент S232: zero-field __eq__ схлопывает множества).
Status: ACTIVE (substrate-only; wiring — G2/O-378, writer — G3/O-410)
Files (full: ADR-O-372_IMPACT.md): `backend/app/domain/semantic_action.py`, `backend/app/services/world/affordance_resolver.py`, `backend/app/domain/body_state_view.py`

`ADR-O-373` [ONTO] **Body Idle-Projection Contract + Fatigue Consolidation + Delta-Policy Enum Unification** (S233; S2B.5)
Суть: (1) FLAT-контракт Phase 0.5: `NPCStateSnapshot` расширен плоскими READ-ONLY полями BodyEngine (velocity/activity/coupling_mode/body_mass); до S2B.5 подсистемы 2B.1–2B.4 были production-мёртвыми (unit-фикстуры = «объекты мечты»). (2) ONE POLICY TYPE / ONE REGISTRY / ONE ENUM IDENTITY: дубль ReductionPolicy в dto.py удалён (владелец models/state_delta.py); Enum Identity Split ломал policy-сравнение → PHYSIOLOGY молча падала в last-wins. PHYSICS_COMPOSITE = pass-through: физиологические дельты не редуцируются, применяются последовательно единым StateApplicator; generic additive-fallback для PhysiologyPayload запрещён. (3) Fatigue: BodyEngine — единственная per-tick проекция (two-way износ, инверсия energy; износ медленнее топлива — отдельный инвариант); legacy-писатели dormant; два payload-продюсера допустимы, два per-tick engines — НЕТ.
❌ Taboo: вторая per-tick fatigue-проекция; прямые записи body_state["fatigue"] мимо StateApplicator; duplicate enum/registry; generic PhysiologyPayload-ветка в _reduce_additive; raw-фикстуры BodyEngine в тестах; mutable-ссылки на body_state в снапшоте.
Status: ACTIVE (поведенческий гейт: n=6, e/h/nut≠0, fat=+0.075, snap_fat 0→3.0 монотонно)
Files (full: ADR-O-373_IMPACT.md): `backend/app/models/state_delta.py`, `backend/app/services/body/body_engine.py`, `backend/app/services/tick_utils.py`

`ADR-O-374` [ONTO] **Canonical Sleep-Coupling Predicates + Sleep Inversion Diagnostics** (S235; S2B.6 Phase A)
Суть: `is_sleep_coupling` в domain/body.py — единственный источник семантики «coupling-режим = физиологический сон» (SLEEP/DEEP_SLEEP/REM; DROWSY — не сон). Причина: string-identity split — продюсер писал литералы enum, потребители сверялись с фантомными "SLEEPING" из doc-drift → сон-физиология ×3 и sleep-ownership были мертвы с рождения (S233-гейт фикстурно-зелёный = объект мечты). Диагностика инверсии двух снов (поведенческий сон без ×3; бессонница с ×3 на ногах) — зонды отреверсированы, отчёты reports/DIAG_S2B6_*. Гварды-вечники (truth-table, membership-pin, grep).
❌ Taboo: строковые свитчи по coupling-литералам вне domain/body.py; фантомные литералы "SLEEPING"/"AWAKE" в коде/фикстурах/доках; обход is_sleep_coupling; второй per-tick physiological engine; калибровка sleep-констант до DUAL-TIME; fatigue→sleep_pressure как прямой мультипликатор.
Status: ACTIVE
Files (full: ADR-O-374_IMPACT.md): `backend/app/domain/body.py`, `backend/app/services/body/body_engine.py`

`ADR-O-375` [ONTO] **Physiological Sleep Onset Machine** (S236; S2B.6 Phase B)
Суть: сон = цепочка физических фактов: schedule-intent → `SleepOnsetEligibility` (чистое условие: intent ∧ NodeRole.BED ∧ settled ∧ alive ∧ ¬GAP9-блоки; не пишет состояние) → ФАКТ `body_state["sleep_onset_tick"]` (int|None, строго is not None; единственный писатель — SleepLifecycleService Фазы 0.6) → coupling-сон-семейство (двусторонний гейт: без факта потолок DROWSY; факт жив → переживает decay). Eligibility ≠ fact; no-BED ≠ resting. `wake_duration` — незажатый homeostatic аккумулятор; sleep_pressure = bounded derived: base × fatigue-модулятор (1 + fatigue/100×COEFF, v1=1.0) — НЕ sp+=fatigue, оси независимы. Wake: arousal-гейт ∨ intent-withdrawal; sleep_end-SSOT нет. Доставка тел к кроватям — эскалация (elig=True=0/1200 при верифицированной машине).
❌ Taboo: второй писатель sleep_onset_tick/wake_duration; вывод факта из coupling (обратная причинность); сон-режимы без факта; routine-строка как источник; калибровка до DUAL-TIME и доставки; прямая связь sp+=fatigue.
Status: ACTIVE
Files (full: ADR-O-375_IMPACT.md): `backend/app/domain/body.py`, `backend/app/services/npc/sleep_onset_resolver.py`, `backend/app/services/npc/sleep_lifecycle_service.py`

`ADR-O-376` [ONTO] **W3 Object FSM — Execution Substrate + Shadow Discovery Gate** (S237)
Суть: W3 = «ЧТО ПРОИЗОШЛО». Домен: `transition_object`/`damage_object` — чистые FSM-переходы; стор: `apply_transition`/`apply_damage` — коммит только на PASS («FSM определяет семантический переход; Store — где он становится World State»). `TransitionResult` (PASS|NO_OP|REJECT + reason, не bool) несёт old_state + topology_effect. OPEN-in-OPEN = легальный NO_OP; chair — политика над операциями отношений W1, не state-хирургия; MOVED = relocate (legacy); bed — честный UNKNOWN_ARCHETYPE до W4; damage ≥1.0 → терминал архетипа (container DESTROYED). Спавнер: editor objects → SpawnMapping (door+door_transition→door; chair; расширение = мини-запись), `object_id = wo_<md5(campaign:spawn_loc:editor_id)>` — IDENTITY ≠ LOCATION, uuid4 запрещён; только initialize_scene (сейв выигрывает). G1 shadow: discovery-тень AffordanceResolver после заморозки снапшота, до решений; `W3_SHADOW_ENABLED` default OFF; ноль writers/decisions/events. Контракт G2 (закрыт O-378) / G3 (закрыт O-410): STEAL = W5-интерпретация TAKE, WorldActionType не расширяется; TRANSFER — атомарный примитив W6; ownership/territory — relation-domains W5+, не поля (god-object запрещён). W-законы: W1=WHAT EXISTS, W2=WHAT IS POSSIBLE, W3=WHAT HAPPENS, W4=WHAT THE BODY CAN DO, W5+=WHAT IT MEANS.
❌ Taboo: доменный переход вызывает стор; except→REJECT (INV-SILENT-FAILURE); resolver читает живой scene_state; исполнение в обход ревалидации precondition-кортежей; DecisionHub object-specific ветки; поля owner/territory в WorldObject; STEAL как механика enum; identity содержит локацию; спавн вне initialize_scene; except:pass в тени.
Status: ACTIVE (G1 ✅ GREEN+ambient; G2 ✅ O-378; G3 ✅ O-410; мини-запись Living Activity EAT: SpawnMapping+food_portion, WorldActionType не расширялся)
Files (full: ADR-O-376_IMPACT.md): `backend/app/domain/object_fsms.py`, `backend/app/services/world/world_object_store.py`, `backend/app/services/world/world_object_spawner.py`

`ADR-O-377` [ONTO] **Non-Blocking Intelligence — Two-Speed World (LLM ≠ условие жизни мира)** (S238)
Суть: быстрый мир (движение/решения/память/отношения/время) НИКОГДА не ждёт медленного интеллекта. Три правила: (1) запрет шлагбаума — ни один sync-путь тика не содержит блокирующего LLM-ожидания (`future.result(timeout)` в стеке `idle_tick/execute` = нарушение); (2) актуальность при применении — stale-валидация (акторы живы, интент активен, тик-возраст ≤ N), протухшее отбрасывается наблюдаемо; (3) деградация без интеллекта — отсутствие LLM-ответа не останавливает быстрые следствия. Жизненный цикл мира ≠ жизненный цикл интеллекта: new_game/restart не управляет LLM-сервером, health-чек — часть протокола восстановления. Первый живой потребитель: `EXPERIENCE_DELTA_COMMITTED` (DeltaGate, observation-only).
❌ Taboo: `future.result()` в стеке тика; мир ждёт агента; применение консультации без stale-проверки; удаление быстрых последствий при LLM-таймауте; bypass outbox для «быстрого» применения LLM-результата.
Status: ACTIVE (cockpit-форма; production-форма реализована — ADR-O-382, S251)
Files (full: ADR-O-377_IMPACT.md): `backend/tests/sandbox/terminal_cockpit.py`, `backend/app/services/game_loop/task_scheduler.py`, `backend/app/services/memory/delta_gate.py`

`ADR-O-378` [ONTO] **W-Track G2 — Affordance Producer-Facts: первый живой мост W2→решение** (S239)
Суть: AffordanceSet НЕ параметр DecisionHub (hub object-agnostic; интерфейс под несуществующего потребителя запрещён) — продюсер превращает W2-факты в производный каузальный факт для СУЩЕСТВУЮЩЕГО канала: `OpportunityContext.weapon_access` (закрытие DEBT-OPP-PRODUCER). Факт = `holder==npc_id ∨ (CarrierMode.FREE ∧ IS_ADJACENT_TO)` — предикат из закрытого реестра W2; WEAPON_ARCHETYPES — калибруемая policy (расширение = мини-запись, npc_id-хардкоды запрещены). Контур: guarded-продюсер (`W3_G2_ENABLED` default OFF = no-op) → `TickState.affordance_facts_map` (frozen) → pipeline: пустая карта = честный False, байт-идентично легаси; сигнатуры DecisionHub не менялись. GORAN β G2 GREEN (honest-zero; engine-флип 0.50→0.70 юнит-доказан). Закон-урок (инцидент H5): все A/B-харнессы обязаны патчить `settings.saves_dir` до `build_game_loop` — иначе мутация production-store.
❌ Taboo: AffordanceSet как параметр DecisionHub до W5-потребителя; object-specific ветки в DecisionHub; расширение реестров W2 ради weapon-фактов; writers/IO/LLM в affordance_facts; чтение живой scene_state (только замороженный снапшот); A/B-харнесс без патча saves_dir; npc_id-хардкоды в WEAPON_ARCHETYPES; G3-семантика в G2-коде.
Status: ACTIVE (G2 ✅ GREEN; G3 закрыт — ADR-O-410)
Files (full: ADR-O-378_IMPACT.md): `backend/app/services/world/affordance_facts.py`, `backend/app/services/tick_orchestrator.py`, `scripts/w3_g2_simple.py`

`ADR-O-382` [ONTO] **Intelligence Queue — Non-Blocking Dialogue Extraction (production-форма ADR-O-377)** (S251; закрытие DEBT-RE-D2A)
Суть: LLM-экстракция диалога декомпозирована от момента события. При `D8P_ENABLED=1` (default OFF = байт-идентично, INV-D8P-NOOP): подписчик NPC_SPOKE enqueue'ит IntelligenceTask (task_id детерминированный, uuid4 запрещён) неблокирующе + немедленный STM-ход с placeholder intent="dialogue" (существующая семантика деградации); исполнение — FIFO через существующий executor-рельс TaskScheduler (второго LLM execution domain НЕТ); результат → STALE-гейт → применение ТОЛЬКО через MemoryManager session API (Закон 4.1.2). Вердикты владельца (D8P_PRE_FLIGHT §13): extraction decoupling ONLY (генерация/R4A не трогаются); окно STALE N=3 — calibration; D8P = time bridge, НЕ state authority — DeltaGate не расширяется (session-семантика → MemoryManager, междоменный мост запрещён); FIFO без retry в v1; one event.id → ≤1 task → ≤1 applied; lifecycle ENQUEUED/EXECUTED/APPLIED/STALE_DISCARDED/FAILED — собственный наблюдаемый реестр, НЕ TaskState.
❌ Taboo: `future.result` на loop-потоке; применение STALE; тихий discard; расширение DeltaGate.WHITELIST под session-семантику; второй LLM execution domain / executor в обход router-сериализации; retry в v1; uuid4 task_id; применение мимо MemoryManager session API; ON по умолчанию; правка router.py; слияние lifecycle IntelligenceTask с TaskState.
Status: ACTIVE (S251: P2-ПОСЛЕ 8.37с при baseline 110.96с; RE-D2 23→0; d8p_intelligence_test 23/23)
Files (full: ADR-O-382_IMPACT.md): `backend/app/services/events/npc_dialogue_subscriber.py`, `backend/app/services/game_loop/task_scheduler.py`, `backend/app/services/memory/memory_manager.py`

`ADR-O-383` [ONTO] **Embodied Constraint — Chronic Body Axes → Feasibility (V1)** (S250)
Суть: замыкает causal edge, доказанный RED-оракулом GC-09B (S249): острые оси (pain/shock/blood_loss) уже ветоируют через production-контур pressure_translator → ActionSpaceCompression → feasibility; хронические оси выносливости в словарь veto не входили. V1 = расширение словаря veto осями fatigue/energy (v1-минимум; hydration/sleep_pressure — CALIBRATION_CANDIDATE вне v1: sleep имеет отдельный SLEEP_GUARD, семантика не доказана). Action-set = семантический прецедент acute blood_loss: FLEE/ATTACK/APPROACH/MANIPULATE; INTIMIDATE исключён — расширение Body→Social-угла без отдельного доказательства запрещено (Q2). Cap 0.3 = «существенно затруднено», не «невозможно» (chronic, не острый incaps). Пороги — CALIBRATION_CANDIDATE (Calibration Lab), НЕ игровые истины: ADR отвечает «может ли Body ограничивать Action», калибровка — «при каком значении и насколько». Границы V1: availability-тракт не читает тело; motor_output_mult (D-MOM) не оживает; sleep-семантика не решена; V2 (BodyStateView→availability) преждевременен — удвоение при живом контуре.
❌ Taboo: жёсткие пороги в коде как игровые истины; INTIMIDATE в chronic-наборе; смешение с motor_output_mult-находкой; авторасширение на все оси без доказанной семантики; второй параллельный body-путь (V2/V3).
Status: ACTIVE (PRE-FLIGHT 2026-09-05, вердикты Q-A/Q-B/Q-C/Q-D/Q2; IMPLEMENT — RED→V1→GREEN за сессию)
Files: `backend/app/services/cfrm/pressure_translator.py`, `backend/tests/gameplay/test_gc09_body_causality.py` (IMPACT: отсутствует — создать stub)

`ADR-O-384` [ONTO] **Living Activity — Desire/Activity/Outcome онтология + срез EAT** (S252)
Суть: замыкание разрывов NEED→…→WORLD CHANGE; флаги default OFF = байт-идентичный no-op. Сущности: Desire (персистентный L2.8, multi-cause provenance L-M1: Tuple[(source,weight)]), ActivityState (факт с причиной+адресом по рождению, resume-токен step_index+step_started_tick), SuccessCriterion (predicate в Goal, не строка). Компоненты: desire_generator (Фаза 0, DESIRES_ENABLED), activity_catalog (L-A2 Catalog Freedom; SLEEP не входит — телесный эталон), activity_lifecycle_service (Фаза 0.7, обобщение сонного шаблона: settled-eligibility → MOVE по рельсу ДО Гейта① → G3 W2-ревалидация предусловий → типизированные мутации стора → терминал damage-O6 + явный release + outcome-факт). Насыщение: сброс ТОЛЬКО терминалом (NO_LABEL_SATISFACTION); гейт living_activity_owns_needs = ОБА флага парой (частичное включение = спираль голода); подавление двойного трека legacy_need_suppressed. Законы Мастера: L-A1 Role Non-Authority, L-A2 Catalog Freedom, L-A3 Slow Strategy Loop, L-A4 StrategyProjector Diagnostic Only, L-A5 BC-1 Facts Never Commands; food_portion — мини-запись ADR-O-376 (потребление = BODY_ACTION, WorldActionType не расширялся).
❌ Taboo: ярлык как источник насыщения; четвёртый реестр active_activities; CONSUME/GIVE в WorldActionType без мини-ADR; object-хирургия мимо WorldObjectStore; AffordanceSet как параметр DecisionHub; флаги по-одиночке; desires как L3-эфемер; uuid4; ручной сброс needs вне терминала.
Status: ACTIVE (EAT 12/12; срезы WORK ✅ O-391, SOCIAL ✅ O-396)
Files (full: ADR-O-384_IMPACT.md): `backend/app/domain/desire.py`, `backend/app/domain/activity.py`, `backend/app/services/npc/activity_lifecycle_service.py`

`ADR-O-385` [ONTO] **Speech-Tube Sanitation — SELF_TALK_SENTINEL + SpeechExposure Contract** (S253)
Суть: четыре уровня речи (private-когниция ≠ экстернализованный солилоквий ≠ whisper ≠ public). (1) SELF_TALK_SENTINEL: солилоквий = слышимое бормотание без агента-адресата — фантом не имеет STM/рёбер/L1; подслушивание легально. (2) NpcDialogueSubscriber — седьмой rel-write-маршрут замкнут на RelationshipWriteGate. (3) Мембрана адресата can_obobserve → can_observe (S192-паритет, fail-open). (4) exposure_radius() SSOT-лестница: private 0 / secret 1.5 / whisper 3 / normal 6 / loud 10 / shout 15; 999-дефолт ambient запрещён.
❌ Taboo: новый dialogue-субстрат (§ENIGMA-002); radius-хардкод у продюсеров NPC_SPOKE; прямые .update() отношений мимо гейта в speech-трубе; agent-обработка сентинела-адресата; расширение лестницы без мини-ADR.
Status: ACTIVE
Files (full: ADR-O-385_IMPACT.md): `backend/app/domain/communication.py`, `backend/app/services/events/npc_dialogue_subscriber.py`

`ADR-O-387` [ONTO] **Dialogue Integrity Axes — Liveness/Exposure/Journal/Pacing** (S254; GC-DIALOGUE-01 Stage-1)
Суть: четыре оси честности речевого контура player↔NPC. (1) LIVENESS: терминал «owner DEAD → EXPIRED» канонического ADR-O-365-мэппинга доведён до диалоговых задач в 4 точках диспетчеризации + worker-гейт (последняя точка перед executor.execute — покрывает in-flight и будущие dispatch-точки by construction); провайдер живости — LifeEngine-снапшот; fail-open S198-паритет; посмертная реплика не материализуется. (2) EXPOSURE AT MATERIALIZATION: NPC_SPOKE/COMMUNICATION_CLAIM несут radius = exposure_radius(semantic) — до фикса вся production-речь жила на хардкоде 10.0 «loud» при зелёной батарее. (3) PLAYER JOURNAL: порог подслушивания из event.radius, fail-open 8.0; private 0 — никогда. (4) TAB PACING: фокус диалога = presentation-режим внимания (опрос ÷4, floor 125 мс; фриз 30с удалён); тики/RNG/реплей-детерминизм инвариантны pacing'у by construction (ADR-O-344, §14).
❌ Taboo: новый dialogue-субстрат; liveness-гейт с собственным реестром смерти (только канонический DEAD→EXPIRED); radius-хардкод у продюсеров речи; «диалог-режим симуляции»; self-relevance/secret-семантика в речи (M2/D); подделка тестами (анти-подделка: срезы «после речи» + target_id=player).
Status: ACTIVE (сценарий GREEN, micro 26/26, IPT 45/45, GORAN β + vertical GREEN; живая-сессия пп.1–2 — чеклист за Мастером)
Files (full: ADR-O-387_IMPACT.md): `backend/app/services/game_loop/task_scheduler.py`, `backend/app/services/execution/dialogue_materializer.py`, `backend/tests/micro/test_dialogue_liveness_gate.py`

`ADR-O-388` [ONTO] **Player Speech Claims — Testimony-Симметрия player→NPC** (S255; GC-SOCIAL-01 Stage-1.5)
Суть: речь игрока = локальное социальное событие мира, не UI-окно. G1-мост: путь «уста игрока → убеждение NPC» отсутствовал (подписчик PLAYER_SPOKE был только L2-памятью) — `ClaimEventSubscriber.on_player_spoke` = зеркало on_npc_spoke: PLAYER_SPOKE + DM-вектор (semantic_action/target_reference/target_id из intent_resolution живого DM) → Proposition (ACCUSE→STOLE subject=target / THREATEN→ATTACKED subject=player с S202-origin-переносом источника звука на жертву / HELP→HELPED) → делегация on_claim_event — мембрана унаследована целиком (distance + can_observe по event.radius). Без DM-вектора — no-op: Stage-1.5 НЕ понимает речь (граница M2/D).
❌ Taboo: парсинг смысла реплики вне DM-вектора; self-relevance/«речь обо мне»-детекция; второй belief-путь мимо ClaimEventSubscriber/мембраны; инъекция belief/event/intent NPC-стороне; поведенческий хардкод реакции свидетеля (интент-семейство или задокументированный top-3 — фальсифицируемо, не скрипт); «если рядом X → вызвать X».
Status: ACTIVE (замок 4/4, батарея 30/30, S1/S3 интеграционно; S2.6–8 end-to-end = живая сессия; долги: DM-ACCUSE недетерминизм при живом LLM — решение Мастера; read_trust=None в harness-мире — V2-бутстрап пар player)
Files (full: ADR-O-388_IMPACT.md): `backend/app/services/events/claim_event_subscriber.py`, `backend/tests/micro/test_player_speech_claim.py`

`ADR-O-389` [ONTO] **NPC Interrupt & Intent Substrate — Will-Persistence + Task Stale-Intent Gate** (S257; GC-INTERRUPT-01)
Суть: (1) СУБСТРАТ (закрытие DEBT-INTENT-SOURCE): решение NPC — долговечное состояние по всему рельсу: DecisionHub.compute → StateDeltas(intent, intent_tick) (решение есть даже без дельт) → intent-only-провод в delta_buffer → apply_batch → intent-ветка _apply_deltas (инерция: смена → мягкий сброс 30% прогресса, сохранение → инкремент) → NPCState.intent (SSOT, WRITE-GUARD) → полный 6-полевой persistence-блок (частичная проекция запрещена — ложная семантика «вечно только что сменился») → round-trip. (2) ГЕЙТ: четвёртая причина смерти диалоговой задачи — воля владельца: _owner_intent_flees (зеркало _owner_is_dead; fail-open S198-паритет; СТРОГО после death-check — смерть сильнее) на 4 точках диспетчеризации; терминал INTERRUPTED(INTERRUPT_TASK_STALE_INTENT) — reason-константа закона №16; outbox расширен до 4-кортежа (npc, outcome, fail_reason, interrupt_reason — D-6: причина прерывания ≠ причина провала). Граница: B действует из собственной причинности, НЕ зная о разговоре; прерывание = побочный эффект мир-действия на волю A, симметрично смерти; in-flight доигрывается; LLM без causal authority.
❌ Taboo: второй writer NPCState.intent (SSOT: StateApplicator); гейт с собственным реестром намерений; чтение CommitmentRegistry из гейта; event-bus как источник воли; «if драка рядом → interrupt»; B-знание о разговоре; self-relevance/понимание речи (M2/D); расширение предиката за flee без семантической таблицы birth↔current; частичная проекция intent-блока; запись реестра из async-воркера.
Status: ACTIVE (E1+E1b+E2 GREEN; golden 180 интентов/30 тиков, max duration 29 — инерция впервые жива, вердикт S213/DEBT-INTENT-SOURCE перевёрнут; боевой контур доказан hp-дельтой, органическое flee-перерешение — за S3-калибровкой)
Files (full: ADR-O-389_IMPACT.md): `backend/app/models/npc_state.py`, `backend/app/services/npc/state_applicator.py`, `backend/app/services/game_loop/task_scheduler.py`

`ADR-O-390` [ONTO] **Epistemic Self-Relevance Channel — «клейм обо мне» как отдельный канал** (S258; GC-RELEVANCE-01)
Суть: слушатель обязан различать «утверждение о третьем лице» и «утверждение обо мне»: до S258 клейм о самом агенте записывался как новость о третьем (perceived_threats содержал самого агента, trigger_proposition мог навести warn на себя). Развязка в EpistemicContextResolver.resolve: записи с subject_id == agent_id → claims_about_self / max_self_confidence (runtime-only поля, сериализация не затронута), полностью исключены из perceived_threats / perceived_violations / max_confidence / trigger_proposition. Потребление (R2): to_modifiers даёт консервативный разговорный буст talk = max_self_confidence × 0.5 (вдвое ниже threat-буста S198 — салиентность, не паника). Граница v1: предикат = только subject_id == agent; ветка object_id == me не тронута; реакция на клейм (RESIST/MODIFY) — следующая ступень лестницы.
❌ Taboo: self-клейм в perceived_threats/violations/trigger; self-relevance как множитель confidence в BeliefRevisionEngine (salience ≠ доверие, №51); реакционные ключи (attack/flee/warn) от self-канала до слоя RESIST/MODIFY; телепатия (канал только внутри мембраны услышанных клеймов); второй writer EpistemicStore; сериализация EpistemicContext; object_id==me-ветка без отдельной семантической таблицы.
Status: ACTIVE (замок 9/9, батарея 61/61, IPT 45/45; end-to-end при живой llama — кандидат живой-сессии)
Files (full: ADR-O-390_IMPACT.md): `backend/app/domain/epistemology.py`, `backend/app/services/npc/epistemic_context_resolver.py`

`ADR-O-391` [ONTO] **WORK Vertical Slice — замыкание «Intent.TRADE → WORLD CHANGE» минимальной сделкой** (S256; Living Activity, третий вертикал)
Суть: потребность → желание → сделка с другим агентом → обмен → изменение мира → исход обоим → следующий тик читает новый SSOT. Канал «давление желания → TRADE» в пайплайне (WORK-gated, urgency × WORK_TRADE_PRESSURE_K=1.0 — якорь шкалы; pressure deforms, not commands — DecisionHub не тронут). ORDER = Transaction(PROPOSED→ACCEPTED→COMPLETED/FAILED) с маршрутизацией к продавцу предмета желания (социальный адресат SocialTargetResolver ≠ экономический контрагент) и дедупом «один открытый заказ на покупателя». SERVE = work-pass Фазы 0 (target_ref = order_id; эль — goods-онтология, не WorldObject); терминал SERVE = точка расчёта: settle_order — валидация ДО мутаций → атомарный SSOT-обмен → COMPLETED → ACTIVITY_OUTCOME обоим + терминальное гашение давления покупателя («насыщение пишет только терминал», EAT-прецедент). Захороненный контур AUDIT #6 НЕ воскрешается (L-W7). Координация §11.1.1: заявлен как O-389 — двойная заявка, перенумерован в O-391 (20 код-сайтов обновлены).
❌ Taboo: воскрешение TransactionEngine/TradeResolver/RandomMarketState/TravellerGenerator/EconomicIntent (BURIED — археологический слой, не долг); второй economic pipeline; GIVE в WorldActionType (compound-барьер W3); DecisionHub проводит сделки/бухгалтерию; неатомарный обмен (FAILED не меняет мир); мутации вне SSOT-профилей (INV-WORK-PERSIST); WORK_ENABLED=OFF с новым causal footprint; повторный settle терминального Transaction; K канала подбором перебора.
Status: ACTIVE (юнит 17/17, SUPERBOX W1–W5 GREEN, IPT 45/45; EAT-регресс байт-идентичен базе)
Files (full: ADR-O-391_IMPACT.md): `backend/app/services/economy/work_orders.py`, `backend/app/services/npc/activity_lifecycle_service.py`, `backend/app/services/phases/post_decision.py`

`ADR-O-392` [ONTO] **P7 Disclosure Verbalization & Eavesdrop Provenance Label** (S259)
Суть: два закона M4-лестницы. (1) VERDICT PRECEDES WORDS: вердикт decide_disclosure выносится ДО вербализации, РОВНО ОДИН раз на реплику (инвариант Мастера); вердикт = данные — сериализуется в промпт как поведенческая директива [ДИРЕКТИВА РАСКРЫТИЯ: LEVEL] (REVEAL/PARTIAL+fraction/HINT/DENY/REDIRECT — P5 решил ЧТО, P7 вербализует КАК, LLM не решает) И эмитится DIALOGUE_OUTCOME из той же вычисленной величины; повторный вызов decide_disclosure = DOUBLE TRUTH вердикта. (2) EAVESDROP LABEL IS PROVENANCE: метка подслушанной реплики — из KnowledgeItem.secret_id спикера, НЕ из текста (PROVENANCE, NOT STRINGS); FULL ⇔ exposure ∈ {secret, whisper} → IDENTIFIED; иначе CLUE; без проводки/знания → (None, None) = observation only, fail-open. Открытое: DEBT-E1-WIRING — set_epistemic_wiring никем не вызывается (P7-B wired, P7-A тест-доказан).
❌ Taboo: второй вызов decide_disclosure «для события»; парсинг текста реплики для метки; расширение гвардов E1/E2; mark_discovered вне Bridge (Р1); правка SSOT-радиусов; LLM решает уровень раскрытия.
Status: ACTIVE (RED 6F/3P точный прогноз → GREEN 9/9; T5 монополия GREEN)
Files (full: ADR-O-392_IMPACT.md): `backend/app/services/execution/dialogue_executor.py`, `backend/app/services/events/npc_dialogue_subscriber.py`

`ADR-O-393` [ONTO] **Determinism Foundation — кросс-процессный детерминизм причинного контура** (S261; IRON RIVER Phase A+B)
Суть: контракт D «same inputs → same trajectory, кросс-процессно» — ВЫПОЛНЕН: 3×MATCH на каноне b8eb93ca. Закрыты четыре P0-брейкера IRON RIVER (wall-clock в состоянии / admission речи / боевой RNG / изоляция лаборатории) + два живых production-бага (Н-18 двойной трек activity↔schedule; гонки за порции). Финальный корень изоляции: LifeEngine.sessions_dir = settings.data_dir/"sessions" — подмена settings.data_dir на temp-копию обязательна (аргумент build_game_loop НЕ изолирует sessions_dir). Методология: красно-зелёный A/B-гейт (канон-хеш 2×150 тиков) + полевой дифф + per-tick трасса + снимок-дифф мутирующих файлов — 9 гипотез, 1 истина, ноль вслепую. PYTHONHASHSEED=0 + cool-down 3с + router-stub — обязательные условия лаборатории.
❌ Taboo: wall-clock в каузальных полях состояния; uuid4/Python-hash в kernel-событиях; admission по реальному времени; лаборатория без подмены settings.data_dir; обрезка памяти NPC в тест-копиях; atexit-очистка на Windows с SQLite (родительская); диагностика в гейт-файле; inline-python в PowerShell (файлы); оптимизация до зелёного гейта; вердикты на полном диске.
Status: ACTIVE (Phase A+B GREEN: 3×MATCH, IPT 45/45, EAT/WORK GREEN; IMPACT: отсутствует — создать stub)
Files: `backend/app/services/game_loop/task_scheduler.py`, `backend/app/services/npc/life_engine.py`, `backend/tests/sandbox/iron_river_*.py` (7 NEW харнессов)

`ADR-O-394` [ONTO] **Causal Slice 1 — DesiredChange: цель первична, способ выбирается** (S262; R5)
Суть: первый вертикальный срез причинного слоя (рамка Мастеров R2-R4). Доменный объект DesiredChange {who, reason, state_type, target_of_change, addressee, method_weights} — причинно определённое изменение, возникающее из состояния/правил (НЕ из LLM, НЕ из победы интента) ДО выбора способа. Срез: угроза → «B.stop_hostile». Законы CS1-CS6: CS1 причина первична — гейт threat≥0.35 + атрибуция из двух живых источников (fear-ось SSOT / Proposition.ATTACKED belief); CS2 цель ДЕФОРМИРУЕТ, не приказывает — to_modifiers → 8-й модификатор Modifier Contract (ADR-O-355), DecisionHub остаётся единственным решателем; CS3 target_of_change ≠ addressee; CS4 оценка способов собирает СУЩЕСТВУЮЩИЕ машины (disposition, drives L3, отношения SSOT, союзники, body_state — ноль дубликатов); CS5 LLM — только вербализация после выбора; CS6 ноль новых интентов/менеджеров. Доказано: «один DesiredChange → разные способы» (слабый → flee-доминанта; стражник+союзники → call_for_help/intimidate — детерминированно). V1-калибровка консервативна (_SCALE=0.6, сдвигает, не переворачивает).
❌ Taboo: порождать интент минуя DecisionHub; LLM как источник DesiredChange; мутация мира продюсером; второй решатель; новые Intent-enum-значения ради среза.
Status: ACTIVE (S262; RED ImportError-контракт → GREEN 8/8)
Files (full: ADR-O-394_IMPACT.md): `backend/app/domain/desired_change.py`, `backend/app/services/npc/causal_slice_threat.py`, `backend/app/services/npc/decision_hub.py`

`ADR-O-395` [ONTO] **Causal Slice 2 — Capability: выбор адресата из способности мира** (S263; R6)
Суть: hunger → DesiredChange(need/resource) → capability-скан (кто способен дать) → addressee B → method_weights {trade, request_service, steal}. Законы CS7-CS13: CS7 capability = ПРОЕКЦИЯ существующего SSOT (в hunger-домене — EconomicProfile.has_good; решение валидно только для hunger-домена, НЕ «capability = EconomicProfile»; будущие проекции inventory/role/knowledge/authority/ownership/skills); «Capability Manager» и второй SSOT запрещены; CS8 Desire не мутируется при адресации; CS9 capability-вакуум = честный None, НЕ fallback на ближайшего; CS10 выбор B = capability × trust × достижимость (причинная цель не проигрывает близости); CS11 предметный/социальный развилка; CS12 анти-двойной-счёт (eco_modifiers безликие + causal_modifiers адресованные; сумма ≤1.0); CS13 контрфактический закон: срез причинен ⟺ изменение мира меняет candidate set → methods → action. Viability-гейт: все способы мертвы → None («наличие capability ≠ наличие пути»).
❌ Taboo: «Capability Manager»/второй capability-SSOT; объявление «capability = EconomicProfile» за пределами hunger-домена; fallback на ближайшего при вакууме; мутация Desire при адресации; npc_id-хардкоды steal-базы (только архетип, S209); запуск steal-веса при will ∉ {broken, deceptive}; сумма method_weights > 1.0; реализация общей формы agent×operation×resource в этом срезе.
Status: ACTIVE (2a GREEN 14/14; 2b — координационный пункт)
Files (full: ADR-O-395_IMPACT.md): `backend/app/domain/desired_change.py` (acquire_resource), `backend/app/services/npc/causal_slice_hunger.py`, `backend/tests/gameplay/test_r6_causal_slice_hunger.py`

`ADR-O-396` [ONTO] **SOCIAL Vertical Slice — «потребность в другом → изменившиеся отношения»** (S264)
Суть: D1–D4 production-доказательство (LLM-free, sync-труба, ×3 детерминированно): EMA-давление → социальный intent → SocialTargetResolver-адресат → NPC_SPOKE-взаимодействие → RelationshipStore trust-мутации (5 NPC) → EMA next-tick. Закрыто четыре живых бага: idle-немота (рудиментный pending_tasks-гейт BUG-CORE-010), dequeue-PACING-break, валидатор broadcast-интентов (TICK_CRASH), enqueue-спам (дедуп+CANCELLED). Семантика 'all' для SPREAD_RUMOR/CALL_FOR_HELP канонизирована в валидаторе.
❌ Taboo: персональный target для broadcast-интентов ('all' легален); enqueue-молчаливый skip без terminal (CANCELLED-протокол); гейт execute_pending по scene.pending_tasks (DialogueQueue — отдельный SSOT); PACING-break на game-time оси; sync-пул в production (только тест-зона).
Status: ACTIVE (D1–D4 ×3 GREEN; IMPACT: отсутствует — создать stub)
Files: `backend/app/services/game_loop/__init__.py`, `backend/app/services/game_loop/task_scheduler.py`, `backend/tests/sandbox/superbox_social_deterministic.py`

`ADR-O-397` [ONTO] **Causal Slice 3 — Grievance: холодное последействие вреда** (S265; R7)
Суть: накопленный вред (trust-дефицит ≤-12 по осям RelationshipStore A→B) в холодной фазе (угроза ушла) → DesiredChange(reason=grievance, target=вредитель) → method_weights по именованным факторам → Modifier Contract. CS14 grievance = ПРОЕКЦИЯ осей, не сущность (флаги/Store/второй SSOT запрещены); CS15 горячее/холодное разделение с R5 (O-394): threat_gradient ≥ 0.35 — территория угрозы; обида — то, что остаётся, когда угроза ушла; каскад threat > hunger > grievance; CS16 жертва может молчать: страх×бессилие×одиночество → честный None. Способы — существующие интенты: intimidate/warn/spread_rumor/call_for_help. Контекст-гейт: изолированная сцена без чужих → None (обида — социальный акт). НАХОДКА: срез вскрыл спавшую дыру intent-without-target — системное лечение 2b-ii addressee→_resolve_target.
❌ Taboo: grievance-сущности/флаги (is_angry, planning_revenge)/GrievanceStore/второй SSOT; активность при горячем threat (CS15); нарушение молчания жертвы (viability); npc_id-хардкоды; новые интенты под месть; сумма весов > 1.0.
Status: ACTIVE (GREEN 10/10; production-доказан живыми обидами канона без инъекций; 2b-ii — координация)
Files (full: ADR-O-397_IMPACT.md): `backend/app/domain/desired_change.py` (REASON_GRIEVANCE), `backend/app/services/npc/causal_slice_grievance.py`, `backend/tests/gameplay/test_r7_causal_slice_grievance.py`

`ADR-O-398` [ONTO] **Seal Semantics, DriftLab Lifecycle & Legal Copy Optimization** (S269)
Суть: (1) SEAL — immutability WorldEpoch по построению: ReadOnlyDict/ReadOnlyList (isinstance-контракт scene_state сохранён; мутация = громкий TypeError); WorldView-чтение оборачивает контейнеры с кэшем на эпоху; move-semantics S266 сохранён; прецедент `__deepcopy__` → return self («immutable by construction → шаринг безопасен»). (2) LIFECYCLE: TaskScheduler._executor_pool не имел shutdown и переживал GameLoop.dispose() — закон: dispose владельца ОБЯЗАН дренировать собственные воркеры ДО закрытия ресурсов (shutdown(wait=True, cancel_futures=True) первым шагом; бесконечный join запрещён). (3) LEGAL COPY: «каждый байт deepcopy обязан иметь архитектурную причину быть скопированным» — цепочка: cProfile → call site → объём → зачем копия → последний consumer → изоляция? → benchmark → IPT → DriftLab MATCH. Принято: C1 seal-sharing, C2 ленивый npc-снимок (копия за тик ради мёртвого читателя недопустима), C3 fsync-лог-гейт лаборатории. ЗАФИКСИРОВАНО: input boundary deepcopy = CURRENTLY RETAINED (move проигрывает copy+seal — измерено, не мнение: 79.9–90.2 vs 105.3–124.5 мс/тик); commit↔input = EPOCH-FINAL BOUNDARY, не разбирать по одному сайту. Догма «deepcopy неприкосновенен» запрещена наравне с догмой «deepcopy убрать».
❌ Taboo: мутация ReadOnly* через каст в обход гварда; расширение запечатки на root-уровень state (ломает move-semantics S266); dispose без drain своих воркеров; бесконечный join в teardown; удаление несущей копии по одному сайту без Epoch-финала; оптимизация копий без полного цепочного доказательства.
Status: ACTIVE (IPT 45/45, epoch 7/7, DriftLab 10k×2 MATCH; перф 132.4→66.0 мс/тик)
Files (full: ADR-O-398_IMPACT.md): `backend/app/domain/world_epoch.py`, `backend/app/services/game_loop/__init__.py` (dispose-quiesce), `backend/app/services/scene_state_manager.py` (C2)

`ADR-O-399` [ONTO] **Worker Effect Outbox — async compute, deterministic commit** (S270)
Суть: воркер-поток `_process_tasks_async` лишается права прямых observable-эффектов (bus.publish / recent_dialogues.append / record_talk / speech_reset из worker-thread превращают arrival-time в скрытую причинную переменную — доказанный спарк DEBT-10K-MISMATCH). Контур: worker compute → frozen `_TaskArtifactRecord` (submit_tick, task_id, events, dialogue_entry, economy_talks, speech_reset) → outbox → main-thread deterministic drain → observable world. Воркер производит ТОЛЬКО данные. Дренаж — ровно две точки (симметрия S203.4), обе безусловные (дренаж и при pending_tasks == 0); сортировка по стабильному ключу (submit_tick, task_id); применение в порядке, зеркалящем существующую последовательность эффектов воркера. W5 (поправка Мастера): submit в эпоху N → artifact ready → первая drain boundary → атомарное применение; `worker completion timing ≠ world causal timing` — LLM-латентность не меняет порядок событий/реплик. Сопутствующий фикс: dialogue_queue task_id → детерминированный (uuid4 в ключе сортировки делал W5 недоказуемым; прецедент запрета — ADR-O-365). Главный гейт 10k×2 MATCH = закрытие DEBT-10K-MISMATCH. STATUS-MODEL: EVENT (объективно произошло, event_tick=submit_tick) ≠ EXPERIENCE (когда субъект получил, arrival-time легален) ≠ MEMORY (что сохранил).
❌ Taboo: `.result()`/`wait()`/`join()` в живом tick-loop; синхронный LLM-вызов на границе тика; привязка commit к submit_tick+1; третья точка дренажа; расширение каналов artifact без мини-ADR; изменение контракта commitment-outbox (O-363/365 — каналы раздельны); новый manager/шина/SSOT (artifact — пассивный контейнер); перенос failed_tasks в канон.
Status: ACTIVE (S270: A1==A2 межпроцессно, IPT 45/45, O-399 CLOSED; открытый хвост: speech_reset skeleton-publication — итерация 2, если расщепление сохранится)
Files (full: ADR-O-399_IMPACT.md): `backend/app/services/game_loop/task_scheduler.py` (outbox, drain), `backend/app/services/execution/dialogue_queue.py` (task_id), `backend/tests/test_worker_outbox_determinism.py`

`ADR-O-400` [ONTO] **Incremental PatternDetector State (Watermark)** (S274)
Суть: History-tax (query_raw 42→78% L1-потока по оси H, onset ~3000 тиков, t_from=0 → полное сканирование на каждой кристаллизации) устраняется инкрементальным state'ом достаточной статистики per (npc, source): n, cumulative (последовательный float), Σx/Σx² (Fraction — exactness contract, statistics.variance эталон), last_sign, sign_flips, first_seen (order contract). Equivalence gate доказал: полная история семантически не необходима, необходим достаточный state; наивный watermark отвергнут на гейте. Flag default OFF = no-op (прецедент S203.1). Equivalence oracle (побитовые сравнения + PBT) ДО benchmark; расхождение skeleton = NO-GO независимо от ускорения. Persistence: scene_state → Фаза 10 atomic commit (прецедент EpistemicStore S193); Rule 28 не затронут.
❌ Taboo: Float-Σ²/Welford в первой реализации; расширение EvidenceOfPersistence; рефакторинг query_evidence в этой итерации; Rule 28; собственная SQLite watermark-state; флаг ON без oracle+skeleton; approx-сравнения в oracle.
Status: ACTIVE (Oracle 11/11, A/B 24×10k RED→YELLOW, IPT 45/45; **канон номера O-400** — Affection перенумерован в O-413, Устав 11.1.1)
Files (full: ADR-O-400_IMPACT.md): `backend/app/services/npc/pattern_detector.py`, `backend/app/services/phases/integration.py`

`ADR-O-401` [STRUCT] **De-godification SSM — extraction в пакет scene_state/** (S274-DEGOD)
Суть: серия ITER1–4c: из scene_state_manager.py экстрагированы leaf/фабричные кластеры в app/services/scene_state/ (environment_modifiers, change_validator, npc_display_name, editor_locator, dm_presentation, scene_factory). Старый класс = фасад (делегаты, re-export); поведение неизменно (IPT 45/45, DriftLab MATCH на каждой итерации). Владельческое ядро (tick-scoped identity, commit/apply/EPOCH/GAP12/RE) не тронуто — STOP-зоны DEGOD_PHASE0_MAP_SSM. Cross-file bridge GameLoop↔SSM (_tick_scenes/_persistence) задокументирован как запретный для наивных extraction-границ.
❌ Taboo: перенос владельческого ядра SSM без отдельного ownership-решения; третий путь зеркала материализации; удаление re-export при живых внешних импортёрах.
Status: ACTIVE
Files (full: ADR-O-401_IMPACT.md): `backend/app/services/scene_state_manager.py`, `backend/app/services/scene_state/*` (6 модулей), `docs/audits/DEGOD_PHASE0_MAP_SSM.md`

`ADR-O-402` [STRUCT] **Turn Pipeline Ownership (Phase 3A)** (S278-DEGOD)
Суть: фазовая машина player-turn выделена из GameLoop в turn_pipeline.py (execute + 6 фаз). Обратные зависимости dm_phase/npc_orchestration от GameLoop разорваны через фазовые контракты DmPhaseDeps/NpcOrchDeps (frozen; TurnServices-контейнер элиминирован по red-flag). SSM tick-seam инкапсулирован (adopt_scene_for_tick/is_tick_locked_for); B-состояния GameLoop — через accessors/setter/provider. Campaign Lifecycle — HOLD до отдельного ownership-design (реализован O-403).
❌ Taboo: game_loop как параметр фазовых модулей; универсальный services-контейнер; NpcTickServices с application-lifetime; смешение seam- и extraction-изменений в одном коммите; коммит при красном гейте.
Status: ACTIVE
Files (full: ADR-O-402_IMPACT.md): `backend/app/services/game_loop/turn_pipeline.py`, `backend/app/services/game_loop/dm_phase.py`, `backend/app/services/game_loop/npc_orchestration.py`

`ADR-O-403` [STRUCT] **Campaign Lifecycle Ownership (Phase 3B)** (S279-DEGOD)
Суть: жизненный цикл кампании выделен из GameLoop в campaign_lifecycle.py. Метод: seam-first (6 итераций: SSM/RelationshipStore/MemoryManager/TemporalEngine/PlayerAvatarService/LifeEngine получили публичные reset-API у владельцев), затем extraction (reset_campaign 12 шагов 1-в-1 + load_campaign + resolve_world_id + diff-IO). Побочно устранён DOUBLE TRUTH пути player_avatar.json (настоящий файл переживал new_game); RelationshipStore получил RAM-кэш-чистку у владельца; routes-прямая запись _campaign_diffs заменена seam-ом record_campaign_diff.
❌ Taboo: приватные проникновения new_game в internals владельцев (все 6 seam-классов закрыты); CampaignManager-контейнер; изменение порядка reset; EPOCH-FINAL.
Status: ACTIVE (HOLD→GREEN→CLOSED)
Files (full: ADR-O-403_IMPACT.md): `backend/app/services/game_loop/campaign_lifecycle.py`, `backend/app/services/game_loop/game_loop.py`, `backend/app/services/memory/relationship_store.py`

`ADR-O-404` [ONTO] **Event Identity — детерминированная событийная идентичность** (S283; Фаза 1 семантического контракта)
Суть: устранён коллизионный дефект identity (класс BUG-FB-037): seed `md5("{type}:{source}:{ts}")` при дефолтном timestamp=0.0 схлопывал ВСЕ события одного (type, source) в один ID за кампанию — молча подавлялись D8P-идемпотентность, AG1-INV-TRACE-ONCE, claim-provenance. Новый контракт: identity(event) = (event_type, source, event_tick, ordinal); ordinal — персистентный монотонный счётчик scene_state["event_ordinals"] (зеркало commitment_ordinals); единственный писатель — next_event_identity (svc/events/event_identity.py); финализация id — ровно на входе в шину (EventBus._finalize_identity); Payload = DATA, в seed не входит; provisional id (тесты/вне lock-окон) — легальный режим. INV-EVENT-IDENTITY в IPT. ОТКРЫТОЕ ОБЯЗАТЕЛЬСТВО: полный replay-MATCH живого конвейера НЕ доказан (replay-запись в DriftLab не подключена; «REPLAY SESSION RECORDED» ≠ доказательство записи — фантомный успех; ремонт replay-инфраструктуры — отдельное ТЗ, см. S301 R5). Изменение id-поколения: cross-version id-equality не гарантируется (как между любыми версиями алгоритма); INV-REPLAY-DETERMINISM не затронут.
❌ Taboo: payload-поля в identity-seed (DATA ≠ IDENTITY); второй независимый счётчик порядка для claim_id; ведение счётчиков вне next_event_identity (DOUBLE TRUTH); мутация scene_state из воркер-потоков; трактовка «REPLAY SESSION RECORDED» как доказательства записи; расширение Predicate ради attribute-claims.
Status: ACTIVE (battery 8/8, INV-EVENT-IDENTITY, DriftLab 200 тиков 0 крашей)
Files (full: ADR-O-404_IMPACT.md): `backend/app/services/events/event_identity.py`, `backend/app/services/events/event_bus.py`, `backend/tests/micro/test_event_identity.py`

`ADR-O-405` [STRUCT] **Investigation Board — Presentation-Persistence (Phase 4 MVI)** (S290)
Суть: доска расследования — организация ссылок игрока над presentation layer (journal/claims/beliefs), НЕ domain primitive (§ENIGMA-002). board_state.json в saves/<campaign>/ рядом с player_avatar.json; атомарная точечная запись (tmp+os.replace); монотонные счётчики id c self-repair только вверх (uuid4 запрещён). ref_id opaque: journal→event_id (ADR-O-404 сквозная identity); резолв материала — клиентский джойн против dialog_journal; мёртвая карточка (ref вытеснен FIFO cap-100) = валидное состояние, рендер серым. Board не знает, что является истиной; LINK/UNLINK = user-authored relation (PLAYER_SUPPORTS/PLAYER_CONTRADICTS), не объективная семантика.
❌ Taboo: запись в EpistemicStore/TruthState; расширение Predicate (hypothesis = свободный текст); автовозвышение hypothesis→belief (Phase 5); LLM; копирование содержимого Journal в Board (второй SSOT — только ref_id); связь Board→causal mechanics (ACCUSE-гейт не подключать); domain-imports из board-модуля; uuid4; DELETE-миграции файла.
Status: ACTIVE (MVI: все 8 операций, гейты §6 закрыты — round-trip, пустая карточка, изоляция байт-в-байт)
Files (full: ADR-O-405_IMPACT.md): `backend/app/services/player_board_service.py`, `backend/app/api/routes_board.py`, `frontend/ui_workbench/windows/board_window.py`

`ADR-O-406` [ONTO] **INV-PLAYER-AUTHORSHIP — Control Source Axis** (S292)
Суть: различие «существует в мире» (Actor) и «управляет своим действием автономно» (AutonomousDecisionAgent) канонизировано осью `ControlSource` (PLAYER_INPUT / NPC_DECISION / SCRIPTED_SYSTEM / COMBAT_CONTROLLER). Единственная точка знания 'player'-строки — `domain/control_source.py`; новые строковые гарды агентности запрещены. Автономный decision pipeline не порождает авторский акт аватара: CommunicationIntent(speaker="player") запрещён в любой фабрике. Четыре слоя защиты: (0) фильтр decision population, (1) гвард DecisionHub._build_communication, (2) гвард attack-фабрики, (3) детектор SimulationIntegrityError(INV-PLAYER-AUTHORSHIP) перед TickMutation (громкое падение, ADR-INV-DEF). Player остаётся легальным target/observer/источником событий/объектом восприятия и убеждений. Психика аватара — player-input pipeline (ADR-TZ08-1) + AvatarStateApplicator (S208). Контекст будущего: мультиплеер требует Actor ≠ AutonomousDecisionAgent как фундаментального различия; COMBAT_CONTROLLER зарезервирован пошаговым боем.
❌ Taboo: CommunicationIntent(speaker="player") из autonomous pipeline; новые строковые гарды 'player' как предиката агентности; тихое удаление не-NPC интентов (только raise); расширение _PLAYER_ACTORS без записи в ADR; исключение player из мира — запрещено только АВТОРСТВО.
Status: ACTIVE (регресс S292: player_in_decisions=0 за ~124 тика; IPT 46→47/47)
Files (full: ADR-O-406_IMPACT.md): `backend/app/domain/control_source.py`, `backend/app/services/npc/decision_hub.py`, `backend/app/services/tick_orchestrator.py`, `backend/tests/IPT.py`

`ADR-O-407` [ONTO] **PLAYER TURN COMMITMENT — Time Gate Semantics** (S292-наследник)
Суть: пока не исполнено обязательство хода игрока, мировое время не продвигается: idle-контур не вызывает TickOrchestrator.execute() → Фаза 0.5 не тикает. Гейт — свойство EXECUTION MODEL игрока, НЕ существования LLM-вызова (табу: формулировать паузу через «ждёт LLM» — при мультиплеере 10000 players глобальная LLM-пауза абсурдна). Для single-player MVP семантически совпадает с паузой на время генерации ответа судьи хода; архитектурно готовит per-player временные контуры. Онтологическая чистота: ADR-O-344 не тронут (оркестратор остаётся владельцем времени — гейт решает, вызывать ли execute); ADR-TZ08-1 не тронут (флаг живёт в game_loop); ADR-002 переформулирован, не нарушен (время не останавливается ВНУТРИ исполняемых тиков); реплей цел (окно паузы не порождает событий). Ограничение фриза: per-task timeout + _abort_generation (O-364) уже существуют; abort → честная ошибка хода (ADR-113). Scope: ТОЛЬКО ход игрока; материализация NPC-реплик (ADR-O-313) остаётся в живом мировом времени.
❌ Taboo: гейт через наличие LLM-вызова; глобальный pause «система ждёт LLM»; продвижение времени game_loop'ом; пауза материализации NPC-диалогов; новый источник времени.
Status: APPROVED-BY-MASTER (рекомендация (а) принята; реализация — отдельная сессия: флаг player_turn_in_flight в game_loop по образцу workbench_paused, инвариант INV-PLAYER-TURN-TIME-GATE)
Files: `backend/app/services/game_loop/game_loop.py` (будущий гейт; IMPACT создать при реализации)

`ADR-408` [FIX] **GATE-TRIGGER-01 — Predicate-фильтр trigger_proposition** (S297; ⚠️ namespace: FIX, ≠ ADR-O-408 [ONTO] S304)
Суть: EpistemicContextResolver выбирает WARN-триггер S197-таргетинга только из угрозных предикатов `_THREAT_PREDICATES = (STOLE, ATTACKED)` — единая константа кормит И perceived_threats, И trigger_proposition. Причина: EXITS_TO-гео-записи (subject = узел графа — легитимная механика «NPC помнит двери») и HELPED (союзники) становились WARN-целью: sanity_membrane.can_address не различает NPC и узел графа, гварды S292 были прозрачны; upsert-мембрана S292 в epistemic_store — мёртвый код (short-circuit), удалена в том же коммите 1e564812. Downstream ThreatDesiredChangeProducer имеет собственный predicate-гейт — defence-in-depth. Реестр живых акторов для can_address — ОТЛОЖЕН как отдельное будущее ADR (Two-Domain Rule).
❌ Taboo: расширение `_THREAT_PREDICATES` без мини-ADR; фильтрация max_confidence (питает to_modifiers); воскрешение upsert-мембраны без реестра акторов.
Status: ACTIVE
Files: `backend/app/services/npc/epistemic_context_resolver.py`, `backend/app/services/npc/epistemic_store.py`, `backend/tests/micro/test_self_relevance_gate.py`, `docs/audits/ADR-408_IMPACT.md`

`ADR-O-409` [ONTO] **Name-Gate Closure — FACE/NAME/LINK** (S306/S308)
Суть: две оси знания + одна ось связи: RecognitionMemory (FACE — «узнаю этого человека», M17) / NameKnowledge (NAME — «знаю, как его зовут», per-campaign, player_avatar.json) / player_link доски (LINK — «считаю, что имя = это лицо»). Отображение: show_name = recognition_confirmed AND name_confirmed. Прогрессия UI: Незнакомец → «человек с фартуком» (generic) → «Имя (?)» → Имя. КАНОНИЧЕСКИЙ ИНВАРИАНТ: npc_id в backend ≠ знание игрока — machine-identity не даёт игроку имени. M17-direct СУЖЕН: разговор подтверждает лицо, не имя (вердикт Мастера). Каналы NAME: SELF_INTRO · NPC_MENTION (услышанное имя → tentative ТОЛЬКО; identity-link с фото ЗАПРЕЩЁН на уровне механизма) · PLAYER_LINK (доска: фото+имя → confirmed; решение игрока). Journal writer-gate: speaker → display_name по NAME-оси; npc_id — скрытый провенанс записи. EncounterHistory/recognition_layer НЕ подключается (третий SSOT cognition запрещён).
❌ Taboo: identity-link из услышанного имени; имя из npc_id напрямую; авто-inference имён; NameKnowledge вне avatar_service-владельца; подключение EncounterHistory как второго источника.
Status: ACTIVE — полная реализация (S306 ядро + S308 PLAYER_LINK; name_gate 7/7). Остаётся включение NAME_GATE_ENABLED в прод (решение Мастера по живому smoke)
Files (full: ADR-O-409_IMPACT.md): `backend/app/services/player_avatar_service.py`, `backend/app/services/events/npc_dialogue_subscriber.py`, `frontend/ui_workbench/workbench_screen.py`

`ADR-O-413` [ONTO] **Causal Slice 4 — Affection: забота о состоянии другого** (S303; R8; **номер переназначен** — изначально бронирован как O-400, конфликт с Watermark S274 разрешён по Уставу 11.1.1, O-413 = max+1)
Суть: четвёртый причинный срез: тёплая связь (trust ≥ 40 ∧ attraction ≥ 40 по осям RelationshipStore) + видимый distress B (world-снапшот, 0-100) + capacity A → DesiredChange(who=A, reason=affection, target_of_change=B, addressee=B) — ПЕРВОЕ структурное who ≠ target_of_change. CS17 affection = проекция тёплых осей, не сущность; CS18 чужой distress читается из world-снапшота (perception-мембрана — долг честности); CS19 capacity: без ресурса и денег → честный None. Способы существующие: talk/trade/call_for_help; сумма ≤ 1.0; каскад threat > hunger > grievance > affection. НАХОДКА: enrichment ронял base_affection канона — attraction-слот V2 никогда не наполнялся; патч вернул тёплый мир в runtime (бисекция: 0 вклада в фейлы).
❌ Taboo: affection-сущности/флаги/Store/второй SSOT; чтение чужого distress мимо world-снапшота; забота без capacity; обход каскада причин; новые интенты; npc_id-хардкоды.
Status: ACTIVE (production-доказан живым probe: orm→lusya←care, trade 0.512 — купить для любимой; каскадный феномен hunger > affection; IMPACT: отсутствует — создать stub)
Files: `backend/app/domain/desired_change.py` (nurture), `backend/app/services/npc/causal_slice_affection.py`, `backend/app/services/npc/npc_tick_pipeline.py`, `backend/tests/gameplay/test_r8_causal_slice_affection.py`

`ADR-O-408` [ONTO] **Canonical Attention→Action Integration — Evidence & Boundaries** (S304; ⚠️ namespace: ONTO, ≠ ADR-408 [FIX] S297; историческая запись — не runtime-контракт)
Суть: история доказательства и границ. (1) OBS-DICT-1→П-1 — источник истины Gate①: RAM-канон scene_state["npc_intents"] (single-writer — оркестратор в точке attention-моста; полный выбор, не только изменения) читается ПОВЕРХ ADR-117-life-кэша. (2) P3e доказал attention→cognition→decision→physical consequence. (3) S304 integration I–V подтвердил путь на живом NPC-рельсе: observe останавливает несовместимое движение; approach порождает встречное. (4) Case C (decision→execution ignored) не воспроизведён за 12 прогонов. (5) NEED-EXEC-1 — отдельный execution-gap need-driven рельса («застывшие эмиттеры»), НЕ attention-defect. (6) Phase VI (APPROACH→CONTACT→COMBAT) — отдельный continuation. Границы: доказан контур внимание→решения→физическое поведение — НЕ «attention fully integrated everywhere» (бой/контакт недоказаны).
❌ Taboo: чтение Гейт① life-кэша как источника intent (INV-N18-SOURCE); объявление need_driven-продолжения при observe багом внимания; патч Гейт①-предиката ради сценариев; интерпретация записи как полного внедрения во все контуры.
Status: ACTIVE (S304 CLOSED)
Files (full: ADR-O-408_IMPACT.md): `backend/app/services/tick_orchestrator.py` (writer npc_intents), `backend/app/services/phases/simulation.py` (reader Gate①), `backend/tests/IPT.py` (INV-N18-SOURCE)

`ADR-O-410` [ONTO] **W-Track G3 — Object Action Executor: первый runtime-writer WorldObjectStore** (S307; коммиты 1ce0a00f+4169f77e; рабочее имя в коммит-сообщениях «S305» → канон S307)
Суть: вертикаль `intent → исполнитель → мутация мира → событие` замкнута. G3-executor (svc/world/g3_executor.py) получает УЖЕ разрешённый интент (STEAL, target_id=wo_*) и отвечает «исполнимо ли → мутация → исход»; целеполагание — не его контур (И-1). Врезка — Фаза 7 release-ветка, до to_event: PASS → apply_transition (TAKE; STEAL=W5-интерпретация, ADR-O-376) + событие существующим путём; REJECT → INTERRUPTED(G3_OBJECT_REJECT), событие НЕ публикуется (D4: событие = утверждение факта); SKIP → passthrough (honest-zero — steal-цели без wo_-identity). Г4-цензус `_ALLOWED_WRITERS` в `_write_subtree`; расширение = мини-ADR. Флаг W3_G3_ENABLED default OFF = no-op до вычислений. D5-факт: chair-TAKE NO_OP недостижим (уже-held → NOT_FREE REJECT) — дубль-THEFT онтологически невозможен. Приёмка: юнит 9/9; GC-00 A/B GREEN (ON: holder=thief_shadow; OFF: байт-идентично); IPT 49/49. Этап 2: compute_object_target_facts (nearest+lex; TARGETABLE_ARCHETYPES=chair→TAKE — calibration policy) → TickState.object_target_map → DecisionHub; Tier-A winner=steal 1.67; will_probe = honest-zero + замок R6.3 (CAN_STEAL≠ACCEPT/WANT — следующий cognition-слой, находка Мастера).
❌ Taboo: executor целеполагает; расширение закрытых реестров (_ACTION_TO_WORLD, цензус Г4) без мини-ADR; write мимо стора; событие при REJECT; повторный WillpowerGate на release; MutationRecord до потребителя.
Status: ACTIVE (двухэтапно GREEN; **L3-обязательство GC-08 открыто** — prerequisite capability spawn_world_object для harness; канон §9.2 roadmap)
Files (full: ADR-O-410_IMPACT.md): `backend/app/services/world/g3_executor.py`, `backend/app/services/world/object_target_facts.py`, `backend/app/services/phases/post_decision.py`

`ADR-O-411` [ONTO] **S2B.7 Pain/Injury — Eternal FLAT-Guard + Zonal Capability Derivation** (S309)
Суть: (1) вечный гвард класса «unit input ≠ production input» для InjuryProcessor: AST-тест пиннит каждое npc.get(...) в handle() к ключам NPCStateSnapshot — третий рецидив закрыт структурно. (2) Injury = физика раны: functional_loss → locomotion_impairment = 1−Π(1−loss) по leg/groin (совокупность; худшая рана на зону) и manipulation_impairment = min по arm_l/arm_r (лучшая рука сохраняет действия). (3) Следствие — физическое: ноги → СТОИМОСТЬ движения в BodyEngine (INJURY_LOCOMOTION_WEAR; закон №8: pressure, не decision); обе руки ≥0.95 → is_capable=False. Ноги не ветят capability бинарно — движение деградирует стоимостью. (4) received_tick при материализации — мост к Recovery S2B.8 (лечение не реализовано). (5) DEATH LOCK (ADR-127) распространён на InjuryProcessor честным чтением life_status. НАХОДКА Wound (physical.py:244) — dormant Multiple Representation (аватарный D&D-путь, таксономии несовместимы; активация = мини-ADR).
❌ Taboo: чтение ключей вне NPCStateSnapshot в InjuryProcessor.handle; второй per-tick physiological engine; injury → emotion; pain как второй HP; сведение capability к одному числу; бинарный locomotion-veto; правка зональных констант без вердикта (закон №13); записи body_state мимо StateApplicator.
Status: ACTIVE ([S2B7-G-debt]: прокидка tick_number через apply_batch — вердикт Мастера; INJURY_LOCOMOTION_WEAR=1.0 — v1 структурный коэффициент, на вердикт)
Files (full: ADR-O-411_IMPACT.md): `backend/app/services/combat/injury_processor.py`, `backend/app/services/body/body_engine.py`, `backend/tests/test_s2b7_injury_chain.py`

`ADR-O-412` [ONTO] **Capability Projection — Tradable Channel** (S310)
Суть: capability агента — проекция SSOT физического состояния (agent × operation × resource), не отдельная сущность. Первый канал: carried_objects (SSOT вещей архетипа, world_ontology-валидация PHYSICAL) → goods (владение, profile_factory) → stock_for_sale (операция TRADABLE, фильтр GOODS_PRICES). Закон Мастера: PHYSICAL ≠ TRADABLE ≠ USABLE — границу операций задаёт система-потребитель (TRADE знает GOODS_PRICES), не онтология мира. До ADR: контур TRADE→ORDER был мёртв (сток пуст у всех — production-доказано); Iron River-труба ждала источника. После: полная петля NEED→DESIRE→TRADE→ORDER→SERVE→settlement→PHYSICAL TRANSFER→OWNERSHIP доказана production-контуром ×3 (reports/f1_clean.txt — эталон). β-Stage 1 закрыт ВЕРИФИКАЦИЕЙ: settle_order уже реализовывал обмен, правки settlement ноль (body_state в settlement не трогается — насыщение только через владение→capability→EAT).
❌ Taboo: α-патчи «settlement → hunger -= …» (второй путь причинности, покупка без вещи); прямая запись body_state в экономическом контуре; проекция non-tradable маркеров в сток; ресток без отдельного ADR; GOODS-независимые стоки.
Status: ACTIVE (β-Stage 1 ✅ ×3, IPT 49/49; открытые швы: β-Stage 2 goods→EAT→body_state — отдельный фронт, рамка у Мастера; ресток; F1a S264-гейт; goods-vs-stock семантика продавца)
Files (full: ADR-O-412_IMPACT.md): `backend/app/services/game_loop/service_factories.py` (tradable-проекция), `backend/tests/sandbox/f1a_trade_gate_probe.py`



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

*Версия: 8.0 (Unified & Compressed: одна запись = один ADR; детали и полные Files-списки — docs/audits/ADR-*_IMPACT.md)*
*Сессия: S310 | IPT 49/49 | Записей STANDALONE: 65 | DriftLab: 10k×2 MATCH (S269/S270)*



