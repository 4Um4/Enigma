# ТЗ: ПОЛНОЕ ВОССТАНОВЛЕНИЕ РАБОТОСПОСОБНОСТИ ENIGMA V.0.5.3.6.7

> **Документ:** Техническое задание на исправление дефектов кода
> **Версия проекта:** Enigma-V.0.5.3.6.7
> **Дата анализа:** 2026-08-01
> **Метод:** Статический анализ исходников + чтение логов + сверка с CAUSAL_CONTRACT v2.0, ADR, MUTATIONS
> **Объём:** 167 дефектов (18 Critical, 35 High, 54 Medium, 60 Low)
> **Аудит покрыл:** 5 доменов, ~708 .py файлов, 32 ключевых лог-файла

---

## 0. EXECUTIVE SUMMARY

Кодовая база ENIGMA V.0.5.3.6.7 находится в состоянии **«частично проведённого рефакторинга»** — между S98 (внедрение `TickState`/`TickMutation`) и S145 (Dialogue Thread System) было разрушено несколько ключевых мостов, и теперь 5 основных подсистем игры **функционально сломаны**, хотя формально компилируются и проходят часть IPT-тестов.

### Пять ключевых симптомов, которые видит игрок

| # | Симптом | Корневая причина (Top-3 контрибьютора) | Домен |
|---|---------|----------------------------------------|-------|
| **S-1** | `DM: Ничего не произошло.` на любое действие игрока | BUG-CORE-003 (рвётся `dm_ctx`-мост), BUG-DLG-002 (DM-agent кидает `ValueError`), BUG-DLG-003 (`all_npcs_raw_snapshot` никогда не присваивается), BUG-DLG-018 (`ResponseValidator` режет 4-ю стену), BUG-FB-008 (8 классов нарушений → один fallback-текст) | Core + Dialogue + Frontend |
| **S-2** | `PlayerPerceptionDTO` всегда пустой (manifestations={}, observed_facts=[], active_perceptions=[]) | BUG-PERC-001 (GameLoop переписывает perception сырым domain-DTO, минуя `_convert_perception`), BUG-PERC-008 (фильтр отсекает спокойных NPC), BUG-FB-001 (SSE `done` не несёт `world_snapshot`), BUG-CORE-006 | Perception + Frontend |
| **S-3** | NPC после сна оказываются на `loc=city_gate, node=exit_west` вместо `tent_*/guard_bed*` | BUG-SPATIAL-001 (cross-loc materialize перезаписывает `target_node_id`), BUG-CORE-004 (`spatial_service` обнуляется каждый тик), BUG-SPATIAL-015 (`resolve_affordance` зонально фильтрует bed), BUG-CORE-005 (movement_intents не эмитятся для не-спящих), BUG-FB-002 (`skip_time` не вызывает `commit_tick_result`/`unlock_tick`) | Spatial + Core + Frontend |
| **S-4** | Угрозы игрока (`угрожать трактирщику ножом`) не вызывают ни страха, ни боя | BUG-PERC-002 / BUG-DLG-019 (`_evt_map` не содержит `player_threatens` → всё падает в `PLAYER_SPOKE`), BUG-DLG-020 (`ReactionSubscriber` не подписан на `PLAYER_SPOKE`) | Dialogue + Perception |
| **S-5** | Dialogue queue спамится 10+ ambient-задачами в один тик | BUG-CORE-010 / BUG-DLG-005 (`execute_pending` энqueue'ит всё, dequeue'ит одно), BUG-DLG-006 (TTL на wall-clock вместо `game_time_seconds`), BUG-DLG-009 (неразличимый возврат `None` из `dequeue_next`) | Dialogue + Core |

### Главный архитектурный диагноз

В проекте **выполнено 5 «незавершённых» миграций**:

1. **Миграция ADR-TZ09-1 (`TickState`/`TickMutation`) →** завершена наполовину. `dm_ctx`-мост между GameLoop и TickState не построен (BUG-CORE-003) → ядро не видит действия игрока.
2. **Миграция ADR-TRAV-FSM (FSM `transition_traversal`) →** FSM существует в `traversal_schema.py`, но **ни одного call site**. Все переходы статусов делаются прямой мутацией (BUG-SPATIAL-005, BUG-SPATIAL-026).
3. **Миграция ADR-O-314 (`player_spatial` удалён) →** запись отключена, но чтение `_enrich_local_positions:1681-1696` всё ещё работает как авторитетный источник (BUG-SPATIAL-004).
4. **Миграция Dual-Rail (ADR-O-201) →** 135 строк кода в `tick_orchestrator.execute()` оказались за ранним `return` (BUG-CORE-001) → Shadow Observer, AdaptiveTickLoader, equivalence_validator никогда не запускаются.
5. **Миграция PlayerPerceptionDTO (domain → snapshot) →** созданы два разных `PlayerPerceptionDTO`-класса с одинаковым именем. GameLoop не вызывает `_convert_perception` перед перезаписью snapshot (BUG-PERC-001).

Каждая из этих миграций — это «узкое место», через которое не проходят данные, и вокруг которого копятся workaround'ы (silent `try/except: pass`).

---

## 1. КАРТА ДЕФЕКТОВ ПО ДОМЕНАМ

| Домен | Кол-во багов | Critical | High | Medium | Low | Файл-отчёт |
|-------|--------------|----------|------|--------|-----|------------|
| DOM-01: Core Tick Pipeline | 18 | 5 | 5 | 5 | 3 | `domain_core.md` |
| DOM-02: Dialogue / LLM / Task Scheduler / DM-Agent | 40 | 7 | 9 | 12 | 12 | `domain_dialogue.md` |
| DOM-03: Perception / Phenomenology / Physiology / Combat / Affective | 29 | 4 | 9 | 9 | 7 | `domain_perception.md` |
| DOM-04: Spatial / Movement / Traversal | 30 | 1 | 9 | 11 | 9 | `domain_spatial.md` |
| DOM-07: Frontend / Backend / Persistence / World Continuity | 50 | 4 | 9 | 14 | 23 | `domain_frontend.md` |
| **ИТОГО** | **167** | **21** | **41** | **51** | **54** | — |

> **Критические баги (Critical, P0):** блокируют основной игровой цикл. Без их исправления игра нефункциональна.
> **Высокий приоритет (High, P1):** серьёзные архитектурные нарушения или сломанные подсистемы.
> **Средний приоритет (Medium, P2):** снижают качество симуляции, но не блокируют.
> **Низкий приоритет (Low, P3):** code hygiene, мёртвый код, cosmetic.

---

## 2. АРХИТЕКТУРНЫЕ НАРУШЕНИЯ (Контрактные)

Следующие баги прямо нарушают `CAUSAL_CONTRACT v2.0` или `ADR Master Index`. Это **не косметика, а разрушение онтологии симуляции**.

| Контракт | Нарушение | Bug ID | Файл |
|----------|-----------|--------|------|
| L1 (State Mutation Law) — единственный путь мутации через `StateApplicator.apply_batch()` | Прямая мутация `scene_state["npc_positions"]` в `_rebuild_cluster_occupancy` | BUG-CORE-018 | `tick_orchestrator.py:262-341` |
| L2 (Runtime Purity Law) — `NpcTickPipeline.run()` — чистая функция | `StateApplicator.apply()` вызывается внутри `run()` — побочный эффект на `RelationshipStore` | BUG-CORE-018 | `npc_tick_pipeline.py:609-636` |
| L2 (Runtime Purity) — `random.*` запрещён, только `KernelRNG` | `ResolutionEngine` использует `random.Random(seed)` | BUG-CORE-012 | `resolution_engine.py:127,145` |
| L2 (Runtime Purity) — `random.*` запрещён | `TaskScheduler` использует `random.choice` | BUG-CORE-011 | `task_scheduler.py:171,199` |
| L2 (Runtime Purity) — `random.*` запрещён в kernel/combat | `ImpactEngine` использует `random.Random(rng_seed)` с `hash()`-сидом | BUG-PERC-003 | `impact_engine.py:24,46,95,131` |
| L2 (Runtime Purity) — `random.*` запрещён | `combat_math.py` fallback к global `random` | BUG-PERC-004 | `combat_math.py:12,50,52,61` |
| L3 (No Retro-Simulation Law) | OK — `macro_simulate` мёртв, `reconcile_state` единственный путь | — | `life_engine.py:283-364` |
| L4 (Silent Failure Prohibition) | 9+ `try/except: pass` и `except Exception` без логирования | BUG-CORE-002, BUG-SPATIAL-023, BUG-DLG-029 и др. | см. §4 |
| L5 (Will & Pressure Law) — WillpowerGate 1 раз за цикл | OK — единственный call site в `phases/input.py:120` | — | — |
| L8 (CFRM & Somatic Gate Law) — Somatic Gate ДО семантического парсинга | Somatic Gate отсутствует до семантического парсинга | BUG-PERC-025 | `decision_hub.py:402-418` |
| L9 (Spatial SSOT) — `player_spatial` мёртв | `_enrich_local_positions` читает `player_spatial` как авторитетный источник | BUG-SPATIAL-004 | `scene_state_manager.py:1681-1696` |
| L10 (Traversal FSM) — `transition_traversal()` — единственный владелец lifecycle | FSM определена, но **0 call sites** — все статусы мутируются напрямую | BUG-SPATIAL-005, BUG-SPATIAL-026 | `traversal_schema.py:55`, `traversal_execution_system.py:86` |
| L11 (Spatial Coherence Validation SC-1...SC-8) | Валидация не реализована — только комментарий | (нет bug ID — отсутствует фича) | `scene_state_manager.py:921` |
| L12 (Physiology & Death Lock) — `body_state["current_hp"]` — единственный SSOT для HP | `combat_math.apply_damage` пишет `target["hp"]` напрямую | BUG-PERC-005 | `combat_math.py:300-322` |
| L12 (Death Lock) — DEAD→ALIVE запрещён | `combat_math.apply_healing` воскрешает мёртвых | BUG-PERC-006 | `combat_math.py:325-340` |
| L12 (Death Lock) — Decay для мёртвых запрещён | `AffectiveDecayHandler` не проверяет `life_status=="DEAD"` | BUG-PERC-029 (O6) | `affective_decay_handler.py:52-93` |
| L12 (Death Lock) — `evaluate_vital_state()` — единственный источник смерти | `combat_math` использует `hp<=0` как источник смерти | BUG-PERC-005 | `combat_math.py:318` |
| L12 (Death Lock) — DEAD→ALIVE через cross-campaign continuity | `world_diff_applicator` пишет `life_status` в корень, не в `body_state` | BUG-FB-007 | `world_diff_applicator.py:40` |
| L14 (Epistemic Memory Law) — L2.5 кристаллизация только при `phase_2_events` | Кристаллизация запускается каждый тик без gate | BUG-PERC-014 | `integration.py:380-422` |
| L14 — Память не генерирует идентичность без каузального входа | OK в pipeline, но BUG-CORE-002 silently отключает L1→L3 projection | BUG-CORE-002 | `tick_orchestrator.py:1260-1265` |
| L13 (Relationship SSOT) — `RelationshipStore` единственный SSOT | OK — нет `relationship_cache` в `NPCState` | — | — |
| L15 (Frontend Authority Law) — Backend = единственный источник истины | `routes.py:update_scene_state` принимает `scene_state` от фронта по block-list | BUG-FB-041 | `routes.py:806-831` |
| L15 — `game_time_seconds` запрещён во фронтенде | Фронтенд сохраняет как инстанс-состояние `self.game_time_seconds` | BUG-FB-045 | `game_screen.py:555,1003,1081,1218` |
| L15 — Wall-clock в симуляции запрещён | `WorldSnapshot.created_at = time.time()` | BUG-FB-013 | `world_snapshot.py:89` |
| L15 — Wall-clock в симуляции запрещён | `world_scheduler.maybe_tick` использует `datetime.now(timezone.utc)` | BUG-FB-012 | `world_scheduler.py:32-34` |
| L15 — Wall-clock в симуляции запрещён | `DialogueQueue` использует `time.time()` для cooldown | BUG-DLG-006 | `dialogue_queue.py:43-50,70,93` |
| L16 (Epistemic Boundary) — DM-agent читает ТОЛЬКО `observed_state` + `embodied_traces` | DM-agent читает `npc_l2_memory_block` (recalled_facts из `narrative_cache`) | BUG-DLG-010 | `dm_phase.py:65-82`, `dm_agent.py:233-236` |
| L17 (Identity Pipeline) — `L1Chronicle` append-only | `archive_old_events` делает `DELETE FROM l1_chronicle_events` | BUG-PERC-013, BUG-FB-020 | `l1_chronicle.py:240-268` |
| L17 — L3 (`EffectiveDrives`) строго эфемерен | OK в `_compute_effective_drives`, но projection сломан BUG-CORE-002 | BUG-CORE-002 | `tick_orchestrator.py:1260-1265` |
| L21 (Invariant Defense) — `SimulationIntegrityError` нельзя ловить try/except в пайплайне | Перехватывается в `movement_engine.py:1244-1247` (`APPLY_CRASH`) | BUG-SPATIAL (try/except audit) | `movement_engine.py:1244-1247` |
| CAUSAL_CONTRACT §4.1.10 — двойная обработка `MovementIntent` с `processed=True` → `RuntimeError` | Инвариант одного исполнения не проверяется | (отсутствует фича) | — |
| CAUSAL_CONTRACT §4.7.48 — `MockProvider` в production запрещён | `MockProvider._pick_response` проверяет `ENIGMA_ENV` вместо `settings.environment` | BUG-FB-021 | `mock_provider.py:126-138` |
| CAUSAL_CONTRACT §4.5.33 — `campaign_id` ≠ `location_id` | `game_loop_bridge.py:127` хардкодит `location = "tavern_silver_wolf"` как fallback | BUG-FB-017 | `game_loop_bridge.py:127` |

---

## 3. БАГ-КАТАЛОГ ПО ДОМЕНАМ

Ниже приведены все 167 дефектов с file:line, симптомом, корневой причиной, severity и предлагаемым фиксом. Дублирование симптомов между доменами намеренное — один и тот же игрок-видимый симптом часто имеет множественные корневые причины.

---

### 3.1. DOM-01: CORE TICK PIPELINE (18 дефектов)

Подробный отчёт: `domain_core.md`. Ниже — выжимка.

#### BUG-CORE-001 — 135 строк мёртвого кода после раннего `return` в `execute()`
- **Файл:строка:** `backend/app/services/tick_orchestrator.py:460-594`
- **Severity:** Critical
- **Симптом:** ADR-O-201 Dual Rail Shadow Observer, AdaptiveTickLoader, equivalence_validator, event_compiler, drift summary — **никогда не выполняются**. Финальная сборка `TickResultDTO` (строки 585-594) не запускается.
- **Причина:** Мультилокационный цикл заканчивается `return _final_result` на строке 458. Legacy single-loc тело (строки 460-594), которое должно было быть удалено, осталось после `return`. ~135 строк мёртвого кода.
- **Фикс:** Удалить строки 460-594 целиком. Если какая-то логика из мёртвого блока ещё нужна (например, CFRM `_deobjectify_event` attach или AdaptiveTickLoader setup), повторно реализовать её внутри активного цикла (строки 411-458) **до** вызова `_run_core_phases(ctx, tick_fully=_tick_fully)`.

#### BUG-CORE-002 — Silent failure в `_compute_effective_drives` → L1 Identity всегда `None`
- **Файл:строка:** `backend/app/services/tick_orchestrator.py:1260-1265`
- **Severity:** Critical
- **Симптом:** L1-черты НИКОГДА не доходят до `DriveResolver.resolve_drives()`. Все NPC drives вычисляются только из L0. Crystallized beliefs и personality drift silently отбрасываются.
- **Причина:** В `_compute_effective_drives(self, npc_list, tick_number)` код делает `_traits = self.memory_manager.get_identity_traits(ctx.campaign_id, _nid)`, но: (a) `self.memory_manager` не существует — только `self._memory_manager` (инициализируется в `__init__` на строке 73); (b) `ctx` не параметр этого метода. Оба исключения `AttributeError` и `NameError` молча глотаются `except Exception: pass`.
- **Фикс:**
  1. Добавить параметр `campaign_id: str` в `_compute_effective_drives`.
  2. Использовать `self._get_memory_manager()` вместо `self.memory_manager`.
  3. Удалить `except Exception: pass` — заменить на явное логирование:
     ```python
     except Exception as e:
         logger.error(f"[L3_PROJECTION] identity traits load failed for {_nid}: {e}")
     ```

#### BUG-CORE-003 — Рваный `hub_event`-мост → действия игрока невидимы для NPC pipeline
- **Файл:строка:** `backend/app/services/pipeline_runner.py:39-43` + `backend/app/services/game_loop/npc_orchestration.py:149-160`
- **Severity:** Critical (корневая причина S-1: «Ничего не произошло»)
- **Симптом:** Игрок атакует/угрожает/разговаривает — NPC реагируют как на `WORLD_TICK`. `Intent.idle score=0.000 event=unknown` в логах.
- **Причина:** `build_tick_state` (pipeline_runner.py:39-43) ищет ключ `"dm_ctx"` в `intervention.payload`:
  ```python
  for interv in ctx.interventions:
      if interv.source == "player" and "dm_ctx" in interv.payload:
          _dm_ctx = interv.payload["dm_ctx"]
          break
  ```
  Но `npc_orchestration.py:149-160` строит `InterventionEvent` с ключами `text`, `player_name`, `semantic_action`, `target_id`, `target_reference`, `tick` — **без `dm_ctx`**. → `_dm_ctx = None` → `state.hub_event = None` → `state.player_target_id = None` → `state.action_type = "idle"`. В `NpcTickPipeline.run` (npc_tick_pipeline.py:136) `_is_player_turn = state.hub_event is not None` = `False`, pipeline работает в idle-режиме.
- **Фикс (вариант A, минимальный):** В `pipeline_runner.build_tick_state` также принимать `ctx.hub_event` напрямую:
  ```python
  _hub_event = getattr(ctx, "hub_event", None)
  _player_target_id = getattr(ctx, "player_target_id", None)
  _action_type = getattr(ctx, "action_type", "idle") or "idle"
  _raw_input = getattr(ctx, "raw_input", "") or ""
  ```
  Передавать эти значения в `create_tick_state` вместо поиска `dm_ctx`.
- **Фикс (вариант B, архитектурный, предпочтителен):** В `npc_orchestration.py` оборачивать resolution в объект `dm_ctx` и класть в `intervention.payload["dm_ctx"]`. Это восстанавливает исходный дизайн.

