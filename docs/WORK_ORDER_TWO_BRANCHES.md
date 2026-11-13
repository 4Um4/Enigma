# ДОРОЖНАЯ КАРТА РАБОТ · ДВЕ ВЕТВИ · 2026-11-11

> Статус: PROPOSED. Навигация + реестр огрехов. НЕ нормативный контракт.
> Основание: независимый аудит .py + РЕЖИМ РАБОТЫ, ROADMAP v4.12 §R, ROADMAP восстановления редактора, ADR-O-439, план трёх бог-функций, DEGOD-карты, ТЗ ЛЛМ.
> Авторитет: живое дерево Мастера. Статусы — из снапшота V.0.5.4.6.2_ЛЛМ_2; сверить блоком входа.
> Не дублирует контракты: ADR и ТЗ остаются источником истины, этот файл маршрутизирует (§R.6.5).
> Ветви назначает Мастер (§R.1.3). Разделение ниже — предложение.

---

## 0. Что уже закрыто — не делать заново

| Пункт | Статус | Дата |
|---|---|---|
| P0-01 бэкапы + SHA-256 манифест | COMPLETED | 2026-11-09 |
| P1-01 ADR-O-439 контракт W (ACCEPTED) | COMPLETED | 2026-11-09 |
| P1-02 фрейм-осознанные конверсии | COMPLETED | 2026-11-09 |
| P1-03 нормализация tavern.json | COMPLETED | 2026-11-09 |
| COV-0 / COV-1 / COV-2 | закрыты; S1 опубликован, S2 — публикация за Мастером | — |
| RE-01 M2/D + G/H · AG1 BC-1 · CCH-0…5 · LC-IMPL-1…2 | закрыты | — |

Власть координат объявлена (W1–W7). Осталась персистентность сейвов и выбор локации.

---

## 1. Порядок чтения (общий вход)

.md — целиком; >2000 строк — частями по 500, все части; Select-Object -Last для документов запрещён (§3.1).

| # | Документ | Кому |
|---|---|---|
| 1 | docs/РЕЖИМ РАБОТЫ.md | обе |
| 2 | docs/ENIGMA_ROADMAP_v4_12_WPS.md — шапка, §0.3, §R целиком, §R.2, обе лестницы §R.3/§R.4, §R.5–R.7 | обе, исполняют свою |
| 3 | docs/audits/ADR-O-439_COORD_FRAME_W.md | обе; Б обязательно |
| 4 | docs/Тесты причинности ТЗ/Задачи сегодняшнего дня/ENIGMA_ROADMAP_восстановление_редактора_мира_runtime.md — §B.1, §C-P1/C-P2, §D.1, §E, §F.1/§F.2 | Б |
| 5 | docs/Почти Актуальные TZ/Редактор кампаний/ENIGMA_MAP_EDITOR_ROADMAP_v1_4.md | Б |
| 6 | …/Редактор кампаний/BLUEPRINT_FORMAT_SPEC_v1.md, ME-2.1-G_Architecture_Review.md, MISSING_TEXTURES.md | Б |
| 7 | docs/audits/ADR-303_map_editor.md, docs/Почти Актуальные TZ/ENIGMA_MAP_EDITOR_SMART_VALIDATION.md | Б |
| 8 | ROADMAP v4.12 §2 RE, §3 AG1, §5 Body, §12 NL, §13/§14 CCH, §16 MEM, §18 MOT | А |
| 9 | docs/Тесты причинности ТЗ/Задачи сегодняшнего дня/ТЗ_ЛЛМ_и_мозг_НПС.md, ТЗ_Мозг_НПС.md | обе (§9) |
| 10 | docs/Почти Актуальные TZ/ENIGMA_декомпозиция_трёх_бог-функций.md | обе (§7) |
| 11 | docs/audits/DEGOD_PHASE0_MAP_SSM.md, DEGOD_PHASE0_MAP_game_loop.md, DEGOD_S3_ITER1_DOSSIER.md | обе; anchors устарели |
| 12 | docs/MUTATIONS.md (хвост), docs/ЗАВЕЩАНИЕ_АРХИТЕКТОРОВ.md, docs/Правила Фикса БАГОВ.md | обе |

