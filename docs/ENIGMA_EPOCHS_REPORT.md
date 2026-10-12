# ДОКЛАД: ВОСЕМЬ ЭПОХ ЭВОЛЮЦИИ ENIGMA И КАРТА БУДУЩЕГО

> **Документ:** Архитектурный доклад об эволюции системы
> **Версия:** Актуализировано и верифицировано кодом на V.0.5.4.3.3 (S347)
> **Дата:** 2026-10 (актуализация S348; базовая редакция — 2026-08-30, v0.5.3.9.2 / S270+)
> **Источник:** `MUTATIONS.md` (протокол v5.0, МЕТА 230), `ADR Master Index`, `00_CAUSAL_CONTRACT_v3.0.md`, `DTO Registry v9.2`, `ENIGMA_ROADMAP_v4_6.md`, `architecture/flags.yaml`, живое дерево `backend/`
> **Покрытие:** S04 → S347 (8 завершённых эпох) + дальний горизонт (Эпохи 9–13+)
> **Протокол верификации этой редакции:** живой IPT **52 passed / 0 failed (0 CRITICAL)**; батарея существования 39 артефактов (Test-Path); 17 семантических код-проверок (Select-String по владельцам законов) — все TRUE; дефолты 5 флагов сверены с `flags.yaml`; единственный писатель `sleep_onset_tick` подтверждён; канон Борко (`config/npc/chronicles/guard_borko.json`) и известный RED подтверждены. Правки против базовой редакции перечислены в §0.1.

---

## 0. КОНТЕКСТ ДОКЛАДА

ENIGMA — не игра в обычном смысле. Это **исследовательский артефакт**, развивающийся более чем 300 сессиями (S04→S347; 230 строк канонического реестра `MUTATIONS` v5.0) через **каузальную методологию**: каждое архитектурное решение фиксируется как ADR, каждый инвариант становится контрактом, каждое нарушение контракта — багом. Эволюция разбита на **эпохи** — дискретные фазы, каждая из которых навсегда изменила онтологию проекта.

Этот доклад описывает:
1. **8 завершённых эпох** (S04 → S347) с конкретными ADR, файлами и инвариантами
2. **Дальний горизонт** (Эпохи 9–13+) и оперативный мост к нему через roadmap v4.6

### 0.1. Правки против базовой редакции (с причинами)

1. **Границы Эпох 5–7** приведены к канону реестра `MUTATIONS.md` §1 (5 = S142–S217 «Санация и Великая Стена», 6 = S218–S248 «Треки», 7 = S249–S310 «Causal Slices & Living World»).
2. Добавлена **Эпоха 8 (S311–S347)**: документ-консолидация, приборы причинности (Consumer Gap), финал RE-01 (M2/D, G/H), трек AUTHORING (CCH-0…4), Understanding Engine, LLM-резилиенс (COV-2/D61–D66), двухветвевой режим v4.6.
3. Бывшие «будущие Эпохи 7–11» перенумерованы в **9–13+** (коллизия с состоявшейся Эпохой 7 устранена).
4. IPT-базлайн: 45/45 → **52/52** (живой прогон; МЕТА реестра 51/51 — устаревший дрейф, эскалирован Мастеру).
5. Док-дрейф-фиксы: «ADR-O-330» для Prophecy занят (Spatial Agency Law); ярлыки L11/L11.1 и L12.1/L12.2 выровнены по атласу; ссылки на запреты — на контракт v3.0; генерационная проекция отношений — через SSOT (L13/A-415), не `relationship_cache`; боевая математика — фактический дом `services/game/combat_math.py` (путь в атласе устарел — эскалировано).
6. Раздел «Истины» пополнен (№6 Consumer Gap, №7 разрыв словаря, №8 честность отказа — с provenance сессий).

---

# ЧАСТЬ I. ПРОШЛЫЕ ЭПОХИ (S04 → S347)

## ЭПОХА 1: КАУЗАЛЬНЫЙ ФУНДАМЕНТ (S04 — S82)

**Девиз:** «Уничтожение телепортации, централизация пространства, базовая физиология»

### Контекст

До Эпохи 1 ENIGMA была обычной RPG с sketch-архитектурой: NPC телепортировались между сценами, RPG-математика (Hit Roll, AC) определяла бой, фронтенд читал backend напрямую. Симуляция была нечестной: NPC "знали" о игроке то, чего не могли знать.

### Главные архитектурные сдвиги

#### 1.1. Уничтожение RPG-математики (ADR-015, ADR-123)

**Было:** `hit_roll = d20 + modifier; if hit_roll >= AC: damage = weapon_dice`

**Стало:** `body_state["current_hp"]` — единственный SSOT для HP. Бой идёт через `ImpactEngine`, который генерирует `PhysiologyPayload` (hp_delta, pain, shock, injuries). Смерть — через `evaluate_vital_state()`, не через `hp <= 0`.

**Создано (существование подтверждено):**
- `backend/app/domain/vital_state.py` — `evaluate_vital_state()` (:94), `is_conscious()` (:155), `is_capable()` (:230)
- `backend/app/services/combat/impact_engine.py` — физика удара
- `backend/app/services/combat/physiology_decay_handler.py` — decay боли/шока

