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
📁 svc/calibration/experiment_runner (инъекция, init_campaign), svc/tick_orchestrator (_process_player_action ветвь), svc/tick_utils (S116 scene_state), fe/map_editor/ui/lab_screen (SSOT-чтение), fe/game_screen (current_snapshot, K2-a/b, :944), fe/keybindings (K1), tests/calibration_lab/test_m1_trust_intervention.py (новый: дельта trust + N1-регрессия statuses), docs/ADR-O-367*.
⚠️ Открытое (решения Мастера): N2 INV-FRONTEND-ISOLATION lab_screen:49 (Вариант B vs Устав §1.1 — рекомендовано ADR-исключение «анклав dev-инструмента» + allowlist линтера; блокирует старт Задачи 2 по §3.11); N3 downloader.py ×3 silent-except (зона S217/S218). Долги: DEBT-LLM-SPAWN (двойной спавн llama-server лаунчер-vs-backend, доказано процессами 1376/3696); DEBT-ABORT-404 (POST /abort→404: per-task timeout ADR-O-364 фактически не рвёт генерацию — хозяину O-364); DEBT-INTENT-PASS-THROUGH (WASD двигают при фокусе диалога — геймплейное решение); флак test_golden_run_produces_metrics (класс DEBT-QUIESCE, изолированные повторы зелёные); DEBT-SOC runtime-подтверждён (SOCIAL_SUBSCRIBER каждый тик).
IPT: 42/44 — 2 красных вне зоны сессии, зарегистрированы. КРАСНЫЕ ИНВАРИАНТЫ: 2 🔴 → 2 🔴 (новых не внесено)

### S221: Лаборатория M1 — ScenarioPlayer (scripted-сценарии) | ✅ pytest 62/1s, SMOKE, lint ✅
🎯 M1/Задача 2 (мастер-решение S220: «ScenarioPlayer — GO; лаборатория — потребитель production spine, не второй spine»): YAML-таймлайн вмешательств вместо одиночного тестового хука. Контракт мастера принят дословно: scenario_id/seed/events, replay-идентичность протокола, запрет второго оркестратора.
⚙️ scenario_player.py (новый): load_scenario — строгий валидатор house-style preset_io (неизвестные ключи/действия, tick>=1, BLACKMAIL требует secret_id; SUPPORTED_ACTIONS = реестр production-ветвей ядра: HELP/BLACKMAIL/ACCUSE/ATTACK/MOVE/THREATEN/PERSUADE/GIVE/DIALOGUE; расширение = мини-ADR); ScenarioPlayer.poll(next_tick) — эмит InterventionEvent со структурированной семантикой (ADR-O-367) строго на назначенном тике (1-based, однократность), журнал эмуляций. Единственный контакт с ядром — фабрика InterventionEvent; граница закреплена тестом test_scenario_player_is_not_second_orchestrator (AST-скан исходника на RelationshipStore/DecisionHub/StateApplicator/process_action/delta_buffer).
⚙️ experiment_runner: ExperimentConfig.scenario_path (валидация в start() ДО мутаций настроек/диска); step() — poll перед idle_tick (суперсессия тестового хука S220); ExperimentResult + scenario_id/scenario_events (не-испущенные при обрыве — emitted=False); ядро: secret_id в consequence-ветвь (M-07/M-08) + лог отклонений компилятора (ACCUSE-гейт §18 наблюдаем). LabScreen: дефолт trust_probe_v1.yaml (побитово воспроизводит S220-прогон: HELP на тике 11 → trust 20.0). test_m1_trust_intervention.py удалён (суперсессия — обе ассерции живут в test_m1_scenario_player.py).
⚙️ Runtime: SMOKE тик10 None → тик11 {trust 20.0, fear -10.0}, errors NONE; suite 63 items 62 passed/1 skipped (pre-existing SUPERBOX-014).
📁 svc/calibration/scenario_player (новый), config/calibration/scenarios/trust_probe_v1.yaml (новый), svc/calibration/experiment_runner, svc/tick_orchestrator (secret_id + лог отклонений), fe/map_editor/ui/lab_screen, tests/calibration_lab/test_m1_scenario_player.py (новый, 11 тестов), tests/calibration_lab/test_m1_trust_intervention.py (удалён).
⚠️ Координация: profile.py в calibration/ — файл НЕ этой сессии (компилируется, конфликт нет, владелец — по хвосту MUTATIONS); IPT-красные: N3 downloader (зона S217/S218) + 2× drain_commitment_outbox (живая коллизия с S203.4/S219-контуром — стаб IPT _NoOpScheduler не реализует новый контракт; мост вправе вводить только S203.4-сессия; эскалация Мастеру); [ECO] Direct write NPCState.stress from domain_phases — guard поймал, зона ядра.
IPT: наш дифф = 0 новых красных; финальный прогон 43/44 — единственный красный N3 downloader (чужая зона S217/S218); коллизия drain_commitment_outbox×2 самоустранилась (параллельная S203.4-сессия довела стаб IPT до контракта между нашими прогонами). КРАСНЫЕ ИНВАРИАНТЫ: 3 🔴 (чужие) → 1 🔴 (чужой)

### S222: Лаборатория M1 — Native Pygame Graphs (визуализация динамики) | ✅ compileall, SMOKE-drives, F5-подтверждено
🎯 M1/Задача 3 (мастер-порядок: «графики — после ScenarioPlayer»; легитимность — «график имеет смысл, только когда определён экспериментальный протокол»: протокол теперь есть — сценарии S221 + SSOT-история): заменить текстовые карточки динамической визуализацией строго средствами Pygame (Вариант B, без Next.js/HTML).
⚙️ ui/graphs.py (новый): LineGraph (линия параметра по тикам, шкала min..max, нулевая линия для двуполярных шкал, сетка+подписи, текущее значение; одинаковые аргументы draw) и BarChart (горизонтальные полосы, русские подписи) — ЧИСТЫЕ рендереры без состояния: история/выбор принадлежат LabScreen (мастер-архитектура «данные отдельно, отрисовка отдельно»). Только pygame.draw; без эмодзи (правило S217).
⚙️ lab_screen: npc_history (per-NPC trust/stress, cap 300 тиков) — фиксируется в _step_simulation из тех же источников, что карточки (trust из SSOT-ключа "npc→player" — ADR-O-367-контур; stress из psyche); правая панель: LineGraph доверия (-100..100) + LineGraph стресса (0..100) + BarChart драйвов (control/significance/fear/desire, русские подписи); клик по карточке выбирает NPC (хитбоксы _card_rects, зелёная рамка выделения); автодефолт — первый NPC; узкий экран — панель честно не рисуется. Runtime-подтверждение ключа drives (VIII.5): {'control': 0.4, 'significance': 0.3, 'fear': 0.2, 'desire': 0.1}.
📁 fe/map_editor/ui/graphs.py (новый), fe/map_editor/ui/lab_screen.py.
⚠️ Наблюдения: MOCK_PROVIDER-warn + L1_CHRONICLE SQLite-teardown в однотиковых SMOKE — класс DEBT-L1-SQLITE; relationship_cache в npc-ключах — наблюдение к DEBT-SOC (L13). IPT-красный по-прежнему один: N3 downloader (чужая зона S217/S218).
IPT: N/A (frontend UI-слой, ядро не тронуто; финальный профиль 43/44 — единственный красный чужой). КРАСНЫЕ ИНВАРИАНТЫ: 1 🔴 (чужой) → 1 🔴

---

### S223: Stage 2A / S203.4 — Task/Windup/Sleep Ownership + Arbiter-INTERRUPT + Persistence (ADR-O-365) | ✅ pytest 88/88, IPT 43/1 (единственный красный — чужой)
🎯 Распространение единого поведенческого владения на всех исполнителей (task/windup/sleep) + приоритетная политика прерывания + персистентность ownership через scene_state. Мастер-вердикты D-1…D-9 (включая verdict B: traversal EXECUTING прерываем — policy, не онтология). Главный результат: **ONE NPC → ONE ACTIVE BEHAVIOR OWNER → ONE EXECUTION PATH → ONE VERIFIABLE RESULT** — инвариант Stage 2A замкнут.
⚙️ **Э1 (контракт):** `ADR-O-365` [ONTO] + IMPACT-аудит; мини-ADR покрывает reason-реестр {DUPLICATE, INCUMBENT, INCUMBENT_PROTECTED}, INTERRUPT(PRIORITY_SUPERSEDE), fail_reason {BLOCKED_TIMEOUT, TASK_ERROR, TASK_CRASH, TASK_IMPOSSIBLE}, priority_policy_version="s203.4.v1" (D-5: смена без мини-ADR запрещена), шкала v1 (EXPLORATION=1/ROUTINE=2/SOCIAL=3/SLEEP=6/SURVIVAL=6/WINDOWED=7, INTERRUPT_THRESHOLD=3), три разведённые приоритетные семантики (queue TaskPriority | DRF float | arbitration int).
⚙️ **Э2 (domain):** `dom/action_priority.py` (новый: resolve_candidate_priority pure function, нормализация Enum/str/None через .name); `dom/action_commitment.py` — расширение фабрики (priority, priority_policy_version, executor_ref, blocked_since_tick, fail_reason), transition_commitment hard contract (FAILED без fail_reason = отказ, симметрия INTERRUPTED), frozenset[str] аннотации; `dom/traversal_schema.py` — PRIORITY_SUPERSEDE в _INTERRUPT_TRAVERSAL_REASONS, transition_commitment_preview паритет (fail_reason + INTERRUPTED), __post_init__ → None.
⚙️ **Э3 (arbiter):** `svc/action/commitment_arbiter.py` — VERDICT_INTERRUPT + REASON_INCUMBENT_PROTECTED + candidate_priority параметр + S203_4_ARBITER_INTERRUPT env-флаг (каскад с ARBITER_ENFORCEMENT); enforce_for_intent() wrapper (arbiter read-only, исполнение interrupt в invocation point); policy table (PROPOSED — прерываем; COMMITTED/BLOCKED — порог; **EXECUTING traversal — прерываем verdict B; task/windup/sleep — INCUMBENT_PROTECTED**); гейты ①② мигрированы на enforce_for_intent; P1 parent-lookup (history-search PRIORITY_SUPERSEDE с terminal_tick==tick, fallback None).
⚙️ **Э4 (verdict B):** traversal EXECUTING прерываем (снятие защиты только для executor='traversal'; born-EXECUTing Н-50 делает строгий D-4 мёртвым в production; bootstrap-семантика: движение прерывают только SURVIVAL(6)/WINDOWED(7), SOCIAL(3) — нет).
⚙️ **Э5 (зеркала):** `svc/action/commitment_registry.py` — _commit_nonsuperseding (R2/F12: авто-supersede запрещён в зеркалах = зомби), mirror_task_committed (canonical-only, D-8: produces_claim ∨ has_prop), mirror_task_terminal (EXECUTING/COMPLETED/FAILED/CANCELLED/EXPIRED/INTERRUPTED, executor-мисматч-гвард), mirror_windup_committed (held_intent_id:=commitment_id, D-1), mirror_task_expired_by_ref (M-29 purge → EXPIRED строго по executor_ref), reconcile_sleep_ownership (D-3: state-based Y6-инвариант — coupling∈{SLEEPING,REM}⇒commit; wake⇒COMPLETED; vanish⇒INTERRUPTED(SLEEP_VANISHED)), sweep extension (TASK_GRACE_TICKS=25 safety-net для task/windup/sleep, TASK_VANISHED/WINDUP_STALE_INTENT/SLEEP_VANISHED). `svc/game_loop/task_scheduler.py` — outbox + _record_task_outcome + drain_commitment_outbox (D-2: воркер никогда не пишет реестр; sync-дренаж на входе execute_pending + безусловно из idle_tick), 9 терминальных хуков (PROCESSING/COMPLETED/FAILED-error/FAILED-crash/CANCELLED-no-executor/CANCELLED-reconstruction×3/CANCELLED-DEDUP). `svc/phases/post_decision.py` — canonical task mirror в Фазе 6, M-29 purge → EXPIRED, windup creation mirror (held_id:=commitment_id), Phase 7 terminal hooks (INTERRUPTED→WINDUP_STALE_INTENT, COMPLETED). `svc/tick_orchestrator.py` — sleep reconciliation после Фазы 0.6. `svc/game_loop/__init__.py` — безусловный drain в idle-окне.
⚙️ **Э6 (персистентность, Н-40):** `dom/action_windup.py` (to_dict/from_dict), `dom/communication.py` (CommunicationIntent + ExposureLevel to_dict/from_dict), `dom/epistemology.py` (Proposition to_dict/from_dict); миграция 11 точек доступа: orchestrator._windup_registry → ctx.scene_state["windup_registry"] (строковый ключ _windup_key, F3: tuple→"campaign::actor"), orchestrator._pending_intents → ctx.scene_state["windup_held_intents"] (CommunicationIntent.to_dict при store, from_dict при load). Round-trip тесты (§12 WARA). Ownership переживает restart.
⚠️ **Инциденты сессии:** (1) **Дубль S203.3-блока в traversal_schema.py** — попал в HEAD релизного коммита d5d083c6 (вероятно merge-conflict; вторая копия перезаписывала первую → PRIORITY_SUPERSEDE отвергался). Ремедиация: удаление дубликата (−114 строк). Урок: при живых параллельных сессиях — аудит целевого файла на дубликаты определений перед каждым применением патча; (2) **W2 cross-zone hotfix** (DIAGNOSTIC_PROBE_CRASH) — чужой диагностический зонд `_opp_will = state.will_state.value` в npc_tick_pipeline:573 (ADR-O-366) читал несуществующее поле TickState.will_state → TICK_CRASH каждого тика Phase 5 → каскад NPC-MOVE/TRAV-DICT/DIALOGUE-INIT. Санкция Мастера: getattr-деградация до None. Урок в протокол: DIAG-PROBE-SAFETY (failure of diagnostics must never abort simulation phase) — предложен в Устав §11; (3) **[ECO] domain_phases write-guard** — оживление Phase 5 (после W2) вскрыло latent: Direct write to NPCState.stress мимо StateApplicator (чужая зона, non-blocking, guard перехватывает); (4) **ActionWindup F821** — пропуск импорта в Phase 7 при миграции Э6-c → NameError → TICK_CRASH → загрязнённый save → каскад. Fix: restore import + delete corrupted save; (5) **isinstance hotfix** (чужой temporal-commitment код, ADR-O-366) — параллельная сессия добавила loop `for _tc in active_commitments[npc_id]:` ожидая list, но наш реестр хранит single dict (закон №1) → итерация по dict-keys (строкам) → .get() crash. Fix: isinstance-гард (dict→[dict], non-dict→skip). Cross-zone, санкция не требовалась (применено как W2-класс). Эскалация: параллельной сессии — их temporal-commitment модель конфликтует с one-owner-per-NPC (наш закон №1); нужен координационный ADR.
⚠️ **Координация:** параллельная сессия (ADR-O-366 OpportunityProducer, lab M1 ScenarioPlayer/Graphs S220-S222) активна в общем рабочем дереве; их изменения в npc_tick_pipeline.py, task_scheduler.py (FIX [4] sync fast-path), calibration, frontend — зафиксированы, не откатывались. Наш вклад: action_commitment, action_priority (новый), traversal_schema, commitment_registry, commitment_arbiter, post_decision, tick_orchestrator, task_scheduler, game_loop/__init__, IPT, test_action_commitment — наши зоны, не пересекаются. ruff-auto-fix каскад на tick_orchestrator (63 фиксов, 12 remaining F821/F841 pre-existing легаси) — зафиксирован как CI-долг.
📁 dom/action_priority (новый), dom/action_commitment, dom/traversal_schema, dom/action_windup (to_dict/from_dict), dom/communication (to_dict/from_dict), dom/epistemology (Proposition to_dict/from_dict), svc/action/commitment_registry, svc/action/commitment_arbiter, svc/phases/post_decision, svc/phases/simulation, svc/phases/movement_bridge, svc/game_loop/task_scheduler, svc/game_loop/__init__, svc/tick_orchestrator, svc/npc/npc_tick_pipeline (W2 hotfix + isinstance hotfix — чужая зона), tests/test_action_commitment (+45: priority 5 + contract 7 + arbiter 9 + mirrors 6 + outbox 3 + windup-serial 2 + intent-serial 2 + sweep 2 - old exempt 1), tests/IPT (_NoOpScheduler.drain_commitment_outbox), tests/sandbox/SUPERBOX/scenarios/action_integrity_test (fail_reason="TASK_IMPOSSIBLE"), docs/ADR (ADR-O-365), docs/audits/ADR-O-365_IMPACT (новый)
IPT: 43/1 — единственный красный INV-SILENT-FAILURE (downloader.py ×3, чужая зона S217/S218). Наш профиль — полностью зелёный (INV-FRONTEND-ISOLATION ✅ — параллельная сессия починила lab_screen между нашими прогонами). КРАСНЫЕ ИНВАРИАНТЫ: было 2 🔴 → стало 1 🔴 (один чужой устранён параллельной сессией, новых не внесено)

