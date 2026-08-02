# ТЗ: ИНФРАСТРУКТУРА ДОЛГОВЕЧНОСТИ ENIGMA

> **Документ:** Техническое задание на 4 инфраструктурные подсистемы, которые продлят полезность LLM-архитектора за пределы естественной границы (v8.5-v9.0)
> **Версия проекта:** Enigma-V.0.5.3.6.8 (S147)
> **Дата:** 2026-08-02
> **Назначение:** Снизить зависимость проекта от одного LLM-партнёра, превратив ADR + тесты + телеметрию в **самодостаточную систему памяти и валидации**, которую может использовать любой новый LLM (или человек) без потери контекста.

---

## 0. КОНТЕКСТ И ЦЕЛИ

### 0.1. Проблема

LLM-архитектор, ведущий ENIGMA, имеет естественную границу полезности на горизонте v8.5-v9.0 (~3-6 месяцев работы). Граница обусловлена:

1. **Контекстное окно** — 708 .py файлов + 30+ ADR + CAUSAL_CONTRACT + MUTATIONS + логи не помещаются одновременно.
2. **Отсутствие памяти между сессиями** — новый чат = новый LLM. ADR как long-term memory — это документация, не память.
3. **Энтропия ошибок нелинейна** — при росте кода в 10×, ошибки растут в ~100×.
4. **Слепота на emergent behavior** — LLM не может mentally simulate 1000 тиков и сказать "через 1000 тиков Люся уйдёт от Торнина с вероятностью 67%".

### 0.2. Решение

Четыре инфраструктурные подсистемы, каждая из которых **делегирует** часть работы LLM внешней механике:

| # | Подсистема | Что делегирует | Что получает LLM |
|---|------------|----------------|------------------|
| **1** | **Property-Based IPT** | Поиск edge-cases | Гарантия: "для любого InterventionEvent инвариант I не нарушается" |
| **2** | **Replay System** | Память между сессиями | Возможность отмотать тик 472 и сказать "здесь начался дрейф" |
| **3** | **Causal Probes** | Мониторинг в реальном времени | Автоматический детектор regressions вместо ручного аудита |
| **4** | **ADR-net (Dependency Graph)** | Tracing влияний ADR | Ответ на "какие ADR ломаются, если я поменяю X" |

### 0.3. Принципы проектирования

1. **Zero-touch production** — все 4 подсистемы НЕ должны ломать production runtime. Probe overhead ≤ 5% CPU.
2. **Append-only где возможно** — replay events и causal probes пишут в SQLite, никогда не мутируют.
3. **LLM-agnostic** — формат данных должен быть читаем любым LLM без специального prompt engineering.
4. **Градуированная активация** — каждая подсистема имеет 3 уровня (OFF / PASSIVE / ACTIVE), переключаемых флагом в `config.py`.
5. **Backward-compatible** — миграция не требует переделки существующего кода; подсистемы встраиваются в уже существующие hook'и.

### 0.4. Текущий baseline (v6.8)

**Что уже есть:**
- `backend/tests/IPT.py` (329 строк, 6 invariants) — ручные probe tests
- `diagnostics/causal_observer.py` (313 строк) — post-mortem лог-парсер
- `diagnostics/health_checkers/{tick_health,movement_health,invariant_health}.py` — пост-хок анализаторы
- `backend/tests/sandbox/SUPERBOX/drift_laboratory.py` (1646 строк) — A/B stress-тестинг
- `backend/app/services/npc/l1_chronicle.py` (337 строк) — append-only SQLite для identity events
- `backend/data/logs/enigma_*.jsonl` — структурированные логи
- `backend/data/logs/scene_changes_*.jsonl` — лог всех SceneChange
- `reports/dna_history.jsonl` — 906+ записей с метриками DNA (SHI, NPI, OBI, SCF, ADR, CVS, PFI)
- `backend/app/services/state/sqlite_persistence_adapter.py` — atomic_commit с транзакционной семантикой
- `docs/ADR (Architecture Decision Records).md` — 21 закон (L1-L21) + references на 30+ ADR

**Чего нет:**
- Property-based testing (поиск edge-cases через генерацию входов)
- Replay системы (запись TickState + InterventionEvent для воспроизведения)
- Real-time causal probes (invariant monitoring в production, не post-mortem)
- ADR dependency graph (текстовые references, не traversable structure)

---

## 1. ПОДСИСТЕМА 1: PROPERTY-BASED IPT (PBT)

### 1.1. Цель

Превратить текущие 6 ручных invariant probe tests в **автоматический генератор edge-cases**. После внедрения LLM-архитектор сможет сказать: "для **любого** InterventionEvent с любым payload, любой комбинацией NPC states, любым spatial layout — инвариант Causal Provenance не нарушается" — и получить машинное подтверждение.

### 1.2. Что заменить / расширить

**Текущий формат IPT (ручной):**
```python
def inv_npc_has_name(world: TestWorld) -> InvariantResult:
    for nid in world.npc_ids:
        pos = world.npc_positions.get(nid, {})
        if not pos.get("name"):
            return InvariantResult("INV-NPC-NAME", "CRITICAL", False, ...)
    return InvariantResult("INV-NPC-NAME", "CRITICAL", True, ...)
```

**Новый формат (property-based):**
```python
from hypothesis import given, strategies as st

@given(
    intervention=st.builds(
        InterventionEvent,
        source=st.sampled_from(["player", "dm", "world"]),
        payload=st.fixed_dictionaries({
            "text": st.text(min_size=1, max_size=200),
            "semantic_action": st.sampleed_from(["attack", "threaten", "talk", "flee"]),
            "target_id": st.one_of(st.none(), st.text(min_size=1, max_size=30)),
        }),
    ),
    npc_count=st.integers(min_value=1, max_value=10),
    tick=st.integers(min_value=0, max_value=10000),
)
def test_inv_causal_provenance_holds_for_any_intervention(intervention, npc_count, tick):
    """Invariant I: любое изменение наблюдаемого состояния имеет конечную причинную цепь."""
    world = _bootstrap_minimal_world(npc_count=npc_count, tick=tick)
    snapshot_before = world.snapshot()
    
    world.apply_intervention(intervention)
    world.idle_tick()
    
    snapshot_after = world.snapshot()
    drift = CausalProvenanceValidator.validate(snapshot_before, snapshot_after, intervention)
    
    assert drift.has_causal_chain(), f"Нарушение инварианта I: {drift.unexplained_changes}"
```

### 1.3. Архитектура

