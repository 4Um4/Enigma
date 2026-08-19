# CAUSAL CONTRACT v3.0: Архитектурные Законы ENIGMA

> **Статус:** Исполняемый закон | **Версия:** 3.0 | **Сессия:** S201
> **Область применения:** Все компоненты бэкенда и фронтенда.
> **Нарушение = архитектурный баг.**

---

## 1. ФИЛОСОФИЯ

ENIGMA — это **единая каузальная система**, где игрок и NPC подчиняются одной онтологии. Нет читов, телепатии или нарушений причинно-следственной цепи. Симуляция честна.

### 1.1. Пятиуровневая архитектура восприятия

```text
L0 (PERCEPTION) — Мир → Восприятие → NPC/Игрок (PerceptualKernel)
L1 (CHRONICLE) — Append-only SQLite факты (TraitDriftEvent)
L2 (IDENTITY) — Кристаллизованные убеждения (CrystallizedBelief, EpistemicRecord)
L3 (DRIVES) — Эфемерные драйвы (EffectiveDrives, 1 тик)
L4 (BEHAVIOR) — Решения (DecisionHub)
```

**Закон:** Нельзя передать Игроку информацию, которую NPC не мог бы получить через `PerceptualKernel`. Симметрия абсолютна.

### 1.2. ФУНДАМЕНТАЛЬНЫЕ ИНВАРИАНТЫ СИМУЛЯЦИИ

**Invariant I — Causal Provenance (Причинное Происхождение)**
> Любое изменение наблюдаемого состояния должно быть объяснимо конечной причинной цепью внутри модели.

**Invariant II — Historical Constraint (Историческое Ограничение)**
> Будущее состояние не должно вычисляться независимо от релевантной истории.

**Invariant III — Temporal Isolation (Временная Изоляция)**
> Каждый шаг симуляции вычисляется относительно неизменяемого прошлого. Результат вычисления шага не может изменить входные данные этого же шага.

**Invariant IV — Semantic Validity**
> Любое состояние, принимаемое симуляцией, должно быть валидно не только по типу и структуре, но и относительно законов домена, в котором оно существует.

```text
Schema validity ≠ Domain validity.
Domain validity ≠ Causal validity.
```

**Invariant V — Epistemic Isolation (Эпистемическая Изоляция)** ⭐ НОВОЕ
> Убеждения субъективны. `EpistemicRecord` хранит субъективное состояние, не факт. `confidence ≠ truth probability`. Убеждения не мутируют World State напрямую.

---

## 2. ОНТОЛОГИЧЕСКИЕ ПОСТУЛАТЫ

### 2.1. Единые источники истины (SSOT)

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
| **Пространственная согласованность** | `SpatialCoherenceValidator` над `location_id + local_position + current_node + SpatialService` | `SpatialCoherenceValidator.validate()` | Запуск движения при рассогласовании координат, узла и графа |
| **Эпистемические убеждения** ⭐ | `EpistemicStore` (per-agent, SQLite) | `EpistemicContextResolver` → `epistemic_modifiers` → `DecisionHub` | Глобальный store; DELETE операции; `DecisionHub` читает `EpistemicStore` напрямую |
| **Социальное давление** ⭐ | `CausalFieldLayer` (Spatial Hash Grid) | `CFL.sample(pos)` → `S_env` | Прямая интерференция метрик агентов; CFL как персистентное состояние |
| **Режим сна** ⭐ | `CouplingProfile` (вычисляется каждый тик) | `CouplingResolver` → множители восприятия/моторики | Скриптовые флаги `is_sleeping`; Игнорирование стимулов во сне |
| **Судьба NPC** ⭐ | `FateTracker` (stability, threat, _critical_ticks) | `FateOutcome` (ALIVE, DEATH, ESCAPE, BROKEN) | Ручные инъекции отношений в End-Screen |

### 2.1.1. Spatial Coherence Contract

Для каждого живого пространственно присутствующего агента:

```text
scene_state.npc_positions[npc_id]
    ↓
local_position
    ↓
SpatialService.resolve_node(local_position)
    ↓
current_node
    ↓
SpatialService.graph
    ↓
TraversalEngine
```

должны представлять одну и ту же физическую реальность.

**Обязательные инварианты:**
- **SC-1.** `local_position` не может быть `(0.0, 0.0)`, если `(0.0, 0.0)` не является явно валидной координатой данной локации.
- **SC-2.** `local_position` должен принадлежать текущей `location_id`.
- **SC-3.** `current_node` должен существовать в текущем `SpatialService`.
- **SC-4.** `current_node` должен быть разрешим из `local_position` с использованием единого алгоритма node resolution.
- **SC-5.** `SpatialService` должен быть собран из авторитетной topology source.
- **SC-6.** Активное движение запрещено до прохождения Spatial Coherence Validation.
- **SC-7.** Persistence не может считаться авторитетной, если сохранённое пространственное состояние нарушает SC-1...SC-5.
- **SC-8.** Recovery из старого или повреждённого состояния должен быть детерминированным и наблюдаемым.

