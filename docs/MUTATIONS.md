# MUTATIONS.md — Каузальная Эволюция ENIGMA

> **Формат:** Домен → Хронология сессий → Запреты. Ищи по `Ctrl+F S##` или домену.

---

## МЕТА

| Показатель | Значение |
|------------|----------|
| Сессий | 118|
| Доменов | 10 |
| Консолидированных запретов | [DERIVED: count(ADR.*.Taboo)] |
| Диапазон | S03—S97 |

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

- 🔵 **S96** Actor-Agnostic Spatial Contract (ADR-O-314).
  - **Проблема:** `TickOrchestrator` парсил текст игрока ("подойди ко мне") и вычислял дистанции, чтобы угадать, кто идёт (актор), нарушая слоевую архитектуру и принцип Epistemic Grounding (§13.2). Существовало легаси-дублирование `player_spatial` рядом с `npc_positions["player"]`.
  - **Решение:** 
    - Введён доменный контракт `MovementRequest(actor_id, target_actor_id)`.
    - `LocalSteeringGoal` переведён с `npc_id` на `actor_id`.
    - `IntentSemanticField` и `IntentParametersDTO` расширены полем `actor_reference` / `actor_id`.
    - Слой Интерпретации (`intent_compressor.py`, `phase_1_input.py`) обновлён для извлечения актора через LLM/Fast-Path и сборки `MovementRequest`.
    - `TickOrchestrator._process_player_dm_action` очищен от 80 строк спагетти-кода (угадывание цели, вычисление дистанции). Теперь он просто читает готовый `MovementRequest`.
    - Хак синхронизации `player_spatial` в `SceneStateManager` удалён. Единственный источник истины позиций — `npc_positions["player"]`.

- 🔵 **S89** ТЗ-09: Execution Pipeline Collapse.
  - Уничтожено ветвление `_phase_5_player_decision` / `_phase_5_decision`. 
  - Введены `TickState` (deep immutable snapshot) и `TickMutation` (pure result).
  - `NpcTickPipeline.run()` стал единственным execution kernel. Временная зависимость от `svc` оставлена до Фазы 4.
  - `TickOrchestrator._phase_5_decision` собирает снимок, вызывает редюсер и применяет мутации.
  - `GameLoop.idle_tick` нормализует среду в `InterventionEvent`.
  - Устранены побочные эффекты: `FrozenInstanceError` (через `dataclasses.replace`), `MappingProxyType` pickle error (через `deepcopy`).

- 🔵 **S97** ТЗ-10: Pure Reducer Completion & Svc Strangulation.
  - Завершена миграция `NpcTickPipeline.run()` в чистую функцию. Параметр `svc: Any` удалён из сигнатуры.
  - Внедрён Strangulation Pattern: `TickState` расширен блоками `preloaded_*` (memory_weights, narrative_cache, social_mods, reputation, economic_profiles, beliefs, traits) для предзагрузки оркестратором.
  - `TickMutation` расширен `l1_drift_events` и `memory_events` для отложенного применения I/O-мутаций.
  - `TickOrchestrator._phase_5_decision` теперь загружает данные ДО вызова `run()` и применяет отложенные мутации ПОСЛЕ.
  - `apply_perception_memory` и `create_memory_event` переведены в режим возврата `EventDTO` без I/O при `memory_manager=None`.
  - DriftLaboratory (3 тика): 0 ошибок, comparisons=4, гейты стабильны.

- 🔵 **S98** ТЗ-06: Dead Code Cleanup & Engineering Debt.
  - **Patch Set A (Dead Code Removal):** Удалены мёртвые методы (`_draw_input_bar`, `_advance_time_by_movement`, `_build_intro_prompt`, `can_proceed`, `add_npc_author_notes`). Удалены мёртвые поля (`PlayerMemory`, `EncounterHistory`). Удалён дублирующий импорт `settings` в `routes.py`. Вычищены мёртвые комментарии и docstrings про `TransitTracker` и `LocationGraph`.
  - **Patch Set B (Production Hygiene):** `print()` в `movement_engine.py`, `tick_orchestrator.py`, `dm_agent.py`, `game_loop_bridge.py` заменён на `logger.debug` с feature-флагами (`movement_debug`, `orchestrator_debug`, `dm_debug` в `config.py`). `except Exception: pass` заменён на `logger.warning` (16 файлов). `asyncio.get_event_loop()` заменён на `get_running_loop()`. `ActionQueue.poll` ловит только `queue.Empty`. `WillState` унифицирован (реэкспорт из `npc_state.py`). `compute_continuous_drift` возвращает `list`.
  - **Patch Set C (Constants & i18n):** 23 магических числа вынесены в `constants.py`. `MSG_*` константы вынесены в `constants.py`. Добавлены i18n ключи для меню, заменены хардкоды в `game_menu.py`. Нормализация `gender` в `state_interpreter.py` и `shadow.json`. `RelationshipStore` переведён на `OrderedDict` с LRU и TTL.
  - **Validation:** Создан `backend/tests/test_tz6_cleanup.py` (10 тестов, все проходят).

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
- 🔵 **S93** ADR-O-301: Kernel Isolation Repair v0.1. Внедрён `KernelRNG(tick, npc_id, salt)`. Убиты 5 утечек детерминизма (`random.*` в kernel layer) и 3 голых `DecisionHub()`. Создана единая фабрика `rng_factory` в `_TickContext`. Подсистемы (DecisionHub, LifeEngine, MovementEngine, StateApplicator) изолированы через `salt`. SUPERBOX: rate=1.540/tick.
- 🟢 **S93** ADR-S93.1: Dead NPC Execution Lock. Мёртвые NPC (`life_status="DEAD"`) полностью исключаются из `ctx.all_npcs_raw` в `_run_core_phases` до Фазы 1. Устраняет "зомби-движение".
- 🟢 **S104** ФАЗА 2: Аффективный и идентификационный слои (Шаги 2.2, 2.3, 2.4).
  - **Шаг 2.2 (ADR-O-206): Emotional Residue Isolation.** Три surgical cuts:
    1. `ImportanceEngine`: Удалён параметр `emotion_tag`. Важность памяти вычисляется строго от `prediction_error` (Surprise).
    2. `MemoryManager`: Скорость забывания (`decay_rate`) вычисляется на основе `importance`, а не тега.
    3. `AffectiveIntegrator`: Формула шрама (`_scar_rate`) сделана нелинейной (`0.1 + 0.4 * (_abs_error ** 1.5)`). Память перестала быть "скрытым источником энергии" (убрано сложение `current_memory` в `current_load_adjusted`), теперь она формирует ожидание (prior), а нагрузка вычисляется как функция от ошибки предсказания.
  - **Шаг 2.3 (ADR-O-208): DriveResolver Pipeline (L0→L1→L3).** Уничтожены фоллбэки на L0 (`drives_base`) в `npc_tick_pipeline.py` и `life_engine.py`. `InterpretationEngine` и `VerbalizationContext` переведены на чтение эфемерной проекции из `state.effective_drives_map`. `TickOrchestrator` больше не читает `_prev_runtime` (кэш L3), а `StateApplicator` блокирует прямую мутацию `drives_runtime`. L3 стала строго эфемерной (L3-P1).
  - **Шаг 2.4 (ADR-O-304): Trait Stabilization Hysteresis.** Внедрена гистерезисная модель активации черт (Trait Dynamics) в `StateApplicator`. Добавлено поле `trait_activation` в `NPCState` (с полным round-trip в сериализации). Энергия активации накапливается нелинейно и превышает `THETA_UP` для активации, удерживается до `THETA_DOWN` (dwell_time), что устраняет мерцание черт.
  - **Шаг 2.1 (ADR-O-205) ОТЛОЖЕН:** Внедрение 3 изолированных проекций (Motor/Narrative/Mnemonic) отложено до реализации масштабного онтологического сдвига "Presentation v2.0" (ObservableSignals Contract, ManifestationPolicy, Three-Channel Presentation).
  Files: docs/audits/ADR-O-206_IMPACT.md, backend/app/services/memory/importance_engine.py, backend/app/services/memory/memory_manager.py, backend/app/services/affective/affective_integrator.py, backend/app/services/affective/affective_decay_handler.py, backend/app/services/tick_orchestrator.py, backend/app/services/npc/state_applicator.py, backend/app/services/npc/npc_tick_pipeline.py, backend/app/services/npc/life_engine.py, backend/app/models/npc_state.py, backend/app/core/constants.py
