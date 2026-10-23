# ROADMAP-AUDIT-01 — Cognitive Infrastructure & Observability

**Тип:** read-only аудит + интеграция дополнений в дорожную карту. Код не менялся.
**Дата:** 2026-10-23 · **Код:** V.0.5.4.4.0 (`version.txt` = `pyproject.toml`; метка архива V.0.5.4.4.2) · **Roadmap:** `ENIGMA_ROADMAP_v4_11_WPS.md` (v4.11-draft, 3617 строк).
**Методология:** каждое утверждение — доказательная цепочка `CLAIM → CODE (file:line) → CALL PATH → TEST → OBSERVABLE RESULT`. Классификация: `VERIFIED` (код + тесты), `PARTIALLY IMPLEMENTED`, `DOCUMENTED ONLY`, `MISSING` (отсутствие подтверждено проверкой альтернативных имён/точек вызова), `UNVERIFIED`. Все предложения — `PROPOSED`, до вердикта Мастера. Метод: 6 параллельных независимых разведок кода + перекрёстная верификация ключевых якорей вручную (sed/grep по файлам).
**Правило результата:** этот документ — обоснование; интегрированные формулировки живут в roadmap (один факт — одно место). Версия roadmap и статусы существующих задач не менялись; очередь §0.2 не расширялась.

---

## 1. Краткий вывод о состоянии архитектуры

1. **Детерминированное ядро реально, LLM из решения изгнан — это не декларация, а проверенный факт.** `DecisionHub` — чистый Python-редьюсер utility-скора без единого LLM-вызова (`decision_hub.py:12` «LLM не участвует. Всё — Python.»; `_score_all` :1055–1137); случайность — только `KernelRNG(tick, npc_id, salt)` (`npc_tick_pipeline.py:934`), детерминизм защищён инвариантами IPT (INV-KERNEL-RNG, INV-WALL-CLOCK) и закртыми DET-1/DET-2/DET-3 (§17.8). Направление «LLM не должен незаметно стать владельцем истины» — соблюдено архитектурно и инвентарно (INV-LLM-EXILE, INV-LLM-NOT-SSOT).

2. **Выбор действия сегодня — это utility-модель, а не Active Inference; неоднозначность локализована.** В `decision_hub.py` нет ни `free_energy`, ни `active_inference` (grep по файлу — ноль); формула скоринга документирована в docstring (:230–238) и считается компонентной суммой с клампом [−2.0; 3.0]. Исполняемый механизм с именем «Active Inference» существует один — `AffectiveIntegrator` (prediction error → аффективная нагрузка, `affective/affective_integrator.py:65–78`, ADR-049/ADR-O-206) — и он про аффект, не про выбор действия. Ожидания в решении мертвы (ExpectationStore удалён DEEP-015; TODO «Эпоха 7» `npc_tick_pipeline.py:459–462`); `DecisionResult.expected_success` никогда не пишется; ResolutionEngine не вызывается (TODO :1200–1202). Канонический stop-rule «полноценный Active Inference — только после BC-1…BC-7» (§3.5) согласован с кодом.

3. **Причинная наблюдаемость — самый тонкий слой из всех десяти направлений.** Существует три частичных «позвоночника» происхождения: (а) `EventDTO.id` (детерминированный md5, `domain/events.py:101–104`) → `ClaimEvent.event_id` → `EpistemicRecord.source_claim_id` (живой, но только для 3 предикатов — THEFT/PLAYER_ATTACKED, `events/observation_subscriber.py:107–114`); (б) `EventDTO.id` → `StateDeltaProposal.trace_id/causal_parent` → `ConclusionRecord.evidence` (производитель жив, терминал спит за BC1_ENABLED OFF); (в) `EventDTO.id` → SQLite `event_memories.id = "{event.id}:{npc}:{md5}"` (живой, но id выбрасывается при загрузке — `memory_manager.py:407–410`, поля event_id в модели нет). При этом `CausalEntry.cause` в проде = None (все боевые вызовы `apply_batch` идут без cause: `phases/affective.py:66`, `phases/integration.py:77`, `phases/commit_phase.py:77`), `Cause.source_belief_id/source_memory_id/trigger_chain` не имеют ни одного писателя, леджер обрезается до 20 записей (`state_applicator.py:539, :1026`), решения не персистентны (`[WHY][DECISION]` — только `logger.debug`, `decision_hub.py:804–819`). Итог: цепочка `belief ← memory ← observation ← world fact` сквозным запросом сегодня не восстанавливается. Пробел уже имеет зарегистрированного владельца-аудита (AUDIT-10H §7.6: `event_id → memory → belief → relationship → decision → action → consequence` — read-only, «не создавать механизм до результатов») и тестовый оракул цепочки (§9.8b) — но не имеет контракта постоянного происхождения. Дополнение MOT-9 (PROPOSED) закрывает именно этот зазор.

4. **Memory lifecycle — самая опасная зона: подтверждена живая латентная деструкция.** seq_0-коллизия верифицирована на текущем коде: production `EventMemory` не имеет поля id и всегда `sequence_id=0` (`models/npc_state.py:230`; `MemoryManager.apply` не назначает), поэтому `getattr(e, "id", f"seq_{e.sequence_id}")` в PromotionEngine даёт «seq_0» для всех членов группы (`promotion_engine.py:157–166`), а фильтр `kept = [m for m in narrative_cache if f"seq_{m.sequence_id}" not in _removed_keys]` (`memory_manager.py:663–665`) при срабатывании компрессии (каждые 10 тиков, `phases/memory.py:36–56`) стирает ВЕСЬ несжатый кэш. Тесты маскируют дефект уникальными sequence_id (`test_compression_stage9.py:130–160`). Абстракции не пишутся в SQLite → после рестарта исходные записи воскресают (MEM-D8 подтверждён). Это уже регистрировалось рой-исследованием памяти (MEM-D5/D8, §7.9) — аудит подтверждает актуальность на V.0.5.4.4.0 и добавляет точные якоря. Плюс четыре тихих пути удаления (FIFO-переполнение WM `working_memory.py:38`, FORGOTTEN-сброс «молча умирает» `:96–99`, seq_0-вбивание, STM-оборот `dialogue_session.py:90–91`) при полном отсутствии referential integrity: PRAGMA foreign_keys=ON включён (`sqlite_store.py:71`), но ни одна таблица не объявляет FK; evidence/causal_parent/contract_ref могут висеть в воздухе незаметно.

5. **Устойчивость намерений построена, но защиты в проде нет — измерительный режим без enforcement.** CommitmentRegistry жив (ROLLOUT-ON, born-True c4b75107, `commitment_registry.py:33`) — но это shadow-реестр: зеркалирует факты, не меняет поведение. Arbiter в LOG_ONLY (`ARBITER_ENFORCEMENT` OFF, `enforce()` всегда True, `commitment_arbiter.py:237–253`); каскад прерываний мёртв (S203_4_ARBITER_INTERRUPT OFF). Anti-thrash сегодня держится исключительно на внутренней гистерезисе хаба: inertia ≤ +0.2, exhaustion −0.08/тик простоя, порог давления 0.15→0.53, стоимость переключения 0.05–0.23, MIN_INTENT_SCORE 0.15 (`decision_hub.py:730–838`, `core/constants.py:77–114`) — плюс «анти-флаппинг»-комментарий арбитра (:55) с измеренным прецедентом «1006 вызовов / 359 REJECT на 200 тиков» (:245–247). Формально критерий «нет бесконечного переключения при неизменных входах» тестом не закреплён нигде.

