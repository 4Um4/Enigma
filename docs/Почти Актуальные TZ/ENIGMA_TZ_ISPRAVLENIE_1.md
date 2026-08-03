# ТЗ: ПОЛНОЕ ВОССТАНОВЛЕНИЕ РАБОТОСПОСОБНОСТИ ENIGMA V.0.5.3.6.8

> **Документ:** Техническое задание на исправление дефектов кода
> **Версия проекта:** Enigma-V.0.5.3.6.8
> **Дата анализа:** 2026-08-03
> **Метод:** Глубокий статический анализ исходников + сверка с CAUSAL_CONTRACT v2.0, ADR Master Index, архитектурными устоями
> **Объём:** 80 дефектов (8 Critical, 24 High, 28 Medium, 20 Low)
> **Аудит покрыл:** 5 доменов, ~399 .py файлов бэкенда, 24 .py файла фронтенда, лог-файлы сессий
> **Принцип:** Документируются ТОЛЬКО активные дефекты V.0.5.3.6.8 (STILL_BROKEN из V.0.5.3.6.7 + NEW, введённые в V.0.5.3.6.8). Уже исправленные дефекты не упоминаются.

---

## 0. EXECUTIVE SUMMARY

Кодовая база ENIGMA V.0.5.3.6.8 находится в состоянии **«частично залеченного рефакторинга»** — после V.0.5.3.6.7 было исправлено ~30 дефектов (dead code в `execute()`, `LifeEngine.__init__` indentation, `task_scheduler` KernelRNG миграция, `_tick_scenes` plural, dead-NPC фильтр до Phase 1 и др.), но параллельно **внесено 38 новых дефектов** и оставлено **42 STILL_BROKEN бага**. Четыре ключевые подсистемы игры функционально сломаны, хотя формально компилируются и проходят часть IPT-тестов.

### Пять ключевых симптомов, которые видит игрок в V.0.5.3.6.8

| # | Симптом | Корневая причина (Top-3 контрибьютора) | Домен |
|---|---------|----------------------------------------|-------|
| **S-1** | Игрок атакует/угрожает/приказывает — NPC реагируют как на `WORLD_TICK` (idle-режим) | BUG-CORE-003 (`hub_event` не доходит до `TickState` — игрок невидим NPC pipeline), BUG-CORE-019 (proactive drives падает с `TypeError`), BUG-DLG-010 (DM-agent читает `narrative_cache` — L16) | Core + Dialogue |
| **S-2** | Affective decay не работает — травмы/шок永不 затухают | BUG-PERC-030 (`decay_affective_imprints` падает с `NameError: 'replace'`), BUG-PERC-031 (`ResonanceProfile` без `@dataclass` — `TypeError`), BUG-PERC-032 (`PhysiologyDecayHandler` читает `body_state` из snapshot, где его нет) | Perception + Affective |
| **S-3** | Бой недетерминирован + HP Double Truth | BUG-CORE-021/BUG-PERC-003 (`impact_engine` `random.Random` с UUID-seed), BUG-PERC-005 (`apply_damage` пишет `target["hp"]` напрямую), BUG-PERC-006 (`apply_healing` воскрешает мёртвых), BUG-PERC-037 (`ConditionEngine` пишет HP напрямую) | Combat + Physiology |
| **S-4** | NPC не могут найти кровать/верстак в другой зоне + A* на stale overlay | BUG-SPATIAL-029 (`SpatialFactory._cache` возвращает stale overlay), BUG-SPATIAL-015 (`resolve_affordance` не извлекает `zone_id`), BUG-SPATIAL-030 (`cluster_relation` всегда "adjacent") | Spatial |
| **S-5** | HTTP `/api/game/action` не возвращает `visual_dto`/`audible_dto`/`player_body_topology` | BUG-FB-030 (`run_turn` rebuild без трёхканальных DTO), BUG-FB-031 (`_run_pipeline` не пробрасывает `world_snapshot`), BUG-FB-001 (SSE `done` без `world_snapshot`) | Frontend |

### Главный архитектурный диагноз

В проекте V.0.5.3.6.8 выполнено 4 «незавершённые» миграции и 3 новых регрессии:

1. **Миграция `TickState`/`TickMutation` (ADR-TZ09-1) →** завершена на 90%. `hub_event`-мост между GameLoop `TickBuffer` и ядерным `_TickContext` НЕ построен (BUG-CORE-003) — ядро не видит действия игрока. `_TickContext` dataclass не имеет поля `hub_event`, `create_tick_context()` не принимает параметр `hub_event`, `pipeline_runner.build_tick_state` читает `getattr(ctx, "hub_event", None)` → всегда `None`.

2. **Миграция KernelRNG (ADR-O-301) →** завершена для `TaskScheduler` и `ResolutionEngine`, но **6 новых файлов** используют `random.*` (impact_engine, combat_math, market_state, traveller, npc_conversation, dm_response_normalizer, attention_layer, rules_agent, llama_cpp_provider) — replay determinism нарушен.

3. **Миграция Three-Channel Presentation (ADR-O-331, L16.1) →** `WorldSnapshotDTO` расширен `VisualDTO`/`AudibleDTO`, Phase 9 корректно их собирает, но `run_turn` и SSE `done` **rebuild-ят snapshot без этих DTO** (BUG-FB-030, BUG-FB-001). Фронтенд никогда не получает трёхканальные данные для player action.

4. **Миграция HP Unification (ADR-HP-UNIFICATION, L12) →** `body_state["current_hp"]` объявлен SSOT, но **4 файла** продолжают писать `target["hp"]` / `p["hp"]` напрямую (combat_math, combat_service, condition_engine) — Double Truth жив.

5. **Новая регрессия: Affective Decay (BUG-PERC-030/031/032) →** три каскадных бага в V.0.5.3.6.8 полностью отключают затухание аффективных травм. `decay_affective_imprints` падает с `NameError`, `ResonanceProfile` не конструируется, `PhysiologyDecayHandler` читает `body_state` из snapshot, где его нет.

6. **Новая регрессия: `openai_compatible_provider.py` (BUG-DLG-041) →** сломанный импорт `from app.services.llm.llm_provider import LlmProvider` — файл не существует. `ProviderType.OPENAI` полностью неработоспособен.

7. **Новая регрессия: SpatialFactory cache (BUG-SPATIAL-029) →** кэшированный `SpatialService` возвращает STALE overlay (`reserved_nodes`, `crowd_density`, `risk_zones`). A* pathfinding и `resolve_node` используют устаревшие данные каждый тик.

---

## 1. КАРТА ДЕФЕКТОВ ПО ДОМЕНАМ

| Домен | Кол-во багов | Critical | High | Medium | Low | Ключевые файлы |
|-------|--------------|----------|------|--------|-----|----------------|
| DOM-01: Core Tick Pipeline | 15 | 1 | 4 | 6 | 4 | `tick_orchestrator.py`, `pipeline_runner.py`, `npc_tick_pipeline.py`, `life_engine.py`, `phase_2_world_tick.py` |
| DOM-02: Dialogue / LLM / DM-Agent | 22 | 5 | 7 | 6 | 4 | `dm_agent.py`, `dm_phase.py`, `dialogue_queue.py`, `dialogue_executor.py`, `mock_provider.py`, `openai_compatible_provider.py` |
| DOM-03: Perception / Combat / Affective | 18 | 5 | 6 | 5 | 2 | `affect.py`, `combat_math.py`, `impact_engine.py`, `physiology_decay_handler.py`, `decision_hub.py`, `condition_engine.py` |
| DOM-04: Spatial / Movement / Traversal | 12 | 1 | 3 | 4 | 4 | `spatial_factory.py`, `spatial_service.py`, `graph_compiler.py`, `projection_engine.py`, `life_engine.py` |
| DOM-07: Frontend / Backend / Persistence | 17 | 2 | 6 | 7 | 2 | `game_loop/__init__.py`, `routes.py`, `routes_debug.py`, `game_loop_bridge.py`, `world_snapshot.py`, `world_scheduler.py` |
| **ИТОГО (с дедупликацией)** | **~80** | **8** | **24** | **28** | **20** | — |

> **Критические баги (Critical, P0):** блокируют основной игровой цикл. Без их исправления игра нефункциональна.
> **Высокий приоритет (High, P1):** серьёзные архитектурные нарушения или сломанные подсистемы.
> **Средний приоритет (Medium, P2):** снижают качество симуляции, но не блокируют.
> **Низкий приоритет (Low, P3):** code hygiene, мёртвый код, cosmetic.

---

## 2. АРХИТЕКТУРНЫЕ НАРУШЕНИЯ (Контрактные)

Следующие баги прямо нарушают `CAUSAL_CONTRACT v2.0` или `ADR Master Index`. Это **не косметика, а разрушение онтологии симуляции**.

| Контракт | Нарушение | Bug ID | Файл |
|----------|-----------|--------|------|
| L2 (Runtime Purity) — `random.*` запрещён, только `KernelRNG` | `ImpactEngine` использует `random.Random(rng_seed)` с `hash()`-seed из UUID | BUG-CORE-021 / BUG-PERC-003 | `impact_engine.py:131` |
| L2 — `random.*` запрещён в kernel/combat | `combat_math.py` fallback к global `random` | BUG-PERC-004 | `combat_math.py:12,50,52,61` |
| L2 — `random.*` запрещён | `market_state.py` + `traveller.py` используют `random.Random()` без seed | BUG-CORE-023 | `market_state.py:97-98`, `traveller.py:117-120` |
| L2 — `random.*` запрещён | `npc_conversation.py` `random.choice` для ambient dialogue | BUG-CORE-024 | `npc_conversation.py:222` |
| L2 — `random.*` запрещён | `dm_response_normalizer.py` `random.choice` | BUG-CORE-025 | `dm_response_normalizer.py:71` |
| L2 — `random.*` запрещён | `attention_layer.py` `random.random()` | BUG-CORE-026 | `attention_layer.py:108,110,120` |
| L2 — `random.*` запрещён | `rules_agent.py` `random.randint` для d20 | BUG-DLG-043 | `rules_agent.py` |
| L2 — `random.*` запрещён | `llama_cpp_provider.py` `random.randint` для LLM seed | BUG-DLG-044 | `llama_cpp_provider.py:163` |
| L2 (Runtime Purity) — `time.time()`/`datetime.now()` запрещён | `DialogueQueue` использует wall-clock `time.time()` для cooldown | BUG-DLG-006 | `dialogue_queue.py:43-50,70,93` |
| L15 — Wall-clock в симуляции запрещён | `world_scheduler.maybe_tick` использует `datetime.now(timezone.utc)` | BUG-FB-012 | `world_scheduler.py:32` |
| L15 — Wall-clock в симуляции запрещён | `WorldSnapshot.created_at = time.time()` + `uuid4()` | BUG-FB-029 | `world_snapshot.py:88-89` |
| L15 — Wall-clock в симуляции запрещён | `EventDTO.create` default `time.time()` + `uuid4()` | BUG-FB-037 | `domain/events.py` |
| L15 — Wall-clock в симуляции запрещён | `WorldProjectionBuffer.project` использует `uuid.uuid4()` | BUG-FB-038 | `world_projection_buffer.py` |
| L15 — Wall-clock в симуляции запрещён | `scene_init._reconcile_elapsed_time` использует `time.time()` | BUG-FB-039 | `scene_init.py` |
| L15 — Wall-clock в симуляции запрещён | `SqlitePersistenceAdapter._upsert` `datetime.now()` для `updated_at` | BUG-FB-040 | `sqlite_persistence_adapter.py` |
| L4 (Silent Failure Prohibition) | `npc_orchestration.py` silent `except Exception: pass` для SpatialFactory | BUG-CORE-020 | `npc_orchestration.py:191-195` |
| L8 (CFRM & Somatic Gate) — Somatic Gate ДО семантического парсинга | Somatic Gate отсутствует до семантического парсинга | BUG-PERC-025 | `decision_hub.py:402-418` |
| L9 (Spatial SSOT) — `player_spatial` мёртв | `life_engine.py:858` читает `player_spatial` как fallback (Double Truth) | BUG-SPATIAL-032 | `life_engine.py:858-872` |
| L9 — `player_spatial` мёртв | `scene_init.py:80` читает `player_spatial` как fallback | BUG-SPATIAL-033 | `scene_init.py:78-82` |
| L10 (Traversal FSM) — `transition_traversal()` единственный владелец lifecycle | `ProjectionEngine` + `EventCompiler` пишут `"status": "MOVING"` напрямую, минуя FSM | BUG-SPATIAL-026 | `projection_engine.py:131-134`, `event_compiler.py:488,657` |
| L11 (Spatial Coherence SC-1...SC-8) | Валидация не реализована как coherent gate | BUG-SPATIAL-036 | `scene_state_manager.py:921` |
| L12 (Physiology & Death Lock) — `body_state["current_hp"]` SSOT для HP | `combat_math.apply_damage` пишет `target["hp"]` напрямую | BUG-PERC-005 | `combat_math.py:300-322` |
| L12 (Death Lock) — DEAD→ALIVE запрещён | `combat_math.apply_healing` воскрешает мёртвых | BUG-PERC-006 | `combat_math.py:325-340` |
| L12 (Death Lock) — Decay для мёртвых запрещён | `AffectiveDecayHandler` не проверяет `life_status=="DEAD"` | BUG-PERC-029 | `affective_decay_handler.py:52-93` |
| L12 — `body_state["current_hp"]` SSOT | `combat_service.py:111` пишет `p["hp"]` напрямую | BUG-PERC-036 | `combat_service.py:111` |
| L12 — Decay для мёртвых + HP SSOT | `ConditionEngine.tick` не проверяет DEAD + пишет HP напрямую | BUG-PERC-037 | `condition_engine.py` |
| L12 — Falsy `body_state` checks запрещены | 5 мест `if body_state:` вместо `is not None` | BUG-PERC-041 | multiple |
| L14 (Epistemic Memory Law) — L2.5 кристаллизация только при `phase_2_events` | Кристаллизация запускается каждый тик без gate | BUG-PERC-014 | `integration.py:380-422` |
| L15 (Frontend Authority) — Backend = единственный источник истины | `routes.py:update_scene_state` принимает `scene_state` от фронта по block-list | BUG-FB-041 | `routes.py:806-831` |
| L15 — Wall-clock запрещён | (см. BUG-FB-012/029/037/038/039/040 выше) | — | — |
| L16 (Epistemic Boundary) — DM-agent читает ТОЛЬКО `observed_state` + `embodied_traces` | DM-agent читает `npc_l2_memory_block` (recalled_facts из `narrative_cache`) | BUG-DLG-010 | `dm_phase.py:65-82`, `dm_agent.py:233-236` |
| L16.1 (Three-Channel Presentation) — `VisualDTO`/`AudibleDTO` независимы | `run_turn` rebuild-ит `WorldSnapshotDTO` без `visual_dto`/`audible_dto`/`player_body_topology` | BUG-FB-030 | `game_loop/__init__.py:1239-1245` |
| L17 (Identity Pipeline) — `L1Chronicle` append-only | `archive_old_events` делает `DELETE FROM l1_chronicle_events` | BUG-PERC-013 | `l1_chronicle.py:240-268` |
| L17 — L1Chronicle UNIQUE constraint | `archive_old_events` не имеет UNIQUE → дубликаты | BUG-FB-044 | `l1_chronicle.py` |
| L21 (Invariant Defense) — `print()` в production запрещён | 35+ `print()` в 11 файлах (spatial, dialogue, frontend) | BUG-FB-036 | multiple |
| CAUSAL_CONTRACT §4.7.48 — `MockProvider` в production запрещён | `MockProvider._pick_response` проверяет `ENIGMA_ENV` вместо `settings.environment` | BUG-FB-021 / BUG-DLG-CAUSAL-4.7.48 | `mock_provider.py:126` |
| CAUSAL_CONTRACT §4.7.49 — Парсинг JSON в DM-агенте запрещён | `dm_agent.py:861` содержит `json.loads` (CJK retry bypasses DMResponseNormalizer) | BUG-DLG-CAUSAL-4.7.49 | `dm_agent.py:861` |
| ADR-O-201 (Dual Rail) — Snapshot Kernel determinism | `WorldSnapshot.snapshot_id = uuid4()`, `created_at = time.time()` — non-deterministic | BUG-FB-029 | `world_snapshot.py:88-89` |

