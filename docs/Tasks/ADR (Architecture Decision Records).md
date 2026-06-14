# ENIGMA ADR MASTER INDEX (LLM-Readable)
> Формат: `ADR-XXX` [TYPE] **Title** — Essence (1 line)
> Type: STD=Standard | ONTO=Ontology (ADR-O) | FIX=Verified Bugfix
> Status: VERIFIED | PROPOSED | DEPRECATED | DEAD
> Taboo: ❌ = Architectural prohibition (hard rule)

---

## LEGEND
| Tag | Meaning |
|-----|---------|
| [STD] | Standard architectural decision |
| [ONTO] | Ontology shift (fundamental paradigm change) |
| [FIX] | Verified runtime bugfix (audit session S50-S83) |
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

`ADR-004` [STD] **Phase 8 Handlers** — Memory/Scene обработчики признаны ненужными
  Files: tick_orchestrator.py

`ADR-013` [STD] **StateDeltas v2** — Плоский god-object заменён на `DeltaDomain` + типизированные frozen Payloads. Одна дельта = один домен
  Files: npc_state.py, delta_buffer.py

`ADR-016` [STD] **Layered Reduction** — Многоступенчатая редукция реальности: Physical → Materialization → Cognitive → Social. Порядок строго детерминирован
  Files: tick_orchestrator.py

`ADR-047` [ONTO] **No Retro-simulation** — Убит `TICK_CATCHUP`. Пропущенное время аналитически вычисляется через `reconcile_state(elapsed_seconds)`
  Taboo: ❌ Циклы `tick()` для нагона времени
  Files: life_engine.py, scene_init.py

`ADR-059` [STD] **Dual-Time Ontology** — Транзиты привязаны к монотонному `scene_state["tick"]`, не к реальному времени
  Files: tick_orchestrator.py, scene_state_manager.py

`ADR-065` [FIX] **Spatial Authority Consolidation** — Убита трёхкратная ручная сборка `SpatialService.build_for_location()` в TickOrchestrator
  Files: tick_orchestrator.py

`ADR-066` [FIX] **Single Movement Ownership** — Убит двойной вызов `process_intents()`. Единственный владелец — `TickOrchestrator`
  Taboo: ❌ Вызов `process_intents()` из `npc_orchestration.py`
  Files: tick_orchestrator.py, npc_orchestration.py

`ADR-089` [FIX] **Campaign ID Integrity** — Убита подмена `campaign_id` на `location_id` в `execute_player_finalize`
  Taboo: ❌ Подмена `campaign_id` на `location_id` в `_TickContext`
  Files: tick_orchestrator.py

`ADR-102` [FIX] **SpatialService replaces load_graph() + FLEE Fix** — `load_graph()` мёртв. `SpatialService.build_for_location()` — единственный источник
  Taboo: ❌ `load_graph()`. ❌ Сравнение legacy/canonical ID без `normalize_id()`
  Files: spatial_runtime.py, spatial_service.py, npc_tick_pipeline.py

`ADR-117` [STD] **Anti-DOUBLE TRUTH Bootstrap & Round-Trip Integrity** — Поддержание эмоции при affective_load > threshold. Обязательная сериализация всех полей NPCState
  Taboo: ❌ Прямой конструктор `NPCState(...)` в тестах (только `from_legacy`)
  Files: npc_state.py, state_applicator.py, tick_orchestrator.py

`ADR-118` [STD] **Runtime Overlay Integrity** — `_apply_runtime_overlay` мержит ТОЛЬКО ключи из whitelist
  Taboo: ❌ `_apply_runtime_overlay` без белых списков вычисленных полей
  Files: npc_loader.py

`ADR-128` [FIX] **Persistence Read-Back** — Убит разрыв write-path / read-path. LifeEngine `_load_npcs()` при cache miss читает SQLite
  Taboo: ❌ `_load_npcs()` без SQLite read-back. ❌ `load_npc_runtime()` возвращает `[]` вместо `None`
  Files: life_engine.py, persistence_port.py

`ADR-129` [FIX] **SpatialQueryService Argument Shift + SceneState Contract** — Неверный порядок аргументов, отсутствие `normalize_scene_state()`
  Taboo: ❌ `visibility()` с неправильным порядком аргументов. ❌ Отсутствие `normalize_scene_state()`
  Files: spatial_runtime.py, scene_state_manager.py