- 🔵 **S94** ТЗ-03: Frontend ↔ Backend Contract Repair. Устранена tri-ontology system. Установлена Single Causal Authority. A1: `GameActionResponse` расширен `scene_state` и `metadata`. A2: `WorldSnapshotDTO.npc_positions` канонизирован как `Dict[str, NPCPositionDTO]`, адаптер удалён. A3: `PeripheralCueDTO.cue_type` → `cue_key`. B1: Frontend authority removal (5 sub-fixes): фронтенд лишён права генерировать время, аватара, журнал. B2: Spatial Oracle no-silent-failure. B3: Dual-channel architecture (`idle_tick` остаётся causal clock, `get_world_state` добавлен как observational layer). C1: `contextlib.suppress(Exception)` заменён на явный `try/except`. C2: `_MinimalFrontendRegistry.find_chunks` добавлен. Создан `backend/tests/test_tz3_contract_repair.py` (11 тестов).
- 🔵 **S95** ADR-O-302: Physics Overlay. Введены §14 (Закон Единичного Времени) и §15 (Закон Изоляции Реального Времени). `REAL_TIME_BRIDGE` (`reconcile_state`) изолирован, магическое число `10.0` заменено на `GAME_TICK_INTERVAL_SECONDS`. `INTERPOLATION_TIME` (`ETKE_IK_SUBSTEP_DT`) выведен в константу, магические `0.1` убиты в `motion_pipeline.py` и `tick_orchestrator.py`. Мёртвый код `get_world_ticks_elapsed` и `get_idle_seconds` удалён. Аффективный декэй переведён на `GAME_TICK_INTERVAL_SECONDS` и `AFFECT_DECAY_BASE_RATE`. Обнаружен и устранён баг `SHI=0%` (метод `on_individual_decision` находился в `TickHealthReport`, а не в `TickHealthChecker`, вызывая `AttributeError`).
- 🔵 **S96** ТЗ-04: Spatial Authority & Physics Repair (Patch Set A+B). Устранены зомби-ридеры `player_distances` (A1-A3), `random.uniform` в `apply_change` заменён на `KernelRNG` (A4). Удалены мёртвые модули `transit_tracker.py` и `location_graph.py` (A5). `game_loop_bridge.py` переведён на логирование ошибок вместо `except: pass` (B1). Введена единая фабрика `SpatialFactory` (B3). Прямые мутации `activity`/`initiative_suppression` и `line_of_sight` переведены на маршрутизацию через `SceneChange` (B4-B5). Создан `test_tz4_spatial_authority.py` (12 тестов).
- 🔵 **S102** Шаг 4: Non-Blocking Backend Startup (DEBT-STARTUP-1). `yield` в FastAPI lifespan перемещён перед llama-server spawn (до 120с блокировки) и LLM health check (до 30с). Медленные операции → `asyncio.create_task(_background_llm_startup)`. Статус записывается в `app.state.startup_status` (ключи: `llm_server`, `llm_health`). `/health` endpoint расширен полем `startup` для фронтенд-поллинга. `time.sleep` → `asyncio.sleep`. Shutdown корректно отменяет задачу и синхронизирует `_llama_server_proc` для atexit. DriftLaboratory: 73 comparisons, rate=1.460/tick, 0 errors.
  Files: main.py, api/routes.py
- 🟢 **S103** ФАЗА 0+1: Документная гигиена + Rule 120 Surgery (ADR-O-204 Phase 3).
  - **Фаза 0 (3 задачи из 7):** Заполнены ADR-O-310_IMPACT.md и ADR-O-311_IMPACT.md (11+11 строк реального контента). RUNTIME ARCHAEOLOGY MAP обновлён до v3.1 (добавлены KernelRNG×3, InterventionEvent, TimeSkipExecutor, секция C5). CAUSAL CONTRACT §4.5.21 уточнён: `birth_tick` (chronicle index) ≠ `birth_time` (game_time_seconds). Остальные 4 шага (переименования, архивация, дедупликация, удаление мёртвого кода) уже выполнены в прошлых сессиях.
  - **Фаза 1 Шаг 1.1 ПРОПУЩЕН:** Порог 100k comparisons признан избыточным эмпирически: при 317 comparisons drift_B=134 (42.3%) доказал двойное создание traversal без накопления статистики. `phase3_ready()` в DriftLab исправлен (убран порог 100k).
  - **Фаза 1 Шаг 1.2 Rule 120 Surgery:** Устранён drift_B=134→0. Три изменения: (1) TickOrchestrator — ProjectionEngine записывает ThickSceneChange ДО legacy apply; (2) SSM — не дублирует traversal если ProjectionEngine уже записал; (3) EquivalenceValidator — сравнивает `fields.status` вместо `contract.status` (устранял семантический разрыв MOVING vs NEW). Rule 6 (direct status mutation) УЖЕ соблюдён — пропущен. DriftLaboratory: 365 comparisons, rate=1.825/tick, drift_B=0, phase3_ready=True.
  - **Новые баги обнаружены (не в рамках surgery):** `merchant_goran` теряет position при переходе city_gate→tavern (NO_POSITION warning). Не фиксится — вне scope Фазы 1.
  Files: docs/audits/ADR-O-310_IMPACT.md, docs/audits/ADR-O-311_IMPACT.md, docs/RUNTIME ARCHAEOLOGY MAP.md, docs/00_CAUSAL_CONTRACT_v2.0.md, docs/ADR (Architecture Decision Records).md, backend/tests/sandbox/SUPERBOX/drift_laboratory.py, backend/app/services/tick_orchestrator.py, backend/app/services/scene_state_manager.py, backend/app/services/equivalence_validator.py

- 🔵 **S104** Декомпозиция Фаз 0.5 и 9 (Оркестратор).
  - **Археология FLEE_NAV (Task 1):** Гипотеза S100 о mismatch `location_id` оказалась ложной. `tavern.json` содержит `"location_id": "tavern_silver_wolf"`, что совпадает с `DEFAULT_LOCATION_ID`. Micro-FLEE fallback из S100 сохранён как safety net.
  - **Декомпозиция Фазы 0.5 (Task 2):** Создан `phases/idle_services.py` (~110 строк). Вынесены L1Chronicle TTL, DynamicAffordanceField purge/decay, PE Decay, Affective Decay, Perceptual Decay, Idle Handlers. Внедрён `Phase0_5Deps`. Оркестратор сокращён на ~105 строк.
  - **Декомпозиция Фазы 9 (Task 3):** Создан `phases/affective.py` (~160 строк). Вынесен `_run_affective_pipeline`. Внедрён `Phase9Deps`. Инвариант ADR-S96.2 сохранён. Оркестратор сокращён на ~160 строк.
  - DriftLaboratory: comparisons=4, 0 errors.
  Files: backend/app/services/tick_orchestrator.py, backend/app/services/phases/idle_services.py, backend/app/services/phases/affective.py

