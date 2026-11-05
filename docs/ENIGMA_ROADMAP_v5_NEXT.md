# ENIGMA — Роадмап «Что дальше» (v5.0-NEXT)

**Ветка:** `V.0.5.4.5.6_Полшага_3` · **Версия:** 0.5.4.5.6 · **Дата снятия статуса:** 2026-11-05
**Полный реестр (историко-артефактный):** `docs/ENIGMA_ROADMAP_v4_12_WPS.md` · **Прямая ссылка:** [ENIGMA_ROADMAP_v4_12_WPS.md на GitHub](https://github.com/4Um4/Enigma/blob/V.0.5.4.5.6_Полшага_3/docs/ENIGMA_ROADMAP_v4_12_WPS.md)

## Как читать этот документ

- ✅ — **закрыто и верифицировано** (сессии/гейты/ADR — в полном роадмапе v4.12). Здесь держим только сводку, без исторических деталей.
- ⬜ — **открыто.** Это и есть рабочий фокус: разделы 2–6 перечисляют всё незакрытое в каноническом порядке.
- Каждый открытый пункт несёт гейт (как закрыть). Формулировки сохранены из v4.12, сокращён только исторический шум.

---

## 1. Снимок прогресса (по трекам)

| Трек | Что это | Статус |
| --- | --- | --- |
| **CCH** — Character Chronicle | Слой 0: AUTHORING → COMPILER | ✅ **Закрыт** (CCH-0…CCH-7, S331→S385). Осталась параллельная линия CCH-02 (§3.6) |
| **RE-01** — Relationship Engine v2 | Отношения, потребности, гейт записи | ✅ **Ядро закрыто** (M0→M2/D, G/H, GC-11). Открыты хвосты: K, Полигон M, R18, RE-D7 (§2) |
| **AG1** — Understanding & Epistemics | Понимание, эпистемика, семантический вход | ✅ **Пакеты закрыты** (§3.2 v4.12). Открыт контур BC-2…BC-13 (§3.1) |
| **DLG** — Диалоговая вертикаль | «ИГРОК=НПС», симметрия спикеров | 🟨 DLG-0 ✅ (S386), DLG-1 ✅ (S388); **открыты DLG-2, DLG-3** (§3.2) |
| **W-TRACK** — World Embodiment | Мир объектов, affordances, G3-исполнитель | 🟨 Субстрат, W2, W3, G2, G3, аудит ✅; **открыты GC-08/Object-cognition/W4–W9** (§3.4) |
| **Body / Embodied** | Телесный контур, ограничение действий | 🟨 GC-09A/09B, ADR-O-383 V1 ✅; **открыты V1+, D-MOM, Sleep** (§3.5) |
| **LC** — Loop Closure | Канал «мир → игрок» / «время → знание» | 🟨 LC-IMPL-1 ✅ (S334), LC-IMPL-2 ✅ (S376); **открыты LC-IMPL-3…6** (§3.3) |
| **NL-01** — Narration | NPC как интерфейс к миру | ⬜ **Открыт весь** (NL-0…NL-12, §3.8) |
| **MOT** — Motive & Decision Trace | Решение как причинная запись | ⬜ **Открыт весь** (MOT-0…8, §3.7; MOT-9 — за гейтом AUDIT-10H) |
| **MEM** — Memory Architecture | Память как история жизни | ⬜ **Открыт весь** (MEM-0…10, §3.9) |
| **COV** — Полнота покрытия | Гарантирующий слой «ничего не упустили» | 🟨 COV-0/1/2 ✅ (S343/S360/S348); **открыты COV-3…11** (§3.10) |
| **EPI** — Жизненный цикл информации | Информация как физический процесс | ⬜ **Открыт** (EPI-0, EPI-CLIMATE, §3.11) |
| **GC-слой** — Gameplay Closure | Доказательства, диф-тесты | ✅ GC-00/01/02/11/27, GC-спринт Б3 закрыты (18/18 зелёных); остаток — по трекам (§4) |
| **Инфра** | LLM-модель, UX, линтеры, IPT | ✅ Миграция на YandexGPT-5-Lite-8B (S362), Shift+F9 (S361), COV-0 линтер-гейт; IPT 54/0 |

**Сводка по сквозной очереди §0.2 v4.12:** 75 пакетов, закрыто 21, открыто 54 (+ долг и будущие эпохи).

---

## 2. СЕЙЧАС — открытые фронты секции A (блокируют качество причинной игры)

- [ ] **A4** — RE-01 фаза **K**: полный removal-test + **Полигон M** (пресеты, INV-1, диф-тест раннего внимания О-2 — единственный хвост Р17).
- [ ] **A6** — **RE-D7**: каноническая схема campaign-bootstrap JSON (отдельный ADR).
- [ ] **A7** — **BC-2 → BC-3** (эпистемический контур, §3.1): вывод меняет прогноз; прогноз меняет DecisionHub. Full-cell GC-04.
- [ ] **A8** — **GC-08-инфраструктура**: capability `spawn_world_object` для harness (§9.2 v4.12) — prerequisite object-cognition W-трека.
- [ ] **A9** — **Body V1+ калибровка** (§5.1 v4.12) через Calibration Lab: chronic-veto cap и пороги (константы помечены CALIBRATION_CANDIDATE).
- [ ] **A11** — **Wildcard-writers NPCState** (AUD-D4): миграция 4 модулей, сужение `"*"`.
- 📌 **A10 (постоянное правило, не задача)** — после каждого шага сохранять IPT зелёным + профильные линтеры (ruff 0, compileall 0).

---

## 3. Очередь треков — открытые пакеты

### 3.1. Поведенческое замыкание BC-2…BC-13 (AG1 §3.5; после M2/D — готово к старту)

Цель: единый контур социализации на существующих Memory/Belief/Relationship/Decision механизмах — не новый набор эмоций и не флаги «месть/обида/влюблённость» как сущности.

- [ ] **BC-2** — Conclusion → Expectation: вывод меняет прогноз следующего взаимодействия. Мини-ADR на открытие моста CONCLUSION→EXPECTATION (ADR-O-381 F3а) + BC1_ENABLED ON + потребитель ExpectationStore; DeltaGate-тропа, provenance, causal parent.
- [ ] **BC-3** — Expectation → Decision: существующий DecisionHub использует ожидание без специальных action-флагов (full-cell GC-04).
- [ ] **BC-4** — Repeated evidence → Generalization: повторяемость усиливает устойчивый вывод; противоречивая — ослабляет/ревизует.
- [ ] **BC-5** — Personal experience → Social testimony: NPC передаёт не только факт, но и собственный вывод («я считаю его ненадёжным»).
- [ ] **BC-6** — Testimony → Recipient belief: получатель учитывает источник, уверенность, собственный опыт и конфликтующие свидетельства.
- [ ] **BC-7** — Conclusion → social strategy: derived-паттерны («избегать», «не давать ресурс», «предупреждать») без флагов конкретных NPC.
- [ ] **BC-8** — Learning: успешный опыт порождает знание/правило/навык, меняющее будущую возможность или предпочтение действия.
- [ ] **BC-9** — Surprise → belief revision: неожиданное поведение другого ломает/уточняет ожидание и отношение.
- [ ] **BC-10** — Self-learning: опыт меняет не только модель другого, но и модель себя.
- [ ] **BC-11** — Social triangles: A→B→C порождает третичное изменение отношений без специального «треугольника отношений».
- [ ] **BC-12** — Long-horizon proof: сценарии «оскорбление→вывод→память→избегание», «обман→вывод→слух→осторожность», «обучение→новое действие», «помощь→благодарность→ответная помощь» проживаются 100–1000 тиков.
- [ ] **BC-13** — Temporal consolidation boundary: immediate causal update ≠ temporal consolidation; сон — допустимое temporal window, но НЕ универсальный `commit()` для памяти; provenance и causal parent обязательны.
- [ ] **3.5b** — Контракт Active Inference ↔ Utility (PROPOSED — до вердикта Мастера; ROADMAP-AUDIT-01 §2.3).
- ⛔ **Stop-правило:** пока BC-1…BC-7 не доказаны, не начинать полноценный Active Inference как отдельный большой слой.

### 3.2. DLG — Диалоговая вертикаль (открытые пакеты)

- [ ] **DLG-2 (M)** — Состояние беседы (DLG-L2): session-state (тема/открытые вопросы/факт знакомства) в DialogueSession + гвардия повторов + анафора-резолв из контекста беседы в промпт; персистенция claims между беседами и тиками. **Гейт: DLG-GC-02** — беседа 5+ ходов: представление один раз, переспрос адресован, возврат к теме работает; через 50 тиков новая беседа без повторного знакомства.
- [ ] **DLG-3 (M)** — Составной вход (DLG-L3): multi-act декомпозиция компрессора, независимые slow-path ветки, порядок сохранён. **Гейт: DLG-GC-03** — команда из 3 действий даёт 3 semantic_acts, ни одна часть не потеряна.
- 📎 Сверка с USL-моделью (`docs/USL — Universal Semantic Layer.md`) до закрытия пакетов; внедрение USL — только после вердикта Мастера (USL-0).

### 3.3. LC — Loop Closure (открытые направления)

- [ ] **LC-IMPL-3** — оживление потребителя мировых событий во фронтенде: Ступень А (индикатор намерения + микрорешение, время идёт) / Ступень Б (полная церемония — тот же кодовый путь фокуса, что при обращении игрока; «облачко над головой» запрещено). Подшаг C3-A2-UI-2 (жизненный цикл индикаторов обращений NPC) ✅ d252d6d1. Осталось: Ступень Б + LC-IMPL-2 ч.2/2 (микрорешение-return) + DEBT-FE-DELTAS (COV-D83).
- [ ] **LC-IMPL-4** — память доезжает до речи + издатели PLAYER_ASKS_WHY: **поглощается NL-3/NL-5**; в этом треке только приёмка сквозного сценария «NPC обращается с памятью о происходившем».
- [ ] **LC-IMPL-5** — следы skip_time: события пропущенного периода оставляют следы (отношения, позиции, вещи, журнал) и не агрегируются в сводки; реестр dormant-сущностей — вердикт по каждой.
- [ ] **LC-IMPL-6** — полный набор диф-тестов F5 (§15.5 v4.12) + **эхо-тест LC-10 «Мир изменился без меня»** как §9-доказательство закрытия петли.

### 3.4. W-TRACK — World Embodiment (открытое)

- [ ] **G3-хвост / GC-08** — L3-обязательство G3: object → affordance → action → persistent consequence. Prerequisite: capability `spawn_world_object` для GC-08-harness (= A8). GC-02 не сливается с GC-08.
- [ ] **Object-cognition** — CAN_STEAL ≠ ACCEPT/WANT (находка Мастера на G3): возможность ≠ желание; следующий cognition-слой над G3.
- [ ] **Caller-guard** — Г4 `_ALLOWED_WRITERS` в WorldObjectStore (enforcement-ради-enforcement запрещён).
- [ ] **Reusable-паттерн объектных действий** — TAKE/USE/MOVE/GIVE/FOLLOW по прецеденту G3.
- [ ] **W4** — Embodied State (поза, локомоция, хват, attachment); Two-Domain (§ENIGMA-002) точечно при реальных W2-потребностях (CAN_GRIP для TAKE-таблицы).
- [ ] **W5–W9** — Presentation Projector / интерфейсы renderers — только контракты + PoC.
- [ ] **DEBT-SLEEP-DELIVERY** — доставка тел к кроватям: вертикальный разрыв `BODY → DECISION → WORLD → BODY` (elig=0/1200 в DriftLab). Решение — при spatial/affordance-контуре: intent → affordance search → reachable target → traversal → settled. Кандидат контент-фикса: «Тень тайно спит в подвале» / W2 sleep-affordance-типы BED→HAMMOCK/GROUND/SHELTER.

### 3.5. Body / Embodied (открытое)

- [ ] **V1+ калибровка** — chronic-veto cap и пороги через Calibration Lab (= A9).
- [ ] **D-MOM** — `motor_output_mult`: orphaned derived state (production consumer не обнаружен). Не блокирует; causal question для Sleep/Decision-фронта.
- [ ] **Sleep-семантика** — граница V1 не расширяется: отдельный вопрос, отдельный фронт.
- [ ] **SLEEP ≠ RESET** — зафиксировать canonical границу (wakefulness → sleep pressure → seeking → affordance → settled → transition → recovery → awakening); без второго SleepStore; все переходы детерминированы и replayable; duration ≠ quality (continuity, interruption, safety, affordance, pressure); прерывание — только через perception/arousal rules; новые recovery variables — только после anti-Bond test.

### 3.6. CCH-02 — Biography → State Audit (параллельная линия)

- [ ] **CCH-02** — автобиографии → PSYCH_EXTRACTION → ECR → аудит R/S/A/N → PSC → MechanismSpec → RP-1. **Триггер старта:** ≥3 утверждённых авторских биографии (RD-02-11). Реализация механизмов — НЕ в этом треке (CCH-03, отдельная очередь из PSC). Центральное утверждение SG-1: понять состояние ≠ уметь симулировать состояние.

### 3.7. MOT + AUDIT-10H — Motive & Decision Trace

- [ ] **MOT-0** — ADR «Decision Trace & Motive Mixture»: ре-верификация якорей §18.2; онтология DecisionTrace ≠ CausalEntry ≠ EventMemory ≠ self-model; реестр читателей; развилка «смесь против лесенки» — арбитру/Мастеру. **Гейт: ADR + DTO Registry + строки COV-0.**
- [ ] **MOT-1** — Тишина → видимость: счётчики отказов продюсеров, диф-тест «продюсер жив». **Гейт: GC-50.**
- [ ] **MOT-2** — Реестр продюсеров мотивов (рефакторинг run(), bit-identical). **Гейт: GC-51.**
- [ ] **MOT-3** — DecisionTrace: dormant-носитель и писатель (после BC-2). **Гейт: GC-52.**
- [ ] **MOT-4** — Исход → trace (outcome link; вход MEM-8/§8.L1). **Гейт: GC-53.**
- [ ] **MOT-5** — Смесь мотивов (Motive Mixture; после входов + развилки; F5-приёмка). **Гейт: GC-54.**
- [ ] **MOT-6** — Читатели trace: EXPLAIN, PLAYER_ASKS_WHY (совместно с NL-5), MEM-9. **Гейт: GC-55.**
- [ ] **MOT-7** — Интроспективный доступ → самообъяснение (мост к NL-11). **Гейт: GC-56.**
- [ ] **MOT-8** — Досье: планы, привычки, нормы (read-only; развилка «Фаза 6 TRAIT134 или отдельный трек» — Мастер). **Гейт: GC-57.**
- [ ] **AUDIT-10H.0** — Подготовка: сценарий (silver_wolf или Open_road), 10 in-game hours ≈ 600 ticks, инструментирование (ObservabilityTap + scene_changes_*.jsonl + replay_recorder). **Гейт: AUDIT-10H-GC-0.**
- [ ] **AUDIT-10H.1** — Сбор 5 потоков: causal_ledger, event_memory, decision_trace (после MOT-3), relationship_event, body_state. **Гейт: AUDIT-10H-GC-1.**
- [ ] **AUDIT-10H.2** — Причинно-следственная карта «событие → consumer → state delta → downstream event»; разрывы и тихие no-op. **Гейт: AUDIT-10H-GC-2** (`reports/AUDIT-10H_causal_chain_map.md`).
- [ ] **AUDIT-10H.3** — Вердикт Мастера о допуске MOT-9 (Causal Provenance Spine, GC-59). **Гейт: AUDIT-10H-GC-3.**

### 3.8. NL-01 — Narration Layer (NPC как интерфейс)

Парадигма: `WORLD TRUTH ≠ NPC MEMORY ≠ NPC BELIEF ≠ HOW NPC EXPLAINS HIMSELF`.

- [ ] **NL-0** — мини-ADR «Narrative Grounding Contract» (§12.3): иерархия источников речи; инварианты NL-INV-TRACE / IGNORANCE / NO-NUMBERS / DISCL / COST + контракты SALIENCE / CONSOLIDATION / SELF-INTERP / MODES.
- [ ] **NL-1** — хронология памяти: `event_id` + `game_day`/`tick` в EventMemory (миграция SQLite; сегодня day=0 у всех runtime-записей); decay из тиков; read-path за пределами top-10.
- [ ] **NL-3** — question-targeted recall: оживить мёртвый канал VerbalizationContext (NL-D1); вопрос игрока → выборка памяти/убеждений/биографии в контекст DM; SUBJ-индекс «о ком»; бюджет K-записей.
- [ ] **NL-4** — вербализация состояния: слепок (affect/PK/body-оси/drives + temporary_drives.reason/intent/life_project_state) → Python-слова (StateInterpreter); починка NL-D2; desires — по флаговому протоколу, фолбэк — EffectiveDrives.
- [ ] **NL-2** — Biographical Record: derived-конспект жизни (origin_events + EventMemory-вехи + L1Chronicle + role_history); anti-Bond: проекция, не SSOT; авторинг-схема origin_events v2 (связка RE-D7).
- [ ] **NL-5** — обоснования убеждений: издать PLAYER_ASKS_WHY → оживить `_explain_mode`; вербализация EpistemicRecord словами; «потому что видел: …»; НЕ causal-отладчик — отсутствие/ошибка объяснения валидны.
- [ ] **NL-6** — эпистемическое расхождение как геймплей: разные наблюдатели → разные версии одного события; CONTRADICTION surfacing.
- [ ] **NL-7** — диалоговая петля расследования: target_hint из UI-фокуса; peer-axis журнала; disclosure-вердикт в DM-пути; настойчивость → discovery cracks.
- [ ] **NL-8** — assertion-валидация реплик против контекста хода (метрика NL-LEAK, F5-корпус); активная ложь — вне трека до отдельного ADR.
- [ ] **NL-9** — GAMEPLAY CLOSURE: GC-41…49 (GC-48/49 — вместе со Ступенью 10).
- [ ] **NL-10** — консолидация и искажение памяти: салиенс-веса; мост E2-консолидации → MemoryCrystal; сжатие эпизодических деталей со временем; искажение на длинном горизонте.
- [ ] **NL-11** — самоинтерпретация: ответ на «почему ты так поступил?» из self-model NPC — рационализация / «просто так» / обвинение обстоятельств — валидные исходы; causal-отладчик запрещён; расхождение самообъяснений разных NPC (GC-49).
- [ ] **NL-12** — отдельный ADR: цепочка `KNOWLEDGE → INTENTION TO DECEIVE → CHOICE OF FALSE CLAIM → NARRATION` (обман, стратегическая ложь, самообман, манипуляция); пост-инвариант: все пять границ NL-INV-MODES тестируемы после внедрения лжи.

Порядок: фаза 1 (W1–W4, W6) параллельно A-секции; фаза 2 (W5, W7–W10) — после BC1_ENABLED ON/BC-2 и M2/D; фаза 3 — closure; фаза 4 (W13, обман) — только после зелёного NL-9.

### 3.9. MEM — Memory Architecture (v4.4)

- [ ] **MEM-0** — ADR «Memory Architecture»: тройка истин `WORLD TRUTH ≠ NPC MEMORY ≠ NPC BELIEF`; four-states forgetting; запреты §16.1 (anti-Bond, anti-архив, запрет авторезолюции противоречий); схема EventMemory v2.
- [ ] **MEM-1** — хронометраж, identity и перспектива записи (game_day/tick из TemporalContext; event_id через EventBus-identity; mem_id без md5-каннибализма; перспектива наблюдателя и сенсорный канал).
- [ ] **MEM-2…MEM-10** — по чеклисту §16.4 v4.12 (консолидация, забывание, реконструкция, MemoryCrystal, связка с NL-10/NL-11, вход MOT-4/§8.L1).
- 📎 Обязательный референс: сценарий Горана (§16.5, шаги 1–18).

### 3.10. COV — Полнота покрытия (открытые пакеты)

- [ ] **COV-3…COV-11** — по чеклисту §17.4 v4.12, включая COV-6 (физическое удаление CROSS_LOC BURY), COV-9 (enforce_system_requirements ROLLOUT-PENDING — включение перед дистрибутивом), протокол поддержания полноты §17.7, детерминизм и целостность рантайма §17.8.

### 3.11. EPI — Жизненный цикл информации (v4.8-draft)

- [ ] **EPI-0** — по чеклисту §19 v4.12 (информация как физический процесс; жизненный цикл наблюдение → хранение → передача → искажение → угасание).
- [ ] **EPI-CLIMATE** — информационный климат кампании.

---

## 4. Долг — главные открытые хвосты (полные реестры: §7 v4.12)

- [ ] **DEBT-CHRONICLE-REPLAY** — replay-кэш декомпозитора не подключён (владелец: контур replay).
- [ ] **DEBT-FE-DELTAS (COV-D83)** — потребительская часть во фронтенде (= LC-IMPL-3).
- [ ] **AUD-D4** — wildcard-writers NPCState (= A11).
- [ ] **RE-D2/S1** — dual-reader: raw-dict-канал слеп при живом pipeline-канале (сжатие — миграция на V2 после M2/D+GC-11).
- [ ] **RE-D9** — канал BehaviorMask мёртв (FAIL_STAGE=PROJECT) + fear-scale mismatch — активация = game-design, отдельный фронт.
- [ ] **Манифест need_slot.gen_rate** — DEBT-регистрация после G/H.
- [ ] **Хвосты CCH-3** — фильтр местоимений-хинтов, self-ref-INFO, канон-пополнения (фамилия Торнина «Серебряная Луна», таверна «Серебряный Волк»).
- [ ] **Полный прогон `redecompose_all_npc.py` на 6 NPC** (LLM-зависимая сессия).
- [ ] **T-CCH-07 живой эхо-тест NPC** + UI-вёрстка Character Debugger живым запуском pygame (отдельные сессии).
- [ ] **Системный долг** (§7.5) — брать паузами; **AUDIT-01 / NL-D / CG-D / MEM-D / COV-D / EPI-D / CCH-D** — read-only реестры находок, исполнение по мере активации владельцев.

---

## 5. Будущие эпохи (после закрытия текущих очередей)

- [ ] **Эпоха 7 — Predictive Perception & Prophecy:** TZ_Stage_2_5 Часть I + VZ/TZ_§19 (surprise = −log P(x_t|z_{t-1})); ObservationLayer/BeliefProjector; Prophecy System (ADR-O-330); Vertical Slice «Секреты Люси». Статус Части I: TEMPORAL EPOCH закрыт S266–S269; активен Predictive Runtime/PP.
- [ ] **Эпоха 8 — Temporal Identity, линии времени:** VZ/ТЕХЗАДАНИЕ ПРЕЕМНИКУ TZ-02 V.2.0 (WorldChronicle, 3 уровня времени), ADR-TIFL-001..003; visual aging после lineage.
- [ ] **Эпоха 9 — Общество + Memetic:** VZ/TZ_MEMETIC_01..03; Factions/Economy/Politics — ТЗ сформулировать. ⚠️ Сирота-зависимость: TZ_CONTENT_POLICY_FUNDAMENT.md отсутствует — создать мини-ТЗ или снять зависимость вердиктом.
- [ ] **Эпоха 10 — Bounded Rationality:** VZ/TZ_§18 (`U_M = I·R·U − C`) — только после Belief Layer. ⚠️ Устав §18 занят (S211) — ренумбер по прецеденту ADR-O-413.
- [ ] **Эпоха 11+ — Контент и презентация:** CT-01 Female-Targeted Dark Fantasy Layer («Таверна Серебряный Волк»); CT-02 AWC Process World Model (реверификация §13.2 обязательна); CT-03 Narrative Frame & Onboarding. Триггеры — решения Мастера (§8.R).
- [ ] **Отложенные ветки (НЕ активировать без Мастера):** MAG — соматико-резонансная магия (§21); WPS — world process simulation (§22); ARC — architecture convergence repair (§29); ARC-NPC — автономная NPC–NPC коммуникация (§30, PROPOSED); CGB — cognitive compute budget (§23, PROPOSED).

---

## 6. Прямые ссылки

- **Этот файл (v5.0-NEXT):** `docs/ENIGMA_ROADMAP_v5_NEXT.md`
- **Полный роадмап v4.12 (исторический реестр):** [github.com/4Um4/Enigma/blob/V.0.5.4.5.6_Полшага_3/docs/ENIGMA_ROADMAP_v4_12_WPS.md](https://github.com/4Um4/Enigma/blob/V.0.5.4.5.6_Полшага_3/docs/ENIGMA_ROADMAP_v4_12_WPS.md)
- **Репозиторий:** [github.com/4Um4/Enigma](https://github.com/4Um4/Enigma) · ветка `V.0.5.4.5.6_Полшага_3`
- **Ключевые ТЗ корпуса:** `docs/Почти Актуальные TZ/` · **Атлас ADR:** `docs/audits/`