`ADR-134` [FIX] **DRF Split-Brain (Instance-Level Bus)** — DRFBus перенесён на уровень экземпляра оркестратора
  Taboo: ❌ `DRFBus` через `default_factory=DRFBus` в `_TickContext`
  Files: tick_orchestrator.py

`ADR-135` [STD] **Causal Scoring Overlay (ДОЛГ 4.2)** — DRF претензии влияют на приоритет: `priority += energy × weight × alignment`
  Taboo: ❌ Clamp override `max(priority, N)`. ❌ Viability veto через `_drf_killed` флаг
  Files: tick_orchestrator.py, movement_engine.py

`ADR-136` [STD] **DRFExecutionContext (Scoped Causal Ledger)** — Pipeline получает `drf_ctx`, а не голый `drf_bus`
  Taboo: ❌ Передача голого `drf_bus` в pipeline
  Files: tick_orchestrator.py, npc_tick_pipeline.py

`ADR-SCENE-LOCK` [FIX] **Tick Unlock Guard** — `unlock_tick()` вызывал `save_scene_state()` при `_tick_locked=True`
  Taboo: ❌ Снятие `_tick_locked` после вызова сохранения состояния
  Files: scene_state_manager.py

`ADR-GL-202` [ONTO] **Generative Constraint Execution Model (GCO)** — Ленивое вычисление графа каузальности. Генеративная модель вместо полного перебора
  Files: tick_orchestrator.py, life_engine.py

`ADR-S83.1` [ONTO] **Tick = Pure Function Evaluation** — Тик — это чистая функция вычисления состояния, а не объект с побочными эффектами
  Files: tick_orchestrator.py

`ADR-O-137` [ONTO] **Viability Pre-Generation Gate (ДОЛГ 4.3)** — Сдвиг к pre-генерационному сжатию пространства действий
  Taboo: ❌ Viability veto через парсинг строк. ❌ Пост-генерационная фильтрация
  Files: life_engine.py, domain/movement.py, npc_tick_pipeline.py

`ADR-O-139` [ONTO] **NPC Physical Integrity Contract (NPIC) & Somatic Gating** — Тело = gate of perception
  Taboo: ❌ Fallback NPC dict без `body_state`. ❌ Проверка shock/pain ПОСЛЕ парсинга
  Files: directive_interpretation_subscriber.py, tick_orchestrator.py

`ADR-O-201` [ONTO] **Causal Kernel Architecture** — `apply_changes` → чистый projection operator. Миграция в 4 фазы
  Status: PHASE_2_COMPLETE
  Files: scene_change.py, scene_state_manager.py, event_compiler.py, equivalence_validator.py

`ADR-O-204` [ONTO] **Phase 3 Preconditions — Causal Kernel Surgery** — Предусловия для миграции Каузального Ядра (Фаза 3)
  Files: scene_state_manager.py, event_compiler.py

`ADR-O-205` [ONTO] **Projection Layer System** — Слой проекции физики в наблюдаемую реальность. Изоляция мутаций
  Files: scene_state_manager.py, projection_engine.py

---

## DOM-02: WILL, PRESSURE & DECISION

`ADR-031` [ONTO] **Cumulative Strain Model** — Убита матрица `action × temperament`. `IntentPressureResolver` → `IntentPressureProfile`
  Files: will.py, affect.py

`ADR-034` [STD] **Phase 1 Boundary Adapter** — Бизнес-логика воли изгнана из `game_loop`. Фаза 1 — чистая функция
  Files: game_loop.py, phase_1_input.py

`ADR-035` [FIX] **Semantic Black Hole** — `semantic_action` пробрасывается напрямую, без `None` fallback
  Files: phase_1_input.py

`ADR-036` [STD] **Single Will Evaluation** — Убит Double Invocation. WillpowerGate вызывается строго 1 раз за цикл
  Taboo: ❌ Вызов WillpowerGate более 1 раза за цикл
  Files: will.py, tick_orchestrator.py

`ADR-037` [STD] **Affect Resonance** — Аффект — не бафф, а искажение интерпретации (Resonance → Distortion)
  Files: affect.py

`ADR-046` [STD] **Inverted Fear** — Страх перед авторитетом бустит `Intent.APPROACH`, а не подавляет
  Files: decision_hub.py