### S224: ТЗ-RE-01 Relationship Engine — Фаза A / M0: онтологический контракт (ADR-O-369) | ✅ IPT 44/44
🎯 Зафиксировать онтологическую границу Relationship Engine как формально ограниченную область (ТЗ-RE-01 v1.9, §10 фаза A / §8.6 M0) — до единой строчки рантайма: фазы B+ физически не могут незаметно добавить второй SSOT, второго writer'а или новый психологический агрегатор.
⚙️ Артефакты: architecture/relationship_engine.yaml (45 узлов: 36 строк §5.0 в классах I/II/III/IV/TOMBSTONE/FORBIDDEN + 8 компонентов §4.1 + FrustrationByNeedProjection; 15 edges; 9 constraints; запреты №1-35 с картой enforcement grep/schema/test_deferred/review; tombstone-параметры §6.19: g, k_up/k_down, τ_n, η_s, β/T_half, H_i/ρ, σ, DeprivationHorizon; мораторий №35.2 до закрытия Р18; Р17-INV-1; COLLISION-решение frustration: владелец NeedLevel.frustration, §5.2-поле = read-only проекция — семантическая эскалация в GPT зафиксирована, в ТЗ v1.9 коллизия §5.1/§5.2 жива). scripts/lint_relationship_engine.py: канонический набор узлов ЗАКРЫТ (новый узел = вердикт GPT + ADR); scoped-греп запрещённых классов имён ТОЛЬКО в backend/app (граница механика/контент №35; allowlist канона: truth_state_tavern.json, lusya.json, village_relations.json); ядро имён захардкожено в линтере и сверяется с yaml (стена заморозки не разбирается изнутри); noqa: RE35 для аудируемых исключений. Регистрации: CI-шаг + pre-commit hook. Доки: ADR-O-369 в атласе (DOM-06&09), ADR-O-369_IMPACT.md, секция 13 DTO-реестра. YAML ≠ второй источник истины (вердикт Мастера): формулы §6 и числа не переносятся.
⚙️ Гейты M0 (все зелёные): ADR-номер = max(368)+1; frustration writers = 0; tombstone-остатки = 0 (24 паттерна); allowlist = ровно 3 файла; build_graph loader — инжекция domain подтверждена кодом, совместимость доказана (RELATIONSHIP в ARCHITECTURE_FLOW_GENERATED, гробницы визуализированы); node-id анти-коллизия; IPT baseline 44/44 == после.
⚙️ Попутно закрыт незакрытый IPT-гейт S217: downloader.py 3× except:pass → logger.debug (INV-SILENT-FAILURE красный → зелёный) + ruff-долг файла (19 автофиксов + E701). 
⚠️ Долги, поднятые сессией (чужие зоны, эскалация Мастеру): (1) DEBT-DOC-DRIFT-228 — validate_doc_refs.py: 228 битых file:line-ссылок в pre-existing файлах (ARCHITECTURE_FLOW_GENERATED от чужих yaml code_ref; TZ_Laboratoria; domain_*.md; ENIGMA_TZ_ISPRAVLENIE и др.) — вклад M0 = 0, но CI-гейт уровня 8 у проекта фактически красный; (2) [ECO] guard-отклонение прямой записи NPCState.stress из domain_phases (живой долг в ядре, ловится write-guard'ом); (3) RelationshipStore (существующий) vs RelationshipStateStore (новый контракт) — reconcile при M1.
📁 architecture/relationship_engine.yaml (новый), scripts/lint_relationship_engine.py (новый), docs/ADR*.md, docs/audits/ADR-O-369_IMPACT.md (новый), docs/DTO Registry*.md, .github/workflows/ci.yml, .pre-commit-config.yaml, backend/app/services/llm/downloader.py
IPT: ✅ 44/44 (до == после; INV-SILENT-FAILURE красный → зелёный). КРАСНЫЕ ИНВАРИАНТЫ: было 1 🔴 → стало 0 🔴

### S225: SMOKE-GORAN β + Delivery Fix + OpportunityProducer + 021 Calibration + Temporal Runtime | ✅ IPT 44/44, GORAN β GREEN

🎯 Финальная закрытие causal spine до temporal layer: доказана полная
   причинная цепочка THEFT→OBSERVE→BELIEF→WARN→PLAYER BELIEF→ACCUSE в
   production path; внедрён OpportunityProducer (world→decision);
   построена CalibrationProfile (40 калибруемых параметров); построен
   Temporal Runtime (Phase 4.5/5.5, contract с 6 поправками Мастера).

⚙️ Пять крупных блоков:

**1. SMOKE-GORAN β harness** (smoke_goran_beta.py — полная перезапись):
   β-hybrid по прецеденту S214: авторинг will_state (psyche["state"]=
   "deceptive") + G1-DIAG (прямой production-compute с фиксированным
   OpportunityContext) + инъекция steal-intent в production Фазу 6 →
   windup → живые тики отпускают THEFT → ObservationSubscriber → belief
   → epistemic_modifiers → DecisionHub WARN → fast-path delivery →
   NPC_SPOKE → ClaimEventSubscriber → player belief → ACCUSE gate.
   Замороженная геометрия (single-variable Control: только позиция
   Goran отличается). Delivery polling (tick→execute_pending→settle→poll).
   save_scene_state fix: get_scene_state при _tick_locked=False возвращает
   свежую копию из persistence; Phase 6 пишет windup в копию, оркестратор
   грузит другую → windup потерян. Фикс: save_scene_state(CAMPAIGN, _scene)
   после injection → persistence обновлён → lock_for_tick грузит с windup.
   7 прогонов: 4 RED (delivery latency / scene_state mismatch) → 3 GREEN
   (fast-path fix + save_scene_state fix). Метрики M1-M10 + Control.

**2. Delivery fix** (task_scheduler.py:138):
   Root cause: max_workers=1 (ADR-O-343) + fast-path submit (async, не
   sync как комментарий обещал) + R4A 300s backoff timer → pool clog →
   warn tasks ждут за медленными R4A tasks. Недетерминизм: 1 tick (backoff
   активен) до >12 ticks (backoff истёк). Фикс: `_executor_pool.submit(...)
   → _process_tasks_async(...)` (прямой вызов, синхронно). LLM-задачи
   остаются на пуле (ADR-O-343 не нарушен). Non-LLM (warn/steal/spread_
   rumor) исполняются мгновенно. Verified: runs 6+7 GREEN, tick=1 stable.

**3. ADR-O-366 OpportunityProducer** (npc_tick_pipeline.py):
   DEBT-OPP-PRODUCER: pipeline:559 не передаёт opportunity_ctx → default
   OpportunityContext() (attention=1.0, allies=0) → score=0.0 → скрытые
   действия (STEAL S209 + R6.3 BROKEN-unlocks) недостижимы в живых тиках.
   Доказано в vivo: thief_shadow intent=IDLE score=0.0 в 7 прогонах.
   Фикс: inline construction OpportunityContext из state.spatial_query
   (real distance) + epistemic_ctx.perceived_allies (subjective) + proxy
   player_attention (proximity, not gaze — Phase 3). INVARIANT: producer
   = DATA only (no Intent/score/unlocked). Acceptance: A (control, no
   producer → IDLE) ✅; C (geometry, player close → no STEAL, behavioral
   change IDLE→OBSERVE) ✅; B (player far → STEAL) ⏳ requires real player
   movement (frozen sq не доходит до state.spatial_query — оркестратор
   перетирает shared_context.spatial_query каждый тик).
   DEBT-OPP-PRODUCER: CLOSED.

**4. 021 CalibrationProfile Phase 1**:
   calibration/profile.py (новый): CalibrationProfile (frozen dataclass,
   40 fields). calibration/config_overlay.py: overlay_module_attrs +
   overlay_profile (extension for non-core/constants modules). 7
   extractions (inline → module-level, behavior-identical):
   dialogue_executor _L_TIMEOUT_SEC; task_scheduler _DIALOGUE_TTL /
   _UI_TTL_SEC / _MAX_TASKS_PER_TICK; npc_tick_pipeline _OPP_ATTENTION_
   RANGE_M; belief_revision_engine _CLAIM_WEIGHT / _SAME_SOURCE_BOOST.
   Acceptance A-F: Profile import ✅, overlay applies+restores ✅, no
   duplicate truth ✅, behavior-identical ✅ (IPT 44/44), GORAN β GREEN ✅.
   Phase 2 (deferred): ~20 inline literals в decision_hub.py + 2 class
   attrs в dialogue_queue (MAX_PENDING_TASKS/MAX_RATE_PER_MINUTE).

**5. Temporal Runtime** (Stage 6):
   Contract (6 поправок Мастера): (1) validity≠success — две отдельные
   проверки, COMPLETED только на success_check=True; (2) три terminal
   states (COMPLETED/CANCELLED/EXPIRED) — отдельные, с reason; (3)
   prediction≠validity≠success — prediction=description (не executed),
   validity="can continue?", success="did occur?"; (4) HOLD="don't
   take new proactive", NOT "ignore reactive" — reactive всегда passes
   BEFORE hold; (5) named rules via registry (not lambdas, replay-safe);
   (6) intent-specific TemporalSpec — DecisionHub produces Intent →
   registry lookup → temporal semantics → TemporalCommitment.
   domain/temporal_specs.py (новый): 4 intent types (STEAL/ATTACK/
   APPROACH/EAT), VALIDITY_RULES + SUCCESS_RULES registries, REACTIVE_
   PREEMPTION_EVENTS (narrow: combat+proximity+player, NOT npc_spoke/
   npc_moved/communication_claim), is_reactive_preemption predicate.
   Phase 4.5 (Temporal Validation) в npc_tick_pipeline.py: immutable
   order reactive→success→validity→expiry→HOLD. Reactive suppression
   (proactive -10, same mechanism as sleep penalty). Phase 5.5 (Temporal
   Commitment): after DecisionHub, if proactive intent has TemporalSpec →
   create commitment in scene_state["active_commitments"].
   Acceptance: STEAL interruption PASS (preemption+validity); EAT
   completion PASS (success+validity); IPT 44/44; GORAN β GREEN.

📁 Files:
   - backend/app/domain/temporal_specs.py (новый)
   - backend/app/services/calibration/profile.py (новый)
   - backend/app/services/calibration/config_overlay.py (overlay_module_attrs + overlay_profile)
   - backend/app/services/npc/npc_tick_pipeline.py (OpportunityProducer + Phase 4.5/5.5 + extraction)
   - backend/app/services/game_loop/task_scheduler.py (fast-path fix + 3 extractions)
   - backend/app/services/execution/dialogue_executor.py (extraction)
   - backend/app/services/npc/belief_revision_engine.py (2 extractions)
   - backend/tests/sandbox/SUPERBOX/scenarios/smoke_goran_beta.py (полная перезапись)
   - docs/audits/ADR-O-366_IMPACT.md
   - docs/ADR (Architecture Decision Records).md (+ADR-O-366)

⚠️ Координация: параллельная сессия добавила DIAG-OPP hotfix в
   npc_tick_pipeline.py (sanctioned by Master W2) — safely degrades
   to None when state.will_state absent. INV-FRONTEND-ISOLATION
   (lab_screen.py) и INV-SILENT-FAILURE (downloader.py) исправлены
   параллельными сессиями → IPT 44/44.

IPT: ✅ 44/44 (ALL GREEN — zero red invariants).
КРАСНЫЕ ИНВАРИАНТЫ: было 2 🔴 (pre-existing) → стало 0 🔴.

Долги:
   - DEBT-OPP-PRODUCER: CLOSED (producer wired, A+C proven, B needs gameplay)
   - DEBT-R4A-BLOCKING: R4A blocks main thread ~3-6s (non-critical post fast-path fix)
   - Calibration knife-edge: conf=0.50=threshold=0.50 (candidate 021 sweep)
   - shared_context.spatial_query lifecycle: orchestrator overwrites echelon-5
   - Phase 2 calibration: ~20 inline literals decision_hub + 2 class attrs
   - "Фаза 6: 0 intents → EventDTO" при comm_built=True (routing puzzle)
   - save_scene_state: get_scene_state returns fresh copy when _tick_locked=False
   - Model config mismatch: Q4_K_M configured, Q5_K_M file present (non-blocking tests)

### S226: W-track Audit + W0 Semantic World | ✅ IPT 44/44, W0-1..W0-5 PASS

🎯 Переход от Temporal Runtime к World/Embodiment Foundation (W-track).
   Сначала аудит coupling'ов (TZ §18 — обязательный deliverable), затем
   минимальный семантический substrate: объект существует в симуляции
   независимо от renderer.

⚙️ **1. AUDIT_W_TRACK_COUPLINGS** (docs/audits/AUDIT_W_TRACK_COUPLINGS.md):
   8 search patterns из TZ §18.1 (pygame import, sprite_id/model_id в
   domain/models, sprite/texture/mesh/animation_clip в domain, age→model
   switch, injury→sprite, object_state→sprite, presentation_firewall,
   animation в action_commitment). Результат: ALL EMPTY — ZERO hard
   couplings. Codebase уже следует 4-уровневой архитектуре (World→Embodied
   →Presentation→Rendering), enforced by CAUSAL CONTRACT §1.1, DTO Registry,
   presentation_firewall.py (acceptable adapter). W-track proceeds directly
   to W0 — no cleanup/migration needed.

⚙️ **2. W0 — Semantic World** (domain/world_object.py + semantic_action.py):
   WorldObject (frozen dataclass): object_id, archetype, location_id,
   position (метры, не пиксели), state (archetype-specific FSM string),
   topology_relations, affordances, ownership, containment, occupancy,
   holder, damage, interaction_history_ref. НИ ОДНОГО поля sprite/model/
   texture/mesh/animation (INVARIANT W0). WorldObjectState enum (INTACT/
   DAMAGED/BROKEN/DESTROYED — base damage track; W3 добавит archetype FSMs).
   WorldObjectRegistry: in-memory store (spawn/get/update/query_by_location/
   clear). Serialization: to_dict/from_dict (round-trip для scene_state).
   SemanticAction (frozen dataclass): action_type (OPEN/TAKE/CARRY/PLACE/
   SIT/STAND/USE/ENTER/EXIT/EQUIP/UNEQUIP/ATTACK), target_object_id,
   target_location_id, target_attachment_slot, preconditions. Precondition
   (frozen dataclass): predicate (named rule ID — resolved via W2 registry),
   args (Tuple). НИ ОДНОГО поля animation_clip/sprite/model (INVARIANT W0).

⚙️ Acceptance: W0-1 (object exists without renderer fields) PASS;
   W0-2 (state transition CLOSED→OPEN) PASS; W0-3 (serialization
   round-trip) PASS; W0-4 (SemanticAction renderer-free) PASS;
   W0-5 (registry query by location) PASS. IPT 44/44 (additive — new
   domain files, pipeline не затронут).

📁 backend/app/domain/world_object.py (новый)
📁 backend/app/domain/semantic_action.py (новый)
📁 docs/audits/AUDIT_W_TRACK_COUPLINGS.md (новый)

IPT: ✅ 44/44 (ALL GREEN). КРАСНЫЕ ИНВАРИАНТЫ: 0 🔴 → 0 🔴.

### S227: Stage 2B.1–2B.3 — Body State Contract + Energy Dynamics + Hydration | ✅ pytest 104/104, IPT 44/0 (ВСЕ ЗЕЛЁНЫЕ)
🎯 Открытие Stage 2B (Body/Homeostasis) после закрытия Stage 2A (S203.4/S223). Первый кирпич: PhysiologicalTransition контракт — тело как причинная модель, изменяющаяся во времени. Доказан на искусственной переменной (energy), затем расширен до load-dependent dynamics и hydration. Мастер-директива: «тело не обязано быть точной копией человеческой биологии — оно обязано быть достаточной причинной моделью».
⚙️ S2B.1 (Body State Contract): dom/delta_payloads (+energy_delta, +hydration_delta), models/npc_state (+energy, +hydration, +body_mass в BODY_STATE_HEALTHY), svc/npc/state_applicator (+extraction v2 pattern, +_apply_physiology_deltas energy/hydration clamp 0-100, +signature params), svc/body/body_engine (НОВЫЙ: pure calculator — handle(npcs, campaign_id, tick) → List[StateDeltas]; reads body_state SSOT НЕ top-level полей; NEVER writes; registered в Phase 0.5 через add_idle_handler). Pipeline: BodyEngine → StateDeltas → delta_buffer → StateApplicator → body_state — единый mutation spine. Δt = GAME_TICK_INTERVAL_SECONDS — единственный временной вход. Нет wall-clock, нет RNG.
⚙️ S2B.2 (Energy Dynamics): BodyEngine расширен от константного к нагрузочной функции: expenditure = BASE_RATE * load * body_mass; recovery = BASE_RATE * (1-load) * sleep_bonus(coupling). Activity load: IDLE(0) < REST(0.1) < WORK(0.5) < WALK(0.7) < RUN(0.9). Sleep bonus: coupling ∈ {SLEEPING, REM} → recovery × 3.0. 5 экспериментов: determinism, monotonicity, recovery+sleep, replay, body-mass sensitivity.
⚙️ S2B.3 (Hydration): one-way loss (no passive recovery — drinking = action, future). BASE_HYDRATION_LOSS × (1+load) × body_mass. 4 эксперимента: baseline-loss-at-idle, monotonicity, determinism, body sensitivity.
⚠️ Координация: temporal_specs.py (параллельная сессия ADR-O-366) — комплементарен (читает body_state, не пишет). ruff-auto-fix каскад на state_applicator/game_loop (pre-existing легаси). [ECO] domain_phases write-guard (чужая зона, non-blocking).
📁 models/delta_payloads, models/npc_state, svc/npc/state_applicator, svc/body/body_engine (НОВЫЙ), svc/game_loop/__init__, tests/test_action_commitment (+14 tests)
IPT: 44/0 — ВСЕ ЗЕЛЁНЫЕ. КРАСНЫЕ ИНВАРИАНТЫ: 0 🔴 → 0 🔴

# Шаг 5 — аутопсия закрыта: гипотеза доказана на 100%, три вывода

1. **Трейсбек:** упал ровно мой `assert not hasattr` — репр в трейсбеке сам показывает `PhysiologyPayload(..., energy_delta=0.0, hydration_delta=0.0, ...)`.
2. **Дерево:** W-TRACK уже завезла оба поля в `delta_payloads.py` (незакоммичено; их же комментарии «S2B.1 proof-of-concept», «Real hunger/fatigue — после контракта S2B.2+»).
3. **Коммит `5926e7e5`: 29 passed на чистом checkout** — коммит самодостаточен; красный существует только в живом дереве.

**Итог:** санация (гард) — корректна и нужна была (доказана аутопсией `17930e9f`, где полей нет); дефект — в моём тесте, пинившем отсутствие полей чужого WIP (трипвайр на их прогресс, не на дефект), плюс мой sequencing-промах — коммит ушёл при красном. Исправляю оба.

**Бонус-находка при сверке состава `17930e9f`:** артефакт 4 (DTO-реестр) в коммит **не вошёл** (7 файлов, DTO Registry отсутствует) — как и IMPACT в первый раз, я выдал его сводкой без листинга. Проверяю и закрываю в этом же follow-up.

### S228: ТЗ-RE-01 Phase B / M1a — субстрат потребностей + S225-санация cross-zone (ADR-O-370) | ✅ IPT 44/44, сьюта 29/29, полный pytest 926/3(pre-existing)
🎯 Первый рантайм-слой RE: RelationshipStateStore (scene_state["relationship_state"], static-сервис по прецеденту CommitmentRegistry; persistence — только atomic_commit, Foundation Freeze) + контракты NeedSlot/NeedLevel/PreferenceModel/HardConstraint/ExclusivityRequirement (домен, frozen, валидаторы, round-trip) + StateApplicator.update_needs (единственный runtime-writer, caller-guard, Cause-поверхность) + SSM-init пустого корня. Красный инвариант Мастера выдержан: МЕСТО ХРАНЕНИЯ без механизма изменения — стор dormant, тик байтово идентичен (IPT 44/44 до==после). Read: frozen DTO, read без мутации, повреждение — громкий отказ. Слоты sexual+intimacy; attachment отсутствует (гейт АТ-1..3); needs-конфиг НЕ заведён (параметризация — фаза M).
⚙️ Коммиты: 17930e9f (M1a, 7 файлов; 28-сьюта) → 5926e7e5 (S225-санация: getattr-гарды S2B.1/S2B.3 energy/hydration — latent AttributeError подтверждён аутопсией 17930e9f: полей в payload НЕТ, прямой доступ падал бы ДО default-аргумента) → follow-up (тест версионно-агностичный + DTO-статус).
⚙️ Атрибуция 3 branch-red (test_audit_quick_wins::t5, decision_hub_goal_boost, opportunity_engine::non_broken_will): PROVEN pre-existing бисекцией a5f45048→1ac78fa2→17930e9f (все 3 FAIL) — M0/M1a исключены; эскалация Мастеру как веточный долг.
⚠️ Инциденты-уроки сессии (мои): (1) патч с «условным применением» не выдаётся — сначала факт сигнатуры (SyntaxError apply_physical, пойман compileall, закрыт в сессии); (2) гейт коммита обязателен и безусловен по зелёному — 5926e7e5 ушёл с красным тестом в живом дереве (самодостаточен на checkout, но sequencing-промах зафиксирован); (3) тест не пинит чужой WIP — hasattr-ассерты на поля параллельной сессии заменены версионно-агностичными; (4) артефакт-листинги выдаются полностью, не сводками (IMPACT и DTO-обновление терялись дважды).
⚠️ Эскалации: W-TRACK coordination — их S2B-код (extraction energy/hydration + body_state-записи) проехал в 17930e9f (git add целого файла); гард совместимости поставлен, при их коммите полей гард станет мёртвым-не-вредным; поля в рабочем дереве уже есть. DEBT: identity-дельты теряются в apply_deltas_only-пути (чужая зона, наблюдение); 3 pre-existing branch-red; DEBT-DOC-DRIFT-228 (из S224).
📁 domain/relationship_contracts.py (новый), services/social/relationship_state_store.py (новой), services/npc/state_applicator.py (+update_needs, санация F821×2/F841×4/S2B-гарды), services/scene_state_manager.py (init-ключ), tests/test_relationship_state_store.py (29), docs/ADR (ADR-O-370), docs/audits/ADR-O-370_IMPACT.md, DTO Registry
IPT: ✅ 44/44. КРАСНЫЕ ИНВАРИАНТЫ: 1 🔴 (S217 downloader) → 0 🔴 (закрыт в S224)

---

### S229: Stage 2B.4 — Nutrition (третья физиологическая переменная BodyEngine) | ✅ pytest 110/110 (commitment-файлы, +6), IPT 44/0
🎯 Nutrition как one-way stock (0-100) по механическому паттерну S2B.2/S2B.3. Мастер-вердикты сессии: BASE_NUTRITION_LOSS=0.05 — v1 calibration constant, НЕ физиологический закон (иерархия временных масштабов: hydration → быстрый кризис, nutrition → медленный); NUTRITION_LOAD_COEFF=0.5 (< гидратационного 1.0); инварианты иерархии — ДВЕ отдельные проверки (базовая ставка и load-коэффициент порознь + поведенческая на load∈{0, 0.5, 0.9}) — калибровка не инвертирует отношение молча; nutrition = STOCK, НЕ hunger (derived homeostatic pressure — S2B.10; слои: тело → физиологические величины → derived homeostasis → pressure → affordance → decision); Δt-семантика per-tick как в S2B.1-2B.3 (размерная Δt — отдельный калибровочный ADR, вердикт Мастера). ADR не создавался: механическое расширение по прецеденту S2B.1-2B.3, управляющий документ — Master-директива 2026-08-28.
⚙️ Патчи: models/delta_payloads (+nutrition_delta: float = 0.0 — non-breaking, combat-продюсеры не мутируют физиологию S2B молча); models/npc_state (+"nutrition": 100.0 в BODY_STATE_HEALTHY — все 8 точек инъекции dict(BODY_STATE_HEALTHY) в game_loop/life_engine/npc_loader наследуют автоматически; старые сейвы — через .get(…,100.0) в clamp); svc/npc/state_applicator (4 точки: extraction v2-паттерн / проброс / параметр сигнатуры / init-default + clamp 0-100 — single-writer путь не изменён); svc/body/body_engine (константы + формула nutrition_delta = -BASE_NUTRITION_LOSS × (1 + load×NUTRITION_LOAD_COEFF) × body_mass; эмиссия + payload; pure calculator не тронут — нет wall-clock/RNG/записей). Wiring верифицирован: game_loop/__init__.py:289-292 add_idle_handler(BodyEngine()) — Phase 0.5, nutrition едет в том же handle(). Тесты +6 (TestS2B4Nutrition): baseline-loss-at-idle (== -0.05), monotonicity (IDLE>WALK>RUN), determinism, body sensitivity (mass 0.8 vs 1.2), slower_than_hydration_invariant (инвариант Мастера), nutrition_clamp_to_zero (зеркало S2B.1, applicator-chain).
⚙️ Гейты: pytest 104→110 (commitment-файлы); RE-сьюта 29/29 (не тронута — общий позвоночник без регрессий в обе стороны); ruff на 5 файлах — 2 pre-existing вне наших строк (npc_state F821 CausalChain:823, F841 ss:1073); IPT 44/0; дубль-аудит V1-V4 — все паттерны ровно 1 раз.
⚠️ Координация: (1) анти-race отработал: S228 занят RE-сессией (ADR-O-370) между ходами — номер S229 = max+1 по фактическому хвосту на момент записи; (2) модель Мастера зафиксирована: RE M1a/M1b = отдельный домен LOVE/SEX/RELATIONSHIP (tombstones: Infatuation/love_score/RelationshipValue/RomanticMarket/линзы; Р17-INV-1; мораторий readout до Р18) — пересечение S2B×RE только общий позвоночник state_applicator (S2B-точки в physiology-ветке, RE update_needs — отдельная; обе стороны гейтово зелёны) и будущий поведенческий уровень BODY × RELATIONSHIP × SOCIAL CONTEXT → ACTION; из S2B не редактируется ни один RE-артефакт (Patch 6 отменён: version-agnostic редакция владельца сильнее и покрывает nutrition-extraction бесплатно); S2B-код не содержит love/sex-сущностей и агрегаторов (запрещённый список — ноль вхождений); (3) S228-запись RE задокументировала таймлайн S2B-полей (17930e9f вёз S2B-extraction без полей → гарды 5926e7e5 → version-agnostic тест) — совместимо с археологией этой сессии.
⚠️ Долги: [LEGACY-HUNGER→S2B-track] life_engine.py:476-482 — писатель body_state["hunger"] (8.0/тик, dormanted гардом «hunger in body_state»): stored-hunger умирает при S2B.10 (hunger = derived pressure поверх nutrition stock; закон №11 — единая проекция физиологии); [DUAL-TIME] TICKS_PER_DAY=24 («1 тик=1 час», constants.py:183) vs GAME_TICK_INTERVAL_SECONDS=10 — оси расходятся 360×; потребители календарной оси: models/temporal.py:34-35, svc/temporal/temporal_engine.py:62-63, svc/economy/economy_tracker.py (daily needs / talk-cooldowns), svc/game_loop/scene_init.py:204-209; S2B.4-калибровка безосевая (в тиках: nutrition 100→0 = 2000 тиков покоя / ~1333 при load=1; hydration 500/250; иерархия 4:1 инвариантна выбору оси) — эскалация Мастеру: выбор авторитетной оси физиологических ритмов; [DOC-DRIFT] запись S227 заявляет body_mass в BODY_STATE_HEALTHY — ключа в файле нет (§13.5), body_mass = placeholder-read (реальная масса S2B.7+); [DOC-DRIFT] SANATION-комментарии applicator устарели с S227 (гард мёртв-не-вреден); полный pytest, два независимых прогона — tests/ (1287 collected) и no-arg повтор (1385 collected; W1-верификация: ОБЕ команды collect-only дают 1390 — различия scope НЕТ, разница 1287→1385→1390 = live-tree drift параллельных сессий, дерево горячее; числа полных прогонов = снимки момента, сравнимы только с таймстампом): множество отказов ИДЕНТИЧНО (12=12, одинаковые ID; 11 видимых G2 ⊂ 12 no-arg при равных счётчиках — скрытый идентифицирован математически). 12 failed = 3 main-layer pre-existing (атрибуция S228, бисекция) + 9 tests/sandbox/: (а) hp_double_truth + causal_closure×2 + life_direction_crisis — 4× stale-тесты с прямыми записями NPCState.hp/.perceptual_kernel, красные с ADR-WRITE-GUARD (S212); (б) causal_movement×2 — drift контракта IntentSemanticField (обязательное поле action, тесты шлют action_type/raw_text); (в) observer_out_of_radius_no_belief — убеждение вне радиуса, эпистемика наблюдения (кандидаты S206/S207/S228); (г) boundary_snap — test-pollution: соло-файл и 8-тестовое подмножество ЗЕЛЁНЫЕ при живом S2B.4-диффе, оба полных прогона КРАСНЫЕ; ингредиент не локализован (санационная сессия); (д) superbox_014_second_order_attribution — pre-existing ≤S213, задокументирован и эскалирован в записи S213 («файл не менялся с V.0.5.3.8.1»; кандидаты S206/S211), присутствует в историческом кэше. Метод атрибуции: трейсбеки (A3/A4) + полное имя-множество no-arg-повтора + исторический pytest-кэш backend/.pytest_cache (~65 записей эпохи ~S225–S226 — летопись тест-здоровья, не источник истины; урок кэшей: активный кэш определяется rootdir и верифицируется, а не угадывается по наличию директории — backend/tests/.pytest_cache оказался пустышкой). Stash неприменим: рабочее дерево несёт незакоммиченный вклад S223–S229 — откат = уничтожение чужой работы. Ни один из 12 не пересекается с S2B.4-диффом по механизму. Sandbox-слой не покрывался гейтами сессий (S227 — commitment-файлы; S228 — main+сьюта) — эскалация Мастеру: санационная сессия behavioral-слоя ДО S203-G long-horizon (иначе метрики §27 ТЗ Stage 2 считаются по гнилой базе). НЕ сделано (scope): hunger engine, eating AI, fatigue (S2B.5), потребители nutrition до S2B.10/11, love/sex/RE-сущности.
📁 models/delta_payloads, models/npc_state, svc/npc/state_applicator, svc/body/body_engine, tests/test_action_commitment (+6)
IPT: ✅ 44/0. КРАСНЫЕ ИНВАРИАНТЫ: 0 🔴 → 0 🔴

### S230: W1 Spatial Topology — Object Relation Substrate (ADR-O-371) | ✅ IPT 44→45/45, pytest 30/30, GORAN β GREEN
🎯 Первое персистентное звено W-track: объектная топология мира как реляционно-нормализованный субстрат над scene_state["world_objects"]. W0 (orphan PoC, 0 потребителей, 0 тестов) поглощён и нормализован без миграции (subtree никогда не персистился).
⚙️ Онтология (Мастер GO по D1–D7): семь отношений ТЗ §20 canonical single-side на WorldObject (LOCATED_AT=location_id+position; HELD_BY=holder; OCCUPIED_BY=occupancy; CONTAINED_BY=container_id; SUPPORTED_BY=supported_by; ATTACHED_TO=attachment(host,slot) атомарно; USED_BY=used_by — независимая ось); CarrierMode (FREE|HELD|CONTAINED|ATTACHED) — ровно один, позиция авторитетна только в FREE; МАТРИЦА КОНФЛИКТОВ СВЕРХ CARRIER-РЕЖИМОВ — КАЛИБРУЕМАЯ ПОЛИТИКА, НЕ ОНТОЛОГИЯ (вердикт Мастера, дословно в ADR) — W1 policy-правил не содержит. Domain world_object.py переписан: frozen + __post_init__ guard (safe by construction), pure transitions (apply_relation_transition/relocate_object), STRICT release, NO auto-release (явная цепочка release→establish), фабрика build_world_object; УДАЛЕНЫ topology_relations / containment stored (→ inverse-запрос; mirror=зомби, урок S215) / affordances stored (pure function, вернётся W2 compute_affordances) / WorldObjectRegistry (процесс-глобальный). Services/world/world_object_store.py (новый): stateless стат. фасад над scene_state (прецеденты CommitmentRegistry/M1a) — read без lazy-init + громкий OntologyViolationError на повреждения; write ТОЛЬКО типизированными операциями (spawn/establish/release/relocate; generic update(**changes) отсутствует by construction); межобъектная валидация: циклы single-parent обходом, ghost-цели, опора FREE+та же локация, relocate блокируется SUPPORTED-зависимыми (содержимое следует владельцу). Snapshot-мост: WorldSnapshot.world_objects (deepcopy, конец dataclass, паттерн active_commitments S215) — пассивная фотография, ноль вызовов стора из тика. Persistence: НОЛЬ специального кода — subtree внутри atomic_commit_all/load_scene_at (Foundation Freeze); DoD доказан реальным SqlitePersistenceAdapter (spawn→relation→commit→reload→тот же объект + мутационный цикл). Отклонение от ТЗ §20.2 по археологии: WorldTopologyProvider НЕ расширен (tick-owned ETKE-IK поле, scene_state не видит) — канонический API на сторе; полевой мерж объектов — композиция W2. Runtime-writers: 0 (доктрина M1a — поведение тика байтово идентично); caller-guard отложен до W3 (легальный causal writer). Гейты: test_world_object_topology.py 30/30 (fixtures door/chair/container/carried_item — только тестовые, вердикт Мастера); INV-WORLD-OBJECT-TOPOLOGY (IPT №45, структурная онтология: live-часть условная — включится сама при W3-спавнере; smoke-часть держит контракт); architecture/world.yaml (новый домен WORLD, YAML-First) + build_graph.
⚙️ Попутно: закрыт залоговый долг S215 (dead imports time/uuid4/field + I001 в world_snapshot.py).
⚠️ Уроки протокола: (1) номер handoff ≠ номер сессии — верифицировать grep'ом хвост MUTATIONS (handoff был «S226», фактический — S230); (2) ruff auto-fix на untracked-файле невидим в git diff — дисциплина «сначала инвентарь --no-fix, потом точечный --fix»; (3) якорь-патч обязан опираться на факт файла — догадка о декларации INVARIANTS (без суффикса : List[Callable]) сломала бы якорь, поймана вставкой из файла до урона.
⚠️ Долги новые: DEBT-IPT-RUFF (24 pre-existing в IPT.py, вкл. F821 os undefined :1129 — NameError в error-пути INV-HP-SSOT при срабатывании); doc-drift §3.8 «max 15 инвариантов» vs 45. Параллельные сессии S227–S229 (Stage 2B Body State — W4-территория, вход W2 по ТЗ §21.1 — сверить их BodyState-контракт до проектирования resolver) — конфликтов файлов нет; эскалация S229 (санация sandbox-слоя, 12 pre-existing failed) — чужая зона, учтена.
📁 domain/world_object.py (переписан), services/world/ (новый пакет), models/world_snapshot.py (+world_objects, +импорт-санация), tests/test_world_object_topology.py (новый), tests/IPT.py (+INV-WORLD-OBJECT-TOPOLOGY), architecture/world.yaml (новый), docs/ADR (ADR-O-371), docs/audits/ADR-O-371_IMPACT.md
IPT: ✅ 45/45 (новый инвариант green). КРАСНЫЕ: 0 🔴 → 0 🔴

### S231: ТЗ-RE-01 M1b (часть 1: M1b.1+M1b.2) — миграционный адаптер + единый write-гейт пяти скаляров (ADR-O-371) | ✅ IPT 45/45, сьюта 118/118
🎯 Ликвидация двойной поверхности отношений до построения readout-слоёв (вердикт Мастера): M1b.1 — deterministic transform legacy JSON→v2 scene_state (Vacuum, .migrated-идемпотентность, скип-чистота, без headroom/round); M1b.2 — RelationshipWriteGate (routing-слой, whitelist 5 скаляров, NaN/foreign-key guard), D3-паритет против legacy update() доказан сеткой 8×8×5 ДО переноса writers.
⚙️ Принцип (ратифицирован): Writer знает только Gate; Gate знает backend; cutover (M1b.4) не мигрирует writers повторно. Шесть write-маршрутов через гейт: social_subscriber (6 вызовов), action_consequence_compiler (BLACKMAIL/HELP/ACCUSE), MemoryManager-фасад, StateApplicator SOCIAL-маршрут, rules_subscriber, decay (архитектурно: handler=produce Δ → delta_buffer → Applicator → Gate; доказано интеграционным тестом с канонической headroom-формулой). Semantic gate §8.6: комплимент — ОДНА направленная запись; зеркальная target→player и кэш-хирургия attraction УДАЛЕНЫ (тест-контракт ожидаемого изменения). Архитектурный proof увековечен тестами: ноль прямых writer'ов вне гейта; attraction-хирургия запрещена. Мёртвый apply_npc_state_updates помечен к удалению M1b.5 (0 вызовов, греп-доказательство).
⚙️ P0-инцидент 2026-08-30 (параллельно, по приказу Мастера): двойной llama-server на 8181 (VRAM 96% → 503 NARRATIVE → DRI 2%) — канонический процессный лок acquire_llama_server_lock (health + bind-проба) в server_lifecycle; оба спавнера (main._background_llm_startup, game_launcher._ensure_llm_running) спрашивают лок ДО Popen; живая верификация Count=1; DRI восстановлен 100%.
⚠️ Уроки сессии (5 sequencing-промахов: S225, M1b.2.3, P0 ×2, каждый — коммит при красном): протокол изменён — верификация и коммит физически раздельные сообщения; патчи на чужие файлы — только уникальный якорь + минимальный диф (инцидент двойной вставки main.py снят git checkout). Наблюдения: слепая зона lint_silent_failures (тела >1 оператора); relationship_cache-контур (fallback DecisionHub, base-init npc_loader, гидратация) — M1b.3; [CONFIG]-спам Q5-пути при живой Q4-модели — кандидату в настройках.
📁 services/social/relationship_write_gate.py (новый), relationship_state_store.py (+migration adapter), events/social_subscriber.py, events/rules_subscriber.py, player_cognition/action_consequence_compiler.py, memory/memory_manager.py, npc/state_applicator.py, game_loop/npc_state_helpers.py (пометка), services/llm/server_lifecycle.py (+lock), main.py, game_launcher.py, tests/test_relationship_state_store.py (118)
IPT: ✅ 45/45. КРАСНЫЕ ИНВАРИАНТЫ: 0 🔴 → 0 🔴

`### S232: W2 Affordances — Semantic Action Resolution (ADR-O-372) | ✅ IPT 45/45, сьюта W2 24/24, W1 30/30, ruff 0`

- 🎯 W2 ТЗ Часть II §21: pure-слой объектных affordances над W1-субстратом — «мир определяет, что доступно; тело — может ли NPC». Substrate-only, 0 runtime-потребителей.
- ⚙️ semantic_action.py (коррекция W0-остатка): закрытый enum WorldActionType (19, §19.2; INSERT/REMOVE_ITEM зарезервированы до W3 — compound без поля второго объекта); STAND→STAND_UP. body_state_view.py: frozen read-model, оси — делегация vital_state (ADR-123), falsy → ValueError (L2.2/§ENIGMA-003). affordance_resolver.py: реестр 7 предикатов (закрыт), таблица v1 (door/chair/container), effective_state (chair-деривация из полей W1), В10-правка Мастера: пара OPEN+CLOSE в OPEN для архетипов с обоими FSM-переходами. Константа AFFORDANCE_ADJACENCY_RADIUS_M=1.5 (calibration v1). 24 теста. Вход-контракт: body_state dict Stage 2B (S227/S229) — энергия/гидратация/питание в v1-view не входят (нет потребителя; расширение W4).
- ⚙️ Инцидент (закрыт в сессии): stranded-декоратор — однострочный якорь вставки перед декорированным классом оставил @dataclass(frozen=True) над enum → zero-field __eq__/__hash__ → множества членов схлопнулись (set-equality ложно зелёные, distinctness ложно красные). Поймано структурным тестом. Урок протокола: якорь перед декорированным классом — две строки. Гвард: test_world_action_type_members_distinct.
- ⚙️ Race-наблюдения: (1) транзиентный IPT 44/45 — полупатченные файлы активной параллельной сессии (M1b/Phase-0), не воспроизведён 3×; (2) НАБЛ-1 eco-stress и DEBT-IPT-RUFF закрыты параллельной сессией в окне нашей археологии — верифицированы их smoke-логом и ruff, засчитаны чужими; (3) файл domain_phases.py мутировал между ходами — все выводы сверенны по факту.
- ⚠️ Долги: DEBT-W-AUDIT (docs/AUDIT_W_TRACK_COUPLINGS.md отсутствует — ТЗ §18.3 обязательный deliverable Stage 2.5); прежние долги handoff без изменений. GORAN β не запускался (0 runtime-импортов, grep-доказано; по запросу).
- 📁 backend/app/domain/semantic_action.py, backend/app/domain/body_state_view.py (новый), backend/app/services/world/affordance_resolver.py (новый), backend/app/domain/constants.py, backend/tests/test_affordance_resolver.py (новый), architecture/world.yaml, docs/audits/ADR-O-372_IMPACT.md (новый)
IPT: ✅ 45/45 (финальный пост-атласный прогон: INV-ADR-NET зелёный с entry O-372, 165 nodes; новых инвариантов нет — вердикт В7). КРАСНЫЕ ИНВАРИАНТЫ: 0 🔴 → 0 🔴

### S233: Stage 2B.5 — Fatigue (ADR-O-373: FLAT-контракт + Enum Identity Split + консолидация per-tick проекции) | ✅ прицельные 164/0, IPT 45/0, полный базлайн ровно 12 known / 0 новых
🎯 S2B.5 fatigue (two-way износ) — и три вскрытых бага класса «тихая смерть», два из которых старше сессии.
⚙️ (1) FLAT-контракт Phase 0.5: S2B.1–2B.4 были production-мёртвыми с S227 — build_npc_snapshots даёт ПЛОСКИЙ NPCStateSnapshot, BodyEngine ждал сырой npc-дикт с body_state → тихий no-op каждый тик (unit-фикстуры кормили raw-формой, которой рантайм не существует — «объекты мечты» §12.3; unit-зелёный ≠ integration-живой). Фикс: idle_tick +4 плоских READ-ONLY поля (velocity/activity/coupling_mode/body_mass), билдеры tick_utils + combat_subscriber ×2 заполняют единый shape (+ обязательные ключи life_status/affective_load/emotion в combat-билдерах — pre-existing, всплыло Pylance). Intended activation S2B.2–2B.4 (вердикт Q5). TestS2B5ProjectionContract — гвард класса.
⚙️ (2) Enum Identity Split (вердикт Мастера: ONE POLICY TYPE / ONE POLICY REGISTRY / ONE ENUM IDENTITY): дубль ReductionPolicy+DELTA_POLICY_REGISTRY в dto.py → aggregate_deltas сравнивал enum'ы РАЗНЫХ классов → PHYSIOLOGY падала в algebraic-редукцию last-wins, вклад одного из physiology-продюсеров терялся на слое агрегации (pre-existing: decay-vs-combat на hit-тиках; после активации BodyEngine стала бы регрессией — decay глох бы каждый тик; поймано композиционным тестом ДО production). PHYSICS_COMPOSITE = PASS-THROUGH на агрегации (не «складывает» — аддитивность возникает при последовательном применении единым StateApplicator, clamp; формулировка исправлена по вердикту). Канон: models/state_delta.py; dto.py — re-export X-as-X (единственная форма, которую fix=true-автофикс не съедает как F401); tick_utils — единый источник импорта. Generic additive-fallback PhysiologyPayload в _reduce_additive ОТКЛОНЁН (маскирует рецидив split). Тесты: identity (is-пиннинг), composition (структура len==2 + сохранность sum=5.215 + порядок).
⚙️ (3) Fatigue-консолидация: BodyEngine — единственная per-tick проекция (wear 0.25×load×mass − recovery 0.1×(1−load), сон ×3 через coupling; шкала 0–100 «плохо вверх», инверсия energy; инвариант «износ медленнее топлива» 0.25<0.5 — отдельный тест; монотонность delta(RUN)>delta(WALK)>delta(IDLE) — вердикт Q3). Legacy dormant: decay fatigue-ветка (W3), сон-восстановление прямой записью −0.20 (W5), reconcile +8/тик (W4; skip-семантика = S2B.6/2B.8, вердикт Q2); W6 drives_runtime["fatigue"] — зомби, досье. Итог: per-tick engine один, event-продюсер один (combat), apply один (StateApplicator) — запрет «два producer'а допустимы, два per-tick engines — нет» соблюдён. Калибровочные смены (закон №13): exp −3%/тик → линейный 0.1; сон −0.20 прямое → −0.245 в формуле; skip → заморозка.
⚙️ Поведенческий гейт Мастера (зонд DIAG_S2B5, Часть VIII.5, реверсирован): body_engine n=6, e=−0.1/h=−0.3/nut=−0.0625/fat=+0.075 (load 0.5 — сверено с формулой); snap_fat 0→3.0 монотонно — полная петля snapshot→engine→delta→buffer→aggregate(pass-through)→apply_batch→body_state→snapshot доказана.
⚙️ Инцидент ruff fix=true: «голый» прогон применил 34 автофикса; F401 съел re-export → identity-тест красный в полном прогоне при зелёном прицельном. Конвенции-усиления §7.12: все прогоны ruff с --no-fix; re-export только X-as-X; комментарии ВНЕ import-блока (I001); isort combine-as-imports=false расщепляет aliased-мультиимпорты — это форм-преференс, не ошибка.
⚙️ Анти-race ×3 (§11.1.1): S231 занят RE M1b, S232 и ADR-O-372 заняты W-track W2 (их записи появились в окно сессии) → сессия S233, ADR-O-373, все внутрикодовые ссылки переименованы (grep-контроль: ADR-O-372 в файлах сессии = 0, ADR-O-373 = 28; 7 ссылок W-track на их O-372 не тронуты). Кластер «affordance ×3» атрибутирован окончательно: test_affordance_resolver.py = W-track W2 (ADR-O-372, файл 21:51) — их WIP-окно в нашем полном прогоне. Снимки полного базлайна (§7.14): закрывающий 22:44–22:47 — ровно 12 known / 0 новых; контрольный 23:04–23:07 — +6 красных окна RE M1b mid-work (MigrationAdapter ×2, V2CutoverLifecycle ×2, calibration M1 trust, mvp relationships — их домен/их тронутые файлы), атрибутировано по именам их тестов, не чинилось (закон №15). Эскалация форматирования: запись W-track S232 ведёт паразитный бэктик перед ### — ломает '^### S' анти-race grep для будущих сессий. RE-шторм (57 grid-красных + INV-SILENT v2_relationship_backend :120→:133, mtime 22:38) — их M1b, самозакрылся их фиксами к 22:44 (grid green, IPT 45/0), import-chain с нашим диффом не пересекается. Раннее окно: app.data ×2 (их M1b, тесты раньше модуля).
⚠️ Эскалации: RE S231 в заголовке ссылается на ADR-O-371 (номер W-track W1) — у M1b должен быть собственный ADR (не правил, закон №15); mypy CI-debt (56 pre-existing по пакету при инвокации как CI — из корня с --config-file mypy.ini; тронутые файлы чисты); ruff pre-existing ×6 (ss/location F841, W293×2 sleep, F821×2 tick_utils forward-refs); InjuryProcessor DEAD-guard + perceptual-ветки decay + remove_statuses — жертвы FLAT-класса; velocity не пишется никем → WALK/RUN только unit-уровень (вердикт Q6b: intent ≠ kinematics, мост = S2B.11/embodiment); Н-56 подтверждён (DLG_QUEUE OVERFLOW в IPT).
📁 models/idle_tick, models/state_delta, services/dto, services/tick_utils, services/body/body_engine, services/combat/physiology_decay_handler, services/combat/combat_subscriber, services/npc/sleep_lifecycle_service, services/npc/life_engine, tests/test_action_commitment (+TestS2B5ProjectionContract/TestS2B5Fatigue/TestDeltaPolicyIdentity, миграция S2B1–4 на плоский снапшот), tests/test_physiology_decay_handler (dormant-тест), tests/sandbox/system/test_temporal_reconciliation (fatigue-frozen), docs/audits/ADR-O-373_IMPACT.md
Уроки: верификационные паттерны — ИЗ ФАЙЛА, не из черновика (§7.3 ×2); ripple-grep по ВСЕМ tests/** (temporal упущен грепом по одному файлу); атрибуция в живом дереве — mtime + изоляционный прогон + механизм отказов; номера сессии/ADR проверяются в момент записи — черновики протухают за часы.
IPT: ✅ 45/0 на закрывающем прогоне сечении 22:47; зонд реверсирован скриптом (DIAG_S2B5 grep = 0). Финальный контрольный прогон: 44/1 — единственный красный INV-SILENT-FAILURE v2_relationship_backend (RE M1b mid-work, их зона; прецедент самозакрытия 22:38→22:44 уже зафиксирован). КРАСНЫЕ ИНВАРИАНТЫ: 0 🔴 → 0 🔴 attributable к сессии.

### S234: ТЗ-RE-01 M1b.4 — Физический cutover отношений: RAM-authoritative V2 (ADR-O-371) | ✅ сьюта 194/194, IPT 45/45
🎯 Третья ступень M1b: writers (M1b.2) уже за гейтом; сменён сам НОСИТЕЛЬ.
   RAM-GO (вердикт Мастера, разворот жёсткой позиции с решающим аргументом
   паритета): RAM = runtime authority (легаси-контракт допускал pre-scene
   writes — IPT-инвариант как вечный сторож), сцена = persistence projection,
   disk-on-update запрещён (Foundation Freeze: только atomic_commit_all),
   sync идемпотентен.
⚙️ Цепь cutover: GameLoop конструктор → memory_manager.switch_to_v2_
   relationships() ДО захвата подписчиками (5 захватчиков получают v2) →
   init_scene_state → bind(campaign, scene) с hydrate (сцена→RAM при пустом,
   pre-scene приоритетен) + migrate transform (M1b.1, split: confirm_migration
   ставит .migrated ТОЛЬКО после успешного atomic_commit_all — истина cutover
   = сохранённый v2) → update пишет RAM + sync_into_scene (проекция) → Фаза 10
   _sync_relationship_directed (multi-location: directed идентичен во всех
   локациях транзакцией) → confirm. Legacy JSON после cutover — заморожен
   (тест mtime+content). new_game: reset RAM + проекция.
⚙️ Доказательства: 194 теста — сетка D3 legacy==v2 8×8×5 (56-красный инцидент
   закрал прилагательное «было» к урокам: prior входит через bind-hydrate),
   pre-scene lifecycle (update без сцены → bind → сцена → save → reload →
   точные значения), sync-идемпотентность, hydrate-приоритет, смена локации
   без потерь, заморозка legacy, reset. IPT 45/45 — INV-TRUST-MONOTONICITY
   зелёный = pre-scene контракт жив в runtime.
⚠️ Уроки: (1) контракт-сдвиг = код+тесты одним пакетом (62 красных —
   неполнота моего пакета, не поломка кода: IPT/интеграционные были зелёными
   всё время); (2) археология по paste ≠ археология по диску (двойной
   докстринг __init__ — улика расхождения; впредь: inspect.getsource или
   точечные фрагменты перед БЫЛО); (3) ruff-автофиксы мутируют файлы между
   моими выдачами — сверять якоря на диске.
📁 social/v2_relationship_backend.py (RAM-authoritative), social/
   relationship_state_store.py (+confirm_migration split), memory/
   memory_manager.py (switch + _v2_scene_ref), game_loop/__init__.py
   (switch-точка), game_loop/scene_init.py (bind+hydrate+migrate+RAM-подъём),
   scene_state_manager.py (Фаза 10 sync + confirm), tests (194)
IPT: ✅ 45/45. КРАСНЫЕ: 0 🔴 → 0 🔴

### S235: Stage 2B.6 Phase A — канонические coupling-предикаты + диагностика инверсии сна (вердикты Q1–Q6) | ✅ прицельные 122/0 (файл) / домен-6 (см. закр. прогон), IPT 45/0, полный базлайн 20:10–20:13: 12 known + 1 атрибутированный чужой / 0 моих
🎯 S2B.6 Phase A (вердикты Мастера Q1-B/Q2-A/Q3-defer/Q4→S2B.8/Q5-диагноз/Q6): единая семантика coupling-сна — развязка «множители живы / метка мертва». Не калибровка: констант не тронуто, ×3 не тронут, фазы не переставлены (порядок 0→0.6→0.5 подтверждён кодом; «лаг 1 тик» — ретракция: Coupling(t)→физиология(t→t+1) — корректная snapshot-семантика).
⚙️ (1) String-identity split (H9): CouplingResolver пишет SLEEP/DEEP_SLEEP, BodyEngine + sleep-зеркало сверялись с фантомными "SLEEPING" (doc-drift: 00_CAUSAL_CONTRACT §5.2 + idle_tick:56 документировали несуществующий enum) → ×3-восстановление и sleep-ownership были мертвы в production с рождения; S233-гейт фикстурно-зелёный (литерал, который резолвер не производит — «объект мечты»). Фикс (Q1-B): is_sleep_coupling(CouplingMode|str) в domain/body.py — единственный источник семантики сон-coupling (SLEEP/DEEP_SLEEP/REM; DROWSY — не сон); миграция BodyEngine ×3-веток + registry:500; канонизация фикстур (SLEEPING→SLEEP ×3, AWAKE→FULL_WAKE ×3+3) + сценария action_integrity ×2 (B1/Y6-ветки оживлены — истинная диагностика S2B6-B/D, не глушить). Doc-фиксы: Causal Contract §5.2 + idle_tick:56 [+ Устав — по факту диффа].
⚙️ (2) A/B-диагностика (зонды VIII.5, реверсированы тройной верификацией; данные reports/DIAG_S2B6_*): 200 тиков × 6 NPC, идентичная инструментация. ДО: FULL_WAKE 829/DROWSY 310/SLEEP 40/DEEP_SLEEP 21; fat_d=−0.245 → 0 (движок слеп). ПОСЛЕ: −0.245=61, +0.760=61 — РОВНО count(SLEEP+DEEP_SLEEP) «до»; П1–П8 предсказаны до прогона, подтверждены все (drift A–E=0/0 в обоих; async-кай ±11 — класс DEBT-QUIESCE). ГЛАВНОЕ: инверсия двух снов в production-числах — поведенческий сон (thief, 200/200) выжимает sleep_pressure→0→FULL_WAKE→без ×3 (−0.065/тик); бессонница (borko, 0/200) накапливает sp→1.0→SLEEP/DEEP_SLEEP на ногах→−0.245/+0.760 поверх маршрута; стационарная антикорреляция обеих осей (borko нетто: fat≈−4.5, en≈+32.5 за прогон — клампы). ar=0.000 во всех 2400 сэмплах (ar-гейт инертен, Q5-диагноз); REM=0. Вывод для B/D: сон-физиология обязана рождаться из onset-цепи (Q6), не из pressure-часов.
⚙️ (3) Археология: F7 ЛОЖЬ — оба легаси-восстановителя стресса мертвы (recover_stress_tick/apply_tick_recovery: 0 вызовов; S2B6-D1: стресс восстанавливается ТОЛЬКО сном; npc_state:629 — doc-drift); F8 закрыт — 7×-блок пишет drives_runtime["fatigue"] (W6-зомби), второго живого body-fatigue-писателя нет. Ownership: sleep_pressure/coupling_profile — единственный runtime-писатель SleepLifecycleService (Phase 0.6); конфиги/расписания не пишут.
⚙️ (4) Гварды: TestS2B6CanonicalCoupling — truth-table предиката (вкл. case-ловушки "sleeping"/"awake"→False), пиннинг 5 членов CouplingMode (новый член обязан пройти через предикат), вечный греп-гвард фантомных литералов in/== "SLEEPING"/"AWAKE"/"DEEP_SLEEPING" по backend/app (прецедент S231).
⚙️ (5) Анти-race: S234 занята RE M1b.4 (RAM-authoritative cutover) в окне между черновиком и записью → сдвиг на S235 (прецедент S233). НОВЫЙ красный полного базлайна test_phase1_validation::bridge_3 — player_spoke удалён из _THREAT_TYPES (belief_transition_engine.py, незакоммиченный дифф −1 vs HEAD; grep-нуль пересечения с моей поверхностью; вчерашний снимок зелёный → изменение дерева в окне 23:41→20:10; вероятный владелец — mid-work трек памяти/психики, чей WIP в дереве: sqlite_store +282, test_phase_a_memory_fixes.py, docx-ТЗ «Контур памяти/психики») — закон №15, НЕ чинился, эскалация этой записью. RE-окна вчерашнего снимка (m1_scenario/mvp_relations) самозакрылись их M1b.4.
📁 domain/body (is_sleep_coupling), services/body/body_engine, services/action/commitment_registry, models/idle_tick (комментарий), tests/test_action_commitment (фикстуры+гварды), tests/sandbox/SUPERBOX/scenarios/action_integrity_test, docs/00_CAUSAL_CONTRACT_v3.0.md, docs/audits/ADR-O-374_IMPACT.md, reports/DIAG_S2B6_*; [S2B6-D2]: ruff pre-existing сценария action_integrity ×5 (F841×3/F401/I001 — не мои строки, не чинилось)
Уроки: §7.30 греп-гейты по литералам — только CaseSensitive; §7.31 счётчики — паттерн дословно из образца (repr-кавычки); §7.32 paste-сообщения «гейты→применение→верификация» — явная маркировка моментов (133/0 уже содержал патч); ретракции тоже требуют грепа (Устав-цель).
IPT: ✅ 45/0. КРАСНЫЕ ИНВАРИАНТЫ: 0 🔴 → 0 🔴 attributable к сессии.

### S236: Stage 2B.6 Phase B — физиологический onset сна: sleep_onset_tick / wake_duration / SleepOnsetEligibility (вердикты В1–В5) | ✅ прицельные 172/0 (3-файл.), домен-6 190/0 (закрывающий), IPT 45/0, полный базлайн 22:22–22:24: 12 known + 3 атрибутированных чужих (bridge_3; m1_scenario/m0_metrics/tick_full_loop — транзиентные окна параллельных WIP, зелёные в изоляции) / 0 моих; зонды реверсированы тройной верификацией
🎯 Phase B (вердикты Мастера В1(a)/В2(c)/В3(i)+wd/В4/В5; уточнения: eligibility≠fact, no-BED≠resting, no sleep_end-SSOT, wd≠проекция sp, motor-рестрикция не acceptance-критерий): сон = цепочка физических фактов «пора→здесь можно→лёг→тело вошло→×3→проснулся», не строка расписания. Констант не тронуто (единственная новая v1 — FATIGUE_PRESSURE_MOD_COEFF=1.0, на ревью Мастера, закон №13); ×3/фазы/arousal-гейт/awake-stress/W4/W-affordance — не тронуты (запрет-лист вердикта соблюдён).
⚙️ (1) B1 канон: body_state + sleep_onset_tick (int|None — ФАКТ; строго is not None, тик 0 валиден) + wake_duration (незажатый аккумулятор-история). CouplingResolver: двусторонний onset-гейт — без факта потолок DROWSY (сон-физиология ×3 и sleep-ownership недостижимы; инверсия Phase A закрыта у источника истины); факт жив → сон-семейство переживает decay sp (×3-окно = весь эпизод, класс F2). Непрерывные оси S189 не тронуты.
⚙️ (2) B2 eligibility: SleepOnsetEligibility (domain/body) + SleepOnsetResolver (NEW, pure): intent (sleep_states) ∧ bed_ok (get_node(position).role==NodeRole.BED; ADR-O-326 JSON-role SSOT) ∧ settled (нет active_traversals) ∧ alive ∧ ¬GAP9-блоки (существующие пороги threat/stress/паралич). First-blocking reason детерминирован; условие НЕ пишет состояние.
⚙️ (3) B3 переход+wake: SleepLifecycleService ветвится по ФАКТУ (не routine): eligible → sleep_onset_tick=tick, wd=0 ([SLEEP_ONSET]); wake = arousal-гейт (Q5, как есть) ∨ intent-withdrawal → _wake_from_sleep (pop факта, wd=0, sleep_end, DreamResidue S189-F дословно). Бодрствуя: wd+=1; sp += 0.005×(1 + fatigue/100×COEFF) (В3(i) модулятор; НЕ sp+=fatigue — оси независимы). depth ← sleep_onset_tick; legacy routine._sleep_start_tick девальвирован (reader мёртв; writer LifeEngine:1883 — [S2B6-D3], удаление санацией).
⚙️ (4) B4 проводка: _phase_0_6 оркестратора — bed_ok/settled → резолвер → сервис (сигнатура +Optional eligibility, обратно совместима). Ко-локация: W3-shadow-блок (их ADR-O-376 Gate-1) в том же методе — мерж-точка двух сессий, не тронут (git-дифф: ровно два hunk, построчная граница чиста).
⚙️ (5) Верификация (5 волн, каждая — прицельный прогон): +23 гварда в test_action_commitment (OnsetGatedCoupling 6 / OnsetEligibility 8 / OnsetTransition 8 — вкл. дифференциальный цепной тест onset→SLEEP→−0.245/+0.76, WARA json round-trip, wd-монотонность, fatigue×2-модулятор, обе wake-причины). Фикстуры мигрированы (test_sleep_routing несёт факт; фантомные AWAKE→FULL_WAKE). Зонды VIII.5 ×3 → 200-тик A/B (DriftLab) → реверс (grep DIAG=0 / compile / 172/0). ПРОГНОЗ-ТАБЛО (до прогона, фальсифицируемость): П1 тройная идентичность факт⇔mode⇔×3 (0=0=0) ✅; П2 borko 0 ×3-тиков ✅; П3 thief→no_bed ✅; П4 wd=200 монотонно ✅; П6 drift A–E 0/0 ✅; П7 REM 0 ✅; П8 ELIG 1200 = 818 no_intent + 382 no_bed + 0 travelling ✅. Честно: П5 (sp≈Phase A) — НЕТОЧНО (sp-дренаж переехал к факту по дизайну B3; предсказание-прокол, механизм верен). Итог Phase A→B в числах: coup SLEEP+DEEP 61→0, fat_d=−0.245 61→0 при 0 фактов — инверсия двух снов (Phase A) убита; сон-физиология теперь имеет причину.
⚙️ (6) Эскалации (закон №15, не чинились): (a) ДОСТАВКА СНА — главный открытый вопрос: граф кровати несёт (смоук: kitchen_bed_1/2→BED, префиксный id тоже; spatial_registry.json — fingerprint, не источник узлов), данные целенаправленны (borko→guard_bed, lusya→kitchen_bed_1), НО тела не доезжают: thief — цель city_gate:tent_3 кросс-локационно (конфиг: «не мигрирует») → 200/200 no_bed; borko — city_gate:guard_bed кросс-локация; lusya — цель ВАЛИДНА и в-локационна, но 129 сон-интентных тиков все no_bed (в моменты проверок не на кровати; IPT-улика: движение при activity='sleeping'). elig=True = 0/1200 — честный ноль верифицированной машины; долгосрочное равновесие без доставки: sp→1.0, motor→0 («мир недосыпа»). Вопрос поведенческого слоя/данных/DUAL-TIME-окон — НЕ калибровки. (b) Дизайн-вход Мастера (сессия): Тень должен тайно спать в подвале/за столом — варианты: data-фикс activity_map (MapEditor-домен; машина подхватит автоматически) vs sleep-affordance-типы (BED→HAMMOCK/GROUND/SHELTER — W2-генерализация по В2(c)); статус: контент-владелец решил отложить, вход зафиксирован. (c) bridge_3 (player_spoke удалён из _THREAT_TYPES, belief_transition_engine.py, дифф −1 vs HEAD, mtime в окне сессии; владелец — трек памяти/психики, WIP: sqlite_store+282, docx-ТЗ) — эскалация S235-прецедентом, в полном прогоне красный. (d) транзиентные окна полного базлайна 22:22–22:24: m1_scenario/m0_metrics/tick_full_loop красные в общем прогоне, ЗЕЛЁНЫЕ в изоляции (после — 1 passed каждый), mtime тестов старые, IPT 45/0, git-дифф оркестратора = 2 hunk (мой+их W3); атрибуция: интерференция параллельных WIP в живом дереве (sqlite/глобальные процессные состояния), класс DEBT-QUIESCE, не моё. (e) 'resting'→fireplace не onset-ится (не-BED) — соответствует §9 вердикта; будущий affordance-вопрос.
📁 domain/body (SleepOnsetEligibility), services/npc/sleep_onset_resolver (NEW), services/npc/coupling_resolver, services/npc/sleep_lifecycle_service, services/tick_orchestrator, tests/test_action_commitment (+23), tests/system/test_sleep_routing, reports/DIAG_S2B6B_sleep.txt; долги: [S2B6-D3] _sleep_start_tick-writer; [S2B6-D2] ruff pre-existing сценария; W293×2 sleep/11 orchestrator — pre-existing, не тронуты
Уроки: §7.34 генеративная деградация командных блоков (все read-only, вред 0; дисциплина: STOP вывода при обнаружении, восстановление новым сообщением с побуквенной выверкой); §7.24-повтор: ripple полного прогона тронутых файлов (tick_orchestrator full_loop не гонялся в волнах — вскрыт только закрывающим базлайном); §7.35 предсказания вычисляются из полного механизма, не из частичного (П5); порядок причин зонда = порядку резолвера (first-blocking маскирует travelling в no_bed — известно, задокументировано); ретракция без грепа — §7.33 (Phase A).
IPT: ✅ 45/0 (финальный, повторный; suspect-хвост был транзиентен). КРАСНЫЕ ИНВАРИАНТЫ: 0 🔴 → 0 🔴 attributable к сессии.

### S237: W3 Object FSM — Execution Substrate + Gate-1 Shadow (ADR-O-376) | ✅ IPT 45/45, W-сьюты 101+1skip, GORAN β G1 GREEN+ambient
🎯 W3 как «что произошло»: первый execution-substrate W-track — доменные FSM-переходы (ТЗ §22.1 ТЗ-точные), production-спавнер из editor-JSON, discovery-тень W2 (Gate-1 из трёх). Vердикты Мастера исполнены: О1 (NO_OP), О2 (chair-политика над отношениями W1), О3 (MOVED=relocate), О4 (bed отложен), О6 (damage→archetype-терминал: container DESTROYED), О7 (TransitionResult не bool), О8 (topology-контракт в W3, реализация W5); identity≠location (wo_-хэш); door+door_transition→один archetype (подтверждено graph_compiler); W3 Causal Contract (пять W-законов, три гейта, Fact отделён от мутации, STEAL=W5-интерпретация TAKE, TRANSFER=W6-примитив, ownership/territory=relation-domains W5+).
⚙️ Домен: object_fsms.py (transition_object/damage_object pure; TransitionResult+old_state+topology_effect; except→REJECT запрещён — INV-SILENT-FAILURE поймал, policy-предусловия ДО доменного вызова). Стор: +apply_transition/apply_damage (коммит ТОЛЬКО на PASS). Спавнер: initialize_scene-only (сейв выигрывает), SpawnMapping {door, door_transition→door, chair}, wo_<md5(campaign:loc:editor_id)>, presentation-фильтр (W0), fault isolation. G1-shadow: World-object projection (мост W1→W2) → resolver → [W3_SHADOW]; точка после build_snapshot ДО Фаз 0+ (affordances раньше решений); discovery читает только снапшот; env W3_SHADOW_ENABLED default OFF = no-op; ShadowMetrics=discovery-статистика (не смешивается с G3-execution-причинами). Live: INV-WORLD-OBJECT-TOPOLOGY live=0→18; спавнер подтверждён в production build_game_loop. GORAN β G1: 10 профилей, 4 AB-пары {2,6,2,2} vs фон {4,7}, медиана 2<5.5, структурный профиль идентичен фону (S216-класс), все guards зелёные → GREEN + AMBIENT QUALIFICATION (DEBT-QUIESCE — внешний фон, не блокер).
📁 backend/app/domain/object_fsms.py, backend/app/services/world/world_object_store.py, backend/app/services/world/world_object_spawner.py, backend/app/services/world/world_objects_projection.py, backend/app/services/world/affordance_shadow.py, backend/app/services/tick_orchestrator.py (G1-врезка), backend/app/services/scene_state_manager.py (world_objects+спавн), backend/tests/test_object_fsms.py, backend/tests/test_world_object_spawner.py, backend/tests/test_affordance_shadow.py, scripts/w3_shadow_simple.py, docs/audits/ADR-O-376_IMPACT.md, docs/ENIGMA_ROADMAP.md (DEBT-QUIESCE), architecture/world.yaml
⚠️ ЧУЖАЯ ЗОНА (не наш scope, ретрансляция Мастеру): TICK_CRASH npc_tick_pipeline:703 — DOUBLE TRUTH active_commitments (TEMPORAL-код пишет list per npc_id против контракта ADR-O-363 dict[npc_id, commitment_dict]; latent, interleaving-зависимый: 0 ошибок в v5 при тех же 600 тиках — недетерминистическая природа подтверждена; зона M1b/S203.x, файл M, менялся 20:58 в окно прогона); PROBE_FAIL INV-TEMPORAL-ISOLATION (scene_state мутирован внутри пайплайна, тики 44/56 v3 — зона M1b write-gates); git 4fae7e4e — full-save параллельной сессии на main+V.0.5.3.9.3_Мир_1 включает их ADR-O-371 M1b.4.1+наш ADR-O-372; MUTATIONS-координация (файл общий).
⚙️ Уроки сессии: (1) v1-харнесс сделал ложный GREEN на двух одинаковых крашах — INVALID RUN-guard обязателен (равные краши != совпадение профилей); (2) команда запуска выдаётся ТОЛЬКО после патча по факту археологии (v1 погиб на предполагаемом API GameLoop; в том же выводе был рабочий эталон — DriftLab/build_game_loop); (3) v3-патч «main целиком» поглотил __main__-гвард — прогон молча exit-0 (grep-контроль хвоста после каждой замены); (4) stderr/stdout топология Redirect-харнессов: шум в err, print() в out — поллинг обязан знать, где что живёт; (5) терминальная конвейер-смерть без traceback = внешнее убийство (окно консоли), фоновый Start-Process с Redirect устойчив.
IPT: ✅ 45/45 (гейт-прогон финальный; INV-WORLD-OBJECT-TOPOLOGY live=18). КРАСНЫЕ ИНВАРИАНТЫ: было 0 🔴 → стало 0 🔴

### S238: AG1-Сессия — Фаза A + EMRL E1/E2.0 + Реестр долгов (Полный цикл) | ✅ 45/45 замков, IPT 45/45

🎯 Три этажа одной сессии. (1) Фаза A — фундамент памяти: закрыты все 9 P0
аудита V.0.5.3.9.3 + 5 живых детонаций тика (легаси temporal-ветка →
TICK_CRASH 3/3→0; L1-UNIQUE каннибализация; мёртвый _shared_context в
провайдерах подписчиков — провод речь→память, 272 строки npc_spoke;
affordance_facts_map-гвард; publish-dict). Все 10 фаз тика живы впервые.
(2) EMRL: E1.0 ExperienceTrace+provenance (TESTIMONY≠копия); E1.1
decay-семантика (floor=is_compressed — суть бессмертна, шум умирает);
E1.2 MemoryCrystal (confidence≠retrieval_strength, домен-граница с
CrystallizedBelief §13.3); E1.4 кокпит (new/wait/restart/mem —
terminal_cockpit.py); E2.0-a/b DeltaGate (whitelist/клампы/TRACE-ONCE/
INV-LLM-NOT-SSOT) + живой провод THREATEN→ПК (Proposal в
reaction_subscriber, Gate=аудит не писатель, belief — тиковая ветка,
causal_parent) + EXPERIENCE_DELTA_COMMITTED→Chronicaler (EventDTO).
(3) Долговая уборка: реестр AG1-D1..D12 в Roadmap 3.0 §4a — D8→ADR-O-377
(атлас+IMPACT, production-план=D8p/S203.4); D2 контекстный лог; D4
сшивка словарей L3 (каскад идентичности мёртв с рождения:
social:aggression ↔ hostile — ни одной общей лексемы; +замок полного
прод-пути); D3 witness через Gate (+7-й разрыв словарей: канонический
player_attacks не матчился в witness-elif); D11 телепатии в проде нет
(писатель reduction:253 жив; warning — от тест-заглушек, заменены);
D7 NPC-интент summary без пустых хвостов; D1/D9 уведомления владельцам.

⚙️ Ключевые законы сессии: LLM ≠ SSOT (между Interpretation и State нет
прямого пути — DeltaGate); две скорости (быстрый мир не ждёт LLM —
ADR-O-377, cockpit-форма); AG1-INV-TRACE-ONCE (один event.id → один
trace → ≤1 дельты поля); суть = акт консолидации (is_compressed), не
зона важности; припоминание растит доступность, не истинность.

⚙️ Системная находка: 7 разрывов словарей за сессию (L3-теги, witness-
elif, _shared_context, affordance_facts_map, publish-dict, SLEEPING-
фантом соседей, player_attacks) — самая частая причина мёртвых контуров
ENIGMA: не отсутствие кода, а два словаря, которые никогда не встречались.

⚠️ Границы честности: субъектность NPC НЕ доказана (доказано:
proposition сохраняется; не доказано: оно меняет поведение без нового
промпта — ключ = E2.0-c, НЕ начат); witness-эмпатия shock*2.0 —
магическое число (полигон); production-форма O-377 — план; экономика
распада long-horizon — наблюдение.

📁 Замки: backend/tests/test_phase_a_memory_fixes.py (45); кокпит:
backend/tests/sandbox/terminal_cockpit.py; зонд:
backend/tests/sandbox/db_dump_probe.py; DTO:
backend/app/domain/npc_state.py (npc_state.py), domain/
state_delta_proposal.py, models/npc/memory_crystal.py, models/npc/
experience_trace.py; Gate: services/memory/delta_gate.py; провод:
services/events/reaction_subscriber.py; распад: services/memory/
working_memory.py, npc_loader.py, npc_tick_pipeline.py; стор:
services/memory/sqlite_store.py (traces/crystals/локи); L1:
services/npc/l1_chronicle.py; belief: npc_loader (beliefs round-trip);
экстракция: services/memory/dialogue_update_extractor.py (контекст-лог).
Атлас: ADR-O-377 + IMPACT. Roadmap: docs/ENIGMA_ROADMAP.md → 3.0
(§2a трек AG1, §4a реестр долгов).

🎯 ТЗ-источники сессии: «Аудит ENIGMA V.0.5.3.9.3 НПС и UI» (Фаза A —
канон); «Контур памяти NPC — разрывы и план» (Этапы 0–6 — E1-канон);
«Контур психики НПС, Фаза B» (B1–B6 — ждёт E2.0-c); мандаты сессии:
«EXPERIENCE→MEMORY→SELF→RELATIONSHIP LOOP» + «Законы двух скоростей»
(владельца — НЕ записаны файлами, кандидат сохранения).

IPT: ✅ 45/45 (весь путь). КРАСНЫЕ ИНВАРИАНТЫ: 0 🔴 → 0 🔴.

### S239: W-track G2 v1 — Affordance Producer-Facts, первый живой мост W2→решение (ADR-O-378) | ✅ IPT 45/45, W-контур 124+1skip, GORAN β G2 GREEN
🎯 Гейт G2 (второй из трёх): W2-факты → производный каузальный факт → СУЩЕСТВУЮЩИЙ канал решения. Вердикты PRE-FLIGHT исполнены: Г3=A″-lite+C (C не начат — бюджет ушёл на честность GORAN-итераций); Г1=канал b1′ (полный сет в хаб не тащится — интерфейс под несуществующего потребителя; weapon_access = документированный DATA-стаб ADR-O-366 → DEBT-OPP-PRODUCER закрыт); Г2=proof-стандарт Мастера (production honest-zero = sanity-gate; доказательство = только controlled-scene).
⚙️ Домен/канал: affordance_facts.py (pure продюсер из замороженного снапшота: WEAPON_ARCHETYPES policy класс-S211; факт = holder ∨ FREE∧IS_ADJACENT_TO — предикат из закрытого реестра W2, lockstep 1.5м; W2-резолвер не расширен — unknown-archetype=KeyError by design) → TickState.affordance_facts_map (frozen preloaded) → NpcTickPipeline: weapon_access=факт (пустая карта = байт-идентично False; сигнатуры DecisionHub не менялись — anti-race-зона была чиста). Флаг W3_G2_ENABLED default OFF=no-op; отказ продюсера = пустая карта (§11). GORAN β G2 (scripts/w3_g2_simple.py, 7×200, INVALID RUN-guard): GREEN — honest-zero, B-молчание, W hits=199/199 + persisted; engine-флип 0.50→0.70 (Δ=W_WEAPON) юнит-доказан; steal-флип условен по will-гейту (цели STEAL — W5/W6).
⚙️ Методология-хроника (4 честных отказа, ноль ложных GREEN, все пойманы гвардами): (1) bootstrap-квант дочерних процессов (sys.path-фикс); (2) H1: get_scene_state вне тика перезаливает из persistence — инъекция только через save-контур; (3) H5: build_game_loop читает saves_dir из ГЛОБАЛЬНЫХ settings (data_dir его НЕ задаёт!) — прогоны №1–3 мутировали общий ROOT/saves/enigma_runtime.db = production-store (~2800 тиков эволюции чужого мира + weapon-артефакт, устранён перезаписью их живой сессией; исходное состояние невосстановимо — эскалация Мастеру); (4) H6: stale-парсинг sqlite-строки. Лечение: settings.saves_dir=str(temp) до build в дочернем — полная изоляция; terminal-дрейф 65→42 = артефакт общего store (канонический S237-класс восстановлен), НЕ регрессия ядра. G1-оговорка: w3_shadow_simple.py (S237) имел тот же дефект — 10 G1-профилей эволюционировали один мир; вердикт G1 валиден (тень=ноль writers), семантика изоляции — нет; все будущие A/B-харнессы обязаны патчить settings.saves_dir.
📁 backend/app/services/world/affordance_facts.py, backend/app/domain/tick.py, backend/app/services/pipeline_runner.py, backend/app/services/tick_orchestrator.py, backend/app/services/npc/npc_tick_pipeline.py, backend/tests/test_affordance_facts.py (23), scripts/w3_g2_simple.py, reports/w3g2_*.json + reports/w3g2_run_history/, docs/audits/ADR-O-378_IMPACT.md
⚠️ ЧУЖАЯ ЗОНА (ретрансляция Мастеру): (1) F821 Intent npc_tick_pipeline:696 — runtime-достижимый latent NameError (Bridge-7-регион, зона Память-серии; их TYPE_CHECKING-mypy-доводка не лечит runtime); (2) data/replay.db = 754 МБ / 68k snapshots / 20k llm_calls — рост без ротации; (3) INCIDENT: production-store ROOT/saves эволюционировал харнессом до изоляции — координация с Память_3 (new-game reset или признать эволюцию); (4) ENIGMA_ROADMAP W-раздел отстаёт (W2/W3 показаны открытыми — закрыты S232/S237/S239); (5) анти-race: ADR-O-377 занят их Non-Blocking Intelligence — мой пакет был поглощён их full-save d92e8d1c под чужим номером в комментах, сдвиг O-378 propagate'нут (13 сайтов); (6) TEst_Result.md (D) / «Правила Фикса БАГОВ.md» (M) — чужие правки, не атрибутированы мной.
⚙️ Вердикты закрытия (Мастер, 2026-09-04): DEBT-W-STORE-INCIDENT = ACCEPT — эволюция ROOT/saves признана каноническим состоянием живого мира (known provenance debt: baseline невосстановим, «стратиграфия нарушена до T≈2800»; reset отклонён — подмена исторической непрерывности опаснее артефакта); ENIGMA_ROADMAP.md v2.1 удалён Мастером (SSOT = роадмап v3_4, синхронизирован до 3.5 — S239-док); constants.py:307 line-drift — pre-existing, оставлен в реле (граница ответственности пакета не смешивается с чужим ремонтом). G3 входит с чистой картой, но не с чистым миром.
IPT: ✅ 45/45 (гейты до/после док-мутаций). КРАСНЫЕ ИНВАРИАНТЫ: было 0 🔴 → стало 0 🔴

### S240: DEBT-W-AUDIT — карта сцеплений simulation↔presentation + входной ограничитель G3 (ТЗ Часть II §18.3 / DoD п.25; вариант B по вердикту Мастера) | ✅ IPT 45/45 (вход/выход), docs-only: 0 .py-патчей, 0 ADR, 0 runtime-прогонов
🎯 Закрыт обязательный deliverable Stage 2.5 W-track: docs/AUDIT_W_TRACK_COUPLINGS.md — не grep-список, а ownership/coupling-граф (Mermaid; легенда legal-write / read-only / DOUBLE-TRUTH-risk) + §4 «входной ограничитель G3». Scope Г7 (Мастер): весь backend/app + presentation bridges; классификация по (слой-хозяин × направление ребра), не по слову «W»; каждая строка FACT/INTERPRETATION/RECOMMENDATION; migration plans НЕ исполнялись (аудит ≠ рефакторинг).
⚙️ Археология только-чтение (A1×15 breadth + A2×19 + A3×17 + A4×5). Инвариант ТЗ подтверждён «пустыми» зондами (V1–V4): 0 identity-полей в domain/models, 0 frame-as-state, 0 импортов frontend из backend (R1-хиты = докстринги), 0 visual/pose в персистенции NPCState — W0/W8-инварианты эмпирически живы. Мосты чистые: 12 Acceptable adapter (snapshot-builder / presentation_assembler / manifestation §17.5 / need_presentation_mapper / narrative_projector / legacy_dialogue_adapter / firewall+momentum / world_routes GET 304 / спавнер-отбрасывание presentation-полей / bootstrap W3 / freeze-чтение INV-III / авторинг psyche в editor-JSON). 0 Simulation coupling. ГЛАВНЫЙ РИСК-УЗЕЛ — B1.4-канал (routes.py:1243–1268): FE пушит ПОЛНЫЙ локальный scene_state (game_screen:581,581→1283; 3 транспорта HTTP/Direct/Retry) → merge НЕзащищённых ключей (protected=7: gts/tick/player_recognition/active_traversals/pending_tasks/spatial_walls/obstacles; world_objects/relationship_state/npc_positions/active_commitments ВНЕ листа) → save_scene_state → atomic_commit_all: (а) anti-writer G3 — FE-эхо world_objects откатит transitions между тиками (B4, INTERPRETATION до одного runtime-зонда; ОБЯЗАТЕЛЬНОЕ УСЛОВИЕ до G3-ON); (б) cross-track: обход CommitmentRegistry (O-363) и RelationshipWriteGate (O-369/370) — релеи §5 аудита; (в) tick-locked: push заменяет tick-scoped кэш локации целиком (SSM:537–541) — race risk. W-граница (§4 аудита): spawn = ЕДИНСТВЕННЫЙ прод-writer (спавнер, initialize_scene-only, сейв выигрывает); establish/release/relocate = 0 app-callers; transition_object/damage_object = 0 runtime-callers (G1 unconsumed эмпирически; role_transition.py — false positive зонда) → G3 = первый runtime-writer; typed-op применения TransitionResult в сторе ОТСУТСТВУЕТ → мини-ADR (закрытые реестры, класс O-349). Прочие находки: F3 character_select.py:376–401 пишет characters.json напрямую в saves (мимо API); F1 game_screen:1797 player_stress=10.0/player_hp=100 хардкод (AvatarStateDTO скаляров не несёт — корень: нет канала аватар-скаляров, Фаза 1.9); F2 game_types:117 _raw_data — сырое scene_state в FE (minor).
⚠️ Anti-race (закрытие): S240 = max+1 по re-grep (хвост S237/238/239); ADR-O не выделялся. Дерево в момент закрытия: параллельная серия АКТИВНА — M backend/app/services/game_loop/__init__.py (чужой WIP, не мой — мой session-score 0 .py), ?? backend/tests/sandbox/SUPERBOX/scenarios/causal_state_test.py (их E2.0-c); их gameplay/ + gc00_baseline3.txt + M-роадмап исчезли из статуса (вероятно коммит) — коммит S240 строго file-scoped (3 docs-файла). Уроки протокола: (1) PowerShell-паттерн с embedded-кавычками — только в одинарных кавычках (A4-2 упал PositionalParameterNotFound, повторён исправленным A4-2r); (2) «пустой» зонд = верификационная находка (фиксировать в реестр, не отбрасывать); (3) релятивация Г-вопросов хэндоффа: Г7-скоуп и порядок B→G3 даны Мастером до кода — PRE-FLIGHT-вердикты по Г1–Г4 остаются обязанностью G3-сессии.
📁 docs/AUDIT_W_TRACK_COUPLINGS.md (новый: §0 метод, §1 граф, §2 реестр 6 подсекций, §3 сводка §18.2, §4 входной ограничитель G3, §5 релеи R1–R6, §A команды), docs/MUTATIONS.md (эта запись), docs/ENIGMA_ROADMAP_v3_4_AVATAR_AGENCY.md (§3: DEBT-W-AUDIT [x] + 5d-журнал)
IPT: ✅ 45/45 (гейт входа и закрытия). КРАСНЫЕ ИНВАРИАНТЫ: было 0 🔴 → стало 0 🔴

### S241: Итерация «Пункт 5» — тесты-детекторы и закрытие долгов (roadmap v3.4) | ✅ IPT 45/45
🎯 Тестовый слой gameplay-closure как детекторы (красный = диагноз, не ретушь) + 4 production-фикса из живых прогонов. Журнал выполнимости перенесён из backend/tests/TEst_Result.md в Roadmap §5d (решение Мастера: единственное место фиксации — docs/ENIGMA_ROADMAP_v3_4_AVATAR_AGENCY.md).
⚙️ (3) PROBE 9.7: REST-путь не разбирал pending_tasks (execute_pending только из idle_tick) → материализация ADR-O-313 в run_turn (зеркало idle-прецедента) — речь NPC становится памятью в player-сессиях. (4) GC-00: backend/tests/gameplay/ — TavernGameplayHarness (build_game_loop production-вход; тики только idle_tick, ходы только run_turn; clean-start: settings-мутация+restore, bus.clear, sessions snapshot/restore, reset_life_engine); эволюция baselines 0/3→1/3→2/3→3/3: ADR-WRITE-GUARD поймал сам harness → тест-баги (nested asyncio, контракт сцены) → контаминация (ретракция DEBT-QUIESCE: offset=N тиков = перенос, не недетерминизм) → детерминизм подтверждён (2×30 идентичны). (5) AUD-D2: self._rel_store не существовал (S198-читатель мёртв) + fall-through при None → None.apply каждый ход; фикс: провод + skip-путь (applied ≠ verified — персистентность в GC-11). (6) AG1-D5: avatar default body_state={'money':48} (виноват НЕ Death Guard) → {**BODY_STATE_HEALTHY, money:48}; зонд red→green. (7) AVID-1: idle не передавал all_npcs_raw (S113-контракт только в REST) → проводка; S198 count=7 с 'player' ×3 — аватар укоренён в idle-мире (CFL/восприятие/соцполе видят игрока между ходами).
⚙️ Уроки: git add -A втянул 30 файлов/43k строк (28676bcb) — впредь точечный add; описательный патч ≠ БЫЛО/СТАЛО (34890fc8 → переиздание 109df98d); nested asyncio.run запрещён; атрибуция недетерминизма без доказанной изоляции = спекуляция.
📁 backend/tests/gameplay/{harness,test_tavern_vertical}.py, svc/game_loop/__init__.py, svc/events/social_subscriber.py, svc/player_avatar_service.py, docs/ENIGMA_ROADMAP_v3_4_AVATAR_AGENCY.md (§5d, 16 строк), reports/gc00_*.txt (10 артефактов)
⚠️ Хвосты: AI-D1, ST-1, PH-1, SC-1, RE-D2, DEBT-R10, AUD-D1/3–12. IPT 45/45, красных 0.

### S242: B1.4-runtime-зонд — runtime-доказательство anti-writer канала (харнесс b1_4_push_probe, 2 изолированных rail) | ✅ IPT 45/45 (вход/выход), зонды сняты, 0 production-изменений
🎯 Обязательное условие G3-ON (аудит §4.3 / хэндофф S240): состав FE-пуша и Δ канона доказаны живым прогоном, не статикой. Харнесс по GC-00-паттерну (production-path ONLY, temp-saves изоляция — урок H5): origin = session_state.scene_state (SSOT) → 3×idle_tick + FE-sync (A4-2r дословно) → player-move → пуш; checkpoint = дисковая копия (unlocked get_scene_state, deepcopy) до/после; direct/http — два изолированных мира (вердикт Мастера: writer boundary, не последовательные writers).
⚙️ Вердикты: direct = RED×8 — wipe реестров (active_commitments 3→0 вкл. player, history 5→0, ordinals 7→0 = риск переиспользования ADR-O-363), wipe backend-only ключей (_version/epistemic_records/player_recognition/pending_tasks/last_save_real_time), protected-лист на пути отсутствует (TIME-FREEZE bypass; находка №1 аудита runtime-подтверждена). http = RED×1 + латентность: критические Δ=0 при writers=0 (RE dormant, G3 нереализован; пустые реестры → update({})=no-op); npc DTO-замещение живо (6/6 NPC; direction: visible/in_transit/position/editor_room_id «dropped», психическое initiative_suppression «added» → персистится в канон); projection-pollution (merge пишет avatar_state/player_perception/visual_dto/… в канон). Таблица RT1–RT8: AUDIT §6; доказательная база: reports/b1_4_probe_report.json (619 строк).
⚙️ Anti-race + процесс-уроки: (1) номер S241 занят параллельной серией («Память_3», a3bd67e7) → перенумерация S242, ссылки в артефактах обновлены (Устав 11.1.1); (2) их v1-коммит всосал мой staged-пакет (их откат + pathspec-переиздание; пакет выжил в index) → терминальный коммит при живых параллельных сериях — ТОЛЬКО `git commit -- <pathspec>`, staged-пакет не держать открытым; (3) мой FE-зонд game_screen:1283 не был реверсирован при развилке на харнесс — пойман git-диффом, снят до коммита; урок: каждый применённый зонд получает реверс-патч в той же сессии независимо от смены плана (класс 2c4dfd9d).
📁 backend/tests/sandbox/b1_4_push_probe.py (новый), reports/b1_4_probe_report.json (новый), docs/AUDIT_W_TRACK_COUPLINGS.md (+§6), docs/MUTATIONS.md (+S242). Roadmap-синхронизация §3 отложена (роадмап активно правит серия «Память_3», a3bd67e7 = 66 строк) — преемнику отдельным мини-коммитом.
Следующий шаг W-трека: Р2 — защита канала (матрица А/Б/В у Мастера; рекомендация В: приёмник-whitelist npc_positions.player + конвергенция Direct-моста; narrowing без конвергенции Direct = ловушка RT2) → G3 PRE-FLIGHT (Г1–Г4, git-археология Фаз 6–7, координация с «Память_3» обязательна).

### S243: Документальное закрытие B0 (E2.0-c/B0-CLOSED) — guard'ы в ADR-атлас (O-379/O-380), ренумбер S241→S243, верификация воспроизводимостью | ✅ IPT 45/45, замки 45/45, обе серии побайтово
🎯 Вердикт владельца (ВЕРБАТИМ): «B0 — CLOSED/GREEN. E2.0-c подтверждён: event → mechanical state → decision и автономный канал mechanical state → decision. Люся: A — флип (flee 0.800 vs B call_for_help 0.272), C — тот же флип 0.777 без события/текста/LLM (одна дельта threat_gradient 0.8 через DeltaGate+StateApplicator); A−C=0.023 = атрибуция side-канала страха, не ошибка; B — чист; D — нелегальные входы отвергаются. 45/45 locks, 45/45 IPT. FLEE-материализация в 1 тике (арбитр) — LIMITATION, не критерий B0.» Сердце доказательства: A≠B + C≠B + concordance(A,C).
⚙️ Хроника B0-работы (сессия-предшественник + верификация S243): 10 раундов археологии (StateApplicator-регион PK; формулы state→scores: risk_penalty=threat×risk×0.9 (hub:1247), escape_salience=threat×0.8→FLEE×1.6 для робких (hub:575-592), threat>0.5→is_provoked (hub:1275)) → красный №1: H2-ловушка (метрика=decision_result.intent — communication-слой, не proof-слой) + H1-ландшафт Горана (request_service 0.71 > flee-потолок ~0.59 — свойство натуры, не разрыв) → два хода: (a) метрика = argmax(scores_trace)+intent+PK+move (к intent-как-единственной-метрике НЕ возвращаться), (b) Люся — флип-кейс (двухсерийный сценарий: без argv = Горан state-доказательство, maid_lusya = флип) → четыре-зелёное (Люся A/B/C/D GREEN; Горан A-красный by-design) → guard'ы (D2/D3 REJECTED). Верификация S243 (пост-дедуп): обе серии побайтово-идентичны (0.800/0.272/0.777/0.023; Горан C−B flee ≈ +0.33) при мёртвом LLM-сервере — дополнительное доказательство LLM-независимости канала. Дубль PK __setattr__ (артефакт двойного патча, латентное затенение) устранён параллельной серией до терминального коммита — фиксируется честно.
⚙️ Документальный кадр: Roadmap v3.6 — ренумбер B0-атрибуций S241→S243 ×7 + B0-чекбокс §B [x] (redirect: production-форма TaskScheduler = AG1-D8p, ADR-O-377 занят Non-Blocking Intelligence, НЕ гейт B0) + санация матрицы §5b (GC-06-ряд перенесён на место после GC-05, пустой дубль заполнен). ADR-атлас: L8.2 PerceptualKernel Write Guard (ADR-O-379, DOM-03) + L14.5 BeliefState Write Guard (ADR-O-380, DOM-06&09) + IMPACT×2. Кокпит-гейт закрыт параллельной серией (Шаг 8 полевого теста): mem до/после restart дословно идентичны — «сохранение причинной идентичности состояния через рестарт» подтверждено в живой сессии (LLM жива). BC-1 открыт (терминологическая лестница §2a): Conclusion = машинно-пригодные триплеты, не фразы; первый потребитель — Expectation (BC-2); conclusion_delta — только через DeltaGate с provenance и causal parent; anti-Bond (Р17-П1) перед каждым слоем; ПЕРВОЕ действие BC-1 — досье-проект контура + PRE-FLIGHT ADR до кода.
⚙️ Досье находок: (1) visible_threat_markers мертвы в проде (0 писателей; словарь _THREAT_MARKER_VALUES есть, событий с маркерами нет) — калибровка экзамена опиралась на state-каналы; кандидат на отдельный фикс (не мой). (2) Дубль def test_threaten_produces_gated_delta (971/980; 971-заглушка NotImplementedError затенена) — санация при ближайшей правке файла замков. (3) BeliefState R8: «два writer'а» реальны (BTE + CoherenceBeliefAggregator), правил мёрджа нет; docstring-заголовок устарел после guard'а. (4) Рассинхрон клампов: Gate threat_gradient [-1..1] vs Applicator [0..1] — поднять при первом касании Gate-контракта. (5) D11-телепатия в idle: perceiving_npcs=None → fallback на всех (гвард WARNING-ит — работает; группа A давала дельты всем 6 NPC). (6) tavern (S194/DriftLab) vs tavern_silver_wolf (GC-00) — расхождение локаций, помечено GC-00. (7) Mid-edit-коллизия параллельной AG1-D5-сессии (avatar BODY_STATE_HEALTHY без импорта) поймана, их фикс завершён; AG1-D5 из моей очереди снят. (8) CHAR_FILTER может обнулять hub_event в player-пути (наблюдение). (9) Throttle: экзамен мержит Log-phases — B1-фальсификатор обязателен в каждом сценарии-наследнике (ловушка «фикстуры-мечты»: A/B только через полный прод-путь). Полевые хвосты Шага 8: FT-1 (адресация «люся:»→TARGET Торнин — S238-класс, резолвер), FT-2 (FLEE-storm ×12, Flee blocked — материализация FLEE жива в длинном окне = материал BC-12, подтверждает limitation-формулировку), FT-3 (пустые речи).
⚙️ Уроки протокола: PowerShell-кавычки — паттерны только в одинарных (инцидент Select-RecordObject/dec:ision.py: опечатки из повреждённых кадров, команда падает, а не молчит); повреждение кадров реальных передач (два инцидента) — важные патчи короткие, с построчной синтакс-верификацией, анкеры из фактически прочитанного, применение пачками ≤4 с контрольным чтением после (коллизия GC-06 — прецедент: ряд применился не на место + пустой дубль, санация в этой сессии).
⚠️ Anti-race: B0-сессия самоназвалась S241 — номер занят параллельной серией («Пункт 5», затем S242 B1.4-зонд) → перенумерация S243, Roadmap-атрибуции обновлены (Устав 11.1.1); история чужих коммитов, называющих B0-работу «S241», не переписывается — отображение зафиксировано здесь; S240 видел мой сценарий в ?? (untracked) — параллельная серия активна; код-пакет B0 вошёл в полный сохраняющий коммит параллельной серии — коммит S243 строго file-scoped docs-only (4 док-файла). H5-зонд (GC-00 изоляция чиста): прямая мутация settings.saves_dir + backend/saves пуст в контрольных прогонах S243.
⚠️ Уведомления соседям (ретрансляция): (а) RE-трек: confirm_migration .migrated not found в temp-среде GC-00 — WARNING каждый тик, каузальной контаминации не создаёт; (б) B1.4/SSM: [DIAG_B14_SSM]-принты в контрольных прогонах S243 ОТСУТСТВУЮТ — зонды сняты (S242), на экзамен не влияли; (в) эхо готовых черновиков: AG1-D1↔RE-D1 (V2RelationshipBackend._cache — двойное наблюдение), W2 (affordance_facts_map-гвард без полей — частично снято S239 G2). reports/LAST_SESSION.md — не тронут (решение владельца). LLM-инфра (не моя зона, эхо владельцу): config ищет qwen_7b по пути Q5_K_M.gguf, файла нет → R4A MEMORY_SUMMARIZATION падает в superbox-прогонах; экзамену не мешает.
📁 docs/ENIGMA_ROADMAP_v3_4_AVATAR_AGENCY.md, "docs/ADR (Architecture Decision Records).md" (L8.2/L14.5), docs/audits/ADR-O-379_IMPACT.md (новый), docs/audits/ADR-O-380_IMPACT.md (новый), docs/MUTATIONS.md (эта запись)
IPT: ✅ 45/45 (гейт входа; док-мутации код не трогают). КРАСНЫЕ ИНВАРИАНТЫ: было 0 🔴 → стало 0 🔴

### S244: Р2-В — защита B1.4-канала: единый whitelist-приёмник player-position (вердикт Мастера «В») | ✅ оба rail GREEN, edges 2/2, IPT 45/45
🎯 Принуждение уже заявленного контракта B1.4-FIX (player position) by construction: FE физически не может быть anti-writer'ом G3. Оба транспорта (HTTP routes.py + Direct game_loop_bridge) сходятся на ОДИН семантический приёмник; else-ветка — честный отказ без записи; FE не менялся (0 строк фронта).
⚙️ Патчи: (1) GameLoop.save_scene_state → B1.4-RECEIVER: из payload принимается только npc_positions["player"]+location_id; сцена не найдена — warning-отказ; tick-locked-окно сужено до player-записи (полная замена сцены исключена — B5); (2) routes.py update_scene_state → тонкий делегат приёмнику (merge/protected NEW-8/TIME-FREEZE субсумированы by construction); (3) replay_player:51 → миграция на scene_manager.save_scene_state (легитимный внутренний writer полных сцен — whitelist его убил бы; E.2-делегат был чистой обёрткой, поведение replay идентично); (4) харнесс b1_4_push_probe → постоянный regression-гейт + edge-пробы E1/E2 (exit-code 1 при падении edges).
⚙️ GREEN-зонд (полный FE-дикт на входе, оба rail): critical Δ=0 (wo/rel/ac/hist/ordinals), top_level Δ=0 (backend-only ключи и projection-ключи целы), npc changed=['player'] только, red=—; edges: missing-scene=отказ без записи, no-player=no-op. Доказательная база: reports/b1_4_probe_report.json ("fix": "R2-V (S244)"). IPT 45/45.
⚙️ Уроки: (1) второй caller GameLoop.save_scene_state (replay_player, BUG-DRIFT-001-контур) пойман grep-гвардом ДО патча — контракт-сдвиг без ре-грепа callers сломал бы реплей-детерминизм; (2) test_new_8_recognition_memory не задет (persistence-слой, ниже канала) — ложные срабатывания grep-паттерна "scene_state)" отфильтрованы чтением; (3) P5 (тест-миграция) не понадобился — субсумация проверена чтением теста, не предположением.
📁 backend/app/services/game_loop/__init__.py (B1.4-RECEIVER), backend/app/api/routes.py (делегат), backend/app/services/replay/replay_player.py (миграция на scene_manager), backend/tests/sandbox/b1_4_push_probe.py (гейт+edges), docs/AUDIT_W_TRACK_COUPLINGS.md (§6 закрытие Р2-В), reports/b1_4_probe_report.json.
Следующий шаг W-трека: G3 PRE-FLIGHT — РАЗМОРОЖЕН (вердикт Мастера: только после зелёного зонда; зонд зелёный): Г1–Г4, git-археология Фаз 6–7, координация с «Память_3» обязательна; мини-ADR typed transition-op в WorldObjectStore (в сторе отсутствует, writers=0). Roadmap-синхронизация §3 (зонд✅→Р2-В✅) — преемнику (роадмап в активном WIP параллельной серии).

### S245: FT-1 — адресация реплики игрока: npc_id как форма прямого матча (полевой хвост Шага 8) | ✅ зонды 3/3×2, GC-00 4/4, IPT 45/45
🎯 Полевой P1-хвост FT-1 закрыт фальсификатором Мастера (target≠nearest) + stash-дифференциалом: «люся: привет» → отвечал Торнин.
⚙️ Цепь: кокпит parse_target резолвит «люся»→npc_id → текст «[обращаясь к maid_lusya] привет» (латиница) → PlayerTargetExtractor.extract(): name_forms (кириллица) слеп к npc_id → has_address_signal (ADDRESS_LEMMAS: «обращаясь»→«обращаться») → sticky-захват прежней цели (поле: Торнин от fallback-nearest праймер-хода). Фикс FIX_SCOPE 1: npc_id-ветка в существующем прямом матче (та же форма обращения, предлоговая косвенность неприменима — «к» часть грамматики адресации). Доказательство: git-stash-пара на идентичном входе (id=thief_shadow без патча → maid_lusya с патчем, [S.0 MATCH] npc_id at pos 13); production-зонды 3/3 ×2 (id-адресация/кириллица/симметрия; отчёты ПОСТпатчевые — одно-блоковый протокол, честно зафиксировано); GC-00 4/4; IPT 45/45.
⚙️ Честность вердикта: полевая подмена НЕ воспроизвелась в harness-зондах ДО патча (3/3 зелёные) — красное доказательство перенесено на in-vitro stash-дифференциал; патч каноничен независимо от этого (канонический идентификатор = легитимная форма прямого обращения). Координация: anti-race проверка показала S243 (B0) и S244 (Р2-В) заняты параллельной серией — номер S245; их BC-1 PRE-FLIGHT на диске — зоны не пересекаются.
📁 backend/app/services/action/player_target_extractor.py, backend/tests/gameplay/test_ft1_target_resolution.py, reports/ft1_probe_{red,green}.txt, reports/field_test_S241.txt (дозакрытие Шага 8), docs/ENIGMA_ROADMAP_v3_4_AVATAR_AGENCY.md (5d: Шаг 9 + галочка FT-1), docs/MUTATIONS.md (эта запись)
⚠️ Хвосты: FT-2 (FLEE-storm — материал BC-12 по их формулировке), FT-3 (пустые речи), У-2-канон pathspec/untracked здесь закрыт; field_test_S241.txt закоммичен (догон «Шаг 8 (доп)», не создавшийся из-за pathspec/untracked-гочи).
IPT: ✅ 45/45. КРАСНЫЕ ИНВАРИАНТЫ: 0 🔴 → 0 🔴

### S246: ТЗ-RE-01 M1b.3.1–3.4 (post-cutover readers: fallback-удаление, bootstrap β, снапшот-гидратация) | ✅ сьюта 205/205, IPT 45/45, канар жив
🎯 Readers-фронт M1b после физического cutover (S232/M1b.4): V2 RAM-authoritative — единственный носитель; кэш = проекция, не источник.
⚙️ M1b.3.1: fallback DecisionHub УДАЛЁН (обе ветки; Vacuum каноничен при живом SSOT) + V2-get легаси-формат ДОСЛОВНО (стрелочные ключи — hub-ридер :316 был слеп на таргет-ключах; сетка D3 не покрывала get; consumers: hub:316 + social_target_resolver:40) + греп-инвариант запрета + миграция test_decision_calibration на compute-kwargs (прод-путь :425-426). 
⚙️ M1b.3.2 (β): bootstrap_from_npc_dicts — подъём 5 скаляров из enriched-диктов (base_values/nature — decay-домен, НЕ переносятся; existing-RAM-wins; «источник конфигурации читает один владелец»: V2 не парсит village_relations.json) + npc_provider lazy-bootstrap (ВТОРОЙ прод-путь: idle/resume минует init_scene_state — закрыт в _ensure_lazy_bind; зонд 0→21/22 ненулевых пар) + интеграция scene_init (обе ветки _load_or_create_scene).
⚙️ M1b.3.3+3.4 (единый разрез): build_npc_snapshots(+relationship_store, +campaign_id) — кэш-слой снапшота = проекция V2 (get_all_for_source; guard store-привязки для смоуков; merge с легаси-диктом, player-дефолты social_stats — фолбэк Vacuum); idle_services-проброс; SocialDecayHandler НЕ тронут (produce Δ над снапшотом — П3); phases/decision:202 безусловная гидратация (sticky-кэш закрыт канонически; до фикса нейтрализован тик-порядком Фаза 0.5 < 5).
⚙️ P0-LLM-инцидент (2026-08-30, параллельно, приказ Мастера): двойной llama-server на 8181 → VRAM 96% → 503 NARRATIVE → DRI 2%; acquire_llama_server_lock (health + bind-проба) в server_lifecycle; оба спавнера (main, game_launcher) спрашивают лок ДО Popen; DRI 100% восстановлен; закрыт полностью (коммиты 47559f86 + 268fc600 + L4-хил).
⚠️ Инциденты-уроки сессии (7 sequencing/формата, счёт честно): S225, M1b.2.3, P0×2, M1b.4.1-partial (архив ≠ диск), M1b.3.2-preview (описочный патч без БЫЛО/СТАЛО → 62 красных: контракт-сдвиг = код+тесты ОДНИМ пакетом), M1b.3.2-fix2 (провал зонда при 202-зелёном: юнит-грин ≠ интеграционная-истина — жёлтые гейты требуют живого зонда не-юнит-доказательства). Транзиент-атаки: IPT-красные ×3 (тройной прогон опроверг; stash-атрибуция чувствительна к save-состоянию — ограничение метода задокументировано), L4-миг (self-healed). Формат-закон: патчи ТОЛЬКО БЫЛО/СТАЛО с дисковыми якорями; интеграционные гейты = зонд живого тика + канар.
⚠️ Досье-находки (в реестр §4b): RE-D1 AG1-D1-сверка (reset_campaign RAM — `_cache` не существует); RE-D2 DialogueUpdateExtractor нулевые дельты (P1: диалоги не пишут отношения!); RE-D3 BeliefCrystallization npc=break_progress:* (не npc_id); RE-D4 FLEE-массовость 6/6 при fear=0.0; RE-D5 game_loop 20 ruff pre-existing; RE-D8 S135-статик мёртв + social_deltas-копия (3.5-зонд); RE-D7 campaign-bootstrap schema-директива Мастера (ADR после 3.x).
📁 decision_hub.py, v2_relationship_backend.py (+get-формат, +npc_provider, +lazy-bootstrap), memory_manager.py (switch+npc_provider), scene_init.py (обе ветки), tick_utils.py (снапшот-гидратация), idle_services.py (проброс), phases/decision.py (безусловная гидратация), server_lifecycle.py/main.py/game_launcher.py (P0-lock), tests/test_relationship_state_store.py (205), test_decision_calibration.py
IPT: ✅ 45/45 (тройная стабильность после транзиента). КРАСНЫЕ: 0 🔴 → 0 🔴

### S247: BC-1 — Conclusion Layer: EXPERIENCE→CONCLUSION (ADR-O-381, dormant) — реализация + приёмка 6/6 GREEN | ✅ IPT 45/45, замки 45/45, ruff 6/6, B0-parity
🎯 Первый шаг лестницы после B0-CLOSED: значимый опыт порождает машино-пригодный вывод (триплет) — не фразу, не скаляр, не флаг поведения. Вердикты владельца (S243, BC1_PRE_FLIGHT §13): F1a (Фаза 9 при phase_2_events) / F2б (ConclusionGate по образу DeltaGate) / F2c (новое CONCLUSION_FORMED) / F3а (dormant M1a; CONCLUSION──X──>EXPECTATION закрыт до BC-2) / P=BC-1 (AG1-D8p отложен). Жёсткий инвариант владельца (§13.1, вербатим): «BC-1 не имеет права создавать conclusion из отсутствия нового опыта» — NO-VACUUM.
⚙️ Слои (5 новых): dom/conclusions (ConclusionPredicate [закрытый реестр, ОДИН предикат IS_DANGEROUS — вердикт «механизм, не онтология»]; ConclusionProposal [frozen, сырьё не команда]; ConclusionRecord [frozen; conclusion_id = триплет+owner+канал, урок 9.6; recall-поля MemoryCrystal НЕ наследуются — вердикт владельца]; formed_tick в срезе =0, retrofit отложен) · svc/memory/conclusion_gate (validate: source-фильтр[TESTIMONY→BC-5] → NO-VACUUM backstop → полнота → кламп → идемпотентность (trace,subject,predicate) — перенос AG1-INV-TRACE-ONCE; apply: dispatch → CONCLUSION_FORMED [observation-only, XI.2, hasattr-guard]) · svc/npc/conclusion_store (per-agent RAM; apply = единственный write-path, caller-цензус {conclusion_gate}; reinforcement = union evidence + max confidence, origin не трогаем; to_dict/from_dict round-trip S193-паттерн; мусор → skip+warning) · svc/memory/conclusion_engine (pure; вход = события EXPERIENCE_DELTA_COMMITTED тика, НЕ состояние; threat-правило v1: value≥0.5 → IS_DANGEROUS об источнике; owner из S115-формата trace_id, неузнаваемое → skip) · svc/memory/conclusion_runtime (bc1_enabled env, default OFF; ensure в orchestrator-__init__ [ДО первых событий тика]; guarded-обёртка Фазы 9 с D5-деградацией; restore при ON из scene_state["conclusions"]).
⚙️ Проводки оркестратора (3): init-ensure + атрибуты; wrapper в _phase_9_integration (до run_phase_9_integration, паттерн G2-продюсера); pre-commit проекция scene_state["conclusions"] (S193-паттерн, сосед epistemic_records). EventType.CONCLUSION_FORMED (event_types.py, сосед EXPERIENCE_DELTA_COMMITTED).
⚙️ Приёмка (bc1_conclusion_test.py — наследование методологии causal_state_test: GC-00-harness, тик-чётность, _TapRegistry, uuid5, громкие фальсификаторы, clear-протокол): A=True (прод-путь: player_threatens → PK 0.75 → вывод (maid_lusya, player, is_dangerous, conf=0.8, evidence=[event-id]) + 1 CONCLUSION_FORMED; метрика = store+события, НЕ intent — урок H2) · B=True (NO-VACUUM, тройной контроль: 0 эмитов / 0 записей / 0 resid) · C=True (state-канал без события, conf=0.8, concordance) · D=REJECTED (ArchitecturalViolationError; тест в цензус НЕ внесён — замок экзамена) · E=True (рестарт round-trip, прецедент SUPERBOX-009) · OFF=True (dormant: store=None, scene_key=absent, events=0). ИТОГ: 6/6 GREEN.
⚙️ Инциденты сессии (все пойманы гейтами, уроки): (1) самоаудит 4b: wired-smoke прошёл при ручном ensure — прод-путь слоя не инициализировался (store навсегда None; docstring обещал init, патч не вызывал) → патчи 4b.1–4b.5 (init-ensure в __init__ [подписка ДО первых событий], однократная подписка флаг-гвардом, restore только при ON [INV-BC1-NOOP edge-case], сигнатура guarded=(ctx,orchestrator)); класс: «смок прошёл ≠ проводка жива» — только прод-порядок init→publish→phase9 доказывает wiring. (2) INV-SILENT-FAILURE (IPT 44/45): except без лога в conclusion_engine:81 → фикс skip+warning (L4). (3) ruff --fix авто-применился без ревью (fix=true): 7 правок, поведение не изменено (перепрогон 6/6); урок: контрольный ruff --no-fix обязателен. (4) Дрожь Горана A 0.706↔0.707: PYTHONHASHSEED=0 → оба прогона = baseline (0.707) и идентичны → процессный hash-недетерминизм (perceiving_ids set-итерация, D11-класс), не регрессия BC-1; B0-охраняемые числа (Люся 0.800/0.272/0.777; A−C=0.023; C−B flee≈+0.33) — точный parity. (5) Утечка BC1_ENABLED из smoke в PS-сессию (опечатка в Remove-Item) — снята; сценарий сам ставит/снимает флаг. (6) ДОК-ВОЛАТИЛЬНОСТЬ: двойная перезапись Roadmap/MUTATIONS параллельными сериями за одно окно — обе волны моих S-марок (S246-черновик и S247-марки Roadmap) стёрты чужим save поверх при уцелевших эксклюзивных файлах (атлас/IMPACT); S246 на диске сменила жильца между чтениями (RE-D2+FT-3 → RE-01 M1b.3.1–3.4). Урок: якоря — только из свежего чтения диска; контроль анкеров непосредственно перед каждым док-коммитом обязателен; «вставлено в редактор» ≠ «на диске» ≠ «живучесть при живых параллельных writer'ах».
⚙️ Anti-race: S246 занята параллельной серией (текущий диск: ТЗ-RE-01 M1b.3.1–3.4; в предыдущем чтении наблюдалась RE-D2+FT-3-запись, затем перезаписана — volatile-хвост обе чужие) → S247 = max+1 по факту диска на момент записи. Зоны параллельных серий не пересекаются с моими файлами (RE-01: decision_hub/v2_relationship_backend/memory_manager/scene_init/tick_utils/idle_services/phases.decision; forensic: router/working_memory_tick — не мои). ADR-O-381 зарегистрирован по max+1 атласа (O-379/O-380 мои S243). Параллельные серии активны — коммит строго file-scoped.
⚙️ Эхо соседям (ретрансляция): LLM-шум моих superbox-прогонов (дедлок роутера + CONFIG-DEBT Q4-label/Q5-файл) закрыт параллельной forensic-сессией (RE-D2 router-deadlock; её DEBT-RE-D2A = production-форма ADR-O-377 — сходится с моим AG1-D8p-входом, двойной мандат); выводы при мёртвом LLM = семантический прыжок LLM-независим (усиливает приёмку). КОЛЛИЗИЯ ИМЁН (координация): «RE-D2» используется ДВУМЯ параллельными находками (router-deadlock forensic-сессии vs DialogueUpdateExtractor нулевые дельты в досье S246-RE-01) — преемнику различать по контексту. RE: confirm_migration WARNING в temp-среде GC-00 — не трогал; их RE-D1 «_cache не существует» = моё эхо AG1-D1↔RE-D1 (V2RelationshipBackend reset) — уже у соседа.
📁 backend/app/domain/conclusions.py, backend/app/services/memory/conclusion_engine.py, backend/app/services/memory/conclusion_gate.py, backend/app/services/memory/conclusion_runtime.py, backend/app/services/npc/conclusion_store.py, backend/app/services/events/event_types.py, backend/app/services/tick_orchestrator.py, backend/app/services/game_loop/__init__.py, backend/tests/sandbox/SUPERBOX/scenarios/bc1_conclusion_test.py, docs/audits/ADR-O-381_IMPACT.md, docs/audits/BC1_PRE_FLIGHT.md, "docs/ADR (Architecture Decision Records).md" (L14.6), docs/ENIGMA_ROADMAP_v3_4_AVATAR_AGENCY.md, docs/MUTATIONS.md (эта запись)
IPT: ✅ 45/45 (финальный: 44/45 → L4-фикс → 45/45). КРАСНЫЕ ИНВАРИАНТЫ: было 1 🔴 (INV-SILENT-FAILURE, моё) → стало 0 🔴

### S248: RE-D2 + FT-3 — двойное forensic-закрытие из живой игровой сессии (дедлок LLM-роутера; пусто-текстовые речи) | ✅ own gates GREEN; IPT 44/45 (1 foreign RED, атрибутирован)
🎯 Вход: живая сессия 2026-09-05 — «LLM не отвечает: время вышло» (подозрение «тяжёлые промты»). Выход: два закрытия §5d-хвостов + новый P1-арх-хвост.
⚙️ RE-D2 CLOSED (723c1a61 + cbdb0927, ROOT_CAUSE_CONFIDENCE 85): self-deadlock request_for_agent (router.py:617–625) — вызов с потока event loop планирует корутину run_coroutine_threadsafe на СОБСТВЕННУЮ петлю + future.result(60) блокирует поток петли → 60.03с глобальная заморозка бэкенда (HTTP/сохранения/idle) при живой и быстрой LLM (3.3–4.3с/вызов). Интермиттентность = asyncness эндпоинта: game_action/game_turn (async→петля) → дедлок; idle_tick (def→threadpool→worker-ветка) → работает. Зомби-round-trip: корутина исполнена ПОСЛЕ отказа ждущего (acquire +5мс, 219 chars, discard). «Тяжёлый промт» опровергнут данными (payload 45+452, max_tokens=200). Fix: fail-fast guard + 2 детектора (runtime + AST-tombstone). Семафор/LLM/промты исключены (V1–V8).
⚙️ FT-3 CLOSED (11058fe0): producer = write_npc_reactions_to_memory (echo DM-реакций, game_loop:1477; rce-парсинг «Имя: текст»); пустой хвост «Имя:» шёл в ОБА стока без фильтров: NPC_SPOKE content="" (6 хендлеров) + STM-ход сессии (npc, player) — partner_id="player" сигнатурный дефолт (memory_manager:115); при закрытии сессии консолидируется в L2. EventMemory.summary структурно непуст (or-цепочка + bracket-фолбэк) — «''» жил в STM-ходе; материализатор оправдан. Fix-B: гвард пустого хвоста + детектор 2/2. B1 (фантомная пара) и B3 (EventMemory self-target) — design-questions; imp=0.80 — follow-up lead. Ретракции: «событие ,680» = summary-строка шины; «VRAM-семафор держался» — снято; F1 «text/content mismatch» — снято or-цепочкой.
⚙️ DEBT-RE-D2A (новый P1-арх): production-форма ADR-O-377 «медленный интеллект не берёт настоящее в заложники» — dialogue-экстракция → intelligence queue (TaskScheduler FIFO → LLM → Proposal → DeltaGate; STALE по tick; REBASE отложен §ENIGMA-002). Guard = containment: до D2A loop-thread вызовы деградируют громко (пустой DialogueUpdate) — согласуется с досье-находкой RE-D2 §4b («диалоги не пишут отношения»). Доктрина Мастера (три скорости, FOCUS TIME ≠ PAUSE TIME, Class A/B/C, право перебивания) — реестр видения; формальный ADR при D2A. BC-1 HOLD снят после GREEN guard.
⚙️ Попутные регистрации: F-NS1 (P2, L2.5 namespace-загрязнение break_progress:*/combat); CONFIG-DEBT = уточнение эха S243 (фактически загружен Q5 4.36 GiB/4.91 BPW — label/path/содержимое рассинхрон); O1-live (aborting-stuck churn + /abort 404 ×2 — мини-аудит _request_in_progress); M-08 (P3, jsonl-реестр промтов мёртв); avatar×2 (BodyTopology YAML; CharacterSheet.effective_hp); SPATIAL 6/7 (FT-2 материал); O2-кандидат (llama-дубль 393-токен промптов); NPC-NPC + soliloquy каналы живы. Эскалация RE-01: V2RelationshipBackend._cache при каждом new_game. Evidence: reports/history/cds_session_20260905_104216_RE_D2_FT3_evidence.log (c1d39236); raw cds_backend.log вне git, freeze.
📁 svc/llm/router.py, svc/memory/working_memory_tick.py, tests/test_re_d2_router_guard.py, tests/test_ft3_empty_speech_guard.py, reports/history/...evidence.log, docs/MUTATIONS.md (эта запись), docs/ENIGMA_ROADMAP...md (§5d)
⚠️ Anti-race: S246 занят RE-01-серией (их запись M1b.3.1–3.4 закоммичена в fee7c7df). ⚠️ Инцидент записи (уроки): чужой WIP откачен checkout'ом, патч-снапшот погиб (PS 5.1 `>` = UTF-16LE → git apply «No valid patches»); их WIP рематериализовался и закоммичен НАМИ под нашими S247-сообщениями (fee7c7df = их S246-запись, e7d63863 = их M1b-дельта; контент цел; история не переписана — rebase при живой серии опасен); 7f9a31e7 = пустой артефакт (удалён). Гейты док-коммитов вперёд: (5) git-снапшоты только `git diff --output=`; (6) grep-верификация ДИФФА на свой маркер ДО коммита (ловушка fee7c7df: git add всасывает ремате-риализованный чужой WIP); (7) «no changes added» после команды вставки = правка не внесена — проверять до следующего шага.
IPT: ✅ 44/45 (собственных красных 0; единственный red — чужой conclusion_engine.py:81, атрибутирован). КРАСНЫЕ: 0 🔴 → 0 🔴

