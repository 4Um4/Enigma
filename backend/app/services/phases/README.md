# Директория `phases/` — Контракты Фаз Тик Оркестратора

Эта директория содержит модули, инкапсулирующие бизнес-логику фаз симуляции (Тик Оркестратора).
Оркестратор (`tick_orchestrator.py`) выступает в роли тонкого диспетчера, делегируя выполнение тяжёлой логики этим модулям.

**Главное правило:** Импорты внутри модулей должны быть отложенными (lazy imports), чтобы избежать циклических зависимостей.

---

## Карта фаз → файлов

| Фаза | Файл | Назначение |
|---|---|---|
| 0 (Simulation) | `simulation.py` | LifeEngine.tick(), MovementEngine, Traversals |
| 0.5 (Decay) | `idle_services.py` | Time-driven decay, DynamicAffordanceField purge |
| 0.6 (Sleep) | *вне phases/* (`services/npc/sleep_lifecycle_service.py`) | Sleep onset, DreamSignal, recovery (ADR-O-353/356) |
| 1 (Input) | `input.py` | InterventionEvent, WillpowerGate, Affective Resonance |
| 2 (EventBus) | *inline в orchestrator* | SpatialEventDetector → NPC_MOVED, PROXIMITY |
| 3 (Memory) | `memory.py` | MemoryManager.apply() для затронутых NPC |
| 4 (Pre-Decision) | *inline в orchestrator* | TopicExtractor → topic для каждого NPC |
| 5 (Decision) | `decision.py` | TickState (immutable) → NpcTickPipeline.run() (pure reducer) → TickMutation |
| 5 (Movement) | `movement_bridge.py` | Movement Bridge: process_movement_intents |
| 6-7 (Post-Decision) | `post_decision.py` | IntentEventAdapter, WindupWriteGate, CommitmentRegistry mirrors |
| 8 (Reduction) | `reduction.py` | Layered Reduction: Physical → Cognitive → Social |
| 9 (Integration) | `integration.py` | CFRM P2, L2.5 Belief Crystallization, ClaimEventSubscriber, WorldSnapshot |
| 9.1 (Affective) | `affective.py` | AffectiveIntegrator, surprise_delta (NOT EmotionTag), EmotionTransition |
| 0.75 (Traversal) | `traversal.py` | TraversalState FSM, Shadow Observation (Dual Rail) |
| — (Validation) | `validation.py` | EquivalenceValidator: Shadow vs Legacy drift A-E |
| 10 (Persistence) | `commit_phase.py` | atomic_commit_all, L1Chronicle, EpistemicStore round-trip |

---

## Детали по модулям

### 1. `simulation.py` (Фаза 0: Симуляция жизни)
- **Назначение:** Вызов `LifeEngine.tick()`, обработка пространственных изменений (инъекция `SceneChange`).
- **Вход:** `_TickContext` (содержит `all_npcs_raw`, `scene_state`, `spatial_service`).
- **Выход:** Мутация `ctx.all_npcs_raw` (генерация интентов, дельт), заполнение `ctx.delta_buffer`.
- **Инварианты:**
  - Запрет на прямую мутацию позиций (ADR-051).
  - Мёртвые NPC исключаются до Фазы 1 (ADR-S93.1).
  - NPC в статусе `MOVING` не генерируют новые интенты (ADR-154).
  - `apply_with_shadow_observation()` — Dual Rail execution (ADR-O-201).

### 2. `idle_services.py` (Фаза 0.5: Затухание в простое)
- **Назначение:** Time-decay для `PerceptualKernel`, `DynamicAffordanceField` (purge/decay), `AffectiveDecayHandler`.
- **Вход:** `_TickContext`, экземпляры сервисов затухания.
- **Выход:** Мутация `ctx.delta_buffer` (отрицательные дельты для затухания).
- **Инварианты:**
  - `affective_load` использует асимметричный аттрактор (гистерезис), не интегратор с утечкой (ADR-138).
  - `shock_impulse` обязательно затухает (ADR-109).
  - `game_time_seconds += GAME_TICK_INTERVAL_SECONDS` — единственный источник времени (ADR-O-302).
  - ⚠️ `ExpectationStore` захоронен (COV-D100/S351) — PE Decay мёртвый код, не использовать.

### 2.1. Sleep Lifecycle (Фаза 0.6 — вне phases/)
- **Файл:** `services/npc/sleep_lifecycle_service.py` (ADR-O-353/356).
- **Назначение:** `SleepLifecycleService.tick()` — arousal accumulation, CouplingProfile update, DreamSignal generation, sleep_end SceneChange.
- **Инварианты:**
  - Сон = эмерджентное свойство телесной архитектуры, не скриптовый `is_sleeping` флаг.
  - `sleep_onset_tick` — ФАКТ (is not None), единственный писатель — SleepLifecycleService.
  - `TimeSkipExecutor` прерывается событиями сна.

### 3. `input.py` (Фаза 1: Ввод и Воля)
- **Назначение:** Обработка `InterventionEvent`, маршрутизация, `WillpowerGate` (Cumulative Strain Model), Affective Resonance.
- **Вход:** `_TickContext` (с `interventions`).
- **Выход:** `IntentPressureProfile`, `AmplifiedPressureProfile`, `WillResponseDTO`, заполнение `ctx.delta_buffer` (например, `stress_delta`).
- **Инварианты:**
  - `WillpowerGate` вызывается строго 1 раз за цикл (Rule 8).
  - `semantic_action` читается с fallback (ADR-083).
  - Somatic Gate: проверка `shock > 0.7` ДО семантического парсинга (ADR-O-139).
  - Ядро не знает 'player' или 'dm_ctx' — только `InterventionEvent` (ADR-TZ08-1).

### 4. `memory.py` (Фаза 3: Память)
- **Назначение:** `MemoryManager.apply()` для затронутых NPC. Обновляет `NPCState` ДО принятия решения (Устав §3.1).
- **Вход:** `_TickContext`, phase_2_events.
- **Выход:** Мутация `ctx.all_npcs_raw` (память NPC).
- **Инварианты:**
  - Early exit, если нет phase_2_events.
  - `MemoryManager` — единственный писатель в память (Устав §4.1.2).

### 5. `decision.py` (Фаза 5: Принятие решений)
- **Назначение:** Предзагрузка данных (`TickState`), вызов Pure Reducer (`NpcTickPipeline.run()`), применение `TickMutation`.
- **Вход:** `_TickContext`, `TickState` (immutable snapshot).
- **Выход:** `TickMutation` (deltas, intents, pending_io), мутация `ctx.all_npcs_raw`.
- **Инварианты:**
  - `DecisionHub` работает на консолидированном восприятии прошлого тика (T-1).
  - Viability Pre-Generation Gate: ROUTINE исключается до генерации интентов при угрозе (ADR-O-137).
  - `L2.5 Beliefs` инжектируются как `drive_modifiers` (ADR-O-305).
  - `NpcTickPipeline.run()` — pure reducer, `svc` параметр убит (ADR-TZ10-1).

### 5.1. `movement_bridge.py` (Фаза 5: Movement Bridge)
- **Назначение:** `process_movement_intents` — мост между DecisionHub и MovementEngine.
- **Инварианты:**
  - `MovementIntent` без `pressure_sources` запрещён (Rule 6).
  - Boundary node — интерфейс между локациями, не место обитания (ADR-145).

### 6. `post_decision.py` (Фазы 6, 7: Адаптация интентов и Windup)
- **Назначение:** `IntentEventAdapter` (`CommunicationIntent` → `EventDTO`), `WindupWriteGate` (перехват ATTACK для создания `ActionWindup`), `CommitmentRegistry` mirrors (ADR-O-363/365).
- **Вход:** `ctx.communication_intents`, `ctx.windup_registry`, `ctx.active_commitments`.
- **Выход:** Публикация `EventDTO` на `EventBus`, создание/обновление `ActionWindup`, терминальные зеркала задач в `commitment_registry`.
- **Инварианты:**
  - `IntentEventAdapter` — единственная точка превращения решения в событие (Устав §3.3).
  - Публикация EventDTO атак с windup происходит только в Фазе 7 (ADR-O-310).
  - `commitment_id = H(tick, npc_id, action, ordinal)` — uuid4 запрещён (ADR-O-363).
  - Терминальные зеркала задач — через outbox (async-воркер никогда не пишет реестр, ADR-O-365).

### 7. `reduction.py` (Фаза 8: Многоступенчатая редукция)
- **Назначение:** Layered Reduction (Physical → Cognitive → Social). Обработка `EventDTO` подписчиками (`CombatSubscriber`, `ReactionSubscriber`).
- **Вход:** `ctx.delta_buffer`, события с `EventBus`.
- **Выход:** Дельты физиологии, восприятия, эмоций (через `DeltaBuffer`).
- **Инварианты:**
  - `CombatSubscriber` пишет ТОЛЬКО `PhysiologyPayload` (Rule 9).
  - Прямая генерация эмоций из боевых событий запрещена (только через Perception).
  - `StateApplicator.apply_batch()` — единый мутатор (Устав §3.8).
  - L5 Post-Commit Validation: `sum(drives)==1.0`, bounds, NaN (ADR-O-207).

### 8. `integration.py` (Фаза 9: Интеграция и Снапшот)
- **Назначение:** CFRM P2 (`LocalCausalSolver`), L2.5 Belief Crystallization, `ClaimEventSubscriber` (Epistemic Core), сборка `WorldSnapshotDTO` + `AvatarStateDTO`.
- **Вход:** `_TickContext`, финальное состояние NPC.
- **Выход:** `ctx.perception_snapshot`, обновление `CrystallizedBeliefStore`, `EpistemicStore` (round-trip).
- **Инварианты:**
  - `MemoryManager.check_identity_promotion` работает только при наличии `phase_2_events` (ADR-S86.7).
  - Эпистемический барьер: DM-агент не читает внутренние состояния NPC (ADR-TZ08-4).
  - `ClaimEventSubscriber` слушает `COMMUNICATION_CLAIM` → обновляет `EpistemicStore` (ADR-O-354/358).
  - `ConclusionStore` (BC-1, ADR-O-381) — dormant default OFF, NO-VACUUM.

### 9. `affective.py` (Фаза 9.1: Аффективный пайплайн)
- **Назначение:** Вычисление интеграла аффекта (`AffectiveIntegrator`), фазовый переход эмоций (`EmotionTransition`).
- **Вход:** `ctx.all_npcs_raw` (поля `perceptual_kernel`, `affective_load`).
- **Выход:** `EmotionPayload` в `ctx.delta_buffer`.
- **Инварианты:**
  - Эмоции не генерируются из одного события. Они рождаются из интеграла угрозы по времени (ADR-049).
  - `Anti-DOUBLE TRUTH bootstrap` при `emotion != NEUTRAL` но `affective_load < threshold` (ADR-117).
  - ⚠️ `EmotionTag` убит как причина (ADR-O-206). Память/вес = `surprise_delta` (`abs(affective_load - prev)`), не тег. Скорость забывания = каузальная глубина.
  - `integrate_affective_pressure()` — единый владелец Active Inference + Hysteresis.

### 10. `motion.py` (ETKE-IK: Непрерывное движение)
- **Назначение:** Обработка `DriveVector` (микро-перемещения). `CollisionAvoidance`, `SteeringResolver`, `MotionIntegrator`.
- **Вход:** `ctx.all_npcs_raw` (поле `drive_vector`), `WorldTopologyProvider`.
- **Выход:** Обновление `local_position` и `velocity` в `ctx.all_npcs_raw`.
- **Инварианты:**
  - `DriveVector` эфемерен: очищается при каждом `tick_decisions` (L3-P1).
  - FLEE через `DriveVector` использует инвертированный `direction` (ADR-ETKE-ACT1).
  - `SOCIAL_DRIFT` используется вместо рандомного `PATROL` (ADR-S91).

### 11. `traversal.py` (Macro-traversals и Shadow Observer)
- **Назначение:** Обработка `MovementIntent` (макро-перемещения). `EventCompiler`, `ProjectionEngine`, `EquivalenceValidator` (Dual Rail).
- **Вход:** `ctx.movement_intents`, `ctx.scene_state`.
- **Выход:** `ThickSceneChange`, мутация `active_traversals` в `scene_state`.
- **Инварианты:**
  - `apply_changes` не может перезаписать активный транзит (`status="MOVING"`) (ADR-130.1).
  - `EventCompiler` не создаёт `TraversalContract` со статусом `COMPLETED` (ADR-O-201.4).
  - `EquivalenceValidator` отключен для кросс-локационных переходов (ADR-O-201.2).
  - `TraversalState` lifecycle управляется `SceneStateManager` через FSM `transition_traversal()` (ADR-TRAV-FSM).
  - `CommitmentRegistry` — владелец behavioral ownership; `SSM.gc_traversals` — единственный GC-владелец (ADR-O-363).

### 12. `validation.py` (Валидация дрейфа)
- **Назначение:** Dual Rail Drift Validation. Сравнение применения физики через Legacy (`scene_manager.apply_changes`) и Shadow (`EventCompiler`).
- **Вход:** `snapshot`, `thick_changes`, `scene_state`.
- **Выход:** Логирование дрейфа (DRIFT A-E), вызов `OntologyViolationError` при критических разрывах.
- **Инварианты:**
  - Shadow Observer только наблюдает и логирует, не вмешиваясь в каузальный поток (Устав §11.2).
  - Проверка `sum(drives)==1.0`, bounds, NaN (ADR-O-207).
  - Drift классы: A (косметический), B (проекционный), C (топологический), D (каузальный), E (онтологический).

### 13. `commit_phase.py` (Фаза 10: Персистентность)
- **Назначение:** Изоляция Фазы 10 — `atomic_commit_all`, `L1Chronicle` flush, `EpistemicStore` round-trip, `DRFBus` drain.
- **Вход:** `_TickContext`, финальный `scene_state`.
- **Выход:** Персистентное состояние (SQLite), append-only L1Chronicle.
- **Инварианты:**
  - `SceneStateManager.commit_tick_result()` → `SQLitePersistenceAdapter.atomic_commit()` (Устав §3.10).
  - `L1Chronicle` — append-only, удаление запрещено (Rule 28).
  - `EpistemicStore` — per-agent, round-trip integrity (S193).
  - `atomic_commit_all` вызывается ровно 1 раз в `unlock_tick()` (S186/§9.4).