`ADR-050` [ONTO] **DecisionContext & Feasibility** — DecisionHub разделён на Фазу 1 (Feasibility) и Фазу 2 (Utility Deformation)
  Files: decision_hub.py

`ADR-056` [STD] **Attention Capture** — Хардкод-порог заменён на `recent_directive` с механизмом сжигания
  Files: perceptual_kernel.py, life_engine.py

`ADR-057` [ONTO] **Legitimacy Gate** — Нет страха/доверия = Irritation вместо Obedience
  Files: directive_interpretation_subscriber.py, decision_hub.py

`ADR-064` [FIX] **Directive Data Continuity** — Убит Баг #6 (Глухая Воля)
  Files: tick_orchestrator.py, directive_interpretation_subscriber.py

`ADR-067` [STD] **Player Command Override** — Приказ игрока перекрывает ЛЮБОЕ решение DecisionHub
  Files: tick_orchestrator.py, npc_tick_pipeline.py

`ADR-068` [FIX] **Partial Name Matching** — NPC с составными именами отзываются на часть имени (≥3 символа)
  Files: npc_tick_pipeline.py

`ADR-081` [STD] **Cognitive Overlay (T+0)** — Инжект шок-импульса > 0.5 мгновенно через Когнитивный Оверлей
  Files: state_applicator.py, tick_orchestrator.py

`ADR-083` [STD] **Semantic Action Fallback** — Чтение `intent.action` без fallback = Silent Crash
  Taboo: ❌ Чтение `intent.action` без fallback на `parameters.semantic_action`
  Files: will.py, affect.py

`ADR-088` [FIX] **Fast Path Emotional Injection** — Убит мёртвый `EmotionalVector` в Fast Path
  Taboo: ❌ Дефолтный `EmotionalVector` (aggression=0.0) для ATTACK
  Files: intent_compressor.py, will.py

`ADR-091` [FIX] **Semantic Action Before Resolution** — `publish_classified_player_event` вызывался ДО `resolve_player_intent()`
  Files: dm_phase.py, __init__.py

`ADR-O-146` [ONTO] **Personality Math Layer (Causal Geometry of Character)** — Аттракторная модель характера. `drive_multiplier()`
  Taboo: ❌ Импорт `_drive_multiplier` из relationship_profile. ❌ desire в RiskPerceptionProfile
  Files: decision/profile_math.py, decision/relationship_profile.py, decision/social_deltas.py, decision/risk_profile.py

---

## DOM-03: PERCEPTION & PHENOMENOLOGY (CFRM)

`ADR-025` [ONTO] **CFRM Core** — Глобального World нет. `ClusterGraph`, `EventBuffer`, `MembraneField`. NPC хранит `PerceptualKernel`
  Files: local_causal_solver.py, perceptual_kernel.py

`ADR-029` [STD] **CFRM Layer 1** — Spatial Index для O(1) поиска. Классификация по осям
  Files: local_causal_solver.py

`ADR-033` [ONTO] **Deobjectification P2** — Смерть объективных событий. `EventDTO` → `FieldDisturbance`
  Taboo: ❌ Хранение `EventDTO` в `EventBuffer`
  Files: local_causal_solver.py, event_buffer.py

`ADR-040` [STD] **Epistemic Classification** — `ClassificationResult` с `confidence`. Fallback-события имеют вес 0.2
  Files: local_causal_solver.py

`ADR-042` [FIX] **Perception Domain** — Реальность течёт в `PerceptionPayload`, а не напрямую в эмоции
  Files: npc_tick_pipeline.py, tick_orchestrator.py

`ADR-115` [FIX] **DOUBLE TRUTH perceptual_kernel** — `write_to_legacy()` / `from_legacy()` не сериализовали `perceptual_kernel`
  Taboo: ❌ `write_to_legacy` / `from_legacy` без `perceptual_kernel` и `affective_load`
  Files: npc_state.py

`ADR-302` [ONTO] **SIL, DSTC & SEL (Active Inference)** — Сдвиг к Активному Выводу. Сенсорно-моторные контуры вместо реактивных дельт
  Files: local_causal_solver.py, perceptual_kernel.py

