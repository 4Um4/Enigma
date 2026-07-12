# ENIGMA ADR MASTER INDEX (LLM-Readable)
> Формат: `ADR-XXX` [TYPE] **Title** — Essence (1 line)
> Type: STD=Standard | ONTO=Ontology (ADR-O) | FIX=Verified Bugfix
> Status: VERIFIED | PROPOSED | DEPRECATED | DEAD
> Taboo: ❌ = Architectural prohibition (hard rule)

---

## LEGEND
| Tag | Meaning |
|-----|---------|
| [STD] | Standard architectural decision |
| [ONTO] | Ontology shift (fundamental paradigm change) |
| [FIX] | Verified runtime bugfix (audit session S50-S86) |
| [DEP] | Deprecated / dead concept |
| `→` | Primary downstream consumer |
| `⚡` | Verified in runtime audit |
| `💀` | Killed concept (do not resurrect) |

---

## DOM-01: FOUNDATION (Core Pipeline, Time, State, Spatial Core)

`ADR-O-308` [ONTO] **Silent Failure Prohibition & Optional Dependency Isolation** — Скрытые баги (except Exception: pass) признаны нарушением Causal Contract §0.IV. Опциональные NLP-зависимости (pymorphy3) переведены в Degraded Mode с обязательным логированием, чтобы отсутствие утилитарного пакета не крашило онтологическое ядро.
  Taboo: ❌ Пустые `except Exception: pass` без логирования. ❌ Жёсткий fail-fast для пакетов уровня Language Layer. ❌ Хранение мёртвых конфигов (`config.json`) с абсолютными путями в активной директории.
  Files: dm_router.py, intent_compressor.py, dm_agent.py, config.json.deprecated

`ADR-001` [STD] **Delta Buffer** — Единственный путь мутации: Phase8Result → delta_buffer → StateApplicator.apply_batch()
  Taboo: ❌ Прямая мутация `all_npcs_raw` в обход DeltaBuffer
  Files: delta_buffer.py, state_applicator.py

`ADR-002` [STD] **Time-driven vs Event-driven** — Фаза 0.5 (time-decay) выполняется всегда; Фаза 8 (event-driven) только при событиях
  Files: tick_orchestrator.py

`ADR-004` [STD] **Phase 8 Handlers** — Memory/Scene обработчики признаны ненужными
  Files: tick_orchestrator.py

`ADR-013` [STD] **StateDeltas v2** — Плоский god-object заменён на `DeltaDomain` + типизированные frozen Payloads. Одна дельта = один домен
  Files: npc_state.py, delta_buffer.py

`ADR-016` [STD] **Layered Reduction** — Многоступенчатая редукция реальности: Physical → Materialization → Cognitive → Social. Порядок строго детерминирован
  Files: tick_orchestrator.py

`ADR-047` [ONTO] **No Retro-simulation** — Убит `TICK_CATCHUP`. Пропущенное время аналитически вычисляется через `reconcile_state(elapsed_seconds)`
  Taboo: ❌ Циклы `tick()` для нагона времени
  Files: life_engine.py, scene_init.py

`ADR-059` [STD] **Dual-Time Ontology** — Транзиты привязаны к монотонному `scene_state["tick"]`, не к реальному времени
  Files: tick_orchestrator.py, scene_state_manager.py

`ADR-065` [FIX] **Spatial Authority Consolidation** — Убита трёхкратная ручная сборка `SpatialService.build_for_location()` в TickOrchestrator
  Files: tick_orchestrator.py

`ADR-066` [FIX] **Single Movement Ownership** — Убит двойной вызов `process_intents()`. Единственный владелец — `TickOrchestrator`
  Taboo: ❌ Вызов `process_intents()` из `npc_orchestration.py`
  Files: tick_orchestrator.py, npc_orchestration.py

`ADR-089` [FIX] **Campaign ID Integrity** — Убита подмена `campaign_id` на `location_id` в `execute_player_finalize`
  Taboo: ❌ Подмена `campaign_id` на `location_id` в `_TickContext`
  Files: tick_orchestrator.py

`ADR-102` [FIX] **SpatialService replaces load_graph() + FLEE Fix** — `load_graph()` мёртв. `SpatialService.build_for_location()` — единственный источник
  Taboo: ❌ `load_graph()`. ❌ Сравнение legacy/canonical ID без `normalize_id()`
  Files: spatial_runtime.py, spatial_service.py, npc_tick_pipeline.py

`ADR-117` [STD] **Anti-DOUBLE TRUTH Bootstrap & Round-Trip Integrity** — Поддержание эмоции при affective_load > threshold. Обязательная сериализация всех полей NPCState
  Taboo: ❌ Прямой конструктор `NPCState(...)` в тестах (только `from_legacy`)
  Files: npc_state.py, state_applicator.py, tick_orchestrator.py

`ADR-118` [STD] **Runtime Overlay Integrity** — `_apply_runtime_overlay` мержит ТОЛЬКО ключи из whitelist
  Taboo: ❌ `_apply_runtime_overlay` без белых списков вычисленных полей
  Files: npc_loader.py

`ADR-128` [FIX] **Persistence Read-Back** — Убит разрыв write-path / read-path. LifeEngine `_load_npcs()` при cache miss читает SQLite
  Taboo: ❌ `_load_npcs()` без SQLite read-back. ❌ `load_npc_runtime()` возвращает `[]` вместо `None`
  Files: life_engine.py, persistence_port.py

`ADR-129` [FIX] **SpatialQueryService Argument Shift + SceneState Contract** — Неверный порядок аргументов, отсутствие `normalize_scene_state()`
  Taboo: ❌ `visibility()` с неправильным порядком аргументов. ❌ Отсутствие `normalize_scene_state()`
  Files: spatial_runtime.py, scene_state_manager.py

`ADR-O-314` [ONTO] **Actor-Agnostic Spatial Contract & Interpretation Layer Authority** — `TickOrchestrator` лишён права гадать об акторе движения по тексту. Введён доменный контракт `MovementRequest`, заполняемый Слоем Интерпретации. `LocalSteeringGoal` переведён на `actor_id`. Убито легаси `player_spatial`.
  Taboo: ❌ Парсинг текста игрока и вычисление дистанций для определения актора в `TickOrchestrator`. ❌ Использование `npc_id` в `LocalSteeringGoal`. ❌ Дублирование позиций игрока в `player_spatial`.
  Files: domain/movement.py, domain/intent.py, domain/intent_profile.py, services/input/intent_compressor.py, services/input/llm_compressor_client.py, services/game_loop/phase_1_input.py, services/tick_orchestrator.py, services/spatial/movement_engine.py, services/scene_state_manager.py

`ADR-134` [FIX] **DRF Split-Brain (Instance-Level Bus)** — DRFBus перенесён на уровень экземпляра оркестратора
  Taboo: ❌ `DRFBus` через `default_factory=DRFBus` в `_TickContext`
  Files: tick_orchestrator.py

`ADR-135` [STD] **Causal Scoring Overlay (ДОЛГ 4.2)** — DRF претензии влияют на приоритет: `priority += energy × weight × alignment`
  Taboo: ❌ Clamp override `max(priority, N)`. ❌ Viability veto через `_drf_killed` флаг
  Files: tick_orchestrator.py, movement_engine.py

`ADR-136` [STD] **DRFExecutionContext (Scoped Causal Ledger)** — Pipeline получает `drf_ctx`, а не голый `drf_bus`
  Taboo: ❌ Передача голого `drf_bus` в pipeline
  Files: tick_orchestrator.py, npc_tick_pipeline.py

`ADR-148` [STD] **EventDTO Default Radius Sentinel** — Дефолтный `radius=999.0` в `EventDTO.create` является латентным риском для аудио-событий (пробивает мембраны `_can_hear`), но не влияет на визуальные (`_can_see` игнорирует поле). Замена на `PERCEPTION_RADIUS["major"]` разрешена только при появлении runtime-бага со слухом.
  Files: domain/events.py, services/npc/perception_filter.py, services/spatial/player_target_pipeline.py

`ADR-SCENE-LOCK` [FIX] **Tick Unlock Guard** — `unlock_tick()` вызывал `save_scene_state()` при `_tick_locked=True`
  Taboo: ❌ Снятие `_tick_locked` после вызова сохранения состояния
  Files: scene_state_manager.py

`ADR-GL-202` [ONTO] **Generative Constraint Execution Model (GCO)** — Ленивое вычисление графа каузальности. Генеративная модель вместо полного перебора
  Files: tick_orchestrator.py, life_engine.py

`ADR-S83.1` [ONTO] **Tick = Pure Function Evaluation** — Тик — это чистая функция вычисления состояния, а не объект с побочными эффектами
  Files: tick_orchestrator.py

`ADR-S86.1` [FIX] **TZ-02 Execution Pipeline Restoration** — Устранены `ImportError` (`apply_drives_mutation`), `NameError` (`effective_drives`, `state` vs `state_for_llm`) и удалён дубликат TIFL-блока. Пайплайн восстановлен.
  Files: tick_orchestrator.py, state_applicator.py, npc_tick_pipeline.py, resolution_engine.py

`ADR-O-137` [ONTO] **Viability Pre-Generation Gate (ДОЛГ 4.3)** — Сдвиг к pre-генерационному сжатию пространства действий
  Taboo: ❌ Viability veto через парсинг строк. ❌ Пост-генерационная фильтрация
  Files: life_engine.py, domain/movement.py, npc_tick_pipeline.py

`ADR-O-139` [ONTO] **NPC Physical Integrity Contract (NPIC) & Somatic Gating** — Тело = gate of perception
  Taboo: ❌ Fallback NPC dict без `body_state`. ❌ Проверка shock/pain ПОСЛЕ парсинга
  Files: directive_interpretation_subscriber.py, tick_orchestrator.py

`ADR-O-201` [ONTO] **Causal Kernel Architecture** — `apply_changes` → чистый projection operator. Миграция в 4 фазы
  Status: PHASE_2_COMPLETE
  Files: scene_change.py, scene_state_manager.py, event_compiler.py, equivalence_validator.py

`ADR-O-201.1` [FIX] **Boundary Drift Fix (S85.1)** — `EventCompiler._compile_boundary_snap` принудительно устанавливает `is_boundary=True` при наличии `target_loc`, устраняя ложный дрейф `legacy_is_boundary=True vs shadow_is_boundary=False`.
  Files: event_compiler.py

`ADR-O-201.2` [FIX] **Topology Drift Fix (S85.1)** — `EquivalenceValidator.validate_topology` отключен для кросс-локационных переходов (`_shadow_target_location`), так как узлы физически разные (напр. `exit_east` vs `exit_west`).
  Files: tick_orchestrator.py

`ADR-O-201.3` [FIX] **Null Coordinate Fix (S85.1)** — `EventCompiler` использует `(0.0, 0.0)` fallback вместо `None` для `SpatialResolution.target_xy`, устраняя `DRIFT[E]` (missing in shadow).
  Files: event_compiler.py

`ADR-O-201.4` [FIX] **Rule 120 Drift Fix (S97)** — `EventCompiler` больше не генерирует `TraversalContract(status="COMPLETED")` для `cause="traversal_complete"` и boundary snap. Устраняет дрейф `Rule 120` (legacy=False vs shadow=True), так как SSM удаляет терминальные транзиты при cleanup, а Shadow Compiler не должен вмешиваться в lifecycle (ADR-TRAV-FSM).
  Taboo: ❌ Создание `TraversalContract` со статусом `COMPLETED` в `EventCompiler`.
  Files: event_compiler.py

`ADR-S85.1.1` [FIX] **Import & Adapter Fix (S85.1)** — `WillState` импортирован из `app.models.will` (не `vital_state`). `NPCStateAdapter.from_legacy` используется в `TickOrchestrator` вместо несуществующего `NPCState.from_legacy`.
  Files: tick_orchestrator.py

`ADR-O-204` [ONTO] **Phase 3 Preconditions — Causal Kernel Surgery** — Предусловия для миграции Каузального Ядра (Фаза 3). **ЭМПИРИЧЕСКИЙ ОВЕРРАЙД (S103):** Порог 100k comparisons признан избыточным. При 317 comparisons drift_B=134 (42.3%) — двойное создание traversal (apply_changes:1503 + EventCompiler:508) доказано без накопления. Surgery обязателен НЕЗАВИСИМО от счётчика. Шаг 1.1 плана (добор до 100k) ПРОПУЩЕН.
  Status: SURGERY_REQUIRED
  Files: scene_state_manager.py, event_compiler.py, drift_laboratory.py

`ADR-O-205` [ONTO] **Projection Layer System** — Слой проекции физики в наблюдаемую реальность. Изоляция мутаций
  Files: scene_state_manager.py, projection_engine.py