#### BUG-CORE-004 — LifeEngine `__init__` indentation bug: `spatial_service`/`persistence`/`claim_bus` обнуляются каждый тик
- **Файл:строка:** `backend/app/services/npc/life_engine.py:246-258`
- **Severity:** Critical (часть корневой причины S-3)
- **Симптом:** `SpatialService`, `PersistencePort`, `DRFBus` молча сбрасываются в `None` после каждой Фазы 5. ADR-128 SQLite read-back молча отключён после первого тика. MovementEngine получает `None`-сервис и падает в CROSS_LOC_INTERCEPT-фоллбэк (отправляет NPC на boundary nodes).
- **Причина:** Строки 250-258 (`self._spatial_service = None`, `self._persistence = None`, `self._claim_bus = None`) находятся **внутри** метода `update_idle_pressure` (строки 246-248), а не внутри `__init__`. Должны быть в `__init__`. Каждый вызов `update_idle_pressure(updates)` (через `tick_orchestrator.py:1391`) обнуляет эти инстанс-атрибуты.
- **Фикс:** Перенести строки 250-258 в `__init__` (сразу после `self._movement_engine = MovementEngine()` на строке 240):
  ```python
  self._movement_engine = MovementEngine()
  self._spatial_service: Optional[Any] = None
  self._persistence: Optional[Any] = None
  self._claim_bus: Optional["DRFBus"] = None
  ```
  Метод `update_idle_pressure` должен содержать **только** `self._idle_pressure.update(updates)`.

#### BUG-CORE-005 — Не-спящие NPC никогда не эмитят movement_intents
- **Файл:строка:** `backend/app/services/npc/npc_tick_pipeline.py:545-606`
- **Severity:** Critical (часть корневой причины S-3)
- **Симптом:** NPC с `Intent.APPROACH`/`FLEE`/`SEEK_ALLY` (всё, кроме attack) и не спящие в данный момент — их movement intents молча дропаются. `movement_intents` всегда пуст для нормального реактивного NPC-поведения. Sleep test подтверждает: NPC на `loc=city_gate` вместо tent/bed.
- **Причина:** If/elif-структура обрабатывает только две ветви:
  ```python
  if _intent_value in _MOVE_INTENTS and _current_routine.get("current") == "sleeping":
      # SLEEP_GUARD — блокирует движение спящих
      ...
  elif _intent_value == "attack":
      # ATTACK branch — строит CommunicationIntent
      ...
  # НЕТ ELSE: не-спящие, не-attack movement intents (approach, flee, ...) потеряны
  ```
  Дополнительно: внутри sleep-ветви (строка 550) `_intent_value = "idle"` устанавливается **до** вызова `_resolve_reactive_movement(intent=_intent_value, ...)` (строка 556), поэтому resolver получает "idle" и возвращает `None`.
- **Фикс:** Реструктурировать диспетчер:
  ```python
  if _intent_value == "attack":
      # build CommunicationIntent for attack
      ...
  else:
      # ВСЕ movement-capable intents (approach, flee, seek_ally, ...) ВКЛЮЧАЯ idle sleeping
      if _current_routine.get("current") == "sleeping" and _intent_value in _MOVE_INTENTS:
          logger.info(f"[SLEEP_GUARD] npc={npc_id} blocking reactive movement={_intent_value}")
          _intent_value = "idle"
          decision = dataclasses.replace(decision, decision=dataclasses.replace(decision.decision, intent=Intent.IDLE))
      if _intent_value in _MOVE_INTENTS:
          _movement = _resolve_reactive_movement(
              npc_id=npc_id, intent=_intent_value,
              intent_target=decision.intent_target or "player",
              scene_state=dict(state.scene_state),
              location_id=state.scene_state.get("location_id", ""),
              spatial_service=state.spatial_service,
              spatial_query=state.spatial_query,
              drf_ctx=_npc_drf_ctx,
          )
          if not _movement and state.spatial_service:
              _target_node = _resolve_proactive_target(
                  intent_value=_intent_value, npc_id=npc_id,
                  intent_target=decision.intent_target,
                  scene_state=dict(state.scene_state),
                  spatial_service=state.spatial_service,
                  location_id=state.scene_state.get("location_id", ""),
              )
              if _target_node:
                  from app.domain.movement import MacroMovementGoal
                  _movement = MacroMovementGoal(
                      actor_id=npc_id, target_node_id=_target_node,
                      reason=f"proactive_{_intent_value}",
                      body_capabilities=state_l2.body_capabilities,
                  )
          if _movement:
              movement_intents.append(_movement)
  ```

#### BUG-CORE-006 — GameLoop `_project_perception` перезаписывает perception из Фазы 9, теряя `observed_facts`
- **Файл:строка:** `backend/app/services/perception/perception_projector.py:34-56` + `backend/app/services/game_loop/__init__.py:956-963, 1054-1060, 1236-1242`
- **Severity:** High (часть корневой причины S-2)
- **Симптом:** `Empty PlayerPerceptionDTO (manifestations={}, observed_facts=[], active_perceptions=[])`. Фаза 9 уже собирает корректный DTO с `observed_facts=_facts_for_dm`, но GameLoop перезаписывает его свежей проекцией БЕЗ `observed_facts`.
- **Причина:** `PerceptionProjector.project(scene_state, all_npcs_raw, tick)` вызывает `self._project_svc.project(_traces, scene_state, tick=tick)` — без аргумента `observed_facts=`, который `PhenomenologyProjectionService.project()` принимает как опциональный 4-й параметр. Затем GameLoop делает `dataclasses.replace(result.world_snapshot, player_perception=_perception)`, перезаписывая версию Фазы 9.
- **Фикс (трёхчастный):**
  1. В `PerceptionProjector.project()` принимать и форвардить `observed_facts`:
     ```python
     def project(self, scene_state, all_npcs_raw, tick, observed_facts=None):
         ...
         return self._project_svc.project(_traces, scene_state, tick=tick, observed_facts=observed_facts)
     ```
  2. В GameLoop `idle_tick` (строки 956-963): **удалить** override целиком — Фаза 9 уже собрала корректную перцепцию.
  3. В `run_turn` (строки 1236-1242) прокинуть `observed_facts=getattr(state, "observed_facts", [])` в builder, либо пропустить rebuild и переиспользовать `_tick_result.world_snapshot`.

#### BUG-CORE-007 — Phase 8 social_input_projector крашится на `SimpleNamespace` shared_context
- **Файл:строка:** `backend/app/services/phases/reduction.py:178-181` + `backend/app/services/events/social_input_projector.py:93, 111`
- **Severity:** High
- **Симптом:** Лог: `[PHASE8_CRASH] handler=social_input error=AttributeError: 'types.SimpleNamespace' object has no attribute 'scene_state'. Events lost this tick.`
- **Причина:** `reduction.py:178-181` создаёт fallback `SimpleNamespace()` для `ctx.shared_context` когда он `None`, но НЕ устанавливает атрибут `scene_state`. Затем `social_input_projector.py:93,111` обращается к `ctx.shared_context.scene_state or {}`, что вызывает `AttributeError`. Ошибка ловится в `reduction.py:214-222` и молча логируется.
- **Фикс (два комплементарных):**
  1. В `reduction.py:179-181` также установить `scene_state`:
     ```python
     ctx.shared_context = SimpleNamespace()
     ctx.shared_context.scene_state = ctx.scene_state  # carry the source of truth
     ```
  2. В `social_input_projector.py:93, 111` использовать defensive `getattr`:
     ```python
     scene_state=getattr(ctx.shared_context, "scene_state", None) or ctx.tick_ctx.scene_state or {},
     ```

#### BUG-CORE-008 — GameLoop пишет в `_tick_scene`, SceneStateManager использует `_tick_scenes`
- **Файл:строка:** `backend/app/services/game_loop/__init__.py:1642`
- **Severity:** High
- **Симптом:** Лог: `AttributeError: 'SceneStateManager' object has no attribute '_tick_scene'. Did you mean: '_tick_scenes'?`. Когда `lock_for_tick` возвращает `None` (сцена не залочена), GameLoop пытается вручную инициализировать сцену через `self.scene_manager._tick_scene = scene_state` — но SSM имеет только `_tick_scenes: Dict[str, dict]` (множественное).
- **Причина:** Рефакторинг ADR-SCENE-LOCK перевёл SSM на dict-keyed-by-location (`_tick_scenes`), но `game_loop/__init__.py:1642` всё ещё использует legacy singular `_tick_scene`.
- **Фикс:** Заменить строки 1642-1644 на:
  ```python
  scene_state = init_scene_state(self, campaign_id, _loc_id, shared_context, campaign_state, player_position=player_position)
  # ADR-SCENE-LOCK: вставить в _tick_scenes dict, не _tick_scene singular
  self.scene_manager._tick_scenes[_loc_id] = scene_state
  self.scene_manager._tick_locked = True
  self.scene_manager._tick_campaign_id = campaign_id
  ```
  Лучше: вызывать `self.scene_manager.lock_for_tick(campaign_id, _loc_id, force=True)` — единый SSOT.

#### BUG-CORE-009 — `phase_2_world_tick.py` деструктурирует proactive NPC tuple неправильно
- **Файл:строка:** `backend/app/services/game_loop/phase_2_world_tick.py:149`
- **Severity:** Medium
- **Симптом:** `NeedEngine.tick` получает `current_activity=""` для каждого NPC, потому что `_wt_npc_raw` на самом деле `NPCState`-объект, а не raw dict. Recovery и need decay считаются против неправильной activity, вызывая ложные голод/усталость во время сна и отдыха.
- **Причина:** `_proactive_npc_data` строится как список `(_pid, _p_l2, _p_l0)` tuples (где `_p_l2 = load_l2_state_from_runtime_dict(_n)` — NPCState-объект). Но потребитель на строке 149 деструктурирует как `for _pid, _wt_npc_raw, _ in _proactive_npc_data:` → `_wt_npc_raw = _p_l2` (NPCState). Затем `isinstance(_wt_npc_raw, dict)` = `False`, ветка `hasattr(_wt_npc_raw, "routine")` обращается к `_p_l2.routine` — это скорее всего строка/enum, не dict.
- **Фикс:**
  ```python
  for _pid, _p_l2, _p_l0 in _proactive_npc_data:
      _wt_npc_raw = next(
          (_n for _n in tick_ctx.all_npcs_raw
           if (_n.get("id") or _n.get("npc_id")) == _pid),
          None,
      )
      if not _wt_npc_raw:
          continue
      _wt_current_activity = _wt_npc_raw.get("routine", {}).get("current", "")
      _wt_ne.tick(_wt_ep, current_activity=_wt_current_activity)
  ```

#### BUG-CORE-010 — Dialogue queue спам: `pending_tasks` пере-enqueue'ятся каждый тик
- **Файл:строка:** `backend/app/services/game_loop/task_scheduler.py:92-138`
- **Severity:** High (корневая причина S-5)
- **Симптом:** `DialogueQueue._heap` растёт безгранично между тиками. 10+ ambient задач в один тик.
- **Причина:** `execute_pending(scene_state, campaign_id)`: (1) итерирует ВСЕ `pending_tasks` и enqueue'ит каждый в `self._dialogue_queue` (строки 98-119). (2) Dequeue'ит ТОЛЬКО ОДНУ задачу через `dequeue_next()` (строка 121). (3) Удаляет ТОЛЬКО dequeued задачу из `pending_tasks` (строки 129-131). Остальные 9+ задач остаются И в `pending_tasks`, И в heap. Следующий тик их снова enqueue'ит → 9+1+new = 10+, опять одна обрабатывается.
- **Фикс (вариант A, предпочтителен):** Очищать `pending_tasks` после enqueue — они теперь в ответственности `DialogueQueue`:
  ```python
  for task_dict in pending:
      if task_dict.get("kind") == "dialogue":
          ...self._dialogue_queue.enqueue(...)
  # All tasks moved to queue; clear source list
  scene_state["pending_tasks"] = []
  ```
- **Фикс (вариант B):** Дедупликация в `DialogueQueue.enqueue` — skip если тот же `task_id` уже в heap. Также добавить TTL/eviction policy для задач, сидящих в heap слишком долго.

#### BUG-CORE-011 — `random.choice` вместо KernelRNG в TaskScheduler
- **Файл:строка:** `backend/app/services/game_loop/task_scheduler.py:171, 199`
- **Severity:** Medium (нарушение KernelRNG-контракта)
- **Симптом:** Недетерминированный выбор цели NPC. Реплеи дают разные социальные графы.
- **Причина:** `import random` на строке 171 и `random.choice(_candidates)` на строке 199.
- **Фикс:**
  ```python
  from app.services.npc.kernel_rng import KernelRNG
  ...
  _tick = scene_state.get("tick", 0)
  _rng = KernelRNG(tick=_tick, npc_id=task.owner_id, salt="task_target_resolve")
  _resolved_target = _rng.choice(_candidates) if _candidates else "soliloquy"
  ```

#### BUG-CORE-012 — `ResolutionEngine` использует `random.Random(seed)` вместо KernelRNG
- **Файл:строка:** `backend/app/services/npc/resolution_engine.py:127, 145`
- **Severity:** Medium (нарушение KernelRNG-контракта)
- **Симптом:** Недетерминированные исходы resolution.
- **Причина:** `self._rng = random.Random(seed)` — при `seed=None` использует wall-clock энтропию. Также читает `state.drives_runtime` (строки 153-154), что нарушает L3-P2 (drives_runtime cache должен быть мёртв; только `effective_drives_map`).
- **Фикс:** Заменить `random.Random(seed)` на `KernelRNG(tick=tick, npc_id=state.npc_id, salt="resolution_engine")`. Передавать `effective_drives` от вызывающего, не читать `state.drives_runtime`.

#### BUG-CORE-013 — `l1_drift_events` всегда пустой в `TickMutation`
- **Файл:строка:** `backend/app/services/npc/npc_tick_pipeline.py:150, 642`
- **Severity:** Medium (нарушение контракта)
- **Симптом:** `pipeline_runner.py:102-104` пытается коммитить `mutation.l1_drift_events` в `l1_chronicle` каждый тик — но список ВСЕГДА пуст. TIFL drift events из `compute_continuous_drift` (`break_progress_engine.py:246`) никогда не проходят через pipeline.
- **Причина:** Строка 150 инициализирует `l1_drift_events: List[Any] = []`. Тело цикла (строки 153-636) никогда не добавляет в него. Строка 642 возвращает его как часть `TickMutation`. Реальные L1 events эмитятся `BreakProgressEngine` (через `decision.py:179, 182, 194`) и `compute_continuous_drift` (`phases/integration.py:212-223`), но последний идёт **напрямую** в `l1_chronicle.commit_tick_buffer` — в обход TickMutation-контракта.
- **Фикс:** В `npc_tick_pipeline.py` собирать drift events из `BreakProgressEngine.calculate()` и аппендить `TraitDriftEvent` в `l1_drift_events` внутри per-NPC цикла.

#### BUG-CORE-014 — Мёртвые NPC НЕ исключаются до Фазы 1
- **Файл:строка:** `backend/app/services/tick_orchestrator.py:600-624` (фильтр только в `_phase_5_decision` на строке 1307-1311)
- **Severity:** Medium (нарушение CAUSAL_CONTRACT)
- **Симптом:** Мёртвые NPC (`life_status="DEAD"`) обрабатываются в Фазах 0-4 (NPIC normalize, input merge, willpower gate, event bus, memory, topic extraction). Их body states могут мутировать, они могут публиковать события, потреблять MemoryManager capacity.
- **Причина:** CAUSAL_CONTRACT говорит "Dead NPCs must be excluded before Phase 1". Но фильтр применяется только в `_phase_5_decision` на строке 1307-1311 — ПОСЛЕ того, как Фазы 0-4 уже отработали.
- **Фикс:** Добавить ранний фильтр в начале `_run_core_phases` перед `_phase_0_simulation`:
  ```python
  def _run_core_phases(self, ctx, tick_fully=True):
      # ADR-123: Death Lock — exclude dead NPCs BEFORE any phase
      ctx.all_npcs_raw = [
          n for n in (ctx.all_npcs_raw or [])
          if n.get("body_state", {}).get("life_status") != "DEAD"
      ]
      if hasattr(ctx, "npc_states") and ctx.npc_states:
          ctx.npc_states = [
              n for n in ctx.npc_states
              if n.get("body_state", {}).get("life_status") != "DEAD"
          ]
      self._snapshot_positions_before(ctx)
      self._phase_0_simulation(ctx)
      ...
  ```

#### BUG-CORE-015 — DRF scoring overlay проверяет `npc_id`, но читает `actor_id`
- **Файл:строка:** `backend/app/services/tick_orchestrator.py:1609-1611`
- **Severity:** Low
- **Симптом:** DRF scoring overlay молча мисраутит pressures на неправильного NPC (или ни на кого).
- **Причина:** Строка 1609: `if not hasattr(_intent, "npc_id"):` — проверяет атрибут `npc_id`. Строка 1611: `_npc_id = _intent.actor_id` — читает атрибут `actor_id`. `CommunicationIntent` имеет `speaker`, не `actor_id` или `npc_id`.
- **Фикс:**
  ```python
  for _intent in intents:
      _npc_id = (
          getattr(_intent, "speaker", None)
          or getattr(_intent, "npc_id", None)
          or getattr(_intent, "actor_id", None)
      )
      if not _npc_id:
          continue
  ```

#### BUG-CORE-016 — `LifeEngine.tick_decisions` — мёртвый код (~500 строк)
- **Файл:строка:** `backend/app/services/npc/life_engine.py:632-1132`
- **Severity:** Low (dead code)
- **Симптом:** `tick_decisions` — дубликат `NpcTickPipeline.run`. Только в тестах (`tests/sandbox/test_causal_bridge_integration.py:307`, `tests/test_tick_orchestrator_full_loop.py:103`). Production-путь использует `NpcTickPipeline.run` через `pipeline_runner.run_pipeline`.
- **Причина:** Был legacy Phase 5 entry point. После ADR-TZ09 (Pure Reducer Pattern) orchestrator переехал на `NpcTickPipeline.run`, но `tick_decisions` не удалили.
- **Фикс:** Удалить `tick_decisions` (строки 632-1132) и его тесты. Обновить `phases/README.md:84` (убрать упоминание).

#### BUG-CORE-017 — Дублирующий мёртвый блок `npcs = self._npc_cache.get(campaign_id)` после `return`
- **Файл:строка:** `backend/app/services/npc/life_engine.py:683-694`
- **Severity:** Low
- **Симптом:** Внутри `tick_decisions` (который сам мёртв по BUG-CORE-016), после первого `return ([], [], [])` на строках 679-683, есть дублирующий блок 684-694.
- **Фикс:** Удалить строки 683-694.

#### BUG-CORE-018 — `_phase_2_event_bus_primary` мутирует `ctx.scene_state["npc_positions"]` напрямую
- **Файл:строка:** `backend/app/services/tick_orchestrator.py:262-341` (`_rebuild_cluster_occupancy`)
- **Severity:** Medium (нарушение L1: `Phase8Result → delta_buffer → StateApplicator.apply_batch()` — единственный путь мутации)
- **Симптом:** `_rebuild_cluster_occupancy` пишет восстановленные позиции NPC напрямую в `ctx.scene_state["npc_positions"]` (строки 307-321), в обход StateApplicator. То же для player position на строках 335-341.
- **Фикс:** Эмитить `StateDeltas(domain=DeltaDomain.SPATIAL, payload=...)` для каждого восстановленного NPC и роутить через `ctx.delta_buffer`. StateApplicator применит их в Фазе 10.

---

### 3.2. DOM-02: DIALOGUE / LLM / TASK SCHEDULER / DM-AGENT (40 дефектов)

