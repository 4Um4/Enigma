# MUTATIONS.md — ENIGMA Causal Evolution

> **Формат v5.0:** одна строка на сессию. Тела сессий НЕ пишутся: решения → `docs/ADR (Architecture Decision Records).md` + `docs/audits/ADR-*_IMPACT.md`; хроника прогонов → `reports/` + git; текущее состояние и долги → `docs/ENIGMA_ROADMAP_v4_2_NL01_APPROVED.md` (§0/§7/§10; реестр ТЗ и самоочистка — §1.3). Прецедентные ссылки, на которые ссылаются коммиты/контракты, сохраняются в строке.
> **Полный исторический архив** (2383 строки, детальные тела S143–S310, диагнозы, инциденты, уроки протокола): `git show b59dac3f:docs/MUTATIONS.md`
> **Протокол ведения (вперёд):** завершая сессию — (1) добавить строку в реестр ниже (ID + суть + вердикт + ADR); (2) живые хвосты → раздел «Живые хвосты» (или roadmap §7, если затрагивает активные треки); (3) ничего многострочного в этот файл. MЕТА содержит только счётчик записей — проверяемый.

## МЕТА
Записей: 203 (канон-греп правила 5 по живому файлу; дубли S-меток: 0 — проверено грепом; двойная коллизия S314/S317 разрешена ренумберами — Understanding→S316, RE-M1b.3.6→S318; пропуски номеров — артефакты ренумберов; сверка с архивом b59dac3f — отдельный хвост) | Доменов: 10 | Базлайн: IPT 51/51

**Примечания целостности номеров:**
- Пропуски S153/S171/S173/S197/S232/S275–S277 — артефакты параллельных серий и ренумберов (прецедент: S243, ренумбер S241→S243; S242, перенумерация при коллизии). Не восстанавливать.
- Дубль: «Доска-детектив К1» записана под S301 и S302 → канон **S302** (S301 канонично = Replay Phantom).
- Дубль S314→S315 (двойная коллизия): closing-коммит 00d0efbe записал Understanding-сессию под S314 (занят RE-сессией), ренумбер 4510e2aa — под S315 (занят «Долговой зачисткой»); канон Understanding-сессии = **S316**. Правило: номер вписывается в артефакты только после явной проверки СВОБОДНОГО номера (счётчики S3XX, не «последняя строка реестра»).
- Параллельная запись S314/S315: git-порядок (коммит S315 раньше) ≠ реестр-порядок; канон: S314 = RE-01 M1b.3.5/GAP-1 (SHA 4041294e), S315 = ruff fix=false (строка её сессии при записи).
- Конфликт ADR-номера: **O-400** фигурирует в S274 (WATERMARK PatternDetector) и S303 (affection) — разрешить по атласу (команда №24), ошибочную строку поправить при следующей правке.

## 0. ENIGMA ONTOLOGY (Context Anchor)
*   **Psyche Layers:** `L0`=Physics/Body, `L1`=Chronicle (append-only SQLite facts), `L2`=Identity/Beliefs (crystalized), `L3`=Drives (ephemeral, per-tick).
*   **Epistemic Boundary:** NPCs only know what they physically perceive (radius/LOS). No telepathy. `target_id` doesn't bypass physics.
*   **Triple Membrane:** Filters L1 facts into L2 beliefs (Physics, Personality, Social).
*   **Pure Reducer:** Tick pipeline must NOT mutate global state; it yields `TickMutation` (deltas) applied later.
*   **Drift:** Desync between shadow/legacy pipelines or state mutations (Class D = spatial desync).
*   **IPT:** Invariant Property Tests (`tests/IPT.py`) — the ultimate AST/Runtime source of truth.
*   **SUPERBOX:** End-to-end causal chain scenario tests (e.g., Belief → Intent → Action → World Event).

## 1. ЭПОХИ ЭВОЛЮЦИИ (границы приблизительны; канон прогресса — roadmap §0.1)

*   **Эпоха 1 (S04–S82): Каузальный Фундамент.** Убита RPG-математика → `body_state`/`ImpactEngine`. `SpatialService` = SSOT графа. Dual-Time Ontology. DTO-контракт.
*   **Эпоха 2 (S83–S104): Чистота Ядра.** `TickOrchestrator` → `InterventionEvent`. `KernelRNG`. L3 эфемерны, L1 append-only. Epistemic Boundary.
*   **Эпоха 3 (S105–S125): Идентичность.** `BeliefCrystallization`, Тройная Мембрана. Reality-Constrained Agency. D&D 5e Combat RNG.
*   **Эпоха 4 (S126–S141): Презентация.** 5-слойная архитектура. World Continuity. UI: Eavesdrop, Mood-иконки из observables.
*   **Эпоха 5 (S142–S217): Санация и Великая Стена.** AST-линтеры, SUPERBOX, Epistemic Core, Stage 0/1/2A (Commitment), Vertical Slice «Тень и золото», Calibration Lab.
*   **Эпоха 6 (S218–S248): Треки.** RE-01 (M0→M1b.4), Body Stage 2B, W-track (W0–G2), AG1 (Фаза A/E1/E2.0/BC-1), Lab M1, B0-CLOSED, forensic-закрытия.
*   **Эпоха 7 (S249–S310): Causal Slices & Living World.** IRON RIVER (детерминизм), R5–R8 CAUSAL SLICES, TEMPORAL EPOCH, CognitionContext, UI Workbench, De-god, G3 EXECUTION, S2B.7 Pain, TRADE β.

## 2. РЕЕСТР СЕССИЙ

### Эпоха 5: Санация и Великая Стена

