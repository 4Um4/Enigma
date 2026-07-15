# CAUSAL CONTRACT v2.0: Архитектурные Законы ENIGMA

**Статус:** Исполняемый закон. Нарушение = архитектурный баг.
**Область применения:** Все компоненты бэкенда и фронтенда.

---

## 1. ФИЛОСОФИЯ

ENIGMA — это **единая каузальная система**, где игрок и NPC подчиняются одной онтологии. Нет читов, телепатии или нарушений причинно-следственной цепи. Симуляция честна.

### 1.1. Трёхуровневая архитектура восприятия

```
L0 (PERCEPTION) — Мир → Восприятие → NPC/Игрок
L1 (BODY) — Живой агент (NPCState) с инерцией личности
L2 (BEHAVIOR) — Решения на основе давления и архетипа
```

**Закон:** Нельзя передать Игроку информацию, которую NPC не мог бы получить через `PerceptualKernel`. Симметрия абсолютна.

---

## 1.2. ФУНДАМЕНТАЛЬНЫЕ ИНВАРИАНТЫ СИМУЛЯЦИИ

Эти три инварианта определяют онтологическую границу системы. Они не зависят от текущей реализации и переживут любой рефакторинг. Нарушение любого из них разрушает возможность причинно согласованной симуляции.

**Invariant I — Causal Provenance (Причинное Происхождение)**
> Любое изменение наблюдаемого состояния должно быть объяснимо конечной причинной цепью внутри модели.

**Invariant II — Historical Constraint (Историческое Ограничение)**
> Будущее состояние не должно вычисляться независимо от релевантной истории.

**Invariant III — Temporal Isolation (Временная Изоляция)**
> Каждый шаг симуляции вычисляется относительно неизменяемого прошлого. Результат вычисления шага не может изменить входные данные этого же шага.

> ⚠️ **ВНИМАНИЕ:** Соответствие конкретных модулей ENIGMA этим инвариантам описано в ненормативном документе `docs/CURRENT_IMPLEMENTATION_MAPPING.md`.

---

## 2. ОНТОЛОГИЧЕСКИЕ ПОСТУЛАТЫ

### 2.1. Единые источники истины

| Домен | Источник | Читается через | Запрет |
|-------|----------|-----------------|--------|
| **Пространство** | `SpatialService` (собирается `SpatialFactory.build_for_campaign()`) | `SpatialService.get_node()` | Чтение позиции из `scene_state["player_distances"]`. Прямая сборка `SpatialService.build_for_location()` в обход `SpatialFactory` |
| **Имена NPC** | `scene_state["npc_positions"][npc_id].name` | `_npc_id_to_display()` + Fuzzy Matching (Слой 2) | Отсутствие поля `name` → слепота резолвера (INV-NPC-NAME) |
| **Локация NPC** | `npc_state.location_id` (поле `location_id` авторитетно) | Любой читатель, но не `location` (legacy) | Чтение легаси-поля `location` |
| **Траектория движения** | `TraversalState` (от `MovementEngine`, lifecycle — `SceneStateManager` через FSM `transition_traversal`) | `SpatialService` → `DecisionHub` → `MovementEngine` → `SceneStateManager` | Телепортация без `TraversalState`. Перезапись активного транзита (`status="MOVING"`) в `apply_changes`. Создание нового `TraversalState` для `cause="traversal_complete"` (нужен только snap `local_position`) |
| **Позиция игрока** | `scene_state["npc_positions"]["player"]` (единственный SSOT) | `SpatialQueryService` | Чтение из `scene_state["player_spatial"]` (legacy, удалён). Дублирование позиций игрока в `player_spatial` |
| **Давление на личность** | `IntentPressureProfile` (от `IntentPressureResolver`) | `WillpowerGate` → `AmplifiedPressureProfile` | Хардкод давления. Обход `IntentPressureResolver` |
| **Эмоции** | `EmotionPayload` (от `AffectiveIntegrator` после фазового перехода) | `StateApplicator` → `NPCState.emotion_tag` | Прямая генерация эмоций из событий. Обход аккумулятора |
| **HP / Физиология** | `body_state["current_hp"]` (канонический источник) | `NPCState.effective_hp` / `effective_max_hp` (свойства с fallback на deprecated `hp`) | Прямая запись в `state.hp` в обход `body_state["current_hp"]` (HP Double Truth, ADR-HP-UNIFICATION) |
| **Отношения NPC-NPC** | `RelationshipStore` (SSOT, масштаб 0-100) | `DecisionHub` через `social_modifiers_map` | Персистенция `relationship_cache` внутри `NPCState` |
| **Каузальная случайность** | `KernelRNG(tick, npc_id, salt)` (ADR-O-301) | `_TickContext.rng_factory` | `random.*` в kernel layer. `DecisionHub()` без `rng`. `KernelRNG` без `salt` |
| **Идентичность NPC** | `L1Chronicle` (append-only, SQLite-персистентно) | `PatternDetector` → `EvidenceOfPersistence` → `BeliefCrystallizationEngine` | Удаление из `L1Chronicle`. `BeliefCrystallizationEngine` читает L1 напрямую (только через `EvidenceOfPersistence`) |