### 2.2. Движение = Результат, не Команда

**SceneChange — это projection свершившегося, а не триггер.**

Истинная физика:
```text
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

**Формула DRP (Drive Resolution Pipeline, ADR-O-208):**
```text
EffectiveDrives = Projection(L0_Archetype, L1_Scars, Context)
```

**Жизненный цикл L3:**
- Рождается в начале тика (`DriveResolver.resolve_drives(L0, beliefs)`)
- Эфемерен (не переживает сериализацию)
- Умирает в конце тика
- Кэширование = ЗАПРЕЩЕНО (L3-P1)

**Запреты:**
- Кэширование `EffectiveDrives`.
- Мутация `drives_runtime` (L0) минуя Belief Layer (L2.5) через `CalibrationEngine`.
- Фоллбэк на L0 (`drives_base`) в `InterpretationEngine` / `VerbalizationContext`.
- `npc_raw["drives"]` как источник правды (уничтожен).

### 2.6. Temporal Identity Formation (TIFL, ADR-TIFL-001) ⭐ НОВОЕ

Непрерывный дрейф `drives_base` на основе `prediction_error`. Если мир постоянно неожидан на оси X, драйв, отвечающий за ось X, растёт. Успех (отсутствие ошибки) слегка снижает драйв (привыкание).

**Формула:**
```python
drifts[drive] = prediction_error * LEARNING_RATE * plasticity
```

где `plasticity = max(0.1, 1.0 - rigidity)` (травмированные личности адаптируются медленнее).

**Запреты:**
- Скалярная мутация личности.
- Игнорирование `prediction_error` в `TickOrchestrator`.

### 2.7. Identity Stability Kernel (ISK, ADR-O-211) ⭐ НОВОЕ

Фазовая устойчивость личности измеряется через `run_perturbation_test` (микро-шум → `delta_g_norm`).

**Режимы:**
- **CRYSTAL:** `mu < 0.01` и `sigma < 0.01` (устойчив)
- **PLASTIC:** `mu > 0.01` и `sigma < mu * 0.5` (адаптивен)
- **BRITTLE:** `sigma > mu * 1.5` (хрупок)
- **CHAOTIC:** иначе

**Запреты:**
- Мгновенная смена метрик.
- Игнорирование `identity_rigidity` в `CalibrationEngine`.

---

## 3. ЭПИСТЕМИЧЕСКИЙ СЛОЙ (Epistemic Core) ⭐ НОВАЯ СЕКЦИЯ

### 3.1. Архитектура убеждений (S188-S201)

**Поток:** `NPC_SPOKE` → `ClaimEventSubscriber` → `ClaimEvent` → `EpistemicRecord` → `EpistemicContext` → `epistemic_modifiers` → `DecisionHub`

```text
World Event (NPC_SPOKE)
    ↓
ClaimEventSubscriber (слушает COMMUNICATION_CLAIM)
    ↓
ClaimEvent {speaker_id, listener_id, proposition, target_id, confidence, tick}
    ↓
BeliefRevisionEngine (pure function)
    ↓
EpistemicRecord {proposition, confidence, source_id, last_updated_tick, provenance}
    ↓
EpistemicStore (per-agent, SQLite, round-trip integrity)
    ↓
EpistemicContextResolver → EpistemicContext {perceived_claims, perceived_beliefs, max_confidence}
    ↓
to_modifiers() → Dict[str, float] (max_confidence * 0.992)
    ↓
DecisionHub.compute(epistemic_modifiers=...)
```

### 3.2. Trust-Based Reliability (ADR-O-357, S199)

Надёжность убеждений зависит от `trust` (из `RelationshipStore`):
- `trust > 0` → `confidence` растёт
- `trust < -30` → обратный эффект (confidence падает)
- Слова врага не убеждают

**Формула:**
```python
reliability = TrustBasedReliabilityProvider.compute(trust)
if trust < -30:
    reliability = -0.5  # обратный эффект
```

### 3.3. Player Epistemic Closure (ADR-O-358, S200-S201)

Игрок — полноправный наблюдатель в `EpistemicStore`.

**Детерминированный fallback:**
```text
intent_type (accuse, praise, intimidate, attack)
    ↓
