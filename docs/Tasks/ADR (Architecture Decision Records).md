# ENIGMA ADR MASTER INDEX (LLM-Readable)
&gt; Формат: `ADR-XXX` [TYPE] **Title** — Essence (1 line)
&gt; Type: STD=Standard | ONTO=Ontology (ADR-O) | FIX=Verified Bugfix
&gt; Status: VERIFIED | PROPOSED | DEPRECATED | DEAD
&gt; Taboo: ❌ = Architectural prohibition (hard rule)

---

## LEGEND
| Tag | Meaning |
|-----|---------|
| [STD] | Standard architectural decision |
| [ONTO] | Ontology shift (fundamental paradigm change) |
| [FIX] | Verified runtime bugfix (audit session S50-S72) |
| [DEP] | Deprecated / dead concept |
| `→` | Primary downstream consumer |
| `⚡` | Verified in runtime audit |
| `💀` | Killed concept (do not resurrect) |

---

## DOM-01: FOUNDATION (Core Pipeline, Time, State, Spatial Core)

`ADR-001` [STD] **Delta Buffer** — Единственный путь мутации: Phase8Result → delta_buffer → StateApplicator.apply_batch()
  Taboo: ❌ Прямая мутация `all_npcs_raw` в обход DeltaBuffer
  Files: delta_buffer.py, state_applicator.py

`ADR-002` [STD] **Time-driven vs Event-driven** — Фаза 0.5 (time-decay) выполняется всегда; Фаза 8 (event-driven) только при событиях
  Files: tick_orchestrator.py

`ADR-013` [STD] **StateDeltas v2** — Плоский god-object заменён на `DeltaDomain` + типизированные frozen Payloads. Одна дельта = один домен
  Files: npc_state.py, delta_buffer.py

`ADR-047` [ONTO] **No Retro-simulation** — Убит `TICK_CATCHUP`. Пропущенное время аналитически вычисляется через `reconcile_state(elapsed_seconds)`
  Taboo: ❌ Циклы `tick()` для нагона времени
  Files: life_engine.py, scene_init.py

`ADR-059` [STD] **Dual-Time Ontology** — Транзиты привязаны к монотонному `scene_state["tick"]`, не к реальному времени. `_preserved_tick` при загрузке
  Files: tick_orchestrator.py, scene_state_manager.py

`ADR-065` [FIX] **Spatial Authority Consolidation** — Убита трёхкратная ручная сборка `SpatialService.build_for_location()` в TickOrchestrator
  Files: tick_orchestrator.py

`ADR-066` [FIX] **Single Movement Ownership** — Убит двойной вызов `process_intents()`. Единственный владелец — `TickOrchestrator`. Invariant: `processed=True` → RuntimeError
  Taboo: ❌ Вызов `process_intents()` из `npc_orchestration.py`
  Files: tick_orchestrator.py, npc_orchestration.py

`ADR-089` [FIX] **Campaign ID Integrity** — Убита подмена `campaign_id` на `location_id` в `execute_player_finalize`. `campaign_id` из аргумента функции
  Taboo: ❌ Подмена `campaign_id` на `location_id` в `_TickContext`
  Files: tick_orchestrator.py

`ADR-102` [FIX] **SpatialService replaces load_graph() + FLEE Fix** — `load_graph()` мёртв (возвращал 0 узлов). `SpatialService.build_for_location()` — единственный источник. FLEE: `get_furthest()` с `exclude_node_ids` + нормализация legacy ID
  Taboo: ❌ `load_graph()` — мёртвый код. ❌ Сравнение legacy/canonical ID без `normalize_id()`
  Files: spatial_runtime.py, spatial_service.py, npc_tick_pipeline.py
  Impact: ADR-102_IMPACT.md

`ADR-128` [FIX] **Persistence Read-Back** — Убит разрыв write-path / read-path. LifeEngine `_load_npcs()` при cache miss читает SQLite → fallback static. `is not None` семантика для `load_npc_runtime()`
  Taboo: ❌ `_load_npcs()` без SQLite read-back. ❌ `load_npc_runtime()` возвращает `[]` вместо `None`
  Files: life_engine.py, persistence_port.py
  Impact: ADR-128 (встроен в основной ADR)

`ADR-129` [FIX] **SpatialQueryService Argument Shift + SceneState Contract + CEI-2** — Три бага: (1) неверный порядок аргументов в `is_line_of_sight_clear`, (2) отсутствие `normalize_scene_state()` firewall, (3) CEI-2 использовал `is_movement_blocked` вместо `is_blocked_by_wall` для макро-навигации
  Taboo: ❌ `visibility()` с неправильным порядком аргументов. ❌ CEI-2 использует `is_movement_blocked` для макро-навигации
  Files: spatial_runtime.py, scene_state_manager.py

`ADR-134` [FIX] **DRF Split-Brain (Instance-Level Bus)** — `execute()` и `execute_player_finalize()` создавали независимые `_TickContext` с отдельными `DRFBus()` через `default_factory`. Claims писались в BUS_A, drain читал из BUS_B → `[DRF_FIELD] claim_field is EMPTY`. Фикс: DRFBus перенесён на уровень экземпляра оркестратора (`self._drf_bus = DRFBus()` в `__init__`). Оба метода передают `drf_bus=self._drf_bus`. Добавлен `_drf_bus.stream.clear()` на начало `execute()`. Idle `_phase_10_persistence` получил drain (ранее отсутствовал).
  Taboo: ❌ `DRFBus` через `default_factory=DRFBus` в `_TickContext` — split-brain при двух контекстах. ❌ Monkey-patch функции для инъекции шины (`func.drf_bus = ...`). ❌ `_phase_10_persistence` без DRF drain — idle claims теряются
  Files: tick_orchestrator.py
  Impact: ADR-134_IMPACT.md

`ADR-136` [STD] **DRFExecutionContext (Scoped Causal Ledger)** — Pipeline получает `drf_ctx: DRFExecutionContext` (dataclass с `tick_id`, `npc_id`, `bus`), а не голый `drf_bus`. Claim автоматически наследует `npc_id` и `tick_id` через `drf_ctx.emit()`. Убран monkey-patch `run_npc_pipeline.drf_bus = ctx.drf_bus`. Внутри NPC loop создаётся scoped контекст через `drf_ctx.for_npc(npc_id)`.
  Taboo: ❌ Передача голого `drf_bus` в pipeline вместо `drf_ctx`. ❌ Ручное заполнение `target_npc` в claim при наличии scoped context
  Files: tick_orchestrator.py, npc_tick_pipeline.py

`ADR-O-137` [ONTO] **Viability Pre-Generation Gate (ДОЛГ 4.3)** — Сдвиг парадигмы: от пост-генерационного скоринга к pre-генерационному сжатию пространства действий. `IntentDomain` enum (SURVIVAL/SOCIAL/ROUTINE/EXPLORATION) + `_compute_viability_mask()` проекция PerceptualKernel → допустимые домены. SURVIVAL давление (threat_gradient > 0.3) исключает ROUTINE из генерации ДО создания intent. NPC физически не может «выбрать» работу при беге. Viability — не предпочтение (priority), а физика возможностей. Gate стоит ДО вызовов `update_routine()`, `_check_need_driven_movement()`, `check_random_events()` — генераторы не вызываются для нежизнеспособных доменов (устраняет «зомби-каузальность»).
  Taboo: ❌ Viability veto через `_drf_killed` флаг или `priority=0` — скрытый скоринг вместо viability. ❌ Viability veto через парсинг строк (`"schedule" in reason`) — ломается при смене имён. ❌ Пост-генерационная фильтрация кандидатов вместо pre-generation gate — ROUTINE уже мутирует state до фильтрации. ❌ `MovementIntent` без поля `domain` — онтологическая неполнота
  Files: life_engine.py, domain/movement.py, npc_tick_pipeline.py