### 2.2. Движение = Результат, не Команда

**SceneChange — это projection свершившегося, а не триггер.**

Истинная физика:
```
Intent → IntentParametersDTO → IntentPressureResolver
  → WillpowerGate (проверка конфликта)
  → DecisionHub (Фаза 5, принятие решения)
  → MovementEngine (Фаза 5, Movement Bridge)
  → SceneChange → SceneStateManager.apply_changes() (Фаза 8)
  → TraversalState (lifecycle: PENDING → MOVING → COMPLETED/CANCELLED)
  → WorldSnapshotBuilder (Фаза 9, immutable projection)
  → API → Frontend
```

**Запрет:** `scene_manager.apply_changes()` из подписчика событий. SceneChange — это только адаптер для фронтенда.

### 2.3. TraversalState отделен от Личности

`TraversalState` живет в `scene_state["active_traversals"]`, **НЕ** в `NPCState`. Это данные о физическом движении, не о психике. Lifecycle управляется `SceneStateManager` через FSM `transition_traversal()` (ADR-TRAV-FSM).

**Структура (projection для фронтенда):**
```python
# scene_state["active_traversals"][npc_id] = {
#     "status": "PENDING" | "MOVING" | "COMPLETED" | "CANCELLED",
#     "source_node": str,
#     "target_node": str,
#     "path_waypoints": List[[x, y], ...],
#     "started_tick": int,
#     "duration_ticks": int,
#     "current_waypoint_idx": int,
# }
```

**Запреты:**
- Прямая мутация `status = "COMPLETED"` в обход `transition_traversal()`.
- Хардкод `current_waypoint_idx` в проекциях.

### 2.4. Тело — Gate of Perception (ADR-O-139)

Тело NPC (`body_state`) — это фильтр восприятия, а не пассивный контейнер HP. Боль и шок проходят через `PerceptualKernel.somatic_urgency` до того, как достигают психики.

**Каузальный порядок директивы:** `Body → Somatic Gate → Semantic Parsing → Legitimacy → Action`

**Запреты:**
- Fallback NPC dict без `body_state` — обязателен `BODY_STATE_DISABLED` sentinel.
- Проверка `shock > 0.7` ПОСЛЕ семантического парсинга директивы.
- `if not body_state: return []` без инъекции `BODY_STATE_DISABLED`.
- Инъекция `pain`/`shock` напрямую в `psyche` dict (только через `PK.somatic_urgency`).

### 2.5. Эфемерность L3 (EffectiveDrives)

L3 (`EffectiveDrives`) — строго эфемерная проекция, вычисляемая из L0 + L2.5 (`CrystallizedBelief`) каждый тик. Не переживает сериализацию, не кэшируется.