Подробный отчёт: `domain_dialogue.md`. Ниже — выжимка.

#### BUG-DLG-001 — DM agent fallback глотает все исключения молча
- **Файл:строка:** `backend/app/agents/dm_agent.py:91-108`
- **Severity:** Critical
- **Симптом:** Каждый error path в `narrate()` → `_build_contract()` коллапсирует в `MSG_NOTHING_HAPPENED` без actionable трейса (только `jsonl_log`).
- **Причина:** `run()` оборачивает `narrate()` в `try/except Exception` и безусловно возвращает `self._fallback_narrate()`. Даже `ValueError` из BUG-DLG-002 спрятан.
- **Фикс:** Различать `DialogueContractViolation` (re-raise / вернуть distinct code) от LLM-failure (fallback OK). Минимум — propagate reason в возвращаемый dict: `{"dm_response": MSG_NOTHING_HAPPENED, "error": "contract_violation", "reason": ...}`.

#### BUG-DLG-002 — DM contract кидает на missing target+STM → silent "Ничего не произошло"
- **Файл:строка:** `backend/app/agents/dm_agent.py:245-249`
- **Severity:** Critical (часть корневой причины S-1)
- **Симптом:** Если `extract_player_target` (в `dm_phase.py:49-95`) не резолвит "трактирщику"/"трактирщика" против `name_forms` NPC, `shared_context.player_target_id` остаётся `""`. На любом non-first tick (`_is_intro=False`) с пустым STM DM кидает `ValueError`.
- **Причина:** Hard contract должен предотвращать LLM-галлюцинации NPC-ответов, когда никто не адресован. Но precondition (`_has_target=False`) — неправильный сигнал: смешивает "игрок никого не адресовал" с "target resolver упал".
- **Фикс:** (a) Если `raw_input` содержит известное русское существительное/роль ("трактирщик", "кузнец", "страж"), но resolver вернул пусто — логировать WARN и продолжать с generic narrative вместо raise. (b) Лучше — ослабить gate до "если игрок никого не адресовал И нечего нарративить (нет событий, нет NPC moves)".

#### BUG-DLG-003 — `all_npcs_raw_snapshot` никогда не присваивается в shared_context
- **Файл:строка:** `backend/app/services/game_loop/__init__.py:1051`
- **Severity:** Critical (часть корневой причины S-1)
- **Симптом:** DM agent читает `getattr(context, "all_npcs_raw_snapshot", None)` (`dm_agent.py:451-453`) → всегда `None`. LLM не получает контекста NPC (нет описаний, voice_profile, author_notes) → генерит пустой/мусорный ответ → валидатор его режет.
- **Причина:** Поле объявлено в `PipelineContext` (`app/models/pipeline_context.py:43-45`) и читается в двух местах, но ни один код path его не присваивает.
- **Фикс:** После `state.shared_context.all_npcs_raw = self._resolve_npcs_snapshot(req.campaign_id)` (строка 1051), добавить:
  ```python
  state.shared_context.all_npcs_raw_snapshot = state.shared_context.all_npcs_raw
  ```

#### BUG-DLG-004 — Player threats публикуются как `PLAYER_SPOKE`, обходя reaction subscribers
- **Файл:строка:** `backend/app/services/game_loop/phase_1_input.py:276-283, 335-348`
- **Severity:** Critical (корневая причина S-4)
- **Симптом:** Игрок пишет `угрожать трактирщику ножом`. IntentCompressor классифицирует как `THREATEN`. Override на строке 346 ставит `_raw_type = "player_threatens"`. Но `_evt_map.get("player_threatens", EventType.PLAYER_SPOKE)` fallback'ит в `PLAYER_SPOKE`. → `ReactionSubscriber`, `CombatSubscriber` никогда не получают событие.
- **Причина:** `_evt_map` покрывает только `dialogue`, `player_interacts`, `attack`, `player_attacks`, `move`, `stealth`. Override map (`_IC_PRIORITY_MAP` строки 335-340) эмитит ключи без записи в `_evt_map`.
- **Фикс:** Добавить недостающие записи в `_evt_map`:
  ```python
  "player_threatens": EventType.PLAYER_THREATENS,
  "player_steals":    EventType.THEFT,
  "player_insults":   EventType.PLAYER_INSULTS,
  "player_flees":     EventType.PLAYER_MOVED,
  "intimidation":     EventType.INTIMIDATION,
  ```

#### BUG-DLG-005 — Dialogue queue дренирует только 1 задачу за тик, энqueue'ит все
- **Файл:строка:** `backend/app/services/game_loop/task_scheduler.py:92-138`
- **Severity:** Critical (корневая причина S-5)
- **Симптом:** `execute_pending()` итерирует `pending` и пушит КАЖДУЮ задачу в `_dialogue_queue` (строки 112-119). Затем вызывает `dequeue_next()` ровно один раз (строка 121) и выполняет ТОЛЬКО её (строки 136-138). Остальные 9+ задач остаются в heap навсегда.
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

#### BUG-DLG-006 — `DialogueQueue` использует wall-clock time для cooldown / rate-limit
- **Файл:строка:** `backend/app/services/execution/dialogue_queue.py:43-44, 49-50, 57, 70, 73, 93`
- **Severity:** High (нарушение L15: Wall-clock в симуляции запрещён)
- **Симптом:** `COOLDOWN_PER_NPC_SEC = 30` (реальные секунды), `MAX_RATE_PER_MINUTE = 20`, `enqueued_at = time.time()`. Если игра на паузе или игрок AFK 5 минут, queue "думает", что прошло 5 минут, и сбрасывает все cooldown'ы.
- **Фикс:** Прокинуть `game_time_seconds` из `scene_state` в `enqueue()` / `dequeue_next()`. Заменить `time.time()` на `game_time_seconds`.

#### BUG-DLG-007 — `clear_dialogue_session` использует non-symmetric key
- **Файл:строка:** `backend/app/services/memory/memory_manager.py:100`
- **Severity:** High
- **Симптом:** `get_dialogue_session` (строки 76-77) строит ключ из `tuple(sorted((npc_id, partner_id)))` — симметричный. Но `clear_dialogue_session` использует `f"{campaign_id}:{npc_id}:{partner_id}"` (строка 100) — non-symmetric. Вызов `clear_dialogue_session(campaign, "player", "maid_lusya")` ищет ключ `campaign:player:maid_lusya`, а хранится `campaign:maid_lusya:player` → сессия НЕ очищается, утекает память.
- **Фикс:**
  ```python
  pair_key = tuple(sorted((npc_id, partner_id)))
  key = f"{campaign_id}:{pair_key[0]}:{pair_key[1]}"
  ```

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

#### BUG-DLG-009 — `dequeue_next` глотает rate-limit как "empty queue"
- **Файл:строка:** `backend/app/services/execution/dialogue_queue.py:77-78`
- **Severity:** High
- **Симптом:** Возвращает `None` и когда heap пуст, и когда rate limit hit. Caller не различает → никогда не делает backoff на enqueue.
- **Фикс:** Either raise `RateLimited` exception, либо вернуть `dequeue_status` enum (`EMPTY`/`RATE_LIMITED`/`OK`).

#### BUG-DLG-010 — DM agent читает L2 narrative_cache (recalled_facts)
- **Файл:строка:** `backend/app/services/game_loop/dm_phase.py:65-82`; consumed at `backend/app/agents/dm_agent.py:233-236`
- **Severity:** High (архитектурное нарушение L16)
- **Симптом:** `dm_phase` экстрактит `narrative_cache` для target NPC, вызывает `memory_manager.recall(...)`, инжектит результат в `shared_context.npc_l2_memory_block`. DM agent пишет это в LLM-промпт как `"L2 Memory block"`. Нарушает правило: **"DM-agent читает ТОЛЬКО observed_state и embodied_traces"**.
- **Фикс:** Удалить L2 memory block из DM agent's prompt. Если дизайн-интенция — позволить DM наррировать континуитет, `narrative_cache` NPC должно проявляться через NPC-речь (уже в STM), а не через прямой доступ DM к NPC-памяти.

#### BUG-DLG-011 — `DialogueUpdateExtractor` молча падает на каждом вызове
- **Файл:строка:** `backend/app/services/memory/dialogue_update_extractor.py:38-49`
- **Severity:** High
- **Симптом:** Три независимых бага в `extract()`: (1) `agent_name="dialogue_extractor"` НЕ в `DEFAULT_AGENT_CAPABILITY_MAP` → fallback на `Capability.GENERAL`. (2) `params={"max_tokens": 200, "temperature": 0.1, "response_format": {"type": "json_object"}}` — dict, не `GenerationParams`. (3) `response.text` — `request_for_agent` возвращает str, не объект → `AttributeError` ловится `except Exception`, возвращается пустой `DialogueUpdate()`. **Никакие claims, questions, topics не экстрактятся.**
- **Фикс:**
  - Добавить `"dialogue_extractor": Capability.FACT_EXTRACTION` в `DEFAULT_AGENT_CAPABILITY_MAP` в `router.py`.
  - Использовать `GenerationParams(max_tokens=200, temperature=0.1, response_format={"type": "json_object"})`.
  - Заменить `response.text` на `response` (уже строка).

#### BUG-DLG-012 — `NpcDialogueSubscriber._process_canonical` имеет дублирующий `except` block (мёртвый код)
- **Файл:строка:** `backend/app/services/events/npc_dialogue_subscriber.py:178, 201`
- **Severity:** High
- **Симптом:** Try block (начиная со строки 124) имеет два `except Exception as mem_err:` handler'а — второй unreachable. Первый глотает ошибку и schedul'ит L2 deferred write. Реальная ошибка (например, `add_dialogue_turn` KeyError) логируется как generic warning.
- **Фикс:** Удалить дублирующий `except` block (строки 201-202). Реструктурировать: логировать failure, затем EITHER schedul'ить L2 deferred write OR re-raise, не оба.

#### BUG-DLG-013 — `DialogueExecutor._generate_with_router` глотает `DialogueContractViolation`
- **Файл:строка:** `backend/app/services/execution/dialogue_executor.py:213-230`
- **Severity:** High
- **Симптом:** `execute()` объявляет handler для `DialogueContractViolation` (строки 92-101). Но `_generate_with_router` имеет свой broad `except Exception` (строки 228-230), возвращающий `""` на **любую** ошибку, включая `DialogueContractViolation`. → contract violation конвертируется в пустую строку, `execute()` заменяет empty text на `[Заглушка] {task.owner_id} молчит.` и эмитит успешный `dialogue_line` artifact.
- **Фикс:**
  ```python
  except DialogueContractViolation:
      raise  # propagate to execute()
  except Exception as e:
      logger.error(...)
      return ""
  ```

#### BUG-DLG-014 — `thread_id` генерируется, но никогда не используется
- **Файл:строка:** `backend/app/services/phases/post_decision.py:67-69, 122, 159`; declared in `app/domain/communication.py:64, 89` and `app/services/memory/dialogue_session.py:55`
- **Severity:** Medium
- **Симптом:** `thread_id` генерируется, передаётся через `DialogueRequest`, реконструируется в `task_scheduler._reconstruct_task`, хранится в `DialogueRequest` и `DialogueSession`. Но **ни один код его не читает**. `MemoryManager.get_dialogue_session` ключует по `(campaign_id, sorted_pair)`.
- **Фикс:** Either (a) удалить поле и весь код, который его устанавливает, или (b) включить `thread_id` в ключ `get_dialogue_session`:
  ```python
  key = f"{campaign_id}:{pair_key[0]}:{pair_key[1]}:{thread_id}"
  ```
  Default `thread_id=""` сохраняет backward compatibility.

#### BUG-DLG-015 — `_is_light_dialog` ссылается на несуществующий `SANDBOX_MEDIUM` ActionType
- **Файл:строка:** `backend/app/agents/dm_agent.py:162-165`
- **Severity:** Low
- **Фикс:** Заменить `"SANDBOX_MEDIUM"` на `"SANDBOX_SOCIAL"`.

#### BUG-DLG-016 — `ReputationEngine.get_all_faction_states` вызывает `List[Any](...)` (TypeError)
- **Файл:строка:** `backend/app/services/social/reputation_engine.py:344`
- **Severity:** Medium
- **Фикс:** `list(self._factions[fid].npc_members)`.

#### BUG-DLG-017 — `dialogue_materializer` всегда эмитит `listener_ids=[]`
- **Файл:строка:** `backend/app/services/execution/dialogue_materializer.py:48-50`
- **Severity:** Medium
- **Фикс:** Либо вычислять listeners в materializer, либо документировать, что `social_input_projector.handle()` MUST вызываться даже когда `spatial_query is None`.

#### BUG-DLG-018 — `ResponseValidator._breaks_fourth_wall` over-triggers
- **Файл:строка:** `backend/app/services/verbalization/response_validator.py:115-138, 74-75`
- **Severity:** High (часть корневой причины S-1)
- **Симптом:** Запрещает слова `игрок`, `игроки`, `симуляция`, `система`, `механика`, `интерфейс`. Сам промпт DM agent'а содержит эти слова (`dm_agent.py:284` "Игрок обращается напрямую..."). Если 7B LLM эхо'ит любое — fallback `"Ничего не произошло."`.
- **Фикс:** (a) Отдельный, looser word-list для DM narrative (только `симуляция`, `интерфейс`, `механика`); или (b) требовать forbidden word в прямой речи (кавычках), не в narrative.

#### BUG-DLG-019 — Player threat events route to PLAYER_SPOKE (см. §0.Bug 3 в domain_dialogue.md)
- Дублирует BUG-PERC-002 / BUG-DLG-004.

#### BUG-DLG-020 — `ReactionSubscriber` не подписан на `PLAYER_SPOKE` (см. §0.Bug 3)
- **Файл:строка:** `backend/app/services/events/reaction_subscriber.py:52-65`
- **Severity:** Critical
- **Симптом:** `_REACTION_EVENT_TYPES` содержит `PLAYER_THREATENS`, `PLAYER_ATTACKS`, `PLAYER_INSULTS`, etc. — но **не** `PLAYER_SPOKE`. Комбинируется с BUG-DLG-019: threats публикуются как `PLAYER_SPOKE`, `ReactionSubscriber` их не слышит.
- **Фикс:** Это корректное поведение — нужно фиксить BUG-DLG-019, чтобы события шли как `PLAYER_THREATENS`. NOT добавлять `PLAYER_SPOKE` в `_REACTION_EVENT_TYPES`.

#### BUG-DLG-021 — `DirectiveInterpretationSubscriber` не на EventBus; вызывается inline с mock event
- **Файл:строка:** `backend/app/services/social/directive_interpretation_subscriber.py:21-24`; called at `backend/app/services/tick_orchestrator.py:726-741, 899-912`
- **Severity:** Medium (архитектурное)
- **Симптом:** "Subscriber" не подписан на EventBus. Вызывается синхронно в `tick_orchestrator._process_player_dm_action` / `_process_player_action` с hand-crafted `types.SimpleNamespace(payload=...)` mock event. Правило "DirectiveInterpretationSubscriber MUST receive all_npcs_raw injection" — выполнено, но дизайн обходит EventBus.
- **Фикс:** Either переименовать класс (e.g. `DirectiveInterpreter`), либо рефакторить в true subscriber, эмитящий deltas через Phase 8 buffer.

#### BUG-DLG-022 — `task_scheduler.process_tasks` — мёртвый код с неверной сигнатурой
- **Файл:строка:** `backend/app/services/game_loop/task_scheduler.py:71-90`
- **Severity:** Low
- **Фикс:** Удалить.

#### BUG-DLG-023 — `IntentEventAdapter.to_event` mapping для non-attack intents — мёртвый код
- **Файл:строка:** `backend/app/services/events/intent_event_adapter.py:38-46`; consumer at `backend/app/services/phases/post_decision.py:34-217`
- **Severity:** Medium
- **Симптом:** `to_event` маппит `intent_type` → `event_type`: `attack → actor_attacks`, `help → help`, `theft/steal/rob → theft`, `intimidate → intimidation`. Но в `post_decision.py:38-165` **все non-attack intents** уходят в `pending_tasks` (`continue` на строке 165) и никогда не достигают `adapter.to_event(intent)`.
- **Фикс:** Either удалить unused ветки в `to_event`, либо рефакторить post_decision вызывать `to_event` для ВСЕХ intents.

#### BUG-DLG-024 — `NpcDialogueSubscriber._process_canonical` записывает `target_id=listener` (семантически инвертировано)
- **Файл:строка:** `backend/app/services/events/npc_dialogue_subscriber.py:138`
- **Severity:** Low (cosmetic)
- **Фикс:** Переименовать параметр `target_id` → `addressee_id` для ясности.

#### BUG-DLG-025 — `NpcDialogueSubscriber` дропает ambient lines без listener
- **Файл:строка:** `backend/app/services/events/npc_dialogue_subscriber.py:70-71`
- **Severity:** Medium
- **Симптом:** `if not speaker or not listener or listener == "all": return`. Soliloquy (`target_id="soliloquy"`) или ambient без цели — подписчик ничего не делает. STM не пишется, L1 chronicle не обновляется.
- **Фикс:** Разрешить `listener="soliloquy"` или `listener=""`, но skip relationship update.

#### BUG-DLG-026 — `dialogue_executor.execute` не передаёт `thread_id` в memory_manager
- **Файл:строка:** `backend/app/services/execution/dialogue_executor.py:171-187`
- **Severity:** Medium
- **Фикс:** Wire `thread_id` через `MemoryManager.get_stm_prompt_block_pair` в `get_dialogue_session` (требует фикс BUG-DLG-014 сначала).

#### BUG-DLG-027 — `task_scheduler._reconstruct_task` ловит только `ValueError` для TaskKind
- **Файл:строка:** `backend/app/services/game_loop/task_scheduler.py:282-285`
- **Severity:** Low
- **Фикс:** Логировать WARN при fallback.

#### BUG-DLG-028 — `WorldSimulationAgent.tick()` вызывает LLM без контекста
- **Файл:строка:** `backend/app/agents/world_sim_agent.py:135-149`
- **Severity:** Low
- **Фикс:** Either удалить `tick()`, либо pull recent events из MemoryManager перед вызовом `simulate()`.

#### BUG-DLG-029 — `dm_phase.py` молча глотает STM и L2 memory extraction errors
- **Файл:строка:** `backend/app/services/game_loop/dm_phase.py:62, 81`
- **Severity:** Medium
- **Фикс:** Заменить `except Exception:` на `except Exception as e: logger.warning(f"[STM_EXTRACT] failed: {e}"); shared_context.npc_stm_block_targeted = ""`.

#### BUG-DLG-030 — `IntentEventAdapter.to_event` inconsistent threat mapping
- **Файл:строка:** `backend/app/services/events/intent_event_adapter.py:38-46`
- **Severity:** Low (мёртвый код, см. BUG-DLG-023)

#### BUG-DLG-031 — `dm_phase.py` пишет player's input в STM как `intent="dialogue"` всегда
- **Файл:строка:** `backend/app/services/game_loop/dm_phase.py:160-169`
- **Severity:** Low
- **Фикс:** Передавать `intent=shared_context.action_type` (уже классифицировано DMRouter).