```
backend/tests/pbt/
├── __init__.py
├── strategies.py              # Hypothesis strategies для всех domain types
│   ├── intervention_strategy()  # Генератор InterventionEvent
│   ├── npc_state_strategy()     # Генератор NPCState (через from_legacy)
│   ├── scene_state_strategy()   # Генератор scene_state
│   ├── spatial_layout_strategy()# Генератор топологии локации
│   └── traversal_strategy()     # Генератор TraversalState
├── properties/
│   ├── test_inv_causal_provenance.py    # Invariant I
│   ├── test_inv_historical_constraint.py # Invariant II
│   ├── test_inv_temporal_isolation.py   # Invariant III
│   ├── test_inv_semantic_validity.py    # Invariant IV
│   ├── test_inv_l3_ephemeral.py         # L3-P1 (EffectiveDrives эфемерны)
│   ├── test_inv_kernel_rng_determinism.py # ADR-O-301
│   ├── test_inv_no_teleportation.py     # ADR-048
│   ├── test_inv_death_lock.py           # ADR-127
│   ├── test_inv_spatial_coherence.py    # SC-1..SC-8
│   └── test_inv_epistemic_boundary.py   # DM-agent не читает mental fields
├── validators.py              # CausalProvenanceValidator, HistoricalConstraintValidator, ...
├── shrinkers.py               # Custom shrink strategies (минимизация контрпримера)
└── seed_corpus.py             # Известные edge-cases из багов v6.7/v6.8 (seed для PBT)
```

### 1.4. Этапы реализации

#### Этап 1.1: Установка зависимостей и bootstrap (4 часа)

**Files:** `backend/requirements.txt`, `backend/tests/pbt/__init__.py`, `backend/tests/pbt/strategies.py`

1. Установить `hypothesis` (уже есть в dev-dependencies? проверить) и `pytest-hypothesis`.
2. Создать пакет `backend/tests/pbt/`.
3. Реализовать `strategies.py` с базовыми генераторами:
   - `intervention_strategy()` — генерирует валидные `InterventionEvent` с произвольным payload
   - `npc_state_strategy()` — генерирует `NPCState` через `from_legacy` (не через конструктор, см. ADR-013)
   - `scene_state_strategy()` — генерирует минимально-валидный `scene_state` с 1-10 NPC
4. Тест: `pytest backend/tests/pbt/test_strategies_smoke.py` — генераторы не падают на 100 случайных значениях.

**Acceptance criteria:**
- `hypothesis` импортируется без ошибок
- 100 random samples от каждого strategy не падают
- Стратегии детерминированы (seed可控)

#### Этап 1.2: CausalProvenanceValidator (8 часов)

**Files:** `backend/tests/pbt/validators.py`, `backend/tests/pbt/properties/test_inv_causal_provenance.py`

1. Реализовать `CausalProvenanceValidator.validate(snapshot_before, snapshot_after, intervention)`:
   - Вычисляет diff между снапшотами
   - Для каждого изменения ищет causal chain (через L1Chronicle + EventBuffer)
   - Возвращает `CausalDriftReport` с `unexplained_changes: List[Change]`
2. Реализовать первый property test: `test_inv_causal_provenance_holds_for_any_intervention`
3. Запустить на 1000 примеров. Зафиксировать контрпримеры.

**Acceptance criteria:**
- Property test проходит на 1000 примеров ИЛИ находит реальный контрпример
- Найденный контрпример минимизируется (hypothesis shrink) до читаемого вида
- Контрпример логируется в `backend/tests/pbt/seed_corpus/` для будущего regression-теста

#### Этап 1.3: Исторические инварианты (6 часов)

**Files:** `backend/tests/pbt/properties/test_inv_historical_constraint.py`, `test_inv_temporal_isolation.py`

1. `HistoricalConstraintValidator` — для каждого изменения проверяет, что вычисление использовало релевантную историю (L1Chronicle events).
2. `TemporalIsolationValidator` — для каждого tick проверяет, что входные данные tick не мутированы во время вычисления.

**Acceptance criteria:**
- Оба property test проходят на 500 примерах каждый
- Найденные нарушения (если есть) документированы как ADR-INV-VIOLATION-XXX

#### Этап 1.4: Spatial Coherence Properties (8 часов)

**Files:** `backend/tests/pbt/properties/test_inv_spatial_coherence.py`

1. `spatial_layout_strategy()` — генерирует случайные топологии локаций с 3-20 узлами, 1-5 boundary nodes, 0-3 dynamic obstacles.
2. Property tests для SC-1..SC-8 (см. CAUSAL_CONTRACT §2.1.1):
   - `test_sc1_local_position_not_zero_when_invalid`
   - `test_sc2_local_position_belongs_to_location`
   - `test_sc3_current_node_exists_in_spatial_service`
   - `test_sc4_current_node_resolvable_from_local_position`
   - `test_sc5_spatial_service_built_from_authoritative_topology`
   - `test_sc6_no_movement_without_coherence_validation`
   - `test_sc7_persistence_not_authoritative_if_invalid`
   - `test_sc8_recovery_is_deterministic`

**Acceptance criteria:**
- Все 8 SC properties проходят на 200 случайных топологиях
- `MovementEngine` не запускается при нарушении SC-6

#### Этап 1.5: Интеграция с существующим IPT (4 часа)

**Files:** `backend/tests/IPT.py`

1. Добавить новую секцию в `INVARIANTS`: `PROPERTY_BASED` (помимо текущих ручных).
2. Property-based tests запускаются с `max_examples=200` (быстрый режим) в IPT, и `max_examples=1000` в CI.
3. В `InvariantResult` добавить поле `counterexamples: List[str]` (минимизированные контрпримеры).
4. IPT exit code: `0` если все property tests прошли, `1` если найден контрпример.

**Acceptance criteria:**
- `python backend/tests/IPT.py` запускает и ручные, и property-based тесты
- Время выполнения ≤ 30 секунд (быстрый режим)
- При провале печатает минимальный контрпример

#### Этап 1.6: Seed corpus из багов v6.7/v6.8 (4 часа)

**Files:** `backend/tests/pbt/seed_corpus/`

1. Для каждого из 14 критических багов v6.7 + 2 регрессий v6.8 создать seed:
   - `seed_bugs_core_003_dm_ctx_bridge.json` — входные данные, на которых баг воспроизводился
   - `seed_bugs_spatial_001_cross_loc_materialize.json`
   - ... (всего 16 seeds)
2. Каждый seed загружается в property test как `@example` декоратор.
3. Любой будущий regression на этих входах будет немедленно пойман.

**Acceptance criteria:**
- 16 seed файлов в `seed_corpus/`
- Все seeds проходят (баги исправлены в v6.8)
- При откате фикса v6.8 соответствующий seed падает

### 1.5. Метрики успеха

