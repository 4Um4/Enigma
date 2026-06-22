# MUTATIONS.md — Каузальная Эволюция ENIGMA

> **Формат:** Домен → Хронология сессий → Запреты. Ищи по `Ctrl+F S##` или домену.

---

## МЕТА

| Показатель | Значение |
|------------|----------|
| Сессий | 90 |
| Доменов | 10 |
| Консолидированных запретов | 86 |
| Диапазон | S03—S90 |

---

## ЛЕГЕНДА

| Символ | Значение |
|--------|----------|
| ⚪ | Эволюция / Изменение логики |
| 🔵 | ADR (Стандарт / Онтология) |
| 🟢 | FIX (Закрытый баг) |
| 🔴 | CRITICAL (Критический баг / Разрыв пайплайна) |
| 💀 | Убитый концепт (не воскрешать) |

---

## 1. ДОМЕНЫ И ЭВОЛЮЦИЯ

- 🔵 **TZ-08 v0.2** Строгая миграция ядра в Event-Driven модель.
  - Внедрён `InterventionEvent` как единственный внешний входной протокол.
  - `execute()` стал чистой функцией `state_t + events → state_t+1`. Ветвление `dm_ctx` убито.
  - Фаза 1 разделена на NPIC, routing и WillpowerGate.
  - `RulesAgent` заменён на синхронный `RulesSubscriber` (pure reducer).
  - `execute_player_finalize` депрекирован (no-op).
  - `TickResultDTO` очищен от physical `movement_intents` и player-specific полей. `npc_contexts` (Narrative Projection) перенесены в `_TickContext` как артефакт тика.
  - Удалён мёртвый код двойного применения дельт (`apply_npc_state_updates`).

### DOM-01: FOUNDATION (Core Pipeline, Time, State)

**Истина:** Симуляция дискретна, презентация непрерывна. `LifeEngine` — лоббист, а не бог-мутатор. Тик — чистая функция вычисления.

- ⚪ **S04** Централизация через `SpatialService` v1.2, убит хардкод локаций.
- ⚪ **S29** Убита телепортация. Внедрен Каузальный Lerp на фронтенде. `DIRECT_REFLEX` удален.
- 🔵 **S34** DualTime Ontology. Запрет ретросимуляции. `LifeEngine.tick()` возвращает интенты, а не мутирует.
- 🔵 **S37** Authoritative Spatial Spine (ADR-048). `SpatialQueryService` инстанцирован.
- 🔵 **S47** Консолидация `SpatialService` в `TickOrchestrator`. Внедрен `_resolve_spatial_service`.
- 🔴 **S49** Инвариант единого владения причинностью движения. `npc_orchestration.py` лишен права вызывать `process_intents`.
- 🟢 **S50** GAP12 УБИТ. `_enrich_local_positions` вычисляет интерполированную позицию для NPC в активном транзите.
- 🔴 **S72** ADR-128 P0: DECAY_INJURY_LOST — NPC injuries терялись после cache miss. Внедрен SQLite read-back.
- 🔴 **S72** ADR-128 P0: Player injuries LOST — AvatarService `_state_to_dict()` не сериализовал `body_state`.
- 🔴 **S73** ADR-130 G1: Schedule Override Reactive Movement — `update_routine()` мутировал поверх активного reactive traversal.
- 🔴 **S74** P0: DRF Split-Brain Fix. DRFBus перенесён на уровень экземпляра оркестратора (ADR-134).
- 🔵 **S74** DRFExecutionContext: Scoped Causal Ledger (ADR-136). Pipeline получает `drf_ctx`, Claim наследует контекст.
- 🔴 **S76** Normalization Gate: `tick_orchestrator.py` инжектит `BODY_STATE_DISABLED` для NPC без `body_state`.
- 🔵 **S83.1** ADR-S83.1: Tick = Pure Function Evaluation. Тик — чистая функция, не объект с побочными эффектами.
- 🔵 **S83+** ADR-GL-202: Generative Constraint Execution Model (GCO). Ленивое вычисление графа каузальности.
- 🔵 **S83+** ADR-O-204: Phase 3 Preconditions — Causal Kernel Surgery.
- 🔵 **S83+** ADR-O-205: Projection Layer System. Слой проекции физики в наблюдаемую реальность.
- 🟢 **S85.1** ADR-O-201: Boundary Drift Fix. `EventCompiler._compile_boundary_snap` принудительно устанавливает `is_boundary=True` при наличии `target_loc`.
- 🟢 **S85.1** ADR-O-201: Topology Drift Fix. `EquivalenceValidator.validate_topology` отключен для кросс-локационных переходов (узлы физически разные).
- 🟢 **S85.1** ADR-O-201: Null Coordinate Fix. `EventCompiler` использует `(0.0, 0.0)` fallback вместо `None` для `SpatialResolution.target_xy`.
- 🟢 **S85.1** Import Fix: `WillState` импортирован из `app.models.will` (не `vital_state`). `NPCStateAdapter` используется вместо `NPCState.from_legacy`.
- 🟢 **S86** ТЗ-02 (Часть A): Восстановлена исполняемость пайплайна. Устранены `ImportError` (`apply_drives_mutation`), `NameError` (`effective_drives`, `state` vs `state_for_llm`). Удалён дубликат TIFL-блока.