---

## 3. БАГ-КАТАЛОГ ПО ДОМЕНАМ

Ниже приведены все ~80 дефектов с file:line, симптомом, корневой причиной, severity и предлагаемым фиксом. Дублирование симптомов между доменами намеренное — один игрок-видимый симптом часто имеет множественные корневые причины.

---

### 3.1. DOM-01: CORE TICK PIPELINE (15 дефектов)

#### BUG-CORE-003 — `hub_event` НЕ доходит до TickState (player actions невидимы NPC pipeline)
- **Файл:строка:** `backend/app/services/pipeline_runner.py:60` + `backend/app/services/tick_utils.py:314-382` + `backend/app/services/dto.py:78-189`
- **Severity:** Critical (корневая причина S-1)
- **Симптом:** NPC pipeline всегда работает в idle-режиме. Игрок атакует/угрожает/приказывает — NPC не реагируют целенаправленно. `DECISION_HUB` логирует `event=unknown` для всех тиков. MOVE-команды игрока не триггерят `_is_move_command` (`npc_tick_pipeline.py:504-523`). Memory events от действий игрока не создаются (`npc_tick_pipeline.py:272-289`). Это блокирует всю боевку, директивы, MOVE-команды.
- **Причина:** GameLoop устанавливает `ctx.hub_event` (HubEventContext) только на **своём** `TickBuffer` (`game_loop/tick_context.py:55`). Затем `run_npc_orchestration` вызывает `tick_orchestrator.execute(...)` **БЕЗ** параметра `hub_event` (`npc_orchestration.py:200-211`). Внутри `execute()` вызывается `create_tick_context()` (`tick_utils.py:314`), который НЕ принимает и НЕ устанавливает `hub_event`. Сам `_TickContext` dataclass (`dto.py:78-189`) **не имеет** поля `hub_event`. В `pipeline_runner.build_tick_state` (`pipeline_runner.py:60`) делается `hub_event=getattr(ctx, "hub_event", None)` → всегда `None`. В `NpcTickPipeline.run` (`npc_tick_pipeline.py:136`): `_is_player_turn = state.hub_event is not None` → всегда `False`. Каскадно ломаются: hearing perception (строка 173), player-action memory events (строка 272), MOVE-override (строка 504), event_type extraction (строка 487 → "unknown").
- **Фикс (трёхуровневый):**
  1. Добавить `hub_event` field в `_TickContext` (`dto.py`):
     ```python
     @dataclass
     class _TickContext:
         ...
         hub_event: Any = None  # ADR-TZ09-1: player action context
     ```
  2. Добавить параметр `hub_event` в `create_tick_context()` (`tick_utils.py`) и пробросить в `_TickContext`.
  3. Добавить параметр `hub_event` в `TickOrchestrator.execute()`, передать `ctx.hub_event` из `run_npc_orchestration` (`npc_orchestration.py:200-211`):
     ```python
     _loc_result = tick_orchestrator.execute(
         ...,
         hub_event=ctx.hub_event if _loc_id == _active_loc else None,
     )
     ```
- **Статус:** STILL_BROKEN

#### BUG-CORE-013 — `l1_drift_events` всегда пустой в TickMutation
- **Файл:строка:** `backend/app/services/npc/npc_tick_pipeline.py:150` (declaration), `:647` (pass to TickMutation)
- **Severity:** High
- **Симптом:** `pipeline_runner.build_npc_contexts_from_intents` (`pipeline_runner.py:106-108`) содержит мёртвый код: `if mutation.l1_drift_events and _svc and _svc.memory_manager: for _event in mutation.l1_drift_events: _svc.memory_manager.l1_chronicle.append(_event)`. Этот блок НИКОГДА не выполняется, потому что `l1_drift_events` всегда `[]`. L1 Chronicle записи идут через побочные пути (`StateApplicator` directly writes to chronicle, Phase 9 `integration.py` commits `TraitDriftEvent`). Контракт L3 ("Kernel must return final_scene_state for commit" + `l1_drift_events` in TickMutation) нарушен.
- **Причина:** В `NpcTickPipeline.run` переменная `l1_drift_events: List[Any] = []` объявлена на строке 150 и передана в `TickMutation(...)` на строке 647. Между этими строками НЕТ ни одного `l1_drift_events.append(...)`. `StateApplicator.apply()` внутри цикла (строка 620) пишет `TraitDriftEvent` напрямую в `_chronicle.commit_tick_buffer` (`state_applicator.py:822-824`), минуя `l1_drift_events` список.
- **Фикс:** В `NpcTickPipeline.run` собирать `l1_drift_events` из `StateApplicator`. Либо `StateApplicator.apply()` должен возвращать drift events в результате, либо `pipeline_runner` должен читать из `chronicle.diff` после apply:
  ```python
  _drift_before = state.l1_chronicle.query_raw(npc_id) if state.l1_chronicle else []
  _new_state = applicator.apply(state=state_l2, result=decision, campaign_id=state.campaign_id)
  _drift_after = state.l1_chronicle.query_raw(npc_id) if state.l1_chronicle else []
  _new_drifts = _drift_after[len(_drift_before):]
  l1_drift_events.extend(_new_drifts)
  ```
- **Статус:** STILL_BROKEN

#### BUG-CORE-015 — `_apply_drf_scoring_overlay` проверяет `npc_id`, читает `actor_id` (DRF overlay = dead code)
- **Файл:строка:** `backend/app/services/tick_orchestrator.py:1593-1623`
- **Severity:** High
- **Симптом:** DRF scoring overlay никогда не применяется к `communication_intents`. DRF bus stream заполняется claims, но priority интентов не модулируется. NPC решения не получают "causal field bonus" от давления фракций/союзников.
- **Причина:** Код проверяет `hasattr(_intent, "npc_id")` (строка 1593), но читает `_intent.actor_id` (строка 1595). `CommunicationIntent` (`domain/communication.py:69-97`) — frozen dataclass с полями: `speaker`, `audience`, `topic`, `intent_type`, `emotional_state`, `exposure_level`, `semantic_action`, `target_id`, `thread_id`. **НЕТ** `npc_id` **И** `actor_id` **И** `priority`. Поэтому: (1) `hasattr(_intent, "npc_id")` → `False` → `continue`; (2) даже если бы цикл вошёл, `_intent.actor_id` → `AttributeError`; (3) даже если бы `actor_id` существовал, `_intent.priority = ...` на frozen dataclass → `FrozenInstanceError`.
- **Фикс:**
  ```python
  for _intent in intents:
      _npc_id = getattr(_intent, "speaker", None) or getattr(_intent, "actor_id", None)
      if not _npc_id:
          continue
      _npc_claims = [c for c in _claims if c.get("target_npc") == _npc_id or c.get("npc_id") == _npc_id]
      if not _npc_claims:
          continue
      _drf_bonus = sum(c.get("weight", 0.0) for c in _npc_claims) * 0.1
      import dataclasses
      if dataclasses.is_dataclass(_intent) and "priority" in getattr(_intent, "__dataclass_fields__", {}):
          _new_prio = min(1.0, getattr(_intent, "priority", 0.5) + _drf_bonus)
          _intent = dataclasses.replace(_intent, priority=_new_prio)
  ```
- **Статус:** STILL_BROKEN

#### BUG-CORE-016 — `LifeEngine.tick_decisions` — мёртвый код ~500 строк
- **Файл:строка:** `backend/app/services/npc/life_engine.py:640-1140`
- **Severity:** Medium
- **Симптом:** Метод `tick_decisions` (500+ строк) существует, но не вызывается из production кода. Только из 2 тестов: `tests/test_tick_orchestrator_full_loop.py:103` и `tests/sandbox/test_causal_bridge_integration.py:307`. Это нарушает ADR-TZ09 (Pure Reducer) — idle path должен идти через `NpcTickPipeline.run`, а не через `LifeEngine.tick_decisions`.
- **Причина:** После миграции на unified `NpcTickPipeline.run` (`tick_orchestrator.py:1280-1390`, `_phase_5_decision`), `tick_decisions` остался как legacy zombie. Содержит полную копию DecisionHub logic (lines 712-1140), включая социальный drift, motion routing, idle_pressure accumulation — но ничего этого не вызывается.
- **Фикс:** Удалить метод `tick_decisions` целиком (`life_engine.py:640-1140`). Адаптировать 2 теста на использование `NpcTickPipeline.run` через `pipeline_runner.run_pipeline`.
- **Статус:** STILL_BROKEN

#### BUG-CORE-017 — Дублированный dead блок после `return` в `tick_decisions`
- **Файл:строка:** `backend/app/services/npc/life_engine.py:687-702`
- **Severity:** Low (внутри BUG-CORE-016)
- **Симптом:** Внутри мёртвого `tick_decisions` — два идентичных блока `if not npcs: ... return ([], [], [])`. Первый return делает второй блок недостижимым.
- **Фикс:** Удалить второй блок (lines 692-702). Или удалить весь `tick_decisions` (см. BUG-CORE-016).
- **Статус:** STILL_BROKEN

#### BUG-CORE-019 (NEW) — `phase_2_world_tick.py` вызывает `_compute_effective_drives` с неверным числом аргументов
- **Файл:строка:** `backend/app/services/game_loop/phase_2_world_tick.py:74-78`
- **Severity:** High
- **Симптом:** Proactive NPC decisions в `tick_world_proactive` всегда получают `_effective_drives_map = {}` (пустой). NPC не получают L3 projection, `WorldTickEngine` не может рассчитать proactive решения. Симуляция "мира без игрока" теряет driver-based behavior.
- **Причина:** Сигнатура `_compute_effective_drives` (`tick_orchestrator.py:1211-1217`) требует 3 позиционных аргумента + self: `(self, npc_list, tick_number, campaign_id)`. Вызов в `phase_2_world_tick.py:74-78` передаёт только 2: `(tick_ctx.all_npcs_raw, _tick_num)` — `campaign_id` отсутствует. → `TypeError: _compute_effective_drives() missing 1 required positional argument: 'campaign_id'`. Ошибка ловится `except Exception as _ed_err: logger.warning(...)` (строки 79-82) — ловится, но proactive decisions не работают. Регрессия: введена в V.0.5.3.6.8 когда `_compute_effective_drives` получил 3-й параметр `campaign_id` для BUG-CORE-002 fix, но caller не обновили.
- **Фикс:**
  ```python
  _effective_drives_map, _, _ = (
      tick_orchestrator._compute_effective_drives(
          tick_ctx.all_npcs_raw, _tick_num, campaign_id  # ← добавить campaign_id
      )
  )
  ```
- **Статус:** NEW