| Метрика | Baseline (v6.8) | Цель (v6.9) |
|---------|-----------------|-------------|
| Ручных invariant tests | 6 | 6 (без изменений) |
| Property-based tests | 0 | 12+ |
| Покрытие инвариантов CAUSAL_CONTRACT | ~30% | ~85% |
| Среднее время обнаружения regression | 1-2 дня (через логи) | <5 минут (CI) |
| Найдено новых edge-cases за разработку | N/A | 20+ (документированных) |

---

## 2. ПОДСИСТЕМА 2: REPLAY SYSTEM

### 2.1. Цель

Записывать **полный каузальный след** каждой сессии (TickState + InterventionEvent + TickMutation + WorldSnapshot), чтобы любой LLM мог:
1. **Отмотать** на любой тик и сказать "здесь начался дрейф"
2. **Воспроизвести** баг с точностью до тика
3. **A/B тестировать** изменения кода на одном и том же сценарии

### 2.2. Принцип

Воспроизведение **только детерминированной части**. LLM-вызовы и `time.time()` не воспроизводимы, но **записываются** (для отладки). При replay:
- `KernelRNG` восстанавливается из `(tick, npc_id, salt)` — детерминирован
- LLM-ответы читаются из кэша (replay store), не вызываются повторно
- `time.time()` подменяется на `game_time_seconds` во время replay

### 2.3. Архитектура

```
backend/app/services/replay/
├── __init__.py
├── replay_recorder.py         # Запись сессии
├── replay_player.py           # Воспроизведение сессии
├── replay_store.py            # SQLite хранилище
├── llm_cache.py               # Кэш LLM-ответов для replay
├── time_freezer.py            # Подмена wall-clock на game_time
└── replay_cli.py              # CLI для запуска replay
```

**Schema SQLite (`replay/{campaign_id}/{session_id}.db`):**

```sql
CREATE TABLE tick_snapshots (
    tick_id INTEGER PRIMARY KEY,
    game_time_seconds REAL NOT NULL,
    tick_state_json TEXT NOT NULL,         -- полный TickState (immutable)
    tick_mutation_json TEXT,               -- результат NpcTickPipeline.run
    world_snapshot_json TEXT,              -- DTO после Phase 9
    commit_hash TEXT NOT NULL,             -- git hash кода, на котором запускалось
    schema_version INTEGER NOT NULL
);

CREATE TABLE interventions (
    intervention_id INTEGER PRIMARY KEY,
    tick_id INTEGER NOT NULL,              -- на каком тике получено
    source TEXT NOT NULL,                  -- "player" / "dm" / "world"
    payload_json TEXT NOT NULL,
    intent_compression_json TEXT,          -- результат IntentCompressor (LLM slow-path)
    FOREIGN KEY (tick_id) REFERENCES tick_snapshots(tick_id)
);

CREATE TABLE llm_calls (
    call_id INTEGER PRIMARY KEY,
    tick_id INTEGER NOT NULL,
    agent_name TEXT NOT NULL,              -- "dm" / "rules" / "dialogue_executor" / "intent_compressor"
    prompt_hash TEXT NOT NULL,             -- SHA-256 промпта (для дедупликации)
    prompt_json TEXT NOT NULL,
    response_json TEXT NOT NULL,
    model_name TEXT NOT NULL,
    latency_ms INTEGER NOT NULL,
    FOREIGN KEY (tick_id) REFERENCES tick_snapshots(tick_id)
);

CREATE TABLE causal_probes (
    probe_id INTEGER PRIMARY KEY,
    tick_id INTEGER NOT NULL,
    probe_name TEXT NOT NULL,              -- "INV-CAUSAL-PROVENANCE" / "INV-L3-EPHEMERAL" / ...
    status TEXT NOT NULL,                  -- "PASS" / "FAIL" / "WARN"
    details_json TEXT,
    FOREIGN KEY (tick_id) REFERENCES tick_snapshots(tick_id)
);

CREATE TABLE scene_changes (
    change_id INTEGER PRIMARY KEY,
    tick_id INTEGER NOT NULL,
    change_json TEXT NOT NULL,
    applied BOOLEAN NOT NULL,
    FOREIGN KEY (tick_id) REFERENCES tick_snapshots(tick_id)
);
```

### 2.4. Этапы реализации

#### Этап 2.1: ReplayStore (SQLite backend) (6 часов)

**Files:** `backend/app/services/replay/replay_store.py`

1. Реализовать `ReplayStore` класс (similar to `L1Chronicle` API):
   - `start_session(campaign_id, commit_hash) -> session_id`
   - `record_tick(tick_id, tick_state, tick_mutation, world_snapshot)`
   - `record_intervention(tick_id, intervention, intent_compression)`
   - `record_llm_call(tick_id, agent_name, prompt, response, model, latency)`
   - `record_causal_probe(tick_id, probe_name, status, details)`
   - `record_scene_change(tick_id, change, applied)`
   - `load_session(session_id) -> ReplaySession`
   - `list_sessions(campaign_id) -> List[SessionMetadata]`
2. Schema migrations (см. SQL выше).
3. Тесты на запись/чтение 100 тиков.

**Acceptance criteria:**
- Запись 100 тиков < 2 секунды
- SQLite file size ≤ 5 MB на 100 тиков (сжатие через zlib для JSON-полей)
- Concurrent writes безопасны (WAL mode)

#### Этап 2.2: ReplayRecorder (hook в TickOrchestrator) (6 часов)

**Files:** `backend/app/services/replay/replay_recorder.py`, изменения в `backend/app/services/tick_orchestrator.py`

1. `ReplayRecorder` подписывается на хуки в `TickOrchestrator._run_core_phases`:
   - После Фазы 0: `recorder.record_tick_state(ctx)`
   - После Фазы 5: `recorder.record_tick_mutation(mutation)`
   - После Фазы 9: `recorder.record_world_snapshot(snapshot)`
   - До Фазы 10: `recorder.record_interventions(ctx.interventions)`
2. Активация через `settings.replay_mode: Literal["off", "passive", "active"]`:
   - `off` — recorder не создаётся, overhead = 0
   - `passive` — recorder пишет в SQLite, но не блокирует тик
   - `active` — recorder пишет синхронно (для CI тестов)
3. LLM call hook: обернуть `LLMProvider.invoke` в `ReplayRecorder.record_llm_call(...)` (только в passive/active mode).

**Acceptance criteria:**
- В `passive` mode overhead ≤ 5% CPU
- В `active` mode overhead ≤ 15% CPU
- Запись не падает, даже если основная симуляция падает (try/except с `logger.error`)
- При `off` mode никаких изменений в perf

#### Этап 2.3: LLM Cache для replay (8 часов)

**Files:** `backend/app/services/replay/llm_cache.py`, изменения в `backend/app/services/llm/router.py`