### DOM-02: WILL, PRESSURE & DECISION

**Истина:** Решения рождаются из искривленного давления (Utility Deformation). Воля — инерция, а не порог. Подчинение требует легитимности.

- 🔵 **S19** WillpowerGate (ADR-031). Cumulative Strain Model вместо бинарки. Шкала COMPLY → CONDITIONED.
- ⚪ **S21** Убийство объективных событий. Давление генерирует `PsychologicalPressure`, а не напрямую интент.
- 🔵 **S24** Affective Resonance (ADR-036). Аффект искажает давление через `ResponseBias`.
- 🔵 **S31** DecisionContext (ADR-050). Feasibility Layer (удаление невозможных действий) и Utility Deformation.
- 🔵 **S36** Legitimacy Gate (ADR-057). Нет страха/доверия = Irritation (агрессия) вместо Obedience.
- 🔴 **S48** Починка обрыва Трубы Воли на границе API. `routes.py` теперь пробрасывает `will_conflict_data`.
- 🟢 **S52** GAP10 УБИТ. `EventContext` обогащён `target_id`. DecisionHub фильтрует бонус `APPROACH` для нецелевых NPC.
- 🟢 **S53** GAP2 УБИТ. Амнезия Воли вылечена. `compute_willpower` читает `trauma_markers`.
- 🟢 **S55** УБИТ Мертвый Вектор Эмоций (ADR-088). `IntentCompressor._fast_path_parse` инжектит агрессию для ATTACK.
- 🟢 **S60** УБИТ `_semantic_action=None` (ADR-091). `publish_classified_player_event` вызывается после резолва.
- 🟢 **S64** УБИТ PHYSICS_OF_POWER NameError. `_context_relevance` не имел параметра `event`.
- 🔵 **S69** Ontology Merge Step 1: Relationship Cache Precedence Contract.
- ⚪ **S71** §ENIGMA-S72 Закон Релятивистского Восприятия. Система перешла от централизованной интерпретации к модуляции личностью.
- 🔴 **S74** ДОЛГ 4.2: Causal Scoring Overlay (ADR-135). DRF претензии влияют на приоритет аддитивно. Убит сломанный clamp.
- 🔵 **S81** ADR-O-146: Personality Math Layer. Введен `profile_math.py`. Социальные дельты и риск модулируются личностью.
- 🟢 **S85.1** ADR-130: `LifeEngine._simulate_major` теперь полностью блокирует генерацию интентов (schedule + need-driven) для NPC в статусе `MOVING`. Устранён "бесконечный бег" и топологические дрейфы.
- 🔵 **S86** ADR-TZ08-6: Онтологическое разделение контрактов. Внедрён `observed_state` (name, description, narrative_cache) в `npc_tick_pipeline.py`. `real_state` и `distortion_bias` полностью удалены из генерации ядра. `r3_direct_builder` переведён на чтение безопасной проекции. Эпистемический Барьер обеспечен на уровне генерации данных.
- 🔵 **S86** ADR-TZ05-1: Изгнание LLM-логики из ядра. Функция `build_verbalization_context` и класс `VerbalizationContext` удалены из `npc_tick_pipeline.py`. Ядро больше не собирает ментальные объекты для LLM. Передаётся только строка `topic`. `r3_direct_builder` обновлён для чтения `topic` напрямую.
- 🟢 **S86** ТЗ-02 (Шаг 1): BUG-001 закрыт. Директивные `perception`-поля применяются вне зависимости от `DeltaDomain`. Каузальная труба воли (приказ → pressure → PerceptualKernel) открыта.
- 🟢 **S86** ТЗ-02 (Шаг 7): `BreakProgressEngine.calculate` подключен к `_phase_5_decision` (до DecisionHub). `WillState.BROKEN` достижим.
- ⚪ **S86** ТЗ-02 (Шаг 8): `BehaviorMask` назначается на основе state. Введён как гистерезисный (квазистабильный) социальный слой между состоянием NPC и DecisionHub.

### DOM-03: PERCEPTION & PHENOMENOLOGY (CFRM)

**Истина:** Объективных фактов нет. Есть возмущения поля, которые проецируются в субъективные феномены.