6. **Регулирование вычислений существует, но не как контракт, и с открытым разрывом offscreen-жизни.** Пять живых регуляторов: LOD AdaptiveTickLoader (порог 12 NPC, гистерезис 5/50, DET-1-детерминизм), tier-планирование LifeEngine (major/minor ÷3/mass-пропуск), OFFSCREEN-SKIP (не упрощение — полный пропуск), speaker-cap 6/ход + caps DialogueQueue, D8P STALE-гейт (3 тика). Но: NPC вне помеченных локаций не живут вовсе — потребности не копятся, когниция не идёт; механизм догона деградировал (`macro_simulate` принудительно `idle_seconds = 0.0`, `life_engine.py:338–344`), `reconcile_state` покрывает только wall-clock-простой (`scene_init.py:133`). Инвариант «NPC вне поля зрения не перестаёт существовать» выполняется только в смысле персистентности снапшота, не в смысле жизни. Эхо-тест LC-10 «Мир изменился без меня» на текущем коде не воспроизводим — что честно отражено статусом LC-IMPL-5/6. Token-budget LLM отсутствует (D63 — вердиктом вынесен из COV-2), per-phase стоимость когниции не измеряется (COV-D64/D71 открыты), числовые бюджеты P14 не установлены — и правильно: профилирование (DET-2: 38.47 мс/тик @ 6 NPC) — единственная точка данных.

7. **Authoring pipeline — самый достроенный контур из десяти, но семантическая валидация не в гейте компиляции.** Полная цепочка жива: авторский текст → Ctrl+G decompose (temperature=0, JSON Mode, нормализатор fail-loud ×6) → F9 canonize («Save = Contract», 422-класс отказа, INV-LLM-NOT-SSOT: LLM_DRAFT в канон запрещён) → сеялка CCH-4 (**существует в коде** — `chronicle_seeder.py`, ADR-O-423, вопреки незакрытой галочке §0.2: сеет EventMemory day<0, knowledge, relationships, импринты decay_rate=0, beliefs; Character Debugger — действительно отсутствует) → CCH-5 проекции. НО: ConsistencyService (хронология/канон, CCH-2.5) не вызывается ни одним маршрутом API — канонизация проверяет структуру, не семантику; итог — отложенные детонации: shipped-канон `guard_borko` роняет сеялку (`SeederError: 12 возраст-якорей без game_start_age`), канон `blacksmith_orm` содержит 13 несеемых отношений (неразрешённые подсказки) и LLM-мусор в payload (`nature: "依赖"`). Белые пятна — сломанный контур end-to-end (реестр есть, производителя нет: 0 white_spots в обоих канонах). CLI авторинга отсутствует (ad-hoc скрипты в корне).

8. **Статистический слой ассертов — MISSING как класс, и это надо зафиксировать честно.** IPT — 53 бинарных инварианта (реестр `IPT.py:2381–2435`; «49/49» в шапке roadmap устарел, и roadmap сам это знает: «шапка IPT 49/49→53 — за Мастером», :1386). SUPERBOX — 89 детерминированных сценариев Control/Treatment; DriftLab — 9 режимов до 100k тиков с вердиктами по хэшам и классами дрейфа A–E. Гипотеза знаменитой «p=0.0542» снята: это `p_sexual` (интенсивность давления, `re_gh_dynamics_test.py:83`), не p-value. Grep по scipy/ks_2samp/chi2/percentile-ассертам — ноль. Единственное сравнение дисперсий — `test_pattern_detector.py:65–80`. Частота переключения намерений, распределение длительности целей, устойчивость различий между NPC на сотнях тиков — сегодня ничем не ассертированы. §8.Q3/Q6 читаются как обещание того, чего нет.

9. **Идентичность: измерительный контур CCH-02 спроектирован, дрейф-диагностика рантайма не имеет владельца.** Четырёхклассная таксономия (canonical origin / current state / development / integrity violation) не зафиксирована нигде; ближайшие носители — ECR-уровни CCH-02 (L0–L3, все MISSING как код), L1-хроника (append-only, INV-L1-APPEND-ONLY), replay-детерминизм, INV-NO-RETRO-SIM. Право NPC на ошибку/забывание/ложь о себе уже канонизировано (§12.0, NL-11) — аудит не меняет его; добавляется только диагностическая классификация расхождений (§14.6 PROPOSED).

10. **Диагностика не мутирует симуляцию — проверено кодом и закреплено законом.** ObservabilityTap — ноль записей в состояние (`observability_tap.py:68–85`, lab-only); CausalObserver — посмертный парсер логов; scene_changes.jsonl — файл-лог; ограничения FORBIDDEN-feedback-loop в `diagnostics.yaml:211–215` и CAUSAL_CONTRACT §11. Нюанс, который надо не потерять: механизмы с причинной лексикой (`causal_slice_*.py` → модификаторы DecisionHub; `CausalEntry.emotional_impact>0.7` → TemporaryDrive) — это симуляционные механизмы, а не наблюдаемость; их лог-строки наблюдаемы, но сами они пишут в мир.

---

## 2. Таблица доказательств по десяти направлениям

Формат: направление → вердикт → ключевые доказательства (file:line) → что уже закрыто существующими механизмами → зазор.

### 2.1 Causal & Epistemic Inspector — `PARTIALLY IMPLEMENTED`