### S249: GC-09 A/B — первый гейт, рождённый нормой GACR (§5a.9-реестр): Body Runtime GREEN + Embodied Constraint RED-доказательство | ✅ A GREEN / B RED (finding)
🎯 Вердикт Мастера (2026-09-05): Body Simulation ≠ Embodied Agency; сплит A/B; RED не ретушировать; Звено 3 — ADR-фронт, не патч; вход — production-legitimate (не инъекция, не combat, не сотни тиков); harness-capability «accelerated body-load» — precondition B.
⚙️ A (7f369e54): 25 production-тиков; one-way-оси hydration/nutrition сместились у обоих субъектов (98.8→92.8/99.7→98.3; 98.5→91.0/99.7→98.1); Контраст персонификации: maid (load 0.5) теряет fatigue 0.375→2.25 и energy 99.5→97.0, blacksmith (load 0, отдых) — на клампах. Численно доказано: ADR-O-373-фикс S2B-провода жив (S2B был production-мёртв до плоского снапшота).
⚙️ B (f8051d70): from_legacy-копии живого maid_lusya; единственная переменная — fatigue+90/energy−90 через StateApplicator; гвард мутации (fatigue>50) зелёный; availability-наборы A≡B — тело не закрывает ни одного интента. RED-доказательство STATE→BEHAVIOR GAP (домен тела, второй после отношений); единственный body-edge — Vital State Guard (смерть/бессознательность, compute:440). Архитектурная гипотеза Мастера «State Consumer Gap» — второй живой домен (не закон: выборка мала).
⚙️ Архитектура Звена 3 (по вердикту): не if-fatigue в _is_intent_available (DecisionHub = парламент всех подсистем); контракт BodyConstraintResolver: BodyState → ActionConstraints (locomotion_capacity/combat_available/social_initiative_available/exploration_available/rest_required) → DecisionHub. Отдельный ADR-фронт «Embodied Constraint», открывается после RED-фиксации.
⚙️ Попутные: intelligence_queue.py соседей (D2A-реализация, их WIP) — атрибуция foreign-red в IPT (44/45→45/45 в этой сессии: их 2 тихих отказа закрыты их серией); релея: «2 INV-SILENT-FAILURE intelligence_queue:54/:217 — их зона, не чиним».
📁 tests/gameplay/test_gc09_body_causality.py (+81), harness.py (read_body, +103 с A-коммитом), docs/MUTATIONS.md (эта запись), roadmap §5d
⚠️ Anti-race: S248 = наш tail; S249 — по max+1 на момент записи (параллельные серии активны, file-scoped только наши файлы).
IPT: ✅ 45/45. КРАСНЫЕ: 0 🔴 → 0 🔴


