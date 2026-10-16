# EPI-AUDIT-01 — Рой-аудит и перестройка дорожной карты эпистемики (Жизненный цикл информации)

**Дата:** 2026-10-16 · **Версия кода:** V.0.5.4.3.7 · **Режим:** read-only аудит + документация; производственный код, тесты, конфигурация и игровые данные не менялись.
**Основание:** задание «ENIGMA — аудит и перестройка дорожной карты эпистемики v4.7+» (пять направлений: Epistemic Actions/Verification Loop · Material Epistemics · Common Ground · Epistemic Climate · Information Logistics/NPC Relay).
**Результат в roadmap:** `docs/ENIGMA_ROADMAP_v4_7.md` — трек EPI §19 (v4.8-draft), Ступень EPI §0.2, §0.1e, находки §7.11 (EPI-D1…D14), §8.AC, гейты §9.3g (EPI-GC-01…09), §11.4, §R.7.
**Метод:** 4 параллельных агента-аудитора (EPI-A эпистемическое ядро; EPI-B решение/обязательства/предметы/персистентность; EPI-C восприятие/коммуникации/социальные события; EPI-D документация и отложенные направления) + выборочная ручная верификация ключевых фактов (EpistemicStore, BeliefRevisionEngine, CommitmentRegistry, BC1_ENABLED=OFF, табу TESTIMONY, flags.yaml, `interaction_history_ref`, отсутствие READ-action).

---

## 7.1. Вердикт аудита: что существует, что работает сквозным образом

### 7.1.1. Статусы архитектурных оснований

