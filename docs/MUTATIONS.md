# MUTATIONS.md — Каузальная Эволюция ENIGMA

> **Формат:** Эпохи эволюции → Домены → Текущий статус.
> Архитектурные запреты вынесены в `docs/ADR (Architecture Decision Records).md` (Canonical Laws).

---

## МЕТА

| Показатель | Значение |
|------------|----------|
| Сессий проведено | 142 |
| Доменов | 10 |
| Текущий статус | Стабильный (IPT 5/5 passed, 0 критических дрейфов) |
| Диапазон аудита | S03 — S142 |

---

## 1. ЭПОХИ ЭВОЛЮЦИИ (Architectural Milestones)

Вместо побаттового лога, эволюция системы делится на 5 ключевых эпох, каждая из которых навсегда изменила онтологию проекта.

### Эпоха 1: Каузальный Фундамент (S04 — S82)
**Фокус:** Уничтожение телепортации, централизация пространства, базовая физиология.
- Убита классическая RPG-математика (Hit Roll, AC). Введено `body_state` и `ImpactEngine`.
- `SpatialService` стал единственным владельцем графа.
- Внедрена Dual-Time Ontology: разделение симуляционного времени и рендера. Появились `TraversalState`.
- Фронтенд переведен на DTO-контракт, убраны прямые чтения `backend/`.