`ADR-O-143` [ONTO] **Somatic Axis in PerceptualKernel** — Боль/шок проходят через воспринимающую линзу личности
  Taboo: ❌ Инъекция pain/shock напрямую в psyche dict
  Files: affective_integrator.py, tick_orchestrator.py, npc_state.py

`ADR-O-147` [ONTO] **Manifest Layer — Observable Physical Manifestations** — Эмоции NPC → моторные проявления → наблюдаемые теги
  Taboo: ❌ Показ эмоций (fearful). ❌ Смешивание cues и manifestations
  Files: behavior_manifestation_service.py, phenomenology_projection_service.py, game_screen.py

---

## DOM-04: SPATIAL & LOCOMOTION

`ADR-008` [STD] **Spatial Centralization** — Убит глобальный `_connections_data`. Единственный источник — `SpatialService`
  Files: spatial_service.py

`ADR-010` [STD] **Macro/Micro Zones** — Архетипы переведены на макро-зоны. Убита парализация из-за микро-зон
  Files: spatial_service.py

`ADR-019` [STD] **Traversal State** — Диагноз телепортации. `TraversalState` как презентационный артефакт
  Files: movement_engine.py

`ADR-048` [STD] **Single Spatial Authority** — Чтение `scene_state["player_distances"]` запрещено
  Taboo: ❌ Чтение позиций из `scene_state`
  Files: spatial_query_service.py, npc_orchestration.py

`ADR-051` [ONTO] **LifeEngine De-godification** — LifeEngine лишён права прямой мутации позиции
  Files: life_engine.py, tick_orchestrator.py

`ADR-052` [FIX] **LOD0/LOD1 Split** — Нормализация префиксов. Устранение Silent Data Loss
  Files: npc_tick_pipeline.py, movement_engine.py

`ADR-053` [FIX] **LifeEngine Intent Pipeline Restoration** — Намерения не теряются на границе LifeEngine → TickOrchestrator
  Files: life_engine.py, tick_orchestrator.py

`ADR-058` [STD] **Frontend Dual-Time Ontology** — Разделение времени симуляции и рендера. Интерполяция `path_waypoints`
  Files: game_loop_bridge.py, scene_renderer.py

`ADR-060` [ONTO] **Movement Ontology Split** — `MovementIntent` объединяет LOD0 и LOD1
  Files: movement_engine.py, npc_tick_pipeline.py

`ADR-061` [STD] **Player Position Authority** — `npc_positions.player` — единственный источник
  Files: scene_state_manager.py, tick_orchestrator.py

`ADR-069` [FIX] **target_local_xy Propagation** — При `reactive:approach` координаты цели пробрасываются через `MacroMovementGoal`
  Files: npc_tick_pipeline.py, scene_state_manager.py

`ADR-070` [FIX] **Ghost Position Interpolation** — При создании нового транзита `from_xy` интерполируется по прогрессу старого
  Files: movement_engine.py

`ADR-071` [FIX] **Bridge Traversal Propagation** — `game_loop_bridge.py` пробрасывает `active_traversals` в `world_snapshot`
  Files: game_loop_bridge.py

`ADR-072` [FIX] **Enrichment LOD0 Guard** — `_enrich_local_positions` не перетирает `local_position` для сдвинувшихся NPC
  Taboo: ❌ `_enrich_local_positions` перетирает `local_position`
  Files: scene_state_manager.py

`ADR-073` [STD] **Adjacency Inference** — Алгоритм вывода связей из смежности полигонов
  Files: graph_compiler.py

`ADR-095` [FIX] **Centroid Graph Compilation** — Вычисляет центр комнаты вместо левого верхнего угла
  Taboo: ❌ Левый верхний угол как позиция узла
  Files: graph_compiler.py

`ADR-096` [FIX] **Frontend Traversal Respect** — Фронтенд не перезаписывает `local_position` для NPC в `MOVING`
  Taboo: ❌ Перезапись `local_position` для NPC в статусе `MOVING`
  Files: game_loop_bridge.py, scene_renderer.py

`ADR-114` [FIX] **Spatial Paralysis Fix (Role-Based Aliases)** — Добавлены name-aliases и role-based legacy aliases
  Taboo: ❌ `graph_compiler.py` без role-based aliases
  Files: graph_compiler.py

`ADR-116` [FIX] **FLEE Intent Lost (PRIORITY_NEEDS NameError)** — `_resolve_reactive_movement()` использовал `PRIORITY_NEEDS` из чужой области
  Taboo: ❌ Использование переменных из локальной области другой функции
  Files: npc_tick_pipeline.py

