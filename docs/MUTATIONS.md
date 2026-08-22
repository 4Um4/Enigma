# MUTATIONS.md — ENIGMA Causal Evolution

> **Формат:** Эпохи → Сессии (S143-S201) → Инварианты. ADRs в `docs/ADR.md`.
> **Path Alias Map (для LLM-контекста):**
> `svc/` = `backend/app/services/` | `dom/` = `backend/app/domain/` | `mod/` = `backend/app/models/`
> `core/` = `backend/app/core/` | `agents/` = `backend/app/agents/` | `api/` = `backend/app/api/`
> `tests/` = `backend/tests/` | `fe/` = `frontend/` | `scripts/` = `scripts/` | `arch/` = `architecture/`
> **Сигнатура:** 🎯 Фокус | ⚙️ Delta (Изменения) | 📁 Файлы

## МЕТА
Сессий: 201 | Доменов: 10 | Статус: Stable (IPT 39/39, 0 drifts) | Аудит: S03-S201

## 0. ENIGMA ONTOLOGY (Context Anchor)
*   **Psyche Layers:** `L0`=Physics/Body, `L1`=Chronicle (append-only SQLite facts), `L2`=Identity/Beliefs (crystalized), `L3`=Drives (ephemeral, per-tick).
*   **Epistemic Boundary:** NPCs only know what they physically perceive (radius/LOS). No telepathy. `target_id` doesn't bypass physics.
*   **Triple Membrane:** Filters L1 facts into L2 beliefs (Physics, Personality, Social).
*   **Pure Reducer:** Tick pipeline must NOT mutate global state; it yields `TickMutation` (deltas) applied later.
*   **Drift:** Desync between shadow/legacy pipelines or state mutations (Class D = spatial desync).
*   **IPT:** Invariant Property Tests (`tests/IPT.py`) - the ultimate AST/Runtime source of truth.
*   **SUPERBOX:** End-to-end causal chain scenario tests (e.g., Belief → Intent → Action → World Event).

---

## 1. ЭПОХИ ЭВОЛЮЦИИ

*   **Эпоха 1 (S04-S82): Каузальный Фундамент.** Убита RPG-математика → `body_state`/`ImpactEngine`. `SpatialService` = SSOT графа. Dual-Time Ontology. DTO-контракт.
*   **Эпоха 2 (S83-S104): Чистота Ядра.** `TickOrchestrator` → `InterventionEvent`. `KernelRNG`. L3 эфемерны, L1 append-only. Epistemic Boundary.
*   **Эпоха 3 (S105-S125): Идентичность.** `BeliefCrystallization`, Тройная Мембрана. Reality-Constrained Agency. `LocalTraversalPlanner` (Z-coords, clearance). D&D 5e Combat RNG.
*   **Эпоха 4 (S126-S141): Презентация.** 5-слойная архитектура. `confidence`/`possible_causes`. World Continuity. UI: Eavesdrop, Mood-иконки из observables.
*   **Эпоха 5 (S142+): Санация.** Удаление TODO/магических чисел. `SocialEngine` ↔ `SpatialQuery`. Epistemic Core (SUPERBOX).

---

## 2. СЕССИИ (S143 — S201)

### S143: Self-Healing (L0-2,7) | ✅
🎯 MVP tick subscription, telemetry.
⚙️ MVP→TICK_COMPLETED; TruthState.secrets; ActionCompiler.factions; /api/health; fixed N3-N7 (routing/traversal).
📁 svc/game_loop, svc/social/mvp, svc/events, svc/tick, svc/player_cognition, mod/truth_state, api/routes, svc/spatial/movement.

### S144: V8.3 Closure + End-Screen | ✅ IPT 6/6
🎯 Закрытие Critical MVP/quick-fix (40+ bugs), оживление пайплайнов.
⚙️ Закрыты V8-SP/PSY/MEM/SOC блокировки. L1Chronicle проброшен через TickState→Applicator. Оживлены Trauma/L3/belief/attack. FastAPI /api/api/ fix. Очистка print-спама.
📁 svc/spatial, svc/npc, svc/phases, svc/memory, svc/events, svc/social, svc/tick, svc/affective, svc/combat, svc/player, svc/pipeline, fe/game_screen.

### S145: Dialogue Threads | ✅
🎯 Структурная память диалогов; запрет LLM без STM.
⚙️ STM persistence; DialogueExecutor STM-injection; per-pair sessions; narrative_cache delay; TTL=game_time; Hard Contract (No STM=No LLM).
📁 svc/memory, svc/game_loop, svc/events, svc/execution, svc/phases, agents/dm, dom/communication, tests/IPT.

### S146: V8.6 Closure | ✅ IPT 6/6
🎯 Закрытие 17 MEDIUM/LOW багов.
⚙️ Spatial (boundary nodes, registry cache); Will/Avatar (SSOT, FSM persist); Cleanup (race conditions, dead code).
📁 svc/npc, svc/spatial, svc/scene, svc/phases, svc/player, svc/memory, svc/combat, svc/events, svc/execution, fe/map_editor.

### S147: Workplace Affordance (ADR-O-326) | ✅
🎯 Привязка действий NPC к точкам мира; апгрейд Map Editor.
⚙️ NPC actions bound to `workplace:<id>`; NodeRole extensions; editor modal; cross_loc_materialize drift fix.
📁 mod/spatial_contracts, svc/spatial, svc/npc/life, svc/event_compiler, fe/map_editor, tests/test_workplace.

### S148: Body Topology (P5/P7) | ✅
🎯 Физическая топология тела и трёхканальная презентация.
⚙️ D&D 5e Encumbrance; BodyTopologyService; VisualDTO/AudibleDTO in WorldSnapshot; PresentationAssembler from PerceivedSignals.
📁 arch/body_topology.yaml, dom/body, dom/presentation, svc/body, svc/scene, svc/simulation, svc/perception, svc/integration, fe/game_screen.