- ⚪ **S21** Убийство объективных событий. Давление генерирует `PsychologicalPressure`.
- ⚪ **S26** Epistemic Classification. Оценка уверенности (confidence) при классификации.
- ⚪ **S30** CFRM Phase 2. `semantic_seed` (геном нарратива). Проекция теряет энергию/форму.
- 🔴 **S78** ADR-O-143: Somatic Bypass УБИТ. `body_state.pain/shock` проходят через `PerceptualKernel.somatic_urgency`.
- 🔵 **S78** ADR-O-142: State Resolution Binding. Двухуровневая модель сознания. Arousal Gate = FSM MUTATOR.
- 🟢 **S62** DOUBLE TRUTH `threat_gradient` УБИТ. `NPCState.write_to_legacy()` теперь пишет `perceptual_kernel`.
- 🔵 **S83+** ADR-302: SIL, DSTC & SEL (Active Inference). Сдвиг к Активному Выводу.
- 🟢 **S86** ТЗ-02 (Шаг 6): `InterpretationEngine` переведён на чтение `drives_runtime` (L3) вместо `drives_base` (L0). NPC интерпретирует мир на основе текущей деформации.

### DOM-04: SPATIAL & LOCOMOTION

**Истина:** `SpatialQueryService` — единственный авторитет. Движение — результат давления и решения. Фронтенд — интерполятор.

- ⚪ **S10** Запрет `MovementIntent` для микроперемещений (требуется `LocalSteeringIntent`).
- 🟢 **S33** Нормализация префиксов макрозон (LOD0 fix).
- ⚪ **S35** Safe Spatial Fallback. Отмена перемещения при отсутствии узла.
- 🔵 **S46** Убита перезапись позиции игрока из протухшего `player_spatial`.
- 🟢 **S51** GAP9 УБИТ. Реалистичное Пробуждение. Сон блокируется непрерывными скалярами.
- 🔵 **S58** Фронтенд: Физика WASD (Pushout Resolution). Игрок больше не застревает.
- 🟢 **S59** ADR-102: `load_graph()` мёртв. Заменён на `SpatialService.build_for_location()`.
- 🔵 **S61** ADR-114: Spatial Paralysis убит. `graph_compiler.py` создает role-based алиасы.
- 🔵 **S67** ADR-121: Двухслойная топология в graph_compiler. `nodes` (dict) и `boundary_map`.
- 🔵 **S68** ADR-125: Target ID SSOT Clarification. Истина идёт через `intent.target`.
- 🟢 **S76** Новые чанки мира: city_gate, market_square. Формат World Partition (adjacency связи).
- 🔴 **S79** БАГ U ЗАКРЫТ: room_2 удалена из tavern.json. Синхронизированы nodes.
- 🔵 **S79** ДОЛГ 6.2 ПРОТОТИП: Boundary Nodes. `NodeRole.BOUNDARY` в spatial_contracts.py.
- 🔵 **S79** Пять архитектурных открытий: Location ≠ Room, цель = Semantic Target, Boundary Node = интерфейс.
- 🟢 **S80** ADR-O-142A: Arousal Gate — missing wake edge закрыт. Спящий NPC пробуждается при wake_pressure.
- 🔵 **S82.0** ADR-S82.0: Spatial Authority Contract. Строгий контракт единого владельца пространственных данных.
- 🔵 **S83+** ADR-303: Coordinate Truth & Physical World Unification (Map Editor).
- 🟢 **S85.1** ADR-130 Guard: `apply_changes` блокирует перезапись активного транзита (`status="MOVING"`). Устранён баг "бесконечного бега".
- 🟢 **S85.1** Traversal Complete Fix: `apply_changes` обрабатывает `cause="traversal_complete"` как проекцию `local_position` (snap), а не создание нового `TraversalState`.
- 🔵 **S87** ADR-TRAV-FSM: Завершена миграция ownership перемещений. `SceneStateManager` стал единственным владельцем lifecycle (через FSM `transition_traversal`). `TickOrchestrator` и `ProjectionEngine` переведены в read-only. `current_waypoint_idx` пробрасывается в `WorldSnapshotBuilder`. Удалён мёртвый код `models/traversal.py`.
- 🔵 S86 Завершение миграции TZ-08 v0.2 и запуск Epistemic Boundary. DM-агент изолирован от ментальных объектов NPC (stress_delta, recalled_facts и др.). RulesAgent заменён на синхронный RulesSubscriber (pure reducer) в game_loop. build_r3_dm_frame перенесён в game_loop. Ядро больше не генерирует нарратив. Удалён мёртвый метод _phase_finalize из tick_orchestrator.py. Внедрён WorldProjectionBuffer как будущий слой оффскрин-симуляции.
- 🔵 **S87** ADR-TRAV-NOOP: Внедрена State-Based Idempotency в `EventCompiler`. Идемпотентность изменения позиции (`current == target`) определяется инвариантом состояния, а не семантикой события (`cause`). Устранены ложные `[SHADOW_COMPILER] FAILED` при завершении транзитов.
- 🔵 **S88** ADR-ETKE-L0: Заложен фундамент ETKE-IK v1 (Embodied Topology & Interaction Kernel). Созданы DTO непрерывной кинематики (AffordanceVector, BodySchema, DriveVector, KinematicProfile) и вычислительное ядро (SteeringResolver, MotionIntegrator, WorldTopologyProvider). Пайплайн интегрирован в TickOrchestrator как параллельная ветка (_process_continuous_motion). Движение переведено из функции графа в результат преобразования DriveVector через поле возможностей.
- 🔵 **S89** ADR-ETKE-ACT1: CAUSAL_BRIDGE → Motion Routing Layer. Двухконтурная модель движения формализована: `same_node + has_coords` → DriveVector (ETKE-IK, непрерывная кинематика), `different_node` → MovementIntent (Traversal FSM, дискретный граф). Введён `MOTION_ROUTING_THRESHOLD` и жизненный цикл DriveVector (очистка при каждом `tick_decisions`, запись в npc dict, потребление `_process_continuous_motion` на следующем тике по модели T-1). FLEE в same_node = инвертированный вектор (отталкивание, intensity=1.0). SUPERBOX: 351 comparisons, rate 1.755/tick.