`ADR-119` [FIX] **Narrative Movement Prohibition (Инвариант 2)** — LLM не может описывать движение NPC без подтверждения
  Taboo: ❌ LLM описывает движение NPC без подтверждения
  Files: npc_tick_pipeline.py, dm_agent.py

`ADR-130` [FIX] **Movement Lock & Target Resolution** — `update_routine()` traversal-aware
  Files: life_engine.py, decision_hub.py

`ADR-145` [STD] **Boundary Transition Pipeline (ДОЛГ 6.2)** — Двухфазная реальность: смысл → материализация
  Taboo: ❌ Boundary node как цель движения. ❌ Boundary resolution при создании traversal
  Files: graph_compiler.py, spatial_contracts.py, tick_orchestrator.py

`ADR-301` [ONTO] **Semantic Index Layer** — Разделение интерпретации строки от физического разрешения узла
  Taboo: ❌ SemanticIndex возвращает один canonical_id
  Files: semantic/index.py, semantic/scoring.py, semantic/selection.py

`ADR-303` [ONTO] **Coordinate Truth & Physical World Unification** — Унификация координат редактора карт и рантайма
  Files: graph_compiler.py, map_editor.py

`ADR-S82.0` [STD] **Spatial Authority Contract** — Строгий контракт единого владельца пространственных данных
  Taboo: ❌ Запрет дублирования пространственной логики
  Files: spatial_service.py, scene_state_manager.py

---

## DOM-05: PHYSIOLOGY & COMBAT

`ADR-015` [ONTO] **Physiology Domain** — Убиты RPG Hit Roll и AC. `body_profile`, `InjuryDTO`, `ImpactEngine`
  Taboo: ❌ RPG-абстракции (Hit Roll, AC)
  Files: impact_engine.py, combat_math.py

`ADR-020` [STD] **DRSL** — `ReductionPolicy`. Тело эволюционирует (`PHYSICS_COMPOSITE`)
  Files: reduction_policy.py

`ADR-021` [STD] **CombatSubscriber** — Мост `EventDTO → ImpactEngine`. Возвращает ТОЛЬКО Physiology-дельты
  Taboo: ❌ `CombatSubscriber` пишет в Emotion (Domain Leakage)
  Files: combat_subscriber.py

`ADR-022` [STD] **Leaky Integrator** — Физиология затухает по экспоненте
  Files: physiology_decay_handler.py

`ADR-027` [STD] **Layered Reduction** — Каскад: Physical → Materialization → Cognitive → Social
  Files: reduction_policy.py

`ADR-028` [STD] **Config Migration** — `combat_stats` удалены из JSON
  Files: npc_config.py

`ADR-084` [FIX] **NameError blood_loss_delta** — Переменная без извлечения
  Files: state_applicator.py

`ADR-099` [FIX] **Silent Loss Physiology (asdict)** — `asdict` не импортирован на уровне модуля
  Files: state_applicator.py

`ADR-100` [FIX] **Serialization Black Hole (body_state)** — `write_to_legacy()` / `from_legacy()` не сериализовали `body_state`
  Taboo: ❌ `write_to_legacy` / `from_legacy` без `body_state`
  Files: npc_state.py

`ADR-101` [FIX] **Rule X Violation (BehaviorManifestation)** — Читал только `stress_delta`, игнорируя `body_state`
  Taboo: ❌ `BehaviorManifestationService` читает эмоции вместо физиологии
  Files: behavior_manifestation_service.py

`ADR-102` [FIX] **shock_impulse Not Applied** — Извлекал, но не применял
  Files: state_applicator.py

`ADR-103` [FIX] **NPC ID Fallback (apply_batch)** — Поиск по `"id"`, хотя dict использует `"npc_id"`
  Files: state_applicator.py

`ADR-104` [FIX] **Idle Tick Perception Blindness** — Вызов `produce_traces()` без `all_npcs_raw`
  Files: tick_orchestrator.py

`ADR-109` [FIX] **Shock Immortality** — `shock_impulse` не затухал между тиками
  Taboo: ❌ `shock_impulse` без decay
  Files: physiology_decay_handler.py, state_applicator.py