#### BUG-DLG-032 — `dialogue_executor.execute` вызывает `confession_parser.parse_and_record` синхронно
- **Файл:строка:** `backend/app/services/execution/dialogue_executor.py:107-116`
- **Severity:** Medium
- **Симптом:** Двойной LLM-вызов на dialogue line.
- **Фикс:** Defer confession parsing в отдельную background task / next-tick processing.

#### BUG-DLG-033 — `task_scheduler._process_tasks_async` пишет `recent_dialogues` с wall-clock `timestamp` и `game_time`
- **Файл:строка:** `backend/app/services/game_loop/task_scheduler.py:236-237`
- **Severity:** Low
- **Фикс:** Удалить поле `timestamp`.

#### BUG-DLG-034 — `dialogue_queue` не делает priority inversion для stale low-priority tasks
- **Файл:строка:** `backend/app/services/execution/dialogue_queue.py:84-105`
- **Severity:** Medium
- **Фикс:** Either skip to next-available speaker, либо age priority по `(now - enqueued_at) / 60`.

#### BUG-DLG-035 — `social_engine.propagate` skip'ает witnesses из results, но `propagation.py` re-checks
- **Файл:строка:** `backend/app/services/social/propagation.py:101-103`
- **Severity:** Medium
- **Фикс:** Использовать `ctx.shared_context.perceiving_npcs` (post Phase 8 filter) как witness set.

#### BUG-DLG-036 — `fate_tracker.update_state` кидает на out-of-range values
- **Файл:строка:** `backend/app/services/social/fate_tracker.py:22-25`
- **Severity:** Low
- **Фикс:** `try: stability = float(...) except (TypeError, ValueError): stability = 0.0`.

#### BUG-DLG-037 — `mvp_tavern_controller.on_tick_completed` использует `npc.get("id", npc.get("npc_id"))` — неправильный key priority
- **Файл:строка:** `backend/app/services/social/mvp_tavern_controller.py:125`
- **Severity:** Low
- **Фикс:** `npc_id = npc.get("npc_id") or npc.get("id")`.

#### BUG-DLG-038 — `_recent_dialogues` list растёт безгранично между тиками
- **Файл:строка:** `backend/app/services/game_loop/task_scheduler.py:48, 239-243`
- **Severity:** Low
- **Фикс:** `self._recent_dialogues = self._recent_dialogues[-100:]` после append.

#### BUG-DLG-039 — `dialogue_materializer` возвращает `Iterable[Any]`, но потребляется как list
- **Файл:строка:** `backend/app/services/execution/dialogue_materializer.py:18, 39-56`
- **Severity:** Low
- **Фикс:** `List[Any]` + `return [event]`.

#### BUG-DLG-040 — `task_scheduler` не тречит failed tasks для retry
- **Файл:строка:** `backend/app/services/game_loop/task_scheduler.py:244-248`
- **Severity:** Low
- **Фикс:** Простой retry: если `retry_count < 2`, re-enqueue с пониженным priority. Иначе push в dead-letter list.

---

### 3.3. DOM-03: PERCEPTION / PHENOMENOLOGY / PHYSIOLOGY / COMBAT / AFFECTIVE (29 дефектов)

Подробный отчёт: `domain_perception.md`. Ниже — выжимка.

#### BUG-PERC-001 — `PlayerPerceptionDTO` всегда EMPTY (DTO type mismatch + bypassed conversion)
- **Файл:строка:** `backend/app/services/game_loop/__init__.py:954-963` and `backend/app/services/perception/phenomenology_projection_service.py:118-127`
- **Severity:** Critical (корневая причина S-2)
- **Симптом:** Фронтенд получает
  ```
  PlayerPerceptionDTO(active_perceptions=[], atmosphere_key=None,
                      atmosphere_intensity=0.0, embodied_traces=[],
                      manifestations={}, observed_facts=[])
  ```
  Это **`embodied_trace.PlayerPerceptionDTO`** shape, НЕ **`snapshot.PlayerPerceptionDTO`** (с `peripheral_cues: List[PeripheralCueDTO]` и `manifestations: List[ManifestationDTO]`).
- **Причина:** Два **разных** `PlayerPerceptionDTO`-класса: `app/domain/embodied_trace.py` (domain) и `app/domain/snapshot.py` (API). `integration.py:567` строит domain DTO и кормит `WorldSnapshotBuilder.build(player_perception=...)` → `_convert_perception` корректно конвертирует domain→API. **Затем** `game_loop/__init__.py:956` вызывает `_project_perception` (вторую проекцию) и **перезаписывает** snapshot через `dataclasses.replace(world_snapshot, player_perception=_perception)`, где `_perception` — **сырой domain DTO**, минуя converter.
- **Фикс:**
  - Удалить второй `_project_perception` call целиком (integration.py уже построил), ИЛИ
  - Прогнать вторую проекцию через `WorldSnapshotBuilder._convert_perception` перед `dataclasses.replace`.

#### BUG-PERC-002 — Player threats никогда не доходят до combat/fear pipeline
- **Файл:строка:** `backend/app/services/game_loop/phase_1_input.py:276-297`
- **Severity:** Critical (корневая причина S-4)
- **Симптом:** DMRouter классифицирует "угрожать" → `event_type="player_threatens"`. Override ставит `_raw_type = "player_threatens"`. Но публикуется `PLAYER_SPOKE`, не `PLAYER_THREATENS`. `ReactionSubscriber`, `SocialSubscriber`, `CombatSubscriber` подписаны на `PLAYER_THREATENS`, но он **не эмитится**.
- **Причина:** `_evt_map` (строки 276-283) содержит только `dialogue`, `player_interacts`, `attack`, `player_attacks`, `move`, `stealth`. Недостающие: `player_threatens`, `player_insults`, `player_steals`, `player_flees`, `intimidation`, `theft`, `betrayal`, `help`, `saved_life`. Все fallback'ят в `PLAYER_SPOKE`.
- **Фикс:** Расширить `_evt_map` (см. BUG-DLG-004).

#### BUG-PERC-003 — Combat использует `random.Random`, не KernelRNG
- **Файл:строка:** `backend/app/services/combat/impact_engine.py:24,46,95,131`
- **Severity:** High (нарушение L2)
- **Симптом:** `import random`; `rng = random.Random(rng_seed)`. Seed = `hash((event_id, actor_id, target_id)) & 0xFFFFFFFF`. Python's `hash()` для строк рандомизирован per-process (PYTHONHASHSEED) → seed **недетерминирован между запусками**.
- **Фикс:** Заменить на `KernelRNG(tick=current_tick, npc_id=actor_id, salt=f"combat:{target_id}")`.

#### BUG-PERC-004 — `combat_math.py` fallback к global `random`
- **Файл:строка:** `backend/app/services/game/combat_math.py:12,50,52,61,71,193,210,276,278,379,404,429`
- **Severity:** High
- **Симптом:** Каждая dice-функция имеет `rng: Optional[random.Random] = None` с телом `_rng = rng or random`.
- **Фикс:** Make `rng` required, либо default на `KernelRNG(tick=0, npc_id="combat", salt="default")`.

#### BUG-PERC-005 — `combat_math.apply_damage` пишет `state.hp` И убивает через `hp<=0`
- **Файл:строка:** `backend/app/services/game/combat_math.py:300-322`
- **Severity:** Critical (3 нарушения в 5 строках)
- **Симптом:**
  ```python
  target["hp"] = max(0, before - damage)        # пишет state.hp
  if target["hp"] <= 0:                          # HP-as-death-source
      target["status"] = "dead" if tier in ("minor","mass") else "incapacitated"
  ```
- **Фикс:** Удалить `apply_damage` (мёртвый код, см. комментарий в `state_applicator.py:926-927`).

#### BUG-PERC-006 — `combat_math.apply_healing` позволяет DEAD → ALIVE
- **Файл:строка:** `backend/app/services/game/combat_math.py:325-340`
- **Severity:** Critical
- **Симптом:**
  ```python
  target["hp"] = min(max_hp, before + amount)
  if target["hp"] > 0:
      target["status"] = "alive"      # воскрешает!
  ```
- **Фикс:** Добавить guard:
  ```python
  if target.get("status") == "dead" or target.get("life_status") == "DEAD":
      return {"hp_before": before, "hp_after": before, "blocked": "dead"}
  ```
  Или удалить функцию (legacy).

#### BUG-PERC-007 — `combat_service.py` — legacy D&D service, обходит SSOT
- **Файл:строка:** `backend/app/services/combat_service.py:1-117`
- **Severity:** High
- **Симптом:** Параллельная боевая система: хранит state как `{"name":..., "hp":..., "initiative":...}` flat dict. `resolve_attack` мутирует `p["hp"]` напрямую. Нет KernelRNG, нет `PhysiologyPayload`, нет `shock_impulse`, нет `evaluate_vital_state`.
- **Фикс:** Определить, wired ли ещё сервис. Если нет — удалить. Если да — роутить через `ImpactEngine.resolve_physical_impact` + `StateApplicator.apply_batch`.

#### BUG-PERC-008 — `BehaviorManifestationService` фильтрует здоровых NPC → пустые traces
- **Файл:строка:** `backend/app/services/perception/behavior_manifestation_service.py:140-145`
- **Severity:** Critical (часть корневой причины S-2)
- **Симптом:**
  ```python
  if (
      trace.locomotion_instability > 0.05
      or trace.posture_rigidity > 0.05
      or trace.micro_pause_density > 0.05
  ):
      traces.append(trace)
  ```
  Спокойный здоровый tavern keeper → all-zero trace → отфильтрован → `embodied_traces=[]` → DM нечего описывать.
- **Фикс:**
  ```python
  traces.append(trace)  # always append; consumer decides what to render
  ```
  Затем `PhenomenologyProjectionService` эмитит `MANIFEST_CALM` tag для здоровых NPC.

#### BUG-PERC-009 — `integration.py` кормит wrong source в `ManifestationPhysicsEngine`
- **Файл:строка:** `backend/app/services/phases/integration.py:474-488`
- **Симптом:** `_npc_positions = ctx.scene_state.get("npc_positions", {})`. `_ndata` — это `NPCPositionDTO` dict (содержит `local_position`, `activity`, `facing`, `velocity`, `display_name`). Он НЕ содержит `psyche`, `social_stats`, `drives_base`, `personality`, `perceptual_kernel`. `ManifestationPhysicsEngine.manifest` читает всё это из `npc_state` → defaults to 0/empty.
- **Фикс:** Использовать `all_npcs_raw` (full NPC state) вместо `npc_positions` для manifest-вызова.

#### BUG-PERC-010 — `BehaviorManifestationService` читает psyche несмотря на "ЗАПРЕТ" в docstring
- **Файл:строка:** `backend/app/services/perception/behavior_manifestation_service.py:48,128,137,167-168,194-199,260-275`
- **Симптом:** Module docstring: *"ЗАПРЕТ: Не читает psyche (fear, anger). Только моторные замки и физиологию."* Но `_manifest_npc` принимает `psyche`, экстрактит `stress` и `affective_load`, использует их для motor patterns:
  ```python
  if stress > 20.0:
      _emo_rigidity = max(_emo_rigidity, min(0.6, stress / 100.0))
  ```
- **Фикс:** Either удалить psyche reads (true to docstring) и полагаться только на `body_state` + `perceptual_kernel.threat_gradient`, либо обновить docstring.

#### BUG-PERC-011 — Dual perception pipeline (inconsistent + wasteful)
- **Файлы:**
  - `backend/app/services/phases/integration.py:462-569` (Pipeline A)
  - `backend/app/services/game_loop/__init__.py:627-638, 954-963` (Pipeline B)
- **Симптом:** Два независимых trace-генератора производят два разных `EmbodiedTraceDTO`-списка, оба кормят `PhenomenologyProjectionService.project()`. Pipeline B перезаписывает Pipeline A. Pipeline A читает `npc_positions` (wrong source — см. BUG-PERC-009), Pipeline B читает `all_npcs_raw` (correct source). Они дают **разные** traces для одних и тех же NPC.
- **Фикс:** Схлопнуть в один pipeline. Рекомендация: оставить Pipeline B (`BehaviorManifestationService` правильно читает `all_npcs_raw`), удалить trace-building loop в `integration.py:472-518`. `PerceptionPhysicsEngine` / `FactExtractor` / `InferenceEngine` из Pipeline A инвокить только если `observed_facts` нужны для DM.

#### BUG-PERC-012 — `PresentationAssembler` читает несуществующее поле `fact.perceived_value`
- **Файл:строка:** `backend/app/services/perception/presentation_assembler.py:31-33`
- **Severity:** Low
- **Фикс:** Заменить на `value=fact.value`.

#### BUG-PERC-013 — `L1Chronicle` удаляет events из active table (нарушает "append-only, no deletions")
- **Файл:строка:** `backend/app/services/npc/l1_chronicle.py:240-268`
- **Severity:** Medium
- **Симптом:** `archive_old_events()`: `DELETE FROM l1_chronicle_events WHERE campaign_id = ? AND tick_id < ?`. Active table мутируется.
- **Фикс:** Either переименовать контракт в "append-only + archival migration", либо использовать одну таблицу с `archived_at_tick` column и никогда не DELETE.

#### BUG-PERC-014 — L2.5 belief crystallization запускается каждый тик (без `phase_2_events` gate)
- **Файл:строка:** `backend/app/services/phases/integration.py:380-422`
- **Severity:** Medium
- **Фикс:** Gate на `if not ctx.phase_2_events: continue`.

#### BUG-PERC-015 — `physics_validator.py` использует `self` в class-level lambda → `NameError`
- **Файл:строка:** `backend/app/services/game/physics_validator.py:82`
- **Severity:** High
- **Симптом:**
  ```python
  lambda char, _: self._check_lifting_capacity(char, 500),   # NameError!
  ```
  Когда правило "поднимаю X кг" срабатывает, Python кидает `NameError: name 'self' is not defined`.
- **Фикс:**
  ```python
  lambda char, _: PhysicsValidator._check_lifting_capacity(char, 500),
  ```

#### BUG-PERC-016 — `InferenceEngine._map_fact_to_cause_key` имеет stub mapping
- **Файл:строка:** `backend/app/services/perception/inference_engine.py:94-95`
- **Severity:** Low
- **Фикс:** Удалить stub, либо добавить правильный `movement.speed` key в `signal_causes.yaml`.

#### BUG-PERC-017 — `PerceptualAttentionService` — dead code (orphan, never wired)
- **Файл:строка:** `backend/app/services/perception/perceptual_attention_service.py` (entire file)
- **Severity:** Medium
- **Симптом:** Определяет `build_perception(events, avatar_state, current_tick) -> PlayerPerceptionDTO` (snapshot variant). Возвращает `PlayerPerceptionDTO` с `avatar_desync: AvatarDesyncDTO` (единственное место, вычисляющее camera_inertia / motion_trail / auditory_muffle). Не импортирован никем. → `avatar_desync` всегда `None` (BUG-PERC-024).
- **Фикс:** Either удалить `PerceptualAttentionService` (и убрать `avatar_desync` из snapshot.PlayerPerceptionDTO), либо wire'нуть: `PerceptionProjector.project()` вызывает `PerceptualAttentionService.build_perception(events, avatar_state, tick)` после `_project_svc.project()`.

#### BUG-PERC-018 — `combat_subscriber` использует `print()` для diagnostics
- **Файл:строка:** `backend/app/services/combat/combat_subscriber.py:73-75`
- **Severity:** Low
- **Фикс:** Заменить на `logger.debug(...)`.

#### BUG-PERC-019 — `game_loop` использует `print()` для PerceptionProjector diagnostics
- **Файл:строка:** `backend/app/services/game_loop/__init__.py:635-637`
- **Severity:** Low
- **Фикс:** Заменить на `logger.debug(...)`.

#### BUG-PERC-020 — `state_applicator.apply_physical` пишет HP дважды с разными типами
- **Файл:строка:** `backend/app/services/npc/state_applicator.py:283-292`
- **Severity:** Low
- **Фикс:** Удалить redundant `int()` cast.

#### BUG-PERC-021 — `state_applicator` логирует DEATH_CERTIFIED дважды (дублирующий блок)
- **Файл:строка:** `backend/app/services/npc/state_applicator.py:932-939`
- **Severity:** Low
- **Фикс:** Удалить дублирующий блок (строки 936-939).

#### BUG-PERC-022 — `BehaviorManifestationService._manifest_npc` ссылается на `_threat` вне scope
- **Файл:строка:** `backend/app/services/perception/behavior_manifestation_service.py:184-189, 267, 288`
- **Severity:** Low
- **Фикс:** Инициализировать `_threat = 0.0` в начале `_manifest_npc`.

#### BUG-PERC-023 — `affective_integrator` читает psyche dict используя drive names как keys
- **Файл:строка:** `backend/app/services/affective/affective_integrator.py:34-39`
- **Severity:** Low
- **Фикс:** Переименовать параметр `psyche` → `drive_weights` или передавать typed `DriveWeights` dataclass.

#### BUG-PERC-024 — `avatar_desync` всегда `None` на API `PlayerPerceptionDTO`
- **Файл:строка:** `backend/app/domain/snapshot.py:186,200-205` and `backend/app/services/integration/world_snapshot_builder.py:200-206`
- **Severity:** Medium
- **Фикс:** Wire `PerceptualAttentionService.build_perception` (или fold в `assemble_avatar_presentation`), устанавливать `avatar_desync` в `_convert_perception`.

#### BUG-PERC-025 — Somatic Gate отсутствует до семантического парсинга
- **Файл:строка:** `backend/app/services/npc/decision_hub.py:402-418`
- **Severity:** Medium (архитектурное нарушение L8)
- **Симптом:** Правило: *"Body before Semantic"*. `DecisionHub.compute()` проверяет vital_state на строке 408 — но это на стадии Action, после semantic parsing. Somatic gate (body vetoing input parsing) не реализован.
- **Фикс:** Добавить ранний somatic gate в `phase_1_input.publish_classified_player_event` или в NPC perception pipeline: если observer's `body_state.shock_impulse > 0.7` или `is_conscious(body_state) == False`, NPC не должен парсить semantic content события (только регистрировать raw disturbance).

#### BUG-PERC-026 — `state_applicator` не пропагирует `life_status` на root-level state
- **Файл:строка:** `backend/app/services/npc/state_applicator.py:930-931`
- **Severity:** Low
- **Фикс:** Verify `NPCState.write_to_legacy` (state_applicator.py:1328) синкает `body_state["life_status"]` на root-level `life_status` field, используемый persistence.

#### BUG-PERC-027 — TODO markers indicate incomplete vital-state processes
- **Файлы:**
  - `backend/app/domain/vital_state.py:122,141` (TODO: death_cause classification, DeathState)
  - `backend/app/services/npc/state_applicator.py:927-929`
  - `backend/app/services/combat/injury_processor.py:221-225` (TODO: BleedingProcess, HypoxiaProcess, PoisonProcess)
  - `backend/app/services/combat/physiology_decay_handler.py:246-248` (ARCHITECTURAL DEBT: decay as bandage)
- **Severity:** Low (intentional backlog)
- **Фикс:** Track в roadmap.