---

## DOM-02: WILL, PRESSURE & DECISION

`ADR-031` [ONTO] **Cumulative Strain Model** — Убита матрица `action × temperament`. `IntentPressureResolver` → `IntentPressureProfile`. Шкала COMPLY → CONDITIONED
  Files: will.py, affect.py
  Impact: ADR-031_IMPACT.md

`ADR-034` [STD] **Phase 1 Boundary Adapter** — Бизнес-логика воли изгнана из `game_loop`. Фаза 1 — чистая функция `resolve_player_intent()`
  Files: game_loop.py, phase_1_input.py

`ADR-035` [FIX] **Semantic Black Hole** — `semantic_action` пробрасывается напрямую, без `None` fallback. Убит тернарный оператор
  Files: phase_1_input.py
  Impact: ADR-035_IMPACT.md

`ADR-036` [STD] **Single Will Evaluation** — Убит Double Invocation. WillpowerGate вызывается строго 1 раз за цикл
  Taboo: ❌ Вызов WillpowerGate более 1 раза за цикл
  Files: will.py, tick_orchestrator.py

`ADR-037` [STD] **Affect Resonance** — Аффект — не бафф, а искажение интерпретации (Resonance → Distortion → `AmplifiedPressureProfile`)
  Files: affect.py

`ADR-046` [STD] **Inverted Fear** — Убит хардкод `base += 0.6`. Страх перед авторитетом бустит `Intent.APPROACH`, а не подавляет
  Files: decision_hub.py

`ADR-050` [ONTO] **DecisionContext & Feasibility** — DecisionHub разделён на Фазу 1 (Feasibility Filtering) и Фазу 2 (Utility Deformation)
  Files: decision_hub.py
  Impact: ADR-050_IMPACT.md

`ADR-056` [STD] **Attention Capture** — Хардкод-порог `initiative_suppression &gt; 0.7` заменён на `recent_directive` с механизмом сжигания директивы
  Files: perceptual_kernel.py, life_engine.py
  Impact: ADR-056_IMPACT.md

`ADR-057` [ONTO] **Legitimacy Gate** — Нет страха/доверия = Irritation (снятие блоков агрессии) вместо Obedience. `GAME_TICK_INTERVAL_SECONDS`: 900 → 60
  Files: directive_interpretation_subscriber.py, decision_hub.py
  Impact: ADR-057_IMPACT.md

`ADR-064` [FIX] **Directive Data Continuity** — Убит Баг #6 (Глухая Воля). `DirectiveInterpretationSubscriber` получает `all_npcs_raw` через fallback на `DMContextDTO`
  Files: tick_orchestrator.py, directive_interpretation_subscriber.py
  Impact: ADR-064_IMPACT.md

`ADR-067` [STD] **Player Command Override** — Приказ игрока перекрывает ЛЮБОЕ решение DecisionHub, включая `flee`. Убран guard `if decision.intent.value not in ("approach", "flee")`
  Files: tick_orchestrator.py, npc_tick_pipeline.py

`ADR-068` [FIX] **Partial Name Matching** — NPC с составными именами отзываются на часть имени (≥3 символа). Рефлекс проверяет отдельные слова
  Files: npc_tick_pipeline.py

`ADR-088` [FIX] **Fast Path Emotional Injection** — Убит мёртвый `EmotionalVector` в Fast Path. `IntentCompressor` маппит `ActionType` → эмоции (ATTACK → aggression=0.8)
  Taboo: ❌ Дефолтный `EmotionalVector` (aggression=0.0) для ATTACK
  Files: intent_compressor.py, will.py

`ADR-O-139` [ONTO] **NPC Physical Integrity Contract (NPIC) & Somatic Gating** — Тело — это gate of perception, а не модификатор. Отсутствие `body_state` ≠ нейтральное состояние (§ENIGMA-003), а = `BODY_STATE_DISABLED` (инертная материя). Каузальный порядок инвертирован: `Body → Somatic Gate → Semantic Parsing → Legitimacy → Action`. Убит fallback без тела (создавал логических призраков).
  Taboo: ❌ Fallback NPC dict без `body_state`. ❌ Проверка `shock` ПОСЛЕ семантического парсинга директивы. ❌ `if not body_state: pass` без инъекции `BODY_STATE_DISABLED`.
  Files: directive_interpretation_subscriber.py, tick_orchestrator.py, pressure_translator.py, npc_state.py

`ADR-O-140` [ONTO] **World Partition Topology** — Локация = чанк сериализации, не мир сама по себе. Мир непрерывен. `location_id` = инфраструктура загрузки, не онтология NPC. `adjacency` — связи между чанками для сшивки навигационных графов. `door_transition` остаётся только для магических порталов/лестниц. `player_spawn` — только стартовая точка мира. Переход = Causal Synchronization Point (глубокий просчёт симуляции чанка перед показом).
  Taboo: ❌ `location_id` как часть онтологии NPC (должен быть вычислимым). ❌ `player_spawn` на каждой карте (только стартовая точка мира). ❌ `door_transition.target_file` для обычного перемещения (только для магических порталов/лестниц).
  Files: graph_compiler.py, scene_state_manager.py, spatial_service.py

`ADR-135` [STD] **Causal Scoring Overlay (ДОЛГ 4.2)** — DRF претензии влияют на приоритет интентов через аддитивный скоринг: `priority += energy × weight × alignment`. Веса: SURVIVAL=0.15, SOCIAL=0.10, ROUTINE=0.02. Alignment: vector∈reason → 1.0, иначе 0.3. Убит сломанный clamp `max(priority, 90/70)` (масштабная ошибка при шкале 0.0–1.0). Overlay унифицирован для idle и player путей через `_apply_drf_scoring_overlay()`. Viability veto ОСОЗНАННО НЕ реализован в MovementEngine — конфликт мотиваций решается ДО генерации интента (ДОЛГ 4.3).
  Taboo: ❌ Clamp override `max(priority, N)` при шкале 0.0–1.0 — уничтожение шкалы. ❌ DRF overlay только в idle path — player path обходит арбитраж. ❌ Viability veto через `_drf_killed` флаг или `priority=0` в MovementEngine — скрытый скоринг вместо viability. ❌ Viability veto через парсинг строк (`"schedule" in reason`) — ломается при смене имён
  Files: tick_orchestrator.py, movement_engine.py

`ADR-O-139` [ONTO] **NPC Physical Integrity Contract (NPIC) & Somatic Gating** — Тело = gate of perception, не модификатор. Отсутствие `body_state` ≠ нейтральное состояние (§ENIGMA-003), а = `BODY_STATE_DISABLED` (инертная материя). Каузальный порядок инвертирован: Body → Somatic Gate → Semantic Parsing → Legitimacy → Action. Убит fallback без тела (логические призраки).
  Taboo: ❌ Fallback NPC dict без `body_state`. ❌ Проверка shock/pain ПОСЛЕ семантического парсинга. ❌ `if not body_state: skip` без инъекции `BODY_STATE_DISABLED`
  Files: directive_interpretation_subscriber.py, tick_orchestrator.py, pressure_translator.py, npc_state.py

---

## DOM-03: PERCEPTION & PHENOMENOLOGY (CFRM)

`ADR-025` [ONTO] **CFRM Core** — Глобального World нет. `ClusterGraph`, `EventBuffer`, `MembraneField`. NPC хранит `PerceptualKernel`
  Files: local_causal_solver.py, perceptual_kernel.py

`ADR-029` [STD] **CFRM Layer 1** — Spatial Index для O(1) поиска. Классификация по осям: PHYSICAL, COGNITIVE, SOCIAL
  Files: local_causal_solver.py

