# ТЗ · Stage 2.5 — Temporal Causality + Predictive Runtime + World/Embodiment Foundation

| Поле | Значение |
|---|---|
| **Документ** | Техническое задание для архитектора (расширенное) |
| **Проект** | ENIGMA (commit `6ed3310`, release `V.0.5.3.8.7`) |
| **Стадия** | Stage 2.5 — вставляется между Stage 2 (Living NPC Kernel) и Stage 3 (Tavern Life) |
| **Тип требования** | Архитектурное + интеграционное (Non-Breaking Migration) |
| **Адресат** | Архитектор runtime-слоя и world/embodiment-слоя ENIGMA |
| **Версия ТЗ** | 2.0 (2026-08-25) — добавлена Часть II: W-track (World/Embodiment Foundation) |
| **Стиль** | Engineering RFC (MUST / SHOULD / MAY в смысле RFC 2119) |
| **Структура** | **Часть I** — Temporal/Predictive Runtime (разделы 1–16). **Часть II** — World/Embodiment Foundation / W0–W9 (разделы 17–46). |
| **Базовый код** | `backend/app/domain/action_commitment.py`, `backend/app/services/action/commitment_arbiter.py`, `backend/app/services/action/commitment_registry.py`, `backend/app/services/npc/npc_tick_pipeline.py`, `backend/app/services/game_loop/task_scheduler.py`, `backend/app/services/tick_orchestrator.py`, `backend/app/domain/body.py`, `backend/app/domain/vital_state.py`, `backend/app/domain/presentation.py`, `backend/app/services/body/body_topology_service.py`, `backend/app/services/spatial/world_topology_provider.py`, `backend/app/services/combat/injury_processor.py`, `backend/app/models/physical.py`, `architecture/body_topology.yaml`, `architecture/frontend.yaml`, `architecture/spatial.yaml` |

---

## Главная цель Stage 2.5

Stage 2.5 решает **две** связанные задачи:

1. **Temporal/Predictive Runtime (Часть I).** NPC принимает решение, основываясь на Causal State `t`, создаёт намерение относительно будущего `t+Δ`, начинает действие, мир продолжает изменяться во время исполнения этого действия.
2. **World/Embodiment Foundation (Часть II).** Закладываются архитектурные контракты, необходимые для будущего живого мира ENIGMA: физически взаимодействующие объекты, перенос/размещение предметов, двери/контейнеры/мебель, embodied actions, непрерывное старение, травмы и физические последствия, болезни, одежда, процедурное создание NPC, наследуемые визуальные признаки, генерация visual assets, 2D/2.5D/3D interchangeable representation, animation/skeleton/attachment, LOD/impostor, строгий VRAM/RAM/CPU budget.

### Главный инвариант Stage 2.5

> Будущая смена визуального представления ENIGMA с 2D на 2.5D/3D **не должна** требовать изменения семантики мира, NPC cognition, DecisionHub, spatial topology, epistemic state или causal state.

### Два несовместимых архитектурных запрета

1. **Запрет A (унаследован из Части I).** Отказ от ticks для получения realtime запрещён (ADR-O-302, ADR-047). Realtime достигается через частотное разделение, не через tickless.
2. **Запрет B (вводится Частью II).** Renderer не является источником истины о мире. Sprite, animation, mesh — проекции Embodied State и Presentation State, а не состояния самого мира.

Эти два запрета определяют весь дальнейший дизайн.

---

## Глоссарий (общий для Части I и Части II)

| Термин | Определение |
|---|---|
| **Tick** | Один шаг дискретной симуляции. В ENIGMA `GAME_TICK_INTERVAL_SECONDS = 60` (игровое время на тик). Не равен кадру рендера и не равен wall-clock секунде. |
| **Causal State** | Состояние мира на момент `t`, в котором все мутации tick `t` уже применены через `StateApplicator` и зафиксированы в `SceneStateManager.commit()`. |
| **Snapshot** | Иммутабельный срез `SnapshotKernel`, из которого `EventCompiler` генерирует `ThickSceneChange` (ADR-O-201). |
| **Commitment** | Поведенческое обязательство NPC, описанное FSM в `action_commitment.py`. Онтологический слой между решением (Intent) и исполнением (Traversal/Windup). |
| **Predicted State** | Гипотеза NPC о состоянии мира в момент `t+Δ`, выведенная из текущего Causal State и активного Commitment. |
| **Expected Outcome** | Контракт ожидаемого результата Commitment: какие поля мира изменятся, на какую величину, за какое число тиков. |
| **Actual Outcome** | Наблюдаемый результат исполнения Commitment после перехода в терминальный статус (`COMPLETED`/`FAILED`/`INTERRUPTED`). |
| **Prediction Error** | Разница между Expected и Actual Outcome. Топливо для адаптации/обучения NPC на уровне L1Chronicle. |
| **Temporal Lag** | Разница между tick, в котором произошло физическое событие, и tick, в котором NPC воспринял это событие как основание для решения. |
| **Frequency Layer** | Независимая частотная плоскость рантайма: render / simulation / decision / LLM. Каждая имеет собственный Hz-бюджет. |
| **Shadow Mode** | Режим, в котором новый компонент ЗЕРКАЛИТ существующий поток без изменения поведения (прецедент: `COMMITMENT_REGISTRY_ENABLED`, `ARBITER_ENFORCEMENT`). |
| **World State** | Семантическое состояние мира: объекты, их расположение, состояния, отношения, владение, причинность. Существует независимо от renderer. |
| **Embodied State** | Состояние тела NPC: поза, локомоция, хват, перенос, attachment, доступность конечностей, физические ограничения. Зависит от World State, не от renderer. |
| **Presentation State** | Параметризованное описание визуала: facing, animation state, visual variant, clothing, body morphology, visible injuries, equipment, LOD, RepresentationMode. Производная World+Embodied State. |
| **Visual Genome** | Детерминированное описание визуальных признаков NPC: пропорции тела, face-параметры, hair, skin, age morphology, наследуемые признаки, шрамы, асимметрия, clothing preferences, seed. |
| **RepresentationMode** | `SPRITE \| DIRECTIONAL_SPRITE \| IMPOSTOR \| LOW_POLY_3D \| FULL_3D`. Переключается runtime без смены identity/state NPC. |
| **Semantic Action** | Интент-уровень действия (`OPEN`, `TAKE`, `CARRY`, `PLACE`, `SIT`, `STAND`, `USE`, `ENTER`, `EXIT`, `EQUIP`, `UNEQUIP`, `ATTACK`). Не равен animation clip. |
| **Affordance** | Множество действий, которые мир позволяет выполнить с объектом в данном состоянии. Производная от World State + Embodied State, не от renderer. |
| **Interaction Point** | Семантический якорь на объекте (`sit_point`, `use_point`, `handle_point`, `approach_point_*`, `sleep_point`). Renderer-agnostic. |
| **Attachment Point** | Семантический якорь на теле NPC (`hand.L`, `hand.R`, `head`, `back`, `waist`, `foot.L`, `foot.R`, `body`). Используется для предметов, одежды, экипировки, эффектов. |
| **Functional Capability** | Вычисляемая из Embodied State способность NPC выполнить действие: `CAN_GRIP_SMALL_OBJECT`, `CAN_USE_TOOL`, `CAN_OPEN_LATCH`, etc. Не равна animation capability. |
| **VRAM/RAM/CPU Budget** | Формализованные лимиты: ≤ 1.5 GB VRAM, 16–32 GB RAM, mid-range CPU. Acceptance constraint, не пожелание. |

---

## 1. Контекст и проблема

### 1.1. Симптом

Игрок и DM-агент наблюдают рассинхрон: NPC реагируют на события мира с задержкой в один-два тика. На уровне UI это проявляется как «бег туда-сюда», «опоздавшие реплики», «телепортация между узлами». На уровне L1Chronicle это проявляется как отсутствие причинной связности между `TraitDriftEvent` разных NPC на одном тике.

### 1.2. Корень проблемы

Текущий цикл tick строго реактивный и линейный:

```
TICK N
├─ LifeEngine.tick()           читает state_t-1, мутирует state_t
├─ DecisionHub                  решает на основе state_t
├─ Intent → MovementEngine     материализует traversal в state_t+1
└─ snapshot сохранён

TICK N+1
├─ NPC видит результат state_t+1
└─ реагирует только сейчас
```

Цикл «посмотрел-решил-сделал» упакован в один tick, но **наблюдение результата действия** происходит на следующем tick. Это создает типичный лаг «NPC живёт на один шаг позади собственного причинного состояния».

### 1.3. Почему нельзя «просто убрать ticks»

Архитектурно запрещено (ADR-O-302, ADR-047):

- `FORBIDDEN: TICK_CATCHUP loops` — нет ретро-симуляции.
- `FORBIDDEN: datetime.now()` в simulation layer.
- `game_time_seconds` — единственный авторитет времени.
- Determinism требует дискретного шага (KernelRNG привязан к `tick`).

Поэтому Stage 2.5 **НЕ отказывается от ticks**. Он вводит временной горизонт внутри tick-структуры: NPC принимает решение, основываясь на Causal State `t`, создаёт намерение относительно будущего `t+Δ`, начинает действие, и **мир продолжает изменяться во время исполнения этого действия**.

### 1.4. Почему Stage 2.5 ставится именно здесь

В коммите `6ed3310` уже появились:

- `backend/app/domain/action_commitment.py` — FSM с состояниями `PROPOSED → COMMITTED → EXECUTING → BLOCKED → {COMPLETED, FAILED, INTERRUPTED, EXPIRED, CANCELLED}`, терминальной историей (`COMMITMENT_HISTORY_CAP_PER_NPC = 10`), детерминированной идентичностью (`build_commitment_id(tick, npc_id, action, ordinal)`).
- `backend/app/services/action/commitment_registry.py` — единый писатель реестра, shadow-зеркала `mirror_traversal_materialized / completed / interrupted`, `sweep()` для orphaned commitments.
- `backend/app/services/action/commitment_arbiter.py` — гейт материализации движения с вердиктами `PASS / REJECT(DUPLICATE|INCUMBENT)`. `INTERRUPT` явно отложен в S203.3/4.
- `backend/app/services/npc/npc_tick_pipeline.py` — pure-reducer NPC-фаз (3–6).
- `backend/app/services/game_loop/task_scheduler.py` — фоновое исполнение dialogue tasks в `ThreadPoolExecutor(max_workers=1)`, уже есть queue/priority/`SpeechScheduler`.
- `backend/app/services/npc/expectation_store.py` — EMA ожиданий наград/угроз (грубый, не привязан к commitment).

Инфраструктура существует, но **commitment пока является постфактум-записью**, а не временным механизмом. Stage 2.5 делает его временным механизмом, не трогая онтологию FSM.

---

## 2. Цели Stage 2.5

### 2.1. MUST

1. **C1 · Temporal Correctness.** NPC, принимая решение на tick `t`, имеет доступ к Causal State `t` (а не `t-1`), и Commitment, созданный на tick `t`, содержит ожидаемое состояние мира в момент `t+Δ` (Expected Outcome).
2. **C2 · Commitment как временной контракт.** `ActionCommitment` расширяется полями `expected_outcome`, `eta_ticks`, `prediction_horizon`, `actual_outcome`, `prediction_error`. Изменения обратно совместимы: старые записи получают `expected_outcome = None` и трактуются как legacy.
3. **C3 · Prediction Engine.** Вводится компонент, который для данного `(npc_id, action, target_id, current_causal_state)` возвращает `ExpectedOutcome` без LLM. Только детерминированные эвристики: ETA по пути, delta hunger по действию, длительность по archetype.
4. **C4 · Outcome Observation.** После перехода Commitment в терминальный статус вычисляется `ActualOutcome` и `PredictionError`. Ошибка публикуется в `L1Chronicle` как `TraitDriftEvent` нового типа `prediction_error`.
5. **C5 · Inertia / Anti-flap.** Commitment в статусе `COMMITTED` или `EXECUTING` не прерывается произвольным следующим решением DecisionHub. Прерывание возможно только через явно описанную политику (раздел 9).
6. **C6 · Non-Breaking Migration.** Stage 2.5 вводится за флагом `STAGE_25_PREDICTIVE_RUNTIME` (env), по умолчанию `OFF`. Поведение тика при `OFF` байтово идентично текущему. Прецедент: `ARBITER_ENFORCEMENT`, `COMMITMENT_REGISTRY_ENABLED`.

### 2.2. SHOULD

1. **S1 · Prediction Horizon Tiered.** Три горизонта: `t+1`, `t+5`, `t+20` тиков. Полное моделирование мира не требуется — достаточно предсказания последствий собственного commitment.
2. **S2 · Replan Trigger.** При `PredictionError > threshold` NPC получает право на досрочный replan внутри того же tick (без ожидания следующего decision phase).
3. **S3 · Determinism Preservation.** Все предсказания используют `KernelRNG(tick, npc_id, salt="prediction")`. Replay должен воспроизводить тот же commitment_id и тот же expected_outcome.

### 2.3. MAY

1. **M1 · LLM Hints.** LLM может подсказывать `expected_outcome` для нестандартных действий (кастомные интенты), но всегда валидируется детерминированным слоем (validation, не генерация).
2. **M2 · Cross-NPC Prediction.** NPC предсказывает действия других NPC (заглядывает в их `active_commitments`). Только чтение `commitment_registry.get_active(other_npc_id)`.

---

## 3. Текущее состояние (audit 6ed3310)

### 3.1. Что уже работает

| Компонент | Файл | Что делает | Готовность к Stage 2.5 |
|---|---|---|---|
| `COMMITMENT_STATUSES` FSM | `action_commitment.py:26-56` | 9 состояний, переходы описаны, терминалы неизменны | Готов. Расширение полями — non-breaking. |
| `build_commitment_id(tick, npc_id, action, ordinal)` | `action_commitment.py:83-91` | Детерминированная идентичность через md5 | Готов. Можно напрямую привязать expected_outcome. |
| `CommitmentRegistry.commit()` | `commitment_registry.py:142-190` | Создаёт COMMITTED, прерывает суперсессию как INTERRUPTED(SUPERSEDED) | Готов. Точка инъекции expected_outcome. |
| `CommitmentArbiter.arbitrate()` | `commitment_arbiter.py:67-121` | PASS / REJECT(DUPLICATE / INCUMBENT) | Готов для расширения INTERRUPT (S203.3). |
| `CommitmentRegistry.sweep()` | `commitment_registry.py:285-309` | Ловит orphaned commitments (TRAVERSAL_VANISHED) | Готов. Источник actual_outcome при vanish. |
| `TaskScheduler` async pool | `task_scheduler.py:30-69` | Фоновая обработка dialogue tasks | Готов как infrastructure для долгих commitment'ов. |
| `ExpectationStore` | `expectation_store.py` | EMA наград/угроз (грубая) | MAY быть заменён PredictedState из Stage 2.5. |
| `SceneStateManager` (commit boundary) | `pipeline.yaml:183-187` | `state_t-1` deep immutable + `WorldProjectionBuffer` | Готов как источник `current_causal_state`. |

### 3.2. Чего не хватает (gap inventory)

1. **G1.** `ActionCommitment` не содержит `expected_outcome`, `eta_ticks`, `actual_outcome`, `prediction_error`. Нет временной проекции.
2. **G2.** Нет `PredictionEngine`. Решение принимается на `state_t-1` (точнее, на snapshot из Phase 0 того же tick, но без горизонта).
3. **G3.** `CommitmentArbiter` не умеет `INTERRUPT` (явно отложено в S203.3/4). Сейчас суперсессия делается автоматически в `commit()` через `INTERRUPTED(SUPERSEDED_BY_NEW_MATERIALIZATION)` — это работает, но без учёта приоритетов и без policy.
4. **G4.** `DecisionHub` не имеет feedback loop: после `COMPLETED`/`FAILED`/`INTERRUPTED` не происходит обновления модели NPC.
5. **G5.** `npc_tick_pipeline.run_npc_pipeline` не имеет phase «prediction». Pipeline: `perception → memory → drives → decision → intent`. Нет звена `prediction → expected_outcome → commitment temporal projection`.
6. **G6.** Нет observability-слоя для temporal lag. `[ARBITER_REJECT]` логи есть, но метрики p95 lag / churn commitments отсутствуют.
7. **G7.** `ExpectationStore` живёт в SQLite (`memory.db`) отдельно от `commitment_history` в `scene_state`. Это расщепление онтологии: «ожидание» и «commitment» должны быть одним объектом или, как минимум, согласованы.

---