`ADR-TZ08-1` [ONTO] **Strict Event-Driven Kernel (InterventionEvent)** — Ядро симуляции переведено на event-driven модель. Введён контракт `InterventionEvent` (`app/contracts/interventions.py`), заменяющий `dm_ctx` и `TickMode`. Ядро не знает слова "player", только interventions. 
  Taboo: ❌ Передача `dm_ctx` в `TickOrchestrator` как активного контракта. ❌ Ветвление `if dm_ctx is not None:` внутри `execute()`.
  Files: contracts/interventions.py, tick_orchestrator.py

`ADR-TZ09-1` [ONTO] **Execution Pipeline Collapse (Унификация Каузального Канала)** — Убито раздвоение мира на player/idle пути. `run_npc_pipeline` (legacy mutation shell) и `tick_decisions` (pure scorer) схлопнуты в единый `NpcTickPipeline.run()`. Введён `TickState` (deep immutable causal snapshot) и `TickMutation` (pure result). `TickOrchestrator._phase_5_decision` стал Assembler + Committer. `GameLoop` переведён на `InterventionEvent`. 
  Taboo: ❌ Возврат `_phase_5_player_decision`. ❌ Прямая передача `DMContext` в пайплайн (только через `TickState`). ❌ Изменяемые дефолты в `TickState` (использовать `frozen()`).
  Status: VERIFIED (15-tick DriftLaboratory run, rate 1.4/tick)
  Files: domain/tick.py, services/npc/npc_tick_pipeline.py, services/tick_orchestrator.py, services/game_loop/__init__.py

`ADR-TZ10-1` [ONTO] **Pure Reducer Completion & Svc Strangulation** — Завершена миграция `NpcTickPipeline.run()` в чистую математическую функцию `run(state: TickState) -> TickMutation`. Убит `svc: Any` (бог-объект с I/O). Внедрён Strangulation Pattern: оркестратор загружает данные (memory, weights, social_mods, beliefs, traits) ДО вызова `run()` в `TickState.preloaded_*`, а применяет мутации (l1_events, memory_events) ПОСЛЕ вызова через `TickMutation.pending_*`. `StateApplicator.apply_batch` теперь вызывается в `TickOrchestrator`, устраняя DOUBLE TRUTH (дельты больше не теряются). 
  Taboo: ❌ Возврат параметра `svc` в сигнатуре `run()`. ❌ Вызов `svc.memory_manager` / `svc.social_engine` внутри `run()`. ❌ Прямая мутация состояния внутри `run()` (только сборка `TickMutation`).
  Status: VERIFIED (DriftLaboratory 3-tick run, 0 NameError, GATE flow stable)
  Files: domain/tick.py, services/npc/npc_tick_pipeline.py, services/tick_orchestrator.py

`ADR-TZ08-2` [ONTO] **Immutable Core Pipeline (_run_core_phases)** — Ветвление логики ядра убито. Введён единый метод `_run_core_phases`, вызываемый всегда. Фаза 1 разделена на 3 независимых подслоя: NPIC normalize, Intervention routing, WillpowerGate. `execute_player_finalize` стал no-op.
  Taboo: ❌ Возврат `TickPlayerResultDTO` из `execute()`. Ядро возвращает только `TickResultDTO`.
  Files: tick_orchestrator.py, domain/tick.py

`ADR-O-301` [ONTO] **Kernel Isolation Repair** — Убиты 5 пробоев детерминизма и 3 голых `DecisionHub()`. Внедрён `KernelRNG(tick, npc_id, salt)`. Единая фабрика в `_TickContext`.
  Taboo: ❌ Использование `random.*` в kernel layer. ❌ `DecisionHub()` без `rng`.
  Files: kernel_rng.py, tick_orchestrator.py, decision_hub.py, npc_tick_pipeline.py, life_engine.py, movement_engine.py, state_applicator.py

`ADR-S93.1` [FIX] **Dead NPC Execution Lock (ADR-123 Enforcement)** — Мёртвые NPC (`life_status="DEAD"`) полностью исключаются из `ctx.all_npcs_raw` в `_run_core_phases` до Фазы 1. Устраняет "зомби-движение" и призрачные решения.
  Taboo: ❌ Генерация интентов и дельт для NPC с `life_status="DEAD"`. ❌ Передача мёртвых NPC в `NpcTickPipeline`.
  Files: tick_orchestrator.py

`ADR-TZ03-1` [ONTO] **Single Causal Authority (Tri-Ontology System Elimination)** — Уничтожена три-онтологическая система (backend kernel truth / frontend inferred truth / fallback truth). Backend — единственный источник истины, frontend — pure renderer. Фронтенд лишён права генерировать время, аватара и журнал. DTO канонизированы (`npc_positions` как `Dict`, `cue_key`). Silent failures (`except: pass`, `suppress(Exception)`) заменены на логирование. Spatial Oracle логирует ошибки. API-поверхность готова к SSE/WorldState (dual-channel: causal + observational).
  Taboo: ❌ `game_time_seconds +=` во фронтенде. ❌ `avatar_state` override во фронтенде. ❌ `dialog_journal.append` во фронтенде. ❌ `contextlib.suppress(Exception)` на системных границах. ❌ `except Exception: pass` в Spatial Oracle. ❌ `snapshot_npc_positions_to_dict` адаптер. ❌ `cue_type` в `PeripheralCueDTO` (использовать `cue_key`).
  Files: frontend/api_client.py, frontend/game_screen.py, frontend/game_loop_bridge.py, frontend/spatial_compilation_orchestrator.py, backend/app/domain/snapshot.py, backend/app/services/integration/world_snapshot_builder.py, backend/app/api/routes.py

`ADR-311` [FIX] **Final Scene State Return (Deepcopy Isolation Fix)** — Устранён критический разрыв трубы (pipe) между ядром симуляции и `SceneStateManager`. `create_tick_context` делает `deepcopy(scene_state)` для изоляции. `TickOrchestrator.execute()` мутировал копию (продвигал время, создавал транзиты), но не возвращал её. `GameLoop.idle_tick` коммитил устаревший оригинальный `_scene`, теряя все мутации. В `TickResultDTO` добавлено поле `final_scene_state`, ядро возвращает `ctx.scene_state`, а `idle_tick` коммитит именно его.
  Taboo: ❌ Коммит `scene_state` в `SceneStateManager` из `idle_tick`, который не является результатом `execute()`.
  Files: backend/app/domain/tick.py, backend/app/services/tick_orchestrator.py, backend/app/services/game_loop/__init__.py

`ADR-O-302` [ONTO] **Physics Overlay (Time Semantics Isolation)** — Введены §14 (Закон Единичного Времени) и §15 (Закон Изоляции Реального Времени). Время симуляции (`game_time_seconds`) — единственный авторитет. `INTERPOLATION_TIME` (`ETKE_IK_SUBSTEP_DT`) выведен в константу, магические `0.1` убиты. `REAL_TIME_BRIDGE` (`reconcile_state`) изолирован и переведён на `GAME_TICK_INTERVAL_SECONDS`. Мёртвый код `get_world_ticks_elapsed` удалён. Wall-clock (`time.time()`, `datetime.now()`) запрещён в simulation layer.
  Taboo: ❌ Использование `datetime.now()` или `time.time()` в `TickOrchestrator`, `LifeEngine`, `DecisionHub`, `TemporalEngine` (кроме metadata). ❌ Магические числа `0.1` или `5.0` для `dt`/`delta_time`. ❌ Вывод тиков из реального времени (`get_world_ticks_elapsed`).
  Files: backend/app/core/constants.py, backend/app/services/motion/motion_pipeline.py, backend/app/services/npc/life_engine.py, backend/app/services/temporal/temporal_engine.py, backend/app/services/tick_orchestrator.py, backend/app/services/affect.py

`ADR-310.1` [STD] **Windup = Pure Temporal Gate** — `ActionWindup` больше не хранит `ActionCommitment` и не реконструирует `CommunicationIntent`. Введён `held_intent_id` (UUID) и словарь `_pending_intents` на `TickOrchestrator`. Фаза 7 делает pure release оригинального интента. Инварианты I-CORE-02 и I-CORE-03 соблюдены.
  Files: domain/action_windup.py, services/tick_orchestrator.py

`ADR-310.2` [FIX] **Stale Intent Validation** — В Фазе 7 (Windup Resolution) внедрён minimal guard. Перед release отложенного интента проверяется: жив ли актёр, присутствует ли он в сцене, жива ли цель и присутствует ли она в сцене. Если проверка не пройдена, windup переходит в статус `INTERRUPTED`, а интент уничтожается. Решена проблема "stale causality execution".
  Files: services/tick_orchestrator.py

`ADR-L1-PERSIST` [FIX] **L1Chronicle SQLite Persistence** — L1Chronicle принимает store для персистентности в SQLite. На рестарте события восстанавливаются. In-memory dict — только кэш на текущую сессию. Привязка к текущей кампании для ленивой загрузки.
  Files: services/npc/l1_chronicle.py, services/tick_orchestrator.py

`ADR-O-310` [STD] **Action Windup Registry & Execution Gate** — `windup_registry` перенесён на уровень `TickOrchestrator` (`self._windup_registry`). Живёт на уровне Orchestrator, переживает тики. WindupWriteGate перехватывает ATTACK для создания `ActionWindup`. EventDTO не публикуется сразу, он публикуется в Фазе 7 (Windup Execution Gate).
  Taboo: ❌ Публикация EventDTO атак с windup до Фазы 7. ❌ Создание windup registry вне TickOrchestrator.
  Files: services/tick_orchestrator.py

`ADR-TZ08-8` [ONTO] **Explicit PerceptionProjector Step** — Вызов `PerceptionProjector` вынесен из ядра симуляции в `game_loop` как явный шаг снапшота (Explicit snapshot step).
  Files: services/game_loop/__init__.py

`ADR-S96.3` [FIX] **Needs Temporal Unification (Triple Truth Elimination)** — Устранён разрыв между `LifeEngine._tick_needs`, `NeedEngine` и `reconcile_state`. Все три системы теперь используют единую скорость роста потребностей, производную от `TemporalConstants.NEED_DECAY_PER_TICK` (0.08). Для `body_state` (шкала 0-100) применяется множитель `* 100.0`.
  Taboo: ❌ Локальные хардкоды `hunger_rate` или `decay_rate` для `FOOD`, не синхронизированные с `TemporalConstants`. ❌ Использование `elapsed_seconds` напрямую для роста потребностей в обход `ticks_equivalent`.
  Files: core/constants.py, npc/life_engine.py, models/economy.py

`ADR-S101.1` [FIX] **WillpowerGate Avatar Stress Channel** — Добавлено поле `stress_delta` в `WillResponseDTO` и вычисление `stress_delta = resistance * pressure.moral_violation * 10.0` в `compute_willpower()`. Результат пробрасывается через `DeltaBuffer` → `EmotionPayload(emotion_tag="distress")` в `tick_orchestrator._phase_1_input`. Ортогонален `fear_delta` (self_risk ось) и Affective Pipeline (интеграл угрозы). DOUBLE APPLY исключён.
  Taboo: ❌ Прямая мутация `player_dict["psyche"]["stress"]` в обход DeltaBuffer. ❌ Использование `stress_delta` из WillpowerGate для NPC (только `npc_id="player"`).
  Files: models/will.py, services/will.py, services/tick_orchestrator.py

`ADR-S102.1` [FIX] **Non-Blocking Backend Startup** — `yield` в FastAPI `lifespan` перемещён перед медленными операциями (llama-server spawn до 120с, LLM health check до 30с). Медленные операции вынесены в `asyncio.create_task` с записью статуса в `app.state.startup_status`. `/health` endpoint расширен полем `startup` для фронтенд-поллинга. `time.sleep` заменён на `asyncio.sleep` внутри фоновой задачи. Shutdown корректно отменяет фоновую задачу и синхронизирует глобальные переменные для `atexit`-хендлера.
  Taboo: ❌ Блокирующие операции (`time.sleep`, `subprocess.Popen` + polling) до `yield` в lifespan. ❌ Фронтенд-поллинг `/health` без информации о статусе фоновых задач.
  Files: main.py, api/routes.py

---

## DOM-02: WILL, PRESSURE & DECISION

`ADR-031` [ONTO] **Cumulative Strain Model** — Убита матрица `action × temperament`. `IntentPressureResolver` → `IntentPressureProfile`
  Files: will.py, affect.py

`ADR-032` [STD] **Intent Resolution Pipeline Contract** — Контракт результата шлюза воли (`IntentResolution`). Фаза 1 публикует события игрока на EventBus и обеспечивает строгий типизированный контракт для `PipelineContext`.
  Files: app/models/locomotion.py, app/models/pipeline_context.py, services/game_loop/phase_1_input.py

`ADR-034` [STD] **Phase 1 Boundary Adapter** — Бизнес-логика воли изгнана из `game_loop`. Фаза 1 — чистая функция
  Files: game_loop.py, phase_1_input.py