| Основание | Статус | Доказательства (файлы/тесты) |
|---|---|---|
| World Truth (канон секретов) | Реализовано + сквозной тест (в скоупе MVP-секретов, не «полная история мира») | `backend/app/models/truth_state.py` (TruthState/Secret/TruthRelation, CONTRADICTS-тип), `services/truth_state_loader.py`, `config/canon/truth_state_tavern.json` (17 секретов/20 связей), `tests/test_p7_01_truth_state.py` |
| Восприятие NPC (видимость/слух/ограничения) | Реализовано (несколько мембран; известная гетерогенность — DEBT-R1) | `services/npc/perception_filter.py` (`_can_see`/`_can_hear`/`calculate_clarity`), `services/spatial/spatial_runtime.py` (LOS-базы, sound_reach), `models/npc_state.py:580-660` (PerceptualKernel.can_observe), `domain/communication.py` (SSOT `exposure_radius`); тесты `test_perception_filter`, `test_perception_witness`, `epistemic_membrane_hardening_test` |
| Наблюдение/свидетельства игрока (ObservationLog, EvidenceLink) | Реализовано частично | `models/observation.py` (Observation/EvidencePolarity/EvidenceLink), `services/player_cognition/observation_log.py`; продюсеры только `action_consequence_compiler.py:152/190` и `npc_confession_parser.py:102`; CONTRADICTS не производится (COV-D40); продюсеров visual_cue/eavesdrop нет (T9/AUD-D10 открыт); RAM-only (COV-D41) |
| PlayerBeliefModel / PlayerEpistemicState | Реализовано + юнит-тесты (RAM-only, подключено к MVP-петле) | `models/player_belief.py`, `services/player_cognition/player_belief_model.py` (идемпотентность по (obs_id, secret_id, polarity), порог ±0.8), `models/player_epistemic_state.py` + `domain/player_epistemics.py` («DISCOVERY IS DELIVERY», монополия DiscoveryBridge); `tests/test_p7_03_player_belief_model.py`, SUPERBOX `epistemic_player_belief_test`, IPT `INV-PLAYER-EPISTEMIC-CLOSURE` |
| EpistemicStore (NPC-убеждения-пропозиции с provenance) | Реализовано + сквозной тест | `services/npc/epistemic_store.py` (EpistemicRecord: Proposition/polarity/confidence/source_id/source_claim_id), проводка `game_loop.py::_register_epistemic_core`, round-trip `scene_state["epistemic_records"]` (`tick_orchestrator.py:780`, restore `game_loop.py:559-562, :1339`); SUPERBOX `epistemic_core/eventbus/persistence/observation/membrane_hardening/second_order` (~25 сценариев) |
| Belief Revision | Реализовано частично | `services/npc/belief_revision_engine.py` (reliability через TrustBasedReliabilityProvider — враг <−30 → отрицательная reliability; same-source boost 0.2; direct_observation 0.9); конфликт пропозиций решается только весом источника; `services/memory/contradiction_resolver.py` мёртв (0 прод-вызовов — MEM-D20 P0); 5 носителей убеждений без арбитра |
| BC-1 Conclusion Layer | Реализовано, dormant (BC1_ENABLED default OFF) | `domain/conclusions.py` (триплет+confidence+evidence[event_ids]+source; TESTIMONY зарезервирован за BC-5), `services/memory/{conclusion_engine,conclusion_gate,conclusion_runtime}.py`, `services/npc/conclusion_store.py` (ценз `_APPLY_ALLOWED_WRITERS`); `tests/sandbox/SUPERBOX/scenarios/bc1_conclusion_test.py` 6/6 (A/B NO-VACUUM/C/D/E round-trip/OFF dormant) |
| Expectation (BC-2) | Не найдено (захоронено; BC-2 открыт) | ExpectationStore удалён (COV-D100, коммит 450931cd); могильники `state_applicator.py:789`, `npc_tick_pipeline.py:459-462`; мост CONCLUSION→EXPECTATION закрыт ADR-O-381 F3а до Ступени 4 |
| DecisionHub | Реализовано (score-аргументация, ~15 интентов; outcome-резолюция оборвана) | `services/npc/decision_hub.py` (~2065 строк; scores_trace, expected_success), эпистемические входы `epistemic_modifiers` (`npc_tick_pipeline.py:583-600`); `ResolutionEngine` не вызывается (`npc_tick_pipeline.py:1200` TODO Фаза 2); тесты `test_decision_hub_goal_boost`, SUPERBOX `epistemic_decision_*` |
| CommitmentRegistry | Реализовано + сквозной тест (ROLLOUT-ON); арбитр enforcement — OFF | `domain/action_commitment.py` (FSM 9 состояний, детерминированные id), `services/action/commitment_registry.py` (единственный писатель scene_state, зеркала задач `mirror_task_*`), арбитр `commitment_arbiter.py` (COMMIT/CONTINUE/REJECT/INTERRUPT; ARBITER_ENFORCEMENT default OFF); `tests/test_action_commitment.py` (~60), `test_commitment_ssm_integration.py` |
| Decision → Action → событие | Реализовано (вербальные/movement/attack); объектная ветка за флагом W3_G3 | `npc_tick_pipeline.py` (CommunicationIntent/StateDeltas), `phases/post_decision.py` (tasks/windup), `phases/...windup...` → `g3_executor.py` (W3_G3_ENABLED OFF), EventCompiler (shadow, EquivalenceValidator); GC-00 (`test_tavern_vertical.py` 100 тиков), `test_tick_orchestrator_full_loop_player_attacks`, `test_f1_trade_materialization` |
| WorldObjectStore | Реализовано (топология/FSM/ценз Г4); история владения — частично (указатель без ledger) | `services/world/world_object_store.py` (7 отношений, CarrierMode, `_ALLOWED_WRITERS`), `domain/world_object.py:128` (`interaction_history_ref` — ref, не ledger), `domain/object_fsms.py` (PASS/NO_OP/REJECT); `test_world_object_topology` (~40), `test_object_fsms` (~30) |
| Предметы-носители текста / READ | Не найдено | grep document/note/letter/readable/READ по `backend/app` — 0 механик; реестр архетипов спавнера без text-bearing; `WorldActionType` без READ |
| Сериализация/сохранение | Реализовано + сквозной тест (эпистемика NPC персистентна; MVP-эпистемика игрока — нет) | `services/scene_state_manager.py`, `services/state/*` (PersistencePort, SQLite-адаптер, MigrationRunner ADR-O-426), `tests/pbt/properties/test_npc_state_roundtrip.py` (PBT 200), SUPERBOX `epistemic_persistence_test`, `test_phase_a_memory_fixes.py::test_beliefs_round_trip_full_cycle`; COV-D41 (RAM-only MVP-петли) подтверждён |
| Пространственные запросы | Реализовано + сквозной тест | `spatial_runtime.py` (euclidean/LOS/sound_reach/extract_scene_for_npc), `spatial_query_service.py` (инжекция в TickState/DecisionHub); `test_spatial_runtime_r4`, PBT `test_spatial_coherence` |
| Социальные события / подписчики | Реализовано | `services/events/event_bus.py` (Event Identity, DLQ), подписчики `reaction_subscriber` (DeltaGate/TRACE-ONCE), `social_subscriber`, `npc_dialogue_subscriber`, `claim_event_subscriber`, `player_speech_act_subscriber`, `observation_subscriber`; Phase8-протокол; `test_reaction_subscriber`, `test_claim_bridge_chain` (пента-равенство provenance) |
| Подслушивание | Реализовано (игрок: журнал/DiscoveryBridge; NPC: claims всем в радиусе) | `test_p6_e2_eavesdrop_channel.py`, `test_recognition_and_eavesdrop.py`, `test_speech_exposure.py` (parity игрок/NPC); NPC-сторона — только пропозиции, STM/отношения третьих лиц не пишутся |
| Слухи / распространение | Частично | `services/social/social_engine.py::propagate` (BFS, hop-decay, искажение по доверию, freq cap) — переносятся event-тип/интенсивность, не Proposition; continuity_note выбрасывается (COV-D39); claims — 1 хоп; SPREAD_RUMOR без полного потребителя; `test_social_engine`, `test_rumor_mutation` |
| Trust (диадический) | Реализовано + сквозной тест | V2-RAM `v2_relationship_backend.py` (±100, write-gate), `trust_based_reliability_provider.py`, GC-11 (`test_gc11_relationship_causality.py`, комплимент → ненулевой V2-RAM + сдвиг intent); SUPERBOX `epistemic_observation_test` T5 |
| Секреты (MVP-петля) | Реализовано + сквозной тест | initial_holders → EventMemory(is_secret) → `knowledge_retrieval.py` → disclosure-лестница (`disclosure_decision.py`) → DiscoveryBridge (R1-монополия `mark_discovered`); серии `test_p1…test_p7`, `test_mvp_tavern_integration`, `test_discovery_mechanics` |
| Common Ground / совместное знание | Не найдено | witness-наборы эфемерны (один тик внутри подписчиков); «A знает, что B знает P» не хранится и не выводится; `test_mutual_attention` — сигнал внимания, не знание |
| Relay / поручения / доставка | Не найдено | OFFER_JOB — вербальный интент-реплика; work_orders — двусторонняя сделка в одной сцене; делегирования задач нет; offscreen-канал отключён (WorldProjectionBuffer VERDICT=OFF, ADR-O-309) |
| Epistemic Climate (групповое доверие) | Не найдено | trust диадический; `faction_alignment_tracker` write-only (COV-D50); `SocialFabricTracker` baseline обнулён (COV-D51); reputation RAM без потребителя; BFS слухов без групповых границ |
| Отложенные направления (information-seeking) | Запланировано | §8.K6 «Information-seeking as an action» (одна строка, без дизайна); §8.J2 `U_M = I·R·U − C` (Эп.10; ТЗ §18-EKS: «ВНЕДРЯТЬ НЕЛЬЗЯ до PC-1…18»); §8.D1–D9; AWC KnowledgeSource/`get_unverified_entries()` (CT-02, реверификация обязательна) |