Proposition (STOLE, HELPED, ATTACKED, PRAISED, WARNED)
```

**Защита:**
```python
new_confidence = max(0.0, old_confidence + delta)  # S201 fix
```

### 3.4. Modifier Contract (ADR-O-355)

`apply_modifiers(scores, *modifier_dicts)` — pure function:
- **Аддитивна:** `final = base + sum(modifiers)`
- **Изолирована:** не мутирует вход
- **Коммутативна:** порядок не важен
- **Без побочных эффектов:** никаких `multiplier`, `cap`, `override`

### 3.5. Запреты эпистемического слоя

- ❌ `ClaimEvent` мутирует World State.
- ❌ `EpistemicRecord` хранит факты — только субъективность.
- ❌ Proposition мутирует `RelationshipStore` напрямую.
- ❌ `DecisionHub` читает `EpistemicStore` (только `Dict[str, float]`).
- ❌ L1 Chronicle хранит субъективные убеждения.
- ❌ Модификаторы с побочными эффектами / не коммутативные.
- ❌ Мутация входного `scores` в `apply_modifiers`.
- ❌ SUPERBOX инъецирует Belief/Relationship напрямую.
- ❌ `if _nid == "player": continue` в подписчике (S200 fix).
- ❌ Отрицательный `confidence` (защита `max(0.0)`).

---

## 4. СОЦИАЛЬНАЯ ФИЗИКА: CAUSAL FIELD LAYER ⭐ НОВАЯ СЕКЦИЯ

### 4.1. Архитектура CFL (ADR-O-209/210, S118)

Социальная физика = **поле**, не граф. Агенты излучают давление в среду и считывают давление из среды. Среда (CFL) — единственный посредник.

```text
NPC_i → emit(CausalEmissionPacket) → CFL Spatial Grid (superposition + cap)
    ↓
CFL.sample(pos_j) → S_env
    ↓
S_total = S_internal + S_env
    ↓
DecisionHub (Utility Deformation)
```

### 4.2. CausalEmissionPacket

```python
@dataclass(frozen=True)
class CausalEmissionPacket:
    npc_id: str
    position: Tuple[float, float]
    pressure_vector: CausalPressureVector  # 5D: fear, control, significance, desire, volatility
    decay_radius: float
    signature_hash: int
```

### 4.3. Spatial Hashing & Saturation

CFL — разреженная решётка (Spatial Hash Grid), привязанная к физическому пространству сцены.

**Суперпозиция с ограничением:**
```python
CFL_cell = min(sum(E_i * exp(-d_i / r_i)), Cap_max)
```

**Смысл:** Толпа из 1000 человек создаёт мощное поле давления, но оно не уходит в бесконечность. Существует физический предел "плотности социального стресса" в одной точке.

### 4.4. Emergent Social Phase Topology (ESPT)

Поле CFL не плоское. Из-за суперпозиции излучений и ограничения насыщения, в нём самопроизвольно возникают **топологические структуры** — социальные аттракторы:

- **Fear Basins:** Области с критическим `fear_pressure`. NPC, попавшие в эту зону, получают мощный упругий изгиб метрики в сторону FLEE.
- **Authority Wells:** Области вокруг NPC с высоким `control_pressure`. Это гравитационные колодцы подчинения.
- **Social Fronts:** Границы между зонами с разным доминирующим давлением. Переход через такую границу вызывает резкий скачок `S_env`.

### 4.5. Запреты CFL

- ❌ Прямая интерференция метрик агентов (NPC_i не может искривлять метрику NPC_j напрямую).
- ❌ CFL как персистентное состояние (только tick-local буфер эмиссий).
- ❌ Чтение сырых событий L1 в MSTD/DecisionHub (только через CPC).
- ❌ Суммирование `S_internal + S_env` без весовой нормализации CPN.
- ❌ O(history) вычисления в рантайме (только O(1) для CSV и O(W) для L1 Tail).

---

## 5. СОН КАК ТЕЛЕСНЫЙ РЕЖИМ ⭐ НОВАЯ СЕКЦИЯ

### 5.1. Архитектура (ADR-O-356, S189)

Сон = эмерджентное свойство телесной архитектуры, не скриптовый переключатель.

**Фазы:**
- **Phase B (CouplingResolver):** `CouplingProfile` вычисляется каждый тик из `sleep_pressure` + `arousal`.
- **Phase C (ActiveCommitment):** `has_active_commitment` блокирует проактивные интенты при активном транзите.
- **Phase D (Sleep Onset):** `_accumulate_arousal_from_stimuli` динамически накапливает `arousal` от стимулов.
- **Phase E.0 (Perception Modulation):** Стимулы модулируются множителями (`external_hearing_mult`, `external_vision_mult`).
- **Phase E (DreamSignal):** `DreamGenerationService` конвертирует стимулы в `DreamSignal` (`DREAM` / `NIGHTMARE`).
- **Phase F (DreamResidue):** При пробуждении `DreamSignal` → `affective_load` + `threat_gradient`.

### 5.2. CouplingProfile

```python
@dataclass(frozen=True)
class CouplingProfile:
    external_vision_mult: float  # 0.0-1.0
    external_hearing_mult: float  # 0.0-1.0
    motor_output_mult: float  # 0.0-1.0
    memory_activation_mult: float  # 0.0-1.0
    imagination_mult: float  # 0.0-1.0
    coupling_mode: CouplingMode  # Enum: AWAKE, DROWSY, SLEEPING, REM
