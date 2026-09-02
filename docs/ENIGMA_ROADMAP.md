# ENIGMA — Дорожная карта преемника

**Версия документа:** 3.0 · 2026-09-03
**Адресат:** LLM-преемник на V.0.5.3.9.6 (ветка `V.0.5.3.9.6_Память_3`)
**Назначение:** Пошаговый план — что делать, в каком порядке, что читать, что формулировать самому.
**Принцип документа:** компактный, без воды; галочки `[ ]` — для трекинга; путь к файлу — для каждого шага.
**Актуализация:** 2026-09-03. Основа — V.0.5.3.9.5 + **сессия AG1 (Фаза A + EMRL E1/E2.0)**: закрыт фундамент памяти (аудит V.0.5.3.9.3: 9 P0 + 5 живых детонаций тика), построена шина опыта E1 и каузальный шлюз E2.0 (DeltaGate). См. новый §2a.

---

## 0. Контекст: где мы сейчас

**Версия кода:** V.0.5.3.9.6 · `version.txt` = `0.5.3.9.6` · синхронизирован с `pyproject.toml` (desync v0.5.3.7.0-era **закрыт**).

**Главные активные треки (на смену defect-fix ТЗ V0.5.3.7.0, которое утрачено):**

1. **ТЗ-RE-01 — Relationship Engine v2** (`docs/Почти Актуальные TZ/ТЗ_RE-01_Relationship_Engine_v1.9.md` + акт передачи `ТЗ_RE-01_ПЕРЕДАЧА_преемнику_Р18.md`). Прогресс: **M0 ✅ (ADR-O-369)** → **M1a ✅ (ADR-O-370)** → **M1b — в процессе (ADR-O-371-серия коммитов, RelationshipWriteGate)** → далее M1b.5 / M2-D / G / H / K / полигон M.
2. **W-TRACK — World Embodiment Foundation** (`docs/Почти Актуальные TZ/TZ_WORLD_EMBODIMENT FOUNDATION (W-TRACK).md`). Прогресс: субстрат WORLD-домена **положен** (ADR-O-371: `architecture/world.yaml`, WorldObjectStore, 30 тестов, IPT 45/45), рантайм-потребителей пока **ноль** (доктрина dormant-substrate). Следующие: W2 AffordanceResolver, W3 transition_object + causal writer, W7 PresentationProjector.
3. **Р18 «Адаптация»** (раунд ТЗ-RE-01) — ОТКРЫТ; режим работы и развилки — в акте передачи (см. §2).
4. **Behavioral Closure / Social Cognition** — **фундамент построен сессией AG1** (см. §2a): Фаза A закрыла P0-дефекты памяти аудита V.0.5.3.9.3, EMRL E1 (шина опыта) и E2.0-a/b (DeltaGate: единственный вход «интерпретация → состояние», живой провод THREATEN→ПК, EXPERIENCE_DELTA_COMMITTED для Chronicaler) — 40 замков `backend/tests/test_phase_a_memory_fixes.py`, IPT 45/45. Осталось: E2.0-c (каузальный экзамен A/B/C/D) → BC-1..BC-12. Не вводить флаги «месть/обида/влюблённость» как сущности; выводы должны быть derived из общих механизмов.

**Эпоха:** переходная между **Эпохой 6 (Stabilization)** и Эпохой 7. Фактическая текущая точка: **RE-01 M1b.4 (физический cutover) + M1b.3.1/3.2 закрыты — V2 RAM-authoritative runtime ЖИВ (writers+readers+bootstrap, 202 теста, зонд 21/22); открыты M1b.3.3–3.7 (decay/гидратация/flat-readers/S128/страж) и M1b.5/M2-D; W-субстрат существует, но runtime-consumer слой dormant; predictive/social cognition ещё не замкнут.** `docs/Почти Актуальные TZ/STABILIZATION_ROADMAP.md`: **стабилизация v0.5.3.7.2–v0.5.3.7.10 завершена** — ядро (Tick, Movement, Decision, LLM) стабильно, **IPT 45/45 (было 39/0)**, `lint_silent_failures` ✅, `lint_relationship_engine` ✅. Остаток долга — god-файлы, mypy --strict (79 → 0 в spatial-слоях), print() в backend (36 → 0), TODO/FIXME.

### Горячие runtime-проблемы (из `reports/LAST_SESSION.md`, 28.08.2026)

| # | Проблема | Статус | Куда смотреть |
|---|----------|--------|---------------|
| 1 | **Симуляция заморожена: все 30 тиков → 0 decisions** (BREAK-1) | ✅ **Разморожена** (Фаза 0.1) — DecisionHub жив, 6/6 NPC выдают решения в smoke-прогоне. Артефакт «0 decisions/tick» — следствие player-turn-only пути. Полное подтверждение — живая сессия. | `backend/app/services/npc/decision_hub.py` |
| 2 | LLM-сервер недоступен при старте backend | ✅ **Исправлено** (Фаза 0.2) — `scripts/llm_server_manager.py`, LOG-GATE-UI на splash показывает статус. `startup_timing.log`: `backend_ok=True, llm_ok=True`. | `scripts/llm_server_manager.py`, `backend/logs/` |
| 3 | 21 traceback в сессии | ✅ **Устранены 3 реальных бага** (Фаза 0.3): (a) `social_subscriber.py` — `RelationshipWriteGate(None)` тормозил тик; (b) `mvp_tavern_controller.py` — DEATH по hp<=0 вместо VitalState verdict; (c) `domain_phases.py` — eco-стресс не доходил через StateApplicator. | `backend/app/services/events/social_subscriber.py`, `backend/app/services/social/mvp_tavern_controller.py`, `backend/app/services/npc/domain_phases.py` |
| 4 | NPI 86% | ✅ **Исправлено** (Фаза 0.4) — 6/6 NPC теперь имеют координаты в smoke. `local_traversal_planner` + `traversability_evaluator` работают. player без координат — требует живой сессии (0.5). | movement-пайплайн, `backend/app/services/spatial/` |
| 5 | Traversal ⏸ у `guard_borko` / `thief_shadow` | ✅ **Разморожен** (Фаза 0.4) — smoke даёт 6/6 `VALID_PATH`. ⏸ в сессии — артефакт arbiter INCUMBENT-отклонения. | `local_traversal_planner.py`, `traversability_evaluator.py` |
| 6 | NEI=0 — NPC слишком комфортны | ⚠️ **Частично** (Фаза 0.6) — eco-стресс теперь доходит до StateApplicator. Needs-writer runtime — в M2/D, не форсировать. | physiology/needs-контур |

DNA в целом: SHI=100%, SCF=1.0, DRI=100%, DPI=100%, BCI формируется. История — `reports/dna_history.jsonl`.

### 5 архитектурных истин (усвоить перед любым шагом)

1. **Truth = Snapshot + Chronicle.** State эфемерен, Identity — append-only. Асимметричная онтология, не баг.
2. **Time & Physics — одно.** Разрешаются только в Causal Kernel.
3. **No Event Sourcing for State, но yes for Identity.** State — snapshot, Identity — L1Chronicle (SQLite append-only).
4. **Symptom ≠ Cause.** Чини pipeline node, не UI.
5. **Vacuum = local rupture, not global zero.** Unknown ≠ Neutral 0.0.

**Новая, Эпоха RE-01 (добавить к истинам):** **«Паттерн, не субстанция»** (принцип Р17-П1) — человеческие категории («идеализация», «влюблённость», «адаптация») не вводятся как состояния-сущности; каждая проходит **anti-Bond тест**: доказывается каузальная работа, которую никто другой в ENIGMA не выполняет, иначе — derived-операция.

### Принципы работы