### DOM-05: PHYSIOLOGY & COMBAT

**Истина:** Тело — материальный объект. Удар — чистая физика контакта, порождающая боль и шок.

- ⚪ **S16** Каскад Shock → Emotion (ReactionSubscriber извлекает `shock_impulse`).
- ⚪ **S20** Очистка `combat_stats`. Перенос способностей в `body_profile`.
- 🟢 **S54** Хардкод _MOVE_VERBS удален. Semantic Bridge замкнут.
- ⚪ **S57** RPG Витализм: нормализация шкалы `pain` (0-100 → 0-1) в `StateInterpreter`.
- 🔴 **S72** ADR-128: Player injuries LOST. Двойная онтология: wounds (legacy) ≠ body_state (truth).
- 🔴 **S73** ADR-130 G2: Uninvited NPC Approach. `_context_relevance()` не имел fallback на payload.
- 🔴 **S74** P1: Player Combat Snapshot EntityView Shift. Игрок стал симулируемой физической сущностью в бою.
- 🔴 **S75** ADR-094 MSOC: CRITICAL BUG — `pressure_translator.py` читал `pain` без нормализации.
- 🟢 **S75** Контракт шкал физиологии зафиксирован. `pain`/`fatigue` = 0-100, `blood_loss`/`shock` = 0-1.
- 🟢 **S76** NPIC Sentinel: Введена константа BODY_STATE_DISABLED (§ENIGMA-003).
- 🟢 **S76** ADR-140: DM Death Scene Pipeline. DM получает life_status через avatar_to_prompt.
- 🟢 **S77** ADR-141: Убит разрыв Injury → Pain. `InjuryProcessor` генерирует `pain_delta` из свойств раны.
- 🟢 **S86** ТЗ-02 (Шаг 12): DOUBLE TRUTH HP устранена. Канонический источник — `body_state["current_hp"]`. Устаревший `state.hp` оставлен как deprecated-проекция и синхронизируется с `body_state` при уроне.

### DOM-06: SOCIAL & MEMORY

**Истина:** Память многослойна. Социальные акты искривляют utility-space целей.

- ⚪ **S03** Мультисобытийность Perception.
- ⚪ **S08** Обогащение NPC социальными связями из `village_relations.json`.
- ⚪ **S27** Физика Власти. `DirectiveInterpretationSubscriber` транслирует приказы в давление.
- 🔵 **S66** `RelationshipStore` назначен Единственным Источником Истины (SSOT).
- 🟢 **S86** ТЗ-02 (Шаг 11): Контур памяти замкнут с соблюдением инварианта "Memory cannot generate new identity without causal input". `compress_narrative_cache` (структурное сжатие) работает в idle. `check_identity_promotion` (L2.5 кристаллизация) работает только при наличии `phase_2_events` (запрет на фантомный дрейф).

### DOM-07: FRONTEND, PRESENTATION & INPUT

**Истина:** Фронтенд — сенсорный орган игрока. Он искажается, болеет и сопротивляется.

- ⚪ **S18** Создание Персонажа через Вектор Начальных Условий.
- ⚪ **S25** Embodied Vector. Предрефлексивные моторные импульсы.
- ⚪ **S56** The Fool v2 — визуализация моторных следов и тултипов наблюдений замкнута.
- 🔴 **S72** ADR-128: PlayerAvatarService сериализует body_state. Труба аватара замкнута.
- 🔴 **S75** ADR-137: Death Feedback Pipeline замкнут. Death overlay на фронтенде.
- 🟢 **S76** Map Editor: Shift+ЛКМ перетаскивание локаций. Outdoor поддержка.
- 🟢 **S81** Visual: shake amplitude уменьшена в 2 раза. NPC/Player gaze утолщены.
- 🔴 **S82** Убран `return` в обработке клавиши J — вызывал вылет игры. ADR-JOURNAL, ADR-SPEECH.

### DOM-08: OBSERVABILITY (CDS & Sandbox)

**Истина:** Наблюдение не создает причинность. CDS — пассивный аудитор.