## 4. Temporal Archaeology

Цель раздела — явно перечислить, на каком именно шаге возникает lag, и зафиксировать budget для каждой стадии pipeline. Без этой таблицы реализация Stage 2.5 рискует устранить один lag и добавить другой.

### 4.1. Цепочка причинного прохождения

```
player input
      │
      ▼
event creation (InterventionEvent, ADR-TZ08-1)
      │
      ▼
world mutation (LifeEngine.tick → SceneChange)
      │
      ▼
snapshot (SnapshotKernel, immutable)
      │
      ▼
NPC perception (LocalCausalSolver, Phase 9)
      │
      ▼
decision (NpcTickPipeline.run_npc_pipeline, Phase 5)
      │
      ▼
commitment (CommitmentRegistry.commit)
      │
      ▼
execution (MovementEngine / TaskScheduler)
      │
      ▼
projection (ProjectionEngine.apply_changes)
      │
      ▼
next snapshot (state_t+1)
```

### 4.2. Lag inventory

| Звено | Читает (tick) | Пишет (tick) | Видно NPC (tick) | Лаг | Комментарий |
|---|---|---|---|---|---|
| Player input | t | t | — | 0 | InterventionEvent принимается в Phase 1 того же tick. |
| LifeEngine mutation | t-1 (snapshot) | t | t+1 | 1 | Decision на tick t видит результат LifeEngine с tick t-1 через snapshot. |
| Snapshot compilation | t | t | t (внутри tick) | 0 | SnapshotKernel иммутабелен внутри tick. |
| NPC perception | t | t (belief) | t+1 (decision) | 1 | LocalCausalSolver пишет belief в Phase 9, decision его увидит только в следующем tick. |
| Decision | t | t | t+1 | 1 | Intent, созданный в Phase 5 tick t, попадёт в Commitment tick t, исполнится tick t+1. |
| Commitment COMMIT | t | t | t (через registry) | 0 | Реестр обновляется синхронно с decision. |
| Commitment EXECUTING | t | t | t+1 (effect) | 1 | MovementEngine материализует traversal в state_t+1. |
| Traversal completion | t (запущен) | t+Δ | t+Δ+1 | Δ+1 | Δ = ETA в tick'ах. |
| Commitment COMPLETED | t+Δ | t+Δ | t+Δ+1 (видно decision) | 1 | Decision tick t+Δ+1 видит COMPLETED tick t+Δ. |
| Belief revision | t+Δ+1 | t+Δ+1 | t+Δ+2 | 1 | CrystallizedBelief обновляется в Phase 9 tick t+Δ+1, виден в decision tick t+Δ+2. |
| **Суммарный lag игрока → реакция NPC** | | | | **≈ 5–7 тиков** | При Δ=3 это ~6 тиков = 6 минут игрового времени. |

### 4.3. Lag budget после Stage 2.5

| Звено | Целевой лаг | Механизм Stage 2.5 |
|---|---|---|
| Player input → Decision видит изменение | 0–1 tick | Decision читает Causal State `t` напрямую (а не snapshot `t-1`). |
| Decision → Commitment с ExpectedOutcome | 0 tick | `PredictionEngine.predict()` вызывается синхронно в Phase 5. |
| Commitment → виден другим NPC | 0 tick (внутри tick) | `CommitmentRegistry.get_active(other_npc_id)` доступен read-only в любом phase. |
| Commitment COMPLETED → адаптация NPC | 1 tick | `PredictionError` публикуется в `L1Chronicle` на следующем tick. |
| **Суммарный целевой lag** | **2–3 tick** | Уменьшение в 2–3 раза без отказа от ticks. |

### 4.4. Лаг-запреты (constraints)

Stage 2.5 НЕ добавляет новые lag-источники:

- `FORBIDDEN: PredictionEngine не должен вызывать LLM в hot path decision.` LLM-подсказки кэшируются и обновляются в idle.
- `FORBIDDEN: expected_outcome не должен мутировать world state.` Это проекция, не мутация (прецедент: ADR-O-201 Law C — Projection-only).
- `FORBIDDEN: prediction_error не должен влиять на determinism replay.` Replay должен воспроизвести тот же expected_outcome; actual_outcome детерминирован состоянием.

---

## 5. Архитектурные принципы

1. **P1. Commitment — временной объект, не только владение.** Сейчас `ActionCommitment` отвечает на «чем занят NPC». Stage 2.5 добавляет ответ на «когда ожидается результат и какой». FSM не меняется, расширяется контейнер данных.
2. **P2. Prediction — pure function, не сервис с состоянием.** `PredictionEngine.predict(npc, action, target, causal_state, rng) → ExpectedOutcome`. Никакого внутреннего кэша, никакого I/O.
3. **P3. Determinism — first-class citizen.** Все предсказания привязаны к `KernelRNG(tick, npc_id, salt="prediction_v1")`. Любая рандомизация вне RNG — `OntologyViolationError`.
4. **P4. Inertia through Commitment, not through lock.** Anti-flap достигается не блокировкой DecisionHub, а тем, что `CommitmentArbiter` отклоняет новые candidates в пользу incumbent (уже работает для DUPLICATE/INCUMBENT; Stage 2.5 добавляет приоритетную политику).
5. **P5. Frequency separation.** Render, simulation, decision, LLM — независимые частоты. Stage 2.5 фиксирует это разделение в конфигурации (`architecture/temporal.yaml` расширение), но не вводит real-time поток.
6. **P6. Shadow-first.** Как `COMMITMENT_REGISTRY_ENABLED` и `ARBITER_ENFORCEMENT`, все новые гейты вводятся за env-флагом, проходят A/B-измерения, и только потом переводятся в enforcement.
7. **P7. Observability — read-only.** Все метрики temporal lag — observability-сигналы. Логи, трейсы, гистограммы — не создают причинность (прецедент: §11 Устава).

---

## 6. Компоненты и контракты

### 6.1. Расширение `ActionCommitment` (domain layer)

**Файл:** `backend/app/domain/action_commitment.py`

`COMMITMENT_STATUSES`, `COMMITMENT_TRANSITIONS`, `ACTIVE_COMMITMENT_STATUSES` остаются без изменений. Расширяется только `build_commitment_dict`:

```python
def build_commitment_dict(
    tick: int,
    npc_id: str,
    action: str,
    ordinal: int,
    cause: str,
    target_id: Optional[str] = None,
    executor: str = "",
    parent_commitment_id: Optional[str] = None,
    initial_status: str = "PROPOSED",
    # ── Stage 2.5: temporal projection ───────────────────────────
    expected_outcome: Optional[Dict[str, Any]] = None,   # PredictedState diff
    eta_ticks: Optional[int] = None,                     # сколько тиков до COMPLETED
    prediction_horizon: Tuple[int, ...] = (1, 5, 20),   # тики, на которые есть прогноз
    prediction_rng_seed: Optional[str] = None,           # для replay-детерминизма
) -> Dict[str, Any]:
    ...
    return {
        ...существующие поля...,
        "expected_outcome": expected_outcome,             # dict или None (legacy)
        "eta_ticks": eta_ticks,
        "prediction_horizon": list(prediction_horizon),
        "prediction_rng_seed": prediction_rng_seed,
        # Заполняется при терминализации:
        "actual_outcome": None,
        "prediction_error": None,                        # dict с метриками ошибки
        "terminal_tick": None,
    }
```

**Контракт `expected_outcome`:**

```python
{
    "predicted_state_delta": {
        "hunger": -30,            # int/float delta
        "food_inventory": -1,
        "location": "kitchen",    # для movement-коммитментов
    },
    "predicted_duration_ticks": 8,
    "predicted_probability": 0.85,  # уверенность предсказания
    "predicted_by": "heuristic:movement_eta_v1",  # источник
    "predicted_at_tick": 42,
}
```

**Контракт `actual_outcome`** (заполняется при переходе в терминальный статус):

```python
{
    "observed_state_delta": {"hunger": -22, "food_inventory": -1},
    "observed_duration_ticks": 11,
    "observed_terminal_status": "COMPLETED",   # или FAILED/INTERRUPTED/EXPIRED
}
```

**Контракт `prediction_error`:**

```python
{
    "delta_error": {"hunger": 8},              # expected - actual
    "duration_error_ticks": 3,                 # actual - expected
    "normalized_error": 0.27,                  # |delta_error| / |expected|
    "status_match": True,
    "publish_to_l1": True,                    # генерирует TraitDriftEvent
}
```

### 6.2. `PredictionEngine` (новый сервис, application layer)

**Файл (предлагаемый):** `backend/app/services/npc/prediction_engine.py`

```python
class PredictionEngine:
    """Stage 2.5: Pure-function predictor. No state, no I/O."""

    @staticmethod
    def predict(
        npc_id: str,
        action: str,
        target_id: Optional[str],
        causal_state: Dict[str, Any],
        rng: "KernelRNG",
        tick: int,
    ) -> Optional[ExpectedOutcome]:
        """
        Возвращает ExpectedOutcome или None (если действие непредсказуемо).

        Маршрутизация по action:
          - "MOVE"         → _predict_move (ETA из pathfinding)
          - "EAT"          → _predict_consume (hunger delta из archetype)
          - "SLEEP"        → _predict_sleep (energy restore curve)
          - "TALK"         → _predict_dialogue (duration из SpeechScheduler)
          - "WORK_<kind>"  → _predict_work (resource delta из economy.yaml)
          - unknown        → None (DecisionHub получит warning)
        """
        ...
```

**Контракт `ExpectedOutcome` (dataclass):**

```python
@dataclass(frozen=True)
class ExpectedOutcome:
    predicted_state_delta: Dict[str, float]
    predicted_duration_ticks: int
    predicted_probability: float           # [0.0, 1.0]
    predicted_by: str                     # "heuristic:movement_eta_v1" etc.
    prediction_rng_seed: str              # для replay

    def to_dict(self) -> Dict[str, Any]: ...
    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "ExpectedOutcome": ...
```

**Эвристики (минимальный набор, MUST):**

| Action | Эвристика | Источник данных |
|---|---|---|
| `MOVE` | `ETA_ticks = ceil(path_length / avg_speed)` | `SpatialService.find_path`, `archetype.movement_speed` |
| `EAT` | `hunger_delta = -food_item.nutrition`, `duration = food_item.consume_ticks` | `config/npc/archetypes/*.json`, `economy.yaml` |
| `SLEEP` | `energy_restore_rate × duration`, capped at archetype.max_energy | `archetype.sleep_profile` |
| `TALK` | `duration_ticks = ceil(speech_pacing_seconds / GAME_TICK_INTERVAL_SECONDS)` | `TaskScheduler._dialogue_ttl`, `SpeechScheduler` pacing |
| `WORK` | `resource_delta`, `duration` из `economy.yaml` для `work_kind` | `architecture/economy.yaml` |

### 6.3. `OutcomeObserver` (новый сервис, application layer)

**Файл (предлагаемый):** `backend/app/services/npc/outcome_observer.py`

```python
class OutcomeObserver:
    """Stage 2.5: Вычисляет actual_outcome и prediction_error при терминализации
    Commitment. Подписан на события CommitmentRegistry (post-terminate hook)."""

    @staticmethod
    def observe(
        scene_state: Dict[str, Any],
        npc_id: str,
        terminal_commitment: Dict[str, Any],
        tick: int,
    ) -> Optional[PredictionError]:
        """
        Сравнивает expected_outcome с фактическими изменениями state NPC
        за период [created_tick, terminal_tick].
        Возвращает PredictionError или None (если expected_outcome was None — legacy).
        """
        ...
        # Публикует TraitDriftEvent(event_type="prediction_error", ...)
        # в L1Chronicle (через existing pattern_detector pipeline).
```

### 6.4. Расширение `CommitmentArbiter` (S203.3, ранее отложенное)

**Файл:** `backend/app/services/action/commitment_arbiter.py`

Добавляется вердикт `INTERRUPT` (ранее отложенный в S203.3/4):

```python
VERDICT_INTERRUPT = "INTERRUPT"

class CommitmentArbiter:
    @staticmethod
    def arbitrate(
        scene_state, npc_id, candidate_target, candidate_source, tick,
        candidate_priority: int = 0,   # NEW
    ) -> ArbitrationResult:
        incumbent = CommitmentRegistry.get_active(scene_state, npc_id)
        if incumbent is None:
            return ArbitrationResult(verdict=VERDICT_PASS)

        incumbent_priority = incumbent.get("priority", 0)
        candidate_priority = candidate_priority

        # Новая политика приоритетов:
        if candidate_priority > incumbent_priority + INTERRUPT_THRESHOLD:
            return ArbitrationResult(
                verdict=VERDICT_INTERRUPT,
                incumbent_id=incumbent["commitment_id"],
                reason="PRIORITY_SUPERSEDE",
            )

        # Существующая логика DUPLICATE / INCUMBENT — без изменений.
        ...
```

### 6.5. Расширение `NpcTickPipeline` (Phase 5 — вставка Prediction Phase)

**Файл:** `backend/app/services/npc/npc_tick_pipeline.py`

В `run_npc_pipeline` добавляется sub-phase между `decision` и `intent_materialization`:

```
Phase 5 (decision):
  5.1  perception (existing)
  5.2  memory       (existing)
  5.3  drives       (existing, DriveResolver L0+L1→L3)
  5.4  decision     (existing, DecisionHub)
  5.5  ★ prediction (NEW, Stage 2.5)
       - Если DecisionHub вернул Intent, вызвать PredictionEngine.predict()
       - Прикрепить expected_outcome к будущему commitment
  5.6  intent emission (existing, с расширенным payload)
```

Вставка **синхронная** (не асинхронная), потому что PredictionEngine — pure function. Это не убивает CPU, так как нет LLM.

### 6.6. `PredictionError` → `L1Chronicle` (extension)

В `backend/app/services/npc/l1_chronicle.py` добавляется новый тип события:

```python
# TraitDriftEvent.event_type расширяется:
PREDICTION_ERROR = "prediction_error"
```

`OutcomeObserver` вызывает `L1Chronicle.append(TraitDriftEvent(target_id=npc_id, event_type="prediction_error", effect_value=prediction_error.normalized_error, ...))`. Дальше существующий `PatternDetector` и `BeliefCrystallizationEngine` обрабатывают это как обычный источник L1.5 статистики.

---

## 7. Поток данных (Stage 2.5 loop)

### 7.1. Архитектурная петля

```
        ┌─────────────────────────────────────────────────────┐
        │                                                     │
        ▼                                                     │
  CURRENT CAUSAL STATE (t)                          PREDICTED FUTURE (t+Δ)
        │                                                     ▲
        ▼                                                     │
   PERCEPTION  ────────────────►  BELIEFS                    │
        │                                                     │
        ▼                                                     │
     DRIVES (L0 + L1 → L3)                                    │
        │                                                     │
        ▼                                                     │
     DECISION (Phase 5.4)                                     │
        │                                                     │
        ▼                                                     │
  ★ PREDICTION (Phase 5.5, NEW)  ──── ExpectedOutcome ────────┘
        │
        ▼
     COMMITMENT (Phase 5.6)
        │  expected_outcome, eta_ticks, prediction_rng_seed
        ▼
     EXECUTION (Phase 0 next tick / TaskScheduler)
        │
        ▼  (eta_ticks later)
     ACTUAL OUTCOME
        │
        ▼
  ★ OUTCOME OBSERVER (NEW)
        │  computes prediction_error
        ▼
     L1CHRONICLE.append(prediction_error event)
        │
        ▼
     PATTERN DETECTOR → BELIEF CRYSTALLIZATION
        │
        ▼
  UPDATED WORLD (next tick decision sees adapted beliefs)
        │
        └──────────────────────────────────────────────────────┘
```

### 7.2. Пример трассировки (конкретный сценарий)

**Scenario:** NPC `lusya` решает пойти на кухню и приготовить еду.

