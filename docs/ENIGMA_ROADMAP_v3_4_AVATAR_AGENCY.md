# ENIGMA — Дорожная карта преемника

**Версия документа:** 4.0 · **Код:** V.0.5.4.2.5 (`version.txt` = `pyproject.toml`) · **Ветка:** main · **Базлайн:** IPT 49/49
**Правило документа:** один факт — одно место. Статус пункта живёт в чеклисте трека; история (нарратив сессий, инциденты, вердикты) — только в `MUTATIONS.md` + `docs/audits/`. Этот документ — операционная карта, не архив.

## Как читать этот документ

1. **§0** — текущее состояние и порядок действий. Начинай здесь.
2. **§1–§8** — архитектурные контракты и открытые направления.
3. **§9** — как доказывается закрытие (методология L0–L4, GAMEPLAY CLOSURE).
4. **§10** — журнал фактических прогонов.
5. **`MUTATIONS.md`** — архив закрытых изменений; **`docs/audits/ADR-*_IMPACT.md`** — обоснования решений.
6. Если код противоречит roadmap — сначала проверяются код/тесты; roadmap не считается доказательством (§13.5 Устава).
7. Иерархия очередей: **§0.2 = что делать сейчас; §8 = какие направления существуют вообще.** §8 — не вторая очередь.

---

## 0. Где мы

### 0.1. Карта треков

| Трек | Закрыто (канон) | Следующий шаг | Канон-ADR |
|---|---|---|---|
| **RE-01 Relationship Engine v2** | M0 → M1a → M1b.0–4 (физический cutover RAM-authoritative) → M1b.3.1–3.4 (S246) | M1b.3.5–3.7 → **GC-11** → M1b.5 → M2/D | O-369/370/371 |
| **W-TRACK World Embodiment** | W1 → W2 → W3+G1 (S237) → G2 (S239) → **G3** (S307, W3_G3_ENABLED default OFF) | object-cognition **CAN_STEAL≠ACCEPT/WANT** + capability `spawn_world_object` → **GC-08**; reusable-паттерн TAKE/USE/MOVE/GIVE/FOLLOW | O-371/372/376/378/410 |
| **AG1: Understanding & Epistemics** | Фаза A → E1 (шина опыта) → E2.0-a/b (DeltaGate) → E2.0-c B0-CLOSED (S243) → **BC-1** (S247, dormant default OFF) | **BC-2** (Conclusion→Expectation) | O-377/379/380/381 |
| **Understanding / Name-Gate** (вне классических треков) | R8 affection (S303/O-413) · Attention→Action (S304) · Understanding Pipeline (S305) · Name-Gate FACE/NAME/LINK (S306, S308/O-409) · S2B.7 Pain/Injury (S309) | интеграция в контуры §3/§5; далее по потребности | O-409/413 |
| **Body / Embodied** | GC-09A ✅ (Body Runtime) → GC-09B RED = находка (State Consumer Gap, выборка 2) → **ADR-O-383 V1** ✅ (pressure_translator, availability-тракт) | калибровка chronic-veto; D-MOM (motor_output_mult — orphaned consumer); sleep-семантика — отдельно | O-383 |
| **Р18 «Адаптация»** | — (открытый раунд) | досье контура по цепочке writer→state→reader→causal effect→substitute→anti-Bond (акт передачи §2) | — |
| **HUMOR / PLAY** | — (план §6) | только после Expectation + Appraisal + Prediction Error | — |

Стабилизация ядра v0.5.3.7.x завершена (STABILIZATION_ROADMAP); история эпох — `docs/ENIGMA_EPOCHS_REPORT.md`.

### 0.2. Сквозная очередь работ (каноническая)

> **§0.2 — единственная каноническая очередь.** Задача, не указанная здесь и не являющаяся prerequisite для её ступеней, требует от архитектора сначала доказать, почему её нужно менять. Полный реестр направлений — §8 (справочник, не очередь).
>
> Правила: (1) сверху вниз; (2) параллельные сессии — по трекам с Anti-Race Protocol (§11.1.1 Устава); (3) 🔴 инварианты живого IPT-прогона всегда раньше очереди (LAST_SESSION.md — только если последняя сессия завершалась запуском игры; headless-разработка его не обновляет); (4) ступень = контрактный гейт + линтеры + IPT + запись в MUTATIONS; (5) закрытие стадии с назначенным acceptance-обязательством — по §9 (реестр привязок §9.9).

**Инструмент сессий (S314, 4041294e):** F5-лаборатория = microscope над production (ExperimentRunner → build_game_loop → idle_tick; temp-saves + MockProvider + ObservabilityTap; рычаг начальных состояний `npc_overrides.social` — canonical WriteGate; headless-прецедент `backend/tests/sandbox/lab_r001_clone_differential.py`). Назначение: GC-11, причинные верификации, калибровки. Отдельные ad-hoc probe не писать.

**Ступень 1 — RE-01: закрыть M1b (активный фронт)**
- [x] M1b.3.5 — flat-readers-зонд закрыт S314 (SHA 4041294e): статика + runtime P1–P6 + лаборатория R001; GAP-1 = 1A Store→cache 🟢 prod / 1B cache→reader 🟢 unit (reader починен) / 1C activation 🔴 NOT BUILT (хвост §3); вход M1b.3.6 — вердикт-матрица
- [ ] M1b.3.6 — S128-разделение по вердикту зонда
- [ ] M1b.3.7 — греп-страж allowlist (кэш-чтения только рендер-проекциям)
- [ ] **GC-11 (L3-gate, обязателен до M2/D):** event → V2-RAM non-zero delta → следующий выбор NPC сдвинут (живой harness; ловит RE-D2-класс нулевой игровой реальности, недоказуемой юнит-сьютой)
- [ ] M1b.5 — удалить мёртвый `apply_npc_state_updates` (0 вызовов, греп-доказательство) + судьба legacy `RelationshipStore` (AUD-D5: wall-clock TTL, тихий `{}`, legacy JSON)

**Ступень 2 — RE-01: M2/D → G/H → K → Полигон M**
- [ ] M2/D — `RelationshipEventSemantics`: первый живой needs-writer через `update_needs` + формат RE-событий (попутно закрывает хвост Фазы 0.6/NEI)
- [ ] G/H — динамика Satisfaction и фрустрации через стор
- [ ] K — полный removal-test
- [ ] Полигон M — пресеты, INV-1, диф-тест раннего внимания О-2 (последний хвост Р17)

**Ступень 3 — Р18 «Адаптация»** (после M2/D либо параллельно; досье не трогает рантайм)
- [ ] Досье контура; развилки Р1–Р7 — арбитру (GPT), не самостоятельно

**Ступень 4 — AG1: эпистемический контур** (может идти параллельно Ступени 2)
- [ ] **BC-2** Conclusion→Expectation: мини-ADR на открытие моста CONCLUSION→EXPECTATION (ADR-O-381 F3а) + BC1_ENABLED ON + потребитель ExpectationStore; DeltaGate-тропа, provenance, causal parent
- [ ] BC-3 — Expectation → Decision (без action-флагов; full-cell GC-04)
- [ ] BC-4 — Repeated evidence → Generalization
- [ ] BC-5 — Personal experience → Social testimony
- [ ] BC-6 — Testimony → Recipient belief
- [ ] BC-7 — Conclusion → social strategy (derived, без флагов NPC)
- STOP: полноценный Active Inference — только после BC-1…BC-7. BC-8…BC-13 — после устойчивого контура (§3).

**Ступень 5 — W-TRACK: следующий слой**
- [ ] Capability `spawn_world_object` для GC-08-harness (инфраструктурный prerequisite, канон §9.2)
- [ ] Object-cognition: CAN_STEAL ≠ ACCEPT/WANT (находка Мастера на G3)
- [ ] Reusable-паттерн объектных действий: TAKE/USE/MOVE/GIVE/FOLLOW
- [ ] W4 — точечно при доказанной W2-потребности (CAN_GRIP для TAKE); гейт §ENIGMA-002
- [ ] W5–W9 — только контракты + PoC

**Ступень 6 — MATH-01** (точечно, не блокирует 1–4)
- [ ] MATH-2 — сон→восприятие (исполнение ADR-O-356 Phase E.0)
- [ ] MATH-3 — эпистемическое остывание (координация с M2/D)
- [ ] MATH-4 — C-пластичность (после устойчивого BC-контура; mini-ADR + Lab)
- [ ] Остальные — по ТЗ §6

**Ступень 7 — Фазы будущего (строгий порядок)**
- [ ] EM-1…7 Unified Appraisal → [ ] PP-1…7 Predictive Perception → [ ] HUM-00…10 (§6)

**Постоянный хвост** (живой сессией, в любой момент)
- [ ] Фаза 0.4 — arbiter INCUMBENT на ⏸ traversal — подтвердить живой сессией; 0.5 — player-координаты (закрыты в кокпите, прод-проверка)
- [ ] Открытые хвосты §7 с владельцем (FT-2, AI-D1, ST-1, PH-1, SC-1, AUD-D*)
- [ ] G3-инфраструктура — при планировании Ступени 5

### 0.3. Истины и принципы

**Пять архитектурных истин:**
1. **Truth = Snapshot + Chronicle.** State эфемерен, Identity — append-only. Асимметричная онтология, не баг.
2. **Time & Physics — одно.** Разрешаются только в Causal Kernel.
3. **No Event Sourcing for State, но yes for Identity.** State — snapshot, Identity — L1Chronicle (SQLite append-only).
4. **Symptom ≠ Cause.** Чини pipeline node, не UI.
5. **Vacuum = local rupture, not global zero.** Unknown ≠ Neutral 0.0.

**Шестая (эпоха RE-01): «Паттерн, не субстанция»** (Р17-П1) — человеческие категории («идеализация», «влюблённость», «адаптация») не вводятся как состояния-сущности; каждая проходит **anti-Bond тест**: доказывается каузальная работа, которую никто другой в ENIGMA не выполняет, иначе — derived-операция.

**Принципы работы:**
- Один фикс → один коммит → один тест. Не пачками.
- CI-гейты обязательны: `ruff` + IPT (`python backend/tests/IPT.py 2>&1 | Select-Object -Last 10`; сейчас 49/49) + профильные линтеры `scripts/lint_*.py`.
- Observability **never mutates**.
- DNA-метрики могут врать — перепроверяй через `backend/data/logs/scene_changes_*.jsonl`.
- `MockProvider` в production-пути запрещён.
- `random.*` и `time.time()` в kernel-слое запрещены → `KernelRNG(tick, npc_id, salt)`. Осторожно: паттерн `rng or random` за Optional-дефолтом невидим линтеру (rng-бомба, §7).
- Файловые runtime-логи гейтятся `ENIGMA_DISABLE_FILE_LOGS` (LOG-GATE).
- Режим RE-01: **GPT задаёт направление, преемник вскрывает факты до решений и спрашивает по каждой развилке.**

**Отложено намеренно (не предлагать как работу):** полноценный Active Inference как тяжёлый engine · counterfactual reasoning · second-order ToM система · политическая симуляция высокого уровня · полный economy simulation · SDK до стабилизации world/relationship контрактов · массовая оптимизация до реального bottleneck · десятки новых эмоций как классы · «любовь/влюблённость/адаптация/месть» как state entities без anti-Bond · контентный взрыв до замыкания причинных циклов.

---

## 1. Карта документов

### 1.1. Существуют и актуальны (проверено Test-Path 2026-08-30; при сомнении — перепроверь)

| Документ | Роль |
|---|---|
| `docs/Почти Актуальные TZ/ТЗ_RE-01_Relationship_Engine_v1.9.md` (1972 строки, аудит 40/40) | Канонический ТЗ RE v2: аксиомы §3, запреты §7, устав §12.2 |
| `docs/Почти Актуальные TZ/ТЗ_RE-01_ПЕРЕДАЧА_преемнику_Р18.md` | Передаточный акт: режим работы, роадмап (а)→(г), развилки Р1–Р7 |
| `docs/Почти Актуальные TZ/TZ_WORLD_EMBODIMENT FOUNDATION (W-TRACK).md` | Часть II Stage 2.5: WORLD→EMBODIED→PRESENTATION→RENDERING, этапы W0–W9 |
| `docs/Почти Актуальные TZ/STABILIZATION_ROADMAP.md` | Вердикт по стабилизации (закрыта); остаток долга — god-файлы, mypy, print(), TODO |
| `docs/ENIGMA_EPOCHS_REPORT.md` | Карта Эпох 1–10 (источник прогресса; отстаёт — на v0.5.3.7.8) |
| `docs/Почти Актуальные TZ/RemontTZ/*.md` (6 файлов) | Мастер-ТЗ на ремонт доменов — историческое, большинство фиксов применено |
| `docs/Почти Актуальные TZ/VZ/*.md` (7 файлов: §18, §19, MEMETIC 01–03, TZ-02, TEXTURES) | Будущие эпохи 7–10 |
| `docs/Почти Актуальные TZ/TZ_Stage_2_5_Temporal_Causality_Predictive_Runtime_1.md` | Temporal causality / predictive runtime (Часть I; W-TRACK — его Часть II) |
| `docs/Почти Актуальные TZ/1_TZ_Architect_Enigma_V0_5_3_8_2.md` (+ Parts 2–4, `1_TZ_Стадия_2.md`) | Архитектурные ТЗ волны 0.5.3.8.x |
| `PSY-ARCH-01_Unified_Psychological_Dynamics.md`, `TZ_Laboratoria_Kalibrovki_ENIGMA.md`, `Plan_Razrabotki_Laboratorii.md` | Психологическая динамика и калибровочная лаборатория (M0-полигон ADR-O-367 жив) |
| `ENIGMA_LLM_PIPELINE_TZ_v1.md`, `ENIGMA_MAP_EDITOR_SMART_VALIDATION.md`, `ENIGMA_TZ2_v2_Narrative_Frame_Onboarding.md`, `ТЗ ENIGMA WORLD-CENTRIC SPATIAL ARCHITECTURE.md` | Периферийные ТЗ (по мере надобности) |
| `docs/audits/ADR-*_IMPACT.md` (+ атлас `docs/ADR (Architecture Decision Records).md`) | Детальные аудиты решений; атлас — единый индекс (130+ файлов) |
| `reports/SESSION_S62_DM_VISION.md`, `reports/LAST_SESSION.md` | Сессии |

### 1.2. Утрачены (ссылки из v1.0 роадмапа невалидны — не искать, не восстанавливать)

- `upload/ENIGMA_TZ_V0.5.3.7.0.md` — папки `upload/` нет; defect-каталог отработан STABILIZATION_ROADMAP.
- `docs/Почти Актуальные TZ/ENIGMA_TZ_INFRASTRUCTURE.md` — нет в репо.
- `docs/Почти Актуальные TZ/ENIGMA_SELF_HEALING_SYSTEM.md` — нет в репо.
- `S1_INPUT_TRACE_IMPLEMENTATION.md`, `INPUT_OBSERVATORY_ROADMAP_S2_S6.md` — нет в репо.

---

## 2. Трек RE-01 — Relationship Engine v2

Источники: ТЗ v1.9 + акт передачи (§1.1). Линтер: `scripts/lint_relationship_engine.py` (CI + pre-commit).

### 2.1. Чеклист фаз