- 🔵 **S105** Декомпозиция остатка Фазы 9 (Integration).
  - Создан `phases/integration.py` (~150 строк). Вынесен `_phase_9_integration` (CFRM P2, L2.5 Belief Crystallization, WorldSnapshot Assembly).
  - Внедрён `Phase9IntegrationDeps`.
  - Ленивая инициализация `_manifest_svc` и `_project_svc` сохранена в обёртке оркестратора.
  - Smoke-test: `TickOrchestrator` инициализируется без ошибок, `_phase_9_integration` доступен.
  Files: backend/app/services/tick_orchestrator.py, backend/app/services/phases/integration.py

- 🔵 **S107** Декомпозиция Фазы 5 (Preload Data) и ревизия `phases/`.
  - В `phases/decision.py` добавлена `assemble_preloaded_data`. Из `_phase_5_decision` убрана ручная сборка мапов памяти, социума и убеждений.
  - Проведена ревизия всех модулей в `backend/app/services/phases/`. Подтверждено использование lazy imports, циклических зависимостей нет.
  - Фаза 8 (`_phase_8_drain_secondary`) проверена — уже является тонкой обёрткой.
  Files: backend/app/services/tick_orchestrator.py, backend/app/services/phases/decision.py

- 🔵 **S108** Декомпозиция Фаз 0, 6, 7 (Simulation & Post-Decision).
  - Создан `phases/simulation.py` (~65 строк). Вынесен `_phase_0_simulation` (LifeEngine tick, Spatial changes injection).
  - Создан `phases/post_decision.py` (~120 строк). Вынесены `_phase_6_post_decision` (IntentEventAdapter) и `_phase_7_windup_resolution` (Windup Registry Gate).
  - Smoke-test: `TickOrchestrator` инициализируется без ошибок, все методы доступны.
  Files: backend/app/services/tick_orchestrator.py, backend/app/services/phases/simulation.py, backend/app/services/phases/post_decision.py

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

- 🔵 **S106** Декомпозиция Фазы 1 (WillpowerGate).
  - Создан `phases/input.py` (~170 строк). Вынесены `_phase_1_input` (Cumulative Strain Model, Affective Resonance) и `_publish_player_intent`.
  - Внедрён `Phase1InputDeps`.
  - Инварианты ADR-031, ADR-036, ADR-039 сохранены.
  - Smoke-test: `TickOrchestrator` инициализируется без ошибок, методы доступны.
  Files: backend/app/services/tick_orchestrator.py, backend/app/services/phases/input.py
- 🟢 **S86** ТЗ-02 (Шаг 7): `BreakProgressEngine.calculate` подключен к `_phase_5_decision` (до DecisionHub). `WillState.BROKEN` достижим.
- ⚪ **S86** ТЗ-02 (Шаг 8): `BehaviorMask` назначается на основе state. Введён как гистерезисный (квазистабильный) социальный слой между состоянием NPC и DecisionHub.
- 🔵 **S93** ADR-S93.2: Secondary Cognitive Contour. Внедрён `PEModifierResolver` и `ExpectationStore`. Ожидания преобразуются в `drive_modifiers` через `tanh` и `Clamp` (0.25). `StateApplicator` — Single Writer для EMA. Затухание ожиданий привязано к `dt_game` в Фазе 0.5.

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
- 🟢 **S97** ADR-O-201.4 Rule 120 Drift Fix: `EventCompiler` (Shadow Compiler) перестал генерировать `TraversalContract(status="COMPLETED")` для `cause="traversal_complete"` и boundary snap. Устранён дрейф `Rule 120`: SSM (владелец lifecycle) удалял терминальный транзит при cleanup, а Shadow оставал его в контракте. Теперь Shadow возвращает `traversal=None`.
- 🔵 **S109** Декомпозиция ETKE-IK и Shadow Observer.
  - Создан `phases/motion.py` (~105 строк). Вынесен `_process_continuous_motion` (SteeringResolver, MotionIntegrator, CollisionAvoidance, Stigmergy).
  - Создан `phases/traversal.py` (~195 строк). Вынесены `_process_traversals` (STL Phase 1, Boundary Resolution) и `_apply_with_shadow_observation` (Dual Rail Execution).
  - Smoke-test: `TickOrchestrator` инициализируется без ошибок, все методы доступны.
  Files: backend/app/services/tick_orchestrator.py, backend/app/services/phases/motion.py, backend/app/services/phases/traversal.py
- 🔵 **S97** ТЗ-09 (Декомпозиция Шаг 1-2): Из `tick_orchestrator.py` вынесены `drf_bus.py` (`DRFBus`, `DRFExecutionContext`) и `dto.py` (`ReductionPolicy`, `SemanticFrame`, `TickPlayerResultDTO`, `_TickContext`, `DMContextDTO`). Оживлён буфер `ctx.scene_changes` в Фазе 10. Удалены `settings.xxx_debug` гейты.
- 🔵 **S87** ADR-TRAV-FSM: Завершена миграция ownership перемещений. `SceneStateManager` стал единственным владельцем lifecycle (через FSM `transition_traversal`). `TickOrchestrator` и `ProjectionEngine` переведены в read-only. `current_waypoint_idx` пробрасывается в `WorldSnapshotBuilder`. Удалён мёртвый код `models/traversal.py`.
- 🔵 S86 Завершение миграции TZ-08 v0.2 и запуск Epistemic Boundary. DM-агент изолирован от ментальных объектов NPC (stress_delta, recalled_facts и др.). RulesAgent заменён на синхронный RulesSubscriber (pure reducer) в game_loop. build_r3_dm_frame перенесён в game_loop. Ядро больше не генерирует нарратив. Удалён мёртвый метод _phase_finalize из tick_orchestrator.py. Внедрён WorldProjectionBuffer как будущий слой оффскрин-симуляции.
- 🔵 **S87** ADR-TRAV-NOOP: Внедрена State-Based Idempotency в `EventCompiler`. Идемпотентность изменения позиции (`current == target`) определяется инвариантом состояния, а не семантикой события (`cause`). Устранены ложные `[SHADOW_COMPILER] FAILED` при завершении транзитов.
- 🔵 **S88** ADR-ETKE-L0: Заложен фундамент ETKE-IK v1 (Embodied Topology & Interaction Kernel). Созданы DTO непрерывной кинематики (AffordanceVector, BodySchema, DriveVector, KinematicProfile) и вычислительное ядро (SteeringResolver, MotionIntegrator, WorldTopologyProvider). Пайплайн интегрирован в TickOrchestrator как параллельная ветка (_process_continuous_motion). Движение переведено из функции графа в результат преобразования DriveVector через поле возможностей.
- 🔵 **S89** ADR-ETKE-ACT1: CAUSAL_BRIDGE → Motion Routing Layer. Двухконтурная модель движения формализована: `same_node + has_coords` → DriveVector (ETKE-IK, непрерывная кинематика), `different_node` → MovementIntent (Traversal FSM, дискретный граф). Введён `MOTION_ROUTING_THRESHOLD` и жизненный цикл DriveVector (очистка при каждом `tick_decisions`, запись в npc dict, потребление `_process_continuous_motion` на следующем тике по модели T-1). FLEE в same_node = инвертированный вектор (отталкивание, intensity=1.0). SUPERBOX: 351 comparisons, rate 1.755/tick.