**Инварианты:**
- **L12: Physiology & Death Lock Law** — `body_state["current_hp"]` SSOT, смерть необратима, decay для мёртвых запрещён

#### 1.2. SpatialService как единственный владелец графа (ADR-008, ADR-048)

**Стало:** `SpatialFactory.build_for_campaign()` — единственный сборщик графа. `SpatialQueryService` — единственный читатель. `TraversalState` — данные о физическом движении, отделённые от личности NPC.

**Создано:** `spatial_factory.py`, `spatial_query_service.py`, `domain/traversal.py` (все подтверждены).

**Инварианты:** **L9: Spatial SSOT & Factory Law** · **L10: Traversal FSM Law** · **SC-1..SC-8: Spatial Coherence Contract**.

#### 1.3. Dual-Time Ontology (ADR-058, ADR-059)

`game_time_seconds` — единственный авторитет; рендер-время (wall-clock) — только визуальные эффекты. Позже формализован §14 Устава (Закон Единичного Времени).

#### 1.4. DTO-контракт фронтенда (ADR-TZ03-1)

Backend = SSOT. Frontend = pure renderer. **L15: Frontend Authority Law.**

### Итоги Эпохи 1

| Метрика | Значение |
|---------|----------|
| Сессий | ~78 (S04-S82) |
| Введённых ADR | ~50 (ADR-001 до ADR-082) |
| Главных контрактов | 4 (L9, L10, L12, L15) |

**Эпоха 1 превратила ENIGMA из RPG-sketch в симуляцию с честной физикой и централизованным пространством.**

---

## ЭПОХА 2: УНИФИКАЦИЯ ПАЙПЛАЙНА И ЧИСТОТА ЯДРА (S83 — S104)

**Девиз:** «Превращение ядра в чистую функцию, изоляция LLM, детерминизм»

#### 2.1. Уничтожение ветвления player/idle (ADR-TZ08-1, TZ09-1, TZ10-1)

Ядро не знает 'player'/'dm_ctx'. `TickState` (domain/tick.py:149) — immutable snapshot; `TickMutation` (:231) — выход. `NpcTickPipeline.run()` — чистая функция. **L1: State Mutation Law** (`Phase8Result → delta_buffer → StateApplicator.apply_batch()`), **L2: Runtime Purity Law**.

#### 2.2. KernelRNG (ADR-O-301)

`KernelRNG(tick, npc_id, salt)` — детерминированный (`kernel_rng.py:43`, seed из `f"{tick}:{npc_id}:{salt}"`). `random.*` в kernel layer запрещён; `DecisionHub()` без `rng` — нарушение.

#### 2.3. L1Chronicle и эфемерность L3 (ADR-O-208, L3-P1)

L1Chronicle — append-only SQLite (`TraitDriftEvent`). L3 (`EffectiveDrives`) — эфемерная проекция, кэширование запрещено. **L17: Identity Pipeline Law.** Append-only подтверждён кодом: `INSERT INTO l1_chronicle_archive`, `DELETE FROM` отсутствует (запрет №28 держится).

#### 2.4. Epistemic Boundary (ADR-TZ08-4/6, ADR-093)

DM-agent — строгий локальный наблюдатель: только `observed_state` + `embodied_traces`. **L16: Epistemic Boundary Law.**

### Итоги Эпохи 2

~22 сессии; ~25 ADR; контракты L1, L2, L16, L17, L3-P1.

**Эпоха 2 превратила ENIGMA в детерминированную чистую функцию с эпистемически честным наблюдателем.**

---

## ЭПОХА 3: КРИСТАЛЛИЗАЦИЯ ИДЕНТИЧНОСТИ (S105 — S125)

**Девиз:** «L2.5 (Убеждения), Тройная Мембрана, физически честное движение»

#### 3.1. BeliefCrystallizationEngine и асимметричная травма (ADR-O-305/306/307)

Трёхслойная модель: L1 (факты) → L1.5 (PatternDetector — чистая статистика) → L2.5 (Belief Engine — психологические линзы). **Асимметричная травма ×6** — подтверждена кодом: `TRAUMA_MULTIPLIER: float = 6.0` (`belief_crystallization_engine.py:17`, применения :96, :130) + авторитетный тест (`SUPERBOX/causal_validation.py`). **L18: Belief Crystallization Law.**

#### 3.2. Тройная Мембрана (ADR-O-306)

Физическая / Личностная / Социальная мембраны с norm-modulated порогами фильтруют L1. **L14: Epistemic Memory Law** — память не генерирует идентичность без каузального входа.

#### 3.3. Entity Continuity (ADR-O-315/316/317/320/321)

L0 (`CoreOrientation`) неизменен; `Identity Pressure Vector` эфемерен; `life_project` — FSM. **L20: LifeProject & Agency Model Law.**

#### 3.4. Embodied Traversal (ADR-S90.1, S91, O-324, O-329)

Geometry Kernel, Z-физика, Clearance, Dynamic Doorway Routing, ETKE-IK (`DriveVector`). **L11: Spatial Agency Law** (Decision Layer не генерирует `target_node_id`) · **L11.1: Hybrid Geometry & Stigmergy Law** (микро ≠ `MovementIntent`).