#### BUG-CORE-020 (NEW) — `npc_orchestration.py` silent `except Exception: pass` для SpatialFactory
- **Файл:строка:** `backend/app/services/game_loop/npc_orchestration.py:191-195`
- **Severity:** Medium (также BUG-SPATIAL-023)
- **Симптом:** Если `SpatialFactory.build_for_campaign` падает (битый editor JSON, неверный campaign_id, race condition в кэше), ошибка полностью проглатывается. NPC в неактивной локации получают `_loc_spatial_svc = None` → movement intents не работают, traversals теряются.
- **Причина:**
  ```python
  _loc_spatial_svc = None
  try:
      from app.services.spatial.spatial_factory import SpatialFactory
      _loc_spatial_svc = SpatialFactory.build_for_campaign(...)
  except Exception:
      pass  # ← L4 violation: Silent Failure Prohibition
  ```
- **Фикс:**
  ```python
  except Exception as _sp_err:
      logger.warning(
          f"[NPC_ORCH] SpatialFactory failed for loc={_loc_id} campaign={campaign_id}: "
          f"{type(_sp_err).__name__}: {_sp_err}"
      )
  ```
- **Статус:** NEW

#### BUG-CORE-021 (NEW) — `impact_engine.py` использует `random.Random(rng_seed)` с недетерминированным seed
- **Файл:строка:** `backend/app/services/combat/impact_engine.py:131` + `backend/app/services/combat/combat_subscriber.py:210-222`
- **Severity:** High (также BUG-PERC-003)
- **Симптом:** Боевые броски d20 (hit/miss, critical), выбор зоны попадания (head/torso/limbs) — недетерминированы между запусками с одинаковым input. Replay determinism нарушен (ADR-O-201 требует 100% replay determinism).
- **Причина:** `impact_engine.py:131`: `rng = random.Random(rng_seed)`. Caller (`combat_subscriber.py:210-222`): `rng_seed=hash((event.id if hasattr(event, "id") else 0, intent.actor_id, intent.target_id)) & 0xFFFFFFFF`. `event.id` генерируется как `str(uuid.uuid4())` в `tick_orchestrator.py:845` → `hash((uuid_str, ...))` различается между запусками.
- **Фикс:** Использовать `KernelRNG` с детерминированным seed на основе (tick, npc_id, salt):
  ```python
  from app.services.npc.kernel_rng import KernelRNG

  def resolve_physical_impact(attacker, defender, intent, tick: int):
      _rng = KernelRNG(tick=tick, npc_id=intent.actor_id, salt=f"combat:{intent.target_id}")
      # использовать _rng.randint, _rng.choices везде
  ```
- **Статус:** NEW

#### BUG-CORE-022 (NEW) — `tick_orchestrator.py` передаёт non-serializable `ctx` в EventDTO payload для TICK_COMPLETED
- **Файл:строка:** `backend/app/services/tick_orchestrator.py:608-617`
- **Severity:** Medium
- **Симптом:** Subscribers `TICK_COMPLETED` (например, `MvpTavernController`) получают EventDTO с `payload["snapshot"]` = полный `_TickContext` object. Любая попытка сериализации (логирование, persistence, SSE-broadcast) упадёт или даст мусор. Deepcopy этого event дублирует ссылки на `npc_services`, `rng_factory`, `event_bus` — потенциальная memory leak.
- **Причина:** `"snapshot": ctx` — `_TickContext` содержит services, rng_factory, event_bus, etc.
- **Фикс:** Передать только serializable поля:
  ```python
  payload={
      "tick_number": ctx.tick_number,
      "campaign_id": ctx.campaign_id,
      "scene_state": ctx.scene_state,
      "npc_contexts": ctx.npc_contexts,
  }
  ```
- **Статус:** NEW

#### BUG-CORE-023 (NEW) — `economy/market_state.py` и `economy/traveller.py` используют `random.Random()` без seed
- **Файл:строка:** `backend/app/services/economy/market_state.py:97-98` + `backend/app/services/economy/traveller.py:117-120`
- **Severity:** Medium
- **Симптом:** Экономическая симуляция (цены, спрос, travelers) полностью недетерминирована. Один и тот же save дает разные экономические результаты между запусками.
- **Причина:** `self._rng = rng or random.Random()` — `random.Random()` без seed = system time entropy.
- **Фикс:** Использовать `KernelRNG` с детерминированным seed:
  ```python
  def __init__(self, tick: int, campaign_id: str = ""):
      from app.services.npc.kernel_rng import KernelRNG
      self._rng = KernelRNG(tick=tick, npc_id=f"market_{campaign_id}", salt="economy")
  ```
- **Статус:** NEW

#### BUG-CORE-024 (NEW) — `execution/npc_conversation.py` использует `random.choice` для ambient dialogue
- **Файл:строка:** `backend/app/services/execution/npc_conversation.py:222`
- **Severity:** Medium (также BUG-DLG-054)
- **Симптом:** Ambient NPC-NPC диалоги (без LLM) выбирают фразы недетерминированно. Один и тот же tick даёт разные реплики между запусками.
- **Причина:** `text = random.choice(_phrases)` — global random.
- **Фикс:** Принять `rng: KernelRNG` параметром в `NpcConversation.execute()` или использовать `KernelRNG(tick, npc_id=speaker_id, salt="ambient_dialogue")`.
- **Статус:** NEW

#### BUG-CORE-025 (NEW) — `verbalization/dm_response_normalizer.py` использует `random.choice`
- **Файл:строка:** `backend/app/services/verbalization/dm_response_normalizer.py:71`
- **Severity:** Medium (также BUG-DLG-053)
- **Симптом:** Нормализация DM-ответа (выбор между синонимами) недетерминированна. Может приводить к различным "финальным" DM-ответам при одинаковом LLM output.
- **Причина:** `return random.choice([...])` — global random.
- **Фикс:** Использовать `KernelRNG` с salt="dm_normalizer", или сделать выбор детерминированным (first-match).
- **Статус:** NEW

#### BUG-CORE-026 (NEW) — `player_cognition/attention_layer.py` использует `random.random()`
- **Файл:строка:** `backend/app/services/player_cognition/attention_layer.py:108, 110, 120`
- **Severity:** Medium (также BUG-PERC-042)
- **Симптом:** Attention layer игрока (вероятность заметить событие) недетерминированна.
- **Причина:** `return random.random() < 0.95` (line 108), `return random.random() < 0.05` (line 110), `return random.random() < probability` (line 120) — global random.
- **Фикс:** Использовать `KernelRNG(tick=current_tick, npc_id="player", salt="attention")` (player is treated as npc_id="player" elsewhere).
- **Статус:** NEW

#### BUG-CORE-027 (NEW, Low) — `reaction_rules.py:75` использует `random.random()` в dead code
- **Файл:строка:** `backend/app/services/reaction/reaction_rules.py:75`
- **Severity:** Low
- **Симптом:** MicroEvents (объект уронил, действие прервано) генерируются недетерминированно — НО `compute_reaction_events` вызывается только из `ReactionResolver.resolve()`, который **не вызывается** ни из `npc_tick_pipeline.py`, ни из других production мест (dead code path).
- **Фикс:** Удалить dead code path (`resolve_reactions`, `compute_reaction_events`), либо подключить к pipeline с `KernelRNG`.
- **Статус:** NEW

#### BUG-CORE-028 (NEW, Low) — Dead `import random` после BUG-CORE-011/012 fix
- **Файл:строка:** `backend/app/services/game_loop/task_scheduler.py:172` + `backend/app/services/npc/resolution_engine.py:23`
- **Severity:** Low (также BUG-DLG-047)
- **Симптом:** Мёртвый импорт `random` остался после миграции на KernelRNG. Lint-noise и потенциальный триггер для случайного использования random в будущем.
- **Фикс:** Удалить `import random` из обоих файлов.
- **Статус:** NEW

---

### 3.2. DOM-02: DIALOGUE / LLM / DM-AGENT (22 дефекта)

#### BUG-DLG-002 — DM contract ValueError → silent "Ничего не произошло"
- **Файл:строка:** `backend/app/agents/dm_agent.py:245-249`
- **Severity:** Critical
- **Симптом:** Если `extract_player_target` не резолвит "трактирщику"/"трактирщика" против `name_forms` NPC, `shared_context.player_target_id` остаётся `""`. На любом non-first tick (`_is_intro=False`) с пустым STM DM кидает `ValueError` → fallback на `MSG_NOTHING_HAPPENED`. Игрок видит "Ничего не произошло" на любые диалоги с NPC, чьё имя не резолвится.
- **Причина:** Hard contract предотвращает LLM-галлюцинации NPC-ответов, но precondition (`_has_target=False`) — неправильный сигнал: смешивает "игрок никого не адресовал" с "target resolver упал".
- **Фикс:** (a) Если `raw_input` содержит известное русское существительное/роль ("трактирщик", "кузнец", "страж"), но resolver вернул пусто — логировать WARN и продолжать с generic narrative вместо raise. (b) Лучше — ослабить gate до "если игрок никого не адресовал И нечего нарративить (нет событий, нет NPC moves)".
- **Статус:** STILL_BROKEN

#### BUG-DLG-004-partial — `_evt_map` missing `player_flees` → PLAYER_SPOKE bypass
- **Файл:строка:** `backend/app/services/game_loop/phase_1_input.py:276-283, 335-348`
- **Severity:** Critical
- **Симптом:** Игрок пишет `убежать` / `сбежать`. IntentCompressor классифицирует как `FLEE`. Override ставит `_raw_type = "player_flees"`. Но `_evt_map.get("player_flees", EventType.PLAYER_SPOKE)` fallback'ит в `PLAYER_SPOKE`. → `ReactionSubscriber`, `CombatSubscriber` никогда не получают событие. NPC не реагируют на бегство игрока. 4 из 5 ключей (`player_threatens`, `player_steals`, `player_insults`, `intimidation`) добавлены в V.0.5.3.6.8, но `player_flees` остался.
- **Причина:** `_evt_map` покрывает `dialogue`, `player_interacts`, `attack`, `player_attacks`, `move`, `stealth`, `player_threatens`, `player_steals`, `player_insults`, `intimidation`. Override map (`_IC_PRIORITY_MAP`) эмитит `player_flees`, но в `_evt_map` его нет.
- **Фикс:**
  ```python
  "player_flees": EventType.PLAYER_MOVED,
  ```
- **Статус:** STILL_BROKEN (partial fix)

#### BUG-DLG-005 — DialogueQueue drains only 1 task per tick, enqueues all
- **Файл:строка:** `backend/app/services/game_loop/task_scheduler.py:92-138`
- **Severity:** Critical (корневая причина dialogue queue spam)
- **Симптом:** `execute_pending()` итерирует `pending` и пушит КАЖДУЮ задачу в `_dialogue_queue` (строки 112-119). Затем вызывает `dequeue_next()` ровно один раз (строка 121) и выполняет ТОЛЬКО её (строки 136-138). Остальные 9+ задач остаются в heap навсегда. `DialogueQueue._heap` растёт безгранично между тиками. 10+ ambient задач в один тик.
- **Причина:** `execute_pending` enqueue'ит все, dequeue'ит одно. Остальные задачи остаются И в `pending_tasks`, И в heap. Следующий тик их снова enqueue'ит → 9+1+new = 10+, опять одна обрабатывается. (V.0.5.3.6.8 добавил очистку `pending_tasks`, но drain-rate всё ещё 1/tick.)
- **Фикс:** Обернуть dequeue в `while`-цикл с лимитом:
  ```python
  processed = 0
  while processed < self._max_tasks_per_tick:
      _eligible = self._dialogue_queue.dequeue_next()
      if not _eligible:
          break
      ...
      processed += 1
  ```
  Также добавить hard cap на размер heap в `enqueue()` (дропать lowest-priority при heap > 50).
- **Статус:** STILL_BROKEN

#### BUG-DLG-006 — `DialogueQueue` использует wall-clock `time.time()` для cooldown
- **Файл:строка:** `backend/app/services/execution/dialogue_queue.py:43-44, 49-50, 57, 70, 73, 93`
- **Severity:** High (нарушение L15)
- **Симптом:** `COOLDOWN_PER_NPC_SEC = 30` (реальные секунды), `MAX_RATE_PER_MINUTE = 20`, `enqueued_at = time.time()`. Если игра на паузе или игрок AFK 5 минут, queue "думает", что прошло 5 минут, и сбрасывает все cooldown'ы. Replay determinism нарушен.
- **Причина:** 7 мест используют `time.time()` (wall-clock) вместо `game_time_seconds`.
- **Фикс:** Прокинуть `game_time_seconds` из `scene_state` в `enqueue()` / `dequeue_next()`. Заменить `time.time()` на `game_time_seconds` во всех 7 местах.
- **Статус:** STILL_BROKEN

#### BUG-DLG-007 — `clear_dialogue_session` использует non-symmetric key
- **Файл:строка:** `backend/app/services/memory/memory_manager.py:100`
- **Severity:** High
- **Симптом:** `get_dialogue_session` (строки 76-77) строит ключ из `tuple(sorted((npc_id, partner_id)))` — симметричный. Но `clear_dialogue_session` использует `f"{campaign_id}:{npc_id}:{partner_id}"` (строка 100) — non-symmetric. Вызов `clear_dialogue_session(campaign, "player", "maid_lusya")` ищет ключ `campaign:player:maid_lusya`, а хранится `campaign:maid_lusya:player` → сессия НЕ очищается, утекает память.
- **Фикс:**
  ```python
  pair_key = tuple(sorted((npc_id, partner_id)))
  key = f"{campaign_id}:{pair_key[0]}:{pair_key[1]}"
  ```
- **Статус:** STILL_BROKEN