| # | Утверждение | Класс | Доказательство |
|---|---|---|---|
| 1.1 | Стабильные идентификаторы причинных событий существуют (EventDTO, md5, ординалы) | VERIFIED | `domain/events.py:62–115` (id = md5(type:source:ts:ordinal), BUG-FB-037), `services/events/event_identity.py:13–29` (единственный писатель `scene_state["event_ordinals"]`) |
| 1.2 | Идентификатор события доезжает до эпизодической памяти только как префикс SQLite-строки; в RAM-модели поля нет, при загрузке отбрасывается | VERIFIED | `memory_manager.py:364–372` (запись), `:407–410` (pop id при load), `models/npc_state.py:214–256` (нет поля event_id), схема `event_memories` без event_id-колонки `sqlite_store.py:160–182` |
| 1.3 | Убеждения уровня BeliefState/CrystallizedBelief не ссылаются на события/память; ConclusionRecord (BC-1, спит) — единственный носитель evidence | VERIFIED | `models/npc/beliefs.py:24–31` (source = строковая метка), архитектурный комментарий «пайплайн не построен» :60–83; `domain/identity_events.py:63–75` (source_id = другой NPC, не event); `domain/conclusions.py:60–62, 88–92` (evidence/causal_parent) + BC1_ENABLED OFF `conclusion_runtime.py:22–30` |
| 1.4 | CausalEntry пишется, но: cause=None во всех боевых вызовах; ledger обрезан до 20; belief/memory/trigger_chain поля Cause не пишутся никем | VERIFIED | `state_applicator.py:195` (единственный конструктор Cause), `:539/:1026` (cap 20), `phases/affective.py:66`, `phases/integration.py:77`, `phases/commit_phase.py:77` (apply_batch без cause), `models/psychological.py:66–68` (поля без писателей), официальный вердикт `models/causality_manifest.py:145` (npc_state.causal_ledger = DEBT) |
| 1.5 | Решение не оставляет персистентного следа: scores_trace живёт один тик в tick-контексте; WHY-разбивка — logger.debug | VERIFIED | `decision_hub.py:804–819`, `npc_tick_pipeline.py:1215–1216` (TickMutation) → `npc_contexts["scores_trace"]` (`pipeline_runner.py:350, 364–414`), потребителей вне SUPERBOX-контекста нет |
| 1.6 | Debug-эндпоинт causal ledger жив (God Mode) | VERIFIED | `api/routes_debug.py:68–96` (GET /api/debug/npc/{npc_id}/causal_ledger) |
| 1.7 | Восстановление «убеждение ← память ← наблюдение ← факт» сквозным запросом невозможно | VERIFIED | три частичных позвоночника (см. §1.3 вывода) + отсутствие joinable id в EventMemory/BeliefFragment/CrystallizedBelief/L1 |
| 1.8 | Диагностика не влияет на симуляцию | VERIFIED | `observability_tap.py:68–85` (ноль записей), `diagnostics/causal_observer.py:59–86`, `diagnostics.yaml:211–215` (FORBIDDEN feedback loop), CAUSAL_CONTRACT §11 (:763–770) |
| 1.9 | Отличить «не наблюдал» от «наблюдал с отрицательным результатом» частично можно (Vacuum-доктрина, unknown ⇒ ноль записей в CCH) | PARTIALLY | §0.3 истина 5; эпистемика: отсутствие записи = нет знания (`epistemic_store.py`); отрицательный результат наблюдения как отдельный факт — MISSING |
| 1.10 | Уже существующие владельцы направления | — | AUDIT-10H (§7.6, read-only аудит цепочки за 10 игровых часов), §9.8b (машинно-читаемая цепочка как оракул GC-тестов), §8.Q4 (social chain traces с provenance), MOT-3/4/6 (DecisionTrace + outcome + читатели), COV-D71 (нет экспорта/дашборда), CCH-4 Debugger (T-CCH-08 дрил-даун) |

**Зазор (→ MOT-9 PROPOSED):** контракт постоянного происхождения (не посмертного аудита): event_id в EventMemory/убеждениях, cause в проде, персистентный след решения, глубина > 20, машинно-читаемый экспорт. Три этапа (сбор → машиночитаемый trace → инспектор) уже описаны в §9.8b + AUDIT-10H; MOT-9 добавляет только runtime-контракт без второго источника истины.

### 2.2 Memory Lifecycle & GC — `PARTIALLY IMPLEMENTED` (с живым деструктивным дефектом)

| # | Утверждение | Класс | Доказательство |
|---|---|---|---|
| 2.1 | WM = FIFO deque(20), переполнение удаляет молча, без счётчика и промоушена | VERIFIED | `working_memory.py:17, 26–38, 124–127` |
| 2.2 | FORGOTTEN-записи умирают «молча» из буферов (кроме is_compressed-эссенции) | VERIFIED | `working_memory.py:91–105` (комментарий «Всё прочее ниже порога — молча умирает») |
| 2.3 | seq_0-коллизия: одна группа компрессии стирает весь несжатый narrative_cache; срабатывание — каждые 10 тиков | VERIFIED | `models/npc_state.py:230` (sequence_id=0, поля id нет), `promotion_engine.py:157–166`, `memory_manager.py:663–665`, триггер `phases/memory.py:36–56`; маскировка тестами `test_compression_stage9.py:130–160` |
| 2.4 | Абстракции компрессии не персистентны → воскресение исходников после рестарта | VERIFIED | `phases/memory.py:44–50` (только JSON-кэш NPC), `memory_manager.py:383–428` (load восстанавливает исходники из SQLite) |
| 2.5 | Decay: хардкод game_days=1.0 на партию из 10 тиков = ускорение календаря ×2.4; LTM не стареет вовсе | VERIFIED | `memory_manager.py:806` + оба боевых вызова без аргумента (`phases/memory.py:118–120`, `working_memory_tick.py:153–156`), фиксация тестом `test_decay_game_days_stage8.py:108–121`; SQLite-строки не переписываются после ingest |
| 2.6 | WM/STM не персистентны (рестарт-амнезия MEM-D33) | VERIFIED | `working_memory.py:5–7` (объявление RAM-only), нет save/load вызовов; восстанавливаются только narrative_cache/identity/beliefs |
| 2.7 | Референсной целостности нет: PRAGMA foreign_keys=ON, но ноль FK-деклараций; evidence/contract_ref могут висеть | VERIFIED | `sqlite_store.py:71` vs `:82–197`; `models/causality_manifest.py:76,78` (compressed_from/contract_ref = DEBT CG-D-11/12) |
| 2.8 | Архивирование существует только у L1-хроники | VERIFIED | `l1_chronicle.py:250` ← `phases/idle_services.py:43`; для event_memories — только delete_campaign |
| 2.9 | Консолидаторы детерминированы (без LLM/RNG) | VERIFIED | `dialogue_consolidator.py:14–29` (llm_client не вызывается), `resonance_engine.py:15, 90–362`, шаблоны `promotion_engine.py:33–47` |
| 2.10 | MemoryCrystal/ExperienceTrace: схемы и SQLite-таблицы есть — писателей/читателей в проде ноль | VERIFIED (DEAD) | `memory_crystal.py:14–121`, `experience_trace.py:21–74`, `sqlite_store.py:107–157, 280–411`; вызыватели — только `test_phase_a_memory_fixes.py:563–761` |
| 2.11 | Существующие владельцы | — | MEM-трек целиком: MEM-2 (seq_0 + единый decay + рестарт-инвариант), MEM-5 (четыре состояния), MEM-10 (replay-канал, компакция LTM, рестарт-амнезия, SCALE-MEM), MEM-D17 (evidence-поле убеждений), MEM-D31/D32/D33; §16.1 запрет авторезолюции противоречий |

**Зазор (→ §16.10 PROPOSED):** не формализованы (а) запрет молчаливого удаления, делающего убеждение/решение/обязательство необъяснимым; (б) различение «удаление оперативной записи ≠ исчезновение исторического факта» как тестируемый инвариант (сегодня случайно выполняется через живучесть SQLite-строк — и нарушается в обратную сторону воскресением 2.4); (в) запрет превращения вероятностного вывода в объективный факт при консолидации; (г) поведение зависимых объектов (evidence/causal_parent/contract_ref) при удалении.