`ADR-110` [FIX] **CombatSubscriber NPCStateSnapshot без shock_impulse** — `_build_snapshot()` не передавал поле
  Files: combat_subscriber.py

`ADR-112` [FIX] **Semantic Inflation Fix (Rule X Enforcement)** — Переведены на `body_state` ONLY
  Taboo: ❌ Чтение `stress_delta`/`psyche_state` для моторных искажений
  Files: behavior_manifestation_service.py, phenomenology_projection_service.py

`ADR-123` [ONTO] **Vital State Evaluator & Injury-Physiology Bridge** — Смерть = процесс. `evaluate_vital_state()`
  Taboo: ❌ `hp <= 0` как источник смерти
  Files: vital_state.py, injury_processor.py, state_applicator.py

`ADR-127` [FIX] **Death Lock — Онтологическая Необратимость Смерти** — Трёхслойный инвариант
  Taboo: ❌ `if state.body_state:` → `is not None`. ❌ Decay для мёртвых
  Files: vital_state.py, physiology_decay_handler.py, npc_state.py

`ADR-131` [ONTO] **Action Eligibility Gate (Player Death Guard)** — Игрок с `life_status="DEAD"` не может действовать
  Taboo: ❌ Обработка player action без проверки `life_status`
  Files: game_loop/__init__.py

`ADR-132` [ONTO] **Player Combat EntityView Shift** — Игрок — симулируемая физическая сущность
  Taboo: ❌ `_make_player_snapshot()` без чтения `avatar_state.body_state`
  Files: combat_subscriber.py

`ADR-137` [FIX] **Death Feedback Pipeline (life_status → UI)** — `AvatarStateDTO.life_status` пробрасывает смерть
  Taboo: ❌ `AvatarStateDTO` без поля `life_status`. ❌ Death Guard без npc_positions
  Files: snapshot.py, avatar_presentation_assembler.py, game_screen.py

`ADR-140` [FIX] **DM Death Scene Pipeline** — DM получает life_status и генерирует death scene
  Taboo: ❌ DM narration без проверки player life_status
  Files: dm_agent.py, phase_6_avatar.py, game_loop/__init__.py

`ADR-141` [STD] **Injury Chronic Pain Bridge** — Убит разрыв Injury → Pain. InjuryProcessor генерирует `pain_delta`
  Taboo: ❌ `InjuryProcessor` генерирует `blood_loss` без `pain_delta`
  Files: injury_processor.py

---

## DOM-06: SOCIAL & MEMORY

`ADR-005/006` [STD] **NPC Social Mapping** — Маппинг `social_stats` в `relationship_cache`
  Files: npc_loader.py

`ADR-007` [STD] **Idle Sync** — Синхронизация `all_npcs_raw` в idle-пути
  Files: game_loop.py

`ADR-043` [ONTO] **Social Physics** — Приказ генерирует `directive_obedience`, а не `MovementIntent`
  Taboo: ❌ `DirectiveInterpretationSubscriber` генерирует `MovementIntent`
  Files: directive_interpretation_subscriber.py

`ADR-080` [FIX] **Player-Only Social Physics** — Вычисляет легитимность по `source_id`
  Files: directive_interpretation_subscriber.py

`ADR-121` [FIX] **RelationshipStore SSOT / DOUBLE TRUTH Elimination** — Единственный SSOT (масштаб 0-100)
  Taboo: ❌ Персистенция `relationship_cache` внутри `NPCState`
  Files: npc_state.py, relationship_store.py, decision_hub.py

`ADR-122` [FIX] **Affective Load Target Derivation** — Целевая нагрузка = `Σ(active_causes + pain + shock)`
  Taboo: ❌ `affective_load` как независимый аккумулятор
  Files: state_applicator.py, physiology_decay_handler.py

`ADR-124` [FIX] **Combat → Perception Bridge** — `ReactionSubscriber` генерирует `PerceptionPayload`
  Files: reaction_subscriber.py, state_applicator.py

`ADR-125` [STD] **Target Resolution SSOT** — `IntentParametersDTO.target_id` депрекирован
  Files: tick_orchestrator.py, dm_phase.py

`ADR-126` [FIX] **Relationship Cache Ontology Merge** — Сборка расширена до Partial Social Graph
  Files: npc_tick_pipeline.py, decision_hub.py

---