- ⚪ **S39** Интеграция CDS. Фронтенд не парсит отчёты симуляции.
- 🟢 **S72** P3: Уборка диагностического шума. Удалены TRACE-принты, понижены до DEBUG.
- 🟢 **S74** Sandbox Tests: 7 тестов для ADR-128/130 по §12.3 Устава.
- 🟢 **S83** ADR-147: LLM Streaming Observability Gate. Убит теневой streaming path, CDS видит execution gate.
- 🟢 **S85.1** SUPERBOX Stabilization: Устранены краши пайплайна (`AttributeError`, `ImportError`, `NameError`) в `L1Chronicle` и `TickOrchestrator`. Достигнут стабильный rate `comparisons=21/15 ticks`.
- 🔵 **S86** ТЗ-02 (Иммунная система): Внедрён Causal Invariant Checker (`backend/tests/sandbox/invariants/`). Тесты `test_hp_double_truth_invariant` и `test_l3_ephemeral_invariant` защищают систему от будущих разрывов между физикой, L0 и L3.

### DOM-09: SOCIAL & AFFECTIVE ARCHITECTURE (SSOT & Causal Derivation)

**Истина:** Отношения — это граф (ребро). Аффективная нагрузка — интеграл с гистерезисом.

- 🔵 **S63** `load_l2_state_from_runtime_dict()` — добавлены 5 полей в конструктор.
- 🔵 **S75** Убит Вечный Двигатель Страха (ADR-138). Асимметричный Аттрактор (Гистерезис).
- 🔵 **S76** ADR-O-140 спроектирован: World Partition Topology.
- 🔴 **S78** ADR-O-143: Somatic Bypass УБИТ. Боль/шок переведены в `PK.somatic_urgency`.
- 🔵 **S83+** ADR-O-206: Emotional Residue Isolation Protocol. Эмоциональный остаток изолирован.

### DOM-10: IDENTITY & ONTOLOGY (Identity Layer & Chronicle)

**Истина:** Идентичность — это фазово-заблокированное поле дрейфа, кристаллизующееся во времени.

- 🔵 **S83+** ADR-GL-203: Error-geometry System & Dynamic Ontology. Эпистемология ENIGMA.
- 🔵 **S83+** ADR-O-207: Runtime Ontology Collapse Plan. Post-Commit Validation Gate (OntologyViolationError).
- 🔵 **S83+** ADR-O-208: DRIVE RESOLUTION PIPELINE (DRP). L1Chronicle + DriveResolver.
- 🔵 **S83+** ADR-O-209/210: Phase-Locked Identity & Bounded Spatial Field Coupling.
- 🔵 **S83+** ADR-O-211: Calibration Engine & Identity Stability Kernel.
- 🔵 **S83+** ADR-TIFL-001: Temporal Identity Formation Layer.
- 🔵 **S83+** ADR-TIFL-002: Identity as Competitive Drift Field (ICDF).
- 🔵 **S83+** ADR-TIFL-003: Identity Constraint Layer & Thermodynamic Crystallization.
- 🔵 **S84** ADR-O-306: Epistemic Heterogeneity & Triple Membrane. L1 Chronicle = персонализированная хроника. Тройная Мембрана (Физика, Личность, Социум) фильтрует L1. InstitutionLayer модулирует пороги PerceptualKernel.
- 🔵 **S84** ADR-O-307: Asymmetric Trauma & Belief Revision. Введён множитель x6 для опровержений. Belief формируется только от personal_persistence.
- 🟢 **S84** P0 FIX: ADR-101/112 (Rule X). BehaviorManifestationService переведён на чтение body_state и PerceptualKernel. Удалён скрытый канал affective_velocity.
- 🟢 **S84** P0 FIX: ADR-102. Вырезан fallback на load_graph() из npc_tick_pipeline. SpatialService становится единым fail-closed авторитетом.
- 🟢 **S84** P0 FIX: ADR-134. Удалён default_factory=DRFBus в _TickContext. Шина DRFBus стала instance-level, Split-Brain устранён.
- 🟢 **S84** P0 FIX: ADR-S85.2. Из архетипов (guard, blacksmith, merchant, tavern_keeper) удалён activity_map. Пространственная привязка теперь строго на уровне индивидов.
- 🔵 **S84** ADR-O-305 / 305A: Belief Crystallization Engine & Evidence Semantics. Зафиксирован контракт L1->L1.5->L2.5. PatternDetector объявлен чистым статистическим слоем. Написаны 8 BDD-тестов (песочниц) для L1.5.
- 🟢 **S85** ТЗ-1: Массовый фикс silent failures и скрытых багов (Шаги 1-8). 
  - `dm_agent.py`: Убит `try/except: pass`, маскировавший неверный импорт `SceneStateManager`.
  - `scene_outcome_builder.py`: Фикс `NameError` при генерации блока "Ключевые NPC" для DM.
  - `routes.py`: Убрана trailing comma (tuple bug), Windows-путь `error.log` заменён на относительный, добавлен отсутствующий `logger`.
  - `dm_router.py`: Фикс опечатки `player_fleses`, убраны `except Exception: pass` для `_INSULT_ROOTS` и `_MORPH`.
  - `intent_compressor.py`: Очищены мусорные леммы (`весь`, `дурь`), добавлено логирование LLM-ошибок в `slow_path_parse`.
  - `mock_provider.py`: Добавлена защита от утекания Mock-ответов в production через `ENIGMA_ENV`.