`ADR-033` [ONTO] **Deobjectification P2** — Смерть объективных событий. `EventDTO` → `FieldDisturbance`. Восприятие вычисляется локально `LocalCausalSolver`
  Taboo: ❌ Хранение `EventDTO` в `EventBuffer` (только `FieldDisturbance`)
  Files: local_causal_solver.py, event_buffer.py

`ADR-040` [STD] **Epistemic Classification** — `ClassificationResult` с `confidence`. Fallback-события имеют вес 0.2
  Files: local_causal_solver.py

`ADR-042` [FIX] **Perception Domain** — Реальность течёт в `PerceptionPayload`, а не напрямую в эмоции. Guard против wipe `all_npcs_raw`
  Files: npc_tick_pipeline.py, tick_orchestrator.py
  Impact: ADR-042_IMPACT.md

`ADR-115` [FIX] **DOUBLE TRUTH perceptual_kernel** — `write_to_legacy()` / `from_legacy()` не сериализовали `perceptual_kernel` + `affective_load` → сброс в 0.0 каждый тик
  Taboo: ❌ `write_to_legacy` / `from_legacy` без `perceptual_kernel` и `affective_load`
  Files: npc_state.py
  Impact: ADR-115_IMPACT.md

---

## DOM-04: SPATIAL & LOCOMOTION

`ADR-008` [STD] **Spatial Centralization** — Убит глобальный `_connections_data` и кэш `_graphs`. Единственный источник — `SpatialService`
  Files: spatial_service.py

`ADR-010` [STD] **Macro/Micro Zones** — Архетипы переведены на макро-зоны. Убита парализация из-за микро-зон
  Files: spatial_service.py

`ADR-019` [STD] **Traversal State** — Диагноз телепортации. `TraversalState` как презентационный артефакт
  Files: movement_engine.py

`ADR-048` [STD] **Single Spatial Authority** — Чтение `scene_state["player_distances"]` запрещено. Внедрён `SpatialQueryService`
  Taboo: ❌ Чтение позиций из `scene_state` (только `SpatialQueryService`)
  Files: spatial_query_service.py, npc_orchestration.py

`ADR-051` [ONTO] **LifeEngine De-godification** — LifeEngine лишён права прямой мутации позиции. Только лоббирование намерений
  Files: life_engine.py, tick_orchestrator.py
  Impact: ADR-051_IMPACT.md

`ADR-052` [FIX] **LOD0/LOD1 Split** — Нормализация префиксов. Устранение Silent Data Loss с интентами. `local_target_xy` при совпадении зон
  Files: npc_tick_pipeline.py, movement_engine.py
  Impact: ADR-052_IMPACT.md

`ADR-053` [FIX] **LifeEngine Intent Pipeline Restoration** — Устранение Silent Pipeline Corruption: намерения больше не теряются на границе LifeEngine → TickOrchestrator
  Files: life_engine.py, tick_orchestrator.py
  Impact: ADR-053_IMPACT.md

`ADR-060` [ONTO] **Movement Ontology Split** — `MovementIntent` объединяет LOD0 и LOD1. `LocalSteeringIntent` отвергнут
  Files: movement_engine.py, npc_tick_pipeline.py

`ADR-061` [STD] **Player Position Authority** — `npc_positions.player` — единственный источник. `player_spatial` — только fallback
  Files: scene_state_manager.py, tick_orchestrator.py

`ADR-069` [FIX] **target_local_xy Propagation** — При `reactive:approach` координаты цели пробрасываются через `MacroMovementGoal` → `SceneChange` → `scene_state_manager`
  Files: npc_tick_pipeline.py, scene_state_manager.py

`ADR-070` [FIX] **Ghost Position Interpolation** — При создании нового транзита `from_xy` интерполируется по прогрессу старого транзита. Устраняет телепортацию назад
  Files: movement_engine.py

`ADR-071` [FIX] **Bridge Traversal Propagation** — `game_loop_bridge.py` пробрасывает `active_traversals` в `world_snapshot` для фронтендной интерполяции
  Files: game_loop_bridge.py

`ADR-072` [FIX] **Enrichment LOD0 Guard** — `_enrich_local_positions` не перетирает `local_position` для сдвинувшихся NPC
  Taboo: ❌ `_enrich_local_positions` перетирает `local_position`, установленный пайплайном
  Files: scene_state_manager.py

`ADR-073` [STD] **Adjacency Inference** — Алгоритм вывода связей из смежности полигонов в `graph_compiler.py`. Двери фильтруют проходимость, но не определяют топологию
  Files: graph_compiler.py
  Impact: ADR-073_IMPACT.md

`ADR-095` [FIX] **Centroid Graph Compilation** — `graph_compiler.py` вычисляет центр комнаты вместо левого верхнего угла. Устраняет телепортацию в углы стен
  Taboo: ❌ Левый верхний угол как позиция узла в навигационном графе
  Files: graph_compiler.py

`ADR-096` [FIX] **Frontend Traversal Respect** — Если NPC в статусе `MOVING`, фронтенд не перезаписывает `local_position` из `npc_positions`
  Taboo: ❌ Перезапись `local_position` для NPC в статусе `MOVING`
  Files: game_loop_bridge.py, scene_renderer.py

`ADR-114` [FIX] **Spatial Paralysis Fix (Role-Based Aliases)** — `graph_compiler.py` строил `alias_map` только из `room_id`. Добавлены name-aliases и role-based legacy aliases (`ENTRANCE→entrance`, `BAR→bar_area`)
  Taboo: ❌ `graph_compiler.py` без role-based aliases — legacy-имена не резолвятся
  Files: graph_compiler.py

`ADR-116` [FIX] **FLEE Intent Lost (PRIORITY_NEEDS NameError)** — `_resolve_reactive_movement()` использовал `PRIORITY_NEEDS` из локальной области другой функции → `NameError` → FLEE терялся
  Taboo: ❌ Использование переменных из локальной области другой функции
  Files: npc_tick_pipeline.py
  Impact: ADR-116_IMPACT.md

`ADR-119` [FIX] **Narrative Movement Prohibition (Инвариант 2)** — LLM не может описывать движение NPC без подтверждения `MovementEngine`. `VerbalizationContext` обогащён `is_moving`
  Taboo: ❌ LLM описывает движение NPC без подтверждения от MovementEngine
  Files: npc_tick_pipeline.py, dm_agent.py

`ADR-130` [FIX] **Movement Lock & Target Resolution** — `update_routine()` traversal-aware: не мутирует routine при активном транзите. `DecisionHub._context_relevance` fallback на `payload.target_id`
  Files: life_engine.py, decision_hub.py
  Impact: ADR-130_IMPACT.md

---

## DOM-05: PHYSIOLOGY & COMBAT

`ADR-015` [ONTO] **Physiology Domain** — Убиты RPG Hit Roll и AC. `body_profile`, `InjuryDTO`, `ImpactEngine` (Pure Function)
  Taboo: ❌ RPG-абстракции (Hit Roll, AC). ❌ Прямая мутация HP в обход `ImpactEngine`
  Files: impact_engine.py, combat_math.py

`ADR-020` [STD] **DRSL** — `ReductionPolicy`. Тело не складывается (`ADDITIVE`), оно эволюционирует (`PHYSICS_COMPOSITE`)
  Files: reduction_policy.py

`ADR-021` [STD] **CombatSubscriber** — Мост `EventDTO → ImpactEngine`. Возвращает ТОЛЬКО Physiology-дельты
  Taboo: ❌ `CombatSubscriber` пишет в Emotion (Domain Leakage)
  Files: combat_subscriber.py

`ADR-022` [STD] **Leaky Integrator** — Физиология затухает по экспоненте `S_t = S_{t-1} * exp(-lambda * dt)`
  Files: physiology_decay_handler.py

`ADR-027` [STD] **Layered Reduction** — Каскад: Physical → Materialization → Cognitive → Social
  Files: reduction_policy.py