### S149: Drift Lab v2 + PBT + Probes | ✅ IPT 7/7
🎯 Устранение Class D drift, Property-Based Testing, Causal Probes.
⚙️ Valid Comparisons/Ground Truth; Hypothesis PBT (INV-PBT-ROUNDTRIP); ProbeRunner + SpatialCoherenceProbe.
📁 svc/phases, svc/spatial, svc/tick, svc/probes, tests/pbt, tests/IPT.

### S150: Dialogue Hard Contract (L4) | ✅ IPT 8/8
🎯 Детекция тихих провалов диалогов.
⚙️ IPT: `INV-DIALOGUE-SCHEDULER-FAIL`. Fix: DecisionHub intents → `approach` if no STM.
📁 svc/phases/post_decision, svc/game_loop/task_scheduler, tests/IPT.

### S151: Zombie Traversal | ✅ IPT 9/9
🎯 Real-time мониторинг терминальных статусов.
⚙️ TraversalFSMProbe + `INV-TRAV-ZOMBIE`.
📁 svc/probes/traversal, svc/tick, tests/IPT.

### S152: Death Lock | ✅ IPT 10/10
🎯 Запрет движения мёртвых NPC (ADR-127).
⚙️ DeathLockProbe + `INV-DEATH-LOCK`.
📁 svc/probes/death, svc/tick, tests/IPT.

### S154: The Great Wall (AST Linters) | ✅ IPT 20/24
🎯 CAUSAL_CONTRACT v2.0; AST-линтеры и runtime-пробы.
⚙️ 11 AST linters (Clock, RNG, HP, Silent, Spatial, FE-Isolation, Epistemic, Domain, Pos-Mut, L1, Retro); 4 Runtime probes.
📁 scripts/lint_*, svc/probes, tests/IPT.

### S155: ADR-Net Parser | ✅ IPT 24/25
🎯 Авто-извлечение ADR-графа из документации.
⚙️ Парсер docs/ADR; `INV-ADR-NET`.
📁 svc/adr_net, tests/IPT.

### S156: Replay Core | ✅ IPT 26/26
🎯 Запись каузального следа.
⚙️ SQLite WAL ReplayStore; ReplayRecorder hooks; `INV-REPLAY-STORE`.
📁 svc/replay, svc/tick, tests/IPT.

### S157: Economy & Social (P2/P3) | ✅ IPT 27/27
🎯 Двойная истина в социальном слое; контур экономики.
⚙️ Double Truth eliminated (ActionConsequence→RelationshipStore); Player avatar tier=major; BreakProgressEngine asymptotic decay.
📁 svc/game_loop, svc/social, svc/player_cognition, svc/npc/break, core/constants.

### S158: UI-Epistemic-01A (Transport) | ✅ IPT 30/30
🎯 Восстановление канала Presentation ↔ Frontend.
⚙️ PerceivedNarrativeDTO/ManifestationDTO; LegacyDialogueAdapter; Telepathy Test.
📁 dom/presentation, dom/snapshot, svc/integration, tests/micro/telepathy.

### S159: UI-Epistemic-01B (Projector) | ✅ IPT 30/30
🎯 Честный фильтр восприятия реплик.
⚙️ NarrativeProjector + AuditoryDistortionPolicy; AvatarPerceptionProfile.
📁 dom/presentation, svc/perception, svc/game_loop, tests/micro/telepathy.

### S160: UI Doctrine v1.0 | ✅
🎯 Философия когнитивного опыта.
⚙️ 3 слоя (Мир, Фокус, UI), Action Markers, Линза Восприятия, Драматургия Внимания.
📁 docs/UI_DOCTRINE_v1.0.

### S161: Self-Healing + UI Layers | ✅ IPT 30/30
🎯 L0-L10 защита от тихих отказов; разделение UI на 3 слоя.
⚙️ L0: ValueError вместо тихих fallback. L5: Schema validator. L7: /health. L10: preflight.py. UI: `game_screen` → Analysis(S3), Focus(S1), Scene(S0).
📁 svc/game_loop, svc/spatial, svc/social, svc/tick, svc/phases, core/schema_validator, scripts/preflight, fe/renderers.

### S162: UI Epistemic Integration | ✅ IPT 26/30
🎯 Подключение PerceivedNarrativeDTO к рендеру.
⚙️ FocusRenderer: прозрачность/цвет зависят от auditory_clarity/delivery_type.
📁 fe/game_screen, fe/focus_renderer.

### S163: UI Action Markers | ✅ IPT 27/30
🎯 Закон Локальности и Временности.
⚙️ Монохромные геометрические иконки над NPC (activity).
📁 fe/game_types, fe/game_screen, fe/focus_renderer.

### S164: UI Redesign HUD | ✅ IPT 26/30
🎯 Закон Минимального Вмешательства.
⚙️ Текстовая панель статуса → геометрические мини-иконки (форма=тип, цвет=тяжесть).
📁 fe/analysis_renderer.

### S165: UI Polish (Animations) | ✅ IPT 27/30
🎯 Ритм Интерфейса.
⚙️ Плавные кривые Fade-in/out для Speech Bubbles и Action Markers.
📁 fe/focus_renderer.

### S166: UI Journal | ✅ IPT 27/30
🎯 Закон Расследования.
⚙️ Вкладки: Наблюдения → Гипотезы → Факты.
📁 fe/analysis_renderer, fe/game_screen.

### S167: UI NPC Activity | ✅ IPT 30/30
🎯 Визуализация действий (синусоидальные микро-анимации).
📁 fe/focus_renderer.

### S168: UI Manifestation | ✅ IPT 30/30
🎯 Визуализация физики тела (pose_tense, gaze_avoidance).
📁 fe/game_types, fe/game_screen, fe/scene_renderer.

### S169: UI Perception | ✅ IPT 30/30
🎯 Закон Эпистемической Честности (рваный текст, эффект «незнакомца»).
📁 fe/focus_renderer, fe/scene_renderer.

### S170: UI Attention | ✅ IPT 29/30
🎯 Закон Внимания (сдвиг камеры при SLAM, белая рамка).
📁 fe/game_screen, fe/focus_renderer.