1. `LLMCache` — read-through кэш:
   - `get(agent_name, prompt_hash) -> Optional[str]` — возвращает закэшированный ответ
   - `set(agent_name, prompt_hash, response)` — записывает
   - Хранение: в `replay/{campaign_id}/{session_id}.db` (таблица `llm_calls`)
2. В `LLMRouter.invoke`:
   - Если `settings.replay_playback = True` → читать из cache, не вызывать LLM
   - Если `settings.replay_record = True` → вызывать LLM и записывать в cache
   - Иначе → обычный вызов
3. Hash-функция для prompt: SHA-256 от JSON-сериализации prompt (стабильной, с sorted keys).

**Acceptance criteria:**
- Replay без LLM (только cache) даёт идентичный world_snapshot на каждом тике
- Hash stable: одинаковый prompt → одинаковый hash (verified via test)
- Cache miss в playback mode → raise `ReplayCacheMissError` (не молча)

#### Этап 2.4: TimeFreezer (8 часов)

**Files:** `backend/app/services/replay/time_freezer.py`

1. Контекст-менеджер `frozen_time(game_time_seconds)`:
   - Подменяет `time.time()` на `game_time_seconds` (для кода, который нарушает ADR-O-302, но не может быть переписан)
   - Подменяет `datetime.now()` на `datetime.fromtimestamp(game_time_seconds)`
   - Восстанавливает при выходе из контекста
2. В `ReplayPlayer.play(session_id, start_tick, end_tick)`:
   - Обернуть весь replay в `frozen_time` для каждого тика
3. Тесты: код с `time.time()` возвращает предсказуемое значение в replay.

**Acceptance criteria:**
- `time.time()` в replay возвращает `game_time_seconds` (с погрешностью ≤ 1ms)
- Не ломает production (`off` mode не активирует подмену)
- Thread-safe (каждый поток имеет свой frozen time)

#### Этап 2.5: ReplayPlayer (10 часов)

**Files:** `backend/app/services/replay/replay_player.py`, `replay_cli.py`

1. `ReplayPlayer.play(session_id, start_tick=0, end_tick=None, breakpoints=None)`:
   - Загружает tick_state из store
   - Подставляет `LLMCache` вместо реального LLM
   - Активирует `TimeFreezer`
   - Вызывает `TickOrchestrator.execute()` для каждого тика
   - Сравнивает результат с записанным `tick_mutation` и `world_snapshot`
   - При расхождении → `ReplayDriftError` с детальным diff
2. Breakpoints:
   - На конкретном `tick_id`
   - На `invariant_violation` (когда causal probe FAIL)
   - На `npc_id` + `event_type` (например, "остановись, когда Люся получит threat")
3. CLI: `python -m app.services.replay.replay_cli play --session <id> --start 470 --end 480`

**Acceptance criteria:**
- Replay воспроизводит записанный сценарий на 100% (0 drift) при том же commit_hash
- При другом commit_hash (изменённом коде) выдаёт diff: "tick 472: mutation.l1_drift_events изменился с [] на [TraitDriftEvent(...)]"
- CLI работает из терминала

#### Этап 2.6: Drift Laboratory integration (4 часа)

**Files:** `backend/tests/sandbox/SUPERBOX/drift_laboratory.py`

1. Добавить опцию `--replay-compare <session_id>` в `drift_laboratory`.
2. Запускает recorded session против текущего кода, сравнивает drift.
3. Отчёт: "5 тиков из 100 имеют drift class C (causal), 2 тика — class D (ontological)".

**Acceptance criteria:**
- DriftLaboratory может A/B сравнивать любой commit против любой записанной сессии
- Отчёт сохраняется в `reports/drift_lab/{session_id}_vs_{commit_hash}.md`

### 2.5. Метрики успеха

| Метрика | Baseline (v6.8) | Цель (v6.9) |
|---------|-----------------|-------------|
| Время до воспроизведения бага | 30-60 мин (manually) | <2 мин (replay CLI) |
| Coverage записанных сессий | 0% | 100% CI runs, опционально production |
| Drift detection между коммитами | N/A | Automatic для CI |
| LLM cache hit rate (replay) | N/A | 100% (без сети) |
| SQLite overhead (passive mode) | N/A | ≤5% CPU, ≤5 MB / 100 ticks |

---

## 3. ПОДСИСТЕМА 3: CAUSAL PROBES

### 3.1. Цель

Превратить текущий post-mortem `CausalObserver` в **real-time invariant monitor**, который работает в production и автоматически детектит regressions без ручного аудита LLM.

### 3.2. Принцип

**Causal Probe = lightweight check, запускаемый в конце каждого тика.**

В отличие от IPT (которые запускаются перед коммитом), probes — это post-commit валидаторы, которые:
- Не блокируют тик
- Пишут результат в `replay_store.causal_probes` (для replay)
- При критическом нарушении — `logger.error` + increment counter
- При накоплении N нарушений за M тиков — `SimulationIntegrityError`

### 3.3. Архитектура

```
backend/app/services/probes/
├── __init__.py
├── probe_registry.py          # Registry всех probes
├── probe_runner.py            # Запускает probes после каждого тика
├── probe_thresholds.py        # Конфиг: когда FALL → ERROR
├── probes/
│   ├── causal_provenance_probe.py    # Invariant I
│   ├── historical_constraint_probe.py # Invariant II
│   ├── temporal_isolation_probe.py   # Invariant III
│   ├── l3_ephemeral_probe.py         # L3-P1
│   ├── kernel_rng_probe.py           # ADR-O-301 (random.* в kernel?)
│   ├── spatial_coherence_probe.py    # SC-1..SC-8
│   ├── death_lock_probe.py           # ADR-127
│   ├── epistemic_boundary_probe.py   # DM-agent не читает mental fields
│   ├── somatic_gate_probe.py         # ADR-O-139 (Body → Somatic → Semantic)
│   ├── traversal_fsm_probe.py        # ADR-TRAV-FSM
│   ├── hp_ssot_probe.py              # ADR-HP-UNIFICATION
│   └── silent_failure_probe.py       # L4 (try/except: pass detector)
└── probe_alerts.py            # Webhook / log alerts при критических нарушениях
```

### 3.4. Этапы реализации

#### Этап 3.1: ProbeRegistry и ProbeRunner (6 часов)

**Files:** `backend/app/services/probes/probe_registry.py`, `probe_runner.py`

1. `Probe` протокол:
   ```python
   class Probe(Protocol):
       name: str  # "INV-CAUSAL-PROVENANCE"
       severity: Literal["INFO", "WARN", "ERROR"]
       def check(self, ctx: ProbeContext) -> ProbeResult: ...
   ```