- ⚪ **S85** ТЗ-1: Архитектурная ревизия опциональных зависимостей. `pymorphy3` переведён в статус Optional Dependency. Внедрён Degraded Mode: при отсутствии пакета NLP-обработка деградирует до regex-only с `WARNING` в лог, но каузальный конвейер не падает. Файл `backend/config.json` переименован в `.deprecated` (мёртвый код с захардкоженными путями).
- 🟢 **S85.1** TraitDriftEvent Contract Fix: `BreakProgressEngine` и `L1Chronicle` переведены на новые поля ADR-O-208 (`target_id`, `tick_id`, `effect_value`). Удалены обращения к устаревшим `npc_id`, `tick`, `trait`, `delta`.
- 🔵 **S85.2** ТЗ-2: Реализован L1.5 (PatternDetector). `TraitDriftEvent` и `EvidenceOfPersistence` переведены на строгий контракт ADR-O-305A. Внедрена комбинированная `behavior_variance` (стат. дисперсия + временная осцилляция). `event_type` физически отсечён от математики.
- 🔵 **S85.2** ТЗ-3: Реализован L2.5 (BeliefCrystallizationEngine). Внедрена `CrystallizedBelief` (source_id, trait, weight). Реализована Асимметричная Травма (x6 множитель при опровержении, ADR-O-307).
- ⚪ **S85.2** L2.5 Integration: В `npc_tick_pipeline.py` внедрён `CrystallizedBeliefModifierResolver` для инъекции убеждений в `DecisionHub`. В `TickOrchestrator` (Фаза 9) замкнут контур генерации L1 -> L1.5 -> L2.5.
- 🟢 **S85.2** Belief Decay Model: Внедрена энтропия убеждений (`BELIEF_DECAY_TAU`). Убеждения растворяются без подкрепления, предотвращая статическую кристаллизацию личности.
- 🔴 **S86** ТЗ-02 (Шаг 9): `L1Chronicle` стал персистентным (SQLite). Внедрена схема `l1_chronicle_events`. DI замкнут от `GameLoop` до `L1Chronicle`. Контракт `TraitDriftEvent` (`target_id`, `tick_id`, `effect_value`) полностью канонизирован.
- 💀 **S86** ТЗ-02 (Шаг 10 ОТМЕНЁН): Применение `ctx.drives_updates` к `state.drives_runtime` ЗАПРЕЩЕНО. `CalibrationEngine` оставлен в pass-through режиме. Мутация скалярных драйвов минуя Belief Layer (L2.5) нарушает ADR-O-208/211. L3 проекция строго эфемерна.
- 🔵 **S88** Epistemic Boundary (Symbolic Interpretation Layer): DM-контур переведён на символьную интерпретацию. `stance_from_decision` и `_project_psychology` переведены на чтение `observed_state` и `intent`. Числовые пороги `stress/fear/trust` удалены из вербализации.
- 🔵 **S88** WorldProjectionBuffer (Shadow Causality): Реализован как pure function (ADR-O-309). Инкапсулирован внутри `SceneStateManager.commit()`. Внедрён strict temporal sealing (diff state_t vs state_t-1). `TickOrchestrator` очищен от логики истории состояний.
- 💀 **S88** LLM Context Exile: Функция `build_verbalization_context` полностью удалена из ядра симуляции (`npc_tick_pipeline.py`). Ядро больше не формирует промпты.

### DOM-04: SPATIAL & LOCOMOTION (S90 AUDIT)

- 🔵 **S90** ADR-S90.1: WorldTopologyProvider v1. `SpatialService` расширен хранением `rooms_geometry` (полигоны). Введён `is_point_in_bounds(x, y)`. `WorldTopologyProvider` формирует non-uniform `AffordanceVector`.
- 🔵 **S90** ADR-S90.2: Motion Policy Layer. Введён `Enum MotionPrimitive` (APPROACH, FLEE, RETREAT, PATROL). `LifeEngine` генерирует 4-элементный `drive_vector`. Интенсивность FLEE модулируется `affective_load`.
- 🔵 **S90** ADR-S90.3: CollisionAvoidance. Внедрён реактивный слой в `motion_pipeline.py` (до `SteeringResolver`). Проверяет `Affordance` впереди движения и смещает вектор перпендикулярно при `can_pass < 0.5`.
- 🔵 **S90** ADR-S90.4: MotionRenderRouter. Фронтенд реализует гибридный рендер: `velocity` (ETKE-IK) → инерция; `active_traversals` (FSM) → `path_waypoints`. `NPCPositionDTO` расширен.

### S91: STIGMERGY & SOCIAL DRIFT (Cognitive Motion)