#### 3.5. Combat RNG: D&D 5e (ADR-164)

`attack_roll`/`damage_roll` живут в **`services/game/combat_math.py`** (:189, :257 — подтверждено); `ImpactEngine` только потребляет (:49–79). **L12.2: D&D 5e Combat Math Law** — вычисление попадания в `impact_engine` запрещено (соблюдено).

### Итоги Эпохи 3

~21 сессия; ~15 ADR; контракты L11, L11.1, L14, L18, L20, L12.2.

**Эпоха 3 превратила ENIGMA в систему с психологически правдоподобной идентичностью и физически честным движением.**

---

## ЭПОХА 4: ПРЕЗЕНТАЦИЯ И ФИЗИКА ВОСПРИЯТИЯ (S126 — S141)

**Девиз:** «5-слойная архитектура Reality → Observable Physics → Perception, World Continuity»

#### 4.1. 5-слойная архитектура восприятия (Presentation v2.0)

Reality → Observable Physics → Embodied Traces → Perception → Phenomenology. `ManifestationDTO.tags` — НЕ эмоции (tense/rigid/trembling, не fearful/anxious); DTO живёт в `domain/snapshot.py:172` (Registry §9, подтверждено).

**Инварианты:** **L8: CFRM & Somatic Gate Law**; CAUSAL_CONTRACT v3.0, запреты №18 (телепатия в UI) и №23 (показ эмоций).

#### 4.2. World Continuity — `WorldStateDiff`/`WorldStateApplicator`, наследие мира между кампаниями.

#### 4.3. UI/UX — журнал-вкладки, Eavesdrop, mood-иконки из observables; `presentation_firewall.py` (подтверждён).

#### 4.4. Pipeline Repair — имя NPC переживает idle_tick (confidence-обновление в pre-commit).

### Итоги Эпохи 4

~16 сессий; ~10 ADR.

**Эпоха 4 сделала презентацию эпистемически честной для игрока и DM-агента.**

---

## ЭПОХА 5: САНАЦИЯ И ВЕЛИКАЯ СТЕНА (S142 — S217)

**Девиз:** «От MVP-стабилизации — через Стену исполняемых инвариантов — к эпистемическому ядру и Vertical Slice»

#### 5.1. Санация и V8.x Closure (S142-S147)
S142 (34 TODO, магические числа), S143 (Self-Healing L0-2,7), S144 (V8.3: 40+ MVP-блокеров; L1Chronicle проброшен через конвейер), S145 (Dialogue Threads; No STM = No LLM), S146 (V8.6: 17 MEDIUM/LOW), S147 (Workplace Affordance, ADR-O-326).

#### 5.2. Великая Стена (S148-S156)
**S154: CAUSAL_CONTRACT v2.0 + 11 AST-линтеров + 4 runtime-пробы** — инварианты стали исполняемыми. S148 Body Topology, S149 DriftLab v2 + PBT + Probes, S151 INV-TRAV-ZOMBIE, S152 INV-DEATH-LOCK, S155 ADR-Net, S156 Replay Core.

#### 5.3. UI-эпистемическая серия (S157-S175)
PerceivedNarrative/Manifestation DTO (S158), AuditoryDistortionPolicy (S159), UI Doctrine (S160), журнал «Наблюдения → Гипотезы → Факты» (S166), манифестации вместо эмоций (S168), «эффект незнакомца» (S169), Visual Casting (S174b/S175).

#### 5.4. Cardinality Sprint (S176-S186)
ADR-O-344..O-352: WorldTick Temporal Ownership, Pure Reducer, Entity Cardinality, Causal Ordering, Semantic Pipeline, FSM Terminality, Replay Determinism, Load Integrity; S186 Foundation Fortification.

#### 5.5. EPISTEMIC CORE — Proposition Layer (S187-S201)
**Главный онтологический сдвиг эпохи.** SUPERBOX-001 (S187) доказал слепоту к содержанию речи; SUPERBOX-002..013 построили Epistemic Core:

```text
Communication → ClaimEvent → Proposition → BeliefRevisionEngine
  → EpistemicStore → EpistemicContextResolver → DecisionHub
```

Примитивы подтверждены кодом: `Proposition`/`ClaimEvent`/`EpistemicRecord`/`EpistemicContext` (`domain/epistemology.py:76/108/123/137`). **Modifier Contract v1 (ADR-O-354/355):** аддитивность, коммутативность, изоляция. S199 Trust-Based Reliability (O-357; инлайн-провайдер удалён S206); S200-S201 Player Epistemic Closure (O-358) — подтверждено: `max(0.0)`-guard на create+update (`belief_revision_engine.py:70-86`), табу `== "player"` в подписчике отсутствует (инвертированная проверка — пусто). Arch-Sleep (S189, O-356).