```

### 5.3. Запреты сна

- ❌ Скриптовые флаги `is_sleeping`.
- ❌ Игнорирование стимулов во сне.
- ❌ Логика пробуждения в `LifeEngine` (вынесено в `SleepLifecycleService`).
- ❌ Игнорирование `sleep_end` в `TimeSkipExecutor`.

---

## 6. ФИЗИОЛОГИЯ И БОЙ: VITAL STATE AXES ⭐ ОБНОВЛЕНО

### 6.1. Три независимые оси (ADR-123)

Смешивание осей в один enum — архитектурная ошибка.

| Ось | Функция | Возвращает |
|-----|---------|-----------|
| Жизнь | `evaluate_vital_state(body_state)` | `LifeStatus.ALIVE` / `DEAD` |
| Сознание | `is_conscious(body_state)` | `bool` |
| Дееспособность | `is_capable(body_state)` | `bool` |

**Пример:** NPC может быть `ALIVE + UNCONSCIOUS + INCAPACITATED`.

### 6.2. InjuryProcessor (ADR-123)

Мост Injury → Physiology. Свойства ран вместо строковых флагов:

```python
# Старый путь (запрещён):
if "bleeding" in critical_effects:
    blood_loss_delta = severity * RATE

# Новый путь:
bleeding_rate = structural_damage * zone_rate * damage_type_modifier
```

### 6.3. Запреты физиологии

- ❌ `hp <= 0` как источник смерти.
- ❌ `shock_impulse >= 0.95` как источник смерти (шок — сигнал, не процесс).
- ❌ `brain_integrity`, `heart_function`, `respiration` без причинного источника.
- ❌ `"dead"` в `body_state["statuses"]` (DOUBLE TRUTH с `life_status`).
- ❌ `InjuryProcessor` читает строковые флаги из `critical_effects`.

---

## 7. ЭМОЦИОНАЛЬНАЯ ИЗОЛЯЦИЯ (ADR-O-206) ⭐ НОВАЯ СЕКЦИЯ

### 7.1. Убийство EmotionTag как причины

`EmotionTag` убит как универсальное состояние. Заменён на 3 несовместимые проекции (ADR-O-205):

1.  **Motor Projection:** `rigidity` от `threat_gradient` (тело не знает о разуме).
2.  **Narrative Projection:** текст от `redirect` (разум рационализирует победу драйва).
3.  **Memory Projection:** важность от `error_vector` (Surprise).

### 7.2. Память — Вес (Истина Опыта)

Важность памяти определяется структурным разрывом (`Surprise`), а не оракулом `EmotionTag`.

```python
# ADR-O-206: Emotional Residue Isolation
surprise_delta = abs(affective_load - prev_affective_load)
if npc_stress > 70 and surprise_delta > 0.2:
    stress_mod = 1.25  # Резкий скачок стресса при высокой нагрузке = травма
elif npc_stress > 50 or surprise_delta > 0.1:
    stress_mod = 1.10
```

### 7.3. Память — Время (Скорость Забывания)

Скорость распада памяти зависит от каузальной глубины (surprise), а не тега.

```python
# ADR-O-206
surprise = abs(load - prev_affective_load)
if surprise > 0.3:
    decay_rate = 0.01  # Шок / Травма: забывается очень медленно
elif load > 0.5:
    decay_rate = 0.03  # Высокая вовлечённость: забывается медленно
else:
    decay_rate = 0.05  # Базовая скорость
```

### 7.4. Запреты эмоциональной изоляции

- ❌ `EmotionTag` в `ImportanceEngine` или `MemoryManager`.
- ❌ Влияние тега на `decay_rate`.
- ❌ Свитчи `if emotion == "fearful"` в `BehaviorManifestationService`.
- ❌ Cross-projection leakage (Motor читает `redirect`).

---

## 8. ДОПУСТИМЫЙ ПОТОК РЕАЛЬНОСТИ (Per-Tick Cascade)

TickOrchestrator `_run_core_phases()` — единая точка входа. Нет ветвления player/idle (ADR-TZ08-2).

### Фаза 0: Simulation (LifeEngine)
```text
LifeEngine.tick() → SceneChange (cognitive) + MovementIntent (schedule/need/random)
  → apply_with_shadow_observation() (Dual Rail, ADR-O-201)
  → _process_traversals() (STL Phase 1, boundary resolution)
  → _process_continuous_motion() (ETKE-IK, DriveVector → velocity)
```

### Фаза 0.5: Time-Driven Decay
```text
idle_handlers → DynamicAffordanceField (purge + decay)
  → PE Decay (ExpectationStore)
  → Affective Decay, Perceptual Decay
  → TraversalExecutionSystem.advance() (projection TraversalState → local_position)
  → _advance_idle_time() (game_time_seconds += GAME_TICK_INTERVAL_SECONDS)
```
**Выполняется ВСЕГДА.** Время не останавливается (ADR-002). `game_time_seconds` — единственный источник времени (ADR-O-302).

### Фаза 0.6: Sleep Lifecycle (ADR-O-353) ⭐ НОВОЕ
```text
SleepLifecycleService.tick() → arousal accumulation → CouplingProfile update
  → DreamSignal generation (if SLEEPING/REM)
  → SceneChange (sleep_end, dream_residue)