- **S143** Self-Healing L0-2,7 (MVP tick subscription, telemetry) · ✅
- **S144** V8.3 Closure + End-Screen (закрытие 40+ критических MVP-багов, оживление пайплайнов) · ✅
- **S145** Dialogue Threads (STM persistence; Hard Contract: No STM = No LLM) · ✅
- **S146** V8.6 Closure (17 MEDIUM/LOW: spatial/will/cleanup) · ✅
- **S147** Workplace Affordance (действия NPC привязаны к точкам мира) · ✅ · ADR-O-326
- **S148** Body Topology (D&D 5e Encumbrance; 3-канальная презентация) · ✅
- **S149** Drift Lab v2 + PBT (hypothesis) + Probes · ✅
- **S150** Dialogue Hard Contract (INV-DIALOGUE-SCHEDULER-FAIL; подход без STM → approach) · ✅
- **S151** Zombie Traversal (TraversalFSMProbe; INV-TRAV-ZOMBIE) · ✅
- **S152** Death Lock (INV-DEATH-LOCK; запрет движения мёртвых) · ✅
- **S154** The Great Wall: CAUSAL_CONTRACT v2.0 + 11 AST-линтеров + 4 runtime-пробы · ✅
- **S155** ADR-Net Parser (INV-ADR-NET) · ✅
- **S156** Replay Core (SQLite WAL ReplayStore, ReplayRecorder hooks) · ✅
- **S157** Economy & Social (Double Truth устранён: ActionConsequence→RelationshipStore; avatar tier=major) · ✅
- **S158** UI-Epistemic-01A Transport (PerceivedNarrativeDTO/ManifestationDTO; Telepathy Test) · ✅
- **S159** UI-Epistemic-01B Projector (AuditoryDistortionPolicy; AvatarPerceptionProfile) · ✅
- **S160** UI Doctrine v1.0 (3 слоя, Action Markers, Линза Восприятия) · ✅
- **S161** Self-Healing L0–L10 + UI Layers (ValueError вместо тихих fallback; preflight) · ✅
- **S162** UI Epistemic Integration (FocusRenderer по clarity/delivery_type) · ✅
- **S163** UI Action Markers (Закон Локальности и Временности) · ✅
- **S164** UI Redesign HUD (геометрические мини-иконки) · ✅
- **S165** UI Polish (ритм интерфейса, fade-кривые) · ✅
- **S166** UI Journal (Наблюдения → Гипотезы → Факты) · ✅
- **S167** UI NPC Activity (микро-анимации действий) · ✅
- **S168** UI Manifestation (физика тела: pose_tense, gaze_avoidance) · ✅
- **S169** UI Perception (эпистемическая честность: рваный текст, «эффект незнакомца») · ✅
- **S170** UI Attention (сдвиг камеры при SLAM) · ✅
- **S172** CI & Mypy Strict (workflow, TYPE_CHECKING; SpeechScheduler latency fix) · ✅
- **S174a** Infra Longevity MVI (PBT validators, Replay LLM Cache, Probes CausalProvenance/TemporalIsolation) · ✅
- **S174b** Visual Casting Audit (data-driven портреты: ExpressionResolver, PortraitRenderer) · ✅
- **S175** Visual Casting Editor (авторские правила expression/priority/asset) · ✅
- **S176** WorldTick Temporal Ownership (суверенитет TickOrchestrator над временем; устранён O(N²) дрейф) · ✅ · ADR-O-344
- **S177** Bugfix V.0.5.3.7.3 (IPT import, soft-degradation, duplicate turns) · ✅
- **S178** Pytest Recovery (PipelineContext contract; мутация StateApplicator зафиксирована долгом S1) · ✅
- **S179** S1: Pure Reducer (StateApplicator убран из NpcTickPipeline) · ✅ · ADR-O-346
- **S180** S2: Entity Cardinality (фильтрация по location_id до TickState) · ✅ · ADR-O-347
- **S181** S3: Causal Ordering (INV-EVENT-CARDINALITY) · ✅ · ADR-O-348
- **S182** S4: Semantic Pipeline (IntentEventAdapter — детерминированный мост) · ✅ · ADR-O-349
- **S183** S5: Dialogue & Travel FSM Terminality (INV-TRAV-TERMINALITY, INV-DIALOGUE-LIVENESS) · ✅ · ADR-O-350
- **S184** S7: Replay Determinism infrastructure (INV-REPLAY-DETERMINISM) · ✅ · ADR-O-351
- **S185** S7: Load Integrity (INV-SAVE-LOAD-INTEGRITY; load_scene_at) · ✅ · ADR-O-352
- **S186** Foundation Fortification (P0-1 Tick/P0-2 NPC/P1-5 Commit/P1-6 EventBus кардинальность) · ✅
- **S187** Epistemic Core Discovery (SUPERBOX-001: слепота к Proposition доказана) · ✅
- **S188** Proposition Layer (Epistemic Core: ClaimEvent→EpistemicRecord→модификаторы; Modifier Contract) · ✅ · ADR-O-354/355
- **S189** Arch-Sleep: Bodily Coupling (CouplingResolver, DreamSignal/Residue) · ✅ · ADR-O-356
- **S190a** SUPERBOX-005 Modifier Attribution (scores_trace_map) · ✅
- **S190b** Self-Healing Closure P0–P4 (CI gates, Doc Drift validator, AST plugin, Live Dashboard, E2E Canary) · ✅
- **S191** SUPERBOX-006 Attribution Isolation (EpistemicContext ортогонален base_score) · ✅
- **S192** SUPERBOX-007 Observation Divergence (радиус слышимости) · ✅
- **S192.1** SUPERBOX-008 Membrane Hardening (target_id ≠ телепатический обход) · ✅
- **S193** SUPERBOX-009 Serialization (EpistemicStore round-trip) · ✅
- **S194** SUPERBOX-010 Decision Divergence (убеждение — причинная переменная Intent) · ✅
- **S195** SUPERBOX-011 Action Causation (Epistemic → QueuedTask) · ✅
- **S196** SUPERBOX-012 World Event Causation (убеждение → реальное событие мира без LLM) · ✅
- **S198a** SUPERBOX-013 Second-Order Observation (каузальная петля 2-го порядка) · ✅
- **S198b** Фаза 8.1: Социальный слой + End-Screen (SocialSubscriber fallback, FateTracker, EndScreenNarrator) · ✅
- **S199** Фаза 8.2: Trust-Based Reliability + триггеры (BROKEN 5 critical ticks; UI убеждений) · ✅ · ADR-O-357
- **S200** Фаза 8.3: Epistemic Store (Player) — игрок полноправный наблюдатель; fallback Proposition; max(0.0) guard · ✅ · ADR-O-358
- **S201** Runtime Epistemic Closure (SUPERBOX-014/015; fix max(0.0) при создании) · ✅
- **S202** Epistemic Core Gate First-Order (SUPERBOX-EPISTEMIC-PRODUCTION-001; intent_profiles.py; WARN не понижается без STM) · ✅
- **S203** TaskScheduler Epistemic Closure (SUPERBOX-016; intent_type в Artifact) · ✅
- **S204** Epistemic Invariants + ADR-Net Sanitation (INV-PLAYER-EPISTEMIC-CLOSURE / TRUST-MONOTONICITY / TRUTH-IMMUTABILITY; 157 файлов ADR к стандарту) · ✅
- **S205** Semantic Torture Test Pass (26 Few-Shot; SequenceMatcher; Intent Preservation 88%) · ✅
- **S206** Canonical Testimony Reliability (инлайн-провайдер удалён; SUPERBOX-RELIABILITY-BASELINE; DEBT-R1/R4/R6) · ✅
- **S207** Observation Channel (ADR-O-360: THEFT → LOS-свидетели → EpistemicStore; инцидент двойного патча DEBT-R5 → INV-PLAYER-EPISTEMIC-CLOSURE поймал) · ✅
- **S208** P0 Avatar Ownership (AvatarStateApplicator whitelist; GameLoop = оркестратор не писатель; DEBT-R4 закрыт; DEBT-R9/R10 досье) · ✅
- **S209** Vertical Slice звено 1: NPC Agency Steal (Intent.STEAL, unlock R6.3, affinity по архетипу без npc_id-хардкодов; SUPERBOX-AGENCY-STEAL 6/6) · ✅ · ADR-O-362
- **S210** Vertical Slice слой 2: Perception Topology R1/R2 (ACTION_PERCEPTION_RADIUS SSOT; sqlite RLock — TICK_CRASH устранён) · ✅
- **S211** Vertical Slice слои 3-4: Характеры (EPISTEMIC_DISPOSITIONS; один belief → разные действия по натуре) + ACCUSE-гейт на EpistemicStore; §18 Устава; открытие DEBT-E1 (PlayerBeliefModel → projection) · ✅
- **S212** Stage 0 & Stage 1: Foundation Freeze + Causal Spine (whitelist упразднён, atomic_commit_all, NPCState Write Guard, Cause/CausalEntry/WorldSnapshot, PerceptualKernel.can_observe; DriftLab 0.0% drift) · ✅
- **S213** Calibration Lab M0 Fundament (config_overlay identity-патч; preset_io; experiment_runner; observability_tap; открытие: idle-среда = MANNEQUIN для любого пресета) · ✅ · ADR-O-361
- **S214** ФИНАЛ Vertical Slice «Тень и золото» (SUPERBOX-GORAN 12/12: мотив→кража→свидетельство→вера→речь→вера игрока→ACCUSE→последствия, без инъекций; 7 живых багов пойманы) · ✅
- **S215** Stage 2A / S203.1: Commitment Registry Shadow (реестр active_commitments; FSM 9 статусов; commitment_id=md5, uuid4 запрещён; зеркала ProjectionEngine primary/SSM fallback; baseline: 64% движений — проактивные соц. интенты; Н-56 DLG_QUEUE OVERFLOW) · ✅ · ADR-O-363
- **S216** Stage 2A / S203.2: Commitment Arbitration (CommitmentArbiter PASS/REJECT(DUPLICATE/INCUMBENT); A/B: SUPERSEDED→0, COMPLETED→100%; Y-находки: SETTLED-конфликт и churn-rhythm → S203.6 необходим; принцип: COMMITMENT решает право действовать, SETTLED STATE — обязанность действовать) · ✅ · ADR-O-363
- **S217** LLM Delivery Layer — Model Manager (дистрибутив без модели → внутриигровой менеджер: скан/докачка Range-resume/отмена/валидация целостности; каталог 7/8 без токена; UI настроек + keybinds; инциденты: кэш-фантом, NameError-race воркеров) · 🟡 runtime-верифицировано · DEBT-D1 (аудит publish_release)