### S172: CI & Mypy Strict | ✅ IPT 30/30
🎯 Готовность CI, строгая типизация, L4 TaskScheduler fix.
⚙️ Workflow move; mypy.ini; TYPE_CHECKING imports; TaskScheduler try/except; SpeechScheduler latency 2.0→0.1.
📁 .github/workflows, mypy.ini, core/calendar, mod/spatial, svc/scene, svc/spatial, svc/game_loop/task, svc/game_loop/speech.

### S174a: Infra Longevity MVI | ✅ IPT 30/30
🎯 Завершение инфра-ТЗ (PBT, Replay, Probes).
⚙️ PBT validators; Replay LLM Cache wiring; Probes (CausalProvenance, HistoricalConstraint, TemporalIsolation); /api/probes/dashboard.
📁 tests/pbt, svc/replay/llm_cache, svc/probes, svc/adr_net, svc/tick, svc/dto, api/routes.

### S174b: Visual Casting Audit | ✅ IPT 30/30
🎯 Рефакторинг портретов в data-driven архитектуру.
⚙️ ExpressionResolver; VisualCastingRepository; PortraitRenderer (чистый рендер).
📁 fe/expression_resolver, fe/visual_casting_repository, fe/portrait_renderer, fe/game_screen.

### S175: Visual Casting Editor | ✅ IPT 30/30
🎯 Авторский инструмент для визуальной режиссуры.
⚙️ Редактор правил (expression_id, priority, asset, evidence) напрямую в JSON.
📁 fe/map_editor/data_manager, fe/map_editor/editor_core.

### S176: WorldTick Temporal Ownership (ADR-O-344) | ✅ IPT 31/31
🎯 Суверенитет TickOrchestrator над временем (Закон Единичного Времени).
⚙️ Устранён O(N²) дрейф (idle_tick loop); L1Chronicle DELETE убран; GraphCompiler wall-cross warning.
📁 svc/game_loop, svc/tick, svc/npc/l1, svc/spatial/graph, tests/IPT.

### S177: Bugfix V.0.5.3.7.3 | ✅ IPT 31/31
🎯 Исполнение критических фиксов.
⚙️ IPT import fix; DialogueExecutor soft-degradation; Duplicate turns fix; Router dead code; DM fallback message.
📁 tests/IPT, svc/execution, svc/events, svc/llm, agents/dm, core/constants.

### S178: Pytest Recovery | ✅ IPT 31/31
🎯 Починка тестов и поиск первопричины Temporal Isolation.
⚙️ PipelineContext contract; entry_node hint; StateApplicator mutation (зафиксировано как долг S1).
📁 svc/game_loop, svc/event_compiler, svc/phases/traversal, tests/sandbox/micro, tests/pbt, tests/test_spatial.

### S179: S1: Pure Reducer (ADR-O-346) | ✅ IPT 31/31
🎯 Устранение мутации TickState внутри NpcTickPipeline.
⚙️ StateApplicator убран из Pipeline; pc_deltas из DecisionResult; TickState hash изолирован от side-effects.
📁 svc/npc/npc_tick_pipeline, svc/tick.

### S180: S2: Entity Cardinality (ADR-O-347) | ✅ IPT 32/32
🎯 Однократная обработка NPC за тик; изоляция сцен.
⚙️ Фильтрация по location_id ДО сборки TickState; `INV-SCENE-ENTITY-ISOLATION`.
📁 svc/tick, tests/IPT.

### S181: S3: Causal Ordering (ADR-O-348) | ✅ IPT 33/33
🎯 Независимость от порядка обработки NPC.
⚙️ `INV-EVENT-CARDINALITY`; структурная независимость Pipeline подтверждена.
📁 tests/IPT.

### S182: S4: Semantic Pipeline (ADR-O-349) | ✅ IPT 34/34
🎯 Детерминированный мост Intent ↔ Domain Event.
⚙️ EventType расширен; IntentEventAdapter; `INV-INTENT-EVENT-COMPLETENESS`.
📁 svc/events/event_types, svc/events/intent_event_adapter, tests/IPT.

### S183: S5: Dialogue & Travel FSM (ADR-O-350) | ✅ IPT 36/36
🎯 Гарантия терминальности FSM.
⚙️ `INV-TRAV-TERMINALITY`; `INV-DIALOGUE-LIVENESS`.
📁 tests/IPT.

### S184: S7: Replay Determinism (ADR-O-351) | ✅ IPT 37/37
🎯 Готовность инфраструктуры реплея.
⚙️ `INV-REPLAY-DETERMINISM` (WARNING).
📁 tests/IPT.

### S185: S7: Load Integrity (ADR-O-352) | ✅ IPT 38/38
🎯 Целостность Save/Load.
⚙️ `INV-SAVE-LOAD-INTEGRITY` (прогон 3 тиков + load_scene_at).
📁 tests/IPT.

### S186: Foundation Fortification | ✅ IPT 39/39
🎯 Строгие законы кардинальности.
⚙️ P0-1: Tick Cardinality; P0-2: NPC Cardinality; P1-5: Commit Cardinality (atomic_commit_all); P1-6: EventBus Cardinality; P1-7: Dialogue Causal Loop.
📁 svc/tick, svc/state, svc/scene, tests/IPT.

### S187: Epistemic Core Discovery (SUPERBOX-001) | ✅
🎯 Обнаружение слепоты к Proposition.
⚙️ Доказана необходимость Proposition Layer (trust listener→speaker != trust listener→third_party).
📁 tests/sandbox/SUPERBOX.

### S188: Proposition Layer (SUPERBOX 002-013) | ✅
🎯 Epistemic Core и мембрана убеждений.
⚙️ Созданы Proposition, ClaimEvent, EpistemicRecord/Store/Context. BeliefRevisionEngine. DecisionHub изолирован от Store (принимает Dict модификаторов). Доказан Modifier Contract.
📁 dom/epistemology, dom/decision_context, svc/npc/epistemic*, svc/npc/decision_hub, svc/events/claim*, tests/SUPERBOX.