**Жизненный цикл L3:**
- Рождается в начале тика (`DriveResolver.resolve_drives(L0, beliefs)`)
- Эфемерен (не переживает сериализацию)
- Умирает в конце тика
- Кэширование = ЗАПРЕЩЕНО (L3-P1)

**Запреты:**
- Кэширование `EffectiveDrives`.
- Мутация `drives_runtime` (L0) минуя Belief Layer (L2.5) через `CalibrationEngine`.
- Фоллбэк на L0 (`drives_base`) в `InterpretationEngine` / `VerbalizationContext`.

---

## 3. ДОПУСТИМЫЙ ПОТОК РЕАЛЬНОСТИ (Per-Tick Cascade)

TickOrchestrator `_run_core_phases()` — единая точка входа. Нет ветвления player/idle (ADR-TZ08-2).

### Фаза 0: Simulation (LifeEngine)
```
LifeEngine.tick() → SceneChange (cognitive) + MovementIntent (schedule/need/random)
  → apply_with_shadow_observation() (Dual Rail, ADR-O-201)
  → _process_traversals() (STL Phase 1, boundary resolution)
  → _process_continuous_motion() (ETKE-IK, DriveVector → velocity)
```

### Фаза 0.5: Time-Driven Decay
```
idle_handlers → DynamicAffordanceField (purge + decay)
  → PE Decay (ExpectationStore)
  → Affective Decay, Perceptual Decay
  → TraversalExecutionSystem.advance() (projection TraversalState → local_position)
  → _advance_idle_time() (game_time_seconds += GAME_TICK_INTERVAL_SECONDS)
```
**Выполняется ВСЕГДА.** Время не останавливается (ADR-002). `game_time_seconds` — единственный источник времени (ADR-O-302).

### Фаза 1: Input Merge (NPIC Normalize → Intervention Routing → WillpowerGate)
```
InterventionEvent → _process_player_dm_action() / _process_player_action()
  → DirectiveInterpretationSubscriber (с инъекцией all_npcs_raw)
  → WillpowerGate (ОДИН раз за цикл, ADR-036)
  → delta_buffer (IdentityPayload, EmotionPayload)
```
**Ядро не знает 'player' или 'dm_ctx'.** Только `InterventionEvent` (ADR-TZ08-1).

### Фаза 2: EventBus (Spatial Events)
```
SpatialEventDetector (old vs new positions) → NPC_MOVED, NPC_PROXIMITY_CLOSE/LEAVE
  → EventBus (первичная волна)
```
Early exit, если нет изменений позиций.

### Фаза 3: Memory Phase
```
MemoryManager.apply() для затронутых NPC
```
Early exit, если нет phase_2_events.

### Фаза 4: Pre-Decision (TopicExtractor)
```
phase_2_events + STM buffer → topic для каждого NPC
  → fallback "наблюдение" (никогда не пустой)
```

### Фаза 5: Decision (Unified Execution Kernel, ADR-TZ09-1)
```
TickState (immutable snapshot, preloaded data) → NpcTickPipeline.run() (pure reducer)
  → TickMutation (npc_deltas, communication_intents, movement_intents, l1_drift_events, memory_events)
  → apply (orchestrator): build_npc_contexts, process_movement_intents
```
**Pure function:** `svc` параметр убит (ADR-TZ10-1). I/O мутации отложены.

### Фаза 6: Post-Decision (IntentEventAdapter + Windup Write Gate)
```
CommunicationIntent → IntentEventAdapter → EventDTO → EventBus
  ATTACK → ActionWindup (held_intent_id, 2 тика подготовки, ADR-O-310)
  DIALOGUE → QueuedTask → scene_state["pending_tasks"] (ADR-O-313)
```

### Фаза 7: Windup Resolution (Execution Gate)
```
windup_registry → completed windups → release held intent
  → Stale Intent Validation (actor alive? target alive? in scene?)
  → EventDTO publish или INTERRUPTED
```