- 🔵 **S90** ADR-S90.1: WorldTopologyProvider v1. `SpatialService` расширен хранением `rooms_geometry` (полигоны). Введён `is_point_in_bounds(x, y)`. `WorldTopologyProvider` формирует non-uniform `AffordanceVector`.
- 🔵 **S90** ADR-S90.2: Motion Policy Layer. Введён `Enum MotionPrimitive` (APPROACH, FLEE, RETREAT, PATROL). `LifeEngine` генерирует 4-элементный `drive_vector`. Интенсивность FLEE модулируется `affective_load`.
- 🔵 **S90** ADR-S90.3: CollisionAvoidance. Внедрён реактивный слой в `motion_pipeline.py` (до `SteeringResolver`). Проверяет `Affordance` впереди движения и смещает вектор перпендикулярно при `can_pass < 0.5`.
- 🔵 **S90** ADR-S90.4: MotionRenderRouter. Фронтенд реализует гибридный рендер: `velocity` (ETKE-IK) → инерция; `active_traversals` (FSM) → `path_waypoints`. `NPCPositionDTO` расширен.

- 🔵 **S117** ADR-O-314: `MacroMovementGoal` migrated to `actor_id`. Удалено легаси-поле `npc_id` для полной консистентности с `LocalSteeringGoal`. Обновлены все создатели и читатели (`npc_tick_pipeline.py`, `movement_engine.py`). IPT 5/5 passed.
  Files: backend/app/domain/movement.py, backend/app/services/npc/npc_tick_pipeline.py, backend/app/services/spatial/movement_engine.py


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
- 🔵 **S110** Чистка оркестратора и вынос валидации.
  - Создан `phases/validation.py` (~90 строк). Вынесена `_validate_shadow_vs_legacy` (Dual Rail Drift Validation).
  - Из `execute_player_finalize` удалено ~200 строк мёртвого кода.
  - Очищены неиспользуемые импорты, обновлена шапка `tick_orchestrator.py`.
  - Smoke-test: `TickOrchestrator` инициализируется без ошибок.
  Files: backend/app/services/tick_orchestrator.py, backend/app/services/phases/validation.py
- 🔵 **S111** Финал декомпозиции `tick_orchestrator.py`.
  - Проведён финальный аудит: размер файла доведён до 991 строки (с ~2200 изначально).
  - Все тяжёлые фазы вынесены в `phases/`. В оркестраторе остались только thin-wrappers, маршрутизация и точка входа `execute`.
  - Подтверждено, что `tick_player_turn` и `execute_player_finalize` нельзя удалять без рефакторинга `game_loop`.
  - Кампания по декомпозиции оркестратора (S101-S111) завершена.
  Files: backend/app/services/tick_orchestrator.py

- 🔵 **S113** ТЗ-Преемник: Universal Task Layer (ADR-O-313) & Social Satiation Cleanup.
  - **Task 1 (Universal Task Layer):** Внедрён `Execution Framework` (ADR-O-313). Тяжёлые I/O операции (LLM) полностью отделены от ядра симуляции. 
    - Созданы контракты `Task`, `TaskExecutor`, `Artifact`, `Materializer` в `domain/execution.py`.
    - `TickOrchestrator` (Фаза 6) перехватывает не-атакующие `CommunicationIntent`, превращает их в `QueuedTask(DialogueRequest)` и кладёт в `scene_state["pending_tasks"]`.
    - Внедрён `TaskScheduler` в `game_loop.idle_tick`. Он асинхронно забирает задачи, исполняет через `DialogueExecutor` (LLM/Stub) и публикует `NPC_SPOKE` через `DialogueMaterializer`.
    - Ядро больше не блокируется на генерации текста. LLM стала обычным `Executor`'ом.
  - **Task 2 (Legacy Cleanup):** Удалён `social_satiation` (deprecated поле).
    - Удалено поле из `NPCState` и сериализации (`write_to_legacy`/`from_legacy`).
    - Удалена `social_satiation_delta` из `SocialPayload`.
    - Удалены мёртвые методы из `DecisionHub` (`_social_satiation_modifier`) и `StateApplicator`.
    - `social_input_ema` (Field Channel) теперь единственный легитимный источник социального давления.
  - **Validation:** DriftLaboratory 200 тиков: comparisons=303, rate=1.515/tick, 0 крашей. Тесты `test_dialogue_task_layer.py` (2 passed) и инварианты (9 passed) зелёные.
  Files: domain/execution.py, domain/communication.py, services/execution/dialogue_executor.py, services/execution/dialogue_materializer.py, services/game_loop/task_scheduler.py, services/phases/post_decision.py, models/delta_payloads.py, models/npc_state.py, services/npc/decision_hub.py, services/npc/state_applicator.py
  - **Task 1 (Рефакторинг `game_loop`):** `game_loop/npc_orchestration.py` переведён на прямой вызов `execute()` с передачей `InterventionEvent` (ADR-TZ08-1). Legacy-методы `tick_player_turn` и `execute_player_finalize` полностью удалены из `tick_orchestrator.py`.
  - **Task 2 (Валидация базовой линии):** Массовый прогон 200 тиков в `DriftLaboratory`. Достигнут `rate=1.500/tick`, `drift_B=0`.
  - **Task 3 (Документирование `phases/`):** Создан `backend/app/services/phases/README.md` с описанием контрактов всех 11 фазовых модулей (входы, выходы, инварианты).
  - **Fix 1 (Краш пайплайна):** Устранён `ModuleNotFoundError: app.services.event_utils` в `phases/post_decision.py`. Импорт `get_event_bus` исправлен на `app.services.events.event_bus`.
  - **Fix 2 (Краш DTO):** Устранён `TypeError: unexpected keyword argument 'observed_facts'` в `DriftLaboratory`, вызванный закэшированным `.pyc` файлом `domain/tick.py`. Кэш принудительно очищен.
  - **Fix 3 (Потеря позиции):** Устранён `[LIFE_ENGINE][NO_POSITION]`. Поля `location_id` и `position` добавлены в `_RUNTIME_TOP_LEVEL_KEYS` в `npc_loader.py` для переживания merge. Внедрена принудительная синхронизация `npc_dict` с `scene_state` (SSOT) в начале `LifeEngine._simulate_major`.
  - **Fix 4 (Дублирование транзитов):** Устранён спам `[DIAG_V] DUPLICATE_POSITION_CHANGE` и бесконечные транзиты в ту же точку. В `SceneStateManager.apply_change` добавлен no-op guard: если `_old_position == change.value`, создание нового `traversal_dict` блокируется (возврат `True`).
  Files: backend/app/services/game_loop/npc_orchestration.py, backend/app/services/tick_orchestrator.py, backend/app/services/phases/README.md, backend/app/services/phases/post_decision.py, backend/app/services/npc/npc_loader.py, backend/app/services/npc/life_engine.py, backend/app/services/scene_state_manager.py