### S189: Arch-Sleep: Bodily Coupling | ✅ IPT 39/39
🎯 Сон как эмерджентное свойство телесной архитектуры.
⚙️ CouplingResolver; ActiveCommitment (блокировка проактивных интентов); Sleep Onset (arousal); Perception Modulation; DreamSignal/Residue.
📁 dom/body, svc/events, svc/npc/coupling, svc/npc/dream, svc/npc/sleep, svc/phases/integration, svc/cfrm.

### S190a: SUPERBOX-005 (Modifier Attribution) | ✅ IPT 39/39
🎯 Математическая атрибуция эпистемического модификатора.
⚙️ `final_score = base_score + epistemic_modifier`; scores_trace_map пробрасывается для всех NPC.
📁 dom/epistemology, svc/npc/epistemic_context, dom/tick, svc/npc/npc_tick, svc/pipeline, tests/SUPERBOX.

### S190b: Self-Healing Closure (P0-P4) | ✅ IPT 39/39
🎯 Закрытие 5 «дыр» самоисцеления.
⚙️ P0: CI Gates; P1: Doc Drift validator; P2: AST Plugin (439 noqa подавлены); P3: Live Dashboard; P4: E2E Canary. Bugfixes: idle_tick None, pipeline_context, mvp_tavern.
📁 .github, scripts/validate*, scripts/lint*, scripts/test*, api/routes, svc/game_loop, mod/pipeline_context, svc/social/mvp.

### S191: SUPERBOX-006 (Attribution Isolation) | ✅ IPT 38/39
🎯 Строгая изоляция эпистемической атрибуции.
⚙️ Доказано: EpistemicContext ортогонален base_score.
📁 tests/SUPERBOX/epistemic_isolation.

### S192: SUPERBOX-007 (Observation Divergence) | ✅ IPT 38/39
🎯 Расхождение наблюдений (радиус слышимости).
⚙️ ClaimEventSubscriber использует SpatialQueryService для обновления убеждений всех NPC в HEARING_RADIUS.
📁 svc/events/claim, svc/game_loop, tests/SUPERBOX.

### S192.1: SUPERBOX-008 (Membrane Hardening) | ✅ IPT 38/39
🎯 `target_id` не является телепатическим обходом.
⚙️ Убрано безусловное добавление target_id в _listeners.
📁 svc/events/claim, tests/SUPERBOX.

### S193: SUPERBOX-009 (Serialization) | ✅ IPT 38/39
🎯 Сериализационная персистентность EpistemicRecord.
⚙️ Адаптеры to_dict/from_dict в EpistemicStore; проброс в scene_state.
📁 svc/npc/epistemic_store, svc/tick, tests/SUPERBOX.

### S194: SUPERBOX-010 (Decision Divergence) | ✅ IPT 38/39
🎯 Убеждение как причинная переменная Intent.
⚙️ Одинаковый мир + убеждение меняют Intent (idle → talk/warn). EventBus clear() для изоляции.
📁 svc/events/event_bus, tests/SUPERBOX.

### S195: SUPERBOX-011 (Action Causation) | ✅ IPT 38/39
🎯 Epistemic → QueuedTask через Universal Task Layer.
⚙️ Цепь: belief → Context → DecisionHub → QueuedTask.
📁 tests/SUPERBOX.

### S196: SUPERBOX-012 (World Event Causation) | ✅ IPT 38/39
🎯 Убеждение → реальное событие мира без LLM.
⚙️ TaskScheduler routing fix; phases/integration schema drift fix; EventBus clear().
📁 svc/game_loop/task, svc/phases/integration, svc/events/event_bus, tests/SUPERBOX.

### S198a: SUPERBOX-013 (Second-Order Observation) | ✅ IPT 39/39
🎯 Замыкание каузальной петли второго порядка.
⚙️ Агент А (WARN) → materialization → Агент В обновляет Store. EpistemicContextResolver modifier 1.5x.
📁 svc/npc/epistemic_context, svc/game_loop/task, svc/execution/dialogue, docs/RECOVERY.

### S198b: Фаза 8.1 — Социальный слой и End-Screen | ✅
🎯 Детерминированные соц. последствия, FateTracker, End-Screen.
⚙️ SocialSubscriber fallback (trust/fear); FateTracker (stability/threat/BROKEN); EndScreenNarrator (текстовый нарратив).
📁 svc/execution/dialogue_materializer, svc/events/social, svc/social/mvp, svc/social/end_screen*, mod/end_screen, api/routes, fe/end_screen, fe/i18n.

### S199: Фаза 8.2 — Epistemic-002 и Триггеры | ✅ IPT 39/39
🎯 Trust-зависимая надёжность; динамика безумия; UI убеждений.
⚙️ TrustBasedReliabilityProvider; SocialSubscriber (gossip/accuse/praise); FateTracker BROKEN (5 critical ticks); UI вкладка «Мои убеждения».
📁 svc/events/social, svc/social/mvp, fe/analysis, fe/settings, svc/integration, docs/ADR-O-357.

### S200: Фаза 8.3 — Epistemic Store (Player) | ✅ IPT 39/39
🎯 Игрок как полноправный наблюдатель; детерминированные пропозиции.
⚙️ ClaimEventSubscriber → NPC_SPOKE; fallback Proposition mapping; игрок в Store; BeliefRevision max(0.0) guard.
📁 svc/events/claim, svc/npc/belief, svc/game_loop, docs/ADR-O-358.

### S201: Фаза 8.3 — Runtime Epistemic Closure | ✅
🎯 Доказательство runtime-замкнутости каузальной петли игрока.
⚙️ Bugfix: max(0.0) при создании нового убеждения; SUPERBOX-014 (player belief); SUPERBOX-015 (full causal pipe without manual subs).
📁 svc/npc/belief, tests/SUPERBOX/epistemic_player, tests/SUPERBOX/epistemic_closure.