`ADR-035` [FIX] **Semantic Black Hole** — `semantic_action` пробрасывается напрямую, без `None` fallback
  Files: phase_1_input.py

`ADR-036` [STD] **Single Will Evaluation** — Убит Double Invocation. WillpowerGate вызывается строго 1 раз за цикл
  Taboo: ❌ Вызов WillpowerGate более 1 раза за цикл
  Files: will.py, tick_orchestrator.py

`ADR-037` [STD] **Affect Resonance** — Аффект — не бафф, а искажение интерпретации (Resonance → Distortion)
  Files: affect.py

`ADR-046` [STD] **Inverted Fear** — Страх перед авторитетом бустит `Intent.APPROACH`, а не подавляет
  Files: decision_hub.py

`ADR-050` [ONTO] **DecisionContext & Feasibility** — DecisionHub разделён на Фазу 1 (Feasibility) и Фазу 2 (Utility Deformation)
  Files: decision_hub.py

`ADR-056` [STD] **Attention Capture** — Хардкод-порог заменён на `recent_directive` с механизмом сжигания
  Files: perceptual_kernel.py, life_engine.py

`ADR-057` [ONTO] **Legitimacy Gate** — Нет страха/доверия = Irritation вместо Obedience
  Files: directive_interpretation_subscriber.py, decision_hub.py

`ADR-064` [FIX] **Directive Data Continuity** — Убит Баг #6 (Глухая Воля)
  Files: tick_orchestrator.py, directive_interpretation_subscriber.py

`ADR-067` [STD] **Player Command Override** — Приказ игрока перекрывает ЛЮБОЕ решение DecisionHub
  Files: tick_orchestrator.py, npc_tick_pipeline.py

`ADR-068A` [FIX] **Partial Name Matching** — NPC с составными именами отзываются на часть имени (≥3 символов)
  Files: npc_tick_pipeline.py

`ADR-081` [STD] **Cognitive Overlay (T+0)** — Инжект шок-импульса > 0.5 мгновенно через Когнитивный Оверлей
  Files: state_applicator.py, tick_orchestrator.py

`ADR-083` [STD] **Semantic Action Fallback** — Чтение `intent.action` без fallback = Silent Crash
  Taboo: ❌ Чтение `intent.action` без fallback на `parameters.semantic_action`
  Files: will.py, affect.py

`ADR-088` [FIX] **Fast Path Emotional Injection** — Убит мёртвый `EmotionalVector` в Fast Path
  Taboo: ❌ Дефолтный `EmotionalVector` (aggression=0.0) для ATTACK
  Files: intent_compressor.py, will.py

`ADR-091` [FIX] **Semantic Action Before Resolution** — `publish_classified_player_event` вызывался ДО `resolve_player_intent()`
  Files: dm_phase.py, __init__.py

`ADR-O-146` [ONTO] **Personality Math Layer (Causal Geometry of Character)** — Аттракторная модель характера. `drive_multiplier()`
  Taboo: ❌ Импорт `_drive_multiplier` из relationship_profile. ❌ desire в RiskPerceptionProfile
  Files: decision/profile_math.py, decision/relationship_profile.py, decision/social_deltas.py, decision/risk_profile.py

`ADR-O-304` [ONTO] **L3 & DecisionContext Pipeline Unification & Projection-Native Transition** — Устранение Split-Brain. PressureTranslator=SSOT контекста (Somatic Veto), TickOrchestrator=SSOT L3-карты. DecisionHub стал projection-native (L0/drives_base изгнан из скоринга, риск-оценок и инерции)
  Taboo: ❌ Ручная сборка DecisionContext (from_kernel). ❌ Локальный DriveResolver/L1Chronicle в npc_tick_pipeline. ❌ Чтение personality.drives_base в принятии решений (только EffectiveDrives)
  Status: VERIFIED (S104). Внедрён Trait Stabilization Hysteresis (Trait Dynamics) через `trait_activation` в `NPCState`. Устранено мерцание черт.
  Files: decision_hub.py, tick_orchestrator.py, npc_tick_pipeline.py, pressure_translator.py, npc_tick_contracts.py, life_engine.py, services/npc/state_applicator.py, models/npc_state.py

`ADR-149` [FIX] **Schedule Freeze — Need Override & Two-Layer Dispatch** — Убит Schedule Freeze: need-driven (priority=0.8) перезаписывает schedule (priority=0.6). Schedule не генерируется если need-driven уже выбран. `routine["current"]` синхронизируется при победе need-driven (BUG SC FIX). Rate: 0.070 → 2.0/tick (28.5x)
  Taboo: ❌ Need priority ниже schedule при критической потребности. ❌ `routine["current"]` не обновлять при need-driven победе (DOUBLE TRUTH freeze). ❌ Schedule генерировать когда need-driven уже выбран
  Files: life_engine.py

`ADR-150` [STD] **Need-Driven Semantic Spatial Binding** — Need-driven `_check_need_driven_movement` резолвит target через `SpatialService.resolve_node(role=NodeRole)` при отсутствии `activity_map` entry. `_NEED_ROLE_MAP` мапит потребности в пространственные роли (hunger→TABLE, socializing→BAR, shelter_urge→BED). Rate рост: 0.27 → 0.40/tick
  Taboo: ❌ Need-driven возвращать None при отсутствии activity_map (молчаливая смерть интента). ❌ Отсутствие записи в `_NEED_ROLE_MAP` для новых потребностей
  Files: life_engine.py, spatial_service.py

`ADR-152` [STD] **Capture-Based Causal Trace (7.4 WHY-Log)** — _score_all переведена в чистую функцию, возвращающую кортеж (scores, components_trace). WHY-лог берёт готовый breakdown победителя из components_trace без повторного вычисления и side-channel. Устранён риск temporal coupling и дрейфа шума при логировании. 
  Taboo: ❌ Side-channel (self._last_trace) для хранения трассировки скоринга. ❌ Повторный вызов _score_components для логирования причин. ❌ Изменение return shape внутренних методов без аудита call-sites 
  Files: decision_hub.py

`ADR-153` [FIX] **Self-Defense Paralysis Fix** — Устранён баг паралича воли: fear_early_exit убивал ATTACK (ставил -1.0), но пост-хок буст самообороны слепо штрафовал FLEE (* 0.6), предполагая, что ATTACK станет доминантным. В результате NPC не бил и не бежал. Фикс: штраф к FLEE применяется только если ATTACK валиден (> 0.0). 
  Taboo: ❌ Штраф FLEE при мёртвом ATTACK (паралич выживания). ❌ Игнорировать _attack_score_pre перед применением _self_defense модификатора 
  Files: decision_hub.py

`ADR-154` [FIX] **LifeEngine Movement Lock (S85.1)** — `LifeEngine._simulate_major` полностью блокирует генерацию интентов (schedule + need-driven) для NPC в статусе `MOVING`. Устранён "бесконечный бег" и топологические дрейфы, возникавшие из-за перезаписи активного транзита.
  Files: life_engine.py

`ADR-S86.2` [FIX] **TZ-02 BUG-001: Directive Perception Pipe (S86)** — Директивные perception-поля (`aggression_inhibition_delta`, `compliance_bias_delta` и др.) вынесены из-под доменного шлюза `if domain == DeltaDomain.PERCEPTION:`. Каузальная труба воли (приказ → pressure → PerceptualKernel) открыта.
  Files: state_applicator.py

`ADR-S86.3` [FIX] **TZ-02 BreakProgressEngine Integration (S86)** — `BreakProgressEngine.calculate` подключен к `_phase_5_decision` (до DecisionHub). `WillState.BROKEN` достижим. Состояния воли фиксируются в `L1Chronicle`.
  Files: tick_orchestrator.py

`ADR-S86.4` [STD] **TZ-02 BehaviorMask Hysteresis (S86)** — `BehaviorMask` назначается на основе state перед DecisionHub. Введён как квазистабильный (гистерезисный) социальный слой, предотвращающий мерцание социальных ролей.
  Files: tick_orchestrator.py

`ADR-S93.2` [ONTO] **Secondary Cognitive Contour (PE Active Inference)** — Внедрён `PEModifierResolver` и `ExpectationStore`. Ожидания (T-1) преобразуются в `drive_modifiers` (T0) через `tanh` нормализацию и `MAX_PE_INF` (Clamp = 0.25). PE не может доминировать над DRF. `StateApplicator` является Single Writer для EMA-обновления. 
  Taboo: ❌ Вычисление EMA вне `StateApplicator`. ❌ Прямое управление интентами на основе PE (только через `drive_modifiers`). ❌ Влияние PE на utility > 0.25.
  Files: expectation_store.py, pe_modifier_resolver.py, tick_orchestrator.py, state_applicator.py, domain/tick.py

`ADR-TZ08-3` [ONTO] **Rules as Pure Reducer (RulesSubscriber)** — Асинхронный RulesAgent удалён. Введён `RulesSubscriber` (`app/services/events/rules_subscriber.py`) как pure reducer: `function(event, snapshot) → delta`. Не имеет состояния, не мутирует снапшот, использует детерминированный seed для бросков d20. 
  Taboo: ❌ Асинхронные вызовы LLM/Rules внутри `game_loop` до применения состояния. ❌ Наличие state/cache в RulesSubscriber.
  Files: events/rules_subscriber.py

`ADR-TZ08-5` [ONTO] **Narrative Projection in game_loop** — Вычисление dm_frame и RulesDelta перенесено из TickOrchestrator в game_loop. Ядро возвращает только state_t+1 (TickResultDTO).
  Taboo: ❌ Вызов LLM или Rules-агентов внутри _run_core_phases.
  Files: game_loop/init.py, events/rules_subscriber.py

`ADR-TZ08-6` [ONTO] **Ontological Separation (observed_state)** — Разделение контрактов в момент генерации. Ядро генерирует `observed_state` (только name, description, narrative_cache) вместо `real_state` (сырой legacy dict с ментальными объектами). Эпистемический Барьер обеспечен онтологически, а не через runtime-фильтры. `WorldProjectionBuffer` зафиксирован как будущий слой оффскрин-симуляции, не влияющий на DM-контур.

`ADR-TZ08-ADD-1` [ONTO] **Time Skip as Observation Policy** — Промотка времени реализована как observation layer поверх единого ядра. `TimeSkipExecutor` не содержит собственной симуляции, а вызывает `Kernel.execute()` в цикле, мутируя `scene_state["tick"]`. Остановка (Policy B) и сжатие (Policy C) определяются детекторами, читающими `TickResultDTO` и SSOT NPC через коллбек. 
  Invariant: `TickOrchestrator.execute()` обязан завершать атомарный commit состояния (`StateApplicator.apply_batch` + `LifeEngine.update_cache`) ДО возврата управления. Нарушение этого инварианта приводит к потере причинной согласованности детекторами Time Skip, так как они читают SSOT сразу после возврата из `execute()`.
  Taboo: ❌ Создание второго симулятора для Time Skip. ❌ Прямой импорт `LifeEngine` внутри `TimeSkipExecutor` (только через `get_npcs_callback`). ❌ Прямой доступ к `LifeEngine._npc_cache` снаружи (только через `get_npc_light_states`). ❌ Вызов `kernel.execute()` без инкремента `scene_state["tick"]` со стороны оркестратора.
  Files: services/world/time_skip_executor.py, services/npc/life_engine.py, services/game_loop/__init__.py

`ADR-TZ05-1` [ONTO] **LLM Context Exile** — Вынос LLM-логики из execution path ядра. Вызов `build_verbalization_context` удалён из `run_npc_pipeline`. Ядро больше не формирует промпты и не собирает ментальные объекты для LLM (physical_state, recalled_facts, suppressed_secrets) в потоке симуляции. Единственная передача темы диалога осуществляется через поле `topic`. Сама функция `build_verbalization_context` сохранена как EXPRESSION LAYER и маркирована TODO для переноса в verbalization слой и переписывания на `observed_state`.
  Taboo: ❌ Вызов `build_verbalization_context` внутри execution path (`run_npc_pipeline`). ❌ Импорт `VerbalizationContext` в execution path ядра.
  Files: npc/npc_tick_pipeline.py, scene/r3_direct_builder.py

`ADR-TZ08-7` [ONTO] **Symbolic Interpretation Layer (Verbalization v1)** — DM-контур переведён из numeric threshold model в symbolic interpretation layer. `stance_from_decision` и `_project_psychology` вычисляют психологию исключительно из наблюдаемых действий (`intent` + `emotion`), а не сырых ментальных полей (`stress`, `fear`, `trust`).
  Taboo: ❌ Чтение `psyche` или `social_stats` в слое вербализации. ❌ Восстановление ментальных полей через инференс из `observed_state`.
  Files: verbalization/verbal_stance.py, verbalization/scene_outcome_builder.py

`ADR-CNSRL` [DEP] **BreakProgressEngine Tech Debt** — Движок расчёта слома воли содержит технический долг, требующий рефакторинга (контракта с DecisionHub).
  Files: services/npc/break_progress_engine.py