#### BUG-DLG-008 — `clear_all_dialogue_sessions` парсит неправильное поле как `npc_id`
- **Файл:строка:** `backend/app/services/memory/memory_manager.py:127-139`
- **Severity:** High
- **Симптом:** Итерирует ключи (формат `campaign:npc_a:npc_b`), затем `parts = key.split(":")` и `npc_id = parts[1]`. Для NPC-NPC сессий (`campaign:maid_lusya:tornin`) вызывает `clear_dialogue_session(campaign, "maid_lusya", "player")` — lookup не находит ничего.
- **Фикс:**
  ```python
  parts = key.split(":")
  if len(parts) >= 3:
      _, npc_a, npc_b = parts[0], parts[1], parts[2]
      self.clear_dialogue_session(campaign_id, npc_a, npc_b)
  ```
- **Статус:** STILL_BROKEN

#### BUG-DLG-009 — `dequeue_next` swallows rate-limit as "empty queue"
- **Файл:строка:** `backend/app/services/execution/dialogue_queue.py:77-78`
- **Severity:** High
- **Симптом:** Возвращает `None` и когда heap пуст, и когда rate limit hit. Caller не различает → никогда не делает backoff на enqueue.
- **Фикс:** Either raise `RateLimited` exception, либо вернуть `dequeue_status` enum (`EMPTY`/`RATE_LIMITED`/`OK`).
- **Статус:** STILL_BROKEN

#### BUG-DLG-010 — DM-agent читает L2 narrative_cache / recalled_facts (L16 violation)
- **Файл:строка:** `backend/app/services/game_loop/dm_phase.py:65-82` + `backend/app/agents/dm_agent.py:233-236`
- **Severity:** Critical (архитектурное нарушение L16)
- **Симптом:** DM-agent (narrative layer) читает L2 memory (`narrative_cache`) NPC через `recall()` и инжектит результат в LLM-промпт как `npc_l2_memory_block`. Это прямое нарушение ADR L16: "DM-agent reads ONLY `observed_state` + `embodied_traces`. No reading `stress_delta`, `real_state`, `recalled_facts`, `narrative_cache`, `npc_l2_memory_block`." DM-agent получает доступ к скрытой каузальности (долгой памяти NPC), что ломает Epistemic Boundary — DM "знает" то, что игрок не мог наблюдать.
- **Причина:** `dm_phase.py:65-82` извлекает `narrative_cache` для target NPC, вызывает `memory_manager.recall(...)`, инжектит результат в `shared_context.npc_l2_memory_block`. Затем `dm_agent.py:233-236` пишет это в LLM-промпт как `"L2 Memory block"`.
- **Фикс:** Удалить L2 memory block из DM agent's prompt. Если дизайн-интенция — позволить DM наррировать континуитет, `narrative_cache` NPC должно проявляться через NPC-речь (уже в STM), а не через прямой доступ DM к NPC-памяти. Удалить блок `dm_phase.py:65-82` целиком.
- **Статус:** STILL_BROKEN

#### BUG-DLG-011 — `DialogueUpdateExtractor` silently fails (3 bugs in one function)
- **Файл:строка:** `backend/app/services/memory/dialogue_update_extractor.py:38-49`
- **Severity:** High
- **Симптом:** Три независимых бага в `extract()`: (1) `agent_name="dialogue_extractor"` НЕ в `DEFAULT_AGENT_CAPABILITY_MAP` → fallback на `Capability.GENERAL`. (2) `params={"max_tokens": 200, "temperature": 0.1, "response_format": {"type": "json_object"}}` — dict, не `GenerationParams`. (3) `response.text` — `request_for_agent` возвращает str, не объект → `AttributeError` ловится `except Exception`, возвращается пустой `DialogueUpdate()`. **Никакие claims, questions, topics не экстрактятся.** Structured thread memory полностью мёртва.
- **Фикс:**
  - Добавить `"dialogue_extractor": Capability.FACT_EXTRACTION` в `DEFAULT_AGENT_CAPABILITY_MAP` в `router.py`.
  - Использовать `GenerationParams(max_tokens=200, temperature=0.1, response_format={"type": "json_object"})`.
  - Заменить `response.text` на `response` (уже строка).
- **Статус:** STILL_BROKEN

#### BUG-DLG-014 — `thread_id` генерируется, но никогда не используется
- **Файл:строка:** `backend/app/services/phases/post_decision.py:67-69, 122, 159`; declared in `app/domain/communication.py:64, 89` and `app/services/memory/dialogue_session.py:55`
- **Severity:** Medium
- **Симптом:** `thread_id` генерируется, передаётся через `DialogueRequest`, реконструируется в `task_scheduler._reconstruct_task`, хранится в `DialogueRequest` и `DialogueSession`. Но **ни один код его не читает**. `MemoryManager.get_dialogue_session` ключует по `(campaign_id, sorted_pair)`. Dialogue Thread System (S145) формально существует, но не функционален — нет thread-based memory continuity.
- **Фикс:** Либо реализовать thread-based session lookup (`get_dialogue_session(campaign, npc_a, npc_b, thread_id)`), либо удалить `thread_id` из всех DTO (dead propagation chain).
- **Статус:** STILL_BROKEN

#### BUG-DLG-CAUSAL-4.7.48 — `mock_provider.py` использует `ENIGMA_ENV` вместо `settings.environment`
- **Файл:строка:** `backend/app/services/llm/mock_provider.py:126`
- **Severity:** High (также BUG-FB-021)
- **Симптом:** MockProvider определяет продакшен по env var `ENIGMA_ENV`, а Settings использует `AIDM_ENVIRONMENT` (env_prefix="AIDM_", `config.py:162`). Настройка `AIDM_ENVIRONMENT=test` НЕ отключает MockProvider (он видит `ENIGMA_ENV` unset → "production" → отдаёт пустую строку). Настройка `ENIGMA_ENV=test` НЕ меняет `settings.environment` (остаётся "production"). Контракт CAUSAL_CONTRACT §4.7.48 нарушен: конфигурация не консистентна.
- **Фикс:**
  ```python
  from app.core.config import settings
  def _pick_response(self, prompt: str) -> str:
      if settings.environment.lower() == "production":
          logging.getLogger(__name__).error("[MOCK_PROVIDER] MockProvider called in production!")
          return ""
      ...
  ```
- **Статус:** STILL_BROKEN

#### BUG-DLG-CAUSAL-4.7.49 — `dm_agent.py` содержит `json.loads` (CJK retry path)
- **Файл:строка:** `backend/app/agents/dm_agent.py:861`
- **Severity:** High
- **Симптом:** DM-agent имеет CJK retry path, который парсит JSON напрямую через `json.loads`, обходя `DMResponseNormalizer`. Нарушение CAUSAL_CONTRACT §4.7.49: "Парсинг JSON в DM-агенте запрещён → `DMResponseNormalizer`".
- **Фикс:** Удалить `json.loads` из `dm_agent.py:861`. Весь JSON-парсинг должен идти через `DMResponseNormalizer.parse()`.
- **Статус:** STILL_BROKEN

#### BUG-DLG-041 (NEW, Critical) — `openai_compatible_provider.py` BROKEN IMPORT
- **Файл:строка:** `backend/app/services/llm/openai_compatible_provider.py:12`
- **Severity:** Critical
- **Симптом:** `from app.services.llm.llm_provider import LlmProvider` — файл `llm_provider.py` НЕ существует (правильно: `provider.py`). `ModuleNotFoundError` при любой попытке использовать `ProviderType.OPENAI`. OpenAI-compatible провайдер (включая vLLM, LM Studio, Ollama, OpenAI API) полностью неработоспособен.
- **Причина:** Импорт указывает на несуществующий модуль `llm_provider` вместо правильного `provider`.
- **Фикс:**
  ```python
  from app.services.llm.provider import LlmProvider  # ← provider, не llm_provider
  ```
- **Статус:** NEW

#### BUG-DLG-042 (NEW) — `ModelRouter.set_lazy_loading` — no-op из-за mismatched attribute name
- **Файл:строка:** `backend/app/services/llm/router.py` (метод `set_lazy_loading`)
- **Severity:** Medium
- **Симптом:** `set_lazy_loading(True)` устанавливает `self._lazy_loading = True`, но consumers читают `self.lazy_loading` (без underscore). Lazy loading никогда не активируется — все провайдеры загружаются eagerly при старте, увеличивая VRAM consumption.
- **Фикс:** Унифицировать имя атрибута: использовать `self._lazy_loading` везде, либо `self.lazy_loading` везде.
- **Статус:** NEW

#### BUG-DLG-043 (NEW) — `rules_agent.py` использует `random.randint` для d20 бросков
- **Файл:строка:** `backend/app/agents/rules_agent.py`
- **Severity:** High
- **Симптом:** Rules agent (D&D 5e броски d20 для skill checks, saving throws) использует `random.randint(1, 20)` — global random. Недетерминированные результаты между запусками.
- **Фикс:** Использовать `KernelRNG(tick=tick, npc_id=actor_id, salt=f"rules_d20:{check_type}")`.
- **Статус:** NEW

#### BUG-DLG-044 (NEW) — `llama_cpp_provider.py` использует `random.randint` для LLM seed
- **Файл:строка:** `backend/app/services/llm/llama_cpp_provider.py:163`
- **Severity:** High
- **Симптом:** LLM seed генерируется через `random.randint(0, 2**31 - 1)` — global random. Один и тот же промпт даёт разные ответы между запусками. Replay determinism для LLM-генерации нарушен.
- **Фикс:** Использовать детерминированный seed на основе (tick, npc_id, salt) через `KernelRNG.randint(0, 2**31 - 1)`, либо передавать seed из вызывающего кода.
- **Статус:** NEW

#### BUG-DLG-045 (NEW) — `DialogueQueue.dequeue_next` пишет None/empty key в `_recent_npc_speak`
- **Файл:строка:** `backend/app/services/execution/dialogue_queue.py`
- **Severity:** Medium
- **Симптом:** Когда `dequeue_next` возвращает задачу с пустым `speaker` (или `None`), ключ `""` или `None` записывается в `_recent_npc_speak` dict. При следующем `enqueue` для любого NPC проверка `speaker in _recent_npc_speak` может ложно сработать для empty key.
- **Фикс:** Skip update `_recent_npc_speak` если `speaker` пустой или `None`.
- **Статус:** NEW

#### BUG-DLG-046 (NEW) — `DialogueQueue.mark_completed` — пустой stub (`pass`)
- **Файл:строка:** `backend/app/services/execution/dialogue_queue.py`
- **Severity:** Medium
- **Симптом:** `mark_completed(task_id)` — метод существует, но тело содержит только `pass`. Завершённые задачи НЕ помечаются как completed в очереди. Cooldown tracking и rate-limit stats некорректны.
- **Фикс:** Реализовать mark_completed: удалить задачу из heap, обновить `_recent_npc_speak` timestamps, evict из pending.
- **Статус:** NEW

#### BUG-DLG-047 (NEW) — `task_scheduler.py` dead `import random` после KernelRNG миграции
- **Файл:строка:** `backend/app/services/game_loop/task_scheduler.py:172`
- **Severity:** Low (также BUG-CORE-028)
- **Симптом:** Мёртвый импорт `random` остался после миграции на `KernelRNG.choice`.
- **Фикс:** Удалить `import random`.
- **Статус:** NEW

#### BUG-DLG-048 (NEW) — `world_sim_agent.py` использует `print()` вместо `logger`
- **Файл:строка:** `backend/app/agents/world_sim_agent.py`
- **Severity:** Low
- **Симптом:** Production stdout загрязнён diagnostic print'ами из world simulation agent. L21 violation: "Использование `print()` в production запрещено".
- **Фикс:** Заменить все `print()` на `logger.debug()`.
- **Статус:** NEW

#### BUG-DLG-049 (NEW) — `world_sim_agent.py:tick(world_id)` игнорирует параметр
- **Файл:строка:** `backend/app/agents/world_sim_agent.py`
- **Severity:** Low
- **Симптом:** Метод `tick(world_id)` принимает параметр `world_id`, но не использует его — использует захардкоженный `self._default_world` или читает из global state. Несколько world-ов не могут симулироваться независимо.
- **Фикс:** Использовать `world_id` параметр для всех lookups.
- **Статус:** NEW

#### BUG-DLG-050 (NEW) — `dm_orchestrator.py` — `Any` не импортирован
- **Файл:строка:** `backend/app/services/action/dm_orchestrator.py`
- **Severity:** Low
- **Симптом:** Тип-аннотация `Any` используется в сигнатурах, но `from typing import Any` отсутствует. При включённом `from __future__ import annotations` — безвредно (строки не вычисляются). При runtime introspection — `NameError`.
- **Фикс:** Добавить `from typing import Any` в imports.
- **Статус:** NEW

#### BUG-DLG-051 (NEW) — `dm_scene_builder.py` — тип mismatch: Dict присваивается в `List[str]` field
- **Файл:строка:** `backend/app/services/action/dm_scene_builder.py`
- **Severity:** Low
- **Симптом:** Поле с аннотацией `List[str]` получает `Dict` значение. Type checker падает, runtime работает (Python не проверяет аннотации), но логика consumer'а, ожидающего list, может сломаться.
- **Фикс:** Привести к единому типу: либо `List[str]` everywhere, либо `Dict` everywhere.
- **Статус:** NEW

#### BUG-DLG-052 (NEW) — `ModelRouter.request_for_agent` — duplicate capability lookup в worker thread path
- **Файл:строка:** `backend/app/services/llm/router.py`
- **Severity:** Medium
- **Симптом:** В worker-thread path `request_for_agent` делает duplicate capability lookup — сначала через `DEFAULT_AGENT_CAPABILITY_MAP`, затем через `_resolve_capability_fallback`. Избыточная работа, может привести к рассинхрону если maps расходятся.
- **Фикс:** Унифицировать lookup в один вызов, кэшировать результат.
- **Статус:** NEW