- 🔵 **S91** ЭТАП 1: DynamicAffordanceField (Dual-Layer). Введён state-object для стигмергии. Слой 1: Hard Overrides (`DeformationRecord`, Absolute Override, TTL). Слой 2: Soft Traces (`TracePayload`, накопление, decay). `WorldTopologyProvider` стал чистым фасадом. `TickOrchestrator` владеет персистентным инстансом. Очистка в Фазе 0.5 (`purge_hard_overrides`, `step_decay`).
- 🔵 **S91** ЭТАП 2: SocialTraceField. Внедрена эмиссия поведенческих следов: `movement_density` (в `_process_continuous_motion`) и `safety_confidence` (в `_apply_phase8_result`). Следы накапливаются и влияют на `AffordanceVector` (например, толпа увеличивает `drag_coefficient`).
- 🔵 **S91** ЭТАП 3: Motion Router & Social Drift. 
  - Внедрено NPC-to-NPC Collision Avoidance с Velocity Awareness (предсказание позиций).
  - `PATROL` примитив заменён на `SOCIAL_DRIFT`.
  - Внедрён Intent Attribution Layer: NPC выбирает социально значимый якорь (бар, вход, стол, группа NPC) на основе Intent Scoring (потребности + угроза) и Memory Bias (anchor_affinity).
- 🔵 **S91** ТЗ-05: LLM Contract & DM-Agent Repair. 
  - Внедрён DM Output Contract Layer (`DMResponseNormalizer`).
  - Валидатор очищен от эвристик: восстановлена статистическая фильтрация (A6), убрано ложное срабатывание на тире (A5), удалён `_force_static` (B5).
  - Внедрена блокировка повторов через `recent_text` (A4).
  - `max_tokens` вынесен в `config.py` (A7).
  - В промпт и `DMContractBuilder` добавлены строгий JSON-формат и динамический forbidden-блок (B1/B2/B3).
  - `MockProvider` заблокирован в production (B4).
  - После аудита зависимостей удалён мёртвый код: `parser.py`, `npc_response_validator.py`, 4 cloud-провайдера (C2/C3/C5).

---

## 2. АРХИТЕКТУРНЫЕ ЗАПРЕТЫ (Синхронизировано с ADR Master Index)

### State & Mutation
1. ❌ Прямая мутация стейта в обход `DeltaBuffer`
2. ❌ Циклы `tick()` для нагона времени (`TICK_CATCHUP`)
3. ❌ Формирование ответа Фазы 8 через `List[dict]`
4. ❌ Подмена `campaign_id` на `location_id` в `_TickContext`
5. ❌ `if state.body_state:` (falsy dict) — использовать `is not None`
6. ❌ Переход `DEAD → ALIVE` через обычную физиологию
7. ❌ Снятие `_tick_locked` после вызова сохранения состояния
8. ❌ Прямая запись в `state.hp` в обход `body_state["current_hp"]` (HP Double Truth) (ADR-HP-UNIFICATION)

### Will & Decision
9. ❌ Вызов WillpowerGate более 1 раза за цикл
10. ❌ Использование RPG-матриц поведения как онтологии
11. ❌ Передача сырых дельт давления из текущего тика в DecisionHub (только T-1)
12. ❌ Возврат дефолтного `EmotionalVector` (aggression=0.0) из `IntentCompressor` для ATTACK
13. ❌ Использование переменных из локальной области другой функции (Python scoping trap)
14. ❌ Чтение `intent.action` без fallback на `parameters.semantic_action`

### Spatial & Movement
15. ❌ Использование `load_graph()` — мёртвый код
16. ❌ Сравнение legacy ID с canonical ID без `normalize_id()`
17. ❌ FLEE без исключения текущего узла NPC из кандидатов
18. ❌ Левый верхний угол комнаты как позиция узла в навигационном графе
19. ❌ Перезапись `local_position` для NPC в статусе `MOVING`
20. ❌ Прямая мутация `npc["position"]` или `npc["location"]`
21. ❌ Чтение позиций из `scene_state` (только `SpatialQueryService`)
22. ❌ Вызов `scene_manager.apply_changes()` из подписчиков
23. ❌ Вызов `process_intents()` или `apply_changes()` из `npc_orchestration.py`
24. ❌ Повторная обработка `MovementIntent` (инвариант `processed=True`)
25. ❌ `_enrich_local_positions` перетирает `local_position`, установленный пайплайном
26. ❌ `graph_compiler.py` без role-based aliases
27. ❌ `SpatialQueryService.visibility()` с неправильным порядком аргументов
28. ❌ CEI-2 использует `is_movement_blocked` для макро-навигации
29. ❌ spatial_runtime consumer-функции без `normalize_scene_state()`
30. ❌ Boundary node как цель движения или место обитания NPC
31. ❌ Перезапись активного транзита (`status="MOVING"`) в `apply_changes` (ADR-130 Guard)
32. ❌ Создание нового `TraversalState` для `cause="traversal_complete"` (нужен только snap `local_position`)