---

## DOM-03: PERCEPTION & PHENOMENOLOGY (CFRM)

`ADR-025` [ONTO] **CFRM Core** — Глобального World нет. `ClusterGraph`, `EventBuffer`, `MembraneField`. NPC хранит `PerceptualKernel`
  Files: local_causal_solver.py, perceptual_kernel.py

`ADR-029` [STD] **CFRM Layer 1** — Spatial Index для O(1) поиска. Классификация по осям
  Files: local_causal_solver.py

`ADR-033` [ONTO] **Deobjectification P2** — Смерть объективных событий. `EventDTO` → `FieldDisturbance`
  Taboo: ❌ Хранение `EventDTO` в `EventBuffer`
  Files: local_causal_solver.py, event_buffer.py

`ADR-040` [STD] **Epistemic Classification** — `ClassificationResult` с `confidence`. Fallback-события имеют вес 0.2
  Files: local_causal_solver.py

`ADR-042` [FIX] **Perception Domain** — Реальность течёт в `PerceptionPayload`, а не напрямую в эмоции
  Files: npc_tick_pipeline.py, tick_orchestrator.py

`ADR-115` [FIX] **DOUBLE TRUTH perceptual_kernel** — `write_to_legacy()` / `from_legacy()` не сериализовали `perceptual_kernel`
  Taboo: ❌ `write_to_legacy` / `from_legacy` без `perceptual_kernel` и `affective_load`
  Files: npc_state.py

`ADR-302` [ONTO] **SIL, DSTC & SEL (Active Inference)** — Сдвиг к Активному Выводу. Сенсорно-моторные контуры вместо реактивных дельт
  Files: local_causal_solver.py, perceptual_kernel.py

`ADR-O-143` [ONTO] **Somatic Axis in PerceptualKernel** — Боль/шок проходят через воспринимающую линзу личности
  Taboo: ❌ Инъекция pain/shock напрямую в psyche dict
  Files: affective_integrator.py, tick_orchestrator.py, npc_state.py

`ADR-O-147` [ONTO] **Manifest Layer — Observable Physical Manifestations** — Эмоции NPC → моторные проявления → наблюдаемые теги
  Taboo: ❌ Показ эмоций (fearful). ❌ Смешивание cues и manifestations
  Files: behavior_manifestation_service.py, phenomenology_projection_service.py, game_screen.py

`ADR-S86.5` [FIX] **TZ-02 InterpretationEngine L3 Sync (S86)** — `InterpretationEngine` переведён на чтение `drives_runtime` (L3) вместо `drives_base` (L0). NPC интерпретирует мир на основе текущей деформации.
  Files: npc_tick_pipeline.py, life_engine.py

`ADR-S86.6` [FIX] **TZ-02 Verbalization L3 Sync (S86)** — `build_verbalization_context` использует `state_for_llm` для извлечения `drives_runtime`. Устранён `NameError` и рассинхрон LLM со симуляцией.
  Files: npc_tick_pipeline.py

---

## DOM-04: SPATIAL & LOCOMOTION

`ADR-008` [STD] **Spatial Centralization** — Убит глобальный `_connections_data`. Единственный источник — `SpatialService`
  Files: spatial_service.py

`ADR-010` [STD] **Macro/Micro Zones** — Архетипы переведены на макро-зоны. Убита парализация из-за микро-зон
  Files: spatial_service.py

`ADR-019` [STD] **Traversal State** — Диагноз телепортации. `TraversalState` как презентационный артефакт
  Files: movement_engine.py

`ADR-048` [STD] **Single Spatial Authority** — Чтение `scene_state["player_distances"]` запрещено
  Taboo: ❌ Чтение позиций из `scene_state`
  Files: spatial_query_service.py, npc_orchestration.py

`ADR-044` [STD] **Single Spatial Authority in Tests** — В тестах и песочницах пространственная истина читается строго из `scene_state` (как SSR), а не из мёртвых кэшей.
  Files: tests/sandbox/oscilloscope_closed_loop.py

`ADR-051` [ONTO] **LifeEngine De-godification** — LifeEngine лишён права прямой мутации позиции
  Files: life_engine.py, tick_orchestrator.py

`ADR-052` [FIX] **LOD0/LOD1 Split** — Нормализация префиксов. Устранение Silent Data Loss
  Files: npc_tick_pipeline.py, movement_engine.py

`ADR-053` [FIX] **LifeEngine Intent Pipeline Restoration** — Намерения не теряются на границе LifeEngine → TickOrchestrator
  Files: life_engine.py, tick_orchestrator.py

`ADR-058` [STD] **Frontend Dual-time Ontology** — Разделение времени симуляции и рендера. Интерполяция `path_waypoints`
  Files: game_loop_bridge.py, scene_renderer.py

`ADR-060` [ONTO] **Movement Ontology Split** — `MovementIntent` объединяет LOD0 и LOD1
  Files: movement_engine.py, npc_tick_pipeline.py

`ADR-061` [STD] **Player Position Authority** — `npc_positions.player` — единственный источник
  Files: scene_state_manager.py, tick_orchestrator.py

`ADR-069` [FIX] **target_local_xy Propagation** — При `reactive:approach` координаты цели пробрасываются через `MacroMovementGoal`
  Files: npc_tick_pipeline.py, scene_state_manager.py

`ADR-070` [FIX] **Ghost Position Interpolation** — При создании нового транзита `from_xy` интерполируется по прогрессу старого
  Files: movement_engine.py

`ADR-071` [FIX] **Bridge Traversal Propagation** — `game_loop_bridge.py` пробрасывает `active_traversals` в `world_snapshot`
  Files: game_loop_bridge.py

`ADR-072` [FIX] **Enrichment LOD0 Guard** — `_enrich_local_positions` не перетирает `local_position` для сдвинувшихся NPC
  Taboo: ❌ `_enrich_local_positions` перетирает `local_position`
  Files: scene_state_manager.py

`ADR-073` [STD] **Adjacency Inference** — Алгоритм вывода связей из смежности полигонов
  Files: graph_compiler.py

`ADR-090` [FIX] **Node Center Fallback** — Если intent не имеет точных координат (schedule/flee), берётся центр узла из графа.
  Files: services/spatial/movement_engine.py

`ADR-095` [FIX] **Centroid Graph Compilation** — Вычисляет центр комнаты вместо левого верхнего угла
  Taboo: ❌ Левый верхний угол как позиция узла
  Files: graph_compiler.py

`ADR-096` [FIX] **Frontend Traversal Respect** — Фронтенд не перезаписывает `local_position` для NPC в `MOVING`
  Taboo: ❌ Перезапись `local_position` для NPC в статусе `MOVING`
  Files: game_loop_bridge.py, scene_renderer.py

`ADR-114` [FIX] **Spatial Paralysis Fix (Role-Based Aliases)** — Добавлены name-aliases и role-based legacy aliases
  Taboo: ❌ `graph_compiler.py` без role-based aliases
  Files: graph_compiler.py

`ADR-116` [FIX] **FLEE Intent Lost (PRIORITY_NEEDS NameError)** — `_resolve_reactive_movement()` использовал `PRIORITY_NEEDS` из чужой области
  Taboo: ❌ Использование переменных из локальной области другой функции
  Files: npc_tick_pipeline.py

`ADR-119` [FIX] **Narrative Movement Prohibition (Инвариант 2)** — LLM не может описывать движение NPC без подтверждения
  Taboo: ❌ LLM описывает движение NPC без подтверждения
  Files: npc_tick_pipeline.py, dm_agent.py

`ADR-130` [FIX] **Movement Lock & Target Resolution** — `update_routine()` traversal-aware
  Files: life_engine.py, decision_hub.py

`ADR-130.1` [FIX] **apply_changes Movement Lock (S85.1)** — `apply_changes` блокирует перезапись активного транзита (`status="MOVING"`). Устранён баг "бесконечного бега".
  Taboo: ❌ Перезапись активного транзита (`status="MOVING"`) в `apply_changes`.
  Files: scene_state_manager.py

`ADR-130.2` [FIX] **Traversal Complete Snap (S85.1)** — `apply_changes` обрабатывает `cause="traversal_complete"` как проекцию `local_position` (snap), а не создание нового `TraversalState`.
  Taboo: ❌ Создание нового `TraversalState` для `cause="traversal_complete"`.
  Files: scene_state_manager.py

`ADR-TRAV-FSM` [STD] **Traversal Lifecycle FSM & Ownership Migration** — Завершена миграция ownership. `SceneStateManager` — единственный владелец lifecycle перемещений. Внедрена FSM (`transition_traversal`) для переключения статусов (PENDING → MOVING → COMPLETED/CANCELLED → cleanup). `ProjectionEngine` и `TickOrchestrator` переведены в режим read-only / эмиттеров фактов. Persistence `current_waypoint_idx` проброшен в WorldSnapshotBuilder. Верифицировано 200-тиковым прогоном SUPERBOX.
  Taboo: ❌ Прямая мутация `status = "COMPLETED"` в обход `transition_traversal()`. ❌ Хардкод `current_waypoint_idx` в проекциях.
  Files: scene_state_manager.py, projection_engine.py, tick_orchestrator.py, traversal_schema.py, world_snapshot_builder.py

`ADR-TRAV-NOOP` [STD] **State-Based Idempotency in EventCompiler** — Идемпотентность изменения позиции (`NPC_POSITION`) определяется инвариантом состояния (`current_state == target_state`), а не семантикой события (`cause`). `EventCompiler` возвращает `None` (NOOP) до запуска тяжёлой логики компиляции, если NPC уже находится на целевом узле. Устраняет ложные срабатывания `[SHADOW_COMPILER] FAILED` при штатном завершении транзитов (traversal_complete) и повышает устойчивость к будущим типам событий (teleport, sync).
  Taboo: ❌ Привязка логики фильтрации идемпотентности к полям `cause` (Semantic Coupling).
  Files: event_compiler.py

`ADR-ETKE-L0` [ONTO] **ETKE-IK v1: Motion Core Data Structures** — Закладка онтологии непрерывного движения и её интеграция в TickOrchestrator. Введены L0 DTO (AffordanceVector, BodySchema, DriveVector, KinematicProfile) и L2 сервисы (SteeringResolver, MotionIntegrator, WorldTopologyProvider). Пайплайн развёрнут как параллельная ветка (_process_continuous_motion), которая активируется при наличии DriveVector и отсутствии активного макро-транзита. Движение переведено из функции графа в результат преобразования вектора давления через физически-ориентированное поле возможностей.
  Taboo: ❌ Использование MovementIntent для микро-перемещений (LOD0) после полного внедрения ETKE-IK. ❌ Прямой запрос полигонов из SpatialService в обход WorldTopologyProvider для нужд непрерывного движения.
  Files: domain/motion_core.py, services/motion/motion_pipeline.py, services/spatial/world_topology_provider.py, services/tick_orchestrator.py

`ADR-ETKE-L2` [ONTO] **ETKE-IK v1: Motion Pipeline & Topology Provider** — Внедрены вычислительные компоненты непрерывного движения. `SteeringResolver` вычисляет `velocity` из `DriveVector` с учётом `AffordanceVector` (grip, drag) и `BodySchema`. `MotionIntegrator` выполняет интеграцию Эйлера (`position += v*dt`) и расчёт усталости. `WorldTopologyProvider` стал единым шлюзом, транслирующим дискретную геометрию `SpatialService` в непрерывное поле возможностей. Пайплайн развёрнут как параллельная подсистема.
  Taboo: ❌ Прямой запрос полигонов из `SpatialService` в обход `WorldTopologyProvider` для нужд непрерывного движения.
  Files: services/motion/motion_pipeline.py, services/spatial/world_topology_provider.py

`ADR-ETKE-ACT1` [ONTO] **Motion Routing Layer (CAUSAL_BRIDGE v2)** — CAUSAL_BRIDGE формализован как полислойный маршрутизатор движения. Геометрический инвариант `same_node vs different_node` определяет контур: `same_node + has_coords` → DriveVector (ETKE-IK, непрерывная кинематика внутри узла), `different_node` → MovementIntent (Traversal FSM, дискретный граф). FLEE в same_node = инвертированный вектор отталкивания (intensity=1.0, SURVIVAL). APPROACH в same_node = нормированный вектор притяжения (intensity=0.7, SOCIAL). Жизненный цикл DriveVector: очистка при каждом `tick_decisions` → запись в npc dict → потребление `_process_continuous_motion` на следующем тике (модель T-1). `MOTION_ROUTING_THRESHOLD` зарезервирован для будущей адаптивной интенсивности.
  Taboo: ❌ CAUSAL_BRIDGE генерирует MovementIntent для same_node перемещений (no-op, должен использовать DriveVector). ❌ DriveVector без очистки при каждом tick_decisions (эффемерность L3-P1). ❌ FLEE через DriveVector с неинвертированным direction (NPC должен удаляться от угрозы).
  Files: services/npc/life_engine.py, services/tick_orchestrator.py, domain/motion_core.py