### 2.3 Active Inference ↔ Utility — `PARTIALLY IMPLEMENTED` (utility — исполняемая модель; AI — концептуальная рамка + аффективный prediction error)

| # | Утверждение | Класс | Доказательство |
|---|---|---|---|
| 3.1 | Выбор действия = utility-скоринг: формула в docstring; компонентная сумма; кламп [−2.0; 3.0]; argmax | VERIFIED | `decision_hub.py:230–238, 1055–1137, 749–751` |
| 3.2 | LLM в решении не участвует | VERIFIED | `decision_hub.py:12`; grep llm-импортов — ноль |
| 3.3 | Терминов Active Inference / free energy в decision-пути нет | VERIFIED (MISSING) | grep по `backend/app` — только affective-слой |
| 3.4 | Единственный исполняемый «Active Inference» — аффективный prediction error (не выбор действия) | VERIFIED | `affective/affective_integrator.py:18, 35, 65–78` (ADR-049/ADR-O-206); канал pe_modifiers_map всегда пуст в проде (`domain/tick.py:163`, `tick_orchestrator.py:2194–2195`) |
| 3.5 | Ожидания не участвуют в решении: ExpectationStore удалён (DEEP-015), рельсы — TODO | VERIFIED (DEAD) | `npc_tick_pipeline.py:459–462` (TODO «Эпоха 7: ExpectationStore (Active Inference)»), `state_applicator.py:789`, возрождение — только MEM-8 после BC-2/BC-3 (§16.4) |
| 3.6 | `expected_success` объявлен, никогда не пишется; ResolutionEngine не встроен | VERIFIED (DEAD) | `decision_hub.py:133`; TODO `npc_tick_pipeline.py:1200–1202` |
| 3.7 | Детерминизм: KernelRNG(tick, npc_id, salt), noise ±0.10; hysteresis-состояние (pressure_accumulator) кросс-тиковое | VERIFIED | `npc_tick_pipeline.py:934`, `kernel_rng.py:27–56`, `decision_hub.py:1119, 775–838` |
| 3.8 | Modifier Contract v1 — 9 аддитивных слоёв модификаторов | VERIFIED | `decision_hub.py:365–393` |
| 3.9 | Существующие владельцы | — | §3.5 (stop-rule BC-1…BC-7 → потом AI), §8.K1–K7, §0.3 «Отложено намеренно», MATH-6 (формулировка «inspired by Active Inference; free-energy wording forbidden»), MEM-8 (ожидания) |

**Зазор (→ §3.5b PROPOSED):** контракт-зафиксация (какая модель исполняется, какие данные, как проверяется) + сравнительный протокол для будущих альтернатив — без предписания матричного перехода.

### 2.4 Authoring Compiler Pipeline — `PARTIALLY IMPLEMENTED` (конвейер жив; семантическая валидация вне гейта)

| # | Утверждение | Класс | Доказательство |
|---|---|---|---|
| 4.1 | Полная цепочка decompose → confirm → canonize жива; LLM_DRAFT в канон не проходит (422) | VERIFIED | `routes_chronicle.py:339–361` (canonize, ValueError→422), `chronicle_store.py:351–355, 286–290` (validate_document), UI `chronicle_app.py:586–632` (F9/Shift+F9) |
| 4.2 | Сеялка CCH-4 существует в коде (roadmap-галочка [ ] не закрыта; Debugger отсутствует) | VERIFIED (расхождение) | `chronicle_seeder.py` (19.8 КБ: SeederError, build_seed_memories/knowledge/relationships/imprints/beliefs), проводка `npc_loader.py:962–996`; Debugger в frontend/chronicle_editor отсутствует |
| 4.3 | Shipped-канон ломает сеялку: guard_borko → SeederError (12 якорей без game_start_age) — fail-loud, не тихий | VERIFIED | `chronicle_seeder.py:124–141, 169–171`; live-проб агента; оба канона имеют game_start_age=null |
| 4.4 | ConsistencyService (хронология intra/cross/canon) не вызывается ни одним API-маршрутом — семантическая валидация вне гейта компиляции | VERIFIED | grep ConsistencyService по backend/app/api и chronicle_store — ноль; вызыватели только тесты/probe |
| 4.5 | Референсы резолвятся только на сеянии; несеяемые записи остаются в каноне с предупреждением | VERIFIED | `chronicle_seeder.py:289–295` (отношения «не сеется»), `:356–358` (belief вне реестра — warning); blacksmith_orm: 13 несеемых отношений |
| 4.6 | Белые пятна: домен+реестр живы, производителя нет (0 white_spots в канонах) | VERIFIED (DEAD-контур) | `white_spot_registry.py` (writer-guard), декомпозитор не создаёт WhiteSpot (`routes_chronicle.py:246–269`) |
| 4.7 | Replay-cache декомпозитора не подключён (DEBT-CHRONICLE-REPLAY) — компиляция воспроизводима статистически, не байт-в-байт | VERIFIED | `biography_decomposer.py:13–15`; temperature=0 + KernelRNG-salt (`:113–117`, `llama_cpp_provider.py:163–165`) |
| 4.8 | CLI авторинга отсутствует; ad-hoc скрипты в корне (`diag_cch_pipeline.py`, `canon_verdicts_report.py`, `fix_confirm_and_canonize.py`) | VERIFIED (MISSING) | inventory scripts/ |
| 4.9 | Существующие владельцы | — | CCH-0…CCH-6 (§13), UX-1…4 (UX-CHRONICLE-CLARITY — отчёт «что сеется» UX-4), CCH-2.5 (ConsistencyService построен), §14 CCH-02 (диагностическая линия), DEBT-CHRONICLE-REPLAY |

**Зазор (→ §13.7 PROPOSED):** гейт семантической валидации в момент канонизации (ConsistencyService + резолюция референсов до канона + отчёт компиляции), решение по guard_borko/orm-канону, CLI-первая версия — без дубля существующего авторинга.

### 2.5 Cognitive Tick Throttling — `PARTIALLY IMPLEMENTED` (регуляторы есть; контракта и offscreen-жизни нет)