| Tick | Phase | Событие | Поле commitment |
|---|---|---|---|
| 100 | 5.4 | DecisionHub возвращает Intent(action=MOVE, target=kitchen) | — |
| 100 | 5.5 ★ | PredictionEngine.predict(lusya, MOVE, kitchen) → ETA=2, hunger=-0 | expected_outcome.delta.hunger=0, eta_ticks=2 |
| 100 | 5.6 | CommitmentRegistry.commit() создаёт commitment с expected_outcome | status=COMMITTED, executor=traversal |
| 100 | Phase 0 next | MovementEngine materializes traversal | status=EXECUTING |
| 101 | Phase 0 | Traversal in progress | — |
| 102 | Phase 0 | Traversal completes (kitchen reached) | status=COMPLETED, terminal_tick=102 |
| 102 | Phase 9 ★ | OutcomeObserver.observe() — actual_duration_ticks=2, state.location=kitchen | actual_outcome, prediction_error.delta_error={} |
| 102 | Phase 9 | L1Chronicle.append(prediction_error, normalized_error=0.0) | prediction_error в chronicle |
| 103 | Phase 5 | Decision видит: location=kitchen, hunger=high → новый Intent(action=EAT) | новый commitment c parent_id=cmt-... |
| 103 | 5.5 ★ | PredictionEngine.predict(lusya, EAT) → hunger=-30, duration=8 | expected_outcome.delta.hunger=-30, eta_ticks=8 |
| 111 | Phase 9 ★ | OutcomeObserver: actual hunger=-22 (food was partial) | prediction_error.delta_error.hunger=8, normalized_error=0.27 |
| 111 | L1Chronicle | prediction_error published, PatternDetector increments behavior_variance for `cooking` | belief crystallization обновится к tick 112 |

### 7.3. Anti-flap демонстрация

Без Stage 2.5: на tick 100 Lusya решила MOVE к кухне. На tick 101 приходит социальный stimulus (например, NPC подошёл и заговорил) — DecisionHub может выдать новый Intent(TALK), который перебьёт MOVE. Lusya разворачивается посреди пути.

С Stage 2.5: `CommitmentArbiter.arbitrate()` видит incumbent `COMMITTED/MOVE/kitchen` и candidate `TALK`. Без `INTERRUPT_THRESHOLD` превышения приоритета — `REJECT(INCUMBENT)`. Lusya продолжает идти, разговор откладывается. Если stimulus критический (`candidate_priority > incumbent_priority + INTERRUPT_THRESHOLD`) — `INTERRUPT(SUPERSEDED)`, Lusya прерывает движение с записью в `commitment_history` и `parent_commitment_id` linkage.

---

## 8. Frequency Separation

Stage 2.5 явно фиксирует разделение частот в `architecture/temporal.yaml` (расширение, без удаления существующих constraints).

### 8.1. Частотные плоскости

| Плоскость | Частота | Бюджет CPU | Механизм |
|---|---|---|---|
| **Render** | 30–60 Hz (wall-clock) | вне backend | frontend `display_manager.py`, не синхронизирован с tick |
| **Simulation tick** | 1 Hz (game time, `GAME_TICK_INTERVAL_SECONDS=60`) | dominates wall-clock в pauseless режиме | `TickOrchestrator.execute()` |
| **Decision (NPC)** | 0.05–0.1 Hz (раз в 10–20 тиков на NPC, phased) | < 5ms/NPC/tick | `NpcTickPipeline.run_npc_pipeline` |
| **LLM call** | ≤ 0.01 Hz (1 call per NPC per 100+ ticks) | ≤ 1 concurrent (ThreadPoolExecutor max_workers=1) | `TaskScheduler.execute_pending` |
| **Prediction** (NEW) | 0.05–0.1 Hz (внутри decision phase) | < 1ms/NPC/tick | `PredictionEngine.predict` (pure function) |
| **Outcome observation** (NEW) | event-driven (на каждый terminal commitment) | < 0.5ms/event | `OutcomeObserver.observe` |

### 8.2. Бюджет CPU на NPC/tick (target)

| Фаза | CPU/NPC/tick (ms) | Комментарий |
|---|---|---|
| Perception | 0.5 | LocalCausalSolver, existing |
| Memory | 0.3 | MemoryManager.apply, existing |
| Drives | 0.2 | DriveResolver, existing |
| Decision | 1.0 | DecisionHub, existing |
| **Prediction** ★ | **0.5** | Новая фаза 5.5, pure function |
| Commitment emission | 0.1 | CommitmentRegistry.commit |
| **Outcome observe** ★ | **0.3** | На терминализацию, не каждый tick |
| **Итого** | **~2.9 ms/NPC/tick** | При 30 NPC: ~87 ms/tick. Запас по 1 Hz tick — порядок. |

### 8.3. Что НЕ меняется

- `GAME_TICK_INTERVAL_SECONDS = 60` остаётся. Stage 2.5 не вводит real-time.
- `KernelRNG(tick, npc_id, salt)` — единственный источник рандома, остаётся.
- Wall-clock остаётся forbidden в simulation layer (ADR-O-302).

---

## 9. Политика прерывания Commitment

### 9.1. Статусы и право на прерывание

| Статус incumbent | Может быть прерван? | Условие |
|---|---|---|
| `PROPOSED` | Да, безусловно | Любой более приоритетный candidate. |
| `COMMITTED` | Да, при `candidate_priority > incumbent_priority + INTERRUPT_THRESHOLD` | Default `INTERRUPT_THRESHOLD = 3` (в `config/calibration/`). |
| `EXECUTING` | Да, при тех же условиях + класс причины ∈ emergency | emergency: hunger_critical, threat_imminent, social_force_high. |
| `BLOCKED` | Да, по таймауту или явному REPLAN | `BLOCKED → FAILED` после `BLOCKED_TIMEOUT_TICKS`. |

### 9.2. Причины прерывания (`interrupt_reason` enum)

Расширение существующей строки `interrupt_reason` в `action_commitment.py`:

| Reason | Семантика | Прецедент |
|---|---|---|
| `SUPERSEDED_BY_NEW_MATERIALIZATION` | Существующий. Двойное исполнение. | (existing) |
| `TRAVERSAL_VANISHED` | Существующий. Sweep поймал orphan. | (existing) |
| `PRIORITY_SUPERSEDE` | NEW. более приоритетный candidate. | Stage 2.5 |
| `EMERGENCY_HUNGER` | NEW. hunger пересёк critical threshold. | Stage 2.5 |
| `EMERGENCY_THREAT` | NEW. threat_imminent (combat-subscriber signal). | Stage 2.5 |
| `SOCIAL_FORCE_HIGH` | NEW. Социальное событие с высоким salience. | Stage 2.5 |
| `TASK_IMPOSSIBLE` | NEW. Pre-condition failed (target destroyed, path blocked permanently). | Stage 2.5 |
| `NEW_INFORMATION` | NEW. NPC получил информацию, делающую commitment нецелесообразным. | Stage 2.5 |

### 9.3. Anti-flap гарантия

`CommitmentArbiter.enforce()` всегда возвращает `False` для новых candidates, если incumbent активен и interrupt policy не сработала. Это **гейт**, а не advisory. Никакой другой код не должен обходить arbiter для создания traversal.

Исключение: `CommitmentRegistry.cancel()` (explicit cancellation) — вызывается только из DM-agent или тестов, сопровождается audit log.

---

## 10. Migration Plan

Stage 2.5 вводится в 4 подэтапа. Каждый — за env-флагом, с A/B-измерениями, с возможностью отката одной константой.

### 10.1. Этап M1 — Field Extension (shadow, non-breaking)

**Цель:** Расширить `build_commitment_dict` новыми полями, не меняя поведения.

**Файлы:**
- `backend/app/domain/action_commitment.py` — добавить параметры `expected_outcome`, `eta_ticks`, `prediction_horizon`, `prediction_rng_seed`, `actual_outcome`, `prediction_error`, `terminal_tick` (все `Optional`, default `None`).
- `backend/app/services/action/commitment_registry.py` — прокинуть новые параметры через `commit()`, без вызова `PredictionEngine`.

**Флаг:** `STAGE_25_COMMITMENT_FIELDS` (default `OFF` — поля не записываются, поведение идентично текущему).

**Acceptance:**
- Все существующие тесты `backend/tests/sandbox/commitment_baseline.py` зелёные.
- Replay детерминизма (`INV-REPLAY-DETERMINISM`) не нарушен: при `OFF` commitment dict байтово идентичен pre-Stage-2.5.

### 10.2. Этап M2 — Prediction Engine (no enforcement)

**Цель:** `PredictionEngine.predict()` вызывается в Phase 5.5, результат **записывается** в `expected_outcome`, но **не используется** для arbitration.

**Файлы:**
- NEW `backend/app/services/npc/prediction_engine.py`
- `backend/app/services/npc/npc_tick_pipeline.py` — вставка Phase 5.5 (conditional на флаг).
- `backend/app/services/tick_orchestrator.py` — Phase 5 делегирует в `run_npc_pipeline`, без изменений в оркестрации.

**Флаг:** `STAGE_25_PREDICTION_ENGINE` (default `OFF`).

**Acceptance:**
- При `ON`: каждый новый commitment имеет non-null `expected_outcome` (кроме unknown actions).
- При `OFF`: поля `expected_outcome` остаются `None` (как в M1).
- A/B прогон 200 tickов: `expected_outcome` populated rate > 80% для MOVE/EAT/SLEEP, < 20% для unknown intents.
- p95 CPU/NPC/tick в Phase 5 ≤ 1.5 ms (измерение через `time.perf_counter()` в observability).

### 10.3. Этап M3 — Outcome Observer + L1Chronicle publication

**Цель:** При терминализации commitment вычисляется `actual_outcome` и `prediction_error`, публикуется в `L1Chronicle`.

**Файлы:**
- NEW `backend/app/services/npc/outcome_observer.py`
- `backend/app/services/action/commitment_registry.py` — post-terminate hook вызывает `OutcomeObserver.observe()`.
- `backend/app/services/npc/l1_chronicle.py` — `TraitDriftEvent.event_type` расширяется `"prediction_error"`.

**Флаг:** `STAGE_25_OUTCOME_OBSERVER` (default `OFF`).

**Acceptance:**
- При `ON`: каждый терминальный commitment с non-null `expected_outcome` получает non-null `actual_outcome` и `prediction_error`.
- `L1Chronicle` получает новые события типа `prediction_error`. `PatternDetector` корректно их агрегирует (без crash).
- Distribution `normalized_error` за 1000 tickов: mean < 0.3, p95 < 0.5 (sanity — предсказания не должны быть полностью случайными).

### 10.4. Этап M4 — Arbiter INTERRUPT (enforcement)

**Цель:** `CommitmentArbiter` получает третий вердикт `INTERRUPT`, политика приоритетов активна.

**Файлы:**
- `backend/app/services/action/commitment_arbiter.py` — extension.
- `config/calibration/interrupt_thresholds.yaml` (NEW) — `INTERRUPT_THRESHOLD`, `BLOCKED_TIMEOUT_TICKS`.

**Флаги:**
- `STAGE_25_ARBITER_INTERRUPT` (default `OFF`) — включает INTERRUPT verdict.
- `ARBITER_ENFORCEMENT` (existing) — должен быть `ON` для вступления INTERRUPT в силу.

**Acceptance:**
- A/B прогон: количество `INTERRUPTED(PRIORITY_SUPERSEDE)` > 0, но < 10% от всех commitments (anti-flap не должен стать «всё прерывается»).
- Thrash metric (коммитментов с `parent_commitment_id != None` и terminal status INTERRUPTED) ≤ 15%.
- p95 wall-clock для tick не увеличился более чем на 10%.

### 10.5. Этап M5 — Replan Trigger (post-Stage 2.5, опционально)

**Цель:** При `prediction_error.normalized_error > REPLAN_THRESHOLD` NPC получает право на досрочный replan внутри того же tick.

**Флаг:** `STAGE_25_REPLAN_TRIGGER` (default `OFF`).

Этот этап опционален и может быть отложен до Stage 8 (Motivation + Commitment / Replanning), где replan становится полноценной когнитивной функцией.

### 10.6. Rollback strategy

Каждый этап независимо откатывается одной env-переменной. Комбинаторика:

| `STAGE_25_COMMITMENT_FIELDS` | `STAGE_25_PREDICTION_ENGINE` | `STAGE_25_OUTCOME_OBSERVER` | `STAGE_25_ARBITER_INTERRUPT` | Поведение |
|---|---|---|---|---|
| OFF | OFF | OFF | OFF | Identical to 6ed3310 (current) |
| ON | OFF | OFF | OFF | Fields exist, all None (no behavior change) |
| ON | ON | OFF | OFF | Predictions recorded, not used |
| ON | ON | ON | OFF | Predictions + outcome observability |
| ON | ON | ON | ON | Full Stage 2.5 active |

**Принцип:** Новые флаги не могут быть `ON`, если предыдущие `OFF`. Этим обеспечивается целостность данных.

---

## 11. Acceptance Criteria (измеримые)

Stage 2.5 считается завершённым, когда:

### 11.1. Functional

- **AC-1.** Для каждого нового commitment с action ∈ {MOVE, EAT, SLEEP, TALK, WORK_*} поле `expected_outcome` не `None`. Покрытие > 80% по A/B прогону 500 tickов.
- **AC-2.** Для каждого терминального commitment с non-null `expected_outcome` поля `actual_outcome` и `prediction_error` не `None`.
- **AC-3.** `prediction_error.normalized_error ∈ [0.0, 1.0]` (sanity bound).
- **AC-4.** `L1Chronicle` получает события `prediction_error`, `PatternDetector` их агрегирует без crash.
- **AC-5.** `CommitmentArbiter` возвращает `INTERRUPT` при превышении приоритета (M4 active).

### 11.2. Performance

- **AC-6.** p95 CPU/NPC/tick в Phase 5 ≤ 1.5 ms (measured via `time.perf_counter()` в observability).
- **AC-7.** p95 wall-clock для tick ≤ текущего + 10%.
- **AC-8.** Memory overhead от `expected_outcome` (commitment_history bounded by `COMMITMENT_HISTORY_CAP_PER_NPC=10`) ≤ 5 KB/NPC.

### 11.3. Determinism

- **AC-9.** Replay того же tick с тем же KernelRNG seed воспроизводит идентичный `expected_outcome` (байтово).
- **AC-10.** `INV-REPLAY-DETERMINISM` тест остаётся зелёным.

### 11.4. Behavioural

- **AC-11.** Thrash metric (доля INTERRUPTED commitments с `parent_commitment_id != None`) ≤ 15% за 1000-tick прогон.
- **AC-12.** Количество «NPC бегает туда-сюда» (двойных reversal за ≤ 3 tickа) уменьшено минимум на 50% vs baseline (измерение через semantic torture reports в `reports/semantic_torture_*.md`).

### 11.5. Observability

- **AC-13.** Логи `[PREDICTION]` содержат `npc_id, action, eta_ticks, predicted_by`.
- **AC-14.** Логи `[OUTCOME_OBSERVER]` содержат `commitment_id, normalized_error, status_match`.
- **AC-15.** Метрика `prediction_error_distribution` доступна в `reports/` (гистограмма по action типам).

---

## 12. Риски и митигации

| # | Риск | Severity | Mitigation |
|---|---|---|---|
| R1 | `PredictionEngine` становится узким местом CPU, если эвристики усложняются. | HIGH | Pure function, no I/O. p95 budget 0.5 ms/NPC/tick. Если пробивается — кэшировать ETA по `(npc, target_node)` до изменения world topology. |
| R2 | `expected_outcome` мутирует world state (нарушение Law C). | CRITICAL | Code review + lint rule: `expected_outcome` поля только для чтения. Тест `test_expected_outcome_is_read_only`. |
| R3 | `INTERRUPT` политика слишком агрессивна, всё прерывается. | HIGH | `INTERRUPT_THRESHOLD` калибруется в A/B. Thrash metric ≤ 15% — hard limit. |
| R4 | `INTERRUPT` политика слишком консервативна, anti-flap не работает. | MEDIUM | Threshold tuning. Если < 5% INTERRUPT — снижать порог. |
| R5 | Stale predictions: NPC держит commitment с `eta_ticks=5`, но world изменился (target уничтожен). | HIGH | `OutcomeObserver` детектирует через `precondition_check` при терминализации. На каждом tick `CommitmentRegistry.sweep()` (existing) ловит orphaned. Stage 2.5 добавляет precondition re-validation при `EXECUTING` каждом tick. |
| R6 | `prediction_error` зашумляет L1Chronicle, ломая existing pattern detection. | MEDIUM | Новые события имеют distinct `event_type="prediction_error"`, существующие `PatternDetector` их фильтруют по default (если не расширен). |
| R7 | Replay ломается: seed `prediction_rng_seed` не совпадает между прогонами. | CRITICAL | `KernelRNG(tick, npc_id, salt="prediction_v1")` — детерминирован. Тест `test_replay_reproduces_expected_outcome`. |
| R8 | Deadlock в `CommitmentArbiter`: два NPC с mutual INTERRUPT. | MEDIUM | `INTERRUPT` только от более приоритетного candidate. Приоритет — scalar, не циклический. |
| R9 | Shadow → enforcement переход ломает существующий игровой баланс. | HIGH | Каждый этап за флагом, A/B измерение, gradual rollout. Pre-flight checklist (`docs/audits/ADR-PRE-FLIGHT CHECKLIST.md`). |
| R10 | LLM-predicted `expected_outcome` (M1) непредсказуем. | LOW | M1 — MAY, не MUST. Если включается, валидируется детерминированным слоем (validation, не генерация). |