`ADR-145` [STD] **Boundary Transition Pipeline (ДОЛГ 6.2)** — Двухфазная реальность: смысл → материализация
  Taboo: ❌ Boundary node как цель движения. ❌ Boundary resolution при создании traversal
  Files: graph_compiler.py, spatial_contracts.py, tick_orchestrator.py

`ADR-301` [ONTO] **Semantic Index Layer** — Разделение интерпретации строки от физического разрешения узла
  Taboo: ❌ SemanticIndex возвращает один canonical_id
  Files: semantic/index.py, semantic/scoring.py, semantic/selection.py

`ADR-303` [ONTO] **Coordinate Truth & Physical World Unification** — Унификация координат редактора карт и рантайма
  Files: graph_compiler.py, map_editor.py

`ADR-S82.0` [STD] **Spatial Authority Contract** — Строгий контракт единого владельца пространственных данных
  Taboo: ❌ Запрет дублирования пространственной логики
  Files: spatial_service.py, scene_state_manager.py

`ADR-S85.1` [FIX] **Semantic Spatial Binding** — Устранён корневой разрыв навигации. `LifeEngine._resolve_position` использует локальный `_ACTIVITY_TO_ROLE_MAP` и вызывает `SpatialService.resolve_node(role=NodeRole)`. Убит фоллбэк в несуществующий узел `common_area`. S89: Расширен для need-driven пути через `_NEED_ROLE_MAP` (ADR-150).
  Taboo: ❌ Возврат к строковым фоллбэкам вроде `common_area` в `_resolve_position`. ❌ Need-driven без semantic fallback при отсутствии activity_map
  Files: backend/app/services/npc/life_engine.py, backend/app/services/spatial/spatial_service.py

`ADR-S91.1` [FIX] **Cross-Location Boundary Routing & Graph Topology Strictness** — Убиты изолированные компоненты и кросс-локационная телепортация. 1) GraphCompiler: orphan rooms (без навигационного узла) исключаются из графа при активной nav-топологии (nodes). 2) MovementEngine: кросс-локационные MacroMovementGoal перехватываются и перенаправляются на boundary node (exit_east/west/etc.) текущей локации через SpatialService.get_boundary_to_neighbor(). 3) _TickContext: поле drf_bus перемещено выше полей с default_factory для совместимости с Python dataclass. Rate: 2.55 -> 2.695/tick.
  Taboo: ❌ Добавлять orphan rooms в навигационный граф при наличии nodes. ❌ Генерировать кросс-локационный SceneChange напрямую, минуя boundary node. ❌ Использовать drf_bus после полей с default в dataclass.
  Files: graph_compiler.py, spatial_service.py, movement_engine.py, tick_orchestrator.py

`ADR-S90.1` [ONTO] **WorldTopologyProvider v1: Hybrid Geometry** — `SpatialService` расширен хранением `rooms_geometry` (полигоны). Введён метод `is_point_in_bounds(x, y)`. `WorldTopologyProvider` использует его для формирования non-uniform `AffordanceVector` (`can_stand=0.0` вне полигонов). Граф и физика объединены без нарушения обратной совместимости.
  Taboo: ❌ Возврат к uniform `AffordanceVector` (константные значения без проверки `is_point_in_bounds`).
  Files: graph_compiler.py, spatial_service.py, world_topology_provider.py

`ADR-S90.2` [ONTO] **Motion Policy Layer (MotionPrimitive)** — Введён `Enum MotionPrimitive` (APPROACH, FLEE, RETREAT, PATROL). `LifeEngine` генерирует 4-элементный список `drive_vector` `[dx, dy, intensity, primitive]`. Интенсивность FLEE модулируется `affective_load` (RETREAT при < 0.7).
  Taboo: ❌ Возврат к 3-элементному `drive_vector`. ❌ Хардкод интенсивности FLEE = 1.0 без учёта нагрузки.
  Files: motion_core.py, life_engine.py, tick_orchestrator.py

`ADR-S90.3` [STD] **CollisionAvoidance (Reactive Spatial Correction)** — Внедрён реактивный слой в `motion_pipeline.py`. Работает ДО `SteeringResolver`. Проверяет `Affordance` (через `WorldTopologyProvider`) в точке впереди движения. Если `can_pass < 0.5` — смещает вектор перпендикулярно (left/right fallback) или останавливает (тупик).
  Taboo: ❌ Вызов `SteeringResolver` до `CollisionAvoidance`.
  Files: motion_pipeline.py

`ADR-S90.4` [STD] **MotionRenderRouter (Hybrid Frontend)** — Фронтенд реализует диспетчеризацию рендера: если есть `velocity` (ETKE-IK) — интерполяция по инерции; если есть `active_traversals` (FSM) — интерполяция по `path_waypoints`. `NPCPositionDTO` расширен полями `velocity` и `exertion_level`.
  Taboo: ❌ Прямое чтение `local_position` без проверки `velocity` и `active_traversals`.
  Files: game_screen.py, snapshot.py, world_snapshot_builder.py

`ADR-S91` [ONTO] **DynamicAffordanceField, Dual-Layer Stigmergy & Social Drift** — Введён state-object `DynamicAffordanceField` с двумя независимыми слоями: 1. Hard Override Layer (структурные деформации, `DeformationRecord`, Absolute Override, TTL). 2. Soft Trace Layer (поведенческие следы, `TracePayload`, накопление, экспоненциальный decay). `WorldTopologyProvider` стал чистым фасадом, мержащим базовую геометрию с обоими слоями. `TickOrchestrator` владеет персистентным инстансом поля и вызывает `purge_hard_overrides` и `step_decay` в Фазе 0.5. Внедрено NPC-to-NPC Collision Avoidance с Velocity Awareness. `PATROL` примитив заменён на `SOCIAL_DRIFT` (социально замаскированное микро-перемещение в idle-режиме).
  Taboo: ❌ Хранение состояния внутри `WorldTopologyProvider` (нарушение SRP). ❌ Очистка региона при смене локации (стигмергия должна жить). ❌ Смешивание Hard Overrides и Soft Traces в одном слое. ❌ Использование `Dict[str, float]` вместо `DeformationRecord` для структурных деформаций. ❌ Создание `WorldTopologyProvider` локально внутри методов тика. ❌ Использование рандомного `PATROL` (убивает социальную глубину).
  Files: world_topology_provider.py, motion_core.py, tick_orchestrator.py, motion_pipeline.py, life_engine.py

`ADR-SHI-02` [FIX] **LifeEngine No-Op Guard & Position Recovery** — `LifeEngine._simulate_major` больше не генерирует `MovementIntent`, если целевая позиция совпадает с текущей (предотвращает BUG_V_GUARD). `_resolve_position` восстанавливает `node_id` из `local_position` через `SpatialService.get_nearest()` с пометкой `LOW_CONFIDENCE` при необходимости, предотвращая потерю NPC.
  Files: services/npc/life_engine.py

`ADR-TZ04-1` [FIX] **Zombie Readers Elimination (A1-A3)** — Убраны чтения `scene_state["player_distances"]` в `combat_subscriber.py`, `r3_direct_builder.py` и `world_state.py`. Переведены на `SpatialQueryService`.
  Taboo: ❌ Чтение `player_distances` из `scene_state`.
  Files: combat_subscriber.py, r3_direct_builder.py, world_state.py

`ADR-TZ04-2` [FIX] **Physics RNG Isolation (A4)** — `random.uniform` в `SceneStateManager.apply_change` заменён на `KernelRNG(tick, npc_id, salt)`.
  Taboo: ❌ Использование `random.uniform()` в `apply_change`.
  Files: scene_state_manager.py

`ADR-TZ04-3` [FIX] **Dead Spatial Modules Removal (A5-A6)** — Удалены `transit_tracker.py` и `location_graph.py`. Мёртвый код в `graph_compiler.py` (122 строки) вырезан.
  Files: transit_tracker.py, location_graph.py, graph_compiler.py

`ADR-TZ04-4` [STD] **SpatialFactory (B3)** — Введена единая фабрика `SpatialFactory.build_for_campaign()`. Прямые вызовы `SpatialService.build_for_location()` запрещены.
  Taboo: ❌ Прямая сборка `SpatialService.build_for_location()` в обход `SpatialFactory`.
  Files: spatial_factory.py, npc_orchestration.py, game_loop/__init__.py, tick_orchestrator.py, scene_state_manager.py, movement_engine.py, spatial_runtime.py

`ADR-TZ04-5` [FIX] **Metadata SceneChange Routing (B4-B5)** — Прямые мутации `activity`, `initiative_suppression` и `line_of_sight` переведены на `SceneChange` (ChangeType.NPC_METADATA, ChangeType.SCENE_METADATA).
  Taboo: ❌ Прямая мутация `scene_state["line_of_sight"]` и `scene_state["npc_positions"][nid]["activity"]`.
  Files: npc_orchestration.py, dm_phase.py, scene_change.py, scene_state_manager.py

## DOM-05: PHYSIOLOGY & COMBAT

`ADR-015` [ONTO] **Physiology Domain** — Убиты RPG Hit Roll и AC. `body_profile`, `InjuryDTO`, `ImpactEngine`
  Taboo: ❌ RPG-абстракции (Hit Roll, AC)
  Files: impact_engine.py, combat_math.py

`ADR-020` [STD] **DRSL** — `ReductionPolicy`. Тело эволюционирует (`PHYSICS_COMPOSITE`)
  Files: reduction_policy.py

`ADR-021` [STD] **CombatSubscriber** — Мост `EventDTO → ImpactEngine`. Возвращает ТОЛЬКО Physiology-дельты
  Taboo: ❌ `CombatSubscriber` пишет в Emotion (Domain Leakage)
  Files: combat_subscriber.py

`ADR-022` [STD] **Leaky Integrator** — Физиология затухает по экспоненте
  Files: physiology_decay_handler.py

`ADR-027` [STD] **Layered Reduction** — Каскад: Physical → Materialization → Cognitive → Social
  Files: reduction_policy.py

`ADR-028` [STD] **Config Migration** — `combat_stats` удалены из JSON
  Files: npc_config.py

`ADR-084` [FIX] **NameError blood_loss_delta** — Переменная без извлечения
  Files: state_applicator.py

`ADR-099` [FIX] **Silent Loss Physiology (asdict)** — `asdict` не импортирован на уровне модуля
  Files: state_applicator.py

`ADR-100` [FIX] **Serialization Black Hole (body_state)** — `write_to_legacy()` / `from_legacy()` не сериализовали `body_state`
  Taboo: ❌ `write_to_legacy` / `from_legacy` без `body_state`
  Files: npc_state.py

`ADR-101` [FIX] **Rule X Violation (BehaviorManifestation)** — Читал только `stress_delta`, игнорируя `body_state`
  Taboo: ❌ `BehaviorManifestationService` читает эмоции вместо физиологии
  Files: behavior_manifestation_service.py

`ADR-102A` [FIX] **shock_impulse Not Applied** — Извлекал, но не применял
  Files: state_applicator.py

`ADR-103` [FIX] **NPC ID Fallback (apply_batch)** — Поиск по `"id"`, хотя dict использует `"npc_id"`
  Files: state_applicator.py

`ADR-104` [FIX] **Idle Tick Perception Blindness** — Вызов `produce_traces()` без `all_npcs_raw`
  Files: tick_orchestrator.py

`ADR-109` [FIX] **Shock Immortality** — `shock_impulse` не затухал между тиками
  Taboo: ❌ `shock_impulse` без decay
  Files: physiology_decay_handler.py, state_applicator.py

`ADR-110` [FIX] **CombatSubscriber NPCStateSnapshot без shock_impulse** — `_build_snapshot()` не передавал поле
  Files: combat_subscriber.py

`ADR-112` [FIX] **Semantic Inflation Fix (Rule X Enforcement)** — Переведены на `body_state` ONLY
  Taboo: ❌ Чтение `stress_delta`/`psyche_state` для моторных искажений
  Files: behavior_manifestation_service.py, phenomenology_projection_service.py

`ADR-O-142` [ONTO] **State Resolution Binding (Consciousness FSM)** — Двухуровневая модель сознания. `NPCState.consciousness_state` (FSM: SLEEPING/AWAKE/UNCONSCIOUS/DEAD) — новый SoR. `routine["current"]` НЕ является FSM state. Arousal Gate = FSM MUTATOR.
  Files: models/npc_state.py, services/npc/life_engine.py

`ADR-O-142A` [FIX] **Arousal Gate (Missing Wake Edge)** — Спящий NPC пробуждается при `wake_pressure`. Behavior transition gate, NOT consciousness.
  Files: services/npc/life_engine.py