| # | Утверждение | Класс | Доказательство |
|---|---|---|---|
| 5.1 | LOD: порог 12 NPC, гистерезис 5/50, дальние локации — только Фаза 10; вход детерминирован (DET-1) | VERIFIED | `adaptive_tick_loader.py:11–68`, `tick_orchestrator.py:724–775, 1014–1018` |
| 5.2 | Tier-планирование: major каждый тик, minor раз в 3, mass не симулируется | VERIFIED | `life_engine.py:746–816`, `constants.py:174` |
| 5.3 | OFFSCREEN NPC полностью пропускаются (не упрощение); догона нет: macro_simulate вырожден (idle_seconds=0.0), reconcile — только wall-clock | VERIFIED | `life_engine.py:636–665, 321–402 (338–344)`, `scene_init.py:133`, `offscreen/world_projection_buffer.py` — мёртв (VERDICT=OFF, ADR-O-309) |
| 5.4 | Речевые/LLM-ограничители: MAX_SPEAKERS_PER_TURN=6; DialogueQueue 20/мин, 30с кулдаун, backpressure 0.7; один LLM-executor | VERIFIED | `constants.py:167`, `execution/dialogue_queue.py:41–49`, `dialogue_executor.py:453` |
| 5.5 | Двухскоростной закон жив: D8P IntelligenceQueue (STALE 3 тика, bound 512) + доктрина отказа LLM «отказ = пауза времени», d61-тест 32/0 | VERIFIED | `intelligence_queue.py:51–111, 259–343`, `main.py:26`, SUPERBOX `d61_llm_outage_doctrine_test.py` |
| 5.6 | Приоритетная очередь LLM существует за LLM_RESILIENCE_V1 (default OFF; прод = abort-предыдущего) | VERIFIED (DORMANT) | `router.py:158–185, 408–550, 851–864`, `flags.yaml:129–136` |
| 5.7 | Token-budget отсутствует (D63 — вердиктом вне COV-2); per-phase стоимость не измеряется (D64/D71 открыты); P14 без чисел | VERIFIED (MISSING) | grep token_budget — ноль; `roadmap:1316, :1321, :1493` |
| 5.8 | DEBT-QUIESCE — это async-interleaving недетерминизм (не пауза внеэкранной когниции); открыт | VERIFIED | `roadmap:1124`, `game_loop.py:2227–2245` (quiesce = дренаж при dispose), `experiment_runner.py:623, 661` |
| 5.9 | Существующие владельцы | — | §8.P1/P12/P13/P14, §8.Q3/Q6, §9.8 SCALE-01…07, COV-2 (закрыт частично), DET-1/2/3 (§17.8), W-контур (кандидат DEBT-QUIESCE) |

**Зазор (→ §23 CGB PROPOSED):** контракт классов работ + инварианты + измерение стоимости; вердикт по offscreen-семантике (замороженные NPC vs накопление/догон) — сегодня инвариант «вне поля зрения не перестаёт существовать» выполняется только как персистентность снапшота.

### 2.6 Commitment & Intent Thrashing — `PARTIALLY IMPLEMENTED` (инфраструктура построена; enforcement спит; ассерта устойчивости нет)

| # | Утверждение | Класс | Доказательство |
|---|---|---|---|
| 6.1 | CommitmentRegistry жив (ROLLOUT-ON), но shadow-only: зеркала фактов, ноль поведенческих эффектов | VERIFIED | `commitment_registry.py:33` (born-True), `flags.yaml:34–41`; доктрина «mirrors facts, never changes behavior» |
| 6.2 | Arbiter LOG_ONLY: enforce() всегда True; REJECT только в телеметрии (1006 вызовов / 359 REJECT / 200 тиков) | VERIFIED | `commitment_arbiter.py:36–50, 237–253, 297–300`, прецедент замера :245–247 |
| 6.3 | Каскад прерываний мёртв: нужен ARBITER_ENFORCEMENT ∧ S203_4_ARBITER_INTERRUPT (оба OFF) | VERIFIED (DORMANT) | `commitment_arbiter.py:40–49`, `flags.yaml:77–91` |
| 6.4 | Anti-thrash сегодня = внутренний гистерезис хаба (inertia/exhaustion/pressure/switching-cost/MIN_INTENT_SCORE) | VERIFIED | `decision_hub.py:730–838, 1761–1908`, `constants.py:77–114` |
| 6.5 | ActionWindup жив для attack/steal (2 тика), stale-валидация в Phase 7; task-очередь прерывает устаревшие интенты | VERIFIED | `domain/action_windup.py:22–68`, `phases/post_decision.py:300–370, 386–578`, `task_scheduler.py:316–392` |
| 6.6 | Ассерта «нет флаттера при неизменных входах» не существует | VERIFIED (MISSING) | grep reconsider/reevaluate/thrash — ноль; 2318 строк test_action_commitment.py не содержат поведенческого анти-флаппинг-ассерта |
| 6.7 | Решение вызывается не каждый тик: LOD + world_tick раз в 15 игровых минут + MOVING-пропуск + nearby-фильтр хода игрока | VERIFIED | `tick_orchestrator.py:1014–1026`, `npc_tick_pipeline.py:146–155`, `core/config.py:47` |
| 6.8 | Существующие владельцы | — | COV-1.5 rollout-пакет 4 (арбитраж: ARBITER_ENFORCEMENT + S203_4_* + зеркала, §17.8 Шаг 6), §8.O9, MOT-5 (смесь, Governor), interrupt_traversal (причины-реестр `domain/action_commitment.py:87–95`) |

**Зазор (→ §17.8 Шаг 7 PROPOSED):** пять критериев приёмки устойчивости намерений для rollout-пакета 4 — до включения enforcement.

### 2.7 Identity Drift Guardrails — `DOCUMENTED ONLY` (измерительный контур спроектирован; runtime-диагностики нет)

| # | Утверждение | Класс | Доказательство |
|---|---|---|---|
| 7.1 | CCH-02: конвейер PSYCH_EXTRACTION → PU → ECR → R/S/A/N → PSC отсутствует как код (capability нет) | VERIFIED (MISSING) | grep PSYCH_EXTRACTION/ECR/PU- по backend — ноль; Capability enum закрыт (`llm/provider.py:159–180`); roadmap :280/:1529 — unchecked |
| 7.2 | Четырёхклассная таксономия расхождений (origin/state/development/integrity violation) нигде не зафиксирована | VERIFIED (MISSING) | отсутствует во всех документах корпуса |
| 7.3 | Ближайшие носители целостности: L1 append-only, INV-NO-RETRO-SIM, INV-EPISTEMIC-TRUTH-IMMUTABILITY, replay-детерминизм | VERIFIED | `IPT.py:979–1045, 1522`; CAUSAL_CONTRACT §10.4 |
| 7.4 | Право NPC на ошибку/забывание/ложь о себе канонизировано; дрейф ≠ неизменность | VERIFIED (доктрина) | §12.0 принципы вердикта NL-01; NL-11; MEM-5 four-states |
| 7.5 | Существующие владельцы | — | §14 (CCH-02 целиком), MEM-4 (temporal anchors), CCH-4 Debugger (расхождение «хроника vs runtime» — легальный показ), MOT (trace) |

**Зазор (→ §14.6 PROPOSED):** фоновая (тестовая) классификация расхождений по четырём классам с исходом UNCLASSIFIED; переиспользует ECR/PU/MOT-9/MEM-5 — без нового стора и без требования совпадения текущих убеждений с досье.

### 2.8 SUPERBOX / DriftLab / Statistical Assertions — статистический слой `MISSING`; инфраструктура `VERIFIED`