## DOM-07: FRONTEND, PRESENTATION & INPUT

`ADR-011/014` [STD] **Narrative Beats** — Убран плоский чат. Пузыри, спикеры
  Files: game_screen.py, narrative_renderer.py

`ADR-035` [ONTO] **Intent Compression** — Русская морфология (pymorphy3 + LLM)
  Files: intent_compressor.py

`ADR-038` [STD] **Embodied Perception DTO** — Скаляры давления и моторные импульсы
  Files: api_schema.py

`ADR-039` [STD] **Resistance Medium** — Конфликт воли = инфекция поля ввода
  Files: text_input.py, game_screen.py

`ADR-041` [STD] **Will Conflict Data** — Проброс конфликта воли через API
  Files: routes.py, tick_orchestrator.py

`ADR-068` [FIX] **Avatar Flesh Injection & API Suturing** — Труба Эмбодимента оборвана на 3 уровнях
  Files: avatar_service.py, routes.py, game_screen.py

`ADR-086` [FIX] **Embodiment Pipe Closed** — `will_conflict_data` проверено доходит до `text_input.infect()`
  Files: tick_orchestrator.py, game_screen.py

`ADR-087` [FIX] **Fast Path Dictionary Expansion** — Расширен приставочными глаголами
  Files: intent_compressor.py

`ADR-092` [FIX] **The Fool v2 Pipeline** — `game_loop_bridge.py` перезаписывал `world_snapshot` целиком
  Files: game_loop_bridge.py, scene_renderer.py

`ADR-093` [FIX] **The Fool Phase 3 (DM Observational Pipeline)** — `player_perception` проброшен в DM-контракт
  Taboo: ❌ DM читает внутренние состояния NPC вместо `embodied_traces`
  Files: pipeline_context.py, dm_agent.py

`ADR-094` [FIX] **RPG Vitalism Revival + MSOC Normalization** — Нормализация `pain / 100.0`
  Taboo: ❌ Чтение `pain`/`fatigue` без нормализации `/100.0`
  Files: state_interpreter.py, avatar_presentation_assembler.py

`ADR-097` [FIX] **Push-out Resolution** — Булева блокировка → Push-out по вектору проникновения
  Taboo: ❌ Булева блокировка коллизий игрока
  Files: scene_renderer.py, collision_system.py

`ADR-098` [FIX] **AABB Coordinate Contract** — Левый верхний угол, не центр
  Files: scene_renderer.py

`ADR-113` [FIX] **LLM Resilience (Retry + Honest Failure)** — 3 retry. `{"error": True}` вместо фейка
  Taboo: ❌ Фейковый нарратив при краше LLM
  Files: llama_cpp_provider.py, agent_runner.py

`ADR-JOURNAL` [STD] **Dialog Journal** — Журнал диалогов (клавиша J/O)
  Taboo: ❌ dialog_journal в scene_state
  Files: game_screen.py

`ADR-SPEECH` [STD] **Speech Bubbles** — Речевые облачка над NPC и игроком
  Taboo: ❌ npc_reactions в message_log
  Files: game_screen.py, scene_renderer.py

`ADR-i18n` [STD] **Localization Module** — Единый файл локализации
  Taboo: ❌ Inline-словари activity_ru в game_screen
  Files: i18n.py, game_screen.py

---

## DOM-08: OBSERVABILITY (CDS & Sandbox)

`ADR-003` [STD] **Test Determinism** — Синтетические фабрики вместо I/O фикстур
  Files: test_factories.py

`ADR-009` [STD] **DI Primitives** — Примитивы, а не объекты в `InterpretationEngine`
  Files: interpretation_engine.py

`ADR-045` [STD] **Causal Oscilloscope** — `DeterministicClock` и `CausalTrace`
  Files: causal_trace.py, deterministic_clock.py

`ADR-054` [FIX] **Test Suite Synchronization & ADR-052 Alignment** — Синхронизация тестов с ADR-052
  Files: tests/sandbox/

`ADR-120` [FIX] **Pre-Bus Failure Observability (Инвариант 3)** — 5 новых паттернов в CDS
  Taboo: ❌ `logger.debug` для крахов аффективного decay
  Files: pattern_registry.py, tick_health.py, causal_observer.py