`ADR-123` [ONTO] **Vital State Evaluator & Injury-Physiology Bridge** — Смерть = процесс. `evaluate_vital_state()`
  Taboo: ❌ `hp <= 0` как источник смерти
  Files: vital_state.py, injury_processor.py, state_applicator.py

`ADR-127` [FIX] **Death Lock — Онтологическая Необратимость Смерти** — Трёхслойный инвариант
  Taboo: ❌ `if state.body_state:` → `is not None`. ❌ Decay для мёртвых
  Files: vital_state.py, physiology_decay_handler.py, npc_state.py

`ADR-131` [ONTO] **Action Eligibility Gate (Player Death Guard)** — Игрок с `life_status="DEAD"` не может действовать
  Taboo: ❌ Обработка player action без проверки `life_status`
  Files: game_loop/__init__.py

`ADR-132` [ONTO] **Player Combat EntityView Shift** — Игрок — симулируемая физическая сущность
  Taboo: ❌ `_make_player_snapshot()` без чтения `avatar_state.body_state`
  Files: combat_subscriber.py

`ADR-137` [FIX] **Death Feedback Pipeline (life_status → UI)** — `AvatarStateDTO.life_status` пробрасывает смерть
  Taboo: ❌ `AvatarStateDTO` без поля `life_status`. ❌ Death Guard без npc_positions
  Files: snapshot.py, avatar_presentation_assembler.py, game_screen.py

`ADR-140` [FIX] **DM Death Scene Pipeline** — DM получает life_status и генерирует death scene
  Taboo: ❌ DM narration без проверки player life_status
  Files: dm_agent.py, phase_6_avatar.py, game_loop/__init__.py

`ADR-141` [STD] **Injury Chronic Pain Bridge** — Убит разрыв Injury → Pain. InjuryProcessor генерирует `pain_delta`
  Taboo: ❌ `InjuryProcessor` генерирует `blood_loss` без `pain_delta`
  Files: injury_processor.py

`ADR-GUARD` [FIX] **LifeEngine Deterministic Position Recovery** — Восстановление позиции NPC должно быть строго детерминированным.
  Files: services/npc/life_engine.py

`ADR-HP-UNIFICATION` [STD] **DOUBLE TRUTH HP Elimination (S86)** — Канонический источник HP — `body_state["current_hp"]`. Устаревший `state.hp` оставлен как deprecated-проекция и синхронизируется с `body_state` при уроне.
  Taboo: ❌ Прямая запись в `state.hp` в обход `body_state["current_hp"]`.
  Files: npc_state.py, state_applicator.py

`ADR-S96.4` [ONTO] **Causal Needs Loop Closure** — Восстановлен замкнутый контур каузальности потребностей. Ранее существовал скрытый аттрактор: `Need ↑ → neglected_ticks ↑ → stress ↑ → degradation ↑` без обязательного обратного пути. `NeedEngine.tick()` теперь принимает `current_activity` и вызывает `EconomicProfile.satisfy_need()`, замыкая цикл: `Pressure → Decision → Activity → Satisfaction → Relief`. 
  Taboo: ❌ Рост `neglected_ticks` без последующего удовлетворения при выполнении активности. ❌ Односторонние клапаны давления (рост без легитимного спада).
  Files: economy/need_engine.py, npc/domain_phases.py, npc/npc_tick_pipeline.py, game_loop/phase_2_world_tick.py, tests/sandbox/SUPERBOX/npc_sandbox.py

---

## DOM-06: SOCIAL & MEMORY

`ADR-005/006` [STD] **NPC Social Mapping** — Маппинг `social_stats` в `relationship_cache`
  Files: npc_loader.py

`ADR-007` [STD] **Idle Sync** — Синхронизация `all_npcs_raw` в idle-пути
  Files: game_loop.py

`ADR-043` [ONTO] **Social Physics** — Приказ генерирует `directive_obedience`, а не `MovementIntent`
  Taboo: ❌ `DirectiveInterpretationSubscriber` генерирует `MovementIntent`
  Files: directive_interpretation_subscriber.py

`ADR-080` [FIX] **Player-Only Social Physics** — Вычисляет легитимность по `source_id`
  Files: directive_interpretation_subscriber.py

`ADR-121` [FIX] **RelationshipStore SSOT / DOUBLE TRUTH Elimination** — Единственный SSOT (масштаб 0-100)
  Taboo: ❌ Персистенция `relationship_cache` внутри `NPCState`
  Files: npc_state.py, relationship_store.py, decision_hub.py

`ADR-122` [FIX] **Affective Load Target Derivation** — Целевая нагрузка = `Σ(active_causes + pain + shock)`
  Taboo: ❌ `affective_load` как независимый аккумулятор
  Files: state_applicator.py, physiology_decay_handler.py

`ADR-124` [FIX] **Combat → Perception Bridge** — `ReactionSubscriber` генерирует `PerceptionPayload`
  Files: reaction_subscriber.py, state_applicator.py

`ADR-125` [STD] **Target Resolution SSOT** — `IntentParametersDTO.target_id` депрекирован
  Files: tick_orchestrator.py, dm_phase.py

`ADR-126` [FIX] **Relationship Cache Ontology Merge** — Сборка расширена до Partial Social Graph
  Files: npc_tick_pipeline.py, decision_hub.py

`ADR-S86.7` [STD] **TZ-02 Event-Conditioned Memory Promotion (S86)** — Контур памяти замкнут с инвариантом: "Memory cannot generate new identity without causal input". `compress_narrative_cache` (структурное сжатие) работает в idle. `check_identity_promotion` (L2.5 кристаллизация) работает только при наличии `phase_2_events`.
  Taboo: ❌ Запуск L2.5 кристаллизации в idle-тиках без `phase_2_events` (фантомный дрейф личности).
  Files: tick_orchestrator.py, memory_manager.py

---

## DOM-07: FRONTEND, PRESENTATION & INPUT

`ADR-0017` [STD] **Character Creation Vector** — Диалог создания персонажа через Вектор Начальных Условий.
  Files: frontend/character_select.py

`ADR-030` [ONTO] **Hybrid Consciousness Entity (Avatar Injection)** — Игрок становится полноправным NPC в симуляции. Инъекция Аватара Игрока как Гибридной Сущности.
  Files: app/models/schemas.py, services/game_loop/__init__.py, frontend/character_select.py

`ADR-075` [STD] **Strict Embodiment Contract** — Строго типизированный транспорт Эмбодимента через каузальную границу API. Если поле пропадёт — краш схемы, а не тихий None. Idle-тики не содержат Волевых конфликтов.
  Taboo: ❌ Использование `getattr` для полей Embodiment. ❌ Возврат тихого `None` при отсутствии поля.
  Files: app/domain/tick.py, app/api/routes.py, frontend/api_client.py, frontend/game_loop_bridge.py

`ADR-082` [FIX] **Case-Insensitive Routing** — NLP возвращает 'ATTACK', маппинг ждет 'attack'. Введена нормализация регистра.
  Files: services/game_loop/phase_1_input.py

`ADR-GENDER` [STD] **Avatar Gender Persistence** — Эндпоинт смены пола аватара. Обязательная персистенция пола аватара. Без этого поле теряется при save/load.
  Files: app/api/routes.py, services/player_avatar_service.py

`ADR-MANIFEST` [STD] **Observable Physical Manifestations** — Конвертация domain manifestations → API ManifestationDTO. Наблюдаемые физические проявления (НЕ эмоции!). Бэкенд — единственный источник истины.
  Taboo: ❌ Вычисление manifestations на фронтенде.
  Files: services/integration/world_snapshot_builder.py, services/perception/phenomenology_projection_service.py, frontend/game_screen.py, frontend/scene_renderer.py

`ADR-011/014` [STD] **Narrative Beats** — Убран плоский чат. Пузыри, спикеры
  Files: game_screen.py, narrative_renderer.py

`ADR-035B` [ONTO] **Intent Compression** — Русская морфология (pymorphy3 + LLM)
  Files: intent_compressor.py

`ADR-038` [STD] **Embodied Perception DTO** — Скаляры давления и моторные импульсы
  Files: api_schema.py

`ADR-039` [STD] **Resistance Medium** — Конфликт воли = инфекция поля ввода
  Files: text_input.py, game_screen.py

`ADR-041` [STD] **Will Conflict Data** — Проброс конфликта воли через API
  Files: routes.py, tick_orchestrator.py

`ADR-068` [FIX] **Avatar Flesh Injection & API Suturing** — Труба Эмбодимента оборвана на 3 уровнях
  Files: avatar_service.py, routes.py, game_screen.py

`ADR-086` [FIX] **Embodiment Pipe Closed** — `will_conflict_data` проверено доходит до `text_input.infect()`
  Files: tick_orchestrator.py, game_screen.py

`ADR-087` [FIX] **Fast Path Dictionary Expansion** — Расширен приставочными глаголами
  Files: intent_compressor.py

`ADR-092` [FIX] **The Fool v2 Pipeline** — `game_loop_bridge.py` перезаписывал `world_snapshot` целиком
  Files: game_loop_bridge.py, scene_renderer.py

`ADR-093` [FIX] **The Fool Phase 3 (DM Observational Pipeline)** — `player_perception` проброшен в DM-контракт
  Taboo: ❌ DM читает внутренние состояния NPC вместо `embodied_traces`
  Files: pipeline_context.py, dm_agent.py

`ADR-094` [FIX] **RPG Vitalism Revival + MSOC Normalization** — Нормализация `pain / 100.0`
  Taboo: ❌ Чтение `pain`/`fatigue` без нормализации `/100.0`
  Files: state_interpreter.py, avatar_presentation_assembler.py

`ADR-097` [FIX] **Push-out Resolution** — Булева блокировка → Push-out по вектору проникновения
  Taboo: ❌ Булева блокировка коллизий игрока
  Files: scene_renderer.py, collision_system.py

`ADR-098` [FIX] **AABB Coordinate Contract** — Левый верхний угол, не центр
  Files: scene_renderer.py

`ADR-113` [FIX] **LLM Resilience (Retry + Honest Failure)** — 3 retry. `{"error": True}` вместо фейка
  Taboo: ❌ Фейковый нарратив при краше LLM
  Files: llama_cpp_provider.py, agent_runner.py

`ADR-JOURNAL` [STD] **Dialog Journal** — Журнал диалогов (клавиша J/O)
  Taboo: ❌ dialog_journal в scene_state
  Files: game_screen.py

`ADR-SPEECH` [STD] **Speech Bubbles** — Речевые облачка над NPC и игроком
  Taboo: ❌ npc_reactions в message_log
  Files: game_screen.py, scene_renderer.py

`ADR-i18n` [STD] **Localization Module** — Единый файл локализации
  Taboo: ❌ Inline-словари activity_ru в game_screen
  Files: i18n.py, game_screen.py

`ADR-TZ08-4` [ONTO] **Epistemic Boundary (DM as Observer)** — DM-агент переведён в режим строго локальной эпистемики. Нарратив рождается исключительно из player_perception и rules_result. Доступ к внутренним состояниям NPC (stress_delta, trust_delta, real_state, recalled_facts, suppressed_secrets) заблокирован на уровне r3_direct_builder и dm_agent.
  Taboo: ❌ Чтение ментальных объектов NPC в слое интерпретации. ❌ Возврат dm_frame из ядра симуляции.
  Files: scene/r3_direct_builder.py, agents/dm_agent.py, tick_orchestrator.py, game_loop/init.py

`ADR-TZ05-2` [ONTO] **DM Output Contract Layer** — Изоляция логики восстановления текста из ответов LLM в DMResponseNormalizer. DM-агент перестал быть парсером, став чистым оркестратором.
  Taboo: ❌ Парсинг JSON-схем внутри dm_agent.py. ❌ Возврат дефолтного EmotionalVector (aggression=0.0) для ATTACK.
  Files: services/verbalization/dm_response_normalizer.py, agents/dm_agent.py

`ADR-TZ05-2` [ONTO] **Prompt Governance & Mock Exclusion** — Синхронизация промпта LLM с валидатором. Forbidden-список генерируется динамически из контракта. MockProvider недоступен в production. 
  Taboo: ❌ Хардкод max_tokens в dm_agent.py. ❌ Использование MockProvider при settings.environment == "production".
  Files: prompts/dm_system.txt, services/verbalization/dm_contract_builder.py, services/llm/factory.py, core/config.py

---

## DOM-08: OBSERVABILITY (CDS & Sandbox)

`ADR-DEBUG-001` [STD] **Explicit WARNING Level for Causal Loggers** — Явное включение WARNING для каузально-критичных логгеров в `main.py`.
  Files: backend/app/main.py

`ADR-003` [STD] **Test Determinism** — Синтетические фабрики вместо I/O фикстур
  Files: test_factories.py

`ADR-009` [STD] **DI Primitives** — Примитивы, а не объекты в `InterpretationEngine`
  Files: interpretation_engine.py