---

### 3.3. DOM-03: PERCEPTION / COMBAT / AFFECTIVE (18 дефектов)

#### BUG-PERC-003 — `ImpactEngine` использует `random.Random(rng_seed)` с `hash()`-seed (UUID)
- **Файл:строка:** `backend/app/services/combat/impact_engine.py:24, 46, 95, 131`
- **Severity:** High (= BUG-CORE-021)
- **Симптом:** Боевые броски d20 (hit/miss, critical), выбор зоны попадания (head/torso/limbs) — недетерминированы. `rng_seed=hash((event.id, ...))` где `event.id = str(uuid.uuid4())` — различается между запусками.
- **Фикс:** См. BUG-CORE-021 — использовать `KernelRNG(tick, npc_id, salt)`.
- **Статус:** STILL_BROKEN

#### BUG-PERC-004 — `combat_math.py` fallback на global `random` при `rng=None`
- **Файл:строка:** `backend/app/services/game/combat_math.py:12, 50, 52, 61`
- **Severity:** High
- **Симптом:** `combat_math.attack_roll(rng=None)` fallback'ит к global `random` — недетерминированные броски d20. Если caller не передаёт `rng` (что происходит в нескольких call sites), combat полностью non-deterministic.
- **Причина:** `import random` на строке 12, `random.randint(1, 20)` на строках 50, 52, 61.
- **Фикс:** Сделать `rng` обязательным параметром (no default `None`). Использовать `KernelRNG` everywhere.
- **Статус:** STILL_BROKEN

#### BUG-PERC-005 — `combat_math.apply_damage` пишет `target["hp"]` напрямую, минуя `body_state["current_hp"]` (L12 violation)
- **Файл:строка:** `backend/app/services/game/combat_math.py:300-322`
- **Severity:** Critical
- **Симптом:** HP Double Truth: `body_state["current_hp"]` (канонический SSOT) и `target["hp"]` (legacy) расходятся. `evaluate_vital_state()` читает `body_state["current_hp"]`, но `apply_damage` пишет `target["hp"]`. NPC может иметь `hp=0` (от combat) но `body_state["current_hp"]=50` (не обновлён) — не умирает. Или наоборот: `hp=50` но `current_hp=0` — "мёртв" по vital_state, но combat продолжается.
- **Причина:** `target["hp"] = max(0, target.get("hp", 0) - damage)` — прямой write в legacy поле.
- **Фикс:**
  ```python
  body = target.setdefault("body_state", {})
  body["current_hp"] = max(0, body.get("current_hp", body.get("hp", 0)) - damage)
  # удалить target["hp"] write полностью
  ```
- **Статус:** STILL_BROKEN

#### BUG-PERC-006 — `combat_math.apply_healing` воскрешает мёртвых (DEAD → ALIVE)
- **Файл:строка:** `backend/app/services/game/combat_math.py:325-340`
- **Severity:** Critical
- **Симптом:** `apply_healing` лечит HP без проверки `life_status`. Если NPC `life_status="DEAD"` с `current_hp=-10`, `apply_healing(50)` ставит `current_hp=40`, но `life_status` остаётся `"DEAD"` (или, если код мутирует `life_status`, становится `"ALIVE"` — воскрешение). Нарушение L12: "DEAD → ALIVE через физиологию запрещён (ADR-127)".
- **Фикс:**
  ```python
  def apply_healing(target, amount):
      body = target.get("body_state", {})
      if body.get("life_status") == "DEAD":
          logger.warning(f"[COMBAT] apply_healing skipped for DEAD npc={target.get('id')}")
          return  # healing forbidden for dead
      body["current_hp"] = min(body.get("max_hp", 100), body.get("current_hp", 0) + amount)
  ```
- **Статус:** STILL_BROKEN

#### BUG-PERC-013 — `archive_old_events` делает `DELETE FROM l1_chronicle_events` (L17 violation)
- **Файл:строка:** `backend/app/services/npc/l1_chronicle.py:240-268`
- **Severity:** High
- **Симптом:** `archive_old_events` выполняет `DELETE FROM l1_chronicle_events WHERE tick < ?` — удаляет старые события из chronicle. Нарушение L17: "L1Chronicle — append-only. Удаление = переписывание истории". Если archive table не существует или миграция не прошла, DELETE падает, но L1Chronicle растёт безгранично.
- **Причина:** Метод существует для ограничения размера L1Chronicle, но нарушает append-only контракт.
- **Фикс:** Заменить DELETE на мягкую архивацию: добавить колонку `archived: bool` и `UPDATE l1_chronicle_events SET archived=1 WHERE tick < ?`. PatternDetector должен читать только `WHERE archived=0`.
- **Статус:** STILL_BROKEN

#### BUG-PERC-014 — Кристаллизация убеждений запускается каждый тик без `phase_2_events` gate (L14 violation)
- **Файл:строка:** `backend/app/services/phases/integration.py:380-422`
- **Severity:** High
- **Симптом:** `BeliefCrystallizationEngine.crystallize()` вызывается в Phase 9 каждый тик, без проверки `phase_2_events`. Нарушение L14: "Память не генерирует идентичность без каузального входа (ADR-S86.7)". NPC кристаллизуют убеждения из пустых/старых данных, создавая фантомные beliefs. Identity drift ускоряется.
- **Причина:** Нет gate `if not ctx.phase_2_events: return` перед crystallization.
- **Фикс:**
  ```python
  if not ctx.phase_2_events:
      logger.debug("[L2.5] Skipping crystallization — no phase_2_events this tick")
      return
  # ... crystallize
  ```
- **Статус:** STILL_BROKEN

#### BUG-PERC-025 — Somatic Gate отсутствует перед semantic parsing в `decision_hub.py` (L8 violation)
- **Файл:строка:** `backend/app/services/npc/decision_hub.py:402-418`
- **Severity:** High
- **Симптом:** DecisionHub парсит semantic action ДО проверки somatic urgency (pain/shock). NPC с `shock > 0.7` принимает полные семантические решения, игнорируя телесный шок. Нарушение L8/ADR-O-139: "Body → Somatic Gate → Semantic Parsing → Legitimacy → Action".
- **Причина:** В `decision_hub.py:402-418` semantic parsing происходит первым, somatic check — после (или отсутствует).
- **Фикс:** Реструктурировать: somatic gate FIRST, затем semantic parsing:
  ```python
  # 1. Somatic Gate (Body → Somatic)
  somatic = self._compute_somatic_urgency(npc.body_state)
  if somatic.shock > 0.7:
      return self._shock_overrides_decision(npc, somatic)
  # 2. Semantic Parsing (Somatic → Semantic)
  semantic = self._parse_semantic_action(...)
  ```
- **Статус:** STILL_BROKEN

#### BUG-PERC-029 — `AffectiveDecayHandler` не проверяет `life_status == "DEAD"` (L12 violation)
- **Файл:строка:** `backend/app/services/affective/affective_decay_handler.py:52-93`
- **Severity:** High
- **Симптом:** Affective decay применяется к мёртвым NPC. Нарушение L12: "Decay для мёртвых запрещён". Мёртвый NPC продолжает "забывать" травмы — бессмысленная операция, расход CPU.
- **Причина:** Нет проверки `if npc.body_state.get("life_status") == "DEAD": continue`.
- **Фикс:**
  ```python
  for npc in npcs:
      if npc.get("body_state", {}).get("life_status") == "DEAD":
          continue
      self._decay(npc)
  ```
- **Статус:** STILL_BROKEN

#### BUG-PERC-030 (NEW, CRITICAL) — `decay_affective_imprints` падает с `NameError: name 'replace' is not defined`
- **Файл:строка:** `backend/app/services/affect.py:264-286` (особенно line 283)
- **Severity:** Critical (корневая причина S-2)
- **Симптом:** Affective Decay phase (Phase 0.5, `idle_services.py:65-78`) полностью сломан. Травмы (`AffectiveImprint`) НИКОГДА не затухают естественно со временем. CAUSAL_CONTRACT §4.6 (no permanent shock/trauma) нарушен. Shock_immortality (ADR-109) — shock never decays.
- **Причина:** `new_imp = replace(imp, reinforcement=max(0.0, new_reinforcement))` — `replace` (from `dataclasses`) НЕ импортирован на уровне модуля. Он импортируется ТОЛЬКО локально внутри `apply_conditioning` (line 305: `from dataclasses import replace`), что не делает его доступным для `decay_affective_imprints`. Runtime: `NameError: name 'replace' is not defined`. Caller (`idle_services.py:69-78`) оборачивает в `try/except Exception as e: logger.warning(...)`, так что ошибка логируется как warning, но imprints НЕ обновляются → травмы сохраняются навсегда.
- **Фикс:**
  ```python
  # affect.py — добавить module-level импорт
  from dataclasses import replace
  ```
- **Статус:** NEW

#### BUG-PERC-031 (NEW, CRITICAL) — `ResonanceProfile` без `@dataclass` — `TypeError` при конструировании
- **Файл:строка:** `backend/app/models/affect.py:73`
- **Severity:** Critical
- **Симптом:** `ResonanceProfile(triggered_imprints=...)` → `TypeError: ResonanceProfile() takes no arguments`. `ResonanceProfile().triggered_imprints` → `AttributeError`. Affective Resonance Scan полностью неработоспособен — NPC не могут "резонировать" с аффективными состояниями других NPC.
- **Причина:** Класс `ResonanceProfile` объявлен без `@dataclass` decorator, но имеет type-annotated fields. Python интерпретирует их как class-level annotations, не как `__init__` parameters.
- **Фикс:**
  ```python
  from dataclasses import dataclass, field

  @dataclass
  class ResonanceProfile:
      triggered_imprints: Tuple[AffectiveImprint, ...] = field(default_factory=tuple)
      resonance_score: float = 0.0
      # ...
  ```
- **Статус:** NEW

#### BUG-PERC-032 (NEW, CRITICAL) — `PhysiologyDecayHandler` читает `body_state` из `NPCStateSnapshot`, но этого поля там нет
- **Файл:строка:** `backend/app/services/combat/physiology_decay_handler.py:92-118`
- **Severity:** Critical
- **Симптом:** `PhysiologyDecayHandler` читает `body_state` из `NPCStateSnapshot`, но `NPCStateSnapshot` имеет `body_state` поля на top-level (`pain`, `fatigue`, `blood_loss`, `shock`, `consciousness`), не вложенными в `body_state` dict. Все reads возвращают `0`/default → early `continue` → **физиологический decay (pain, fatigue, blood_loss, shock, consciousness, PK) НИКОГДА не применяется.** NPC остаются с перманентным pain/fatigue/shock навсегда.
- **Причина:** `snapshot.body_state.get("pain", 0)` — но `snapshot.pain` это top-level field, `snapshot.body_state` is `None`.
- **Фикс:** Читать top-level fields:
  ```python
  pain = getattr(snapshot, "pain", 0) or snapshot.get("pain", 0) if isinstance(snapshot, dict) else 0
  # или унифицировать NPCStateSnapshot, чтобы содержал body_state dict
  ```
- **Статус:** NEW

#### BUG-PERC-033 (NEW) — `InjuryProcessor.handle` проверяет `body_state.life_status`, но в snapshot `life_status` top-level
- **Файл:строка:** `backend/app/services/combat/injury_processor.py`
- **Severity:** Medium
- **Симптом:** `InjuryProcessor` проверяет `body_state.get("life_status")`, но в `NPCStateSnapshot` `life_status` — top-level field. Проверка всегда возвращает `None` → injuries применяются к мёртвым NPC.
- **Фикс:** Унифицировать: либо `life_status` всегда в `body_state`, либо всегда top-level.
- **Статус:** NEW

#### BUG-PERC-034 (NEW) — `CombatSubscriber._build_snapshot` не включает `life_status` в NPCStateSnapshot
- **Файл:строка:** `backend/app/services/combat/combat_subscriber.py`
- **Severity:** Medium
- **Симптом:** `_build_snapshot` конструирует `NPCStateSnapshot` без `life_status` field. Все downstream consumers (InjuryProcessor, PhysiologyDecayHandler) получают `life_status=None` → не могут определить, жив ли NPC.
- **Фикс:** Включить `life_status=body_state.get("life_status", "ALIVE")` в snapshot construction.
- **Статус:** NEW

#### BUG-PERC-035 (NEW) — `physics_validator.py:82` lambda ссылается на `self` внутри class-body — NameError при вызове
- **Файл:строка:** `backend/app/services/game/physics_validator.py:82`
- **Severity:** Medium
- **Симптом:** Lambda определённая в class-body ссылается на `self`, но `self` не существует в class scope. При вызове lambda — `NameError: name 'self' is not defined`.
- **Фикс:** Вынести lambda в метод `__init__` или сделать static method.
- **Статус:** NEW

#### BUG-PERC-036 (NEW) — `combat_service.py:111` пишет `p["hp"]` напрямую (L12 violation)
- **Файл:строка:** `backend/app/services/combat_service.py:111`
- **Severity:** High
- **Симптом:** `combat_service` пишет HP напрямую в `p["hp"]`, минуя `body_state["current_hp"]`. HP Double Truth. Нет `life_status` update — NPC может умереть (hp=0), но `life_status` остаётся `"ALIVE"`.
- **Фикс:**
  ```python
  body = p.setdefault("body_state", {})
  body["current_hp"] = max(0, body.get("current_hp", 0) - damage)
  if body["current_hp"] <= 0 and body.get("life_status") != "DEAD":
      body["life_status"] = "DEAD"
      # emit death event через evaluate_vital_state
  ```