#### BUG-PERC-028 — `CombatSubscriber` инжектит `missed_targets` через `setattr` на `Phase8Result`
- **Файл:строка:** `backend/app/services/combat/combat_subscriber.py:237`
- **Severity:** Low
- **Фикс:** Добавить `missed_targets: List[Dict[str, Any]] = field(default_factory=list)` в `Phase8Result` dataclass.

#### BUG-PERC-029 (он же O6) — `AffectiveDecayHandler` не проверяет DEAD status
- **Файл:строка:** `backend/app/services/affective/affective_decay_handler.py:52-93`
- **Severity:** Medium (нарушение L12: Decay для мёртвых запрещён)
- **Симптом:** Handler итерирует всех NPC и decays `affective_load` для каждого. НЕТ `if npc.get("life_status") == "DEAD": continue`. Мёртвый NPC продолжает decay до 0.0, потом `emotion_tag` = "neutral".
- **Фикс:** Добавить `if npc.get("life_status", "ALIVE") == "DEAD": continue` после строки 55.

---

### 3.4. DOM-04: SPATIAL / MOVEMENT / TRAVERSAL (30 дефектов)

Подробный отчёт: `domain_spatial.md`. Ниже — выжимка топовых багов.

#### BUG-SPATIAL-001 — Cross-loc materialize теряет оригинальную bed target
- **Файл:строка:** `backend/app/services/spatial/movement_engine.py:323` (rewrite) и `:269-289` (materialize lookup)
- **Severity:** Critical (корневая причина S-3)
- **Симптом:** NPC оказываются на `loc=city_gate, node=exit_west` (или `exit_east` в target loc), хотя расписание говорит `tent_*/guard_bed*`. Оригинальный bed intent молча заменяется boundary node.
- **Причина:** Cross-loc intercept **мутирует** `intent.target_node_id` in place:
  ```python
  intent.target_node_id = boundary_node.node_id.split(":")[-1]   # было "guard_bed", стало "exit_west"
  intent.location_id = current_loc
  target_loc = current_loc
  ```
  Затем, когда NPC достигает boundary, materialize block ищет bed в **новой** локации, используя уже переписанный `intent.target_node_id`:
  ```python
  _target_node_id_short = intent.target_node_id.split(":")[-1]   # "exit_west", НЕ "guard_bed"!
  ```
  Lookup либо возвращает противоположный boundary в target loc, либо fallback'ит на `entry_node_hint` (тоже boundary). Реальный bed (`guard_bed`) никогда не запрашивается.
- **Фикс:**
  1. НЕ мутировать `intent.target_node_id`. Хранить отдельное поле `intent._boundary_node_id` (или local var `pending_target_node_id`).
  2. В materialize lookup'ить **оригинальный** target:
     ```python
     original_target = intent.target_node_id  # никогда не переписывается
     target_node_obj = target_svc.get_node(original_target) or \
                       target_svc.get_node(f"{target_loc}:{original_target}")
     ```
  3. Если оригинальный target реально не существует в target loc, поднять `SimulationIntegrityError` — НЕ fallback'ить на `entry_node_hint`.

#### BUG-SPATIAL-002 — `find_path` ищет `start_node` в зоне TARGET'а
- **Файл:строка:** `backend/app/services/spatial/spatial_service.py:526`
- **Severity:** High (latent)
- **Симптом:** Если `find_path` вызвать с `target_node`, чья `zone_id` отличается от фактической зоны NPC, возвращённый путь начинается с ближайшего узла в зоне target'а — обычно boundary node. Реальный start-node NPC дропается.
- **Причина:**
  ```python
  start_node = self.get_nearest(target_node.zone_id, start_xy, urgency)
  ```
  Comment: "in the same zone", но код использует `target_node.zone_id`, предполагая, что NPC уже в зоне target'а.
- **Фикс:**
  ```python
  def find_path(self, start_xy, target_node, urgency=Urgency.NORMAL, start_zone: Optional[str] = None):
      zone = start_zone or target_node.zone_id
      start_node = self.get_nearest(zone, start_xy, urgency)
  ```

#### BUG-SPATIAL-003 — `print()` debug statements в `find_path`
- **Файл:строка:** `backend/app/services/spatial/spatial_service.py:528, 531, 534, 600`
- **Severity:** Low
- **Фикс:** Заменить на `logger.debug(...)`.

#### BUG-SPATIAL-004 — `player_spatial` всё ещё читается как авторитетный источник
- **Файл:строка:** `backend/app/services/scene_state_manager.py:1019-1030` (init), `:1681-1696` (`_enrich_local_positions`)
- **Severity:** High (нарушение L9)
- **Симптом:** Правило: "player_spatial is DEAD; truth is in `npc_positions['player']`". Но `_enrich_local_positions` делает обратное:
  ```python
  if npc_id == "player":
      _ps = scene_state.get("player_spatial", {})
      _plp = _ps.get("local_position", {})
      ...
      entry["local_position"] = _plp
      ...
      continue
  ```
- **Причина:** "player_spatial is DEAD" применено наполовину: writes отключены, но reads активны. Результат: **double truth**.
- **Фикс:**
  1. Перестать читать `player_spatial` в `_enrich_local_positions`. Игрок должен течь через тот же `editor_coords` / `svc.get_node(current_node)` path, что и NPC.
  2. Удалить `"player_spatial": {...}` block из scene initialization (строка 1019).
  3. Удалить параметр `player_spatial` из `update_player_target` (строка 539).

#### BUG-SPATIAL-005 — `transition_traversal()` FSM — dead code (0 call sites)
- **Файл:строка:** `backend/app/domain/traversal_schema.py:55-78` (FSM), `backend/app/services/scene_state_manager.py:1210-1234` (пишет status напрямую)
- **Severity:** High (нарушение L10)
- **Симптом:** Правило: "Status mutation bypassing `transition_traversal()` FSM" запрещено. Но:
  - `build_traversal_dict` (`traversal_schema.py:171-190`) хардкодит `"status": "MOVING"`.
  - `SSM.apply_change` вызывает `build_traversal_dict` и хранит результат напрямую в `scene_state["active_traversals"][npc_id]` (строка 1232) — **без `transition_traversal`**.
  - `TraversalExecutionSystem.advance` (строка 86) пишет `trav["status"] = "COMPLETED"` напрямую.
  - grep `transition_traversal` по `backend/` → **0 call sites**.
- **Фикс:**
  1. В `build_traversal_dict` начинать с `"PENDING"`, затем вызывать `transition_traversal(d, "MOVING")`.
  2. В `TraversalExecutionSystem.advance` заменить `trav["status"] = "COMPLETED"` на `transition_traversal(trav, "COMPLETED")`.
  3. В `SSM.apply_change` при `cause="traversal_complete"` вызывать `transition_traversal(active_travs[npc_id], "COMPLETED")`.

#### BUG-SPATIAL-006 — `(0.0, 0.0)` sentinel leaks
- **Файлы:** `scene_state_manager.py:977, 1186-1190`, `event_compiler.py:311-312, 749-750`, `spatial_observatory_service.py:228, 233, 238, 239`
- **Severity:** High
- **Симптом:** Правило: "local_position (0.0, 0.0) is FORBIDDEN unless explicitly valid". Несколько мест нарушают:
  - `SSM` template NPC fallback: `pos_entry.setdefault("local_position", {"x": 0.0, "y": 0.0})`
  - `event_compiler` `_resolve_source_xy` fallback: комментарий запрещает, код делает
  - `spatial_observatory_service` `_extract_pos`: возвращает `(0.0, 0.0)` при malformed input
- **Фикс:** Каждое место — поднять `SimulationIntegrityError` или вернуть `None` и обработать на caller'е.

#### BUG-SPATIAL-007 — `euclidean_distance` только (0,0)+(0,0) считает missing
- **Файл:строка:** `backend/app/services/spatial/spatial_runtime.py:71-83`
- **Severity:** High
- **Фикс:**
  ```python
  if (ax == 0.0 and ay == 0.0) or (bx == 0.0 and by == 0.0):
      return 999.0
  ```

#### BUG-SPATIAL-008 — `cluster_relation` всегда возвращает `"adjacent"`
- **Файл:строка:** `backend/app/services/spatial/spatial_query_service.py:81-98`
- **Severity:** Medium
- **Фикс:** Добавить `cluster_to_neighbors: dict[str, set[str]]` field в `ClusterOccupancy` и проверять `cl_b in cluster_to_neighbors.get(cl_a, set())`.

#### BUG-SPATIAL-009 — `SpatialRegistry.find_artifact` имеет missing `return None`
- **Файл:строка:** `backend/app/services/spatial/spatial_registry.py:122-140`
- **Severity:** Low
- **Фикс:** Add explicit `return None` + second candidate path.

#### BUG-SPATIAL-010 — `SpatialService.__init__` присваивает `self._spatial_obstacles` дважды
- **Файл:строка:** `backend/app/services/spatial/spatial_service.py:132` and `:134`
- **Severity:** Low
- **Фикс:** Удалить строку 134.

#### BUG-SPATIAL-011 — `motion_pipeline.py` использует `Optional[Dict[str, dict]]` без импорта
- **Файл:строка:** `backend/app/services/motion/motion_pipeline.py:11, 38, 88, 122`
- **Severity:** Low (latent — `from __future__ import annotations` спасает)
- **Фикс:** `from typing import TYPE_CHECKING, Any, Dict, Optional, Tuple`.

#### BUG-SPATIAL-012 — `is_reachable` лжёт про disconnected nodes
- **Файл:строка:** `backend/app/services/spatial/spatial_service.py:728-732`
- **Severity:** Medium
- **Фикс:** Rename в `is_present_in_graph` + добавить реальный `is_reachable_from(start_node, target_node)` через A*.

#### BUG-SPATIAL-013 — `euclidean_distance` возвращает `999.0` вместо sentinel
- **Файл:строка:** `backend/app/services/spatial/spatial_runtime.py:82`
- **Severity:** Low
- **Фикс:** `Optional[float]` + `None`.

#### BUG-SPATIAL-014 — `update_npc_position` — мёртвый код, обходящий TraversalState контракт
- **Файл:строка:** `backend/app/services/scene_state_manager.py:1853-1883`
- **Severity:** Low (сегодня), High (latent)
- **Фикс:** Удалить.

#### BUG-SPATIAL-015 — `resolve_affordance` возвращает nearest nav node в WRONG zone
- **Файл:строка:** `backend/app/services/spatial/spatial_service.py:327-377`
- **Severity:** High (часть корневой причины S-3)
- **Симптом:** Если ближайший bed object в `tent_1`, но `origin_zone="tavern"`, `get_nearest("tavern", (bed_x, bed_y))` возвращает ближайший tavern node к bed'у — обычно `tavern:exit_east`. NPC маршрутизируется на boundary node вместо bed'а.
- **Фикс:** Убрать zone filter в финальном `get_nearest` call, либо принимать `target_zone` параметром.

#### BUG-SPATIAL-016 — `find_path` не проверяет существование `target_node` явно
- **Файл:строка:** `backend/app/services/spatial/spatial_service.py:510-535`
- **Severity:** Medium
- **Фикс:**
  ```python
  if target_node is None or target_node.node_id not in self._graph:
      logger.warning(f"[FIND_PATH] target {target_id} not in graph (loc={self._location_id})")
      return []
  ```

#### BUG-SPATIAL-017 — `try_reserve_node` позволяет double-occupancy под URGENT
- **Файл:строка:** `backend/app/services/spatial/spatial_overlay.py:72-104`
- **Severity:** Medium
- **Фикс:** Either эвиктить предыдущего holder, либо вернуть `False`.

#### BUG-SPATIAL-018 — `apply_changes` zombie-cleanup конфликтует с `build_traversal_dict`
- **Файл:строка:** `backend/app/services/scene_state_manager.py:1347-1362`
- **Severity:** Medium (one-tick-stale)
- **Фикс:** Run zombie-cleanup ПОСЛЕ `TraversalExecutionSystem.advance`.

#### BUG-SPATIAL-019 — `event_compiler` ghost interpolation линейная start→end, не multi-waypoint
- **Файл:строка:** `backend/app/services/event_compiler.py:712-728`
- **Severity:** Medium
- **Фикс:** Заменить на вызов `TraversalExecutionSystem._interpolate_path(wp, prog, segment_modes, segment_arc_heights)`.

#### BUG-SPATIAL-020 — `MovementEngine._spatial_intent_gate` — мёртвый код
- **Файл:строка:** `backend/app/services/spatial/movement_engine.py:71-118`
- **Severity:** Low
- **Фикс:** Удалить.

#### BUG-SPATIAL-021 — `movement_engine.py` объявляет `logger` дважды
- **Файл:строка:** `backend/app/services/spatial/movement_engine.py:9` and `:37`
- **Severity:** Low
- **Фикс:** Удалить второе определение.

#### BUG-SPATIAL-022 — `spatial_target_resolver.py` глотает `ValueError` с `pass`
- **Файл:строка:** `backend/app/services/spatial/spatial_target_resolver.py:77-78`
- **Severity:** Low
- **Фикс:** Test enum membership явно.

#### BUG-SPATIAL-023 — `tick_orchestrator.py` молча глотает `SpatialRegistry` load errors
- **Файл:строка:** `backend/app/services/tick_orchestrator.py:527-533` и `:1260-1265`
- **Severity:** Medium
- **Фикс:** `logger.warning(f"[SPATIAL_REGISTRY] load failed: {e}")`.

#### BUG-SPATIAL-024 — `movement_engine` cross-loc intercept молча дропает intent
- **Файл:строка:** `backend/app/services/spatial/movement_engine.py:326-338`
- **Severity:** Medium
- **Фикс:** Поднять `SimulationIntegrityError` с `invariant_id="INV-CROSS-LOC-NO-BOUNDARY"`.

#### BUG-SPATIAL-025 — `_enrich_local_positions` использует `get_nearest(zone=location_id)` для player
- **Файл:строка:** `backend/app/services/scene_state_manager.py:1685-1696`
- **Severity:** Medium
- **Фикс:** Использовать `get_nearest_safe_node` (без zone filter).

#### BUG-SPATIAL-026 — `TraversalExecutionSystem.advance` не вызывает `transition_traversal`
- **Файл:строка:** `backend/app/services/spatial/traversal_execution_system.py:86-87`
- **Severity:** High
- **Фикс:** `from app.domain.traversal_schema import transition_traversal; transition_traversal(trav, "COMPLETED")`.

#### BUG-SPATIAL-027 — `phases/traversal.py` materialize эмитит `local_position` snap без `traversal_proposal`
- **Файл:строка:** `backend/app/services/phases/traversal.py:104-117`
- **Severity:** Medium (brittle string match)
- **Фикс:** Использовать explicit flag на `SceneChange` (e.g. `is_traversal_complete: bool = False`).

#### BUG-SPATIAL-028 — `_resolve_macro_relocation` возвращает `[]` на missing target_node_obj
- **Файл:строка:** `backend/app/services/spatial/movement_engine.py:670-673`
- **Severity:** Medium (diagnostic loss)
- **Фикс:**
  ```python
  if not target_node_obj:
      _trace.failure = MovementFailure.TARGET_NODE_NOT_FOUND
      _trace.path_status = PathStatus.NO_PATH
      logger.warning(f"[MOVEMENT_TRACE] npc={intent.actor_id} failure=M003 target={intent.target_node_id}")
      return []
  ```

#### BUG-SPATIAL-029 — `SpatialOverlay.build_overlay_from_scene` использует `position` field (canonical OR short)
- **Файл:строка:** `backend/app/services/spatial/spatial_overlay.py:43-57`
- **Severity:** Medium
- **Фикс:** Нормализовать все позиции в canonical form при build overlay.

#### BUG-SPATIAL-030 — `find_path` cache key опускает `start_xy`
- **Файл:строка:** `backend/app/services/spatial/spatial_service.py:537-546`
- **Severity:** Low
- **Фикс:** Документировать, что `find_path` возвращает graph-node paths, не xy-accurate. Или включить `start_xy` (rounded to 0.5m) в cache key.

> **Дополнительно (TODOs в spatial domain):** `motion/motion_pipeline.py:247` — TODO для affordance collision check. `MotionIntegrator.integrate` делает `position += velocity * dt` **без collision check**. ETKE-IK continuous motion может проводить NPC сквозь стены.

---

### 3.5. DOM-07: FRONTEND / BACKEND / PERSISTENCE / WORLD CONTINUITY (50 дефектов)

Подробный отчёт: `domain_frontend.md`. Ниже — выжимка топовых багов.

#### BUG-FB-001 — `stream_turn` SSE дропает `world_snapshot` в done event
- **Файл:строка:** `backend/app/services/game_loop/__init__.py:1424-1435`
- **Severity:** Critical (часть корневой причины S-2 в Direct mode)
- **Симптом:** В Direct mode (`DirectGameGateway` / `game_loop_bridge.py`) bridge читает `event.get("world_snapshot")` из SSE `done` event. Для нормальных ходов это всегда `None` → bridge fallback'ит на empty dict → `npc_positions` пуст, `player_perception` missing.
- **Причина:** `done` payload в `stream_turn` несёт только `tokens`, `ms`, `tps`, `game_time_seconds`, `will_conflict_data`. Только death early-exit branch (строки 1347-1356) и `run_turn` (REST path, строки 1200-1245) build'ят и передают `world_snapshot`. `stream_turn` пропускает этот блок целиком.
- **Фикс:** Зеркалировать post-pipeline block из `run_turn` (строки 1200-1271) внутри `stream_turn` между `dm_text_parts` flush и `yield {"type": "done", ...}`. Добавить `world_snapshot` и `npc_positions` в done payload.

#### BUG-FB-002 — `skip_time` никогда не персистит мутированное state (NPC teleport-back after sleep)
- **Файл:строка:** `backend/app/services/game_loop/__init__.py:743-822`
- **Severity:** Critical (корневая причина S-3 sleep bug)
- **Симптом:** После "sleep" фронтенд показывает NPC на новых позициях (возвращённый `world_snapshot`), но следующий `idle_tick`/`game_action` грузит OLD persisted scene_state → NPC телепортируются обратно.
- **Причина:** `skip_time` вызывает `self.scene_manager.lock_for_tick(campaign_id, "")` и мутирует `_scene` in-place через `_time_skip.skip(...)`, но **никогда не вызывает `commit_tick_result` или `unlock_tick`**. Threading lock `lock.release()` в `finally:` — это `_skip_lock`, не scene_manager lock.
  1. `scene_manager._tick_locked` остаётся `True` forever после sleep.
  2. `scene_manager._tick_scenes[""]` держит мутированную sleep scene, но persistence всё ещё имеет pre-sleep state.
  3. Следующий `idle_tick` вызывает `lock_all_for_tick`, видит `_tick_locked=True` и **ничего не делает**; `get_scene_state(campaign_id, "tavern")` fallback'ит на `load_scene_at`, который возвращает OLD persistence row.
- **Фикс:** В `skip_time` finally block добавить:
  ```python
  self.scene_manager.commit_tick_result(campaign_id, result.final_state)
  self.scene_manager.unlock_tick(campaign_id)
  ```
  Также вызывать `lock_all_for_tick` по `_location_ids` из `SpatialRegistry.get_all_location_ids()` вместо `lock_for_tick(campaign_id, "")` — sleep должен обрабатывать все локации.