### S202: Epistemic Core Gate (First-Order) | ✅ IPT 40/41
🎯 Доказательство замыкания полного production causal loop первого порядка (WORLD TRUTH → BELIEF → DECISION → ACTION → WORLD CHANGE) через реальный `GameLoop`.
⚙️ Исправлен production bottleneck: `WARN` и другие claim-producing интенты больше не понижаются до `approach` из-за отсутствия STM (создан `intent_profiles.py`). `BeliefRevisionEngine` восстановлен к first-order убеждениям (убран преждевременный Second-Order ToM `ASSERTS`). Создан и успешно пройден тест `SUPERBOX-EPISTEMIC-PRODUCTION-001` (Control vs Treatment, Save/Load Persistence).
📁 dom/intent_profiles, svc/npc/belief_revision, svc/phases/post_decision, svc/game_loop/task_scheduler, svc/execution/dialogue_executor, tests/SUPERBOX/scenarios/epistemic_production_test.

### S203: Фаза 8.3 — TaskScheduler Epistemic Closure (SUPERBOX-016) | ✅
🎯 Доказательство полной рантайм-трубы: TaskScheduler → DialogueExecutor → Materializer → EventBus → EpistemicStore[player].
⚙️ Bugfix: `intent_type` не передавался в `Artifact.data` в `DialogueExecutor`, из-за чего `DialogueMaterializer` публиковал `NPC_SPOKE` с `intent_type="talk"`, и fallback в `ClaimEventSubscriber` не срабатывал. Маппинг `subject_id`/`object_id` для `intimidate`/`attack` исправлен (`speaker` нападает на `target`). Создан `SUPERBOX-016`.
📁 svc/execution/dialogue_executor, svc/events/claim_event_subscriber, tests/SUPERBOX/scenarios/epistemic_scheduler_closure.

