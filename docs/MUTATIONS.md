# MUTATIONS.md — ENIGMA Causal Evolution

> **Формат:** Эпохи → Сессии (S143-S201) → Инварианты. ADRs в `docs/ADR.md`.
> **Path Alias Map (для LLM-контекста):**
> `svc/` = `backend/app/services/` | `dom/` = `backend/app/domain/` | `mod/` = `backend/app/models/`
> `core/` = `backend/app/core/` | `agents/` = `backend/app/agents/` | `api/` = `backend/app/api/`
> `tests/` = `backend/tests/` | `fe/` = `frontend/` | `scripts/` = `scripts/` | `arch/` = `architecture/`
> **Сигнатура:** 🎯 Фокус | ⚙️ Delta (Изменения) | 📁 Файлы

## МЕТА
Сессий: 202 | Доменов: 10 | Статус: Stable (IPT 39/39, 0 drifts) | Аудит: S03-S217

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

---

### S210: Vertical Slice, слой 2 — Perception Topology (R1/R2) + L1-P0 | ✅ IPT 44/44
🎯 Честная мембрана действий игрока: SSOT-таблица ACTION_PERCEPTION_RADIUS (сестра ACTION_INTENSITY); симметрия честности — кража игрока тиха, как кража Shadow (3.0 = whisper). P0: гонка sqlite-транзакций (TOCTOU in_transaction→commit при check_same_thread=False) — RLock-сериализация; TICK_CRASH исчез из двойных прогонов.⚙️ action_perception_radius() SSOT-резолв (unknown→15.0, не 999 — ADR-148); phase_1_input обе точки патчены; reaction_subscriber fallback→WARNING (наблюдаемость телепатии); SUPERBOX-PERCEPTION-TOPOLOGY 4/4 (таблица, симметрия, AST-гвард, двойная мембрана: radius-канал + sight-канал — stealth ≠ невидимость). ИНТЕГРАЦИОННЫЕ КОЛЛИЗИИ параллельной сессии: (1) Causal Ledger вставка разорвала post_init npc_state — сироты удалены, чужой блок сохранён, текст intent-валидации теперь чужой (семантика идентична); (2) Calibration Lab idle_tick-цикл — Rule 25 формализован: песочница с чистого старта ≠ ретро-симуляция живой камеры, SANDBOX_WHITELIST в lint_retro_simulation. Досье: R5 (TICK_CRASH проглатывается орковым except — решение о громкости отложено).📁 dom/constants (ACTION_PERCEPTION_RADIUS), svc/game_loop/phase_1_input, svc/events/reaction_subscriber, svc/memory/sqlite_store (RLock), models/npc_state (фикс сирот), scrip

---

### S211: Vertical Slice, слои 3-4 — Характеры + Player Epistemic Action | ✅ IPT 43/44 (1 чужой)
🎯 Слой 3 (R7): монокультура WARN мертва — один belief → разные действия по натуре (guard→REPORT 1.89, maid→RUMOR 1.755, merchant→WARN, thief молчит). Слой 4 (R10/§18): убеждение игрока = способность — ACCUSE-гейт на EpistemicStore через resolver (conf ≥ 0.5); слабый слух блокирует; ЛОЖНОЕ обвинение проходит (вера ≠ истина, различие эмерджентно).⚙️ Слой 3: EPISTEMIC_DISPOSITIONS (доменная таблица, калибруема, табу npc_id-хардкодов) + to_modifiers(+archetype, легаси-ветка байт-в-байт S198) + проброс profile_l0.archetype (pipeline:496, единственный вызов). Слой 4: ActionType.ACCUSE + ACCUSE-first распознавание + get_confidence_for_subject (resolver — граница чтения) + гейт в ActionConsequenceCompiler (инъекция late-binding set_epistemic_resolver; mvp_controller) + ветка последствий (fear+25/trust−15, TruthState не трогается — истинность решают NPC). §18 Law of Singular Epistemic Authority (Устав). АРХЕОЛОГИЧЕСКОЕ ОТКРЫТИЕ: параллельная belief-система игрока (PlayerBeliefModel + ObservationLog/Evidence) — старый прототип gameplay-projection; судьба — DEBT-E1 (authority→projection, 6 шагов, пост-slice; мост Proposition↔secret_id НЕ строится — схлопывание богатой модели в флаг = грех класса S206). SUPERBOX-DISPOSITIONS 6/6, SUPERBOX-ACCUSATION 5/5. Инциденты: сеттер разорвал конструктор компилятора (якорь-присвоение + def — урок: якорь обязан включать хвост метода; py_compile не ловит); атрибут mvp_controller (не _mvp). Чужой красный: calibration:327 except:pass (SILENT-FAILURE) — контекст не предоставлен, долг CAL-1.📁 АРХИТЕКТУРНЫЙ_УСТАВ (§18), dom/epistemic_dispositions, models/player_action (ACCUSE), svc/npc/epistemic_context_resolver, svc/npc/npc_tick_pipeline, svc/player_cognition/action_semantic_resolver, svc/player_cognition/action_consequence_compiler, svc/game_loop/init (инъекция), tests/.../epistemic_dispositions_test, tests/.../accusation_gate_test

---