#### BUG-FB-003 — Двойной `/api/api/` prefix на `/api/debug/llm/restart`
- **Файл:строка:** `backend/app/api/routes.py:160` + `backend/app/main.py:487`
- **Severity:** High
- **Фикс:** `@router.post("/debug/llm/restart")` (router уже смонтирован с `prefix="/api"`).

#### BUG-FB-004 — `BackendContract` не имеет `set_continuity_mode` и `_base_url`
- **Файл:строка:** `frontend/api_client.py:376-377, 421`
- **Severity:** High
- **Фикс:** Either убрать `set_continuity_mode` и фиксить `get_world_state` использовать `self._contract._t.base_url`; либо добавить `BackendContract.set_continuity_mode` и `_base_url` property.

#### BUG-FB-005 — `WorldSnapshotBuilder._empty_snapshot` опускает required perception fields
- **Файл:строка:** `backend/app/services/integration/world_snapshot_builder.py:372-391`
- **Severity:** High
- **Фикс:** Добавить `active_traversals={}`, `avatar_state=None`, `ambient_phenomenology=None`, `player_perception=None`, `recent_dialogues=recent_dialogues or []`.

#### BUG-FB-006 — `/api/world_state` endpoint не передаёт `player_perception` / `avatar_state` / `all_npcs_raw`
- **Файл:строка:** `backend/app/api/world_routes.py:59-60`
- **Severity:** Medium
- **Фикс:** Прокинуть perception/avatar/etc. из cached `last_world_snapshot` на `game_loop`, либо задепрекейтить endpoint.

#### BUG-FB-007 — `world_diff_applicator` пишет `life_status` в NPC root, не в `body_state`
- **Файл:строка:** `backend/app/services/state/world_diff_applicator.py:40`
- **Severity:** High (нарушение L12: Death Lock для cross-campaign continuity)
- **Симптом:** Когда `WorldStateApplicator.apply()` вызывается в CONTINUOUS mode для fates в `_DEAD_FATES`, он ставит `npc_cache[npc_id]["life_status"] = "DEAD"`. Но все consumer'ы `life_status` в симуляции читают `npc["body_state"]["life_status"]`. Мёртвые NPC из предыдущей кампании оживают и действуют.
- **Фикс:**
  ```python
  _bs = npc_cache[npc_id].setdefault("body_state", {})
  _bs["life_status"] = "DEAD"
  _bs["current_hp"] = 0
  _bs["consciousness"] = 0.0
  ```
  Также фикс `tests/test_world_continuity.py:54` → assertion на `body_state.life_status`.

#### BUG-FB-008 — `ResponseValidator._get_fallback_text` всегда возвращает "Ничего не произошло."
- **Файл:строка:** `backend/app/services/verbalization/response_validator.py:270-272` и triggers at lines 62, 67, 71, 75, 85, 91, 98, 103
- **Severity:** Critical (корневая причина S-1)
- **Симптом:** DM responses молча заменяются на "Ничего не произошло." для 8 классов нарушений: empty, non_russian, repeat, fourth_wall, cannot_speak, cannot_move, unauthorized_movement_only, forbidden action.
- **Фикс:**
  - Различать fallback text per violation class (repeat → "Мир замирает в ожидании.", fourth_wall → silent drop, empty → "Тишина.").
  - Tighten `_breaks_fourth_wall`: только flag "игрок" при прямом обращении ("Ты, игрок"), не в third-person narration.
  - Tighten `_contains_non_russian`: требовать <30% Cyrillic И >50 ASCII letters.
  - Логировать каждый fallback с full LLM output в `enigma_<date>.jsonl`.

#### BUG-FB-009 — `routes_debug.reset_campaign_relationships` импортирует несуществующий модуль
- **Файл:строка:** `backend/app/api/routes_debug.py:99`
- **Severity:** Medium
- **Фикс:**
  ```python
  from app.services.game_loop_accessor import get_game_loop
  from fastapi import Request
  loop = get_game_loop(request)
  ```

#### BUG-FB-010 — `SqlitePersistenceAdapter.delete_campaign` оставляет orphan per-location rows
- **Файл:строка:** `backend/app/services/state/sqlite_persistence_adapter.py:171-187`
- **Severity:** Critical (New Game не сбрасывает state)
- **Симптом:** `delete_campaign` делает `DELETE FROM state_kv WHERE key = ? OR key = ?` с `f"scene:{campaign_id}"` и `f"runtime:{campaign_id}"`. Но `save_scene` пишет в `f"scene:{campaign_id}:{location_id}"`. После New Game все `scene:{campaign_id}:tavern`, `scene:{campaign_id}:city_gate`, etc. выживают в SQLite и ре-лоадятся.
- **Фикс:**
  ```python
  conn.execute("DELETE FROM state_kv WHERE key LIKE ?", (f"scene:{campaign_id}:%",))
  conn.execute("DELETE FROM state_kv WHERE key LIKE ?", (f"runtime:{campaign_id}:%",))
  conn.execute("DELETE FROM state_kv WHERE key IN (?, ?, ?)",
               (f"scene:{campaign_id}", f"runtime:{campaign_id}", f"events_tick:{campaign_id}"))
  ```

#### BUG-FB-011 — `atomic_commit` пишет в wrong key (без location suffix)
- **Файл:строка:** `backend/app/services/state/sqlite_persistence_adapter.py:252-256`
- **Severity:** High
- **Фикс:**
  ```python
  _loc_id = scene_state.get("location_id", "default") if isinstance(scene_state, dict) else "default"
  self._upsert(f"scene:{campaign_id}:{_loc_id}", scene_state)
  ```

#### BUG-FB-012 — `world_scheduler.maybe_tick` использует wall clock
- **Файл:строка:** `backend/app/services/world_scheduler.py:32-34`
- **Severity:** Medium (нарушение L15)
- **Фикс:** Drive scheduling off `scene_state["tick"]` modulo `WORLD_TICK_EVERY_TURNS` (уже в `constants.py:306 = 2`).

#### BUG-FB-013 — `WorldSnapshot.created_at = time.time()` (wall clock)
- **Файл:строка:** `backend/app/models/world_snapshot.py:89`
- **Severity:** Medium
- **Фикс:** `created_at=tick` (или удалить поле).

#### BUG-FB-014 — `scene_state["last_save_real_time"] = time.time()`
- **Файл:строка:** `backend/app/services/scene_state_manager.py:1489-1491`
- **Severity:** Low
- **Фикс:** Вынести в отдельный diagnostic log file.

#### BUG-FB-015 — `game_action` route не возвращает `scene_state` или `metadata`
- **Файл:строка:** `backend/app/api/routes.py:569-595` vs `frontend/api_client.py:320-321`
- **Severity:** Medium
- **Фикс:** Either добавить `"scene_state": ...` в response, либо удалить fields из `GameActionResponse`.

#### BUG-FB-016 — `DirectGameGateway.send_action` имеет мёртвый код после `return`
- **Файл:строка:** `frontend/api_client.py:497-503`
- **Severity:** Low
- **Фикс:** Переместить diagnostic выше return или удалить.

#### BUG-FB-017 — `game_loop_bridge.turn()` хардкодит `location = "tavern_silver_wolf"` как fallback
- **Файл:строка:** `frontend/game_loop_bridge.py:127`
- **Severity:** Medium
- **Фикс:** Если `find_starting_location` падает, вернуть `TurnResult(error="No starting location for campaign")`.

#### BUG-FB-018 — `game_loop_bridge.turn()` не передаёт `world_x`/`world_y` в `stream_turn`
- **Файл:строка:** `frontend/game_loop_bridge.py:179-189`
- **Severity:** Medium
- **Фикс:** Расширить `stream_turn` signature + run Spatial Oracle в `_run_pipeline`.

#### BUG-FB-019 — `TruthState.discovered_secrets` — mutable `Set` в `frozen=True` dataclass
- **Файл:строка:** `backend/app/models/truth_state.py:44-57`
- **Severity:** Low
- **Фикс:** `frozenset` для `discovered_secrets`, возвращать новый `TruthState` из `mark_discovered`.

#### BUG-FB-020 — `L1Chronicle.archive_old_events` удаляет из active events table
- **Файл:строка:** `backend/app/services/npc/l1_chronicle.py:258-261`
- **Severity:** Low (data preserved in archive)
- **Фикс:** Mark rows as `archived=1` и иметь `query_raw` filter, либо документировать archive-then-delete pattern.

#### BUG-FB-021 — `MockProvider._pick_response` читает `ENIGMA_ENV` env var вместо `settings.environment`
- **Файл:строка:** `backend/app/services/llm/mock_provider.py:126-138`
- **Severity:** Medium (нарушение CAUSAL_CONTRACT §4.7.48)
- **Фикс:** MockProvider принимает `environment: str` в constructor (passed from `settings.environment` by factory). Удалить `os.getenv("ENIGMA_ENV")`.

#### BUG-FB-022 — `frontend/constants.py` определяет `RENDER_COLORS`, `COLOR_TEXT_*`, `AGGRESSION_COLORS` ДВАЖДЫ
- **Файл:строка:** `frontend/constants.py:88-136` (first) and `:154-201` (second)
- **Severity:** Low
- **Фикс:** Удалить second block.

#### BUG-FB-023 — `frontend/i18n.py` определяет `ui:death_title`, `ui:death_subtitle`, `ui:journal_title`, `ui:narrator` ДВАЖДЫ
- **Файл:строка:** `frontend/i18n.py:63-66` и `:108-112`
- **Severity:** Low
- **Фикс:** Удалить дубликаты.

#### BUG-FB-024 — (описан в original report, player_session_service.is_player_active) — wall clock для session lifetime
- **Severity:** Low (acceptable for session lifetime)
- **Фикс:** OK как есть.

#### BUG-FB-025 — BUG-FB-040: различные medium/low severity баги (см. `domain_frontend.md` для деталей)
- Включая: `fate_tracker` edge cases, `world_continuity` edge cases, `player_session` multi-player broken, etc.

#### BUG-FB-041 — `routes.py:update_scene_state` не валидирует protected keys по schema
- **Файл:строка:** `backend/app/api/routes.py:806-831`
- **Severity:** High (нарушение L15)
- **Симптом:** Endpoint принимает arbitrary `scene_state: dict` от фронта и мерджит, skip'ая только hardcoded `_protected_keys`. Любой другой key (`npc_positions`, `objects`, `environment`) может быть перезаписан фронтом — нарушение "backend is the only source of truth".
- **Фикс:** Switch на allow-list: только принимать frontend writes для `player_position`. Reject все остальные keys с 403.

#### BUG-FB-042 — `player_session_service` поддерживает только ONE active player per campaign
- **Файл:строка:** `backend/app/services/player_session_service.py:30, 195-213`
- **Severity:** Medium
- **Фикс:** `Dict[str, Dict[str, PlayerSession]]` (campaign → player → session).

#### BUG-FB-043 — `campaign_state_service.get_campaign_state` молча создаёт empty state при corrupt JSON
- **Файл:строка:** `backend/app/services/campaign_state_service.py:65-72`
- **Severity:** Medium
- **Фикс:** Rename corrupt file в `campaign_meta.json.corrupt-{timestamp}`, затем создать fresh state. Логировать corruption.

#### BUG-FB-044 — `game_loop.idle_tick` инкрементит `game_time_seconds` на hardcoded `60.0`
- **Файл:строка:** `backend/app/services/game_loop/__init__.py:893`
- **Severity:** Low
- **Фикс:** Использовать `constants.GAME_TICK_INTERVAL_SECONDS` + `Calendar.advance`.

#### BUG-FB-045 — `frontend/game_screen.py` хранит `game_time_seconds` как инстанс-состояние
- **Файл:строка:** `frontend/game_screen.py:555, 1003, 1081, 1218`
- **Severity:** Low
- **Фикс:** Переименовать в `display_time_seconds` (или `_hud_time_seconds`).

#### BUG-FB-046 — `scene_state_manager.commit` пишет `last_save_real_time`, но никто не читает
- **Файл:строка:** `backend/app/services/scene_state_manager.py:1489-1491`
- **Severity:** Low
- **Фикс:** Удалить или вынести в audit log.

#### BUG-FB-047 — `WorldSnapshotDTO` `@dataclass(frozen=True)`, но `routes.py:game_action` мутирует dict через `asdict`
- **Файл:строка:** `backend/app/api/routes.py:540-548` and `backend/app/services/game_loop/__init__.py:1267-1271`
- **Severity:** Low
- **Фикс:** Документировать, что frozen — на dataclass level, dict projection — mutable.

#### BUG-FB-048 — `routes_debug.agent_health_dashboard` возвращает mock agent statuses
- **Файл:строка:** `backend/app/api/routes_debug.py:23-32`
- **Severity:** Low
- **Фикс:** Wire к actual per-agent model pool lookups через `router.get_model_for_agent(agent_name)`, либо удалить endpoint.

#### BUG-FB-049 — `frontend/api_client.py:BackendContract` не включает `observed_facts` в `_map_action_response`
- **Файл:строка:** `frontend/api_client.py:302-324` vs `backend/app/models/schemas.py:80`
- **Severity:** Low
- **Фикс:** Добавить `observed_facts: list = field(default_factory=list)` в `GameActionResponse` и `observed_facts=raw.get("observed_facts", [])` в `_map_action_response`.

#### BUG-FB-050 — `game_loop_bridge.py` не передаёт `recent_dialogues` из idle_tick в TurnResult
- **Файл:строка:** `frontend/game_loop_bridge.py:179-223`
- **Severity:** Medium (covered by BUG-FB-001 fix)
- **Фикс:** Резолвится фиксом BUG-FB-001.

> **Дополнительные баги BUG-FB-025..BUG-FB-036** (см. `domain_frontend.md`): `player_perception` key-present-but-None confusion, `idle_tick` response missing `confirmed_location_id`, `is_telegraph` возвращает truncated response, и др.

---

## 4. ТИХИЕ ОТКАЗЫ (try/except: pass) — Critical Catalog

Это главный **скрытый враг** проекта. Большинство багов выше сопровождаются silent swallow. Ниже — все найденные `try/except: pass` и `except Exception` без логирования:

| Файл:строка | Pattern | Severity | Bug |
|-------------|---------|----------|-----|
| `tick_orchestrator.py:1264-1265` | `except Exception: pass` вокруг `memory_manager.get_identity_traits` | **Critical** | BUG-CORE-002 — L1 identity projection навсегда отключена |
| `tick_orchestrator.py:532-533` | `except Exception: pass` вокруг `SpatialRegistry.get_or_load` | Medium | BUG-SPATIAL-023 — AdaptiveTickLoader отключён, мир замерзает без ошибки |
| `tick_orchestrator.py:726-741, 899-912` | `DirectiveInterpretationSubscriber` вызывается с mock event | Medium | BUG-DLG-021 — обход EventBus |
| `npc_tick_pipeline.py:188-191, 286-289, 314-317, 584-585, 635-636` | `except Exception as _e: logger.warning(...)` per-NPC | Medium | Memory event creation, belief integration, proactive movement — skip per-NPC |
| `reduction.py:204-210, 214-222` | Phase8Context construction и handler.handle() swallowed | High | BUG-CORE-007 — social_input crash спрятан |
| `pipeline_runner.py:144-145, 175-176` | Memory apply failures for individual NPCs swallowed | Medium | Memory propagation молча дропает events |
| `npc_orchestration.py:194-195` | `_loc_spatial_svc = SpatialFactory.build_for_campaign(...); except Exception: pass` | Medium | Silent spatial service build failure для non-active locations |
| `movement_engine.py:1244-1247` | `except Exception as exc: logger.error("[APPLY_CRASH]...")` — **swallows SimulationIntegrityError** | **High** | BUG-SPATIAL audit — NPC traversal silently lost, нарушение L21 |
| `dm_agent.py:91-108` | `try/except Exception` вокруг `narrate()` → unconditional `_fallback_narrate()` | **Critical** | BUG-DLG-001 — все DM errors сворачиваются в fallback |
| `dm_agent.py:300-307, 637-644, 726-727, 866, 1028-1029` | Various `except Exception` | Medium | Silent failures в scene description, system prompt load, JSON parse |
| `dm_phase.py:62, 81` | `except Exception:` без логирования | Medium | BUG-DLG-029 — STM и L2 memory extraction failures невидимы |
| `dialogue_update_extractor.py:47-49` | `except Exception` → empty `DialogueUpdate()` | **High** | BUG-DLG-011 — zero structured updates to STM |
| `dialogue_memory_subscriber.py:68` | `except Exception` | Medium | All dialogue memory writes молча падают |
| `npc_dialogue_subscriber.py:178, 201` | duplicate `except` block | High | BUG-DLG-012 — dead code, реальная ошибка спрятана |
| `task_scheduler.py:150, 219` | `except Exception` | Medium | Task reconstruction / materializer failures невидимы |
| `memory_manager.py:304, 348` | `except Exception` | Low | Logged as warning, OK |
| `agent_runner.py:82` | `except Exception` — "B5-FIX silent failure suppressed" | Medium | Abort_generation failure silenced |
| `game_loop/__init__.py:1572` | `except Exception` — "B5-FIX silent failure suppressed" — Death Guard NPC positions fetch | Medium | NPC positions невидимы после death |
| `spatial_target_resolver.py:77-78` | `except ValueError: pass` | Low | OK для NodeRole membership test, но плохой pattern |
| `spatial_registry.py:127-128` | `except (IndexError, ValueError)` | Low | Defensive, OK |
| `scene_state_manager.py:1667-1670` | `except Exception as e: logger.error(...)` — но build failure silent (svc stays None) | Medium | Build failure спрятана |
| `graph_compiler.py:784, 800, 815` | `except Exception as e: logger.error(...)` вокруг JSON parsing | Low | OK |
| `combat_subscriber.py:73-75` | `print()` для diagnostics | Low | BUG-PERC-018 — должен быть `logger.debug` |
| `game_loop/__init__.py:635-637` | `print()` для PerceptionProjector diagnostics | Low | BUG-PERC-019 |

**Главный принцип исправления:** Каждый `except Exception: pass` без логирования должен быть либо:
1. Удалён (если защищаемый код не нужен).
2. Заменён на `except SpecificError as e: logger.warning(...)` (если ошибка ожидаема).
3. Заменён на `raise SimulationIntegrityError(...)` (если ошибка нарушает инвариант).

---

## 5. МЁРТВЫЙ / DISCONNECTED КОД — Catalog