### Фаза 8: Layered Reduction (drain + handle)
```
drain_events → handle (детерминированный порядок):
  perception → reaction → social → combat → homeostasis
  → Phase8Result → delta_buffer
  → StateApplicator.apply_batch() (единый мутатор)
  → L5 Post-Commit Validation (sum(drives)==1.0, bounds, NaN, ADR-O-207)
```

### Фаза 9: Integration (CFRM + WorldSnapshot)
```
LocalCausalSolver → FieldDisturbance → EventBuffer
  → BeliefCrystallizationEngine (L2.5, только при phase_2_events)
  → WorldSnapshotBuilder → WorldSnapshotDTO
```

### Фаза 9.1: Affective Pipeline
```
integrate_affective_pressure() (единый владелец Active Inference + Hysteresis)
  → Tuple[new_load, new_memory]
  → EmotionTransition (if load > threshold)
```

### Фаза 10: Persistence (Atomic Commit)
```
SceneStateManager.commit_tick_result() → SQLitePersistenceAdapter.atomic_commit()
  → INSERT OR REPLACE (State перезаписан)
L1Chronicle → SQLite (append-only)
DRFBus → drain()
```

### Фаза 10+: Player Perception (Explicit Snapshot Step, ADR-TZ08-8)
```
GameLoop (не ядро): PerceptionProjector
  → PhenomenologyProjectionService (PerceptionEvent)
  → PerceptualAttentionService (фильтр по бюджету)
  → PlayerPerceptionDTO (peripheral_cues, manifestations, active_perceptions)
  → WorldSnapshotDTO.player_perception
```

---

## 4. ЗАПРЕТЫ (HARD CONSTRAINTS)

### 4.1. Запреты на Движение

1. **Прямая мутация позиции:** `npc["position"] = ...` ❌
2. **Чтение позиции из неавторитетного источника:** `scene_state["player_spatial"]` ❌ → используй `SpatialQueryService` (player_spatial удалён, ADR-O-314)
3. **Телепортация Игрока:** `if target == player: bypass latency` ❌ → Игрок подвержен мембранам, как и NPC
4. **SceneChange как триггер:** `scene_manager.apply_changes()` из подписчика ❌ → только адаптер для фронтенда
5. **LOD0/LOD1 Corruption:** Передача `local_target_xy` в `MacroMovementGoal` или `target_node_id` в `LocalSteeringGoal` ❌ → физики разделены
6. **Перезапись активного транзита:** `apply_changes` не может перезаписать `status="MOVING"` (ADR-130.1)
7. **Новый транзит на complete:** `cause="traversal_complete"` → snap `local_position`, не новый `TraversalState` (ADR-130.2)
8. **Boundary node как цель:** Boundary node — интерфейс между локациями, не место обитания (ADR-145)
9. **Голый `process_intents()`:** Вызов из `npc_orchestration.py` ❌ → единственный владелец — `TickOrchestrator` (ADR-066)
10. **Двойная обработка интента:** `MovementIntent` с `processed=True` → `RuntimeError` (инвариант одного исполнения)

### 4.2. Запреты на Волю и Давление

11. **Решение без происхождения:** `MovementIntent` без `pressure_sources` ❌
12. **Давление без видимости:** Получение давления через мембрану с `attenuation=0.0` ❌
13. **Double Invocation:** WillpowerGate вызывается ОДИН раз за цикл ❌ → Фаза 1 только переводит семантику
14. **Domain Leakage:** `CombatSubscriber` пишет в Emotion ❌ → только `PhysiologyPayload`
15. **Голый вызов Директивы:** `DirectiveInterpretationSubscriber().handle()` без инъекции `all_npcs_raw` ❌ → `ObediencePressure=0.00` = мёртвая Каузальная Труба
16. **Somatic Gate после парсинга:** Проверка `shock > 0.7` ПОСЛЕ семантического парсинга ❌ → каузальный порядок: Body → Somatic Gate → Semantic (ADR-O-139)
17. **Мёртвый Вектор Эмоций:** Возврат дефолтного `EmotionalVector()` для `ActionType.ATTACK` ❌ (ADR-088)