- 🔵 **S86** ТЗ-02 (Иммунная система): Внедрён Causal Invariant Checker (`backend/tests/sandbox/invariants/`). Тесты `test_hp_double_truth_invariant` и `test_l3_ephemeral_invariant` защищают систему от будущих разрывов между физикой, L0 и L3.

- 🔵 **S114** ТЗ: INVARIANT DEFENSE SYSTEM.
  - Внедрена двухслойная защита от регрессий: Invariant Probe Tests (IPT) и InvariantHealthChecker.
  - Созданы `backend/app/errors.py` (`SimulationIntegrityError`), `backend/tests/IPT.py` (6 инвариантов), `diagnostics/health_checkers/invariant_health.py`.
  - Расширен `CausalObserver` (3 новых паттерна) и `ReportRenderer` (секция "🔴 КРАСНЫЕ ИНВАРИАНТЫ").
  - Внедрены 4 runtime assertion в пайплайн (`post_decision.py`, `tick_orchestrator.py`, `world_snapshot_builder.py`).
  - Добавлен эмиттер `[TICK_ORCH]` для питания CDS сводкой тика.
  - Обновлен `РЕЖИМ РАБОТЫ.md` (§3.7 заменен на IPT, добавлен §3.8, расширен §4).
  - Baseline IPT: 2 красных инварианта (INV-TIME-GROW, INV-NPC-MOVE).
  Files: backend/tests/IPT.py, backend/app/errors.py, diagnostics/health_checkers/invariant_health.py, diagnostics/causal_observer.py, diagnostics/report_renderer.py, diagnostics/dna_metrics.py, diagnostics/pattern_registry.py, backend/app/services/phases/post_decision.py, backend/app/services/tick_orchestrator.py, backend/app/services/integration/world_snapshot_builder.py, docs/РЕЖИМ РАБОТЫ.md

- 🟢 **S115** ТЗ-Преемник: Финализация Трубы Диалогов и Очистка Контекста (Валидация и Багфиксы).
  - **Археология подтвердила:** Все 5 задач ТЗ (Память, Асинхронность, UI, Социум, CausalObserver) уже были реализованы предыдущим исполнителем. Тесты CDS (12 шт.) и инвариант CausalObserver — зелёные.
  - **Bugfix 1 (SpatialTransitionMode импорт):** В `backend/app/services/event_compiler.py` отсутствовал импорт `SpatialTransitionMode`, что вызывало тихий краш Shadow Compilation (`NameError`) и потерю всех транзитов. Импорт восстановлен.
  - **Bugfix 2 (TickResultDTO.final_scene_state — КРИТИЧНО):** В `backend/app/domain/tick.py`, `backend/app/services/tick_orchestrator.py` и `backend/app/services/game_loop/__init__.py` устранён критический разрыв трубы. Ядро работало с `deepcopy(scene_state)` (в `create_tick_context`), но `TickResultDTO` не возвращал мутированный снимок. `idle_tick` коммитил устаревший оригинал, теряя все изменения (время, транзиты, позиции). Добавлено поле `final_scene_state` в `TickResultDTO`, ядро возвращает `ctx.scene_state`, а `idle_tick` коммитит именно его.
  - **Bugfix 3 (SyntaxError в game_loop):** В `backend/app/services/game_loop/__init__.py:1369` блок обновления кэша `LifeEngine` выпал из `try:` из-за неверного отступа, оставив `except` сиротой. Отступ исправлен.
  - **Bugfix 4 (IPT.py campaign_id):** В `backend/tests/IPT.py` был захардкожен `tavern_silver_wolf` (location_id) вместо `Open_road` (campaign_id). `SpatialFactory` не мог найти editor JSON. Исправлено на `Open_road`.
  - **Bugfix 5 (IPT.py npc_position):** В `backend/tests/IPT.py` тест ожидал `list` для `local_position`, но `NPCPositionDTO` отдаёт `dict` `{"x": float, "y": float}`. Из-за этого все позиции возвращали `(0, 0)`, и инвариант `INV-NPC-MOVE` падал. Логика извлечения координат переписана для поддержки `dict`.
  - **Bugfix 6 (TraversalExecutionSystem закомментирован):** В `backend/app/services/tick_orchestrator.py` вызов `TraversalExecutionSystem.advance(ctx.scene_state, ctx.tick_number)` был закомментирован. Транзиты создавались, но никогда не завершались. Вызов раскомментирован.
  - **Validation:** Все 5 инвариантов IPT теперь проходят (5 passed / 0 failed). `DriftLaboratory` отрабатывает без крашей.
  Files: backend/app/services/event_compiler.py, backend/app/domain/tick.py, backend/app/services/tick_orchestrator.py, backend/app/services/game_loop/__init__.py, backend/tests/IPT.py

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

- 🔵 **S99** ТЗ-6: Engineering Debt Cleanup (Final Stage).
  - **UI Hardcodes & Magic Numbers Eliminated:** Все хардкод-строки в `game_screen.py`, `campaign_select.py`, `character_select.py` заменены на ключи `i18n.py`. Магические числа (RGB-цвета, шрифты, масштаб) вынесены в `frontend/constants.py`. `scene_renderer.py` полностью переведён на константы.
  - **Sprite Registry Unification:** Убит дублирующий файл `frontend/sprite_resolver.py`. Его функциональность (`ENTITY_SPRITE_MAP`, `get_entity_sprite`) перенесена в `frontend/map_editor/sprite_registry.py`.
  - **Validation:** Создан `backend/tests/sandbox/test_tz6_ui_hardcodes_removed.py` (6 AST-тестов: компиляция, наличие ключей/констант, отсутствие хардкодов, структура реестра спрайтов).
  - **Pipeline Stability Verified:** DriftLaboratory (200 тиков) подтверждает отсутствие регрессий: rate=1.600/tick, 0 критических ошибок.
- 🟢 **S101** Шаг 3: WillpowerGate Avatar Stress Channel (Task 2.2). Добавлено поле `stress_delta` в `WillResponseDTO`. `compute_willpower()` генерирует `stress_delta = resistance * moral_violation * 10.0` (масштаб 0-10 за действие, шкала стресса 0-100). Проброс через `DeltaBuffer` → `EmotionPayload(emotion_tag="distress")` в `_phase_1_input`. DOUBLE APPLY проверен: все 6 производителей `stress_delta` ортогональны. DriftLaboratory: 336 comparisons, rate=1.680/tick, 0 errors.
  Files: models/will.py, services/will.py, services/tick_orchestrator.py
- 🟢 **S102** Шаг 4: Non-Blocking Backend Startup (DEBT-STARTUP-1). `yield` в FastAPI lifespan перемещён перед llama-server spawn (до 120с блокировки) и LLM health check (до 30с). Медленные операции → `asyncio.create_task(_background_llm_startup)`. Статус записывается в `app.state.startup_status` (ключи: `llm_server`, `llm_health`). `/health` endpoint расширен полем `startup` для фронтенд-поллинга. `time.sleep` → `asyncio.sleep`. Shutdown корректно отменяет задачу и синхронизирует `_llama_server_proc` для atexit. DriftLaboratory: 73 comparisons, rate=1.460/tick, 0 errors.
  Files: main.py, api/routes.py