2. `ProbeContext` — immutable snapshot пост-tick состояния:
   - `tick_id`, `game_time_seconds`
   - `tick_state` (вход)
   - `tick_mutation` (выход)
   - `world_snapshot` (после Phase 9)
   - `interventions` (что пришло от игрока)
   - `l1_events` (что записано в L1Chronicle)
3. `ProbeRunner.run_all(ctx)`:
   - Запускает все зарегистрированные probes
   - Агрегирует результаты
   - Записывает в `replay_store.causal_probes` (если replay активен)
   - При `severity == "ERROR"` инкрементит счётчик
4. Hook в `TickOrchestrator` — после Фазы 10 (commit) вызывать `ProbeRunner.run_all(ctx)`.

**Acceptance criteria:**
- ProbeRunner с 12 probes добавляет ≤ 10ms на тик
- Probe failure не роняет тик (только логирует)
- Probe results видны в `replay_store`

#### Этап 3.2: Базовые инвариант-пробы (10 часов)

**Files:** `backend/app/services/probes/probes/{causal_provenance,historical_constraint,temporal_isolation,l3_ephemeral,kernel_rng}_probe.py`

1. **CausalProvenanceProbe** — для каждого изменения в `tick_mutation.npc_deltas` проверяет, что есть соответствующий `TraitDriftEvent` в `l1_events` или `InterventionEvent`.
2. **HistoricalConstraintProbe** — для каждого решения NPC проверяет, что `DecisionHub.compute` получил `effective_drives` (L3), вычисленные из L0 + L2.5 beliefs (не из L0 напрямую).
3. **TemporalIsolationProbe** — хеширует `tick_state` до и после `NpcTickPipeline.run`. Если hash изменился → нарушение Invariant III.
4. **L3EphemeralProbe** — проверяет, что `EffectiveDrives` не сохраняется в `scene_state` и не переживает сериализацию.
5. **KernelRNGProbe** — статический анализ: grep на `random\.(choice|Random|randint|uniform)` в `backend/app/services/{npc,spatial,combat,game}/`. Должен возвращать 0 (с допустимыми исключениями, whitelisted в `kernel_rng_probe.py`).

**Acceptance criteria:**
- Каждый probe имеет unit test (наPASS и наFAIL)
- Все 5 probes активированы в `passive` mode
- На v6.8 baseline все probes возвращают PASS

#### Этап 3.3: Spatial & Traversal probes (8 часов)

**Files:** `probes/{spatial_coherence,death_lock,traversal_fsm,hp_ssot}_probe.py`

1. **SpatialCoherenceProbe** — для каждого живого NPC проверяет SC-1..SC-8 (см. CAUSAL_CONTRACT §2.1.1).
2. **DeathLockProbe** — для каждого NPC с `life_status="DEAD"`:
   - Не в `npc_deltas` (decay для мёртвых запрещён)
   - Не в `decision_intents` (мёртвые не решают)
   - Не в `movement_intents` (мёртвые не ходят)
   - `body_state["current_hp"]` не растёт (DEAD → ALIVE запрещён)
3. **TraversalFSMProbe** — для каждого `active_traversal`:
   - Статус ∈ {PENDING, MOVING, COMPLETED, CANCELLED}
   - Переход был через `transition_traversal()` (не прямой мутацией)
   - Zombie traversals (COMPLETED, но не удалены) ≤ 1 тик
4. **HPSsotProbe** — для каждого изменения HP:
   - Источник — `body_state["current_hp"]`, не `state.hp`
   - `evaluate_vital_state` — единственный источник смерти

**Acceptance criteria:**
- На v6.8 baseline: 0 violations
- При искусственном внедрении бага (например, `state.hp = 0` напрямую) — probe падает

#### Этап 3.4: Epistemic Boundary Probe (6 часов)

**Files:** `probes/epistemic_boundary_probe.py`, `somatic_gate_probe.py`

1. **EpistemicBoundaryProbe** — статический + runtime анализ DM-agent:
   - Static: AST-парсинг `dm_agent.py`, проверка что НЕ читаются `recalled_facts`, `real_state`, `stress_delta`, `trust_delta`, `fear` (с whitelist для observable aliases)
   - Runtime: hook в `DMAgent.narrate()` — логировать все поля из `context`, детектить "forbidden" keys
2. **SomaticGateProbe** — для каждого `InterventionEvent` с target NPC:
   - Если `target.body_state.shock_impulse > 0.7` → semantic parsing должен быть пропущен (только raw disturbance)
   - Если нет → нарушение ADR-O-139

**Acceptance criteria:**
- EpistemicBoundaryProbe находит BUG-DLG-010 (DM читает L2 memory) при его наличии
- SomaticGateProbe находит нарушение порядка Body → Somatic → Semantic

#### Этап 3.5: Silent Failure Detector (4 часа)

**Files:** `probes/silent_failure_probe.py`

1. AST-сканер `backend/app/`:
   - `try: ... except Exception: pass` → WARN
   - `try: ... except: pass` (bare) → ERROR
   - `try: ... except Exception: return None` без логирования → WARN
2. Whitelist для известных-безопасных cases (например, optional imports).
3. Запуск в CI (не в production — overhead слишком велик для runtime).

**Acceptance criteria:**
- На v6.8 находит ≤ 7 silent failures (соответствует аудиту)
- При добавлении нового `except: pass` — CI падает

#### Этап 3.6: Probe Alerts и Dashboard (4 часа)

**Files:** `probes/probe_alerts.py`, изменения в `backend/app/api/routes.py`

1. `ProbeAlerts` — настраиваемые действия при критических нарушениях:
   - Webhook в Discord/Slack (если настроено)
   - `logger.error` с полным контекстом
   - Increment counter в `prometheus` (если настроено)
   - При N нарушениях за M тиков → `SimulationIntegrityError` (как ADR-INV-DEF требует)
2. `/api/probes/dashboard` endpoint:
   - Текущий статус всех probes
   - История за последние 100 тиков
   - Top-5 нарушителей

**Acceptance criteria:**
- Dashboard доступен на `/api/probes/dashboard`
- Алерты работают в dev-режиме (логи)

### 3.5. Метрики успеха

| Метрика | Baseline (v6.8) | Цель (v6.9) |
|---------|-----------------|-------------|
| Real-time probes | 0 | 12+ |
| Probe overhead на тик | 0 ms | ≤ 10 ms |
| Detect regression без LLM аудита | 0% | 80%+ |
| Post-mortem анализ (CausalObserver) | вручную, post-hoc | automatic, real-time |
| `/api/probes/dashboard` | не существует | live |

---

## 4. ПОДСИСТЕМА 4: ADR-NET (DEPENDENCY GRAPH)

### 4.1. Цель