### 4.3. Запреты на Восприятие и UI

18. **Телепатия в UI:** Передача Игроку информации о внутренних состояниях NPC ❌ → только внешние наблюдения ("замер", "дрожит")
19. **Повторное вычисление в восприятии:** `PerceptualAttentionService` читает `StateDeltas.fear_delta` ❌ → только `PerceptionEvent.salience`
20. **Лаг в ввод:** `perceptual_latency` для задержки ввода ❌ → только визуальный `desync` (шлейфы, инерция камеры)
21. **Слепота Fuzzy Matching:** Удаление поля `name` из `npc_positions` ❌ → `name` обязателен для резолва цели (INV-NPC-NAME)
22. **Краш сериализации:** Использование `asdict()` на границе API без проверки типа ❌ → только `Pydantic`/`Dataclass`
23. **Показ эмоций:** Показ fearful, anxious ❌ → только наблюдаемые проявления (tense, rigid). `ManifestationDTO.tags` — НЕ эмоции
24. **DM читает ментальные объекты:** DM-агент читает `stress_delta`, `trust_delta`, `real_state`, `recalled_facts` ❌ → только `observed_state` + `embodied_traces` (ADR-TZ08-4/6)

### 4.4. Запреты на Ретро-симуляцию и Кэширование

25. **Ретро-симуляция:** `TICK_CATCHUP` с циклом `LifeEngine.tick()` ❌ → только `reconcile_state(elapsed_seconds)` (ADR-047)
26. **Кэш-фантомы:** Не очищен `__pycache__` после рефакторинга DTO ❌ → обязательная очистка перед запуском
27. **Кэширование EffectiveDrives (L3):** Эфемерная проекция, пересчитывается каждый тик. Кэш = рассинхрон идентичности (L3-P1)
28. **Удаление из L1Chronicle:** Append-only хранилище. Удаление = переписывание истории
29. **Phantom Identity Drift:** Запуск `check_identity_promotion` (L2.5) в idle без `phase_2_events` ❌ → память не генерирует идентичность без каузального входа (ADR-S86.7)

### 4.5. Запреты на Время и Пространство

30. **Зависимость времени от игрока:**
    ❌ `tick += 1` внутри `player.action()`
    ✅ `game_time_seconds += GAME_TICK_INTERVAL_SECONDS` в Фазе 0.5 (всегда)
31. **Wall-clock в симуляции:** `time.time()` / `datetime.now()` в `TickOrchestrator`, `LifeEngine`, `DecisionHub`, `TemporalEngine` ❌ → только `game_time_seconds` (ADR-O-302)
32. **Магические числа dt:** `0.1` или `5.0` для `dt`/`delta_time` ❌ → `ETKE_IK_SUBSTEP_DT` / `GAME_TICK_INTERVAL_SECONDS` в константах
33. **Подмена Campaign ID:** Использование `location_id` как `campaign_id` в `_TickContext` ❌ (ADR-089)
34. **Ретросимуляция дальних регионов:** `for i in range(missed_ticks): npc.tick()` ❌ → `reconcile_state()`
35. **Прямое редактирование сжатого состояния:** `lod_state.compressed["mood"] = 0.5` ❌ → только через `StateApplicator`
36. **Время как свойство сущности:** `npc.birth_time = world_clock.tick` (семантический разрыв) ❌ → `birth_tick` (int, chronicle index) для L1Chronicle lookups; `birth_time` (float, game_time_seconds) для age-вычислений
37. **Глобальный random:** `random.*` в kernel layer ❌ → `KernelRNG(tick, npc_id, salt)` (ADR-O-301)
38. **Голый DecisionHub():** `DecisionHub()` без `rng` ❌ (ADR-O-301)

### 4.6. Запреты на Физиологию и Бой

