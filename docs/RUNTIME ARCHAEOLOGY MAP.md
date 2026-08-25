# RUNTIME ARCHAEOLOGY MAP (v3.1 — Causal Kernel & Identity Compliant)

**Статус:** Актуальная топология рантайма. Нарушение потока = архитектурный баг.
**Объект аудита:** TickOrchestrator + Causal Kernel (EventCompiler/ProjectionEngine) + Identity Layer (L1/L3) + Persistence

---

## ТРИ ФУНДАМЕНТАЛЬНЫЕ ИСТИНЫ РАНТАЙМА

### Истина №1: Источник истины = Snapshot + Chronicle
В ENIGMA нет классического Event Sourcing для восстановления *состояния*. State — это слепок, но *Идентичность* — это история.
- **State (Состояние):** `LifeEngine._npc_cache` (RAM, dict references) + SQLite `state_kv` (`INSERT OR REPLACE`). Эфемерно и перезаписываемо.
- **Identity (Идентичность):** `L1Chronicle` (Append-only история деформаций). Не перезаписывается, только аппендится. Персистентна в SQLite (таблица `l1_chronicle_events`, ADR-L1-PERSIST).
- **Пересчет:** L3 (`EffectiveDrives`) — строго эфемерная проекция, вычисляемая из L0 + L1 каждый тик. Кэширование L3 = смерть причинности (ADR-O-208).

### Истина №2: Время и Физика — одно целое (Causal Kernel)
Не существует независимого слоя `resolve(entity, dt)`. Время неразрывно связано с циклом `TickOrchestrator.execute()`.
При этом физика (pathfinding, RNG, geometry, boundary resolution) вычисляется **ТОЛЬКО** внутри `EventCompiler` на основе иммутабельного `SnapshotKernel`. Случайность детерминирована через `KernelRNG(tick, npc_id, salt)` (ADR-O-301). `ProjectionEngine` — чистая функция проекции без вычислений (ADR-O-201).

### Истина №3: Нет Event Sourcing для State (но есть для Identity)
- `ctx.delta_buffer.clear()` уничтожает дельты состояния после применения.
- `INSERT OR REPLACE` перезаписывает State целиком.
- Восстановление *состояния* из истории физики невозможно. Но *причины* этого состояния сохраняются в `L1Chronicle` и `CausalTrace`.

---

## КАРТА ИСПОЛНЕНИЯ (Causal Write Path)