`ADR-045` [STD] **Causal Oscilloscope** — `DeterministicClock` и `CausalTrace`
  Files: causal_trace.py, deterministic_clock.py

`ADR-054` [FIX] **Test Suite Synchronization & ADR-052 Alignment** — Синхронизация тестов с ADR-052
  Files: tests/sandbox/

`ADR-120` [FIX] **Pre-Bus Failure Observability (Инвариант 3)** — 5 новых паттернов в CDS
  Taboo: ❌ `logger.debug` для крахов аффективного decay
  Files: pattern_registry.py, tick_health.py, causal_observer.py

`ADR-133` [FIX] **Sandbox Test Protocol** — 7 sandbox-тестов покрывают save/load body_state
  Files: tests/sandbox/persistence/, tests/sandbox/movement/

`ADR-147` [FIX] **LLM Streaming Observability Gate** — Убит теневой streaming path
  Files: router.py, pattern_registry.py, causal_observer.py

`ADR-S85.3` [FIX] **SUPERBOX Idle Stability & Observer Fix** — Добавлен режим `idle_simulation_stability` в DriftLaboratory. Исправлена оптика метрики `UNIQUE_NODES_VISITED`: чтение позиций переведено на `scene_state["npc_positions"]` (SSOT), вместо кэша `LifeEngine`.
  Taboo: ❌ Чтение пространственных позиций NPC из кэша `LifeEngine` в метриках тестов.
  Files: backend/tests/sandbox/SUPERBOX/drift_laboratory.py

`ADR-S85.1.2` [FIX] **SUPERBOX Pipeline Stabilization (S85.1)** — Устранены краши пайплайна (`AttributeError`, `ImportError`, `NameError`) в `L1Chronicle` и `TickOrchestrator`. Достигнут стабильный rate `comparisons=21/15 ticks`.
  Files: backend/app/services/npc/l1_chronicle.py, backend/app/services/tick_orchestrator.py

`ADR-151` [STD] **Probe → Telemetry Transition** — Диагностические print-зонды классифицированы на 3 слоя: 🟢 Essential (print — всегда видны: GATE_*, NPC_SET, DRF_*, TIFL_DRIFT, GATE_ZOMBIE), 🟡 Condensed (logger.debug — видны при DEBUG level: NEED_TRACE, SCHED_TRACE, AFF_*, SEL_DIAG, DRF_VOTE), 🔴 Removed (полностью убраны: MOVEMENT_DEBUG, SCENE_CHANGE_DIAG, TRAV_CHECK_P1, дубликаты в player path). Убиты пустые блоки от некорректного удаления.
  Taboo: ❌ Удалять print-зонды без замены на logger.debug. ❌ Пустые блоки после удаления probe (SyntaxError)
  Files: tick_orchestrator.py, life_engine.py, movement_engine.py

`ADR-IMMUNE-001` [STD] **Causal Invariant Checker (S86)** — Внедрена иммунная система ENIGMA (`backend/tests/sandbox/invariants/`). Тесты `test_hp_double_truth_invariant` и `test_l3_ephemeral_invariant` защищают систему от будущих разрывов между физикой, L0 и L3.
  Taboo: ❌ Игнорирование падения тестов в `invariants/` ради запуска фич.
  Files: backend/tests/sandbox/invariants/test_cross_layer_consistency.py

`ADR-SHI-01` [FIX] **CDS Pipeline Repair (SHI=0% Fix)** — Восстановлена труба логирования. Regex в `pattern_registry.py` обновлён для парсинга отрицательных score (`-?[\d.]+`). Устранён `NameError` (`hub_event`) в `npc_tick_pipeline.py`. Симуляция снова "видима" для CDS.
  Files: diagnostics/pattern_registry.py, services/npc/npc_tick_pipeline.py

`ADR-INV-DEF` [STD] **Invariant Defense System (IPT & Red Invariants)** — Двухслойная защита от регрессий. Invariant Probe Tests (IPT) запускаются до коммита. InvariantHealthChecker + SimulationIntegrityError ловят тихие деградации post-mortem. Эмиттер `[TICK_ORCH]` в ядре кормит CDS сводкой тика.
  Taboo: ❌ Закрывать шаг без запуска `python backend/tests/IPT.py`. ❌ Перехват `SimulationIntegrityError` через try/except в пайплайне. ❌ Игнорирование секции "🔴 КРАСНЫЕ ИНВАРИАНТЫ" в `LAST_SESSION.md`.
  Files: backend/tests/IPT.py, backend/app/errors.py, diagnostics/health_checkers/invariant_health.py, diagnostics/causal_observer.py, diagnostics/report_renderer.py, diagnostics/dna_metrics.py, backend/app/services/phases/post_decision.py, backend/app/services/tick_orchestrator.py, backend/app/services/integration/world_snapshot_builder.py

---

## DOM-09: SOCIAL & AFFECTIVE ARCHITECTURE (SSOT & Causal Derivation)

`ADR-049` [ONTO] **Causal Pressure Pipeline** — Замыкание контуров Восприятие-Эмоция-Решение
  Files: decision_hub.py, tick_orchestrator.py

`ADR-055` [ONTO] **Affective Pressure Pipeline** — Прямой прыжок Perception→Emotion запрещён
  Files: affective_pressure.py, tick_orchestrator.py

`ADR-138` [ONTO] **Dissipative Psychodynamics & Hysteresis** — Убит Вечный Двигатель Страха. Асимметричный аттрактор
  Taboo: ❌ Интегратор с утечкой для `affective_load`
  Files: affective_integrator.py, tick_orchestrator.py, life_engine.py

`ADR-O-206` [ONTO] **Emotional Residue Isolation Protocol** — Эмоциональный остаток изолирован от физиологического цикла
  Status: VERIFIED (S104). EmotionTag полностью изолирован от логики памяти и физиологии. Шрамы памяти модулируются нелинейно от Surprise. Нагрузка вычисляется как функция ошибки предсказания, а не как сумма памяти и энергии.
  Files: affective_integrator.py, affective/affective_integrator.py, memory/importance_engine.py, memory/memory_manager.py, affective/affective_decay_handler.py

`ADR-DET-02` [FIX] **Domain Boundary Integrity (PE_DISAPPOINTMENT Leak)** — Устранена прямая мутация `trust_delta` (SOCIAL field) из `EMOTION` handler. Модуляция разочарования (PE < -0.3) теперь применяется строго внутри блока `DeltaDomain.SOCIAL`, соблюдая Single Writer Policy (I-CORE-05). Установлена основа для будущего перехода на event-mediated influence (EmotionalSignal).
  Files: services/npc/state_applicator.py

`ADR-S96.2` [FIX] **Affective Pipeline DOUBLE TRUTH Elimination** — Убито дублирование логики аффективного интегратора в `TickOrchestrator` (idle vs player paths). Мёртвый `pressure_derivation.py` удалён. `integrate_affective_pressure` стал единственным владельцем Active Inference + Hysteresis, возвращая `Tuple[new_load, new_memory]`. 
  Taboo: ❌ Возврат к инлайн-вычислению `pk_load` и `affective_memory` в `TickOrchestrator`. ❌ Воскрешение `pressure_derivation.py`. ❌ Интегратору запрещено влиять на policy (scoring/decisions) — он вычисляет только state.
  Files: affective/affective_integrator.py, tick_orchestrator.py, affective/pressure_derivation.py (DELETED)

`ADR-TZ6-2` [STD] **Frontend Constants & i18n Final Closure** — Завершена чистка хардкодов. Магические числа (RGB-цвета, размеры шрифтов, масштаб) вынесены в `frontend/constants.py`. Все русские строки переведены на ключи `frontend/i18n.py`. Убит дублирующий модуль `sprite_resolver.py`, его функциональность перенесена в `map_editor/sprite_registry.py`.
  Taboo: ❌ Хардкод UI-строк в файлах фронтенда. ❌ Инлайн RGB-кортежей и размеров шрифтов в рендерере. ❌ Возврат дублирующего модуля `sprite_resolver.py`.
  Files: frontend/constants.py, frontend/i18n.py, frontend/game_screen.py, frontend/scene_renderer.py, frontend/campaign_select.py, frontend/character_select.py, frontend/map_editor/sprite_registry.py, frontend/sprite_resolver.py (DELETED)

`ADR-TZ6-1` [STD] **Engineering Debt Cleanup (Dead Code, Silent Failures, Magic Numbers)** — Удалены мёртвые методы (`_draw_input_bar`, `_advance_time_by_movement`, `_build_intro_prompt`, `can_proceed`, `add_npc_author_notes`) и поля (`PlayerMemory`, `EncounterHistory`). `except Exception: pass` заменены на `logger.warning`. `WillState` унифицирован в `npc_state.py` (из `will.py` удалён дубликат). `print()` заменены на `logger.debug` с feature-флагами. Магические числа вынесены в `constants.py`, UI-строки в `i18n.py`. `RelationshipStore` переведён на LRU/TTL кэш.
  Taboo: ❌ Использование дублирующего `WillState` из `will.py`. ❌ Возврат к `except Exception: pass`. ❌ Хардкод UI-строк вместо `i18n`.
  Files: movement_engine.py, tick_orchestrator.py, dm_agent.py, game_loop_bridge.py, api_client.py, main.py, will.py, npc_state.py, constants.py, i18n.py, relationship_store.py, game_screen.py, game_types.py

---

## DOM-10: IDENTITY & ONTOLOGY (Identity Layer & Chronicle)

`ADR-O-112` [ONTO] **Actor-Agnostic Combat Pipeline (Universal Violence)** — Боевой конвейер: `Any Actor → Any Actor`
  Status: PROPOSED
  Files: combat_subscriber.py, state_applicator.py, player_avatar_service.py

`ADR-GL-203` [ONTO] **Error-Geometry System & Dynamic Ontology** — Эпистемология ENIGMA: Геометрия ошибок и исполнение семантики
  Files: domain/exceptions.py, causal_trace.py

`ADR-O-207` [ONTO] **Post-Commit Validation Gate** — L5 валидация. OntologyViolationError убивает тик
  Taboo: ❌ Коммит состояния с NaN или sum(drives) != 1.0
  Files: domain/exceptions.py, state_applicator.py

`ADR-O-208` [ONTO] **Identity Chronicle & Drives (DRP)** — L1Chronicle (append-only) и DriveResolver (L0+L1→L3)
  Taboo: ❌ Кэширование EffectiveDrives. ❌ Удаление из L1Chronicle. ❌ Фоллбэк на L0 (drives_base) в InterpretationEngine/VerbalizationContext.
  Status: VERIFIED (S104). L3 стала строго эфемерной. Уничтожены фоллбэки на L0. Прямая мутация drives_runtime заблокирована.
  Files: domain/identity_events.py, services/npc/l1_chronicle.py, services/npc/drive_resolver.py, services/npc/npc_tick_pipeline.py, services/npc/life_engine.py, services/tick_orchestrator.py

`ADR-O-208.1` [FIX] **TraitDriftEvent Contract Fix (S85.1)** — `BreakProgressEngine` и `L1Chronicle` переведены на новые поля ADR-O-208 (`target_id`, `tick_id`, `effect_value`). Удалены обращения к устаревшим `npc_id`, `tick`, `trait`, `delta`.
  Taboo: ❌ Чтение устаревших полей (`npc_id`, `tick`, `trait`, `delta`) из `TraitDriftEvent`.
  Files: backend/app/services/npc/break_progress_engine.py, backend/app/services/npc/l1_chronicle.py

`ADR-O-208.2` [STD] **L1Chronicle SQLite Persistence (S86)** — `L1Chronicle` стал персистентным (SQLite). Внедрена схема `l1_chronicle_events`. DI замкнут от `GameLoop` до `L1Chronicle`. Контракт `TraitDriftEvent` полностью канонизирован.
  Files: backend/app/services/npc/l1_chronicle.py, backend/app/services/memory/sqlite_store.py, backend/app/services/game_loop_builder.py

`ADR-O-209/210` [ONTO] **Phase-Locked Identity & Bounded Spatial Field Coupling** — Фазовая блокировка идентичности и ограниченная связь с пространственным полем
  Files: decision/profile_math.py, spatial_service.py

`ADR-O-211` [ONTO] **Calibration Engine & Identity Stability Kernel** — Pure Projection Gate. CalibrationEngine исключён из каузального графа мутаций состояния. Не эмитирует апдейты, только валидирует и пропускает L3_raw. Эмоциональное взросление полностью делегировано в L2.5 (BeliefCrystallizationEngine). Стресс-тест (50k тиков) выявил накопление шума (Test C). Стабилизация драйвов признана тупиком — кристаллизоваться должны причины (Убеждения), а не эмоции (скаляры).
  Taboo: ❌ Гистерезис на скалярных драйвах. ❌ Эмиссия state mutations из CalibrationEngine. ❌ Мутация drives_runtime минуя Belief Layer.
  Files: services/npc/calibration_engine.py, services/npc/belief_crystallization_engine.py