- Один фикс → один коммит → один тест. Не пачками.
- CI-гейты обязательны: `ruff` + `pytest backend/tests/IPT.py` (сейчас 45/45) + профильные линтеры `scripts/lint_*.py` (relationship_engine, kernel_rng, l1_append_only, epistemic_boundary, spatial_ssot, frontend_isolation, wall_clock, silent_failures и др.).
- Observability **never mutates**.
- DNA-метрики могут врать — перепроверяй через `backend/data/logs/scene_changes_*.jsonl`.
- `MockProvider` в production-пути запрещён.
- `random.*` и `time.time()` в kernel-слое запрещены → только `KernelRNG(tick, npc_id, salt)`.
- Файловые runtime-логи гейтятся `ENIGMA_DISABLE_FILE_LOGS` (LOG-GATE); git-хуки гоняют тесты без записи в `data/logs`.
- Режим RE-01: **GPT задаёт направление, преемник вскрывает факты до решений и спрашивает по каждой развилке.**

---

## 1. Документы: что существует, что утрачено (проверено Test-Path 2026-08-30)

### ✅ Существуют и актуальны

| Документ | Роль |
|----------|------|
| `docs/Почти Актуальные TZ/ТЗ_RE-01_Relationship_Engine_v1.9.md` (1972 строки, аудит 40/40) | Канонический ТЗ Relationship Engine v2: аксиомы §3, запреты §7, устав §12.2 |
| `docs/Почти Актуальные TZ/ТЗ_RE-01_ПЕРЕДАЧА_преемнику_Р18.md` | Передаточный акт: режим работы, роадмап (а)→(г), развилки Р1–Р7 |
| `docs/Почти Актуальные TZ/TZ_WORLD_EMBODIMENT FOUNDATION (W-TRACK).md` | Часть II Stage 2.5: 4-хуровневая архитектура WORLD→EMBODIED→PRESENTATION→RENDERING, этапы W0–W9 |
| `docs/Почти Актуальные TZ/STABILIZATION_ROADMAP.md` | Вердикт по стабилизации: закрыта; остаток долга — god-файлы, mypy, print(), TODO |
| `docs/ENIGMA_EPOCHS_REPORT.md` | Карта Эпох 1–10 (источник истины по прогрессу; сама отстаёт — на момент v0.5.3.7.8) |
| `docs/Почти Актуальные TZ/RemontTZ/*.md` (6 файлов) | Мастер-ТЗ на ремонт доменов (CORE/SPATIAL/DIALOGUE/PERCEPTION/FRONTEND) — историческое, большинство фиксов уже применено |
| `docs/Почти Актуальные TZ/VZ/*.md` (7 файлов: §18, §19, MEMETIC 01–03, TZ-02, TEXTURES) | Будущие эпохи (7–10) |
| `docs/Почти Актуальные TZ/TZ_Stage_2_5_Temporal_Causality_Predictive_Runtime_1.md` | Temporal causality / predictive runtime (Часть I; W-TRACK — его Часть II) |
| `docs/Почти Актуальные TZ/1_TZ_Architect_Enigma_V0_5_3_8_2.md` (+ Parts 2–4, `1_TZ_Стадия_2.md`) | Архитектурные ТЗ волны 0.5.3.8.x |
| `docs/Почти Актуальные TZ/PSY-ARCH-01_Unified_Psychological_Dynamics.md`, `TZ_Laboratoria_Kalibrovki_ENIGMA.md`, `Plan_Razrabotki_Laboratorii.md` | Психологическая динамика и калибровочная лаборатория (M0-полигон ADR-O-367 жив) |
| `docs/Почти Актуальные TZ/ENIGMA_LLM_PIPELINE_TZ_v1.md`, `ENIGMA_MAP_EDITOR_SMART_VALIDATION.md`, `ENIGMA_TZ2_v2_Narrative_Frame_Onboarding.md`, `ТЗ ENIGMA WORLD-CENTRIC SPATIAL ARCHITECTURE.md` | Периферийные ТЗ (по мере надобности) |
| `docs/audits/ADR-O-369/370/371_IMPACT.md` (+ атлас `docs/ADR (Architecture Decision Records).md`, 130+ файлов) | Свежие ADR и единый атлас |
| `reports/SESSION_S62_DM_VISION.md`, `reports/LAST_SESSION.md` | Сессии |

### ❌ Утрачены / не найдены (ссылки из v1.0 роадмапа более не валидны)

- `upload/ENIGMA_TZ_V0.5.3.7.0.md` — главный defect-fix ТЗ эпохи 0.5.3.7.0. **Папки `upload/` нет.** Его defect-каталог фактически отработан STABILIZATION_ROADMAP — не искать, не восстанавливать.
- `docs/Почти Актуальные TZ/ENIGMA_TZ_INFRASTRUCTURE.md` — нет в репо.
- `docs/Почти Актуальные TZ/ENIGMA_SELF_HEALING_SYSTEM.md` — нет в репо.
- `S1_INPUT_TRACE_IMPLEMENTATION.md`, `INPUT_OBSERVATORY_ROADMAP_S2_S6.md` — нет в репо.

---

## 2. Активный трек №1 — RE-01: Relationship Engine v2

### Прогресс по фазам (все гейты зелёные, runtime байтово идентичен)