---

## 13. Интеграция с Roadmap (0 → 8)

### 13.1. Обновлённый roadmap

```
STAGE 0  Foundation Freeze
         │
         ▼
STAGE 1  Causal Spine (ADR-O-201)
         │
         ▼
STAGE 2  Living NPC Kernel (commit 6ed3310 — ActionCommitment, Arbiter, Registry, NpcTickPipeline)
         │
         ▼
★ STAGE 2.5  Temporal Causality + Predictive Runtime  ◄── THIS TZ
         │
         ▼
STAGE 3  Tavern Life
         │
         ▼
STAGE 4  Spatial + Social Availability
         │
         ▼
STAGE 5  NPC ↔ NPC Society
         │
         ▼
STAGE 6  Perception
         │
         ▼
STAGE 7  Epistemic Propagation
         │
         ▼
STAGE 8  Motivation + Commitment / Replanning
```

### 13.2. Зависимости Stage 2.5 → другие стадии

| Stage | Зависимость от Stage 2.5 |
|---|---|
| **Stage 3 (Tavern Life)** | Должен использовать `expected_outcome` для описания рутин (кулинария, уборка) вместо hardcoded durations. |
| **Stage 4 (Spatial + Social Availability)** | Использует `CommitmentArbiter.INTERRUPT` для прерывания на social events (SOCIAL_FORCE_HIGH). |
| **Stage 5 (NPC ↔ NPC Society)** | NPC могут читать `commitment_registry.get_active(other_npc_id)` для моделирования намерений других NPC. |
| **Stage 6 (Perception)** | `OutcomeObserver` зависит от perception для корректного `actual_outcome`. |
| **Stage 7 (Epistemic Propagation)** | `prediction_error` становится источником epistemic update (асимметричная травма x6 уже работает для обычных TraitDriftEvent). |
| **Stage 8 (Motivation + Commitment / Replanning)** | **НЕ создаёт commitment с нуля.** Поднимает уже существующий `ActionCommitment` до когнитивной роли. Commitment становится мостом между решением и будущим. Replan trigger (M5) переходит в полноценную функцию Stage 8. |

### 13.3. Архитектурная петля (финальная, post-Stage 8)

```
┌────────────────────────────────────────────────────────────────┐
│                                                                │
│      CURRENT WORLD  ──────────────►  PREDICTED FUTURE           │
│           │                                   ▲                │
│           ▼                                   │                │
│       PERCEPTION                              │                │
│           │                                   │                │
│           ▼                                   │                │
│         BELIEFS                               │                │
│           │                                   │                │
│           ▼                                   │                │
│          NEEDS                                │                │
│           │                                   │                │
│           ▼                                   │                │
│        DECISION  ────────────►  COMMITMENT ───┘                │
│           │                          │                         │
│           ▼                          ▼                         │
│       EXECUTION  ◄──────────────────  EXPECTED OUTCOME          │
│           │                                                    │
│           ▼                                                    │
│      ACTUAL OUTCOME                                            │
│           │                                                    │
│           ▼                                                    │
│      PREDICTION ERROR  ─────►  L1CHRONICLE  ─────►  PATTERN     │
│                                                        │       │
│                                                        ▼       │
│                                              UPDATED BELIEFS    │
│                                                        │       │
│                                                        ▼       │
│                                              UPDATED WORLD  ───┘
└────────────────────────────────────────────────────────────────┘
```

Это момент, когда ENIGMA перестаёт быть пошаговым автоматом реакций и начинает моделировать существ, живущих во времени.

---

## 14. Observability (минимальный набор)

Stage 2.5 вводит следующие observability-сигналы (только чтение, без причинности):

| Сигнал | Источник | Формат | Назначение |
|---|---|---|---|
| `[PREDICTION]` log | `PredictionEngine.predict()` | `npc_id, action, eta_ticks, predicted_by, predicted_probability` | A/B-замер покрытия предсказаний. |
| `[OUTCOME_OBSERVER]` log | `OutcomeObserver.observe()` | `commitment_id, normalized_error, status_match, delta_error` | Распределение ошибки предсказания. |
| `[ARBITER_INTERRUPT]` log | `CommitmentArbiter` (new verdict) | `npc_id, incumbent_id, candidate_target, reason` | Anti-flap telemetry. |
| `prediction_error_distribution` report | L1Chronicle aggregation | гистограмма по action типам | Калибровка эвристик. |
| `commitment_lifecycle_stats` report | `commitment_registry` | terminal status → count, mean duration, mean normalized_error | Health-check системы. |

Все observability-сигналы подчиняются §11 Устава: **наблюдение не создаёт причинность**. Они не должны влиять на determinism или game outcome.

---

## 15. Ссылки

### 15.1. Внутренние документы

- `docs/АРХИТЕКТУРНЫЙ_УСТАВ_ENIGMA.md` — Устав, §3 (фазы tick), §11 (observability), §14–15 (time semantics).
- `docs/RUNTIME ARCHAEOLOGY MAP.md` — карта исполнения, три фундаментальные истины рантайма.
- `docs/ENIGMA_ROADMAP.md` — дорожная карта преемника.
- `docs/audits/ADR-O-201_Causal Kernel Architecture.md` — Causal Kernel (LAW A/B/C).
- `docs/audits/ADR-FOUNDATION-FREEZE_IMPACT.md` — Stage 0 freeze.
- `docs/audits/ADR-CAUSAL-SPINE_IMPACT.md` — Stage 1.
- `docs/audits/ADR-TZ08-8_IMPACT.md` — Stage 2 (Living NPC Kernel).
- `docs/audits/ADR-O-363` (ссылка в `commitment_arbiter.py:4`) — Commitment Arbiter.
- `architecture/temporal.yaml` — временная конфигурация (расширяется в Stage 2.5).
- `architecture/pipeline.yaml` — топология pipeline (расширяется новой Phase 5.5).

### 15.2. Ключевые файлы кода

- `backend/app/domain/action_commitment.py` — расширение полей.
- `backend/app/services/action/commitment_arbiter.py` — добавление INTERRUPT verdict.
- `backend/app/services/action/commitment_registry.py` — post-terminate hook.
- `backend/app/services/npc/npc_tick_pipeline.py` — вставка Phase 5.5.
- `backend/app/services/npc/prediction_engine.py` — NEW.
- `backend/app/services/npc/outcome_observer.py` — NEW.
- `backend/app/services/npc/l1_chronicle.py` — расширение event_type.
- `backend/app/services/tick_orchestrator.py` — без структурных изменений, только прокидывание флагов.
- `config/calibration/interrupt_thresholds.yaml` — NEW.

### 15.3. Внешние ссылки

- Commit `6ed3310` (V.0.5.3.8.7): https://github.com/4Um4/Enigma/commit/6ed3310fa38379df115e87800d13a25558c31635

---

## 16. Открытые вопросы (для архитектора)

1. **Q1.** Должен ли `PredictionEngine` поддерживать предсказание цепочки commitment'ов (multi-step plan), или только single-step? Текущее ТЗ предполагает single-step; multi-step может быть отложен до Stage 8.
2. **Q2.** Как `expected_outcome` взаимодействует с `WorldProjectionBuffer` (ADR-O-309)? Должен ли prediction-слой читать `state_t-1` через projection buffer, или напрямую из `SceneStateManager`?
3. **Q3.** Должен ли `OutcomeObserver` учитывать `WorldProjectionEvent` (derived narrative) при вычислении `actual_outcome`, или только прямые state delta?
4. **Q4.** Политика `INTERRUPT_THRESHOLD` — scalar или вектор по типам действий? Например, `INTERRUPT_THRESHOLD_MOVE=3`, `INTERRUPT_THRESHOLD_TALK=1` (разговоры легче прервать).
5. **Q5.** Должен ли `prediction_error` влиять на `CrystallizedBelief` о себе (NPC «учится» своей неточности), или только о внешних источниках?
6. **Q6.** Должен ли `expected_outcome` сохраняться в SQLite для replay, или достаточно in-memory (как `active_commitments`)?

Эти вопросы должны быть решены архитектором до реализации M2.

---

# ЧАСТЬ II · WORLD / EMBODIMENT FOUNDATION (W-TRACK)

Часть II расширяет Stage 2.5 контрактами, которые делают ENIGMA фундаментом физически воплощённого мира. Цель — не production-контент (модели, текстуры, анимации), а **архитектурные интерфейсы и proof-of-concept**, доказывающие инвариант:

> Новый NPC, новый возраст, новый шрам, потерянная конечность, болезнь, новая одежда, перенос стула, открытие двери или совершенно новый renderer не должны требовать переписывания мозга NPC. Они должны изменять World/Embodied State, из которого разные presentation backends независимо строят своё изображение.

Часть II разбита на подэтапы **W0–W9**. Из них **W0–W4 — обязательны для Stage 2.5** (семантика мира + embodied execution). **W5–W9 — формализуются как интерфейсы и minimal proof-of-concept**; полная реализация откладывается до стабилизации temporal/predictive runtime (Часть I).

---

## 17. Четырёхуровневая архитектура (главный принцип Части II)

```
WORLD / SIMULATION
        ↓
EMBODIED STATE
        ↓
PRESENTATION STATE
        ↓
RENDERING
```

| Уровень | Отвечает за | Не отвечает за |
|---|---|---|
| **WORLD / SIMULATION** | что существует; где находится; что с ним произошло; что оно может делать; что NPC может делать с ним; причинные последствия; физиологические изменения; возраст; здоровье; отношения; владение; spatial topology | sprite, animation, mesh |
| **EMBODIED STATE** | позу; локомоцию; хват; перенос; attachment; posture; доступность конечностей; физические ограничения; interaction pose; движение; физическое состояние тела; возможность выполнить конкретное действие | mesh deformation, sprite frame |
| **PRESENTATION STATE** | facing; animation state; visual variant; clothing; body morphology; visible injuries; visible disease symptoms; hair; skin; equipment; temporary appearance; selected RepresentationMode; LOD | pixel/texel output |
| **RENDERING** | sprite; billboard; impostor; 3D mesh; skeleton; material; texture; lighting; animation playback; camera; batching; LOD; GPU budget | истину о мире |

**Контракт:** Renderer НЕ является источником истины о мире. Любое значение, которое читается из renderer для принятия решения в симуляции, классифицируется как `Architectural Violation`.

### 17.1. Целевая архитектура (итоговая диаграмма)

```
                    ENIGMA WORLD
                         │
                  WorldSnapshot
                         │
          ┌──────────────┴──────────────┐
          ↓                             ↓
    WORLD SEMANTICS              EMBODIED STATE
          │                             │
    location/state                body/capability
    affordances                   posture
    ownership                     attachment
    relationships                 mobility
    causality                     injury
          │                        disease
          │                        aging
          └──────────────┬──────────────┘
                         ↓
                 PRESENTATION STATE
                         │
              VisualGenome
              morphology
              clothing
              equipment
              visible injuries
              animation state
                         │
          ┌──────────────┼──────────────┐
          ↓              ↓              ↓
        SPRITE        IMPOSTOR         3D
          │              │              │
          └──────────────┼──────────────┘
                         ↓
                      RENDERER
```

### 17.2. Отношение к существующей кодовой базе

| Существующий компонент | Уровень (по 4-уровневой модели) | Статус |
|---|---|---|
| `backend/app/domain/body.py` — `BodyTopology`, `BodySlot`, `Item`, `EncumbranceLevel` | EMBODIED + WORLD | Существует, требует расширения до полного Embodied State. |
| `backend/app/domain/vital_state.py` — `LifeStatus`, `evaluate_vital_state` | EMBODIED (тело) | Существует, переходный слой. Stage 2.5 формализует в BodyState. |
| `backend/app/domain/presentation.py` — `NPCVisualState`, `VisualDTO`, `AudibleDTO`, `PoseOverlay` | PRESENTATION | Существует, требует расширения до `VisualBodyState` + `VisualGenome`. |
| `backend/app/services/body/body_topology_service.py` | EMBODIED | Существует, читает `architecture/body_topology.yaml`. |
| `backend/app/services/spatial/world_topology_provider.py` — `WorldTopologyProvider`, `DynamicAffordanceField` | WORLD | Существует, частично покрывает W1/W2. |
| `backend/app/services/combat/injury_processor.py` — `InjuryProcessor` | EMBODIED | Существует, переходный слой «свойства вместо флагов». Stage 2.5 формализует в Injury → Body → Capability chain. |
| `backend/app/models/physical.py` — `PhysicalOutcome`, `WoundSeverity`, `DamageType` | WORLD (combat events) | Существует. |
| `frontend/presentation_firewall.py` | PRESENTATION → RENDERING bridge | Существует, ключевой guard. |
| `frontend/visual_casting_repository.py` | RENDERING | Существует, текущий 2D sprite pipeline. |
| `architecture/body_topology.yaml` | EMBODIED config | Существует, требует расширения до universal attachment system. |
| `docs/Почти Актуальные TZ/VZ/TEXTURES_AND_GEOMETRY_TZ.md` | RENDERING (Phase 3) | Существует, какTZ уже декларирует слоистую систему текстур. Stage 2.5 делает его renderer-agnostic. |

### 17.3. Gap inventory (что отсутствует)

1. **GW1.** Нет Object State Machine. Объекты мира (двери, стулья, контейнеры) не имеют формализованного FSM состояния. Сейчас sprite frame выступает фактическим состоянием.
2. **GW2.** Нет контракта переноса предметов (`HELD_BY`, `ATTACHED_TO`, `LOCATED_AT`, `SUPPORTED_BY`, `CONTAINED_BY`, `OCCUPIED_BY`, `USED_BY`).
3. **GW3.** Semantic Action не отделён от Embodied Execution. `OPEN(door)` сейчас материализуется сразу в traversal/animation, без звена preconditions → world state transition.
4. **GW4.** `BodyState` NPC не формализован как непрерывный (age, development, morphology). Существующий `BodyTopology` — для инвентаря, не для физиологии.
5. **GW5.** Injury → Body → Capability → Visual chain не замкнут. `injury_processor.py` генерирует physiological effects, но не обновляет `Functional Capability` и не пробрасывает в Presentation State.
6. **GW6.** Нет Disease / Condition Model как семантического состояния.
7. **GW7.** Нет `VisualGenome` — детерминированного описания визуальных признаков.
8. **GW8.** Нет `RepresentationMode` enum и runtime-safe переключения.
9. **GW9.** Нет formal LOD/Impostor/Asset Streaming policy.
10. **GW10.** Нет formal VRAM/RAM/CPU budget как acceptance constraint.
11. **GW11.** Нет formal Texture Policy (resolution = screen-space information density).
12. **GW12.** Нет `Interaction Point` контракта для мебели и объектов.
13. **GW13.** Процедурная генерация NPC отсутствует. Каждый NPC требует ручных ассетов.
14. **GW14.** Нет тестов: 1000-NPC generation, Aging test, Injury test, Transfer test, Renderer Independence test.

---

## 18. Аудит существующих hard couplings

Перед реализацией W-track архитектор **ОБЯЗАН** провести аудит и классифицировать все существующие жёсткие связи между simulation и presentation.

### 18.1. Что искать

Архитектор должен провести `rg`-поиск по паттернам:

| Паттерн | Что означает | Пример |
|---|---|---|
| `if age > X: model = ...` | Age → model coupling | Дискретная смена модели по возрасту |
| `if injured: sprite = ...` | Injury → sprite coupling | Sprite-вариант вместо injury state |
| `if carrying: animation = ...` | Carry → animation coupling | Animation как источник state |
| `if door_open: sprite = ...` | Object state → sprite coupling | Sprite frame = object state |
| `sprite_id` как поле NPCState | NPC state включает sprite id | Identity смешана с renderer |
| `model_id` как поле NPCState | NPC state включает model id | Identity смешана с renderer |
| `animation_clip` как поле Commitment | Commitment знает animation | Semantic Action нарушен |
| Прямой импорт `pygame` или rendering lib из `backend/app/` | Domain layer зависит от renderer | Нарушение изоляции |

### 18.2. Классификация найденных couplings

Каждое найденное coupling классифицируется в одну из пяти категорий:

| Категория | Описание | Действие |
|---|---|---|
| **Simulation coupling** | Логика симуляции прямо зависит от renderer (например, sprite frame используется как state). | Архитектурное нарушение. Должно быть устранено или обернуто в adapter в Stage 2.5. |
| **Presentation coupling** | Presentation слой знает слишком много о world state (например, sprite-вариант injury требует знания типа раны). | Архитектурное нарушение. Presentation должен получать параметризованное `VisibleInjury` описание. |
| **Legacy coupling** | Существующий код, использующий устаревший паттерн (например, `hp <= 0: dead = True`). | Не обязательно немедленно переписывать. Должно быть помечено `# LEGACY_COUPLED: see W-track` и иметь explicit migration plan. |
| **Acceptable adapter** | Существующий bridge между слоями, который корректно изолирует (например, `presentation_firewall.py`). | Сохранить. |
| **Architectural violation** | Прямое нарушение 4-уровневой модели (например, backend import pygame, или NPCState содержит sprite_id). | Должно быть устранено в Stage 2.5. |

### 18.3. Deliverable аудита

Отдельный документ (или приложение к этому ТЗ): `AUDIT_W_TRACK_COUPLINGS.md` с таблицей:

| Файл:строка | Паттерн | Категория | Migration plan |
|---|---|---|---|

Этот документ — **обязательный deliverable** Stage 2.5 (см. DoD пункт 25).

---

## 19. W0 — Semantic World (минимальный контракт)

W0 фиксирует, что мир состоит из **семантических объектов**, а не из sprites или meshes.

### 19.1. Базовая онтология объекта

```python
# backend/app/domain/world_object.py (NEW)

class WorldObjectState(str, Enum):
    """Базовые состояния объекта. Подклассы расширяют своими FSM."""
    INTACT = "INTACT"
    DAMAGED = "DAMAGED"
    BROKEN = "BROKEN"
    DESTROYED = "DESTROYED"

@dataclass(frozen=True)
class WorldObject:
    """Семантический объект мира. Существует независимо от renderer."""
    object_id: str                        # детерминированный id (см. W6 VisualGenome)
    archetype: str                        # "door", "chair", "container", "table", "bed", ...
    location_id: str                      # текущая локация
    position: Tuple[float, float]         # текущая позиция (мир, не пиксели)
    state: str                            # специфичный для archetype FSM (см. W3)
    topology_relations: Tuple[str, ...]   # связи с другими объектами (см. W1)
    affordances: Tuple[str, ...]          # доступные действия в текущем state
    ownership: Optional[str] = None       # npc_id владельца (если есть)
    containment: Tuple[str, ...] = ()     # object_id содержимых (если container)
    occupancy: Optional[str] = None       # npc_id, занимающий объект (если chair/bed)
    holder: Optional[str] = None          # npc_id, переносящий объект (если CARRIED)
    damage: float = 0.0                   # 0.0–1.0 (или физические единицы)
    interaction_history_ref: Optional[str] = None  # ref в L1Chronicle
```

### 19.2. Контракт `affordances`

`affordances` — производная от `archetype + state + holder + occupancy + damage`. Например:

| Archetype | state | holder | occupancy | affordances |
|---|---|---|---|---|
| `door` | `CLOSED` | None | None | `[OPEN, KNOCK, LOCK, UNLOCK, BREAK]` |
| `door` | `OPEN` | None | None | `[CLOSE, PASS_THROUGH, LOCK]` |
| `door` | `LOCKED` | None | None | `[UNLOCK, BREAK, KNOCK]` |
| `door` | `BROKEN` | None | None | `[REPAIR, PASS_THROUGH]` |
| `chair` | `AVAILABLE` | None | None | `[SIT, TAKE, MOVE, KICK]` |
| `chair` | `OCCUPIED` | None | NPC_17 | `[STAND_UP(for NPC_17), KICK]` |
| `chair` | `HELD` | NPC_17 | None | `[PLACE, DROP, THROW]` |
| `chair` | `BROKEN` | None | None | `[REPAIR, DISCARD]` |
| `container` | `CLOSED` | None | None | `[OPEN, LOCK, UNLOCK, BREAK]` |
| `container` | `OPEN` | None | None | `[CLOSE, INSERT_ITEM, REMOVE_ITEM]` |

Affordance вычисляется pure function `compute_affordances(object: WorldObject, body_state: BodyState) -> Tuple[str, ...]`. Это уже частично реализовано в `DynamicAffordanceField` (S91), но на уровне зон, не объектов. Stage 2.5 поднимает это до уровня объектов.

### 19.3. Migration от sprite к семантике

Запрещённая архитектура:

```python
# WRONG
door_sprite_id = "door_open"
if door_sprite_id == "door_open":
    npc_can_pass = True
```

Должно быть:

```python
# RIGHT
door = WorldObjectRegistry.get(door_id)
if door.state == "OPEN":
    npc_can_pass = True
# Renderer отдельно читает presentation.animation = "OPENING" / "OPEN"
```

---

## 20. W1 — Spatial Topology

W1 формализует пространственные отношения между объектами.

### 20.1. Существующее состояние

`backend/app/services/spatial/world_topology_provider.py` уже предоставляет `WorldTopologyProvider` как фасад над `SpatialService` + `DynamicAffordanceField`. `DynamicAffordanceField` хранит стигмергические деформации (hard overrides + soft traces). `architecture/spatial.yaml` фиксирует spatial contract.

### 20.2. Расширение W1

Stage 2.5 расширяет `WorldTopologyProvider` до поддержки **объектных отношений**, а не только зональных:

```python
# backend/app/services/spatial/world_topology_provider.py (EXTENSION)

class WorldTopologyProvider:
    # existing methods...

    def query_object_relations(
        self, object_id: str
    ) -> Tuple[ObjectRelation, ...]:
        """Возвращает все пространственные отношения объекта.
        Включая support, attachment, containment, occupancy."""
        ...

    def query_objects_at(
        self, location_id: str, position: Tuple[float, float], radius: float = 0.0
    ) -> Tuple[str, ...]:
        """Возвращает object_id всех объектов в точке/радиусе."""
        ...
```

### 20.3. Минимальные отношения

| Отношение | Семантика | Пример |
|---|---|---|
| `LOCATED_AT(location, position)` | Объект находится в локации в координатах. | Chair в tavern_main_room, (5.2, 3.1). |
| `SUPPORTED_BY(supporter_id)` | Объект лежит на другом объекте. | Bowl on Table. |
| `CONTAINED_BY(container_id)` | Объект внутри контейнера. | Coin in Chest. |
| `OCCUPIED_BY(npc_id)` | Объект занят NPC (стул, кровать). | Chair occupied by NPC_17. |
| `HELD_BY(npc_id)` | Объект переносится NPC. | Chair held by NPC_17. |
| `ATTACHED_TO(host_id, slot)` | Объект прикреплён к другому (меч на поясе). | Sword attached to NPC_17.waist_sheath. |
| `USED_BY(npc_id)` | Объект используется NPC (tool in hand). | Hammer used by NPC_17.hand.R. |

### 20.4. Инвариант W1

Любое пространственное перемещение объекта проходит через одну из этих семи операций. Прямая мутация `object.position` без обновления отношений — `OntologyViolationError`.

---

## 21. W2 — Affordances / Interaction

W2 формализует, какие действия мир позволяет выполнить с объектом.

### 21.1. Affordance resolution

```python
# backend/app/services/world/affordance_resolver.py (NEW)

class AffordanceResolver:
    """Pure function: (object_state, npc_body_state) -> available_actions."""

    @staticmethod
    def resolve(
        obj: WorldObject,
        npc_body_state: "BodyState",
        npc_position: Tuple[float, float],
    ) -> Tuple[SemanticAction, ...]:
        """Возвращает семантические действия, доступные NPC
        с данным body state над объектом в данном состоянии."""
        ...
        # Пример: chair in AVAILABLE state, NPC has 2 functional hands
        #         → (SIT, TAKE, MOVE)
        # Пример: chair in AVAILABLE state, NPC has 0 functional hands
        #         → (SIT) — TAKE требует CAN_GRIP_LARGE_OBJECT
```

### 21.2. Precondition контракт

Каждое Semantic Action имеет явные preconditions:

```python
# backend/app/domain/semantic_action.py (NEW)

@dataclass(frozen=True)
class SemanticAction:
    action_type: str            # OPEN, TAKE, CARRY, PLACE, SIT, ...
    target_object_id: Optional[str] = None
    target_location_id: Optional[str] = None
    target_attachment_slot: Optional[str] = None
    preconditions: Tuple[Precondition, ...] = ()

@dataclass(frozen=True)
class Precondition:
    """Pure predicate over (world_state, npc_body_state)."""
    predicate: str             # "CAN_GRIP_LARGE_OBJECT", "IS_ADJACENT_TO", "STATE_IS"
    args: Tuple[Any, ...]
```

### 21.3. Примеры precondition contract

| Action | Preconditions |
|---|---|
| `OPEN(door)` | `STATE_IS(door, CLOSED)`, `IS_ADJACENT_TO(npc, door.handle_point)`, `CAN_GRIP_SMALL_OBJECT(npc)`, `NOT_LOCKED(door)` |
| `TAKE(chair)` | `STATE_IS(chair, AVAILABLE)`, `IS_ADJACENT_TO(npc, chair)`, `CAN_GRIP_LARGE_OBJECT(npc)`, `ENCUMBRANCE_OK(npc, chair.weight)` |
| `CARRY(chair)` | `STATE_IS(chair, HELD_BY=npc)`, `CAN_GRIP_LARGE_OBJECT(npc)`, `ENCUMBRANCE_OK(npc, chair.weight)` |
| `PLACE(chair, target)` | `STATE_IS(chair, HELD_BY=npc)`, `IS_VALID_PLACEMENT(target, chair)`, `CAN_GRIP_LARGE_OBJECT(npc)` |
| `SIT(chair)` | `STATE_IS(chair, AVAILABLE)`, `IS_ADJACENT_TO(npc, chair.sit_point)`, `CAN_BEND(npc)` |
| `EQUIP(sword, slot=waist_sheath)` | `IS_IN_INVENTORY(npc, sword)`, `SLOT_FREE(npc, waist_sheath)`, `CAN_GRIP_SMALL_OBJECT(npc)` |
| `ATTACK(target)` | `IS_IN_RANGE(npc, target)`, `HAS_FUNCTIONAL_LIMB(npc, attacking_limb)` |

Precondition выполняется pure function; он **не** вызывает LLM, не делает IO, не мутирует state.

---

## 22. W3 — Object State Machine

W3 формализует FSM состояний для каждого archetype объекта.

### 22.1. Базовые FSM (минимальный набор)

```python
# backend/app/domain/object_fsms.py (NEW)

# Дверь
DOOR_STATES = ("CLOSED", "OPEN", "LOCKED", "BROKEN")
DOOR_TRANSITIONS = {
    "CLOSED": {"OPEN", "LOCKED", "BROKEN"},
    "OPEN":   {"CLOSED"},
    "LOCKED": {"CLOSED", "BROKEN"},     # UNLOCK returns to CLOSED
    "BROKEN": {"OPEN", "CLOSED"},        # REPAIR
}

# Стул
CHAIR_STATES = ("AVAILABLE", "OCCUPIED", "HELD", "MOVED", "BROKEN")
CHAIR_TRANSITIONS = {
    "AVAILABLE": {"OCCUPIED", "HELD", "MOVED", "BROKEN"},
    "OCCUPIED":  {"AVAILABLE"},          # STAND_UP
    "HELD":      {"AVAILABLE", "MOVED", "BROKEN"},  # PLACE / DROP / THROW
    "MOVED":     {"AVAILABLE", "BROKEN"},
    "BROKEN":    {"AVAILABLE"},          # REPAIR
}

# Контейнер
CONTAINER_STATES = ("CLOSED", "OPEN", "LOCKED", "DESTROYED")
CONTAINER_TRANSITIONS = {
    "CLOSED":   {"OPEN", "LOCKED", "DESTROYED"},
    "OPEN":     {"CLOSED"},
    "LOCKED":   {"CLOSED", "DESTROYED"},
    "DESTROYED": set(),                   # terminal
}

# Кровать
BED_STATES = ("FREE", "OCCUPIED")
BED_TRANSITIONS = {
    "FREE":     {"OCCUPIED"},
    "OCCUPIED": {"FREE"},
}
```

### 22.2. Generic transition validator

```python
def transition_object(
    obj: WorldObject,
    new_state: str,
    tick: int,
    cause: str,
) -> bool:
    """Универсальный FSM-переход. False = запрещён."""
    fsm = OBJECT_FSMS.get(obj.archetype)
    if fsm is None:
        return False  # unknown archetype — no transition
    allowed = fsm.get(obj.state, set())
    if new_state not in allowed:
        return False
    obj = replace(obj, state=new_state)
    # ... publish to L1Chronicle / commit_history ...
    return True
```

### 22.3. Базовый инвариант W3

> `door_sprite = open` **никогда** не является фактическим состоянием мира.
> `Door.state = OPEN` — это состояние мира.
> `presentation.animation = OPENING` — это проекция в Presentation State.

---

## 23. W4 — Embodied State

W4 формализует состояние тела NPC отдельно от World State.

### 23.1. `BodyState` (новый доменный объект)

```python
# backend/app/domain/body_state.py (NEW, расширяет существующий body.py)

@dataclass(frozen=True)
class BodyState:
    """Непрерывное состояние тела NPC. Не переключается между моделями."""

    # ── Возраст (непрерывный, НЕ дискретный) ──────────────────────
    age_years: float                     # 17.43, не "child" / "adult" / "elder"
    developmental_stage: float           # 0.0 (newborn) ... 1.0 (full adult) ... 1.2 (elder)

    # ── Морфология ────────────────────────────────────────────────
    stature: float                       # meters
    body_mass: float                     # kg
    proportions: Dict[str, float]        # limb ratios, head_ratio, shoulder_width, etc.

    # ── Состояние конечностей и систем ───────────────────────────
    limb_state: Dict[str, LimbState]     # "hand.L", "hand.R", "foot.L", "foot.R", "head", ...
    sensory_state: SensoryState          # vision, hearing, smell acuity
    posture: Posture                     # STANDING, SITTING, CROUCHING, LYING, BENT
    mobility: MobilityProfile            # max_speed, acceleration, turn_rate

    # ── Травмы и условия ──────────────────────────────────────────
    wounds: Tuple[Wound, ...]            # активные раны
    chronic_changes: Tuple[ChronicChange, ...]   # ампутации, шрамы, перманентные изменения
    acute_conditions: Tuple[Condition, ...]      # болезнь, отравление, infection

    # ── Функциональные возможности (вычисляются, не хранятся) ────
    # functional_capabilities: see W4 §23.3 — computed property

    @property
    def functional_capabilities(self) -> "FunctionalCapabilitySet":
        """PURE function: body_state → capabilities. Не persisted."""
        return CapabilityEvaluator.evaluate(self)
```

### 23.2. `LimbState`

```python
@dataclass(frozen=True)
class LimbState:
    body_part: str                       # "hand.L", "foot.R", etc.
    functional: bool                     # может выполнять базовые действия
    integrity: float                      # 0.0 (ампутирован) ... 1.0 (intact)
    pain_level: float                     # 0.0 ... 1.0
    motor_control: float                  # 0.0 (паралич) ... 1.0 (full control)
    dexterity: float                      # 0.0 (нет) ... 1.0 (full)
    grip_strength: float                  # 0.0 ... 1.0
    # ... остальные параметры ...
```

### 23.3. Functional Capability — вычисляемое, не сохраняемое