- 🔵 **S92** ТЗ-08 Addendum: Time Skip Architecture.
  - Внедрён `TimeSkipExecutor` (`backend/app/services/world/time_skip_executor.py`) как единая точка входа для промотки времени.
  - Реализованы `SkipPolicyA` (headless batch), `SkipPolicyB` (stop on significance), `SkipPolicyC` (milestone sampling).
  - Внедрены `SignificanceDetector` и `SemanticMilestoneFilter` как чистые функции анализа `TickResultDTO.significant_events` и абсолютных состояний NPC.
  - Инъекция зависимости SSOT: `TimeSkipExecutor` принимает `get_npcs_callback` (напр. `GameLoop._resolve_npcs_snapshot`), чтобы не хардкодить `LifeEngine` и не нарушать Dependency Inversion.
  - Продвижение времени (инкремент `scene_state["tick"]`) выполняется в `TimeSkipExecutor`, ядро остаётся чистой функцией.
  - Защита от гонок: `GameLoop.skip_time` использует `threading.Lock` привязанный к `campaign_id`.
  - Лёгкий срез NPC: `LifeEngine.get_npc_light_states()` для оптимизации производительности детекторов.
- 🟢 **S92** ADR-117 FIX: Исправлен баг сериализации `compress_narrative_cache` в `tick_orchestrator.py`. `NPCState.write_to_legacy` вызывался как метод экземпляра, хотя является `@staticmethod`, что приводило к потере данных NPC между тиками.
- 🟢 **S92** ADR-O-201 FIX: Исправлен баг shallow copy в `projection_engine.py`. `scene_state.active_traversals[npc] = thick.traversal.fields` присваивал ссылку, нарушая иммутабельность `ThickSceneChange`. Заменено на `copy.deepcopy`.
- 🟢 **S92** DOM-04 Tests Update: Обновлены песочницы `test_boundary_nodes.py`, `test_adjacency_inference.py`, `test_boundary_transition.py`, `test_projection_engine.py`, `test_causal_closure.py` для соответствия ADR-TRAV-FSM, ADR-O-304 и 5-элементному возврату `compile_graph` (добавлен `rooms_geometry`).
- 🔵 **S88** Epistemic Boundary (Symbolic Interpretation Layer): DM-контур переведён на символьную интерпретацию. `stance_from_decision` и `_project_psychology` переведены на чтение `observed_state` и `intent`. Числовые пороги `stress/fear/trust` удалены из вербализации.
- 🔵 **S88** WorldProjectionBuffer (Shadow Causality): Реализован как pure function (ADR-O-309). Инкапсулирован внутри `SceneStateManager.commit()`. Внедрён strict temporal sealing (diff state_t vs state_t-1). `TickOrchestrator` очищен от логики истории состояний.
- 💀 **S88** LLM Context Exile: Функция `build_verbalization_context` полностью удалена из ядра симуляции (`npc_tick_pipeline.py`). Ядро больше не формирует промпты.
- 🟢 **S93** ADR-S93.3: L2.5 Implementation. Stub-методы `PatternDetector` убраны. Внедрена инъекция `L1Chronicle` в конструктор. `BeliefCrystallizationEngine` применяет x6 множитель для негативных убеждений. Порог кристаллизации понижен до 3 событий.
- ⚠️ **S93** TECH_DEBT (S-94): L1Chronicle TTL (Task 2.3) — ограничение памяти не реализовано (отменено для сохранения ADR-O-208). Требует отдельной реализации с архивацией, а не обрезки.
- ⚠️ **S93** TECH_DEBT (S-94): WillpowerGate для аватара (Task 2.2) — базовая психика инициализируется, но полная логика сопротивления (`stress_delta` при конфликте с `drives_base`) требует расширения `_base_humanoid.json` и доработки `WillpowerGate`.