### 7.1.2. Карта действующих связей (Этап A3)

**Работает сквозным образом (доказано тестами):**

```
событие в мире (EventDTO/EventBus)
  → доступность информации (мембраны: perception_filter — свет/LOS/шум; can_observe; exposure_radius)
  → восприятие конкретным НПС (claim_event_subscriber — речь; observation_subscriber — THEFT/ATTACKED/EXITS)
  → свидетельство (ClaimEvent/Proposition с provenance; BeliefRevisionEngine + TrustBasedReliabilityProvider)
  → убеждение (EpistemicStore per-agent; round-trip scene_state)
  → выбор действия (EpistemicContextResolver → epistemic_modifiers → DecisionHub, ~15 интентов)
  → исполнение (commitment/task/windup → dialogue_executor / movement / G3)
  → новое событие в мире (EventBus/EventCompiler-shadow/L1Chronicle)
```

**Параллельный контур переживания (частично работает, спит на хвосте):** реакция свидетелей (Фаза 8, ReactionSubscriber) → StateDeltaProposal → DeltaGate (whitelist/клампы/идемпотентность) → `EXPERIENCE_DELTA_COMMITTED` → Фаза 9 → ConclusionEngine → ConclusionGate → ConclusionStore (BC-1, **default OFF**) → `CONCLUSION_FORMED`. Дальше разрыв: ExpectationStore захоронен, BC-2…BC-7 открыты.