| # | Утверждение | Класс | Доказательство |
|---|---|---|---|
| 8.1 | IPT: 53 зарегистрированных бинарных инварианта (шапка roadmap «49/49» устарела — и roadmap сам это фиксирует «за Мастером») | VERIFIED | реестр `IPT.py:2381–2435` (53 функции), `:1386` roadmap |
| 8.2 | SUPERBOX: 89 сценариев, детерминированные Control/Treatment, адаптер калибровки | VERIFIED | `tests/sandbox/SUPERBOX/` (scenarios/), `calibration/superbox_adapter.py:39–95` |
| 8.3 | DriftLab: 9 режимов (200/5 000/10 000/100 000 тиков), классы дрейфа A–E, вердикты MATCH по SHA-256, seed 44444 в replay-режимах | VERIFIED | `drift_laboratory.py:86–114, 245–257, 2196–2199`; артефакт `reports/дрейф_replay_determinism.md` (2×10k MATCH, 78.3 мс/тик) |
| 8.4 | «p=0.0542» в roadmap — это p_sexual (давление), не p-value | VERIFIED (снятие гипотезы) | `scenarios/re_gh_dynamics_test.py:83`, `docs/audits/ADR-O-419_IMPACT.md:16` |
| 8.5 | Статистических ассертов (p-value/KS/χ²/частоты/перцентили-вердикты) — ноль; единственное дисперсионное сравнение — test_pattern_detector | VERIFIED (MISSING) | grep scipy/ks_2samp/chi2/mannwhitney/ttest/wilcoxon — ноль; `identity/test_pattern_detector.py:65–80` |
| 8.6 | Scale-инструмент жив (p50/p95-зоны), ~30 отчётов до 120 NPC × 10k тиков; гейты §9.8 SCALE-01…07 открыты; 100k-прогонов в артефактах нет | VERIFIED | `probes/scale_instrument.py:26–29, 191–245`, `probes/scale_reports/` |
| 8.7 | Воспроизводимость: без глобального seed по дизайну (ADR-O-301); изоляция + KernelRNG + двойные прогоны; seed=42 харнесса декоративен | VERIFIED | `kernel_rng.py:27–87`, `experiment_runner.py:10–11, 308–357`, `harness.py:97–98` |
| 8.8 | Существующие владельцы | — | §8.Q1–Q7, §9.8, P12/P13, MEM-10 SCALE-MEM, §9.13 Vision suite |

**Зазор (→ §9.14 PROPOSED):** контракт статистического ассерта (8 обязательных полей) как расширение §9; запрет произвольных диапазонов без экспериментальной базы; четкое разделение двух детерминизмов (фикс-seed повтор ≠ меж-seed устойчивость).

### 2.9/2.10 — Authoring Compiler Pipeline и Cognitive Tick Throttling повторно (Часть IV задания) = 2.4 и 2.5 соответственно; самостоятельных дополнительных зазоров не обнаружено.

---

## 3. Существующие механизмы, закрывающие часть требований

| Требование задания | Уже закрыто (владелец) |
|---|---|
| Диагностический контур, не влияющий на симуляцию | ObservabilityTap / CausalObserver / scene_changes.jsonl / diagnostics.yaml FORBIDDEN-loop (§0.3 «Observability never mutates», INV-в IPT) |
| Машиночитаемая цепочка как тестовый оракул | §9.8b (event → … → world change) |
| Read-only аудит причинной цепочки | AUDIT-10H-0/1/2 (§7.6) |
| След решения (механизм) | MOT-трек §18 (MOT-0…8, MOT-L1…L9, гейты GC-50…57) |
| Жизненный цикл памяти | MEM-трек §16 (MEM-0…10, MEM-D1…D41, four-states, запрет авторезолюции) |
| Stop-rule против преждевременного Active Inference | §3.5 STOP + §0.3 «Отложено намеренно» |
| Двухскоростной закон / отказ LLM = пауза | ADR-O-377 + IntelligenceQueue (D8P) + доктрина D61 (d61-тест 32/0) |
| Детерминизм тика | DET-1/2/3 (§17.8), INV-KERNEL-RNG/WALL-CLOCK/REPLAY-DETERMINISM |
| Устойчивость намерений (механизмы) | гистерезис DecisionHub; CommitmentRegistry/Arbiter (S203.4); interrupt_traversal причины-реестр; ActionWindup |
| Авторинг: LLM не валидатор и не писатель | INV-LLM-NOT-SSOT; «Save = Contract» 422; нормализатор fail-loud; провенанс LLM_DRAFT/AUTHOR_* |
| Хронологическая согласованность (механизм построен) | CCH-2.5 ConsistencyService (вне гейта — зазор 2.4) |
| Возраст/две оси времени | age_math + birth_epoch/age_at_game_start + KnowledgeLink learned≥historical |
| Масштаб/длительность (инструмент) | DriftLab 9 режимов; scale_instrument; F5-лаборатория; SUPERBOX |
| Приоритет поставки контента сеялке | COV-10/S5; CCH-6 калибровка; самоочистка ТЗ |

---

## 4. Точные изменения дорожной карты (файл, раздел, характер изменения)

Файл: `docs/ENIGMA_ROADMAP_v4_11_WPS.md` (все правки помечены «дополнение аудита 2026-10-23»; PROPOSED до вердикта Мастера; версия документа и существующие статусы не менялись; очередь §0.2 не расширялась).

| № | Раздел | Характер |
|---|---|---|
| 1 | §3.5b (новая) | PROPOSED-контракт «Active Inference ↔ Utility»: что исполняется (utility-редьюсер, KernelRNG, гистерезис), что спит (ExpectationStore/expected_success/pe_modifiers_map), что концептуально (AI); рабочий вариант A (utility остаётся; AI — рамка + аффективный prediction error), путь B через BC-2/BC-3+MEM-8, вариант C — только по сравнительным экспериментам; риски неоднозначности; критерий приёмки |
| 2 | §9.14 (новая) | PROPOSED-контракт статистического слоя доказательства: двухслойная доктрина, 8 полей статистического ассерта, запрет диапазонов без экспериментальной базы, разделение двух детерминизмов, привязка к Q3/Q6/P12/P13/§9.8 |
| 3 | §13.7 (новая) | PROPOSED: свидетельство по CCH-4 (сеялка существует, ADR-O-423; Debugger нет — вердикт о частичном закрытии за Мастером); ship-blocker guard_borko (SeederError) и канон-долг blacksmith_orm; CCH-7 Semantic Validation Gate (ConsistencyService в гейт canonize + резолюция референсов + отчёт компиляции; CLI-первая версия) |
| 4 | §14.6 (новая) | PROPOSED: Identity Drift Guardrails — 4-классная таксономия расхождений, фоновый аудит, критерий «классифицировано или UNCLASSIFIED», переиспользование ECR/PU/MOT-9/MEM-5 |
| 5 | §16.10 (новая) | PROPOSED: критерии приёмки Memory Lifecycle (запрет молчаливого удаления, необъяснимость, консолидация ≠ факт, референсная целостность) + новые находки MEM-D42 (тихие пути удаления без учёта) и MEM-D43 (dangling evidence/contract_ref); привязка к MEM-0/2/5/10 |
| 6 | §17.8 Шаг 7 (новый пункт) | PROPOSED: критерии приёмки устойчивости намерений для rollout-пакета 4 (арбитраж) |
| 7 | §18.10 (новая) | PROPOSED: MOT-D12 (разрыв позвоночника происхождения) + MOT-9 (контракт постоянного происхождения = runtime-форма цепочки §9.8b; зависимость AUDIT-10H + MOT-0…3; гейт GC-59) + ре-верификация якорей §18.2 на V.0.5.4.4.0 |
| 8 | §9.3h | Регистрация GC-59 (гейт MOT-9) |
| 9 | §23 (новый раздел) | PROPOSED-контур CGB «Cognitive Compute Budget»: классы работ, карта существующих регуляторов, инварианты, пакеты-кандидаты CGB-0…3, гейты CGB-GC-01…04, запрет числовых бюджетов до профилирования; в §0.2 не входит |
| 10 | §8.AF (новая) | Указатель MASTER TODO на §23 (аналог AD/AE; поглощения: P14/Q3/Q6 остаются владельцами) |
| 11 | §0.1 | Строка карты треков CGB (PROPOSED, до вердикта) |
| 12 | §R.7 | Владение §23: read-only обеим ветвям до вердикта; после — Б (тик-ядро §R.2) |
| 13 | «Как читать» п.16 + §1.1 | Навигация на §23 и настоящий аудит-документ |
| 14 | Хвост документа | Абзац «Дополнение аудита 2026-10-23» — перечень интегрированного, по прецеденту v4.8/v4.10/v4.11 |