- [x] **M0** (ADR-O-369) — онтологический контракт: `architecture/relationship_engine.yaml` (45 узлов, 20 событий, 6 предикатов, запреты №1–35). Рантайм не тронут.
- [x] **M1a** (ADR-O-370) — субстрат: `RelationshipStateStore` (scene_state-backed), контракты NeedSlot/PreferenceModel/HardConstraint, `StateApplicator.update_needs` (single-writer, caller-guard). 28 тестов.
- [x] **M1b.0** — `RelationshipWriteGate` (whitelist 5 скаляров, NaN/foreign-key guard) + D3-паритет против legacy `update()`.
- [x] **M1b.1** — миграционный адаптер legacy→v2 (детерминированный, идемпотентный, 9 приёмочных тестов).
- [x] **M1b.2** — гейт + D3-сетка 8×8×5; все 6 write-маршрутов через гейт; semantic gate §8.6 (комплимент — одна направленная запись); вечные греп-инварианты (ноль writer'ов вне гейта).
- [x] **M1b.4** (S234) — физический cutover: `V2RelationshipBackend`, RAM = runtime authority; сцена = persistence projection; disk-on-update запрещён; lazy/late-bind + hydrate; legacy JSON заморожен. Сьюта 194.
- [x] **M1b.3.1** — fallback DecisionHub удалён (обе ветки); кэш = projection-only; Vacuum каноничен; V2-`get` легаси-формат (стрелочные ключи — ридер был слеп).
- [x] **M1b.3.2** — bootstrap → RAM: `bootstrap_from_npc_dicts` (только 5 скаляров; existing-RAM-wins) + npc_provider lazy-bootstrap (закрыт второй прод-путь idle/resume; зонд 0→21/22 ненулевых пар). Сьюта 202.
- [x] **M1b.3.3+3.4** (S246) — единый разрез: `build_npc_snapshots(+relationship_store, +campaign_id)` — кэш-слой снапшота = проекция V2; decay-хендлер не тронут (produce Δ). Сьюта 205, канар жив. Урок: юнит-зелёный ≠ интеграционная истина — гейт = живой зонд.
- [x] **M1b.3.5** (S314, 4041294e) — зонд исполнен: статика + runtime P1–P6 + F5-лаборатория R001 (создан рычаг npc_overrides.social через canonical WriteGate); GAP-1: 1A 🟢 / 1B 🟢 (reader nested-read починен) / 1C 🔴 NOT BUILT; M1b.3.6 — по вердикт-матрице.
- [ ] **M1b.3.6** — S128-разделение по вердикту зонда.
- [ ] **M1b.3.7** — греп-страж allowlist: кэш-чтения только рендер-проекциям.
- [ ] **GC-11** (L3-gate, обязателен для закрытия M2/D) — event → V2-RAM non-zero delta → следующий выбор/поведение NPC сдвинут (живой harness-прогон; ловит RE-D2-класс нулевой игровой реальности, недоказуемой юнит-сьютой).
- [ ] **M1b.5** — удалить мёртвый `apply_npc_state_updates` (0 вызовов доказано грепом) + судьба legacy `RelationshipStore`/vestigial provider (см. AUD-D5).
- [ ] **M2/D** — `RelationshipEventSemantics`: первый живой писатель потребностей через `update_needs` + формат RE-событий в causal-машинерии.
- [ ] **G/H** — динамика Satisfaction и фрустрации через стор.
- [ ] **K** — полный removal-test.
- [ ] **Полигон M** — пресеты, INV-1, диф-тест раннего внимания **О-2** (единственный хвост Р17).

### 2.2. Р18 «Адаптация» (открытый раунд)

Правило раунда: **не доказываем, что адаптация существует; доказываем или опровергаем, что есть каузальная работа, которую никто другой в ENIGMA не выполняет**. Первое действие — досье адаптационного контура по цепочке `writer → state → reader → causal effect → existing substitute → anti-Bond test → остаток`. Развилки Р1–Р7 — вопросом арбитру (GPT), не самостоятельными решениями. Зоны вскрытия — §6.3/§5.0/§5.1/§8.1/§6.19/§6.4 ТЗ v1.9.

---

## 3. Трек AG1 — Understanding & Epistemics (понимание, эпистемика, семантический вход)

Судья трека: мандат **«EXPERIENCE → MEMORY → SELF → RELATIONSHIP LOOP»**. Сюда же интегрируется Understanding / Name-Gate (§3.4): `player text → semantic acts → world reasoning` — архитектурный вектор, не вспомогательный парсер.

### 3.1. Законы трека (несущие, не сжимать)

1. **LLM — медленный консультант, не SSOT:** между Interpretation и State нет прямого пути (DeltaGate; INV-LLM-NOT-SSOT).
2. **Две скорости:** быстрый мир (тики) никогда не ждёт медленного интеллекта (LLM) — ADR-O-377 (cockpit-форма жива; production-форма = intelligence queue, DEBT-RE-D2A).
3. **AG1-INV-TRACE-ONCE:** один event.id → один causal trace → ≤1 принятой дельты поля.
4. «Суть» эпизода = акт консолидации (`is_compressed`), не зона важности.
5. Припоминание растит доступность, не истинность.

### 3.2. Пакеты (закрыто)

- [x] **Фаза A** (S238) — фундамент памяти: P0-дефекты аудита V.0.5.3.9.3 (№1–9) + живые детонации 4.5/7.5/9.5/9.6/9.12/10.0. Все 10 фаз тика живы; речь NPC становится памятью; персистентность сквозная. 40 замков `backend/tests/test_phase_a_memory_fixes.py`.
- [x] **E1** — шина опыта: E1.0 `ExperienceTrace` + provenance (TESTIMONY ≠ копия); E1.1 decay-floor = `is_compressed` (суть бессмертна, шум умирает); E1.2 `MemoryCrystal` (confidence ≠ retrieval_strength; домен-граница с CrystallizedBelief); E1.3 TraceSource; E1.4 терминальный кокпит; E1.5 приёмка владельца.
- [x] **E2.0-a/b** — DeltaGate + `StateDeltaProposal` (whitelist/клампы/идемпотентность/INV-LLM-NOT-SSOT); живой провод в reaction_subscriber (S115-точка); Gate = аудит, не писатель; `EXPERIENCE_DELTA_COMMITTED` (EventDTO).
- [x] **E2.0-c / B0-CLOSED** (S243) — causal proof: SUPERBOX `causal_state_test` A/B/C/D на GC-00-харнесе; одна переменная = авторизованная дельта; argmax-флип без события/текста/LLM; D-атаки REJECTED → рождены ADR-O-379 (PK write guard) + ADR-O-380 (BeliefState write guard). LIMITATION: флип уровня решения; материализация движения — материал BC-12.
- [x] **BC-1** (S247, ADR-O-381) — Conclusion Layer: EXPERIENCE → машино-пригодный вывод (триплет subject/predicate/object + confidence [0..1] + evidence[event_ids → L1] + source=DIRECT_EXPERIENCE; НЕ фразы, НЕ флаги поведения). `ConclusionGate` (закрытый predicate-реестр, старт IS_DANGEROUS; Gate = аудит, не писатель; идемпотентность по AG1-INV-TRACE-ONCE) → `ConclusionStore.apply` (единственный write-path) → `CONCLUSION_FORMED` (observation-only). NO-VACUUM: без новых EXPERIENCE_DELTA нет CONCLUSION_FORMED. Per-agent RAM + round-trip `scene_state["conclusions"]` (собственная SQLite запрещена). `BC1_ENABLED` default OFF (INV-BC1-NOOP). Приёмка 6/6 GREEN.

Историческая формулировка честности E1 («proposition сохраняется, но не доказано как состояние») — снята E2.0-c/B0.

### 3.3. Терминологическая лестница (перепрыгивать запрещено)

E2.0 = state-delta integrity → E2.0-b = live propagation → BC-1 = semantic leap (**реализован** S247) → **BC-2 = открыт** (Conclusion → Expectation). Мост CONCLUSION → EXPECTATION закрыт до BC-2 (ADR-O-381 F3а): включение = мини-ADR + `BC1_ENABLED` ON + потребитель ExpectationStore. DeltaGate-тропа обязательна для conclusion_delta (provenance + causal parent).

### 3.4. Understanding / Name-Gate (вне классического трека)

- [x] S305 — Understanding Pipeline: Multi-Act + World Validation + Player-Move + Recovery Boundary (micro 95/95, Gate A 3/3).
- [x] S306/S308 (ADR-O-409) — Name-Gate Closure: FACE/NAME/LINK (NAME-ось + writer-гейт + гейт головы; доска связывает имя↔лицо; name_gate 7/7).
- [ ] Интеграция понимания в единый контур §3 по мере потребности (не форсировать вне §0.2).

### 3.5. Поведенческое замыкание BC-2…BC-13 (после M2/D; до тяжёлого Active Inference)

Цель: единый контур социализации на уже существующих Memory/Belief/Relationship/Decision механизмах — не новый набор эмоций и не флаги «месть/обида/влюблённость» как сущности.

- [ ] **BC-2** — Conclusion → Expectation: вывод меняет прогноз следующего взаимодействия.
- [ ] **BC-3** — Expectation → Decision: существующий DecisionHub использует ожидание без специальных action-флагов (full-cell GC-04).
- [ ] **BC-4** — Repeated evidence → Generalization: повторяемость усиливает устойчивый вывод; противоречивая — ослабляет/ревизует.
- [ ] **BC-5** — Personal experience → Social testimony: NPC передаёт не только факт, но и собственный вывод («я считаю его ненадёжным»).
- [ ] **BC-6** — Testimony → Recipient belief: получатель учитывает источник, уверенность, собственный опыт и конфликтующие свидетельства.
- [ ] **BC-7** — Conclusion → social strategy: derived-паттерны («избегать», «не давать ресурс», «предупреждать») без флагов конкретных NPC.
- [ ] **BC-8** — Learning: успешный опыт порождает знание/правило/навык, меняющее будущую возможность или предпочтение действия.
- [ ] **BC-9** — Surprise → belief revision: неожиданное поведение другого ломает/уточняет ожидание и отношение.
- [ ] **BC-10** — Self-learning: опыт меняет не только модель другого, но и модель себя («я умею», «я ошибся», «должен быть осторожнее»).
- [ ] **BC-11** — Social triangles: A→B→C порождает третичное изменение отношений без специального «треугольника отношений».
- [ ] **BC-12** — Long-horizon proof: сценарии «оскорбление→вывод→память→избегание», «обман→вывод→слух→осторожность», «обучение→новое действие», «помощь→благодарность→ответная помощь» проживаются 100–1000 тиков.
- [ ] **BC-13** — Temporal consolidation boundary: immediate causal update ≠ temporal consolidation. Значимый опыт может немедленно менять canonical state через DeltaGate, но отдельные следствия требуют времени/повторной обработки. Сон — допустимое temporal window, но НЕ универсальный магический `commit()` для памяти. Любое изменение имеет provenance и causal parent.

**Stop:** пока BC-1…BC-7 не доказаны, не начинать полноценный Active Inference как отдельный большой слой.

---

## 4. Трек W-TRACK — World Embodiment (Часть II Stage 2.5)

Главный инвариант: **Renderer не является источником истины о мире**; новый NPC/шрам/предмет/renderer не требуют переписывания мозга NPC.

### 4.1. Чеклист

- [x] **W-субстрат** (S230/ADR-O-371) — WORLD-домен: `architecture/world.yaml`, семантическая объектная топология, WorldObjectStore (персистенция внутри `scene_state`), WorldSnapshot +1 поле. 30 тестов + INV-WORLD-OBJECT-TOPOLOGY.
- [x] **W2** (S232/ADR-O-372) — AffordanceResolver: pure `(WorldObject, BodyStateView, npc_position) → SemanticAction[]`; реестр 7 предикатов закрыт (расширение = мини-ADR); INSERT/REMOVE зарезервированы. 24 теста.
- [x] **W3** (S237/ADR-O-376) — `transition_object`/`damage_object` (TransitionResult, не bool) + production-спавнер (SpawnMapping, wo_-identity, initialize_scene-only, live=18) + G1 discovery-shadow GREEN.
- [x] **G2** (S239/ADR-O-378) — producer-facts: первый живой мост W2→решение (weapon_access → OpportunityContext; DecisionHub object-agnostic); `W3_G2_ENABLED` default OFF.
- [x] **G3** (S307/ADR-O-410, коммиты `1ce0a00f`+`4169f77e`) — воля → объектная цель → intent → исполнитель → мутация мира → событие. Этап 1: `g3_executor` (PASS/NO_OP/REJECT/SKIP; provenance-обёртка; целеполагание вне контура) + Г4-цензус `_write_subtree` + Фаза 7 + `W3_G3_ENABLED` (default OFF). Этап 2: `compute_object_target_facts` (nearest+lex; `TARGETABLE_ARCHETYPES`=chair→TAKE — calibration policy) → `TickState.object_target_map` → DecisionHub. Гейты: Tier-A юнит (winner=steal 1.67, target=wo_id; входы — мир-параметры, веса не тронуты) · GC-00 A/B GREEN (ON: holder=thief_shadow+THEFT; OFF: байт-идентично) · IPT 49/49. Honest-zero + замок R6.3 задокументированы.
- [x] **DEBT-W-AUDIT** (S240) — `docs/AUDIT_W_TRACK_COUPLINGS.md`: ownership/coupling-граф, 0 Simulation coupling, 12 Acceptable adapter; канал B1.4 (FE-пуш полного scene_state) защищён S244 (единый whitelist-приёмник player-position, оба rail GREEN).
- [ ] **G3-хвост / GC-08** — L3-обязательство G3: object → affordance → action → persistent consequence. Prerequisite: capability `spawn_world_object` для GC-08-harness (инфраструктурная, канон §9.2; факт: API харнесса не имеет). GC-02 не сливается с GC-08 (player→world ≠ object→affordance→action).
- [ ] **Object-cognition** — CAN_STEAL ≠ ACCEPT/WANT (находка Мастера на G3): возможность ≠ желание; следующий cognition-слой над G3.
- [ ] **Caller-guard** — Г4 `_ALLOWED_WRITERS` в WorldObjectStore (текущие писатели через инъекцию — legal; enforcement-ради-enforcement запрещён).
- [ ] **Reusable-паттерн объектных действий** — TAKE/USE/MOVE/GIVE/FOLLOW по прецеденту G3.
- [ ] **W4** — Embodied State (поза, локомоция, хват, attachment); Two-Domain (§ENIGMA-002) не доказан — точечно при реальных W2-потребностях (CAN_GRIP для TAKE-таблицы).
- [ ] **W5–W9** — Presentation Projector / интерфейсы renderers — только контракты + PoC.

### 4.2. Закон-урок харнессов (S239, DEBT-W-STORE-INCIDENT — ACCEPT Мастера)

Все A/B-харнессы обязаны патчить `settings.saves_dir` до `build_game_loop` (эталон — `scripts/w3_g2_simple.py`). Легитимность состояния (продолжающаяся история мира) ≠ валидность baseline (экспериментальная чистота): `ROOT/saves` содержит production-evolved state (стратиграфия нарушена до T≈2800); reset отклонён — подмена исторической непрерывности мира опаснее артефакта.

---

## 5. Трек Body / Embodied — телесный контур и ограничение действий

**Красная граница (инвариант, не сжимать):** **Body не является отдельным автором действий. Body формирует ограничения/давление, а решение остаётся у агентного контура.**

```
Body (canonical state)
    → chronic pressure (homeostatic / pain / fatigue / sleep pressure)
    → feasibility / availability constraints (ActionConstraints)
    → Decision landscape deformation
    → DecisionHub (агентный контур)
    → commitment → execution
```

Прямой путь `body → direct action` запрещён. Доказательство границы: GC-09B RED-находка (S-журнал §10: `a6708f46`) — авторизованная дельта fatigue+90/energy−90 не изменила availability до V1; единственный body-edge был Vital State Guard (смерть/бессознательность). V1 (ADR-O-383) закрыл availability-тракт через pressure_translator (chronic-veto cap 0.3, константы CALIBRATION_CANDIDATE) — не патчем `_is_intent_available`.

### 5.1. Статус

- [x] **GC-09A** — Body Runtime GREEN (коммит `7f369e54`): production-провод BodyEngine→StateApplicator жив; one-way-оси сместились у обоих субъектов; тело персонифицированно дифференцировано (25 тиков).
- [x] **GC-09B** — RED = находка (коммит `a6708f46`): «state exists ≠ state has consequence»; State Consumer Gap — вторая выборка домена (первая — отношения, RE-D2).
- [x] **ADR-O-383 V1** (коммиты `5b14af56`+`fa82f359`+`b9b6f90c`+fix2) — Embodied Constraint IMPLEMENT: RED→ADR→V1→GREEN за сессию; GC-09B-full 2/2.
- [ ] **V1+ калибровка** — chronic-veto cap и пороги через Calibration Lab (константы помечены CALIBRATION_CANDIDATE).
- [ ] **D-MOM** — `motor_output_mult`: orphaned derived state (sleep/body → CouplingResolver → персистится в `body_state`, production consumer не обнаружен). Не блокирует; causal question для Sleep/Decision-фронта.
- [ ] **Sleep-семантика** — граница V1 не расширяется: отдельный вопрос, отдельный фронт.

### 5.2. SLEEP ≠ RESET (дизайн-контракт)

Сон не является отдельной «анимацией отдыха» и не является `fatigue = 0`. Сон — **temporal runtime mode организма**, в котором Body продолжает изменяться по собственным законам.

```
SLEEP ≠ RESET
SLEEP = state-dependent recovery process.
```

- [ ] Зафиксировать canonical границу: wakefulness → sleep pressure accumulation → sleep seeking → reachable recovery affordance → settled → sleep transition → recovery runtime → awakening.
- [ ] Не создавать второй SleepStore, если canonical BodyState уже способен хранить необходимые temporal variables.
- [ ] Все переходы сна детерминированы и replayable; sleep runtime не имеет прямого writer-пути мимо canonical StateApplicator / владельца Body domain.
- [ ] Разделить duration и quality: 8 часов в sleep state ≠ автоматически одинаковое восстановление. Recovery зависит минимум от: continuity, interruption, safety/threat context, available recovery affordance, pre-existing sleep pressure.
- [ ] Не моделировать нейрофизиологию человека ради биологической точности: NREM/REM/EEG не обязательные canonical сущности; режимы восстановления = функциональные recovery modes, не декоративная копия медицинской терминологии.
- [ ] Прерывание сна — только через существующие perception/arousal rules; NPC не просыпается от каждого event. Different stimulus relevance → no interruption / partial arousal / full awakening (зависит от perception accessibility, arousal threshold, current body state, threat appraisal). No global "wake all NPCs" shortcut.
- [ ] Новые recovery variables — только после anti-Bond test: какую причинную работу выполняет переменная, которую уже не выполняют fatigue / sleep pressure / existing body state. Не создавать `cognitive_recovery = 0.8` / `emotional_recovery = 0.6` ради психологической правдоподобности.

### 5.3. DEBT-SLEEP-DELIVERY (доставка тел к кроватям)

Внешняя зона (spatial/behavioral; НЕ физиология — сон-машина верифицирована S235/S236). Симптом (DriftLab 200 тиков × 6 NPC): elig=True = 0/1200 — тела не доезжают до кроватей при живом графе. Следствие без доставки: `sleep_pressure→1.0`, `motor_output_mult→0` («мир недосыпа»). Это не Body bug — вертикальный разрыв `BODY → DECISION → WORLD → BODY`: физиология может быть корректна, но мир производит хронический недосып, если embodied actor не способен физически достичь recovery affordance. Решение — при spatial/affordance-контуре: intent → affordance search → reachable target → traversal → settled → физиологический переход (машина подхватит автоматически). Дизайн-вход Мастера: «Тень тайно спит в подвале» — первый кандидат контент-фикса (activity_map/MapEditor или W2 sleep-affordance-типы BED→HAMMOCK/GROUND/SHELTER). Канонически связано с GC-09/GC-10 (§9).

---

## 6. Планы будущего

> Две разные сущности: **6.A — дизайн-контракты** (задают будущую модель мира; не «TODO», а онтологические обязательства с запретами) и **6.B — будущие эпохи** (пакеты реализации, ссылки на VZ-ТЗ). Приоритет и порядок — только через §0.2.

### 6.A. Дизайн-контракты

#### 6.A.1. MATH-01 — математическая композиция и пластичность личности

Основание: Math_GAME.md v2 (полная рантайм-верификация формул) + внешняя математическая рецензия. Не новый engine — оформление и точечные замыкания уже существующей математики.

- [ ] **MATH-1** Центральная композиция $W_t \to O_i \to \varepsilon_i \to L_i \to \mathbf d_i \to E_i \to a_i \to W_{t+1}$ формализована (Math_GAME.md §2a). Статья = «ENIGMA: Mathematical Architecture of a Subjective World», структура I–X по рецензии.
- [ ] **MATH-2** Сон→восприятие: $R^{eff} = R \cdot v_{hearing}(\kappa)$, $P(\text{hear}) = \mathbf 1[d \le R^{eff}]$, $arousal \mathrel{+}= g(R^{eff})$. НЕ новый ADR — исполнение ADR-O-356 Phase E.0 (закрывает П-4; сходимость двух независимых аудитов). Детерминизм сохраняется: масштабируем радиус, не вероятность.
- [ ] **MATH-3** Эпистемическое остывание (П-2): $c(t) = c_0 e^{-\Delta t/\tau_e}$ — уровень-II полураспад; координация с RE-01 M2/D. Появляется возраст информации.
- [ ] **MATH-4** C-пластичность (уровень III) — редкое evidence-gated событие: хронический `tifl_pressure_model`-поток (L1, D тиков, |cum|>θ) → PatternDetector → CalibrationEngine ΔC ($C'=C'^T$). Гейты: §ENIGMA-002 (два домена), ISK до/после (BRITTLE/CHAOTIC запрещён), anti-Bond (механизм, не сущность), mini-ADR обязателен, калибровка через Lab. ЗАПРЕТ: random C, частые ΔC, ΔC из одиночных событий. Обоснование: аттрактор текущей C — $\mathbf d^* = (0, 4/23, 10/23, 9/23)$, fear=0 (Math §7.5); хронический страх через L1 работает, но топология «не умеет» хронически меняться.
- [ ] **MATH-5** Детерминистическая непредсказуемость: сценарий-тест «тот же ввод, другой день — другая реакция» через скрытые медленные переменные (pressure_accumulator / affective_memory / sleep_state / sleep_debt / recovery_history). Инвариант: same seed + same world + same temporal/recovery history → same outcome; different recovery history → potentially different outcome → только через canonical state. Сон — не бинарный reset: результат зависит от temporal continuity, interruption history, качества восстановления. Игрок видит следствия (хуже слышит, медленнее реагирует, перестал шутить, сорвался), не внутренние числа.
- [ ] **MATH-6** Терминология AIF канонизирована (Math §18.4): «prediction-error-driven, inspired by Active Inference»; запрет «базируется на минимизации свободной энергии» до вариационного F.
- [ ] **MATH-7** Позиция детерминированных мембран (путь A рецензии): threshold-модель = актив репродуцируемости (реплей/DriftLab/Calibration Lab). Soft-мембраны $\sigma(\alpha(R-d))$ — осознанно отклонены.
- [ ] **MATH-8** Боевые долги: П-9 (SOLID-чит; код сам помечен «Временно отключено»), П-11 (клиентский d20+damage → KernelRNG-сервер), П-13 (`randint(2,20)` — фамбл недостижим), П-14, П-15 (hp-SSOT в API-пути).
- [ ] **MATH-9** Аттрактор C — численная верификация в Calibration Lab (юнит: итерация релаксации до сходимости → $\mathbf d^*$).
- [ ] **MATH-10** Двухслойная семантика травмы в контент-дизайне: base расслабляется (~109 тиков), effective — навсегда (L1-шрам). Инструменты «навсегда» = шрамы/веры/отношения, не мгновенные стат-мутации.

#### 6.A.2. Unified Appraisal / «палитра эмоций» (EM)

- [ ] **EM-1** Минимальное пространство оценок: valence, arousal/intensity, agency, controllability, fairness/norm violation, self/other relevance, certainty/uncertainty, future consequence/expectation.
- [ ] **EM-2** Отделить appraisal от emotion, emotion от relationship, relationship от belief.
- [ ] **EM-3** Вывести anger/fear/sadness/pride/shame/gratitude/envy/resentment/contempt/hope как derived regions, а не отдельные state-machines.
- [ ] **EM-4** Decay, accumulation, interference, memory reactivation и social contagion — общие законы.
- [ ] **EM-5** Emotion → action preference: чувства голосуют за существующие действия; не создавать `if emotion == X → action Y`.
- [ ] **EM-6** Expression dictionary: словарь речи/позы/интонации отдельно от причинности.
- [ ] **EM-7** Calibration lab: пороги и веса на сценариях, а не вручную на каждом NPC.

#### 6.A.3. Predictive Perception / Surprise (PP)

- [ ] **PP-1** Унифицировать observation/belief truth sources.
- [ ] **PP-2** Измеримый surprise/prediction error как свойство ожидания, а не эмоциональный всплеск.
- [ ] **PP-3** Surprise для пересмотра beliefs/relationships/expectations.
- [ ] **PP-4** PlayerBeliefModel ≠ NPC ToM: собственные убеждения NPC и убеждения о чужих убеждениях не смешивать.
- [ ] **PP-5** Second-order ToM (`A believes B believes X`) — только после первого порядка и при доказанной необходимости.
- [ ] **PP-6** Prophecy / prediction vertical slice — после PP-1…PP-4.
- [ ] **PP-7** Temporal state → perception quality: BodyState и recovery state причинно меняют доступность/качество восприятия без второго perception engine. Fatigue/sleep pressure → reduced effective attention; sleep state → altered arousal threshold; deep rest → restoration. Реализация через существующие perception contracts и deterministic thresholds/scaling. НЕ вводить `random_sleepiness()`, `chance_to_miss_event()`. Путь: canonical body state → derived perception modifier → existing Observation/Perception pipeline.

#### 6.A.4. HUMOR / PLAY / SOCIAL INCONGRUITY (HUM)

Юмор вводится **после замыкания Experience→Conclusion→Expectation, Unified Appraisal и измеримого Prediction Error** — иначе пришлось бы создавать специальные «юмористические» костыли. Это не `humor_engine` ради шуток, а вертикальный тест субъективного мира: один и тот же event может быть смешным для одного NPC, нейтральным для другого, непонятным для третьего и угрожающим для четвёртого.

**HUM-00 — контракт и anti-Bond**
- [ ] Минимальные derived-компоненты: `Incongruity`, `PredictionError`, `Resolution`, `Benignity`, `HumorAppraisal`, `HumorAttempt`, `HumorReaction`.
- [ ] Запретить canonical state `is_funny`, `humor_level`, `is_joking` как источники поведения.
- [ ] Personality — только вход в производную disposition: playfulness, openness/flexibility, social confidence, risk tolerance, norm rigidity (уже существующие traits).
- [ ] Temporal plasticity: disposition меняется вследствие опыта, отношений, текущего appraisal/body state и успешных/неуспешных социальных эпизодов.
- [ ] Anti-Bond: доказать, что юмор не дублирует существующие appraisal/relationship/prediction mechanisms; без уникальной каузальной работы — derived operation.

**HUM-01 — Perception: incongruity**
- [ ] Сопоставлять наблюдение с expectation NPC, а не с «объективной смешностью» события.
- [ ] Измерять discrepancy между ожидаемым и наблюдаемым.
- [ ] Не считать любой surprise юмором: surprise может вести к fear, confusion, anger, curiosity и другим appraisal regions.
- [ ] Минимальная форма разрешения: NPC должен иметь возможность построить правдоподобную связь между двумя скриптами/интерпретациями.

**HUM-02 — Resolution / Logical Mechanism**
- [ ] `Script Opposition` и `Logical Mechanism` как данные/операции, не библиотека анекдотов.
- [ ] Несколько механизмов: semantic shift, analogy, inversion, exaggeration, literalization, causal reversal — если реально нужны.
- [ ] Высокая неожиданность без разрешения остаётся confusion/uncertainty, не автоматически humor.
- [ ] LLM может реализовать Language Layer, но не источник истины о том, что произошёл юмористический акт.

**HUM-03 — Benignity / social safety**
- [ ] Violation оценивается относительно норм, угрозы, статуса, контекста и доступного агенту знания.
- [ ] Учитывать relationship state, но не сводить юмор к `trust`.
- [ ] Один violation допускает разные appraisal outcomes: amusement / neutral / confusion / insult / threat.
- [ ] Self-directed humor — как безопасный вариант из общей модели target/self-other relevance, не из флага `self_irony`.

**HUM-04 — Individual humor disposition**
- [ ] Текущая disposition производится из personality + experience + appraisal/body + relationship/epistemic context.
- [ ] Не хранить как вечный scalar personality trait.
- [ ] Temporal drift: один NPC в разных состояниях и периодах жизни реагирует на одинаковый паттерн по-разному.
- [ ] Изменения disposition имеют provenance и объяснимы через реальные изменения входных факторов.

**HUM-05 — Humor as coping / pressure response**
- [ ] Humor-as-coping — derived action/appraisal pattern, не отдельная эмоция «смелость через юмор».
- [ ] Юмор при высоком fear/stress/pressure допустим, если NPC ожидает снижения напряжения, поддержки self-control, сохранения социальной связи или возможности продолжить действие.
- [ ] Режимы `tension_release` / `social_support` / `self-protection` / `defiant_play` / `absurdization/meaning-reframing` — только если выводятся из общих appraisal/motivation механизмов, не отдельные флаги.
- [ ] Длительная тяжёлая ситуация меняет вероятность/форму coping-humor через pressure accumulation, memory и self-model, не через таймер.
- [ ] Юмор может быть неадаптивным: маскировать страх, раздражать союзника, разрушать серьёзность, доводить до риска.
- [ ] Экстремальное давление не делает автоматически смешным; «шутка на грани» — причинный выбор с оценкой ожидаемой реакции и риска.

**HUM-06 — Humor production**
- [ ] Opportunity для шутки из текущего контекста; candidate generation → audience model → expected reaction → risk/benefit → attempt.
- [ ] Production не по расписанию и не при каждом surprise.
- [ ] Чем слабее модель аудитории/отношений/контекста, тем выше вероятность нейтральной/неудачной/подавленной попытки.
- [ ] LLM — только языковая реализация разрешённого runtime `HumorAttempt`.

**HUM-07 — Failed humor / consequences**
- [ ] Реакции: laugh/amusement, neutral, confusion, embarrassment, offense/conflict, bonding и другие derived outcomes.
- [ ] Реакция слушателя — experience и при необходимости memory.
- [ ] Успех/провал меняет expectations о собеседнике и self-model.
- [ ] Отношения меняются через обычный RelationshipEventSemantics.
- [ ] Повторные удачные эпизоды формируют социальную привычку/ожидание, но не `friend_is_funny` флаг.

**HUM-08 — Social transmission**
- [ ] B услышал шутку A → B получает собственную observation/provenance, не копию внутреннего состояния A.
- [ ] C, не наблюдавший событие, не получает его автоматически.
- [ ] Передача может менять reputation/familiarity/expectations через существующие testimony/social mechanisms.
- [ ] Искажение/непонимание при неполной передаче — проверить.

**HUM-09 — Long-horizon humor**
- [ ] 100–1000 тиков: disposition меняется вместе с жизнью NPC (серия удачных шуток → больше playfulness; унижение/хроническое давление → юмор исчезает/защитный/агрессивный/рискованный; восстановление → обратно без reset).
- [ ] Same seed + same history → same humor outcomes; другой history → другой outcome.

**HUM-10 — Observability**
- [ ] Chronicle: expectation → incongruity → resolution/failed → benignity/social appraisal → attempt/reaction → consequence.
- [ ] NPC Inspector отвечает «почему он пошутил?» без LLM-галлюцинации.
- [ ] UI не показывает скрытые коэффициенты как gameplay truth; human-readable объяснение без раскрытия математики.

#### 6.A.5. PLAYER AVATAR / EMBODIED AGENCY (AV)

Аватар игрока не «ещё один NPC» и не тупой курсор. Это **тот же causal actor**, но с особой границей агентности.

**Исходная мотивация:** правила настольного RPG уже подразумевают, что персонаж не равен управляющему игроку. Класс, происхождение, ценности, нормы, страх, характер, убеждения, границы и прошлый опыт причинно влияют на **что персонаж готов сделать**, а не только на текст после действия. Монах воспринимает богохульство как сильное нарушение идентичности, но насилие против врага веры — как совместимое с нормами. Все такие различия — **derived из общего состояния и контекста**, не hardcoded запреты.

**Главный принцип:**

> **PLAYER INPUT ≠ AVATAR WILL.** Игрок предлагает намерение. Аватар остаётся causal субъектом действия. Разногласие между ними — игровое состояние, имеющее причины, последствия, память и историю.

**AV-00 — Canonical Avatar Contract**
- [ ] Описать `player` как actor с теми же canonical state domains, что и NPC, но с отдельным `agency_boundary`.
- [ ] Зафиксировать границу: `player_intent → avatar_appraisal → resistance/accept/modify → execution`.
- [ ] Запретить avatar-only writer там, где существующий canonical writer уже может изменить состояние.
- [ ] ADR-030/031/036/037/039/041/084 собрать в один contract/index; удалить ложные обещания из комментариев и ADR.
- [ ] Определить домены аватара, обязательные в MVP, и сознательно deferred.
- [ ] Инвариант: отсутствие avatar-specific DecisionHub ≠ отсутствие avatar agency.

**AV-01 — Persistent Psyche / Personality Substrate**
- [ ] Настоящий persistent psyche аватара: `fear`, `conviction`, `shame`, `aggression`, `curiosity`, `identity_rigidity` и существующие параметры.
- [ ] Связать CharacterProfile/values с canonical psyche вместо параллельной мёртвой конфигурации.
- [ ] Разделить **stable disposition** и **current state**.
- [ ] Устранить fallback-константы `0.5` как production source of truth.
- [ ] Единая convention шкал: никакого смешивания `0..1` и `0..100` в одном resolver.
- [ ] Save/load восстанавливает psyche без потери причинной истории.

**AV-02 — Preferences / Values / Norms / Identity** (слой ролевого смысла сопротивления; не список запретов)
- [ ] Ценности как оценочные параметры/constraints: sacredness, loyalty, honesty, violence tolerance, modesty, autonomy, purity/discipline, status, compassion — только там, где нужны игровому домену.
- [ ] Предпочтения — ordinary appraisal inputs, не `allowed_targets`/`forbidden_actions` списки.
- [ ] Actor-specific attraction/preferences/comfort boundaries без предположения о едином «нормальном» персонаже.
- [ ] Происхождение/класс/культура инициализируют priors, но не заменяют навсегда опыт и обучение.
- [ ] Нормативный конфликт объясним: «это против моей веры», «это унижает меня», «я не доверяю ему» — разные causal reasons, не один `REFUSE`.
- [ ] Запретить `if monk and blasphemy` как gameplay-critical writer.

**AV-03 — Willpower + CharacterFilter + Affect: единый Resolver**

Существующие системы **не сливаются математически**. Они — разные источники evidence для единой точки принятия решения.

```text
PRESSURE ───────────────┐
VALUES / NORMS ─────────┤
PREFERENCES ────────────┤
TRAUMA RESONANCE ───────┤
CURRENT BODY ───────────┤
PLAYER TRUST ───────────┤→ AvatarActionResolver
RELATIONSHIP ───────────┤        ↓
EPISTEMIC CONTEXT ──────┘  ACCEPT / MODIFY / RESIST / REFUSE
                                   ↓
                           execution / counter-offer
```

- [ ] Сохранить `WillpowerGate` как pressure/strain mechanism.
- [ ] Сохранить `CharacterFilter` как identity/value appraisal.
- [ ] Affective/trauma resonance — distortion of pressure, не ещё один veto-флаг.
- [ ] Единый `AvatarActionResolution`/эквивалентный контракт, агрегирующий причины.
- [ ] Machine-readable `reasons[]`, severity, dominant factors, counter-offer provenance.
- [ ] Один слабый фактор не превращает автоматически действие в REFUSE.

**AV-04 — Social / Romantic / Sexual Agency Boundaries**

Цель — доказать, что **обычные preference, norm, comfort, attraction, trust, fear и relationship механизмы действительно влияют на действия аватара**, а не создать «сексуальную подсистему».
- [ ] Player-originated flirtation проходит тот же appraisal pipeline, что и NPC-originated social intent.
- [ ] Персонаж может принять/изменить/смягчить/отвергнуть социальный intent согласно состоянию и preferences.
- [ ] Отсутствие attraction ≠ hostility: neutrality, politeness, avoidance, embarrassment — из общей модели.
- [ ] Discomfort/social exposure ≠ moral violation.
- [ ] Trust/familiarity могут менять доступность близости, но не заменяют preference/consent boundary.
- [ ] Тематика без privileged writer — тест универсальности social action machinery.
- [ ] Тесты покрывают контрасты: «раскованный vs скромный», «attraction есть/нет», «безопасный контекст vs threat/pressure».

**AV-05 — Player Trust / Relationship to the Controller** (отдельная ось, не синоним identity integrity)
- [ ] `player_trust` как relationship-like state — если calibration подтвердит необходимость.
- [ ] Отличить «я знаю, кто я» (`identity_integrity`) от «я доверяю тому, кто мной управляет» (`player_trust`).
- [ ] Trust меняется через историю: полезные приказы, предательство, принуждение, уважение границ.
- [ ] Влияет на expected intent и вероятность accepting/modifying, но не shortcut `trust > threshold → obey`.
- [ ] Высокий trust не отменяет values/trauma/physical danger; низкий не означает sabotage.
- [ ] Все изменения trust имеют provenance и доступны Chronicle.

**AV-06 — Negotiation with the Player**
- [ ] `RESIST` может порождать counter-offer: другой маршрут, меньший риск, другой объект, помощь, ожидание, stealth, retreat.
- [ ] Counter-offer — executable game intent, не только текст.
- [ ] Игрок может принять/отклонить/изменить counter-offer.
- [ ] Повторное давление имеет cumulative consequences.
- [ ] Уступка не стирает disagreement: history сохраняет факт конфликта и outcome.
- [ ] Negotiation не обязано быть UI modal: может быть embodied/implicit через action modification, movement, silence, hesitation, внутренний голос.

**AV-07 — Inner Voice / Soliloquy**
- [ ] Player-avatar генерирует private/speechless proposition через production communication path.
- [ ] Триггеры: сильный dissonance, high affective load, memory reactivation, sleep/dream, major identity conflict, extreme pressure. Не scheduled monologue.
- [ ] Первый production path — deterministic narration hooks/templates.
- [ ] LLM — optional Language Layer после DeltaGate; causal state/reason/outcome — в Python.
- [ ] Counter-offer и narrative hook доходят до DM/API/frontend.
- [ ] Голос отражает actual state; не создаёт новую скрытую psyche.

**AV-08 — Resistance Medium / Embodied Conflict**
- [ ] Resistance Medium — редкая сильная форма конфликта; lifecycle `trigger → escalation → resolution → aftermath`, без implicit reset.
- [ ] Input interference — только когда canonical resolver реально вернул соответствующее состояние.
- [ ] Частота конфликтов — causal thresholds, не cooldown «ради геймплея»; normal play не превращается в постоянную борьбу с клавиатурой.
- [ ] PerceptualMomentum, shake, tunnel vision, latency — феноменологическая проекция, не психический state writer.

**AV-09 — Escalation / Recovery / Conditioning**
- [ ] Formalize transition semantics: `COMPLY → RELUCTANT → DISTRESSED → PANICKED → DISSOCIATING → BROKEN → CONDITIONED`.
- [ ] Какие переходы обратимы, какие оставляют scars, какие требуют длительного восстановления.
- [ ] Recovery каузален: safety, sleep, social support, successful agency, time/decay.
- [ ] Conditioning меняет будущие thresholds/expectations, но не магический permanent flag.
- [ ] Broken state → freeze, collapse, avoidance, observation и другие существующие embodied outcomes.
- [ ] После восстановления — memory/affective consequences, если их породила история. Тестировать «сломался, но игра продолжается».

**AV-10 — Limited Autonomous Agency**
- [ ] Минимальный `AvatarAutonomyResolver` поверх существующих affordances/DecisionHub/Body/Perception — не второй полный NPC stack.
- [ ] Разрешённые случаи: idle/settled behavior, panic/freeze, dissociation, extreme pressure, sleep/dream, explicit counter-offer.
- [ ] Автономное действие проходит canonical execution и verification.
- [ ] Никаких отдельного memory/relationship/world-state writer или secret belief store только для аватара.
- [ ] Граница «agency vs interface fight»: автономия редкая, причинная, объяснимая.

**AV-11 — Avatar Memory / Experience / Self-Model**
- [ ] С FIFO-буфера реплик — на общий MemoryManager/experience substrate, где production-ready.
- [ ] Опыт `player_action → avatar conflict → outcome` сохраняется как experience с provenance.
- [ ] Experience меняет self-model: «я способен», «не справился», «игрок обычно уважает мой отказ», «это опасно».
- [ ] Repeated evidence → conclusion → expectation — применяется к отношению аватара к игроку.
- [ ] Memory decay не стирает identity/conditioning без causal reason.
- [ ] Save/load и replay восстанавливают состояние и историю.

**AV-12 — Avatar Epistemics** (поздний, но обязательный при доказанной ценности слой)

```text
WORLD TRUTH ≠ PLAYER KNOWLEDGE ≠ AVATAR BELIEF ≠ NPC BELIEF
```

- [ ] Avatar получает собственные observations и belief records через общий epistemic pipeline.
- [ ] Player input не превращает неизвестный аватару факт в его belief.
- [ ] Сценарий: игрок знает истину, аватар имеет ложное belief и сопротивляется приказу из-за своей модели мира.
- [ ] Обратное: аватар видел событие, игрок нет; counter-offer на information asymmetry.
- [ ] Полное переиспользование Proposition/SpeechAct/ClaimEvent/EpistemicRecord/BeliefRevisionEngine — не AvatarBeliefEngine.
- [ ] Различие player knowledge / avatar belief / avatar ToM сохраняется.

**AV-13 — Avatar Relationships / Social Consequences**
- [ ] Аватар участвует в Relationship Engine как actor, без отдельной relationship store.
- [ ] Отказ/помощь/ложь/унижение/флирт/спасение — через обычные RelationshipEventSemantics.
- [ ] NPC делают выводы о характере аватара по действиям.
- [ ] Аватар меняет отношения не только по команде, но и по тому, **как именно** исполнил/изменил command.
- [ ] Social consequences меняют будущую resistance и trust.

**AV-14 — Avatar + Humor / Coping**
- [ ] Юмор аватара — из его expectations/appraisal/relationship/context, тот же humor substrate, не отдельный «humor mode».
- [ ] Coping humor при страхе/давлении — способ удержать agency, если следует из history/self-model.
- [ ] Не допускать `stress → joke` и `high humor → joke` shortcut.
- [ ] Humor attempt/failed humor влияет на player trust, relationships, memory только через общие causal mechanisms.

**AV-15 — Observability / «Why did my character refuse?»**
- [ ] Chronicle: player intent → relevant context → pressure/values/preferences/trauma/body/trust → resolution → execution/counter-offer → consequence.
- [ ] Inspector отвечает без LLM как authority.
- [ ] Различать `cannot` / `will not` / `does not trust` / `does not know` / `does not want` / `does not understand`, если причины существуют в runtime.
- [ ] UI не обязан показывать числа; causal-human-readable explanation достаточно.
- [ ] Resistance Medium и phenomenology — presentation of an already-proven state.

**AV-16 — Avatar Vertical Slice** — полный causal loop:

```text
player command → avatar appraisal → accept/modify/resist/refuse
→ optional negotiation → execution → world/social consequence
→ experience/memory → changed expectation/trust/self-model
→ different response to a later command
```

Обязательные контрасты: AV-GC-01…12 (см. §9.4).

**AV-17 — Anti-Bond / Anti-Second-ENIGMA Rules**
- [ ] Нет `is_monk → veto(blasphemy)` как единственного механизма.
- [ ] Нет `orientation → hardcoded allowed_targets` как canonical action gate.
- [ ] Нет `personality_trait → action` прямой таблицы без context.
- [ ] Нет `player_trust > X → obey`.
- [ ] Нет `BROKEN → game_over`.
- [ ] Нет второго полного DecisionHub/MemoryManager/EpistemicStore/RelationshipStore только для игрока.
- [ ] Нет LLM-generated hidden resistance state.
- [ ] Нет periodic inner monologue / resistance ticks без causal trigger.
- [ ] Нет presentation-layer writer, который сам меняет psyche.

**AV-18 — Calibration / Scope Ceiling**

**MVP avatar:** `body + perception + psyche + values/preferences + affect + resistance + inner voice + limited memory/experience + player trust + social consequences`.
**Later:** `full avatar epistemics + richer self-model + limited autonomous agency + long-horizon conditioning`.
**Deferred:** полный автономный NPC cognition stack, отдельный avatar-specific social engine, тяжёлые second-order ToM, отдельная система эмоций.

- [ ] Каждая новая avatar-фича сначала доказывает, что её нельзя вывести из существующего общего механизма.
- [ ] Сущность, лишь переименовывающая existing state, не получает отдельного writer/store.
- [ ] Avatar vertical closure — до расширения в десятки специализированных параметров.

### 6.B. Будущие эпохи (пакеты реализации; ТЗ в `docs/Почти Актуальные TZ/`)

- [ ] **Эпоха 7 — Predictive Perception & Prophecy:** `TZ_Stage_2_5_..._1.md` (Часть I) + `VZ/TZ_§19_...md` (surprise = −log P(x_t|z_{t-1})); ObservationLayer/BeliefProjector (P1-31); Prophecy System (ADR-O-330), Vertical Slice «Секреты Люси — секреты таверны». Детализировано в PP (§6.A.3).
- [ ] **Эпоха 8 — Temporal Identity, линии времени:** `VZ/ТЕХЗАДАНИЕ ПРЕЕМНИКУ TZ-02 V.2.0` (WorldChronicle, 3 уровня времени), ADR-TIFL-001..003; `VZ/TEXTURES_AND_GEOMETRY_TZ.md` — visual aging после lineage.
- [ ] **Эпоха 9 — Общество + Memetic:** `VZ/TZ_MEMETIC_01..03`; Factions / Economy (`architecture/economy.yaml` есть, инженерного ТЗ нет) / Politics — ТЗ сформулировать.
- [ ] **Эпоха 10 — Bounded Rationality:** `VZ/TZ_§18_Resource_Bounded_Epistemic_Selection_Law.md` (`U_M = I·R·U − C`) — **только после** Belief Layer.
- [ ] **Эпоха 11+ — Контент и презентация** (когда угодно, изолированно): `ENIGMA_TZ_Female_Targeted_Dark_Fantasy_Layer.pdf`, Map Editor Smart Validation, `AWC_Process_World_Model_TZ.pdf`, Narrative Frame Onboarding, Laboratoria Kalibrovki (полигон).

---

## 7. Долг — единый реестр

> **Правило реестра (главное): долг без владельца и без следующего действия — запрещён.** Не «запомнить», а «кому и что». Чужие зоны — только уведомление, не чинить. Закрытие долга = галочка + строка в журнале §10.

### 7.1. AG1-D (реестр сессии AG1)

| ID | Долг | P | Зона/владелец | Действие | Статус |
|---|---|---|---|---|---|
| AG1-D1 | `V2RelationshipBackend` не имеет `_cache` → new_game reset падает | P1 | RE-01 M1b | сверка RE-D1 | открыт |
| AG1-D2 | `Dialogue update failed:` — тихий глоток в подписчике диалогов (L4-нарушение) | P1 | AG1 | — | ✅ закрыт 2026-09-03 |
| AG1-D3 | Witness-ветка reaction_subscriber:301–316 не под Gate-контрактом | P2 | AG1 | обвязать Proposal/Gate по прецеденту E2.0-b | открыт |
| AG1-D4 | `identity_traits` пусты после wait 12 — резонанс не доезжает | P2 | AG1 | диагностический круг: 3 команды | открыт |
| AG1-D5 | Аватар жив с hp=0 (`[FATE]`-лог каждый тик) | P2 | body | — | ✅ закрыт 2026-09-04 (Шаг 6); производный AVID-1 закрыт Шагом 7 |
| AG1-D6 | ~~Q4/Q5-рассинхрон имени модели~~ | P3 | LLM | — | ✅ закрыт (STALE: S217-фикс qwen_7b_q4 жив, config/llm_sources.json синхронизирован — S311-серия) |
| AG1-D7 | `actor → player:` пустой хвост при imp=0.8 | P2 | AG1 | трассировка producer-пути | открыт |
| AG1-D8 | ADR-O-377 не в реестре атласа | P1 | AG1/cross | запись в атлас + IMPACT + production-план | в работе (первый) |
| AG1-D9 | `affordance_facts_map`: гвард стоит, поле у W2-владельца не объявлено | P3 | W-track | уведомление владельцу | открыт |
| AG1-D10 | Ambient-шум в recall (canned-фразы наполняют кэш) | P3 | AG1/контент | Этап 1 (контентная важность) | открыт |
| AG1-D11 | Witness-fallback «телепатия» при пустых perceiving_npcs | P2 | AG1/perception | известная графа perception_filter; проверить прод-путь | открыт |

### 7.2. RE-D (реестр RE-сессии M1b.3.x)

| ID | Долг | P | Зона | Действие | Статус |
|---|---|---|---|---|---|
| RE-D1 | AG1-D1 сверка: reset_campaign переписан на RAM (M1b.4.2), `_cache` не существует — либо долг устарел, либо падение в другой точке | P2 | RE | прогон new_game при M1b.3.3 | открыт |
| RE-D2 | DialogueUpdateExtractor нулевые дельты (`trust=+0.0`; диалоги НЕ пишут отношения) | P1 | dialogue/AG1 | — | ✅ закрыт S248 (router fail-fast guard + working_memory гвард; DEBT-RE-D2A остаётся) |
| RE-D3 | BeliefCrystallization: таргеты `npc=break_progress:resistance` (не npc_id) — кристаллизация от не-агентов | P2 | identity | локализовать trait_drift source_id | открыт |
| RE-D4 | FLEE-массовость: 6/6 NPC FLEE при fear=0.0 | P2 | decision/калибровка | зонд score-разложения FLEE | открыт (живая склейка с FT-2/Н-53) |
| RE-D5 | `game_loop/__init__.py`: 20 ruff pre-existing (F401×14, F821×4, W291) | P3 | game_loop | god-file-декомпозиция (закон №15: не чинить в чужой сессии) | открыт |
| RE-D6 | scene_init W293×2 (докстринги) | P3 | scene_init | при следующей правке файла | открыт |
| RE-D7 | Директива Мастера: каноническая схема campaign-bootstrap JSON (world/actors/facts/relationships/knowledge/motivations; CANON/INITIAL-разделение; «JSON описывает причины, не поведение») | P2 | RE/authoring | отдельный ADR после M1b.3.x | открыт |
| RE-D8 | S135-статик decision_hub:166 = мёртвый путь + social_deltas standalone-копия | P2 | RE | зонд M1b.3.5 | открыт |
| D-MOM | `motor_output_mult` — orphaned derived state / dead consumer edge (§5) | P3 | Sleep/Decision-фронт | causal question после калибровки хронических порогов | открыт |

### 7.3. AUD-D (реестр внешнего аудита V.0.5.3.9.6, 2026-09-04)

Метод: статический скан (mypy 2.3.1 строгий конфиг, греп random/wall-clock/silent-fail, TODO-инвентаризация, call-sites). Каждый пункт привязан к файлу:строке.

| ID | Долг | P | Зона | Действие | Статус |
|---|---|---|---|---|---|
| AUD-D1 | **mypy: 726 ошибок в backend/app**. Hotspots: game_loop/__init__.py (63), tick_orchestrator.py (49), api/routes.py (37), llm/router.py (20), dm_agent.py (20), combat_math.py (17). Runtime-класс (union-attr/arg-type/attr-defined/call-arg ≈209) — латентные краши | P1 | cross | триаж P17; CI-храповик «новых ошибок нет» | открыт |
| AUD-D2 | social_subscriber None-инвариант (`RelationshipWriteGate\|None.apply` ×5) | P1 | events | — | ✅ закрыт (Шаг 5: провод стора + skip-путь; P97-верификатор зелёный) |
| AUD-D4 | `npc_state.py:613–621` `_ALLOWED_WRITERS`: 4 wildcard-писателя (`"*"`: npc_loader, phases.decision, phases.memory, life_engine) — контракт «StateApplicator = единственный L2 writer» обойдён санкционированно | P1 | npc | зарегистрировать как A11; мигрировать 4 модуля; сузить `"*"` (прецедент avatar_state_applicator) | открыт |
| AUD-D5 | Legacy `RelationshipStore` жив в прод-пути (state_applicator:62, memory_manager:28): (а) TTL 3600 c через `time.time()` — wall-clock ветка, кандидат replay-дрейфа; (б) `except → тихий {}` — сброс данных; (в) `_save` пишет legacy JSON | P2 | RE | решение судьбы в M1b.5/M1b.3.5; минимум TTL→tick-based, except→Fail Loud | открыт |
| AUD-D6 | **DilemmaEngine — мёртвый контур в проде**: `check_triggers()` каждый тик, но `register_dilemma()` не вызывается никем → `_dilemmas` пуст | P2 | social/MVP | канон `dilemmas.json` + загрузчик в init_campaign, или исключить check_triggers | открыт |
| AUD-D7 | `main.py` — 34 `print()` живы (строки 98–365, блок запуска). Долг «print→logger ✅» не соответствует билду | P3 | main | заменить на logger (единый фронт с LOG-GATE) | открыт |
| AUD-D8 | ~~`mypy.ini` повреждён~~ | P3 | CI | — | ✅ закрыт (S311-серия: STALE — конфиг здоров, `mypy` первой строкой; вероятно, починен ранее чужой сессией без записи) |
| AUD-D9 | `dm_phase.py:175–176` — `intent="dialogue"`, `tone=""` захардкожены: метаданные памяти обеднены | P3 | game_loop | LLM-классификация полей или mini-ADR об MVP-упрощении | открыт |
| AUD-D10 | **Ambient-наблюдения не попадают в ObservationLog**: прод-писатели только action_consequence_compiler:108 и npc_confession_parser:95; `visual_cue`/`eavesdrop` без источника — журнал расследования слеп | P2 | player_cognition/T9 | мост perception → observation_log (T9) | открыт |
| AUD-D11 | TODO/FIXME: 75 маркеров в 48 файлах (отслеживалось только 5 в domain/) | P3 | cross | классификация P4 | открыт |

### 7.4. Хвосты полевых тестов и журнала (преемник «Пункт 5»)

| ID | Долг | P | Действие | Статус |
|---|---|---|---|---|
| PROBE 9.7 | run_turn materialization parity | P1 | — | ✅ закрыт (Шаг 3: execute_pending в REST-пути, game_loop/__init__.py) |
| AVID-1 | Аватар вне idle-снапшота | P2 | — | ✅ закрыт (Шаг 7, вердикт GAP: idle-проводка all_npcs_raw + upsert_character) |
| FT-1 | Адресация реплики: npc_id как форма прямого матча | P1 | — | ✅ закрыт S245 (npc_id-ветка в PlayerTargetExtractor.extract:638; stash-дифференциал + зонды 3/3) |
| FT-2 | FLEE+позиции: «threat not found in npc_positions» ×12; Люся выпадает из позиций idle | P1 | пост-мортем по scene_changes_*.jsonl; зонд; склейка RE-D4/Н-53 | открыт |
| FT-3 | Пусто-текстовые speech-эпизоды imp=0.80 | P2 | — | ✅ закрыт S248 (producer write_npc_reactions_to_memory — пустой хвост без фильтров) |
| AI-D1 | `test_game_loop_pipeline.py` — единственный юнит-гейт _run_pipeline permanently SKIPPED (конструкторные моки §13.4) | P2 | рефактор в headless-класс или retirement с переносом ассертов | открыт |
| ST-1 | stream_turn: нет commit/unlock/execute (SSE недостижим в Direct-контракте, лок мягкий) | P2 | при активации SSE — патч-зеркало PROBE 9.7; кандидат REACH-03 | открыт |
| PH-1 | `test_player_turn_headless.py` мёртв под ADR-WRITE-GUARD (пост-конструкционные записи из tests.*) | P2 | миграция на конструкторные kwargs/фабрику; гейт после GC-00 | открыт |
| SC-1 | SHADOW_COMPILER «Node not found» в run_turn (tavern:entrance/right_table/fireplace — namespace целей vs граф) | P2 | археология источника node-id; вердикт о namespace-каноне | открыт |
| DEBT-RE-D2A | intelligence queue = production-форма ADR-O-377 | P1-арх | формальный ADR там | открыт |
| F-NS1 | namespace-хвост S248 | P2 | по археологии SC-1 | открыт |

### 7.5. Системный долг (не блокирует, брать паузами)

- [ ] **God-файлы:** `game_loop/__init__.py`, `life_engine.py`, `tick_orchestrator.py`.
- [x] ~~mypy --strict spatial-слои~~ ✅ 0 ошибок (spatial_runtime, spatial_service, graph_compiler, spatial_query_service, npc_state; было 79 каскадных).
- [x] ~~print() → logger~~ ✅ (36 вхождений main.py) — ⚠️ AUD-D7: статус частично откатился (34 `print()` живы).
- [~] TODO/FIXME domain/ — 5 backlog-маркеров (не баги).
- [x] ~~DEBT-IPT-RUFF~~ ✅ ruff clean.
- [ ] **DEBT-QUIESCE** (async-interleaving недетерминизм) — внешняя зона (async-слой), НЕ косметика тестов. Симптом (S237): между идентичными OFF-прогонами варьируют пропорция COMPLETED/INTERRUPTED и микропозиции при стабильных терминалах/наборах. Влияние: A/B-гейты закрываются с ambient qualification (GORAN β G1 — прецедент). Вердикт Мастера: воспроизводимые причинные цепочки уровня «кража → наблюдение → вера → смена цели» требуют execution/interleaving-детерминизм как ФУНДАМЕНТАЛЬНЫЙ слой — кандидат W-контура после стабилизации. Точка данных: latent TICK_CRASH npc_tick_pipeline:703 (active_commitments DOUBLE TRUTH) — interleaving-зависим. Связь: GC-19.
- [ ] **rng-бомба** (остаток MATH-8/П-7/П-11) — линтер v2 ловит Optional-дефолты и literal-seed (S315), 9 сайтов промаркированы `ADR-O-301-DEBT`; боевые фиксы (KernelRNG-инъекция в combat_math, routes d20, `apply_damage` status-дубль) — MATH-8.
- [ ] **W-ретрансляции Мастеру:** `data/replay.db` = 754 МБ / 68k snapshots (рост без ротации).
- [x] ~~DEBT-W-AUDIT~~ ✅ (S240, §4.1). · [x] ~~DEBT-W-STORE-INCIDENT~~ ✅ ACCEPT (закон-урок §4.2).

### 7.6. Прочие реестровые хвосты

- [ ] Н-6 (HEARING_RADIUS), Н-9 (consciousness_state doc drift), Н-11 (стаб trace_causal_chain), Н-12 (wildcard-writers Task 0.9 = AUD-D4), Н-21 (soft-degradation снапшота), Н-31 (uuid4 в Фазе 6), Н-32 (H-37 FIX лжёт), Н-43 (FSM без владельца вызова), Н-45/Н-46 (sweep vanished / bypass-легализация — частично легализованы S203.3), Н-52 (мёртвая ветка), Н-53 (GROUND_TRUTH location_id=''), Н-56 (DLG_QUEUE OVERFLOW — единая первопричина churn), DEBT-R1 (radius 999.0 THEFT), DEBT-R3 (закрыт S209), DEBT-R10 (avatar psyche — vertical slice), DEBT-E1 (PlayerBeliefModel authority→projection, 6 шагов, §18 Устава), DEBT-EVBUS, DEBT-SOC, DEBT-L1-SQLITE, DEBT-MOCK, DEBT-CL1, CAL-1, pytest.ini-hygiene, world_tick.json вне saves/, фантом-каталог backend\backend\data, CONFIG-DEBT.
- [x] ~~S301-дубль в MUTATIONS.md~~ ✅ разрешён (MUTATIONS v5.0): канон S301 = Replay Phantom (жив хвост R5), «Доска-детектив К1» = S302; пропуски номеров (S153/S171/S173/S197/S232/S275–S277) зафиксированы в шапке как артефакты ренумберов.

---

## 8. MASTER TODO — реестр направлений

> **Это справочник существующих направлений, НЕ очередь.** Очередь — только §0.2. Приоритет задаётся тегами: A-секция — блокирует качество причинной игры; далее B–T — по лестнице «Рекомендуемый порядок». Если задача не в §0.2 и не prerequisite для неё — сначала докажи, почему её нужно менять (§0.2).

### A. СЕЙЧАС — блокирует качество причинной игры

- [ ] **A0** Закрыть RE-01 **M1b.3.5–3.7** (активный фронт): 3.5 flat-readers-зонд (находки RE-D8) → 3.6 S128-разделение → 3.7 греп-страж. Затем A1.
- [ ] **A1** RE-01 M1b.5: удалить мёртвый `apply_npc_state_updates` (0 вызовов, греп) + судьба legacy `RelationshipStore` и vestigial provider v2 (REMOVED/фасад по факту readers).
- [ ] **A2** RE-01 M2/D: `RelationshipEventSemantics` + первый живой needs-writer через `update_needs` + формат RE-событий.
- [ ] **A3** G/H: Satisfaction + frustration через стор.
- [ ] **A4** K: removal-test; Полигон M: INV-1, О-2.
- [ ] **A5** GC-11 (L3-gate до M2/D) + доказательство персистентности trust-дельт чтением стора (в журнале: «delta applied ≠ relationship state verified»).
- [ ] **A6** RE-D7: каноническая схема campaign-bootstrap JSON (отдельный ADR).
- [ ] **A7** BC-2 → BC-3 (Эпистемический контур, §3.5): вывод меняет прогноз; прогноз меняет DecisionHub. Full-cell GC-04.
- [ ] **A8** GC-08-инфраструктура: capability `spawn_world_object` для harness (§9.2) — prerequisite object-cognition W-трека.
- [ ] **A9** Body V1+ калибровка (§5.1) через Calibration Lab.
- [ ] **A10** Сохранить IPT 49/49 + профильные линтеры после каждого шага.
- [ ] **A11** Wildcard-writers NPCState (AUD-D4): миграция 4 модулей, сужение `"*"`.

### B. КОГНИЦИЯ / ОБУЧЕНИЕ (Эпистемический контур)

- [ ] **B1** Experience → Conclusion — ✅ S247 (ADR-O-381, BC1_ENABLED default OFF): триплет (subject, predicate, object) + confidence [0..1] + evidence[event_ids → L1] + source=DIRECT_EXPERIENCE; НЕ фразы, НЕ флаги поведения. Приёмка bc1_conclusion_test 6/6: A — threat-событие → DeltaGate → EXPERIENCE_DELTA_COMMITTED → Фаза 9 → ConclusionGate → Store (вывод без текста/LLM); B — NO-VACUUM (0/0/0); C — state-канал concordance; D — мимо Gate → ArchitecturalViolationError; E — рестарт round-trip; OFF — dormant. Механизм доказан; потребитель — B2/BC-2.
- [ ] **B2** Conclusion → Expectation.
- [ ] **B3** Expectation → existing DecisionHub.
- [ ] **B4** Repetition → generalization/crystallization.
- [ ] **B5** Contradiction → belief revision.
- [ ] **B6** Personal conclusion → testimony.
- [ ] **B7** Testimony → recipient belief with provenance/confidence.
- [ ] **B8** Derived social strategies: avoid/refuse/warn/seek/help/reconcile.
- [ ] **B9** Learning from another NPC.
- [ ] **B10** Self-model updates: «я могу/не могу», «я ошибся», «мне нужно изменить стратегию».
- [ ] **B11** Social triangle / reputation emergence.
- [ ] **B12** Long-horizon emergent scenarios and replay tests.

### C. ПСИХИКА — после B, без взрыва количества флагов

- [ ] **C1** Unified appraisal space. · **C2** Derived emotion regions. · **C3** Shared decay/accumulation/interference rules. · **C4** Mood as recent appraisal field, not a second emotion database. · **C5** Memory reactivation of affect. · **C6** Emotion/action voting over available actions. · **C7** Social contagion with distance/provenance/intensity bounds. · **C8** Expression dictionary separated from causal state. · **C9** Calibration laboratory + scenario corpus.

### D. PERCEPTION / EPISTEMICS

- [ ] **D1** ObservationLayer/BeliefProjector. · **D2** Unified epistemic source-of-truth. · **D3** First-order NPC beliefs about world/agents. · **D4** Second-order ToM only where justified. · **D5** Surprise/prediction error as measurable epistemic discrepancy. · **D6** Belief revision with confidence, provenance, contradiction. · **D7** Prophecy/prediction vertical slice. · **D8** Epistemic persistence save/load. · **D9** Replay determinism for epistemic chains.

### E. BODY / HOMEOSTASIS / EMBODIED AGENCY

- [ ] **E1** Needs writer via RE-01 M2/D. · **E2** Energy/hydration/nutrition → fatigue → sleep → recovery. · **E3** Pain/injury → affordance/constraint → action. · **E4** Temperature and environmental pressure. · **E5** Body state не flat/frozen в production snapshots. · **E6** Intent → commitment → execution → verification. · **E7** Stale intent cancellation. · **E8** Single owner of behavior. · **E9** Bounded conversation and cooldowns. · **E10** Valid idle/settled state; eliminate perpetual movement/chat. · **E11** Sleep delivery and alternative sleep affordances (см. §5.3, GC-10). · **E12** Death/recovery semantics и DeathState TODOs.

### F. WORLD / OBJECTS / AFFORDANCES

- [x] **F1** W2 AffordanceResolver — ✅ S232/ADR-O-372 (24 теста).
- [x] **F2** W3 + causal writer G3 — ✅ (домен/стор/спавнер S237/ADR-O-376, live=18; воля→цель→мутация→событие S307/ADR-O-410).
- [ ] **F3** Caller guard / single writer в WorldObjectStore (Г4 `_ALLOWED_WRITERS`; текущие писатели через инъекцию — legal).
- [ ] **F4** W4 embodied state: pose, locomotion, grasp, attachment. · **F5** Objects become actionable affordances for NPC reasoning. · **F6** Furniture/tasks/containers/resources в action selection. · **F7** W5–W9 presentation projector/rendering contracts. · **F8** Renderer remains pure consumer. · **F9** Object consequences в Chronicle/Memory.

### G. TIME / IDENTITY / LINEAGE

- [ ] **G1** WorldChronicle. · **G2** Three time levels and consistency rules. · **G3** Persistence across save/load. · **G4** Identity continuity through long campaigns. · **G5** Lineage/ancestry/ownership history. · **G6** Visual aging after lineage. · **G7** Historical consequences: old actions remain legible.

### H. SOCIETY

- [ ] **H1** Factions. · **H2** Reputation emerging from testimony + observed behavior. · **H3** Economy. · **H4** Politics/power relations. · **H5** Institutions/roles/authority. · **H6** Cooperation, coalition, exclusion. · **H7** Social norms and norm violations. · **H8** Sanctions/rewards/boycotts. · **H9** Group-level memory без замены individual memory. · **H10** Population-scale stability: 50+ NPC × 30+ min.

### I. MEMETIC / CULTURAL

- [ ] **I1–I3** MEMETIC-01..03. · **I4** Beliefs/rumors mutate through transmission. · **I5** Cultural norms from repeated social reinforcement. · **I6** Competing narratives and source credibility.

### J. BOUNDED RATIONALITY

- [ ] **J1** Belief Layer prerequisite. · **J2** Information/resource/cost model `U_M = I·R·U − C`. · **J3** Attention limits. · **J4** Memory retrieval cost/selection. · **J5** Action evaluation budget. · **J6** NPC-specific rationality limits. · **J7** Bounded rationality создаёт правдоподобные ошибки, не random stupidity.

### K. ACTIVE INFERENCE / HABITS

- [ ] **K1** Определить реальную world model до тяжёлой математики. · **K2** Prediction → candidate futures → expected consequence → action. · **K3** Habit formation from repeated successful action sequences. · **K4** Habit decay/interference. · **K5** Exploration vs exploitation. · **K6** Information-seeking as an action. · **K7** Performance benchmark: active inference не становится tick bottleneck.

### L. COUNTERFACTUAL / REFLECTION

- [ ] **L1** Store decision/outcome pairs для «what if». · **L2** Counterfactual alternative generation. · **L3** Regret/relief/guilt/confidence как derived appraisals, не флаги. · **L4** Counterfactual impact on future strategy. · **L5** Bound computation — NPC не симулирует фьючерсы бесконечно.

### M. MEMORY / SELF / LEARNING

- [ ] **M1** EventMemory persistence. · **M2** Belief persistence. · **M3** Relationship persistence. · **M4** Replay exactness after save/load. · **M5** Memory salience/decay calibration. · **M6** Consolidation: episodic experience → durable knowledge. · **M7** Self-model/identity changes from experience. · **M8** Skill/knowledge acquisition from social teaching. · **M9** Forgetting selective, not arbitrary. · **M10** False/uncertain memory только если epistemic design требует.

### N. DIALOGUE / LANGUAGE / EXPRESSION

- [ ] **N1** DialogueQueue production-path audit/closure. · **N2** SpeechScheduler pacing/dedup в main path. · **N3** LLM timeout/cancellation (один зависший вызов не блокирует execution). · **N4** Preserve proposition on DialogueRequest failure; no silent dict fallback. · **N5** Dialogue grounded in actual belief/memory/relationship state. · **N6** NPC может не соглашаться с собственным прежним statement при изменении belief. · **N7** NPC может цитировать source/provenance («я видел», «мне сказал X»). · **N8** NPC может сознательно withhold information. · **N9** NPC может лгать, когда world/social conditions оправдывают. · **N10** Expression варьируется по personality/appraisal без изменения causal truth.

### O. ACTION / SOCIAL BEHAVIOR

- [ ] **O1** Rich action vocabulary: approach, leave, refuse, help, accuse, warn, gossip, reconcile, negotiate, teach, learn, observe, hide, trade, defend, betray. · **O2** Affordance-based fallback. · **O3** No hardcoded emotion→action rules. · **O4** Action selection учитывает opportunity, distance, risk, allies, relationship. · **O5** Social actions создают consequences для memory/relationship. · **O6** NPC распознаёт занятость другого NPC (разговор с кем-то ещё). · **O7** Turn-taking, attention, conversational ownership. · **O8** Spatial/social awareness: кто присутствует, кто слышит, кто может вмешаться. · **O9** Persistent refusal/avoidance из expectations, не флагов.

### P. HARDENING / QUALITY / PERFORMANCE

- [ ] **P1** DEBT-QUIESCE (§7.5). · **P2** Remaining god-file decomposition. · **P3** mypy --strict вне spatial-слоёв. · **P4** TODO/FIXME classification. · **P5** Kernel RNG audit. · **P6** wall-clock audit. · **P7** silent-failure audit. · **P8** frontend-isolation audit. · **P9** L1 append-only audit. · **P10** Epistemic boundary audit. · **P11** Replay determinism. · **P12** 1000-tick LLM-free survival test. · **P13** Long-horizon drift tests. · **P14** Performance budget 6/50/100+ NPC. · **P15** Memory growth/compaction. · **P16** Async cancellation/executor saturation. · **P17** mypy-триаж AUD-D1: 726 → политика «runtime-классы в kernel-файлах первыми»; CI-храповик «не хуже текущего»; гигиена — попутно при god-file-декомпозиции. Не «починить все» — осознанный порядок. · **P18** `lint_kernel_rng` v2: AST-запрет `Optional[random.Random] = None → _rng = rng or random` и `rng_seed: int = 42` — RNG-бомбы за Optional-дефолтами невидимы текущему линтеру (П-7, AUD-D12).

### Q. CALIBRATION / OBSERVABILITY

- [ ] **Q1** Scenario corpus body/social/epistemic. · **Q2** Differential tests для одного causal change. · **Q3** DriftLab 200/1000/10000 tick profiles. · **Q4** Social chain traces with provenance. · **Q5** Separate «mechanism works» from «content is good». · **Q6** Metrics, детектирующие живое поведение без путаницы motion с causality. · **Q7** Never allow observability to mutate state.

### R. CONTENT / WORLD DESIGN

- [ ] **R1** Tavern vertical slice с осмысленными задачами. · **R2** NPC schedules and role obligations. · **R3** Food/resources scarcity. · **R4** Furniture/object affordances. · **R5** Secrets and social consequences. · **R6** Relationships с asymmetric preferences. · **R7** Teaching/learning scenes. · **R8** Betrayal/reconciliation scenarios. · **R9** Reputation/social exclusion scenarios. · **R10** Long-lived NPC stories. · **R11** Campaign/world onboarding. · **R12** Dark-fantasy layer — если направление продукта остаётся.

### S. TOOLING / SDK / EDITOR

- [ ] **S1** Map Editor smart validation. · **S2** Visual design social graphs. · **S3** Visual design factions/relationships. · **S4** Visual design world affordances. · **S5** Campaign/content SDK. · **S6** Scenario runner for social experiments. · **S7** Replay/trace viewer. · **S8** Calibration dashboard. · **S9** Authoring tools: secrets, norms, jobs, relationships.

### T. UI / PRESENTATION

- [ ] **T1** PresentationProjector. · **T2** Renderer pure-consumer compliance. · **T3** Player goal overlay. · **T4** Journal tabs and temporal/social history. · **T5** Exit-tavern/modal flow. · **T6** Name recognition pacing. · **T7** NPC movement speed / readable staging. · **T8** Social consequences observable без раскрытия hidden variables. · **T9** Ambient-наблюдения → ObservationLog + журнал игрока: автофиксация `visual_cue`/`eavesdrop` (в т.ч. «рваный» текст по clarity), провенанс глаз/ухо/рот, маркер NEW (см. AUD-D10).

### U. ОТЛОЖИТЬ — намеренно не делать пока (каноническая запись в §0.3; здесь — ссылка)

См. §0.3 «Отложено намеренно». Не предлагать как работу без решения Мастера.

### V. ДОЛГОСРОЧНЫЕ ВОЗМОЖНОСТИ

- [ ] **V1** Group emotions / crowd dynamics. · **V2** Collective memory / traditions. · **V3** Reputation markets / information brokers. · **V4** Institutional memory. · **V5** Generational knowledge transfer. · **V6** Language/cultural drift. · **V7** Emergent norms and taboo formation. · **V8** Multi-agent coalition formation. · **V9** Resource-driven social stratification. · **V10** Historical causality over months/years. · **V11** NPC-specific life projects and legacy. · **V12** World-level narrative emergence from distributed memory.

### Рекомендуемый порядок из MASTER TODO

`A1–A11 → GC-00/01 + NEG-01…06 → B1–B12 → C1–C9 + D1–D9 → E/F hard runtime + GC-03…11 → AV1–AV4 + AV-GC-01…05 → AV5–AV10 + AV-GC-06…10 → HU1–HU5 → HU6–HU13 + GC-29…40 → AV11–AV16 + AV-GC-11…16 → GC-17…24 → G → H/I → J/K → L → M/N/O enrichment → GC-25…28 + SCALE → P/Q hardening at scale → R/S/T content/tooling → V long-horizon`.

**Почему AV разбит на два прохода:** сначала оживить уже существующие psyche/values/resistance и получить короткий L3 vertical; затем inner voice, negotiation, recovery, humor integration. Полная avatar epistemics и limited autonomy — только после того, как общие memory/epistemic/relationship substrates реально production-connected. Это предотвращает создание «второго ENIGMA» внутри player actor.

**Ключевой принцип:** не строить систему для названия явления, если уже существует более общий механизм, из которого явление выводится.

**Avatar principle:** `PLAYER INPUT ≠ AVATAR WILL`. Класс, происхождение, ценности, предпочтения, страх, отношения, память и опыт — не декоративные теги: если заявлены как игровые свойства, они обязаны иметь путь `state → appraisal → action → consequence → future state`. Аватар не получает отдельный cognitive stack, если то же явление выражается общим механизмом NPC.

---

## 9. GAMEPLAY CLOSURE — обязательный слой доказательства

### 9.0. Зачем этот раздел существует

Роадмап хорошо доказывает наличие отдельных механизмов, контрактов и линтеров, но этого недостаточно для утверждения **«игра работает»**. SUPERBOX отвечает «механизм вообще способен работать?», AUD — «есть ли дефект в production-коде?», GAMEPLAY Closure — на более строгий вопрос:

> **Может ли игрок вызвать причинную цепочку через настоящий production-путь, переживает ли она тик, меняет ли состояние NPC/мира, влияет ли на следующий выбор и становится ли следствие наблюдаемым игроком?**

Gameplay-тесты не заменяют IPT/SUPERBOX/AUD. Они закрывают отсутствующий уровень доказательства — **L3: player → runtime → consequence → future behavior → observable result**.

### 9.1. Четыре уровня доказательства

| Уровень | Вопрос | Тип проверки | Что НЕ доказывает |
|---|---|---|---|
| L0 | Контракт существует? | schema / type / static | runtime |
| L1 | Механизм работает изолированно? | unit / SUPERBOX | production reachability |
| L2 | Production-путь вызывает механизм? | integration / canary | полноценная игровая история |
| **L3** | Игрок может вызвать цепь и получить устойчивое следствие? | **vertical gameplay test** | художественное качество |
| L4 | Человек может понять причинную цепь? | Chronicle / Inspector / UI | внутреннюю корректность |

**Правило:** feature нельзя считать «закрытой» только по L1. Для значимой игровой механики требуется минимум L2 + L3; для систем, видимых игроку, — также L4.

### 9.2. Канонический `TavernGameplayHarness`

Не создавать второй simulation engine. Harness вызывает существующий production runtime через минимальный интерфейс:

`new_game(seed)` · `spawn_npc(...)` · `spawn_world_object(...)` · `move_player(...)` · `player_action(...)` · `advance_ticks(n)` · `inspect_npc(...)` · `inspect_world(...)` · `get_chronicle(...)` · `save_game() / load_game()` · `replay_from_seed(...)`

Harness обязан проходить через настоящий `TickOrchestrator`, `NpcTickPipeline`, `DecisionHub`, WorldSnapshot, EventCompiler/ProjectionEngine и зарегистрированных subscribers. **Запрещено вручную вызывать внутренний writer, чтобы «доказать» его работу.**

**Закон-урок харнессов:** обязателен патч `settings.saves_dir` до `build_game_loop` (§4.2).

### 9.3. GAMEPLAY Acceptance Tests (GC)

- [ ] **GC-00 — Game is actually alive.** 6 NPC tavern, 100 LLM-free ticks. За прогон существуют decisions, movement/settled states, physiological changes, observations, memory/experience events, relationship activity там, где есть причины. Один seed → одинаковая causal history. Нулевые counters сами по себе не доказательство смерти — проверять production trace. 📌 *Текущий статус: тест существует (`tests/gameplay/test_tavern_vertical.py`), baseline №4 3/3 PASSED (93.44s, CLEAN-START верифицирован, коммит bd4); матрица §9.10 — «закрыто», «уверены» — открытые.*
- [ ] **GC-01 — Real Tick Vertical Slice.** `new_game → real tick → snapshot → decision → execution → verification`. Harness не обходит production path; один NPC проходит полный цикл.
- [ ] **GC-02 — Player action → world consequence.** Игрок действует над объектом; объект меняет canonical state; изменение попадает в causal/event слой и остаётся после следующего тика. Не сливается с GC-08 (player→world ≠ object→affordance→action).
- [ ] **GC-03 — Observation → Experience/Memory → changed behavior.** NPC реально видит/слышит событие в пределах perception rules; observation создаётся; experience/memory сохраняется; следующий выбор отличается от baseline.
- [~] **GC-04 — Experience → Conclusion → Expectation → Decision.** Повторяемое событие порождает машино-пригодный conclusion; conclusion меняет expectation; expectation входит в DecisionHub; NPC выбирает действие, которое без history не выбрал бы. **S243: сегмент E2-state→DecisionHub доказан** (causal_state_test A/C — флип argmax от авторизованной дельты без текста); Conclusion = BC-1 ✅; Expectation = BC-2, открыт. Full-cell закрытие — после BC-3.
- [ ] **GC-05 — Testimony → Belief → third-party behavior.** A переживает, сообщает B; B учитывает provenance/source/confidence и меняет belief; B или C демонстрируют поведенческое следствие.
- [x] **GC-06 — Same world, different history → different behavior.** Два прогона из одинакового мира и seed, различная история. При одинаковом snapshot поведение расходится из-за сохранённой history/epistemic state. ✅ S243: одна WorldSnapshot+seed, единственная переменная = авторизованная дельта истории; argmax Люси расходится (flee vs call_for_help); Горан — state-эффект в скорах при H1-ландшафте (флип-порог не пересечён — свойство натуры, не разрыв). LIMITATION: decision-level (материализация движения — BC-12).
- [ ] **GC-07 — Same event, different observation → different belief/behavior.** Два NPC в одной сцене, но один имеет доступ к событию, другой нет (или иной clarity/provenance). Не должны автоматически получать одинаковое знание.
- [ ] **GC-08 — World object → affordance → action → world change.** NPC обнаруживает объект/ресурс, получает affordance, принимает действие, достигает target, выполняет interaction, изменяет объект. **Назначенный L3-гейт G3/W-трека** (§9.9); prerequisite — capability `spawn_world_object`.
- [ ] **GC-09 — Body → constraint → action → recovery.** Дефицит energy/hydration/sleep/pain становится homeostatic pressure, ограничивает affordances/decision, вызывает подходящее действие, а recovery меняет body state обратно. Проверять реальным тиком, не прямой записью body-поля.

```
Дефицит (energy/hydration/nutrition/sleep/pain) → canonical homeostatic pressure
Pressure → ограничивает affordances → меняет Decision landscape → вызывает embodied action
→ требует реального достижения world affordance → запускает recovery runtime → изменяет BodyState.
```

Запрет: прямой test-write body field — не считать доказательством recovery. **Статус: GC-09A (Body Runtime) ✅ GREEN (`7f369e54`); GC-09B (Embodied Constraint) RED→закрыт через ADR-O-383 V1 (§5.1). Остаток: recovery-ветка (по §9.9 — реестр привязок).**

- [ ] **GC-10 — Sleep delivery.** NPC получает sleep pressure, выбирает reachable sleep target, проходит traversal, становится settled, и только после этого sleep state снижает pressure. Отдельно проверить альтернативные sleep affordances (BED/HAMMOCK/GROUND/SHELTER) — только если действительно отличаются по recovery conditions, не ради контентного enum.

```
NPC: accumulates sleep pressure → changed constraints/landscape → selects recovery intent
→ discovers valid sleep affordance → validates reachable target → traverses → settled
→ enters sleep state → deterministic recovery → can be interrupted by relevant perception/threat
→ resumes or exits → wakes with causally derived BodyState.

Acceptance: same seed + same world + same sleep history → same sleep/recovery outcome.
Interrupted sleep ≠ uninterrupted equal nominal duration, если различие имеет доказанную causal работу.
```

Связь: DEBT-SLEEP-DELIVERY (§5.3).
- [ ] **GC-11 — Relationship event → state → future social action.** Реальное социальное событие проходит RelationshipEventSemantics → canonical writer → snapshot → DecisionHub и меняет последующее социальное действие. **Назначенный L3-гейт RE (следующий фронт, §9.9); обязателен для закрытия M2/D.** Также: доказательство персистентности trust-дельт чтением стора.
- [ ] **GC-12 — Repeated evidence → generalization.** Одного эпизода недостаточно. Повторяемая evidence усиливает conclusion/expectation; противоположные наблюдения ослабляют/ревизуют.
- [ ] **GC-13 — Contradiction → belief revision.** NPC ожидает X, получает наблюдаемое not-X, получает prediction error/surprise, пересматривает belief/expectation, демонстрирует новое поведение.
- [ ] **GC-14 — Self-learning.** Действие → результат → изменение self-model/knowledge/skill → повторная ситуация даёт иной выбор.
- [ ] **GC-15 — Social triangle.** A влияет на B, B взаимодействует с C; C получает доступную ему информацию/событие. Изменение отношений A–C/B–C — из общих механизмов, без triangle flag.
- [ ] **GC-16 — Long-horizon story.** 100–1000 тиков: `оскорбление→память→избегание`, `обман→вывод→слух→осторожность`, `помощь→благодарность→ответная помощь`, `обучение→новое действие`. Не допускается perpetual movement/chat или стирание причинной истории. **Периодический gate зрелости (§9.9) — не на каждую стадию.**
- [ ] **GC-17 — Competing writers / state integrity.** Два источника меняют одно canonical поле: только авторизованный writer; wildcard обход невозможен. Проверять не только grep, но и runtime-конфликтом.
- [ ] **GC-18 — Wall-clock independence.** Одинаковый seed/scenario с различными реальными задержками между тиками — результат и replay совпадают. `time.time()` не меняет gameplay state.
- [ ] **GC-19 — Async/interleaving determinism.** Один сценарий несколько раз при разных допустимых задержках/порядках async completion. Проверяются canonical causal history, commitment terminal states, micropositions. Допустимые различия явно отделяются от причинно значимого state. Связь: DEBT-QUIESCE.
- [ ] **GC-20 — Persistence continuation.** Сохранить в середине причинной цепи, загрузить, продолжить: NPC memory, beliefs, relationships, body, world objects, identity продолжают историю без reset/duplicate application.

```
GC-20 — Temporal Recovery → Future Behavior:
одинаковый world snapshot + seed + текущий input, но различная temporal recovery history
→ canonical body/perception state → changed decision landscape → different future behavior.
Никакого random modifier. Расхождение объяснимо через Chronicle / Snapshot / causal provenance.
```

- [ ] **GC-21 — Replay exactness.** Один seed + одинаковый input/event stream → одинаковые snapshots, causal events, terminal outcomes. Сравнивать не только финальные числа, но идентичность причинной цепочки.
- [ ] **GC-22 — Ambient discovery reachability.** NPC/player в зоне `visual_cue`/`eavesdrop`; observation реально появляется в ObservationLog с provenance `eye/ear`; secret становится discoverable, появляется в журнале игрока. Проверить низкую clarity/«рваный» текст. Закрывает AUD-D10.
- [ ] **GC-23 — Dilemma reachability.** MVP dilemma загружается в production `init_campaign`, попадает в registry, вызывается игровым условием. Тест обязан падать, если `check_triggers()` жив, но `_dilemmas` пуст. Закрывает AUD-D6.
- [ ] **GC-24 — LLM failure isolation.** LLM задерживается/падает/отменяется. WorldTick не зависает, bounded worker освобождается, быстрый мир живёт, LLM-originated proposal не становится SSOT. Отдельно покрыть путь отмены `abort_generation` (AUD-D3).
- [ ] **GC-25 — Chronicle causal trace.** Для реальной истории Chronicle показывает минимум: `что произошло → что изменилось → почему → что изменилось в будущем поведении`. Chronicle читает trace/state и не мутирует их.
- [ ] **GC-26 — NPC Inspector explanation.** Для текущего решения NPC: provenance-путь от доступных affordances/constraints через relevant memory/belief/expectation/relationship/body pressure к выбранному действию. LLM — не источник объяснения причинности.
- [ ] **GC-27 — Player-visible consequence.** Цепочка, которую engine считает успешной, имеет наблюдаемый результат в реальном frontend: изменение положения/объекта/действия/диалога/отношения или иной presentation effect. Renderer — pure consumer.
- [ ] **GC-28 — Full Tavern Living World.** 6 NPC, player, world objects, relationships, secrets, body pressures, ambient observations. Минимум 200 тиков. Несколько независимых причинных цепочек, не сливающихся в одну глобальную реакцию. Завершение без silent-fail, с сохранением причинной истории.
- [ ] **GC-29 — Humor perception vertical.** Expectation → incongruent event → valid resolution → amusement. Same event without resolution — non-humorous.
- [ ] **GC-30 — Same event, different NPC.** Identical event → amusement / confusion / neutrality / offense / threat — объяснимо их expectation, appraisal, relationship, knowledge, current state.
- [ ] **GC-31 — Temporal humor plasticity.** Same NPC + same event в разных точках истории → разные outcomes, т.к. experience/state/relationship изменились. No direct humor-field mutation.
- [ ] **GC-32 — Benign violation.** Same norm violation, разные audience/context → разные outcomes; low trust сама по себе не подавляет весь humor.
- [ ] **GC-33 — Coping humor under acute pressure.** Humor доступен как ответ только когда appraisal/motivation/social context поддерживают; resulting action имеет causal consequences.
- [ ] **GC-34 — Coping humor under chronic pressure.** Long-running stress меняет propensity/form через accumulated pressure/memory/self-model; no timer, no permanent `humor_mode`.
- [ ] **GC-35 — Failed humor.** Attempt misunderstood/rejected; слушатель и говорящий приобретают appropriate experience; будущие expectations/relationship behavior могут отличаться.
- [ ] **GC-36 — Audience model.** Выбор шутить/как шутить зависит от того, кто слышит, relationship, status, threat, expected reaction.
- [ ] **GC-37 — Social transmission of humor.** A шутит, B слышит, C нет; B сохраняет testimony/experience, C не получает информацию без causal transmission.
- [ ] **GC-38 — Humor production is unscheduled.** За длинный LLM-free run NPC не испускают шутки просто потому, что N тиков прошло; каждая попытка имеет causal trigger.
- [ ] **GC-39 — Humor observability.** Chronicle/Inspector реконструирует «почему реакция/попытка» без LLM как causal authority.
- [ ] **GC-40 — Humor replay/persistence.** Humor-related experience, disposition-relevant history, social consequences переживают save/load и воспроизводятся под replay.

### 9.4. Avatar gameplay closure (AV-GC)

- [ ] **AV-GC-01** Values differential: same command, same world, different avatar values/norms → different accept/modify/refuse outcome.
- [ ] **AV-GC-02** Class/culture priors: different initialized priors могут давать different appraisal, но repeated experience меняет outcome без переписывания class identity.
- [ ] **AV-GC-03** Social preference differential: same flirt/social intent, different preference/comfort state → different response без hardcoded action table.
- [ ] **AV-GC-04** Pressure vs value differential: identical action — сопротивление из fear/pressure у одной истории и из moral/identity у другой; Chronicle различает причины.
- [ ] **AV-GC-05** Unified resolver: WillpowerGate, CharacterFilter и affect/trauma дают одно canonical action resolution, не конкурирующие execution paths.
- [ ] **AV-GC-06** Negotiation: refusal порождает executable counter-offer; игрок принимает через production path.
- [ ] **AV-GC-07** Player trust differential: same command после respectful vs coercive history → different acceptance/appraisal там, где модель предсказывает.
- [ ] **AV-GC-08** Resistance lifecycle: конфликт имеет trigger, escalation, resolution, aftermath; no one-input reset.
- [ ] **AV-GC-09** Recovery: stress/strain восстанавливается через causal factors; BROKEN/CONDITIONED — long-term gameplay, не game over.
- [ ] **AV-GC-10** Inner voice reachability: реальный конфликт достигает private avatar narration через API/frontend; DTO-only hooks проваливают тест.
- [ ] **AV-GC-11** Avatar epistemic asymmetry: игрок и аватар могут владеть разной информацией/beliefs; аватар действует по своему belief.
- [ ] **AV-GC-12** Avatar social consequence: avatar-modified/refused action меняет NPC relationship и позже — доступные avatar/NPC social outcomes.
- [ ] **AV-GC-13** Avatar humor/coping: identical pressure → coping humor / panic / avoidance / defiance в зависимости от avatar history/state.
- [ ] **AV-GC-14** Save/load/replay: psyche, trust, memories, scars, conditioning, релевантные будущим решениям, переживают persistence и replay.
- [ ] **AV-GC-15** Limited autonomy: только определённые extreme/idle states порождают autonomous avatar actions; normal input остаётся player-originated.
- [ ] **AV-GC-16** No second stack: аватар использует canonical stores/writers; дублирующих memory/relationship/epistemic/world writer нет.

### 9.5. Differential tests — важнейшие тесты против «пустой симуляции»

- [x] **DIFF-01 — History differential.** `World_0 + History_A` vs `World_0 + History_B` → одинаковая геометрия/текущий world state, но различный NPC behavior. Если поведение всегда одинаково — memory/epistemics не участвуют причинно. ✅ S243: causal_state_test (GC-00-харнес; один snapshot+seed; единственная переменная — авторизованная дельта): C-группа — argmax Люси flips → flee без события/текста; B-группа — контроль (дельт нет). LIMITATION: доказано на уровне решения (argmax), не материализации движения.
- [ ] **DIFF-02 — Observation differential.** `Event_X` происходит одинаково, но `NPC_A` наблюдает, `NPC_B` нет. Их belief state и последующее решение не становятся одинаковыми только потому, что событие существовало в мире.
- [ ] **DIFF-03 — Body differential.** Одинаковая социальная ситуация при разном sleep/energy pressure допускает различное решение, если affordance/decision scoring реально учитывает body constraint.
- [ ] **DIFF-04 — Relationship differential.** Одинаковый объект/задача при разной history отношений даёт различное социальное решение, если relationship state причинно подключён.
- [ ] **DIFF-05 — Testimony differential.** Одинаковое событие, разные источники свидетельства (high/low trust, direct testimony vs hearsay) → разные confidence/belief outcomes там, где контракт предусматривает.
- [ ] **DIFF-06 — Humor differential.** Same event + same world, different expectation/relationship history → different humor appraisal.
- [ ] **DIFF-07 — Pressure differential.** Same NPC + humorous opportunity при low vs high acute/chronic pressure → different propensity/form of coping humor, где appraisal/motivation model предсказывает.
- [ ] **DIFF-08 — Resolution differential.** Same incongruity с/без доступного logical/semantic resolution → amusement vs confusion/uncertainty.
- [ ] **DIFF-09 — Avatar values differential.** Same player intent and world, different values/preferences → different avatar appraisal.
- [ ] **DIFF-10 — Avatar history differential.** Same avatar profile and current command, different prior treatment by player → different player-trust/acceptance outcome, где causally justified.
- [ ] **DIFF-11 — Player knowledge differential.** Same world truth, но игрок знает факт, которого нет у аватара → аватар не действует магически по player-only knowledge.
- [ ] **DIFF-12 — Avatar memory differential.** Same current world and profile, different prior trauma/experience → different resistance.
- [ ] **DIFF-13 — Negotiation differential.** Same refusal pressure, different available affordances → different counter-offer.

### 9.6. Reachability audit

Для каждой значимой feature: `mechanism exists → production caller → player trigger → state write → next-tick effect → future behavior → player-visible consequence`.

- [ ] **REACH-01** Все feature-механизмы из MASTER TODO имеют production caller.
- [ ] **REACH-02** Для каждого caller существует игровой trigger или явно documented non-gameplay utility path.
- [ ] **REACH-03** Нет «мёртвых контуров»: зарегистрированные engine/checker/subscriber вызываются, но никогда не получают реальные данные (см. ST-1).
- [ ] **REACH-04** Каждый runtime writer имеет canonical owner и test на competing writer.
- [ ] **REACH-05** Каждый player-facing discovery path имеет источник ObservationLog.
- [ ] **REACH-06** Каждая заявленная MVP-фича имеет минимум один L3 vertical test.
- [ ] **REACH-07** Avatar ADR contour: production caller, player trigger, canonical state write, next-tick effect, player-visible consequence.
- [ ] **REACH-08** Avatar counter-offer — executable intent, не только narration.
- [ ] **REACH-09** Private avatar narration достигает реального communication/API path.
- [ ] **REACH-10** CharacterProfile values и psyche реально потребляются тем же production resolver, что решает avatar actions.

### 9.7. Negative-path tests

- [ ] **NEG-01** Missing/None dependency не даёт `union-attr`/`NoneType` падения тика; ветка корректно disabled или fail-loud.
- [ ] **NEG-02** Invalid/stale intent не выполняется и не телепортирует NPC.
- [ ] **NEG-03** Duplicate event.id не применяет одну причинную дельту дважды.
- [ ] **NEG-04** Unauthorized writer получает ArchitecturalViolationError.
- [ ] **NEG-05** Broken persistence payload не превращается в тихий `{}` и не стирает состояние.
- [ ] **NEG-06** LLM timeout/cancellation не блокирует WorldTick.
- [ ] **NEG-07** Unknown observation не превращается в false certainty.
- [ ] **NEG-08** Dead/invalid actor не продолжает автономное действие.
- [ ] **NEG-09** Renderer/presentation mutation обнаруживается тестом архитектурного нарушения.
- [ ] **NEG-10** `random.*`, wall-clock и необработанный `rng or random` в kernel/gameplay-critical path обнаруживаются lint + runtime probe.
- [ ] **NEG-11** Incongruity без разрешения не превращается автоматически в humor.
- [ ] **NEG-12** Высокий `humor disposition`/playfulness не заставляет шутить при угрозе или каждом тике.
- [ ] **NEG-13** Высокий trust не гарантирует humor, низкий не запрещает универсально; appraisal must decide.
- [ ] **NEG-14** Chronic pressure не создаёт бесконечный `humor_mode` и не мутирует personality напрямую без evidence/causal path.
- [ ] **NEG-15** LLM не может сам записать `HumorAppraisal`, relationship delta или hidden humor state в обход canonical writers.
- [ ] **NEG-16** Avatar psyche missing/malformed payload не молча fallback на gameplay-critical константы.
- [ ] **NEG-17** Mixed `0..1`/`0..100` avatar scales отвергаются contract-тестами; BROKEN/mental-strain thresholds достижимы только в intended ranges.
- [ ] **NEG-18** Player command не может напрямую писать avatar psyche/relationship/belief мимо canonical writers.
- [ ] **NEG-19** `REFUSE` без применимого reason отвергается avatar resolution contract.
- [ ] **NEG-20** `player_trust` alone не переопределяет values, physical constraints, trauma, epistemic uncertainty.
- [ ] **NEG-21** Resistance Medium не мутирует canonical avatar state.
- [ ] **NEG-22** `BROKEN` не может молча terminate кампанию или удалить avatar state.
- [ ] **NEG-23** Inner voice не создаёт нового скрытого психологического состояния, отсутствующего в canonical runtime.
- [ ] **NEG-24** Player-only knowledge не инжектируется в avatar belief без observation/testimony path.
- [ ] **NEG-25** Avatar-specific duplicate stores/writers (memory, relationships, epistemics, world state) — architectural violations.

### 9.7b. Avatar differential matrix

- [ ] `same command × different values` · [ ] `same command × different player history` · [ ] `same world × different avatar knowledge` · [ ] `same trauma × different current pressure` · [ ] `same refusal × different available affordances` · [ ] `same pressure × different humor/coping history`

### 9.8. Масштаб и длительность (SCALE)

- [ ] **SCALE-01** Smoke: 6 NPC × 30 ticks.
- [ ] **SCALE-02** Stability: 6 NPC × 200 ticks.
- [ ] **SCALE-03** Long horizon: 6 NPC × 1000 ticks.
- [ ] **SCALE-04** Persistence: save/load минимум в 3 точках одной истории.
- [ ] **SCALE-05** Replay: минимум 3 одинаковых прогона одного seed.
- [ ] **SCALE-06** Async differential: минимум 3 варианта timing/interleaving.
- [ ] **SCALE-07** Campaign stress: 20–50 NPC — только после single-tavern closure; масштабирование не маскирует отсутствие L3 correctness.

### 9.8b. Chronicaler как oracle, а не источник истины

Chronicle — производная observability-слойка. Для каждого GC-теста сохранять machine-readable trace:

`event → observation → experience → memory → conclusion → expectation/belief → appraisal/relationship/body pressure → affordance → decision → commitment → execution → verification → world change`.

Тест не проверяет «красивую фразу» — он проверяет наличие причинных звеньев и соответствие canonical state. Human-readable Chronicle — L4-представление той же цепочки.

### 9.9. Правило закрытия feature

Feature считается **CLOSED** только если:

1. L1 mechanism test зелёный;
2. L2 production integration test зелёный;
3. соответствующий L3 GC-тест зелёный;
4. negative-path тесты закрыты;
5. persistence/replay проверены, если feature stateful;
6. reachability подтверждена, если feature player-facing;
7. Chronicle/Inspector может объяснить причинную цепочку, если она должна быть наблюдаема;
8. нет известного AUD debt, непосредственно ломающего этот путь.

**IPT 49/49 без этих условий не является достаточным доказательством gameplay closure.**

**Правило закрытия стадии (ратифицировано Мастером 2026-09-05):** стадия с назначенным gameplay acceptance обязательством не считается CLOSED на основании одних L0/L1/L2-доказательств. Требуется доказательство назначенного игрового следствия **по природе механизма**: player-causal → player-triggered vertical (L3); system-causal → production gameplay scenario с системным триггером; dormant-substrate → acceptance у consumer-фронта (искусственный player-триггер до consumer'а не требуется); periodic/long-horizon → сценарий класса GC-16/SCALE, не на каждый фронт. Назначение клетки — на PRE-FLIGHT фронта, отдельным вердиктом, с записью в реестр ниже. По умолчанию ≤1 primary-клетки на фронт; две — только с явным обоснованием двух независимых игровых причинностей (прецедент: BC = GC-03 + GC-04). Форма доказательства (L0–L4) и природа обязательства — независимые оси.

**Реестр привязок стадия→клетка (минимальный позвоночник; расширяется только PRE-FLIGHT-вердиктом, по одному фронту):**

| GC | Домен | Причинная истина | Обязателен для фронта |
|---|---|---|---|
| **GC-11** | Relationships | event → social state → различие в следующем выборе | RE (следующий фронт) |
| **GC-08** | World/G3 | object → affordance → action → persistent consequence | W-track G3 |
| **GC-09** | Body | pressure → constraint → decision restriction → recovery | Body delivery |
| **GC-03** | Memory/epistemics | разный опыт → разный выбор идентичных агентов | BC epistemic causality |
| **GC-16** | Long horizon | 100+ тиков, causal history жива, seed-детерминизм | периодический gate зрелости (не на каждую стадию) |

**Миграция (правило поглощения):** закрытия до 2026-09-05 сохраняют исторический статус; отсутствующее игровое доказательство поглощается фронтальными гейтами: RE M0–M1b.3.4 → GC-11 @ M2/D; W1–G2 → GC-08 @ G3; B0/E2.0-c/BC-1 → GC-04 full-cell @ BC-3. Очередь переоткрытия прошлого не создаётся.

**Обоснование старта:** RE-D2 доказал, что зелёная архитектура может производить нулевую игровую реальность; DEBT-SLEEP-DELIVERY доказал то же для тела. GC-02 (player→world) — отдельная пользовательская вертикаль, не сливается с GC-08.

### 9.10. Матрица уверенности (GC → статус)

**Правило:** «исправлено» = код изменён; «закрыто» = acceptance test зелёный; «уверены» = пройден весь требуемый уровень доказательства и нет известного blocker debt.

| ID | Область | Mechanism | Production path | L3 | Negative | Persistence | Исправлено | Закрыто | Уверены | Доказательство |
|---|---|---|---|---|---|---|---|---|---|---|
| GC-00 | Runtime | живой world tick | TickOrchestrator → NPC | GC-00 | NEG-06 | SCALE-05 | да | ✅ bd4 3/3 | [ ] | reports/gc00_baseline4.txt |
| GC-01 | Tick | полный цикл NPC | production tick | GC-01 | NEG-02 | SCALE-05 | да | [ ] | [ ] | |
| GC-02 | World | player action → consequence | action → compiler → projection | GC-02 | NEG-03 | GC-20/21 | да | [ ] | [ ] | |
| GC-03 | Perception/Memory | observation → memory | perception → E1 | GC-03 | NEG-07 | GC-20/21 | indirect | [ ] | [ ] | |
| GC-05 | Epistemics | testimony → belief | speech → ClaimEvent → belief | GC-05 | NEG-07 | GC-20/21 | indirect | [ ] | [ ] | |
| GC-06 | Memory | history differential | memory → cognition | GC-06 | NEG-07 | GC-21 | да | ✅ S243 (с оговоркой) | [x] | causal_state_test: C → другой argmax; D = negative; limitation decision-level, BC-12 |
| GC-07 | Perception | observation differential | perception filter | GC-07 | NEG-07 | GC-21 | да | [ ] | [ ] | |
| GC-08 | World/Action | object → affordance → action | W2/W3 → Decision → execution | GC-08 | NEG-02/04 | GC-20/21 | да | [ ] | [ ] | |
| GC-09 | Body | pressure → constraint → recovery | Body/Needs → Decision | GC-09 | NEG-08 | GC-20/21 | да | 🟡 A ✅ `7f369e54`; B RED→V1 ✅ (ADR-O-383) | [ ] | recovery-ветка открыта |
| GC-10 | Sleep | reachable sleep delivery | intent → traversal → settled | GC-10 | NEG-02 | GC-20/21 | да | [ ] | [ ] | |
| GC-11 | Relationships | event → state → social action | RE Gate → snapshot → Decision | GC-11 | NEG-04 | GC-20/21 | да | [ ] | [ ] | |
| GC-12 | Learning | repetition/generalization | experience → conclusion | GC-12 | NEG-03 | GC-20/21 | indirect | [ ] | [ ] | |
| GC-13 | Belief revision | contradiction → revision | observation → surprise → belief | GC-13 | NEG-07 | GC-20/21 | да | [ ] | [ ] | |
| GC-14 | Self model | result → learning | action → outcome → self | GC-14 | NEG-03 | GC-20/21 | да | [ ] | [ ] | |
| GC-15 | Social | triangle/reputation | social graph/subscribers | GC-15 | NEG-04 | GC-20/21 | да | [ ] | [ ] | |
| GC-16 | Long horizon | persistent causal story | real ticks | GC-16 | all relevant | GC-20/21 | да | [ ] | [ ] | |
| GC-17 | Integrity | competing writers | StateApplicator/Gate | GC-17 | NEG-04 | GC-21 | indirect | [ ] | [ ] | |
| GC-18 | Time | wall-clock independence | kernel/runtime | GC-18 | NEG-10 | GC-21 | indirect | [ ] | [ ] | |
| GC-19 | Async | interleaving determinism | TaskScheduler/execution | GC-19 | NEG-06 | GC-21 | indirect | [ ] | [ ] | |
| GC-20 | Persistence | save/load continuation | snapshot + projection | GC-20 | NEG-05 | required | да | [ ] | [ ] | |
| GC-21 | Replay | exact causal replay | seed + input/event stream | GC-21 | NEG-10 | required | indirect | [ ] | [ ] | |
| GC-22 | Player cognition | ambient discovery | perception → ObservationLog | GC-22 | NEG-07 | GC-20/21 | да | [ ] | [ ] | |
| GC-23 | MVP | dilemmas reachable | init_campaign → registry → trigger | GC-23 | NEG-01 | GC-20 | да | [ ] | [ ] | |
| GC-24 | LLM | failure isolation/cancel | TaskScheduler → provider | GC-24 | NEG-06 | GC-21 | indirect | [ ] | [ ] | |
| GC-25 | Observability | causal Chronicle | trace → projector | GC-25 | NEG-09 | GC-20/21 | да | [ ] | [ ] | |
| GC-26 | Debugging | NPC Inspector | runtime trace/state | GC-26 | NEG-09 | GC-20/21 | да | [ ] | [ ] | |
| GC-27 | Frontend | consequence reaches renderer | API → PresentationProjector → renderer | GC-27 | NEG-09 | GC-20/21 | да | [ ] | [ ] | |
| GC-28 | MVP | full living tavern | all production layers | GC-28 | all | required | да | [ ] | [ ] | |
| GC-29 | Humor | expectation → incongruity → resolution → appraisal | perception → predictive/appraisal | GC-29 | NEG-11 | GC-40 | да | [ ] | [ ] | |
| GC-30 | Humor | individual appraisal | perception + personality/state/relationship | GC-30 | NEG-13 | GC-40 | да | [ ] | [ ] | |
| GC-31 | Humor | temporal disposition | memory/appraisal/history | GC-31 | NEG-14 | GC-40 | да | [ ] | [ ] | |
| GC-32 | Humor | benign violation | appraisal + relationship | GC-32 | NEG-13 | GC-40 | да | [ ] | [ ] | |
| GC-33 | Humor/Coping | acute pressure → humor response | appraisal → motivation → action | GC-33 | NEG-12 | GC-40 | да | [ ] | [ ] | |
| GC-34 | Humor/Coping | chronic pressure → adapted response | pressure → memory/self-model → decision | GC-34 | NEG-14 | GC-40 | да | [ ] | [ ] | |
| GC-35 | Humor | failed attempt → consequences | speech → reaction → memory/relationship | GC-35 | NEG-11/13 | GC-40 | да | [ ] | [ ] | |
| GC-36 | Humor/Social | audience model | perception → relationship → decision | GC-36 | NEG-12 | GC-40 | да | [ ] | [ ] | |
| GC-37 | Humor/Epistemic | social transmission | testimony → belief/experience | GC-37 | NEG-07 | GC-40 | да | [ ] | [ ] | |
| GC-38 | Runtime | no scheduled jokes | decision/action scheduler | GC-38 | NEG-12 | GC-40 | indirect | [ ] | [ ] | |
| GC-39 | Observability | causal explanation | trace → Chronicle/Inspector | GC-39 | NEG-15 | GC-40 | да | [ ] | [ ] | |
| GC-40 | Replay | humor persistence/replay | snapshot + memory + relationship | GC-40 | NEG-14/15 | required | indirect | [ ] | [ ] | |

**Матрица reachability для известных AUD-долгов:**

| AUD | Что ломается в игре | Gameplay test |
|---|---|---|
| AUD-D1 | latent type/interface crashes могут оборвать реальный путь | GC-00/01/24 + NEG-01 |
| AUD-D2 | социальная реакция падает в production None-ветке | GC-11 + NEG-01 |
| AUD-D4 | competing writers перетирают canonical NPC state | GC-17 + NEG-04 |
| AUD-D5 | отношения зависят от wall-clock / тихо обнуляются | GC-18/20/21 + NEG-05 |
| AUD-D6 | feature существует, но игрок никогда не может вызвать | GC-23 + REACH-03 |
| AUD-D7 | startup observability debt; kernel напрямую не ломает | startup smoke + NEG-09 |
| AUD-D8 | CI даёт ложную уверенность в strict typing gate | CI config test + AUD audit |
| AUD-D9 | память диалога теряет intent/tone metadata | GC-03/25 |
| AUD-D10 | игрок слышит/видит улику, но расследование её не получает | **GC-22** |
| AUD-D11 | скрытые TODO = unreachable/legacy path | REACH-01…06 + targeted audit |
| AUD-D12 | replay расходится из-за RNG default path | GC-18/21 + NEG-10 |

**Итоговый статус ENIGMA (уровни уверенности):**

| Уровень | Условие | Статус |
|---|---|---|
| **MECHANISM GREEN** | L0/L1: contracts + unit/SUPERBOX | [ ] |
| **RUNTIME GREEN** | L2: production integration | [ ] |
| **GAMEPLAY GREEN** | L3: GC vertical scenarios | [ ] |
| **OBSERVABILITY GREEN** | L4: Chronicle/Inspector/player-visible proof | [ ] |
| **REPLAY GREEN** | deterministic replay + persistence | [ ] |
| **REACHABILITY GREEN** | player can actually trigger claimed features | [ ] |
| **ENIGMA GAMEPLAY CLOSED** | все обязательные строки зелёные; нет blocker AUD debt | [ ] |

### 9.11. Минимальный порядок закрытия тестового слоя

1. **Сначала:** GC-00, GC-01, GC-17, GC-18, GC-19, NEG-01…06 — доказать, что runtime не врёт и не разваливается.
2. **Затем:** GC-02, GC-03, GC-08, GC-09, GC-10, GC-11 — доказать физический и социальный причинный цикл.
3. **Затем:** GC-04…GC-07, GC-12…GC-15 — доказать memory/belief/learning/social cognition.
4. **Затем:** HU1–HU5 + GC-29…34 — восприятие юмора и coping; затем temporal/social plasticity.
5. **Затем:** HU6–HU13 + GC-35…40 — production, failed humor, transmission, observability, replay.
6. **Затем:** GC-20/21 — общий persistence/replay gate.
7. **Затем:** GC-22/23/24 — конкретные известные reachability/failure gaps AUD-D3/D6/D10.
8. **Затем:** GC-25…GC-28 — observability, frontend visibility, full tavern acceptance.
9. **После этого:** масштабирование SCALE-03/07 и дальнейшие эпохи.

**Главный Stop-rule:** если GC-тест не может быть написан без прямого вызова внутреннего writer/engine — это не повод ослабить тест. Это сигнал, что production reachability ещё не замкнута.

### 9.12. Файлы gameplay-слоя

Не плодить сотни unit-тестов ради числа. Existing SUPERBOX/IPT сохраняются как L0/L1. Новый слой — маленький, но вертикальный:

- `backend/tests/gameplay/test_tavern_vertical.py` (существует; GC-00 детекторы)
- `backend/tests/gameplay/test_causal_differentials.py`
- `backend/tests/gameplay/test_negative_paths.py`
- `backend/tests/gameplay/test_replay_persistence.py`
- `backend/tests/gameplay/test_reachability.py`
- `backend/tests/gameplay/test_chronicle_observability.py`
- `backend/tests/gameplay/test_humor_vertical.py`
- `backend/tests/gameplay/test_humor_differentials.py`
- `backend/tests/gameplay/test_humor_coping.py`

Один vertical test может закрывать несколько внутренних механизмов — это предпочтительнее десятков тестов, напрямую вызывающих их writers.

---

## 10. ЖУРНАЛ ТЕСТОВ И ЗАКРЫТИЙ

> Решение Мастера (итерация «Пункт 5», 2026-09-04): файл `backend/tests/TEst_Result.md` удалён; **единственное место фиксации выполнимости — этот журнал**. Протокол: (1) каждое закрытие пункта/долга = обновление галочки/статуса в соответствующем разделе (§2, §5, §7, §8, §9); (2) каждый значимый прогон/гейт = строка в таблице ниже. Красный тест = диагноз (незамкнутый контур + причина + подозреваемый узел), а не повод прятать результат: при FAIL колонка «Диагноз» обязательна. Закрытие стадии с назначенным acceptance-обязательством обязано цитировать результат назначенного гейта (клетка + зелёный прогон/коммит) в строке журнала. Протокол окон тишины (§3.12 РЕЖИМА РАБОТЫ): долгие прогоны — валидация PROCESS EXIT + канонические маркеры + полный артефакт; `exit=-1` = INVALID RUN, не GREEN и не RED.

| Дата | Шаг | Объект | Результат | Диагноз / причина |
|------|-----|--------|-----------|-------------------|
| 2026-09-04 | Базлайн итерации «Пункт 5» | IPT (45 инвариантов) | ✅ 45/45, 0 CRITICAL | — |
| 2026-09-04 | Базлайн итерации «Пункт 5» | pytest tests/ (полный) | 📌 по коммиту d92e8d1c: 1614 passed / 15 pre-existing failed / 32 skipped | sandbox/scenario, decision_hub goal_boost; свежий полный прогон — в составе GC-00 (harness) |
| 2026-09-04 | Шаг 1 (миграция) | TEst_Result.md → журнал | ✅ удалён, протокол перенесён | из журнала спасён незарегистрированный хвост PROBE 9.7 |
| 2026-09-04 | Шаг 2 (детектор) | test_npc_state_r6.py (5 тестов) | ✅ 5/5 passed | противоречивые прогоны старого журнала = история миграции шкалы identity_integrity 0..100→0..1; билд самосогласован (SSOT npc_state.py:667/810/1149); pytest.ini подхвачен pytest 8.3.3 — долг S213 закрыт фактом |
| 2026-09-04 | Шаг 3 (PROBE 9.7, P1) | run_turn materialization parity — патч game_loop/__init__.py:1481 (ADR-O-313, зеркало idle-прецедента :1245) | ✅ патч применён: compile ✅, ruff 20 (pre-existing, +0), IPT 45/45, 0 CRITICAL | ROOT_CAUSE: REST-путь никогда не разбирал pending_tasks (execute_pending только из idle_tick:1245) → NPC_SPOKE не публиковался → «0 строк npc_spoke»/память речи мертва в player-сессиях (FAIL_STAGE: MATERIALIZE). FIX_SCOPE 1: execute_pending + drain_commitment_outbox между commit (:1479) и unlock (:1510); fast-path реплики попадают в recent_dialogues этого же хода; LLM-задачи на пуле ADR-O-343 (REST не блокируется). Хвосты: AI-D1, ST-1 |
| 2026-09-04 | Шаг 3.5 (вердикты) | pytest -rs + тело stream_turn + семантика лока + frontend transport | ✅ вердикты получены | AI-D1: явный skip «Flaky… Needs refactor» (:52) — гейт мёртв, преемники headless вне pytest-коллекции; ST-1: разрыв подтверждён (нет commit/unlock/execute в WS-методе), но SSE недостижим в Direct-контракте (api_client.py:585–587), лок мягкий → P1→P2, кандидат REACH-03. Гигиена: коммит 28676bcb (git add -A) втянул 30 файлов/43k строк не из этой итерации; впредь точечный git add |
| 2026-09-04 | S239 (W-трек, ADR-O-378) | GORAN β G2: 7×200 тиков, процесс-изоляция + settings.saves_dir | ✅ GREEN: honest-zero (диффы ≤ OFF/OFF-фона), B-молчание, W hits=199/199 + weapon_persisted; engine-флип 0.50→0.70 юнит-доказан; W-контур 124+1skip, IPT 45/45 | 4 честных отказа пойманы гвардами (bootstrap-квант / H1 потеря инъекции / H5 общий-store / stale-парсинг), ноль ложных GREEN; terminal-дрейф 65→42 = артефакт общего store, не регрессия ядра; B1 trav=120 — одиночный ambient-выброс (DEBT-QUIESCE, ось не гейт) |
| 2026-09-04 | S239 (док-санация) | drift O-373→O-376 (неполный propagate S237) | ✅ 24 сайта закрыты | Урок: propagate-sweep обязан покрывать ВСЕ файлы Files-списка ADR, не только доки |
| 2026-09-04 | Шаг 4 (GC-00 baseline №1) | pytest tests/gameplay/test_tavern_vertical.py (3 детектора, -s) | ❌ 0/3 (единый корень) | ArchitecturalViolationError «Direct write to NPCState.drives from tests.gameplay.harness» — ADR-WRITE-GUARD (S212) поймал нарушение САМОГО harness'а: позитив, enforcement жив. Корень: _init_avatar_body пишет поля пост-конструкцией (скопирован из прецедента test_player_turn_headless, мёртв под guard → хвост PH-1). Попутно: WARNING location_templates.json не найден (pre-existing) |
| 2026-09-04 | Шаг 4 (GC-00 baseline №2) | pytest -s (полный) | 🟡 1/3: determinism ✅ (вакуум-оговорка), liveness ❌, P97 ❌ (TypeError вложенного asyncio.run — баг ТЕСТА); 301.71s | Корни тест-слоя: nested asyncio.run в P97; _scene_after_tick ждал dict — idle_tick возвращает объект → time=0 + подозрение вакуумного PASS; изоляция saves не сработала — [AVATAR] XRayProbe != Tester: прочитан прод-saves → аватар контаминирован (Psyche {}, hp=0.0). LIVE-подтверждения: AUD-D2, AG1-D5, DEBT-R10, RE-D2, НОВЫЙ SC-1 (namespace run_turn ≠ граф), SOMATIC_VETO body_state missing. DM_AGENT_CRASH при LLM-off — изоляция отказа выстояла |
| 2026-09-04 | Шаг 4 (GC-00 baseline №3) | pytest -s → reports/gc00_baseline3.txt | 🟡 2/3: liveness ✅, P97 ✅, determinism ❌; 310.36s | RETRACTION: атрибуция DEBT-QUIESCE снята — расхождение на тике 0 с offset РОВНО = 30 тикам run1 → контаминация состояния между прогонами, не async-недетерминизм; spoke/moved идентичны. Векторы: config.py:49 жёсткий дефолт saves; sessions world_tick.json переносит sim_tick (experiment_runner:113–115); глобальные синглтоны (LifeEngine) без сброса. Фикс: H-6/H-7 → baseline №4 |
| 2026-09-04 | Шаг 4 (GC-00 baseline №4 — ФИНАЛ) | pytest -s → reports/gc00_baseline4.txt; IPT 45/45 | ✅ 3/3 PASSED, 93.44s | CLEAN-START верифицирован: saves_dir=Temp\gc00_*; seed_determinism: 2×30 тиков идентичны (last_time 43500, spoke 8, moved 23; 30/30 отпечатков) — детерминизм ПОДТВЕРЖДЁН, ретракция закрыта (перенос был контаминацией); host-изоляция байтово доказана (sim_tick 6610/19:56 восстановлен дословно); P97 ✅ (PROBE 9.7 в REST-пути). Время 310s→93.44s (×3.3). H-8: bus.clear + sessions snapshot/restore + SpatialRegistry invalidate + reset_life_engine в dispose |
| 2026-09-04 | Шаг 5 (AUD-D2, production-fix) | game_loop/__init__.py (провода стора :264+) + social_subscriber.py (skip-путь None-ветки) | ✅ ЗАКРЫТ: P97 1 passed 90.72s; ruff clean; IPT 45/45 | ROOT_CAUSE (двойной): (а) S198-читатель idle:1162 ждал self._rel_store — атрибута НЕ существовало (обе точки локальные) → shared_context.relationship_store ВСЕГДА None; (б) индент-баг: for _ev в events вне else → None.apply ERROR каждый ход. FIX: self._rel_store = _rel_store (:264) + полный skip-путь (warning → rumors → return Phase8Result). ДОКАЗАНО P97. НЕ доказано: персистентность trust-дельт чтением стора — верификация в GC-11 |
| 2026-09-04 | Шаг 6 (AG1-D5, Этап А — зонд) | test_gc00_ag1_d5_avatar_body_initialization → reports/gc00_ag1_d5_probe.txt | 🔴 RED (ожидаемый, 1.31s) — вердикт ПОДТВЕРЖДЁН | ROOT: avatar default body_state={'money': 48} — аватар чистого мира получает эконом-словарь вместо тела; NPC-паритет сломан. Эффект: effective_hp=0.0 + life_status ABSENT → Death Guard видит 'ALIVE' (:2154). Death Guard и VitalState НЕПРАВИЛЬНЫ (hp≤0≠смерть, ADR-123) — дефект в инициализации, не в guard. DOUBLE TRUTH опровергнут: dict-сторона player/Tester NOT IN SNAPSHOT. SECONDARY: аватар отсутствует в all_npcs_raw idle-прогонов → хвост AVID-1. Зонд коммитится как красный детектор; Stage B — на решение Мастера |
| 2026-09-04 | Шаг 6 (AG1-D5, Stage B — фикс) | player_avatar_service.py: default body_state = {**BODY_STATE_HEALTHY, money:48} + импорт | ✅ ЗАКРЫТ: зонд GREEN 1.09s (current_hp=100, life_status=ALIVE, 17 ключей тела); полный GC-00 4/4 (89.10s); IPT 45/45; ruff clean | Красный→фикс→зелёный за одну итерацию. Аватар чистого мира получил телесный паритет NPC (включая sleep-оси S188 — закрывает часть фронта DEBT-SLEEP для аватара). Stage A→B: 5baea803 (RED-зонд) → текущий коммит (GREEN) |
| 2026-09-04 | Шаг 7 (AVID-1 — GAP закрыт) | game_loop/__init__.py (idle-проводка S113 all_npcs_raw) + harness.py (upsert_character восстановлен) | ✅ ЗАКРЫТ: S198_PIPELINE_ENTER count=7 с 'player' ×3 тика; срезы кэш/снапшот/runtime 7/7/7; GC-00-модуль 4/4 (93.87s); IPT 45/45 | Вердикт Стадии 3: GAP (BY-DESIGN опровергнут кодом ADR-030). Дифференциал: до фикса count=6 при живой инъекции (транзит) — idle не передавал список оркестратору; после — count=7. Второй компонент: harness-баг (sheet потерян при guard-фиксе bd1 → list_characters пуст → инъекция молча пропускалась). Production-эффект: аватар укоренён в idle-мире — CFL/восприятие/соцполе видят игрока между ходами (embodied player runtime) |
| 2026-09-04 | Кросс-ретроспектива (из S240) | Инцидент контаминации prod-saves (bd2/bd3) — адъюдикация Мастера | ✅ вердикт: DEBT-W-STORE-INCIDENT = ACCEPT | Эволюция ROOT/saves признана каноническим состоянием живого мира (known provenance debt, «стратиграфия нарушена до T≈2800», reset отклонён). Вклад: инцидент порождён baseline №2/№3 (env-изоляция мертва, config.py:49); закрыт H-6..H-8 — прогоны bd4+ чисты |
| 2026-09-04 | Шаг 8 (полевой тест; контракт: без ремонтов) | terminal_cockpit полный маршрут: new→наблюдение→wait 3→адресное→wait 12→mem→restart→mem; LLM жива (Q4) | ✅ сессия завершена; 4 фикса ПОДТВЕРЖДЕНЫ В ПОЛЕ: hp=100 (AG1-D5), S198 count=7 в ходах И idle (AVID-1), реплики материализуются (PROBE 9.7), social-коммиты (AUD-D2); player_xy_valid=True; ПЕРСИСТЕНТНОСТЬ: mem до/после restart ДОСЛОВНО идентичны; психика аватара материализовалась (identity_integrity 0.9978, life_project survival) | НОВЫЕ хвосты: FT-1 (P1) адресация «люся:»→TARGET Торнин; FT-2 (P1) FLEE-storm: threat вне npc_positions, Люся выпала из позиций idle; FT-3 (P2) пусто-текстовые speech-эпизоды imp=0.80. Живые подтверждения: AG1-D1, RE-D2, SOMATIC_VETO, Н-45/46, DEBT-R10. Транскрипт: reports/field_test_S241.txt |
| 2026-09-05 | Шаг 9 / S245 (FT-1 закрыт) | player_target_extractor.py (npc_id-ветка прямого матча) + test_ft1_target_resolution.py | ✅ ЗАКРЫТ: production-зонды 3/3 ×2 (213.51s/205.05s), GC-00 4/4 (95.08s), IPT 45/45 | ROOT_CAUSE (stash-дифференциал на идентичном входе): клиенты кладут резолвнутый адресат в текст латинским npc_id → name_forms-матч (кириллица) слеп → has_address_signal → sticky переносит прежнюю цель. Фикс: npc_id = форма прямого упоминания (адресация и есть «к» — предлоговая косвенность неприменима). Честная оговорка: оба отчёта ft1_probe_* — ПОСТпатчевые прогоны («ДО» не исполнялось); красное доказательство = stash-дифференциал. Патч каноничен независимо |
| 2026-09-05 | S247 (BC-1, реализация/приёмка — ADR-O-381 dormant; вердикт P=BC-1) | bc1_conclusion_test (новый SUPERBOX); IPT 45/45 (после L4-фикса INV-SILENT-FAILURE, было 44/45); ruff 6/6; causal_state_test обе серии: Люся полный parity, Горан seed-parity (PYTHONHASHSEED=0: дрожь 0.706↔0.707 = процессный hash-недетерминизм perceiving_ids, D11-класс, не регрессия) | ✅ 6/6 GREEN: A — (maid_lusya, player, is_dangerous, conf=0.8, evidence=[id]) прод-путём; B — NO-VACUUM тройной контроль (0/0/0); C — state-канал, conf=0.8, concordance; D — REJECTED; E — round-trip; OFF — dormant (store=None, scene_key=absent) | BC1_ENABLED default OFF. AG1-D8p отложен |
| 2026-09-05 | S248 (RE-D2 + FT-3 — двойное forensic из живой сессии) | router.py (fail-fast guard), working_memory_tick.py (гвард пустого хвоста), 2 детектора, evidence-лог (c1d39236) | ✅ ЗАКРЫТЫ: RE-D2 self-deadlock request_for_agent (60.03с глобальная заморозка при живой LLM 3.3–4.3с/вызов; интермиттентность = asyncness эндпоинта: game_action/game_turn async→петля→дедлок vs idle_tick def→threadpool→worker; зомби-round-trip; «тяжёлые промты» опровергнуты данными) + FT-3 producer write_npc_reactions_to_memory: пустой хвост «Имя:» в ОБА стока без фильтров; материализатор оправдан | Хвосты: DEBT-RE-D2A (P1-арх: intelligence queue = production-форма ADR-O-377), F-NS1, O1-аудит, M-08, B1/B3 design-q, avatar×2, imp=0.80-lead; BC-1 HOLD снят; _cache-эскалация RE-01; CONFIG-DEBT корроборирован (фактически Q5). IPT 44/45 (единственный red — чужой, атрибутирован) |
| 2026-09-05 | GC-09A Body Runtime (§9.9-реестр; вердикт Мастера: Body Simulation ≠ Embodied Agency; A/B-сплит) | test_gc09_body_causality (A) + harness.read_body | ✅ GREEN: 25 production-тиков, one-way-оси живого контура сместились у обоих субъектов (blacksmith hydration 98.8→92.8 / nutrition 99.7→98.3 при load=0 — клампы fatigue/energy; maid_lusya hydration 98.5→91.0 / nutrition 99.7→98.1 + fatigue 0.375→2.25, energy 99.5→97.0 при load≈0.5 — тело персонифицированно дифференцировано) — BodyEngine→StateApplicator production-провод жив, не unit-only | Коммит 7f369e54 |
| 2026-09-05 | GC-09B Embodied Constraint (RED-детектор; вердикт Мастера: «state exists ≠ state has consequence») | test_gc09_body_causality (B) — авторизованная дельта fatigue+90/energy−90 через production StateApplicator на from_legacy-копиях живого maid_lusya; гвард мутации зелёный | 🔴 RED = НАХОДКА (документированное доказательство, не провал): availability A≡B — 10 интентов идентичны при предельном износе; causal edge BODY→DECISION AVAILABILITY для осей выносливости отсутствует; единственный body-edge = Vital State Guard (compute:440). STATE→BEHAVIOR GAP — второй домен после отношений (архитектурная гипотеза State Consumer Gap, выборка 2). Звено 3 = ADR-фронт BodyConstraintResolver, НЕ патч _is_intent_available | Коммит a6708f46 (amended) |
| 2026-09-05 | ADR-O-383 V1 Embodied Constraint IMPLEMENT (закрытие GC-09B-RED) | pressure_translator (chronic-veto cap 0.3, константы CALIBRATION_CANDIDATE) + GC-09B-full oracle | ✅ GREEN: 2/2 (A жив; B-full: измотанное тело меняет итоговое решение через полный контур decision_ctx→feasibility; RED→ADR→V1→GREEN за сессию) | Инциденты-уроки: 2× red-commit (fa82f359, b9b6f90c — ruff F821 игнорирован; гейт≠барьер без exit-ветвления; в remote попал NameError-код, закрыт fix2). Границы V1 — в ADR (не расширяются): availability-тракт, motor_output_mult (D-MOM), sleep-семантика — отдельные вопросы | Коммиты 5b14af56+fa82f359+b9b6f90c+fix2 |
| 2026-09-05 | Базлайн сессии аудита роадмапа | IPT | ✅ 49/49 (0 CRITICAL) | «KILLER_SPIRIT: убито=0, пощажено=1» — стоп-протокол процессов работает; базлайн v4.0-перезаписи |
```

### 10.1. Унаследованные хвосты журнала (живые владельцы)

- [x] **PROBE 9.7** — ✅ ЗАКРЫТ (Шаг 3). Смотри §7.4.
- [ ] **AI-D1** (P2, тест-гигиена): test_game_loop_pipeline.py — единственный юнит-гейт _run_pipeline permanently SKIPPED: явный skip «Flaky… Needs refactor» (:52). Гейт мёртв: регресс конвейера REST юнит-слоем не ловится; тест построен на конструкторных моках GameLoop(**mock_deps) — §13.4 (объект мечты). Преемники — headless-скрипты вне pytest-коллекции: test_run_turn_e2e.py (требует LLM), test_player_turn_headless.py (LLM-free, InterventionEvent → TickResultDTO). Действие: рефактор гейта в headless-класс (pytest-коллекция, MockProvider только в test-env) или retirement с переносом ассертов (_PipelineState/PipelineContext) в headless-гейт. Владелец: итерация «Пункт 5» / преемник.
- [ ] **ST-1** (P2): ВЕРДИКТ: разрыв подтверждён — в stream_turn (:1560–1733) нет commit_tick_result/unlock_tick/execute_pending (коммиты :1035/:1202/:1479, анлоки :1046/:1290/:1510 — вне WS-метода) → при активации SSE: WS-тик не персистится, pending_tasks не материализуются, Death-Guard early-return без unlock. Смягчение: фронтенд Direct-контракт SSE не поддерживает (api_client.py:585–587 NotImplementedError) → путь недостижим в проде; лок мягкий (lock_for_tick :242–248 возвращает None). Действие: при активации SSE — патч-зеркало PROBE 9.7 (commit + execute_pending + drain + unlock) до финального done-yield; кандидат REACH-03.
- [ ] **PH-1** (P2, прецедент): test_player_turn_headless.py (эталон player-хода, база harness'а) мёртв под ADR-WRITE-GUARD: пост-конструкционные записи NPCState.drives/psyche/body_state из tests.* → ArchitecturalViolationError (guard S212; скрипт __main__-формат вне pytest — падение никем не замечено). Действие: миграция прецедента на конструкторные kwargs/фабрику; прогон отдельным гейтом после GC-00.
- [ ] **SC-1** (P2, spatial/namespace, NEW из GC-00 baseline №2): SHADOW_COMPILER «Node not found» в run_turn-пути: tavern:entrance (event_compiler:280), tavern:right_table (:155), tavern:fireplace (:280) — цели NPC не разрешаются в скомпилированном графе (namespace целей vs граф; см. расхождение tavern/tavern_silver_wolf из GC-00-археологии). Эффект: shadow-рельса пишет FAILED-записи позиций, dual-rail компаризатор теряет материал. Действие: археология источника node-id (MovementIntent) vs компиляции графа; вердикт о namespace-каноне. Связь: F-NS1.
- [x] **AVID-1** — ✅ ЗАКРЫТ (Шаг 7, вердикт GAP). Смотри §7.4.
- [x] **FT-1** — ✅ ЗАКРЫТ (S245). Смотри §7.4.
- [ ] **FT-2** (P1, FLEE+позиции): wait-тики: FLEE_NAV «threat=maid_lusya not found in npc_positions! Flee blocked» ×12 — NPC решает бежать от Люси каждый тик, исполнение заблокировано; сама Люся отсутствует в npc_positions idle-тиков (SPATIAL_DATA 6/7→5/6). Живая склейка RE-D4 + Н-53. Действие: локализовать беглеца и причину исчезновения Люси из позиций (post-mortem по scene_changes_*.jsonl); зонд.
- [x] **FT-3** — ✅ ЗАКРЫТ (S248). Смотри §7.4.

---

## 11. Гейты, Stop-criteria, Recovery, Ресурсы

### 11.1. Гейты и Stop-criteria

| Переход | Stop-criteria (все ✅) |
|---|---|
| Фаза 0 → 1 | Симуляция жива: decisions > 0 стабильно ×3 сессии · tracebacks ~0 · SHI=100% честно (перепроверено по scene_changes_*.jsonl) · IPT 49/49 |
| Фаза 1 → 2 | RE-01 M2/D зелёный · RelationshipWriteGate покрывает 100% writers · линтер в CI · Replay exact-match |
| Фаза 2 → 3 | §19 surprise измеряется · Prophecy green · Vertical Slice играбелен |
| Фаза 3 → 4 | WorldChronicle persistence green · 3 времени консистентны |
| Фаза 4 → 5 | 50+ NPC × 30+ мин стабильно |
| Фаза 5 → 6 | §18 активен после Belief Layer |
| **Gameplay Closure (стадийный слой) → дальнейшее расширение** | GC-00…28, required NEG/REACH, **+ назначенные acceptance-гейты стадий (реестр §9.9) зелёные для закрываемого фронта; форма доказательства — по природе механизма (§9.9)**; persistence/replay и MVP Tavern acceptance зелёные; нет blocker AUD debt |

### 11.2. Красные флаги — STOP

1. DNA врут (SHI=100% при неподвижных NPC) → проверять по jsonl-логам.
2. `PlayerBeliefModel` ≠ NPC ToM (нужен second-order BELIEVES).
3. `MockProvider` в production-пути.
4. Observability мутирует state.
5. §18 до Belief Layer.
6. Version desync (`version.txt` ↔ `pyproject.toml` ↔ frontend-константы).
7. `random.*`/`time.time()` в kernel-слое.
8. Writer потребностей/отношений в обход `RelationshipWriteGate`/`update_needs` — прямая мутация RelationshipStateStore запрещена (single-writer, caller-guard).
9. Фронтенд/симуляция читает состояние из renderer — Architectural Violation (W-TRACK контракт).
10. Введение состояния-сущности для «идеализация/влюблённость/адаптация» без anti-Bond теста (Р17-П1).
11. **Body как прямой автор действия** (§5, ADR-O-383): body → constraint/pressure → decision; прямой body→action edge запрещён.

### 11.3. Quick recovery — если зашёл в тупик

| Симптом | Что делать |
|---|---|
| 0 decisions/tick (симуляция заморожена) | `backend/app/services/npc/decision_hub.py` — веса решений, связь с RelationshipStore/WriteGate; `git log` на недавние писатели |
| LLM молчит | `backend/logs/cds_session_*.log`; `scripts/llm_server_manager.py`; LOG-GATE-UI на splash |
| `movement_traversal ⏸` | `local_traversal_planner.py` + `traversability_evaluator.py` + `geometry_kernel.py`; проверить arbiter INCUMBENT (commitment держит прежнюю цель) |
| IPT падает | какой инвариант красный в `IPT.py`; профильные линтеры `scripts/lint_*.py` |
| Регрессия, непонятно где | `git bisect`; marker — `pytest backend/tests/canary/test_full_playthrough.py` |
| Сломан контракт RE | `scripts/lint_relationship_engine.py` + `architecture/relationship_engine.yaml` |
| Сломан WORLD-контракт | `backend/tests/test_world_object_topology.py` + `architecture/world.yaml` |
| Version desync | `version.txt` + `pyproject.toml` + frontend-константы синхронизировать |

### 11.4. Ресурсы и ключевые файлы кода

| Подсистема | Файл (проверено) |
|---|---|
| Tick pipeline | `backend/app/services/tick_orchestrator.py` |
| DecisionHub | `backend/app/services/npc/decision_hub.py` |
| DM-agent | `backend/app/agents/dm_agent.py`; фаза DM — `backend/app/services/game_loop/dm_phase.py` |
| Dialogue | `backend/app/dialogue/dialogue_router.py`, `backend/app/services/verbalization/` |
| Relationship Engine v2 | `architecture/relationship_engine.yaml`; стор/gate — `git show 73e0539f` (RelationshipWriteGate), `53183000` (адаптер), `17930e9f` (RelationshipStateStore) |
| WORLD-домен | `architecture/world.yaml`, WorldObjectStore (ADR-O-371); executor G3 — `backend/app/services/world/g3_executor.py`, `object_target_facts.py` |
| Movement/Spatial | `backend/app/services/spatial/` — mypy --strict: 0 ошибок |
| Impact/Physiology | `backend/app/services/combat/impact_engine.py`, `backend/app/domain/vital_state.py` |
| Kernel RNG | `backend/app/core/kernel_rng.py` |
| Tests (IPT) | `backend/tests/IPT.py` (49/49, ruff clean) |
| Gameplay layer | `backend/tests/gameplay/` (harness + GC-детекторы) |
| Canary | `backend/tests/canary/test_full_playthrough.py` |
| Lint-гейты | `scripts/lint_*.py` |
| LLM-менеджер | `scripts/llm_server_manager.py` |
| Session data | `backend/data/logs/scene_changes_*.jsonl`, `reports/dna_history.jsonl` |
| Architecture YAML | `architecture/*.yaml` (23 файла) |

---

**Назначение документа выполнено: операционная карта преемника.** Текущая точка — §0.1; очередность — §0.2; методология доказательства — §9; журнал — §10. Архив: `MUTATIONS.md`. Документ завершён.