---

## 2. РЕЕСТР ОГРЕХОВ КОДА

Классы: CRIT — отравляет истину/память; HIGH — ломает детерминизм, чистоту, управляемость; MED — тихая потеря данных/контракта; LOW — шум; GAP — отсутствующая способность.
CRIT закрывается раньше очереди (§0.2 правило 3).

### 2.1 Ветвь А — когниция, память, решение

| ID | Файл | Огрех | Следствие | Класс | Гейт закрытия |
|---|---|---|---|---|---|
- [x] **D-A01 (CRIT)** — RCE fallback ложной памяти удалён. `extract_speech_events` больше не приписывает нарратив без кавычек целевому NPC как речь. Тест `test_rce_blocks_narrative_without_quotes` добавлен. IPT 54/0. (Ветвь А)
| D-A02 [x] **CRIT** | services/npc/decision_hub.py | compute() READ ONLY + WARA §12.2 — **CLOSED** 2026-11-12: мутации `:880`/`:916` перенесены в `StateDeltas.pressure_accumulator_update` (спец-поле по образцу intent); WARA §12.2 восстановлен (`to_persistence_dict:1013` + `from_legacy:1333` — по `causality_manifest:141` DEBT/terminal=decision обязателен) | скрытая мутация входа ломала temporal isolation/replay; WARA-разрыв = гистерезис давления мёртв в проде (accumulated обнулялся каждым тиком) | **CRIT** (был HIGH) | ✅ D-A02 unit 6/6 (`test_d_a02_read_only_and_roundtrip.py`); IPT 54/54 · 0 CRITICAL; BC-1 6/6; регресс 40/40 (intent/contracts/decision) |
| D-A03 | services/memory/memory_manager.py | object.__setattr__(npc_state, "narrative_cache", …) | обход frozen-контракта; второй писатель NPCState | MED | единый write-path + ADR о владельце |
| D-A04 | services/memory/memory_manager.py | _mem_id = event.id:npc_id:md5(summary) | одинаковый текст в разных контекстах схлопывается | MED | две одинаковые реплики в разных тиках = две записи |
| D-A05 | services/npc/npc_tick_pipeline.py | causal slices: except → warning → no-op; allies=0 захардкожен | документированная ≠ живая причинность; слой молча мёртв | HIGH | ablation: убери слой → поведение изменилось; fail-loud |
| D-A06 | services/npc/state_applicator.py | apply_deltas_only не применяет identity-дельты (признано в комментарии) | тихая потеря изменений личности | MED | round-trip тест identity-дельты |
| D-A07 | services/memory/memory_manager.py | recall = importance × accessibility + теги; нет семантики, нет рефлексии | слабый retrieval против исследовательского базлайна | GAP | ADR + benchmark precision/recall |
| D-A08 | services/memory/memory_manager.py | reset_campaign_state лезет в store._collection_path, _recent_cache | фасад не закрыл внутренности | LOW | публичный API стора |
| D-A09 | state_applicator + внешние писатели | заявлен единственный писатель NPCState, но пишут память, оркестратор, GameLoop | размытая власть записи | MED | совместный ADR: gateway или сужение контракта |

### 2.2 Ветвь Б — тик, мир, платформа, фронт