Превратить ADR из текстовых markdown-файлов в **traversable dependency graph**, который позволит:
1. Ответить "какие ADR ломаются, если я поменяю X?"
2. Detect конфликты между ADR автоматически
3. Visualize влияние одного решения на всю систему
4. Любому новому LLM быстро понять "что связано с чем"

### 4.2. Принцип

Каждый ADR получает **машинно-читаемую metadata-секцию** (YAML front-matter), которая парсится в граф. Текст остаётся для человека, metadata — для инструментов.

### 4.3. Формат ADR v2.0

**Текущий формат (пример из `ADR Master Index`):**
```markdown
**L9: Spatial SSOT & Factory Law** (ADR-008, 048, S82.0, TZ04-4, O-314)
`SpatialFactory.build_for_campaign()` — единственный сборщик графа...
- Taboo: ❌ Прямая сборка `SpatialService` в обход фабрики. ...
- Files: spatial_factory.py, spatial_query_service.py, domain/movement.py
```

**Новый формат (с metadata):**
```markdown
---
adr_id: ADR-O-314
title: Actor-Agnostic Spatial Contract
status: ACTIVE
domain: DOM-04
laws: [L9]
supersedes: [ADR-048, ADR-008]
superseded_by: []
depends_on: [ADR-O-302, ADR-128]
conflicts_with: []
related_to: [ADR-TRAV-FSM, ADR-O-139]
files:
  - path: backend/app/services/spatial/spatial_factory.py
    role: IMPLEMENTS
  - path: backend/app/services/spatial/spatial_query_service.py
    role: IMPLEMENTS
  - path: backend/app/domain/movement.py
    role: DEFINES
  - path: backend/app/services/scene_state_manager.py
    role: CONSUMES
invariants: [SC-1, SC-2, SC-3, SC-4, SC-5, SC-6, SC-7, SC-8]
probes: [spatial_coherence_probe]
ipt_tests: [test_inv_spatial_coherence]
introduced_in_session: S82
last_modified_session: S147
---

# ADR-O-314: Actor-Agnostic Spatial Contract

## Контекст
...текст для человека...

## Решение
...текст для человека...

## Taboos
❌ Прямая сборка `SpatialService` в обход фабрики
...
```

### 4.4. Архитектура

```
backend/app/services/adr_net/
├── __init__.py
├── adr_parser.py              # Парсинг YAML front-matter из .md файлов
├── adr_graph.py               # NetworkX-граф зависимостей
├── adr_conflict_detector.py   # Детектор конфликтов
├── adr_query.py               # Query API: "что ломается, если я поменяю X?"
├── adr_visualizer.py          # Graphviz / Mermaid render
└── adr_cli.py                 # CLI для запросов
```

**ADR Graph schema (NetworkX MultiDiGraph):**

```
Nodes:
  - ADR nodes: {adr_id, title, status, domain, laws, session}
  - File nodes: {path, role}
  - Invariant nodes: {invariant_id, severity}
  - Probe nodes: {probe_name}
  - IPT test nodes: {test_name}

Edges:
  ADR -[SUPERSEDES]-> ADR
  ADR -[DEPENDS_ON]-> ADR
  ADR -[CONFLICTS_WITH]-> ADR
  ADR -[RELATED_TO]-> ADR
  ADR -[IMPLEMENTS]-> File
  ADR -[DEFINES]-> Invariant
  ADR -[ENFORCES]-> Probe
  ADR -[TESTED_BY]-> IPTTest
  File -[CONSUMES]-> File (import graph)
```

### 4.5. Этапы реализации

#### Этап 4.1: ADR Parser (6 часов)

**Files:** `backend/app/services/adr_net/adr_parser.py`

1. Парсинг YAML front-matter из всех `.md` файлов в `docs/`:
   - `docs/ADR (Architecture Decision Records).md` (master index)
   - `docs/Causal_Contract_v2.0.md` (canonical law)
   - Отдельные ADR-файлы (если есть)
2. Извлечение metadata-полей (см. формат выше).
3. Backward-compatible: ADR без YAML front-matter парсятся из текста (regex для `**L9: ... (ADR-008, 048, ...)**`).
4. Тесты: парсинг всех 21 law из master index.

**Acceptance criteria:**
- Все 21 law распарсены в `ADRNode` объекты
- Backward-compatible парсинг для ADR без metadata
- 100% coverage в unit tests

#### Этап 4.2: ADR Graph (8 часов)

**Files:** `backend/app/services/adr_net/adr_graph.py`

1. Построение NetworkX MultiDiGraph из распарсенных ADR.
2. Node types: `ADRNode`, `FileNode`, `InvariantNode`, `ProbeNode`, `IPTTestNode`.
3. Edge types: `SUPERSEDES`, `DEPENDS_ON`, `CONFLICTS_WITH`, `RELATED_TO`, `IMPLEMENTS`, `DEFINES`, `ENFORCES`, `TESTED_BY`.
4. Graph persistence: JSON-сериализация в `docs/_adr_graph.json` (для быстрой загрузки без повторного парсинга).
5. Incremental update: при изменении ADR-файла пересобирается только затронутая часть графа.

**Acceptance criteria:**
- Граф строится за < 1 секунду
- JSON-сериализация ≤ 100 KB
- Graph query "соседи ADR-O-314" — <10ms

#### Этап 4.3: Conflict Detector (6 часов)

**Files:** `backend/app/services/adr_net/adr_conflict_detector.py`

1. **Static conflicts:**
   - ADR с `status=ACTIVE` и `superseded_by=[]`, но другой ADR ссылается на него как на superseded
   - ADR с `conflicts_with` на другой ADR, но без явного разрешения
   - Файл в `IMPLEMENTS` двух ADR с разными `role`
2. **Dynamic conflicts:**
   - ADR требует `random.*` запрет, но в `files` есть `.py` с `random.choice`
   - ADR требует `time.time()` запрет, но в `files` есть `time.time()`
   - ADR требует `try/except: pass` запрет, но в `files` есть такой паттерн
3. Запуск в CI: `python -m app.services.adr_net.adr_cli check-conflicts`.

**Acceptance criteria:**
- На v6.8 находит 0 static conflicts (если есть — bug)
- Находит динамические конфликты на основе probes (Subsystem 3)
- CI failing при любом конфликте

#### Этап 4.4: Query API (8 часов)

**Files:** `backend/app/services/adr_net/adr_query.py`, `adr_cli.py`

1. Query methods:
   - `what_breaks_if_i_change(file_path)` → список ADR, которыеdepend от этого файла
   - `what_breaks_if_i_change_adr(adr_id)` → список ADR, которые зависят
   - `who_enforces(invariant_id)` → ADR + probe + IPT test
   - `conflicts_of(adr_id)` → ADR, с которыми конфликтует
   - `ancestry_of(adr_id)` → цепочка supersedes до корня
   - `files_touched_by(domain)` → все файлы DOM-XX