```python
# backend/app/services/body/capability_evaluator.py (NEW)

class CapabilityEvaluator:
    """Pure function: BodyState → FunctionalCapabilitySet.

    НЕ использует LLM. НЕ делает IO. НЕ мутирует state.
    Только детерминированные правила."""

    @staticmethod
    def evaluate(body: BodyState) -> "FunctionalCapabilitySet":
        caps = set()

        # Grip capabilities
        left_hand = body.limb_state.get("hand.L")
        right_hand = body.limb_state.get("hand.R")

        if left_hand and left_hand.grip_strength > 0.5:
            caps.add(FunctionalCapability.CAN_GRIP_SMALL_OBJECT)
        if right_hand and right_hand.grip_strength > 0.5:
            caps.add(FunctionalCapability.CAN_GRIP_SMALL_OBJECT)
        if ((left_hand and left_hand.grip_strength > 0.7) and
            (right_hand and right_hand.grip_strength > 0.7)):
            caps.add(FunctionalCapability.CAN_GRIP_LARGE_OBJECT)
            caps.add(FunctionalCapability.CAN_USE_TOOL)

        # Mobility
        if body.mobility.max_speed > 0.5:
            caps.add(FunctionalCapability.CAN_WALK)
        if body.mobility.max_speed > 3.0:
            caps.add(FunctionalCapability.CAN_RUN)

        # Sensory
        if body.sensory_state.vision > 0.3:
            caps.add(FunctionalCapability.CAN_SEE)
        if body.sensory_state.hearing > 0.3:
            caps.add(FunctionalCapability.CAN_HEAR)

        # Latch / Fine motor
        if ((left_hand and left_hand.dexterity > 0.7) or
            (right_hand and right_hand.dexterity > 0.7)):
            caps.add(FunctionalCapability.CAN_OPEN_LATCH)

        # ... другие правила ...

        return FunctionalCapabilitySet(frozenset(caps))


class FunctionalCapability(str, Enum):
    CAN_GRIP_SMALL_OBJECT = "CAN_GRIP_SMALL_OBJECT"
    CAN_GRIP_LARGE_OBJECT = "CAN_GRIP_LARGE_OBJECT"
    CAN_USE_TOOL = "CAN_USE_TOOL"
    CAN_OPEN_LATCH = "CAN_OPEN_LATCH"
    CAN_WALK = "CAN_WALK"
    CAN_RUN = "CAN_RUN"
    CAN_SEE = "CAN_SEE"
    CAN_HEAR = "CAN_HEAR"
    CAN_SWIM = "CAN_SWIM"
    CAN_CLIMB = "CAN_CLIMB"
    CAN_SPEAK = "CAN_SPEAK"
    # ...
```

### 23.4. Интеграция с CommitmentArbiter (Часть I)

`CommitmentArbiter.arbitrate()` (см. §6.4 Части I) теперь должен также проверять:

```python
# Расширение arbiter
incumbent_capabilities = CapabilityEvaluator.evaluate(npc.body_state)
if not action.preconditions_met(incumbent_capabilities):
    return ArbitrationResult(
        verdict=VERDICT_REJECT,
        reason="CAPABILITY_MISSING",
        ...
    )
```

Это замыкает loop: **тело определяет, что NPC может сделать; мир определяет, что доступно; arbiter их совмещает**.

---

## 24. W5 — Body / Aging / Injury / Disease (interfaces, proof-of-concept)

W5 — формализация интерфейсов. Полная реализация откладывается.

### 24.1. Continuous Aging

```python
# backend/app/services/body/aging_engine.py (NEW, minimal)

class AgingEngine:
    """Pure function: BodyState(t) → BodyState(t+Δ).

    НЕ переключает между child/adult/elder моделями.
    Изменяет непрерывные параметры."""

    @staticmethod
    def age(body: BodyState, delta_game_seconds: float) -> BodyState:
        """Обновляет возраст и производные параметры за delta_game_seconds."""
        years_passed = delta_game_seconds / (60 * 60 * 24 * 365)  # sec → years
        new_age = body.age_years + years_passed

        # Developmental stage — непрерывная функция
        new_dev = _developmental_curve(new_age, body.genetics)

        # Stature / body mass — медленный дрейф
        new_stature = _stature_curve(new_age, body.genetics)
        new_mass = _mass_curve(new_age, body.genetics, body.nutrition_history)

        return replace(body,
            age_years=new_age,
            developmental_stage=new_dev,
            stature=new_stature,
            body_mass=new_mass,
        )
```

**Запрет (W5-Aging-1):** Дискретная конструкция `if age >= 18: body = AdultBody()` **запрещена** в симуляции. Допускается в renderer как optimization (выбор sprite/mesh по диапазону age), но не как source of truth.

### 24.2. Injury → Body → Capability → Visual chain

```python
# Полная причинная цепочка (контракт, не реализация)

# 1. Event
combat_event = CombatEvent(attacker=..., target=..., damage_type=SLASHING, zone="hand.R", ...)

# 2. Injury (новая рана)
injury = Injury.from_combat_event(combat_event)
# Injury: {zone, type, severity, structural_damage, bleeding_rate, ...}

# 3. Body State mutation
body = npc.body_state
new_limb = replace(body.limb_state["hand.R"],
    integrity=max(0.0, body.limb_state["hand.R"].integrity - injury.structural_damage),
    grip_strength=max(0.0, body.limb_state["hand.R"].grip_strength - injury.grip_impairment),
    pain_level=min(1.0, body.limb_state["hand.R"].pain_level + injury.pain),
)
new_body = replace(body, limb_state={**body.limb_state, "hand.R": new_limb})

# 4. Functional Capability (recomputed automatically, pure function)
new_caps = CapabilityEvaluator.evaluate(new_body)
# Теперь CAN_GRIP_SMALL_OBJECT может быть False, если right_hand.grip_strength < 0.5

# 5. Behavioral consequence
# DecisionHub видит: fewer affordances available (см. W2)
# → NPC выбирает другие действия (использует левую руку, просит помощи, etc.)

# 6. Visual consequence (проекция в Presentation State, отдельный шаг)
visual_state = PresentationProjector.project(new_body, npc.visual_genome)
# VisibleInjury: {zone: "hand.R", type: "slash", severity: 0.7, blood_amount: 0.4}
# Renderer решает: рисовать blood overlay, blood drip animation, или 3D wound mesh
```

**Запрет (W5-Injury-1):** `injury_sprite = True` как состояние мира — запрещено. `injury` должен быть объектом с `zone`, `type`, `severity`, `structural_damage`. Renderer отдельно решает, как это показать.

### 24.3. Disease / Condition Model

```python
# backend/app/domain/condition.py (NEW, minimal)

@dataclass(frozen=True)
class Condition:
    """Болезнь/состояние NPC. Семантическое, не визуальное."""
    condition_id: str                    # "flu", "infection", "poisoning", "exhaustion"
    onset_tick: int
    severity: float                       # 0.0 (subclinical) ... 1.0 (critical)
    duration_ticks: Optional[int]         # None = chronic
    physiological_effects: Dict[str, float]  # {mobility: -0.2, stamina: -0.3, cognition: -0.1, ...}
    functional_effects: Tuple[FunctionalEffect, ...]
    transmission_vector: Optional[str] = None  # "airborne", "contact", "fluid"
    contagious: bool = False

@dataclass(frozen=True)
class FunctionalEffect:
    capability: FunctionalCapability
    modifier: float                       # multiplier, e.g. 0.7 (30% impairment)
```

**Принцип (W5-Disease-1):** Один и тот же `Condition` существует без renderer, с 2D renderer, с 2.5D renderer, с 3D renderer. Renderer только читает `visible_symptoms` из Presentation State.

---

## 25. W6 — Visual Genome / Procedural Identity

W6 формализует детерминированное описание визуальных признаков.

### 25.1. `VisualGenome`

```python
# backend/app/domain/visual_genome.py (NEW)

@dataclass(frozen=True)
class VisualGenome:
    """Детерминированное описание визуальных признаков NPC.

    Seed-stable: один и тот же (npc_id, world_seed) → одна и та же VisualGenome.
    Используется для save/load, replay, population generation, offspring."""

    genome_seed: str                     # md5(npc_id + world_seed)

    # ── Базовая морфология ────────────────────────────────────────
    body_proportions: Dict[str, float]   # head_ratio, shoulder_width, hip_width, limb_ratio, ...
    sex: str                             # "male" / "female" / "other"
    ethnicity_params: Dict[str, float]   # skin tone, hair texture, facial structure

    # ── Face ──────────────────────────────────────────────────────
    face_parameters: Dict[str, float]    # eye_distance, nose_width, lip_thickness, jaw_angle, ...

    # ── Hair ──────────────────────────────────────────────────────
    hair_params: Dict[str, float]        # color, length, style_seed, density, ...

    # ── Skin ───────────────────────────────────────────────────────
    skin_params: Dict[str, float]        # tone, texture, freckles, ...

    # ── Возрастная морфология ─────────────────────────────────────
    age_morphology_curve: Dict[float, Dict[str, float]]   # age → morphology deltas

    # ── Унаследованные признаки (genotype) ────────────────────────
    inherited_traits: Dict[str, float]   # genetics — не phenotype

    # ── Шрамы и асимметрия ────────────────────────────────────────
    scars: Tuple[ScarSpec, ...]          # genetic / developmental scars (НЕ combat)
    asymmetry: Dict[str, float]          # natural asymmetry parameters

    # ── Clothing preferences ──────────────────────────────────────
    clothing_preferences: Dict[str, float]  # style preferences, color preferences, ...

    # ── Variation ────────────────────────────────────────────────
    variation_seed: int                  # для procedural variation
```

### 25.2. Deterministic appearance generation

```python
# backend/app/services/world/visual_genome_factory.py (NEW)

class VisualGenomeFactory:
    """Детерминированная генерация VisualGenome из (npc_id, world_seed).

    Использует KernelRNG-производный seed. Результат стабилен."""

    @staticmethod
    def generate(npc_id: str, world_seed: str, parents: Optional[Tuple[str, str]] = None) -> VisualGenome:
        if parents is None:
            # Procedural NPC: pure seeded generation
            seed = _derive_seed(npc_id, world_seed)
            return _generate_random_genome(seed)
        else:
            # Offspring: blend of parents' genomes
            parent_a_genome = VisualGenomeStore.get(parents[0])
            parent_b_genome = VisualGenomeStore.get(parents[1])
            return _blend_genomes(parent_a_genome, parent_b_genome,
                                  mutation_rate=0.05,
                                  world_seed=world_seed,
                                  npc_id=npc_id)
```

### 25.3. Inheritance model (genotype ≠ phenotype)

```python
# backend/app/services/world/genome_blender.py (NEW, minimal)

def _blend_genomes(
    parent_a: VisualGenome,
    parent_b: VisualGenome,
    mutation_rate: float,
    world_seed: str,
    npc_id: str,
) -> VisualGenome:
    """Смешивает геномы родителей.

    Не полноценная биологическая симуляция — простая эвристика:
    - Some traits: average (height, body proportions)
    - Some traits: choose one (eye color, hair color — Mendelian-like)
    - Some traits: random with mutation (face parameters)
    - Some traits: independent re-generation (asymmetry, scars)
    """
    rng = KernelRNG(tick=0, npc_id=npc_id, salt="genome_blend")
    blended = {}
    for key in GENOME_BLENDABLE_TRAITS:
        a_val = parent_a.body_proportions.get(key, 0.5)
        b_val = parent_b.body_proportions.get(key, 0.5)
        blend = (a_val + b_val) / 2.0
        # Mutation
        if rng.random() < mutation_rate:
            blend += rng.uniform(-0.1, 0.1)
        blended[key] = max(0.0, min(1.0, blend))
    return VisualGenome(
        genome_seed=_derive_seed(npc_id, world_seed),
        body_proportions=blended,
        # ... other fields ...
    )
```

### 25.4. Acceptance test для W6

- **AT-W6-1.** `generate(npc_id="npc_42", world_seed="alpha")` всегда возвращает идентичную `VisualGenome` (byte-equal dict).
- **AT-W6-2.** Save/load: `appearance_before == appearance_after`.
- **AT-W6-3.** Replay: тот же seed → тот же genome.
- **AT-W6-4.** 1000 NPC generation: все genomes уникальны (вероятность коллизии < 10⁻⁶).

---

## 26. W7 — Presentation State

W7 формализует параметризованное описание визуала (не mesh, не texture).

### 26.1. `VisualBodyState` (расширение существующего `NPCVisualState`)

```python
# backend/app/domain/presentation.py (EXTENSION)

@dataclass(frozen=True)
class VisualBodyState:
    """Параметризованное описание визуала NPC.
    Производная от BodyState + VisualGenome + ClothingState + EquipmentState.
    НЕ mesh. НЕ texture. НЕ animation clip."""

    # ── Базовая морфология (из VisualGenome) ─────────────────────
    base_morphology: Dict[str, float]
    age_morphology: Dict[str, float]      # текущие age-related deltas
    sex_body_shape: Dict[str, float]

    # ── Hair & Skin (проекция VisualGenome с учётом state) ───────
    hair: HairVisualState                 # color, length, current style, dirt_level, ...
    skin: SkinVisualState                 # tone, dirt, sweat, pallor (из disease), ...

    # ── Clothing & Equipment ────────────────────────────────────
    clothing: Tuple[ClothingLayer, ...]  # слои одежды (см. TEXTURES_AND_GEOMETRY_TZ §2)
    equipment: Tuple[EquipmentVisual, ...] # меч на поясе, щит за спиной, etc.

    # ── Видимые раны и болезни ────────────────────────────────────
    visible_injuries: Tuple[VisibleInjury, ...]
    visible_disease_markers: Tuple[VisibleSymptom, ...]
    missing_anatomy: Tuple[str, ...]      # ["hand.R.finger_index", "foot.L.toe_small"]

    # ── Временные модификаторы ───────────────────────────────────
    dirt: float                           # 0.0 ... 1.0
    blood_damage_state: float             # 0.0 ... 1.0
    temporary_appearance_modifiers: Tuple[AppearanceModifier, ...]  # status effects (drunk, scared, etc.)

    # ── Renderer-specific ────────────────────────────────────────
    representation_mode: RepresentationMode
    lod: int                              # 0 (highest) ... 4 (impostor)
    facing: float                         # radians
    animation_state: AnimationState       # current animation (см. W8)
```

### 26.2. `PresentationProjector` (новый сервис)

```python
# backend/app/services/presentation/presentation_projector.py (NEW)

class PresentationProjector:
    """Pure function: (BodyState, VisualGenome, ClothingState, EquipmentState) → VisualBodyState.

    Не делает IO. Не вызывает LLM. Не мутирует state."""

    @staticmethod
    def project(
        body: BodyState,
        genome: VisualGenome,
        clothing: ClothingState,
        equipment: EquipmentState,
        rep_mode: RepresentationMode,
        lod: int,
        facing: float,
        animation: AnimationState,
    ) -> VisualBodyState:
        ...
```

### 26.3. `RepresentationMode` (новый enum)

```python
class RepresentationMode(str, Enum):
    SPRITE = "SPRITE"                     # current 2D
    DIRECTIONAL_SPRITE = "DIRECTIONAL_SPRITE"
    IMPOSTOR = "IMPOSTOR"                 # billboard
    LOW_POLY_3D = "LOW_POLY_3D"
    FULL_3D = "FULL_3D"
```

### 26.4. Runtime-safe switching

```python
# NPC может сменить RepresentationMode без смены identity/state:

npc.representation_mode = RepresentationMode.IMPOSTOR  # far from camera
# ...
npc.representation_mode = RepresentationMode.FULL_3D  # close-up
# World State, BodyState, VisualGenome — НЕ ИЗМЕНИЛИСЬ
# Renderer отдельно решает, какие assets загрузить
```

### 26.5. Интеграция с существующим `presentation_firewall.py`

Существующий `frontend/presentation_firewall.py` — это guard, который уже изолирует presentation от domain. Stage 2.5 формализует его как **единственный** путь от `WorldSnapshot` к renderer. Любой другой путь — `Architectural Violation`.

---

## 27. W8 — Animation / Attachment

W8 формализует, что animation state — производная от (World + Embodied + Action + Movement + Posture).

### 27.1. Animation как производная, не как источник

```python
@dataclass(frozen=True)
class AnimationState:
    """Текущее анимационное состояние NPC. Производная, не источник."""

    primary_state: str                    # WALKING, IDLE, SITTING, OPENING, USING, ...
    secondary_states: Tuple[str, ...]     # INJURED_WALK, CARRYING, etc.
    pose_overlay: PoseOverlay             # существующий контракт из presentation.py
    gaze_arrow: Optional[GazeArrow]       # существующий контракт
    activity_badge: Optional[str]         # существующий контракт
    # Renderer отдельно выбирает clip: 2D sprite frame sequence, 3D skeletal anim, etc.
```

### 27.2. Universal Attachment System

Существующий `architecture/body_topology.yaml` уже определяет слоты: `right_hand`, `left_hand`, `belt_sheath`, `belt_pouch`, `pocket_*`, `backpack_*`, `worn_*`, `hidden_*`. Stage 2.5 расширяет это до **универсального** attachment system:

```python
# backend/app/domain/attachment_points.py (NEW)

class UniversalAttachmentPoint(str, Enum):
    """Универсальные attachment points. Renderer-agnostic."""
    HAND_L = "hand.L"
    HAND_R = "hand.R"
    HEAD = "head"
    BACK = "back"
    WAIST = "waist"
    FOOT_L = "foot.L"
    FOOT_R = "foot.R"
    BODY = "body"
    # Дополнительные специфичные:
    BELT_SHEATH = "belt.sheath"
    BACK_OVER = "back.over"               # плащ
    BACKPACK_MAIN = "backpack.main"
    SHOULDER_L = "shoulder.L"
    SHOULDER_R = "shoulder.R"
```

### 27.3. Использование attachment system

| Назначение | Attachment Point |
|---|---|
| Перенос предметов (TAKE/CARRY) | `HAND_L`, `HAND_R`, `BODY` (для больших), `BACK` (для ношения на спине) |
| Инструменты | `HAND_L`, `HAND_R` |
| Одежда | `BODY`, `BACK_OVER`, `WAIST`, `FOOT_L`, `FOOT_R` |
| Экипировка | `BELT_SHEATH`, `BACK`, `SHOULDER_L`, `SHOULDER_R` |
| Ребёнок на руках | `HAND_L` + `HAND_R` (two-handed carry) или `BODY` |
| Предметы в руках | `HAND_L`, `HAND_R` |
| Визуальные эффекты (кровь, грязь) | `BODY`, `HEAD`, `HAND_L`, `HAND_R`, `FOOT_L`, `FOOT_R` |
| Повреждённые/отсутствующие части | Тот же attachment point остаётся, но помечается `integrity=0.0` |

### 27.4. Запрет (W8-Anim-1)

> `animation_clip_id` НЕ МОЖЕТ быть полем в `WorldObject`, `Commitment`, `BodyState`, `Intent` или любом другом domain-объекте симуляции.

`AnimationState` живёт только в `VisualBodyState` (Presentation State), и его формирует `PresentationProjector` на основе World+Embodied+Action.

---

## 28. W9 — 2D / 2.5D / 3D Representation

W9 формализует, что **один WorldSnapshot** может быть отрисован любым renderer.

### 28.1. Renderer abstraction

```python
# backend/app/services/presentation/renderer_port.py (NEW)

class RendererPort(Protocol):
    """Абстракция renderer. Все renderer'ы должны реализовывать этот интерфейс."""

    def render_frame(
        self,
        world_snapshot: "WorldSnapshot",
        visual_body_states: Dict[str, VisualBodyState],
        camera: "CameraState",
        delta_time: float,
    ) -> "RenderFrame":
        """Pure projection: (world + visual states + camera) → render frame."""
        ...
```

### 28.2. Renderer Independence Test (главный acceptance критерий)

```python
# backend/tests/renderer_independence_test.py (NEW)

def test_same_world_snapshot_renderable_by_all_renderers():
    """Один и тот же WorldSnapshot должен быть отображён любым renderer
    без изменения WorldSnapshot."""

    snapshot = build_test_world_snapshot()
    visual_states = build_test_visual_body_states()

    # 2D renderer (current)
    renderer_a = SpriteRenderer()
    frame_a = renderer_a.render_frame(snapshot, visual_states, camera, dt=0.016)

    # 2.5D renderer (future)
    renderer_b = DirectionalSpriteRenderer()
    frame_b = renderer_b.render_frame(snapshot, visual_states, camera, dt=0.016)

    # 3D renderer (future)
    renderer_c = Full3DRenderer()
    frame_c = renderer_c.render_frame(snapshot, visual_states, camera, dt=0.016)

    # WorldSnapshot не изменился
    assert snapshot == build_test_world_snapshot()
    assert visual_states == build_test_visual_body_states()

    # Все три renderer'а успешно отрисовали кадр (без исключений)
    assert frame_a is not None
    assert frame_b is not None
    assert frame_c is not None
```

### 28.3. LOD / Impostor / Asset Streaming

```python
# backend/app/services/presentation/lod_policy.py (NEW)

class LODPolicy:
    """Camera-aware LOD. Определяется screen-space size + visibility + importance,
    не просто distance."""

    @staticmethod
    def determine_lod(
        npc_id: str,
        world_position: Tuple[float, float],
        camera: "CameraState",
        npc_importance: float,            # 0.0 ... 1.0 (story-relevant NPC gets higher)
    ) -> Tuple[RepresentationMode, int]:
        """Возвращает (RepresentationMode, LOD level 0..4)."""
        screen_size = camera.project_size(world_position)
        visibility = camera.compute_visibility(world_position)

        if screen_size < 0.005 or visibility < 0.1:
            return RepresentationMode.IMPOSTOR, 4
        elif screen_size < 0.02:
            return RepresentationMode.IMPOSTOR, 3
        elif screen_size < 0.05 and npc_importance < 0.5:
            return RepresentationMode.SPRITE, 2
        elif screen_size < 0.1:
            return RepresentationMode.DIRECTIONAL_SPRITE, 1
        else:
            return RepresentationMode.FULL_3D, 0
```

**Принцип (W9-LOD-1):** В изометрической/верхней камере большинство NPC никогда не должны получать high-detail rendering, потому что screen-space size остаётся малым.

---

## 29. Performance Budget (formal acceptance constraint)

| Параметр | Цель | Источник |
|---|---|---|
| **VRAM** | ≤ 1.5 GB | acceptance constraint |
| **RAM** | 16 GB baseline, 32 GB preferred | hardware profile |
| **CPU** | mid-range contemporary (4-core / 8-thread baseline) | hardware profile |
| **GPU** | 8 GB VRAM target | hardware profile |

### 29.1. Что должно быть формализовано