Новый файл: `docs/audits/ROADMAP-AUDIT-01_Cognitive_Infrastructure_and_Observability.md` (настоящий документ).

---

## 5. Новые зависимости и критерии приёмки (сводно)

| Предложение | Зависимости | Критерий приёмки (проверяемый результат) |
|---|---|---|
| MOT-9 (происхождение) | AUDIT-10H-1 (что рвётся); MOT-0…MOT-3 (онтология и DecisionTrace); MEM-1 (event_id на memory-пути — общий носитель); COV-D71 (экспорт) | GC-59: по любому убеждению/решению NPC на сотнях тиков запрос восстанавливает цепочку до мирового факта по живым id (не логам); глубина истории > 20; экспорт машинно-читаем; Observability-нуль-мутация подтверждена диф-тестом |
| §16.10 (память) | MEM-0 (ADR-носитель запретов); MEM-2 (seq_0/decay/рестарт); MEM-5 (четыре состояния); MEM-10 (компакция/replay) | (1) каждый путь удаления либо сохраняет объяснимость зависимых убеждений/решений/обязательств, либо блокирован при живых ссылках (тест на каждый путь); (2) удаление WM-записи не удаляет исторический факт (LTM-инвариант + запрет воскресения); (3) абстракция наследует provenance и не становится «фактом мира» (тест); (4) dangling evidence/contract_ref невозможны или явно типизированы (тест) |
| §3.5b (AI↔U) | BC-2/BC-3 (путь B); MEM-8 (ожидания); MATH-6 (аффективный PE) | Разработчик по одному чтению контракта называет: какая модель принимает решение, какие данные читает, где проверяется; альтернативные модели сравнимы по детерминированному протоколу (F5 A/B, SUPERBOX-диф) без смены онтологии |
| §13.7 (CCH-7) | CCH-2.5 (ConsistencyService построен); CCH-4 сеялка (существует); UX-4 | Канонизация запускает семантическую валидацию (хронология/референсы/противоречия) и возвращает отчёт с точными позициями ошибок; каноны без game_start_age не проходят молча; компиляция воспроизводима (replay-cache); CLI-прогон = тот же гейт, что UI |
| §14.6 (дрейф) | CCH-02-3 (ECR); MOT-9 (происхождение); MEM-5 (four-states); NL-11/NL-12 (границы лжи/заблуждения) | Каждое обнаруженное расхождение «канон ↔ состояние» классифицировано в один из 4 классов или явно UNCLASSIFIED; класс ≠ ошибка (забывание/ложь/развитие — валидные); дрейф-аудит не пишет в игровое состояние (INV-DIAG-NOT-GAMESTATE) |
| §17.8 Шаг 7 (устойчивость намерений) | rollout-пакет 4 (ARBITER_ENFORCEMENT + S203_4_*); MOT-5 (смесь) | (1) неизменные входы → нет бесконечных переключений (стресс-тест); (2) каждое прерывание ссылается на конкретное событие/причину из реестра причин; (3) сроки повторной оценки определены; (4) детерминированный повтор сценария воспроизводит порядок решений; (5) удержание не блокирует адаптацию к реальному изменению мира |
| §23 CGB | P14 (профилирование — владелец чисел); §9.8 SCALE; COV-D64/D71 (измерение); LC-IMPL-5/MEM-D14 (offscreen-следы); DET-1…3 | CGB-GC-01 карта классов работ/владельцев; CGB-GC-02 инварианты в IPT; CGB-GC-03 per-phase стоимость измерима; CGB-GC-04 вердикт offscreen-семантики с диф-тестом «возврат в активную зону без необъяснимого скачка». Числовые бюджеты — только после профилирования целевого оборудования (P14) |
| §9.14 (статистика) | §9.8; DriftLab/SUPERBOX (инфраструктура есть); P12/P13; калибровочная лаборатория | Каждый статистический ассерт имеет 8 полей контракта; ни один диапазон не назначен без прогонов на базовом корпусе; SUPERBOX/IPT сохраняют точные гарантии; отчёт хранится и сравним с базовой линией |

---

## 6. Приоритеты и обоснование

**P0 (блокирует достоверность состояния — чинить в существующих пакетах, не новыми треками):**
- seq_0-деструкция + неперсистентность абстракций (MEM-2, уже запланировано; аудит добавляет точные якоря и требование «теста деструкции на прод-пути» — текущие тесты маскируют дефект уникальными sequence_id).
- Ship-blocker authoring: guard_borko SeederError / game_start_age=null в shipped-канонах (§13.7; чинится содержимым канона + вердиктом по поведению сеялки — код писать не обязательно).
- Decay game_days=1.0 — ускорение календаря ×2.4 (MEM-2, MEM-D2; уже в плане).

**P1 (контракты, необходимые до расширения зависимых систем):**
- MOT-9/MOT-D12 (происхождение) — потому что Memory GC, Identity Drift, Intent-прерывания и NL-объяснения все опираются на восстанавливаемую цепочку; закрывает пятый вопрос критерия завершения («какие вычисления можно отложить») общей онтологией.
- §17.8 Шаг 7 (критерии устойчивости намерений) — ДО включения rollout-пакета 4: включение enforcement без ассертов породит поведение без доказанных гарантий.
- §3.5b (AI↔U контракт) — дешёвая фиксация статуса до BC-2/BC-3; предотвращает повторный спор «что у нас decision-модель».
- §16.10 (запреты памяти) — интегрируется в MEM-0 ADR, который ещё не утверждён.

**P2 (параллельно, не блокируют):**
- §23 CGB (контур, вердикт offscreen-семантики может подождать LC-IMPL-5 — но не экономики: экономика умножит число обязательных причинных событий, и без контракта классов работ бюджетирование станет ретроактивным).
- §9.14 (статистический слой) — ценен после стабилизации базового контура; до него P12/P13 остаются владельцами горизонтов.
- §13.7 CCH-7 / §14.6 — после MOT-0…3 и CCH-02-3 соответственно.