`ADR-O-212` [ONTO] **Social Physics Inertia & Approximation** — Социальная физика — функция аппроксимации поведения группы во времени. 4 слоя: Физика, Психика, Общество (VillageMemoryField), Политика (InstitutionLayer). Институциональная инерция запрещает мгновенную эскалацию
  Taboo: ❌ Narrative Gravity как отдельный слой данных (Double Truth). ❌ Мгновенная реакция InstitutionLayer. ❌ resistance_to_change = 0.0. ❌ myth_level от количества убийств
  Files: social/village_memory_field.py, social/social_memory_updater.py, social/institutional_inertia.py

`ADR-O-305` [ONTO] **Belief Crystallization Engine (L2.5)** — Трёхслойная модель формирования убеждений: L1 (Факты) → L1.5 (PatternDetector: чистая статистика) → L2.5 (Belief Engine: психологическая проекция). PatternDetector группирует L1Chronicle по source_id и генерирует EvidenceOfPersistence (cumulative_effect, behavior_variance). Belief Engine интерпретирует статистику в CrystallizedBelief (trait) с учётом личности и Асимметричной Травмы. Belief → Policy Injection в DecisionHub
  Status: VERIFIED
  Taboo: ❌ Наличие полей trait/emotion в PatternDetector (нарушение ADR-O-306). ❌ BeliefCrystallizationEngine читает L1Chronicle напрямую (работает только через EvidenceOfPersistence). ❌ Скалярный Страх (убеждение без source_id). ❌ Drives Do Not Learn (Invariant L3-P4)
  Files: pattern_detector.py, belief_crystallization_engine.py, crystallized_belief_store.py, crystallized_belief_modifier_resolver.py, domain/identity_events.py

`ADR-O-305.1` [ONTO] **Belief Decay Model (S85.2)** — Внедрена энтропия убеждений (`BELIEF_DECAY_TAU`). Убеждения растворяются без подкрепления, предотвращая статическую кристаллизацию личности.
  Taboo: ❌ Отсутствие Decay для CrystallizedBelief.
  Files: belief_crystallization_engine.py

`ADR-S85.2` [STD] **Archetype vs Individual Data Separation** — Архетип = Профессия (содержит только `schedule`), Индивид = Должность (содержит `activity_map` для кросс-локаций). Удалены захардкоженные пространственные привязки из архетипов.
  Taboo: ❌ Хранение `activity_map` с конкретными координатами (напр. `tavern_silver_wolf:main_hall`) внутри архетипов.
  Files: config/npc/archetypes/*.json, config/npc/individuals/*.json

`ADR-TIFL-001` [ONTO] **Temporal Identity Formation Layer** — Формирование идентичности во времени. Темпоральный слой L1
  Files: services/npc/l1_chronicle.py

`ADR-TIFL-002` [ONTO] **Identity as Competitive Drift Field (ICDF)** — Идентичность как конкурентное поле дрейфа
  Files: services/npc/drive_resolver.py, domain/identity_events.py

`ADR-TIFL-003` [ONTO] **Identity Constraint Layer & Thermodynamic Crystallization** — Слой ограничений идентичности и кристаллизация черт
  Files: services/npc/drive_resolver.py

`ADR-O-306` [ONTO] **Epistemic Heterogeneity & Triple Membrane** — L1 Chronicle каждого NPC — персонализированная запись, не объективная хроника. L1 фильтруется через Тройную Мембрану: Физическую, Личностную и Социальную (Norm-модулированные пороги). InstitutionLayer только модулирует пороги (Социальная Линза), не инжектит события
  Taboo: ❌ Инъекция событий в L1 Chronicle из социальных слоев. ❌ Игнорирование Norm-модуляции порогов восприятия
  Files: perceptual_kernel.py, l1_chronicle.py, social/institution_layer.py

`ADR-O-307` [ONTO] **Asymmetric Trauma & Belief Revision** — Опровержение убеждения в 6 раз сильнее подтверждения. Belief формируется только при personal_persistence (Опыт > Давления)
  Taboo: ❌ Симметричное обновление confidence убеждений
  Files: belief_crystallization_engine.py, pattern_detector.py

`ADR-O-305A` [ONTO] **Evidence Semantics (L1 → L1.5 Contract)** — Строгий математический мост между L1 Chronicle и PatternDetector. `TraitDriftEvent` содержит направленный вектор `effect_value` (-1.0 до 1.0) и `observation_weight`. PatternDetector агрегирует данные в `EvidenceOfPersistence` (cumulative_effect, frequency_per_tick, behavior_variance). `event_type` существует исключительно как provenance и запрещён в формулах
  Taboo: ❌ Использование `event_type` в математических формулах PatternDetector. ❌ Выход `effect_value` за пределы [-1.0, 1.0]. ❌ Зависимость `NOISE_THRESHOLD` от размера окна (только абсолютный `MIN_EVENTS`)
  Files: pattern_detector.py, domain/identity_events.py

`ADR-O-309` [ONTO] **WorldProjectionBuffer (Shadow Causality Layer)** — Stateless causal projection engine. Читает committed world state и генерирует WorldProjectionEvent (слухи, вторичные эффекты) как производный слой. НЕ является оффскрин-симулятором и НЕ выполняет автономное обновление мира.
  Taboo: ❌ Изменение состояния мира (scene_state, npc_states). ❌ Запуск симуляции NPC (LifeEngine.tick). ❌ Использование reconcile_state как механизма движения. ❌ Хранение внутреннего состояния (stateless pure function only). ❌ Вызов проекции вне `SceneStateManager.commit()`.
  Files: services/offscreen/world_projection_buffer.py, domain/world_projection.py, services/scene_state_manager.py

`ADR-S93.3` [FIX] **L2.5 PatternDetector & Belief Engine Implementation** — Stub-методы `PatternDetector` заменены на чтение `L1Chronicle` через инъекцию зависимости. Порог `MIN_EVENTS_FOR_PERSISTENCE` понижен до 3. `BeliefCrystallizationEngine` применяет асимметричную травму (x6).
  Taboo: ❌ Использование `PatternDetector` без передачи `L1Chronicle` в конструктор. ❌ Жёсткие пороги (if/else) в формировании убеждений.
  Files: pattern_detector.py, belief_crystallization_engine.py, tick_orchestrator.py

`ADR-O-322` [ONTO] **Epistemology Machine Architecture** — Система переведена в ранг "Машины Эпистемологии". 2 ортогональные оси (Мир, Познание) и downstream-потребители. Зафиксированы 5 инвариантов: невозрастание истины, запрет каузального возврата, изоляция потребителей, реляционная сущность, единственный мост Manifestation.
  Taboo: ❌ Возврат к линейному Pipeline. ❌ Нарушение 5 инвариантов. ❌ Чтение Reality потребителями (DM, UI).
  Files: architecture/perception_architecture.yaml, docs/audits/ADR-O-322_IMPACT.md

`ADR-O-323` [ONTO] **Atomic Fact Extraction** — `ObservedFact` строго атомарен. Составные выводы запрещены на уровне FactExtractor.
  Taboo: ❌ Составные факты типа `hand_on_weapon` в слое FactExtraction.
  Files: architecture/observed_fact_types.yaml, docs/audits/ADR-O-323_IMPACT.md

`ADR-O-324` [ONTO] **ObservationRelation Contract** — `ObservationContext` переименован в `ObservationRelation`. Объект отношения, а не мира. Только параметры среды.
  Taboo: ❌ Хранение NPC id, Faction, Mood, Memory внутри ObservationRelation.
  Files: architecture/perception_architecture.yaml, docs/audits/ADR-O-324_IMPACT.md

`ADR-O-325` [ONTO] **Authoring Data Isolation** — `signal_causes.yaml` вынесен в `authoring/`. Статические priors удалены.
  Taboo: ❌ Чтение `signal_causes.yaml` в runtime-физике. ❌ Статические вероятности в YAML.
  Files: architecture/authoring/signal_causes.yaml, docs/audits/ADR-O-325_IMPACT.md

`ADR-DM-001` [STD] **DM Prompt Minimum Contract** — В промпте DM ВСЕГДА минимум (локация + кто рядом). Никогда не пропускать автоматически. Симптомы — ВСЕГДА. DM описывает что видит игрок, даже в диалоге. NPC онтология — ВСЕГДА в промпте. Без этого DM не знает КТО перед ним.
  Taboo: ❌ Автоматический пропуск блоков локации/симптомов/NPC онтологии в сборке DM-промпта.
  Files: agents/dm_agent.py

`ADR-O-148` [STD] **Canonical NPC Name** — Каноническое имя NPC — единый источник истины для DM-агента.
  Files: agents/dm_agent.py

`ADR-O-311` [STD] **Exposure Default Contract** — Радиус выводится из semantic exposure level по умолчанию.
  Files: app/domain/communication.py

`ADR-S96.1` [ONTO] **L2.5 → L3 Projection Contract Closure** — `DriveResolver` переключён с сырых L1 событий на `CrystallizedBelief` (L2.5). Закрыт контур легитимной мутации драйвов (ADR-O-211). `resolve_drives` теперь принимает `beliefs: List[CrystallizedBelief]` и применяет их к `drives_base` (L0) для формирования эфемерной проекции (L3). Устранён `pass` (L3=L0).
  Taboo: ❌ Возврат к чтению L1Chronicle внутри DriveResolver. ❌ Прямая мутация L0 минуя Belief Layer.
  Files: drive_resolver.py, tick_orchestrator.py

`ADR-O-312` [ONTO] **Channel Topology Classification (Fundamental Physics Laws)** — Все внутренние процессы NPC классифицируются по физической природе явления, а не по реализации. Четыре фундаментальных класса:
  
  | Класс | Вопрос | Природа | Примеры | Persisted state |
  |-------|--------|---------|---------|-----------------|
  | **Field** | Среда действует постоянно? | Непрерывное поле среды | Социальность, свет, шум, температура | EMA (полураспад) |
  | **Reservoir** | Внутри организма что-то накапливается/расходуется? | Запас с притоком/оттоком | Усталость, голод, алкоголь, раны | Уровень + decay |
  | **Structural** | Меняется ли структура личности/отношений? | История деформаций | Доверие, репутация, травма, отношения | Накопитель + hysteresis |
  | **Cognitive** | Меняется ли модель мира NPC? | Знание и выводы | Убеждения, ожидания, подозрения, секреты | Crystallized beliefs |
  
  - **Field Channel** реализуется как: `Сенсор → EMA → Error = Setpoint - EMA → Utility Deformation`. Не имеет собственного "запаса". Мотивация = ошибка регуляции.
  - **Класс канала определяется природой явления, а не реализацией.** EMA — лишь один из способов моделирования Field. Завтра можно заменить на Kalman Filter или Diffusion Field.
  
  **Социальность = Field Channel.** `social_satiation` объявляется @deprecated. Мотивация вычисляется на лету: `error = setpoint - EMA`.
  
  Taboo: ❌ Определение класса канала по реализации (EMA/integrator), а не по физике явления. ❌ Введение промежуточного state-интегратора для Field Channel. ❌ Удаление deprecated-полей без эмпирического подтверждения.
  
  Status: VERIFIED (Social Field Channel MVP)
  Files: homeostasis_projector.py, social_input_projector.py, behavior_modifiers.py

`ADR-O-313` [ONTO] **Universal Task Layer (Producer/Consumer Materialization)** — Тяжёлые процессы (разговор, ремесло, торговля) отделены от симуляции. Архитектура: `Need → Decision (Intent) → Task (Queue) → Materialization (Worker) → Event (Projection)`. 
  - Симуляция (TickOrchestrator) не вызывает материализацию напрямую. Она создаёт `Task` и кладёт его в очередь `scene_state["pending_tasks"]`.
  - `TaskScheduler` (живёт в `game_loop`, не в ядре) потребляет задачи, выполняет тяжёлые операции (LLM, экономика) через `TaskExecutor` и возвращает `Artifact`.
  - `Materializer` превращает `Artifact` в `WorldEvent` (EventDTO) и публикует в `EventBus`.
  - **Пример с диалогом:** `DecisionHub` создаёт `CommunicationIntent` → `TaskScheduler` превращает его в `QueuedTask(DialogueRequest)` → `DialogueExecutor` (LLM) генерирует текст → `DialogueMaterializer` публикует `NPC_SPOKE`.
  Taboo: ❌ Вызов LLM или других блокирующих I/O операций внутри `TickOrchestrator`/`DecisionHub`. ❌ Связывание интента напрямую с материализацией.
  Status: VERIFIED (Dialogue System v2.0 Integrated)
  Files: domain/execution.py, domain/communication.py, services/execution/dialogue_executor.py, services/execution/dialogue_materializer.py, services/game_loop/task_scheduler.py, services/phases/post_decision.py