| Что | Файл:строка | Action |
|------|-------------|--------|
| 135 строк мёртвого кода после `return` в `execute()` | `tick_orchestrator.py:460-594` | Удалить (BUG-CORE-001) |
| `LifeEngine.tick_decisions` — ~500 строк дубликата pipeline | `life_engine.py:632-1132` | Удалить (BUG-CORE-016) |
| Дублирующий блок `npcs = self._npc_cache.get(...)` после `return` | `life_engine.py:683-694` | Удалить (BUG-CORE-017) |
| `transition_traversal()` FSM — 0 call sites | `traversal_schema.py:55-78` | Wire в `build_traversal_dict` + `advance` (BUG-SPATIAL-005/026) |
| `update_npc_position` — bypasses TraversalState контракт, 0 callers | `scene_state_manager.py:1853-1883` | Удалить (BUG-SPATIAL-014) |
| `MovementEngine._spatial_intent_gate` — duplicate no-op filter | `movement_engine.py:71-118` | Удалить (BUG-SPATIAL-020) |
| `PerceptualAttentionService` — весь файл не wired | `perceptual_attention_service.py` | Wire или удалить (BUG-PERC-017) |
| `ManifestationPhysicsEngine` trace loop в `integration.py:472-518` — overridden by Pipeline B | `integration.py:472-518` | Удалить или скормить `all_npcs_raw` (BUG-PERC-009/011) |
| `combat_math.apply_damage` / `apply_healing` — acknowledged dead code | `combat_math.py:300-340` | Удалить (BUG-PERC-005/006) |
| `combat_service.py` — параллельная legacy D&D система | `combat_service.py:1-117` | Удалить или роутить через `ImpactEngine` (BUG-PERC-007) |
| `WorldSimulationAgent.tick()` — useless LLM call | `world_sim_agent.py:135-149` | Удалить (BUG-DLG-028) |
| `task_scheduler.process_tasks` — dead method с wrong signature | `task_scheduler.py:71-90` | Удалить (BUG-DLG-022) |
| `IntentEventAdapter.to_event` non-attack branches — dead code | `intent_event_adapter.py:38-46` | Удалить (BUG-DLG-023) |
| `thread_id` field — generated but never read | `domain/communication.py`, `dialogue_session.py`, etc. | Удалить или wire (BUG-DLG-014) |
| `mock_agent_health_dashboard` — hardcoded identical status | `routes_debug.py:23-32` | Wire или удалить (BUG-FB-048) |
| `routes_debug.reset_campaign_relationships` — dead route (ImportError) | `routes_debug.py:99` | Исправить импорт (BUG-FB-009) |
| `DirectGameGateway.send_action` — diagnostic code after `return` | `api_client.py:497-503` | Удалить (BUG-FB-016) |
| `_recent_dialogues` — растёт безгранично | `task_scheduler.py:48, 239-243` | Cap at 100 (BUG-DLG-038) |

---

## 6. ПЛАН ПОЧИНКИ (4 ФАЗЫ)

> **Главный принцип:** Один шаг = одно изменение. Перед изменением кода обязательна археология (PowerShell / print-диагностика) для понимания ownership. После фикса — `python backend/tests/IPT.py` до и после.

### ФАЗА 0 — СТАБИЛИЗАЦИЯ (4-6 часов) — Critical P0

Цель: вернуть играбельность. После Фазы 0 игрок видит DM-ответы, NPC двигаются к bed'ам, perception не пустой.

| # | Bug ID | Что делать | Файл | Ожидаемый эффект |
|---|--------|------------|------|------------------|
| 0.1 | BUG-CORE-003 | Замостить `dm_ctx`-мост: в `pipeline_runner.build_tick_state` читать `ctx.hub_event`, `ctx.player_target_id`, `ctx.action_type`, `ctx.raw_input` напрямую через `getattr(ctx, ..., default)` | `pipeline_runner.py:39-43` | S-1 фикс — DM начинает видеть действия игрока |
| 0.2 | BUG-DLG-003 | После `state.shared_context.all_npcs_raw = ...` добавить `state.shared_context.all_npcs_raw_snapshot = state.shared_context.all_npcs_raw` | `game_loop/__init__.py:1051` | S-1 фикс — DM получает контекст NPC в LLM-промпт |
| 0.3 | BUG-FB-008 + BUG-DLG-018 | Различать fallback text per violation class. Tighten `_breaks_fourth_wall` (только прямое обращение). Tighten `_contains_non_russian` (<30% Cyrillic AND >50 ASCII). Логировать каждый fallback с full LLM output | `response_validator.py:62-103, 115-156, 270-272` | S-1 фикс — DM-ответы перестают быть пустыми |
| 0.4 | BUG-DLG-002 | Ослабить DM contract gate: если `raw_input` содержит известное русское существительное/роль, но resolver вернул пусто — логировать WARN и продолжать с generic narrative вместо raise | `dm_agent.py:245-249` | S-1 фикс — DM не падает на неразрезолвленных target'ах |
| 0.5 | BUG-PERC-002 + BUG-DLG-004 + BUG-DLG-019 | Расширить `_evt_map` в `phase_1_input.py:276-283` всеми недостающими ключами (`player_threatens`, `player_steals`, `player_insults`, `player_flees`, `intimidation`, `theft`, `betrayal`, `help`, `saved_life`) | `phase_1_input.py:276-283` | S-4 фикс — угрозы доходят до ReactionSubscriber |
| 0.6 | BUG-PERC-001 + BUG-CORE-006 | В GameLoop `idle_tick` **удалить** override `dataclasses.replace(world_snapshot, player_perception=_perception)`. Фаза 9 уже построила корректный DTO. В `run_turn` прокинуть `observed_facts=getattr(state, "observed_facts", [])` в builder | `game_loop/__init__.py:954-963, 1236-1242`, `perception_projector.py:34-56` | S-2 фикс — perception не пустой |
| 0.7 | BUG-PERC-008 | Удалить фильтр `if trace.locomotion_instability > 0.05 or ...` в `behavior_manifestation_service.py:140-145` — всегда append. Добавить `MANIFEST_CALM` tag для здоровых NPC в `PhenomenologyProjectionService` | `behavior_manifestation_service.py:140-145` | S-2 фикс — DM имеет что описывать |
| 0.8 | BUG-SPATIAL-001 | В cross-loc intercept НЕ мутировать `intent.target_node_id`. Хранить оригинальный target в local var, lookup'ить его в target loc | `movement_engine.py:269-289, 322-324` | S-3 фикс — NPC достигают bed'а |
| 0.9 | BUG-CORE-004 | Перенести строки 250-258 в `__init__` LifeEngine — `spatial_service`/`persistence`/`claim_bus` больше не обнуляются | `life_engine.py:246-258` | S-3 фикс — SpatialService переживает тик |
| 0.10 | BUG-CORE-005 | Реструктурировать if/elif в `npc_tick_pipeline.py:545-606` — добавить else-ветвь для всех movement-capable intents | `npc_tick_pipeline.py:545-606` | S-3 фикс — NPC эмитят movement intents |
| 0.11 | BUG-FB-002 | В `skip_time` finally добавить `commit_tick_result` + `unlock_tick`. Использовать `lock_all_for_tick` по всем location_ids | `game_loop/__init__.py:743-822` | S-3 фикс — sleep-мутации персистятся |
| 0.12 | BUG-CORE-010 + BUG-DLG-005 | Очищать `pending_tasks` после enqueue в `execute_pending`. Add hard cap на heap size (50) | `task_scheduler.py:92-138` | S-5 фикс — queue не растёт |
| 0.13 | BUG-FB-001 | В `stream_turn` между `dm_text_parts` flush и `yield {"type": "done", ...}` — зеркалировать post-pipeline block из `run_turn` (строки 1200-1271). Добавить `world_snapshot` и `npc_positions` в done payload | `game_loop/__init__.py:1424-1435` | S-2 фикс в Direct mode |
| 0.14 | BUG-FB-010 + BUG-FB-011 | Prefix delete в `delete_campaign`. В `atomic_commit` писать в `f"scene:{campaign_id}:{_loc_id}"` | `sqlite_persistence_adapter.py:171-187, 252-256` | New Game реально сбрасывает state |

**После Фазы 0:** запустить IPT (`python backend/tests/IPT.py`). Ожидаемо: 5/5 passed (или 6/6). Если не прошли — откатить последний фикс, разобраться.

---

### ФАЗА 1 — АРХИТЕКТУРНАЯ ВОССТАНОВЛЕНИЕ (8-12 часов) — High P1

Цель: восстановить контракты ADR. После Фазы 1 система онтологически чиста.

| # | Bug ID | Что делать | Файл |
|---|--------|------------|------|
| 1.1 | BUG-CORE-001 | Удалить строки 460-594 в `tick_orchestrator.execute()`. Если нужна логика из мёртвого блока (CFRM attach, AdaptiveTickLoader), повторно реализовать внутри активного цикла | `tick_orchestrator.py:460-594` |
| 1.2 | BUG-CORE-002 | Добавить параметр `campaign_id` в `_compute_effective_drives`. Использовать `self._get_memory_manager()`. Удалить `except Exception: pass`, заменить на `logger.error(...)` | `tick_orchestrator.py:1260-1265` |
| 1.3 | BUG-CORE-007 | В `reduction.py:179-181` установить `ctx.shared_context.scene_state = ctx.scene_state`. В `social_input_projector.py:93, 111` использовать `getattr(...)` defensive | `reduction.py:178-181`, `social_input_projector.py:93, 111` |
| 1.4 | BUG-CORE-008 | Заменить `_tick_scene` на `_tick_scenes[_loc_id]` (или вызвать `lock_for_tick(..., force=True)`) | `game_loop/__init__.py:1642` |
| 1.5 | BUG-CORE-014 | Добавить ранний фильтр dead NPCs в `_run_core_phases` перед `_phase_0_simulation` | `tick_orchestrator.py:600-624` |
| 1.6 | BUG-CORE-018 + BUG-CORE-Purity | Эмитить `StateDeltas(domain=DeltaDomain.SPATIAL, ...)` для восстановленных NPC в `_rebuild_cluster_occupancy`. Удалить `StateApplicator.apply()` вызов из `NpcTickPipeline.run` | `tick_orchestrator.py:262-341`, `npc_tick_pipeline.py:609-636` |
| 1.7 | BUG-SPATIAL-005 + BUG-SPATIAL-026 | Wire `transition_traversal()` FSM в `build_traversal_dict` (PENDING → MOVING) и в `TraversalExecutionSystem.advance` (MOVING → COMPLETED) | `traversal_schema.py:171-190`, `traversal_execution_system.py:86-87` |
| 1.8 | BUG-SPATIAL-004 | Удалить чтение `player_spatial` в `_enrich_local_positions`. Удалить `"player_spatial": {...}` block из scene init. Удалить параметр `player_spatial` из `update_player_target` | `scene_state_manager.py:1019, 1681-1696, 539` |
| 1.9 | BUG-SPATIAL-015 | Убрать zone filter в финальном `get_nearest` call в `resolve_affordance`. Принимать `target_zone` параметром | `spatial_service.py:327-377` |
| 1.10 | BUG-SPATIAL-006 + BUG-SPATIAL-007 | Удалить (0,0) sentinel в SSM template fallback. Tighten `euclidean_distance` sentinel check до OR | `scene_state_manager.py:977, 1186-1190`, `event_compiler.py:311-312, 749-750`, `spatial_observatory_service.py:228-239`, `spatial_runtime.py:71-83` |
| 1.11 | BUG-SPATIAL-002 | Принять `start_zone` параметром в `find_path` | `spatial_service.py:526` |
| 1.12 | BUG-SPATIAL-024 | Поднимать `SimulationIntegrityError` с `invariant_id="INV-CROSS-LOC-NO-BOUNDARY"` вместо silent drop | `movement_engine.py:326-338` |
| 1.13 | BUG-PERC-003 + BUG-PERC-004 | Заменить `random.Random(rng_seed)` на `KernelRNG(...)` в `impact_engine.py`. Убрать `rng or random` fallback в `combat_math.py` | `impact_engine.py:24,46,95,131`, `combat_math.py:12,50,52,61` |
| 1.14 | BUG-PERC-005 + BUG-PERC-006 | Удалить `combat_math.apply_damage` и `apply_healing` (acknowledged dead code) | `combat_math.py:300-340` |
| 1.15 | BUG-PERC-007 | Определить, wired ли `combat_service.py`. Если нет — удалить. Если да — роутить через `ImpactEngine.resolve_physical_impact` | `combat_service.py:1-117` |
| 1.16 | BUG-PERC-015 | Заменить `lambda char, _: self._check_lifting_capacity(...)` на `lambda char, _: PhysicsValidator._check_lifting_capacity(...)` | `physics_validator.py:82` |
| 1.17 | BUG-PERC-029 (O6) | Добавить `if npc.get("life_status", "ALIVE") == "DEAD": continue` в `AffectiveDecayHandler` | `affective_decay_handler.py:52-93` |
| 1.18 | BUG-FB-007 | В `world_diff_applicator.py:40` писать `life_status` в `_bs["life_status"]` (через `setdefault`). Фикс `tests/test_world_continuity.py:54` | `world_diff_applicator.py:40` |
| 1.19 | BUG-FB-003 | Изменить декоратор на `@router.post("/debug/llm/restart")` | `routes.py:160` |
| 1.20 | BUG-FB-004 | Реализовать `BackendContract.set_continuity_mode` (POST на `/api/game/continuity_mode`) и `_base_url` property | `frontend/api_client.py:210-324` |
| 1.21 | BUG-FB-005 | Добавить `active_traversals`, `avatar_state`, `ambient_phenomenology`, `player_perception`, `recent_dialogues` в `_empty_snapshot` | `world_snapshot_builder.py:372-391` |
| 1.22 | BUG-FB-041 | Switch `update_scene_state` на allow-list: принимать только `player_position` от фронта | `routes.py:806-831` |
| 1.23 | BUG-DLG-006 | Прокинуть `game_time_seconds` из `scene_state` в `DialogueQueue.enqueue()` / `dequeue_next()`. Заменить `time.time()` на `game_time_seconds` | `dialogue_queue.py:43-50, 70, 93` |
| 1.24 | BUG-DLG-010 | Удалить L2 memory block (`npc_l2_memory_block`) из DM agent's prompt. NPC continuity идёт через NPC-речь в STM | `dm_phase.py:65-82`, `dm_agent.py:233-236` |
| 1.25 | BUG-DLG-011 | Добавить `"dialogue_extractor": Capability.FACT_EXTRACTION` в `DEFAULT_AGENT_CAPABILITY_MAP`. Использовать `GenerationParams(...)`. Заменить `response.text` на `response` | `router.py:133-140`, `dialogue_update_extractor.py:38-49` |
| 1.26 | BUG-DLG-012 | Удалить дублирующий `except` block в `npc_dialogue_subscriber.py:201-202`. Реструктурировать error handling | `npc_dialogue_subscriber.py:178, 201` |
| 1.27 | BUG-DLG-013 | Re-raise `DialogueContractViolation` из `_generate_with_router` | `dialogue_executor.py:213-230` |
| 1.28 | BUG-FB-012 | Drive scheduling off `scene_state["tick"]` modulo `WORLD_TICK_EVERY_TURNS`. Удалить `datetime.now()` | `world_scheduler.py:32-34` |
| 1.29 | BUG-FB-013 | Заменить `created_at=time.time()` на `created_at=tick` | `world_snapshot.py:89` |
| 1.30 | BUG-FB-021 | MockProvider принимает `environment: str` в constructor. Удалить `os.getenv("ENIGMA_ENV")` | `mock_provider.py:126-138`, `factory.py:78` |

**После Фазы 1:** запустить IPT + все sandbox-тесты + canary `tests/canary/test_full_playthrough.py`. Ожидаемо: 0 критических дрейфов.

---

### ФАЗА 2 — ОЧИСТКА И ДЕТАЛИ (6-8 часов) — Medium P2

Цель: устранить мёртвый код, silent swallows, доработать незавершённые миграции.