**Параллельная MVP-петля игрока (детектив):** действие/диалог/подслушивание → ActionConsequenceCompiler/NpcConfessionParser → ObservationLog + EvidenceLink → PlayerBeliefModel; DiscoveryBridge → PlayerEpistemicState (0/1/2) + TruthState.mark_discovered (R1-монополия). RAM-only (COV-D41), без CONTRADICTS (COV-D40).

**Разорвано/отсутствует (переходы, которых нет):**
- «исход действия → коррекция убеждения» — ResolutionEngine вне пайплайна (EPI-D3);
- «противоречивые свидетельства → ревизия вниз» — CONTRADICTS не производится (EPI-D5), contradiction_resolver мёртв (EPI-D4);
- «передача сведений через посредника» — 1 хоп максимум (EPI-D8);
- «предмет/документ как источник свидетельства» — носителей и READ нет (EPI-D7);
- «совместное наблюдение → общее знание/тайна/утечка» — witness-наборы эфемерны (EPI-D9);
- «групповой опыт → фон доверия» — только диада (EPI-D10);
- «проверка собственного убеждения действием» — нет триггера и действия (реальный разрыв всех пяти направлений).

**Ответ на диагностический вопрос:** главный дефицит ENIGMA — не базовые сущности (эпистемическая машина богатая) и не хранилища (сторы есть и в основном с гардами), а (1) недоказанная интеграция существующих компонентов (dormant-флаги, рельсы без продюсеров/потребителей, захороненный Expectation, оборванный outcome) и (2) отсутствующие механизмы физического движения информации (носители, маршруты, общая экспозиция, групповой фон). Три проблемы не эквивалентны.

## 7.2. Таблица пяти направлений