*   **Dialogues:** `STM`, `SCHEDULER-FAIL` (L4), `LIVENESS`
*   **Traversal/Death:** `ZOMBIE`, `DEATH-LOCK`, `TERMINALITY`
*   **Time/Space:** `WALL-CLOCK`, `KERNEL-RNG`, `SPATIAL-SSOT`, `POSITION-MUTATION`, `TICK-CARDINALITY`, `TEMPORAL-ISOLATION`, `SCENE-ENTITY-ISOLATION` / `NPC-CARDINALITY`
*   **Architecture:** `SILENT-FAILURE`, `FRONTEND-ISOLATION`, `DOMAIN-PURITY`, `L1-APPEND-ONLY`, `NO-RETRO-SIM`, `COMMIT-CARDINALITY`, `HP-SSOT`, `WORLD-OBJECT-TOPOLOGY` (S230, ADR-O-371)`
*   **Epistemic/Social:** `EPISTEMIC-BOUNDARY`, `INTENT-EVENT-COMPLETENESS`, `FATE-CRITICAL-BROKEN`
*   **Infra:** `PBT-ROUNDTRIP`, `ADR-NET`, `REPLAY-STORE`, `REPLAY-DETERMINISM` (WARN), `SAVE-LOAD-INTEGRITY`, `EVENT-CARDINALITY`

---


*Новые сессии добавляются в конец Раздела 2 строго в порядке возрастания номера.*