### Эпоха 6: Треки (S218–S248)

- **S218** LLM Infrastructure: Model Catalog, Downloader & Startup Optimization · ✅
- **S219** Stage 2A/S203.3: Traversal Ownership + INTERRUPT-контракт (interrupt_traversal атомарен на двух рельсах; SSM.gc_traversals — единственный GC-владелец) · ✅ · ADR-O-363
- **S220** Lab M1: Intervention Consequence Routing (semantic_action → ActionConsequenceCompiler; maid trust 0→20; идемпотентность) + FE-стабилизация запуска · ✅ · ADR-O-367
- **S221** Lab M1: ScenarioPlayer (scripted-сценарии, событийная накачка зон) · ✅
- **S222** Lab M1: Native Pygame Graphs (визуализация динамики экспериментов) · ✅
- **S223** Stage 2A/S203.4: Task/Windup/Sleep Ownership + Arbiter-INTERRUPT (PRIORITY_SUPERSEDE; домен tasks.py удалён — uuid4-причина смерти; outbox async-воркеров) · ✅ · ADR-O-365
- **S224** ТЗ-RE-01 M0: онтологический контракт (relationship_engine.yaml: 45 узлов, 20 событий, запреты №1–35; линтер CI+pre-commit) · ✅ · ADR-O-369
- **S225** SMOKE-GORAN β + Delivery Fix + OpportunityProducer + 021 Calibration + Temporal Runtime · ✅
- **S226** W-track Audit + W0 Semantic World (W0-1..W0-5 PASS) · ✅
- **S227** Stage 2B.1–2B.3: Body State Contract + Energy Dynamics + Hydration · ✅
- **S228** ТЗ-RE-01 M1a: RelationshipStateStore субстрат + update_needs single-writer (caller-guard) · ✅ · ADR-O-370
- **S229** Stage 2B.4: Nutrition (третья физиологическая переменная BodyEngine) · ✅
- **S230** W1 Spatial Topology: Object Relation Substrate (architecture/world.yaml; INV-WORLD-OBJECT-TOPOLOGY) · ✅ · ADR-O-371
- **S231** ТЗ-RE-01 M1b часть 1: миграционный адаптер legacy→v2 + RelationshipWriteGate (5 скаляров) · ✅ · ADR-O-371
- **S233** Stage 2B.5: Fatigue (FLAT-контракт + Enum Identity Split + per-tick проекция) · ✅ · ADR-O-373
- **S234** ТЗ-RE-01 M1b.4: физический cutover — V2 RAM-authoritative, legacy JSON заморожен · ✅ · ADR-O-371
- **S235** Stage 2B.6 Phase A: канонические coupling-предикаты + диагностика инверсии сна (вердикты Q1–Q6) · ✅
- **S236** Stage 2B.6 Phase B: физиологический onset сна (sleep_onset_tick = ФАКТ, не расписание; SleepOnsetEligibility/Resolver; инверсия двух снов убита) · ✅ · эскалация → DEBT-SLEEP-DELIVERY
- **S237** W3 Object FSM: Execution Substrate + Gate-1 Shadow (transition/damage_object → TransitionResult; спавнер live=18; урок: INVALID RUN-guard обязателен — равные краши ≠ совпадение) · ✅ · ADR-O-376
- **S238** AG1: Фаза A + EMRL E1/E2.0 + реестр долгов (все 10 фаз тика живы; системная находка: 7 разрывов словарей за сессию — самая частая причина мёртвых контуров ENIGMA) · ✅ · ADR-O-377
- **S239** W-track G2: Affordance Producer-Facts — первый живой мост W2→решение (закон: A/B-харнессы патчат saves_dir до build_game_loop) · ✅ · ADR-O-378
- **S240** DEBT-W-AUDIT: ownership/coupling-граф simulation↔presentation + входной ограничитель G3 (B1.4-канал = главный риск-узел) · ✅
- **S241** Итерация «Пункт 5»: тесты-детекторы + PROBE 9.7 (REST-материализация) + GC-00 baseline 0/3→3/3 + AUD-D2 + AG1-D5 + AVID-1 (аватар укоренён в idle-мире) · ✅
- **S242** B1.4-runtime-зонд: runtime-доказательство anti-writer канала (direct RED×8 — wipe реестров; урок: терминальный коммит при параллельных сериях — только `git commit -- <pathspec>`) · ✅
- **S243** Документальное закрытие B0/E2.0-c (ренумбер S241→S243; guard'ы PK/Beliefs в атлас; B0-числа верифицированы побайтово при мёртвом LLM) · ✅ · ADR-O-379/380
- **S244** Р2-В: защита B1.4-канала — единый whitelist-приёмник player-position (оба транспорта; FE физически не anti-writer G3 by construction) · ✅
- **S245** FT-1: адресация реплики — npc_id как форма прямого матча (полевой хвост; красное доказательство = stash-дифференциал) · ✅
- **S246** ТЗ-RE-01 M1b.3.1–3.4: post-cutover readers (fallback DecisionHub удалён; bootstrap β; снапшот-гидратация; P0-LLM-лок llama-server) · ✅
- **S247** BC-1: Conclusion Layer EXPERIENCE→CONCLUSION (dormant default OFF; триплеты не фразы; NO-VACUUM; Gate/Store/Engine; приёмка 6/6) · ✅ · ADR-O-381
- **S248** RE-D2 + FT-3 forensic: дедлок LLM-роутера (self-deadlock request_for_agent; router fail-fast) + пусто-текстовые речи (producer-гвард) · ✅

### Эпоха 7: Causal Slices & Living World (S249–S310)

- **S249** GC-09 A/B (норма GACR §9.9): Body Runtime GREEN + Embodied Constraint RED-доказательство («state exists ≠ state has consequence»; State Consumer Gap, выборка 2) · ✅ A / 🔴 B = находка
- **S250** ADR-O-383 Embodied Constraint V1: pressure_translator (chronic-veto cap 0.3, CALIBRATION_CANDIDATE) — RED→ADR→V1→GREEN за сессию · ✅ · ADR-O-383
- **S251** AG1-D8p Intelligence Queue (production-форма ADR-O-377; DEBT-RE-D2A закрыт: P2-ПОСЛЕ 8.37с vs baseline 110.96с) · ✅ · ADR-O-382
- **S252** Living Activity срез EAT (SUPERBOX 12/12) · ✅ · ADR-O-384
- **S253** Player Dialogue Track Р-А/Р-Б/Р-В: санация речевой трубы · ✅ · ADR-O-385
- **S254** GC-DIALOGUE-01 Stage-1 Р-Г: журнал из event.radius + TAB-пейсинг ×4 + D0 SSOT-радиус материализатора + liveness-гейты ×4 · ✅ · ADR-O-387
- **S255** GC-SOCIAL-01 Stage-1.5 Social Conversation: G1 PlayerSpeechClaim (testimony player→NPC) · ✅ (S2.6–8 end-to-end = живая сессия)
- **S256** WORK Vertical Slice: разрыв «Intent.TRADE → WORLD CHANGE» замкнут минимальной сделкой на живом субстрате · ✅ · ADR-O-391
- **S257** GC-INTERRUPT-01: intent-субстрат E1/E1b (DEBT-INTENT-SOURCE закрыт) + flee-гейты задач ×4; golden 180/29 (вердикт S213 перевёрнут) · ✅ · ADR-O-389
- **S258** GC-RELEVANCE-01 self-relevance: клейм «обо мне» — отдельный эпистемический канал (R1 развязка + R2 разговорный буст) · ✅ · ADR-O-390
- **S259** M4/P7 Disclosure Verbalization + Eavesdrop Provenance Label (RED 6F/3P точный прогноз; T5 монополия) · ✅ · ADR-O-392
- **S260** IRON RIVER D-1 Phase A: четыре P0-брейкера детерминизма закрыты (F1–F4) + D-2 мини-гейт · ✅
- **S261** IRON RIVER Phase A+B: контракт D закрыт — детерминизм причинного контура кросс-процессный (A/B 3×MATCH) · ✅
- **S262** R5 CAUSAL SLICE 1 DesiredChange: угроза → желаемое изменение → способ (одна цель → разные способы) · ✅ · ADR-O-394
- **S263** R6 CAUSAL SLICE 2a capability: голод → желаемое изменение → кто способен дать · ✅ · ADR-O-395
- **S264** SOCIAL Vertical Slice: pressure→intent→target→interaction→relationship→next-tick (D1–D4 ×3; trust-дельты 5 NPC) · ✅
- **S265** R7 CAUSAL SLICE 3 grievance: накопленный вред → направленное последействие · ✅ · ADR-O-397
- **S266** TEMPORAL EPOCH Phase 1: карта + ядро + PR-1/2/3 + локация-гейты + drift-инструменты (EAT 🔴) · ✅ (EAT закрыт S267)
- **S267** FIX EAT: опровержение диагноза передачи; полная каузальная цепь Living Activity в multi-location tick · ✅
- **S268** TEMPORAL EPOCH PR-5: WorldView в TickState + гигиена hot-path · ✅
- **S269** DriftLab → научный инструмент + Epoch seal (10k×2 MATCH) + PERF-методология cProfile/deepcopy · ✅
- **S270** Worker Effect Outbox CLOSED: анатомия experience-канала (A1==A2 межпроцессно) · ✅ · ADR-O-399
- **S271** SLEEP VERTICAL SLICE: первая причинная вертикаль NEED→SATISFACTION + Visibility Contract · ✅
- **S272** Предгейт P1 tick_provider: гипотеза опровергнута; fast-path submit_tick omission закрыт (outbox 4/4, liveness 7/7) · ✅
- **S273** PHASE-C-DEBT CLOSED: relocation-supersede фикс + GAP12 root-cause (SDF = RED not-attributed → хвост) · ✅
- **S274** WATERMARK: Incremental PatternDetector State (History-tax; A/B 24×10k p95 230.6→154.9 YELLOW; L1-поток) · ✅ · ADR-O-400 (первая бронь — канон)
- **S274-DEGOD** De-godification SSM: серия ITER1–4c · ✅ · ADR-O-401
- **S278-DEGOD** Turn Pipeline Ownership Phase 3A · ✅ · ADR-O-402
- **S279-DEGOD** Campaign Lifecycle Ownership Phase 3B · ✅ · ADR-O-403
- **S280** UI Workbench: съём legacy диалоговых полос · ✅
- **S281** FIX: телепорт игрока при Esc→настройки→Esc (resume-локация) · ✅
- **S282** PHASE D Exploration Vertical: autonomous bootstrap-unlock (Э-3 GREEN=8/0; population conditional) · ✅ с оговорками
- **S283** Event Identity: детерминированная событийная идентичность (Фаза 1 семантического контракта; replay MISMATCH→MATCH — гейт отложен) · ✅ · ADR-404
- **S284** POPULATION LADDER + movement fixes №1/№2/№2b (ДЕФЕКТ №3 ОТКРЫТ: relocation «домой» переживает смену реальности) · ✅/хвост
- **S285** UI-миграция + Recognition M17 + Resume-цепь + Esc-пауза (сводная) · ✅
- **S286** Фаза 2 семантического контракта: Journal → Presentation vertical slice · ✅
- **S287** Фаза 3.1: SemanticSpan + DM_NARRATED (provenance текст→renderer) · ✅
- **S288** Фаза 3.2: Claim Bridge (provenance-позвоночник утверждений) · ✅
- **S289** UI Workbench: M19 скролл + M12 эпистемические маркеры + F12 mode-switch · ✅
- **S290** Phase 4: Investigation Board MVI (presentation-persistence) · ✅
- **S291** BUG-JOURNAL-CHANNEL: эхо player-реплик + мёртвый RCE-путь журнала · ✅
- **S292** INV-PLAYER-AUTHORSHIP: Control Source Axis F1 (player исключён из NPC-популяции решений) · ✅
- **S293** Phase 4.1: Board UX Vertical + Полигон + Smoke-фиксы · ✅
- **S294** CognitionContext v0 P1: инфраструктура внимания (DriftLab 200т: drift A–E = 0.0000%) · ✅
- **S295** CognitionContext v0 P2: первый живой цикл восприятие→обнаружение→ориентация · ✅
- **S296** CognitionContext v0 P3d: внимание → наблюдаемое поведение (верховный критерий; G0/G1/G2/G4 GREEN, G3 изоляционно) · ✅
- **S297** Приёмка ТЗ предшественника: GATE-TRIGGER-01 + P0-расследование (все заявленные файлы/ADR-O-406/мембраны реальны — «недостоверный» снимок был обрезан) · ✅
- **S298** UI Workbench S3/S4: F12-редактор стиля (B2-broadcast, HSV-пикер, типографика, аватары, клавиатура меню) · ✅
- **S299** UI Workbench D4/D5: клавиатура end-screen + Esc-семантика дропдауна · ✅
- **S300** UI Workbench D6: кэш биндов + миграция K_*-хардкодов · ✅
- **S301** Replay Phantom, Опция A+B: R1–R4 закрыты (replay_store_path SSOT; count_ticks); R5 отложен до ReplayPlayer v2; DEBT-ASYNC-SETTLE закрыт (опровергнут археологией) · 🟡 (R5 жив)
- **S302** Доска-детектив К1: фото NPC + маркеры каналов + hover-задержка (канон номера для дубля «К1») · ✅
- **S303** R8 CAUSAL SLICE 4 affection: тёплая связь → забота о состоянии ДРУГОГО (PRODUCTION-ПРОБ orm→lusya←care) · ✅ · ADR-O-413 (ренумбер с O-400, Устав 11.1.1; конфликт разрешён)
- **S304** Canonical Attention→Action Integration (Контракт Барсука I–V) · ✅ CLOSED
- **S305** G-TRACK Understanding Pipeline: Multi-Act + World Validation + Player-Move + Recovery Boundary (micro 95/95; Gate A 3/3) · ✅
- **S306** NameKnowledge: NAME-ось + writer-гейт + гейт головы (name_gate 7/7) · ✅ · ADR-O-409
- **S307** W-TRACK G3 EXECUTION: воля → объектная цель → мутация мира → событие (двухэтапно GREEN; g3_executor + compute_object_target_facts; коммиты 1ce0a00f+4169f77e; рабочее имя в коммитах «S305» → канон S307) · ✅ · ADR-O-410
- **S308** PLAYER_LINK: третий канал — доска связывает имя↔лицо · ✅ · ADR-O-409
- **S309** S2B.7 Pain/Injury: вечный FLAT-гвард + зонная capability-деривация + тик раны · ✅
- **S310** TRADE MATERIALIZATION β-Stage 1: Capability Projection (β-Stage 2 + ресток — живые швы) · ✅ · ADR-O-412
- **S311** Doc-Restructure + ADR-Net гигиена: roadmap v4.0 (3389→1277) · MUTATIONS v5.0 (2383→249, one-liner протокол) · атлас v8.0 (814→712, единый Format-Б, 12 Format-А возвращены графу) · parser-fix точка в ID (+3 теста, граф 281→285) · 62 IMPACT-шапки нормализованы · +5 stub (O-368/383/393/396/413) · ренумбер Affection→O-413 (Устав 11.1.1) · долги: AUD-D8/T3-STALE ✅ без кода, T5-ложная тревога ✅, Н-55 BORKO-debug ✅ удалён (3 debug-ветки), T6-ордек ✅ 6 корневых скриптов удалены (~31 КБ), T2 CLI-QUIET ✅ · 8 коммитов: 83bf7cee/3fb96020/0955c57a/4489456a/0ca69296/6e393586/58770cd8/46a6921d · протокол: LAST_SESSION.md — условный источник (headless-разработка не обновляет его; основной гейт = живой IPT; РЕЖИМ §3/§3.11, Правила §14/Health Checker/принцип №4 приведены) · следующая цель: кодовый фронт — Ступень 1 §0.2 (RE-01 M1b.3.5)
- **S314** RE-01 M1b.3.5 flat-readers-зонд (RE-D8) + GAP-1 трёхслойный вердикт + R001-лаборатория: 1A Store→enrichment→rc[player] 🟢 production-proven (R15: goran rc_player_trust=60.0 селективно, остальные 5 NPC 0.0), 1B cache→reader 🟢 unit-proven (micro 3/3: fear-ось 0.75/0.30 непрерывно, trust-дизъюнкция порога −30: −0.2/0.0, Vacuum-гвард), 1C player-intervention→hub_event(actor=player) 🔴 NOT BUILT (36/36 вызовов is_player=False — интервенции мутируют мир, не рождают событие интерпретации) · reader-fix nested-read при actor_is_player (порог/формула/клампы не тронуты; не-player ветка байт-эквивалентна прежнему фактическому поведению) · F5-лаборатория = microscope над production (ExperimentRunner→build_game_loop→idle_tick; temp-saves+MockProvider+ObservabilityTap; контур ADR-O-361/368 подтверждён кодом) · preset_io: npc_overrides.social (whitelist 5 скаляров гейта, NaN/bool-гварды) · runner: _apply_initial_social (canonical update_relationships после тика 1; Initial=Store: +60/+60, −60/−60, 0→Vacuum-no-op; A≡A2 детерминизм Store-уровня) · пресеты golden_social_{p60,m60,z0} + сценарии clone_probe_v1/diag · платформа: WIP-PLATFORM 953051fc (S312/S313-стек) · хвосты: GAP-1C / GAP-4 idle-store wiring / α-design-question (rc[actor_id], модели A–D) / fear×0.15 CALIBRATION_CANDIDATE / lab CWD-path · IPT 49/49 ×3 · коммит: 4041294e
- **S312 ТЗДНЯ** (2 дефекта преемнику + починка старых тестов): P1 CI-blocker закрыт (source-guard llm_server_manager + except-мембраны ×2; collection 8 errors→0); P2 full_loop восстановлен (мембрана scene_state в reaction_subscriber:232 + тест к контракту S113/TickResultDTO — pure reducer, вход не мутируется); 70/72 старых падений закрыто (актуализации: S210 perceiving-контракт + or-ловушка хелпера, S214 reason-константа, S267 action=, S268 copy/overlay, S276 prefix-target_loc, S292 text-payload, IRON RIVER game_time-оси, DEGOD пути-фасады, SLEEP-SLICE/FIX-SCENE atomicity, цензус Г4: +activity_lifecycle_service runtime-writer +3 тестовых; NPCState._ALLOWED_WRITERS: +2 sandbox PK-scoped) · мини-ADR ×2 (цензусы) · коммит: git
- **S313** Understanding Track: arbitration-boundary (QUESTION/no-acts → LLM slow-path; fast-path больше не закрывает вопросы молча) + P1/RC2 fast-фантомный ATTACK (action-override по снятой фантом-пропозиции; падежный резолв NPC-имён `_resolve_npc_by_name` в фантом-детекте — живой регресс «ударить Горана» пойман acceptance'ом; UNCERTAIN-override запрещён) + Consumption/Step5 интеграция (ASK_PROVENANCE — канонический тип; ownership provenance перенесён из consumer в canonicalization; keyword-детектор удалён, regression lock «consumer не читает topic»; Predicate.NAME мини-запись; Act Consumer: конкурирующие claims без overwrite, challenge БЕЗ мутации belief) · **RCA: current inference path demonstrated non-reproducible canonical output despite temperature=0 + fixed seed** (det-check GREEN→RED на идентичном состоянии; invalidated A/B) → RC8/RC3 BACKLOG до стабильного inference path (Qwen3-8B) · few-shot RC8 = PRESENT/EFFECT UNPROVEN · probe corpus v0 + det-check = постоянный протокол (det-check RED → semantic experiment STOP) · 9 замков + micro conftest env-иммунитет · baseline: micro 142/142, IPT 49/0 · RCA-карта: reports/RC8_DETERMINISM_RCA.md · 🟡 RC8/RC3 open-backlog → закрыто S316
- **S316** Understanding Track: DEBT-INFERENCE-NONDET закрыт тёплым протоколом (инструментализация [DET-ENV]/[DET-TRACE]; M1 cold×4: флакинг 0–24%; M2 warm×3: 90/90 GREEN; det-check = тёплая пара + контрбаланс) · RC8 A/B валиден: STATE-B (few-shot) 0/27 ASK_PROVENANCE в 9 прогонах vs STATE-A 2–3/27 → few-shot удалён из production (ENIGMA_RC8_STATE=B легаси; замок диффа 3 строки) · unspecified-дефект pipeline закрыт (акт без topic = честное UNKNOWN §ENIGMA-003; corpus-маркер «*»; замки 3/3) · order-effect = observed order-dependent degradation (причина не установлена) · baseline v2 (reports/rc8_baseline_v2.txt): ASK_PROV=3/27, unspecified=0 · ✅ · micro 158/158, IPT 49/0 · коммиты: 8d1124ff, 72db70f3, 82da83b5, 00d0efbe · следующий шаг: класс-эксперимент PROVENANCE/ORDINARY/THIRD-PERSON на независимых формулировках
- **S314 Долги-зачистка** (санкция «закрыть все долги и ошибки mypy/ruff»): ADR-O-R2 — feasibility-контракт оживлён (decision_hub: кейс-нормализация + множитель 0<f<1; gc09-B ✅ 2/2 — RED-маркер S254 закрыт); mypy strict 13→0, soft 92→0 (__all__-экспорт ×6 источников, PipelineContext-легализация, Any-инварианты, unreachable-гварды); ruff 244→10 (F841-скрипт ×53, E70x per-file policy в ruff.toml — ОСТОРОЖНО: fix=true в шапке, разведка всегда --no-fix) · мини-инциденты: ruff-разведка 14 silent-автофиксов (выучено), als-скрипт сломал __future__ (восстановлен, 17/17), TOML-дубль ключа · run_terminal_dm удалён (оба API мертвы, преемник run_terminal_mvp) · f1_trade-коллизия S189×economic (R2_DIAG-данные в хвостах) · коммит: git
- **S315** Долговая зачистка (санкция Мастера, вне §0.2): AUD-D3 abort_generation guard (hasattr, прецедент router) · P18 lint_kernel_rng v2 (BoolOp fallback-bomb + literal rng_seed + маркер ADR-O-301-DEBT; 9 сайтов = MATH-8) · ruff fix=false (S314-инцидент) · DEBT-LOC-HARDCODE vacuum+fail-loud (связка с S282 wipe доказана) · B1 ADR-Net parser v2 (N/A→[], atlas-form, standalone-ветка, merge-guard, _parse_files_value; 411n/265e; with_files 5→55; INV-ADR-NET GREEN) · STALE-закрытия: W-F821, S313 tick_ctx, CONTINUE-WIPE (M16) · уроки: `a or b`=BoolOp; патч-по-памяти → сломанные БЫЛО ×2 (§13.2 обязателен всегда) · коммиты: 89d297d3, 6710976d, fade60a5, df83c2ce · IPT 49/49
- **S317** INV-CONSUMER-GAP Stage 1 / старт Causal Anatomy (ТЗ-мандат; ADR-O-414): Layer-1-линтер lint_consumer_gap (тупой+подозрительный: census 174 typed+24 container; детекторы Store/Load, getattr/setattr, keyword-конструкторы frozen, object.__setattr__, dict-литералы, one-hop алиасы, сентинелы models; domain/-ридеры; PARSE fail-loud; utf-8-sig BOM-урок ×11) + debt-реестр consumer_gap_debts (26 записей CG-D-01..14/B1 + ADR-123/S310; запись без authority = CRITICAL и орфан выживает — D2-доказано) · урожай 180→31 находки (7 патчей сканера: snake-акронимы, payload-over-merge, BOM ×3 read-sites, алиасы .get/update, конструкторы, сентинел-namespace no-op-урок) → roadmap §7.8 (внесён, коммитится владельцем v4.2) · IPT 49→50 INV-CONSUMER-GAP-ORPHAN (лимит 15 не тронут) · экзамен E1/E3/D2 RED→GREEN ×6 (E3: NO_READER-only = различение Store/Load; D2: двойная защита реестра) · ✅ · ADR-O-414 + IMPACT + EXAM · коммит: git (pathspec) · Stage 2 = causality_manifest (KNOWN_ORGANS десятка / KNOWN_TERMINALS, organ/terminal-декларации ~198 полей), Stage 3 = perturbation harness → GC-11 · Дополнение (внесено S321, хвост реестра): Stage 2a/2b закрыты в теле S317 — манифест 198→291 (+93: relationship_contracts/desired_change/epistemology/memory_crystal/experience_trace; schema-self-exclusion), debt-реестр поглощён (Q-A; SHA 3315aaf2/bdb6d2a5/84cc95bb), орган-отчёт 10/10 (3 CAUSAL), экзамен E2/E6/E7/E9/D1; уроки: сериальные однотипные правки = auto-verify обоих read-sites (3 инцидента); дамп-скрипты запускать ДО патчей; git add до pathspec-коммита untracked

- **S318** RE-01 M1b.3.6 S128-разделение (renumber c S317 — номер занят параллельной INV-CONSUMER-GAP-сессией 028408e9/ADR-O-414; вход = вердикт-матрица S314; историческая формулировка S128 утрачена — не восстанавливалась, Р4): RE-D8 закрыт — удалены мёртвый S135-статик AgentAction._get_rel_value (0 прод-callers), дубликат DecisionHub._compute_risk+_THREAT_MARKER_VALUES (прод = risk.py perceive_risk), Scalar-ветка social_deltas (Graph>Vacuum); test_flee_collapse_fix мигрирован на compute_objective_risk+nested+cast-гигиена; читатель-карта relationship_cache = вход M1b.3.7 · F5 R001 behavior-neutral (артефакт = baseline) · R002 fear-probe: fear-scale mismatch доказан (V2 −100..100 vs ×100; F70→_fear 7000) НО канал BehaviorMask мёртв end-to-end (FAIL_STAGE=PROJECT: setattr после to_persistence_dict; mask-поля только в snapshot(); mask_in_dump=false при вооружённых условиях) → RE-D9 (шкала+проекция+consumers = game-design, STOP по бюджету; State Consumer Gap выборка 4) · IPT 50/50 (старт 49/49, +INV-CONSUMER-GAP параллельной S317) · SHA 9c282746

- **S319** RE-01 M1b.3.7 греп-страж freeze-поверхности relationship_cache (вход = читатель-карта S318; развилка решена кодом: «nested-кэш» = та же структура {target:{trust,fear}} → allowlist = заморозка всей легальной поверхности): scripts/lint_relationship_cache_allowlist.py — точные счётчики строк-сайтов на файл (GROWTH=новый сайт вне ценза / SHRINK+MISSING=ценз-тач ADR; комментарии считаются; utf-8-sig ×11-урок; root от __file__ CWD-урок; UNREADABLE=fail-loud); baseline 19 файлов/52 сайтов независимо пересчитан суд-прогоном (таблица→факт заморозки); роли: SANITIZER tick_utils×10, DECISION-READER×8 файлов (преходяще легальны — сжатие после M2/D+GC-11), WRITER-SYNC/TICK-HYDRATE, LOADER/BOOTSTRAP, OWNER/PROJECTION, DECL×2, DOC×3, COPY-THROUGH; микротест 7/7 (tmp: clean/growth/new-file/shrink/missing/pin/real-tree); конфликт Anti-Race IPT.py MM (чужой staged suspect_files) — механика сохранения за Мастером; граница: GAP-1C/α/GAP-4/RE-D9 не тронуты; IPT 51/51 · ✅ · ADR-O-415

- **S320** RE-01 GC-11 L3-gate исполнен живым harness (F5/R003; A/B/B2, HELP@5+MOVE@15 vs MOVE-only@15, Закон XI): звено event→V2-RAM ДОКАЗАНО живьём (store trust 0→20.0/−10 через ScenarioPlayer→idle_tick→компилятор→WriteGate; контроль 0.0; санити тики 1–4 A≡B; B≡B2 детерминизм) при поведенческом НУЛЕ (полный dict merchant_goran идентичен 30 тиков — post-hoc дифф lab_r003_diff_analysis) → RED=находка, RE-D2-класс выборка 5 (Consumer Gap): S1 Dual-Reader Divergence (pipeline-канал store→state_l2 жив — memory_manager._relationships ≡ game_loop._rel_store, TZ-10; raw-dict-канал директивного подписчика слеп — gate не гидратирует npc_dict) + S2 Threshold Inertia (bias −30 / BehaviorMask fear>60∧trust<0, trust<−50 недостижимы одной дельтой) + S3 Silent-World (idle без player-направленных выборов) · попутные находки: doc-drift ADR-O-367 Files (test_m1_trust_intervention.py отсутствует в main — жив только в ветке V.0.5.3.9.2), SocialTargetResolver 0 прод-вызовов (мёртвый reader, кандидат сжатия allowlist O-415 — ценз отдельно), MISSING_TRAVERSAL_PROPOSAL ×4 (ADR-O-323, pre-existing) · граница: GAP-1C/GAP-4/RE-D9/α не тронуты · ✅ RED=находка · ADR-O-416
- **S321** INV-CONSUMER-GAP Stage 3 / PerturbationHarness (ADR-O-414; вердикты Мастера: INVALID/INJECTION_FAILED/GAP/WIRED, INJECTION_FAILED≠GAP, CAUSAL=семантика A — проводимость до вычисления, argmax_flip=annotation, state-level only, A/A rows+scores): прибор tests/gameplay/perturbation_harness.py (адаптер над TavernGameplayHarness §9.2; PHYSIOLOGY=apply_deltas_only+Cause / RELATIONSHIP_V2=update_relationships; uuid5; noise-off; тик-чётность) · smoke GREEN (A/A 24/24+scores≡) · пробы: fatigue+90 GAP+utility (57 осей; дельта выживает до N — накопитель, не перезапись), energy−90 GAP+utility (11; razor-гейт 9.9<10.0 сработал), trust+60 V2 GAP+utility (52 оси, 1-й пост-инъекц. тик; baseline-Vacuum read_trust=None) → Q2-дифференциал: S1 опровергнут для находки S320 (store→utility проводит; поведенческий ноль = S2/S3) · re-proof GREEN ×2 (test_gc09_reproof_{fatigue,energy}.py; capped×0.3±0.30; fatigue двухтрактовый: cap O-383 + sleep_pressure O-375 — прибор разделил два ребра одного органа) · beliefs: S243-миссматч → вердикт = миграция proof на epistemic_decision_divergence_test.py (S194; хвост — манифест-хирургия) · находки: energy razor-margin, hub ФАЗА-1 dead-continue, асимметрия 57/11 (→ CG-D-15/16/17) · базлайн: IPT 51/51 (параллельные 50→51), линтер GREEN (291/77/0) · ✅ прибор+re-proof; хвосты → roadmap §7.8 · коммит: git (pathspec)

- **S322** RE-01 M1b.5: npc_state_helpers.py удалён ЦЕЛИКОМ (обе функции мертвы — 0 импортов/0 вызовов; омоним layered_memory.write_npc_memory = другой живой метод; до-Stage-0 онтология; 143 del, 71384bba) · AUD-D5 вердикт по фактам: legacy RelationshipStore НЕ прод-SSOT после M1b.4.2 cutover (switch в GameLoop.__init__ до всех 5 захватов _relationships; V2 RAM-authoritative; legacy = M1b.1-фолбэк + тест-фикстура; removal = фаза K) · AUD-D5(б) corrupt-ветка fail-loud: ContractValidationError (домен ADR-O-370) вместо except→{}-Vacuum (ec67f730) + smoke §3.9 + regression ×2 в сьюту (f97208b9, 205→207) · гипотезы: H1 (legacy shadowed) ✅, H2 (разрыв new_game-reset) ❌ опровергнута (CampaignLifecycle после switch → reset = V2-метод), H3 (MemoryManager.update_relationship мёртв) ✅ (0 prod-вызовов) · НАХОДКА: scene_state_provider v2 — НЕ vestigial (doc-drift-маркер в v2-docstring+scene_init): несущий sync-тракт (sync_into_scene из update/reset/bootstrap; bind() сцену не обновляет; тест-enforced test_location_change_keeps_relationships) — удаление = потеря отношений при save · TECH_DEBT_NOTE: Pylance/mypy-жалобы pre-existing тест-фикстур (140 err/файл; AFFECTS_CURRENT_BUG: NO; pyproject tests.* exclusion unused) · IPT 51/51 ×6 · коммиты: 71384bba, ec67f730, f97208b9, 942df582, d34a0b53, fcca78b9 · Р2 исполнен (фасад + сирота _relationship_write_gate удалены; TestMemoryManagerGateParity удалён — gate-покрытие в TestWriteGateD3Parity; сьюта 207→205; residual-grep=0) · Р4 исполнен (v2-docstring «НЕ vestigial» + scene_init канонизация) · ретро-регистрация RE-M1b-цикла: ADR-O-417 + ADR-O-417_IMPACT (аддендум S322) · TECH_DEBT_NOTE+: Pylance Protocol-narrow reset_campaign_state (hasattr-гварды, runtime-safe, pre-existing)

- **S323** Аудит корпуса «Почти Актуальные TZ» + самоочистка вшита в roadmap: git rm 20+txt (ТЗ-А×4+Стадия_2 → наследие A2-LIVE §7.6/ADR-O-363/365; STABILIZATION; IRON_RIVER [S260–261]; LLM_PIPELINE [O-313/359/364]; контур-трио 31.08 → поглощено §7.3/§7.7/RE-D9; RemontTZ×6 → DEBT-DOC-DRIFT-ISPRAVLENIE закрыт; docx-исходники ×6 → конвертация в md ×3: декомпозиция/TZ-EKS/Living-Activity [гейт покрытия; decomposition.docx никогда не коммитился — удалён с диска]), git mv 2 → docs/audits (RUST NO-GO, RELEASE_DEFECT); попутно в индекс IMPACT O-415/416 (+O-417 добавлен; артефакты S319–S322, Устав §11.4). Roadmap: §1.1 акт. + §1.3 реестр ТЗ + ПРОТОКОЛ САМООЧИСТКИ (7 правил) + §0.2 правило(6) + §6.C CT-01..03 + якоря §4.1/§5.3/§7.5; указатели РЕЖИМ §3/Правила §15/шапка MUTATIONS → v4_2_NL01 (были на несуществующий v3_4 — блокер пусто-оконного режима); RE-01 v1.9 шапка → «КАНОНИЧЕСКИЙ ИСПОЛНЯЕМЫЙ КОНТРАКТ». Корпус: 24 файла (22 md + 2 pdf). IPT 51/51 ×2 · validate: line-drift только pre-existing

- **S323-верификация** Living-txt: удаление ратифицировано — txt был битым экстрактом с OOXML-утечкой (шинглы w:tab/hyperlink/pageref), md покрывает 66/66 секций, 76.9% = XML-мусор+TOC, не потеря контента. Дефекты признаны: (1) плейсхолдер S{max+1} в DEBT-строке §3 → S323 (исправлено); (2) плейсхолдер в сообщении коммита cbb0c9d1 — аменд НЕ проводился (живая параллельная S322-amendment 7384fecc в окне сессии, правило 4); номер каноничен по строке S323, сообщение коммита историческое. МЕТА-baseline 49/49→51/51.
- **S324** Долговая зачистка AST-гейта §1 (lint_enigma_ast; санкция Мастера, ветка долгов): гейт 299→45 — все 45 = hot-zone M2/D (tick_orchestrator 14 / npc_tick_pipeline 13 / post_decision 5 / reaction_subscriber 5 / decision_hub 4 / state_applicator 2 / v2_relationship_backend 2), parked → reports/ast_gate_hotzone_parked.txt, добьёт владелец ветки (вердикт Мастера: а); 245 сайтов / 59 файлов: однострочные noqa-хвосты ENIGMA001/002 по прецеденту дерева (415 канон-сайтов); триаж: E001 57 построчно — все легитимные Optional-контракты (round-trip ADR-O-371/O-208, defensive-ридеры, optional-wiring), E002 242 — паттерн + спот-чеки, T1-кандидат work_orders:85-88 опровергнут чтением (уже fail-loud), 0 поведенческих фиксов; инциденты: EOF-артефакт скрипта (+\n×59) пойман спот-чеком, устранён до коммита (дифф 245/245), первый commit упал (pathspec-синтаксис) — повтор, hook ADR-WARNING разрешён ЧАСТЬ XIV (все NO); гейты: compileall 0, mypy 0/550, ruff 0, IPT 51/51 ×2 · ✅ · ea655cdb

## 3. Живые хвосты (открытое; владелец обязателен)

### Эскалации Мастеру (решения вне компетенции преемника)
- [x] ~~ADR-O-400 задвоен в атласе~~ ✅ разрешён (ренумбер: Affection → **ADR-O-413** по Уставу 11.1.1, max+1 от O-412; канон O-400 = Watermark S274; приёмка-записи обеих сессий не менялись). Остаток: проверить другие ссылки O-400-Affection по дереву при первом касании (IMPACT O-413 создан).
- **DEBT-IDLE-ORACLE** (S282-класс): idle переименовывает локацию по координатам без MovementIntent — отложен на вердикт Мастера.
- **S310 β-Stage 2** (goods→EAT→body_state): рамка запрошена у Мастера.
- **S301 Инцидент Б**: диалоговая труба пространственно слепа — постановка dialogue-task (post_decision:218–275) и executor не проверяют дистанцию/LOS.
- **S273 SDF = RED not-attributed**: атрибуция красного прогона SDF не завершена.
- **O-399 speech_reset** (S270-хвост): skeleton-publication из submit — итерация 2, если расщепление скелета сохранится; 🔴 OPEN.

### Открытые долги
- **DEBT-D1** (S217): аудит publish_release.
- [x] ~~DEBT-ADR-CLI-QUIET~~ ✅ закрыт (S311: basicConfig в adr_cli.main; IMPACT-стаб ADR-NET-CLI-QUIET_FIX; smoke-прогон)
- **DEBT-ADR-NET-N/A-FILL** (остаток B1, S315): заполнить Files в ~118 N/A-аудитах (doc-работа; INV-ADR-NET зелёный и без этого — 55/242 ≥ 10%).
- [x] ~~DEBT-DOC-DRIFT-ISPRAVLENIE~~ ✅ закрыт (S323): RemontTZ-пакет (вкл. ENIGMA_TZ_ISPRAVLENIE.md) удалён как суперсиденный — находки поглощены §7.3 AUD-D / §7.7 NL-D / RE-D9; line-drift исчезли вместе с файлами; история в git.
- **DEBT-TS**: функциональность темпа будет переделана (M4).
- **DEBT-SYSMSG**: системные ошибки невидимы до потребителя (bounded-буферы).
- **DEBT-FOCUS-OBJECTS** (S285): клик по объекту = переключение фокуса.
- **DEBT-NG-HEALTHCHECK** (S285).
- **DEBT-FE-DELTAS** (S286-класс): game_loop:1385 проецирует внутренние StateDeltas (stress/trust/fear) во фронт-канал — Rule 11 утечка.
- **AST-гейт 45 hot-zone noqa** (S324; владелец M2/D): reports/ast_gate_hotzone_parked.txt — однострочные noqa при первом касании файлов (behavior-neutral); до добивки гейт lint_enigma_ast = 45 (advisory, в IPT не гейтится).

### Открытые фронтовые хвосты
- **S284 Дефект №3**: relocation-intent «домой» переживает смену реальности (transfer/dwell/S186) — proposal из реальности тика N, валидация против другой; **строгая вертикаль НЕ собрана** (точки на разных HEAD).
- **S301 R5** (Replay Phantom): отложен до ReplayPlayer v2.
- **S283 replay-гейт**: защитный MISMATCH → живой replay-MATCH — ремонт отложен.
- **S306 recognition-набор**: RE-D2 (STM async boundary — блокер consumption; ⚠️ омоним закрытого RE-D2 S248 — другой баг), R18 (DM JSON-обёртка в тексте), R16 (actor/addressee различение), R17 (имя-дрейф Горан→Горох) + прочие из записи S306.
- **S310 живые швы**: β-Stage 2 + ресток (конечный сток → honest FAILED, retry-churn borko).
- **S309 Wound** (physical.py:244): dormant Multiple Representation — аватарный D&D-путь _check_wound, таксономии несовместимы.
- **S255 GC-SOCIAL-01 S2.6–8**: механизм доказан замком; end-to-end — живая сессия.
- **GC09-B(-R2) статус клетки**: вердикт S250 «закрыт через ADR-O-383 V1», но в прогонах S259–V.0.5.4.2.3 фигурирует как pre-existing RED — сверить матрицу §9.10 roadmap при первом касании.
- **S248-хвосты** (статус не подтверждён, проверить при касании): F-NS1, O1-аудит _request_in_progress, M-08, B1/B3 design-q, avatar×2, imp=0.80-lead.
- **S276-хвост**: Фикс №1 (prefix-authoritative target_loc) CLOSED; Фикс №2 (динамическая карта) — статус в источнике обрезан, сверить.
- **S314 RCOC Mode F**: random._inst-инструментальная точка не существует (KernelRNG не экспонирует подмену) — _RNGCounter-заглушка честная, счётчики останутся 0. Полная реализация — владелец KernelRNG.
- **S314 E402 game_launcher**: осознанный паттерн (импорты после sys.path/env-настройки — легально); noqa-блоки остаются, настоящий долг = TODO миграции map_editor на относительные импорты (уже в коде).
- **S313 RC8/RC3** → закрыто S316: тёплый протокол валиден; RC8 A/B — few-shot имеет доказанный отрицательный эффект (0/27 vs 2–3/27), строки удалены из production; ASK_PROV = 3/27 на baseline v2; канонизация provenance OPEN (класс-эксперимент — хвост S316).
- **S316 следующий эксперимент**: канонизация provenance как КЛАССА (PROVENANCE vs ORDINARY vs THIRD-PERSON QUESTION, независимые формулировки) под тёплым контрбалансированным протоколом; baseline v2 = reports/rc8_baseline_v2.txt.
- **S316 IV.3 hygiene (отдельный пакет)**: identity-blind REUSE в production-спавнерах llm_manager — перенести fingerprint-принцип [DET-ENV].
- **S316 IV.4 (defer)**: payload компрессора не самоописан (top_k/top_p/repeat_penalty — серверные дефолты) — provider-independence долг.
- [x] ~~S313 DEBT-INFERENCE-NONDET~~ ✅ закрыт S316: cold-инстансы флакают (0–24% пар, входы байт-идентичны — дивергенция ниже нашего слоя); warm same-PID протокол 3×90/90 GREEN — принят как experimental protocol (det-check = тёплая пара, контрбаланс, fingerprint); порядок-деградация = observed order-dependent degradation (причина не установлена).
- **S313 probe corpus** (tests/sandbox/SUPERBOX/scenarios/semantic_probe_corpus.py): постоянный детерминизм/регресс-инструмент Understanding (~70 реплик, два режима корпуса: exploratory/generalization; правим один вход — мерим поле-за-полем).
- **S313 эскалации**: llm_manager health-check («уже запущен» без /health → INVALID-прогоны; зомби llama-server).
- **S314 GAP-1C (activation NOT BUILT)**: player-интервенции мутируют мир, но не становятся hub_event(actor=player) → bias-ветки читателя структурно недостижимы в production; фронт = understanding (player→NPC событие через мембрану мира); семантика контура — решает Мастер. Различие «PLAYER CHANGES WORLD» vs «NPC RECEIVES PLAYER ACTION AS EVENT» — архитектурная находка R15.
- **S314 GAP-4 (idle-store wiring)**: build_npc_snapshots на idle-пути получает relationship_store=None (idle_services:87–89, оба источника None) → V2-гидратация снапшотов не выполняется, decay-домен читает legacy-кэш; владелец — decay/lifecycle, не decision; в patch-queue не входит.
- **S314 α-design-question (GAME-DESIGN, Мастеру)**: должен ли NPC интерпретировать событие агента с учётом отношения к этому агенту (rc[actor_id] вместо rc["player"])? Модели: A — любое соцсобытие; B — доверие к источнику без смены смысла; C — отношение×память/контекст; D — emergent из существующих систем без отдельного relationship_bias. Reader не менялся до вердикта.
- **S314 прочее**: fear×0.15 CALIBRATION_CANDIDATE (шкала 0–100 → кламп при fear>6.67, fear-дифференциал в проде вырожден; калибровка через Lab) · lab_screen:63 CWD-относительный путь пресета (работает только из корня).

## 4. Правила ведения (вперёд)

1. **Одна строка на сессию**: `ID Суть · вердикт · ADR/коммиты`. Многострочные тела запрещены. Рабочий цикл: Мастер скидывает лог сессии в конец файла → первым шагом следующей сессии LLM сжимает его в строку реестра, хвосты — в §3 или roadmap §7.
2. **Адресаты контента:** решения → ADR-атлас + `docs/audits/ADR-*_IMPACT.md`; хроника/диагнозы → `reports/` + git commit message; состояние активных треков и их долги → roadmap §0/§7/§10. Здесь — только реестр сессий и хвосты, не попавшие в roadmap.
3. **Хвост:** живой долг → «Живые хвосты» (или roadmap §7, если на активном треке) + владелец; мёртвый не переносится.
4. **Anti-Race (§11.1.1 Устава):** S-номер = max(диска)+1 перед записью; ADR — по атласу; дубль номеров — пометка в шапке, история не переписывается. `git commit --amend` при живых параллельных сессиях ЗАПРЕЩЁН (инцидент S318: amend молча пересоздал чужой коммит — контент сохранён, hash потерян); терминальный коммит — только `git commit -- <pathspec>`. `git commit --amend` при живых параллельных сессиях ЗАПРЕЩЁН — окно add→amend захватывает чужой HEAD (инцидент S318: amend молча пересоздал чужой коммит; контент/сообщение сохранены, hash потерян); терминальный коммит — только `git commit -- <pathspec>`.
5. **МЕТА — только счётчик**, проверяемый грепом `^- \*\*S[0-9]`.
6. **Сжатие файла** — по решению Мастера; архив всегда = git-хэш в шапке.