### Perception & Phenomenology
33. ❌ Хранение `EventDTO` в `EventBuffer` (только `FieldDisturbance`)
34. ❌ Обход `LocalCausalSolver` при генерации давления
35. ❌ Мутация состояния из `CausalObserver`
36. ❌ Прямая генерация эмоций из боевых событий (только через Perception)
37. ❌ `write_to_legacy` / `from_legacy` без `perceptual_kernel` и `affective_load`
38. ❌ Показ эмоций (fearful, anxious) — только наблюдаемые проявления (tense, rigid)
39. ❌ Смешивание cues и manifestations — отдельные каналы
40. ❌ Вычисление manifest в GameScreen — только чтение из perception data
41. ❌ Инъекция pain/shock напрямую в psyche dict (только через PK.somatic_urgency)

### Physiology & Combat
42. ❌ Прямая мутация HP аватара в обход `ImpactEngine`
43. ❌ `CombatSubscriber` пишет в Emotion (Domain Leakage)
44. ❌ `BehaviorManifestationService` читает эмоции вместо физиологии (Rule X)
45. ❌ Вызов `publish_classified_player_event` ДО `resolve_player_intent`
46. ❌ `shock_impulse` без decay в `PhysiologyDecayHandler`
47. ❌ `StateApplicator` проверяет `shock_impulse > 0.0` вместо `!= 0.0`
48. ❌ `NPCStateSnapshot` без поля `shock_impulse`
49. ❌ `PhysiologyDecayHandler` без проверки `life_status == "DEAD"`
50. ❌ `evaluate_vital_state` без DEATH LOCK
51. ❌ Двойная онтология: `wounds/conditions` (legacy) ≠ `body_state` (runtime truth)
52. ❌ Обработка player action без проверки `life_status`
53. ❌ `_make_player_snapshot()` без чтения `avatar_state.body_state`
54. ❌ Чтение `pain`/`fatigue` без нормализации `/100.0` в потребителях с порогами 0-1 (MSOC)

### Frontend & Presentation
55. ❌ Булева блокировка коллизий игрока (только Push-out Resolution)
56. ❌ Перезапись `result.world_snapshot` целиком в `game_loop_bridge.py`
57. ❌ Применение моторных смещений ПОСЛЕ отрисовки спрайта
58. ❌ Импорт `backend/app/` во фронтенд (Устав §1.1)
59. ❌ Передача игроку внутренних метрик NPC (HP, fear)
60. ❌ DM читает внутренние состояния NPC вместо `embodied_traces`
61. ❌ Фейковый нарратив при краше LLM ("Твоё сознание мутнеет...")

### Serialization & Persistence
62. ❌ `write_to_legacy` / `from_legacy` без `body_state`
63. ❌ Прямой конструктор `NPCState(...)` в тестах (только `from_legacy`)
64. ❌ `_apply_runtime_overlay` без белых списков для вычисленных полей (Invariant 1)
65. ❌ Персистенция `relationship_cache` внутри `NPCState` (SSOT = RelationshipStore)
66. ❌ Использование интегратора с утечкой для `affective_load` (только аттрактор насыщения)
67. ❌ Отсутствие idle-decay для `PerceptualKernel` (Rule 38)
68. ❌ AFFECTIVE_BOOT / подтягивание `affective_load` до порога `emotion_tag`
69. ❌ LifeEngine `_load_npcs()` без SQLite read-back
70. ❌ `load_npc_runtime()` возвращает `[]` вместо `None`

### Identity & Ontology
71. ❌ Кэширование `EffectiveDrives` (L3-P1 эфемерна)
72. ❌ Удаление событий из `L1Chronicle`
73. ❌ Коммит состояния с NaN или sum(drives) != 1.0 (OntologyViolationError)
74. ❌ Viability veto через `_drf_killed` или парсинг строк (только IntentDomain gate)
75. ❌ `MovementIntent` без поля `domain`
76. ❌ Чтение устаревших полей (`npc_id`, `tick`, `trait`, `delta`) из `TraitDriftEvent` (использовать `target_id`, `tick_id`, `effect_value`)
77. ❌ Использование `event_type` в математических формулах L1.5 (PatternDetector) (ADR-O-305A)
78. ❌ Наличие полей `trait`/`emotion` в `PatternDetector` или `EvidenceOfPersistence` (нарушение ADR-O-306)
79. ❌ `BeliefCrystallizationEngine` читает `L1Chronicle` напрямую (работает только через `EvidenceOfPersistence`) (ADR-O-305)
80. ❌ Скалярный страх (`CrystallizedBelief` без `source_id`) / Отсутствие `Decay` для `CrystallizedBelief`
81. ❌ Мутация `state.drives_runtime` (L0) минуя Belief Layer (L2.5) через `CalibrationEngine` (ADR-O-208/211)
82. ❌ Запуск L2.5 кристаллизации (`check_identity_promotion`) в idle-тиках без `phase_2_events` (фантомный дрейф личности)