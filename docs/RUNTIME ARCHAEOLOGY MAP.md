# RUNTIME ARCHAEOLOGY MAP (v3.2 — актуализация под V.0.5.3.9.1)

**Статус:** Актуальная топология рантайма на версию **0.5.3.9.1** (ветка `V.0.5.3.9.1_ДОВОДКА_2`). Нарушение потока = архитектурный баг.
**Объект аудита:** GameLoop + TickOrchestrator + Causal Kernel (EventCompiler/ProjectionEngine) + Commitment Layer + Identity (L1/L3) + Persistence + Relationship Engine Contract (ADR-O-369)

> Примечание по терминологии: в документах архитектуры (`architecture/pipeline.yaml`, сгенерированные схемы) «SnapshotKernel» — это *архитектурный ярлык* для иммутабельного среза реальности. В коде этому ярлыку соответствуют **`WorldSnapshot`** (`backend/app/models/world_snapshot.py`, frozen dataclass) и **`WorldSnapshotDTO`** (`backend/app/domain/snapshot.py`). Отдельного класса с именем `SnapshotKernel` в коде НЕТ.

---

## ТРИ ФУНДАМЕНТАЛЬНЫЕ ИСТИНЫ РАНТАЙМА

### Истина №1: Источник истины = Snapshot + Chronicle
В ENIGMA нет классического Event Sourcing для восстановления *состояния*. State — это слепок, но *Идентичность* — это история.
- **State (Состояние):** `LifeEngine._npc_cache` (RAM, dict references) + SQLite `state_kv` (`INSERT OR REPLACE`). Эфемерно и перезаписываемо.
- **Identity (Идентичность):** `L1Chronicle` (`backend/app/services/npc/l1_chronicle.py`) — append-only история деформаций. Персистентна в SQLite (таблица `l1_chronicle_events`, ADR-L1-PERSIST). Только аппендится, не перезаписывается.
- **Пересчет:** L3 (`EffectiveDrives`) — строго эфемерная проекция, вычисляемая из L0 + L1 каждый тик через `DriveResolver`. Кэширование L3 = смерть причинности (ADR-O-208).

### Истина №2: Время и Физика — одно целое (Causal Kernel)
Не существует независимого слоя `resolve(entity, dt)`. Время неразрывно связано с циклом `TickOrchestrator.execute()`.
Физика (pathfinding, RNG, geometry, boundary resolution) вычисляется **ТОЛЬКО** внутри `EventCompiler.compile(snapshot: WorldSnapshot, change: SceneChange) -> ThickSceneChange` (`backend/app/services/event_compiler.py`) на основе замороженного среза `WorldSnapshot`. Случайность детерминирована через `KernelRNG(tick, npc_id, salt)` (`backend/app/services/npc/kernel_rng.py`, ADR-O-301). `ProjectionEngine` (`backend/app/services/projection_engine.py`) — чистая функция проекции `apply()` / `apply_batch()`, без вычислений (ADR-O-201).

### Истина №3: Нет Event Sourcing для State (но есть для Identity)
- `ctx.delta_buffer.clear()` уничтожает дельты состояния после применения.
- `INSERT OR REPLACE` перезаписывает State целиком.
- Восстановление *состояния* из истории физики невозможно. Но *причины* этого состояния сохраняются в `L1Chronicle` и `CausalTrace`.

---

## КАРТА ИСПОЛНЕНИЯ (Causal Write Path)