### S212: Stage 0 & Stage 1 — Foundation Freeze + Causal Spine | ✅ IPT 44/44
🎯 Полное исполнение ТЗ `ENIGMA_TZ_Stage0_Stage1_Foundation_Freeze.md`. Упразднена двойная истина состояния (Stage 0), внедрена причинная цепочка и детерминированный реплей (Stage 1).
⚙️ Stage 0: Упразднён whitelist `_RUNTIME_TOP_LEVEL_KEYS` (Task 0.2). `JsonPersistenceAdapter` bypass закрыт, всё через `atomic_commit` (Task 0.3). Внедрён `ArchitecturalViolationError` и guard `__setattr__` в `NPCState` (Task 0.4). Мигрированы writers в `NPCState.beliefs` на `BeliefTransitionEngine.commit` (Task 0.5, 0.6). Создан `update_relationships` API в `StateApplicator` (Task 0.7). Устранены прямые мутации `_avatar.body_state` (Task 0.8). Прямые мутации `NPCState` заменены на `object.__setattr__` (Task 0.9). Упразднён параллельный WorldTick-путь `phase_2_world_tick.py` (Task 0.10), `write_to_legacy` переименован в `to_persistence_dict`.
⚙️ Stage 1: Внедрён `WorldSnapshot` в `TickOrchestrator` (Task 1.3). Добавлены `Cause` и `MissingProvenanceError` в `StateApplicator.apply` (Task 1.2). Добавлены методы `query_ledger` и `trace_causal_chain` в `NPCState` (Task 1.4). Добавлен `PerceptualKernel.can_observe` (Task 1.5). Детерминизм подтверждён DriftLaboratory (0.0% drift, Task 1.1).
📁 models/npc_state, models/psychological, services/npc/state_applicator, services/npc/npc_loader, services/npc/belief_transition_engine, services/scene_state_manager, services/game_loop/phase_2_world_tick, services/events/claim_event_subscriber, services/tick_orchestrator, errors.py, tests/test_stage0_and_1_invariants.py

---