### Эпоха 2: Унификация Пайплайна и Чистота Ядра (S83 — S104)
**Фокус:** Превращение ядра в чистую функцию, изоляция LLM, детерминизм.
- **TZ-08/TZ-09/TZ-10:** Уничтожено ветвление `player/idle`. `TickOrchestrator` переведен на `InterventionEvent`. Введены `TickState` и `TickMutation`. Убит бог-объект `svc: Any`.
- **ADR-O-301:** Полная изоляция случайности. Внедрен `KernelRNG(tick, npc_id, salt)). Убиты все утечки `random.*` в kernel layer.
- **L3-P1 / DRP:** `EffectiveDrives` (L3) объявлены строго эфемерными. Введен `L1Chronicle` (append-only SQLite). Убиты фоллбэки на L0 в принятии решений.
- **Epistemic Boundary:** Изоляция DM-агента от ментальных объектов. Ядро возвращает только `observed_state`.

### Эпоха 3: Кристаллизация Идентичности и Эпистемика (S105 — S125)
**Фокус:** L2.5 (Убеждения), Тройная Мембрана,闭环е каузальности потребностей.
- **ADR-O-305/306/307:** Внедрен `BeliefCrystallizationEngine`. Асимметричная травма (x6 для опровержений). Тройная Мембрана (Физика, Личность, Социум) фильтрует L1.
- **Entity Continuity (ADR-O-320):** Переход к Reality-Constrained Agency Model. Введен `Identity Pressure Vector` (Layer 2) и `LifeProject` FSM.
- **Embodied Traversal (S130-S132):** Внедрение `LocalTraversalPlanner` и `Geometry Kernel`. Движение определяется физической геометрией, а не примитивным A* по узлам графа. Появилась честная физика прыжка (Z-координата) и зазоров (clearance).
- **Combat RNG:** Интеграция D&D 5e математики с сохранением детерминизма.

### Эпоха 4: Презентация и Физика Восприятия (S126 — S141)
**Фокус:** 5-слойная архитектура (Reality → Observable Physics → Perception), World Continuity.
- **Presentation v2.0:** Внедрены поля `confidence` и `possible_causes` в `EmbodiedTraceDTO`. Скрытая травма (хромота) порождает наблюдаемое поведение без утечки ментальных стейтов.
- **World Continuity:** Появилась опция наследия мира между кампаниями (`WorldStateDiff`, `WorldStateApplicator`).
- **UI/UX:** Журнал переведен на вкладки, внедрена механика подслушивания (Eavesdrop). Mood-иконки рисуются строго из наблюдаемых проявлений.
- **Pipeline Repair:** Восстановлена труба исчезновения имени NPC после `idle_tick` (обновление `confidence` перенесено в pre-commit).

### Эпоха 5: Санация и Очистка Долгов (S142)
**Фокус:** Устранение магических чисел, TODO/FIXME, финальная типизация.
- Очищено 34 пустых маркера `TODO:`. Магические числа из `BreakProgressEngine` вынесены в `constants.py`.
- Устранено дублирование цветовой схемы фронтенда (`ui_theme.py`).
- `SocialEngine` начал честно получать `player_distances` от `SpatialQueryService`.

- 🟢 **S143** ENIGMA SELF-HEALING (Уровень 0-2, 7): Внедрена система защиты от тихих отказов. MvpTavernController подписан на TICK_COMPLETED (N2/M-03). TruthState получил discovered_secrets (M-02), ActionCompiler отмечает секреты (M-07/M-08) и применяет delta к фракциям (M-12). N4 (NameError в _fallback_to_astar) и N7 (zombie traversal) исправлены. N3 (ambient routing dead code) и N6 (dup method) исправлены. Добавлен /api/health telemetry dashboard (Уровень 7) для мониторинга mvp_controller.
  Files: backend/app/services/game_loop/__init__.py, backend/app/services/social/mvp_tavern_controller.py, backend/app/services/events/event_types.py, backend/app/services/tick_orchestrator.py, backend/app/services/player_cognition/action_consequence_compiler.py, backend/app/models/truth_state.py, backend/app/api/routes.py, backend/app/services/game_loop/task_scheduler.py, backend/app/services/spatial/movement_engine.py

- 🟢 **S144** ENIGMA V8.3 DAY 1-4 + END-SCREEN FIX (40+ bugs fixed): Закрыты все Critical MVP blockers (V8-SP-1/2, V8-PSY-1..5, V8-MEM-1..3), NPC↔NPC social consequences (V8-SOC-1/3/4), и 30+ quick-fix багов (V8-PSY-7/10/13/14/16/18/19/21/23, V8-MEM-4/5/8, V8-SP-3/4/5/9, V8-SOC-8, V8-TICK-1/5, V8-WL-4/6, V8-MVP-6/8/9/10, V8-FC-01/02). L1Chronicle проброшен через весь конвейер (TickState -> NpcTickPipeline -> StateApplicator). Trauma pipeline, L3 Identity cascade, belief pipeline, attack windup оживлены. SocialDeltaEngine нормализован. Player coords гарантированы. 
  END-SCREEN FIX: Исправлен двойной префикс `/api/api/` в FastAPI (404 Not Found), триггер выхода привязан к южной двери (py >= 12.5), добавлены методы в FallbackGateway.
  CLEANUP: Убран спам `print()` из `game_loop`, `simulation.py`, `movement_engine.py`, `life_engine.py`. Добавлена заглушка `start_session` для VramMonitor.
  IPT 6/6 passed.
  Files: backend/app/services/spatial/graph_compiler.py, movement_engine.py, scene_state_manager.py; backend/app/services/npc/break_progress_engine.py, decision_hub.py, life_engine.py, state_applicator.py, npc_tick_pipeline.py; backend/app/services/phases/decision.py, memory.py, simulation.py; backend/app/services/memory/memory_manager.py, resonance_engine.py; backend/app/services/events/social_subscriber.py; backend/app/services/social/propagation.py, social_deltas.py, social_fabric_tracker.py, mvp_tavern_controller.py; backend/app/services/tick_orchestrator.py; backend/app/services/drf_bus.py; backend/app/services/affective/affective_decay_handler.py; backend/app/services/combat/physiology_decay_handler.py; backend/app/services/player_avatar_service.py; backend/app/services/vram_monitor.py; backend/app/services/game_loop/__init__.py; backend/app/domain/tick.py; backend/app/services/pipeline_runner.py; backend/app/models/npc_state.py; backend/app/services/npc/npc_loader.py; backend/app/api/routes.py; frontend/game_screen.py; frontend/api_client.py

- 🟢 **S145** ENIGMA DIALOGUE THREAD SYSTEM (Этапы 1-4): Внедрена структурная память диалогов. Реплика игрока теперь доходит до STM целевого NPC (BUG-DL-01), а STM не стирается при ходьбе внутри локации (BUG-DL-08). DialogueExecutor инжектит STM-блок для NPC↔NPC (BUG-DL-02). DM-агент получает targeted STM (BUG-DL-03) и L2 Memory (BUG-DL-11). Внедрены Per-pair sessions (BUG-DL-05, ключ `campaign:npc:partner`) и `thread_id` (BUG-DL-04). Реализована отложенная запись реплик в `narrative_cache` (BUG-DL-06) и суммаризация диалога в EventMemory при очистке (BUG-DL-07). TTL реплик переведён на `game_time_seconds` (BUG-DL-12). Добавлен Hard Contract: запрет на вызов LLM без STM (кроме greeting/approach). Добавлен `INV-DIALOGUE-STM` в IPT.
  Files: backend/app/services/memory/memory_manager.py, backend/app/services/memory/dialogue_session.py, backend/app/services/memory/dialogue_update_extractor.py, backend/app/services/memory/dialogue_consolidator.py, backend/app/services/game_loop/dm_phase.py, backend/app/services/game_loop/task_scheduler.py, backend/app/services/events/npc_dialogue_subscriber.py, backend/app/services/execution/dialogue_executor.py, backend/app/services/phases/post_decision.py, backend/app/agents/dm_agent.py, backend/app/domain/communication.py, backend/tests/IPT.py

- 🟢 **S147** WORKPLACE AFFORDANCE CONTRACT (ADR-O-326): Привязка действий NPC к точкам мира через теги `workplace:<npc_id>`. В `NodeRole` добавлены `GUARD_POST`, `DARK_CORNER`, `SERVING_STATION`, `KITCHEN_COUNTER`, `INN_DESK`. В `role_resolver` внедрён приоритет `editor_tags` над keywords. В `life_engine._resolve_position` добавлен поиск персонального рабочего места через `filters=[workplace:npc_id]` с fallback на роль. В `city_gate.json` добавлен узел `guard_post` с тегами. 
  MAP EDITOR UPGRADE: В `data_manager.py` внедрена валидация `_VALID_ROLES` и метод `update_node`. В `editor_core.py` двойной клик по узлу открывает `ModalDialog` с выпадающим списком ролей и полем ввода тегов. Добавлена команда `SimpleNodeUpdateCommand` для Undo/Redo.
  PIPELINE FIX: В `movement_engine._resolve_macro_relocation` восстановлена инициализация `current_pos` и `current_xy` из `npc_positions` (NameError fix). В `event_compiler` добавлена обработка `cross_loc_materialize` (ThickSceneChange с BoundaryResolution), устраняющая дрейф D (Causal Drift) при пересечении границ локаций. 
  TESTS: Добавлен кросс-доменный тест `test_workplace_affordance.py` (JSON → GraphCompiler → SpatialService → LifeEngine).
  Files: backend/app/models/spatial_contracts.py, backend/app/services/spatial/role_resolver.py, backend/app/services/spatial/spatial_service.py, backend/app/services/npc/life_engine.py, backend/app/services/spatial/movement_engine.py, backend/app/services/event_compiler.py, frontend/map_editor/data_manager.py, frontend/map_editor/editor_core.py, frontend/map_editor/undo_manager.py, frontend/map_editor/campaigns/Open_road/locations/city_gate.json, frontend/map_editor/location_templates/city_gate.json, backend/tests/test_workplace_affordance.py

- 🟢 **S146** ENIGMA V8.6 CLOSURE (Days 3-5): Закрыты оставшиеся 17 багов из контракта v8.6 (MEDIUM/LOW). 
  **Spatial (Day 3):** V8-SP-23 (boundary nodes больше не перетирают `location_id`), V8-SP-24 (устранён micro_snap deadlock у boundary node через `NodeRole.BOUNDARY` check), V8-SP-25 (исправлена геометрия `market_square` и adjacency reciprocity), V8-SP-26 (`reinit_campaign` сбрасывает все кэши: `SpatialFactory`, `LifeEngine`, `SpatialRegistry`), V8-SP-28 (`boundary_map` хранит actual node coords), V8-ED-5 (`_rebuild_spatial_registry` использует правильный `campaign_id`).
  **Will/Avatar (Day 4):** V8-WL-6 (`player_pressure` SSOT восстанавливает каузальную integrity ADR-031), V8-WL-7/8 (безопасная загрузка аватара: `WillState` try/except, `trauma_markers`/`body_state` None-guards), V8-WL-9 (полная персистенция FSM state: `recent_failures`, `life_project`, `strain_memory`), V8-PSY-29 (удалён dead code `CalibrationEngine`), V8-PSY-30 (нормализация `event_type` к uppercase в `perception_filter`), V8-PSY-31 (удалена dead variable `gregariousness` в `will.py`).
  **Cleanup (Day 5):** V8-MEM-16 (защита `_identity_cache` от race condition через `threading.RLock`), V8-SOC-8 (удалены мёртвые event types: COMBAT, BETRAYAL, SAVED_LIFE, NPC_INTERACTS_NPC), V8-DLG-15 (удалено мёртвое поле `listener_ids`), V8-DLG-16 (удалён unreachable `except` handler), V8-MVP-23 (добавлен None-check для `_tick_result`).
  IPT 6/6 passed.
  Files: backend/app/services/npc/life_engine.py; backend/app/services/spatial/movement_engine.py, graph_compiler.py, local_traversal_planner.py; backend/app/services/scene_state_manager.py; backend/app/services/game_loop_builder.py; frontend/map_editor/editor_core.py, campaigns/Open_road/locations/market_square.json, city_gate.json; backend/app/services/phases/input.py; backend/app/services/player_avatar_service.py; backend/app/services/tick_orchestrator.py; backend/app/services/npc/perception_filter.py; backend/app/services/will.py; backend/app/services/memory/memory_manager.py; backend/app/services/combat/combat_subscriber.py; backend/app/services/events/reaction_subscriber.py, social_subscriber.py, social_input_projector.py; backend/app/services/execution/dialogue_materializer.py; backend/app/services/events/npc_dialogue_subscriber.py; backend/app/services/game_loop/npc_orchestration.py  

- 🟢 **S148** ТЗ Presentation v2.0 (Спринты P5, P7): Реализована физическая топология тела (BodyTopology) и трёхканальная презентация. Созданы доменные модели `Item`, `BodySlot`, `BodyTopology` (D&D 5e Encumbrance + Bulk System) и YAML-контракт `architecture/body_topology.yaml`. Внедрён `BodyTopologyService` с логикой добавления/удаления/осмотра и сериализацией. `WorldSnapshotDTO` расширен каналами `VisualDTO` и `AudibleDTO`. `PresentationAssembler` теперь собирает визуальные и аудио проявления NPC из `PerceivedSignals`. Обновлён контракт фронтенда (`game_screen.py`) для приёма новых DTO. `scene_state_manager` и `world_state` переведены на использование `player_body_topology`.
  Files: architecture/body_topology.yaml, backend/app/domain/body.py, backend/app/domain/presentation.py, backend/app/services/body/body_topology_service.py, backend/app/services/scene_state_manager.py, backend/app/services/simulation/world_state.py, backend/app/services/perception/presentation_assembler.py, backend/app/services/integration/world_snapshot_builder.py, backend/app/services/phases/integration.py, backend/app/services/game_loop/__init__.py, frontend/game_screen.py

- 🟢 **S149** DRIFT LABORATORY V2 & CAUSAL DRIFT ELIMINATION: 
  **Causal Drift (Class D):** Устранён рассинхрон `is_boundary` между Legacy и Shadow пайплайнами при `cross_loc_materialize`. В `validation.py` вычисление переведено на проверку `cause` из `ThickSceneChange`. В `movement_engine.py` добавлен guard от пустого `target_location_id`. 
  **DriftLaboratory v2:** Внедрён *Valid Comparisons Tracking* (учёт `crashed_ticks`) и *Ground Truth Validator* (проверка `npc_positions` на пустоту и SC-1). Исправлена логика `phase3_ready` (жёсткие критерии: 100k comparisons, 0 C/D/E drift, 0 crashed ticks). Исправлен дефолтный `location_id` в `DriftConfig` (`tavern_silver_wolf` → `tavern`).
  IPT 6/6 passed. DriftLaboratory: 0 D-drift, 0 crashed ticks.
  Files: backend/app/services/phases/validation.py, backend/app/services/spatial/movement_engine.py, backend/tests/sandbox/SUPERBOX/drift_laboratory.py

- 🟢 **S149** INFRASTRUCTURE MVI: PBT + CAUSAL PROBES + DRIFT LAB V2 (Подсистемы 1, 3 + DriftLab):
  **DriftLaboratory v2:** Внедрён *Valid Comparisons Tracking* (учёт `crashed_ticks`) и *Ground Truth Validator* (проверка `npc_positions` на пустоту и SC-1). Исправлена логика `phase3_ready` (жёсткие критерии: 100k comparisons, 0 C/D/E drift, 0 crashed ticks). Исправлен дефолтный `location_id` в `DriftConfig` (`tavern_silver_wolf` → `tavern`).
  **Causal Drift (Class D) Elimination:** Устранён рассинхрон `is_boundary` между Legacy и Shadow пайплайнами при `cross_loc_materialize`. В `validation.py` вычисление переведено на проверку `cause` из `ThickSceneChange`. В `movement_engine.py` добавлен guard от пустого `target_location_id`.
  **Подсистема 1 (PBT):** Внедрена библиотека `hypothesis`. Создан пакет `backend/tests/pbt/` со стратегиями генерации NPC. Реализован property-тест `test_npc_state_roundtrip` (Round-Trip Integrity, §12.2 WARA). PBT интегрирован в `IPT.py` как инвариант `INV-PBT-ROUNDTRIP` (Этап 1.5).
  **Подсистема 3 (Causal Probes):** Внедрён `ProbeRunner` в `TickOrchestrator` (после Фазы 10). Реализована базовая проба `SpatialCoherenceProbe` (SC-1: координаты не 0.0, 0.0) для real-time мониторинга в production.
  IPT: 7/7 passed. DriftLaboratory: 0 D-drift, 0 crashed ticks.
  Files: backend/app/services/phases/validation.py, backend/app/services/spatial/movement_engine.py, backend/app/services/tick_orchestrator.py, backend/app/services/probes/*, backend/tests/sandbox/SUPERBOX/drift_laboratory.py, backend/tests/pbt/*, backend/tests/IPT.py

- 🟢 **S150** DIALOGUE HARD CONTRACT ENFORCEMENT (L4 Silent Failure Elimination):
  Внедрён инвариант `INV-DIALOGUE-SCHEDULER-FAIL` в `IPT.py`, детектирующий тихие провалы диалогов в `TaskScheduler`.
  **Root Cause:** `DecisionHub` генерировал содержательные интенты (`offer_job`, `call_for_help`) для NPC без истории взаимодействий (STM). `DialogueExecutor` честно падал с `DialogueContractViolation`, но `TaskScheduler` глотал ошибку (L4 violation).
  **Fix:** Внедрён перехват в `post_decision.py` (Фаза 6) и `task_scheduler.py`. Если NPC пытается начать содержательный диалог без STM, его интент принудительно понижается до `approach` (установление контакта).
  IPT: 8/8 passed.
  Files: backend/app/services/phases/post_decision.py, backend/app/services/game_loop/task_scheduler.py, backend/tests/IPT.py

- 🟢 **S151** ZOMBIE TRAVERSAL DETECTOR (Подсистема 3 + IPT):
  Внедрена проба `TraversalFSMProbe` в `TickOrchestrator` (real-time мониторинг терминальных статусов `COMPLETED`/`CANCELLED` в `active_traversals`).
  Добавлен инвариант `INV-TRAV-ZOMBIE` в `IPT.py`.
  Это гарантирует соблюдение ADR-TRAV-FSM: завершённые перемещения не могут "зависать" в `scene_state` и блокировать новые маршруты.
  IPT: 9/9 passed.
  Files: backend/app/services/probes/probes/traversal_fsm_probe.py, backend/app/services/tick_orchestrator.py, backend/tests/IPT.py

- 🟢 **S152** DEATH LOCK DETECTOR (Подсистема 3 + IPT):
  Внедрена проба `DeathLockProbe` в `TickOrchestrator` (real-time мониторинг `active_traversals` для NPC с `life_status="DEAD"`).
  Добавлен инвариант `INV-DEATH-LOCK` в `IPT.py`.
  Это гарантирует соблюдение ADR-127: мёртвые NPC не могут двигаться или иметь зависшие перемещения.
  IPT: 10/10 passed.
  Files: backend/app/services/probes/probes/death_lock_probe.py, backend/app/services/tick_orchestrator.py, backend/tests/IPT.py

- 🟢 **S154** THE GREAT WALL OF ENIGMA (Подсистема 3 + AST Linters):
  Внедрена серия AST-линтеров и runtime-проб для защиты архитектурных законов (CAUSAL_CONTRACT v2.0). Все линтеры интегрированы в `IPT.py` и запускаются перед каждым фиксом.
  **AST Linters:**
  1. `INV-WALL-CLOCK` (§15): Запрет `time.time()` в симуляции.
  2. `INV-KERNEL-RNG` (ADR-O-301): Запрет `random.*` в симуляции.
  3. `INV-HP-SSOT` (ADR-HP-UNIFICATION): Запрет прямого присваивания `state.hp`.
  4. `INV-SILENT-FAILURE` (L4): Запрет `except: pass` без логирования.
  5. `INV-SPATIAL-SSOT` (L9): Запрет прямой сборки `SpatialService` вне фабрики.
  6. `INV-FRONTEND-ISOLATION` (§1.1): Запрет импорта `backend.app` во фронтенд.
  7. `INV-EPISTEMIC-BOUNDARY` (§17): Запрет чтения ментальных полей в DM/Verbalization.
  8. `INV-DOMAIN-PURITY` (§1.2): Запрет импорта `services/models` в доменный слой.
  9. `INV-POSITION-MUTATION` (§4.1): Запрет прямой мутации позиции вне `SceneStateManager`.
  10. `INV-L1-APPEND-ONLY` (Rule 28): Запрет удаления событий из `L1Chronicle`.
  11. `INV-NO-RETRO-SIM` (Rule 25): Запрет циклов с вызовами `tick()` (ретро-симуляция).
  
  **Runtime Probes (real-time):**
  1. `SpatialCoherenceProbe` (SC-1): Проверка координат `(0.0, 0.0)`.
  2. `TraversalFSMProbe`: Детектор зомби-перемещений (COMPLETED/CANCELLED).
  3. `DeathLockProbe` (ADR-127): Мёртвые NPC не имеют `active_traversals`.
  4. `L3EphemeralProbe` (L3-P1): L3-проекции не персистятся.
  
  IPT: 20/24 passed (4 CRITICAL debts exposed for other assistants to fix).
  Files: scripts/lint_*.py, backend/app/services/probes/*, backend/tests/IPT.py

- 🟢 **S155** ADR-NET PARSER (Подсистема 4, Этап 4.1):
  Создан парсер `backend/app/services/adr_net/adr_parser.py`, извлекающий ADR-узлы (ID, тип, законы, файлы) из `docs/ADR (Architecture Decision Records).md` (Master Index) и `docs/audits/` (Impact Audits).
  Внедрена нормализация ID (ADR-148, ADR-O-327, ADR-TZ08-1) для устранения дубликатов.
  Парсер интегрирован в `IPT.py` как инвариант `INV-ADR-NET` (граф должен содержать >20 узлов, >10% с файлами).
  IPT: 24/25 passed. 1 CRITICAL debt exposed (Frontend imports).
  Files: backend/app/services/adr_net/__init__.py, backend/app/services/adr_net/adr_parser.py, backend/tests/IPT.py

- 🟢 **S156** REPLAY SYSTEM CORE (Подсистема 2, Этапы 2.1-2.2):
  Создан `ReplayStore` (SQLite backend с WAL mode и zlib-сжатием) для записи каузального следа сессии (`tick_snapshots`, `interventions`, `llm_calls`, `causal_probes`).
  Создан `ReplayRecorder`, подписанный на хуки в `TickOrchestrator` (после Фазы 0 и Фазы 9).
  Внедрён инвариант `INV-REPLAY-STORE` (round-trip тест хранилища).
  IPT: 26/26 passed.
  Files: backend/app/services/replay/__init__.py, backend/app/services/replay/replay_store.py, backend/app/services/replay/replay_recorder.py, backend/app/services/tick_orchestrator.py, backend/tests/IPT.py

- 🟢 **S157** ECONOMY & SOCIAL EMERGENCE (P2/P3 Partial):
  **P2: Emergent Social Drama (DOUBLE TRUTH Elimination):** 
  `ActionConsequenceCompiler` (MVP) now writes `trust`/`fear` deltas directly into `RelationshipStore` (Kernel SSOT). 
  Fixed the disconnect where blackmail/help affected the end-screen tracker but not the core simulation. 
  `DirectiveInterpretationSubscriber` now sees these changes, making NPCs obey out of fear.
  **P3: Economy Contour Activation (Partial):**
  Player avatar now has `tier="major"`, enabling `NeedEngine` to tick hunger for the player in `phase_2_world_tick.py`. 
  `ServiceFactory` now creates an `EconomicProfile` for the player.
  **P1: Balance Fix (BreakProgressEngine):**
  Reduced `BREAK_DELTA_*` constants in `constants.py` to prevent identity integrity from dropping to 0.000 from background stress in 3 days. 
  Added asymptotic decay (`integrity * delta`) to the final stages of breakdown.
  IPT: 27/27 passed. P2 Smoke Test passed.
  Files: backend/app/services/game_loop/__init__.py, backend/app/services/social/mvp_tavern_controller.py, backend/app/services/player_cognition/action_consequence_compiler.py, backend/app/services/game_loop/service_factories.py, backend/app/services/npc/break_progress_engine.py, backend/app/core/constants.py


- 🟢 **S158** UI-EPISTEMIC-01A (Transport Only): Восстановлен потерянный канал данных между Presentation Layer и Frontend. Созданы доменные DTO PerceivedNarrativeDTO и PerceivedManifestationDTO (с разделением perception_certainty и uditory_clarity, без INTERNAL в delivery_type). WorldSnapshotDTO расширен полем perceived_narratives. WorldSnapshotBuilder **транспортирует** PerceivedNarrativeDTO в WorldSnapshotDTO, сохраняя обратную совместимость через LegacyDialogueAdapter. Реализован Telepathy Test, проверяющий эпистемический барьер. PerceptionProjector вынесен в следующий спринт. IPT 30/30 passed.
  Files: backend/app/domain/presentation.py, backend/app/domain/snapshot.py, backend/app/services/integration/legacy_dialogue_adapter.py, backend/app/services/integration/world_snapshot_builder.py, backend/tests/micro/test_telepathy_epistemic_barrier.py
- 🟢 **S159** UI-EPISTEMIC-01B (PerceptionProjector): Реализован честный фильтр восприятия реплик. Создан NarrativeProjector, принимающий изолированный PerceptionContext (игрок, спикеры, профиль аватара) вместо scene_state. Логика искажения текста вынесена в AuditoryDistortionPolicy. Радиусы восприятия вынесены в конфигурационные константы. event_id более не генерируется внутри проектора. NarrativeProjector инжектируется в GameLoop через DI. Создан AvatarPerceptionProfile для изоляции психики. IPT 30/30 passed, Telepathy Test passed.
  Files: backend/app/domain/presentation.py, backend/app/services/perception/auditory_distortion_policy.py, backend/app/services/perception/narrative_projector.py, backend/app/services/game_loop/__init__.py, backend/tests/micro/test_telepathy_epistemic_barrier.py
- 🟢 **S160** UI BIBLE v1.0 (Architecture Document): Сформулирована визуальная доктрина и UX-контракт. Определена композиция экрана (3 слоя: Мир, Фокус, Прикладной UI), иерархия внимания, визуальный язык (палитра, типографика) и тайминги. Введён концепт "Action Markers" для визуализации действий NPC без текста. Спланирован план миграции фронтенда (S161-S165).
  Files: docs/UI_BIBLE_v1.0.md
- 🟢 **S160 (Update)** UI BIBLE v1.0 (Доктрина Внимания): Документ переписан с учётом UX-философии. Введён принцип "Линзы Восприятия" и симметрия эпистемического барьера для аватара (состояния влияют на искажение UI, а не на числа). Задана "Драматургия Внимания" (95% времени в центре сцены, правило 2 секунд). Журнал переосмыслен как инструмент расследования (Наблюдения -> Гипотезы). Введён собственный язык пиктограмм вместо эмодзи.
  Files: docs/UI_BIBLE_v1.0.md
- 🟢 **S160 (Final)** UI DOCTRINE v1.0 (Философия Когнитивного Опыта): Документ переработан и переименован. Введены 3 фундаментальных закона (Мир важнее интерфейса, Никаких абстрактных параметров, Интерфейс никогда не врёт). Добавлены 4 ключевых раздела: Ритм Интерфейса (Tick-Based Choreography), Закон Ненавязчивости, Мультимодальность (без дублирования смыслов) и Стоимость Внимания. Журнал переосмыслен как инструмент расследования ("Что видел -> Что думаю -> Что оказалось правдой"). UI провозглашён полноправным участником симуляции (UI как Актёр).
  Files: docs/UI_DOCTRINE_v1.0.md

- 🟢 **S161** SELF-HEALING SYSTEM IMPLEMENTATION (Levels 0, 1, 5, 7, 10):
  Внедрена многоуровневая система защиты от тихих отказов и архитектурных багов согласно ТЗ ENIGMA_SELF_HEALING_SYSTEM.md.
  
  **Уровень 0 (Silent Failure Eradication):**
  - `scene_init.py`: Тихий `return` при `player_position is None` заменён на `ValueError` (INV-PLAYER-POSITION), если координаты отсутствуют и не могут быть восстановлены. Устранён Silent Failure, приводивший к `coords=None` у игрока (SC-1 Violation).
  - `spatial_runtime.py`: Тихий возврат `(0.0, 0.0)` при ошибке парсинга `local_position` заменён на `ValueError` (INV-SC-1), предотвращая скрытый пространственный дрейф.
  - `game_loop/__init__.py`: `getattr(..., None)` для `spatial_query` (eavesdrop) и `memory_manager._layered` заменены на `RuntimeError`/`TypeError` (Fail Loud).
  - `mvp_tavern_controller.py`: Загрузка `TruthState` защищена `assert` (Fail Loud при None или 0 secrets). Тихий `logger.warning` при пустом `TICK_COMPLETED` payload заменён на `RuntimeError`.
  - `tick_orchestrator.py`, `pipeline_runner.py`, `tick_utils.py`, `phases/decision.py`, `phases/post_decision.py`: `getattr(ctx.shared_context, "spatial_query", None)` и `_memory_mgr` дополнены `logger.debug`/`logger.error` для легальных fallback'ов и обнаружения missing wiring.
  
  **Уровень 5 (Startup Schema Validation):**
  - Создан `backend/app/core/schema_validator.py` — пассивная валидация NPC configs (schedule × activity_map consistency, N9), TruthState и EventBus подписок при старте сервера. Ошибки логируются, но не блокируют запуск (на этапе внедрения).
  
  **Уровень 7 (Telemetry Dashboard):**
  - `routes.py`: `/health` endpoint расширен мониторингом очередей (`pending_tasks`, `active_traversals`) и активными предупреждениями (`warnings`). Статус `DEGRADED` при 🔴 критических проблемах.
  
  **Уровень 10 (Pre-flight Checklist):**
  - Создан `backend/scripts/preflight.py` — 8-этапная проверка перед плейтестом (MVP Controller, TruthState, NPC configs, Spatial registry, Faction IDs, EventBus subscriptions, 5-tick canary). Ловит N1, N2, N8, N9, N12, M-03, R-01 за 5 секунд.
  
  IPT: 30/30 passed. Preflight: 8/8 passed.
  Files: backend/app/services/game_loop/scene_init.py, backend/app/services/spatial/spatial_runtime.py, backend/app/services/game_loop/__init__.py, backend/app/services/social/mvp_tavern_controller.py, backend/app/services/tick_orchestrator.py, backend/app/services/pipeline_runner.py, backend/app/services/tick_utils.py, backend/app/services/phases/decision.py, backend/app/services/phases/post_decision.py, backend/app/core/schema_validator.py, backend/app/main.py, backend/app/api/routes.py, backend/scripts/preflight.py