- Texture atlas policy (все NPC sprite'ы в одном атласе per location).
- Compression policy (ASTC/BC7 for 3D, PNG/WebP for 2D).
- Mipmap policy (для 3D, для impostor).
- Shared materials / shared textures.
- Asset streaming (загрузка по требованию, не all-in-RAM).
- Sprite atlas (один PNG для всех directional frames одного NPC).
- Impostor pre-rendering (sprite captured from 3D master, cached).

### 29.2. Texture Policy (формальный принцип)

> **Texture resolution is determined by screen-space information density, not by source asset quality.**

Запрещено: 4K/8K texture на tiny isometric object без explicit обоснования.

### 29.3. Animation Budget (формальный принцип)

Запрещено: `N NPC × full skeleton × 60 FPS` для всех NPC.

Должно поддерживать градации:

```
simulation-only
        ↓
frozen visual (NPC вне зоны интереса)
        ↓
sprite (directional, low FPS)
        ↓
impostor (billboard)
        ↓
low-poly 3D (few bones)
        ↓
full animation (full skeleton)
```

---

## 30. Simulation / Render Frequency Separation (формализация Части I §8 для renderer)

```
Simulation Tick     ≠    Animation Tick     ≠    Render Frame
```

Renderer интерполирует между simulation states. Это позволяет:
- Большому количеству NPC (дешёвая симуляция, плавное движение).
- Отсутствие необходимости вычислять cognition каждый кадр.
- Дешёвую симуляцию NPC вне зоны видимости.

Часть I §8 уже зафиксировала частоты: render 30–60 Hz, simulation 1 Hz, decision 0.05–0.1 Hz, LLM ≤ 0.01 Hz. Stage 2.5 добавляет: **renderer интерполирует**, simulation — авторитет.

---

## 31. Asset Generation Pipeline (контракт, не реализация)

```
NPC data (Identity + BodyState + VisualGenome + ClothingState + EquipmentState)
        ↓
VisualGenome (детерминированный seed)
        ↓
Body parameters (морфология)
        ↓
3D master asset / procedural body  (production-time, опционально)
        ↓
animations (production-time)
        ↓
directional renders  (production-time, опционально)
        ↓
sprite sheets / impostors  (cached, runtime-loadable)
        ↓
runtime asset
```

**Принцип:** Runtime не обязан загружать master 3D asset. 3D может быть production/master representation, а 2D/2.5D — дешёвым runtime representation.

---

## 32. Acceptance Tests (W-track)

Stage 2.5 W-track считается завершённым, если пройдены следующие тесты. Каждый тест имеет как 2D, так и «renderer-OFF» и (требуется только интерфейсная готовность) 2.5D/3D версию.

### 32.1. AT-W0-1: 1000 NPC Generation Test

```python
def test_generate_1000_npcs_without_manual_assets():
    """Сгенерировать 1000 NPC без ручного создания sprite/model."""
    for i in range(1000):
        npc_id = f"npc_gen_{i}"
        npc = NpcFactory.generate(npc_id=npc_id, world_seed="test_world")
        assert npc.visual_genome is not None
        assert npc.body_state is not None
        assert npc.clothing_state is not None
        assert npc.visual_body_state is not None
        assert npc.representation_mode in RepresentationMode

    # Все genomes уникальны
    genomes = [npc.visual_genome for npc in generated]
    assert len(set(g.genome_seed for g in genomes)) == 1000

    # Save/load сохраняет appearance
    for npc in generated:
        saved = serialize(npc)
        loaded = deserialize(saved)
        assert loaded.visual_genome == npc.visual_genome
```

### 32.2. AT-W5-1: Aging Test

```python
def test_aging_without_model_replacement():
    """NPC стареет от 10 до 60 лет без смены identity."""
    npc = NpcFactory.generate(npc_id="npc_age", age_years=10.0)
    initial_id = npc.npc_id
    initial_genome = npc.visual_genome

    for age in [11, 12, 15, 20, 30, 45, 60]:
        npc = advance_time(npc, until_age=age)
        assert npc.npc_id == initial_id           # identity preserved
        assert npc.visual_genome == initial_genome # genome preserved
        assert npc.body_state.age_years == age
        assert 0.0 <= npc.body_state.developmental_stage <= 1.2
        # Renderer отдельно решает, какой sprite/mesh использовать

    # Нет события AGE_THRESHOLD_REPLACE_MODEL
    log = get_simulation_log()
    assert "AGE_THRESHOLD_REPLACE_MODEL" not in log
```

### 32.3. AT-W5-2: Injury Test

```python
def test_injury_persists_through_save_load_and_renderer_change():
    """Травма сохраняется через save/load и смену renderer."""
    npc = NpcFactory.generate(npc_id="npc_injury", age_years=25.0)

    # Apply injury: right hand cut
    injury = Injury(zone="hand.R", type="slash", structural_damage=0.5)
    npc = apply_injury(npc, injury)
    assert npc.body_state.limb_state["hand.R"].integrity < 1.0

    # Capability changes
    caps = CapabilityEvaluator.evaluate(npc.body_state)
    assert FunctionalCapability.CAN_GRIP_LARGE_OBJECT not in caps

    # Save/load
    saved = serialize(npc)
    loaded = deserialize(saved)
    assert loaded.body_state.limb_state["hand.R"].integrity == npc.body_state.limb_state["hand.R"].integrity

    # Renderer change
    loaded.representation_mode = RepresentationMode.SPRITE
    visual_state_a = PresentationProjector.project(loaded.body_state, ...)
    loaded.representation_mode = RepresentationMode.FULL_3D
    visual_state_b = PresentationProjector.project(loaded.body_state, ...)
    # Visible injury preserved
    assert any(vi.zone == "hand.R" for vi in visual_state_a.visible_injuries)
    assert any(vi.zone == "hand.R" for vi in visual_state_b.visible_injuries)
```

### 32.4. AT-W5-3: Disease Test

```python
def test_disease_progression_without_renderer_dependence():
    """Болезнь развивается и влияет на функциональность."""
    npc = NpcFactory.generate(npc_id="npc_disease", age_years=30.0)
    initial_caps = CapabilityEvaluator.evaluate(npc.body_state)

    # Apply disease
    disease = Condition(condition_id="flu", severity=0.5,
                       physiological_effects={"mobility": -0.3, "stamina": -0.4})
    npc = apply_condition(npc, disease)

    # Capability changes
    new_caps = CapabilityEvaluator.evaluate(npc.body_state)
    # Возможно, CAN_RUN больше не доступен
    assert new_caps != initial_caps

    # Recovery
    npc = advance_time(npc, until_tick=... + recovery_duration)
    assert disease not in npc.body_state.acute_conditions

    # Visual layer sees symptoms, not disease object
    visual_state = PresentationProjector.project(npc.body_state, ...)
    assert any(vs.type == "pallor" for vs in visual_state.visible_disease_markers)
```

### 32.5. AT-W3-1: Transfer Acceptance Test

```python
def test_take_carry_move_place_without_renderer():
    """TAKE → CARRY → MOVE → PLACE работает без renderer."""
    renderer_off()

    npc = NpcFactory.generate(npc_id="npc_transfer", age_years=25.0)
    chair = WorldObjectRegistry.spawn(archetype="chair", location_id="tavern", position=(5.0, 3.0))
    assert chair.state == "AVAILABLE"

    # TAKE
    take_action = SemanticAction(action_type="TAKE", target_object_id=chair.object_id)
    assert AffordanceResolver.resolve(chair, npc.body_state, npc.position)[0].action_type == "TAKE"
    execute_action(npc, take_action)
    chair = WorldObjectRegistry.get(chair.object_id)
    assert chair.state == "HELD"
    assert chair.holder == npc.npc_id

    # CARRY (move while holding)
    move_action = SemanticAction(action_type="MOVE", target_location_id="tavern", target_position=(7.0, 4.0))
    execute_action(npc, move_action)
    assert npc.position == (7.0, 4.0)
    chair = WorldObjectRegistry.get(chair.object_id)
    assert chair.position == (7.0, 4.0)  # chair moves with holder

    # PLACE
    place_action = SemanticAction(action_type="PLACE", target_object_id=chair.object_id,
                                   target_position=(7.5, 4.0))
    execute_action(npc, place_action)
    chair = WorldObjectRegistry.get(chair.object_id)
    assert chair.state == "AVAILABLE"
    assert chair.holder is None
    assert chair.position == (7.5, 4.0)

    # Теперь тот же тест при разных renderer'ах — simulation результат идентичен
    for renderer in [SpriteRenderer(), DirectionalSpriteRenderer(), Full3DRenderer()]:
        renderer_on(renderer)
        npc2 = NpcFactory.generate(npc_id="npc_transfer_2", age_years=25.0)
        chair2 = WorldObjectRegistry.spawn(archetype="chair", ...)
        execute_action(npc2, take_action)
        # ... same assertions ...
        assert chair2.state == "HELD"
        # ... etc ...
```

### 32.6. AT-W9-1: Renderer Independence Test

(см. §28.2)

### 32.7. AT-W7-1: Representation Mode Switch Test

```python
def test_npc_can_switch_representation_mode_without_identity_change():
    npc = NpcFactory.generate(npc_id="npc_rep", age_years=25.0)
    initial_id = npc.npc_id
    initial_body = npc.body_state
    initial_genome = npc.visual_genome

    npc.representation_mode = RepresentationMode.SPRITE
    npc.representation_mode = RepresentationMode.IMPOSTOR
    npc.representation_mode = RepresentationMode.FULL_3D

    assert npc.npc_id == initial_id
    assert npc.body_state == initial_body
    assert npc.visual_genome == initial_genome
```

### 32.8. AT-W6-1..4: Determinism Tests

(см. §25.4)

---

## 33. Definition of Done (W-track)

Stage 2.5 W-track считается архитектурно завершённым только если доказано (см. пункт 36 в исходной спецификации):

1. **W-DoD-1.** World State не зависит от renderer.
2. **W-DoD-2.** Object interaction не зависит от animation.
3. **W-DoD-3.** Object transfer работает без renderer.
4. **W-DoD-4.** Embodied execution отделён от semantic action.
5. **W-DoD-5.** NPC body state существует независимо от visual asset.
6. **W-DoD-6.** Возраст является непрерывным состоянием, а не переключателем модели.
7. **W-DoD-7.** Injury может менять physical capability и visual state.
8. **W-DoD-8.** Disease может менять physical capability и visual state.
9. **W-DoD-9.** Attachment system существует как общий контракт.
10. **W-DoD-10.** Interaction points существуют независимо от конкретной модели.
11. **W-DoD-11.** Новый NPC может быть сгенерирован без ручного sprite/model creation.
12. **W-DoD-12.** Visual generation deterministic.
13. **W-DoD-13.** Один NPC может менять representation mode без смены identity.
14. **W-DoD-14.** 2D и будущий 3D renderer могут читать один WorldSnapshot.
15. **W-DoD-15.** Simulation tick отделён от render frame.
16. **W-DoD-16.** VRAM/RAM/CPU budgets формализованы.
17. **W-DoD-17.** Texture policy формализована.
18. **W-DoD-18.** LOD/impostor strategy определена.
19. **W-DoD-19.** Save/load сохраняет embodied state.
20. **W-DoD-20.** Replay не ломается из-за visual generation.
21. **W-DoD-21.** 1000+ NPC generation test проходит без ручной подготовки ассетов.
22. **W-DoD-22.** Aging test проходит без model replacement как simulation event.
23. **W-DoD-23.** Injury test проходит через 2D/2.5D/3D representation.
24. **W-DoD-24.** Carry/Place test проходит через 2D/2.5D/3D representation.
25. **W-DoD-25.** Архитектор выявил все текущие hard-couplings между simulation и presentation (см. §18.3).

---

## 34. Что НЕ делать сейчас (W-track scope limit)

Stage 2.5 W-track **не** должен превращаться в:

- Производство сотен 3D моделей.
- Создание всех animation clips.
- Полную систему facial animation.
- Production texture pipeline.
- Создание всех возрастных моделей.
- Создание полноценного character creator.
- Полную физическую симуляцию.
- AAA skeletal system.

Stage 2.5 W-track требует **архитектурный контракт и минимальный proof-of-concept**, а не production content. Полная реализация W5–W11 откладывается до стабилизации temporal/predictive runtime (Часть I).

---

## 35. Дорожная карта W-track (после Stage 2.5)

После стабилизации Stage 2.5 W-track разворачивается последовательно:

| Stage | Название | Scope |
|---|---|---|
| **W0** | Semantic World | WorldObject, affordances, ownership, containment, occupancy, holder, damage, interaction history |
| **W1** | Spatial Topology | Object relations, world topology provider extension |
| **W2** | Affordances / Interaction | AffordanceResolver, Precondition contract, SemanticAction |
| **W3** | Object State / Relations | FSM для door/chair/container/bed, transition validator |
| **W4** | Embodied State | BodyState, LimbState, CapabilityEvaluator, интеграция с CommitmentArbiter |
| **W5** | Body / Aging / Injury / Disease | AgingEngine, InjuryProcessor extension, Condition model |
| **W6** | Visual Genome / Procedural Identity | VisualGenome, VisualGenomeFactory, GenomeBlender |
| **W7** | Presentation State | VisualBodyState, PresentationProjector, RepresentationMode |
| **W8** | Animation / Attachment | AnimationState, UniversalAttachmentPoint |
| **W9** | 2D / 2.5D / 3D Representation | RendererPort, LODPolicy, Renderer Independence Test |
| **W10** | LOD / Impostor / Asset Streaming | Full asset pipeline, streaming, VRAM management |
| **W11** | Production World | All content, all ages, all injuries, full character creator |

**В рамках Stage 2.5 (этот документ):**
- W0–W4 — обязательны (интерфейсы + minimal proof-of-concept).
- W5–W9 — формализуются как интерфейсы и **пустые** реализации (stubs), доказывающие инвариант.
- W10–W11 — полностью откладываются.

---

## 36. Интеграция Части II с Частью I

### 36.1. Общие компоненты

| Часть I компонент | Часть II расширение |
|---|---|
| `ActionCommitment` (§6.1) | Должен также содержать `semantic_action: SemanticAction` (W2) и `target_object_id` (W0). |
| `CommitmentArbiter` (§6.4) | Должен вызывать `AffordanceResolver` и `CapabilityEvaluator` для precondition check (W2 + W4). |
| `PredictionEngine` (§6.2) | Должен учитывать Embodied State при предсказании: NPC с ампутированной правой рукой не может предсказать успешный TAKE правой рукой. |
| `OutcomeObserver` (§6.3) | Должен также сравнивать expected Embodied State transition с actual (например, ожидалось что hunger -30, но NPC не смог взять еду из-за injury). |
| `INTERRUPT_THRESHOLD` (§9) | Должен учитывать functional capability: NPC с CAN_WALK=False не должен получать MOVE commitments. |
| Phase 5.5 Prediction (§6.5) | Должна также проверять preconditions для semantic action. |

### 36.2. Обновлённый NPC Tick Pipeline (с W-track)

```
Phase 5 (decision):
  5.1  perception (existing)
  5.2  memory       (existing)
  5.3  drives       (existing)
  5.4  decision     (existing)
  5.5  ★ prediction (Part I)
       - Semantic action chosen (W2)
       - Preconditions check (W2 + W4 CapabilityEvaluator)
       - If preconditions fail → replan
       - Else: ExpectedOutcome computed
  5.6  intent emission (existing, с semantic_action + expected_outcome)
```

### 36.3. Расширенная архитектурная петля (финальная)

```
┌────────────────────────────────────────────────────────────────────────┐
│                                                                        │
│   WORLD STATE  ──────────►  EMBODIED STATE  ──────────►  PREDICTED    │
│   (objects,          │     (body, capability,   │            FUTURE    │
│    topology,         │     attachment, injury)  │                     │
│    affordances,      │                          │                     │
│    ownership,        │                          │                     │
│    causality)        │                          │                     │
│        │             │                          │                     │
│        ▼             │                          │                     │
│   PERCEPTION         │                          │                     │
│        │             │                          │                     │
│        ▼             │                          │                     │
│   BELIEFS            │                          │                     │
│        │             │                          │                     │
│        ▼             │                          │                     │
│   DRIVES             │                          │                     │
│        │             │                          │                     │
│        ▼             │                          │                     │
│   DECISION (semantic action)                    │                     │
│        │             │                          │                     │
│        ▼             │                          │                     │
│   ★ PRECONDITION CHECK (W2+W4)                  │                     │
│        │             │                          │                     │
│        ▼             │                          │                     │
│   ★ PREDICTION (expected outcome) ──────────────┘                     │
│        │                                                               │
│        ▼                                                               │
│   COMMITMENT (with semantic_action + expected_outcome + eta)          │
│        │                                                               │
│        ▼                                                               │
│   EXECUTION (traversal / windup / task)                               │
│        │                                                               │
│        ▼                                                               │
│   ACTUAL OUTCOME                                                       │
│        │                                                               │
│        ▼                                                               │
│   ★ PREDICTION ERROR  ─────►  L1CHRONICLE  ─────►  PATTERN DETECTOR    │
│                                                        │               │
│                                                        ▼               │
│                                              UPDATED BELIEFS           │
│                                              + UPDATED EMBODIED STATE  │
│                                              + UPDATED WORLD STATE      │
│                                                        │               │
│                                                        ▼               │
│                                              PRESENTATION PROJECTOR    │
│                                                        │               │
│                                          ┌─────────────┼─────────────┐ │
│                                          ▼             ▼             ▼ │
│                                        SPRITE      IMPOSTOR         3D │
│                                          │             │             │ │
│                                          └─────────────┼─────────────┘ │
│                                                        ▼               │
│                                                     RENDERER            │
│                                                        │               │
│                                                        ▼               │
│                                              UPDATED WORLD  ──────────┘
└────────────────────────────────────────────────────────────────────────┘
```

Это момент, когда ENIGMA перестаёт быть пошаговым автоматом реакций и становится фундаментом физически воплощённого мира.

---

## 37. Дополнительные риски W-track (расширение §12 Части I)

| # | Риск | Severity | Mitigation |
|---|---|---|---|
| **RW1** | `BodyState` становится «god object»: все поля мира в одном dataclass. | HIGH | Строго разделить World State (objects) и Embodied State (body). BodyState только про тело NPC. |
| **RW2** | `CapabilityEvaluator` становится слишком медленным (full body eval per tick). | MEDIUM | Pure function, кэшируется по `(body_state_hash)`. Инвалидируется только при change в body state. |
| **RW3** | `VisualGenome` seed ломается при save/load разных версий. | HIGH | `genome_seed` versioned: `genome_seed_v1`, `genome_seed_v2`. Migration plan для каждого version. |
| **RW4** | Renderer Independence Test не выявляет coupling, потому что 2D/3D renderer'ы оба импортируют одни и те же типы. | MEDIUM | Тест должен импортировать renderer'ы как **полностью** отдельные модули, без shared imports кроме `RendererPort`. |
| **RW5** | AgingEngine ломает determinism: floating-point drift. | HIGH | Все curves — pure functions of `(age, genetics)`, deterministic. Тест `test_aging_determinism`: одинаковый age → одинаковый phenotype. |
| **RW6** | InjuryProcessor (существующий) и W5 Injury chain конфликтуют (двойной processing). | HIGH | Существующий `injury_processor.py` становится adapter к новой Injury chain. Прецедент: `legacy_delta_adapter.py`. |
| **RW7** | LOD Policy оставляет important NPC без деталей. | LOW | `npc_importance` — отдельный сигнал, проверяется в тесте. Story-relevant NPC всегда LOD 0. |
| **RW8** | W6 Genome Blender создаёт biologically impossible комбинации. | LOW | Stage 2.5 — proof-of-concept, не production. Validation — в W11. |
| **RW9** | `WorldObjectRegistry` становится узким местом (один dict для всех объектов мира). | MEDIUM | Sharding по location_id. Прецедент: `commitment_registry`. |
| **RW10** | Coupling audit (§18) выявляет слишком много нарушений, блокируя Stage 2.5. | MEDIUM | Категория «Legacy coupling» позволяет отложить миграцию. Stage 2.5 требует только выявление и классификацию, не устранение. |

---

## 38. Дополнительные открытые вопросы (для архитектора, W-track)

1. **WQ1.** Должен ли `BodyState` быть frozen dataclass (immutable) или mutable? Frozen упрощает determinism, mutable упрощает in-place updates. Прецедент в коде: `NPCVisualState` frozen, `commitment` mutable.
2. **WQ2.** Как `VisualGenome` мигрирует между версиями? Полная регенерация или field-by-field migration?
3. **WQ3.** Должен ли `RepresentationMode` быть полем NPCState (per-NPC) или глобальной настройкой renderer'а?
4. **WQ4.** Как `WorldObject` идентифицируется? Тот же паттерн, что `commitment_id` (md5 seed)? Или UUID4?
5. **WQ5.** Должна ли `InteractionHistoryRef` быть отдельной таблицей в SQLite, или частью `L1Chronicle`?
6. **WQ6.** Должен ли `CapabilityEvaluator` поддерживать复合 capabilities (например, `CAN_OPEN_LATCH` требует `CAN_GRIP_SMALL_OBJECT` + `dexterity > 0.7`)?
7. **WQ7.** Как `AffordanceResolver` обрабатывает условные affordances (например, `OPEN(door)` доступен, но если `door.locked=True`, то сначала нужен `UNLOCK`)?
8. **WQ8.** Как `PresentationProjector` обрабатывает **изменения** visual state (например, переход от SPRITE к FULL_3D mid-frame)? Crossfade или hard cut?

Эти вопросы должны быть решены архитектором до реализации W4 и W7.

---

## 39. Расширенная дорожная карта (с W-track)

```
STAGE 0  Foundation Freeze
         │
         ▼
STAGE 1  Causal Spine (ADR-O-201)
         │
         ▼
STAGE 2  Living NPC Kernel (commit 6ed3310 — ActionCommitment, Arbiter, Registry, NpcTickPipeline)
         │
         ▼
★ STAGE 2.5  Temporal Causality + Predictive Runtime + World/Embodiment Foundation  ◄── THIS TZ
         │   ┌─ Part I: Temporal/Predictive Runtime (M1–M5)
         │   └─ Part II: W0–W9 (interfaces + minimal PoC; W5–W9 stubs)
         ▼
STAGE 3  Tavern Life
         │
         ▼
STAGE 4  Spatial + Social Availability
         │
         ▼
STAGE 5  NPC ↔ NPC Society
         │
         ▼
STAGE 6  Perception
         │
         ▼
STAGE 7  Epistemic Propagation
         │
         ▼
STAGE 8  Motivation + Commitment / Replanning
         │
         ▼
STAGE W5–W11  (post-Stabilization)
         Full Embodiment, Visual Production, Asset Pipeline, LOD/Streaming
```

---

## 40. Главный вывод

Stage 2.5 — это **не ещё один этап AI**. Это момент, когда ENIGMA закладывает фундамент физически воплощённого мира:

- **Часть I** вводит временной горизонт для NPC: мир продолжает изменяться во время исполнения действия.
- **Часть II** вводит физическое воплощение: NPC имеют тела, объекты имеют состояния, переносы предметов работают без renderer, травмы меняют возможности, болезни влияют на поведение, процедурная генерация создаёт новых NPC без ручных ассетов, 2D/2.5D/3D renderer'ы читают один WorldSnapshot.

Вместе они закрывают главный архитектурный риск ENIGMA:

> Новый NPC, новый возраст, новый шрам, потерянная конечность, болезнь, новая одежда, перенос стула, открытие двери или совершенно новый renderer не должны требовать переписывания мозга NPC. Они должны изменять World/Embodied State, из которого разные presentation backends независимо строят своё изображение.

Это и есть правильная точка, в которой Stage 2.5 становится фундаментом физически воплощённого мира ENIGMA.

---

## 41. Финальные ссылки

### 41.1. Внутренние документы (расширенный список)

- `docs/АРХИТЕКТУРНЫЙ_УСТАВ_ENIGMA.md` — Устав.
- `docs/RUNTIME ARCHAEOLOGY MAP.md` — карта исполнения.
- `docs/ENIGMA_ROADMAP.md` — дорожная карта преемника.
- `docs/audits/ADR-O-201_Causal Kernel Architecture.md` — Causal Kernel.
- `docs/audits/ADR-FOUNDATION-FREEZE_IMPACT.md` — Stage 0.
- `docs/audits/ADR-CAUSAL-SPINE_IMPACT.md` — Stage 1.
- `docs/audits/ADR-TZ08-8_IMPACT.md` — Stage 2.
- `docs/audits/ADR-O-363` — Commitment Arbiter.
- `docs/Почти Актуальные TZ/VZ/TEXTURES_AND_GEOMETRY_TZ.md` — Phase 3 rendering system (рассматривается как W7/W8/W9 production roadmap).
- `architecture/temporal.yaml` — временная конфигурация.
- `architecture/pipeline.yaml` — топология pipeline.
- `architecture/body_topology.yaml` — существующая топология тела (инвентарь).
- `architecture/spatial.yaml` — spatial contract.
- `architecture/frontend.yaml` — frontend topology.

### 41.2. Ключевые файлы кода (расширенный список)

**Существующие (расширяются):**
- `backend/app/domain/action_commitment.py` — расширение `semantic_action`, `target_object_id`.
- `backend/app/domain/body.py` — расширение до `BodyState`.
- `backend/app/domain/presentation.py` — расширение `NPCVisualState` до `VisualBodyState`.
- `backend/app/domain/vital_state.py` — становится частью `CapabilityEvaluator`.
- `backend/app/services/action/commitment_arbiter.py` — добавление precondition check.
- `backend/app/services/action/commitment_registry.py` — без изменений.
- `backend/app/services/body/body_topology_service.py` — расширение до Universal Attachment System.
- `backend/app/services/spatial/world_topology_provider.py` — расширение object relations.
- `backend/app/services/combat/injury_processor.py` — adapter к новой Injury chain.
- `backend/app/services/npc/expectation_store.py` — заменяется на `PredictionEngine` + `OutcomeObserver`.
- `frontend/presentation_firewall.py` — formal guard, без изменений.

**Новые (Stage 2.5 W-track):**
- `backend/app/domain/world_object.py` — W0.
- `backend/app/domain/object_fsms.py` — W3.
- `backend/app/domain/semantic_action.py` — W2.
- `backend/app/domain/body_state.py` — W4.
- `backend/app/domain/visual_genome.py` — W6.
- `backend/app/domain/attachment_points.py` — W8.
- `backend/app/domain/condition.py` — W5.
- `backend/app/services/world/affordance_resolver.py` — W2.
- `backend/app/services/world/visual_genome_factory.py` — W6.
- `backend/app/services/world/genome_blender.py` — W6.
- `backend/app/services/body/capability_evaluator.py` — W4.
- `backend/app/services/body/aging_engine.py` — W5.
- `backend/app/services/presentation/presentation_projector.py` — W7.
- `backend/app/services/presentation/renderer_port.py` — W9.
- `backend/app/services/presentation/lod_policy.py` — W9.
- `backend/tests/renderer_independence_test.py` — AT-W9-1.
- `backend/tests/w_track_acceptance_tests.py` — все W-track ATs.

### 41.3. Внешние ссылки

- Commit `6ed3310` (V.0.5.3.8.7): https://github.com/4Um4/Enigma/commit/6ed3310fa38379df115e87800d13a25558c31635

---

**Конец документа (Часть I + Часть II).**