2. CLI:
   ```
   python -m app.services.adr_net.adr_cli impact --file backend/app/services/tick_orchestrator.py
   python -m app.services.adr_net.adr_cli ancestry --adr ADR-O-314
   python -m app.services.adr_net.adr_cli conflicts
   python -m app.services.adr_net.adr_cli visualize --output docs/_adr_graph.png
   ```

**Acceptance criteria:**
- CLI работает для всех 4 команд
- Query `impact --file tick_orchestrator.py` возвращает осмысленный список (5+ ADR)
- Визуализация генерирует PNG/Mermaid

#### Этап 4.5: Visualizer (4 часа)

**Files:** `backend/app/services/adr_net/adr_visualizer.py`

1. Graphviz render (через `networkx.drawing.nx_pydot`):
   - Цвет по domain (DOM-01 = blue, DOM-02 = green, etc.)
   - Толщина edge по `severity` (DEPENDS_ON = thin, CONFLICTS_WITH = thick red)
2. Mermaid render для Markdown:
   ```mermaid
   graph LR
   ADR-O-314 -->|DEPENDS_ON| ADR-O-302
   ADR-O-314 -->|SUPERSEDES| ADR-048
   ADR-O-314 -->|IMPLEMENTS| spatial_factory.py
   ```
3. Авто-генерация `docs/_adr_graph.md` с Mermaid-диаграммой.

**Acceptance criteria:**
- PNG генерируется < 2 секунды
- Mermaid рендерится в GitHub Markdown
- Граф читаем (не "волоссяной шар")

#### Этап 4.6: Migration всех ADR в metadata-формат (12 часов)

**Files:** `docs/ADR (Architecture Decision Records).md` + все ADR-файлы

1. Для каждого из 21 law добавить YAML front-matter.
2. Прогнать через `adr_parser` — убедиться, что все парсится.
3. Прогнать через `adr_conflict_detector` — убедиться, что 0 конфликтов.
4. Зафиксировать в `docs/_adr_graph.json`.

**Acceptance criteria:**
- Все 21 law имеют metadata
- Граф строится без ошибок
- 0 конфликтов

### 4.6. Метрики успеха

| Метрика | Baseline (v6.8) | Цель (v6.9) |
|---------|-----------------|-------------|
| ADR с metadata | 0 | 21 (100%) |
| Traversable dependencies | 0 | Все |
| Conflict detection | вручную | automatic |
| "What breaks if I change X" query | N/A | <10ms |
| Время для нового LLM понять архитектуру | 2-3 часа чтения | 15 минут (graph + query) |

---

## 5. ИНТЕГРАЦИЯ ВСЕХ 4 ПОДСИСТЕМ

### 5.1. Поток данных

```
[Player Input]
      ↓
[TickOrchestrator.execute]
      ↓
   Phase 0-9 (core pipeline)
      ↓
[ReplayRecorder.record] ←─ Subsystem 2 (Replay)
      ↓
[ProbeRunner.run_all] ←──── Subsystem 3 (Causal Probes)
      ↓
[Phase 10: Commit]
      ↓
[IPT + PBT in CI] ←──────── Subsystem 1 (Property-Based Tests)
      ↓
[ADR-Net check] ←─────────── Subsystem 4 (Dependency Graph)
```

### 5.2. Конфигурация

В `backend/app/core/config.py`:

```python
class Settings(BaseSettings):
    # Subsystem 1: PBT
    pbt_enabled: bool = True
    pbt_max_examples_ci: int = 1000
    pbt_max_examples_ipt: int = 200
    
    # Subsystem 2: Replay
    replay_mode: Literal["off", "passive", "active"] = "passive"
    replay_playback: bool = False  # True для replay
    replay_llm_cache: bool = True
    
    # Subsystem 3: Causal Probes
    probes_enabled: bool = True
    probes_fail_threshold: int = 3  # N нарушений за M тиков
    probes_fail_window: int = 100   # M тиков
    probes_dashboard: bool = True
    
    # Subsystem 4: ADR-Net
    adr_net_strict: bool = False  # True в CI — fail при конфликтах
    adr_net_visualize: bool = False  # True для docs build
```

### 5.3. CI Pipeline

```yaml
# .github/workflows/ci.yml (или эквивалент)
jobs:
  test:
    steps:
      - run: python backend/tests/IPT.py  # включает PBT
      - run: python -m app.services.adr_net.adr_cli check-conflicts
      - run: python -m app.services.probes.probe_runner --ci-mode
      - run: python -m app.services.replay.replay_cli play --session latest --max-drift 0
```

---

## 6. ПЛАН РЕАЛИЗАЦИИ (ОБЩИЙ)

### 6.1. Порядок внедрения

Подсистемы можно реализовывать **параллельно**, но с приоритетом:

| Приоритет | Подсистема | Зависимость | Время |
|-----------|------------|-------------|-------|
| 1 | Subsystem 4 (ADR-Net) | Независима | 44 часа |
| 2 | Subsystem 3 (Causal Probes) | Зависит от ADR-Net для metadata | 38 часов |
| 3 | Subsystem 2 (Replay) | Независима, но использует probes для записи | 42 часа |
| 4 | Subsystem 1 (PBT) | Зависит от Replay (для shrink) и ADR-Net (для invariant mapping) | 34 часа |

**Итого: ~158 часов** чистой работы (~4 недели при 40-часовой неделе, или ~8 недель при 20-часовой).

### 6.2. Минимальный viable infrastructure (MVI)

Если нет времени на все 4 подсистемы сразу — минимальный набор:

1. **Subsystem 1 (PBT), Этапы 1.1-1.3** (18 часов) — базовые property tests на главные инварианты.
2. **Subsystem 3 (Causal Probes), Этапы 3.1-3.2** (16 часов) — ProbeRunner + 5 базовых probes.
3. **Subsystem 4 (ADR-Net), Этапы 4.1-4.2** (14 часов) — парсер + граф без визуализации.

**MVI: ~48 часов** (1-2 недели). Уже даёт:
- Property-based тесты на главные инварианты
- Real-time probes в production
- Traversable ADR-graph

### 6.3. Когда внедрять

**Лучшее время:** между v6.9 (стабилизация) и v7.0 (Vertical Slice). Это даст:
- Стабильный baseline для разработки инфраструктуры
- Инфраструктуру, готовую поддержать Prophecy System (v7.5) и Generational Depth (v9.0)

**Худшее время:** во время разработки Prophecy System. Это создаст dual-task pressure и обе задачи пострадают.

### 6.4. Критерии готовности инфраструктуры

MVI считается готовой, когда:

- [ ] 5+ property tests проходят на 1000 примеров каждый
- [ ] 5+ probes активны в `passive` mode, 0 violations на v6.9
- [ ] ADR-Net строится <1 сек, 21 law распарсен
- [ ] Любой новый LLM может за 15 минут понять архитектуру через `adr_cli visualize` + `adr_cli impact`

Полная инфраструктура (все 4 подсистемы) считается готовой, когда дополнительно:

- [ ] Replay воспроизводит записанную сессию с 0 drift
- [ ] Drift Laboratory может A/B сравнивать любой commit
- [ ] CI падает при любом `try/except: pass` или `random.*` в kernel layer
- [ ] `/api/probes/dashboard` live

---

## 7. ОЖИДАЕМЫЙ ЭФФЕКТ

### 7.1. Для LLM-архитектора

| До инфраструктуры | После |
|-------------------|-------|
| 2-3 часа на поиск бага в логах | <5 минут через replay |
| 30-60 мин на воспроизведение бага | <2 минуты через `replay_cli play` |
| Ручной аудит 167 файлов на `except: pass` | Автоматический probe, 0ms |
| "Я не помню, мы фиксили это раньше?" | Seed corpus + replay store: "да, тик 472, commit abc123" |
| "Какие ADR ломаются, если я поменяю decision_hub?" | `adr_cli impact --file decision_hub.py` <10ms |
| Слепота на emergent behavior | Probe alerts при накоплении дрейфа |

### 7.2. Для проекта

| До | После |
|----|-------|
| Зависимость от одного LLM | Любой LLM может войти за 15 минут |
| Баги находятся пост-фактум | Баги находятся в реальном времени |
| Regressions замечаются через недели | Regressions замечаются в CI <5 минут |
| Архитектура в голове одного LLM | Архитектура в traversable graph |
| Сложность растёт линейно с кодом | Сложность контролируется через probes |

### 7.3. Для будущего

После внедрения этой инфраструктуры:
- **v7.0 (Vertical Slice)** — разрабатывается с real-time probe feedback
- **v7.5 (Prophecy System)** — каждое изменение в belief layer автоматически проверяется через PBT
- **v8.0 (WorldChronicle)** — новый domain добавляется с auto-generated property tests
- **v9.0 (Generational Depth)** — replay позволяет отлаживать emergent bugs через 1000 тиков

**Граница полезности LLM сдвигается с v8.5-v9.0 до v9.5-v10.0** — за счёт того, что инфраструктура берёт на себя memory + edge-case detection + invariant monitoring.

---

## 8. РИСКИ И МИТИГАЦИЯ

| Риск | Вероятность | Impact | Митигация |
|------|-------------|--------|-----------|
| Replay overhead в production | Medium | High | `passive` mode с sampling (запись 1 из 10 тиков) |
| Probe false-positives | Medium | Medium | Whitelist для известных safe-patterns |
| ADR metadata устаревает | High | Low | Auto-sync: parser проверяет `files` в ADR против реальных `*.py` |
| Hypothesis слишком медленный | Low | Medium | `max_examples=200` в IPT, `1000` в CI |
| LLM cache промахи при replay | Medium | High | Hash включает все значимые поля prompt; cache miss = error |
| Graph visualization unreadable | Medium | Low | Filter по domain; interactive viewer (dash) для большого графа |

---

## 9. ФИНАЛЬНЫЕ ЗАМЕЧАНИЯ

### 9.1. Почему это не over-engineering

Эта инфраструктура — **не для текущего ENIGMA**. Она для **будущего ENIGMA** — того, который дойдёт до v9.0, v10.0 и далее. Без неё каждый новый LLM будет:
1. Тратить 2-3 часа на чтение ADR
2. Делать те же ошибки, что предыдущий
3. Не иметь возможности воспроизвести emergent bugs

Это **капитал**. Как ADR — капитал для памяти, так и эта инфраструктура — капитал для **масштабируемости LLM-разработки**.

### 9.2. Приоритет MVI

Если нет ресурсов на полное внедрение — реализуй **MVI** (Subsystem 1 + 3 + 4, без Replay). Это даст 80% ценности за 30% effort.

### 9.3. Что НЕ делать

- **Не строить custom test framework.** Hypothesis существует, используй его.
- **Не строить custom observability stack.** Prometheus + Grafana работают.
- **Не строить custom graph database.** NetworkX + JSON достаточно для 100-200 ADR.
- **Не делать эту инфраструктуру до стабилизации v6.9.** Сначала баги, потом infrastructure.

### 9.4. Когда остановиться

Подсистемы 1-4 имеют естественную точку убывающей отдачи:
- 5 probes → 12 probes → 20 probes → больше не помогает
- 21 ADR в graph → 50 ADR → 100 ADR → graph становится нечитаемым
- 5 property tests → 15 → 30 → время CI становится неприемлемым

После MVI + полной инфраструктуры — **остановиться и сосредоточиться на game design**, не на infrastructure.

---

## 10. ИТОГО

| Подсистема | Часов | Файлов новых | Файлов изменённых | Сложность |
|------------|-------|--------------|-------------------|-----------|
| 1. Property-Based IPT | 34 | 12 | 1 (IPT.py) | Medium |
| 2. Replay System | 42 | 6 | 3 (tick_orch, llm/router, config) | High |
| 3. Causal Probes | 38 | 16 | 2 (tick_orch, routes) | Medium |
| 4. ADR-Net | 44 | 6 | 21 (ADR files) | Medium |
| **Итого** | **158** | **40** | **27** | — |

**MVI (рекомендуется первым):**
- Subsystem 1 (Этапы 1.1-1.3): 18 часов
- Subsystem 3 (Этапы 3.1-3.2): 16 часов
- Subsystem 4 (Этапы 4.1-4.2): 14 часов
- **Итого MVI: 48 часов** (1-2 недели)

После MVI — evaluate, стоит ли достраивать остальное.

---

## 11. СЛЕДУЮЩИЕ ШАГИ

1. **Подтверди приоритет** — MVI сначала, или полная инфраструктура?
2. **Подтверди тайминг** — после v6.9 стабилизации, или параллельно?
3. **Выбери ответственного** — ты сам, или делегировать LLM-сессии?
4. **Создай ветку** `V.0.5.3.7.0_infrastructure` от v6.9
5. **Начни с Subsystem 4 (ADR-Net)** — она не требует code changes в backend, только docs + parsing tooling. Самый безопасный старт.

---

*Документ подготовлен на основе аудита v6.8, существующей инфраструктуры (IPT, CausalObserver, DriftLaboratory, L1Chronicle, dna_history.jsonl) и архитектурных принципов CAUSAL_CONTRACT v2.0. Все file:line references точны на v6.8.*