`ADR-028` [STD] **Config Migration** — `combat_stats` удалены из JSON
  Files: npc_config.py

`ADR-084` [FIX] **NameError blood_loss_delta** — `state_applicator.py` использовал переменную без извлечения из `PhysiologyPayload`
  Files: state_applicator.py

`ADR-099` [FIX] **Silent Loss Physiology (asdict)** — `asdict` не импортирован на уровне модуля → `NameError` → вся `PhysiologyPayload` пропускалась
  Files: state_applicator.py

`ADR-100` [FIX] **Serialization Black Hole (body_state)** — `write_to_legacy()` / `from_legacy()` не сериализовали `body_state` → физиология терялась каждый тик
  Taboo: ❌ `write_to_legacy` / `from_legacy` без `body_state`
  Files: npc_state.py

`ADR-101` [FIX] **Rule X Violation (BehaviorManifestation)** — `BehaviorManifestationService` читал только `stress_delta`, игнорируя `body_state` (pain/blood_loss/shock)
  Taboo: ❌ `BehaviorManifestationService` читает эмоции вместо физиологии (Rule X)
  Files: behavior_manifestation_service.py

`ADR-102` [FIX] **shock_impulse Not Applied** — `StateApplicator` извлекал `shock_impulse`, но не применял к `body_state`
  Files: state_applicator.py

`ADR-103` [FIX] **NPC ID Fallback (apply_batch)** — `StateApplicator.apply_batch()` искал только по `"id"`, но NPC dict использует `"npc_id"`
  Files: state_applicator.py

`ADR-104` [FIX] **Idle Tick Perception Blindness** — `_phase_9_integration()` вызывал `produce_traces()` без `all_npcs_raw` → `body_state=None` в idle тиках
  Files: tick_orchestrator.py

`ADR-105` [FIX] **Semantic Action Lost in Transit** — `publish_classified_player_event` вызывался ДО `resolve_player_intent()` → `_semantic_action=None`
  Files: dm_phase.py, __init__.py

`ADR-106` [FIX] **UnboundLocalError _legacy_d** — `_legacy_d` определена внутри первого `elif`, читалась во втором → память мертва для 6/6 NPC
  Files: npc_tick_pipeline.py

`ADR-107` [FIX] **VerbalizationContext TypeError** — `intent_target: Optional[str]` без `= None`. `physical_state` дефолт заменён на `"unharmed"`
  Files: npc_tick_pipeline.py

`ADR-108` [FIX] **UrgencyLevel Duplicates EmotionTag** — `StateInterpreter._stress_to_word()` дублирует `EmotionTag`. `NPCStateDescription.emotional_state` — мёртвое поле
  Files: state_interpreter.py

`ADR-109` [FIX] **Shock Immortality** — `shock_impulse` не затухал между тиками. 4 причины: отсутствие в snapshot, в decay handler, блокировка отрицательных дельт
  Taboo: ❌ `shock_impulse` без decay. ❌ `StateApplicator` проверяет `&gt; 0.0` вместо `!= 0.0`
  Files: physiology_decay_handler.py, state_applicator.py, npc_state_snapshot.py

`ADR-110` [FIX] **CombatSubscriber NPCStateSnapshot без shock_impulse** — `_build_snapshot()` не передавал `shock_impulse` → `ImpactEngine` видел 0.0
  Files: combat_subscriber.py

`ADR-111` [FIX] **Print-диагностика в production** — 13 `print()` конвертированы в `logger.debug()`. Safeguard print'ы оставлены
  Files: combat_subscriber.py, tick_orchestrator.py, state_applicator.py

`ADR-112` [FIX] **Semantic Inflation Fix (Rule X Enforcement)** — `BehaviorManifestationService` и `PhenomenologyProjectionService` читали `stress_delta`/`psyche_state`. Переведены на `body_state` ONLY
  Taboo: ❌ Чтение `stress_delta`/`psyche_state` для моторных искажений и атмосферы
  Files: behavior_manifestation_service.py, phenomenology_projection_service.py

`ADR-123` [ONTO] **Vital State Evaluator & Injury-Physiology Bridge** — Смерть = процесс, не событие. `evaluate_vital_state()` (ALIVE/DEAD), `InjuryProcessor` ( bleeding_rate = structural_damage * zone_rate )
  Taboo: ❌ `hp &lt;= 0` как источник смерти. ❌ Строковые флаги `critical_effects`
  Files: vital_state.py, injury_processor.py, state_applicator.py, decision_hub.py

`ADR-127` [FIX] **Death Lock — Онтологическая Необратимость Смерти** — Трёхслойный инвариант: (1) `evaluate_vital_state` возвращает DEAD немедленно, (2) `NPCStateSnapshot.life_status`, (3) `PhysiologyDecayHandler` пропускает мёртвых
  Taboo: ❌ `if state.body_state:` (falsy dict) → `is not None`. ❌ Decay для мёртвых NPC. ❌ Переход DEAD→ALIVE через обычную физиологию
  Files: vital_state.py, physiology_decay_handler.py, npc_state.py

`ADR-131` [ONTO] **Action Eligibility Gate (Player Death Guard)** — Игрок с `life_status="DEAD"` не может действовать. Guard в `run_turn` ДО `lock_for_tick` возвращает `ChatTurnResponse` (GameOver)
  Taboo: ❌ Обработка player action без проверки `life_status`
  Files: game_loop/__init__.py

`ADR-132` [ONTO] **Player Combat EntityView Shift** — Игрок — симулируемая физическая сущность в бою. `_make_player_snapshot()` читает живой `body_state` из `all_npcs_raw`, а не возвращает захардкодированного бессмертного (hp=100, pain=0)
  Taboo: ❌ `_make_player_snapshot()` без чтения `avatar_state.body_state`
  Files: combat_subscriber.py

`ADR-137` [FIX] **Death Feedback Pipeline (life_status → UI)** — `AvatarStateDTO.life_status` пробрасывает смерть до фронтенда. `PhysicalPresentationState.DEAD` enum. Assembler DEAD override (перекрывает ВСЕ проекции). Frontend Death Overlay. Death Guard v2: npc_positions в snapshot — мир продолжает жить после смерти игрока
  Taboo: ❌ `AvatarStateDTO` без поля `life_status`. ❌ Death Guard без npc_positions в world_snapshot (мир замерзает)
  Files: snapshot.py, avatar_presentation_assembler.py, game_screen.py, game_loop/__init__.py

`ADR-140` [FIX] **DM Death Scene Pipeline** — DM получает life_status из player_state через avatar_to_prompt и генерирует death scene narration. DM НЕ вычисляет смерть — только читает замороженный факт S74-S75. Death Guard вызывает DM вместо хардкод-строки (с fallback при Exception)
  Taboo: ❌ DM narration без проверки player life_status. ❌ `avatar_to_prompt` без life_status. ❌ Death Guard без вызова DM (подмена нарратива хардкодом)
  Files: dm_agent.py, phase_6_avatar.py, game_loop/__init__.py
  Impact: ADR-140_IMPACT.md

`ADR-141` [STD] **Injury Chronic Pain Bridge** — Убит разрыв Injury → Pain. InjuryProcessor генерирует `pain_delta` из свойств раны (`structural_damage * zone_modifier * type_modifier`), компенсируя экспоненциальное затухание `PhysiologyDecayHandler`. Замыкает трубу `Injury → Pain → EmbodiedTrace → DM narration`.
  Taboo: ❌ `InjuryProcessor` генерирует `blood_loss` без `pain_delta`. ❌ Хардкод хронической боли без учёта зоны и типа раны
  Files: injury_processor.py

---

## DOM-06: SOCIAL & MEMORY

`ADR-005/006` [STD] **NPC Social Mapping** — Маппинг `social_stats` в `relationship_cache`. Обогащение из `village_relations.json`
  Files: npc_loader.py