39. **HP Death:** `hp <= 0` как источник смерти ❌ → единственный владелец — `evaluate_vital_state()` (ADR-123)
40. **Death Lock:** `if state.body_state:` (falsy dict) ❌ → `is not None`. Decay для мёртвых запрещён. Переход `DEAD → ALIVE` через физиологию запрещён (ADR-127)
41. **Shock Immortality:** `shock_impulse` без decay ❌ → перманентный шок (ADR-109)
42. **MSOC Normalization:** Чтение `pain`/`fatigue` без `/100.0` в потребителях с порогами 0-1 ❌ (ADR-094)
43. **HP Double Truth:** Прямая запись в `state.hp` в обход `body_state["current_hp"]` ❌ (ADR-HP-UNIFICATION)
44. **Player Action Without Life Status Check:** Мёртвый игрок не может действовать ❌ (ADR-131)
45. **Мёртвый NPC в pipeline:** Генерация интентов/дельт для NPC с `life_status="DEAD"` ❌ → исключение до Фазы 1 (ADR-S93.1)

### 4.7. Запреты на LLM и Материализацию

46. **LLM в ядре:** Вызов LLM или блокирующего I/O внутри `TickOrchestrator` / `DecisionHub` ❌ → только через `TaskScheduler` + `TaskExecutor` (ADR-O-313)
47. **Фейковый нарратив:** Фейковый нарратив при краше LLM ("Твоё сознание мутнеет...") ❌ → честная ошибка + retry (ADR-113)
48. **MockProvider в production:** `settings.environment == "production"` + `MockProvider` ❌
49. **Парсинг JSON в DM-агенте:** `dm_agent.py` парсит JSON-схемы ❌ → `DMResponseNormalizer` (ADR-TZ05-2)

---

## 5. ПРИНЦИП НАБЛЮДАЕМОСТИ (CDS Non-Invasiveness)

**Наблюдение не создает причинность.** CDS и `reports/LAST_SESSION.md` — это проекция свершившегося.

1. **Запрет обратной связи:** Данные из отчётов CDS запрещено парсить и использовать в runtime симуляции.
2. **Чистота наблюдателя:** Падение CDS не должно прерывать каузальный поток. CDS работает в `try/except` и отдельном потоке.
3. **Каузальные разрывы:** Если CDS обнаруживает разрыв (Intent создан, Traversal нет), он фиксирует для LLM-архитектора, но не инжектит фиксы.
4. **Invariant Defense:** `SimulationIntegrityError` (runtime) и `InvariantHealthChecker` (post-mortem) — два слоя защиты. Перехват `SimulationIntegrityError` через `try/except` в пайплайне запрещён — игра должна упасть громко (ADR-INV-DEF).

---

## 6. АРХИТЕКТУРНАЯ ЦЕЛОСТНОСТЬ: ПРИНЦИПЫ

### 6.1. Инерция личности (от L1)
Личность **сопротивляется** изменениям. Запрещена моментальная мутация статов.

```python
new_value = (old_value * core.rigidity) + (delta * (1 - core.rigidity))
```

### 6.2. Симметрия восприятия (от L0)
Игрок и NPC получают одинаковую информацию через разные `ProjectionPolicy`. Нет привилегий.

### 6.3. Единственность решений (от L2)
`DecisionHub` — единственное место, где NPC принимает решение. Все давление аккумулируется и влияет на utility, но не на сам процесс выбора.

### 6.4. Каузальная труба диалогов (ADR-O-313)
Тяжёлые процессы (разговор, торговля) отделены от симуляции:
```
Need → Decision (Intent) → Task (Queue) → Materialization (Worker) → Event (Projection)
```
`TickOrchestrator` создаёт `Task`, кладёт в `scene_state["pending_tasks"]`. `TaskScheduler` (в `game_loop`) исполняет через `TaskExecutor`, возвращает `Artifact`. `Materializer` публикует `WorldEvent` в `EventBus`.

### 6.5. Dual Rail Execution (ADR-O-201)
Legacy + Shadow parallel execution. Drift statistics A/B/C/D/E (cosmetic / projection / topological / causal / ontological). `EventCompiler` (shadow) и `SceneStateManager` (legacy) работают параллельно; `EquivalenceValidator` сравнивает.