Обоснование неповышения: ни один P2-пункт не нарушает сегодня фундаментальный инвариант — они либо диагностические, либо оптимизационные; «механизм выглядит полезным» — недостаточное основание для P0/P1 (§12 правил задания).

---

## 7. Что обязательно закрыть до экономики и общества

1. **seq_0/персистентность консолидации (MEM-2)** — экономика порождает обязательства/транзакции-воспоминания; деструкция кэша каждые 10 тиков сделает финансовую память NPC необъяснимой.
2. **MOT-9 / позвоночник происхождения (после AUDIT-10H)** — споры «почему NPC считает, что должен продавцу» без происхождения неразрешимы; экономика — первый массовый производитель убеждений-обязательств (contract_ref уже намечен и помечен DEBT CG-D-11/12).
3. **§16.10 запрет молчаливого удаления** — обязательства (commitments) переживут память о них без инварианта; это прямо ломает общество обещаний.
4. **§17.8 Шаг 7 + rollout-пакет 4** — общественные взаимодействия требуют устойчивых намерений (обещание, которое флаттерает каждый тик, не является обязательством).
5. **§3.5b контракт** — экономические решения (цена/обмен/работа) будут строить модификаторы поверх Modifier Contract; фиксация семантики до этого — дешёвая страховка.
6. **COV-3 (экономический контур — уже в очереди)** и ** ConsumptionResolver** — вне настоящего аудита, но его критерий (голод снимается едой) — предварительное условие любого общества.

## 8. Что можно формализовать сейчас / реализовать позднее, отложить или выполнять параллельно

- **Формализовать сейчас (дёшево, реализация позже):** §3.5b (текст контракта), §16.10 (запреты в MEM-0 ADR), §14.6 (таксономия), §9.14 (шаблон ассерта), §23.2 (инварианты текстом).
- **Реализовать по расписанию существующих треков:** MOT-9 (после MOT-0…3), CCH-7 (после CCH-4/CCH-6), CGB-0…3 (после AUDIT-10H и первого P14-профилирования).
- **Параллельно без ущерба:** §9.14 (тестовый контур), CGB-2 (измерение стоимости — чистая телеметрия), дрейф-аудит (тестовый контур).
- **Отложить:** интерактивный визуальный граф-инспектор (третий этап §3; UI после стабилизации контрактов — принцип соло-разработки); статистические пороги/диапазоны (до накопления прогонов); числовые бюджеты (до профилирования); UI-редактор поверх CLI-валидации.
- **Уже покрыто существующими механизмами (не дублировать):** stop-rule AI (§3.5), four-states памяти (§16.1), флаг-дисциплина (COV-0), «Observability never mutates» (§0.3), reason-реестр прерываний (S203.3), аудит цепочки (AUDIT-10H).
- **Не оправданы доказательствами (не предлагать):** отдельный Commitment Arbiter поверх существующего S203.4-контура (не поглощён — уже построен); второй источник истины для диагностики; универсальная memory-архивация ради GC (L1-архив уже жив; event_memories архивируются только по вердикту MEM-10); отдельный «Identity Engine» (закрывается CCH-02+MOT-9+MEM-5 переиспользованием).

---

## 9. Неустранённые неопределённости и недостающие доказательства

1. **Частота live-fire seq_0-вбивания не измерена** (структурно гарантирована при срабатывании компрессии; но доля тиков с ≥3 одно-тэговыми записями importance<0.6 — нет данных; компрессия не эмитит метрику). Закрывается тестом деструкции на прод-пути (MEM-2) — не в этом аудите.
2. **§18.2-якоря MOT верифицировались на V.0.5.4.3.3**; на V.0.5.4.4.0 подтверждено: срезы вынесены в `causal_slice_*.py` (вызов остаётся инлайн на тех же якорях :602–851), allies=0 на :654/:765 — на месте, fail-silent — на месте (уже с logger.warning), DesiredChange→modifiers жив (что согласуется с §18.0). Полная ре-верификация — первый пункт MOT-0 (как и записано).
3. **Поведение D8P STALE-гейта при латентности LLM > 3 тиков** (drain rate) не измерено — влияет на оценку стоимости асинхронной когниции в CGB.
4. **Содержимое runtime-артефактов** (`scene_changes.jsonl`, `replay.db` 754 МБ — §7.5) не анализировалось: файлов нет в чек-ауте; проверены писатели, не содержимое.
5. **Replay-глубина**: существует ли живой прогон 100k тиков (long_horizon) — в reports/ артефактов нет; заявленный профиль P13 не доказан прогоном.
6. **Seed-политика**: расхождение 44444 (код) vs 54321 (исторический отчёт) требует git-археологии; контракт RCOC (Mode F) — заглушка.
7. **Полный список потребителей `npc["desires"]`** — grep-уровень; исчерпывающий вызывной анализ не проводился (не влияло на вердикты).
8. **Экономическая матрица (COV-3 D1–D10)** принята по roadmap без повторного код-аудита (вне скоупа задания).
9. **Дублирование `produce_cognition_modifiers` в `npc_tick_pipeline.py:903–931`** (идентичный блок дважды, второй затирает первый) — найдено агентом, вручную не перепроверено построчно; кандидат в §7-хвосты после подтверждения владельцем ветви А.

---

## 10. Ответы на пять вопросов критерия завершения (текущее состояние → чем закрывается)

1. **Почему NPC пришёл к убеждению и какое событие его вызвало?** Сегодня: частично (ConclusionRecord.evidence — спит; BeliefState/CrystallizedBelief — без ссылок; debug-леджер — 20 записей, cause=None). Закрывается: MOT-9 (+MEM-1/MEM-3 evidence-поле), поверх AUDIT-10H-1.
2. **Почему воспоминание сохраняется/обобщается/удаляется?** Сегодня: правила есть, но не полны и местами деструктивны (§2.2). Закрывается: MEM-0/2/5/10 + §16.10 критерии.
3. **Какая исполняемая модель определяет выбор действия?** Сегодня: utility-редьюсер с гистерезисом и KernelRNG (формула в коде, контракт — нет). Закрывается: §3.5b.
4. **Как биография превращается в валидированное начальное состояние?** Сегодня: конвейер жив до структурной валидации + сеялка существует; семантика вне гейта; shipped-каноны содержат блокеры. Закрывается: §13.7 (CCH-7 + вердикты по канонам).
5. **Какие вычисления можно отложить/удешевить без нарушения причинной целостности?** Сегодня: регуляторы есть (LOD/tiers/caps/STALE), классы работ и инварианты не формализованы, offscreen-семантика не решена. Закрывается: §23 CGB (после AUDIT-10H и P14-профилирования).

---

*Аудит исполнен read-only; единственные записи — настоящий файл и интегрированные PROPOSED-дополнения в `ENIGMA_ROADMAP_v4_11_WPS.md`. Код, тесты, флаги и статусы не менялись. Точка версии roadmap не поднималась (§R.6.6 — компетенция Мастера).*