| ID | Файл | Огрех | Следствие | Класс | Гейт закрытия |
|---|---|---|---|---|---|
| D-B01 | services/tick_orchestrator.py (~163 KB) | «только порядок фаз», но содержит бизнес-логику: occupancy, синхронизация локаций, проекции, хеши | god-object | HIGH | §7.2: оркестратор = список фаз; APS Bottleneck ↓ |
| D-B02 | services/tick_orchestrator.py | _npc_runtime_locations — RAM-кэш как параллельная правда локации | двойная правда с scene_state; призраки | HIGH | один резолвер; кэш удалён; T-матрица P1 |
| D-B03 | services/tick_orchestrator.py | три поколения заплаток на один корень: SC-3 FIX, S186 FIX, S267 | каждый фикс добавляет претендента на истину | HIGH | заплатки сняты после D-B02; регресс зелёный |
| D-B04 | services/tick_orchestrator.py | temporal hash покрывает 6 полей; json.dumps(default=str) | инвариант частичный; сериализация нестабильна | MED | canonical serializer; покрытие обосновано |
| D-B05 | frontend/game_screen.py (CC 337), ui_workbench/workbench_screen.py (~197 KB), map_editor/core/editor_core.py, event_handler.py (CC 87) | god-объекты фронта | регрессии, нетестируемость | HIGH | план трёх бог-функций + Phase-0 карты |
| D-B06 | docs/audits/DEGOD_PHASE0_MAP_*.md | карты от 2026-09-21: SSM 2427 строк, game_loop 2902 — файлы изменились | anchors ведут не туда | MED | карты пересняты, anchors grep-верифицированы |
| D-B07 | флаг-реестр COV-0 | 16 чужих ROLLOUT-PENDING вне цикла оживления (COV-1.5) | флаги есть, поведения нет | MED | rollout-пакеты или вердикт «похоронить» |
| D-B08 | life_engine.py, tick_orchestrator.py | отладка конкретных NPC в hot-коде (guard_borko), археологические комментарии S### | шум; ложное ощущение документации | LOW | диагностика под флаг; история в ADR/MUTATIONS |

### 2.3 Спорная зона / владелец не определён → вердикт Мастера

| ID | Файл | Огрех | Класс | Предложение |
|---|---|---|---|---|
| D-X01 | services/scene/narrative_extractor.py | uuid.uuid4() в object_id/event_id → недетерминированные ID в состоянии мира | HIGH | Б (W-TRACK), потребитель памяти — А |
| D-X02 | narrative_extractor → SSM.apply_narrative_extractions | текст LLM становится фактом мира; противоречит «LLM ≠ canonical truth» | HIGH | совместно: low-confidence proposal либо запрет canonical-записи |
| D-X03 | domain/events.py | EventDTO.create ordinal=0 по умолчанию → коллизия identity при множественности | HIGH | вне §R.2 → Мастер; обязать ordinal где кардинальность >1 |
| D-X04 | services/npc/life_engine.py (~150 KB) | update_routine 382, tick 315, _simulate_major 259; macro_simulate выродился (idle_seconds=0.0 → всегда self.tick) | HIGH | расщепить: needs/routine → А, spatial/movement → Б |
| D-X05 | services/npc/npc_tick_pipeline.py | зоны в §R.2 нет | — | подтвердить А (трек AG1); сигнатура TickState→TickMutation заморожена |
| D-X06 | services/scene_state_manager.py | общий файл: tick-lock/save/spatial (Б) × narrative/RE-sync (А) | — | построчное владение §R.6.4 + последовательная запись |
| D-X07 | все слои | нет реестра живых слоёв: продюсер/потребитель/ablation | HIGH | совместно, до наращивания этажей (§8) |

---

## 3. ВЕТВЬ А «Субъект» — лестница