| Поле | Verification Loop | Material Epistemics | Information Logistics | Common Ground | Epistemic Climate |
|---|---|---|---|---|---|
| **Текущее состояние** | Отсутствует целиком; субстрат есть (claim-канал, confidence/provenance, эпистемические модификаторы решения); BC-1 dormant, BC-2 открыт | Отсутствует целиком; WorldObjectStore/FSM/ценз + L1Chronicle + EvidenceLink(MVP) + knowledge_retrieval готовы | Отсутствует целиком; CommitmentRegistry (ON), claim-доставка, eavesdrop-перехват, clarity-искажение, traversal готовы | Отсутствует; witness-наборы вычисляются каждый тик, но эфемерны; ASSERTS-примитив доказан | Отсутствует; диадический trust + reliability-провайдер + BFS готовы; reputation/faction — писатели без потребителей |
| **Переиспользуемые механизмы** | EpistemicStore, EpistemicContextResolver, BeliefRevisionEngine, ClaimEventSubscriber, DialogueSession, DecisionHub, CommitmentRegistry, цензы записи (ADR-O-380-прецедент) | WorldObjectStore (ценз Г4), object_fsms, EventCompiler, L1Chronicle (interaction_history_ref-прецедент), EvidencePolarity, DiscoveryBridge (совместимость с MVP-петлёй) | Proposition/ClaimEvent, CommitmentRegistry+FSM+арбитр+приоритеты, task_scheduler, traversal, NPC_SPOKE/COMMUNICATION_CLAIM + exposure_radius, eavesdrop-канал, AuditoryDistortionPolicy, EpistemicRecord.provenance | witness-наборы ObservationSubscriber/ReactionSubscriber/ClaimEvent-аудитория, EpistemicStore (per-agent записи), ASSERTS-примитив (SUPERBOX-022), E1-провenance | V2-trust (write-gate), TrustBasedReliabilityProvider, SocialEngine.propagate (искажение/затухание), MEM-8 per-source expectations (план), BC-4 (план) |
| **Реальный разрыв** | derived-триггер (противоречие × ставка); intent CROSS_CHECK; цель/лимиты/условия прекращения; анти-цикл; NO-DRIFT-гарантия | readable-архетип; READ-действие; DocumentClaim (текст/авторство/достоверность/полярность); ownership-ledger; мост «чтение → свидетельство» | MessagePayload (proposition+origin-цепочка); intent RELAY_MESSAGE; поручение-commitment; завершение/отмена/повтор; «C слышит только при встрече» | co-witness фиксация/вывод; statement-экспозиция; договор тайны как явная запись; утечка/обнаружение утечки без телепатии | групповой агрегат; границы области действия; механизм узнавания; анти-двойной-учёт |
| **Дублирование (уже покрывает часть задачи)** | §8.K6 (поглощён как первая реализация), BC-4/BC-6 (AG1 — ревизия при конфликте), MEM-D20 (арбитр носителей — владелец MEM) | GC-02/GC-08/F5/F9 (объект как аффорданс/последствие — не дубль: EPI — эпистемическая роль); COV-D40 (CONTRADICTS-продюсер — координация) | BC-5/BC-6 (AG1 — семантика передачи/приёма выводов), §8.B6/B7, SocialEngine (амбиентные слухи — остаётся) | CCH-01 KnowledgeLink (FR-8.2 «кто что знает» — идея), §8.H9/V2, ADR-O-209…212 VillageMemoryField (прото-консенсус) | §8.H2/I6/V3, ADR-O-209…212 InstitutionLayer («система задержек»), TrustDeep (RE §6.6) |
| **Решение** | Встроить (новая вертикаль на существующих механизмах; после допуска) | Встроить (Б-инфраструктура + А-потребление через S-гейт; после LOG) | Встроить (первым — минимальные зависимости) | Встроить (v0 = derived + явные записи тайн; после LOG) | Отложить в исследовательский бэклог (прототип после LOG+MAT) |
| **Место в дорожной карте** | Ступень EPI §0.2, пакет EPI-VER-0/1 §19.4; допуск: BC1 ON + BC-2/BC-3 + вердикт MEM-D20 | Ступень EPI, пакеты EPI-MAT-0/1; допуск: EPI-LOG v0 + S-гейт объектных фактов | Ступень EPI, пакеты EPI-LOG-0/1/2; допуск: EPI-0 | Ступень EPI, пакеты EPI-CG-0/1; допуск: EPI-LOG-2 + MEM-1 | Ступень EPI, пакет EPI-CLIMATE-0 (исследование; гейт прототипа EPI-GC-09) |
| **Критерий готовности** | EPI-GC-02/03/04: цикл «сомнение→проверка→свидетельство→ревизия→решение» с негативами (ложный/недоступный источник, NO-DRIFT, анти-цикл, сохранение неопределённости) | EPI-GC-07: «носитель ≠ автор ≠ истина», первый CONTRADICTS-случай через ревизию с полярностью | EPI-GC-05/06: маршрут/перехват/provenance-цепь; завершаемость доставки, идемпотентность | EPI-GC-08: co-witness без второго порядка; нет телепатии утечки | EPI-GC-09 (в лаборатории): локальность области действия, нет синхронизации/двойного учёта |

## 7.3. Новая последовательность (и отличие от исходной гипотезы)

Гипотеза задания: Этап 0 → 1 VER → 2 LOG → 3 MAT → 4 CG → 5 CLIMATE.

**Вердикт: порядок подтверждён с одной перестановкой (LOG↔VER) и явными критериями допуска.**