```text
1. Загрузка (Read Path)
   SQLite -> load_npcs_merged() -> LifeEngine._npc_cache (RAM)
   L1 Chronicle -> Загружается в память (append-only list/dict)
   Внешний вход — строго через `InterventionEvent` (ADR-TZ08-1). Ядро не знает 'player' или 'dm_ctx'.

2. Симуляция и Давление (Phase 0-5)
   LifeEngine.tick() -> Intent/MacroMovementGoal
   DecisionHub (Pure Scoring) -> Модулирует Utility, генерирует Intent
   DRFBus -> Каузальный арбитраж (drf_ctx)

3. Срез Реальности (Pre-Compile)
   TickOrchestrator -> Создает SnapshotKernel (Immutable)
   └── Включает: all_npcs_raw, scene_state, traversals, spatial data

4. Генерация Физики (Causal Kernel) [ADR-O-201]
   EventCompiler(SnapshotKernel, Intents) 
   └── Вычисляет: Pathfinding, RNG (через KernelRNG, ADR-O-301), Boundary transitions, Geometry
   └── Порождает: ThickSceneChange (Full Physical Contract)
   └── ЗАПРЕТ: SpatialService запросы или RNG внутри apply_changes

5. Мутация Состояния (Phase 1-9 -> StateApplicator)
   Производители дельт -> ctx.delta_buffer.append(StateDeltas)
   └── Identity: L1Chronicle.append(TraitDriftEvent)
   _aggregate_deltas() (Схлопывание по DRSL)
   StateApplicator.apply_batch(deltas, all_npcs_raw)
   └── Мутация all_npcs_raw in-place (dict references)
   └── L5 Валидация: Проверка sum(drives)==1.0, bounds, NaN (ADR-O-207)
       └── FAIL -> OntologyViolationError (Убивает тик)

6. Проекция и Применение Физики [ADR-O-201]
   ProjectionEngine.apply_changes(ThickSceneChange)
   └── Чистая проекция (Pure Apply). Без ветвлений >1 уровня.
   └── Запись координат, статусов в scene_state/npc_positions

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

`DeltaBuffer` — центральный водосток системы. Изолировать один домен от DeltaBuffer невозможно.

### C2: Кто читает all_npcs_raw? (Центральный ствол)
Зависимость пронизывает систему, но теперь оборачивается в `SnapshotKernel` для Causal Kernel:
- **SnapshotKernel:** Упаковывает `all_npcs_raw` для EventCompiler.
- **Потребители Pipeline:** DirectiveInterpretationSubscriber, Will/Decision, CFRM, Affective Pipeline, BehaviorManifestationService.
- **Persistence:** LifeEngine.update_cache(), SQLite.

### C3: Какие фазы действительно обязательны?
- **Нельзя пропустить:** Phase 0 (LifeEngine), Phase 0.5 (Time Decay), Phase Compile (EventCompiler), Phase Apply (ProjectionEngine), Phase 10 (Persistence).
- **Можно пропустить при отсутствии событий:** Phase 2 (EventBus), Phase 3 (Memory). Имеют early exit guards.

### C4: Что выживает между тиками?
- **State:** SQLite + Cache (Мутируется in-place)
- **Identity:** L1Chronicle (Append-only, SQLite persistence)
- **Memory:** SQLite
- **Relations:** RelationshipStore
- **Не выживает:** DeltaBuffer, DRFBus Claims, Events, TickContext, SnapshotKernel, EffectiveDrives (L3)

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
- **Слой физики:** ДА. `EventCompiler` вычисляет физику только для NPC с активными интентами/транзитами на основе `SnapshotKernel`.
- **Слой презентации:** ДА. `dm_scene_builder._filter_by_visibility` отсекает невидимых NPC от LLM.
- **Слой времени:** ДА (частично). `reconcile_state()` позволяет аналитически догнать время при загрузке.
- **Слой Валидации:** ДА. `StateApplicator` выполняет L5 Post-Commit проверку онтологии (ADR-O-207).
- **Слой промотки времени:** ДА. `TimeSkipExecutor` (ADR-TZ08-ADD-1) вызывает `Kernel.execute()` в цикле, не создавая второй симулятор. Детекторы (SignificanceDetector, SemanticMilestoneFilter) читают `TickResultDTO`.

---

## КАРТА НАБЛЮДАЕМОСТИ (CDS)

```text
Источник: TickOrchestrator, Pipeline
     ↓
CausalObserver (Пассивный аудитор)
     ↓
CausalTrace (Пишется в reports/)
     ↓
LAST_SESSION.md (Контекст для LLM-архитектора)

ЗАПРЕТЫ:
- CDS не пишет в DeltaBuffer
- CDS не прерывает Pipeline при крушении (только логирует [PIPELINE][CRITICAL])
- Данные отчетов CDS не парсятся рантаймом для принятия решений


ТЗ отложенное в долгий ящик:
## Оставшийся резерв (только если захотите позже)

Единственный крупный потребитель — **бут uvicorn: 5.66с** (импорт 0.74с + ~5с lifespan: GameLoop init, стартовые таблицы, LLM health check с 30с-таймаутом в фоне). Инфраструктура для этого уже есть: health-эндпоинт умеет отдавать `startup_status`, лаунчер может пускать в меню до полной готовности GameLoop и догружать его, пока игрок смотрит на меню. Потенциал ещё −3…4с (итог ~3–4с до меню). Но это отдельная задача с изменением порядка жизненного цикла — по протоколу требует ADR-PRE-FLIGHT (затрагивает startup-контракт GameLoop), не «парой строк». Рекомендую отложить до стабильного релиза текущих изменений.