```text
1. Загрузка (Read Path)
   SQLite -> load_npcs_merged() -> LifeEngine._npc_cache (RAM)
   L1 Chronicle -> Загружается в память (append-only)
   Внешний вход — строго через `InterventionEvent` (ADR-TZ08-1). Ядро не знает 'player' или 'dm_ctx'.
   Точка входа над ядром — `GameLoop` (backend/app/services/game_loop/__init__.py):
   new_game(), idle_tick(), skip_time(), run_turn()/stream_turn() — всё делегирует в TickOrchestrator.
   Frontend ходит через `frontend/game_loop_bridge.py` (GameLoopBridge — синхронная обёртка над async GameLoop).

2. Симуляция и Давление (Phase 0-5)
   LifeEngine.tick() -> Intent/MacroMovementGoal
   DecisionHub (Pure Scoring) -> Модулирует Utility, генерирует Intent
   DRFBus -> Каузальный арбитраж (drf_ctx)

2.5 Commitment Layer (S203.1 / Stage 2A)
   backend/app/domain/action_commitment.py — FSM «что NPC обязан исполнять»
   (commit_registry, commitment_arbiter, windup, sweep-правила в тестах test_action_commitment.py).
   Онтологический слой МЕЖДУ решением (Intent) и исполнением (Traversal/Windup).
   Phase 7 (_phase_7_windup_resolution) — Execution Gate по ADR-O-310.

3. Срез Реальности (Pre-Compile)
   TickOrchestrator (_get_snapshot_builder / snapshot builder) -> Создает WorldSnapshot (frozen dataclass)
   └── Включает: all_npcs_raw, scene_state, traversals, spatial data

4. Генерация Физики (Causal Kernel) [ADR-O-201]
   EventCompiler.compile(WorldSnapshot, SceneChange)
   └── Вычисляет: Pathfinding, RNG (через KernelRNG, ADR-O-301), Boundary transitions (is_boundary=True принудительно), Geometry (fallback target_xy = (0.0, 0.0))
   └── Порождает: ThickSceneChange (Full Physical Contract)
   └── ЗАПРЕТ: SpatialService запросы или random.* внутри apply/apply_batch

5. Мутация Состояния (Phase 1-9 -> StateApplicator)
   Производители дельт -> ctx.delta_buffer.append(StateDeltas)
   └── Identity: L1Chronicle.append(TraitDriftEvent)
   _aggregate_deltas() (Схлопывание по DRSL)
   StateApplicator.apply_batch(deltas, all_npcs_raw)
   └── Мутация all_npcs_raw in-place (dict references)
   └── L5 Валидация: sum(drives)==1.0, bounds, NaN (ADR-O-207)
       └── FAIL -> OntologyViolationError (Убивает тик)

6. Проекция и Применение Физики [ADR-O-201]
   ProjectionEngine.apply(state, ThickSceneChange) / apply_batch(state, [ThickSceneChange])
   └── Чистая проекция (Pure Apply). Без ветвлений >1 уровня, без сервисов, без RNG.
   └── Запись координат, статусов в scene_state/npc_positions
   └── Legacy-путь: SceneStateManager.apply_changes() существует как мост (GameLoop.apply_changes),
       миграция мутаций в EventCompiler/ProjectionEngine — по фазам 0->1->2->3 (ADR-O-201).

7. Сохранение (Phase 10)
   LifeEngine.update_cache(all_npcs_raw) (Синхронизация RAM)
   SceneStateManager.commit() -> SQLitePersistenceAdapter.atomic_commit()
   └── _upsert (INSERT OR REPLACE) -> State перезаписан
   L1 Chronicle -> Персистенция истории дрейфа
```

---

## КАРТА ИДЕНТИЧНОСТИ И ОНТОЛОГИИ (Identity Pipeline)

```text
Источник L0 (Archetype Drives)
     +
История L1 (L1Chronicle: TraitDriftEvent[])
     │
     ↓ (Каждый тик)
DriveResolver.resolve_drives(L0, L1_weighted)
     │
     ↓
EffectiveDrives (L3) [MappingProxyType - Immutable]
     │
     ├→ Модулирует DecisionHub (Utility Deformation)
     ├→ Модулирует RiskPerceptionProfile
     └→ Модулирует Somatic Urgency (через Willpower)
     
Калибровка:
CalibrationEngine -> Предотвращает осцилляцию L0 (ADR-O-211)

Жизненный цикл L3:
- Рождается в начале тика
- Эфемерен (не переживает сериализацию)
- Умирает в конце тика
- Кэширование = ЗАПРЕЩЕНО (L3-P1)
```

---

## КАРТА ЗАВИСИМОСТЕЙ (Этап C)

### C1: Кто производит StateDelta?
Дельты производятся 15+ модулями во всех доменах:
- **Combat:** ImpactEngine, InjuryProcessor, PhysiologyDecayHandler
- **Affective:** AffectiveDecayHandler, ReactionSubscriber, EmotionResolution
- **Social:** DirectiveInterpretationSubscriber, SocialDeltaEngine
- **Decision:** WillpowerGate, DecisionHub
- **Identity:** DriveResolver, CalibrationEngine
- **Epistemik:** EpistemicStore (убеждения/предикаты, подключается через set_epistemic_services)

`DeltaBuffer` — центральный водосток системы. Изолировать один домен от DeltaBuffer невозможно.

### C2: Кто читает all_npcs_raw? (Центральный ствол)
Зависимость пронизывает систему, но оборачивается в замороженный срез `WorldSnapshot` для Causal Kernel:
- **WorldSnapshot:** Упаковывает `all_npcs_raw` для EventCompiler.
- **Потребители Pipeline:** DirectiveInterpretationSubscriber, Will/Decision, CFRM, Affective Pipeline, BehaviorManifestationService.
- **Persistence:** LifeEngine.update_cache(), SQLite.