### S204: Фаза 8.3 — Epistemic Invariants & ADR-Net Sanitation | ✅ IPT 44/44
🎯 Финальное замыкание Фазы 8.3. Внедрение инвариантов эпистемической честности и починка ADR-Net парсера.
⚙️ Добавлены 3 новых инварианта в IPT: `INV-PLAYER-EPISTEMIC-CLOSURE` (публикация NPC_SPOKE обновляет EpistemicStore[player]), `INV-EPISTEMIC-TRUST-MONOTONICITY` (trust монотонно влияет на reliability), `INV-EPISTEMIC-TRUTH-IMMUTABILITY` (ClaimEvent не мутирует World Truth).
⚙️ Массовая санация `docs/audits/`: созданы скрипты `scripts/fix_adr_headers.py` и `scripts/fix_adr_files.py`. Все 157 файлов ADR приведены к стандарту парсера (заголовок `ADR-XXX [TYPE] **Title**` и секция `Files:`). `INV-ADR-NET` полностью зелёный.
📁 backend/tests/IPT.py, scripts/fix_adr_*.py, docs/audits/*.

### S205: Semantic Torture Test Pass (S203 Completion) | ✅ IPT 41/41
🎯 Доведение S203 (Natural Language Torture Test) до целевых метрик без хардкода.
⚙️ `LLMCompressorClient` промпт расширен 26 Few-Shot Examples (покрытие идиом и косвенной речи). `PropositionMatcher` в `legacy_bridge.py` переведён на `SequenceMatcher` (Embedding Similarity stub). Тестовый датасет `semantic_torture_test.py` расширен до 50+ фраз на категорию. Метрика Intent Preservation достигла 88.0% (цель 85%), Causal Class Equivalence — 86.9% (INTIMIDATE 95.9%). Регрессий IPT не обнаружено (41/41 passed).
📁 svc/input/llm_compressor_client, svc/player_cognition/legacy_bridge, tests/sandbox/SUPERBOX/scenarios/semantic_torture_test.

### S206: ADR-O-357 Enforcement — Canonical Testimony Reliability | ✅ IPT 44/44
🎯 Устранение Double Truth в reliability: инлайн-провайдер удалён, канонический TrustBasedReliabilityProvider вживлён в живой контур.⚙️ Archæology: обнаружены dead-code провайдер (с NameError-опечаткой), дубль в IPT.py, сцепление инварианта с инлайном. Гейт: SUPERBOX-RELIABILITY-BASELINE (BEFORE/AFTER, предрегистрированная delta-матрица; semantic delta только в градуации врага: cross-confirm −31→0.786, −50→0.514, −100→0.0). Атомарный коммит: 7 патчей (game_loop, subscriber, IPT, SUPERBOX 014/015/016, harness). Prior незнакомца = 50 (константа). Долги: DEBT-R1 (radius 999.0 THEFT), DEBT-R4 (except в подписчике), DEBT-R6 (изоляция SUPERBOX-сценариев).📁 svc/npc/trust_based_reliability_provider, svc/events/claim_event_subscriber, svc/game_loop/init, tests/IPT, tests/sandbox/SUPERBOX/scenarios/*, docs/audits/ADR-O-357_IMPACT.md
⚠️ Anti-race protocol: номер S205 взят как max(известных)+1 по контексту (S204 последний). Перед записью сверь фактический хвост MUTATIONS.md — если параллельная сессия заняла номер, сдвинь и обнови ссылки в Addendum.
IPT: ✅ 44/44 (гейт-прогон). КРАСНЫЕ ИНВАРИАНТЫ: было 0 🔴 → стало 0 🔴

### S207: Phase C — Observation Channel & Source-Weighted Reliability (ADR-O-360) | ✅ IPT 44/44
🎯 Второй канал убеждений: THEFT → LOS-свидетели → EpistemicStore (direct_observation). Testimony и observation на одном движке ревизии.
⚙️ ObservationSubscriber (новый, мембрана visibility+дистанция — event.radius игнорируется); context-ветка TrustBasedReliabilityProvider (DIRECT_OBSERVATION_RELIABILITY=0.9); revise(+reliability_context, проброс). Инцидент: двойное применение патча → фантомный импорт → ImportError проглочен try/except (DEBT-R5) → тихая смерть ядра → поймано INV-PLAYER-EPISTEMIC-CLOSURE (2 CRITICAL) → фиксом-дедупликацией. Номера: ADR-O-360 (O-359 занят), S207. SUPERBOX-OBSERVATION 5/5 (T1 0.9; T2 no-telepathy дистанция; T3 truth-immutability; T4 same-source буст; T5 вражеский cross-confirm 0.7143 точной формулой). Формат spatial_walls/spatial_obstacles верифицирован (T2b).
📁 svc/events/observation_subscriber, svc/npc/trust_based_reliability_provider, svc/npc/belief_revision_engine, svc/game_loop/__init__, tests/sandbox/SUPERBOX/scenarios/epistemic_observation_test, docs/ADR (атлас L14.4), docs/audits/ADR-O-360_IMPACT.md

### S208: P0 Avatar Ownership + DEBT-R4 | ✅ IPT 44/44
🎯 Восстановление canonical ownership model NPCState аватара игрока. P0: диалог с NPC падал «Direct write to NPCState.body_state» (guard NPCState.setattr / _ALLOWED_WRITERS). Закрытие DEBT-R4 (per-listener изоляция belief revision).⚙️ Археология: guard caller-based; construction легален (self-write), содержимое dict не охраняется (DEBT-R9). Триггер: avatar_service пост-конструкционные дефолты (default-ветка падала с Stage 0 Task 0.4 — психика аватара всегда жила на getattr-дефолтах потребителя); латентно: game_loop write-back:1777; phase_6 культура object.setattr (DEBT-R8). SHI-FIX psyche/drives — мёртвый код (save не пишет / load не читает / дефолты потребителя идентичны) — удалён; аватарная психика = DEBT-R10 (vertical slice). Введён AvatarStateApplicator (whitelist узко: body_state/stress/emotion); GameLoop → оркестратор, не писатель; phase_6 мигрирован; DISABLED-ветка game_loop:1787 была достижима только через нарушение — сохранена в applicator с честным входом. P0-D: ArchitecturalViolationError различим (critical-лог [ARCH_VIOLATION]) до деградации. Guard-дисциплина доказана: поймал прямую запись в самом SUPERBOX-тесте (T3 fix). DEBT-R4: per-listener try/except в on_claim_event, smoke-доказано. SUPERBOX-AVATAR-SYNC 5/5. Досье: R7 (WARN-монокультура), R8, R9, R10.📁 svc/avatar_state_applicator (новый), svc/player_avatar_service, svc/game_loop/init, svc/game_loop/phase_6_avatar, models/npc_state (_ALLOWED_WRITERS + ADR-комментарий), svc/events/claim_event_subscriber, tests/sandbox/SUPERBOX/scenarios/avatar_ownership_sync_test

### ⚛️ V0.5.3.8.3 — FOUNDATION FREEZE (после S208)
Epistemic Core production path стабилизирован (S206: canonical testimonyreliability; S207: Observation Channel, два источника знания); Avatarownership восстановлен (S208); runtime mutation discipline доказана.Дальнейшее развитие переносится из архитектурного доказательства вGAMEPLAY VERTICAL SLICE.

### S209: Vertical Slice, звено 1 — NPC Agency: Steal (ADR-O-361) | ✅ IPT 44/44
🎯 Первое эмерджентное действие NPC: Shadow может решить украсть сам. Цепь мотив→кража→свидетельство→вера работает без единой инъекции.
⚙️ Intent.STEAL (PROACTIVE) + unlock-ветка _is_intent_available (R6.3 — движок ждал первого потребителя) + _steal_affinity (archetype=thief→0.8 × desire; commoner→0.08; без npc_id-хардкодов). Маршрутизатор Фазы 6: windowed=(attack|steal) — steal не утекает в диалоговый слой. Windup 2 тика (STEAL_WINDUP_DURATION_TICKS; окно обнаружения). Фаза 7: object-action цель (кража целит в объект). Маппинг steal→THEFT (source=вор, whisper-radius честный). SUPERBOX-AGENCY-STEAL 6/6 (opportunity-гейт, контроль натуры, маршрутизация, материализация, эмерджентное Goran-замыкание belief=0.9, no-telepathy). DEBT-R3 закрыт. Инциденты: двойной патч, фантомная _intent_val, placeholder-скоринг, 3× ExposureLevel-угадывание, маршрутизатор-пожиратель — все пойманы (Pylance/сквозной тест), уроки в ADR-O-361_IMPACT.
📁 models/npc_state (Intent.STEAL), svc/npc/decision_hub (affinity, unlock), svc/phases/post_decision (маршрутизатор, gate, Фаза 7 object-action), svc/events/intent_event_adapter (маппинг), dom/intent_profiles, core/constants, tests/sandbox/SUPERBOX/scenarios/agency_steal_test

### S210: Vertical Slice, слой 2 — Perception Topology (R1/R2) + L1-P0 | ✅ IPT 44/44
🎯 Честная мембрана действий игрока: SSOT-таблица ACTION_PERCEPTION_RADIUS (сестра ACTION_INTENSITY); симметрия честности — кража игрока тиха, как кража Shadow (3.0 = whisper). P0: гонка sqlite-транзакций (TOCTOU in_transaction→commit при check_same_thread=False) — RLock-сериализация; TICK_CRASH исчез из двойных прогонов.⚙️ action_perception_radius() SSOT-резолв (unknown→15.0, не 999 — ADR-148); phase_1_input обе точки патчены; reaction_subscriber fallback→WARNING (наблюдаемость телепатии); SUPERBOX-PERCEPTION-TOPOLOGY 4/4 (таблица, симметрия, AST-гвард, двойная мембрана: radius-канал + sight-канал — stealth ≠ невидимость). ИНТЕГРАЦИОННЫЕ КОЛЛИЗИИ параллельной сессии: (1) Causal Ledger вставка разорвала post_init npc_state — сироты удалены, чужой блок сохранён, текст intent-валидации теперь чужой (семантика идентична); (2) Calibration Lab idle_tick-цикл — Rule 25 формализован: песочница с чистого старта ≠ ретро-симуляция живой камеры, SANDBOX_WHITELIST в lint_retro_simulation. Досье: R5 (TICK_CRASH проглатывается орковым except — решение о громкости отложено).📁 dom/constants (ACTION_PERCEPTION_RADIUS), svc/game_loop/phase_1_input, svc/events/reaction_subscriber, svc/memory/sqlite_store (RLock), models/npc_state (фикс сирот), scrip

### S211: Vertical Slice, слои 3-4 — Характеры + Player Epistemic Action | ✅ IPT 43/44 (1 чужой)
🎯 Слой 3 (R7): монокультура WARN мертва — один belief → разные действия по натуре (guard→REPORT 1.89, maid→RUMOR 1.755, merchant→WARN, thief молчит). Слой 4 (R10/§18): убеждение игрока = способность — ACCUSE-гейт на EpistemicStore через resolver (conf ≥ 0.5); слабый слух блокирует; ЛОЖНОЕ обвинение проходит (вера ≠ истина, различие эмерджентно).⚙️ Слой 3: EPISTEMIC_DISPOSITIONS (доменная таблица, калибруема, табу npc_id-хардкодов) + to_modifiers(+archetype, легаси-ветка байт-в-байт S198) + проброс profile_l0.archetype (pipeline:496, единственный вызов). Слой 4: ActionType.ACCUSE + ACCUSE-first распознавание + get_confidence_for_subject (resolver — граница чтения) + гейт в ActionConsequenceCompiler (инъекция late-binding set_epistemic_resolver; mvp_controller) + ветка последствий (fear+25/trust−15, TruthState не трогается — истинность решают NPC). §18 Law of Singular Epistemic Authority (Устав). АРХЕОЛОГИЧЕСКОЕ ОТКРЫТИЕ: параллельная belief-система игрока (PlayerBeliefModel + ObservationLog/Evidence) — старый прототип gameplay-projection; судьба — DEBT-E1 (authority→projection, 6 шагов, пост-slice; мост Proposition↔secret_id НЕ строится — схлопывание богатой модели в флаг = грех класса S206). SUPERBOX-DISPOSITIONS 6/6, SUPERBOX-ACCUSATION 5/5. Инциденты: сеттер разорвал конструктор компилятора (якорь-присвоение + def — урок: якорь обязан включать хвост метода; py_compile не ловит); атрибут mvp_controller (не _mvp). Чужой красный: calibration:327 except:pass (SILENT-FAILURE) — контекст не предоставлен, долг CAL-1.📁 АРХИТЕКТУРНЫЙ_УСТАВ (§18), dom/epistemic_dispositions, models/player_action (ACCUSE), svc/npc/epistemic_context_resolver, svc/npc/npc_tick_pipeline, svc/player_cognition/action_semantic_resolver, svc/player_cognition/action_consequence_compiler, svc/game_loop/init (инъекция), tests/.../epistemic_dispositions_test, tests/.../accusation_gate_test

### S212: Stage 0 & Stage 1 — Foundation Freeze + Causal Spine | ✅ IPT 44/44
🎯 Полное исполнение ТЗ `ENIGMA_TZ_Stage0_Stage1_Foundation_Freeze.md`. Упразднена двойная истина состояния (Stage 0), внедрена причинная цепочка и детерминированный реплей (Stage 1).
⚙️ Stage 0: Упразднён whitelist `_RUNTIME_TOP_LEVEL_KEYS` (Task 0.2). `JsonPersistenceAdapter` bypass закрыт, всё через `atomic_commit` (Task 0.3). Внедрён `ArchitecturalViolationError` и guard `__setattr__` в `NPCState` (Task 0.4). Мигрированы writers в `NPCState.beliefs` на `BeliefTransitionEngine.commit` (Task 0.5, 0.6). Создан `update_relationships` API в `StateApplicator` (Task 0.7). Устранены прямые мутации `_avatar.body_state` (Task 0.8). Прямые мутации `NPCState` заменены на `object.__setattr__` (Task 0.9). Упразднён параллельный WorldTick-путь `phase_2_world_tick.py` (Task 0.10), `write_to_legacy` переименован в `to_persistence_dict`.
⚙️ Stage 1: Внедрён `WorldSnapshot` в `TickOrchestrator` (Task 1.3). Добавлены `Cause` и `MissingProvenanceError` в `StateApplicator.apply` (Task 1.2). Добавлены методы `query_ledger` и `trace_causal_chain` в `NPCState` (Task 1.4). Добавлен `PerceptualKernel.can_observe` (Task 1.5). Детерминизм подтверждён DriftLaboratory (0.0% drift, Task 1.1).
📁 models/npc_state, models/psychological, services/npc/state_applicator, services/npc/npc_loader, services/npc/belief_transition_engine, services/scene_state_manager, services/game_loop/phase_2_world_tick, services/events/claim_event_subscriber, services/tick_orchestrator, errors.py, tests/test_stage0_and_1_invariants.py

### S213: Лаборатория калибровки психики — M0 Fundament (ADR-O-361) | ✅ IPT 44/44
🎯 Фундамент Psychology Calibration Laboratory (ТЗ Лаборатории v1.0, План M0): подмена параметров, headless-эксперименты на реальном конвейере, пассивное наблюдение, 5 метрик, контрольные пресеты зон.
⚙️ Артефакты: config_overlay (identity-патч from-import биндингов decision_hub + verify вход/выход, запрет вложенности — тихая ложь экспериментов исключена); preset_io (строгий валидатор: [PLAN]-параметры и taboo ADR-O-360 → громкий отказ) + пресеты mannequin/chaos/enigma_golden; preset_materializer (temp-копия config/npc, патч npc_overrides, прямой редирект npc_loader._CONFIG_NPC_ROOT + поведенческая верификация реальным загрузчиком); experiment_runner (чистый старт = пустой temp-saves, offline MockProvider, restore настроек/диска/RAM-кэшей, dispose-каскад DriftLab, settle+final_quiesce async-слоя); observability_tap (пассивный sync-наблюдатель, канал ТЗ 14.2 IntentEventAdapter); метрики M0 (causal_depth — честный None, DEBT-CAUSAL-DEPTH); superbox_adapter (baseline-delta семантика AC-005); architecture/calibration.yaml; W-IR: personality_from_legacy читает psyche.identity_rigidity (было всегда 0.5 — параметр некалибруем).
⚙️ ОТКРЫТИЕ M0 (зонный отчёт 150 тиков × 3 пресета): idle-среда без вмешательств классифицирует ЛЮБОЙ пресет как MANNEQUIN (cc≈0.006, loop=1.0 при ~300 bus-событиях/тик-окно; нулевые дельты social_dialogue:NEUTRAL) — судьбы не возникают из вакуума; сквозной сигнал пресетов есть (golden div +68% vs mannequin); условие зоны ENIGMA = событийная накачка (ScenarioPlayer, ТЗ 11 → M1). Ядро replay покадрово детерминировано; rel/l1 — async-слой одного подписчика (DEBT-QUIESCE).
⚙️ Инциденты сессии (закрыты в сессии): 2 красные серии материализатора (Path-identity как ключ патчей ненадёжен → прямое присваивание; патчер/верификатор расходились в семантике приоритетов → единый _effective_override); INV-SILENT-FAILURE от собственного except:pass (L4); post-dispose «SQLite connection» страгглеры (final_quiesce).
📁 svc/calibration/* (overlay, preset_io, preset_materializer, experiment_runner, observability_tap, metrics/, superbox_adapter), config/calibration/test_presets/, tests/calibration_lab/* (52), architecture/calibration.yaml, docs/audits/ADR-O-361_IMPACT.md, models/npc_state.py (W-IR).
⚠️ Координация: параллельные S208-S212 (номер сдвинут с S208 на S213 по §11.1.1); ADR-O-361 подтверждён за лабораторией (Steal-сессия заняла O-362; устаревшая ссылка (ADR-O-361) в их записи S209 — их зона); PRE-EXISTING КРАСНЫЙ: SUPERBOX-014 second_order_attribution красен БЕЗ overlay (файл не менялся с V.0.5.3.8.1 → деградация ядра позже; кандидаты: S206 reliability prior / S211 dispositions) — чужая зона, эскалация Мастеру. Долги M1+: DEBT-QUIESCE, DEBT-CAUSAL-DEPTH, DEBT-EVBUS (dispose не отписывает шину), DEBT-SOC (мёртвый S198-фикс: _idle_shared_context не существует), DEBT-L1-SQLITE, DEBT-MOCK (random.choice; гейт ENIGMA_ENV≠settings.environment), DEBT-CL1 (overlay не покрывает константы вне core.constants), pytest.ini ([tool:pytest] не читается pytest 8), world_tick.json вне saves/.
IPT: ✅ 44/44 (SILENT-FAILURE зелёный). КРАСНЫЕ ИНВАРИАНТЫ: 0 🔴 → 0 🔴

### S214: ФИНАЛ Vertical Slice «Тень и золото» — SUPERBOX-GORAN 12/12 | ✅
🎯 Vertical Slice доказан целиком: мотив → решение (STEAL 1.04) → windup → THEFT → наблюдение (LOS-мембрана) → belief (6 агентов независимо) → характер (WARN 1.96 по disposition) → речь → вера игрока → ACCUSE-гейт → последствия (fear=25) — БЕЗ единой инъекции belief/event/intent. β-гибрид: инъекция ТОЛЬКО входа (OpportunityContext, will_state, позиции); канонические реплики через production execute_pending (API SUPERBOX-016).⚙️ Production-находки теста (7 живых багов): (1) контракт update_relationships разорван чужой миграцией — TICK_CRASH на каждом THEFT; (2) opportunity will-гейт только broken — расширен до deceptive (воля как мембрана скрытности); (3) WorldSnapshot geometry-поля ломали dataclass-порядок — чужая коллизия, fields в конец с дефолтами; (4) canonical-очередь не разбирается в idle (исполнение только через execute_pending — тест-режим, production-вопрос в SMOKE); (5) NPCStateAdapter читает will_state из psyche["state"], не из корня; (6) mvp_controller без подчёркивания (инъекция ACCUSE-гейта); (7) L1-инстанс-изоляция двух миров (temp-saves на каждый). Живые феномены: player наблюдал кражу conf=1.00 (ADR-O-358 в production); blacksmith_orm независимо WARN 1.43 (характеры множатся); G9 — causal attribution: одна стена расстояния = истории нет. §18, DEBT-E1 задекларированы (S211).📁 tests/sandbox/SUPERBOX/scenarios/goran_vertical_slice_test, models/world_snapshot (geometry-порядок), services/economy/opportunity_engine (deceptive-гейт), services/npc/state_applicator (контракт-фикс), services/social/mvp_tavern_controller (rel_store-инъекция), Устав §18 (S211)

---

## 3. СВОДКА ИНВАРИАНТОВ (IPT)

*   **Dialogues:** `STM`, `SCHEDULER-FAIL` (L4), `LIVENESS`
*   **Traversal/Death:** `ZOMBIE`, `DEATH-LOCK`, `TERMINALITY`
*   **Time/Space:** `WALL-CLOCK`, `KERNEL-RNG`, `SPATIAL-SSOT`, `POSITION-MUTATION`, `TICK-CARDINALITY`, `TEMPORAL-ISOLATION`, `SCENE-ENTITY-ISOLATION` / `NPC-CARDINALITY`
*   **Architecture:** `SILENT-FAILURE`, `FRONTEND-ISOLATION`, `DOMAIN-PURITY`, `L1-APPEND-ONLY`, `NO-RETRO-SIM`, `COMMIT-CARDINALITY`, `HP-SSOT`
*   **Epistemic/Social:** `EPISTEMIC-BOUNDARY`, `INTENT-EVENT-COMPLETENESS`, `FATE-CRITICAL-BROKEN`
*   **Infra:** `PBT-ROUNDTRIP`, `ADR-NET`, `REPLAY-STORE`, `REPLAY-DETERMINISM` (WARN), `SAVE-LOAD-INTEGRITY`, `EVENT-CARDINALITY`

---
*Новые сессии добавляются в конец Раздела 2 строго в порядке возрастания номера.*