`ADR-133` [FIX] **Sandbox Test Protocol** — 7 sandbox-тестов покрывают save/load body_state
  Files: tests/sandbox/persistence/, tests/sandbox/movement/

`ADR-147` [FIX] **LLM Streaming Observability Gate** — Убит теневой streaming path
  Files: router.py, pattern_registry.py, causal_observer.py

---

## DOM-09: SOCIAL & AFFECTIVE ARCHITECTURE (SSOT & Causal Derivation)

`ADR-049` [ONTO] **Causal Pressure Pipeline** — Замыкание контуров Восприятие-Эмоция-Решение
  Files: decision_hub.py, tick_orchestrator.py

`ADR-055` [ONTO] **Affective Pressure Pipeline** — Прямой прыжок Perception→Emotion запрещён
  Files: affective_pressure.py, tick_orchestrator.py

`ADR-138` [ONTO] **Dissipative Psychodynamics & Hysteresis** — Убит Вечный Двигатель Страха. Асимметричный аттрактор
  Taboo: ❌ Интегратор с утечкой для `affective_load`
  Files: affective_integrator.py, tick_orchestrator.py, life_engine.py

`ADR-O-206` [ONTO] **Emotional Residue Isolation Protocol** — Эмоциональный остаток изолирован от физиологического цикла
  Files: affective_integrator.py, physiology_decay_handler.py

---

## DOM-10: IDENTITY & ONTOLOGY (Identity Layer & Chronicle)

`ADR-O-112` [ONTO] **Actor-Agnostic Combat Pipeline (Universal Violence)** — Боевой конвейер: `Any Actor → Any Actor`
  Status: PROPOSED
  Files: combat_subscriber.py, state_applicator.py, player_avatar_service.py

`ADR-GL-203` [ONTO] **Error-Geometry System & Dynamic Ontology** — Эпистемология ENIGMA: Геометрия ошибок и исполнение семантики
  Files: domain/exceptions.py, causal_trace.py

`ADR-O-207` [ONTO] **Post-Commit Validation Gate** — L5 валидация. OntologyViolationError убивает тик
  Taboo: ❌ Коммит состояния с NaN или sum(drives) != 1.0
  Files: domain/exceptions.py, state_applicator.py

`ADR-O-208` [ONTO] **Identity Chronicle & Drives (DRP)** — L1Chronicle (append-only) и DriveResolver (L0+L1→L3)
  Taboo: ❌ Кэширование EffectiveDrives. ❌ Удаление из L1Chronicle
  Files: domain/identity_events.py, services/npc/l1_chronicle.py, services/npc/drive_resolver.py

`ADR-O-209/210` [ONTO] **Phase-Locked Identity & Bounded Spatial Field Coupling** — Фазовая блокировка идентичности и ограниченная связь с пространственным полем
  Files: decision/profile_math.py, spatial_service.py

`ADR-O-211` [ONTO] **Calibration Engine & Identity Stability Kernel** — Двигатель калибровки и ядро стабильности. Анти-осцилляция
  Taboo: ❌ Неконтролируемый дрейф базовых драйвов без калибровки
  Files: services/npc/calibration_engine.py

`ADR-O-212` [ONTO] **Social Physics Inertia & Approximation** — Социальная физика — функция аппроксимации поведения группы во времени. 4 слоя: Физика, Психика, Общество (VillageMemoryField), Политика (InstitutionLayer). Институциональная инерция запрещает мгновенную эскалацию
  Taboo: ❌ Narrative Gravity как отдельный слой данных (Double Truth). ❌ Мгновенная реакция InstitutionLayer. ❌ resistance_to_change = 0.0. ❌ myth_level от количества убийств
  Files: social/village_memory_field.py, social/social_memory_updater.py, social/institutional_inertia.py

`ADR-TIFL-001` [ONTO] **Temporal Identity Formation Layer** — Формирование идентичности во времени. Темпоральный слой L1
  Files: services/npc/l1_chronicle.py

`ADR-TIFL-002` [ONTO] **Identity as Competitive Drift Field (ICDF)** — Идентичность как конкурентное поле дрейфа
  Files: services/npc/drive_resolver.py, domain/identity_events.py

`ADR-TIFL-003` [ONTO] **Identity Constraint Layer & Thermodynamic Crystallization** — Слой ограничений идентичности и кристаллизация черт
  Files: services/npc/drive_resolver.py