### C3: Какие фазы действительно обязательны?
Реальный порядок в `TickOrchestrator._run_core_phases()`:
- **Нельзя пропустить:** Phase 0 (Simulation, `phases/simulation.py`) → Phase 0.6 (Sleep Lifecycle, BUG-SLEEP-007) → Phase 0.5 (Idle Services / Time Decay) → Phase 0.75 (Traversal Lifecycle) → Compile (EventCompiler) → Apply (ProjectionEngine) → Phase 7 (Windup Resolution, Execution Gate ADR-O-310) → Phase 10 (Persistence).
- **Можно пропустить при отсутствии событий:** Phase 2 (EventBus), Phase 3 (Memory). Имеют early exit guards.
- **Прочие:** 1/1.1 (input merge), 4 (pre-decision), 5 (decision), 6 (post-decision), 8 (secondary drain), 9 (integration), POST-9 (_resolve_cross_location_transfers — очередь межлокационных переходов разрешается в начале тика целевой локации).

### C4: Что выживает между тиками?
- **State:** SQLite + Cache (Мутируется in-place)
- **Identity:** L1Chronicle (Append-only, SQLite persistence)
- **Memory:** SQLite
- **Relations:** RelationshipStore (backend/app/services/memory/relationship_store.py, кэш с TTL)
- **Epistemика:** EpistemicStore / crystallized_belief_store (внедряется в оркестратор через set_epistemic_services)
- **Commitments:** активные обязательства NPC переживают тик (FSM в domain/action_commitment.py, зеркальная валидация в traversal_schema.py)
- **Не выживает:** DeltaBuffer, DRFBus Claims, Events, TickContext, WorldSnapshot (frozen срез тика), EffectiveDrives (L3)

### C5: Кто предоставляет детерминированную случайность?
- **KernelRNG** (`services/npc/kernel_rng.py`): Единственный источник случайности в kernel layer (ADR-O-301).
- **Потребители:** DecisionHub (salt='decision_hub'), MovementEngine, StateApplicator, LifeEngine — каждый со своим salt.
- **ЗАПРЕТ:** `random.*` в kernel layer.

### C6: Минимальная единица симуляции и персистенции
- **Симуляция:** NPC (дельты группируются по `npc_id`, L3 вычисляется per-NPC)
- **Персистенция State:** Campaign/Location (атомарный коммит пакета `runtime:{campaign_id}`)
- **Персистенция Identity:** L1Chronicle (пакетная запись событий)

---

## КАРТА DRFBus (Эфемерный арбитраж)

```text
Производители:
- TickOrchestrator (emit через DRFExecutionContext)
- LifeEngine (emit через _claim_bus, инжектируется из ctx.drf_bus)
- npc_tick_pipeline (emit через drf_ctx)

Потребители:
- TickOrchestrator (_apply_drf_scoring_overlay — аддитивная модуляция приоритетов)

Жизненный цикл:
- Создается в __init__ оркестратора (Instance-level, ADR-134)
- Очищается в начале execute() (stream.clear())
- Дрейнится в Phase 10 (drain())
- Является эфемерным кэшем межфазного арбитража. Не переживает тик.

Инварианты:
- Pipeline получает drf_ctx (Scoped Ledger), а не голый drf_bus (ADR-136)
- Скоринг аддитивен: priority += energy × weight × alignment (ЗАПРЕТ: clamp/override, ADR-135)
```

---

## МЕХАНИЗМЫ "ЛЕНИВОСТИ" И ОГРАНИЧЕНИЙ В РАНТАЙМЕ

- **Слой симуляции:** НЕТ (пока). `LifeEngine.tick()` обходит всех NPC (кроме `tier == mass`). GCO (ADR-GL-202) спроектирован, но не реализован.
- **Слой физики:** ДА. `EventCompiler` вычисляет физику только для NPC с активными интентами/транзитами на основе замороженного `WorldSnapshot`.
- **Слой презентации:** ДА. `dm_scene_builder._filter_by_visibility` (backend/app/services/action/dm_scene_builder.py) отсекает невидимых NPC от LLM.
- **Слой времени:** ДА (частично). `reconcile_state()` позволяет аналитически догнать время при загрузке.
- **Слой Валидации:** ДА. `StateApplicator` выполняет L5 Post-Commit проверку онтологии (ADR-O-207).
- **Слой промотки времени:** ДА. `TimeSkipExecutor` (backend/app/services/world/time_skip_executor.py, ADR-TZ08-ADD-1) вызывает execute() оркестратора в цикле, не создавая второй симулятор. Детекторы (SignificanceDetector, SemanticMilestoneFilter) читают `TickResultDTO`. В GameLoop.skip_time — межпоточный skip_lock.