#### 5.6. Stage 0/1, Ownership, Vertical Slice (S202-S217)
S209 Intent.STEAL (ADR-O-362; `_INTENT_EVENT_MAP["steal"] → EventType.THEFT` подтверждён, `intent_event_adapter.py:35`); S211 EPISTEMIC_DISPOSITIONS + ACCUSE-гейт; **S212 Stage 0+1** (Foundation Freeze, Causal Spine, Write Guards, ADR-SSOT-EPISTEMIC/ECONOMIC; DriftLab 0.0%); S213 Calibration Lab (O-361); **S214 ФИНАЛ Vertical Slice «Тень и золото»** (SUPERBOX-GORAN 12/12 — мотив→кража→свидетельство→вера→речь→вера игрока→ACCUSE→последствия, без инъекций); S215-S216 Commitment Registry + Arbitration (O-363); S217 LLM Model Manager.

### Итоги Эпохи 5

~72 сессии; ~35 ADR; артефакты: IPT-фреймворк, SUPERBOX-001..015, DriftLab, Replay, ADR-Net, Vertical Slice.

**Эпоха 5 превратила ENIGMA в самообороняющуюся систему с доказанной эпистемической причинностью и первым сквозным доказательством агентности.**

---

## ЭПОХА 6: ТРЕКИ (S218 — S248)

**Девиз:** «Домены получают владельцев: RE-01, Body, W-TRACK, AG1»