`ADR-007` [STD] **Idle Sync** — Синхронизация `all_npcs_raw` в idle-пути
  Files: game_loop.py

`ADR-043` [ONTO] **Social Physics** — Приказ генерирует `directive_obedience` (давление), а не `MovementIntent`
  Taboo: ❌ `DirectiveInterpretationSubscriber` генерирует `MovementIntent`
  Files: directive_interpretation_subscriber.py
  Impact: ADR-043_IMPACT.md

`ADR-080` [FIX] **Player-Only Social Physics** — `DirectiveInterpretationSubscriber` вычисляет легитимность по `source_id`. NPC-to-NPC власть жива
  Files: directive_interpretation_subscriber.py

`ADR-121` [FIX] **RelationshipStore SSOT / DOUBLE TRUTH Elimination** — `relationship_cache` существовал в двух форматах (плоский 0-1 vs вложенный 0-100). `RelationshipStore` — единственный SSOT (масштаб 0-100)
  Taboo: ❌ Персистенция `relationship_cache` внутри `NPCState`. ❌ Плоский формат `{"fear": 0.5}`
  Files: npc_state.py, relationship_store.py, decision_hub.py

`ADR-122` [FIX] **Affective Load Target Derivation** — Целевая нагрузка (`target_load`) вычисляется как `Σ(active_causes + pain + shock)`. Фактический `affective_load` — персистентный интеграл (L0), релаксирующий к цели с гистерезисом (ADR-138). `PerceptualKernel` получил idle-decay (Rule 38)
  Taboo: ❌ `affective_load` как независимый аккумулятор. ❌ `threat_gradient` без decay
  Files: state_applicator.py, physiology_decay_handler.py

`ADR-124` [FIX] **Combat → Perception Bridge** — `ReactionSubscriber` генерирует `PerceptionPayload(threat_gradient_delta)` для свидетелей насилия. Шок → `min(0.5, shock * 2.0)`
  Files: reaction_subscriber.py, state_applicator.py

`ADR-125` [STD] **Target Resolution SSOT** — `IntentParametersDTO.target_id` депрекирован. `tick_orchestrator` читает из `intent.target`. ADR-124 сохранён как несущий кабель
  Files: tick_orchestrator.py, dm_phase.py

`ADR-126` [FIX] **Relationship Cache Ontology Merge & Observer Collapse Fix** — Сборка `relationship_cache` расширена до Partial Social Graph (все `nearby_npcs`). `_get_rel_value` с политикой Graph &gt; Scalar &gt; Vacuum
  Files: npc_tick_pipeline.py, decision_hub.py

---

## DOM-07: FRONTEND, PRESENTATION & INPUT

`ADR-011/014` [STD] **Narrative Beats** — Убран плоский чат. Пузыри, спикеры, фильтрация эха
  Files: game_screen.py, narrative_renderer.py

`ADR-035` [ONTO] **Intent Compression** — Русская морфология (pymorphy3 Fast Path + LLM Slow Path). Галлюцинации отсекаются Pydantic
  Files: intent_compressor.py
  Impact: ADR-035_IMPACT.md

`ADR-038` [STD] **Embodied Perception DTO** — Бэкенд присылает скаляры давления и моторные импульсы, не RPG-статы
  Files: api_schema.py

`ADR-039` [STD] **Resistance Medium** — Конфликт воли = инфекция поля ввода (`text_input.infect()`). S-curve инерция
  Files: text_input.py, game_screen.py

`ADR-041` [STD] **Will Conflict Data** — Проброс конфликта воли через API
  Files: routes.py, tick_orchestrator.py

`ADR-068` [FIX] **Avatar Flesh Injection & API Suturing** — Труба Эмбодимента оборвана на 3 уровнях: бэкенд без `body_state`/`psyche`, API выбрасывал `will_conflict_data`, фронтенд не извлекал
  Files: avatar_service.py, routes.py, game_screen.py

`ADR-086` [FIX] **Embodiment Pipe Closed** — `will_conflict_data` проверено доходит до `text_input.infect()` через `shared_context` (та же ссылка `id()`)
  Files: tick_orchestrator.py, game_screen.py

`ADR-087` [FIX] **Fast Path Dictionary Expansion** — `IntentCompressor._ACTION_LEMMAS` расширен приставочными глаголами (`выбить`, `откусить`, `укусить`, `душить`, `пнуть`)
  Files: intent_compressor.py

`ADR-092` [FIX] **The Fool v2 Pipeline** — `game_loop_bridge.py` перезаписывал `world_snapshot` целиком, уничтожая `player_perception`. Рендерер применял дрожь ПОСЛЕ отрисовки
  Files: game_loop_bridge.py, scene_renderer.py

`ADR-093` [FIX] **The Fool Phase 3 (DM Observational Pipeline)** — `player_perception` с `embodied_traces` проброшен в DM-контракт. DM читает следы, не внутренние состояния
  Taboo: ❌ DM читает внутренние состояния NPC (pain, fear) вместо `embodied_traces`
  Files: pipeline_context.py, dm_agent.py

`ADR-094` [FIX] **RPG Vitalism Revival + MSOC Normalization** — `StateInterpreter.interpret()` мёртвый код. Нормализация `pain / 100.0`. S75: ADR-094 MSOC fix — `avatar_presentation_assembler` и `pressure_translator` читали `pain`/`fatigue` (0-100) без нормализации при порогах 0-1. КРИТИЧЕСКИЙ БАГ: `pressure_translator` блокировал FLEE при `pain > 0.8` (т.е. при pain > 0.8% — всегда). Контракт: `body_state` хранит `pain`/`fatigue` в 0-100, все читатели с порогами 0-1 обязаны нормализовать `/100.0`
  Taboo: ❌ Чтение `pain`/`fatigue` без нормализации `/100.0` в потребителях с порогами 0-1 (MSOC)
  Files: state_interpreter.py, npc_tick_pipeline.py, avatar_presentation_assembler.py, pressure_translator.py

`ADR-097` [FIX] **Push-out Resolution** — Булева блокировка коллизий → застревание. Push-out по вектору проникновения + `PLAYER_RADIUS` = 0.25
  Taboo: ❌ Булева блокировка коллизий игрока (только Push-out Resolution)
  Files: scene_renderer.py, collision_system.py

`ADR-098` [FIX] **AABB Coordinate Contract** — `scene_renderer.py` трактовал `x, y` как центр. Фикс: левый верхний угол (соответствует бэкенду)
  Files: scene_renderer.py

`ADR-113` [FIX] **LLM Resilience (Retry + Honest Failure)** — 3 retry с exponential backoff (1s/2s/2s). Partial stream recovery (&gt;20 chars). `{"error": True}` вместо фейкового нарратива
  Taboo: ❌ Фейковый нарратив при краше LLM ("Твоё сознание мутнеет..."). ❌ `agent_runner.py` возвращает `None` при timeout
  Files: llama_cpp_provider.py, agent_runner.py

---

## DOM-08: OBSERVABILITY (CDS & Sandbox)

`ADR-003` [STD] **Test Determinism** — Убраны I/O фикстуры, введены синтетические фабрики
  Files: test_factories.py

`ADR-004` [STD] **Phase 8 Handlers** — Memory/Scene обработчики признаны ненужными
  Files: tick_orchestrator.py

`ADR-009` [STD] **DI Primitives** — В `InterpretationEngine` передаются примитивы, а не объекты
  Files: interpretation_engine.py

`ADR-045` [STD] **Causal Oscilloscope** — `DeterministicClock` и `CausalTrace` для верификации причинности
  Files: causal_trace.py, deterministic_clock.py

`ADR-059` [STD] **CDS Integration** — Пассивная диагностика. Не влияет на fear/trust/pain/will/memory
  Files: causal_observer.py, dna_metrics.py
  Impact: ADR-059_IMPACT.md