---

## КАРТА НАБЛЮДАЕМОСТИ (CDS)

```text
Источник: TickOrchestrator, Pipeline
     ↓
CausalObserver (Пассивный аудитор; diagnostics/causal_observer.py — читает лог-файл ПОСЛЕ завершения игры, пост-мортем)
     ↓
CausalTrace (Пишется в reports/)
     ↓
LAST_SESSION.md (Контекст для LLM-архитектора)

ЗАПРЕТЫ:
- CDS не пишет в DeltaBuffer
- CDS не прерывает Pipeline при крушении (только логирует [PIPELINE][CRITICAL])
- Данные отчетов CDS не парсятся рантаймом для принятия решений
```

---

## КАРТА СЕРВИСНОГО СЛОЯ НАД ЯДРОМ (GameLoop / TaskScheduler)

```text
GameLoop (backend/app/services/game_loop/__init__.py)
├── DI-конструктор: создаёт TickOrchestrator, SocialEngine factory, Epistemic core,
│   RelationshipStore, MemoryManager, Dialogue subscribers, Economy tracker.
├── new_game() / idle_tick() / skip_time() / run_turn() / stream_turn()
├── TaskScheduler (game_loop/task_scheduler.py): очередь задач на тик,
│   _MAX_TASKS_PER_TICK = 1 (одна задача на тик, без голодания).
├── Executors (backend/app/services/execution/): DialogueExecutor, NpcConversationExecutor
│   — паттерн QueuedTask -> Iterable[Artifact] (domain/execution.py).
├── Подфазы GameLoop: phase_1_input, phase_2_world_tick, dm_phase, phase_6_avatar, speech_scheduler...
└── Frontend-мост: frontend/game_loop_bridge.py (GameLoopBridge, синхронная обёртка над async).

Инвариант: GameLoop — фасад и DI-композитор. Вся симуляционная логика — в TickOrchestrator и ниже.
GameLoop НЕ мутирует state напрямую (apply_changes() — только делегация scene_manager'у).
```

---

## КАРТА КОНТРАКТНЫХ ГЕЙТОВ (линтеры / CI, ADR-O-369)

```text
Relationship Engine Contract (Phase A / M0, ADR-O-369):
- Канонический контракт: architecture/relationship_engine.yaml (37 узлов онтологии §5.0,
  классы I–IV + TOMBSTONE + FORBIDDEN, запреты №1–35, мораторий №35.2, инвариант Р17-INV-1).
- Гейт: scripts/lint_relationship_engine.py — CI (.github/workflows/ci.yml) + pre-commit.
  Закрывает «тихое воскрешение» уничтоженных сущностей (Infatuation, Bond, g, η_s и т.д.)
  и запретные рёбра; новый узел онтологии = вердикт GPT + ADR.
- Подавление легальных прозаических упоминаний: # noqa: RE35 (аудируемо в диффе).
- Рантайм Relationship Engine на момент контракта НЕ менялся — это заморозка границ перед RE-фазами.
- Владелец frustration: NeedLevel.frustration (§5.2-поле — read-only проекция).

Прочие гейты CI/pre-commit:
- lint_epistemic_boundary.py — граница эпистемики
- lint_enigma_ast.py — AST-права архитектуры (§1)
- lint_frontend_isolation.py — изоляция frontend от backend-внутренностей
- LOG-GATE: гейт файловых runtime-логов (ENIGMA_DISABLE_FILE_LOGS); git-хуки гоняют тесты без записи в data/logs.
- LOG-GATE-UI: диагноз «почему AI не работает» на экране загрузки (модель/CUDA/VRAM/антивирус/порт) — игроку не нужны логи.
```

---

## ОТЛОЖЕННЫЙ РЕЗЕРВ (долгий ящик, не забыть)

Единственный крупный потребитель старта — **бут uvicorn: ~5.7с** (импорт 0.74с + ~5с lifespan: GameLoop init, стартовые таблицы, LLM health check с 30с-таймаутом в фоне). Инфраструктура есть: health-эндпоинт умеет отдавать `startup_status`, лаунчер может пускать в меню до полной готовности GameLoop и догружать его, пока игрок смотрит на меню. Потенциал ещё −3…4с (итог ~3–4с до меню). Но это отдельная задача с изменением порядка жизненного цикла — по протоколу требует ADR-PRE-FLIGHT (затрагивает startup-контракт GameLoop), не «парой строк». Рекомендовано отложить до стабильного релиза.

---

*Карта актуализирована 29.08.2026 по коммиту `1ac78fa2` (RE-01 Phase A / M0, ADR-O-369), версия проекта 0.5.3.9.1.*