1. **Этап 0 (EPI-0) — вердиктный допуск базового контура** (немедленно, без кода): контур «событие→восприятие→свидетельство→убеждение→решение» уже доказан сквозными тестами (EPI-D1), поэтому Этап 0 — не закрытие разрывов EPI, а (а) ре-верификация карты §19.2, (б) релеи разрывов владельцам (MEM-D20, MOT-4/MEM-8, COV-7 D40/D41, T9), (в) фиксация критериев допуска EPI-VER. Гейт EPI-GC-01.
2. **Этап 1 (EPI-LOG v0) — передача сообщений.** Перестановка относительно гипотезы (был Этап 2). Зависимость: **никаких незакрытых** — CommitmentRegistry ROLLOUT-ON, claim-доставка/eavesdrop/clarity/traversal живы (EPI-D11/D12). VER при этом ждёт BC-2/BC-3 (вне контроля EPI). LOG создаёт транспортное основание для MAT/CG.
3. **Этап 2 (EPI-VER v0) — проверка убеждений.** Допуск: BC1_ENABLED ON + BC-2/BC-3 (Ступень 4 AG1) + вердикт арбитра 5 носителей (MEM-D20) — иначе EPI дублировал бы ревизионную семантику AG1/MEM. CROSS_CHECK первым; PROBE — по вердикту EPI-VER-0; TAIL/BAIT — отложены.
4. **Этап 3 (EPI-MAT v0) — материальная эпистемика.** После LOG (стабильный транспорт свидетельств) + S-гейт объектных фактов Б. Перенос выше возможен санкцией Мастера при приоритете детективного контура (обоснование переноса — вердикт COV-D40 + S-гейт; вертикаль остаётся «один предмет — один эпизод»).
5. **Этап 4 (EPI-CG v0) — общая осведомлённость.** После LOG-2 (утечка = передача; обнаружение = свидетельство) + MEM-1 (перспектива записи). v0 = derived co-witness + явные записи тайн/обязательств; без second-order ToM.
6. **Этап 5 (EPI-CLIMATE) — исследование и прототип.** После LOG+MAT+BC-5/6: климат строится на причинной истории обманов/обещаний, которой до тех пор нет. Все восемь рисков задания воспроизводимы на текущем коде (EPI-D10).

Каждое место подтверждено конкретной зависимостью (таблица §19.6 roadmap), не предпочтением.

## 7.4. Изменения документации

| Файл | Что изменено | Почему |
|---|---|---|
| `docs/ENIGMA_ROADMAP_v4_7.md` | (1) §0.1: строка трека EPI в карте треков; (2) §0.1e: вклад EPI в канонические слои; (3) §0.2: Ступень EPI (6 пакетов с гейтами); (4) §1.1: строка аудита EPI-AUDIT-01; (5) §7.11: реестр находок EPI-D1…D14 + P0-сводка; (6) §8: секция AC с поглощениями K6/D5/D6/B6/B7/H2/I4/I6/J2/T9/N7/N8; (7) §9.3g: гейты EPI-GC-01…09 + универсальные запрещающие свойства; (8) §11.4: строка ресурсов; (9) §R.7: владение §19; (10) §19: полная спецификация трека (19.0–19.8); (11) финальный абзац: регистрация дополнения v4.8-draft | Задание требует встроить пять направлений в актуальную дорожную карту с зависимостями, критериями приёмки, границами и без дублирования; структура и идентификаторы существующих разделов сохранены (никакая существующая задача не удалена и не переопределена) |
| `docs/audits/EPI-AUDIT-01_Information_Life_Cycle.md` | Создан (этот документ) | Связанный документ обоснования порядка (§6 задания): полный вердикт аудита с доказательствами; roadmap остаётся компактным |

Не изменялись: производственный код, тесты, `architecture/flags.yaml`, конфигурация, игровые данные, MUTATIONS.md (реестр сессий ведётся владеющими сессиями по Уставу; данная сессия — read-only аудит, строка MUTATIONS не создаётся в силу ограничения задания «редактируется только документация дорожной карты и связанный документ обоснования»).

## 7.5. Проверка непротиворечивости