Зоны: services/memory/**, memory_manager.py, BC-контур, epistemic_store, conclusion_store, belief_crystallization_engine, RE-контур, Body-контур, DecisionHub, verbalization/**, dm_agent.py, chronicle/**, phases/memory.py, рельсы npc_memory_modifiers.
Разделы: §2 RE, §3 AG1, §5 Body, §12 NL, §13/§14 CCH, §16 MEM, §18 MOT, §19 EPI (ядро).

| Шаг | Работа | Пререквизит | Гейт |
|---|---|---|---|
| А0 [x] | вход §1 + живой IPT + археология §3.6 | — | 0 CRITICAL |
| А1 [x] | D-A01 RCE: убрать fallback «весь текст = речь» | — | CRIT закрыт |
| А2 [x] | D-A02 DecisionHub: чистота compute() — **CLOSED** 2026-11-12: READ ONLY восстановлен (мутация через `StateDeltas.pressure_accumulator_update`, спец-поле по образцу `intent`/`intent_tick`); WARA §12.2 восстановлен. severity HIGH → CRIT (см. §2.1) | — | ✅ вход не мутирован; replay-паспорт совпал (T6 determinism); D-A02 unit 6/6; IPT 54/54 |
| А3 [x] INFRA | BC-2 Conclusion → Expectation: инфраструктура (DTO/Store/Bridge/Runtime/wiring) — **INFRASTRUCTURE CLOSED** 2026-11-13; BC-2 функционально НЕ закрыт, formation → А3.1 | BC-1 закрыт | ✅ unit 14/14; IPT 55/0/0 (0 CRITICAL) @ e9762397; `BC2_ENABLED` = ROLLOUT-PENDING/OFF |
| А3.1 | BC-2 Formation: реальные контекстные сигналы (`MAY_CAUSE_PHYSICAL_HARM` ← `physical_strength` в `NPCState`; `MAY_USE_FORCE_IN_CONFLICT` ← aggression taxonomy в `L1Chronicle`); требует ADR-O-XXX (разрешить при closeout) | А3 INFRA; вердикт Master по сигналам | ADR + F5-сценарий; `BC2_ENABLED` ON — отдельный вердикт |
| А4 | MEM-0 → MEM-1 → MEM-2 | S1 ✅ | §9.3e MEM-GC |
| А5 | NL-0 → NL-1 (миграция event_memories поверх раннера S1) | S1 ✅ | §9.3b NL-GC |
| А6 | D-A05 causal slices: оживить или похоронить + ablation | — | реестр D-X07 по своим слоям |
| А7 | D-A03 / D-A04 / D-A06 / D-A08 | — | по гейту каждого ID |
| А8 | NL-3 → NL-4 → NL-8a/8b | S2 | до публикации — dormant |
| А9 | D-A07 recall: семантика + рефлексия | ADR | benchmark против базлайна |
| А10 | декомпозиция NpcTickPipeline.run (§7.1) | D-X05 подтверждён | golden master; run ≤ 150 строк |
| А11 | декомпозиция DmAgent._build_contract | — | 4 снапшот-теста; ≤ 80 строк |
| А12 | CCH-6 калибровка + гейт CCH-02 | S5 | §9.3d |
| А13 | MOT (§18), досье Р18 «Адаптация», RE-01 K removal-test | — | §9.10 |
| А14 | D-A09 совместный ADR о единственном писателе | Б | ADR + гейт |
| А15 | ТЗ модели: Этапы 1, 2, 3 | — | docs/research/* → передача Б |

**А3 `[x] INFRA` · BC-2 — INFRASTRUCTURE CLOSED / formation → А3.1 (2026-11-13, вердикт Master: вариант D)**

Сделано:
- 4 новых файла: `domain/expectations.py`, `services/npc/expectation_store.py`,
  `services/npc/expectation_bridge.py`, `services/memory/expectation_runtime.py`.
- Wiring: `tick_orchestrator.py` (3 точки: `__init__`, pre-commit, Phase 9 wrapper)
  + `game_loop.py` (1 точка: restore). Симметрично BC-1, всё под `if bc2_enabled()`.
- `BC2_ENABLED` зарегистрирован в `architecture/flags.yaml` (ROLLOUT-PENDING, default OFF).
- IPT 55/0/0 · 0 CRITICAL · BC-2 unit 14/14 · BC-1 regress 6/6 (A/B/C/D/E/OFF).

PENDING:
1. **SUPERBOX полного цикла** (HANDOFF BC2-2 §11) — не написан.
2. **Прод-formation заблокирован signal-gap**: `MAY_CAUSE_PHYSICAL_HARM` требует
   `physical_strength` в `NPCState`; `MAY_USE_FORCE_IN_CONFLICT` требует aggression
   taxonomy в `L1Chronicle`. Bridge корректно возвращает `[]` (Master §4 HANDOFF:
   «не подменять отсутствие информации выдуманным сценарием»).
3. **BC-3 LOCKED by Master** — входит в формулировку А3, но заморожен.

Relay для MUTATIONS при закрытии серии:
- IPT recursion в `load_npcs_merged` — единичный флейк (нет прямых/обратных
  импортов BC-2 → `npc_loader`). Не BC-2.
- Незакоммиченная чужая WIP в `conclusion_gate.py` (-143/+73) и
  `conclusion_store.py` (-87/+87) — не моя, не трогаю. Master разводит при merge.
- Pre-existing `SC-4` spatial coherence (maid_lusya pos far from fireplace) —
  известный дефект зоны Б, исключён Master из BC-2 scope.

**Вердикт Master (2026-11-13): вариант D — APPROVED.**
- A3 INFRASTRUCTURE CLOSED: DTO/Store/Bridge/Runtime/wiring. Подтверждено: unit 14/14; IPT 55/0/0 (0 CRITICAL, re-verified e9762397); wiring под `if bc2_enabled()`.
- Formation (реальные контекстные сигналы) → **А3.1** (автономная задача; см. ROADMAP §0.2 Ступень 4, пункт BC-2.1).
- `BC2_ENABLED` остаётся ROLLOUT-PENDING, default OFF. BC-2 функционально НЕ закрыт.
- `ADR-O-XXX` для BC-2 — разрешить при closeout А3.1; произвольный номер не назначать.
- Cross-branch на 4 точки в zone Б: остаётся в силе (симметрично BC-1).

---

## 4. ВЕТВЬ Б «Мир и платформа» — лестница

Зоны: ядро тика (game_loop/__init__.py, tick_orchestrator.py, REST/лок/фазы), services/world/**, services/spatial/**, движение, экономика, sqlite_store + migration runner + save-версионирование, LLM-контур, frontend/** + Map Editor + Workbench, релизный контур, авторский контент.
Разделы: §4 W-TRACK, §15 LC, §17 COV.

| Шаг | Работа | Пререквизит | Гейт |
|---|---|---|---|
| Б0 | вход §1 + IPT + паспорт (HEAD, git status, SHA-256 чужого WIP, DriftLab MATCH×2) | — | 0 CRITICAL |
| Б1 | P1-04 миграция сейвов (W5) + node_17 | P1-01/02 ✅ | идемпотентность; CONTINUE жив; проверить покрытие MigrationRunner (ADR-O-426) — не плодить второй механизм |
| Б1p | контент-срез: 3 канон-биографии → публикация S5 (фронт Б10) | — | S5 разблокирует CCH-6 у А |
| Б2 | Ф2: P2-01 resolve_primary → P2-02 лог оракула → P2-03 клик-пикинг → P2-04 приёмка | Б1 | P2-04 = P1 закрыта |
| Б3 | Ф3: P3-01 честный результат → P3-02 валидатор фрейма (D.1.4) → P3-04 origin-драг | Б2 | ERROR блокирует, WARNING нет |
| Б4 | Ф4: P4-01 зеркальный sync (D.3) → P4-02 тесты границы → P4-03 ADR зеркал → затем P3-03 | Б3 | delete зеркален; CWD-независимость |
| Б5 | Ф5 ресурсы (P5-01…04) и Ф6 запуск (P6-01…04) — параллельно (§F.2) | Б3 | по гейтам пунктов |
| Б6 | D-B02 + D-B03: единый резолвер локации, снять кэш и три поколения заплаток | после P2-04 | ADR; T-матрица P1; сейв-версия + бэкап |
| Б7 | D-B01 / D-B04: декомпозиция оркестратора Д0→Д1→Д3 (§7.2) | Д0 сразу; Д1 после Б2 | байт-идентичный тик на Д1; APS ↓ |
| Б8 | декомпозиция GameScreen.run | после P2-03 | контрактные тесты мержа; smoke 1–9; ≤ 280 строк |
| Б9 | D-B06 переснять Phase-0 карты; D-B05 карты Workbench/editor_core/event_handler | — | anchors верифицированы |
| Б10 | Ф7 → Ф8 → Ф9 World Editor, CRUD из мира, Asset Library (единый SpriteRegistry, B-25) | Б3, Б5 | по гейтам пунктов |
| Б11 | Ф10: P10-01 регресс T1–T12 + T0 → P10-02 ADR/CI | всё | T2/T5/T8/T10 в CI |
| Б12 | D-B07 rollout-пакеты; D-B08 диагностика под флаг | — | флаги оживлены или похоронены |
| Б13 | публикация S2; после объектного мира — S3 | COV-2 закрыт | приняты А |
| Б14 | ТЗ модели: Этап 3b harness, Этапы 5–6 прогоны и железо | корпус от А (S8) | окно тишины; один сервер |

---

## 5. Гейты стыковки

| Гейт | Направление | Артефакт | Статус |
|---|---|---|---|
| S1 | Б → А | migration runner + шаблон | ✅ опубликован |
| S2 | Б → А | надёжный LLM-канал | COV-2 закрыт, публикация за Мастером — блокирует NL-3/NL-4 |
| S3 | Б → А | сценические микрособытия + observed_fact_types | после объектного мира (COV-GC-06) |
| S4 | А ↔ Б | одна травма, одна запись, vital_state SSOT | парный ADR |
| S5 | Б → А | ≥3 канон-биографий + autobiographies | ✅ опубликован (Б1p, 2026-11-11, aff447da) |
| S6 | А → Б | NL-3 VerbalizationContext + PLAYER_ASKS_WHY + NL-4 | после А8 |
| S7 | оба | общий IPT/CI, детекторы в своих неймспейсах | постоянно |
| S8 | А → Б | карта контрактов + Golden Corpus | предложение, требует вердикта |

Личной координации нет — только артефакты (§R.5).

---

## 6. Коллизии и анти-гонка

Общие файлы — построчное владение (§R.6.4), запись последовательно (Anti-Race §11.1.1):
- scene_state_manager.py: Б — tick-lock/commit, save-routing, editor-locator, scene factory, spatial enrichment, update_npc_position; А — R2.1 narrative, RE-синхронизация. Anchors устарели (D-B06).
- ROADMAP §0.2 чеклисты, §7 реестры, §9.10 матрица, §10 журнал, COV-0 флаг-реестр — свои строки.
- MUTATIONS.md — append-only, последовательно. Номер сессии — при завершении. ADR ID = max+1 с проверкой (§11).

Приборы — главный конфликт: IPT, DriftLab, SUPERBOX, llama-server :8181, Host broker :8182 общие. Два долгих прогона одновременно → exit=-1, порт-конфликт → INVALID (§3.12). Окна тишины 20–30 мин по очереди; короткие гейты без ожидания; GREEN-пакеты только в своём окне.

Read-only для обеих до вердикта: §21 MAG, §22 WPS, §23 CGB, §30 ARC-NPC.

Замороженные контракты, делающие параллельность безопасной: TickState → TickMutation, DecisionHub.compute, формат DMContract. Ревизия — отдельный ADR, не «заодно».

---

## 7. Дегодификация

### 7.1 Документация ЕСТЬ

| Объект | Документ | Ветвь |
|---|---|---|
| NpcTickPipeline.run (CC 208), DmAgent._build_contract (CC 196) | ENIGMA_декомпозиция_трёх_бог-функций.md | А |
| GameScreen.run (CC 337) | тот же план, фазы 0–6 | Б |
| scene_state_manager.py, game_loop/__init__.py | DEGOD_PHASE0_MAP_*.md (устарели) | Б |
| паспорт воспроизводимости | DEGOD_S3_ITER1_DOSSIER.md | общий |

Семь правил: только экстракция без переписывания; один шов за шаг; golden master до первого шага; импорты только модульного уровня; инвариант переезжает с кодом и живёт в одном месте; OFF-ветки байтово прежние; сигнатуры внешних контрактов заморожены.

### 7.2 Документации НЕТ — протокол tick_orchestrator.py (авторское, зона Б)

Кластеры: T1 surface/флаги · T2 constructor wiring · T3 DI/lazy · T4 _rebuild_cluster_occupancy · T5 execute() (сцены, локации, время, C3) · T6 _deobjectify_event · T7 обёртки фаз · T8 _phase_5_decision · T9 _compute_effective_drives · T10 _advance_idle_time · T11 _apply_drf_scoring_overlay. Anchors уточнить археологией.

Целевые модули: services/tick/scene_collection.py (T5) · cluster_occupancy.py (T4) · time_authority.py (T10) · temporal_probe.py (T8-хеши) · runtime_locations.py (T5-локации, ликвидация двойной правды) · проекции attention/intent → в существующий services/phases/decision.py. Оркестратор = список фаз + DI.

| Фаза | Содержание | Гейт |
|---|---|---|
| Д0 | Phase-0 карта: BASELINES (mypy/ruff/IPT), кластеры+anchors, владение состоянием, call-site surface, CONTRACT. Паспорт: HEAD + git status + SHA-256 чужого WIP + DriftLab MATCH×2 | карта принята |
| Д1 | чистые экстракции T4, T10, temporal probe | байт-идентичный тик; hash совпал; IPT 0 CRITICAL; ruff/mypy 0 |
| Д2 | runtime_locations — устранение двойной правды (не байт-нейтрально) | ADR; T-матрица P1; сейв-версия + бэкап |
| Д3 | execute() → список фаз; T8 → phases/* | полный golden master; APS ↓ |
| Д4 | повторный cc_map.py / APS.py | оркестратор вне топа CC |

Инварианты переезжают с кодом: INV-TIME-FREEZE, INV-TICK-CARDINALITY → time_authority; INV-POSITION-MUTATION, INV-SPATIAL-SSOT → cluster_occupancy + runtime_locations; INV-TEMPORAL-ISOLATION → temporal_probe; INV-PLAYER-AUTHORSHIP остаётся на границе сборки TickMutation; INV-COMMIT-CARDINALITY у SSM, не трогать.
Откат: git-тег до Д1; Д1 помодульно; Д2 только с версией сейва и бэкапом.
Запрещено: менять сигнатуру execute(), семантику find_chunks, порядок фаз, OFF-ветки; «заодно улучшать».

### 7.3 Документации НЕТ — Phase-0 карты прочих

Нет карт: life_engine.py (D-X04), decision_hub.py, state_applicator.py, workbench_screen.py, editor_core.py, event_handler.py.
Порядок: карта (read-only) → вердикт → экстракция. Шаблон: BASELINES → FACT (кластеры+anchors) → State ownership (скрытые связки, SHARED MUTABLE) → Call-site surface (grep) → CONTRACT.
Владение: decision_hub/state_applicator — А; workbench/editor_core/event_handler — Б; life_engine — D-X04.

### 7.4 Порядок дегодификации относительно ремонта

1. GameScreen.run трогает те же call-site, что P1-02/P2-03 → старт после P2-03.
2. Оркестратор Д2 трогает те же факты, что P1-04/P2-01 → старт после P2-04. Д0/Д1 раньше можно.
3. Экстрагировать код, который вот-вот изменится, — двойная работа и риск потерять инвариант.

---

## 8. Реестр живых слоёв (D-X07) — до наращивания этажей

На каждый слой: включён по умолчанию? · есть продюсер? · есть потребитель? · есть ablation «убери → поведение изменилось»? · есть трасса input→delta→decision?
Не проходит — честно dormant. Первыми проверить слои 6 (salience/consolidation), 8 (belief→expectation), 12 (deception).
Ведут совместно: когнитивные слои — А, мировые продюсеры — Б.

---

## 9. ТЗ модели — разделение по этапам

ТЗ read-only: production-код, конфиг и действующая модель не меняются → совместимо с ремонтом.

| Этап | Содержание | Ветвь |
|---|---|---|
| 1 | археология прежних испытаний | А |
| 2 | карта контрактов: prompts, verbalization, декомпозитор, IntentCompressor | А |
| 3 | Golden Corpus: семантика, эпистемика, биография, когниция | А |
| 3b | harness, замороженные условия, SHA256 GGUF | Б |
| 5–6 | сравнительные прогоны + железо (RTX 3070 Ti 8 GB, RAM 16 GB, :8181/:8182) | Б |
| 7–9 | сводка, рекомендация | Б собирает; решает Мастер |

Контроль: Hermes-3-Llama-3.1-8B Q4_K_M. Кандидаты: YandexGPT-5-Lite-8B Q5_K_M, GigaChat-20B-A3B-instruct Q4_K_M.
Артефакты: docs/research/LLM_PREVIOUS_TESTS_INVENTORY.md, ENIGMA_LLM_CONTRACT_MATRIX.md, ENIGMA_LLM_GOLDEN_CORPUS.md, ENIGMA_LLM_BENCHMARK_RESULTS.md, ENIGMA_LLM_MODEL_RECOMMENDATION.md.
До завершения Этапа 1 новые испытания запрещены. Тяжёлые прогоны — в окне тишины, один сервер, не убивать по имени, не обходить Host broker.
Передача А→Б требует S8 — вердикт Мастера.

---

## 10. Правила против расползания

1. Не добавляй новый продюсер фактов, пока у факта нет владельца и прибора.
2. Один факт — одно место. Параллельная реализация останавливает обе стороны до вердикта (§R.6.2).
3. Шаг закрывается гейтом, не уверенностью: IPT 0 CRITICAL + целевой тест + byte-diff для рефакторинга.
4. Рефакторинг байт-нейтрален. Изменение поведения — отдельный пункт с ADR.
5. Улучшения (Ф7–Ф9) не подменяют ремонт (Ф1–Ф6).
6. Измерение только на неподвижной платформе; exit=-1 = INVALID.
7. Находка чужой зоны → строка в §7, не правка.
8. CRIT-огрехи — раньше очереди.

---

## 11. Вердикты Мастера

1. Назначение букв обоим агентам (§R.1.3); принятие файла как навигации (если дублирует ROADMAP — удалить, оставить ссылки).
2. D-X01…D-X07: владельцы спорных зон, ordinal, uuid4, LLM→canonical, life_engine, npc_tick_pipeline, построчное владение SSM.
3. Протокол декомпозиции оркестратора (§7.2) — до первого переноса.
4. S8 для ТЗ модели.
5. Публикация S2; ранний S5 (Б1p).
6. P3-04 вариант A/B; P4-03 судьба зеркал.
7. Окна тишины: расписание долгих прогонов.
8. **A3/BC-2 (2026-11-13, вариант D — APPROVED):** инфраструктура BC-2 CLOSED; formation → А3.1 (автономная задача, ADR-O-XXX при closeout); `BC2_ENABLED` = ROLLOUT-PENDING/OFF; BC-2 функционально не закрыт.

---

## 12. Чеклист закрытия шага (обе ветви)

- [ ] Археология §3.6: PIPELINE_OBJECT / OWNER / TYPE, читатели, писатели (>1 → STOP)
- [ ] ADR-PRE-FLIGHT, если затронуты домены или новые DTO/фазы
- [ ] Патч §4: Файл: / БЫЛО: / СТАЛО: / IPT: / КРАСНЫЕ ИНВАРИАНТЫ:
- [ ] IPT X passed / Y failed (0 CRITICAL) — только хвост
- [ ] Целевой тест зелёный; рефакторинг — byte-diff пуст
- [ ] Долгие прогоны в окне тишины; артефакт полный; канонические маркеры
- [ ] Строка в §10 ROADMAP + галочка в чеклисте своей ветви
- [ ] MUTATIONS.md; номер сессии — при завершении
- [ ] ruff / mypy 0; APS.py каждые 5 шагов
- [ ] Огрех из §2 закрыт своим гейтом и отмечен в реестре