```

### Фаза 1: Input Merge (NPIC Normalize → Intervention Routing → WillpowerGate)
```text
InterventionEvent → _process_player_dm_action() / _process_player_action()
  → DirectiveInterpretationSubscriber (с инъекцией all_npcs_raw)
  → WillpowerGate (ОДИН раз за цикл, ADR-036)
  → delta_buffer (IdentityPayload, EmotionPayload)
```
**Ядро не знает 'player' или 'dm_ctx'.** Только `InterventionEvent` (ADR-TZ08-1).

### Фаза 2: EventBus (Spatial Events)
```text
SpatialEventDetector (old vs new positions) → NPC_MOVED, NPC_PROXIMITY_CLOSE/LEAVE
  → EventBus (первичная волна)
```
Early exit, если нет изменений позиций.

### Фаза 3: Memory Phase
```text
MemoryManager.apply() для затронутых NPC
```
Early exit, если нет phase_2_events.

### Фаза 4: Pre-Decision (TopicExtractor)
```text
phase_2_events + STM buffer → topic для каждого NPC
  → fallback "наблюдение" (никогда не пустой)
```

### Фаза 5: Decision (Unified Execution Kernel, ADR-TZ09-1)
```text
TickState (immutable snapshot, preloaded data) → NpcTickPipeline.run() (pure reducer)
  → TickMutation (npc_deltas, communication_intents, movement_intents, l1_drift_events, memory_events)
  → apply (orchestrator): build_npc_contexts, process_movement_intents
```
**Pure function:** `svc` параметр убит (ADR-TZ10-1). I/O мутации отложены.

### Фаза 6: Post-Decision (IntentEventAdapter + Windup Write Gate)
```text
CommunicationIntent → IntentEventAdapter → EventDTO → EventBus
  ATTACK → ActionWindup (held_intent_id, 2 тика подготовки, ADR-O-310)
  DIALOGUE → QueuedTask → scene_state["pending_tasks"] (ADR-O-313)
```

### Фаза 7: Windup Resolution (Execution Gate)
```text
windup_registry → completed windups → release held intent
  → Stale Intent Validation (actor alive? target alive? in scene?)
  → EventDTO publish или INTERRUPTED
```

### Фаза 8: Layered Reduction (drain + handle)
```text
drain_events → handle (детерминированный порядок):
  perception → reaction → social → combat → homeostasis
  → Phase8Result → delta_buffer
  → StateApplicator.apply_batch() (единый мутатор)
  → L5 Post-Commit Validation (sum(drives)==1.0, bounds, NaN, ADR-O-207)
```

### Фаза 9: Integration (CFRM + WorldSnapshot + Epistemic)
```text
LocalCausalSolver → FieldDisturbance → EventBuffer
  → BeliefCrystallizationEngine (L2.5, только при phase_2_events)
  → ClaimEventSubscriber (слушает COMMUNICATION_CLAIM, обновляет EpistemicStore) ⭐
  → WorldSnapshotBuilder → WorldSnapshotDTO
```

### Фаза 9.1: Affective Pipeline
```text
integrate_affective_pressure() (единый владелец Active Inference + Hysteresis)
  → Tuple[new_load, new_memory]
  → EmotionTransition (if load > threshold)
```

### Фаза 10: Persistence (Atomic Commit)
```text
SceneStateManager.commit_tick_result() → SQLitePersistenceAdapter.atomic_commit()
  → INSERT OR REPLACE (State перезаписан)
L1Chronicle → SQLite (append-only)
EpistemicStore → SQLite (per-agent, round-trip) ⭐
DRFBus → drain()
```

### Фаза 10+: Player Perception (Explicit Snapshot Step, ADR-TZ08-8)
```text
GameLoop (не ядро): PerceptionProjector
  → PhenomenologyProjectionService (PerceptionEvent)
  → PerceptualAttentionService (фильтр по бюджету)
  → PlayerPerceptionDTO (peripheral_cues, manifestations, active_perceptions)
  → WorldSnapshotDTO.player_perception