- [x] **M0 (ADR-O-369)** — онтологический контракт: `architecture/relationship_engine.yaml` (45 узлов, 20 событий, 6 предикатов, запреты №1–35) + `scripts/lint_relationship_engine.py` в CI/pre-commit. Рантайм не тронут.
- [x] **M1a / Phase B (ADR-O-370)** — субстрат: `RelationshipStateStore` (scene_state-backed, dormant), контракты NeedSlot/PreferenceModel/HardConstraint, `StateApplicator.update_needs` (single-writer, caller-guard). 28 тестов.
- [x] **M1b.0** — `RelationshipWriteGate` (routing-слой, whitelist 5 скаляров, NaN/foreign-key guard) + D3-паритет против legacy `update()`.
- [x] **M1b.1** — миграционный адаптер legacy→v2 (deterministic transform, идемпотентность, 9 приёмочных тестов).
- [x] **M1b.2 (полностью, 2.0–2.7)** — RelationshipWriteGate + D3-сетка 8×8×5; ВСЕ 6 write-маршрутов через гейт (social_subscriber, compiler, MemoryManager-фасад, StateApplicator, rules_subscriber, decay-архитектурно); semantic gate §8.6 (комплимент — ОДНА направленная запись, кэш-хирургия attraction удалена); вечные греп-инварианты (ноль writer'ов вне гейта).
- [x] **M1b.4 (физический cutover, RAM-GO)** — `V2RelationshipBackend`: RAM = runtime authority (pre-scene writes — паритет-контракт легаси, сторож IPT INV-TRUST-MONOTONICITY), сцена = persistence projection, disk-on-update запрещён, lazy/late-bind, hydrate, split-маркер `.migrated` только после atomic_commit_all, Фаза 10 multi-location sync, legacy JSON заморожен. Сьюта 194.
- [x] **M1b.3.1** — fallback DecisionHub УДАЛЁН (обе ветки; кэш = projection-only; Vacuum каноничен) + V2-`get` легаси-формат (стрелочные ключи — ридер был слеп; сетка D3 не покрывала get) + миграция test_decision_calibration на compute-kwargs.
- [x] **M1b.3.2 (вердикт β)** — bootstrap отношений → RAM: `bootstrap_from_npc_dicts` (только 5 скаляров; base_values/nature — decay-домен; existing-RAM-wins; «источник конфигурации читает один владелец») + npc_provider lazy-bootstrap (закрыл ВТОРОЙ прод-путь: idle/resume минует init_scene_state; зонд: 0 → 21/22 ненулевых пар). Сьюта 202.
- [ ] **M1b.3.3–3.7** — decay/гидратация (единый разрез `build_npc_snapshots`: V2 → снапшот-кэш; decay = produce Δ над снапшотом, не трогать) → flat-readers-зонд (3 находки в досье) → S128-разделение (вердикт (а) получен) → греб-страж allowlist.
- [ ] **M1b.5** — удалить мёртвый `apply_npc_state_updates` (0 вызовов доказано грепом) + судьба legacy-класса/vestigial provider.
- [ ] **M2/D** — `RelationshipEventSemantics`: первый реальный писатель потребностей через `update_needs` + формат RE-событий в causal-машинерии.
- [ ] **G/H** — динамика Satisfaction и фрустрации через стор.
- [ ] **K (фаза I артефакт)** — полный removal-test.
- [ ] **Полигон M** — пресеты, INV-1, диф-тест раннего внимания **О-2** (единственный хвост Р17).

### Р18 «Адаптация» (открытый раунд)

Источники: акт передачи (§3) + ТЗ v1.9 §12.2. Правило раунда: **«Не доказываем, что адаптация существует; доказываем или опровергаем, что есть каузальная работа, которую никто другой не выполняет»**. Первое действие — досье адаптационного контура по цепочке `writer → state → reader → causal effect → existing substitute → anti-Bond test → остаток`. Развилки Р1–Р7 — вопросом арбитру (GPT), не самостоятельными решениями. Зоны вскрытия — §6.3/§5.0/§5.1/§8.1/§6.19/§6.4 ТЗ v1.9.


---

## 2a. Трек AG1 — Фаза A / EMRL: шина опыта и каузальный шлюз (сессия 2026-09-02..03, ЗАКРЫТ частично)

**Судья трека:** мандат «EXPERIENCE → MEMORY → SELF → RELATIONSHIP LOOP» (владелец). Ключевые законы сессии: (1) **LLM — медленный консультант, не SSOT**: между Interpretation и State нет прямого пути (DeltaGate); (2) **две скорости**: быстрый мир (тики) никогда не ждёт медленного интеллекта (LLM) — ADR-O-377 (cockpit-форма жива, production-форма в плане); (3) **AG1-INV-TRACE-ONCE**: один event.id → один causal trace → ≤1 принятой дельты поля; (4) «суть» эпизода = акт консолидации (is_compressed), не зона важности; (5) припоминание растит доступность, не истинность.

### Фаза A — Фундамент памяти (ЗАКРЫТА ✅)

Закрытые P0 аудита V.0.5.3.9.3 (№1–9) + внеплановые живые детонации: 4.5 (дефолтный summary), 7.5 (ампутация легаси temporal-ветки → TICK_CRASH 3/3→0), 9.5 (спикер речи в память), 9.6 (mem_id digest — конец каннибализации), 9.12 (мёртвый `_shared_context` в провайдерах — провод речь→память: 272 строки npc_spoke), 10.0 (L1-UNIQUE: guard под констрейнт + OR IGNORE). Итог: все 10 фаз тика живы, речь NPC становится памятью, персистентность сквозная.

### EMRL E1 — Шина опыта (ЗАКРЫТА ✅)

| Кольцо | Что | Артефакты |
|---|---|---|
| E1.0 | ExperienceTrace + provenance (TESTIMONY ≠ копия) + таблица | `backend/app/models/npc/experience_trace.py`, `sqlite_store.save_trace/load_traces` |
| E1.1 | Decay-семантика: floor = is_compressed (суть бессмертна, шум умирает) | `working_memory.py` E1.1-floor |
| E1.2 | MemoryCrystal (semantic, memory-домен) + confidence/retrieval_strength разделены + домен-граница с CrystallizedBelief | `backend/app/models/npc/memory_crystal.py`, `sqlite_store.save_crystal/load_crystals` |
| E1.3 | Provenance-контракт (внутри E1.0) | TraceSource |
| E1.4 | Кокпит: `new`/`mem`/`wait`/`restart`/адресация/класс-отцепление экстрактора | `backend/tests/sandbox/terminal_cockpit.py` |
| E1.5 | Диагностическая приёмка (живой прогон: рассказ→память→рестарт→память) | ✅ руками владельца |

Формулировка честности (вердикт владельца): **доказано** — NPC сохраняет NPC-originated proposition; **не доказано** — что оно становится причинным внутренним состоянием. Первый кандидат-наблюдение: «Надеюсь, они не придут сюда» (Горан, imp=0.26, пережил рестарт) — proposition, не состояние.

### EMRL E2.0 — Каузальный шлюз (a/b закрыты, c — следующий)

| Пакет | Что | Статус |
|---|---|---|
| E2.0-a | DeltaGate + StateDeltaProposal (whitelist/клампы/идемпотентность/INV-LLM-NOT-SSOT) | ✅ |
| E2.0-b | Живой провод: Proposal в reaction_subscriber (S115-точка), Gate = аудит не писатель, belief — тиковая ветка (causal_parent), EXPERIENCE_DELTA_COMMITTED (EventDTO) | ✅ 40/40 |
| E2.0-c | SUPERBOX causal_state_test: A/B/C/D, детерминистичный инвариант (один snapshot+seed+event; единственная переменная — авторизованная дельта; D = запись мимо гейта → ожидаем ArchitecturalViolationError) | [ ] СЛЕДУЮЩИЙ ШАГ |

Терминологическая лестница (запрещено перепрыгивать): E2.0 = state-delta integrity; E2.0-b = live propagation; **BC-1 = semantic leap** (EXPERIENCE→CONCLUSION) — только после зелёного E2.0-c.

---

## 3. Активный трек №2 — W-TRACK: World Embodiment (Часть II Stage 2.5)

Главный инвариант: **Renderer не является источником истины о мире**; новый NPC/шрам/предмет/renderer не требуют переписывания мозга NPC.

- [x] **W-субстрат (ADR-O-371)** — WORLD-домен: `architecture/world.yaml`, семантическая объектная топология, WorldObjectStore (персистенция внутри `scene_state`), `WorldSnapshot` +1 поле. 30 тестов (`backend/tests/test_world_object_topology.py`) + INV-WORLD-OBJECT-TOPOLOGY в IPT. Рантайм-потребителей: 0 (доктрина dormant-substrate).
- [ ] **W2** — AffordanceResolver (read-потребитель субстрата).
- [ ] **W3** — `transition_object` + causal writer (спавнер; тогда же caller-guard по образцу M1a `_ALLOWED_WRITERS`).
- [ ] **W4** — Embodied State (поза, локомоция, хват, attachment).
- [ ] **W5–W9** — Presentation Projector / интерфейсы renderers — только контракты + PoC.

---

## 4. Фазы и порядок работ (обновлённая последовательность)

### Фаза 0 — Разморозка симуляции (немедленно, до любых feature-работ)

Статус 2026-08-30: сессия дезминтинга проведена; IPT 45/45, smoke β (Goran) чистый. Детали фиксов — в комментариях кода с меткой `FIX (Phase-0 ...)`.

- [x] **0.1** BREAK-1 частично снят: WorldTick-путь жив — smoke даёт **6/6 NPC-решений** ([DECISION_HUB] guard_borko/merchant_goran/maid_lusya/blacksmith_orm/thief_shadow/tavern_keeper_tornin); «0 decisions» в DNA последней сессии — артефакт player-turn пути и счётчика [R3_DIRECT] (диагностика `diagnostics/pattern_registry.py`). Требует подтверждения живой игровой сессией.
- [x] **0.2** LLM-сервер при старте: подтверждён OK (`startup_timing.log`: `backend_ok=True, llm_ok=True`; `[STARTUP] LLM (сервер): доступен`). Фолс-тревога последней сессии.
- [x] **0.3** Tracebacks устранены (3 фикса): (1) `social_subscriber.py` — None-стор больше не оборачивается в RelationshipWriteGate (было `NoneType.update` каждый тик); S116-fallback понижен до debug; (2) `mvp_tavern_controller.py` — DEATH триггерится только по `life_status==DEAD` (SSOT VitalStateEvaluator), hp<=0 без DEAD → WARN вместо ValueError→DLQ каждый тик; (3) `domain_phases.py` — eco-стресс проводится через `StateApplicator.apply_deltas_only` (было: guard ломал запись, стресс молча терялся — вклад в NEI=0). `lint_silent_failures` — ✅ 0.
- [~] **0.4** Traversal: в текущем билде smoke даёт 6/6 `VALID_PATH / traversal=CREATED`; ⏸ у guard_borko/thief_shadow в последней сессии — вероятно arbiter INCUMBENT-отклонения (commitment держит прежнюю цель). Подтвердить живой сессией.
- [ ] **0.5** player без координат — требует живой игровой сессии (не воспроизводится в smoke).
- [~] **0.6** NEI=0: eco-стресс дельт теперь доходит (фикс 0.3); полноценный рантайм-писатель потребностей — только в M2/D (по плану RE-01, не форсировать).

### Фаза 1 — Завершение RE-01 M1b→M2 (параллельно с Фазой 0 после разморозки)

- [ ] M1b.5 (мёртвый код), затем M2/D, G/H — по ТЗ v1.9; каждая фаза = контрактный гейт + линтер + IPT 45/45.

### Фаза 1.5 — Поведенческое замыкание NPC (после M2/D, до тяжёлого Active Inference)

Цель: не новый набор эмоций, а единый контур социализации на уже существующих Memory/Belief/Relationship/Decision механизмах.

- [ ] **BC-1** Experience → Conclusion: значимый опыт должен порождать вывод о причине/агенте/паттерне, а не только память + scalar trust/fear.
- [ ] **BC-2** Conclusion → Expectation: вывод должен менять прогноз следующего взаимодействия.
- [ ] **BC-3** Expectation → Decision: существующий DecisionHub должен использовать ожидание без специальных action-флагов.
- [ ] **BC-4** Repeated evidence → Generalization: повторяемость должна усиливать устойчивый вывод; contradictory evidence — ослаблять/ревизовать его.
- [ ] **BC-5** Personal experience → Social testimony: NPC должен уметь передавать не только факт, но и собственный вывод («я считаю его ненадёжным»).
- [ ] **BC-6** Testimony → Recipient belief: получатель должен учитывать источник, уверенность, собственный опыт и конфликтующие свидетельства.
- [ ] **BC-7** Conclusion → social strategy: допустимы derived-паттерны «избегать», «не сотрудничать», «не давать ресурс», «предупреждать», но без флагов конкретных NPC.
- [ ] **BC-8** Learning: успешный опыт должен уметь порождать знание/правило/навык, которое меняет будущую возможность или предпочтение действия.
- [ ] **BC-9** Surprise → belief revision: неожиданное поведение другого должно ломать/уточнять ожидание и отношение.
- [ ] **BC-10** Self-learning: опыт должен при необходимости менять не только модель другого, но и модель себя («я умею», «я ошибся», «я должен быть осторожнее»).
- [ ] **BC-11** Social triangles: A→B→C должен порождать третичное изменение отношений без специального «треугольника отношений».
- [ ] **BC-12** Long-horizon proof: сценарии `оскорбление→обида→память→избегание`, `обман→вывод→слух→осторожность`, `обучение→новое действие`, `помощь→благодарность→ответная помощь` проживаются 100–1000 тиков.

**Stop:** пока BC-1…BC-7 не доказаны, не начинать полноценный Active Inference как отдельный большой слой.

### Фаза 1.6 — Unified Appraisal / «палитра эмоций»

- [ ] **EM-1** Определить минимальное пространство оценок: valence, arousal/intensity, agency, controllability, fairness/norm violation, self/other relevance, certainty/uncertainty, future consequence/expectation.
- [ ] **EM-2** Отделить appraisal от emotion, emotion от relationship и relationship от belief.
- [ ] **EM-3** Вывести anger/fear/sadness/pride/shame/gratitude/envy/resentment/contempt/hope как derived regions, а не отдельные state-machines.
- [ ] **EM-4** Сделать decay, accumulation, interference, memory reactivation и social contagion общими законами.
- [ ] **EM-5** Emotion → action preference: чувства голосуют за существующие действия; не создавать `if emotion == X → action Y`.
- [ ] **EM-6** Expression dictionary: словарь речи/позы/интонации отдельно от причинности.
- [ ] **EM-7** Calibration lab: подобрать пороги и веса на сценариях, а не вручную на каждом NPC.

### Фаза 1.7 — Predictive Perception / Surprise

- [ ] **PP-1** Унифицировать observation/belief truth sources.
- [ ] **PP-2** Ввести измеримый surprise/prediction error как свойство ожидания, а не просто эмоциональный всплеск.
- [ ] **PP-3** Использовать surprise для пересмотра beliefs/relationships/expectations.
- [ ] **PP-4** Закрыть PlayerBeliefModel ≠ NPC ToM: собственные убеждения NPC и убеждения о чужих убеждениях не смешивать.
- [ ] **PP-5** Second-order ToM: `A believes B believes X` — только после первого порядка и при доказанной необходимости.
- [ ] **PP-6** Prophecy / prediction vertical slice — после PP-1…PP-4.

### Фаза 2 — Эпоха 7: Predictive Perception & Prophecy (legacy roadmap; детализирована в Фазе 1.7)

- [ ] `docs/Почти Актуальные TZ/TZ_Stage_2_5_..._1.md` (Часть I) + `VZ/TZ_§19_Predictive_Perception_Dynamics.md` (surprise = −log P(x_t|z_{t-1})).
- [ ] `ObservationLayer/BeliefProjector` (P1-31) — унификация источников правды убеждений.
- [ ] Prophecy System (ADR-O-330), Vertical Slice «Секреты Люси — секреты таверны».

### Фаза 3 — Эпоха 8: Temporal Identity, линии времени

- [ ] `VZ/ТЕХЗАДАНИЕ ПРЕЕМНИКУ TZ-02 V.2.0` (WorldChronicle, 3 уровня времени), ADR-TIFL-001..003.
- [ ] `VZ/TEXTURES_AND_GEOMETRY_TZ.md` — visual aging (после lineage).

### Фаза 4 — Эпоха 9: Общество (Factions, Economy, Politics) + Memetic

- [ ] `VZ/TZ_MEMETIC_01..03` — меметический домен.
- [ ] Factions / Economy (`architecture/economy.yaml` есть, инженерного ТЗ нет) / Politics — ТЗ сформулировать.

### Фаза 5 — Эпоха 10: Bounded Rationality

- [ ] `VZ/TZ_§18_Resource_Bounded_Epistemic_Selection_Law.md` (`U_M = I·R·U − C`) — **только после** Belief Layer.

### Фаза 6 — Контент и презентация (когда угодно, изолированно)

- [ ] `ENIGMA_TZ_Female_Targeted_Dark_Fantasy_Layer.pdf`, `ENIGMA_MAP_EDITOR_SMART_VALIDATION.md`, `AWC_Process_World_Model_TZ.pdf` (Эпоха 11+, только дизайн), Narrative Frame Onboarding, Laboratoria Kalibrovki (полигон).

### Долг (не блокирует, брать паузами)

- [ ] God-файлы: `game_loop/__init__.py`, `life_engine.py`, `tick_orchestrator.py`.
- [x] ~~mypy --strict: 79 ошибок (`spatial_runtime.py`, `spatial_service.py`)~~ **✅ Исправлено** — mypy --strict: 0 ошибок в spatial-слоях (`spatial_runtime.py`, `spatial_service.py`, `graph_compiler.py`, `spatial_query_service.py`, `npc_state.py`). Было 79 каскадных ошибок, включая `bool()` в `npc_state.py` и `Dict[str, dict]` → `Dict[str, Dict[str, Any]]` в `graph_compiler.py`.
- [x] ~~`print()` → logger (76 вхождений)~~ **✅ Исправлено** — все 36 `print()` в `backend/app/main.py` заменены на `logger.info/error/warning` с корректным уровнем. Ruff-clean.
- [~] TODO/FIXME в доменном слое (`backend/app/domain/`) — 5 записей: context-aware intensity (v2), S28 enum IntentType, IntentSemanticField extension, DeathState backlog (2 TODO). Это backlog-маркеры будущей функциональности, а не баги — оставлены как есть.
- [x] ~~DEBT-IPT-RUFF: 24 pre-existing нарушения в `IPT.py`~~ **✅ Исправлено** — `ruff check IPT.py`: `All checks passed!` (F821 `os` :1129 — не ошибка, т.к. `import os` на строке 1115 внутри функции; 24 нарушения были устранены в предыдущей сессии).
- [ ] **DEBT-QUIESCE (async-interleaving недетерминизм)** — внешняя зона (async-слой/M1b-контур), НЕ косметика тестов. Симптом (S237): между идентичными OFF-прогонами варьируют пропорция COMPLETED/INTERRUPTED commitment-терминалов и микропозиции NPC (фоновые диффы {4,7} по 9 осям) при стабильных terminals_total/npc-set/world_objects. Влияние: A/B-гейты закрываются с ambient qualification (GORAN β G1 — прецедент S237). Будущее требование (вердикт Мастера): воспроизводимые причинные цепочки уровня «кража → наблюдение → вера → смена цели → перенос стула → сторожит» требуют execution/interleaving-детерминизм как ФУНДАМЕНТАЛЬНОГО слоя, не тестовой косметики — кандидат W-контура после стабилизации. Точка данных: latent TICK_CRASH npc_tick_pipeline:703 (active_commitments DOUBLE TRUTH) — interleaving-зависим.
- [ ] **DEBT-SLEEP-DELIVERY (доставка тел к кроватям)** — внешняя зона (spatial/behavioral; НЕ физиология — сон-машина верифицирована независимо: S235/S236). Симптом (S236, DriftLab 200 тиков × 6 NPC): elig=True = 0/1200 — тела не доезжают до кроватей при живом графе (смоук: kitchen_bed_1/2→BED) и целенаправленных данных: thief→city_gate:tent_3 (кросс-локационная цель; конфиг «не мигрирует»), borko→city_gate:guard_bed (кросс-локация), lusya→tavern:kitchen_bed_1 (валидная в-локационная цель; 129/129 сон-тиков no_bed — в моменты проверок в пути). Следствие без доставки: sleep_pressure→1.0, motor_output_mult→0 («мир недосыпа» — долгосрочное равновесие). Статус (вердикт Мастера): НЕ blocker Body Life; blocker качественного long-horizon сна в кампании Open_road. Решение — при spatial/affordance-контуре: intent → affordance search → reachable target → traversal → settled → физиологический переход (машина подхватит автоматически). Дизайн-вход Мастера (S236): «Тень тайно спит в подвале» — первый кандидат контент-фикса (activity_map/MapEditor или W2 sleep-affordance-типы BED→HAMMOCK/GROUND/SHELTER).


### §4a. Реестр долгов сессии AG1 (единый; префикс AG1-D; не разрозненный — это исполняемый реестр)

| ID | Долг | P | Зона/владелец | Действие | Статус |
|---|---|---|---|---|---|
| AG1-D1 | `V2RelationshipBackend` не имеет `_cache` → new_game reset падает | P1 | RE-01 M1b (чужая) | уведомление владельцу RE-трека в LAST_SESSION.md | [ ] |
| AG1-D2 | `Dialogue update failed:` — тихий глоток в подписчике диалогов (L4-нарушение) | P1 | AG1 | локализовать except → лог-гейт | [ ] |
| AG1-D3 | Witness-ветка reaction_subscriber:301–316 не под Gate-контрактом (только target-путь) | P2 | AG1 | обвязать Proposal/Gate по прецеденту E2.0-b | [ ] |
| AG1-D4 | `identity_traits` пусты после wait 12 — резонанс не доезжает (гейт DECAY_EVERY / RAM WorkingMemory / ключ) | P2 | AG1 | диагностический круг: 3 команды | [ ] |
| AG1-D5 | Аватар жив с hp=0 (`[FATE]`-лог каждый тик) | P2 | body (ADR-131-контур) | связать с E5/E12 | [ ] |
| AG1-D6 | Q4/Q5-рассинхрон имени модели (хвост S217) | P3 | LLM | `config`: одна строка | [ ] |
| AG1-D7 | `actor → player:` пустой хвост при imp=0.8 (producer теряет текст при непустом префиксе) | P2 | AG1 | трассировка producer-пути | [ ] |
| AG1-D8 | ADR-O-377 не в реестре атласа (cockpit-заглушка жива, production-план TaskScheduler не записан) | **P1** | AG1/cross | запись в атлас + IMPACT-файл + production-план | [ ] → **в работе, первый** |
| AG1-D9 | `affordance_facts_map`: гвард стоит, поле у W2-владельца не объявлено | P3 | W-track (чужая) | уведомление владельцу | [ ] |
| AG1-D10 | Ambient-шум в recall (canned-фразы наполняют кэш) | P3 | AG1/контент | Этап 1 (контентная важность) — план контура памяти | [ ] |
| AG1-D11 | Witness-fallback «телепатия» при пустых perceiving_npcs (реакция ВСЕХ NPC) | P2 | AG1/perception | известная графа perception_filter; проверить прод-путь | [ ] |

**Правило реестра:** долг без владельца и без следующего действия — запрещён (не «запомнить», а «кому и что»). Чужие зоны (D1, D9) — только уведомление, не чинить.

### §4b. Реестр долгов RE-сессии (M1b.3.x, 2026-09-0x; префикс RE-D)

| ID | Долг | P | Зона | Действие | Статус |
|---|---|---|---|---|---|
| RE-D1 | AG1-D1 сверка: reset_campaign переписан на RAM (M1b.4.2), `_cache` не существует — либо долг устарел, либо падение в другой точке | P2 | RE (моя) | прогон new_game при M1b.3.3 | [ ] |
| RE-D2 | DialogueUpdateExtractor нулевые дельты (`trust=+0.0` в живом логе; soliloquy-пары с нулями) — LLM-зависимый баг, диалоги НЕ пишут отношения | **P1** | dialogue/AG1 | трейс extractor→LLM→вес; кандидат отдельного досье | [ ] |
| RE-D3 | BeliefCrystallization: таргеты `npc=break_progress:resistance` (не npc_id) — кристаллизация от не-агентов, шум в L2.5 | P2 | identity | локализовать источник trait_drift source_id | [ ] |
| RE-D4 | FLEE-массовость: 6/6 NPC FLEE при fear=0.0 — поведенческий дисбаланс скоринга | P2 | decision/калибровка | зонд score-разложения FLEE | [ ] |
| RE-D5 | `game_loop/__init__.py`: 20 ruff pre-existing (F401×14, F821×4, W291) — чужие зоны, не чинить в RE-сессии (закон №15) | P3 | game_loop |god-file-декомпозиция (существующий долг) | [ ] |
| RE-D6 | scene_init W293×2 (:89/:366 докстринги) — pre-existing, тот же класс | P3 | scene_init | при следующей правке файла | [ ] |
| RE-D7 | Директива Мастера: каноническая схема campaign-bootstrap JSON (world/actors/facts/relationships/knowledge/motivations; CANON/INITIAL-разделение; «JSON описывает причины, не поведение»; секреты/beliefs/will — рантайм, не авторинг) — отдельный ADR после M1b.3.x | P2 | RE/authoring | ADR + схема | [ ] |
| RE-D8 | S135-статик decision_hub:166 = мёртвый путь (зовёт несуществующий get_relationship; state не имеет relationship_store) + social_deltas standalone-копия — finding 3.5-класс, судьба в M1b.3.5 | P2 | RE | зонд 3.5 | [ ] |

- Патч-формат: ТОЛЬКО БЫЛО/СТАЛО с фактическими якорями с диска (не paste-архив, не «описание словами» — обе формы дали каскадные красные в M1b.3.2); сигнатуры/тела сверять инспекцией перед выдачей.
---

## 5. MASTER TODO INVENTORY — все известные и возможные направления

Это не приказ делать всё сразу. Это полный реестр работ, разделённый на **сейчас / затем / потом / опционально**. `[ ]` означает незавершённое направление; приоритет задаётся тегом.

### A. СЕЙЧАС — блокирует качество причинной игры

- [ ] **A0** Закрыть RE-01 **M1b.3.3–3.7** (ратифицированная лестница, активный фронт): 3.3+3.4 единый разрез `build_npc_snapshots`-гидратация из V2 (decay = produce Δ над снапшотом, не трогать) → 3.5 flat-readers-зонд (3 находки в §4b RE-D8) → 3.6 S128-разделение (вердикт (а) получен) → 3.7 греб-страж allowlist. Затем **A1**.
- [ ] **A1** Закрыть RE-01 M1b.5: удалить мёртвый `apply_npc_state_updates` (0 вызовов, греп-доказательство) + судьба legacy-класса RelationshipStore и vestigial provider v2 (REMOVED/фасад по факту readers).
- [ ] **A2** Закрыть RE-01 M2/D: RelationshipEventSemantics + первый живой needs-writer через `update_needs` + формат RE-событий в causal-машинерии.
- [ ] **A3** Закрыть G/H: Satisfaction + frustration через canonical store.
- [ ] **A4** Закрыть K/removal-test и полигон M.
- [ ] **A5** Подтвердить Фазу 0 живой игровой сессией: decisions, player coordinates, traversal.
- [ ] **A6** Исправить/подтвердить DEBT-QUIESCE: детерминизм async interleaving для причинных цепочек.
- [ ] **A7** Исправить DEBT-SLEEP-DELIVERY: intent → reachable sleep target → traversal → settled → sleep.
- [x] **A8** ~~Проверить всех writers~~ **Writers закрыты (M1b.2 вечные инварианты: 0 writer'ов вне Gate; сетка D3; decay-архитектурно)**; readers — открытый фронт = A0 (fallback уже удалён 3.1; bootstrap 3.2). Остаток: греп-страж 3.7.
- [ ] **A9** Проверить persistence/replay для новых relationship/memory данных (V2 RAM→projection→atomic_commit; replay-determinism на RE-данных не гонялся).
- [ ] **A10** Сохранить IPT 45/45 + профильные линтеры после каждого изменения.

### B. СЛЕДУЮЩЕЕ — самый высокий gameplay ROI (фундамент E2.0 см. §2a)

- [ ] **B0** E2.0-c: каузальный экзамен A/B/C/D + ADR-O-377 в реестр (production-форма TaskScheduler). **Ворота для B1.**
- [ ] **B1** Experience → Conclusion (машино-пригодные триплеты `subject/predicate/object + confidence + evidence[]`, не фразы).
- [ ] **B2** Conclusion → Expectation.
- [ ] **B3** Expectation → existing DecisionHub.
- [ ] **B4** Repetition → generalization/crystallization.
- [ ] **B5** Contradiction → belief revision.
- [ ] **B6** Personal conclusion → testimony.
- [ ] **B7** Testimony → recipient belief with provenance/confidence.
- [ ] **B8** Derived social strategies: avoid/refuse/warn/seek/help/reconcile.
- [ ] **B9** Learning from another NPC: experience → knowledge/skill/rule → changed behavior.
- [ ] **B10** Self-model updates: «я могу/не могу», «я ошибся», «мне нужно изменить стратегию».
- [ ] **B11** Social triangle / reputation emergence.
- [ ] **B12** Long-horizon emergent scenarios and replay tests.

### C. ПСИХИКА — после B, без взрыва количества флагов

- [ ] **C1** Unified appraisal space.
- [ ] **C2** Derived emotion regions.
- [ ] **C3** Shared decay/accumulation/interference rules.
- [ ] **C4** Mood as recent appraisal field, not a second emotion database.
- [ ] **C5** Memory reactivation of affect.
- [ ] **C6** Emotion/action voting over available actions.
- [ ] **C7** Social contagion with distance/provenance/intensity bounds.
- [ ] **C8** Expression dictionary separated from causal state.
- [ ] **C9** Calibration laboratory + scenario corpus.

### D. PERCEPTION / EPISTEMICS

- [ ] **D1** ObservationLayer/BeliefProjector.
- [ ] **D2** Unified epistemic source-of-truth.
- [ ] **D3** First-order NPC beliefs about world/agents.
- [ ] **D4** Second-order ToM only where justified.
- [ ] **D5** Surprise/prediction error as measurable epistemic discrepancy.
- [ ] **D6** Belief revision with confidence, provenance and contradiction.
- [ ] **D7** Prophecy/prediction vertical slice.
- [ ] **D8** Epistemic persistence save/load.
- [ ] **D9** Replay determinism for epistemic chains.

### E. BODY / HOMEOSTASIS / EMBODIED AGENCY

- [ ] **E1** Needs writer via RE-01 M2/D.
- [ ] **E2** Energy/hydration/nutrition → fatigue → sleep → recovery.
- [ ] **E3** Pain/injury → affordance/constraint → action.
- [ ] **E4** Temperature and environmental pressure.
- [ ] **E5** Ensure body state is not flat/frozen in production snapshots.
- [ ] **E6** Intent → commitment → execution → verification.
- [ ] **E7** Stale intent cancellation.
- [ ] **E8** Single owner of behavior.
- [ ] **E9** Bounded conversation and cooldowns.
- [ ] **E10** Valid idle/settled state; eliminate perpetual movement/chat.
- [ ] **E11** Sleep delivery and alternative sleep affordances.
- [ ] **E12** Death/recovery semantics and remaining DeathState TODOs.

### F. WORLD / OBJECTS / AFFORDANCES

- [ ] **F1** W2 AffordanceResolver.
- [ ] **F2** W3 `transition_object` + causal writer.
- [ ] **F3** Caller guard / single writer for world objects.
- [ ] **F4** W4 embodied state: pose, locomotion, grasp, attachment.
- [ ] **F5** Objects become actionable affordances for NPC reasoning.
- [ ] **F6** Furniture/tasks/containers/resources integrated into action selection.
- [ ] **F7** W5–W9 presentation projector/rendering contracts.
- [ ] **F8** Renderer remains pure consumer.
- [ ] **F9** Object consequences enter Chronicle/Memory when semantically relevant.

### G. TIME / IDENTITY / LINEAGE

- [ ] **G1** WorldChronicle.
- [ ] **G2** Three time levels and consistency rules.
- [ ] **G3** Persistence across save/load.
- [ ] **G4** Identity continuity through long campaigns.
- [ ] **G5** Lineage/ancestry/ownership history.
- [ ] **G6** Visual aging after lineage.
- [ ] **G7** Historical consequences: old actions remain legible in current world.

### H. SOCIETY

- [ ] **H1** Factions.
- [ ] **H2** Reputation emerging from individual testimony + observed behavior.
- [ ] **H3** Economy.
- [ ] **H4** Politics/power relations.
- [ ] **H5** Institutions/roles/authority.
- [ ] **H6** Cooperation, coalition and exclusion.
- [ ] **H7** Social norms and norm violations.
- [ ] **H8** Sanctions/rewards/boycotts.
- [ ] **H9** Group-level memory without replacing individual memory.
- [ ] **H10** Population-scale stability: 50+ NPC × 30+ min.

### I. MEMETIC / CULTURAL

- [ ] **I1** MEMETIC-01.
- [ ] **I2** MEMETIC-02.
- [ ] **I3** MEMETIC-03.
- [ ] **I4** Beliefs/rumors mutate through transmission.
- [ ] **I5** Cultural norms emerge from repeated social reinforcement.
- [ ] **I6** Competing narratives and source credibility.

### J. BOUNDED RATIONALITY

- [ ] **J1** Belief Layer prerequisite.
- [ ] **J2** Information/resource/cost model `U_M = I·R·U − C`.
- [ ] **J3** Attention limits.
- [ ] **J4** Memory retrieval cost/selection.
- [ ] **J5** Action evaluation budget.
- [ ] **J6** NPC-specific rationality/resource limits.
- [ ] **J7** Validate that bounded rationality creates plausible mistakes rather than random stupidity.

### K. ACTIVE INFERENCE / HABITS

- [ ] **K1** Define the actual world model before adding heavy mathematics.
- [ ] **K2** Prediction → candidate futures → expected consequence → action.
- [ ] **K3** Habit formation from repeated successful action sequences.
- [ ] **K4** Habit decay/interference.
- [ ] **K5** Exploration vs exploitation.
- [ ] **K6** Information-seeking as an action.
- [ ] **K7** Performance benchmark; do not let active inference become the tick bottleneck.

### L. COUNTERFACTUAL / REFLECTION

- [ ] **L1** Store decision/outcome pairs sufficient for «what if».
- [ ] **L2** Counterfactual alternative generation.
- [ ] **L3** Regret / relief / guilt / confidence as derived appraisals, not flags.
- [ ] **L4** Counterfactual impact on future strategy.
- [ ] **L5** Bound computation so NPCs do not endlessly simulate futures.

### M. MEMORY / SELF / LEARNING

- [ ] **M1** EventMemory persistence.
- [ ] **M2** Belief persistence.
- [ ] **M3** Relationship persistence.
- [ ] **M4** Replay exactness after save/load.
- [ ] **M5** Memory salience and decay calibration.
- [ ] **M6** Consolidation: episodic experience → durable knowledge.
- [ ] **M7** Self-model / identity changes from experience.
- [ ] **M8** Skill/knowledge acquisition from social teaching.
- [ ] **M9** Forgetting that is selective, not arbitrary.
- [ ] **M10** False/uncertain memory only if epistemic design requires it.

### N. DIALOGUE / LANGUAGE / EXPRESSION

- [ ] **N1** DialogueQueue production-path audit/closure.
- [ ] **N2** SpeechScheduler pacing/dedup in actual main path.
- [ ] **N3** LLM timeout/cancellation so one hung call cannot block execution.
- [ ] **N4** Preserve proposition on DialogueRequest failure; no silent dict fallback.
- [ ] **N5** Dialogue grounded in actual belief/memory/relationship state.
- [ ] **N6** NPC can disagree with its own prior statement when belief changes.
- [ ] **N7** NPC can cite source/provenance («я видел», «мне сказал X»).
- [ ] **N8** NPC can deliberately withhold information.
- [ ] **N9** NPC can lie/deceive when world/social conditions justify it.
- [ ] **N10** Expression varies by personality/appraisal without changing causal truth.

### O. ACTION / SOCIAL BEHAVIOR

- [ ] **O1** Rich action vocabulary: approach, leave, refuse, help, accuse, warn, gossip, reconcile, negotiate, teach, learn, observe, hide, trade, defend, betray.
- [ ] **O2** Affordance-based fallback when preferred action unavailable.
- [ ] **O3** No hardcoded emotion→action rules.
- [ ] **O4** Action selection accounts for opportunity, distance, risk, allies and relationship.
- [ ] **O5** Social actions create consequences that feed memory/relationship.
- [ ] **O6** NPC recognizes when another NPC is talking to someone else / unavailable.
- [ ] **O7** Turn-taking, attention and conversational ownership.
- [ ] **O8** Spatial/social awareness: who is present, who can hear, who can intervene.
- [ ] **O9** Persistent refusal/avoidance should emerge from expectations, not flags.

### P. HARDENING / QUALITY / PERFORMANCE

- [ ] **P1** DEBT-QUIESCE.
- [ ] **P2** Remaining god-file decomposition.
- [ ] **P3** mypy --strict outside spatial layers.
- [ ] **P4** Remaining TODO/FIXME classification.
- [ ] **P5** Kernel RNG audit.
- [ ] **P6** wall-clock audit.
- [ ] **P7** silent-failure audit.
- [ ] **P8** frontend-isolation audit.
- [ ] **P9** L1 append-only audit.
- [ ] **P10** Epistemic boundary audit.
- [ ] **P11** Replay determinism.
- [ ] **P12** 1000-tick LLM-free survival test.
- [ ] **P13** Long-horizon drift tests.
- [ ] **P14** Performance budget for 6/50/100+ NPC.
- [ ] **P15** Memory growth / compaction strategy.
- [ ] **P16** Async cancellation / executor saturation.

### Q. CALIBRATION / OBSERVABILITY

- [ ] **Q1** Scenario corpus for body/social/epistemic behavior.
- [ ] **Q2** Differential tests for one causal change.
- [ ] **Q3** DriftLab 200/1000/10000 tick profiles.
- [ ] **Q4** Social chain traces with provenance.
- [ ] **Q5** Separate «mechanism works» from «content is good».
- [ ] **Q6** Metrics that detect living behavior without confusing motion with causality.
- [ ] **Q7** Never allow observability to mutate state.

### R. CONTENT / WORLD DESIGN

- [ ] **R1** Tavern vertical slice with meaningful tasks.
- [ ] **R2** NPC schedules and role obligations.
- [ ] **R3** Food/resources scarcity.
- [ ] **R4** Furniture/object affordances.
- [ ] **R5** Secrets and social consequences.
- [ ] **R6** Relationships with asymmetric preferences.
- [ ] **R7** Teaching/learning scenes.
- [ ] **R8** Betrayal/reconciliation scenarios.
- [ ] **R9** Reputation/social exclusion scenarios.
- [ ] **R10** Long-lived NPC stories.
- [ ] **R11** Campaign/world onboarding.
- [ ] **R12** Dark-fantasy/female-targeted layer if product direction remains.

### S. TOOLING / SDK / EDITOR

- [ ] **S1** Map Editor smart validation.
- [ ] **S2** Visual design of social graphs.
- [ ] **S3** Visual design of factions/relationships.
- [ ] **S4** Visual design of world affordances.
- [ ] **S5** Campaign/content SDK.
- [ ] **S6** Scenario runner for social experiments.
- [ ] **S7** Replay/trace viewer.
- [ ] **S8** Calibration dashboard.
- [ ] **S9** Authoring tools for secrets, norms, jobs and relationships.

### T. UI / PRESENTATION

- [ ] **T1** PresentationProjector.
- [ ] **T2** Renderer pure-consumer compliance.
- [ ] **T3** Player goal overlay.
- [ ] **T4** Journal tabs and temporal/social history presentation.
- [ ] **T5** Exit-tavern/modal flow.
- [ ] **T6** Name recognition pacing.
- [ ] **T7** NPC movement speed / readable staging.
- [ ] **T8** Make social consequences observable without exposing hidden variables.

### U. ОТЛОЖИТЬ — намеренно не делать пока

- [ ] Полноценный Active Inference как отдельный тяжёлый engine.
- [ ] Counterfactual reasoning.
- [ ] Большую Theory-of-Mind систему второго порядка.
- [ ] Политическую симуляцию высокого уровня.
- [ ] Полный economy simulation.
- [ ] SDK до стабилизации world/relationship contracts.
- [ ] Массовую оптимизацию до появления реального bottleneck.
- [ ] Новые десятки эмоций как отдельные классы.
- [ ] «Любовь», «влюблённость», «адаптация», «месть» как state entities без anti-Bond доказательства.
- [ ] Контентный взрыв до замыкания причинных циклов.

### V. ДОПОЛНИТЕЛЬНЫЕ ДОЛГОСРОЧНЫЕ ВОЗМОЖНОСТИ

- [ ] **V1** Group emotions / crowd dynamics.
- [ ] **V2** Collective memory / traditions.
- [ ] **V3** Reputation markets / information brokers.
- [ ] **V4** Institutional memory.
- [ ] **V5** Generational knowledge transfer.
- [ ] **V6** Language/cultural drift.
- [ ] **V7** Emergent norms and taboo formation.
- [ ] **V8** Multi-agent coalition formation.
- [ ] **V9** Resource-driven social stratification.
- [ ] **V10** Historical causality over months/years of simulation.
- [ ] **V11** NPC-specific life projects and legacy.
- [ ] **V12** World-level narrative emergence from distributed memory.

### Рекомендуемый порядок из всего MASTER TODO

`A1–A10 → B1–B12 → C1–C9 + D1–D9 → E/F hard runtime → G → H/I → J/K → L → M/N/O enrichment → P/Q hardening at scale → R/S/T content/tooling → V long-horizon`.

Ключевой принцип: **не строить систему для названия явления, если уже существует более общий механизм, из которого явление может быть выведено.**

---

## 6. Гейты и Stop-criteria

| Переход | Stop-criteria (все ✅) |
|---------|------------------------|
| Фаза 0 → 1 | Симуляция жива: decisions > 0 стабильно ×3 сессии · tracebacks ~0 · SHI=100% честно (перепроверено по `scene_changes_*.jsonl`) · IPT 45/45 |
| Фаза 1 → 2 | RE-01 M2/D зелёный · RelationshipWriteGate покрывает 100% writers · линтер `lint_relationship_engine.py` в CI · Replay exact-match |
| Фаза 2 → 3 | §19 surprise измеряется · Prophecy green · Vertical Slice играбелен |
| Фаза 3 → 4 | WorldChronicle persistence green · 3 времени консистентны |
| Фаза 4 → 5 | 50+ NPC × 30+ мин стабильно |
| Фаза 5 → 6 | §18 активен после Belief Layer |

### Красные флаги — STOP

1. DNA врут (SHI=100% при неподвижных NPC) → проверять по jsonl-логам.
2. `PlayerBeliefModel` ≠ NPC ToM (нужен second-order BELIEVES).
3. `MockProvider` в production-пути.
4. Observability мутирует state.
5. §18 до Belief Layer.
6. Version desync (`version.txt` ↔ `pyproject.toml` ↔ frontend-константы).
7. `random.*`/`time.time()` в kernel-слое.
8. **(новый)** Writer потребностей/отношений в обход `RelationshipWriteGate` / `update_needs` — прямая мутация RelationshipStateStore запрещена (single-writer, caller-guard).
9. **(новый)** Фронтенд/симуляция читает состояние из renderer — Architectural Violation (W-TRACK контракт).
10. **(новый)** Введение состояния-сущности для «идеализация/влюблённость/адаптация» без anti-Bond теста (Р17-П1).


---

## 7. Quick recovery — если зашёл в тупик

| Симптом | Что делать |
|---------|------------|
| 0 decisions/tick (симуляция заморожена) | `backend/app/services/npc/decision_hub.py` — веса решений, связь с RelationshipStore/WriteGate; `git log` на недавние писатели |
| LLM молчит | `backend/logs/cds_session_*.log`; `scripts/llm_server_manager.py`; LOG-GATE-UI на splash |
| `movement_traversal ⏸` | `local_traversal_planner.py` + `traversability_evaluator.py` + `geometry_kernel.py` |
| IPT падает | какой инвариант красный в `IPT.py`; профильные линтеры `scripts/lint_*.py` |
| Регрессия, непонятно где | `git bisect`; marker — `pytest backend/tests/canary/test_full_playthrough.py` |
| Сломан контракт RE | `scripts/lint_relationship_engine.py` + `architecture/relationship_engine.yaml` |
| Сломан WORLD-контракт | `backend/tests/test_world_object_topology.py` + `architecture/world.yaml` |
| Version desync | `version.txt` + `pyproject.toml` + frontend-константы синхронизировать |

---

## 8. Ресурсы и ключевые файлы кода

| Подсистема | Файл (проверено) |
|------------|------------------|
| Tick pipeline | `backend/app/core/tick_orchestrator.py` |
| DecisionHub | `backend/app/services/npc/decision_hub.py` (переехал из `cognition/`) |
| DM-agent | `backend/app/agents/dm_agent.py` (переехал из корня `app/`); фаза DM — `backend/app/services/game_loop/dm_phase.py` |
| Dialogue | `backend/app/dialogue/dialogue_router.py`, `backend/app/services/verbalization/` |
| Relationship Engine v2 | `architecture/relationship_engine.yaml`; стор/gate — см. `git show 73e0539f` (RelationshipWriteGate), `53183000` (адаптер), `17930e9f` (RelationshipStateStore) |
| WORLD-домен | `architecture/world.yaml`, WorldObjectStore (ADR-O-371) |
| Movement/Spatial | `backend/app/services/spatial/` (`spatial_service`, `spatial_runtime`, `spatial_query_service`, `graph_compiler`) — **mypy --strict: 0 ошибок** (было 79 каскадных из npc_state.py, graph_compiler.py, spatial_query_service.py) |
| Impact/Physiology | `backend/app/services/combat/impact_engine.py`, `backend/app/domain/vital_state.py` |
| Kernel RNG | `backend/app/core/kernel_rng.py` |
| Tests (IPT) | `backend/tests/IPT.py` (45/45, Ruff clean: `All checks passed!` — 24 pre-existing нарушения устранены) |
| Canary | `backend/tests/canary/test_full_playthrough.py` |
| Lint-гейты | `scripts/lint_*.py` (13 линтеров) |
| LLM-менеджер | `scripts/llm_server_manager.py` |
| Session data | `backend/data/logs/scene_changes_*.jsonl`, `reports/dna_history.jsonl` |
| Architecture YAML | `architecture/*.yaml` (23 файла: authority, body_topology, calibration, economy, frontend, identity, input, memory, perception, physiology, pipeline, player_cognition, relationship_engine, spatial, state, temporal, verbalization, world, ...) |

---

**Документ завершён. Фактический следующий шаг (два параллельных фронта): (1) AG1: E2.0-c каузальный экзамен → BC-1 Conclusion (триплеты, не фразы) — §2a; (2) RE-01 M1b.5 → M2/D → causal hardening/DEBT-QUIESCE. Сходятся в Фазе 1.5: Experience→Conclusion→Expectation→Decision→Experience и Social Testimony. После доказательства этого контура — Unified Appraisal/«палитра эмоций» и Predictive Perception. Active Inference, Counterfactual, Society/SDK и масштабирование — позже. MASTER TODO в §5 является полным реестром, а не последовательностью немедленной реализации. Реестр долгов сессии AG1 — §4a (не блокирует, но не оставлять без присвоенного владельца).**