`ADR-120` [FIX] **Pre-Bus Failure Observability (Инвариант 3)** — 80% багов ДО EventBus. 5 новых паттернов: `pipeline_critical`, `causality_crash`, `phase8_crash`, `tick_orch_error`, `affect_decay_fail`. PFI (Pre-Bus Failure Index) в DNA
  Taboo: ❌ `logger.debug` для крахов аффективного decay. ❌ `print()` для Phase 8 крахов
  Files: pattern_registry.py, tick_health.py, causal_observer.py, tick_orchestrator.py, dna_metrics.py

`ADR-133` [FIX] **Sandbox Test Protocol for Persistence & Movement** — Фиксы ADR-128/130 верифицированы только через smoke-test. 7 sandbox-тестов покрывают: save/load body_state (Rule 54/55), SSOT body_state над wounds (Rule 56), Movement Lock (Rule 57), Payload Fallback (Rule 58). Протокол §12.3: объекты через from_legacy/реальные словари
  Files: tests/sandbox/persistence/, tests/sandbox/movement/

---

## DOM-09: SOCIAL & AFFECTIVE ARCHITECTURE (SSOT & Causal Derivation)

`ADR-049` [ONTO] **Causal Pressure Pipeline & Affective Accumulation** — Замыкание контуров Восприятие-Эмоция-Решение. Этап 3: DecisionHub больше не генерирует `EmotionPayload`
  Files: decision_hub.py, tick_orchestrator.py
  Impact: ADR-049_IMPACT.md

`ADR-055` [ONTO] **Affective Pressure Pipeline** — Прямой прыжок Perception→Emotion запрещён. Промежуточный слой `AffectivePressure`. `resolve_emotion_from_pressure`
  Files: affective_pressure.py, tick_orchestrator.py, legacy_delta_adapter.py
  Impact: ADR-055_IMPACT.md

`ADR-138` [ONTO] **Dissipative Psychodynamics & Hysteresis** — Убит Вечный Двигатель Страха. `integrate_affective_pressure` переведён с интегратора с утечкой (`load + in - out`) на асимметричный аттрактор (`load + (target - load) * rate`). Рост быстрый (0.30), спад медленный (0.05 + will*0.1). PK получил idle-decay (Фаза 0.5). Cache Desync устранён (`update_cache` после idle)
  Taboo: ❌ Интегратор с утечкой для `affective_load` (аттрактор насыщения). ❌ PerceptualKernel без idle-decay (Rule 38). ❌ AFFECTIVE_BOOT / подтягивание `affective_load` до `emotion_tag`
  Files: affective_integrator.py, tick_orchestrator.py, life_engine.py
  Impact: ADR-138_IMPACT.md

`ADR-116` [FIX] **Emotion Pipeline Integrity (emotion: 0.0 Fix)** — `load_l2_state_from_runtime_dict()` создавал `NPCState` без `emotion`/`affective_load`/`body_state`/`perceptual_kernel`. 8 фиксов в 6 файлах
  Taboo: ❌ Создание `NPCState` без полного набора полей. ❌ Строковые теги эмоций без `_emotion_from_str()`
  Files: npc_state.py, npc_loader.py, state_applicator.py, tick_orchestrator.py, reaction_subscriber.py, game_loop/__init__.py
  Impact: ADR-116_IMPACT.md

---

## ADR-O: ONTOLOGY DECISIONS (Universal Abstractions)

`ADR-O-112` [ONTO] **Actor-Agnostic Combat Pipeline (Universal Violence)** — Боевой конвейер: `Player → NPC` → `Any Actor → Any Actor`. `UniversalSnapshotBuilder`, `AvatarState` снапшоты
  Status: PROPOSED
  Files: combat_subscriber.py, state_applicator.py, player_avatar_service.py
  Impact: ADR-O-112_IMPACT.md

---

## CONSOLIDATED ARCHITECTURAL TABOOS (Hard Rules)

### State & Mutation
1. ❌ Прямая мутация стейта в обход `DeltaBuffer`
2. ❌ Циклы `tick()` для нагона времени (`TICK_CATCHUP`)
3. ❌ Формирование ответа Фазы 8 через `List[dict]`
4. ❌ Подмена `campaign_id` на `location_id` в `_TickContext`
5. ❌ `if state.body_state:` (falsy dict) — использовать `is not None`
6. ❌ Переход `DEAD → ALIVE` через обычную физиологию (только `RevivalSystem`)

### Spatial & Movement
7. ❌ Использование `load_graph()` — мёртвый код, возвращает пустой граф
8. ❌ Сравнение legacy ID (`room_1`) с canonical ID (`tavern:room_1`) без `normalize_id()`
9. ❌ FLEE без исключения текущего узла NPC из кандидатов
10. ❌ Левый верхний угол комнаты как позиция узла в навигационном графе (только центроид)
11. ❌ Перезапись `local_position` для NPC в статусе `MOVING`
12. ❌ Прямая мутация `npc["position"]` или `npc["location"]`
13. ❌ Чтение позиций из `scene_state` (только `SpatialQueryService`)
14. ❌ Вызов `scene_manager.apply_changes()` из подписчиков
15. ❌ Вызов `process_intents()` или `apply_changes()` из `npc_orchestration.py`
16. ❌ Повторная обработка `MovementIntent` (инвариант `processed=True`)
17. ❌ `_enrich_local_positions` перетирает `local_position`, установленный пайплайном
18. ❌ Хардкод языковых глаголов в `npc_tick_pipeline.py`
19. ❌ `graph_compiler.py` без role-based aliases — legacy-имена не резолвятся
20. ❌ `SpatialQueryService.visibility()` с неправильным порядком аргументов
21. ❌ CEI-2 использует `is_movement_blocked` для макро-навигации (мебель ≠ стена)
22. ❌ spatial_runtime consumer-функции без `normalize_scene_state()`
23. ❌ `SceneStateManager.get_scene_state()` без `isinstance(scene, dict)` guard

### Will & Decision
24. ❌ Вызов WillpowerGate более 1 раза за цикл
25. ❌ Использование RPG-матриц поведения как онтологии
26. ❌ Передача сырых дельт давления из текущего тика в DecisionHub (только T-1)
27. ❌ Возврат дефолтного `EmotionalVector` (aggression=0.0) из `IntentCompressor` для ATTACK
28. ❌ Использование переменных из локальной области другой функции (Python scoping trap)

### Perception & Phenomenology
29. ❌ Хранение `EventDTO` в `EventBuffer` (только `FieldDisturbance`)
30. ❌ Обход `LocalCausalSolver` при генерации давления
31. ❌ Мутация состояния из `CausalObserver`
32. ❌ Прямая генерация эмоций из боевых событий (только через Perception)
33. ❌ `write_to_legacy` / `from_legacy` без `perceptual_kernel` и `affective_load`
34. ❌ `write_to_legacy` / `from_legacy` без `body_state`

### Physiology & Combat
35. ❌ Прямая мутация HP аватара в обход `ImpactEngine`
36. ❌ `CombatSubscriber` пишет в Emotion (Domain Leakage)
37. ❌ `BehaviorManifestationService` читает эмоции вместо физиологии (Rule X)
38. ❌ `StateInterpreter` вычисляет `UrgencyLevel` из `stress` — дублирует `EmotionResolution`
39. ❌ Вызов `publish_classified_player_event` ДО `resolve_player_intent`
40. ❌ `shock_impulse` без decay в `PhysiologyDecayHandler`
41. ❌ `StateApplicator` проверяет `shock_impulse &gt; 0.0` вместо `!= 0.0`
42. ❌ `NPCStateSnapshot` без поля `shock_impulse`
43. ❌ `PhysiologyDecayHandler` без проверки `life_status == "DEAD"`
44. ❌ `evaluate_vital_state` без DEATH LOCK
45. ❌ `import logging` внутри функции вместо уровня модуля
46. ❌ Двойная онтология: `wounds/conditions` (legacy) ≠ `body_state` (runtime truth)
47. ❌ `AvatarService` сериализует без `body_state`, `affective_load`, `perceptual_kernel`
48. ❌ Обработка player action без проверки `life_status` (мёртвый игрок не может действовать)
49. ❌ `_make_player_snapshot()` без чтения `avatar_state.body_state` (статический снапшот = бессмертный в бою)