```

---

## 9. CAUSAL CARDINALITY LAWS ⭐ НОВАЯ СЕКЦИЯ (S176-S186)

### 9.1. Tick Cardinality (ADR-O-344)

`TickOrchestrator` — единственный владелец `game_time_seconds` и `tick`.

**Запреты:**
- ❌ `GameLoop` меняет время.
- ❌ `TickOrchestrator` продвигает время в цикле по сценам.
- ❌ Множественные коммиты в `execute()`.

### 9.2. Entity Cardinality (ADR-O-347)

`all_npcs_raw` фильтруется по `location_id` ДО сборки `TickState`. NPC из других локаций исключаются.

**Запреты:**
- ❌ Передача полного `all_npcs_raw` без фильтрации.
- ❌ Обработка NPC с чужим `location_id`.

### 9.3. Event Cardinality (ADR-O-348)

`INV-EVENT-CARDINALITY` (нет дублирования `NPC_MOVED`). `NpcTickPipeline` = Pure Reducer (структурная независимость от порядка NPC).

**Запреты:**
- ❌ Мутация общего состояния в цикле NPC.
- ❌ Зависимость Фазы 8 от порядка `npc_deltas`.

### 9.4. Commit Cardinality (S186)

`atomic_commit_all` вызывается ровно 1 раз в `unlock_tick()`. `SceneStateManager.commit()` обновляет только RAM-кэш.

### 9.5. Intent-Event Completeness (ADR-O-349)

`IntentEventAdapter._INTENT_EVENT_MAP` = детерминированный мост.

**Запреты:**
- ❌ Сырые строки для `event_type`.
- ❌ Новые `CommunicationIntent` без маппинга.
- ❌ `unknown` / `npc_spoke` fallback.

### 9.6. Dialogue & Travel Terminality (ADR-O-350)

- `INV-TRAV-TERMINALITY`: транзиты не виснут > `duration_ticks + 2`.
- `INV-DIALOGUE-LIVENESS`: `pending_tasks` ≤ 20.

### 9.7. Replay Determinism (ADR-O-351)

`INV-REPLAY-DETERMINISM` (WARNING). `ReplayRecorder` подключён. Полный A/B тест через `DriftLaboratory`.

### 9.8. Save/Load Integrity (ADR-O-352)

`INV-SAVE-LOAD-INTEGRITY`. `SqlitePersistenceAdapter.load_scene_at` (не legacy `load_scene()`).

---

## 10. ЗАПРЕТЫ (HARD CONSTRAINTS)

### 10.1. Запреты на Движение
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

### 10.2. Запреты на Волю и Давление
11. **Решение без происхождения:** `MovementIntent` без `pressure_sources` ❌
12. **Давление без видимости:** Получение давления через мембрану с `attenuation=0.0` ❌
13. **Double Invocation:** WillpowerGate вызывается ОДИН раз за цикл ❌ → Фаза 1 только переводит семантику
14. **Domain Leakage:** `CombatSubscriber` пишет в Emotion ❌ → только `PhysiologyPayload`
15. **Голый вызов Директивы:** `DirectiveInterpretationSubscriber().handle()` без инъекции `all_npcs_raw` ❌ → `ObediencePressure=0.00` = мёртвая Каузальная Труба
16. **Somatic Gate после парсинга:** Проверка `shock > 0.7` ПОСЛЕ семантического парсинга ❌ → каузальный порядок: Body → Somatic Gate → Semantic (ADR-O-139)
17. **Мёртвый Вектор Эмоций:** Возврат дефолтного `EmotionalVector()` для `ActionType.ATTACK` ❌ (ADR-088)

### 10.3. Запреты на Восприятие и UI
18. **Телепатия в UI:** Передача Игроку информации о внутренних состояниях NPC ❌ → только внешние наблюдения ("замер", "дрожит")
19. **Повторное вычисление в восприятии:** `PerceptualAttentionService` читает `StateDeltas.fear_delta` ❌ → только `PerceptionEvent.salience`
20. **Лаг в ввод:** `perceptual_latency` для задержки ввода ❌ → только визуальный `desync` (шлейфы, инерция камеры)
21. **Слепота Fuzzy Matching:** Удаление поля `name` из `npc_positions` ❌ → `name` обязателен для резолва цели (INV-NPC-NAME)
22. **Краш сериализации:** Использование `asdict()` на границе API без проверки типа ❌ → только `Pydantic`/`Dataclass`
23. **Показ эмоций:** Показ fearful, anxious ❌ → только наблюдаемые проявления (tense, rigid). `ManifestationDTO.tags` — НЕ эмоции
24. **DM читает ментальные объекты:** DM-агент читает `stress_delta`, `trust_delta`, `real_state`, `recalled_facts` ❌ → только `observed_state` + `embodied_traces` (ADR-TZ08-4/6)

### 10.4. Запреты на Ретро-симуляцию и Кэширование
25. **Ретро-симуляция:** `TICK_CATCHUP` с циклом `LifeEngine.tick()` ❌ → только `reconcile_state(elapsed_seconds)` (ADR-047)
26. **Кэш-фантомы:** Не очищен `__pycache__` после рефакторинга DTO ❌ → обязательная очистка перед запуском
27. **Кэширование EffectiveDrives (L3):** Эфемерная проекция, пересчитывается каждый тик. Кэш = рассинхрон идентичности (L3-P1)
28. **Удаление из L1Chronicle:** Append-only хранилище. Удаление = переписывание истории
29. **Phantom Identity Drift:** Запуск `check_identity_promotion` (L2.5) в idle без `phase_2_events` ❌ → память не генерирует идентичность без каузального входа (ADR-S86.7)

### 10.5. Запреты на Время и Пространство
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

### 10.6. Запреты на Физиологию и Бой
39. **HP Death:** `hp <= 0` как источник смерти ❌ → единственный владелец — `evaluate_vital_state()` (ADR-123)
40. **Death Lock:** `if state.body_state:` (falsy dict) ❌ → `is not None`. Decay для мёртвых запрещён. Переход `DEAD → ALIVE` через физиологию запрещён (ADR-127)
41. **Shock Immortality:** `shock_impulse` без decay ❌ → перманентный шок (ADR-109)
42. **MSOC Normalization:** Чтение `pain`/`fatigue` без `/100.0` в потребителях с порогами 0-1 ❌ (ADR-094)
43. **HP Double Truth:** Прямая запись в `state.hp` в обход `body_state["current_hp"]` ❌ (ADR-HP-UNIFICATION)
44. **Player Action Without Life Status Check:** Мёртвый игрок не может действовать ❌ (ADR-131)
45. **Мёртвый NPC в pipeline:** Генерация интентов/дельт для NPC с `life_status="DEAD"` ❌ → исключение до Фазы 1 (ADR-S93.1)

### 10.7. Запреты на LLM и Материализацию
46. **LLM в ядре:** Вызов LLM или блокирующего I/O внутри `TickOrchestrator` / `DecisionHub` ❌ → только через `TaskScheduler` + `TaskExecutor` (ADR-O-313)
47. **Фейковый нарратив:** Фейковый нарратив при краше LLM ("Твоё сознание мутнеет...") ❌ → честная ошибка + retry (ADR-113)
48. **MockProvider в production:** `settings.environment == "production"` + `MockProvider` ❌
49. **Парсинг JSON в DM-агенте:** `dm_agent.py` парсит JSON-схемы ❌ → `DMResponseNormalizer` (ADR-TZ05-2)

### 10.8. Запреты на Эпистемический слой ⭐ НОВОЕ
50. **Claim ≠ Truth:** `ClaimEvent` никогда не является World Truth и не мутирует World State.
51. **Belief ≠ Truth:** `EpistemicRecord` хранит субъективное состояние, не факт. `confidence ≠ truth probability`.
52. **Proposition не мутирует RelationshipStore:** Только через `epistemic_modifiers` → `DecisionHub`.
53. **DecisionHub не знает об EpistemicStore:** DecisionHub получает только `Dict[str, float]`.
54. **L1 Chronicle не хранит субъективные убеждения:** Только provenance событий («A сообщил C утверждение P»), не объявляет P фактом.
55. **EpistemicContext не содержит World Truth:** Только `perceived_*` поля.
56. **Модификаторы с побочными эффектами:** Запрещены.
57. **Мутация входного scores в apply_modifiers:** Запрещена. Функция создаёт копию.
58. **Некоммутативные операции:** `multiplier`, `cap`, `override` без нового контракта v2 запрещены.
59. **SUPERBOX инъецирует Belief/Relationship/Decision напрямую:** Инъекция только `ClaimEvent`.
60. **Player Epistemic Bypass:** `if _nid == "player": continue` в подписчике ❌ (S200 fix).
61. **Negative Confidence:** Отрицательный `confidence` ❌ (защита `max(0.0)`, S201 fix).

### 10.9. Запреты на CFL ⭐ НОВОЕ
62. **Прямая интерференция метрик:** NPC_i не может искривлять метрику NPC_j напрямую, только через CFL.
63. **CFL как персистентное состояние:** Только tick-local буфер эмиссий.
64. **Чтение сырых событий L1 в MSTD/DecisionHub:** Только через CPC.
65. **Суммирование без CPN:** `S_internal + S_env` без весовой нормализации CPN.

### 10.10. Запреты на Сон ⭐ НОВОЕ
66. **Скриптовые флаги:** `is_sleeping` ❌ → только `CouplingProfile`.
67. **Игнорирование стимулов во сне:** `_accumulate_arousal_from_stimuli` обязателен.
68. **Пробуждение в LifeEngine:** Вынесено в `SleepLifecycleService`.
69. **Игнорирование sleep_end в TimeSkipExecutor:** Прерывание ускорения обязательно.

### 10.11. Запреты на Эмоциональную изоляцию ⭐ НОВОЕ
70. **EmotionTag в ImportanceEngine/MemoryManager:** ❌ → только `surprise_delta`.
71. **Влияние тега на decay_rate:** ❌ → только каузальная глубина.
72. **Свитчи `if emotion == "fearful"`:** ❌ в `BehaviorManifestationService`.
73. **Cross-projection leakage:** Motor читает `redirect` ❌.

### 10.12. Предусловия исполнения движения
Движение не может быть запущено только на основании наличия `MovementIntent`. Перед созданием `TraversalState` должны быть подтверждены:

1. Actor Spatial State valid.
2. Actor `location_id` совпадает с graph zone.
3. Actor `local_position` не является запрещённым sentinel.
4. Actor position разрешается в topology node.
5. Target node существует.
6. Target node принадлежит допустимой spatial zone.
7. A* graph был скомпилирован из актуальной topology source.
8. Required topology connections существуют.
9. Dynamic obstacles не делают маршрут непроходимым.
10. Если `start_node == target_node`, результатом является `ALREADY_AT_TARGET`, а не `A_STAR_FAILED`.
11. Если `find_path()` возвращает `[start_node]`, это успешное состояние с нулевым traversal distance.
12. `A_STAR_FAILED` должен означать именно отсутствие маршрута, а не:
    - actor position corruption;
    - missing target node;
    - disconnected graph;
    - invalid topology;
    - start already at target;
    - stale persistence;
    - obstacle compilation error.

---

## 11. ПРИНЦИП НАБЛЮДАЕМОСТИ (CDS Non-Invasiveness)

**Наблюдение не создает причинность.** CDS и `reports/LAST_SESSION.md` — это проекция свершившегося.

1. **Запрет обратной связи:** Данные из отчётов CDS запрещено парсить и использовать в runtime симуляции.
2. **Чистота наблюдателя:** Падение CDS не должно прерывать каузальный поток. CDS работает в `try/except` и отдельном потоке.
3. **Каузальные разрывы:** Если CDS обнаруживает разрыв (Intent создан, Traversal нет), он фиксирует для LLM-архитектора, но не инжектит фиксы.
4. **Invariant Defense:** `SimulationIntegrityError` (runtime) и `InvariantHealthChecker` (post-mortem) — два слоя защиты. Перехват `SimulationIntegrityError` через `try/except` в пайплайне запрещён — игра должна упасть громко (ADR-INV-DEF).

---

## 12. АРХИТЕКТУРНАЯ ЦЕЛОСТНОСТЬ: ПРИНЦИПЫ

### 12.1. Инерция личности (от L1)
Личность **сопротивляется** изменениям. Запрещена моментальная мутация статов.
```python
new_value = (old_value * core.rigidity) + (delta * (1 - core.rigidity))
```

### 12.2. Симметрия восприятия (от L0)
Игрок и NPC получают одинаковую информацию через разные `ProjectionPolicy`. Нет привилегий.

### 12.3. Единственность решений (от L2)
`DecisionHub` — единственное место, где NPC принимает решение. Все давление аккумулируется и влияет на utility, но не на сам процесс выбора.

### 12.4. Каузальная труба диалогов (ADR-O-313)
Тяжёлые процессы (разговор, торговля) отделены от симуляции:
```text
Need → Decision (Intent) → Task (Queue) → Materialization (Worker) → Event (Projection)
```
`TickOrchestrator` создаёт `Task`, кладёт в `scene_state["pending_tasks"]`. `TaskScheduler` (в `game_loop`) исполняет через `TaskExecutor`, возвращает `Artifact`. `Materializer` публикует `WorldEvent` в `EventBus`.

### 12.5. Dual Rail Execution (ADR-O-201)
Legacy + Shadow parallel execution. Drift statistics A/B/C/D/E (cosmetic / projection / topological / causal / ontological). `EventCompiler` (shadow) и `SceneStateManager` (legacy) работают параллельно; `EquivalenceValidator` сравнивает.

### 12.6. Эпистемическая гетерогенность (ADR-O-306)
L1Chronicle каждого NPC — персонализированная запись, не объективная хроника. Фильтруется через Тройную Мембрану: Физическую, Личностную, Социальную (Norm-модулированные пороги).

### 12.7. Epistemic Isolation (ADR-O-354/355) ⭐ НОВОЕ
Убеждения субъективны и изолированы от World State. `DecisionHub` получает только числовые модификаторы, не `EpistemicStore`. Modifier Contract гарантирует аддитивность, изоляцию, коммутативность.

### 12.8. Social Field Physics (ADR-O-209/210) ⭐ НОВОЕ
Социальное давление распространяется через поле (CFL), не через прямые связи. Superposition + Saturation Cap предотвращают мгновенные массовые коммиты. Emergent Social Phase Topology создаёт Fear Basins, Authority Wells, Social Fronts.

---

## 13. МИГРАЦИЯ ЗНАНИЙ: Из чего взяли этот контракт

### Foundation & Runtime
- **ADR-031** (WillpowerGate & Hybrid Consciousness)
- **ADR-035** (Semantic Compression)
- **ADR-037** (Affective Distortion)
- **ADR-042** (Target Resolution & Fuzzy Matching)
- **ADR-047** (No Retro-simulation)
- **ADR-048** (Single Spatial Authority)
- **ADR-049** (Affective Accumulation over Time)
- **ADR-058/059** (Dual-Time Ontology)
- **ADR-060** (Movement Ontology Split: LOD0/LOD1)
- **ADR-O-201** (Causal Kernel Architecture, Dual Rail)
- **ADR-O-207** (Post-Commit Validation Gate)
- **ADR-O-301** (KernelRNG Isolation)
- **ADR-O-302** (Physics Overlay, Time Semantics Isolation)
- **ADR-O-313** (Universal Task Layer)
- **ADR-O-314** (Actor-Agnostic Spatial Contract)
- **ADR-TZ08-1** (Strict Event-Driven Kernel, InterventionEvent)
- **ADR-TZ08-2** (Immutable Core Pipeline)
- **ADR-TZ08-4/6** (Epistemic Boundary, observed_state)
- **ADR-TZ09-1** (Execution Pipeline Collapse, TickState/TickMutation)
- **ADR-TZ10-1** (Pure Reducer Completion, Svc Strangulation)
- **ADR-TRAV-FSM** (Traversal Lifecycle FSM)
- **