- **Статус:** NEW

#### BUG-PERC-037 (NEW) — `ConditionEngine.tick` не проверяет `life_status == "DEAD"` + `tick_conditions` пишет HP напрямую (L12 violation)
- **Файл:строка:** `backend/app/services/npc/condition_engine.py`
- **Severity:** High
- **Симптом:** `ConditionEngine.tick` применяет conditions (bleeding, poison, disease) к мёртвым NPC — нет DEAD check. `tick_conditions` пишет HP напрямую в `state.hp`, минуя `body_state["current_hp"]`. L12 violation × 2.
- **Фикс:** (1) Добавить `if life_status == "DEAD": continue` в начале цикла. (2) Заменить все `state.hp -= ...` на `body_state["current_hp"] -= ...`.
- **Статус:** NEW

#### BUG-PERC-038 (NEW) — Multiple `effective_hp <= 0` проверки как источник death/skip (L12 violation)
- **Файл:строка:** multiple (combat, condition, physiology consumers)
- **Severity:** Medium
- **Симптом:** Несколько файлов используют `if npc.effective_hp <= 0: skip` как источник death determination. Нарушение L12: "`hp <= 0` как источник смерти запрещён → единственный владелец — `evaluate_vital_state()`".
- **Фикс:** Заменить все `effective_hp <= 0` checks на `body_state.get("life_status") == "DEAD"`.
- **Статус:** NEW

#### BUG-PERC-039 (NEW) — `_determine_response_bias` без default return → implicit `None` → no distortion applied
- **Файл:строка:** `backend/app/services/npc/interpretation_engine.py` (метод `_determine_response_bias`)
- **Severity:** Medium
- **Симптом:** `_determine_response_bias` не имеет `return` в одном из ветвлений → возвращает `None` неявно. Caller получает `None` вместо `ResponseBias` object → no cognitive distortion applied. NPC интерпретируют события без bias.
- **Фикс:** Добавить `return ResponseBias.default()` в конце метода.
- **Статус:** NEW

#### BUG-PERC-040 (NEW, LOW) — `PerceptualAttentionService` мёртвый код; импортирует `PlayerPerceptionDTO` из неправильного модуля
- **Файл:строка:** `backend/app/services/perception/perceptual_attention_service.py`
- **Severity:** Low
- **Симптом:** `PerceptualAttentionService` импортирует `PlayerPerceptionDTO` из `app.models.front` (legacy), но актуальный DTO находится в `app.models.pipelines` или `app.domain.snapshot`. Service мёртв — не вызывается из production.
- **Фикс:** Удалить dead code или обновить импорт.
- **Статус:** NEW

#### BUG-PERC-041 (NEW, MEDIUM) — L12 falsy `body_state` checks (5 мест)
- **Файл:строка:** multiple (`decision_hub.py`, `injury_processor.py`, `condition_engine.py`, `affective_decay_handler.py`, `combat_math.py`)
- **Severity:** Medium
- **Симптом:** 5 мест используют `if body_state:` (falsy check) вместо `if body_state is not None:`. Если `body_state = {}` (пустой dict, но валидный), проверка возвращает `False` → NPC обрабатывается как без body. Нарушение L12: "`if state.body_state:` (falsy dict) запрещён → `is not None`".
- **Фикс:** Заменить все `if body_state:` на `if body_state is not None:`.
- **Статус:** NEW

---

### 3.4. DOM-04: SPATIAL / MOVEMENT / TRAVERSAL (12 дефектов)

#### BUG-SPATIAL-015 — `resolve_affordance` zone-filter для bed STILL BROKEN (fix неэффективен)
- **Файл:строка:** `backend/app/services/spatial/spatial_service.py:376-379` + `backend/app/services/spatial/graph_compiler.py:520-540`
- **Severity:** High
- **Симптом:** NPC ищет кровать (`resolve_affordance("sleep", ...)`). Кровать находится в другой зоне (напр. `tent_1`). `get_nearest(_obj_zone, ...)` должен искать узел в зоне объекта, но возвращает узел в `origin_zone` (зоне NPC). NPC идёт к boundary node в своей зоне вместо кровати.
- **Причина:** Fix на строке 378: `_obj_zone = best_obj.get("zone_id") or origin_zone or self._location_id`. Но `_extract_affordance_objects` (`graph_compiler.py:520-540`) НЕ извлекает `zone_id` из editor JSON — поле отсутствует в словаре. `best_obj.get("zone_id")` всегда `None`. Fallback: `origin_zone` (зона NPC, не объекта). Контракт ADR-O-330 ("Кровать — объект, не узел графа") нарушен: объект не знает свою зону.
- **Фикс:** В `_extract_affordance_objects` добавить извлечение `zone_id`:
  ```python
  affordance_objects.append({
      ...
      "zone_id": obj.get("zone_id") or obj.get("room_id") or "",
  })
  ```
- **Статус:** STILL_BROKEN (fix применён, но неэффективен — данные не несут zone_id)

#### BUG-SPATIAL-023 — Silent `except Exception: pass` для SpatialFactory в npc_orchestration.py
- **Файл:строка:** `backend/app/services/game_loop/npc_orchestration.py:191-195`
- **Severity:** Medium (= BUG-CORE-020)
- **Симптом:** См. BUG-CORE-020.
- **Статус:** STILL_BROKEN

#### BUG-SPATIAL-026 — Direct `status` mutation bypassing FSM в ProjectionEngine
- **Файл:строка:** `backend/app/services/projection_engine.py:131-134` + `backend/app/services/event_compiler.py:488, 657`
- **Severity:** Medium
- **Симптом:** Shadow path (`ProjectionEngine`) создаёт `traversal_dict` с `"status": "MOVING"` напрямую, минуя `transition_traversal()` FSM. Legacy path (`SSM.apply_change` → `build_traversal_dict`) использует FSM правильно (PENDING → MOVING). Расхождение: shadow пишет MOVING без валидации перехода. Если FSM правила изменятся, shadow продолжит писать MOVING напрямую.
- **Причина:** `event_compiler.py:488,657`: `"status": "MOVING"` — HARDCODED, не через `transition_traversal()`.
- **Фикс:** В `event_compiler.py` заменить `"status": "MOVING"` на `"status": "PENDING"`, затем в `projection_engine.py:134` вызвать `transition_traversal()`:
  ```python
  # event_compiler.py
  "status": "PENDING",  # start with PENDING
  # projection_engine.py:134
  from app.domain.traversal_schema import transition_traversal
  transition_traversal(_fields, "MOVING")  # FSM: PENDING → MOVING
  ```
- **Статус:** STILL_BROKEN

#### BUG-SPATIAL-029 (NEW, Critical) — SpatialFactory cache возвращает STALE overlay
- **Файл:строка:** `backend/app/services/spatial/spatial_factory.py:48-51` + `backend/app/services/spatial/spatial_service.py:210-216`
- **Severity:** Critical (корневая причина S-4)
- **Симптом:** A* pathfinding и `resolve_node` используют STALE overlay на каждом тике. `reserved_nodes` содержит узлы, занятые NPC, которые давно ушли. `crowd_density` отражает позиции NPC из первого тика (когда сервис был собран), а не текущие. NPC не могут зарезервировать узлы, которые были заняты NPC на первом тике. `risk_zones`, `light_levels` тоже stale. NPC "застревают" на узлах, блокируются phantom-reservations.
- **Причина:** `SpatialFactory.build_for_campaign` кэширует `SpatialService` по `(campaign_id, location_id)` с инвалидацией ТОЛЬКО по SHA-256 fingerprint map файла. Overlay строится один раз в `SpatialService.build_for_location` из `scene_state` ПРИ СБОРЕ. Метод `set_overlay()` существует, но ВЫЗЫВАЕТСЯ ИЗ НИГДЕ (0 call sites кроме `__init__`). Overlay НЕ обновляется при возврате кэшированного сервиса. Каскадно: `resolve_node` фильтрует по stale `reserved_nodes`; `_edge_cost` использует stale `crowd_density`/`risk_zones`/`light_levels`; `is_reachable` проверяет stale `blocked_nodes`.
- **Фикс:** В `SpatialFactory.build_for_campaign` обновлять overlay перед возвратом кэшированного сервиса:
  ```python
  if cached_fp == current_fp and current_fp != "":
      from app.services.spatial.spatial_overlay import build_overlay_from_scene
      cached_svc.set_overlay(build_overlay_from_scene(scene_state))  # REFRESH OVERLAY
      return cached_svc
  ```
- **Статус:** NEW

#### BUG-SPATIAL-030 (NEW, High) — `cluster_relation` всегда возвращает "adjacent" (dead `neighbors` variable)
- **Файл:строка:** `backend/app/services/spatial/spatial_query_service.py:81-98`
- **Severity:** High
- **Симптом:** `cluster_relation(entity_a, entity_b)` всегда возвращает "same" (если same cluster) или "adjacent" (если different cluster with any entities). Никогда не возвращает "distant". `DecisionHub` / `SocialEngine`, использующие `cluster_relation` для определения социальной близости, получают ложное "adjacent" для любых двух NPC в разных кластерах.
- **Причина:** `neighbors = self._cluster_occupancy.cluster_to_entities.get(cl_a, set())` — вычисляется, но НИКОГДА не используется (dead code). `cl_b in self._cluster_occupancy.cluster_to_entities` проверяет existence (almost always true), не adjacency.
- **Фикс:** Использовать `ClusterGraph` для проверки adjacency:
  ```python
  if self._cluster_graph:
      cl_a_def = self._cluster_graph.clusters.get(cl_a)
      if cl_a_def and cl_b in cl_a_def.boundary_cells:
          return "adjacent"
  return "distant"
  ```
- **Статус:** NEW

#### BUG-SPATIAL-031 (NEW, Medium) — `print()` debug pollution в production (spatial_service + graph_compiler)
- **Файл:строка:** `backend/app/services/spatial/spatial_service.py:530, 533, 536, 602` + `backend/app/services/spatial/graph_compiler.py:459`
- **Severity:** Medium
- **Симптом:** Production stdout загрязнён diagnostic print'ами на каждый вызов `find_path`. Логи production не проходят через logging config. При 50+ NPC на тик — тысячи print'ов в stdout.
- **Фикс:** Заменить все `print()` на `logger.debug()`.
- **Статус:** NEW

#### BUG-SPATIAL-032 (NEW, High) — `player_spatial` читается в LifeEngine motion_router (L9 violation)
- **Файл:строка:** `backend/app/services/npc/life_engine.py:858-872`
- **Severity:** High
- **Симптом:** NPC с `intent=APPROACH`/`FLEE` к игроку читает позицию игрока из `player_spatial` (DEAD поле, ADR-048). Если фронтенд фильтрует игрока из `npc_positions`, NPC получает stale позицию из `player_spatial`. L9: "No `player_spatial` reads." Double Truth.
- **Причина:** `_ps = scene_state.get("player_spatial", {})` — fallback к legacy полю.
- **Фикс:** Удалить fallback на `player_spatial`. Если player не в `npc_positions` — логировать error и skip:
  ```python
  if not _target_pos_entry and _move_target == "player":
      logger.error(f"[MOTION_ROUTER] Player not in npc_positions for npc={npc_id}")
      continue
  ```
- **Статус:** NEW

#### BUG-SPATIAL-033 (NEW, Medium) — `player_spatial` читается в scene_init._update_player_position (L9 violation)
- **Файл:строка:** `backend/app/services/game_loop/scene_init.py:78-82`
- **Severity:** Medium
- **Симптом:** При обновлении позиции игрока из фронтенда, если `node["position"]` пуст, читается `player_spatial["position"]` как fallback. L9 violation.
- **Фикс:** Удалить fallback на `player_spatial`. Вычислять node_id через `SpatialService.get_nearest()`.
- **Статус:** NEW

#### BUG-SPATIAL-034 (NEW, Medium) — `_ensure_spatial_service` вызывается, но НИКОГДА не определён
- **Файл:строка:** `backend/app/services/scene_state_manager.py:1856`
- **Severity:** Medium
- **Симптом:** `SceneStateManager.update_npc_position()` вызывает `self._ensure_spatial_service(location_id, scene_state)` — метод, который НЕ СУЩЕСТВУЕТ в классе. `AttributeError: 'SceneStateManager' object has no attribute '_ensure_spatial_service'`. Метод `update_npc_position` — тоже 0 внешних call sites (dead code), но публичный — любой future caller получит `AttributeError`.
- **Фикс:** Заменить на `SpatialFactory.build_for_campaign` или удалить `update_npc_position` целиком.
- **Статус:** NEW

#### BUG-SPATIAL-035 (NEW, Low) — SpatialEventDetector генерирует NPC_MOVED для player (semantic mismatch)
- **Файл:строка:** `backend/app/services/spatial/spatial_event_detector.py:33-46, 85-104`
- **Severity:** Low
- **Симптом:** `SpatialEventDetector` итерирует ALL `npc_positions` включая `"player"`. Когда игрок меняет узел, публикуется `NPC_MOVED` event с `source="player"`. Подписчики, ожидающие NPC-to-NPC proximity, получают события с player.
- **Фикс:** Фильтровать player: `if npc_id == "player": continue`.
- **Статус:** NEW