### 6.6. Эпистемическая гетерогенность (ADR-O-306)
L1Chronicle каждого NPC — персонализированная запись, не объективная хроника. Фильтруется через Тройную Мембрану: Физическую, Личностную, Социальную (Norm-модулированные пороги).

---

## 7. МИГРАЦИЯ ЗНАНИЙ: Из чего взяли этот контракт

- **ADR-031** (WillpowerGate & Hybrid Consciousness)
- **ADR-035** (Semantic Compression)
- **ADR-037** (Affective Distortion)
- **ADR-042** (Target Resolution & Fuzzy Matching)
- **ADR-047** (No Retro-simulation)
- **ADR-048** (Single Spatial Authority)
- **ADR-049** (Affective Accumulation over Time)
- **ADR-058/059** (Dual-Time Ontology)
- **ADR-060** (Movement Ontology Split: LOD0/LOD1)
- **ADR-O-139** (NPIC & Somatic Gating)
- **ADR-O-142** (Consciousness FSM)
- **ADR-O-143** (Somatic Axis in PerceptualKernel)
- **ADR-O-201** (Causal Kernel Architecture, Dual Rail)
- **ADR-O-207** (Post-Commit Validation Gate)
- **ADR-O-208** (Identity Chronicle & Drives, L3 эфемерность)
- **ADR-O-211** (Calibration Engine, запрет мутации L0)
- **ADR-O-301** (KernelRNG Isolation)
- **ADR-O-302** (Physics Overlay, Time Semantics Isolation)
- **ADR-O-305** (Belief Crystallization Engine, L2.5)
- **ADR-O-306** (Epistemic Heterogeneity, Triple Membrane)
- **ADR-O-307** (Asymmetric Trauma, x6)
- **ADR-O-313** (Universal Task Layer)
- **ADR-O-314** (Actor-Agnostic Spatial Contract)
- **ADR-TZ08-1** (Strict Event-Driven Kernel, InterventionEvent)
- **ADR-TZ08-2** (Immutable Core Pipeline)
- **ADR-TZ08-4/6** (Epistemic Boundary, observed_state)
- **ADR-TZ09-1** (Execution Pipeline Collapse, TickState/TickMutation)
- **ADR-TZ10-1** (Pure Reducer Completion, Svc Strangulation)
- **ADR-TRAV-FSM** (Traversal Lifecycle FSM)
- **ADR-HP-UNIFICATION** (HP Double Truth Elimination)
- **ADR-INV-DEF** (Invariant Defense System)

---

## 8. СПИСОК ПЕСОЧНИЦ (Fail Conditions)

Каждый запрет имеет тест. Полный список — в `docs/DTO Registry (Реестр контрактов).md` → Section 9 "Список Песочниц". Ключевые:

- `test_no_direct_mutation_of_position`
- `test_no_direct_scene_change_in_resolver`
- `test_pressure_modifies_utility_not_commands`
- `test_membrane_visibility_enforced`
- `test_decision_requires_pressure_provenance`
- `test_target_resolution_requires_name_in_npc_positions`
- `test_directive_subscriber_requires_npc_state`
- `test_no_telepathy_in_ui_observation`
- `test_willpower_gate_single_invocation_per_tick`
- `test_affective_load_accumulation_over_time`
- `test_hp_double_truth_invariant`
- `test_l3_ephemeral_invariant`
- `test_kernel_rng_determinism`
- `test_apply_changes_does_not_overwrite_active_traversal`
- `test_apply_changes_snaps_position_on_traversal_complete`
- `test_asymmetric_trauma_x6`

Invariant Probe Tests (IPT) запускаются до коммита: `python backend/tests/IPT.py`.

---

**КЛЮЧЕВАЯ ИДЕЯ:** Это не просто правила. Это **описание одной честной симуляции**, где игрок — не король, а персонаж, подчиняющийся тем же законам, что и NPC.