### Frontend & Presentation
50. ❌ Булева блокировка коллизий игрока (только Push-out Resolution)
51. ❌ Перезапись `result.world_snapshot` целиком в `game_loop_bridge.py`
52. ❌ Применение моторных смещений ПОСЛЕ отрисовки спрайта
53. ❌ Импорт `backend/app/` во фронтенд (Устав §1.1)
54. ❌ Передача игроку внутренних метрик NPC (HP, fear)
55. ❌ DM читает внутренние состояния NPC вместо `embodied_traces`
56. ❌ Масштабная несовместимость: `pain` 0-100 vs интерпретаторы 0-1
57. ❌ Обработка клавиши `Ё` только через `pygame.K_BACKQUOTE`
58. ❌ Использование `asdict()` на границе API без валидации
59. ❌ LLM описывает движение NPC без подтверждения от `MovementEngine`
60. ❌ DM контракт без блока о перемещениях NPC при отсутствии `npc_movement_summary`

### Social & Memory
61. ❌ Публикация в память в обход `MemoryManager`
62. ❌ `DirectiveInterpretationSubscriber` генерирует `MovementIntent`
63. ❌ Вызов директивы без инъекции `all_npcs_raw`DTO 
64. ❌ Персистенция `relationship_cache` внутри `NPCState` (DOUBLE TRUTH)
65. ❌ Плоский формат `{"fear": 0.5}` в `relationship_cache`
66. ❌ `affective_load` как независимый аккумулятор с затуханием
67. ❌ Хранение `threat_gradient` навсегда без decay или recompute

### Observability
68. ❌ Обратная связь из CDS в рантайм симуляции
69. ❌ Прерывание каузального потока при падении CDS
70. ❌ `logger.debug` для крахов аффективного decay (WARNING)
71. ❌ `print()` для Phase 8 крахов (структурированный `[PIPELINE][CRITICAL]`)
72. ❌ CDS не парсит пред-шинные отказы

### DRF & Causal Field
73. ❌ `DRFBus` через `default_factory=DRFBus` в `_TickContext` — split-brain при двух контекстах (ADR-134)
74. ❌ Monkey-patch функции для инъекции шины (`func.drf_bus = ...`) — нарушает причинную прозрачность (ADR-134)
75. ❌ `_phase_10_persistence` без DRF drain — idle claims теряются (ADR-134)
76. ❌ Передача голого `drf_bus` в pipeline вместо `drf_ctx` — потеря scoped identity (ADR-136)
77. ❌ DRF overlay только в idle path — player path обходит арбитраж (ADR-135)
78. ❌ Viability veto через `_drf_killed` флаг или `priority=0` в MovementEngine — скрытый скоринг вместо viability (ДОЛГ 4.3)
79. ❌ Viability veto через парсинг строк (`"schedule" in reason`) — ломается при смене имён (ДОЛГ 4.3)
80. ❌ Clamp override `max(priority, N)` при шкале 0.0–1.0 — уничтожение шкалы (ADR-135)

### Death & Agency
81. ❌ `AvatarStateDTO` без поля `life_status` — фронтенд слеп к смерти (ADR-137)
82. ❌ Death Guard без npc_positions в world_snapshot — мир замерзает при смерти игрока (ADR-137)### Death & Agency
81. ❌ `AvatarStateDTO` без поля `life_status` — фронтенд слеп к смерти (ADR-137)
82. ❌ Death Guard без npc_positions в world_snapshot — мир замерзает при смерти игрока (ADR-137)
92. ❌ DM narration без проверки player `life_status` — каузальный обман, DM описывает живого мертвеца (ADR-139)
93. ❌ `avatar_to_prompt` без `life_status` — DM слеп к смерти (ADR-139)
94. ❌ Death Guard без вызова DM — подмена нарратива хардкодом (ADR-139)

### Physiology Scale Contract (ADR-094 MSOC)
83. ❌ Чтение `pain`/`fatigue` без нормализации `/100.0` в потребителях с порогами 0-1 — `body_state` SSOT хранит 0-100, Decision/Presentation layers работают в 0-1

### Emotional Physics & Psychodynamics (ADR-138)
84. ❌ Использование интегратора с утечкой (`load + incoming - recovery`) для `affective_load` — аттрактор насыщения, вечный страх (ADR-138)
85. ❌ Отсутствие idle-decay для `PerceptualKernel` (threat, uncertainty, anomaly) — вечный реконструктор страха (ADR-138, Rule 38)
86. ❌ AFFECTIVE_BOOT / Anti-DOUBLE TRUTH: подтягивание `affective_load` до порога `emotion_tag` — положительная обратная связь (ADR-138)

### Viability Pre-Generation (ADR-O-137)
87. ❌ Пост-генерационная фильтрация кандидатов вместо pre-generation gate — ROUTINE уже мутирует `routine["current"]` и создаёт SceneChange до фильтрации
88. ❌ `MovementIntent` без поля `domain` — viability mask не может работать, онтологическая неполнота
89. ❌ Fallback NPC dict без `body_state` — создание "логического призрака" с социальными весами, но без физики (NPIC, ADR-O-139)
90. ❌ Проверка shock/pain ПОСЛЕ семантического парсинга в `DirectiveInterpretationSubscriber` — тело определяет доступность интерпретации, не модулирует результат (Somatic Gating, ADR-O-139)
91. ❌ `if not body_state: skip` без инъекции `BODY_STATE_DISABLED` — вызывает State Starvation Collapse при холодном старте (NCC, ADR-O-139)

### Narrative Continuity (ADR-140)
92. ❌ DM narration без проверки player `life_status` — каузальный обман, DM описывает живого мертвеца (ADR-140)
93. ❌ `avatar_to_prompt` без `life_status` — DM слеп к смерти (ADR-140)
94. ❌ Death Guard без вызова DM — подмена нарратива хардкодом (ADR-140)
95. ❌ `InjuryProcessor` генерирует `blood_loss` без `pain_delta` — труба embodied symptoms сухая (ADR-141)
96. ❌ Хардкод хронической боли без учёта зоны и типа раны — нарушение ADR-123 / ADR-141

---

## VERIFIED FIXES REGISTRY (GAP → ADR)