#### BUG-SPATIAL-036 (NEW, Low) — Spatial Coherence Validation SC-1..SC-8 не реализованы как coherent gate
- **Файл:строка:** `backend/app/services/scene_state_manager.py:921, 977, 1740-1744`
- **Severity:** Low
- **Симптом:** Spatial Coherence Contract SC-1..SC-8 — нет единой validation функции. SC-1 (no (0,0)) частично проверяется. SC-2..SC-8 НЕ проверяются. Контракт "No movement before coherence validation" (SC-6) — movement происходит без explicit validation.
- **Фикс:** Создать `SpatialCoherenceValidator` с методами `validate_sc1..sc8()`, вызывать перед `MovementEngine.process_intents()`.
- **Статус:** NEW

#### BUG-SPATIAL-037 (NEW, Low) — `try_reserve_node` — dead code (0 call sites)
- **Файл:строка:** `backend/app/services/spatial/spatial_overlay.py:72-104`
- **Severity:** Low
- **Симптом:** `try_reserve_node()` определён, но НИКОГДА не вызывается. `reserved_nodes` строится только через `build_overlay_from_scene` (чтение текущих позиций), без динамической резервации.
- **Фикс:** Удалить dead code ИЛИ интегрировать в `MovementEngine` для URGENT резервации перед A*.
- **Статус:** NEW

#### BUG-SPATIAL-038 (NEW, Low) — Дублированный `logger = logging.getLogger(__name__)` в movement_engine.py
- **Файл:строка:** `backend/app/services/spatial/movement_engine.py:11` и `:38`
- **Severity:** Low
- **Симптом:** `logger` объявлен дважды. Lint-noise.
- **Фикс:** Удалить строку 38.
- **Статус:** NEW

---

### 3.5. DOM-07: FRONTEND / BACKEND / PERSISTENCE (17 дефектов)

#### BUG-FB-001 — SSE `done` не несёт `world_snapshot` (нормальный путь)
- **Файл:строка:** `backend/app/services/game_loop/__init__.py:1427-1438`
- **Severity:** Critical (корневая причина S-5)
- **Симптом:** После player action через SSE (`/api/game/action/stream`) frontend получает `done` событие без `world_snapshot`. `result.world_snapshot` в `game_loop_bridge.py:208` = `None`, fallback на `{}`. NPC позиции, `player_body_topology`, `visual_dto`, `audible_dto`, `game_time_seconds`, `recent_dialogues` — НЕ обновляются. Только Death Guard path (строка 1350-1359) правильно включает `world_snapshot`.
- **Причина:** `yield {"type": "done", "tokens": ..., "ms": ..., "tps": ..., "game_time_seconds": ..., "will_conflict_data": ...}` — `world_snapshot` отсутствует. `state` здесь это `_PipelineState` (game_loop/__init__.py:82), который НЕ имеет поля `world_snapshot`. Phase 9 (`integration.py:584`) строит `ctx.world_snapshot`, но `_run_pipeline` не пробрасывает его в `_PipelineState`.
- **Фикс:** (1) Добавить `world_snapshot: Optional[Any] = None` в `_PipelineState`. (2) В `_run_pipeline` после `_tick_orch.execute()` прочитать `TickResultDTO.world_snapshot` и сохранить в `_PipelineState`. (3) В `stream_turn` построить `WorldSnapshotDTO` и передать в `done`:
  ```python
  yield {
      "type": "done",
      "tokens": token_count, "ms": elapsed_ms, "tps": tps,
      "game_time_seconds": _ss_scene.get("game_time_seconds", 0),
      "will_conflict_data": ...,
      "world_snapshot": _ws_dict,  # ← ДОБАВИТЬ
  }
  ```
- **Статус:** STILL_BROKEN

#### BUG-FB-008 — `_get_fallback_text` всё ещё возвращает "Ничего не произошло." для 5 из 8 классов нарушений
- **Файл:строка:** `frontend/game_screen.py` (метод `_get_fallback_text`)
- **Severity:** Low
- **Симптом:** 5 из 8 классов нарушений возвращают один и тот же generic fallback текст. Игрок не может различить "LLM timeout", "contract violation", "validation failure", "content policy block" — всё выглядит как "Ничего не произошло".
- **Фикс:** Дифференцировать fallback тексты для каждого класса нарушений (напр. "Система нарратива перегружена" для timeout, "Действие отклонено" для content policy).
- **Статус:** STILL_BROKEN

#### BUG-FB-012 — `world_scheduler.maybe_tick` использует wall-clock `datetime.now(timezone.utc)`
- **Файл:строка:** `backend/app/services/world_scheduler.py:32`
- **Severity:** High (нарушение L15)
- **Симптом:** World scheduler (фоновый тик мира) использует wall-clock time для решения "прошло ли N минут реального времени". При сохранении/загрузке сейва поведение недетерминировано: один и тот же save даст разные результаты в зависимости от того, когда игра была запущена. Replay determinism (ADR-O-201) нарушен.
- **Причина:** `now = datetime.now(timezone.utc)` — wall-clock.
- **Фикс:** Использовать каузальный tick counter (`game_time_seconds`):
  ```python
  def maybe_tick(self, world_id: str, every_game_seconds: int) -> dict:
      _current_game_time = get_life_engine().get_game_time(world_id)
      _last_tick_at = self._last_tick_game_time(world_id)
      if _last_tick_at and _current_game_time - _last_tick_at < every_game_seconds:
          return {"triggered": False, ...}
  ```
- **Статус:** STILL_BROKEN

#### BUG-FB-017 — `game_loop_bridge.py` хардкодит `tavern_silver_wolf` как fallback
- **Файл:строка:** `frontend/game_loop_bridge.py:107` и `:127`
- **Severity:** High
- **Симптом:** При запуске новой кампании без сохранённого `current_location`, если `find_starting_location` падает (exception), location остаётся `"tavern_silver_wolf"` — все действия игрока применяются к tavern вместо реальной стартовой локации кампании.
- **Причина:** Комментарий врет: "Убран хардкод tavern_silver_wolf" — но хардкод установлен ДО вызова `find_starting_location` и сохраняется если `find_starting_location` бросает исключение.
- **Фикс:** Использовать `DEFAULT_LOCATION_ID` из `app.core.constants`:
  ```python
  from app.core.constants import DEFAULT_LOCATION_ID
  def turn(self, ..., location: str = DEFAULT_LOCATION_ID, ...):
      location = DEFAULT_LOCATION_ID
      try:
          location = self._loop.find_starting_location(campaign_id)
      except Exception as e:
          logger.warning(f"[BRIDGE] find_starting_location failed: {e}")
  ```
- **Статус:** STILL_BROKEN

#### BUG-FB-021 — `MockProvider._pick_response` проверяет `ENIGMA_ENV` вместо `settings.environment`
- **Файл:строка:** `backend/app/services/llm/mock_provider.py:126`
- **Severity:** High (= BUG-DLG-CAUSAL-4.7.48)
- **Симптом:** См. BUG-DLG-CAUSAL-4.7.48. MockProvider определяет продакшен по `ENIGMA_ENV`, а Settings использует `AIDM_ENVIRONMENT`. Конфигурация не консистентна.
- **Фикс:** См. BUG-DLG-CAUSAL-4.7.48 — использовать `settings.environment`.
- **Статус:** STILL_BROKEN

#### BUG-FB-029 — `WorldSnapshot.created_at = time.time()` + `uuid4()` (wall-clock + non-deterministic UUID)
- **Файл:строка:** `backend/app/models/world_snapshot.py:88-89`
- **Severity:** High
- **Симптом:** Внутренний `WorldSnapshot` (НЕ `WorldSnapshotDTO`) — frozen dataclass с `created_at: float` и `snapshot_id: UUID`. Используется как "Snapshot Kernel" (ADR-O-201). `time.time()` = wall-clock, `uuid4()` = non-deterministic. Один и тот же `scene_state` + event даст разные `snapshot_id`/`created_at` между запусками → нарушает "Первый закон причинности ENIGMA: Одинаковый Snapshot + Одинаковый Event = Одинаковый Result".
- **Фикс:**
  ```python
  snapshot = WorldSnapshot(
      snapshot_id=_seeded_uuid(tick, campaign_id, location_id),  # hashlib-based
      created_at=float(tick),  # simulation time, not wall-clock
      ...
  )
  ```
- **Статус:** STILL_BROKEN

#### BUG-FB-030 (NEW, Critical) — `run_turn` строит WorldSnapshotDTO БЕЗ `visual_dto`/`audible_dto`/`player_body_topology` (L16.1 нарушен)
- **Файл:строка:** `backend/app/services/game_loop/__init__.py:1239-1245`
- **Severity:** Critical (корневая причина S-5)
- **Симптом:** Для HTTP player action путь (`/api/game/action`) финальный `WorldSnapshotDTO` строится без трёхканальных DTO. Phase 9 integration (`phases/integration.py:584-593`) корректно строит `ctx.world_snapshot` со всеми DTO, но `_run_pipeline` возвращает `_PipelineState` БЕЗ поля `world_snapshot`. `run_turn` игнорирует Phase 9 результат и rebuild-ит через `_builder.build()` без параметров `visual_dto`/`audible_dto`/`player_body_topology`. L16.1 (Three-Channel Presentation) нарушен: frontend никогда не получает `visual_dto`/`audible_dto`/`player_body_topology` для player action.
- **Фикс:** См. BUG-FB-001. Добавить `world_snapshot` в `_PipelineState`, использовать Phase 9 результат вместо rebuild.
- **Статус:** NEW

#### BUG-FB-031 (NEW) — `_run_pipeline` не возвращает `TickResultDTO.world_snapshot` из ядра
- **Файл:строка:** `backend/app/services/game_loop/__init__.py:2004-2013`
- **Severity:** High
- **Симптом:** Phase 9 строит `ctx.world_snapshot = WorldSnapshotDTO(...)` со всеми DTO. `_TickContext` имеет поле `world_snapshot`. Но `_run_pipeline` не пробрасывает `ctx.world_snapshot` в `_PipelineState`. Результат Phase 9 теряется.
- **Фикс:** См. BUG-FB-001.
- **Статус:** NEW

#### BUG-FB-032 (NEW) — `game_screen.py:1665-1670` — dead code
- **Файл:строка:** `frontend/game_screen.py:1665-1670`
- **Severity:** Medium
- **Симптом:** Frontend пытается читать `result.response.player_body_topology`, `result.response.visual_dto`, `result.response.audible_dto` напрямую из response. Но ни `GameActionResponse` ни `TurnResult` НЕ имеют этих полей на верхнем уровне — они вложены в `world_snapshot` dict. `hasattr(result.response, "player_body_topology")` всегда `False`, блок никогда не выполняется.
- **Фикс:** Удалить dead code. Данные уже обновляются через `_action_ws` (world_snapshot).
- **Статус:** NEW

#### BUG-FB-033 (NEW) — `routes.py:876` хардкодит `tavern_silver_wolf` как default для Spatial Observatory
- **Файл:строка:** `backend/app/api/routes.py:876`
- **Severity:** Medium
- **Симптом:** Endpoint `/api/spatial/observatory` при отсутствии `location_id` использует `tavern_silver_wolf`. Если редактор карт открывает не-tavern кампанию, observatory всё равно анализирует tavern.
- **Фикс:** Требовать обязательный `location_id` или использовать `DEFAULT_LOCATION_ID`.
- **Статус:** NEW

#### BUG-FB-034 (NEW) — `scene_state_manager.find_starting_location` хардкодит `"tavern"` как last-resort fallback
- **Файл:строка:** `backend/app/services/scene_state_manager.py:801`
- **Severity:** Medium
- **Симптом:** Если editor JSON не содержит ни одной локации с `player_spawn`, возвращается хардкод `"tavern"`. Это не соответствует ни одному реальному location_id кампании → `lock_for_tick` создаст сцену с несуществующим location_id → все spatial queries упадут.
- **Фикс:** Использовать `DEFAULT_LOCATION_ID` из `app.core.constants` или поднимать `ValueError`.
- **Статус:** NEW

#### BUG-FB-035 (NEW) — `routes_debug.py:99` — broken import `from app.core.game_loop import get_game_loop`
- **Файл:строка:** `backend/app/api/routes_debug.py:99`
- **Severity:** High
- **Симптом:** Endpoint `/api/debug/reset-relationships/{campaign_id}` падает с `ImportError` при вызове. Модуль `app.core.game_loop` НЕ существует. Корректный путь — `app.services.game_loop_accessor`.
- **Фикс:** `from app.services.game_loop_accessor import get_game_loop`.
- **Статус:** NEW

#### BUG-FB-036 (NEW) — L21 violation: `print()` в production коде (11 файлов, 35+ вызовов)
- **Файл:строка:** multiple (spatial_service.py, graph_compiler.py, world_sim_agent.py, game_loop/__init__.py, world_snapshot_builder.py, llama_cpp_provider.py, и др.)
- **Severity:** Medium
- **Симптом:** Production stdout загрязнён 35+ `print()` вызовами. L21: "Использование `print()` в production запрещено (только `logger.debug`)".
- **Фикс:** Заменить все `print()` на `logger.debug()` / `logger.info()`.
- **Статус:** NEW

#### BUG-FB-037 (NEW) — `EventDTO.create` использует `time.time()` и `uuid4()` по умолчанию
- **Файл:строка:** `backend/app/domain/events.py` (метод `EventDTO.create`)
- **Severity:** Medium
- **Симптом:** `EventDTO.create` default'ит `timestamp=time.time()` и `event_id=uuid4()` — wall-clock + non-deterministic. Все events получают разные IDs между запусками. Replay determinism нарушен.
- **Фикс:** Сделать `timestamp` и `event_id` обязательными параметрами (caller передаёт `game_time_seconds` и deterministic ID).
- **Статус:** NEW

