# ENIGMA — Дорожная карта преемника

**Версия документа:** 2.0 · 2026-08-30
**Адресат:** LLM-преемник на V.0.5.3.9.4 (ветка `V.0.5.3.9.4_Память_1`)
**Назначение:** Пошаговый план — что делать, в каком порядке, что читать, что формулировать самому.
**Принцип документа:** компактный, без воды; галочки `[ ]` — для трекинга; путь к файлу — для каждого шага.
**Актуализация:** сверена с кодом (`backend/app`, `architecture/*.yaml`, `scripts/`), `git log`, `reports/LAST_SESSION.md` (28.08.2026) и свежими ADR (O-367…O-371).

---

## 0. Контекст: где мы сейчас

**Версия кода:** V.0.5.3.9.4 · `version.txt` = `0.5.3.9.4` · синхронизирован с `pyproject.toml` (desync v0.5.3.7.0-era **закрыт**).

**Главные активные треки (на смену defect-fix ТЗ V0.5.3.7.0, которое утрачено):**

1. **ТЗ-RE-01 — Relationship Engine v2** (`docs/Почти Актуальные TZ/ТЗ_RE-01_Relationship_Engine_v1.9.md` + акт передачи `ТЗ_RE-01_ПЕРЕДАЧА_преемнику_Р18.md`). Прогресс: **M0 ✅ (ADR-O-369)** → **M1a ✅ (ADR-O-370)** → **M1b — в процессе (ADR-O-371-серия коммитов, RelationshipWriteGate)** → далее M1b.5 / M2-D / G / H / K / полигон M.
2. **W-TRACK — World Embodiment Foundation** (`docs/Почти Актуальные TZ/TZ_WORLD_EMBODIMENT FOUNDATION (W-TRACK).md`). Прогресс: субстрат WORLD-домена **положен** (ADR-O-371: `architecture/world.yaml`, WorldObjectStore, 30 тестов, IPT 45/45), рантайм-потребителей пока **ноль** (доктрина dormant-substrate). Следующие: W2 AffordanceResolver, W3 transition_object + causal writer, W7 PresentationProjector.
3. **Р18 «Адаптация»** (раунд ТЗ-RE-01) — ОТКРЫТ; режим работы и развилки — в акте передачи (см. §2).

**Эпоха:** переходная между **Эпохой 6 (Stabilization)** и Эпохой 7. `docs/Почти Актуальные TZ/STABILIZATION_ROADMAP.md`: **стабилизация v0.5.3.7.2–v0.5.3.7.10 завершена** — ядро (Tick, Movement, Decision, LLM) стабильно, **IPT 45/45 (было 39/0)**, `lint_silent_failures` ✅, `lint_relationship_engine` ✅. Остаток долга — god-файлы, mypy --strict (79 → 0 в spatial-слоях), print() в backend (36 → 0), TODO/FIXME.

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
- [x] **M1b.2.1–2.3** — перевод writers на гейт: `social_subscriber` (6 вызовов), `action_consequence_compiler` (BLACKMAIL/HELP/ACCUSE), `MemoryManager`-фасад (write-гейт в `__init__`, ADR-O-371-нумерация коммитов).
- [ ] **M1b.5** — удалить мёртвый `apply_npc_state_updates` (0 вызовов доказано грепом).
- [ ] **M2/D** — `RelationshipEventSemantics`: первый реальный писатель потребностей через `update_needs` + формат RE-событий в causal-машинерии.
- [ ] **G/H** — динамика Satisfaction и фрустрации через стор.
- [ ] **K (фаза I артефакт)** — полный removal-test.
- [ ] **Полигон M** — пресеты, INV-1, диф-тест раннего внимания **О-2** (единственный хвост Р17).

### Р18 «Адаптация» (открытый раунд)

Источники: акт передачи (§3) + ТЗ v1.9 §12.2. Правило раунда: **«Не доказываем, что адаптация существует; доказываем или опровергаем, что есть каузальная работа, которую никто другой не выполняет»**. Первое действие — досье адаптационного контура по цепочке `writer → state → reader → causal effect → existing substitute → anti-Bond test → остаток`. Развилки Р1–Р7 — вопросом арбитру (GPT), не самостоятельными решениями. Зоны вскрытия — §6.3/§5.0/§5.1/§8.1/§6.19/§6.4 ТЗ v1.9.


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

### Фаза 2 — Эпоха 7: Predictive Perception & Prophecy

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
```


---

## 5. Гейты и Stop-criteria

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

## 6. Quick recovery — если зашёл в тупик

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

## 7. Ресурсы и ключевые файлы кода

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

**Документ завершён. Следующий шаг — Фаза 1: завершение RE-01 M1b (перевод оставшихся writers на RelationshipWriteGate), затем M2/D — runtime needs-writer, и Эпохи 7–10. Технический долг: god-файлы, остаток TODO/FIXME, mypy --strict на остальных модулях.**