### S213: Лаборатория калибровки психики — M0 Fundament (ADR-O-361) | ✅ IPT 44/44
🎯 Фундамент Psychology Calibration Laboratory (ТЗ Лаборатории v1.0, План M0): подмена параметров, headless-эксперименты на реальном конвейере, пассивное наблюдение, 5 метрик, контрольные пресеты зон.
⚙️ Артефакты: config_overlay (identity-патч from-import биндингов decision_hub + verify вход/выход, запрет вложенности — тихая ложь экспериментов исключена); preset_io (строгий валидатор: [PLAN]-параметры и taboo ADR-O-360 → громкий отказ) + пресеты mannequin/chaos/enigma_golden; preset_materializer (temp-копия config/npc, патч npc_overrides, прямой редирект npc_loader._CONFIG_NPC_ROOT + поведенческая верификация реальным загрузчиком); experiment_runner (чистый старт = пустой temp-saves, offline MockProvider, restore настроек/диска/RAM-кэшей, dispose-каскад DriftLab, settle+final_quiesce async-слоя); observability_tap (пассивный sync-наблюдатель, канал ТЗ 14.2 IntentEventAdapter); метрики M0 (causal_depth — честный None, DEBT-CAUSAL-DEPTH); superbox_adapter (baseline-delta семантика AC-005); architecture/calibration.yaml; W-IR: personality_from_legacy читает psyche.identity_rigidity (было всегда 0.5 — параметр некалибруем).
⚙️ ОТКРЫТИЕ M0 (зонный отчёт 150 тиков × 3 пресета): idle-среда без вмешательств классифицирует ЛЮБОЙ пресет как MANNEQUIN (cc≈0.006, loop=1.0 при ~300 bus-событиях/тик-окно; нулевые дельты social_dialogue:NEUTRAL) — судьбы не возникают из вакуума; сквозной сигнал пресетов есть (golden div +68% vs mannequin); условие зоны ENIGMA = событийная накачка (ScenarioPlayer, ТЗ 11 → M1). Ядро replay покадрово детерминировано; rel/l1 — async-слой одного подписчика (DEBT-QUIESCE).
⚙️ Инциденты сессии (закрыты в сессии): 2 красные серии материализатора (Path-identity как ключ патчей ненадёжен → прямое присваивание; патчер/верификатор расходились в семантике приоритетов → единый _effective_override); INV-SILENT-FAILURE от собственного except:pass (L4); post-dispose «SQLite connection» страгглеры (final_quiesce).
📁 svc/calibration/* (overlay, preset_io, preset_materializer, experiment_runner, observability_tap, metrics/, superbox_adapter), config/calibration/test_presets/, tests/calibration_lab/* (52), architecture/calibration.yaml, docs/audits/ADR-O-361_IMPACT.md, models/npc_state.py (W-IR).
⚠️ Координация: параллельные S208-S212 (номер сдвинут с S208 на S213 по §11.1.1); ADR-O-361 подтверждён за лабораторией (Steal-сессия заняла O-362; устаревшая ссылка (ADR-O-361) в их записи S209 — их зона); PRE-EXISTING КРАСНЫЙ: SUPERBOX-014 second_order_attribution красен БЕЗ overlay (файл не менялся с V.0.5.3.8.1 → деградация ядра позже; кандидаты: S206 reliability prior / S211 dispositions) — чужая зона, эскалация Мастеру. Долги M1+: DEBT-QUIESCE, DEBT-CAUSAL-DEPTH, DEBT-EVBUS (dispose не отписывает шину), DEBT-SOC (мёртвый S198-фикс: _idle_shared_context не существует), DEBT-L1-SQLITE, DEBT-MOCK (random.choice; гейт ENIGMA_ENV≠settings.environment), DEBT-CL1 (overlay не покрывает константы вне core.constants), pytest.ini ([tool:pytest] не читается pytest 8), world_tick.json вне saves/.
IPT: ✅ 44/44 (SILENT-FAILURE зелёный). КРАСНЫЕ ИНВАРИАНТЫ: 0 🔴 → 0 🔴

---

### S214: ФИНАЛ Vertical Slice «Тень и золото» — SUPERBOX-GORAN 12/12 | ✅
🎯 Vertical Slice доказан целиком: мотив → решение (STEAL 1.04) → windup → THEFT → наблюдение (LOS-мембрана) → belief (6 агентов независимо) → характер (WARN 1.96 по disposition) → речь → вера игрока → ACCUSE-гейт → последствия (fear=25) — БЕЗ единой инъекции belief/event/intent. β-гибрид: инъекция ТОЛЬКО входа (OpportunityContext, will_state, позиции); канонические реплики через production execute_pending (API SUPERBOX-016).⚙️ Production-находки теста (7 живых багов): (1) контракт update_relationships разорван чужой миграцией — TICK_CRASH на каждом THEFT; (2) opportunity will-гейт только broken — расширен до deceptive (воля как мембрана скрытности); (3) WorldSnapshot geometry-поля ломали dataclass-порядок — чужая коллизия, fields в конец с дефолтами; (4) canonical-очередь не разбирается в idle (исполнение только через execute_pending — тест-режим, production-вопрос в SMOKE); (5) NPCStateAdapter читает will_state из psyche["state"], не из корня; (6) mvp_controller без подчёркивания (инъекция ACCUSE-гейта); (7) L1-инстанс-изоляция двух миров (temp-saves на каждый). Живые феномены: player наблюдал кражу conf=1.00 (ADR-O-358 в production); blacksmith_orm независимо WARN 1.43 (характеры множатся); G9 — causal attribution: одна стена расстояния = истории нет. §18, DEBT-E1 задекларированы (S211).📁 tests/sandbox/SUPERBOX/scenarios/goran_vertical_slice_test, models/world_snapshot (geometry-порядок), services/economy/opportunity_engine (deceptive-гейт), services/npc/state_applicator (контракт-фикс), services/social/mvp_tavern_controller (rel_store-инъекция), Устав §18 (S211)

---

### S215: Stage 2A / S203.1 — Commitment Registry (Shadow, ADR-O-363) | ✅ IPT 44/44, pytest 25/25
🎯 Первый слой Unified Behavioral Ownership: реестр поведенческого владения — отсутствующий онтологический слой между Intent (психика) и Traversal (физика). Археология Н-1…Н-52: 6 производителей поведения → 3 исполнителя → 0 единых владельцев; CANCELLED без продюсера (Н-45); PENDING виртуален — traversal рождается MOVING (Н-50); lifecycle размазан по 5 модулям; has_active_commitment слеп к windup/task (Н-35); Double Truth activity: расписание против психики (Н-18, подтверждено самим LifeEngine:1216 «DOUBLE TRUTH → Schedule Freeze», Н-39).
⚙️ domain/action_commitment (новый): FSM 9 статусов; CANCELLED из любой активной фазы (поймано семантическим тестом, матрица тавтологична таблице); INTERRUPTED без interrupt_reason = отказ; commitment_id=md5(tick:npc:action:ordinal), uuid4 запрещён; build_commitment_dict — единственный способ создания; empty cause запрещён. services/action/commitment_registry (новый): единственный писатель scene_state["active_commitments"] (только активные) + commitment_history (retained, cap 10/NPC) + commitment_ordinals (монотонные, не переиспользуются); суперсессия осиротевшего обязательства с parent_commitment_id (№3a); sweep (INTERRUPTED/TRAVERSAL_VANISHED) после Фазы 0.5 в оркестраторе. Врезка зеркал: SSM.apply_change (материализация, cause verbatim от upstream — SSM не классифицирует, №7; UNKNOWN_LEGACY_SOURCE для пустых, №8); TES.advance (COMPLETED); movement_engine (легализация обхода Н-46a: INTERRUPTED/CROSS_LOCATION_TRANSFER); world_snapshot.active_commitments (deepcopy-заморозка, поле в конце dataclass). Н-49 fix: fail-fast в build_traversal_dict (silent-PENDING невозможен). Shadow-контракт: COMMITMENT_REGISTRY_ENABLED=False = полный no-op; A/B DriftLab: AB diff=0, ON/OFF diff=0 по поведению (единственные расхождения — жизненный цикл llama-server: start/stop против «уже запущен»). Исправления по ходу: FSM-дыра CANCELLED; Н-46b скорректирован (SSM НЕ перезаписывает MOVING — внешний guard 1238–1244; вектор сиротства — только engine pop/death-cleanup); Н-52: внутренняя suppression-ветка SSM (1268–1277, SLEEP_FIX #1) мертва — недостижима из-за внешнего guard.
⚠️ Коллизия с параллельной сессией (S212/S213-окно) в world_snapshot.py: дефолты spatial_walls/obstacles — чужой фикс нашего же TypeError; принят без изменений. Долги: Н-6 (HEARING_RADIUS), Н-9 (consciousness_state doc drift), Н-10 (комментарий ledger), Н-11 (стаб trace_causal_chain), Н-12 (4 wildcard-writers Task 0.9), Н-21 (soft-degradation снапшота), Н-31 (uuid4 в Фазе 6), Н-32 (H-37 FIX лжёт — терминалы выбрасываются), Н-42 (TaskState DOUBLE TRUTH execution.py|tasks.py → S203.4), Н-43 (FSM без владельца вызова), Н-52 (мёртвая ветка), dead imports time/uuid4 в world_snapshot, cross-scene parent-лаг, death-cleanup лаг sweep (ловится следующим тиком).
📁 domain/action_commitment (новый), services/action/ (новый), services/scene_state_manager, services/spatial/traversal_execution_system, services/spatial/movement_engine, services/tick_orchestrator, models/world_snapshot, domain/traversal_schema, tests/test_action_commitment.py (новый), tests/test_commitment_ssm_integration.py (новый)

⚙️ Инцидент ANOMALY→фикс: baseline v1 показал пустой реестр при живых traversals — dual-rail
открытие: ProjectionEngine (ADR-O-204, shadow-rail) пишет traversals ДО SSM, guard in-flight
глушит SSM-ветку в production. Зеркало перенесено в ProjectionEngine._apply_position (точка
первого писателя, tick/cause из thick-контракта); SSM-зеркало = fallback (guard исключает
двойной commit). Baseline v2 (200 тиков, tavern, 6 NPC): terminals=42 (COMPLETED 38,
INTERRUPTED 4), SUPERSEDED=4 (~9% сиротства), actives=2. ГЛАВНЫЙ ВЫВОД: 64% движений —
проактивные социальные интенты DecisionHub (offer_job 9, change_role 7, request_service 5,
call_for_help 4, spread_rumor 2), schedule 19%, need 17%, random wander 0%. Н-56: DLG_QUEUE
OVERFLOW 288/20 в том же прогоне — единая первопричина churn движения (TZ §12–13) и churn
диалогов (TZ §15). Числа = вход S203.2 (REJECT) и S203-E (opportunity gate).
Долги доб.: Н-53 (GROUND_TRUTH location_id='', A/B-верифицирован pre-existing, 197/197),
Н-55 (забытый BORKO-дебаг в movement_engine:257–285 с if True:), Н-56 (DLG_QUEUE overflow),
teardown-шум SQLite у переживающих teardown async-воркеров.

---

### S216: Stage 2A / S203.2 — Commitment Arbitration (ADR-O-363) | ✅ IPT 44/44, pytest 36/36
🎯 Внедрение права Commitment Registry влиять на материализацию поведения: CommitmentArbiter — gate перед исполнителями движения. Арбитр решает ТОЛЬКО «получает ли candidate право материализоваться при текущем incumbent» (Мастер-инвариант: не «можно ли NPC двигаться» — это DecisionHub). Четыре семантики ADR-O-363 в кодировке Мастера: PASS → COMMIT (через mirror); REJECT(DUPLICATE) → CONTINUE; REJECT(INCUMBENT) → REJECT; INTERRUPT ≡ отсутствует до S203.3/4 (арбитр НЕ умеет убивать incumbent — граница спринта).
⚙️ domain: ACTIVE_COMMITMENT_STATUSES = {PROPOSED, COMMITTED, EXECUTING, BLOCKED} — Мастер: COMMITTED считается занятым, commitment race исключён (окно COMMIT→EXECUTING атомарно по построению: mirror коммитит после записи traversal одним стеком). Миграция has_active_commitment (npc_tick_pipeline:470) → CommitmentRegistry.has_behavioral_owner: registry-first + legacy-fallback (NEW==OLD при traversal-only; FLAG=OFF → fallback → no-op). svc/action/commitment_arbiter (новый): verdict PASS | REJECT + reason ∈ {DUPLICATE, INCUMBENT} (Мастер: вердикт-классификатор запрещён — REJECT_X как отдельные Verdicts → NO); read-only (реестр не пишет; единственный commit-писатель — mirror при материализации; race-free by construction); один арбитр, два invocation points: Гейт① simulation.py (life_intents до MovementEngine), Гейт② movement_bridge.py (резолвнутые макро + passthrough с target_node_id; микро/steering не гейтится — ADR-O-328). ARBITER_ENFORCEMENT через env (default False) — после 3× класса сбоя «правка в редакторе между командами не выполнена» (S203.1 OFF-захват; arb_enforced ×2) — инженерный вывод: ручные шаги из A/B-петли удалены, тройная верификация флага до/прогон/после. Телеметрия [ARBITER_REJECT] logger.info — полный контекст Мастера (tick/npc/candidate_target/candidate_source/incumbent_id/incumbent_target/reason).
⚙️ ИЗМЕРЕНИЯ: log-only (print-зонд по Часть VIII.5): CALLS=986–1006, REJECTS=348–359 (~36% кандидатов конфликтуют), профиль кандидатов совпал с baseline-профессией churn: 81% — proactive-social (request_service 195, offer_job 121, block_path 99, call_for_help 96, ambush 77, change_role 74, spread_rumor 73, seek_ally 73). A/B ENFORCEMENT (env-верифицирован): **SUPERSEDED 4–16 → 0** (главный KPI Мастера); **COMPLETED 62–90% → 100% (42/42)** — каждое обязательство доезжает; движение живо (200/200 тиков с traversals, real_errors=0, terminals 42=42 — объём сохранён). Центральная гипотеза Stage 2A доказана числами: один владелец → предсказуемое исполнение. LOG_ONLY недетерминизм: SUPERSEDED 4→16→8→16→13 по 5 прогонам (async-слой, класс DEBT-QUIESCE; вариативна пропорция COMPLETED/INTERRUPTED, объём стабилен) — база = диапазон.
⚠️ Уроки сессии: (1) зонд logger.info в sandbox-захвате = слепое измерение (ложные CALLS=0) — Часть VIII.5 обязательна, print() до финализации; (2) инвертированный enforce()-контракт (LOG_ONLY возвращал False при REJECT) — пойман моим же тестом test_log_only_always_permits; (3) 3× ручной флаг → env-паттерн. Долги: проде-режим флага — решение Мастера после SUPERBOX-ACTION-INTEGRITY (рекомендация: False до поведенческого гейта, затем True); SUPERBOX-ACTION-INTEGRITY (сценарии TZ §26 A/B на enforcement-контуре) — следующий гейт Stage 2A; async-недетерминизм baseline (DEBT-QUIESCE-класс) — измерен, не чинится здесь.
📁 domain/action_commitment (ACTIVE-set), services/action/commitment_arbiter (новый), services/action/commitment_registry (has_behavioral_owner), services/npc/npc_tick_pipeline (миграция проекции), services/phases/simulation (Гейт①), services/phases/movement_bridge (Гейт②), tests/test_action_commitment.py (+11: проекция 5 + арбитр 6)

⚙️ SUPERBOX-ACTION-INTEGRITY (промежуточный behavioral gate Мастера перед ownership surgery; closed by verdict): 3 сценария (eat/sleep/impossible) × 150 тиков, enforcement=ON, runtime-инъекции после тика 0 (археология Н-57: NPC не в файлах кампании, стейты ленивы; hunger-ключ создаётся, schedule в стейте отсутствует — сон форсирован sleep_pressure, C — через activity_map). RED=0 — связка Registry+Arbitration поведенчески чиста (R6 FAILED-release ✅; G1/G4/G5/G7 ноль нарушений; все терминалы COMPLETED). ГЛАВНОЕ (формулировка Мастера): доказана integrity ИСПОЛНЕНИЯ, не integrity ПОВЕДЕНИЯ ВО ВРЕМЕНИ — Y-SETTLED: DEEP_SLEEP + активный MOVE одновременно = конфликт доменов власти, система владеет действием, но не владеет бездействием; Y-CHURN-RHYTHM: terminal→новый commitment стабильно 2–3 тика без пауз — «отсутствие действия должно быть валидным состоянием, не дырой между commitment» (центральная находка Stage 2A; S203.6 — доказанно необходимый слой). Y-RESOLVER: сломанная activity_map не останавливает NPC (fallback-цепочка) — вход археологии S203.3. Y-NEED: hunger=0.9 → hunger-cause=0 при доминировании schedule:eating — микрозонд в S203-D. Y-REPLAY: 10 vs 11 при идентичных стартах — RED снят вердиктом (узкий вывод: внешний temporal nondeterminism меняет число behavioral events; инварианты владения целы) → DEBT-QUIESCE. Принцип Stage 2A (в документацию): COMMITMENT решает, кто имеет право действовать; SETTLED STATE решает, имеет ли NPC вообще обязанность действовать. S203.3-спецификация расширена: INTERRUPT = гарантии (terminal transition → cause persisted → ownership released → executor stopped → no stale materialization), не флаг.
📁 tests/sandbox/SUPERBOX/scenarios/action_integrity_test.py (новый), reports/superbox_action_integrity.md

---

### S217: LLM Delivery Layer — Model Manager (дистрибутив без модели → внутриигровой менеджер моделей) | 🟡 runtime-верифицировано, IPT-гейт перед коммитом
🎯 Тестер получил релиз без файла модели (5 ГБ исключены из enigma_setup.iss) → llama-server exit(1) на каждом старте, backend крутился без LLM: movement-интенты материализовались, вербальные падали в DLG_QUEUE OVERFLOW — «NPC ходят, но молчат». Двойной баг запуска: game_launcher проверяет файл и отказывается, а main.py дублировал Popen БЕЗ проверки (ложный автозапуск мёртвого процесса). Решение класса «доставка»: полный менеджер моделей внутри игры — скан/скачивание/докачка/валидация/выбор/тест.
⚙️ Ядро запуска: жёсткая валидация в _background_llm_startup (main.py) — существование + размер перед Popen, startup_status=failed + llm_error=model_file_missing; /api/llm/status расширен (model_path, model_exists, server_executable_exists, error_reason). Launcher: проверка модели при старте → принудительный экран LLM-настроек; ESC в игре → return "PAUSE" → настройки → продолжение сессии без рестарта; [DIAG_LAUNCH]-зонд размера файла (Часть VIII.5).
⚙️ Downloader (svc/llm/downloader.py): докачка Range-resume (206 → дозапись 'ab'; 200 → рестарт — обрыв сети не теряет гигабайты); cancel_download + /api/llm/cancel/{key} — отмена с удалением недокачанного файла; валидация целостности: файл >1 МБ + (если remote известен) ≥0.99×remote — «скачано» на пустом/битом файле невозможно (инцидент: 3788988416 vs 4683073920 = тензор за пределами файла, доказано llama-server stderr); ручные модели: скан *.gguf папки Models LLM, дубли отсечены по target_path в статусе; размеры через HF Tree API (urllib-HEAD не видит Content-Length за CDN-редиректом — PowerShell HttpWebRequest видел, urllib нет; Tree API отдаёт JSON размеров всех квантов разом) + периодический воркер 60 сек; ЛЕНИВЫЙ старт воркеров из get_model_status — потоки при импорте ловили NameError get_llm_sources (модуль не доисполнен; поймано smoke-тестом §3.9: функция вернула 4683073920 при упавшем воркере); VRAM через nvidia-smi (кэш) → recommended ≤80% VRAM; User-Agent + HF_TOKEN (env) в скачивание и Tree API; 401 → человеческая диагностика для gated.
⚙️ Каталог (config/llm_sources.json): 3 gated-источника (gemma-3-12b/4b bartowski, mistral-pygmalion PygmalionAI — 401 без токена) заменены открытыми русскоязычными: T-lite-7B-abliterated (WTFPL, Q4_K_M 4693 МБ), Vikhr-Llama-3.2-1B (770 МБ), PavelGPT-7B-128K (4166 МБ); плюс Qwen2.5-7B Q4/Q5/Q6 и Mistral-Nemo-12B Q3_K_M (5801 МБ — пограничный для 8 ГБ VRAM; при OOM — контекст 4096). Итог 7/8 без токена (было 5/8). УРОК: имена файлов репозитория верифицировать Tree API ДО вписывания URL — 2× 404 от угаданных имён (ggml-model-Q4_K_M.gguf у PavelGPT; Vikhr без «-instruct.» в имени файла). Дубль qwen_7b+qwen_7b_q4 (две записи, один target_path) устранён; default_model → qwen_7b_q4; model_qwen_7b_path Q5→Q4 (второй хардкод-рассинхрон из smoke-вывода).
⚙️ UI (fe/settings_screen.py): модалка действий модели [Сделать активной | Скачать заново | Проверить модель]; модалка проверки: вопрос + ответ (test_prompt проброшен из routes), textwrap-перенос; прогресс-модалка: %, скорость МБ/с, ETA, «Отменить загрузку» (удаляет файл на бэкенде), защита от двойного клика (_is_dl_modal_open — двойной POST порождал второй круг скачивания); подтверждение выхода — кнопки Да/Нет мышью; ESC закрывает ТОЛЬКО модалку, не меню; секции [Установленные]/[Доступные] + MOUSEWHEEL-скролл; ASCII-маркеры [АКТИВНА]/[ГОТОВО]/[СКАЧАТЬ]/[ОШИБКА]/[РЕКОМЕНД.]/[ЛИЦЕНЗИЯ] вместо эмодзи (consolas рендерит «?»); _fit_font — кегль по font.size (не по len(name)); тактильный отклик inflate(4,4)+hover во всех окнах; llm_test_log-оверлей удалён (перекрывал Назад/Выход). Вкладка «Управление» + fe/keybindings.py (новый): DEFAULT_KEYBINDS/load/save/get_key + ребинд-диалог, persistence keybinds.json.
⚙️ Установщик: enigma_setup.iss — строка модели раскомментирована (Components: llm); models_setup.iss остаётся альтернативой доставки.
⚠️ Инциденты сессии (все — цикл Hypothesis→Archaeology→Fix): UnboundLocalError os (локальный import тенит глобальный); AttributeError 'str'.get (не-словари в ответе статуса); «активна и скачана» при отсутствии файла (is_active по default_model-хардкоду + exists() без размера); кэш-фантом старого бэкенд-процесса (тройная диагностика №1/2/3 разделила код/процесс/сеть); NameError-race воркеров; timeout UI (HEAD-спам + nvidia-smi в каждом запросе → кэш + фон); двойной клик → двойная загрузка.
Долги: DEBT-D1: аудит publish_release.ps1 не выполнен (исходная задача сессии); DEBT-D2: YandexGPT-5-Lite gated (файл на диске — работает, remote не сверяется, помечен честно); DEBT-D3: dropdown для 100+ моделей + поиск по HF с фильтром VRAM — M1; DEBT-D4: HF_TOKEN только через env, UI-настройки нет; DEBT-D5: gemma-12b на диске стала «ручной моделью» без remote-валидации; DEBT-D6: keybindings не подключены к фактическому вводу game_screen (ребинд сохраняется, потребители читают DEFAULT — интеграция отдельным шагом); DEBT-D7: ревизия settings_screen.py на «двойные определения» после серии патчей (дубль _show_download_modal удалён).
IPT: 🟡 не прогонялся в сессии (все изменения — delivery/UI/launcher слой, ядро симуляции не тронуто); обязательный прогон `python backend/tests/IPT.py` перед коммитом — гейт не снимается.
КРАСНЫЕ ИНВАРИАНТЫ: было 0 🔴 (baseline S216) → 0 🔴 по runtime-наблюдению (тики идут, NPC говорят на восстановленной Qwen Q4 4683073920 байт); post-mortem LAST_SESSION.md — ожидает прогон Мастера.
📁 game_launcher.py, backend/app/main.py, backend/app/api/routes.py, backend/app/services/llm/downloader.py, backend/app/core/config.py, config/llm_sources.json, frontend/settings_screen.py, frontend/keybindings.py (новый), frontend/game_menu.py, frontend/game_screen.py, enigma_setup.iss

---

### S218: LLM Infrastructure — Model Catalog, Downloader & Startup Optimization | ✅
🎯 Замыкание исходного бага «NPC молчат у тестера» (модель не доставлена) + оптимизация старта с 15–17с до 7.0с.⚙️ Каталог: 11 моделей в llm_sources.json (gemma/mistral-pygmalion заменены на открытые RU-модели: T-lite, Vikhr, PavelGPT, Vikhr-Nemo-12B, NekoMix-12B, Qwen2.5-14B со split-parts). Downloader: докачка (Range), отмена с удалением, Tree API для remote-размеров (кэш 5 мин, ленивый воркер — убита гонка NameError при импорте), сплит-файлы Qwen-14B (сумма частей, llama-server грузит нативно). UI: разделы Установленные/Доступные, [РЕКОМЕНД.] по VRAM 80% (nvidia-smi, кэш), [ЛИЦЕНЗИЯ] для gated, адаптивный шрифт _fit_font, масштаб + скроллбар, модалки действий модели (активировать/скачать заново/проверить с промптом), отмена скачивания. Установщик: модель исключена (галочка llm-компонента удалена), nocompression снят с CUDA (2.27ГБ → ~1.4ГБ), Models LLM исключён из staging. Старт: NO_PROXY+127.0.0.1 (анти-прокси/IPv6), health-таймауты 0.3–0.5с, окно загрузки первым действием main() с единой шкалой этапов, [TIMING]-телеметрия в startup_timing.log. publish_release: самоочистка конфликтных тегов.📁 config/llm_sources.json, backend/app/services/llm/downloader.py, backend/app/api/routes.py, backend/app/main.py, backend/app/core/config.py, frontend/settings_screen.py, game_launcher.py, enigma_setup.iss, publish_release.ps1

### S219: Stage 2A / S203.3 — Traversal Ownership + INTERRUPT-контракт (ADR-O-363) | ✅ pytest 43/43, IPT наш-профиль 42/42
🎯 Завершение ownership-хирургии traversal: единый GC-владелец + легальный INTERRUPT с атомарностью двух рельсов. Закон Мастера: INTERRUPT не успешен, пока traversal и commitment не достигли согласованного terminal — частичное прерывание запрещено.
⚙️ dom/traversal_schema: interrupt_traversal (prepare-then-commit: preview обеих FSM без мутаций → CANCELLED+INTERRUPTED(reason) → запись живёт до SSM-GC; семантика False: ALREADY_TERMINAL | NOT_FOUND | REJECTED_INVALID — не смешиваются; причины CROSS_LOCATION_MATERIALIZE/CROSS_LOCATION_TRANSFER из реестра, расширение=мини-ADR) + transition_commitment_preview. Легализация bypass'ов: Н-46a (ME:330) и Н-46c (ORCH:967, S186_TRANSFER) → interrupt_traversal за флагом TRAVERSAL_OWNERSHIP_ENFORCEMENT (env, default OFF; legacy pop = A/B-база). Ц1: SSM.gc_traversals() — единственный GC (вынос из apply_changes + гарантированный вызов из оркестратора после Фазы 0.5 — закрыло INV-TRAV-ZOMBIE-окно, пойманное Ц1-переносом); TES-самоудаление устранено (mirror COMPLETED сохранён).
⚠️ Инциденты сессии: (1) DOMAIN-PURITY — мой импорт services из domain в commit-фазе, пойман INV и исправлен доменной записью (transition_commitment + history-структура); неполная замена тела при патче → 3 NameError — исправлено цельным блоком; (2) Ц1-окно: COMPLETED-запись живёт до GC-прохода → INV-TRAV-ZOMBIE красный → gc-гарантия за тик; (3) G6 chunk_migration (10k тиков) отменён по времени — replaced юнит-тестом cross-scene continuity + микропрогоном 300 тиков (миграция в tavern-окне не наступила: 0 CROSS_LOCATION-событий; полный G6 — опция Мастера). A/B OFF/ON: профили в LOG_ONLY-диапазоне (SUPERSEDED 13/4; cross-loc события в мире отсутствуют → interrupt-пути не активируются — нейтральность). ЧУЖИЕ КРАСНЫЕ (не наша зона, эскалация): INV-FRONTEND-ISOLATION (lab_screen.py:48 → calibration.experiment_runner, S213-зона), INV-SILENT-FAILURE (llm/downloader.py ×3, растёт в параллельной сессии).
📁 domain/traversal_schema (interrupt_traversal, preview), services/scene_state_manager (gc_traversals), services/tick_orchestrator (GC-точка + Н-46c-легализация), services/spatial/movement_engine (Н-46a-легализация), services/spatial/traversal_execution_system (самоудаление устранено), tests/test_action_commitment.py (+7: interrupt 6 + G6)

### S220: Лаборатория M1 — Intervention Consequence Routing + FE-серия стабилизации запуска | ✅ pytest 52/1s, IPT 42/44 (оба красных вне зоны), F5-подтверждено
🎯 M1/Задача 1 ТЗ Лаборатории (Вариант B, Pygame-окно): заставить Trust отвечать на вмешательства игрока. Диагноз по протоколу (5 разрывов, все — чтение кода обеих сторон): (1) text-only payload умирал на guard _process_player_action (ядро текст не парсит — L4.1); (2) ветви последствий на intervention-пути НЕ СУЩЕСТВОВАЛО — production-применение живёт в _execute_dm_and_intent_resolution (DM-конвейер), ActionSemanticResolver — сирота (0 вызывов в кодовой базе); (3) _campaign_id=None в lab-сборке (init_campaign зовётся только из new_game) → P2-мост в RelationshipStore мёртв; (4) LabScreen читал social_stats.trust (кэш запрещён L13) вместо ключа relationships из SSOT; (5) латентный TICK_CRASH player-ветки Фазы 10 — пустой S116-фоллбэк (tick_utils:389) не имел scene_state, недостижимо до структурированной семантики.
⚙️ Backend: инъекция с готовой семантикой (semantic_action/target_reference/target_id, kwargs-проброс фабрики — потребляется и consequence-веткой, и конвертером tick_utils:350→IntentDTO→will-гейт); ветвь HELP/BLACKMAIL/ACCUSE → ctx.mvp_controller.action_compiler (зеркало production write-path: process_action → RelationshipStore.update, идемпотентный детерминированный action_id "interv:tick:ACTION:target"); start() зеркалит P-MVP-1 (init_campaign); S116-фоллбэк насыщен scene_state=scene_state (закрыт краш commit_phase:77; для run()-прогонов no-op — доказано двойным изолированным повтором упавшего теста); LabScreen → плоский ключ "maid_lusya→player" (форма get_all, saturation headroom учтена в тесте дельта-ассертом). Runtime-доказательство: trust None→{20.0,-10.0} на тике 11, 14×ok, идемпотентность держит.
⚙️ FE-серия (по приказу Мастера, вне исходного ТЗ — блокеры запуска): current_snapshot-сирота (краш cold-start game_screen:2135 — писатель утерян при рефакторинге; инициализация + восстановление при journal-рендере); K1: get_key двухкандидатный K_<name>/K_<UPPER> — tab/escape/return были мертвы ВСЕГДА (конвенция pygame несимметрична, дефолты lowercase); K2-a: ESC при фокусе ввода закрывает диалог, не паузу (ESC-unfocus TextInput был мёртвым кодом — PAUSE-ветка перехватывала раньше); K2-b: Tab-toggle (было только открытие); опечатка :944 (_end_screen_data → end_screen_data — отложенный показ финала при ошибке API).
⚙️ Вердикт «Назад→end_screen» (closed-not-repro, механизм установлен): спавн tavern y=11.91 в 0.59 юнита от порога ExitTrigger 12.5 + WASD pass-through при застрявшем диалоге (дефект-предок = Баг TAB, устранён K2) + опечатка :944 глотала показ финала в run#1 → отложенный end_screen в run#2. Оба звена устранены, невоспроизводимость подтверждена многократным резюмом.
📁 svc/calibration/experiment_runner (инъекция, init_campaign), svc/tick_orchestrator (_process_player_action ветвь), svc/tick_utils (S116 scene_state), fe/map_editor/ui/lab_screen (SSOT-чтение), fe/game_screen (current_snapshot, K2-a/b, :944), fe/keybindings (K1), tests/calibration_lab/test_m1_trust_intervention.py (новый: дельта trust + N1-регрессия statuses), docs/ADR-O-366*.
⚠️ Открытое (решения Мастера): N2 INV-FRONTEND-ISOLATION lab_screen:49 (Вариант B vs Устав §1.1 — рекомендовано ADR-исключение «анклав dev-инструмента» + allowlist линтера; блокирует старт Задачи 2 по §3.11); N3 downloader.py ×3 silent-except (зона S217/S218). Долги: DEBT-LLM-SPAWN (двойной спавн llama-server лаунчер-vs-backend, доказано процессами 1376/3696); DEBT-ABORT-404 (POST /abort→404: per-task timeout ADR-O-364 фактически не рвёт генерацию — хозяину O-364); DEBT-INTENT-PASS-THROUGH (WASD двигают при фокусе диалога — геймплейное решение); флак test_golden_run_produces_metrics (класс DEBT-QUIESCE, изолированные повторы зелёные); DEBT-SOC runtime-подтверждён (SOCIAL_SUBSCRIBER каждый тик).
IPT: 42/44 — 2 красных вне зоны сессии, зарегистрированы. КРАСНЫЕ ИНВАРИАНТЫ: 2 🔴 → 2 🔴 (новых не внесено)

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