#### BUG-FB-038 (NEW) — `WorldProjectionBuffer.project` использует `uuid.uuid4()` для `event_id`
- **Файл:строка:** `backend/app/services/offscreen/world_projection_buffer.py`
- **Severity:** Medium
- **Симптом:** Offscreen simulation events получают non-deterministic UUIDs. `WorldProjectionBuffer` (L16: pure function) должен быть детерминирован.
- **Фикс:** Использовать seeded UUID на основе (tick, npc_id, salt).
- **Статус:** NEW

#### BUG-FB-039 (NEW) — `scene_init._reconcile_elapsed_time` использует `time.time()` (wall-clock)
- **Файл:строка:** `backend/app/services/game_loop/scene_init.py`
- **Severity:** Medium
- **Симптом:** `_reconcile_elapsed_time` вычисляет elapsed time через `time.time()` — wall-clock. При save/load elapsed time различается.
- **Фикс:** Использовать `game_time_seconds` из save.
- **Статус:** NEW

#### BUG-FB-040 (NEW) — `SqlitePersistenceAdapter._upsert` использует `datetime.now(timezone.utc)` для `updated_at`
- **Файл:строка:** `backend/app/services/state/sqlite_persistence_adapter.py`
- **Severity:** Medium
- **Симптом:** `updated_at` поле = wall-clock. При replay `updated_at` различается → детерминизм нарушен.
- **Фикс:** Использовать `game_time_seconds` или сделать `updated_at` опциональным (audit only, не для логики).
- **Статус:** NEW

#### BUG-FB-041 — `routes.py:update_scene_state` принимает scene_state от frontend по block-list
- **Файл:строка:** `backend/app/api/routes.py:806-831`
- **Severity:** High
- **Симптом:** Frontend может перезаписать почти любой ключ `scene_state` через POST. Block-list содержит только 7 ключей. Все остальные ключи (`npc_positions`, `objects`, `environment`, `location_id`, `body_state`, etc.) frontend может мутировать напрямую. Нарушение L15 (Frontend Authority: backend = ONLY source of truth).
- **Фикс:** Перейти с block-list на allow-list (только `npc_positions.player.local_position`).
- **Статус:** STILL_BROKEN

#### BUG-FB-042 (NEW) — `game_loop/__init__.py:1632` — legacy `player_inventory_snapshot` чтение (нарушение L16.1)
- **Файл:строка:** `backend/app/services/game_loop/__init__.py:1632`
- **Severity:** Medium
- **Симптом:** GameLoop читает `player_inventory_snapshot` (legacy) вместо `player_body_topology` (SSOT по L16.1). Inventory отображается из устаревшего источника.
- **Фикс:** Заменить на `scene_state.get("player_body_topology")`.
- **Статус:** NEW

#### BUG-FB-043 (NEW) — `api/routes.py:569-595` — `/api/game/action` возвращает `response` вместо `dm_response` (нарушение L4.2)
- **Файл:строка:** `backend/app/api/routes.py:569-595`
- **Severity:** High
- **Симптом:** Endpoint `/api/game/action` возвращает dict с ключом `response` вместо `dm_response`. L4.2: "`GameActionResponse` содержит `dm_response`, `world_snapshot`, `will_conflict_data`". Frontend, ожидающий `dm_response`, получает `None`.
- **Фикс:** Заменить `response` на `dm_response` в return dict.
- **Статус:** NEW

#### BUG-FB-044 (NEW) — `l1_chronicle.archive_old_events` не имеет UNIQUE constraint → дубликаты в архиве
- **Файл:строка:** `backend/app/services/npc/l1_chronicle.py`
- **Severity:** Medium
- **Симптом:** Archive table не имеет UNIQUE constraint на `(event_id, tick)`. При retry archive operation появляются дубликаты. L1Chronicle раздувается.
- **Фикс:** Добавить `UNIQUE(event_id, tick)` constraint в archive table schema.
- **Статус:** NEW

---

## 4. ПЛАН ИСПОЛНЕНИЯ (Приоритет и последовательность фиксов)

### Фаза 1: Critical (P0) — без них игра нефункциональна

| # | Bug ID | Домен | Оценка | Зависимости |
|---|--------|-------|--------|-------------|
| 1 | BUG-CORE-003 | Core | 2ч | Нет. Разблокирует player→NPC causal pipe |
| 2 | BUG-PERC-030 | Perception | 0.5ч | Нет. Одна строка `from dataclasses import replace` |
| 3 | BUG-PERC-031 | Perception | 0.5ч | Нет. Добавить `@dataclass` decorator |
| 4 | BUG-PERC-032 | Perception | 2ч | Унификация NPCStateSnapshot |
| 5 | BUG-DLG-041 | Dialogue | 0.5ч | Нет. Одна строка импорта |
| 6 | BUG-SPATIAL-029 | Spatial | 1ч | Нет. Одна строка `set_overlay()` |
| 7 | BUG-FB-001 + BUG-FB-030 + BUG-FB-031 | Frontend | 4ч | Взаимосвязаны — фиксить вместе |
| 8 | BUG-DLG-002 | Dialogue | 2ч | Зависит от BUG-CORE-003 |
| 9 | BUG-DLG-004-partial | Dialogue | 0.5ч | Нет. Добавить `player_flees` |
| 10 | BUG-DLG-005 | Dialogue | 2ч | Нет. `while`-цикл drain |
| 11 | BUG-DLG-010 | Dialogue | 1ч | Нет. Удалить L2 memory block |
| 12 | BUG-PERC-005 + BUG-PERC-006 | Combat | 3ч | HP SSOT unification |

**Итого Phase 1:** ~19 часов. После этой фазы игра функциональна: player actions видны NPC, бой работает, HP консистентен, affective decay работает, трёхканальные DTO доставляются.

### Фаза 2: High (P1) — серьёзные архитектурные нарушения

| # | Bug ID | Домен | Оценка | Зависимости |
|---|--------|-------|--------|-------------|
| 1 | BUG-CORE-019 | Core | 0.5ч | Нет |
| 2 | BUG-CORE-015 | Core | 2ч | Нет |
| 3 | BUG-CORE-013 | Core | 3ч | StateApplicator refactor |
| 4 | BUG-CORE-021 + BUG-PERC-003 | Combat | 3ч | KernelRNG migration |
| 5 | BUG-CORE-023 | Economy | 1ч | KernelRNG |
| 6 | BUG-DLG-006 | Dialogue | 2ч | game_time_seconds propagation |
| 7 | BUG-DLG-007 + BUG-DLG-008 | Memory | 1ч | Session key unification |
| 8 | BUG-DLG-009 | Dialogue | 1ч | Status enum |
| 9 | BUG-DLG-011 | Dialogue | 2ч | Capability map + GenerationParams |
| 10 | BUG-DLG-043 + BUG-DLG-044 | LLM | 2ч | KernelRNG |
| 11 | BUG-DLG-CAUSAL-4.7.48 + BUG-FB-021 | LLM | 0.5ч | settings.environment |
| 12 | BUG-DLG-CAUSAL-4.7.49 | DM-Agent | 1ч | DMResponseNormalizer |
| 13 | BUG-PERC-004 | Combat | 1ч | KernelRNG |
| 14 | BUG-PERC-013 + BUG-FB-044 | Memory | 2ч | L1Chronicle refactor |
| 15 | BUG-PERC-014 | Memory | 0.5ч | phase_2_events gate |
| 16 | BUG-PERC-025 | Perception | 3ч | DecisionHub restructure |
| 17 | BUG-PERC-029 | Affective | 0.5ч | DEAD check |
| 18 | BUG-PERC-036 + BUG-PERC-037 | Combat | 3ч | HP SSOT + DEAD check |
| 19 | BUG-SPATIAL-015 | Spatial | 2ч | graph_compiler zone_id |
| 20 | BUG-SPATIAL-030 | Spatial | 2ч | ClusterGraph |
| 21 | BUG-SPATIAL-032 | Spatial | 0.5ч | Удалить player_spatial read |
| 22 | BUG-FB-012 | World | 2ч | game_time_seconds |
| 23 | BUG-FB-017 + BUG-FB-033 + BUG-FB-034 | Frontend | 1ч | DEFAULT_LOCATION_ID |
| 24 | BUG-FB-029 + BUG-FB-037 + BUG-FB-038 | Determinism | 3ч | Seeded UUID |
| 25 | BUG-FB-035 | API | 0.5ч | Import fix |
| 26 | BUG-FB-041 | API | 2ч | Allow-list |
| 27 | BUG-FB-043 | API | 0.5ч | dm_response key |

**Итого Phase 2:** ~42 часов. После этой фазы ADR-контракты соблюдены, replay determinism восстановлен, архитектурные нарушения устранены.

### Фаза 3: Medium + Low (P2 + P3) — качество и code hygiene

Оставшиеся ~36 багов (BUG-CORE-016/017/022/024/025/026/027/028, BUG-DLG-014/042/045/046/048/049/050/051/052, BUG-PERC-033/034/035/038/039/040/041, BUG-SPATIAL-023/026/031/033/034/035/036/037/038, BUG-FB-008/032/036/039/040/042/044).

**Итого Phase 3:** ~25 часов. Оценка: ~0.5–1ч на баг.

---

## 5. ВЕРИФИКАЦИЯ ПОСЛЕ ФИКСА

После каждой фазы выполнять:

1. **IPT (Invariant Probe Tests):** `python backend/tests/IPT.py` — все тесты должны pass.
2. **Replay determinism test:** Запустить один и тот же save 2 раза, сравнить `world_snapshot` побитово.
3. **Contract linting:** `ruff check .` — без ошибок.
4. **Full playthrough canary:** `python backend/tests/canary/test_full_playthrough.py` — игрок проходит tavern сценариий: атакует NPC, угрожает трактирщику, спит, торгует. Все 4 действия должны вызвать наблюдаемые NPC-реакции.
5. **Affective decay test:** Запустить idle_tick на 100 ticks, проверить что `AffectiveImprint.reinforcement` затухает.
6. **Three-channel DTO test:** Вызвать `/api/game/action`, проверить что `world_snapshot.visual_dto` / `audible_dto` / `player_body_topology` не `None`.
7. **HP consistency test:** После боя проверить `body_state["current_hp"] == state.hp` (если `hp` ещё существует).

---

## 6. АРХИТЕКТУРНЫЕ РЕКОМЕНДАЦИИ (Долгосрочные)

1. **Унификация `NPCStateSnapshot`:** Сейчас `body_state` поля (pain, fatigue, shock, life_status, current_hp) раскиданы между top-level и `body_state` dict в разных consumers. Унифицировать: `NPCStateSnapshot.body_state: dict` всегда содержит все поля. Это устранит BUG-PERC-032/033/034 и предотвратит будущие regression.

2. **Module-level `replace` import audit:** BUG-PERC-030 (`NameError: 'replace'`) — симптом. Провести audit всех файлов, использующих `dataclasses.replace`, убедиться что импорт module-level, не локальный.

3. **KernelRNG enforcement через linting:** Создать ruff plugin, который запрещает `import random` и `random.*` в `backend/app/services/` (кроме `kernel_rng.py`). Это предотвратит будущие BUG-CORE-021..027 regression.

4. **`game_time_seconds` propagation contract:** Зафиксировать в ADR, что `game_time_seconds` — единственный источник времени, и все cooldown/timestamp/scheduler должны принимать его параметром. Удалить `time.time()` / `datetime.now()` из всех non-audit путей.

5. **Frontend Authority allow-list:** Заменить все block-list подходы в API routes на allow-list. Frontend может мутировать только `player.local_position` — ничего больше.

6. **`WorldSnapshot` Snapshot Kernel determinism:** Внедрить `_seeded_uuid(tick, campaign_id, location_id)` для всех snapshot_id / event_id. Это восстановит "Первый закон причинности ENIGMA: Одинаковый Snapshot + Одинаковый Event = Одинаковый Result".

7. **`thread_id` lifecycle:** Либо реализовать thread-based dialogue session lookup (BUG-DLG-014), либо удалить `thread_id` из всех DTO. Текущее состояние (генерируется, но не используется) — dead propagation chain.

8. **Dead code cleanup:** `LifeEngine.tick_decisions` (BUG-CORE-016, 500+ строк), `try_reserve_node` (BUG-SPATIAL-037), `PerceptualAttentionService` (BUG-PERC-040), `resolve_reactions` (BUG-CORE-027) — удалить или подключить к pipeline.

---

## 7. КЛЮЧЕВАЯ ИДЕЯ

ENIGMA V.0.5.3.6.8 — это не сломанная игра, а **незавершённая миграция**. Архитектурные контракты (CAUSAL_CONTRACT v2.0, ADR Master Index) корректны и полны. Проблема — в execution: 4 незавершённые миграции + 3 новые регрессии оставили "узкие места", через которые не проходят данные.

Порядок фикса критичен:
1. **Сначала BUG-CORE-003** (hub_event) — без него player actions невидимы NPC, и все остальные фиксы нельзя верифицировать.
2. **Затем BUG-PERC-030/031/032** (affective decay) — без них симуляция "зависает" в перманентном шоке.
3. **Затем BUG-FB-001/030/031** (three-channel DTO) — без них frontend слеп к визуальному/аудио состоянию.
4. **Затем combat/HP bugs** — без них бой недетерминирован и HP неконсистентен.

После Phase 1 (Critical) игра становится функциональной. После Phase 2 (High) — архитектурно чистой. После Phase 3 (Medium/Low) — production-ready.