| # | Bug IDs | Что делать |
|---|---------|------------|
| 2.1 | BUG-CORE-009 | Деструктурировать tuple правильно в `phase_2_world_tick.py:149` — lookup raw dict из `tick_ctx.all_npcs_raw` |
| 2.2 | BUG-CORE-011 + BUG-CORE-012 | Заменить `random.choice` / `random.Random(seed)` на `KernelRNG(...)` в `task_scheduler.py:171,199` и `resolution_engine.py:127,145` |
| 2.3 | BUG-CORE-013 | Собирать `l1_drift_events` из `BreakProgressEngine.calculate()` и аппендить `TraitDriftEvent` в `npc_tick_pipeline.py` per-NPC цикле |
| 2.4 | BUG-CORE-015 | DRF scoring overlay — использовать `getattr(_intent, "speaker", None) or getattr(_intent, "npc_id", None) or ...` |
| 2.5 | BUG-CORE-016 + BUG-CORE-017 | Удалить `tick_decisions` (~500 строк) и дублирующий блок. Обновить `phases/README.md:84` |
| 2.6 | BUG-SPATIAL-003 + BUG-SPATIAL-010 + BUG-SPATIAL-011 + BUG-SPATIAL-021 | Code hygiene: print→logger, удалить дубликаты, добавить missing imports |
| 2.7 | BUG-SPATIAL-008 | `cluster_relation` — добавить `cluster_to_neighbors: dict[str, set[str]]` field |
| 2.8 | BUG-SPATIAL-012 | Rename `is_reachable` → `is_present_in_graph`. Добавить реальный `is_reachable_from(start, target)` через A* |
| 2.9 | BUG-SPATIAL-014 | Удалить `update_npc_position` (dead code, bypasses TraversalState) |
| 2.10 | BUG-SPATIAL-016 + BUG-SPATIAL-028 | Add explicit `target_node` existence check. Populate `MovementTrace` на `TARGET_NODE_NOT_FOUND` |
| 2.11 | BUG-SPATIAL-017 | `try_reserve_node` under URGENT — либо evict, либо вернуть `False` |
| 2.12 | BUG-SPATIAL-018 | Run zombie-cleanup ПОСЛЕ `TraversalExecutionSystem.advance` |
| 2.13 | BUG-SPATIAL-019 | Multi-waypoint interpolation в `event_compiler` shadow |
| 2.14 | BUG-SPATIAL-023 | `logger.warning(f"[SPATIAL_REGISTRY] load failed: {e}")` |
| 2.15 | BUG-SPATIAL-025 | Использовать `get_nearest_safe_node` (без zone filter) для player в `_enrich_local_positions` |
| 2.16 | BUG-SPATIAL-027 | Использовать explicit flag `is_traversal_complete: bool = False` на `SceneChange` вместо brittle string match |
| 2.17 | BUG-SPATIAL-029 | Normalize all positions в canonical form при build overlay |
| 2.18 | BUG-PERC-009 + BUG-PERC-011 | Схлопнуть dual perception pipeline. Использовать `all_npcs_raw` (correct source). Удалить trace-building loop в `integration.py:472-518` |
| 2.19 | BUG-PERC-010 | Либо удалить psyche reads из `BehaviorManifestationService`, либо обновить docstring |
| 2.20 | BUG-PERC-013 + BUG-FB-020 | Решить: либо переименовать контракт в "append-only + archival migration", либо mark rows as `archived=1` и не DELETE |
| 2.21 | BUG-PERC-014 | Gate crystallization на `if not ctx.phase_2_events: continue` |
| 2.22 | BUG-PERC-017 + BUG-PERC-024 | Wire `PerceptualAttentionService.build_perception` или удалить + убрать `avatar_desync` |
| 2.23 | BUG-PERC-025 | Добавить ранний somatic gate в `phase_1_input.publish_classified_player_event`: если `body_state.shock_impulse > 0.7` или `is_conscious(body_state) == False` — не парсить semantic content |
| 2.24 | BUG-DLG-001 | Различать `DialogueContractViolation` (re-raise / distinct code) от LLM-failure (fallback OK) |
| 2.25 | BUG-DLG-007 + BUG-DLG-008 | Использовать sorted-pair key в `clear_dialogue_session` и `clear_all_dialogue_sessions` |
| 2.26 | BUG-DLG-009 | `dequeue_next` возвращать `dequeue_status` enum или raise `RateLimited` |
| 2.27 | BUG-DLG-014 + BUG-DLG-026 | Wire `thread_id` через `MemoryManager.get_dialogue_session` key — либо удалить поле и весь код |
| 2.28 | BUG-DLG-016 | `list(self._factions[fid].npc_members)` |
| 2.29 | BUG-DLG-017 | Либо вычислять listeners в materializer, либо документировать hand-off |
| 2.30 | BUG-DLG-021 | Переименовать `DirectiveInterpretationSubscriber` → `DirectiveInterpreter` (он не subscriber) |
| 2.31 | BUG-DLG-023 + BUG-DLG-030 | Удалить unused branches в `IntentEventAdapter.to_event` |
| 2.32 | BUG-DLG-025 | Разрешить `listener="soliloquy"` или `listener=""` в `NpcDialogueSubscriber` — STM write, skip relationship update |
| 2.33 | BUG-DLG-029 | Заменить `except Exception:` на `except Exception as e: logger.warning(...)` в `dm_phase.py:62, 81` |
| 2.34 | BUG-DLG-031 | Передавать `intent=shared_context.action_type` в `add_dialogue_turn` |
| 2.35 | BUG-DLG-032 | Defer confession parsing в background task |
| 2.36 | BUG-DLG-034 | Priority inversion для stale low-priority tasks в `dialogue_queue` |
| 2.37 | BUG-DLG-035 | Использовать `ctx.shared_context.perceiving_npcs` как witness set в `propagation.py` |
| 2.38 | BUG-FB-006 | Прокинуть perception/avatar/etc. из cached `last_world_snapshot` в `/api/world_state` |
| 2.39 | BUG-FB-009 | Заменить import на `from app.services.game_loop_accessor import get_game_loop` |
| 2.40 | BUG-FB-012 + BUG-FB-013 + BUG-FB-014 | Удалить все wall-clock из simulation artifacts |
| 2.41 | BUG-FB-015 | Либо добавить `scene_state`/`metadata` в response, либо удалить fields из `GameActionResponse` |
| 2.42 | BUG-FB-017 | Если `find_starting_location` падает, вернуть `TurnResult(error="No starting location for campaign")` |
| 2.43 | BUG-FB-018 | Расширить `stream_turn` signature + run Spatial Oracle в `_run_pipeline` |
| 2.44 | BUG-FB-038 | Завершить A1 миграцию: frontend читает scene_state только через API, удалить JSON mirror write |
| 2.45 | BUG-FB-039 | Заменить direct file access на `game_loop.scene_manager.get_scene_state(...)` |
| 2.46 | BUG-FB-042 | `Dict[str, Dict[str, PlayerSession]]` (campaign → player → session) |
| 2.47 | BUG-FB-043 | Rename corrupt file, затем создать fresh state. Логировать corruption |
| 2.48 | BUG-FB-044 | Использовать `constants.GAME_TICK_INTERVAL_SECONDS` + `Calendar.advance` |
| 2.49 | BUG-FB-045 | Переименовать frontend instance var в `display_time_seconds` |
| 2.50 | BUG-FB-046 | Удалить `last_save_real_time` или вынести в audit log |
| 2.51 | BUG-FB-048 | Wire `agent_health_dashboard` к actual per-agent model pool lookups |
| 2.52 | BUG-FB-049 | Добавить `observed_facts` в `GameActionResponse` и `_map_action_response` |
| 2.53 | BUG-FB-022 + BUG-FB-023 | Удалить дублирующие блоки в `frontend/constants.py` и `frontend/i18n.py` |
| 2.54 | BUG-FB-050 | Резолвится фиксом BUG-FB-001 |
| 2.55 | BUG-PERC-012 + BUG-PERC-016 + BUG-PERC-018 + BUG-PERC-019 + BUG-PERC-020 + BUG-PERC-021 + BUG-PERC-022 + BUG-PERC-023 + BUG-PERC-026 + BUG-PERC-027 + BUG-PERC-028 | Code hygiene: dead branches, print→logger, duplicate blocks, defensive init |
| 2.56 | BUG-DLG-015 + BUG-DLG-022 + BUG-DLG-024 + BUG-DLG-027 + BUG-DLG-028 + BUG-DLG-033 + BUG-DLG-036 + BUG-DLG-037 + BUG-DLG-038 + BUG-DLG-039 + BUG-DLG-040 | Code hygiene: dead code, fallback logging, etc. |

**После Фазы 2:** запустить `python backend/tests/IPT.py` + ruff check + canary. Ожидаемо: 0 warnings, 0 errors.

---

### ФАЗА 3 — ТЕСТЫ И ВАЛИДАЦИЯ (4-6 часов) — финальная проверка

| # | Что делать |
|---|------------|
| 3.1 | Добавить IPT-тесты для новых инвариантов: `test_dm_ctx_bridge_wired`, `test_player_threatens_event_published`, `test_perception_pipeline_single`, `test_skip_time_persists_state`, `test_dialogue_queue_drains_within_tick_budget`, `test_spatial_service_survives_tick` |
| 3.2 | Добавить regression-тесты для всех P0-багов (по одному тесту на каждый BUG-CORE-001..014, BUG-DLG-001..005, BUG-PERC-001..008, BUG-SPATIAL-001/004/005/015/026, BUG-FB-001/002/007/008/010/011) |
| 3.3 | Запустить `DriftLaboratory` для воспроизведения сценариев из логов (sleep test, threat test, perception test) |
| 3.4 | Запустить canary `tests/canary/test_full_playthrough.py` |
| 3.5 | Полная очистка `__pycache__` + перезапуск backend + 30-минутный playthrough |
| 3.6 | Сверка с CAUSAL_CONTRACT: пройти по каждому правилу и подтвердить compliance |
| 3.7 | Обновить `MUTATIONS.md` — записать S146 "ENIGMA STABILIZATION" с описанием всех фиксов |

---

## 7. ПРОЦЕССНЫЕ РЕКОМЕНДАЦИИ

### 7.1. Перед началом работы

1. **Прочитать `CAUSAL_CONTRACT v2.0`, `ADR Master Index`, `MUTATIONS.md`** — без этого нельзя трогать код.
2. **Создать ветку `V.0.5.3.6.8_stabilization`** от текущего `HEAD`.
3. **Закрыть все IDE**, открыть только VSC + terminal.
4. **Очистить `__pycache__`** — `find . -type d -name __pycache__ -exec rm -rf {} +`.
5. **Запустить IPT baseline**: `python backend/tests/IPT.py` — записать результат "до".

### 7.2. Во время фикса

1. **Один шаг = одно изменение.** Не делать 5 фиксов одновременно.
2. **Перед изменением кода — археология.** Прочитать file полностью, найти все call sites, понять ownership.
3. **После каждого фикса:**
   - `python backend/tests/IPT.py` — должен пройти.
   - Если падает — откатить фикс, разобраться.
   - Логировать в `worklog.md`: что изменено, какой баг закрыт.
4. **Никогда не коммитить в `main`** — только в feature-branch.
5. **Использовать `ruff check .`** после каждых 3-5 фиксов.

### 7.3. Категорические запреты

| Запрет | Альтернатива |
|--------|--------------|
| `try/except Exception: pass` | `try/except SpecificError as e: logger.warning(...)` или `raise SimulationIntegrityError(...)` |
| `random.*` в kernel layer | `KernelRNG(tick, npc_id, salt)` |
| `time.time()` / `datetime.now()` в симуляции | `game_time_seconds` |
| Прямая мутация `scene_state["npc_positions"]` | `delta_buffer` + `StateApplicator.apply_batch()` |
| Прямая мутация `state.hp` | `body_state["current_hp"]` через `PhysiologyPayload` |
| `DecisionHub()` без `rng` | `DecisionHub(rng=KernelRNG(...))` |
| `print()` в production | `logger.debug(...)` |
| LLM в `TickOrchestrator` / `DecisionHub` | `TaskScheduler` + `TaskExecutor` |
| MockProvider в production | Реальный LLM provider |

### 7.4. Критерии готовности

Фаза 0 готова, когда:
- [ ] Игрок видит DM-ответы на `угрожать трактирщику ножом` (не "Ничего не произошло")
- [ ] NPC после сна оказываются в `tent_*` / `guard_bed*`, не на `exit_west`
- [ ] `PlayerPerceptionDTO` содержит non-empty `embodied_traces` и `observed_facts`
- [ ] `DialogueQueue._heap` не растёт между тиками
- [ ] Player threats триггерят fear/stress_delta в target NPC

Фаза 1 готова, когда:
- [ ] `python backend/tests/IPT.py` — 6/6 passed
- [ ] `ruff check .` — 0 errors
- [ ] В логах нет `[PHASE8_CRASH]`, `[TICK_CRASH]`, `[APPLY_CRASH]`
- [ ] `transition_traversal()` имеет ≥2 call sites в grep

Фаза 2 готова, когда:
- [ ] `grep -r "except Exception: pass" backend/app/` — 0 результатов
- [ ] `grep -r "random\.choice\|random\.Random\|random\.randint" backend/app/services/{npc,spatial,combat,game}/` — 0 результатов (только KernelRNG)
- [ ] `grep -r "time\.time()\|datetime\.now" backend/app/services/{tick_orchestrator,life_engine,decision_hub,world_scheduler}.py backend/app/models/world_snapshot.py` — 0 результатов
- [ ] `grep -r "print(" backend/app/` — 0 результатов

Фаза 3 готова, когда:
- [ ] Все новые IPT-тесты проходят
- [ ] 30-минутный playthrough не падает
- [ ] `MUTATIONS.md` обновлён

---

## 8. ПРИЛОЖЕНИЯ

### 8.1. Файлы-отчёты по доменам (детальные)

- `domain_core.md` — 18 багов DOM-01 (Core Tick Pipeline), 492 строки
- `domain_spatial.md` — 30 багов DOM-04 (Spatial/Movement), 742 строки
- `domain_dialogue.md` — 40 багов DOM-02 (Dialogue/LLM), 457 строк
- `domain_perception.md` — 29 багов DOM-03 (Perception/Combat), 555 строк
- `domain_frontend.md` — 50 багов DOM-07 (Frontend/Persistence), 573 строки

Каждый отчёт содержит file:line, симптом, корневую причину, severity, предлагаемый фикс.

### 8.2. Сопоставление симптомов и корневых причин (детальная карта)

| Симптом | Bug IDs (контрибьюторы) | Главный | Фаза фикса |
|---------|--------------------------|---------|------------|
| **S-1: "Ничего не произошло"** | BUG-CORE-003, BUG-DLG-002, BUG-DLG-003, BUG-DLG-018, BUG-FB-008 | BUG-CORE-003 (если не починить — остальные не помогут) | 0.1, 0.2, 0.3, 0.4 |
| **S-2: Пустой PlayerPerceptionDTO** | BUG-PERC-001, BUG-PERC-008, BUG-CORE-006, BUG-FB-001 | BUG-PERC-001 (DTO type mismatch + override) | 0.6, 0.7, 0.13 |
| **S-3: NPC на exit_west после сна** | BUG-SPATIAL-001, BUG-CORE-004, BUG-SPATIAL-015, BUG-CORE-005, BUG-FB-002 | BUG-SPATIAL-001 (cross-loc materialize теряет target) + BUG-FB-002 (sleep не персистится) | 0.8, 0.9, 0.10, 0.11 |
| **S-4: Угрозы не вызывают реакций** | BUG-PERC-002, BUG-DLG-019, BUG-DLG-004, BUG-DLG-020 | BUG-PERC-002 (`_evt_map` missing keys) | 0.5 |
| **S-5: Dialogue queue спам** | BUG-CORE-010, BUG-DLG-005, BUG-DLG-006, BUG-DLG-009 | BUG-CORE-010 (`execute_pending` drain bug) | 0.12 |

### 8.3. Контрактные нарушения — итоговая сводка

| Контракт | Кол-во нарушений | Главные bug IDs |
|----------|------------------|-----------------|
| L1 (State Mutation Law) | 2 | BUG-CORE-018, BUG-CORE-Purity |
| L2 (Runtime Purity Law) | 4 | BUG-CORE-011, BUG-CORE-012, BUG-PERC-003, BUG-PERC-004 |
| L4 (Silent Failure Prohibition) | 9+ | см. §4 |
| L8 (CFRM & Somatic Gate Law) | 1 | BUG-PERC-025 |
| L9 (Spatial SSOT) | 1 | BUG-SPATIAL-004 |
| L10 (Traversal FSM Law) | 2 | BUG-SPATIAL-005, BUG-SPATIAL-026 |
| L11 (Spatial Coherence Validation SC-1..SC-8) | 8 (фича отсутствует) | (нужно реализовать) |
| L12 (Physiology & Death Lock Law) | 4 | BUG-PERC-005, BUG-PERC-006, BUG-PERC-029, BUG-FB-007 |
| L14 (Epistemic Memory Law) | 1 | BUG-PERC-014 |
| L15 (Frontend Authority Law) | 5 | BUG-FB-012, BUG-FB-013, BUG-FB-014, BUG-FB-041, BUG-FB-045 |
| L16 (Epistemic Boundary Law) | 1 | BUG-DLG-010 |
| L17 (Identity Pipeline Law) | 1 | BUG-PERC-013, BUG-FB-020 |
| L21 (Invariant Defense Law) | 1 | BUG-SPATIAL audit (`movement_engine.py:1244-1247`) |
| CAUSAL_CONTRACT §4.1.10 (Double processing MovementIntent) | 1 (фича отсутствует) | — |
| CAUSAL_CONTRACT §4.7.48 (MockProvider в production) | 1 | BUG-FB-021 |
| CAUSAL_CONTRACT §4.5.33 (campaign_id ≠ location_id) | 1 | BUG-FB-017 |

### 8.4. Карта мёртвого кода (на удаление)

| Файл:строка | Что | Строк |
|-------------|-----|-------|
| `tick_orchestrator.py:460-594` | Unreachable legacy single-loc body | 135 |
| `life_engine.py:632-1132` | `tick_decisions` (дубликат NpcTickPipeline.run) | ~500 |
| `life_engine.py:683-694` | Дублирующий мёртвый блок | 12 |
| `combat_math.py:300-340` | `apply_damage` + `apply_healing` (acknowledged dead code) | 40 |
| `combat_service.py:1-117` | Параллельная legacy D&D система | 117 |
| `scene_state_manager.py:1853-1883` | `update_npc_position` (bypasses TraversalState) | 30 |
| `movement_engine.py:71-118` | `_spatial_intent_gate` (duplicate no-op filter) | 47 |
| `integration.py:472-518` | `ManifestationPhysicsEngine` trace loop (overridden by Pipeline B) | 46 |
| `perceptual_attention_service.py` (entire file) | Never wired | ~200 |
| `world_sim_agent.py:135-149` | `tick()` useless LLM call | 14 |
| `task_scheduler.py:71-90` | `process_tasks` dead method | 19 |
| `intent_event_adapter.py:38-46` | Non-attack branches dead | 8 |
| `routes_debug.py:23-32, 99` | Mock dashboard + dead route | 35 |
| `api_client.py:497-503` | Diagnostic after return | 6 |
| **ИТОГО к удалению:** | | **~1210 строк** |

### 8.5. Рекомендуемый порядок применения фиксов

> Принцип: **сначала мосты (bridges), потом компоненты**. Сломанный мост делает любую починку компонента бесполезной.

1. **Bridges (мосты):** BUG-CORE-003 (`dm_ctx`-мост), BUG-CORE-001 (восстановление post-return кода), BUG-PERC-001 (perception DTO conversion), BUG-SPATIAL-005+026 (FSM wiring).
2. **Data sources:** BUG-SPATIAL-004 (`player_spatial`), BUG-DLG-003 (`all_npcs_raw_snapshot`), BUG-PERC-009 (`all_npcs_raw` vs `npc_positions`).
3. **Critical path:** BUG-CORE-004 (LifeEngine `__init__`), BUG-CORE-005 (movement_intents else-branch), BUG-SPATIAL-001 (cross-loc materialize), BUG-FB-002 (skip_time persistence), BUG-FB-010+011 (SQLite keys).
4. **Events:** BUG-PERC-002 (`_evt_map`), BUG-DLG-019 (threats routing), BUG-DLG-020 (subscriber not subscribed).
5. **Drainage:** BUG-CORE-010 (`execute_pending`), BUG-DLG-005, BUG-DLG-006.
6. **Combat/HP:** BUG-PERC-005, BUG-PERC-006, BUG-PERC-003, BUG-PERC-004, BUG-PERC-029, BUG-FB-007.
7. **Wall clock:** BUG-FB-012, BUG-FB-013, BUG-FB-014, BUG-DLG-006.
8. **Cleanup:** все Medium/Low.

---

## 9. ЗАКЛЮЧЕНИЕ

Кодовая база ENIGMA V.0.5.3.6.7 — это **технически сложный, архитектурно продуманный проект**, который находится в переходном состоянии между S98 и S145. Из 167 найденных дефектов:

- **21 Critical** делают игру нефункциональной для игрока (5 видимых симптомов).
- **41 High** нарушают архитектурные контракты и создают скрытые риски.
- **51 Medium** снижают качество симуляции.
- **54 Low** — code hygiene, мёртвый код, cosmetic.

**Главный диагноз:** проект пострадал от **«миграций наполовину»** — 5 крупных архитектурных переходов было начато, но не завершено. Вокруг каждого незавершённого моста накопились workaround'ы (silent `try/except: pass`, dead code, dual pipelines).

**Хорошая новость:** ядро онтологии (CAUSAL_CONTRACT, ADR) — **здоровое**. Контракты правильно описаны, просто не везде реализованы. Фикс не требует переписывания архитектуры — только **достроить мосты и убрать workaround'ы**.

**Рекомендуемая последовательность:**
1. ФАЗА 0 (4-6 часов) — стабилизация, играбельность.
2. ФАЗА 1 (8-12 часов) — архитектурная реставрация.
3. ФАЗА 2 (6-8 часов) — очистка.
4. ФАЗА 3 (4-6 часов) — тесты и валидация.

**Итого: 22-32 часа чистой работы** (без учёта тестирования и отладки). После завершения всех 4 фаз система должна соответствовать CAUSAL_CONTRACT v2.0 на 100%, проходить IPT 6/6, и обеспечивать честную симуляцию, задуманную в ADR.

---

*Документ подготовлен на основе статического анализа исходного кода Enigma-V.0.5.3.6.7, чтения логов `causal_validation.log`, `sleep_test2.log`, `cds_session_*.log`, и сверки с `00_CAUSAL_CONTRACT_v2.0.md`, `ADR (Architecture Decision Records).md`, `MUTATIONS.md`. Все file:line references точны на момент анализа.*