- 🔵 **S118** ТЗ: Внутренняя телеология NPC (LifeProject & Identity Crisis).
  - **Оживление CoreOrientation (L0):** Через скрипт `scripts/fix_core_orientation.py` добавлено поле `core_orientation` в JSON 6 NPC кампании `Open_road` (`family_builder`, `wealth_creator` и др.). Бусты в `DecisionHub` заработали (скоринг Горана вырос с 0.4 до 0.7+).
  - **Введение L2.7 (LifeDirection):** Добавлено динамическое поле `life_direction` в `NPCState`. Настроена сериализация (`psyche["life_direction"]`, round-trip тест зелёный). Инициализируется из L0 при спавне.
  - **Кризис Идентичности:** В `BreakProgressEngine` добавлен флаг `identity_crisis` (срабатывает при `stage="deformation"`). Создан модуль `life_project_resolver.py`, который при кризисе вычисляет новый жизненный вектор (например, `family_builder` -> `isolation`).
  - **Интеграция в DecisionHub:** `DecisionHub` переведён на чтение `state.life_direction` вместо статичного L0. Добавлены кризисные направления (`isolation`, `revenge`, `hermit`). Интеграционный тест `test_life_direction_crisis.py` подтверждает, что кризис меняет решения NPC (от `call_for_help` к `block_path`).
  Files: backend/app/models/npc_state.py, backend/app/services/npc/decision_hub.py, backend/app/services/npc/break_progress_engine.py, backend/app/services/npc/life_project_resolver.py, backend/app/services/npc/npc_loader.py, backend/tests/sandbox/system/test_life_direction_crisis.py, scripts/fix_core_orientation.py, config/npc/individuals/*.json

- 🟢 **S120** P5 FIX: NPC Traversal Pipe Repair.
  - **Археология:** `NpcTickPipeline` вызывал `_resolve_reactive_movement` и `_resolve_proactive_target`, но `SpatialService` и `SpatialQuery` не доходили до него из `TickOrchestrator` (failure stage: PASS). Кроме того, `_resolve_proactive_target` пытался вызывать несуществующие методы `find_nearest_node` у `SpatialQueryService`.
  - **Фикс 1 (Инъекция):** `pipeline_runner.py` и `tick_orchestrator.py` обновлены для явной передачи `spatial_service` и `spatial_query` в `build_tick_state`. Внедрён безопасный fallback для `SpatialQueryService` в тестах.
  - **Фикс 2 (Методы графа):** `_resolve_proactive_target` переведён на использование `spatial_service.get_nearest()` и `spatial_service.resolve_node()`.
  - **Фикс 3 (Семантика логов):** Устранён ложный warning `target_node_id is None` для не-реактивных интентов (seek_ally, offer_job и др.).
  - **Validation:** IPT 5/5 passed. DriftLaboratory (1000 тиков): 0 крашей, 438 успешных транзитов, утечек нет.
  Files: backend/app/services/pipeline_runner.py, backend/app/services/tick_orchestrator.py, backend/app/services/npc/npc_tick_pipeline.py


### DOM-11: DOCUMENTATION & AUDIT (ТЗ-07)

- 🟢 **S101** Шаг 3: WillpowerGate Avatar Stress Channel (Task 2.2). Добавлено поле `stress_delta` в `WillResponseDTO`. `compute_willpower()` генерирует `stress_delta = resistance * moral_violation * 10.0` (масштаб 0-10 за действие, шкала стресса 0-100). Проброс через `DeltaBuffer` → `EmotionPayload(emotion_tag="distress")` в `_phase_1_input`. DOUBLE APPLY проверен: все 6 производителей `stress_delta` ортогональны. DriftLaboratory: 336 comparisons, rate=1.680/tick, 0 errors.
  Files: models/will.py, services/will.py, services/tick_orchestrator.py

- 🟢 **S102** Шаг 4: Non-Blocking Backend Startup (DEBT-STARTUP-1). `yield` в FastAPI lifespan перемещён перед llama-server spawn (до 120с блокировки) и LLM health check (до 30с). Медленные операции → `asyncio.create_task(_background_llm_startup)`. Статус записывается в `app.state.startup_status` (ключи: `llm_server`, `llm_health`). `/health` endpoint расширен полем `startup` для фронтенд-поллинга. `time.sleep` → `asyncio.sleep`. Shutdown корректно отменяет задачу и синхронизирует `_llama_server_proc` для atexit. DriftLaboratory: 73 comparisons, rate=1.460/tick, 0 errors.
  Files: main.py, api/routes.py
  - **Patch Set A (Archive & Cleanup):** Удалён пустой `12.md`. В архив `docs/ARCHIVE/2026-06-19/` отправлены устаревший `CAUSAL_CONTRACT.md` (v1.0) и 5 файлов `ТЕХЗАДАНИЕ ПРЕЕМНИКУ`. Ссылки в проекте обновлены на актуальный `docs/00_CAUSAL_CONTRACT_v2.0.md`. Файл ТЗ-7 также перенесён в архив.
  - **Patch Set B (ADR Status Matrix):** Создан `docs/audits/ADR_STATUS_MATRIX.md` с актуальными статусами. В файлы shadow-ADR (O-201, O-204, O-205, O-206, O-211) добавлены блоки со статусом `Phase 0 🔴` и планами ремонта.
  - **Patch Set C (Documentation Sync):** В `README.md` обновлён блок `Repository Anchors` с правильными путями (актуальные ТЗ перенесены в `docs/Диаграммы игры/`). В `03_KNOWN_ISSUES_AND_BUGS.md` всем 9 багам проставлен статус `ЗАКРЫТ ✅`, так как археология показала, что они устранены в коде.

- 🔵 **S116** ТЗ-INFRA-1: Инфраструктура, P0-P3 баги, mypy strict & Рефакторинг.
  - **Инфраструктура:** Настроены GitHub Actions (`test.yml`, `superbox.yml`). `pytest` конфиг перенесён в `pyproject.toml` (`--strict-markers`). `mypy` внедрён в CI.
  - **Багфиксы (P0-P1):** Починены математика выделения стен в редакторе (`_point_near_line`), RGB-цвета, выход из редактора (`self._running`). UI: направление взгляда NPC (добавлено поле `facing_angle` в `PerceivedEntity`), фильтрация WASD в русской раскладке, парсер составных имён, позиция HUD (`sh` вместо `sw`).
  - **Багфиксы (P2-P3):** Автоматически очищены 33 файла от `print()` спама (заменено на `logger.debug`). Вынесены хардкоды (`duration_ticks`). Удалён мёртвый код в `api_client.py` и `editor_core.py`.
  - **Архитектура (Долг D):** Убито легаси-поле `state.hp`. Канонический источник теперь `body_state["current_hp"]` (ADR-HP-UNIFICATION). 
  - **Архитектура (Долг E):** `GameLoopBridge` переведён на persistent event loop (устранены `asyncio.run` на каждый ход). Внедрена инкапсуляция внутренних сервисов `GameLoop`.
  - **Типизация (C.3):** Слои `domain/`, `models/` и `state/` полностью прошли `mypy --strict` (0 ошибок). Слой `services/` переведён на "мягкий" режим `mypy` (137 файлов автотипизированы).
  Files: .github/workflows/test.yml, backend/pyproject.toml, frontend/game_screen.py, frontend/scene_renderer.py, frontend/map_editor/editor_core.py, backend/app/services/npc/state_applicator.py, backend/app/services/game_loop/__init__.py, frontend/game_loop_bridge.py, backend/app/domain/movement.py

- 🔵 **S117** Чистка фронтенда, LLM-инфраструктуры и статический анализ.
  - **`player_spatial` cleanup:** Легаси-поле `player_spatial` удалено из `frontend/game_screen.py` и 4 тестов. Позиция игрока теперь читается исключительно из `npc_positions["player"]` (SSOT).
  - **LLM Proxy Fix:** Обнаружен баг — прокси-клиент `Throne` рвал соединения к `localhost`. Внедрён обход (`urllib.request.ProxyHandler({})` и `httpx` `trust_env=False`) в `llm_compressor_client.py`, `health.py`, `llama_cpp_provider.py`. LLM-сервер теперь корректно отвечает на запросы.
  - **Intent Compressor:** Промпт LLM переведён на русский. Добавлен fallback в `_slow_path_parse` (если LLM недоступна, используется Fast-Path). Fast-Path улучшен для понимания прямых обращений ("Торнин, отойди к двери").
  - **Ruff Integration:** Внедрён линтер Ruff (`ruff.toml`). Ошибки (`E402`, `F821`, `E741`, `F841`) исправлены во всём проекте. `ruff check .` проходит без ошибок.
  Files: frontend/game_screen.py, backend/app/services/input/llm_compressor_client.py, backend/app/services/llm/health.py, backend/app/services/llm/llama_cpp_provider.py, backend/app/services/input/intent_compressor.py, backend/app/services/game_loop/phase_1_input.py

- 🟢 **S118** P0: LLM Slow-Path активирован. `IntentCompressor` внедрён в `GameLoop`. LLM-парсинг вынесен из ядра (`phase_1_input.py`) в оркестратор. `resolve_player_intent` теперь принимает готовый `semantic_field`.
  Files: backend/app/services/game_loop/__init__.py, backend/app/services/game_loop/phase_1_input.py, backend/app/services/input/intent_compressor.py

- 🟢 **S118** P1: Промпты DM переведены на русский. Найдена и устранена утечка английского через `StanceType` и `ToneType` в `verbal_stance.py`.
  Files: backend/app/services/verbalization/verbal_stance.py

- 🟢 **S118** Этап 0: Критические баги (C1-C14). Починены `NameError`/`ImportError` в 14 файлах (C1-C14). Внедрён единый порт `settings.llama_cpp_port` (8181) в `main.py`, `routes.py`, `game_launcher.py`. Устранены утечки файловых дескрипторов (`try...finally`).
  Files: backend/app/api/routes.py, backend/app/core/config.py, backend/app/main.py, game_launcher.py, backend/app/services/affect.py, backend/app/services/npc/state_applicator.py, backend/app/services/game_loop/npc_state_helpers.py, backend/app/services/world/time_skip_executor.py, backend/app/services/game_loop/task_scheduler.py, backend/app/services/npc/expectation_store.py, backend/app/services/action/dm_router.py, backend/app/services/verbalization/state_interpreter.py

- 🔵 **S118** ТЗ Этап 1.1: Таверна ожила. `Intent.TALK` добавлен в `PROACTIVE_INTENTS` в `DecisionHub`. NPC теперь сами инициируют диалоги в `idle_tick`. `SocialTargetResolver` возвращает `None` вместо `actor_id` при отсутствии цели, чтобы избежать самостоятельного разговора.
  Files: backend/app/services/npc/decision_hub.py, backend/app/services/phases/post_decision.py

- 🔵 **S118** ТЗ Этап 1.3: Интеграция `combat_math.py` и превентивная агрессия. В `ImpactEngine._resolve_contact` внедрён вызов `attack_roll` из `combat_math.py`. Результаты D&D 5e (Hit/Miss/Crit) маппятся на `ContactLevel`. В `DecisionHub` добавлен триггер: если `perceptual_kernel.threat_gradient > 0.5`, NPC атакует первым (fight > flight), даже в `WORLD_TICK`.
  Files: backend/app/services/combat/impact_engine.py, backend/app/services/npc/decision_hub.py

- 🔵 **S118** Vulture Audit & Ruff. Настроен `ruff.toml` (игнор `E501`/`E402` для тестов). Удалены мёртвые фабрики в `scene_change.py` и заглушки в `tick_orchestrator.py`. `combat_math.py` спасён от удаления и подключён к `ImpactEngine`.
  Files: backend/app/services/scene_change.py, backend/app/services/tick_orchestrator.py, ruff.toml

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
33. ❌ Использование `scene_state.get("player_distances")` (зомби-ридер) — только `SpatialQueryService.player_distances()`
34. ❌ Прямая сборка `SpatialService.build_for_location()` в обход `SpatialFactory.build_for_campaign()`
35. ❌ Использование `random.uniform()` в `apply_change` (нарушение детерминизма)
36. ❌ Прямая мутация `scene_state["line_of_sight"]` и `scene_state["npc_positions"][nid]["activity"]` в обход `SceneChange` (RCG Pre-Fix)

### Perception & Phenomenology
37. ❌ Хранение `EventDTO` в `EventBuffer` (только `FieldDisturbance`)
38. ❌ Обход `LocalCausalSolver` при генерации давления
39. ❌ Мутация состояния из `CausalObserver`
40. ❌ Прямая генерация эмоций из боевых событий (только через Perception)
41. ❌ `write_to_legacy` / `from_legacy` без `perceptual_kernel` и `affective_load`
42. ❌ Показ эмоций (fearful, anxious) — только наблюдаемые проявления (tense, rigid)
43. ❌ Смешивание cues и manifestations — отдельные каналы
44. ❌ Вычисление manifest в GameScreen — только чтение из perception data
45. ❌ Инъекция pain/shock напрямую в psyche dict (только через PK.somatic_urgency)

### Physiology & Combat
46. ❌ Прямая мутация HP аватара в обход `ImpactEngine`
47. ❌ `CombatSubscriber` пишет в Emotion (Domain Leakage)
48. ❌ `BehaviorManifestationService` читает эмоции вместо физиологии (Rule X)
49. ❌ Вызов `publish_classified_player_event` ДО `resolve_player_intent`
50. ❌ `shock_impulse` без decay в `PhysiologyDecayHandler`
51. ❌ `StateApplicator` проверяет `shock_impulse > 0.0` вместо `!= 0.0`
52. ❌ `NPCStateSnapshot` без поля `shock_impulse`
53. ❌ `PhysiologyDecayHandler` без проверки `life_status == "DEAD"`
54. ❌ `evaluate_vital_state` без DEATH LOCK
55. ❌ Двойная онтология: `wounds/conditions` (legacy) ≠ `body_state` (runtime truth)
56. ❌ Обработка player action без проверки `life_status`
57. ❌ `_make_player_snapshot()` без чтения `avatar_state.body_state`
58. ❌ Чтение `pain`/`fatigue` без нормализации `/100.0` в потребителях с порогами 0-1 (MSOC)

### Frontend & Presentation
59. ❌ Булева блокировка коллизий игрока (только Push-out Resolution)
60. ❌ Перезапись `result.world_snapshot` целиком в `game_loop_bridge.py`
61. ❌ Применение моторных смещений ПОСЛЕ отрисовки спрайта
62. ❌ Импорт `backend/app/` во фронтенд (Устав §1.1)
63. ❌ Передача игроку внутренних метрик NPC (HP, fear)
64. ❌ DM читает внутренние состояния NPC вместо `embodied_traces`
65. ❌ Фейковый нарратив при краше LLM ("Твоё сознание мутнеет...")

### Serialization & Persistence
66. ❌ `write_to_legacy` / `from_legacy` без `body_state`
67. ❌ Прямой конструктор `NPCState(...)` в тестах (только `from_legacy`)
68. ❌ `_apply_runtime_overlay` без белых списков для вычисленных полей (Invariant 1)
69. ❌ Персистенция `relationship_cache` внутри `NPCState` (SSOT = RelationshipStore)
70. ❌ Использование интегратора с утечкой для `affective_load` (только аттрактор насыщения)
71. ❌ Отсутствие idle-decay для `PerceptualKernel` (Rule 38)
72. ❌ AFFECTIVE_BOOT / подтягивание `affective_load` до порога `emotion_tag`
73. ❌ LifeEngine `_load_npcs()` без SQLite read-back
74. ❌ `load_npc_runtime()` возвращает `[]` вместо `None`

### Identity & Ontology
75. ❌ Кэширование `EffectiveDrives` (L3-P1 эфемерна)
76. ❌ Удаление событий из `L1Chronicle`
77. ❌ Коммит состояния с NaN или sum(drives) != 1.0 (OntologyViolationError)
78. ❌ Viability veto через `_drf_killed` или парсинг строк (только IntentDomain gate)
79. ❌ `MovementIntent` без поля `domain`
80. ❌ Чтение устаревших полей (`npc_id`, `tick`, `trait`, `delta`) из `TraitDriftEvent` (использовать `target_id`, `tick_id`, `effect_value`)
81. ❌ Использование `event_type` в математических формулах L1.5 (PatternDetector) (ADR-O-305A)
82. ❌ Наличие полей `trait`/`emotion` в `PatternDetector` или `EvidenceOfPersistence` (нарушение ADR-O-306)
83. ❌ `BeliefCrystallizationEngine` читает `L1Chronicle` напрямую (работает только через `EvidenceOfPersistence`) (ADR-O-305)
84. ❌ Скалярный страх (`CrystallizedBelief` без `source_id`) / Отсутствие `Decay` для `CrystallizedBelief`
85. ❌ Мутация `state.drives_runtime` (L0) минуя Belief Layer (L2.5) через `CalibrationEngine` (ADR-O-208/211)
86. ❌ Запуск L2.5 кристаллизации (`check_identity_promotion`) в idle-тиках без `phase_2_events` (фантомный дрейф личности)
87. ❌ Использование `random.*` в kernel layer. ❌ Вызов `DecisionHub()` без `rng`. (ADR-O-301)

### Dead NPC & Secondary Cognitive Contour (S-93)
88. ❌ Генерация интентов и дельт для NPC с `life_status="DEAD"`. ❌ Передача мёртвых NPC в `NpcTickPipeline` (ADR-S93.1)
89. ❌ Вычисление EMA ожиданий вне `StateApplicator` — StateApplicator является Single Writer (ADR-S93.2)
90. ❌ Прямое управление интентами на основе PE — только через `drive_modifiers` (ADR-S93.2)
91. ❌ Влияние PE на utility > 0.25 (MAX_PE_INF Clamp) — PE не может доминировать над DRF (ADR-S93.2)
92. ❌ Использование `PatternDetector` без передачи `L1Chronicle` в конструктор (ADR-S93.3)
93. ❌ Жёсткие пороги (if/else) в формировании убеждений `BeliefCrystallizationEngine` (ADR-S93.3)
94. ❌ Отсутствие затухания ожиданий в Фазе 0.5 — ожидания обязаны затухать привязанные к `dt_game` (ADR-S93.2)