- **Stage 2A:** S219 Traversal Ownership + INTERRUPT; S223 Task/Windup/Sleep Ownership + Arbiter-INTERRUPT (O-365; `domain/tasks.py` удалён — uuid4-причина смерти).
- **RE-01:** M0 (S224, O-369: 45 узлов, 20 событий, запреты №1–35, линтер) → M1a (S228, O-370: RelationshipStateStore, single-writer) → M1b (S231/S234/S246: cutover — V2 RAM-authoritative).
- **Body 2B:** S227-S236 — Energy/Hydration/Nutrition/Fatigue (O-373), coupling-предикаты, `sleep_onset_tick` = ФАКТ (O-375; единственный писатель подтверждён: `sleep_lifecycle_service.py:71` — единственное присваивание по backend).
- **W-TRACK:** W0 (S226), W1 (S230, O-371), W3 FSM (S237, O-376), G2 (S239, O-378).
- **AG1:** Фаза A + E1/E2.0 (S238, O-377), B0-CLOSED (S243, O-379/380 — guard'ы PK/Beliefs), **BC-1** (S247, O-381: EXPERIENCE→CONCLUSION; `ConclusionStore.apply` — write-path подтверждён, `conclusion_store.py:30/56`).
- **Lab M1** (S220-S222, O-367); стабилизация: mypy --strict spatial 79→0, print()→logger 36→0.
- **Forensic:** S240-S248 (anti-writer B1.4 RED×8, дедлок LLM-роутера RE-D2, пусто-текстовые речи).

### Итоги Эпохи 6

~30 сессий; ~17 ADR; RE-01 V2 RAM-authoritative; BC-1 dormant (подтверждено: `BC1_ENABLED default ""` = OFF, ROLLOUT-PENDING).

**Эпоха 6 превратила домены в треки с владельцами, контрактами и tombstone-онтологией.**

---

## ЭПОХА 7: CAUSAL SLICES & LIVING WORLD (S249 — S310)

**Девиз:** «Причинные срезы, железная река детерминизма, живой мир и CognitionContext»

- **State Consumer Gap (S249-S250):** GC-09A GREEN + Embodied Constraint RED («state exists ≠ state has consequence») → ADR-O-383 pressure_translator за сессию. Паттерн «RED = находка» стал каноном.
- **Речевой/социальный контур (S253-S259):** O-385/387/389/390/392; PlayerSpeechClaim (S255); WORK Vertical Slice (S256, O-391).
- **IRON RIVER (S260-S261):** 4 P0-брейкера; детерминизм причинного контура **кросс-процессный** (A/B 3×MATCH). S269: DriftLab → научный инструмент, Epoch seal 10k×2 MATCH.
- **CAUSAL SLICES R5-R8:** `DesiredChange` — причинно определённое изменение ДО выбора способа. REASON-каскад подтверждён кодом: `REASON_THREAT/NEED/BELIEF/AFFECTION/EXPRESSION/GRIEVANCE` (`desired_change.py:29-34`); R5 (S262, O-394), R6 (S263, O-395), R7 grievance (S265, O-397), R8 affection (S303, O-413 — production-проб orm→lusya←care).
- **TEMPORAL EPOCH и поток (S266-S274):** карта+ядро+PR, FIX EAT (S267 — полная каузальная цепь в multi-location), WorldView в TickState (S268), Worker Effect Outbox (S270, O-399), WATERMARK PatternDetector (S274, O-400: p95 230.6→154.9).
- **Living World:** SLEEP VERTICAL SLICE (S271 — NEED→SATISFACTION), Exploration Phase D (S282), S2B.7 Pain/Injury (S309), G3 EXECUTION (S307, O-410), TRADE β (S310, O-412).
- **De-god + UI Workbench + семантический контракт:** O-401/402/403; Event Identity (S283, ADR-404); Journal→Presentation (S286), SemanticSpan/DM_NARRATED (S287), Claim Bridge (S288), Investigation Board (S290); **CognitionContext v0** (S294-S296 — внимание→обнаружение→наблюдаемое поведение; DriftLab 200т: drift A–E = 0.0000%); Name-Gate (S306/S308, O-409); UI Workbench (F12, энд-скрин).

### Итоги Эпохи 7

~55 сессий; ~30 ADR.

**Эпоха 7 доказала: причинные срезы (угроза, голод, обида, привязанность) проводят последствия до наблюдаемого поведения, и детерминизм держит железную реку.**

---

## ЭПОХА 8: КОНСОЛИДАЦИЯ, RE-01 ФИНАЛ, AUTHORING И UNDERSTANDING (S311 — S347)

**Девиз:** «Один факт — одно место; причинность доказывается приборами; личность компилируется из авторского текста; система честно деградирует»

### 8.1. Документ-консолидация (S311, S323)
MUTATIONS v5.0 (2383→249, one-liner), roadmap v4.0 (3389→1277), атлас v8.0 (814→712), ADR-Net parser-fix (граф 281→285), 62 IMPACT-шапки; самоочистка TZ-корпуса (протокол §1.3).

### 8.2. Приборы причинности (S314-S322)
- **F5-лаборатория (S314):** microscope над production (ExperimentRunner → build_game_loop → idle_tick; temp-saves + MockProvider + ObservabilityTap; рычаг `npc_overrides.social` — canonical WriteGate).
- **INV-CONSUMER-GAP (S317, ADR-O-414):** `lint_consumer_gap` (census 174+24), debt-реестр, `causality_manifest` (`KNOWN_ORGANS` подтверждён, `causality_manifest.py:25`) 198→291 полей; урожай 180→31.
- **RE-01 M1b.3.5–3.7 (S314-S319):** GAP-1 (1A prod-proven / 1B unit-proven / 1C NOT BUILT), RE-D8 закрыт, греп-страж allowlist (O-415: 19 файлов / 52 сайта).
- **GC-11 (S320, O-416):** event→V2-RAM ДОКАЗАНО живьём при поведенческом НУЛЕ — RE-D2-класс (Dual-Reader Divergence / Threshold Inertia / Silent-World).
- **PerturbationHarness (S321):** проводимость state→reader доказывается инъекцией (fatigue/energy/trust).
- **M1b.5 (S322, O-417):** `npc_state_helpers` удалён целиком; legacy store НЕ прод-SSOT; fail-loud `ContractValidationError`.
- **Долговая линия:** ADR-O-R2 (feasibility-контракт оживлён), mypy strict 13→0, ruff 244→0.

### 8.3. RE-01 финал контура (S326, S329)
- **M2/D (S326, O-418):** первый живой needs-writer — `RelationshipEventSemantics` (dormant; флаг подтверждён: `RELATIONSHIP_EVENTS_ENABLED default ""` ROLLOUT-PENDING), `DeltaDomain.RELATIONSHIP`, `NeedDeltaPayload`, сплит Фаза 9/10, `apply_relationship_deltas` с Cause.
- **G/H (S329, O-419):** время→потребность (gen_rate; флаг `RELATIONSHIP_DYNAMICS_ENABLED` dormant — подтверждён), событие→потребность (волна Фр2 = дельта), SLEEP→WAKE (no-op без утверждённых форм); pure-readout Ф1/Ф3/Ф4/С5.
- Далее: **K (removal-test) → Полигон M**.

### 8.4. Детерминизм инференса (S313, S316)
RCA non-reproducible inference → тёплый протокол ([DET-ENV]/[DET-TRACE]; warm 90/90); **few-shot удалён из production** (RC8 A/B); det-check — постоянный протокол (RED → semantic experiment STOP).

### 8.5. AUTHORING: Character Chronicle (S331-S347)
**Слой 0 канонического порядка:** авторский текст → декомпозиция → машинная хроника → валидированный seed ДО первого тика (LLM — декомпозитор, Python — валидатор и писатель; INV-LLM-NOT-SSOT).
- **CCH-0 (S331, O-420):** контракт AUTHORING COMPILER; WhiteSpot первоклассен (writer-guard); два времени (historical_age ≠ learned_age).
- **CCH-1 (S332):** 6 DTO подтверждены кодом (`domain/chronicle.py`: ChronicleDocument :295, ChronicleEntry :210, WhiteSpot :192, KnowledgeLink :237, BiographyDecomposition :283, ClarificationQuestion :174); T-CCH-01 GREEN (Люся 5/5).
- **CCH-2 (S335):** декомпозитор (FACT_EXTRACTION temp=0, KernelRNG-seed), нормализатор fail-loud ×6 + мембрана vague-relation; T-CCH-02 GREEN 6/0 на живом Q4_K_M.
- **CCH-2.5 (S336, O-422):** Chronicle Consistency — трёхуровневый сверщик; финал склейки/конфликтов — всегда автор.
- **CCH-3 (S337-S340):** редактор UI MVP («Принять как канон», Save = Contract; главное меню + F7).
- **CCH-4 (S341→S347):** сеялка + Character Debugger (гейты T-CCH-05..08 подтверждены: `tests/micro/test_chronicle_cch4_seed.py`); S345 — gap-detector live, **LIVE MAP 134 gaps / 134 words / 6 NPC**; S347 — реестр-строка, МЕТА 230. Канон на диске: `config/npc/chronicles/guard_borko.json` (13 072 б) — источник известного RED `test_p2_provenance_origin_vs_seeded` (`tests/gameplay/test_p2_canon_sync.py`; вердикт Мастера: файл как есть, владелец CCH-4 дорабатывает гейт).
- Далее: **CCH-5** (экспорт-проекции) → CCH-6 (калибровка).

### 8.6. Loop Closure — начало (S334, O-421 + O-421a)
LC-IMPL-1: **IdleEventProjection** (`@dataclass(frozen=True)` подтверждён, `idle_projection.py:19-20`) — наблюдаемая проекция idle-событий `{cause, target, value}`; v1-словарь {ACTIVITY_OUTCOME, THEFT}; флаг подтверждён: `IDLE_EVENTS_PROJECTION_ENABLED default "1"` ROLLOUT-ON; строго read-only (замок K2). Диф-тест «мир молчит → мир говорит» GREEN 3/3.

### 8.7. Understanding Engine и честная деградация (S-SUE серия, S343-S347, ADR-O-424)
- **UX-UE-01 / D4 (ADR-O-424):** fail-closed readiness-гейт авторитетных путей — не-RESOLVED player-вмешательство не диспетчеризуется (единая точка `_phase_1_input_merge` до ветвления); L1-гейт attack/damage-дрейта (утечка подтверждена живьём: «Не бей Торнина» фиксировал несостоявшуюся атаку).
- **S-UE-fix3:** контракт гейта приведён к факту интерпретации — **неразобранная негация закрывает исполнение ORDER-актов** (корневой диагноз: `_content_words` len>2-фильтр отрезал частицу «не»; фикс — параметр `keep_short`); позитивные приказы не блокируются; LLM `negated=False` — мост. Языковая граница Qwen2.5-7B (negated не распознаётся тремя путями) зафиксирована честно — не объявлена решённой.
- **COV-2 / D61-D66:** детектор отказа (`pool_backoff_status` + `/llm/outage`), настоящий рестарт llama-server (kill по PID, поллинг /health, сброс backoff), per-call таймаут рестарта 30с→180с, приоритетная очередь worker, wall-time watchdog, **доктрина обязательной LLM** (модалка двух выборов, гейты кадра ×4).
- **UX-FB:** честная деградация LLM-хода — внешний `dialogue_log`, RCE-гейт (фоллбэк не реплика NPC: без атрибуции имени, без STM-загрязнения), оба пути деградации флагаются.
- **S343:** восстановление утраченной записи ENIGMA_PROV_B реестра (флаг-контур COV).

### 8.8. Двухветвевой режим v4.6
**Ветвь А «Субъект»** (memory / epistemics / verbalization / chronicle / RE / Body) и **Ветвь Б «Мир и платформа»** (ядро тика / spatial / LLM-контур / frontend / релиз): лестницы А1–А10 и Б1–Б10, гейты стыковки S1–S7 (артефактная передача), Anti-Race Protocol.

### Итоги Эпохи 8

| Метрика | Значение |
|---------|----------|
| Сессий | ~30 (S311-S347, с ренумберами S316/S318/S326/S337–S339/S341–S342) |
| Введённых ADR | O-414..O-424 (включая O-421a, O-423; диапазон подтверждён живым грепом) |
| Ключевых приборов | F5-лаборатория, lint_consumer_gap + causality_manifest, PerturbationHarness, det-check |
| Ключевой статус | **IPT 52/52 (0 CRITICAL)**; ruff 0; mypy 0 (3 CI-режима); micro 326/326; pytest 2413 passed / 33 skipped / 7 xfailed + 1 известный RED (вердикт Мастера); МЕТА 230; RE-01 до G/H; CCH-0..4; LC-IMPL-1 |

**Эпоха 8 сделала методологию самостоятельным предметом инженерии: причинность доказывается приборами, знание консолидируется по правилу «один факт — одно место», личность компилируется из авторского текста, а отказ LLM — честен и наблюдаем.**

---

### Общий итог 8 эпох

| # | Главная тема | Главный сдвиг |
|---|--------------|---------------|
| 1 | Каузальный фундамент | Уничтожение телепортации, централизация пространства |
| 2 | Чистота ядра | TickState → TickMutation, KernelRNG, L1Chronicle |
| 3 | Идентичность | BeliefCrystallization (×6 подтверждён), Triple Membrane, Embodied Traversal |
| 4 | Восприятие | 5-layer Reality → Perception, World Continuity |
| 5 | Великая Стена + Epistemic Core | Исполняемые инварианты, Proposition Layer, Vertical Slice «Тень и золото» |
| 6 | Треки | Владельцы доменов: RE-01, Body 2B, W-TRACK, AG1 (BC-1) |
| 7 | Causal Slices & Living World | R5-R8, IRON RIVER, TEMPORAL EPOCH, CognitionContext, De-god, G3 |
| 8 | Консолидация + AUTHORING + Understanding | Consumer Gap приборы, RE-01 финал, CCH-0..4, ADR-O-424, LLM-резилиенс, Two-Branch v4.6 |

**Текущее состояние (V.0.5.4.3.3, S347):** IPT 52/52, ruff 0, mypy 0, micro 326/326. RE-01: следующий шаг K → Полигон M. AG1: BC-1 dormant, следующий шаг BC-2. CCH: следующий шаг CCH-5. LC: LC-IMPL-1 закрыта, далее LC-IMPL-2/3. Режим — двухветвевой v4.6. Каноническая очередь — roadmap §0.2.

---

# ЧАСТЬ II. ДАЛЬНИЙ ГОРИЗОНТ (v7.5 → v13.0+)

## КОНТЕКСТ ПРОЕКТИРОВАНИЯ

Видение: игра-симулятор эффекта бабочки (девушка выбирает из 3 парней); игрок как 4-й кандидат — Prophecy System; рождение/смерть и смена поколений; 20-30 живых NPC, фракции, экономика.

**Оперативный мост (v4.6):** ближайшее будущее определяется канонической очередью roadmap §0.2 в двухветвевом режиме (Ветвь А: CCH-5/6, RE K→M, BC-2..BC-7, NL-01, MEM; Ветвь Б: COV-0..11, LC-IMPL-2/3, GC-спринт). Примитивы Эпохи 9 уже существуют: эпистемическая агентность доказана Vertical Slice (S214), ACCUSE-гейт и PlayerSpeechClaim — готовые точки входа Prophecy.

## ЭПОХА 9: VERTICAL SLICE И PROPHECY SYSTEM (v7.5 — v8.0)
Vertical Slice «Люся и 3 парня» (многомерные отношения, L2.5-интеграция, FSM `CHOOSING_PARTNER`). **Prophecy System:** игрок **утверждает** будущее → `PROPHECY` InterventionEvent → belief кристаллизуется в L2.5 → confirmation bias → ×6 trauma multiplier → уход от партнёра без реального предательства. **Новый ADR: Prophecy Causality Law** (номер — по Anti-Race Protocol; O-330 из базовой редакции занят — Spatial Agency Law).

## ЭПОХА 10: WORLD CHRONICLE И ГЕНЕРАЦИОННАЯ ГЛУБИНА (v8.5 — v9.0)
WorldChronicle (append-only SQLite; Birth & Death → Aging → Lineage & Succession → Integration). Наследование: 0.5× CrystallizedBelief родителя; унаследованные связи — **через SSOT-хранение отношений** (RelationshipStore / RelationshipStateStore; персистенция `relationship_cache` запрещена L13 / ADR-O-415). Memetic Domain (Bass diffusion, player-created memes). Кровная месть через `family_chronicle`.

## ЭПОХА 11: ПОЛНОЦЕННОЕ ОБЩЕСТВО (v9.5)
Фракции как first-class entities; экономика как driver поведения; политика (законы через memetic adoption). Crusader Kings 3 level с LLM и эпистемической честностью.

## ЭПОХА 12: §18 — РЕСУРСНО-ОГРАНИЧЕННЫЙ ЭПИСТЕМИЧЕСКИЙ ВЫБОР (v10.0+)

```text
U_M(m, c) = I(m, c) · R(m) · U(c) − C(m, c);  активация: U_M > 0
```

Bounded rationality (Simon/Kahneman) для NPC. **Пререквизиты (актуально на S347):** BC-2…BC-7 (лестница А3) + MEM-8. TZ §18 «ВНЕДРЯТЬ НЕЛЬЗЯ» снимается только после завершения Belief Layer.

## ЭПОХА 13+: НЕОГРАНИЧЕННАЯ ЭВОЛЮЦИЯ (v11.0+)
LLM Pipeline v2 (constrained generation, semantic cache); Female-Targeted Dark Fantasy Layer (6 доменов); AWC Process/World Model; Map Editor Smart Validation; Textures & Geometry.

---

# ЧАСТЬ III. КАРТА ЭПОХ

| Эпоха | Версия | Сессии | Главная тема | Главный артефакт |
|-------|--------|--------|--------------|------------------|
| 1 | v0.x | S04-S82 | Каузальный фундамент | SpatialService, body_state, Dual-Time |
| 2 | v0.5.x | S83-S104 | Чистота ядра | TickState/TickMutation, KernelRNG, L1Chronicle |
| 3 | v0.5.3.x | S105-S125 | Идентичность | BeliefCrystallization, Triple Membrane, Embodied Traversal |
| 4 | v0.5.3.x | S126-S141 | Восприятие | 5-layer Reality→Perception, World Continuity |
| 5 | v0.5.3.x | S142-S217 | Великая Стена + Epistemic Core | CAUSAL_CONTRACT v2.0, Modifier Contract, Vertical Slice |
| 6 | v0.5.3.7.x | S218-S248 | Треки | RE-01 M0–M1b, Body 2B, W-TRACK, AG1/BC-1 |
| 7 | v0.5.3.8–9.x | S249-S310 | Causal Slices & Living World | IRON RIVER, R5-R8, CognitionContext, G3 |
| 8 | v0.5.4.x | S311-S347 | Консолидация + AUTHORING + Understanding | INV-CONSUMER-GAP, RE-01 финал, CCH-0..4, ADR-O-424, Two-Branch v4.6 |
| 9 | v7.5-v8.0 | — | Vertical Slice + Prophecy | player-as-prophet |
| 10 | v8.5-v9.0 | — | Генерационная глубина | WorldChronicle, Memetic, Lineage |
| 11 | v9.5 | — | Полноценное общество | Factions, Economy, Politics |
| 12 | v10.0+ | — | §18 Epistemic Selection | Bounded rationality |
| 13+ | v11.0+ | — | Неограниченная эволюция | LLM Pipeline v2, ... |

Граф зависимостей: 1→2→3→4→5→6→7→8→9(Prophecy)→10(Generations)→11(Society)→12(§18, требует завершённый Belief Layer BC-2..BC-7).

---

# ЧАСТЬ IV. ИЗВЛЕЧЁННЫЕ АРХИТЕКТУРНЫЕ ИСТИНЫ

После 300+ сессий (230 строк канонического реестра) система эмпирически пришла к **8 непреложным фактам**:

1. **Истина = Snapshot + Chronicle.** State эфемерен, identity — append-only история (L1Chronicle). Каждое состояние — проекция истории.
2. **Время и Физика — одно целое.** «Обновить позицию» отдельно от «обновления времени» — один акт, не два.
3. **Нет Event Sourcing для State (но есть для Identity).** State перезаписывается; identity event-sourced. Асимметрия: state мимолётен, identity вечен.
4. **Симптом не является причиной.** Фикс — на ПЕРВЫЙ отказавший узел pipeline. UI — симптом.
5. **Вакуум — это локальный разрыв.** Unknown ≠ Neutral(0.0) (§ENIGMA-003/004).
6. **Существование состояния ≠ наличие последствия** ⭐ Эпоха 8. GC-09B (S249), GC-11 (S320: событие→хранилище живо, поведение нулевое), RE-D9 (S318), D-MOM (S328). Ответ — INV-CONSUMER-GAP (O-414) + PerturbationHarness: проводимость state→reader доказывается прибором.
7. **Самая частая причина мёртвых контуров — разрыв словаря** ⭐ Эпоха 8. S238: 7 разрывов за сессию. Ответ: ключи-константы (§12.1), census-манифест, fail-loud.
8. **Честность отказа** ⭐ Эпоха 8. Деградация LLM наблюдаема и не маскируется под реплику NPC (UX-FB RCE-гейт, D61 доктрина обязательной LLM, внешний dialogue_log). Система, которая не может говорить, обязана сказать об этом честно — а не галлюцинировать.

---

# ЧАСТЬ V. ФИЛОСОФСКИЙ ИТОГ

## Что построено за 8 эпох

1. **Каузальная честность** — каждое изменение имеет причину (Invariant I)
2. **Историческая честность** — будущее считается из прошлого (Invariant II)
3. **Временная изоляция** — шаг неизменяем во время вычисления (Invariant III)
4. **Семантическая валидность** — невозможное состояние отвергается (Invariant IV)
5. **Эпистемическая честность** — никто не знает больше, чем должен (Triple Membrane, Epistemic Core)
6. **Идентификационная честность** — личность — это история (L1Chronicle)
7. **Восприятийная честность** — наблюдатель видит проявления (5-layer)
8. **Инструментальная честность** ⭐ — причинность доказывается приборами (Consumer Gap, PerturbationHarness, RED=находка)
9. **Честность происхождения** ⭐ — личность компилируется из авторского текста с provenance (CCH, Слой 0)
10. **Честность отказа** ⭐ — деградация наблюдаема, не маскируется (UX-FB, D61)

## Главная идея

**ENIGMA — это не продукт, это исследование.** Каждая эпоха — ответ на вопрос «можно ли честно симулировать X?». После 8 эпох: физика, детерминизм, идентичность, восприятие, исполнимость собственных законов, владение доменами, причинные срезы, методология доказательства, происхождение личности и честный отказ — да, можно.

Versu закрылся. Façade — academic demo. Prom Week — paper. NVIDIA ACE — middleware без игры. AI Dungeon — без инвариантов. У ENIGMA есть шанс занять **пустующее место**.

---

# ФИНАЛ

8 эпох пройдено. Эпоха 1 моделирует пространство. 2 — детерминизм. 3 — идентичность. 4 — восприятие. 5 — исполнимость собственных законов + эпистемическую причинность. 6 — владение. 7 — причинные срезы и живой мир. 8 — саму методологию доказательства, происхождение личности и честный отказ. Эпоха 9 моделирует будущее (Prophecy). 10 — поколения. 11 — общество. 12 — ограниченный разум.

Это **постепенное онтологическое расширение** — углубление модели реальности. И в этом — уникальность ENIGMA.

---

*Доклад актуализирован на S348 по канону `MUTATIONS.md` v5.0 (МЕТА 230), `ADR Master Index`, `00_CAUSAL_CONTRACT_v3.0.md`, `DTO Registry v9.2`, `architecture/flags.yaml` и живому дереву `backend/`. Верификация: живой IPT 52/52 (0 CRITICAL); батарея существования 39 артефактов; 17 семантических код-проверок — все TRUE (TRAUMA_MULTIPLIER=6.0, max(0.0)-guard, отсутствие player-continue, INSERT без DELETE, single-writer sleep_onset_tick, frozen IdleEventProjection, 6 DTO CCH, 6 REASON-констант, дефолты 5 флагов). Базовая редакция (v0.5.3.9.2, S270+) — в git-истории.*