| GAP | ADR | Description | Verification |
|-----|-----|-------------|--------------|
| GAP1 | ADR-081 | Когнитивный Оверлей: критический шок инжектится в `all_npcs_raw` мгновенно (T+0) | `tick_orchestrator.py:634` |
| GAP2 | ADR-082 | Амнезия Сопротивления: `compute_willpower` читает `trauma_markers`, +0.1 identity_rigidity | `will.py:122-125` |
| GAP3 | ADR-073 | body_state инъекция в `translate_kernel_to_context`, Somatic Veto | `state_interpreter.py` |
| GAP4 | ADR-077 | Ингибирование Шоком: `shock &gt; 0.7` ингибирует подчинение | `directive_interpretation_subscriber.py:58` |
| GAP5 | ADR-076 | RPG Витализм: `state_interpreter.py` читает `pain`, `shock_impulse`, `blood_loss` | `state_interpreter.py:273-291` |
| GAP6 | ADR-050 | Синдром Глухого Общества: потеря семантики (GAP8) | S50 |
| GAP7 | ADR-053 | Слепота Аватара: игрок парсится как наблюдатель в `_extract_observer_state` | `local_causal_solver.py:320-324` |
| GAP8 | ADR-073 | IntentEventAdapter Data Loss: `CommunicationIntent` обогащён `semantic_action` и `target_id` | `intent_event_adapter.py:46` |
| GAP9 | ADR-051 | Конфликт Транзитов: сон блокируется `threat_gradient &gt; 0.3` и `stress &gt; 50` | `life_engine.py:1179-1182` |
| GAP10 | ADR-052 | Незваные NPC: `EventContext` обогащён `target_id`, DecisionHub фильтрует APPROACH | `decision_hub.py:916` |
| GAP11 | ADR-054 | Хардкод Глаголов: `IntentCompressor` распознаёт наречия 1-го лица ("сюда", "мне") | `intent_compressor.py:93-98` |
| GAP12 | ADR-073 | Парадокс Призрачной Позиции: интерполяция `local_position` для NPC в активном транзите | `scene_state_manager.py:1145,1585` |
| GAP13 | ADR-080 | Player-Only Social Physics: NPC-to-NPC власть жива | `directive_interpretation_subscriber.py:77-92` |

---

## IMPACT AUDIT INDEX

| ADR | File | Key Downstream | Runtime Impact | Rollback Complexity |
|-----|------|----------------|----------------|---------------------|
| 031 | ADR-031_IMPACT.md | Phase1 Semantic Bridge, EventBus | +20-50ms tick latency | Low (restore local calls) |
| 035 | ADR-035_IMPACT.md | WillpowerGate, S28 Gate, DirectiveInterpretationSubscriber | 0 | Trivial (1 ternary) |
| 042 | ADR-042_IMPACT.md | DirectiveInterpretationSubscriber, DecisionHub | 0 | Trivial (remove guard) |
| 043 | ADR-043_IMPACT.md | DecisionHub | 0 | Low (remove `_service_archetypes`) |
| 047 | ADR-047_IMPACT.md | SceneInit, SceneStateManager, LifeEngine | 0 (O(N) at load) | Medium (restore TICK_CATCHUP) |
| 048 | ADR-048_IMPACT.md | SpatialQueryService, _resolve_reactive_movement | +1ms (get_nearest) | Trivial (remove sync block) |
| 049 | ADR-049_IMPACT.md | LocalCausalSolver, DecisionHub, PressureTranslator | 0 | Medium (restore emotion_map) |
| 050 | ADR-050_IMPACT.md | LocalCausalSolver, DecisionHub, CausalTrace | +0.1MB RAM (sandbox) | Medium (delete sandbox dirs) |
| 051 | ADR-051_IMPACT.md | TickOrchestrator, SceneInit, MovementEngine | +1-2ms / -1.5ms | High (restore 6 files) |
| 052 | ADR-052_IMPACT.md | MovementEngine, SceneStateManager | -latency (macro bypass) | Low (remove normalization) |
| 053 | ADR-053_IMPACT.md | TickOrchestrator, MovementEngine | 0 (fixes silent loss) | Low (restore signature) |
| 054 | ADR-054_IMPACT.md | CI/CD | 0 (test-only) | Trivial |
| 055 | ADR-055_IMPACT.md | TickOrchestrator, DecisionHub, LegacyStateDeltaAdapter | +0.5ms tick | Medium (delete affective dir) |
| 056 | ADR-056_IMPACT.md | LifeEngine, DecisionHub, StateApplicator, MovementEngine | +0.1KB RAM/NPC | Low (restore 3 checks) |
| 057 | ADR-057_IMPACT.md | LifeEngine, DecisionHub, TopicExtractor | 0 (fundamental UX shift) | Medium (restore 3 blocks) |
| 058 | ADR-058_IMPACT.md | SceneRenderer, GameScreen, Backend API | +0.01MB RAM | Medium (restore find_path) |
| 059 | ADR-059_IMPACT.md | LLM Architects, Developer | +2-5MB RAM (log buffer) | Low (set DIAGNOSTICS_ENABLED=False) |
| 064 | ADR-064_IMPACT.md | DirectiveInterpretationSubscriber, DecisionHub, StateApplicator | 0 | Trivial (remove fallback block) |
| 073 | ADR-073_IMPACT.md | DirectiveInterpretationSubscriber, DecisionHub, CFRM/ImpactEngine | +0.1ms tick | Medium (remove 4 blocks) |
| 102 | ADR-102_IMPACT.md | SpatialQueryService, PerceptionFilter, SceneRenderer | 0.8ms warm (build_for_location) | High (7 independent fixes) |
| 115 | ADR-115_IMPACT.md | LifeEngine, DecisionHub, PressureDerivation, AffectiveIntegrator | +200 bytes/NPC | Medium (remove 5 blocks) |
| 116 | ADR-116_IMPACT.md | DecisionHub, VerbalizationContext, WorldSnapshotBuilder | +0.1ms tick | High (6 files, 6 rollbacks) |
| 123 | ADR-123_VITAL_STATE_INJURY_BRIDGE.md | DecisionHub, StateApplicator, InjuryProcessor | 0 | Medium (restore hp&lt;=0) |
| 130 | ADR-130_IMPACT.md | LifeEngine, DecisionHub, MovementEngine | +0.01ms tick | Medium (remove 4 blocks) |
| O-112 | ADR-O-112_IMPACT.md | DecisionHub, IntentEventAdapter, CombatSubscriber, StateApplicator | +5-10% Phase 8 | High (restore player-check) |
| 134 | ADR-134_IMPACT.md | TickOrchestrator (execute + finalize), LifeEngine, npc_tick_pipeline | 0 (same bus, no new objects per tick) | Medium (restore default_factory + two _TickContext) |
| 135 | ADR-135_IMPACT.md | MovementEngine, TickOrchestrator (idle + player paths) | +0.1ms tick (claim scan per intent) | Low (remove _apply_drf_scoring_overlay calls) |
| 136 | ADR-136_IMPACT.md | npc_tick_pipeline, TickOrchestrator (DRFExecutionContext) | +0.05ms tick (context creation per NPC) | Low (restore drf_bus parameter) |
| 137 | - | AvatarStateDTO, GameScreen, DecisionHub, PressureTranslator | 0 | Low (remove life_status field + overlay) |
| 138 | ADR-138_IMPACT.md | AffectiveIntegrator, TickOrchestrator, LifeEngine, DecisionHub | 0 (stronger emotional stability, slower panic exits) | Medium (restore leaky integrator + remove PK decay) |
| 139 | ADR-139_IMPACT.md | dm_agent, phase_6_avatar, game_loop Death Guard | +1 LLM call at death | Low (restore hardcoded death string) |

---

## SCALING INSTRUCTIONS FOR LLM

**Adding a new ADR:**
1. Place under correct `DOM-XX` section (create new DOM if domain is new)
2. Use format: `` `ADR-XXX` [TYPE] **Title** — One-line essence ``
3. Add `Taboo:` line if this ADR introduces a prohibition
4. Add `Files:` line with primary changed files
5. If FIX, add to `VERIFIED FIXES REGISTRY` table
6. If Impact Audit exists, add to `IMPACT AUDIT INDEX` table
7. If new Taboo introduced, add to `CONSOLIDATED ARCHITECTURAL TABOOS` with next number

**Query patterns this index supports:**
- "Find all FIX in DOM-05" → scan DOM-05 for [FIX]
- "What taboos relate to spatial?" → search Taboo section for "spatial" / "movement"
- "Which ADRs touch DecisionHub?" → grep `Files:` for `decision_hub.py`
- "What was GAP4?" → search `VERIFIED FIXES REGISTRY`
- "Rollback ADR-057" → open `ADR-057_IMPACT.md` or read Rollback section