- **Не создано второй системы истины/убеждений/свидетельств:** все пакеты EPI строятся на EpistemicStore/ClaimEvent/CommitmentRegistry/WorldObjectStore/TruthState; запрет закреплён EPI-L2 и гейтом EPI-GC-01 (греп-инвариант отсутствия вторых эпистемических сторов); MVP-петля игрока остаётся за COV-7 (§19.2: строка «закрывается COV-7, не EPI — анти-дубль»).
- **Не нарушено разделение истины, восприятия, памяти и убеждения:** EPI-L4 разводит объект-факт / DocumentClaim / эпистемическую поверхность; EPI-L3 запрещает прямую запись уверенности; EPI-L5 запрещает second-order; заключения/ревизия остаются у AG1/MEM (§19.7: «EPI не редактирует — потребляет»).
- **Физическая доступность информации не обойдена:** EPI-L1 («у всякого знания есть маршрут») + EPI-GC-05/07/08 (негатив-тесты телепатии сообщения/чтения/утечки); правило EPI-D14 (radius явно, не сентинел 999).
- **Не введён глобальный механизм доверия:** EPI-L6 + EPI-GC-09 (локальность области действия, анти-синхронизация, анти-двойной-учёт); CLIMATE — исследовательский бэклог, не обязательный этап.
- **Производственный код не изменён:** правки только в двух markdown-документах; репозиторий верифицирован (не осталось правок вне docs).
- **Существующие задачи и решения не потеряны:** вставки аддитивны; строки §8.D/§8.J/§8.K/§8.H/§8.I/§8.N/§8.T не редактировались (поглощения описаны в §8.AC); закрытые работы (BC-1 S247, E2.0-c S243, COV-0/1/2, M2/D S326, G/H S329 и др.) не меняли статус.
- **Все новые этапы имеют зависимости и критерии приёмки:** каждый пакет Ступени EPI содержит критерий допуска и гейт §9.3g; универсальные свойства (всеведение/подмена/причинность/идемпотентность/детерминизм/сохранение/негативы/совместимость/анти-дубль) встроены в §9.3g.
- **Произвольных числовых порогов не введено:** EPI-L7 (качественные критерии v0; любые числа — только калибровочный контур с ADR, источником и способом проверки; диапазон 0,3–0,7 явно запрещён как основание проверки).

## 7.6. Неопределённости (не проверено или не удалось установить надёжно)

1. **Сверка якорей с репозиторием 4Um4/Enigma (upstream):** аудит выполнен по архиву `Enigma-V.0.5.4.3.7_-_1.zip`; git-метрики и история коммитов не использовались как критерий прогресса (ограничение задания). Соответствие архива текущему HEAD upstream не проверяемо из архива — ре-верификация §19.2 на живой версии включена в EPI-0.
2. **GC-59+: не выделялись** — гейты EPI именованы в неймспейсе EPI-GC (прецедент LC-GC/MEM-GC/COV-GC), чтобы не создавать коллизий глобальной нумерации GC-00…58; правило max+1 остаётся за Мастером при переводе в общий реестр.
3. **EPI-D3 (ResolutionEngine):** TODO `npc_tick_pipeline.py:1200` указывает «Фаза 2 / Эпоха 7»; владелец интеграции выведен из §18.4 MOT-4/§16.4 MEM-8, но прямого вердикта владельца о судьбе ResolutionEngine в аудитории нет.
4. **EPI-D13 (три мембраны слуха):** расхождение физики подтверждено чтением кода, но целевой вердикт «одна мембрана» — юрисдикция владельцев восприятия (зоны А/Б §R.2); EPI-LOG презюмирует claim-канал как единственную мембрану доставки — презумпция требует подтверждения владельцем.
5. **AWC (CT-02) KnowledgeSource/origin_chain:** самый проработанный эскиз логистики во всём корпусе, но документ помечен «база V.0.5.3.4.6 — реверификация §13.2 обязательна» и ждёт вердикта Мастера; EPI-LOG не опирается на него архитектурно (только как источник идей).
6. **TrustDeep (§6.6 ТЗ RE-01):** статус реализации двухканального доверия в коде не проверялся (зона RE-01); для CLIMATE-прототипа принята ссылка без верификации.
7. **Поведение `SocialEngine.propagate` при флаге RELATIONSHIP_DYNAMICS_ENABLED=ON** (G/H S329) не моделировалось: возможное влияние динамики отношений на граф распространения слухов требует проверки владельца RE-01 при исполнении EPI-LOG-2.
8. **Статус GC-58/GC-50…57 сдвига:** если дополнение MOT шага 2 сдвинет нумерацию гейтов (примечание в GC-58), перекрёстные ссылки §9.3g не затрагиваются (именованный неймспейс), но реестр привязок §9.9 потребует сверки при следующей записи в MUTATIONS.
