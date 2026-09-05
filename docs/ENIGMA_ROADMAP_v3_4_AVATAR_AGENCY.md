# ENIGMA --- Дорожная карта преемника

**Версия документа:** 3.6 · 2026-09-05 (+AG1: E2.0-c/B0 CLOSED — S243, четыре группы GREEN, PK/beliefs-guard, клетки §5b GC-04/GC-06/DIFF-01; +W-синхронизация §0/§3/§5-F/Долг/5d: W1✅ W2✅ W3✅ G1✅ G2✅ — S239/ADR-O-378; следующий гейт W-трека — G3 Execution; W-долги зарегистрированы) **Адресат:** LLM-преемник на V.0.5.3.9.6 (ветка
`V.0.5.3.9.6_Память_3`) **Назначение:** Пошаговый план --- что делать, в
каком порядке, что читать, что формулировать самому. **Принцип
документа:** компактный, без воды; галочки `[ ]` --- для трекинга; путь
к файлу --- для каждого шага. **Актуализация:** 2026-09-04 +
HUMOR/PLAY + внешний аудит 2026-09-04 (§4c: AUD-D1...D12). Основа ---
V.0.5.3.9.5 + **сессия AG1 (Фаза A + EMRL E1/E2.0)**: закрыт фундамент
памяти (аудит V.0.5.3.9.3: 9 P0 + 5 живых детонаций тика), построена
шина опыта E1 и каузальный шлюз E2.0 (DeltaGate). См. новый §2a.

------------------------------------------------------------------------

## 0. Контекст: где мы сейчас

**Версия кода:** V.0.5.3.9.7 · `version.txt` = `0.5.3.9.7` ·
синхронизирован с `pyproject.toml` (desync v0.5.3.7.0-era **закрыт**).

**Главные активные треки (на смену defect-fix ТЗ V0.5.3.7.0, которое
утрачено):**

1.  **ТЗ-RE-01 --- Relationship Engine v2**
    (`docs/Почти Актуальные TZ/ТЗ_RE-01_Relationship_Engine_v1.9.md` +
    акт передачи `ТЗ_RE-01_ПЕРЕДАЧА_преемнику_Р18.md`). Прогресс: **M0
    ✅ (ADR-O-369)** → **M1a ✅ (ADR-O-370)** → **M1b --- в процессе
    (ADR-O-371-серия коммитов, RelationshipWriteGate)** → далее M1b.5 /
    M2-D / G / H / K / полигон M.

2.  **W-TRACK --- World Embodiment Foundation**
    (`docs/Почти Актуальные TZ/TZ_WORLD_EMBODIMENT FOUNDATION (W-TRACK).md`).
    Прогресс (актуализировано S239): **W1 ✅** (ADR-O-371: субстрат,
    30 тестов) → **W2 ✅** (S232/ADR-O-372: AffordanceResolver, 24
    теста, закрытый реестр 7 предикатов) → **W3 ✅** (S237/ADR-O-376:
    FSM transition_object/damage_object + production-спавнер live=18 +
    Gate-1 discovery-shadow GREEN) → **G2 ✅** (S239/ADR-O-378:
    producer-facts weapon_access --- ПЕРВЫЙ живой runtime-мост
    W2→решение через OpportunityContext; W3_G2_ENABLED default OFF;
    GORAN β GREEN). Рантайм-потребителей: 1 (G2). Остался **G3
    (Execution)**: commitment → ревалидация precondition-кортежей →
    transition → атомарная мутация → MutationRecord/Fact (контракт в
    ADR-O-376/378). DEBT-W-AUDIT закрыт (S240):
    `docs/AUDIT_W_TRACK_COUPLINGS.md` (ownership/coupling-граф +
    входной ограничитель G3; главный риск-узел B1.4, релеи R1--R6). W4 deferred
    (Two-Domain не доказан); W5--W9 --- контракты + PoC.

3.  **Р18 «Адаптация»** (раунд ТЗ-RE-01) --- ОТКРЫТ; режим работы и
    развилки --- в акте передачи (см. §2).

4.  **HUMOR / PLAY / SOCIAL INCONGRUITY** --- новый
    когнитивно-социальный трек. Юмор не является отдельной эмоцией,
    фиксированным `humor_level` или генератором шуток: он выводится из
    expectation/prediction error + incongruity + resolution +
    benignity/social context, а способность шутить меняется во времени
    через personality, experience, current state и relationships.

5.  **Behavioral Closure / Social Cognition** --- **фундамент построен
    сессией AG1** (см. §2a): Фаза A закрыла P0-дефекты памяти аудита
    V.0.5.3.9.3, EMRL E1 (шина опыта) и E2.0-a/b (DeltaGate:
    единственный вход «интерпретация → состояние», живой провод
    THREATEN→ПК, EXPERIENCE_DELTA_COMMITTED для Chronicaler) --- 40
    замков `backend/tests/test_phase_a_memory_fixes.py`, IPT 45/45.
    Осталось: E2.0-c ✅ (S243, B0-CLOSED: causal proof) → BC-1 ✅ (S247:
    ADR-O-381, dormant ON, приёмка 6/6 GREEN — выводы-триплеты рождаются
    из EXPERIENCE_DELTA, NO-VACUUM зелёный) → BC-2..BC-12 (BC-2
    Conclusion→Expectation — следующий). Не
    вводить флаги «месть/обида/влюблённость» как сущности; выводы должны
    быть derived из общих механизмов.

**Эпоха:** переходная между **Эпохой 6 (Stabilization)** и Эпохой 7.
Фактическая текущая точка: **RE-01 M1b.4 (физический cutover) +
M1b.3.1/3.2 закрыты --- V2 RAM-authoritative runtime ЖИВ
(writers+readers+bootstrap, 202 теста, зонд 21/22); открыты M1b.3.3--3.7
(decay/гидратация/flat-readers/S128/страж) и M1b.5/M2-D; W-субстрат
существует, но runtime-consumer слой dormant; predictive/social
cognition ещё не замкнут.**
`docs/Почти Актуальные TZ/STABILIZATION_ROADMAP.md`: **стабилизация
v0.5.3.7.2--v0.5.3.7.10 завершена** --- ядро (Tick, Movement, Decision,
LLM) стабильно, **IPT 45/45 (было 39/0)**, `lint_silent_failures` ✅,
`lint_relationship_engine` ✅. Остаток долга --- god-файлы, mypy
--strict (79 → 0 в spatial-слоях), print() в backend (36 → 0),
TODO/FIXME.

### Горячие runtime-проблемы (из `reports/LAST_SESSION.md`, 28.08.2026)

  ------------------------------------------------------------------------------------------------------------------
  \#   Проблема         Статус                             Куда смотреть
  ---- ---------------- ---------------------------------- ---------------------------------------------------------
  1    **Симуляция      ✅ **Разморожена** (Фаза 0.1) ---  `backend/app/services/npc/decision_hub.py`
       заморожена: все  DecisionHub жив, 6/6 NPC выдают    
       30 тиков → 0     решения в smoke-прогоне. Артефакт  
       decisions**      «0 decisions/tick» --- следствие   
       (BREAK-1)        player-turn-only пути. Полное      
                        подтверждение --- живая сессия.    

  2    LLM-сервер       ✅ **Исправлено** (Фаза 0.2) ---   `scripts/llm_server_manager.py`, `backend/logs/`
       недоступен при   `scripts/llm_server_manager.py`,   
       старте backend   LOG-GATE-UI на splash показывает   
                        статус. `startup_timing.log`:      
                        `backend_ok=True, llm_ok=True`.    

  3    21 traceback в   ✅ **Устранены 3 реальных бага**   `backend/app/services/events/social_subscriber.py`,
       сессии           (Фаза 0.3): (a)                    `backend/app/services/social/mvp_tavern_controller.py`,
                        `social_subscriber.py` ---         `backend/app/services/npc/domain_phases.py`
                        `RelationshipWriteGate(None)`      
                        тормозил тик; (b)                  
                        `mvp_tavern_controller.py` ---     
                        DEATH по hp\<=0 вместо VitalState  
                        verdict; (c) `domain_phases.py`    
                        --- eco-стресс не доходил через    
                        StateApplicator.                   

  4    NPI 86%          ✅ **Исправлено** (Фаза 0.4) ---   movement-пайплайн, `backend/app/services/spatial/`
                        6/6 NPC теперь имеют координаты в  
                        smoke. `local_traversal_planner` + 
                        `traversability_evaluator`         
                        работают. player без координат --- 
                        требует живой сессии (0.5).        

  5    Traversal ⏸ у    ✅ **Разморожен** (Фаза 0.4) ---   `local_traversal_planner.py`,
       `guard_borko` /  smoke даёт 6/6 `VALID_PATH`. ⏸ в   `traversability_evaluator.py`
       `thief_shadow`   сессии --- артефакт arbiter        
                        INCUMBENT-отклонения.              

  6    NEI=0 --- NPC    ⚠️ **Частично** (Фаза 0.6) --- p   hysiology/needs-контур
       слишком          eco-стресс теперь доходит до       
       комфортны        StateApplicator. Needs-writer      
                        runtime --- в M2/D, не             
                        форсировать.                       
  ------------------------------------------------------------------------------------------------------------------

DNA в целом: SHI=100%, SCF=1.0, DRI=100%, DPI=100%, BCI формируется.
История --- `reports/dna_history.jsonl`.

### 5 архитектурных истин (усвоить перед любым шагом)

1.  **Truth = Snapshot + Chronicle.** State эфемерен, Identity ---
    append-only. Асимметричная онтология, не баг.
2.  **Time & Physics --- одно.** Разрешаются только в Causal Kernel.
3.  **No Event Sourcing for State, но yes for Identity.** State ---
    snapshot, Identity --- L1Chronicle (SQLite append-only).
4.  **Symptom ≠ Cause.** Чини pipeline node, не UI.
5.  **Vacuum = local rupture, not global zero.** Unknown ≠ Neutral 0.0.

**Новая, Эпоха RE-01 (добавить к истинам):** **«Паттерн, не
субстанция»** (принцип Р17-П1) --- человеческие категории
(«идеализация», «влюблённость», «адаптация») не вводятся как
состояния-сущности; каждая проходит **anti-Bond тест**: доказывается
каузальная работа, которую никто другой в ENIGMA не выполняет, иначе ---
derived-операция.

### Принципы работы

-   Один фикс → один коммит → один тест. Не пачками.
-   CI-гейты обязательны: `ruff` + `pytest backend/tests/IPT.py` (сейчас
    45/45) + профильные линтеры `scripts/lint_*.py`
    (relationship_engine, kernel_rng, l1_append_only,
    epistemic_boundary, spatial_ssot, frontend_isolation, wall_clock,
    silent_failures и др.).
-   Observability **never mutates**.
-   DNA-метрики могут врать --- перепроверяй через
    `backend/data/logs/scene_changes_*.jsonl`.
-   `MockProvider` в production-пути запрещён.
-   `random.*` и `time.time()` в kernel-слое запрещены → только
    `KernelRNG(tick, npc_id, salt)`.
-   Файловые runtime-логи гейтятся `ENIGMA_DISABLE_FILE_LOGS`
    (LOG-GATE); git-хуки гоняют тесты без записи в `data/logs`.
-   Режим RE-01: **GPT задаёт направление, преемник вскрывает факты до
    решений и спрашивает по каждой развилке.**

------------------------------------------------------------------------

## 1. Документы: что существует, что утрачено (проверено Test-Path 2026-08-30)

### ✅ Существуют и актуальны

  ----------------------------------------------------------------------------------------------------------------------------------
  Документ                                                                             Роль
  ------------------------------------------------------------------------------------ ---------------------------------------------
  `docs/Почти Актуальные TZ/ТЗ_RE-01_Relationship_Engine_v1.9.md` (1972 строки, аудит  Канонический ТЗ Relationship Engine v2:
  40/40)                                                                               аксиомы §3, запреты §7, устав §12.2

  `docs/Почти Актуальные TZ/ТЗ_RE-01_ПЕРЕДАЧА_преемнику_Р18.md`                        Передаточный акт: режим работы, роадмап
                                                                                       (а)→(г), развилки Р1--Р7

  `docs/Почти Актуальные TZ/TZ_WORLD_EMBODIMENT FOUNDATION (W-TRACK).md`               Часть II Stage 2.5: 4-хуровневая архитектура
                                                                                       WORLD→EMBODIED→PRESENTATION→RENDERING, этапы
                                                                                       W0--W9

  `docs/Почти Актуальные TZ/STABILIZATION_ROADMAP.md`                                  Вердикт по стабилизации: закрыта; остаток
                                                                                       долга --- god-файлы, mypy, print(), TODO

  `docs/ENIGMA_EPOCHS_REPORT.md`                                                       Карта Эпох 1--10 (источник истины по
                                                                                       прогрессу; сама отстаёт --- на момент
                                                                                       v0.5.3.7.8)

  `docs/Почти Актуальные TZ/RemontTZ/*.md` (6 файлов)                                  Мастер-ТЗ на ремонт доменов
                                                                                       (CORE/SPATIAL/DIALOGUE/PERCEPTION/FRONTEND)
                                                                                       --- историческое, большинство фиксов уже
                                                                                       применено

  `docs/Почти Актуальные TZ/VZ/*.md` (7 файлов: §18, §19, MEMETIC 01--03, TZ-02,       Будущие эпохи (7--10)
  TEXTURES)                                                                            

  `docs/Почти Актуальные TZ/TZ_Stage_2_5_Temporal_Causality_Predictive_Runtime_1.md`   Temporal causality / predictive runtime
                                                                                       (Часть I; W-TRACK --- его Часть II)

  `docs/Почти Актуальные TZ/1_TZ_Architect_Enigma_V0_5_3_8_2.md` (+ Parts 2--4,        Архитектурные ТЗ волны 0.5.3.8.x
  `1_TZ_Стадия_2.md`)                                                                  

  `docs/Почти Актуальные TZ/PSY-ARCH-01_Unified_Psychological_Dynamics.md`,            Психологическая динамика и калибровочная
  `TZ_Laboratoria_Kalibrovki_ENIGMA.md`, `Plan_Razrabotki_Laboratorii.md`              лаборатория (M0-полигон ADR-O-367 жив)

  `docs/Почти Актуальные TZ/ENIGMA_LLM_PIPELINE_TZ_v1.md`,                             Периферийные ТЗ (по мере надобности)
  `ENIGMA_MAP_EDITOR_SMART_VALIDATION.md`,                                             
  `ENIGMA_TZ2_v2_Narrative_Frame_Onboarding.md`,                                       
  `ТЗ ENIGMA WORLD-CENTRIC SPATIAL ARCHITECTURE.md`                                    

  `docs/audits/ADR-O-369/370/371_IMPACT.md` (+ атлас                                   Свежие ADR и единый атлас
  `docs/ADR (Architecture Decision Records).md`, 130+ файлов)                          

  `reports/SESSION_S62_DM_VISION.md`, `reports/LAST_SESSION.md`                        Сессии
  ----------------------------------------------------------------------------------------------------------------------------------

### ❌ Утрачены / не найдены (ссылки из v1.0 роадмапа более не валидны)

-   `upload/ENIGMA_TZ_V0.5.3.7.0.md` --- главный defect-fix ТЗ эпохи
    0.5.3.7.0. **Папки `upload/` нет.** Его defect-каталог фактически
    отработан STABILIZATION_ROADMAP --- не искать, не восстанавливать.
-   `docs/Почти Актуальные TZ/ENIGMA_TZ_INFRASTRUCTURE.md` --- нет в
    репо.
-   `docs/Почти Актуальные TZ/ENIGMA_SELF_HEALING_SYSTEM.md` --- нет в
    репо.
-   `S1_INPUT_TRACE_IMPLEMENTATION.md`,
    `INPUT_OBSERVATORY_ROADMAP_S2_S6.md` --- нет в репо.

------------------------------------------------------------------------

## 2. Активный трек №1 --- RE-01: Relationship Engine v2

### Прогресс по фазам (все гейты зелёные, runtime байтово идентичен)

-   [x] **M0 (ADR-O-369)** --- онтологический контракт:
    `architecture/relationship_engine.yaml` (45 узлов, 20 событий, 6
    предикатов, запреты №1--35) + `scripts/lint_relationship_engine.py`
    в CI/pre-commit. Рантайм не тронут.
-   [x] **M1a / Phase B (ADR-O-370)** --- субстрат:
    `RelationshipStateStore` (scene_state-backed, dormant), контракты
    NeedSlot/PreferenceModel/HardConstraint,
    `StateApplicator.update_needs` (single-writer, caller-guard). 28
    тестов.
-   [x] **M1b.0** --- `RelationshipWriteGate` (routing-слой, whitelist 5
    скаляров, NaN/foreign-key guard) + D3-паритет против legacy
    `update()`.
-   [x] **M1b.1** --- миграционный адаптер legacy→v2 (deterministic
    transform, идемпотентность, 9 приёмочных тестов).
-   [x] **M1b.2 (полностью, 2.0--2.7)** --- RelationshipWriteGate +
    D3-сетка 8×8×5; ВСЕ 6 write-маршрутов через гейт (social_subscriber,
    compiler, MemoryManager-фасад, StateApplicator, rules_subscriber,
    decay-архитектурно); semantic gate §8.6 (комплимент --- ОДНА
    направленная запись, кэш-хирургия attraction удалена); вечные
    греп-инварианты (ноль writer'ов вне гейта).
-   [x] **M1b.4 (физический cutover, RAM-GO)** ---
    `V2RelationshipBackend`: RAM = runtime authority (pre-scene writes
    --- паритет-контракт легаси, сторож IPT INV-TRUST-MONOTONICITY),
    сцена = persistence projection, disk-on-update запрещён,
    lazy/late-bind, hydrate, split-маркер `.migrated` только после
    atomic_commit_all, Фаза 10 multi-location sync, legacy JSON
    заморожен. Сьюта 194.
-   [x] **M1b.3.1** --- fallback DecisionHub УДАЛЁН (обе ветки; кэш =
    projection-only; Vacuum каноничен) + V2-`get` легаси-формат
    (стрелочные ключи --- ридер был слеп; сетка D3 не покрывала get) +
    миграция test_decision_calibration на compute-kwargs.
-   [x] **M1b.3.2 (вердикт β)** --- bootstrap отношений → RAM:
    `bootstrap_from_npc_dicts` (только 5 скаляров; base_values/nature
    --- decay-домен; existing-RAM-wins; «источник конфигурации читает
    один владелец») + npc_provider lazy-bootstrap (закрыл ВТОРОЙ
    прод-путь: idle/resume минует init_scene_state; зонд: 0 → 21/22
    ненулевых пар). Сьюта 202.
-   [x] **M1b.3.3+3.4** --- ЕДИНЫЙ РАЗРЕЗ закрыт: `build_npc_snapshots(+relationship_store, +campaign_id)` — кэш-слой снапшота = проекция V2 (decay/BehaviorMask на каноне; sticky закрыт и в phases/decision:202 безусловной гидратацией); handler decay не тронут (produce Δ). Сьюта 205, канар жив. Урок: юнит-зелёный ≠ интеграционная истина — гейт = живой зонд.
-   [ ] **M1b.3.5--3.7** --- flat-readers-зонд (интерпретация/risk/social_deltas: формат {target:{attr}} vs {attr}; S135-статик мёртв — RE-D8) → S128-разделение (вердикт (а)) → греб-страж allowlist (кэш-чтения только рендер-проекциям).
-   [ ] **GC-11 (L3-gate, обязателен для закрытия M2/D):** event →
    V2-RAM non-zero delta → следующий выбор/поведение NPC сдвинут
    (живой harness-прогон; ловит RE-D2-класс нулевой игровой
    реальности в runtime, недоказуемой юнит-сьютой).
-   [ ] **M1b.5** --- удалить мёртвый `apply_npc_state_updates` (0
    вызовов доказано грепом) + судьба legacy-класса/vestigial provider.
-   [ ] **M2/D** --- `RelationshipEventSemantics`: первый реальный
    писатель потребностей через `update_needs` + формат RE-событий в
    causal-машинерии.
-   [ ] **G/H** --- динамика Satisfaction и фрустрации через стор.
-   [ ] **K (фаза I артефакт)** --- полный removal-test.
-   [ ] **Полигон M** --- пресеты, INV-1, диф-тест раннего внимания
    **О-2** (единственный хвост Р17).

### Р18 «Адаптация» (открытый раунд)

Источники: акт передачи (§3) + ТЗ v1.9 §12.2. Правило раунда: **«Не
доказываем, что адаптация существует; доказываем или опровергаем, что
есть каузальная работа, которую никто другой не выполняет»**. Первое
действие --- досье адаптационного контура по цепочке
`writer → state → reader → causal effect → existing substitute → anti-Bond test → остаток`.
Развилки Р1--Р7 --- вопросом арбитру (GPT), не самостоятельными
решениями. Зоны вскрытия --- §6.3/§5.0/§5.1/§8.1/§6.19/§6.4 ТЗ v1.9.

------------------------------------------------------------------------

## 2a. Трек AG1 --- Фаза A / EMRL: шина опыта и каузальный шлюз (сессия 2026-09-02..03, ЗАКРЫТ частично)

**Судья трека:** мандат «EXPERIENCE → MEMORY → SELF → RELATIONSHIP LOOP»
(владелец). Ключевые законы сессии: (1) **LLM --- медленный консультант,
не SSOT**: между Interpretation и State нет прямого пути (DeltaGate);
(2) **две скорости**: быстрый мир (тики) никогда не ждёт медленного
интеллекта (LLM) --- ADR-O-377 (cockpit-форма жива, production-форма в
плане); (3) **AG1-INV-TRACE-ONCE**: один event.id → один causal trace →
≤1 принятой дельты поля; (4) «суть» эпизода = акт консолидации
(is_compressed), не зона важности; (5) припоминание растит доступность,
не истинность.

### Фаза A --- Фундамент памяти (ЗАКРЫТА ✅)

Закрытые P0 аудита V.0.5.3.9.3 (№1--9) + внеплановые живые детонации:
4.5 (дефолтный summary), 7.5 (ампутация легаси temporal-ветки →
TICK_CRASH 3/3→0), 9.5 (спикер речи в память), 9.6 (mem_id digest ---
конец каннибализации), 9.12 (мёртвый `_shared_context` в провайдерах ---
провод речь→память: 272 строки npc_spoke), 10.0 (L1-UNIQUE: guard под
констрейнт + OR IGNORE). Итог: все 10 фаз тика живы, речь NPC становится
памятью, персистентность сквозная.

### EMRL E1 --- Шина опыта (ЗАКРЫТА ✅)

  ----------------------------------------------------------------------------------------------------------------------
  Кольцо       Что                                                       Артефакты
  ------------ --------------------------------------------------------- -----------------------------------------------
  E1.0         ExperienceTrace + provenance (TESTIMONY ≠ копия) +        `backend/app/models/npc/experience_trace.py`,
               таблица                                                   `sqlite_store.save_trace/load_traces`

  E1.1         Decay-семантика: floor = is_compressed (суть бессмертна,  `working_memory.py` E1.1-floor
               шум умирает)                                              

  E1.2         MemoryCrystal (semantic, memory-домен) +                  `backend/app/models/npc/memory_crystal.py`,
               confidence/retrieval_strength разделены + домен-граница с `sqlite_store.save_crystal/load_crystals`
               CrystallizedBelief                                        

  E1.3         Provenance-контракт (внутри E1.0)                         TraceSource

  E1.4         Кокпит:                                                   `backend/tests/sandbox/terminal_cockpit.py`
               `new`/`mem`/`wait`/`restart`/адресация/класс-отцепление   
               экстрактора                                               

  E1.5         Диагностическая приёмка (живой прогон:                    ✅ руками владельца
               рассказ→память→рестарт→память)                            
  ----------------------------------------------------------------------------------------------------------------------

Формулировка честности (вердикт владельца): **доказано** --- NPC
сохраняет NPC-originated proposition; **не доказано** --- что оно
становится причинным внутренним состоянием. Первый кандидат-наблюдение:
«Надеюсь, они не придут сюда» (Горан, imp=0.26, пережил рестарт) ---
proposition, не состояние.

### EMRL E2.0 --- Каузальный шлюз (a/b закрыты, c --- следующий)

  ---------------------------------------------------------------------------------------
  Пакет            Что                                                   Статус
  ---------------- ----------------------------------------------------- ----------------
  E2.0-a           DeltaGate + StateDeltaProposal                        ✅
                   (whitelist/клампы/идемпотентность/INV-LLM-NOT-SSOT)   

  E2.0-b           Живой провод: Proposal в reaction_subscriber          ✅ 40/40
                   (S115-точка), Gate = аудит не писатель, belief ---    
                   тиковая ветка (causal_parent),                        
                   EXPERIENCE_DELTA_COMMITTED (EventDTO)                 

  E2.0-c           SUPERBOX causal_state_test: A/B/C/D, детерминистичный \[x\] ✅ CLOSED
                   инвариант (один snapshot+seed+event; единственная     (S243, B0-CLOSED
                   переменная --- авторизованная дельта; D = запись мимо владельцем):
                   гейта → ожидаем ArchitecturalViolationError)          4 группы GREEN
                   на GC-00-харнесе. Люся (флип-кейс): A argmax
                   call_for_help→flee (0.272→0.800), C = тот же
                   флип→flee 0.777 БЕЗ события/текста/LLLM (одна
                   дельта threat_gradient 0.8 через DeltaGate+Applicator);
                   A−C=0.023 = side-канал страха (атрибуция, не ошибка);
                   B: PK=0, дельт нет. Горан (companion): state→scores
                   доказан (flee +0.33 формульно), флип исключён
                   H1-ландшафтом (request_service 0.71 > flee-потолок).
                   D: D1/D2/D3 REJECTED (PK-guard + beliefs-guard
                   закрыли DEBT-R9/ADR-SSOT-EPISTEMIC). LIMITATION
                   (не критерий B0): флип уровня решения;
                   FLEE-материализация в 1-тиковом окне блокирована
                   арбитром (материал BC-12). Доказана каузальная
                   независимость механики от языковой экспрессии.
  ---------------------------------------------------------------------------------------

Терминологическая лестница (запрещено перепрыгивать): E2.0 = state-delta
integrity; E2.0-b = live propagation; **BC-1 = semantic leap**
(EXPERIENCE→CONCLUSION) --- только после зелёного E2.0-c. E2.0-c =
causal proof (B0-CLOSED, S243) → **BC-1 открыт** (тройплеты, не фразы;
первый потребитель — Expectation BC-2; DeltaGate-тропа обязательна для
conclusion_delta с provenance и causal parent).

------------------------------------------------------------------------

## 2b. Трек MATH-01: Математическая композиция и пластичность личности

**Основание:** Math_GAME.md v2 (полная рантайм-верификация формул) +
внешняя математическая рецензия. Не новый engine --- оформление и
точечные замыкания уже существующей математики.

-   [ ] **MATH-1** Центральная композиция
    $W_t \to O_i \to \varepsilon_i \to L_i \to \mathbf d_i \to E_i \to a_i \to W_{t+1}$
    формализована (Math_GAME.md §2a). Статья = «ENIGMA: Mathematical
    Architecture of a Subjective World», структура I--X по рецензии.
-   [ ] **MATH-2** Сон→восприятие:
    $R^{eff} = R \cdot v_{hearing}(\kappa)$,
    $P(\text{hear}) = \mathbf 1[d \le R^{eff}]$;
    $arousal \mathrel{+}= g(R^{eff})$. НЕ новый ADR --- исполнение
    ADR-O-356 Phase E.0 (закрывает П-4; сходимость двух независимых
    аудитов). Детерминизм сохраняется (масштабируем радиус, не
    вероятность).
-   [ ] **MATH-3** Эпистемическое остывание (П-2):
    $c(t) = c_0 e^{-\Delta t/\tau_e}$ --- уровень-II полураспад;
    координация с RE-01 M2/D. Появляется возраст информации.
-   [ ] **MATH-4** C-пластичность (уровень III) --- редкое
    evidence-gated событие: хронический `tifl_pressure_model`-поток (L1,
    D тиков, \|cum\|\>θ) → PatternDetector → CalibrationEngine
    $\Delta C$ ($C'=C'^T$). Гейты: §ENIGMA-002 (два домена, где
    L1-шрамов доказано недостаточно), ISK до/после (BRITTLE/CHAOTIC
    запрещён), anti-Bond (механизм, не сущность), mini-ADR обязателен,
    калибровка через Lab. ЗАПРЕТ: random C, частые ΔC, ΔC из одиночных
    событий. Обоснование: аттрактор текущей C ---
    $\mathbf d^* = (0, 4/23, 10/23, 9/23)$, fear=0 (Math §7.5);
    хронический страх через L1 работает, но топология «не умеет»
    хронически меняться.
    - [ ] MATH-5 Принцип детерминистической непредсказуемости:
    сценарий-тест «тот же ввод, другой день — другая реакция»
    через скрытые медленные переменные
    (pressure_accumulator / affective_memory / sleep_state /
    sleep_debt / recovery_history).

    Сон не является бинарным reset-механизмом fatigue. Его результат
    зависит от temporal continuity, interruption history и качества
    доступного восстановления.

    Один и тот же NPC при одинаковом внешнем input может демонстрировать
    различную реакцию не из-за random variation, а вследствие скрытого
    накопленного состояния организма и истории восстановления.

    Игрок видит следствия (хуже слышит, медленнее реагирует, перестал
    шутить, сорвался на обычную фразу, избегает сложного решения), не
    внутренние числа.

    Invariant:
    same seed + same world + same temporal/recovery history
        → same outcome

    same seed + same world + different recovery history
        → potentially different outcome
        → только через canonical state.
-   [ ] **MATH-6** Терминология AIF канонизирована (см. Math §18.4):
    «prediction-error-driven, inspired by Active Inference»; запрет
    «базируется на минимизации свободной энергии» до вариационного F.
-   [ ] **MATH-7** Позиция детерминированных мембран (путь A рецензии):
    threshold-модель = актив репродуцируемости
    (реплей/DriftLab/Calibration Lab). Soft-мембраны
    $\sigma(\alpha(R-d))$ --- осознанно отклонены.
-   [ ] **MATH-8** Боевые долги: П-9 (SOLID-чит; код сам помечен
    «Временно отключено»), П-11 (клиентский d20+damage →
    KernelRNG-сервер), П-13 (`randint(2,20)` --- фамбл недостижим),
    П-14, П-15 (hp-SSOT в API-пути).
-   [ ] **MATH-9** Аттрактор C --- численная верификация в Calibration
    Lab (юнит: итерация релаксации до сходимости → $\mathbf d^*$).
-   [ ] **MATH-10** Двухслойная семантика травмы в контент-дизайне: base
    расслабляется (\~109 тиков), effective --- навсегда (L1-шрам).
    Дизайнерские инструменты «навсегда» = шрамы/веры/отношения, не
    мгновенные стат-мутации.

## 3. Активный трек №2 --- W-TRACK: World Embodiment (Часть II Stage 2.5)

Главный инвариант: **Renderer не является источником истины о мире**;
новый NPC/шрам/предмет/renderer не требуют переписывания мозга NPC.

-   [x] **W-субстрат (ADR-O-371)** --- WORLD-домен:
    `architecture/world.yaml`, семантическая объектная топология,
    WorldObjectStore (персистенция внутри `scene_state`),
    `WorldSnapshot` +1 поле. 30 тестов
    (`backend/tests/test_world_object_topology.py`) +
    INV-WORLD-OBJECT-TOPOLOGY в IPT. Рантайм-потребителей: 0 (доктрина
    dormant-substrate).
-   [x] **W2** (S232/ADR-O-372) --- AffordanceResolver: pure
    `(WorldObject, BodyStateView, npc_position) → SemanticAction[]`,
    реестр 7 предикатов закрыт (расширение = мини-ADR), INSERT/REMOVE
    зарезервированы. 24 теста.
-   [x] **W3 домен/стор/спавнер** (S237/ADR-O-376) ---
    transition_object/damage_object (TransitionResult, не bool) +
    production-спавнер (SpawnMapping, wo_-identity,
    initialize_scene-only, live=18) + G1 shadow (GORAN β GREEN +
    ambient). Гейты исполнения: **G1 ✅ / G2 ✅ / G3 --- контракт, не
    реализовано**.
-   [x] **G2** (S239/ADR-O-378) --- producer-facts: первый живой мост
    W2→решение (weapon_access → OpportunityContext;
    DEBT-OPP-PRODUCER закрыт; DecisionHub object-agnostic, сигнатуры
    не менялись; W3_G2_ENABLED default OFF).
-   [ ] **G3 (Execution)** --- СЛЕДУЮЩИЙ ШАГ W-трека: executor
    объектных действий (commitment → ревалидация W2-кортежей →
    transition → мутация → Fact/L1Chronicle; тогда же Г4 caller-guard
    `_ALLOWED_WRITERS` --- writers сейчас 0). **G3-acceptance
    precondition (2026-09-05):** для исполнения GC-08 харнессу не хватает
    capability `spawn_world_object` (канон §5a.2; фактический API
    харнесса не имеет) — инфраструктурный prerequisite доказательства,
    не игровая задача; зависимость: W-G3 implementation → GC-08 scenario
    design → harness capability audit → spawn_world_object → GC-08
    executable → W-G3 eligible for closure. GC-02 не сливается с GC-08
    (player→world vs object→affordance→action — разные вопросы).
    transition → мутация → Fact/L1Chronicle; тогда же Г4 caller-guard
    `_ALLOWED_WRITERS` --- writers сейчас 0). Зона Фаз 6--7: git-археология
    + координация с параллельными сериями обязательны до PRE-FLIGHT.
-   [x] **DEBT-W-AUDIT** --- ЗАКРЫТ (S240): `docs/AUDIT_W_TRACK_COUPLINGS.md`
    (ownership/coupling-граф + входной ограничитель G3 §4; 0 Simulation
    coupling, 12 Acceptable adapter, V1--V4 «пустые» зонды верифицируют
    W0/W8). Главный риск-узел --- B1.4-канал (FE пушит полный scene_state
    → merge незащищённых ключей → atomic_commit; world_objects/
    relationship_state/commitments вне protected-листа) --- anti-writer
    G3; обязательные условия до G3-ON и cross-track релеи --- §4/§5
    аудита. G3 = первый runtime-writer (relations/transitions = 0
    callers; typed-op перехода в сторе нет --- мини-ADR).
-   [ ] **W4** --- Embodied State (поза, локомоция, хват, attachment);
    Two-Domain (§ENIGMA-002) не доказан --- точечно при реальных
    W2-потребностях (CAN_GRIP для TAKE-таблицы).
-   [ ] **W5--W9** --- Presentation Projector / интерфейсы renderers ---
    только контракты + PoC.

------------------------------------------------------------------------

## 4. Фазы и порядок работ (обновлённая последовательность)

### Фаза 0 --- Разморозка симуляции (немедленно, до любых feature-работ)

Статус 2026-08-30: сессия дезминтинга проведена; IPT 45/45, smoke β
(Goran) чистый. Детали фиксов --- в комментариях кода с меткой
`FIX (Phase-0 ...)`.

-   [x] **0.1** BREAK-1 частично снят: WorldTick-путь жив --- smoke даёт
    **6/6 NPC-решений** (\[DECISION_HUB\]
    guard_borko/merchant_goran/maid_lusya/blacksmith_orm/thief_shadow/tavern_keeper_tornin);
    «0 decisions» в DNA последней сессии --- артефакт player-turn пути и
    счётчика \[R3_DIRECT\] (диагностика
    `diagnostics/pattern_registry.py`). Требует подтверждения живой
    игровой сессией.
-   [x] **0.2** LLM-сервер при старте: подтверждён OK
    (`startup_timing.log`: `backend_ok=True, llm_ok=True`;
    `[STARTUP] LLM (сервер): доступен`). Фолс-тревога последней сессии.
-   [x] **0.3** Tracebacks устранены (3 фикса): (1)
    `social_subscriber.py` --- None-стор больше не оборачивается в
    RelationshipWriteGate (было `NoneType.update` каждый тик);
    S116-fallback понижен до debug; (2) `mvp_tavern_controller.py` ---
    DEATH триггерится только по `life_status==DEAD` (SSOT
    VitalStateEvaluator), hp\<=0 без DEAD → WARN вместо ValueError→DLQ
    каждый тик; (3) `domain_phases.py` --- eco-стресс проводится через
    `StateApplicator.apply_deltas_only` (было: guard ломал запись,
    стресс молча терялся --- вклад в NEI=0). `lint_silent_failures` ---
    ✅ 0.
-   \[\~\] **0.4** Traversal: в текущем билде smoke даёт 6/6
    `VALID_PATH / traversal=CREATED`; ⏸ у guard_borko/thief_shadow в
    последней сессии --- вероятно arbiter INCUMBENT-отклонения
    (commitment держит прежнюю цель). Подтвердить живой сессией.
-   [ ] **0.5** player без координат --- требует живой игровой сессии
    (не воспроизводится в smoke).
-   \[\~\] **0.6** NEI=0: eco-стресс дельт теперь доходит (фикс 0.3);
    полноценный рантайм-писатель потребностей --- только в M2/D (по
    плану RE-01, не форсировать).

### Фаза 1 --- Завершение RE-01 M1b→M2 (параллельно с Фазой 0 после разморозки)

-   [ ] M1b.5 (мёртвый код), затем M2/D, G/H --- по ТЗ v1.9; каждая фаза
    = контрактный гейт + линтер + IPT 45/45.

### Фаза 1.5 --- Поведенческое замыкание NPC (после M2/D, до тяжёлого Active Inference)

Цель: не новый набор эмоций, а единый контур социализации на уже
существующих Memory/Belief/Relationship/Decision механизмах.

-   [ ] **BC-1** Experience → Conclusion: значимый опыт должен порождать
    вывод о причине/агенте/паттерне, а не только память + scalar
    trust/fear.
-   [ ] **BC-2** Conclusion → Expectation: вывод должен менять прогноз
    следующего взаимодействия.
-   [ ] **BC-3** Expectation → Decision: существующий DecisionHub должен
    использовать ожидание без специальных action-флагов.
-   [ ] **BC-4** Repeated evidence → Generalization: повторяемость
    должна усиливать устойчивый вывод; contradictory evidence ---
    ослаблять/ревизовать его.
-   [ ] **BC-5** Personal experience → Social testimony: NPC должен
    уметь передавать не только факт, но и собственный вывод («я считаю
    его ненадёжным»).
-   [ ] **BC-6** Testimony → Recipient belief: получатель должен
    учитывать источник, уверенность, собственный опыт и конфликтующие
    свидетельства.
-   [ ] **BC-7** Conclusion → social strategy: допустимы
    derived-паттерны «избегать», «не сотрудничать», «не давать ресурс»,
    «предупреждать», но без флагов конкретных NPC.
-   [ ] **BC-8** Learning: успешный опыт должен уметь порождать
    знание/правило/навык, которое меняет будущую возможность или
    предпочтение действия.
-   [ ] **BC-9** Surprise → belief revision: неожиданное поведение
    другого должно ломать/уточнять ожидание и отношение.
-   [ ] **BC-10** Self-learning: опыт должен при необходимости менять не
    только модель другого, но и модель себя («я умею», «я ошибся», «я
    должен быть осторожнее»).
-   [ ] **BC-11** Social triangles: A→B→C должен порождать третичное
    изменение отношений без специального «треугольника отношений».
    - [ ] BC-12 Long-horizon proof:
    сценарии
    «оскорбление → вывод → память → избегание»,
    «обман → вывод → слух → осторожность»,
    «обучение → новое действие»,
    «помощь → благодарность → ответная помощь»
    проживаются 100–1000 тиков.

    - [ ] BC-13 Temporal consolidation boundary.

    Разделить:

        immediate causal update 
        ≠
        temporal consolidation.

    Значимый опыт может немедленно изменить canonical state через
    DeltaGate, но отдельные следствия опыта могут требовать времени и
    повторной обработки.

    Сон является одним из допустимых temporal windows для consolidation,
    но не единственным источником learning/belief revision.

    Запрет:
    sleep() не является универсальным магическим commit() для памяти.

    Проверить:

        Experience
            ↓
        immediate state effect
            +
        persistent trace
            ↓
        temporal processing
            ↓
        selective consolidation /
        revision /
        strengthening /
        weakening

    Любое изменение должно иметь provenance и causal parent.

**Stop:** пока BC-1...BC-7 не доказаны, не начинать полноценный Active
Inference как отдельный большой слой.

Цель:

Сон не является отдельной «анимацией отдыха» и не является
fatigue = 0.

Сон — temporal runtime mode организма, в котором Body продолжает
изменяться по собственным законам.

Главный принцип:

    SLEEP ≠ RESET

    SLEEP = state-dependent recovery process.

- [ ] Зафиксировать canonical границу:

      wakefulness
          ↓
      sleep pressure accumulation
          ↓
      sleep seeking
          ↓
      reachable recovery affordance
          ↓
      settled
          ↓
      sleep transition
          ↓
      recovery runtime
          ↓
      awakening

- [ ] Не создавать второй SleepStore, если canonical BodyState уже
  способен хранить необходимые temporal variables.

- [ ] Все переходы сна должны быть deterministic и replayable.

- [ ] Sleep runtime не должен иметь прямого writer-пути мимо canonical
  StateApplicator / владельца Body domain.

- [ ] Разделить duration и quality.

  8 часов в sleep state ≠ автоматически одинаковое восстановление.

- [ ] Recovery зависит как минимум от:

      continuity
      interruption
      safety / threat context
      available recovery affordance
      pre-existing sleep pressure

- [ ] Не моделировать нейрофизиологию человека ради биологической
  точности.

  NREM/REM/EEG не являются обязательными canonical сущностями.

  Если разные режимы восстановления понадобятся, они должны быть
  введены как функциональные recovery modes, а не как декоративная
  копия медицинской терминологии.

- [ ] Observation / threat / relevant stimulus может прервать sleep state
  только через существующие perception/arousal rules.

- [ ] NPC не должен просыпаться от каждого event в мире.

- [ ] Different stimulus relevance может давать:

      no interruption
      partial arousal
      full awakening

- [ ] Реакция зависит от:

      perception accessibility
      arousal threshold
      current body state
      threat appraisal.

- [ ] No global "wake all NPCs" shortcut.

- [ ] Проверить, выполняет ли единый recovery process разные уникальные
  каузальные работы для:

      Body restoration
      Perception restoration
      Cognitive availability

- [ ] Новые recovery variables разрешены только после anti-Bond test:

      какую причинную работу эта переменная выполняет,
      которую уже не выполняют fatigue / sleep pressure /
      existing body state?

- [ ] Не создавать:

      cognitive_recovery = 0.8
      emotional_recovery = 0.6

  только ради психологической правдоподобности.

  Новая ось появляется только при доказанной уникальной causal work.


### Фаза 1.6 --- Unified Appraisal / «палитра эмоций»

-   [ ] **EM-1** Определить минимальное пространство оценок: valence,
    arousal/intensity, agency, controllability, fairness/norm violation,
    self/other relevance, certainty/uncertainty, future
    consequence/expectation.
-   [ ] **EM-2** Отделить appraisal от emotion, emotion от relationship
    и relationship от belief.
-   [ ] **EM-3** Вывести
    anger/fear/sadness/pride/shame/gratitude/envy/resentment/contempt/hope
    как derived regions, а не отдельные state-machines.
-   [ ] **EM-4** Сделать decay, accumulation, interference, memory
    reactivation и social contagion общими законами.
-   [ ] **EM-5** Emotion → action preference: чувства голосуют за
    существующие действия; не создавать `if emotion == X → action Y`.
-   [ ] **EM-6** Expression dictionary: словарь речи/позы/интонации
    отдельно от причинности.
-   [ ] **EM-7** Calibration lab: подобрать пороги и веса на сценариях,
    а не вручную на каждом NPC.

### Фаза 1.7 --- Predictive Perception / Surprise

-   [ ] **PP-1** Унифицировать observation/belief truth sources.
-   [ ] **PP-2** Ввести измеримый surprise/prediction error как свойство
    ожидания, а не просто эмоциональный всплеск.
-   [ ] **PP-3** Использовать surprise для пересмотра
    beliefs/relationships/expectations.
-   [ ] **PP-4** Закрыть PlayerBeliefModel ≠ NPC ToM: собственные
    убеждения NPC и убеждения о чужих убеждениях не смешивать.
-   [ ] **PP-5** Second-order ToM: `A believes B believes X` --- только
    после первого порядка и при доказанной необходимости.
-   [ ] **PP-6** Prophecy / prediction vertical slice --- после
    PP-1...PP-4.
- [ ] PP-7 Temporal state → perception quality.

  BodyState и recovery state могут причинно изменять доступность и
  качество perception без создания второго perception engine.

  Минимальные направления:

      fatigue / sleep pressure
          → reduced effective attention

      sleep state
          → altered arousal threshold

      deep rest / settled recovery
          → restoration of perception capacity

  Реализация должна использовать существующие perception contracts и
  deterministic thresholds/scaling, а не probability hacks.

  Не вводить:
      random_sleepiness()
      chance_to_miss_event()

  Предпочтительно:

      canonical body state
          ↓
      derived perception modifier
          ↓
      existing Observation / Perception pipeline.

### Фаза 1.8 --- HUMOR / PLAY / SOCIAL INCONGRUITY

Юмор вводится **после замыкания Experience→Conclusion→Expectation,
Unified Appraisal и измеримого Prediction Error**, потому что иначе
пришлось бы создавать специальные «юмористические» костыли. Это не
`humor_engine` ради шуток, а вертикальный тест субъективного мира: один
и тот же event может быть смешным для одного NPC, нейтральным для
другого, непонятным для третьего и угрожающим для четвёртого.

#### HUM-00 --- контракт и anti-Bond

-   [ ] Определить минимальные derived-компоненты: `Incongruity`,
    `PredictionError`, `Resolution`, `Benignity`, `HumorAppraisal`,
    `HumorAttempt`, `HumorReaction`.
-   [ ] Запретить canonical state `is_funny`, `humor_level` и
    `is_joking` как источники поведения.
-   [ ] Personality допускается только как вход в производную
    disposition: playfulness, openness/flexibility, social confidence,
    risk tolerance, norm rigidity и другие уже существующие traits.
-   [ ] Отдельно зафиксировать temporal plasticity: disposition меняется
    вследствие опыта, отношений, текущего appraisal/body state и
    успешных/неуспешных социальных эпизодов.
-   [ ] Anti-Bond: доказать, что юмор не дублирует существующие
    appraisal/relationship/ prediction mechanisms; если отдельный state
    не выполняет уникальную каузальную работу, он остаётся derived
    operation.

#### HUM-01 --- Perception: incongruity

-   [ ] Сопоставлять наблюдение с expectation NPC, а не с «объективной
    смешностью» события.
-   [ ] Измерять discrepancy между ожидаемым и наблюдаемым.
-   [ ] Не считать любой surprise юмором: surprise может вести к fear,
    confusion, anger, curiosity и другим appraisal regions.
-   [ ] Зафиксировать минимальную форму разрешения: NPC должен иметь
    возможность построить правдоподобную связь между двумя
    скриптами/интерпретациями.

#### HUM-02 --- Resolution / Logical Mechanism

-   [ ] Ввести представление `Script Opposition` и `Logical Mechanism`
    как данных/операций, не как библиотеку анекдотов.
-   [ ] Поддержать несколько механизмов: semantic shift, analogy,
    inversion, exaggeration, literalization, causal reversal и
    эквивалентные общие операции, если они реально нужны.
-   [ ] Проверить, что высокая неожиданность без разрешения остаётся
    confusion/uncertainty, а не автоматически humor.
-   [ ] LLM может реализовать Language Layer, но не является источником
    истины о том, что произошёл юмористический акт.

#### HUM-03 --- Benignity / social safety

-   [ ] Оценивать violation относительно норм, угрозы, статуса,
    контекста и доступного агенту знания.
-   [ ] Учитывать relationship state, но не сводить юмор к `trust`.
-   [ ] Один и тот же violation должен допускать разные appraisal
    outcomes: amusement / neutral / confusion / insult / threat.
-   [ ] Self-directed humor допускается как отдельный безопасный
    вариант, если он следует из общей модели target/self-other
    relevance, а не из флага `self_irony`.

#### HUM-04 --- Individual humor disposition

-   [ ] Производить текущую humor disposition из уже существующих
    personality + experience + appraisal/body + relationship/epistemic
    context.
-   [ ] Не хранить её как вечный scalar personality trait.
-   [ ] Проверить temporal drift: один NPC в разных состояниях и
    периодах жизни реагирует на одинаковый юмористический паттерн
    по-разному.
-   [ ] Проверить, что изменения disposition имеют provenance и могут
    быть объяснены через реальные изменения входных факторов.

#### HUM-05 --- Humor as coping / pressure response

Юмор не должен ограничиваться безопасной игрой. Он может быть **ответной
стратегией на тяжёлую текущую или длительную ситуацию**, если общая
модель appraisal/agency делает её доступной.

-   [ ] Описать humor-as-coping как derived action/appraisal pattern, а
    не как отдельную эмоцию «смелость через юмор».
-   [ ] Допустить юмор при высоком fear/stress/pressure, если NPC
    ожидает, что такая реакция снижает субъективное напряжение,
    поддерживает self-control, сохраняет социальную связь или позволяет
    продолжать действие.
-   [ ] Различать как минимум: `tension_release`, `social_support`,
    `self-protection`, `defiant_play`, `absurdization/meaning-reframing`
    --- только если эти режимы выводятся из общих appraisal/ motivation
    механизмов и не становятся отдельными флагами.
-   [ ] Длительная тяжёлая ситуация должна менять вероятность/форму
    coping-humor через pressure accumulation, memory и self-model, а не
    через таймер.
-   [ ] Юмор может быть неадаптивным: он способен маскировать страх,
    раздражать союзника, разрушать серьёзность ситуации или довести NPC
    до рискованного поведения.
-   [ ] Отдельно проверить границу: экстремальное давление не должно
    автоматически делать NPC смешным или постоянно шутящим.
-   [ ] «Шутка на грани» должна оставаться причинным выбором с оценкой
    ожидаемой реакции и риска.

#### HUM-06 --- Humor production

-   [ ] NPC может обнаружить opportunity для шутки из текущего
    контекста.
-   [ ] Candidate generation → audience model → expected reaction →
    risk/benefit → attempt.
-   [ ] Production не запускается по расписанию и не обязана происходить
    при каждом surprise.
-   [ ] Чем слабее модель аудитории/отношений/контекста, тем выше
    вероятность нейтральной, неудачной или подавленной попытки.
-   [ ] LLM используется только для языковой реализации разрешённого
    runtime `HumorAttempt`.

#### HUM-07 --- Failed humor / consequences

-   [ ] Зафиксировать реакции: laugh/amusement, neutral, confusion,
    embarrassment, offense/conflict, bonding и другие derived outcomes.
-   [ ] Реакция слушателя становится experience и при необходимости
    memory.
-   [ ] Успех/провал меняет expectations о конкретном собеседнике и
    собственный self-model.
-   [ ] Отношения могут измениться через обычный
    RelationshipEventSemantics.
-   [ ] Повторные удачные эпизоды могут формировать социальную
    привычку/ожидание, но не специальный `friend_is_funny` флаг.

#### HUM-08 --- Social transmission

-   [ ] Если B услышал шутку A, B получает собственную
    observation/provenance, а не копию внутреннего состояния A.
-   [ ] C, не наблюдавший событие, не получает его автоматически.
-   [ ] Передача шутки/истории может менять reputation, familiarity или
    expectations через существующие testimony/social mechanisms.
-   [ ] Проверить искажение/непонимание при неполной передаче.

#### HUM-09 --- Long-horizon humor

-   [ ] 100--1000 тиков: humor disposition меняется вместе с жизнью NPC.
-   [ ] После серии удачных безопасных шуток NPC может стать более
    склонным к playfulness в соответствующем контексте.
-   [ ] После унижения/конфликта/хронического давления юмор может
    исчезнуть, стать защитным, агрессивным или более рискованным ---
    только если это следует из общих механизмов.
-   [ ] После восстановления/поддержки disposition может измениться
    обратно без reset.
-   [ ] Same seed + same history → same humor outcomes; другой history →
    другой outcome.

#### HUM-10 --- Observability

-   [ ] Chronicle показывает: expectation → incongruity →
    resolution/failed resolution → benignity/social appraisal →
    attempt/reaction → consequence.
-   [ ] NPC Inspector способен ответить «почему он пошутил?» без
    LLM-галлюцинации: доступная ситуация, relevant expectation,
    appraisal, relationship/audience model, pressure и выбранный action.
-   [ ] UI не показывает скрытые коэффициенты как gameplay truth;
    допускается human-readable объяснение без раскрытия внутренней
    математики.



### Фаза 1.9 --- PLAYER AVATAR / EMBODIED AGENCY

Аватар игрока не является «ещё одним NPC» и не является тупым курсором.
Это **тот же causal actor**, что и NPC, но с особой границей агентности:
игрок производит intent от имени аватара, а состояние аватара может принять,
изменить, затормозить или отвергнуть этот intent. Цель фазы --- замкнуть уже
существующий контур ADR-030/031/036/037/039/041/084, а не изобретать второй
cognitive stack.

Исходная мотивация: правила настольного RPG уже подразумевают, что персонаж
не равен управляющему им игроку. Класс, происхождение, ценности, нормы,
страх, характер, убеждения, границы и прошлый опыт должны причинно влиять на
то, **что персонаж готов сделать**, а не только на текст после действия.
Монах может воспринимать богохульство как сильное нарушение идентичности,
но насилие против врага веры --- как совместимое с его нормами. Смелый
ловелас может иметь низкую social-exposure pressure в флирте, а скромный
персонаж --- высокую. Персонаж с определённой ориентацией не должен
автоматически принимать сексуальный intent игрока, если он противоречит его
ценностям/предпочтениям. Все такие различия должны быть **derived из
общего состояния и контекста**, а не набором hardcoded запретов.

Главный принцип:

> **PLAYER INPUT ≠ AVATAR WILL.**
>
> Игрок предлагает намерение. Аватар остаётся causal субъектом действия.
> Разногласие между ними --- игровое состояние, имеющее причины,
> последствия, память и историю.

#### AV-00 --- Canonical Avatar Contract

-   [ ] Формально описать `player` как actor с теми же canonical state
    domains, что и допустимые NPC-домены, но с отдельным `agency_boundary`.
-   [ ] Зафиксировать границу: `player_intent → avatar_appraisal →
    resistance/accept/modify → execution`.
-   [ ] Запретить отдельный avatar-only writer там, где существующий
    canonical writer уже может изменить состояние.
-   [ ] ADR-030/031/036/037/039/041/084 собрать в один актуальный
    contract/index; удалить ложные обещания из комментариев и ADR, если
    production reality им не соответствует.
-   [ ] Определить, какие домены аватара обязательны в MVP, а какие
    сознательно deferred.
-   [ ] Ввести invariant: отсутствие avatar-specific DecisionHub не должно
    означать отсутствие avatar agency.

#### AV-01 --- Persistent Psyche / Personality Substrate

-   [ ] Реализовать настоящий persistent psyche для аватара: `fear`,
    `conviction`, `shame`, `aggression`, `curiosity`, `identity_rigidity`
    и связанные уже существующие параметры.
-   [ ] Связать CharacterProfile/values с canonical psyche вместо
    параллельной мёртвой конфигурации.
-   [ ] Разделить **stable disposition** и **current state**: ценности и
    склонности не должны каждый тик переписываться stress-ом, но состояние
    должно влиять на текущую доступность действий.
-   [ ] Устранить fallback-константы `0.5` как production source of truth.
-   [ ] Проверить диапазоны всех психических шкал и привести их к единой
    convention; никакого смешивания `0..1` и `0..100` в одном resolver.
-   [ ] Save/load должен восстанавливать psyche без потери причинной
    истории.

#### AV-02 --- Preferences / Values / Norms / Identity

Это слой, которого не хватает для ролевого смысла сопротивления. Он не
должен превращаться в список запретов.

-   [ ] Представить ценности как оценочные параметры/constraints:
    sacredness, loyalty, honesty, violence tolerance, modesty,
    autonomy, purity/discipline, status, compassion и аналогичные
    **только там, где они нужны игровому домену**.
-   [ ] Представить предпочтения как ordinary appraisal inputs, а не
    `allowed_targets`/`forbidden_actions` списки.
-   [ ] Для социальных/романтических действий поддержать actor-specific
    attraction/preferences/comfort boundaries без предположения, что
    существует единый «нормальный» персонаж.
-   [ ] Происхождение/класс/профессия/культура могут инициализировать
    priors, но не должны навсегда заменять опыт и обучение.
-   [ ] Нормативный конфликт должен быть объясним: «это против моей
    веры», «это унижает меня», «я не доверяю ему», «я не хочу этого» ---
    разные causal reasons, а не один `REFUSE`.
-   [ ] Запретить код вида `if monk and blasphemy` как gameplay-critical
    writer. Конкретный результат должен возникать из values/norms,
    context и appraisal.

#### AV-03 --- Willpower + CharacterFilter + Affect: единый Resolver

Существующие системы **не сливаются математически**. Они становятся
разными источниками evidence для единой точки принятия решения.

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

-   [ ] Сохранить `WillpowerGate` как pressure/strain mechanism.
-   [ ] Сохранить `CharacterFilter` как identity/value appraisal.
-   [ ] Сохранить affective/trauma resonance как distortion of pressure,
    а не как ещё один veto-флаг.
-   [ ] Ввести единый `AvatarActionResolution`/эквивалентный контракт,
    который агрегирует причины и выбирает итоговый режим.
-   [ ] Возвращать machine-readable `reasons[]`, severity, dominant
    factors и counter-offer provenance.
-   [ ] Не позволять одному слабому фактору автоматически превращать
    действие в REFUSE; итог зависит от общей модели и calibration.

#### AV-04 --- Social / Romantic / Sexual Agency Boundaries

Цель не в создании отдельной «сексуальной подсистемы», а в доказательстве,
что **обычные preference, norm, comfort, attraction, trust, fear и
relationship mechanisms действительно влияют на действия аватара**.

-   [ ] Player-originated flirtation проходит тот же appraisal pipeline,
    что и NPC-originated social intent.
-   [ ] Персонаж может принять, изменить, смягчить или отвергнуть
    социальный/романтический intent согласно своему состоянию и
    preferences.
-   [ ] Отсутствие attraction не должно автоматически означать hostility;
    возможны neutrality, politeness, avoidance, embarrassment и другие
    outcomes из общей модели.
-   [ ] Discomfort/social exposure должен отличаться от moral violation.
-   [ ] Trust и familiarity могут изменять доступность близости, но не
    заменяют preference/consent boundary.
-   [ ] Сексуальная/романтическая тематика не должна получать специальный
    privileged writer: это один из тестов универсальности social action
    machinery.
-   [ ] Тесты должны покрывать как минимум контраст «раскованный персонаж
    vs скромный», «есть attraction vs нет attraction», «безопасный
    контекст vs threat/pressure».

#### AV-05 --- Player Trust / Relationship to the Controller

Это отдельная ось и не синоним identity integrity.

-   [ ] Ввести `player_trust`/эквивалент как relationship-like state,
    если calibration подтвердит необходимость.
-   [ ] Отличить: «я знаю, кто я» (`identity_integrity`) от «я доверяю
    тому, кто мной управляет» (`player_trust`).
-   [ ] Trust меняется через историю: полезные приказы, предательство,
    принуждение, успешные переговоры, уважение границ.
-   [ ] Trust влияет на expected intent of player и вероятность
    accepting/modifying a request, но не становится универсальным
    shortcut `trust > threshold → obey`.
-   [ ] Высокий trust не должен отменять values/trauma/physical danger;
    низкий trust не должен автоматически означать sabotage.
-   [ ] Все изменения trust имеют provenance и доступны Chronicle.

#### AV-06 --- Negotiation with the Player

Игрок не обязан либо «приказывать», либо получать отказ. Между ними нужен
каузальный negotiation channel.

-   [ ] `RESIST` может порождать counter-offer: другой маршрут, меньший
    риск, другой объект, помощь, ожидание, stealth, retreat и т.п.
-   [ ] Counter-offer должен быть executable game intent, а не только
    текстом в input field.
-   [ ] Игрок может принять, отклонить или изменить counter-offer.
-   [ ] Повторное давление должно иметь cumulative consequences, а не
    пересчитываться каждый раз с нуля.
-   [ ] Уступка аватара не должна стирать disagreement: history сохраняет
    факт конфликта и его outcome.
-   [ ] Negotiation не должен быть обязательным UI modal; он может быть
    embodied/implicit через action modification, movement, silence,
    hesitation и внутренний голос.

#### AV-07 --- Inner Voice / Soliloquy

Private communication channel уже существует. Задача --- включить его для
аватара после восстановления canonical state.

-   [ ] Player-avatar может генерировать private/speechless proposition
    через production communication path.
-   [ ] Триггеры: сильный dissonance, high affective load, memory
    reactivation, sleep/dream, major identity conflict, extreme pressure.
-   [ ] Inner voice не должна работать как scheduled monologue.
-   [ ] Первый production path --- deterministic narration hooks/templates.
-   [ ] LLM допускается только как optional Language Layer после
    DeltaGate; causal state, reason и outcome остаются в Python.
-   [ ] Counter-offer и narrative hook должны доходить до DM/API/frontend,
    а не умирать внутри DTO.
-   [ ] Проверить, что голос отражает actual state и не создаёт новую
    скрытую psyche.

#### AV-08 --- Resistance Medium / Embodied Conflict

Существующий заражаемый input --- presentation layer, а не source of
truth.

-   [ ] Сохранить Resistance Medium как редкую сильную форму конфликта.
-   [ ] Удалить implicit reset semantics: конфликт должен иметь lifecycle
    `trigger → escalation → resolution → aftermath`.
-   [ ] Input interference допускается только когда canonical resolver
    реально вернул соответствующее состояние.
-   [ ] Частота конфликтов определяется causal thresholds, а не cooldown
    «ради геймплея».
-   [ ] Проверить, что normal play не превращается в постоянную борьбу с
    клавиатурой.
-   [ ] PerceptualMomentum, shake, tunnel vision и latency остаются
    феноменологической проекцией, а не психическим state writer.

#### AV-09 --- Escalation / Recovery / Conditioning

`BROKEN` и `CONDITIONED` --- не Game Over, а долгосрочные изменения
агентности.

-   [ ] Formalize transition semantics для
    `COMPLY → RELUCTANT → DISTRESSED → PANICKED → DISSOCIATING → BROKEN →
    CONDITIONED`.
-   [ ] Определить, какие переходы обратимы, какие оставляют scars и какие
    требуют длительного восстановления.
-   [ ] Recovery должен быть causal: safety, sleep, social support,
    successful agency, time/decay и другие реальные факторы.
-   [ ] Conditioning может менять будущие thresholds/expectations, но не
    должен быть магическим permanent flag.
-   [ ] Broken state может приводить к freeze, collapse, avoidance,
    observation или другим существующим embodied outcomes.
-   [ ] После восстановления остаются memory/affective consequences,
    если их породила история.
-   [ ] Отдельно тестировать «сломался, но игра продолжается».

#### AV-10 --- Limited Autonomous Agency

Не создавать второй полный NPC stack. Автономия аватара включается только
в местах, где это необходимо для сохранения embodied agency.

-   [ ] Определить минимальный `AvatarAutonomyResolver` поверх существующих
    affordances/DecisionHub/Body/Perception mechanisms.
-   [ ] Разрешённые случаи: idle/settled behavior, panic/freeze,
    dissociation, extreme pressure, sleep/dream, explicit counter-offer.
-   [ ] Автономное действие всегда проходит canonical execution и
    verification.
-   [ ] Никаких отдельного memory writer, relationship writer,
    world-state writer или secret belief store только для аватара.
-   [ ] Проверить границу «agency vs interface fight»: автономия должна
    быть редкой, причинной и объяснимой.

#### AV-11 --- Avatar Memory / Experience / Self-Model

-   [ ] Перевести аватар с FIFO-буфера последних реплик на общий
    MemoryManager/experience substrate там, где это уже production-ready.
-   [ ] Опыт `player_action → avatar conflict → outcome` сохраняется как
    experience с provenance.
-   [ ] Experience может менять self-model: «я способен», «я не справился»,
    «игрок обычно уважает мой отказ», «это действие опасно».
-   [ ] Repeated evidence → conclusion → expectation применяется и к
    отношению аватара к игроку.
-   [ ] Memory decay не должен стирать identity/conditioning без causal
    reason.
-   [ ] Save/load и replay должны восстанавливать состояние и историю.

#### AV-12 --- Avatar Epistemics

Полноценная epistemics для аватара --- поздний, но обязательный при
доказанной ценности слой. Игрок может знать одно, а его персонаж --- другое.

```text
WORLD TRUTH
   ≠ PLAYER KNOWLEDGE
   ≠ AVATAR BELIEF
   ≠ NPC BELIEF
```

-   [ ] Avatar получает собственные observations и belief records через
    общий epistemic pipeline.
-   [ ] Player input не превращает автоматически неизвестный аватару факт
    в его belief.
-   [ ] Проверить scenario: игрок знает истину, аватар имеет ложное
    belief и сопротивляется приказу из-за своей модели мира.
-   [ ] Проверить обратное: аватар видел событие, игрок его не видел;
    avatar counter-offer может быть основан на information asymmetry.
-   [ ] Полностью переиспользовать Proposition/SpeechAct/ClaimEvent/
    EpistemicRecord/BeliefRevisionEngine, не создавать AvatarBeliefEngine.
-   [ ] Сохранить distinction между player knowledge, avatar belief и
    avatar ToM.

#### AV-13 --- Avatar Relationships / Social Consequences

-   [ ] Аватар участвует в Relationship Engine как actor, без отдельной
    relationship store.
-   [ ] Его отказ, помощь, ложь, унижение, флирт, спасение и т.п. проходят
    через обычные RelationshipEventSemantics.
-   [ ] NPC могут делать выводы о характере аватара по его действиям.
-   [ ] Avatar может менять отношения не только по player command, но и
    по тому, **как именно** он исполнил/изменил command.
-   [ ] Social consequences способны менять будущую resistance и trust.

#### AV-14 --- Avatar + Humor / Coping / Phenomenology

Аватар должен использовать тот же humor substrate, а не иметь отдельный
«humor mode».

-   [ ] Юмор аватара может возникать из его expectations, appraisal,
    relationship и context.
-   [ ] Coping humor при страхе/давлении может становиться способом
    удержать agency, если это следует из его history/self-model.
-   [ ] Игрок может наблюдать, что аватар шутит в невозможной ситуации не
    потому, что «так прописано», а потому что это стало его learned coping
    strategy.
-   [ ] Не допускать `stress → joke` и `high humor → joke` shortcut.
-   [ ] Humor attempt/failed humor влияет на player trust, relationships,
    memory только через общие causal mechanisms.

#### AV-15 --- Observability / "Why did my character refuse?"

-   [ ] Chronicle показывает causal chain: player intent → relevant
    context → pressure/values/preferences/trauma/body/trust → resolution →
    execution/counter-offer → consequence.
-   [ ] Inspector отвечает на «почему аватар отказался?» без LLM как
    authority.
-   [ ] Отдельно показывать difference между `cannot`, `will not`,
    `does not trust`, `does not know`, `does not want` и `does not
    understand`, если соответствующие причины существуют в runtime.
-   [ ] UI не обязан показывать числовые коэффициенты; достаточно
    causal-human-readable explanation.
-   [ ] Resistance Medium и phenomenology являются presentation of an
    already-proven state.

#### AV-16 --- Avatar Vertical Slice

Минимальный вертикальный сценарий должен доказать не красивую реплику, а
полный causal loop:

```text
player command
 → avatar appraisal
 → accept/modify/resist/refuse
 → optional negotiation
 → execution
 → world/social consequence
 → experience/memory
 → changed expectation/trust/self-model
 → different response to a later command
```

Обязательные контрасты:

-   [ ] `AV-GC-01` Монах: богохульство вызывает нормативный конфликт,
    тогда как действие, совместимое с его ценностями, не вызывает того же
    сопротивления.
-   [ ] `AV-GC-02` Ловелас vs скромняга: одинаковый social/flirt intent
    получает различный appraisal и action outcome.
-   [ ] `AV-GC-03` Preference boundary: отсутствие соответствующего
    attraction/comfort не превращается автоматически в hostility, но
    может дать refusal/avoidance/embarrassment.
-   [ ] `AV-GC-04` Trauma differential: одинаковый command после разных
    histories даёт разные resistance outcomes.
-   [ ] `AV-GC-05` Negotiation: REFUSE/MODIFY порождает executable
    counter-offer, который игрок может принять.
-   [ ] `AV-GC-06` Trust history: после серии уважительных команд принятие
    одного и того же спорного intent меняется; после coercion меняется в
    другую сторону.
-   [ ] `AV-GC-07` Recovery: repeated pressure → escalation → recovery;
    BROKEN не означает game over.
-   [ ] `AV-GC-08` Memory: после save/load/replay avatar remembers the
    causal consequence relevant to a later decision.
-   [ ] `AV-GC-09` Epistemic asymmetry: player knowledge ≠ avatar belief.
-   [ ] `AV-GC-10` Social consequence: avatar action changes an NPC
    relationship, which later changes an avatar/NPC interaction.
-   [ ] `AV-GC-11` Inner voice: at least one conflict reaches player-visible
    private narration through production API.
-   [ ] `AV-GC-12` Humor/coping: same impossible situation can produce
    coping humor for one avatar history and panic/avoidance for another.

#### AV-17 --- Anti-Bond / Anti-Second-ENIGMA Rules

-   [ ] Нет `is_monk → veto(blasphemy)` как единственного механизма.
-   [ ] Нет `orientation → hardcoded allowed_targets` как canonical action
    gate; preferences participate in appraisal.
-   [ ] Нет `personality_trait → action` прямой таблицы без context.
-   [ ] Нет `player_trust > X → obey`.
-   [ ] Нет `BROKEN → game_over`.
-   [ ] Нет второго полного DecisionHub/MemoryManager/EpistemicStore/
    RelationshipStore только для игрока.
-   [ ] Нет LLM-generated hidden resistance state.
-   [ ] Нет periodic inner monologue / resistance ticks без causal trigger.
-   [ ] Нет presentation-layer writer, который сам меняет psyche.

#### AV-18 --- Calibration / Scope Ceiling

Поскольку проект solo, потолок аватара фиксируется архитектурно.

**MVP avatar:**

`body + perception + psyche + values/preferences + affect + resistance +
inner voice + limited memory/experience + player trust + social
consequences`.

**Later:**

`full avatar epistemics + richer self-model + limited autonomous agency +
long-horizon conditioning`.

**Deferred:**

полный автономный NPC cognition stack, отдельный Avatar-specific social
engine, тяжёлые second-order ToM и отдельная система эмоций.

-   [ ] Каждая новая avatar-фича сначала доказывает, что её нельзя вывести
    из существующего общего механизма.
-   [ ] Если новая сущность только переименовывает existing state, она не
    получает отдельного writer/store.
-   [ ] Avatar vertical closure обязателен до расширения в десятки
    специализированных психологических параметров.

### Фаза 2 --- Эпоха 7: Predictive Perception & Prophecy (legacy roadmap; детализирована в Фазе 1.7)

-   [ ] `docs/Почти Актуальные TZ/TZ_Stage_2_5_..._1.md` (Часть I) +
    `VZ/TZ_§19_Predictive_Perception_Dynamics.md` (surprise = −log
    P(x_t\|z\_{t-1})).
-   [ ] `ObservationLayer/BeliefProjector` (P1-31) --- унификация
    источников правды убеждений.
-   [ ] Prophecy System (ADR-O-330), Vertical Slice «Секреты Люси ---
    секреты таверны».

### Фаза 3 --- Эпоха 8: Temporal Identity, линии времени

-   [ ] `VZ/ТЕХЗАДАНИЕ ПРЕЕМНИКУ TZ-02 V.2.0` (WorldChronicle, 3 уровня
    времени), ADR-TIFL-001..003.
-   [ ] `VZ/TEXTURES_AND_GEOMETRY_TZ.md` --- visual aging (после
    lineage).

### Фаза 4 --- Эпоха 9: Общество (Factions, Economy, Politics) + Memetic

-   [ ] `VZ/TZ_MEMETIC_01..03` --- меметический домен.
-   [ ] Factions / Economy (`architecture/economy.yaml` есть,
    инженерного ТЗ нет) / Politics --- ТЗ сформулировать.

### Фаза 5 --- Эпоха 10: Bounded Rationality

-   [ ] `VZ/TZ_§18_Resource_Bounded_Epistemic_Selection_Law.md`
    (`U_M = I·R·U − C`) --- **только после** Belief Layer.

### Фаза 6 --- Контент и презентация (когда угодно, изолированно)

-   [ ] `ENIGMA_TZ_Female_Targeted_Dark_Fantasy_Layer.pdf`,
    `ENIGMA_MAP_EDITOR_SMART_VALIDATION.md`,
    `AWC_Process_World_Model_TZ.pdf` (Эпоха 11+, только дизайн),
    Narrative Frame Onboarding, Laboratoria Kalibrovki (полигон).

### Долг (не блокирует, брать паузами)

-   [ ] God-файлы: `game_loop/__init__.py`, `life_engine.py`,
    `tick_orchestrator.py`.
-   [x] ~~mypy --strict: 79 ошибок (`spatial_runtime.py`,
    `spatial_service.py`)~~ **✅ Исправлено** --- mypy --strict: 0
    ошибок в spatial-слоях (`spatial_runtime.py`, `spatial_service.py`,
    `graph_compiler.py`, `spatial_query_service.py`, `npc_state.py`).
    Было 79 каскадных ошибок, включая `bool()` в `npc_state.py` и
    `Dict[str, dict]` → `Dict[str, Dict[str, Any]]` в
    `graph_compiler.py`.
-   [x] ~~`print()` → logger (76 вхождений)~~ **✅ Исправлено** --- все
    36 `print()` в `backend/app/main.py` заменены на
    `logger.info/error/warning` с корректным уровнем. Ruff-clean. ⚠️
    **AUD-D7 (2026-09-04):** в V.0.5.3.9.6 в `main.py` снова **34
    `print()`** (блок запуска + llama-server, строки 98--365) --- статус
    частично откатился; ядро не задето, см. §4c.
-   \[\~\] TODO/FIXME в доменном слое (`backend/app/domain/`) --- 5
    записей: context-aware intensity (v2), S28 enum IntentType,
    IntentSemanticField extension, DeathState backlog (2 TODO). Это
    backlog-маркеры будущей функциональности, а не баги --- оставлены
    как есть.
-   [x] ~~DEBT-IPT-RUFF: 24 pre-existing нарушения в `IPT.py`~~ **✅
    Исправлено** --- `ruff check IPT.py`: `All checks passed!` (F821
    `os` :1129 --- не ошибка, т.к. `import os` на строке 1115 внутри
    функции; 24 нарушения были устранены в предыдущей сессии).
-   [ ] **DEBT-QUIESCE (async-interleaving недетерминизм)** --- внешняя
    зона (async-слой/M1b-контур), НЕ косметика тестов. Симптом (S237):
    между идентичными OFF-прогонами варьируют пропорция
    COMPLETED/INTERRUPTED commitment-терминалов и микропозиции NPC
    (фоновые диффы {4,7} по 9 осям) при стабильных
    terminals_total/npc-set/world_objects. Влияние: A/B-гейты
    закрываются с ambient qualification (GORAN β G1 --- прецедент S237).
    Будущее требование (вердикт Мастера): воспроизводимые причинные
    цепочки уровня «кража → наблюдение → вера → смена цели → перенос
    стула → сторожит» требуют execution/interleaving-детерминизм как
    ФУНДАМЕНТАЛЬНОГО слоя, не тестовой косметики --- кандидат W-контура
    после стабилизации. Точка данных: latent TICK_CRASH
    npc_tick_pipeline:703 (active_commitments DOUBLE TRUTH) ---
    interleaving-зависим.
-   [ ] **DEBT-SLEEP-DELIVERY (доставка тел к кроватям)** --- внешняя
    зона (spatial/behavioral; НЕ физиология --- сон-машина
    верифицирована независимо: S235/S236). Симптом (S236, DriftLab 200
    тиков × 6 NPC): elig=True = 0/1200 --- тела не доезжают до кроватей
    при живом графе (смоук: kitchen_bed_1/2→BED) и целенаправленных
    данных: thief→city_gate:tent_3 (кросс-локационная цель; конфиг «не
    мигрирует»), borko→city_gate:guard_bed (кросс-локация),
    lusya→tavern:kitchen_bed_1 (валидная в-локационная цель; 129/129
    сон-тиков no_bed --- в моменты проверок в пути). Следствие без
    доставки: sleep_pressure→1.0, motor_output_mult→0 («мир недосыпа»
    --- долгосрочное равновесие). Статус (вердикт Мастера): НЕ blocker
    Body Life; blocker качественного long-horizon сна в кампании
    Open_road. Решение --- при spatial/affordance-контуре: intent →
    affordance search → reachable target → traversal → settled →
    физиологический переход (машина подхватит автоматически).
    Дизайн-вход Мастера (S236): «Тень тайно спит в подвале» --- первый
    кандидат контент-фикса (activity_map/MapEditor или W2
    sleep-affordance-типы BED→HAMMOCK/GROUND/SHELTER).
    DEBT-SLEEP-DELIVERY — Sleep Architecture Delivery Boundary

    Сон-машина физиологически верифицирована независимо.

    Открытая проблема находится не внутри Body/Sleep Runtime, а на границе:

        homeostatic pressure
            ↓
        motivation / intent
            ↓
        affordance discovery
            ↓
        reachable recovery target
            ↓
        traversal
            ↓
        settled
            ↓
        sleep transition
            ↓
        recovery runtime.

    Следствие:

        физиология может быть корректна,
        но мир всё равно производит хронический недосып,
        если embodied actor не способен физически достигнуть
        recovery affordance.

    Это не Body bug.

    Это вертикальный разрыв:

        BODY → DECISION → WORLD → BODY.
-   [ ] **rng-бомба: rng or random в боевом ядре** Все функции
    combat_math.py принимают rng: Optional\[random.Random\] = None и
    делают \_rng = rng or random. Если хоть один call-site не инъецирует
    KernelRNG --- глобальный недетерминизм, нарушение ADR-O-301 и
    INV-REPLAY-DETERMINISM. AST-линтер kernel_rng это не ловит (вызов
    спрятан за default-параметр). Проверка call-sites --- мини-пакет №2.
    Отдельный запах: apply_damage пишет target\["status"\] = "dead" ---
    display-дубль рядом с каноническим life_status (мягкий DOUBLE TRUTH,
    в сравнительную оценку).
-   [x] **DEBT-W-AUDIT** --- ЗАКРЫТ (S240): `docs/AUDIT_W_TRACK_COUPLINGS.md`
    (§1 граф; §2 реестр Файл:строка/Паттерн/Категория/FACT-INTERPRETATION-
    RECOMMENDATION/Migration; §3 сводка §18.2: 0 Simulation coupling, 12
    Acceptable adapter; §4 входной ограничитель G3; §5 релеи R1--R6).
    Порог ТЗ перекрыт: поиск шире §18.1 (обратное ребро backend→frontend,
    W-граница writers, сериализация, API). Главный риск-узел --- B1.4-канал
    (routes.py:1243--1268: FE-пуш полного scene_state → merge
    незащищённых ключей → atomic_commit): anti-writer G3 + обходы
    CommitmentRegistry (R1) / RelationshipWriteGate (R2) --- релеи чужим
    сериям; условия до G3-ON --- §4.3 аудита. Владелец: W-трек.
-   [x] **DEBT-W-STORE-INCIDENT** (S239; инцидент закрыт; **вердикт
    Мастера 2026-09-04: ACCEPT --- признать эволюцию**) --- GORAN-харнессы
    S239 до изоляции мутировали общий production-store
    `ROOT/saves/enigma_runtime.db` (~2800 тиков эволюции + weapon-артефакт,
    вытеснен живой перезаписью «Память_3»). **Known provenance debt:**
    `ROOT/saves` содержит production-evolved state, возникший вследствие
    pre-isolation GORAN runs (~2800 ticks); исходное baseline-состояние
    невосстановимо; состояние признано легитимным для продолжения серии,
    но не является чистым baseline. Reset отклонён (подмена исторической
    непрерывности мира опаснее артефакта). Различение: **легитимность
    состояния** (продолжающаяся история мира) ≠ **валидность baseline**
    (экспериментальная чистота) --- «стратиграфия нарушена до T≈2800».
    G3 входит с чистой картой, но не с чистым миром. Закон-урок: **все
    A/B-харнессы обязаны патчить `settings.saves_dir` до
    `build_game_loop`** (эталон --- `scripts/w3_g2_simple.py`); G1-харнесс
    S237 имел тот же дефект (вердикт G1 валиден: тень --- ноль writers).
    Закон-урок: **все A/B-харнессы обязаны патчить `settings.saves_dir`
    до `build_game_loop`** (эталон --- `scripts/w3_g2_simple.py`);
    G1-харнесс S237 имел тот же дефект (вердикт G1 валиден: тень ---
    ноль writers; семантика изоляции --- нет). Хроника: MUTATIONS S239,
    ADR-O-378_IMPACT.
-   [ ] **W-ретрансляции Мастеру** (S239): F821 `Intent`
    `npc_tick_pipeline.py`~:697 --- runtime-достижимый latent NameError
    (Bridge-7, зона «Память»; их TYPE_CHECKING-mypy-доводка runtime не
    лечит); `data/replay.db` = 754 МБ / 68k snapshots (рост без
    ротации). Устаревшие чужие долги: AG1-D9 (поле объявлено ---
    S239/ADR-O-378), AG1-D8 (ADR-O-377 в атласе уже записан).

### §4a. Реестр долгов сессии AG1 (единый; префикс AG1-D; не разрозненный --- это исполняемый реестр)

  ----------------------------------------------------------------------------------------------------
  ID        Долг                           P        Зона/владелец      Действие             Статус
  --------- ------------------------------ -------- ------------------ -------------------- ----------
  AG1-D1    `V2RelationshipBackend` не     P1       RE-01 M1b (чужая)  уведомление          \[ \]
            имеет `_cache` → new_game                                  владельцу RE-трека в 
            reset падает                                               LAST_SESSION.md      

  AG1-D2    `Dialogue update failed:` ---  P1       AG1                ✅ ЗАКРЫТ           \[x\]
            тихий глоток в подписчике              2026-09-03:          (контекстный лог:
            диалогов (L4-нарушение)               repr+partner+len;   замок 41/41)

  AG1-D3    Witness-ветка                  P2       AG1                обвязать             \[ \]
            reaction_subscriber:301--316                               Proposal/Gate по     
            не под Gate-контрактом (только                             прецеденту E2.0-b    
            target-путь)                                                                    

  AG1-D4    `identity_traits` пусты после  P2       AG1                диагностический      \[ \]
            wait 12 --- резонанс не                                    круг: 3 команды      
            доезжает (гейт DECAY_EVERY /                                                    
            RAM WorkingMemory / ключ)                                                       

  AG1-D5    Аватар жив с hp=0              P2       body               ✅ ЗАКРЫТ 2026-09-04 (Шаг 6): корень = default body_state {'money':48} (не Death Guard/VitalState — они корректны); фикс {**BODY_STATE_HEALTHY, money:48}; зонд green, GC-00 4/4; производный хвост AVID-1 (аватар вне idle-снапшота) — открыт
            (`[FATE]`-лог каждый тик)               (ADR-131-контур)                        

  AG1-D6    Q4/Q5-рассинхрон имени модели  P3       LLM                `config`: одна       \[ \]
            (хвост S217)                                               строка               

  AG1-D7    `actor → player:` пустой хвост P2       AG1                трассировка          \[ \]
            при imp=0.8 (producer теряет                               producer-пути        
            текст при непустом префиксе)                                                    

  AG1-D8    ADR-O-377 не в реестре атласа  **P1**   AG1/cross          запись в атлас +     \[ \] →
            (cockpit-заглушка жива,                                    IMPACT-файл +        **в
            production-план TaskScheduler                              production-план      работе,
            не записан)                                                                     первый**

  AG1-D9    `affordance_facts_map`: гвард  P3       W-track (чужая)    уведомление          \[ \]
            стоит, поле у W2-владельца не                              владельцу            
            объявлено                                                                       

  AG1-D10   Ambient-шум в recall           P3       AG1/контент        Этап 1 (контентная   \[ \]
            (canned-фразы наполняют кэш)                               важность) --- план   
                                                                       контура памяти       

  AG1-D11   Witness-fallback «телепатия»   P2       AG1/perception     известная графа      \[ \]
            при пустых perceiving_npcs                                 perception_filter;   
            (реакция ВСЕХ NPC)                                         проверить прод-путь  
  ----------------------------------------------------------------------------------------------------

**Правило реестра:** долг без владельца и без следующего действия ---
запрещён (не «запомнить», а «кому и что»). Чужие зоны (D1, D9) ---
только уведомление, не чинить.

### §4b. Реестр долгов RE-сессии (M1b.3.x, 2026-09-0x; префикс RE-D)

  ----------------------------------------------------------------------------------------------------------------------------------
  ID      Долг                                                       P        Зона                  Действие                Статус
  ------- ---------------------------------------------------------- -------- --------------------- ----------------------- --------
  RE-D1   AG1-D1 сверка: reset_campaign переписан на RAM (M1b.4.2),  P2       RE (моя)              прогон new_game при     \[ \]
          `_cache` не существует --- либо долг устарел, либо падение                                M1b.3.3                 
          в другой точке                                                                                                    

  RE-D2   DialogueUpdateExtractor нулевые дельты (`trust=+0.0` в     **P1**   dialogue/AG1          трейс                   \[ \]
          живом логе; soliloquy-пары с нулями) --- LLM-зависимый                                    extractor→LLM→вес;      
          баг, диалоги НЕ пишут отношения                                                           кандидат отдельного     
                                                                                                    досье                   

  RE-D3   BeliefCrystallization: таргеты                             P2       identity              локализовать источник   \[ \]
          `npc=break_progress:resistance` (не npc_id) ---                                           trait_drift source_id   
          кристаллизация от не-агентов, шум в L2.5                                                                          

  RE-D4   FLEE-массовость: 6/6 NPC FLEE при fear=0.0 ---             P2       decision/калибровка   зонд score-разложения   \[ \]
          поведенческий дисбаланс скоринга                                                          FLEE                    

  RE-D5   `game_loop/__init__.py`: 20 ruff pre-existing (F401×14,    P3       game_loop             god-file-декомпозиция   \[ \]
          F821×4, W291) --- чужие зоны, не чинить в RE-сессии (закон                                (существующий долг)     
          №15)                                                                                                              

  RE-D6   scene_init W293×2 (:89/:366 докстринги) --- pre-existing,  P3       scene_init            при следующей правке    \[ \]
          тот же класс                                                                              файла                   

  RE-D7   Директива Мастера: каноническая схема campaign-bootstrap   P2       RE/authoring          ADR + схема             \[ \]
          JSON                                                                                                              
          (world/actors/facts/relationships/knowledge/motivations;                                                          
          CANON/INITIAL-разделение; «JSON описывает причины, не                                                             
          поведение»; секреты/beliefs/will --- рантайм, не авторинг)                                                        
          --- отдельный ADR после M1b.3.x                                                                                   

  RE-D8   S135-статик decision_hub:166 = мёртвый путь (зовёт         P2       RE                    зонд 3.5                \[ \]
          несуществующий get_relationship; state не имеет                                                                   
          relationship_store) + social_deltas standalone-копия ---                                                          
          finding 3.5-класс, судьба в M1b.3.5                                                                               
  ----------------------------------------------------------------------------------------------------------------------------------

-   Патч-формат: ТОЛЬКО БЫЛО/СТАЛО с фактическими якорями с диска (не
    paste-архив, не «описание словами» --- обе формы дали каскадные
    красные в M1b.3.2); сигнатуры/тела сверять инспекцией перед выдачей.

### §4c. Реестр долгов внешнего аудита V.0.5.3.9.6 (2026-09-04; префикс AUD-D)

> Метод: статический скан (mypy 2.3.1 по строгому конфигу, греп-паттерны
> random/wall-clock/silent-fail, TODO-инвентаризация, проверка
> call-sites). Каждый пункт привязан к файлу:строке. «Подтверждение» ---
> уже известный долг, независимо верифицированный.

  ---------------------------------------------------------------------------------------------------------------------
  ID        Долг                                       P      Зона                 Действие                    Статус
  --------- ------------------------------------------ ------ -------------------- --------------------------- --------
  AUD-D1    **mypy: 726 ошибок в backend/app**         P1     cross                триаж: сначала              \[ \]
            (строгий конфиг). Разбивка: no-untyped-def                             union-attr/attr-defined в   
            154, no-any-return 92, arg-type 84,                                    kernel-файлах (npc/,        
            union-attr 62, attr-defined 54, assignment                             game_loop/, events/,        
            50, unreachable 37, var-annotated 34.                                  memory/); CI-храповик       
            Hotspots: `game_loop/__init__.py` (63),                                «новых ошибок нет»; гигиену 
            `tick_orchestrator.py` (49),                                           чистить при                 
            `api/routes.py` (37), `llm/router.py`                                  god-file-декомпозиции       
            (20), `dm_agent.py` (20), `combat_math.py`                                                         
            (17). Runtime-класс (union-attr +                                                                  
            arg-type + attr-defined + call-arg ≈ 209)                                                          
            --- латентные краши/дрейф интерфейсов;                                                             
            остальное --- гигиена                                                                              

  AUD-D2    `social_subscriber.py:181–193` --- 5×      P1     events               None-инвариант в            ✅ ЗАКРЫТ 2026-09-04 (Шаг 5): self._rel_store провод + skip-путь; P97-верификатор зелёный
            union-attr                                                             конструкторе/подписчике +   
            `RelationshipWriteGate|None.apply`: тот же                             тест None-ветки             
            класс, что тик-падение Фазы 0.3                                                                    
            (NoneType.update); латентные краши                                                                 
            социального пути при None-гейте                                                                    

  AUD-D3    `agent_runner.py:79` вызывает              P2     llm/agents           реализовать                 \[ \]
            `LlmProvider.abort_generation` ---                                     `abort_generation` в        
            **метода не существует** в интерфейсе →                                провайдерах или убрать      
            AttributeError при первой попытке отмены                               мёртвый вызов               
            зависшего LLM-вызова; прямое звено N3                                                              

  AUD-D4    `npc_state.py:613–621` `_ALLOWED_WRITERS`: P1     npc                  зарегистрировать как A11;   \[ \]
            **4 wildcard-писателя** (`"*"`:                                        мигрировать 4 модуля;       
            npc_loader, phases.decision,                                           сузить `"*"` до полевых     
            phases.memory, life_engine) с TODO «Task                               записей (прецедент:         
            0.9 (миграция на StateApplicator)» ---                                 avatar_state_applicator)    
            Task 0.9 в roadmap не зарегистрирован;                                                             
            контракт «StateApplicator = единственный                                                           
            L2 writer» обойдён санкционированно                                                                

  AUD-D5    Legacy `RelationshipStore` (R1.4,          P2     RE (чужая)           решение судьбы в            \[ \]
            `services/memory/relationship_store.py`)                               M1b.5/M1b.3.5; минимум: TTL 
            **жив в прод-пути** (импорты:                                          → tick-based, except → Fail 
            `state_applicator.py:62`,                                              Loud                        
            `memory_manager.py:28`): (а) TTL 3600 c                                                            
            через `time.time()` + LRU в read-пути ---                                                          
            wall-clock ветка, кандидат replay-дрейфа                                                           
            (коорд. с P6/DEBT-QUIESCE); (б)                                                                    
            `except → тихий возврат {}` при битом JSON                                                         
            --- сброс данных отношений; (в) `_save`                                                            
            пишет legacy JSON на каждом save                                                                   

  AUD-D6    **DilemmaEngine --- мёртвый контур в       P2     social/MVP           канон `dilemmas.json` +     \[ \]
            проде**: `check_triggers()` вызывается                                 загрузчик в init_campaign,  
            каждый тик (mvp_tavern_controller), но                                 или исключить               
            `register_dilemma()` не вызывается никем                               check_triggers из тика      
            вне тестов (V8-MVP-18 подтверждён) ---                                                             
            `_dilemmas` пуст, дилеммы MVP недостижимы                                                          

  AUD-D7    `main.py` --- 34 `print()` живы (строки    P3     main                 заменить на logger (единый  \[ \]
            98--365, блок запуска llama-server). Долг                              фронт с LOG-GATE)           
            «print→logger ✅ закрыто» не соответствует                                                         
            текущему билду; стартап-путь, kernel не                                                            
            задет                                                                                              

  AUD-D8    `mypy.ini` повреждён: первая строка `ypy]` P3     CI                   фикс заголовка + гейт       \[ \]
            вместо `[mypy]` (обрезаны символы при                                  валидности конфига в        
            правке); mypy при этом конфиг применяет                                pre-commit                  
            --- проверить, какая секция реально                                                                
            читается, и зафиксировать целостность                                                              

  AUD-D9    `dm_phase.py:175–176` ---                  P3     game_loop            LLM-классификация полей или \[ \]
            `intent="dialogue"`, `tone=""`                                         mini-ADR об MVP-упрощении   
            захардкожены (TODO: LLM-classify): все                                                             
            диалоговые ходы пишутся в память/L1 с                                                              
            одинаковым intent и пустым tone ---                                                                
            метаданные памяти обеднены                                                                         

  AUD-D10   **Ambient-наблюдения не попадают в         P2     player_cognition/T   мост perception →           \[ \]
            ObservationLog**: единственные                                         observation_log (см. T9);   
            прод-писатели ---                                                      провенанс глаз/ухо/рот      
            `action_consequence_compiler.py:108`                                                               
            (действия игрока) и                                                                                
            `npc_confession_parser.py:95` (признания).                                                         
            `discovery_surface` секретов                                                                       
            `visual_cue`/`eavesdrop` не имеет                                                                  
            источника --- журнал расследования слеп к                                                          
            мирским уликам (жёстко режет MVP «секреты                                                          
            таверны»)                                                                                          

  AUD-D11   **TODO/FIXME: 75 маркеров в 48 файлах**    P3     cross                классификация по P4: бэклог \[ \]
            backend/app (roadmap отслеживал только 5 в                             / баг / мёртвый долг; 5     
            domain/). Заметные:                                                    domain-записей уже учтены   
            `json_persistence_adapter.py:31`                                                                   
            «временная заглушка --- save_npcs пишет в                                                          
            major_npcs.json (legacy путь)»;                                                                    
            `constants.py:307` B-01 Background                                                                 
            WorldTick --- в roadmap не зарегистрирован                                                         

  AUD-D12   Подтверждение известных: `combat_math.py`  ---    combat               уже в §Долг + MATH-8;       \[ \]
            --- 10 функций `rng or random`;                                        предложение: расширение     
            `impact_engine.py:124` `rng_seed=42`;                                  линтера → P18               
            клиентский d20 (`api/routes.py:582`) ---                                                           
            rng-бомба/П-7/П-11 актуальны;                                                                      
            `lint_kernel_rng` не видит (дефолт спрятан                                                         
            за Optional)                                                                                       
  ---------------------------------------------------------------------------------------------------------------------

## **Правило реестра --- то же, что §4a/§4b:** долг без владельца и без следующего действия запрещён; чужие зоны (D5) --- уведомление, не чинить.

## 5. MASTER TODO INVENTORY --- все известные и возможные направления

Это не приказ делать всё сразу. Это полный реестр работ, разделённый на
**сейчас / затем / потом / опционально**. `[ ]` означает незавершённое
направление; приоритет задаётся тегом.

### A. СЕЙЧАС --- блокирует качество причинной игры

-   [ ] **A0** Закрыть RE-01 **M1b.3.3--3.7** (ратифицированная
    лестница, активный фронт): 3.3+3.4 единый разрез
    `build_npc_snapshots`-гидратация из V2 (decay = produce Δ над
    снапшотом, не трогать) → 3.5 flat-readers-зонд (3 находки в §4b
    RE-D8) → 3.6 S128-разделение (вердикт (а) получен) → 3.7 греб-страж
    allowlist. Затем **A1**.
-   [ ] **A1** Закрыть RE-01 M1b.5: удалить мёртвый
    `apply_npc_state_updates` (0 вызовов, греп-доказательство) + судьба
    legacy-класса RelationshipStore и vestigial provider v2
    (REMOVED/фасад по факту readers).
-   [ ] **A2** Закрыть RE-01 M2/D: RelationshipEventSemantics + первый
    живой needs-writer через `update_needs` + формат RE-событий в
    causal-машинерии.
-   [ ] **A3** Закрыть G/H: Satisfaction + frustration через canonical
    store.
-   [ ] **A4** Закрыть K/removal-test и полигон M.
-   [ ] **A5** Подтвердить Фазу 0 живой игровой сессией: decisions,
    player coordinates, traversal.
-   [ ] **A6** Исправить/подтвердить DEBT-QUIESCE: детерминизм async
    interleaving для причинных цепочек.
-   [ ] **A7** Исправить DEBT-SLEEP-DELIVERY: intent → reachable sleep
    target → traversal → settled → sleep.
-   [x] **A8** ~~Проверить всех writers~~ **Writers закрыты (M1b.2
    вечные инварианты: 0 writer'ов вне Gate; сетка D3;
    decay-архитектурно)**; readers --- открытый фронт = A0 (fallback уже
    удалён 3.1; bootstrap 3.2). Остаток: греп-страж 3.7.
-   [ ] **A9** Проверить persistence/replay для новых
    relationship/memory данных (V2 RAM→projection→atomic_commit;
    replay-determinism на RE-данных не гонялся).
-   [ ] **A10** Сохранить IPT 45/45 + профильные линтеры после каждого
    изменения.
-   [ ] **A11** Закрыть wildcard-писателей «Task 0.9»: 4 модуля с `"*"`
    в `_ALLOWED_WRITERS` (`npc_loader`, `phases.decision`,
    `phases.memory`, `life_engine`) → миграция на StateApplicator,
    сужение до полевых записей (см. §4c AUD-D4).

### B. СЛЕДУЮЩЕЕ --- самый высокий gameplay ROI (фундамент E2.0 см. §2a)

-   [x] **B0** E2.0-c: каузальный экзамен A/B/C/D — ✅ S243, B0-CLOSED
    (вердикт владельца вербатим — §2a): 4 группы GREEN на GC-00-харнесе
    (causal_state_test, обе серии); guard'ы PK/beliefs — ADR-O-379/O-380
    (атлас L8.2/L14.5 + IMPACT-файлы). Production-форма TaskScheduler —
    AG1-D8p (ADR-O-377 занят Non-Blocking Intelligence), НЕ гейт B0.
    **Ворота для B1 открыты.**
-   [x] **B1** Experience → Conclusion — ✅ S247 (ADR-O-381, dormant ON):
    приёмка bc1_conclusion_test 6/6 GREEN на GC-00-харнесе. A (прод-путь:
    threat-событие → DeltaGate → EXPERIENCE_DELTA_COMMITTED → Фаза 9 →
    ConclusionGate → Store) — вывод `(maid_lusya, player, is_dangerous,
    conf=0.8, evidence=[event-id])` без текста/LLM; B — NO-VACUUM
    (инвариант владельца: без нового опыта → 0 эмитов, 0 записей);
    C — state-канал без события (concordance, conf=0.8); D — мимо
    ConclusionGate → ArchitecturalViolationError (замок); E — рестарт
    round-trip; OFF — dormant: store=None, scene_key=absent. Механизм
    доказан; потребитель — B2/BC-2. BC1_ENABLED default OFF.
-   [ ] **B2** Conclusion → Expectation.
-   [ ] **B3** Expectation → existing DecisionHub.
-   [ ] **B4** Repetition → generalization/crystallization.
-   [ ] **B5** Contradiction → belief revision.
-   [ ] **B6** Personal conclusion → testimony.
-   [ ] **B7** Testimony → recipient belief with provenance/confidence.
-   [ ] **B8** Derived social strategies:
    avoid/refuse/warn/seek/help/reconcile.
-   [ ] **B9** Learning from another NPC: experience →
    knowledge/skill/rule → changed behavior.
-   [ ] **B10** Self-model updates: «я могу/не могу», «я ошибся», «мне
    нужно изменить стратегию».
-   [ ] **B11** Social triangle / reputation emergence.
-   [ ] **B12** Long-horizon emergent scenarios and replay tests.

### C. ПСИХИКА --- после B, без взрыва количества флагов

-   [ ] **C1** Unified appraisal space.
-   [ ] **C2** Derived emotion regions.
-   [ ] **C3** Shared decay/accumulation/interference rules.
-   [ ] **C4** Mood as recent appraisal field, not a second emotion
    database.
-   [ ] **C5** Memory reactivation of affect.
-   [ ] **C6** Emotion/action voting over available actions.
-   [ ] **C7** Social contagion with distance/provenance/intensity
    bounds.
-   [ ] **C8** Expression dictionary separated from causal state.
-   [ ] **C9** Calibration laboratory + scenario corpus.

### D. PERCEPTION / EPISTEMICS

-   [ ] **D1** ObservationLayer/BeliefProjector.
-   [ ] **D2** Unified epistemic source-of-truth.
-   [ ] **D3** First-order NPC beliefs about world/agents.
-   [ ] **D4** Second-order ToM only where justified.
-   [ ] **D5** Surprise/prediction error as measurable epistemic
    discrepancy.
-   [ ] **D6** Belief revision with confidence, provenance and
    contradiction.
-   [ ] **D7** Prophecy/prediction vertical slice.
-   [ ] **D8** Epistemic persistence save/load.
-   [ ] **D9** Replay determinism for epistemic chains.

### HU. HUMOR / PLAY / COPING

-   [ ] **HU1** Humor contract + anti-Bond.
-   [ ] **HU2** Incongruity from NPC expectation/prediction error.
-   [ ] **HU3** Resolution / Script Opposition / Logical Mechanism.
-   [ ] **HU4** Benignity and social safety; no `trust → humor`
    shortcut.
-   [ ] **HU5** Dynamic humor disposition from personality +
    experience + current state + relationship/epistemic context; no
    fixed `humor_level`.
-   [ ] **HU6** Humor-as-coping under acute and chronic pressure.
-   [ ] **HU7** Humor production as opportunity → audience model →
    expected reaction → risk/benefit → attempt.
-   [ ] **HU8** Failed humor → experience/memory/self-model/relationship
    consequences.
-   [ ] **HU9** Social transmission with provenance and partial
    observation.
-   [ ] **HU10** Long-horizon temporal adaptation.
-   [ ] **HU11** LLM only as Language Layer; runtime decides causal
    humor status.
-   [ ] **HU12** Chronicle/Inspector causal explanation.
-   [ ] **HU13** Calibration corpus: harmless, affiliative,
    self-directed, hostile, absurd, failed and coping-humor scenarios.


### AV. PLAYER AVATAR / AGENCY

-   [ ] **AV1** Canonical avatar actor contract and agency boundary.
-   [ ] **AV2** Persistent psyche; eliminate fallback personality constants.
-   [ ] **AV3** Values/norms/preferences as appraisal inputs, not hardcoded
    veto tables.
-   [ ] **AV4** Unified AvatarActionResolver over pressure, values,
    preferences, affect/trauma, body, trust, relationship and epistemics.
-   [ ] **AV5** Social/romantic/sexual agency boundaries using general
    preference + appraisal machinery.
-   [ ] **AV6** Player trust / relationship-to-controller as history-bearing
    state, only if calibration validates it.
-   [ ] **AV7** Negotiation and executable counter-offers.
-   [ ] **AV8** Inner voice/private channel and deterministic narration
    before optional LLM verbalization.
-   [ ] **AV9** Resistance Medium lifecycle and rare causal activation.
-   [ ] **AV10** Escalation/recovery/conditioning; BROKEN is not game over.
-   [ ] **AV11** Limited autonomous agency without a second NPC stack.
-   [ ] **AV12** Avatar memory/experience/self-model integration.
-   [ ] **AV13** Avatar epistemics and player-vs-avatar knowledge
    asymmetry.
-   [ ] **AV14** Avatar participation in ordinary relationships/social
    consequences.
-   [ ] **AV15** Avatar + humor/coping integration.
-   [ ] **AV16** Chronicle/Inspector causal explanation.
-   [ ] **AV17** AV-GC-01...12 vertical closure.
-   [ ] **AV18** Calibration and explicit scope ceiling.

### E. BODY / HOMEOSTASIS / EMBODIED AGENCY

-   [ ] **E1** Needs writer via RE-01 M2/D.
-   [ ] **E2** Energy/hydration/nutrition → fatigue → sleep → recovery.
-   [ ] **E3** Pain/injury → affordance/constraint → action.
-   [ ] **E4** Temperature and environmental pressure.
-   [ ] **E5** Ensure body state is not flat/frozen in production
    snapshots.
-   [ ] **E6** Intent → commitment → execution → verification.
-   [ ] **E7** Stale intent cancellation.
-   [ ] **E8** Single owner of behavior.
-   [ ] **E9** Bounded conversation and cooldowns.
-   [ ] **E10** Valid idle/settled state; eliminate perpetual
    movement/chat.
-   [ ] **E11** Sleep delivery and alternative sleep affordances.
-   [ ] **E12** Death/recovery semantics and remaining DeathState TODOs.

### F. WORLD / OBJECTS / AFFORDANCES

-   [x] **F1** W2 AffordanceResolver --- ✅ S232/ADR-O-372 (24 теста).
-   [~] **F2** W3: домен+стор+спавнер ✅ (S237/ADR-O-376, live=18);
    causal writer = G3 --- не реализован, следующий шаг W-трека.
-   [ ] **F3** Caller guard / single writer --- с первым легальным
    writer в G3 (writers сейчас 0; enforcement-ради-enforcement
    запрещён).
-   [ ] **F4** W4 embodied state: pose, locomotion, grasp, attachment.
-   [ ] **F5** Objects become actionable affordances for NPC reasoning.
-   [ ] **F6** Furniture/tasks/containers/resources integrated into
    action selection.
-   [ ] **F7** W5--W9 presentation projector/rendering contracts.
-   [ ] **F8** Renderer remains pure consumer.
-   [ ] **F9** Object consequences enter Chronicle/Memory when
    semantically relevant.

### G. TIME / IDENTITY / LINEAGE

-   [ ] **G1** WorldChronicle.
-   [ ] **G2** Three time levels and consistency rules.
-   [ ] **G3** Persistence across save/load.
-   [ ] **G4** Identity continuity through long campaigns.
-   [ ] **G5** Lineage/ancestry/ownership history.
-   [ ] **G6** Visual aging after lineage.
-   [ ] **G7** Historical consequences: old actions remain legible in
    current world.

### H. SOCIETY

-   [ ] **H1** Factions.
-   [ ] **H2** Reputation emerging from individual testimony + observed
    behavior.
-   [ ] **H3** Economy.
-   [ ] **H4** Politics/power relations.
-   [ ] **H5** Institutions/roles/authority.
-   [ ] **H6** Cooperation, coalition and exclusion.
-   [ ] **H7** Social norms and norm violations.
-   [ ] **H8** Sanctions/rewards/boycotts.
-   [ ] **H9** Group-level memory without replacing individual memory.
-   [ ] **H10** Population-scale stability: 50+ NPC × 30+ min.

### I. MEMETIC / CULTURAL

-   [ ] **I1** MEMETIC-01.
-   [ ] **I2** MEMETIC-02.
-   [ ] **I3** MEMETIC-03.
-   [ ] **I4** Beliefs/rumors mutate through transmission.
-   [ ] **I5** Cultural norms emerge from repeated social reinforcement.
-   [ ] **I6** Competing narratives and source credibility.

### J. BOUNDED RATIONALITY

-   [ ] **J1** Belief Layer prerequisite.
-   [ ] **J2** Information/resource/cost model `U_M = I·R·U − C`.
-   [ ] **J3** Attention limits.
-   [ ] **J4** Memory retrieval cost/selection.
-   [ ] **J5** Action evaluation budget.
-   [ ] **J6** NPC-specific rationality/resource limits.
-   [ ] **J7** Validate that bounded rationality creates plausible
    mistakes rather than random stupidity.

### K. ACTIVE INFERENCE / HABITS

-   [ ] **K1** Define the actual world model before adding heavy
    mathematics.
-   [ ] **K2** Prediction → candidate futures → expected consequence →
    action.
-   [ ] **K3** Habit formation from repeated successful action
    sequences.
-   [ ] **K4** Habit decay/interference.
-   [ ] **K5** Exploration vs exploitation.
-   [ ] **K6** Information-seeking as an action.
-   [ ] **K7** Performance benchmark; do not let active inference become
    the tick bottleneck.

### L. COUNTERFACTUAL / REFLECTION

-   [ ] **L1** Store decision/outcome pairs sufficient for «what if».
-   [ ] **L2** Counterfactual alternative generation.
-   [ ] **L3** Regret / relief / guilt / confidence as derived
    appraisals, not flags.
-   [ ] **L4** Counterfactual impact on future strategy.
-   [ ] **L5** Bound computation so NPCs do not endlessly simulate
    futures.

### M. MEMORY / SELF / LEARNING

-   [ ] **M1** EventMemory persistence.
-   [ ] **M2** Belief persistence.
-   [ ] **M3** Relationship persistence.
-   [ ] **M4** Replay exactness after save/load.
-   [ ] **M5** Memory salience and decay calibration.
-   [ ] **M6** Consolidation: episodic experience → durable knowledge.
-   [ ] **M7** Self-model / identity changes from experience.
-   [ ] **M8** Skill/knowledge acquisition from social teaching.
-   [ ] **M9** Forgetting that is selective, not arbitrary.
-   [ ] **M10** False/uncertain memory only if epistemic design requires
    it.

### N. DIALOGUE / LANGUAGE / EXPRESSION

-   [ ] **N1** DialogueQueue production-path audit/closure.
-   [ ] **N2** SpeechScheduler pacing/dedup in actual main path.
-   [ ] **N3** LLM timeout/cancellation so one hung call cannot block
    execution.
-   [ ] **N4** Preserve proposition on DialogueRequest failure; no
    silent dict fallback.
-   [ ] **N5** Dialogue grounded in actual belief/memory/relationship
    state.
-   [ ] **N6** NPC can disagree with its own prior statement when belief
    changes.
-   [ ] **N7** NPC can cite source/provenance («я видел», «мне сказал
    X»).
-   [ ] **N8** NPC can deliberately withhold information.
-   [ ] **N9** NPC can lie/deceive when world/social conditions justify
    it.
-   [ ] **N10** Expression varies by personality/appraisal without
    changing causal truth.

### O. ACTION / SOCIAL BEHAVIOR

-   [ ] **O1** Rich action vocabulary: approach, leave, refuse, help,
    accuse, warn, gossip, reconcile, negotiate, teach, learn, observe,
    hide, trade, defend, betray.
-   [ ] **O2** Affordance-based fallback when preferred action
    unavailable.
-   [ ] **O3** No hardcoded emotion→action rules.
-   [ ] **O4** Action selection accounts for opportunity, distance,
    risk, allies and relationship.
-   [ ] **O5** Social actions create consequences that feed
    memory/relationship.
-   [ ] **O6** NPC recognizes when another NPC is talking to someone
    else / unavailable.
-   [ ] **O7** Turn-taking, attention and conversational ownership.
-   [ ] **O8** Spatial/social awareness: who is present, who can hear,
    who can intervene.
-   [ ] **O9** Persistent refusal/avoidance should emerge from
    expectations, not flags.

### P. HARDENING / QUALITY / PERFORMANCE

-   [ ] **P1** DEBT-QUIESCE.
-   [ ] **P2** Remaining god-file decomposition.
-   [ ] **P3** mypy --strict outside spatial layers.
-   [ ] **P4** Remaining TODO/FIXME classification.
-   [ ] **P5** Kernel RNG audit.
-   [ ] **P6** wall-clock audit.
-   [ ] **P7** silent-failure audit.
-   [ ] **P8** frontend-isolation audit.
-   [ ] **P9** L1 append-only audit.
-   [ ] **P10** Epistemic boundary audit.
-   [ ] **P11** Replay determinism.
-   [ ] **P12** 1000-tick LLM-free survival test.
-   [ ] **P13** Long-horizon drift tests.
-   [ ] **P14** Performance budget for 6/50/100+ NPC.
-   [ ] **P15** Memory growth / compaction strategy.
-   [ ] **P16** Async cancellation / executor saturation.
-   [ ] **P17** mypy-триаж по AUD-D1: 726 ошибок → политика
    «runtime-классы (union-attr/arg-type/attr-defined) в kernel-файлах
    первыми»; CI-храповик «не хуже текущего»; гигиена (no-untyped-def)
    --- попутно при god-file-декомпозиции. Не «починить все» ---
    осознанный порядок.
-   [ ] **P18** `lint_kernel_rng` v2: AST-запрет паттернов
    `Optional[random.Random] = None` → `_rng = rng or random` и
    `rng_seed: int = 42` --- RNG-бомбы за Optional-дефолтами невидимы
    текущему линтеру (П-7, AUD-D12).

### Q. CALIBRATION / OBSERVABILITY

-   [ ] **Q1** Scenario corpus for body/social/epistemic behavior.
-   [ ] **Q2** Differential tests for one causal change.
-   [ ] **Q3** DriftLab 200/1000/10000 tick profiles.
-   [ ] **Q4** Social chain traces with provenance.
-   [ ] **Q5** Separate «mechanism works» from «content is good».
-   [ ] **Q6** Metrics that detect living behavior without confusing
    motion with causality.
-   [ ] **Q7** Never allow observability to mutate state.

### R. CONTENT / WORLD DESIGN

-   [ ] **R1** Tavern vertical slice with meaningful tasks.
-   [ ] **R2** NPC schedules and role obligations.
-   [ ] **R3** Food/resources scarcity.
-   [ ] **R4** Furniture/object affordances.
-   [ ] **R5** Secrets and social consequences.
-   [ ] **R6** Relationships with asymmetric preferences.
-   [ ] **R7** Teaching/learning scenes.
-   [ ] **R8** Betrayal/reconciliation scenarios.
-   [ ] **R9** Reputation/social exclusion scenarios.
-   [ ] **R10** Long-lived NPC stories.
-   [ ] **R11** Campaign/world onboarding.
-   [ ] **R12** Dark-fantasy/female-targeted layer if product direction
    remains.

### S. TOOLING / SDK / EDITOR

-   [ ] **S1** Map Editor smart validation.
-   [ ] **S2** Visual design of social graphs.
-   [ ] **S3** Visual design of factions/relationships.
-   [ ] **S4** Visual design of world affordances.
-   [ ] **S5** Campaign/content SDK.
-   [ ] **S6** Scenario runner for social experiments.
-   [ ] **S7** Replay/trace viewer.
-   [ ] **S8** Calibration dashboard.
-   [ ] **S9** Authoring tools for secrets, norms, jobs and
    relationships.

### T. UI / PRESENTATION

-   [ ] **T1** PresentationProjector.
-   [ ] **T2** Renderer pure-consumer compliance.
-   [ ] **T3** Player goal overlay.
-   [ ] **T4** Journal tabs and temporal/social history presentation.
-   [ ] **T5** Exit-tavern/modal flow.
-   [ ] **T6** Name recognition pacing.
-   [ ] **T7** NPC movement speed / readable staging.
-   [ ] **T8** Make social consequences observable without exposing
    hidden variables.
-   [ ] **T9** Ambient-наблюдения → ObservationLog + журнал игрока:
    автофиксация `visual_cue`/`eavesdrop` (в т.ч. «рваный» текст по
    clarity), провенанс глаз/ухо/рот, маркер NEW (см. §4c AUD-D10;
    UI-консультация сессии 2026-09-04, пункт №2).

### U. ОТЛОЖИТЬ --- намеренно не делать пока

-   [ ] Полноценный Active Inference как отдельный тяжёлый engine.
-   [ ] Counterfactual reasoning.
-   [ ] Большую Theory-of-Mind систему второго порядка.
-   [ ] Политическую симуляцию высокого уровня.
-   [ ] Полный economy simulation.
-   [ ] SDK до стабилизации world/relationship contracts.
-   [ ] Массовую оптимизацию до появления реального bottleneck.
-   [ ] Новые десятки эмоций как отдельные классы.
-   [ ] «Любовь», «влюблённость», «адаптация», «месть» как state
    entities без anti-Bond доказательства.
-   [ ] Контентный взрыв до замыкания причинных циклов.

### V. ДОПОЛНИТЕЛЬНЫЕ ДОЛГОСРОЧНЫЕ ВОЗМОЖНОСТИ

-   [ ] **V1** Group emotions / crowd dynamics.
-   [ ] **V2** Collective memory / traditions.
-   [ ] **V3** Reputation markets / information brokers.
-   [ ] **V4** Institutional memory.
-   [ ] **V5** Generational knowledge transfer.
-   [ ] **V6** Language/cultural drift.
-   [ ] **V7** Emergent norms and taboo formation.
-   [ ] **V8** Multi-agent coalition formation.
-   [ ] **V9** Resource-driven social stratification.
-   [ ] **V10** Historical causality over months/years of simulation.
-   [ ] **V11** NPC-specific life projects and legacy.
-   [ ] **V12** World-level narrative emergence from distributed memory.

### Рекомендуемый порядок из всего MASTER TODO

`A1–A11 → GC-00/01 + NEG-01…06 → B1–B12 → C1–C9 + D1–D9 → E/F hard runtime + GC-03…11 → AV1–AV4 + AV-GC-01…05 → AV5–AV10 + AV-GC-06…10 → HU1–HU5 → HU6–HU13 + GC-29…40 → AV11–AV16 + AV-GC-11…16 → GC-17…24 → G → H/I → J/K → L → M/N/O enrichment → GC-25…28 + SCALE → P/Q hardening at scale → R/S/T content/tooling → V long-horizon`.

**Почему AV разбит на два прохода:** сначала нужно оживить уже существующие psyche/values/resistance и получить короткий L3 vertical. Затем можно включать inner voice, negotiation, recovery и humor integration. Полная avatar epistemics и limited autonomy идут только после того, как общие memory/epistemic/relationship substrates реально production-connected. Это предотвращает создание «второго ENIGMA» внутри player actor.

Ключевой принцип: **не строить систему для названия явления, если уже
существует более общий механизм, из которого явление может быть
выведено.**

**Avatar principle:** `PLAYER INPUT ≠ AVATAR WILL`. Игрок инициирует intent,
но avatar appraisal/resistance остаётся частью causal runtime. Класс,
происхождение, ценности, предпочтения, страх, отношения, память и опыт не
являются декоративными тегами: если они заявлены как игровые свойства, они
должны иметь путь `state → appraisal → action → consequence → future state`.
При этом аватар не получает отдельный cognitive stack, если то же явление
уже может быть выражено общим механизмом NPC.

------------------------------------------------------------------------

------------------------------------------------------------------------

## 5a. GAMEPLAY CLOSURE --- обязательный слой доказательства

### Зачем этот раздел существует

Текущий роадмэп хорошо доказывает наличие отдельных механизмов,
контрактов и линтеров, но этого недостаточно для утверждения **«игра
работает»**. SUPERBOX отвечает на вопрос «механизм вообще способен
работать?», AUD --- «есть ли дефект в production-коде?», а GAMEPLAY
Closure отвечает на более строгий вопрос:

> **Может ли игрок вызвать причинную цепочку через настоящий
> production-путь, переживает ли она тик, меняет ли состояние NPC/мира,
> влияет ли на следующий выбор и становится ли следствие наблюдаемым
> игроком?**

Поэтому gameplay-тесты не заменяют IPT/SUPERBOX/AUD. Они закрывают
отсутствующий уровень доказательства --- **L3: player → runtime →
consequence → future behavior → observable result**.

### 5a.1 Четыре уровня доказательства

  -----------------------------------------------------------------------
  Уровень           Вопрос            Тип проверки      Что НЕ доказывает
  ----------------- ----------------- ----------------- -----------------
  L0                Контракт          schema / type /   runtime
                    существует?       static            

  L1                Механизм работает unit / SUPERBOX   production
                    изолированно?                       reachability

  L2                Production-путь   integration /     полноценная
                    вызывает          canary            игровая история
                    механизм?                           

  **L3**            Игрок может       **vertical        художественное
                    вызвать цепь и    gameplay test**   качество
                    получить                            
                    устойчивое                          
                    следствие?                          

  L4                Человек может     Chronicle /       внутреннюю
                    понять причинную  Inspector / UI    корректность
                    цепь?                               вместо runtime
  -----------------------------------------------------------------------

**Правило:** feature нельзя считать «закрытой» только по L1. Для
значимой игровой механики требуется минимум L2 + L3; для систем, которые
должны быть видимы игроку, также L4.

### 5a.2 Канонический `TavernGameplayHarness`

Не создавать второй simulation engine. Harness должен вызывать
существующий production runtime.

Минимальный интерфейс сценария:

-   `new_game(seed)`
-   `spawn_npc(...)`
-   `spawn_world_object(...)`
-   `move_player(...)`
-   `player_action(...)`
-   `advance_ticks(n)`
-   `inspect_npc(...)`
-   `inspect_world(...)`
-   `get_chronicle(...)`
-   `save_game() / load_game()`
-   `replay_from_seed(...)`

Harness обязан проходить через настоящий `TickOrchestrator`,
`NpcTickPipeline`, `DecisionHub`, WorldSnapshot,
EventCompiler/ProjectionEngine и зарегистрированных subscribers.
Запрещено вручную вызывать внутренний writer, чтобы «доказать» его
работу.

### 5a.3 GAMEPLAY Acceptance Tests

-   [ ] **GC-00 --- Game is actually alive.** 6 NPC tavern, 100 LLM-free
    ticks. За время прогона существуют decisions, movement/settled
    states, physiological changes, observations, memory/experience
    events и relationship activity там, где имеются соответствующие
    причины. Один seed даёт один и тот же causal history. Нулевые
    counters сами по себе не считаются доказательством смерти ---
    проверять production trace.

-   [ ] **GC-01 --- Real Tick Vertical Slice.**
    `new_game → real tick → snapshot → decision → execution → verification`.
    Проверяет, что harness не обходит production path и что один NPC
    реально проходит полный цикл.

-   [ ] **GC-02 --- Player action → world consequence.** Игрок выполняет
    действие над объектом; объект меняет canonical state; изменение
    попадает в causal/event слой и остаётся после следующего тика.

-   [ ] **GC-03 --- Observation → Experience/Memory → changed
    behavior.** NPC реально видит/слышит событие в пределах perception
    rules; observation создаётся; experience/memory сохраняется;
    следующий выбор NPC отличается от baseline.

-   [~] **GC-04 --- Experience → Conclusion → Expectation → Decision.**
    Повторяемое событие порождает машино-пригодный conclusion;
    conclusion меняет expectation; expectation входит в существующий
    DecisionHub; NPC выбирает действие, которое без этого history не
    выбрал бы. **S243: сегмент E2-state→DecisionHub доказан**
    (causal_state_test A/C — флип argmax от авторизованной дельты без
    текста); сегменты Conclusion/Expectation — BC-1/BC-2, открыты
    (терминологическая лестница §2a). Full-cell закрытие — после BC-3.

-   [ ] **GC-05 --- Testimony → Belief → third-party behavior.** A лично
    переживает событие, сообщает B; B учитывает
    provenance/source/confidence и меняет belief; C или B демонстрирует
    поведенческое следствие.

-   [x] **GC-06 --- Same world, different history → different
    behavior.** Два прогона стартуют из одинакового мира и seed, но
    получают различную историю. При одинаковом текущем snapshot
    поведение должно расходиться именно из-за сохранённой
    history/epistemic state. ✅ S243: causal_state_test — одна
    WorldSnapshot+seed, единственная переменная = авторизованная дельта
    истории; argmax Люси расходится (flee vs call_for_help); Горан —
    state-эффект в скорах при H1-ландшафте (флип-порог не пересечён —
    свойство натуры, не разрыв). LIMITATION: decision-level (BC-12 —
    материализация движения).

-   [ ] **GC-07 --- Same event, different observation → different
    belief/behavior.** Два NPC находятся в одной сцене, но один имеет
    доступ к событию, другой нет (или получает иной clarity/provenance).
    Они не должны автоматически получать одинаковое знание.

-   [ ] **GC-08 --- World object → affordance → action → world change.**
    NPC обнаруживает доступный объект/ресурс, получает affordance,
    принимает действие, достигает target, выполняет interaction и
    изменяет объект.

-   [ ] **GC-09 --- Body → constraint → action → recovery.** Дефицит
    energy/hydration/sleep/pain становится homeostatic pressure,
    ограничивает affordances/decision, вызывает подходящее действие, а
    recovery меняет body state обратно. Проверять реальным тиком, а не
    прямой записью body-поля.
    GC-09 — Body → constraint → embodied action → recovery.

    Дефицит:

        energy
        hydration
        nutrition
        sleep
        pain / injury

    становится canonical homeostatic pressure.

    Pressure:

        ограничивает доступные affordances
        ↓
        меняет Decision landscape
        ↓
        вызывает embodied action
        ↓
        требует реального достижения world affordance
        ↓
        запускает recovery runtime
        ↓
        изменяет BodyState.

    Проверять реальным production tick:

        Body
        → Decision
        → Commitment
        → World target
        → Traversal
        → Settled
        → Recovery
        → changed Body.

    Запрет:

        прямой test-write body field
            → считать доказательством recovery.

-   [ ] **GC-10 --- Sleep delivery.** NPC получает sleep pressure,
    выбирает reachable sleep target, проходит traversal, становится
    settled и только после этого sleep state начинает реально снижать
    pressure. Отдельно проверить альтернативные sleep affordances.
    GC-10 — Sleep Vertical Slice.

    NPC:

        accumulates sleep pressure
            ↓
        experiences changed constraints /
        action landscape
            ↓
        selects recovery intent
            ↓
        discovers valid sleep affordance
            ↓
        validates reachable target
            ↓
        traverses
            ↓
        becomes settled
            ↓
        enters sleep state
            ↓
        undergoes deterministic recovery
            ↓
        can be interrupted by relevant perception/threat
            ↓
        resumes or exits sleep
            ↓
        wakes with causally derived BodyState.

    Acceptance:

        same seed + same world + same sleep history
            → same sleep/recovery outcome.

        interrupted sleep
            ≠
        uninterrupted sleep of equal nominal duration,
        если это различие имеет доказанную causal работу.

    Отдельно проверить альтернативные recovery affordances:

        BED
        HAMMOCK
        GROUND
        SHELTER

    только если они действительно отличаются по доступным recovery conditions,
    а не ради контентного enum.


-   [ ] **GC-11 --- Relationship event → state → future social action.**
    Реальное социальное событие проходит RelationshipEventSemantics →
    canonical writer → snapshot → DecisionHub и меняет последующее
    социальное действие.

-   [ ] **GC-12 --- Repeated evidence → generalization.** Одного эпизода
    недостаточно для устойчивого обобщения. Повторяемая evidence
    усиливает conclusion/expectation; одно или несколько противоположных
    наблюдений ослабляют или ревизуют его.

-   [ ] **GC-13 --- Contradiction → belief revision.** NPC ожидает X,
    получает наблюдаемое not-X, получает prediction error/surprise,
    пересматривает belief/expectation и демонстрирует новое поведение.

-   [ ] **GC-14 --- Self-learning.** NPC совершает действие, получает
    результат, формирует изменение self-model/knowledge/skill, после
    чего повторная ситуация вызывает иной выбор.

-   [ ] **GC-15 --- Social triangle.** A влияет на B, B взаимодействует
    с C; C получает доступную ему информацию/социальное событие.
    Изменение отношений A--C или B--C возникает из общих механизмов, без
    специального triangle flag.

-   [ ] **GC-16 --- Long-horizon story.** Минимум 100--1000 тиков для
    нескольких сценариев: `оскорбление→память→избегание`,
    `обман→вывод→слух→осторожность`,
    `помощь→благодарность→ответная помощь`, `обучение→новое действие`.
    Не допускается perpetual movement/chat или полное стирание причинной
    истории.

-   [ ] **GC-17 --- Competing writers / state integrity.** Два источника
    пытаются изменить одно canonical поле. Разрешён только
    авторизованный writer; wildcard обход должен быть невозможен.
    Проверяется не только grep, но и реальным runtime-конфликтом.

-   [ ] **GC-18 --- Wall-clock independence.** Один и тот же
    seed/scenario запускается с различными реальными задержками между
    тиками. Причинный результат и replay должны совпадать. `time.time()`
    не должен менять gameplay state.

-   [ ] **GC-19 --- Async/interleaving determinism.** Один сценарий
    запускается несколько раз при разных допустимых задержках/порядках
    async completion. Проверяется canonical causal history, commitment
    terminal states и micropositions. Если различия допустимы, они
    должны быть явно отделены от причинно значимого state.

-   [ ] **GC-20 --- Persistence continuation.** Сохранить игру в
    середине причинной цепи, загрузить и продолжить. NPC memory,
    beliefs, relationships, body, world objects и identity должны
    продолжить историю без reset/duplicate application.
    - [ ] GC-20 — Temporal Recovery → Future Behavior.

    Два прогона имеют:

        одинаковый world snapshot
        одинаковый seed
        одинаковый текущий внешний input

    но различную temporal recovery history.

    Проверить:

        recovery history
            → canonical body/perception state
            → changed decision landscape
            → different future behavior.

    Никакого random modifier.

    Расхождение должно быть объяснимо через Chronicle / Snapshot /
    causal provenance.

-   [ ] **GC-21 --- Replay exactness.** Один seed + одинаковый
    input/event stream → одинаковые snapshots, causal events и terminal
    outcomes. Сравнивать не только финальные числа, но и идентичность
    причинной цепочки.

-   [ ] **GC-22 --- Ambient discovery reachability.** NPC/player
    находится в зоне `visual_cue` или `eavesdrop`; observation реально
    появляется в ObservationLog с provenance `eye/ear`; соответствующий
    secret становится discoverable и появляется в журнале игрока.
    Проверить также низкую clarity/«рваный» текст.

-   [ ] **GC-23 --- Dilemma reachability.** MVP dilemma действительно
    загружается в production `init_campaign`, попадает в registry и
    может быть вызвана игровым условием. Тест обязан падать, если
    `check_triggers()` жив, но `_dilemmas` пуст.

-   [ ] **GC-24 --- LLM failure isolation.** LLM
    задерживается/падает/отменяется. WorldTick не зависает бесконечно,
    bounded worker освобождается, быстрый мир продолжает жить, а
    LLM-originated proposal не становится SSOT. Отдельно покрыть путь
    отмены `abort_generation`.

-   [ ] **GC-25 --- Chronicle causal trace.** Для реальной истории
    Chronicle показывает минимум:
    `что произошло → что изменилось → почему → что изменилось в будущем поведении`.
    Chronicle читает trace/state и не мутирует их.

-   [ ] **GC-26 --- NPC Inspector explanation.** Для текущего решения
    NPC можно получить provenance-путь: доступные
    affordances/constraints → relevant
    memory/belief/expectation/relationship/body pressure → выбранное
    действие. Запрещено использовать LLM как источник объяснения
    причинности.

-   [ ] **GC-27 --- Player-visible consequence.** Причинная цепочка,
    которую engine считает успешной, имеет наблюдаемый результат в
    реальном frontend: изменение
    положения/объекта/действия/диалога/отношения или иной допустимый
    presentation effect. Renderer остаётся pure consumer.

-   [ ] **GC-28 --- Full Tavern Living World.** 6 NPC, player, world
    objects, relationships, secrets, body pressures и ambient
    observations. Минимум 200 тиков. Есть несколько независимых
    причинных цепочек, которые не сливаются в одну глобальную реакцию.
    Сценарий завершается без silent-fail и с сохранением причинной
    истории.

-   [ ] **GC-29 --- Humor perception vertical.** NPC has an expectation,
    observes an incongruent event, finds a valid resolution and produces
    amusement. Same event without resolution remains non-humorous.

-   [ ] **GC-30 --- Same event, different NPC.** Identical event
    produces amusement for one NPC, confusion/neutrality/offense/threat
    for another, explained by their existing expectation, appraisal,
    relationship, knowledge and current state.

-   [ ] **GC-31 --- Temporal humor plasticity.** Same NPC + same event
    at different points in history produces different humor outcomes
    because relevant experience/state/relationship changed. No direct
    humor-field mutation.

-   [ ] **GC-32 --- Benign violation.** Same norm violation with
    different audience/context yields different outcomes; low trust is
    not itself sufficient to suppress all humor.

-   [ ] **GC-33 --- Coping humor under acute pressure.** NPC faces a
    difficult/impossible immediate situation; humor becomes an available
    response only when appraisal/motivation/ social context support it,
    and the resulting action has causal consequences.

-   [ ] **GC-34 --- Coping humor under chronic pressure.** Long-running
    stress/uncertainty changes humor propensity or form through
    accumulated pressure/memory/self-model; no timer, no permanent
    `humor_mode`.

-   [ ] **GC-35 --- Failed humor.** A joke/attempt is misunderstood or
    rejected; listener and speaker acquire appropriate experience, and
    future expectations/relationship behavior can differ.

-   [ ] **GC-36 --- Audience model.** NPC chooses whether/how to joke
    differently depending on who can hear, relationship, status, threat
    and expected reaction.

-   [ ] **GC-37 --- Social transmission of humor.** A jokes, B hears, C
    does not; B can retain testimony/experience while C does not gain
    the information without a causal transmission.

-   [ ] **GC-38 --- Humor production is unscheduled.** Over a long
    LLM-free run NPCs do not emit jokes merely because N ticks elapsed;
    every production attempt has a causal trigger.

-   [ ] **GC-39 --- Humor observability.** Chronicle/Inspector
    reconstructs why a humor reaction or attempt happened without using
    LLM as causal authority.

-   [ ] **GC-40 --- Humor replay/persistence.** Humor-related
    experience, disposition-relevant history and social consequences
    survive save/load and reproduce under replay.



### 5a.3b Avatar gameplay closure

-   [ ] **AV-GC-01** Values differential: same command, same world, different
    avatar values/norms → different accept/modify/refuse outcome.
-   [ ] **AV-GC-02** Class/culture priors: different initialized priors may
    produce different appraisal, but repeated experience can change the
    outcome without rewriting class identity.
-   [ ] **AV-GC-03** Social preference differential: same flirt/social intent,
    different preference/comfort state → different response without a
    hardcoded action table.
-   [ ] **AV-GC-04** Pressure vs value differential: identical action can be
    resisted for fear/pressure by one history and for moral/identity reasons
    by another; Chronicle distinguishes the causes.
-   [ ] **AV-GC-05** Unified resolver: WillpowerGate, CharacterFilter and
    affect/trauma produce one canonical action resolution, not competing
    execution paths.
-   [ ] **AV-GC-06** Negotiation: refusal generates an executable counter-offer
    and player can accept it through the production path.
-   [ ] **AV-GC-07** Player trust differential: same command after respectful
    versus coercive history yields different acceptance/appraisal where the
    model predicts it.
-   [ ] **AV-GC-08** Resistance lifecycle: conflict has trigger, escalation,
    resolution and aftermath; no one-input reset.
-   [ ] **AV-GC-09** Recovery: stress/strain can recover through causal factors;
    BROKEN/CONDITIONED produce long-term gameplay rather than game over.
-   [ ] **AV-GC-10** Inner voice reachability: a real conflict reaches private
    avatar narration through API/frontend; DTO-only hooks fail the test.
-   [ ] **AV-GC-11** Avatar epistemic asymmetry: player and avatar can possess
    different information/beliefs and the avatar acts on its own belief.
-   [ ] **AV-GC-12** Avatar social consequence: avatar-modified/refused action
    changes an NPC relationship and later changes the avatar's available
    social outcomes.
-   [ ] **AV-GC-13** Avatar humor/coping: identical pressure can yield coping
    humor, panic, avoidance or defiance depending on avatar history/state.
-   [ ] **AV-GC-14** Save/load/replay: psyche, trust, memories, scars and
    conditioning relevant to later decisions survive persistence and replay.
-   [ ] **AV-GC-15** Limited autonomy: only defined extreme/idle states can
    generate autonomous avatar actions; normal input remains player-originated.
-   [ ] **AV-GC-16** No second stack: avatar uses canonical stores/writers;
    no duplicate memory/relationship/epistemic/world writer exists.

### 5a.4 Differential tests --- самые важные тесты против «пустой симуляции»

-   [x] **DIFF-01 --- History differential.** `World_0 + History_A` и
    `World_0 + History_B` → одинаковая геометрия/текущий world state, но
    различный NPC behavior. Если поведение одинаково всегда,
    memory/epistemics не участвуют причинно. ✅ S243: causal_state_test
    (GC-00-харнес, один snapshot+seed, единственная переменная —
    авторизованная дельта): C-группа — argmax Люси flips → flee без
    события/текста; B-группа — контроль (дельт нет). LIMITATION:
    доказано на уровне решения (argmax), не материализации движения.

-   [ ] **DIFF-02 --- Observation differential.** `Event_X` происходит
    одинаково, но `NPC_A` наблюдает его, а `NPC_B` нет. Их belief state
    и последующее решение не должны стать одинаковыми только потому, что
    событие существовало в мире.

-   [ ] **DIFF-03 --- Body differential.** Одинаковая социальная
    ситуация при разном sleep/energy pressure должна допускать различное
    решение, если affordance/decision scoring реально учитывает body
    constraint.

-   [ ] **DIFF-04 --- Relationship differential.** Одинаковый
    объект/задача при разной history отношений должен давать различное
    социальное решение, если relationship state причинно подключён.

-   [ ] **DIFF-05 --- Testimony differential.** Одинаковое событие, но
    разные источники свидетельства (high/low trust, direct testimony vs
    hearsay) → разные confidence/belief outcomes там, где это
    предусмотрено контрактом.

-   [ ] **DIFF-06 --- Humor differential.** Same event + same world, but
    different expectation or relationship history → different humor
    appraisal.

-   [ ] **DIFF-07 --- Pressure differential.** Same NPC and same
    humorous opportunity under low versus high acute/chronic pressure →
    different propensity/form of coping humor where the
    appraisal/motivation model predicts it.

-   [ ] **DIFF-08 --- Resolution differential.** Same incongruity
    with/without an available logical/semantic resolution → amusement
    versus confusion/uncertainty.


-   [ ] **DIFF-09 --- Avatar values differential.** Same player intent and
    world, different values/preferences → different avatar appraisal.
-   [ ] **DIFF-10 --- Avatar history differential.** Same avatar profile and
    current command, different prior treatment by player → different
    player-trust/acceptance outcome where causally justified.
-   [ ] **DIFF-11 --- Player knowledge differential.** Same world truth, but
    player knows a fact the avatar does not → avatar does not magically act
    on player-only knowledge.
-   [ ] **DIFF-12 --- Avatar memory differential.** Same current world and
    profile, different prior trauma/experience → different resistance.
-   [ ] **DIFF-13 --- Negotiation differential.** Same refusal pressure,
    different available affordances → different counter-offer.

### 5a.5 Reachability audit

Для каждой значимой feature вести отдельную проверку:

`mechanism exists → production caller → player trigger → state write → next-tick effect → future behavior → player-visible consequence`.

-   [ ] **REACH-01** Все feature-механизмы из MASTER TODO имеют
    production caller.
-   [ ] **REACH-02** Для каждого caller существует игровой trigger или
    явно documented non-gameplay utility path.
-   [ ] **REACH-03** Нет «мертвых контуров»: зарегистрированные
    engine/checker/subscriber вызываются, но никогда не получают
    реальные данные.
-   [ ] **REACH-04** Каждый runtime writer имеет canonical owner и test
    на competing writer.
-   [ ] **REACH-05** Каждый player-facing discovery path имеет источник
    ObservationLog.
-   [ ] **REACH-06** Каждая заявленная MVP-фича имеет минимум один L3
    vertical test.
-   [ ] **REACH-07** Avatar ADR contour has production caller, player trigger,
    canonical state write, next-tick effect and player-visible consequence.
-   [ ] **REACH-08** Avatar counter-offer is an executable intent, not only
    narration.
-   [ ] **REACH-09** Private avatar narration reaches the real communication/API
    path.
-   [ ] **REACH-10** CharacterProfile values and psyche are actually consumed
    by the same production resolver that decides avatar actions.

### 5a.6 Negative-path tests

-   [ ] **NEG-01** Missing/None dependency не приводит к
    `union-attr`/`NoneType` падению тика; ветка либо корректно disabled,
    либо fail-loud.

-   [ ] **NEG-02** Invalid/stale intent не выполняется и не
    телепортирует NPC.

-   [ ] **NEG-03** Duplicate event.id не применяет одну причинную дельту
    дважды.

-   [ ] **NEG-04** Unauthorized writer получает
    ArchitecturalViolationError.

-   [ ] **NEG-05** Broken persistence payload не превращается в тихий
    `{}` и не стирает состояние.

-   [ ] **NEG-06** LLM timeout/cancellation не блокирует WorldTick.

-   [ ] **NEG-07** Unknown observation не превращается в false
    certainty.

-   [ ] **NEG-08** Dead/invalid actor не продолжает автономное действие.

-   [ ] **NEG-09** Renderer/presentation mutation обнаруживается тестом
    архитектурного нарушения.

-   [ ] **NEG-10** `random.*`, wall-clock и необработанный
    `rng or random` в kernel/gameplay-critical path обнаруживаются
    lint + runtime probe.

-   [ ] **NEG-11** Incongruity без разрешения не превращается
    автоматически в humor.

-   [ ] **NEG-12** Высокий `humor disposition`/playfulness не заставляет
    NPC шутить при угрозе или каждом тике.

-   [ ] **NEG-13** Высокий trust не гарантирует humor, а низкий trust не
    запрещает его универсально; appraisal must decide.

-   [ ] **NEG-14** Chronic pressure не создаёт бесконечный `humor_mode`
    и не мутирует personality напрямую без evidence/causal path.

-   [ ] **NEG-15** LLM не может сам записать `HumorAppraisal`,
    relationship delta или hidden humor state в обход canonical writers.
-   [ ] **NEG-16** Avatar psyche missing/malformed payload does not silently
    fall back to gameplay-critical constants.
-   [ ] **NEG-17** Mixed `0..1`/`0..100` avatar scales are rejected by contract
    tests; BROKEN/mental-strain thresholds must be reachable only in the
    intended ranges.
-   [ ] **NEG-18** A player command cannot directly write avatar psyche,
    relationship or belief state around canonical writers.
-   [ ] **NEG-19** `REFUSE` without an applicable reason is rejected by the
    avatar resolution contract.
-   [ ] **NEG-20** `player_trust` alone cannot override values, physical
    constraints, trauma or epistemic uncertainty.
-   [ ] **NEG-21** Resistance Medium cannot mutate canonical avatar state.
-   [ ] **NEG-22** `BROKEN` cannot silently terminate the campaign or delete
    avatar state.
-   [ ] **NEG-23** Inner voice cannot create a new hidden psychological state
    that is absent from canonical runtime state.
-   [ ] **NEG-24** Player-only knowledge is not injected into avatar belief
    without an observation/testimony path.
-   [ ] **NEG-25** Avatar-specific duplicate stores/writers for memory,
    relationships, epistemics or world state are architectural violations.



### 5a.6b Avatar differential matrix

-   [ ] `same command × different values`
-   [ ] `same command × different player history`
-   [ ] `same world × different avatar knowledge`
-   [ ] `same trauma × different current pressure`
-   [ ] `same refusal × different available affordances`
-   [ ] `same pressure × different humor/coping history`

### 5a.7 Масштаб и длительность

-   [ ] **SCALE-01** Smoke: 6 NPC × 30 ticks.
-   [ ] **SCALE-02** Stability: 6 NPC × 200 ticks.
-   [ ] **SCALE-03** Long horizon: 6 NPC × 1000 ticks.
-   [ ] **SCALE-04** Persistence: save/load минимум в 3 точках одной
    истории.
-   [ ] **SCALE-05** Replay: минимум 3 одинаковых прогона одного seed.
-   [ ] **SCALE-06** Async differential: минимум 3 варианта
    timing/interleaving.
-   [ ] **SCALE-07** Campaign stress: 20--50 NPC только после
    прохождения single-tavern closure; масштабирование не должно
    маскировать отсутствие L3 correctness.

### 5a.8 Chronicaler как oracle, а не как источник истины

Chronicle должен быть производной observability-слойкой. Для каждого
GC-теста желательно сохранять machine-readable trace:

`event → observation → experience → memory → conclusion → expectation/belief → appraisal/relationship/body pressure → affordance → decision → commitment → execution → verification → world change`.

Тест не должен проверять «красивую фразу». Он проверяет наличие
причинных звеньев и соответствие их canonical state. Human-readable
Chronicle используется как L4-представление той же цепочки.

### 5a.9 Правило закрытия feature

Feature считается **CLOSED** только если:

1.  L1 mechanism test зелёный;
2.  L2 production integration test зелёный;
3.  соответствующий L3 GC-тест зелёный;
4.  negative-path тесты закрыты;
5.  persistence/replay проверены, если feature stateful;
6.  reachability подтверждена, если feature player-facing;
7.  Chronicle/Inspector может объяснить причинную цепочку, если она
    должна быть наблюдаема;
8.  нет известного AUD debt, который непосредственно ломает этот путь.

`IPT 45/45` без этих условий не является достаточным доказательством
gameplay closure.

**Правило закрытия стадии (дополнение, ратифицировано Мастером 2026-09-05):**
стадия, имеющая назначенное gameplay acceptance обязательство, не может
считаться CLOSED только на основании L0/L1/L2-доказательств. Требуется
доказательство назначенного игрового следствия, **соответствующее природе
механизма**: player-causal → player-triggered vertical (L3);
system-causal → production gameplay scenario с системным триггером;
dormant-substrate → acceptance у consumer-фронта (искусственный
player-триггер до consumer'а не требуется); periodic/long-horizon →
сценарий класса GC-16/SCALE, не на каждый фронт. Назначение клетки — на
PRE-FLIGHT фронта, отдельным вердиктом, с записью в реестр ниже. По
умолчанию ≤1 primary-клетки на фронт; две допустимы только с явным
обоснованием двух независимых игровых причинностей (прецедент: BC =
GC-03 + GC-04 — разные причинные переходы). Форма доказательства
(L0–L4) и природа обязательства — независимые оси: метка indirect в §5b
не является автоматическим разрешением класса теста.

**Реестр привязок стадия→клетка (минимальный позвоночник, вердикт
Мастера 2026-09-05; расширяется только PRE-FLIGHT-вердиктом, по одному
фронту):**

| GC | Домен | Причинная истина | Обязателен для фронта |
|---|---|---|---|
| **GC-11** | Relationships | event → social state → различие в следующем выборе | RE (следующий фронт) |
| **GC-08** | World/G3 | object → affordance → action → persistent consequence | W-track G3 |
| **GC-09** | Body | pressure → constraint → decision restriction → recovery | Body delivery |
| **GC-03** | Memory/epistemics | разный опыт → разный выбор идентичных агентов | BC epistemic causality |
| **GC-16** | Long horizon | 100+ тиков, causal history жива, seed-детерминизм | периодический gate зрелости (не на каждую стадию) |

**Миграция (правило поглощения):** закрытия до 2026-09-05 сохраняют
исторический статус; отсутствующее игровое доказательство поглощается
фронтальными гейтами: RE M0–M1b.3.4 → GC-11 @ M2/D; W1–G2 → GC-08 @ G3;
B0/E2.0-c/BC-1 → GC-04 full-cell @ BC-3. Очередь переоткрытия прошлого
не создаётся.

Обоснование старта: RE-D2 доказал, что зелёная архитектура может
производить нулевую игровую реальность; DEBT-SLEEP-DELIVERY доказал
то же для тела. GC-02 (player→world) остаётся отдельной
пользовательской вертикалью — не сливается с GC-08.

### 5a.10 Что делать с уже существующими тестами

Не плодить сотни unit-тестов ради числа. Existing SUPERBOX/IPT
сохраняются как L0/L1. Новый слой должен быть маленьким, но
вертикальным:

-   `backend/tests/gameplay/test_tavern_vertical.py`
-   `backend/tests/gameplay/test_causal_differentials.py`
-   `backend/tests/gameplay/test_negative_paths.py`
-   `backend/tests/gameplay/test_replay_persistence.py`
-   `backend/tests/gameplay/test_reachability.py`
-   `backend/tests/gameplay/test_chronicle_observability.py`
-   `backend/tests/gameplay/test_humor_vertical.py`
-   `backend/tests/gameplay/test_humor_differentials.py`
-   `backend/tests/gameplay/test_humor_coping.py`

Один vertical test может закрывать сразу несколько внутренних
механизмов. Это предпочтительнее десятков тестов, которые напрямую
вызывают их writers.

------------------------------------------------------------------------

## 5b. GAMEPLAY CLOSURE MATRIX --- единая таблица уверенности

**Правило:** колонка «исправлено» означает код изменён; «закрыто»
означает acceptance test зелёный; «уверены» означает, что пройден весь
требуемый уровень доказательства и нет известного blocker debt.

  --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
  ID      Область             Механизм                    Production path           L3 test Negative    Persistence / Player-visible   Исправлено   Закрыто   Уверены   Доказательство /
                                                                                                        Replay                                                          коммит
  ------- ------------------- --------------------------- ------------------------- ------- ----------- ------------- ---------------- ------------ --------- --------- ----------------
  GC-00   Runtime             живой world tick            TickOrchestrator → NPC    GC-00   NEG-06      SCALE-05      да               ✅ (bd4: 3/3, reports/gc00_baseline4.txt)  \[ \]     \[ \]     

  GC-01   Tick                полный цикл NPC             production tick           GC-01   NEG-02      SCALE-05      да               \[ \]        \[ \]     \[ \]     

  GC-02   World               player action → consequence action → compiler →       GC-02   NEG-03      GC-20/21      да               \[ \]        \[ \]     \[ \]     
                                                          projection                                                                                                    

  GC-03   Perception/Memory   observation → memory        perception → E1           GC-03   NEG-07      GC-20/21      indirect         \[ \]        \[ \]     \[ \]     

  GC-05   Epistemics          testimony → belief          speech → ClaimEvent →     GC-05   NEG-07      GC-20/21      indirect         \[ \]        \[ \]     \[ \]     
                                                          belief                                                                                                        

  GC-06   Memory              history differential        memory → cognition        GC-06   NEG-07      GC-21         да               ✅ (S243,    \[x\]     \[x\] с   \[x\]     \[ \]
                              C-группа: один мир + одна  оговоркой                  causal_state_test                                          дельта истории →    
                                                                                                                                      C; D-группа =                    другой argmax;     
                                                                                                                                      negative;                       A-группа =         
                                                                                                                                      limitation:                     полный путь)       
                                                                                                                                      decision-level,                                   
                                                                                                                                      BC-12)                                                                                                                                                            

  GC-07   Perception          observation differential    perception filter         GC-07   NEG-07      GC-21         да               \[ \]        \[ \]     \[ \]     

  GC-08   World/Action        object → affordance →       W2/W3 → Decision →        GC-08   NEG-02/04   GC-20/21      да               \[ \]        \[ \]     \[ \]     
                              action                      execution                                                                                                     

  GC-09   Body                pressure → constraint →     Body/Needs → Decision     GC-09   NEG-08      GC-20/21      да               \[ \]        \[ \]     \[ \]     
                              recovery                                                                                                                                  

  GC-10   Sleep               reachable sleep delivery    intent → traversal →      GC-10   NEG-02      GC-20/21      да               \[ \]        \[ \]     \[ \]     
                                                          settled                                                                                                       

  GC-11   Relationships       event → state → social      RE Gate → snapshot →      GC-11   NEG-04      GC-20/21      да               \[ \]        \[ \]     \[ \]     
                              action                      Decision                                                                                                      

  GC-12   Learning            repetition/generalization   experience → conclusion   GC-12   NEG-03      GC-20/21      indirect         \[ \]        \[ \]     \[ \]     

  GC-13   Belief revision     contradiction → revision    observation → surprise →  GC-13   NEG-07      GC-20/21      да               \[ \]        \[ \]     \[ \]     
                                                          belief                                                                                                        

  GC-14   Self model          result → learning           action → outcome → self   GC-14   NEG-03      GC-20/21      да               \[ \]        \[ \]     \[ \]     

  GC-15   Social              triangle/reputation         social graph/subscribers  GC-15   NEG-04      GC-20/21      да               \[ \]        \[ \]     \[ \]     

  GC-16   Long horizon        persistent causal story     real ticks                GC-16   all         GC-20/21      да               \[ \]        \[ \]     \[ \]     
                                                                                            relevant                                                                    

  GC-17   Integrity           competing writers           StateApplicator/Gate      GC-17   NEG-04      GC-21         indirect         \[ \]        \[ \]     \[ \]     

  GC-18   Time                wall-clock independence     kernel/runtime            GC-18   NEG-10      GC-21         indirect         \[ \]        \[ \]     \[ \]     

  GC-19   Async               interleaving determinism    TaskScheduler/execution   GC-19   NEG-06      GC-21         indirect         \[ \]        \[ \]     \[ \]     

  GC-20   Persistence         save/load continuation      snapshot + projection     GC-20   NEG-05      required      да               \[ \]        \[ \]     \[ \]     

  GC-21   Replay              exact causal replay         seed + input/event stream GC-21   NEG-10      required      indirect         \[ \]        \[ \]     \[ \]     

  GC-22   Player cognition    ambient discovery           perception →              GC-22   NEG-07      GC-20/21      да               \[ \]        \[ \]     \[ \]     
                                                          ObservationLog                                                                                                

  GC-23   MVP                 dilemmas reachable          init_campaign → registry  GC-23   NEG-01      GC-20         да               \[ \]        \[ \]     \[ \]     
                                                          → trigger                                                                                                     

  GC-24   LLM                 failure isolation/cancel    TaskScheduler → provider  GC-24   NEG-06      GC-21         indirect         \[ \]        \[ \]     \[ \]     

  GC-25   Observability       causal Chronicle            trace → projector         GC-25   NEG-09      GC-20/21      да               \[ \]        \[ \]     \[ \]     

  GC-26   Debugging           NPC Inspector               runtime trace/state       GC-26   NEG-09      GC-20/21      да               \[ \]        \[ \]     \[ \]     

  GC-27   Frontend            consequence reaches         API →                     GC-27   NEG-09      GC-20/21      **да**           \[ \]        \[ \]     \[ \]     
                              renderer                    PresentationProjector →                                                                                       
                                                          renderer                                                                                                      

  GC-28   MVP                 full living tavern          all production layers     GC-28   all         required      **да**           \[ \]        \[ \]     \[ \]     
  --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

| GC-29 \| Humor \| expectation → incongruity → resolution → appraisal
  \| perception → predictive/appraisal \| GC-29 \| NEG-11 \| GC-40 \| да
  \| \[ \] \| \[ \] \| \[ \] \| \|
| GC-30 \| Humor \| individual appraisal \| perception +
  personality/state/relationship \| GC-30 \| NEG-13 \| GC-40 \| да \| \[
  \] \| \[ \] \| \[ \] \| \|
| GC-31 \| Humor \| temporal disposition \| memory/appraisal/history \|
  GC-31 \| NEG-14 \| GC-40 \| да \| \[ \] \| \[ \] \| \[ \] \| \|
| GC-32 \| Humor \| benign violation \| appraisal + relationship \|
  GC-32 \| NEG-13 \| GC-40 \| да \| \[ \] \| \[ \] \| \[ \] \| \|
| GC-33 \| Humor/Coping \| acute pressure → humor response \| appraisal
  → motivation → action \| GC-33 \| NEG-12 \| GC-40 \| да \| \[ \] \| \[
  \] \| \[ \] \| \|
| GC-34 \| Humor/Coping \| chronic pressure → adapted response \|
  pressure → memory/self-model → decision \| GC-34 \| NEG-14 \| GC-40 \|
  да \| \[ \] \| \[ \] \| \[ \] \| \|
| GC-35 \| Humor \| failed attempt → consequences \| speech → reaction →
  memory/relationship \| GC-35 \| NEG-11/13 \| GC-40 \| да \| \[ \] \|
  \[ \] \| \[ \] \| \|
| GC-36 \| Humor/Social \| audience model \| perception → relationship →
  decision \| GC-36 \| NEG-12 \| GC-40 \| да \| \[ \] \| \[ \] \| \[ \]
  \| \|
| GC-37 \| Humor/Epistemic \| social transmission \| testimony →
  belief/experience \| GC-37 \| NEG-07 \| GC-40 \| да \| \[ \] \| \[ \]
  \| \[ \] \| \|
| GC-38 \| Runtime \| no scheduled jokes \| decision/action scheduler \|
  GC-38 \| NEG-12 \| GC-40 \| indirect \| \[ \] \| \[ \] \| \[ \] \| \|
| GC-39 \| Observability \| causal explanation \| trace →
  Chronicle/Inspector \| GC-39 \| NEG-15 \| GC-40 \| да \| \[ \] \| \[
  \] \| \[ \] \| \|
| GC-40 \| Replay \| humor persistence/replay \| snapshot + memory +
  relationship \| GC-40 \| NEG-14/15 \| required \| indirect \| \[ \] \|
  \[ \] \| \[ \] \| \|

### 5b.1 Матрица reachability для известных AUD-долгов

  -------------------------------------------------------------------------
  AUD             Что ломается в игре     Какой gameplay    Закрытие
                                          test должен это   
                                          поймать           
  --------------- ----------------------- ----------------- ---------------
  AUD-D1          latent type/interface   GC-00/01/24 +     \[ \]
                  crashes могут оборвать  NEG-01            
                  реальный путь                             

  AUD-D2          социальная реакция      GC-11 + NEG-01    \[ \]
                  может упасть именно в                     
                  production None-ветке                     

  AUD-D3          отмена LLM может упасть GC-24 + NEG-06    \[ \]
                  AttributeError и                          
                  нарушить isolation                        

  AUD-D4          competing writers могут GC-17 + NEG-04    \[ \]
                  перетирать canonical                      
                  NPC state                                 

  AUD-D5          отношения могут         GC-18/20/21 +     \[ \]
                  зависеть от             NEG-05            
                  wall-clock/тихо                           
                  обнулиться                                

  AUD-D6          feature существует, но  GC-23 + REACH-03  \[ \]
                  игрок никогда не может                    
                  её вызвать                                

  AUD-D7          startup                 startup smoke +   \[ \]
                  observability/logging   NEG-09            
                  debt; kernel gameplay                     
                  напрямую не ломает                        

  AUD-D8          CI может давать ложную  CI config test +  \[ \]
                  уверенность в strict    AUD audit         
                  typing gate                               

  AUD-D9          память диалога теряет   GC-03/25          \[ \]
                  intent/tone metadata                      

  AUD-D10         игрок слышит/видит      **GC-22**         \[ \]
                  улику, но расследование                   
                  её не получает                            

  AUD-D11         скрытые TODO могут      REACH-01...06 +   \[ \]
                  означать                targeted audit    
                  unreachable/legacy path                   

  AUD-D12         replay может            GC-18/21 + NEG-10 \[ \]
                  расходиться из-за RNG                     
                  default path                              
  -------------------------------------------------------------------------

### 5b.2 Итоговый статус ENIGMA

  ----------------------------------------------------------------------------
  Уровень уверенности Условие                              Статус
  ------------------- ------------------------------------ -------------------
  **MECHANISM GREEN** L0/L1: contracts + unit/SUPERBOX     \[ \]

  **RUNTIME GREEN**   L2: production integration           \[ \]

  **GAMEPLAY GREEN**  L3: GC vertical scenarios            \[ \]

  **OBSERVABILITY     L4:                                  \[ \]
  GREEN**             Chronicle/Inspector/player-visible   
                      proof                                

  **REPLAY GREEN**    deterministic replay + persistence   \[ \]

  **REACHABILITY      player can actually trigger claimed  \[ \]
  GREEN**             features                             

  **ENIGMA GAMEPLAY   все обязательные строки выше         \[ \]
  CLOSED**            зелёные; нет blocker AUD debt        
  ----------------------------------------------------------------------------

------------------------------------------------------------------------

## 5c. Минимальный порядок закрытия тестового слоя

1.  **Сначала:** GC-00, GC-01, GC-17, GC-18, GC-19, NEG-01...NEG-06 ---
    доказать, что runtime не врёт и не разваливается.
2.  **Затем:** GC-02, GC-03, GC-08, GC-09, GC-10, GC-11 --- доказать
    физический и социальный причинный цикл.
3.  **Затем:** GC-04...GC-07, GC-12...GC-15 --- доказать
    memory/belief/learning/social cognition.
4.  **Затем:** HU1--HU5 + GC-29...34 --- сначала восприятие юмора и
    coping, затем temporal/social plasticity.
5.  **Затем:** HU6--HU13 + GC-35...40 --- production, failed humor,
    transmission, observability, replay.
6.  **Затем:** GC-20/21 --- общий persistence/replay gate.
7.  **Затем:** GC-22/23/24 --- закрыть конкретные известные
    reachability/failure gaps AUD-D3/D6/D10.
8.  **Затем:** GC-25...GC-28 --- observability, frontend visibility и
    full tavern acceptance.
9.  **После этого:** масштабирование SCALE-03/07 и дальнейшие эпохи.

**Главный Stop-rule:** если GC-тест не может быть написан без прямого
вызова внутреннего writer/engine, это не повод ослабить тест. Это
сигнал, что production reachability ещё не замкнута.

## 5d. ЖУРНАЛ ТЕСТОВ И ЗАКРЫТИЙ (поглощает TEst_Result.md)

> Решение Мастера (итерация «Пункт 5», 2026-09-04): файл `backend/tests/TEst_Result.md` удалён; единственное место фиксации выполнимости — этот документ. Протокол: (1) каждое закрытие пункта/долга = обновление галочки/статуса в соответствующем разделе (§2a, §4a–§4c, §5, §5a, §5b); (2) каждый значимый прогон/гейт = строка в таблице ниже. Красный тест = диагноз (незамкнутый контур + причина + подозреваемый узел), а не повод прятать результат: при FAIL колонка «Диагноз» обязательна. Закрытие стадии с назначенным acceptance-обязательством обязано цитировать результат назначенного гейта (клетка + зелёный прогон/коммит) в строке журнала.

| Дата | Шаг | Объект | Результат | Диагноз / причина |
|------|-----|--------|-----------|-------------------|
| 2026-09-04 | Базлайн итерации «Пункт 5» | IPT (45 инвариантов) | ✅ 45/45, 0 CRITICAL | — |
| 2026-09-04 | Базлайн итерации «Пункт 5» | pytest tests/ (полный) | 📌 по коммиту d92e8d1c: 1614 passed / 15 pre-existing failed (sandbox/scenario, decision_hub goal_boost) / 32 skipped | свежий полный прогон — в составе шага GC-00 (harness) |
| 2026-09-04 | Шаг 1 (миграция) | TEst_Result.md → 5d | ✅ удалён, протокол перенесён | из журнала спасён незарегистрированный открытый хвост PROBE 9.7 (ниже) |
| 2026-09-04 | Шаг 2 (детектор) | test_npc_state_r6.py (5 тестов) | ✅ 5/5 passed | противоречивые прогоны старого журнала = история миграции шкалы identity_integrity 0..100→0..1; билд самосогласован (SSOT npc_state.py:667/810/1149); находка закрыта (historical, живого бага нет); бонус: pytest.ini подхвачен pytest 8.3.3 — долг S213 закрыт фактом |
| 2026-09-04 | Шаг 3 (PROBE 9.7, P1) | run_turn materialization parity — патч game_loop/__init__.py:1481 (ADR-O-313, зеркало idle-прецедента :1245) | ✅ патч применён: compile ✅, ruff 20 (pre-existing, +0), IPT 45/45, 0 CRITICAL | ROOT_CAUSE: REST-путь никогда не разбирал pending_tasks (execute_pending вызывался только из idle_tick:1245) → NPC_SPOKE не публиковался → «0 строк npc_spoke»/память речи NPC мертва в player-сессиях (FAIL_STAGE: MATERIALIZE). FIX_SCOPE 1: execute_pending + drain_commitment_outbox над _tick_scenes-сценой между commit (:1479) и unlock (:1510); fast-path реплики попадают в recent_dialogues этого же хода; LLM-задачи на пуле ADR-O-343 (REST не блокируется). Живой REST-smoke (реплика NPC → npc_spoke в L2) — в составе GC-00. Порождённые хвосты: AI-D1 (мёртвый гейт-тест), ST-1 (stream_turn REST-зеркало?) |
| 2026-09-04 | Шаг 3.5 (вердикты) | pytest -rs (причина скипа) + тело stream_turn + семантика лока + frontend transport | ✅ вердикты получены | AI-D1: явный skip «Flaky… Needs refactor» (:52) — гейт мёртв, преемники headless вне pytest-коллекции; ST-1: разрыв подтверждён (нет commit/unlock/execute в WS-методе), но SSE недостижим в Direct-контракте (api_client.py:585–587), лок мягкий → P1→P2, кандидат REACH-03. Гигиена: коммит 28676bcb (git add -A) втянул 30 файлов/43k строк (w3g2-отчёты, логи, правки reaction_subscriber/npc_tick_pipeline/test_phase_a — не из этой итерации); впредь точечный git add |
| 2026-09-04 | S239 (W-трек, ADR-O-378) | GORAN β G2: 7×200 тиков, процесс-изоляция + settings.saves_dir | ✅ GREEN: honest-zero (диффы ≤ OFF/OFF-фона), B-молчание, W hits=199/199 + weapon_persisted; engine-флип 0.50→0.70 юнит-доказан; W-контур 124+1skip, IPT 45/45 | Хроника: 4 честных отказа пойманы гвардами (bootstrap-квант / H1 потеря инъекции / H5 общий-store / stale-парсинг), ноль ложных GREEN; terminal-дрейф 65→42 = артефакт общего store (канонический S237-класс восстановлен изоляцией), не регрессия ядра; B1 trav=120 — одиночный ambient-выброс (DEBT-QUIESCE, ось не гейт) |
| 2026-09-04 | S239 (док-санация) | drift O-373→O-376 (неполный propagate S237) | ✅ 24 сайта закрыты (доки/исходники/тесты/скрипт; гейты зелёные до/после) | Урок: propagate-sweep обязан покрывать ВСЕ файлы Files-списка ADR, не только доки |
| 2026-09-04 | Шаг 4 (GC-00 baseline №1) | pytest tests/gameplay/test_tavern_vertical.py (3 детектора, -s) | ❌ 0/3 (2 failed + 1 error, единый корень) | Все 3 падения = ArchitecturalViolationError «Direct write to NPCState.drives from tests.gameplay.harness» — ADR-WRITE-GUARD (S212) поймал нарушение САМОГО harness'а: позитив, enforcement жив. Корень: _init_avatar_body пишет поля пост-конструкцией (скопирован из прецедента test_player_turn_headless, который мёртв под guard'ом → новый хвост PH-1). Production-обвязка fixture (load_campaign/ensure_scene/select_player/CharacterSheet) прошла. Попутно: WARNING location_templates.json не найден (pre-existing, вне шага). Действие: конструкторные kwargs / фабрика (§13.4) → baseline №2 |
| 2026-09-04 | Шаг 4 (GC-00 baseline №2) | pytest tests/gameplay/test_tavern_vertical.py -s (полный) | 🟡 1/3: determinism ✅ (вакуум-оговорка), liveness ❌ (AssertionError), P97 ❌ (TypeError вложенного asyncio.run — баг ТЕСТА; run_turn полностью исполнился); 301.71s (P14) | Корни тест-слоя: (1) nested asyncio.run в P97; (2) _scene_after_tick ждал dict — idle_tick возвращает объект/ответ без final_state-ключей → time=0 + подозрение вакуумного PASS; (3) изоляция saves не сработала — [AVATAR] XRayProbe != Tester: прочитан прод-saves (env-подмена бессильна) → аватар контаминирован (Psyche {}, hp=0.0). LIVE-подтверждения базы (не чинить в GC-слое): AUD-D2 (social_subscriber:195 NoneType.apply ERROR), AG1-D5 (hp=0.0 при живом ходе, перепроверка после изоляции), DEBT-R10 (Psyche {}), RE-D2 (DIALOGUE_UPDATE TimeoutError ×4), НОВЫЙ SC-1 (SHADOW_COMPILER Node not found: tavern:entrance/right_table/fireplace — namespace run_turn ≠ граф), SOMATIC_VETO body_state missing. DM_AGENT_CRASH при LLM-off — изоляция отказа выстояла (ход выжил) |
| 2026-09-04 | Шаг 4 (GC-00 baseline №3) | pytest -s → reports/gc00_baseline3.txt | 🟡 2/3: liveness ✅ (первый живой PASS), P97 ✅ (PROBE 9.7-инвариант зелёный в REST-пути), determinism ❌; 310.36s | RETRACTION: атрибуция DEBT-QUIESCE снята — расхождение на тике 0 (tick 2727 vs 2757; last_time 70760 vs 71060) с offset РОВНО = 30 тикам run1 → контаминация состояния между прогонами, не async-недетерминизм; spoke/moved идентичны (34/5 оба прогона) — динамика стабильна. Векторы: (1) изоляция saves мертва — GC00-SETUP напечатал прод-путь (config.py:49 жёсткий дефолт, settings-синглтон создан до env-подмены); (2) sessions world_tick.json переносит sim_tick (experiment_runner:113–115); (3) глобальные синглтоны (LifeEngine) без сброса между сборками. Фикс: H-6/H-7 (calibration-паттерн прямой мутации settings + restore); полная изоляция sessions/синглтонов — по археологии experiment_runner → baseline №4. Таблицы дословно: gc00_baseline3.txt :17-27, :68-73. Наблюдение: фантом-каталог backend\backend\data (pre-existing, scene_state_manager:724) |
| 2026-09-04 | Шаг 4 (GC-00 baseline №3 — дословная фиксация) | reports/gc00_baseline3.txt | ✅ срез зафиксирован | LIVENESS: 100/100 тиков, 0 crashes, decisions=111, npc_spoke=111 (речь жива БЕЗ LLM — fast-path), moved=16, traversals=4, proximity 62/14, pending_tail=0×100 (INV-DIALOGUE-LIVENESS здоров). P97: pending 0→0, recent_dialogues=1, npc_spoke=8 за ход, dm_response=106 при мёртвом DM — PROBE 9.7 замкнут до API-границы, ход пережил DM_AGENT_CRASH (сигнал GC-24). КОНТАМИНАЦИЯ — диск-улика: data/sessions/Open_road/world_tick.json sim_tick=6610, updated_at=19:56 (наш прогон писал мимо temp-saves); liveness шёл поверх существующей кампании (финиш tick=2726, старт ~2626); det-run2 продолжал run1 (tick 2757 = 2727+30). Вердикт determinism-теста недействителен до clean-start: нужны (1) снапшот/restore sessions (calibration _snapshot_dir), (2) invalidate RAM-кэшей LifeEngine, (3) bus.clear() между прогонами (подписчики прошлых GameLoop не снимаются dispose'ом) — патч H-8 после археологии |
| 2026-09-04 | Шаг 4 (GC-00 baseline №4 — ФИНАЛ) | pytest -s → reports/gc00_baseline4.txt; IPT 45/45 | ✅ 3/3 PASSED, 93.44s | CLEAN-START верифицирован: saves_dir=Temp\gc00_*; seed_determinism: 2×30 тиков идентичны (last_time 43500, spoke 8, moved 23 в обоих; 30/30 отпечатков) — детерминизм ПОДТВЕРЖДЁН на чистом старте, ретракция закрыта (асинхронщина не подтверждена, перенос был контаминацией); host-изоляция байтово доказана (sim_tick 6610/19:56 восстановлен дословно); P97 ✅ (PROBE 9.7 в REST-пути). Время 310s→93.44s (×3.3, попутный P14-выигрыш изоляции). Эволюция: №1 0/3 (guard поймал harness) → №2 1/3 (nested-asyncio/contract/изоляция) → №3 2/3 (контаминация) → №4 3/3. H-8: bus.clear + sessions snapshot/restore + SpatialRegistry invalidate + reset_life_engine в dispose |
| 2026-09-04 | Шаг 5 (AUD-D2, production-fix №1) | game_loop/__init__.py (провода стора :264+) + social_subscriber.py (skip-путь None-ветки) | ✅ ЗАКРЫТ: P97 1 passed 90.72s, SOCIAL_SUB ERROR/None-warning исчезли; ruff clean; IPT 45/45 | ROOT_CAUSE (двойной): (а) S198-читатель idle:1162 ждал self._rel_store — атрибута НЕ существовало (обе точки :181/:264 локальные) → shared_context.relationship_store ВСЕГДА None; (б) индент-баг: for _ev в events вне else → None.apply ERROR каждый ход. FIX: self._rel_store = _rel_store (:264) + полный skip-путь в None-ветке (warning → rumors → return Phase8Result). Эффект (уточнение по вердикту Мастера): write-контур восстановлен — стор доехал до shared_context (None-ветка не срабатывает), gate.apply вызывается без ERROR. ДОКАЗАНО P97: отсутствие ERROR/None-ветки в живом REST-ходе. НЕ доказано: персистентность trust-дельт чтением стора (delta applied ≠ relationship state verified) — верификация в GC-11.
| 2026-09-04 | Шаг 6 (AG1-D5, Этап А — зонд, фикс отложен) | tests/gameplay/test_tavern_vertical.py::test_gc00_ag1_d5_avatar_body_initialization → reports/gc00_ag1_d5_probe.txt | 🔴 RED (ожидаемый, 1.31s) — вердикт ПОДТВЕРЖДЁН | ROOT: avatar default body_state={'money': 48} (load_state default-ветка) — аватар чистого мира получает эконом-словарь вместо тела; NPC-паритет сломан (NPC→BODY_STATE_HEALTHY ×3 точки, аватар→money-only). Эффект: effective_hp=0.0 (fallback npc_state:796, семантика=DISABLED current_hp=0) + life_status ABSENT → Death Guard видит 'ALIVE' (:2154). Death Guard и VitalState НЕПРАВИЛЬНЫ (hp≤0≠смерть, ADR-123) — дефект в инициализации, не в guard. DOUBLE TRUTH опровергнут: dict-сторона player/Tester NOT IN SNAPSHOT — единственное тело в NPCState. SECONDARY-находка: аватар отсутствует в all_npcs_raw idle-прогонов (в REST-пути был) — новый хвост AVID-1. Зонд коммитится как красный детектор; Stage B-фикс — {**BODY_STATE_HEALTHY, 'money': 48} construction-time (S208-прецедент) — на решение Мастера | Дефект был двойной: wiring (self._rel_store отсутствовал) + control-flow (fall-through в for при None). rumors-контур в None-ветке сохранён. Попутно: санирован mojibake «для社交ной» :163. Логи: reports/gc00_aud_d2_p97.txt |
| 2026-09-04 | Шаг 6 (AG1-D5, Stage B — фикс) | player_avatar_service.py: default body_state = {**BODY_STATE_HEALTHY, money:48} + импорт | ✅ ЗАКРЫТ: зонд GREEN 1.09s (current_hp=100, life_status=ALIVE, 17 ключей тела); полный GC-00 4/4 (89.10s); IPT 45/45; ruff clean | Красный→фикс→зелёный за одну итерацию. Аватар чистого мира получил телесный паритет NPC (включая sleep-оси S188 — энергетика/гидратация теперь инициализированы, закрывает часть фронта DEBT-SLEEP для аватара). Stage A→B: 5baea803 (RED-зонд) → текущий коммит (GREEN) |
| 2026-09-04 | Шаг 7 (AVID-1 — GAP закрыт) | game_loop/__init__.py (idle-проводка S113 all_npcs_raw) + harness.py (upsert_character восстановлен) | ✅ ЗАКРЫТ: S198_PIPELINE_ENTER count=7 с 'player' ×3 тика (прямой smoke); срезы кэш/снапшот/runtime 7/7/7; зонд PASS; GC-00-модуль 4/4 (93.87s); IPT 45/45 | Вердикт Стадии 3: GAP (BY-DESIGN опровергнут кодом ADR-030). Дифференциал: до фикса count=6 при живой инъекции (транзит, не персист) — idle не передавал список оркестратору; после — count=7. Второй компонент: harness-баг (sheet потерян при guard-фиксе bd1 → list_characters пуст → инъекция молча пропускалась). Production-эффект: аватар укоренён в idle-мире — CFL/восприятие NPC/соцполе видят игрока между ходами (embodied player runtime). Отчёты: gc00_avid1_probe/fix/fix2 |
| 2026-09-04 | Кросс-ретроспектива (из S240) | Инцидент контаминации prod-saves (bd2/bd3) — адъюдикация Мастера | ✅ вердикт: DEBT-W-STORE-INCIDENT = ACCEPT | Эволюция ROOT/saves признана каноническим состоянием живого мира (known provenance debt, «стратиграфия нарушена до T≈2800», reset отклонён — подмена исторической непрерывности опаснее артефакта; вердикт — в записи S240). Наш вклад: инцидент порождён baseline №2/№3 (env-изоляция была мертва, config.py:49 жёсткий дефолт); закрыт H-6..H-8 (settings-мутация+restore, sessions snapshot/restore, байтовая верификация host-состояния) — прогоны bd4+ чисты |
| 2026-09-04 | Шаг 8 (полевой тест, post-gate field test; контракт: без ремонтов) | terminal_cockpit полный маршрут: new→наблюдение→wait 3→адресное→wait 12→mem→restart→mem; LLM жива (Q4) | ✅ сессия завершена; 4 наших фикса ПОДТВЕРЖДЕНЫ В ПОЛЕ: hp=100 (AG1-D5), S198 count=7 с 'player' в ходах И idle (AVID-1), реплики материализуются (PROBE 9.7), social-коммиты (AUD-D2); player_xy_valid=True (Фаза 0.5-проблема закрыта в кокпите); ПЕРСИСТЕНТНОСТЬ: mem до/после restart ДОСЛОВНО идентичны — причинная история переживает рестарт; психика аватара материализовалась (identity_integrity 0.9978, life_project survival) | НОВЫЕ хвосты: FT-1 (P1) адресация «люся:»→TARGET Торнин — парсер понял, резолвер нет (S238-класс; suspicion: прокс-приоритет при distance 0.0); FT-2 (P1) FLEE-storm: NPC бежит от maid_lusya ×12, Flee blocked — threat вне npc_positions, Люся выпала из позиций idle (RE-D4+Н-53 live); FT-3 (P2) пусто-текстовые speech-эпизоды imp=0.80. Живые подтверждения: AG1-D1 (new_game V2 reset _cache ERROR), RE-D2 (TimeoutError при живом LLM, stm 0→176), SOMATIC_VETO (REST-тик), Н-45/46 (sweep vanished), DEBT-R10 (Psyche {} первый ход → материализовалась). Транскрипт: reports/field_test_S241.txt |

**Унаследованные открытые хвосты журнала (не зарегистрированы в §4a; владелец — итерация «Пункт 5»):**

- [x] **PROBE 9.7 (хвост Фазы A, P1, игровой опыт):** ✅ ЗАКРЫТ 2026-09-04 (итерация «Пункт 5», Шаг 3). Формулировка зонда «не зарегистрирован в run_turn-wiring» снята археологией: подписки глобальны (singleton-EventBus, регистрация в GameLoop.__init__); первопричина — отсутствие вызова execute_pending в REST-пути (FAIL_STAGE: MATERIALIZE). Фикс: game_loop/__init__.py:1481 (зеркало idle-прецедента). Гейты: compile ✅, ruff +0, IPT 45/45. Живой REST-smoke — в GC-00.
- [ ] **AI-D1 (P2, тест-гигиена):** test_game_loop_pipeline.py — единственный юнит-гейт _run_pipeline — permanently SKIPPED: явный @pytest.mark.skip «Flaky integration test: AsyncMock breaks sync DMResult expectations in run_dm_phase. Needs refactor» (:52). Гейт мёртв: регресс конвейера REST юнит-слоем не ловится; тест построен на конструкторных моках GameLoop(**mock_deps) — §13.4 (объект мечты). Преемники — headless-скрипты вне pytest-коллекции: tests/sandbox/micro/test_run_turn_e2e.py (требует LLM-сервер), tests/sandbox/micro/test_player_turn_headless.py (LLM-free, InterventionEvent → TickResultDTO). Действие: рефактор гейта в headless-класс (pytest-коллекция, MockProvider только в test-env) или retirement с переносом ассертов (_PipelineState/PipelineContext) в headless-гейт. Владелец: итерация «Пункт 5». Закрытие: галочка + строка журнала.
- [ ] **ST-1 (P2, понижен из P1 — мёртвый прод-контур):** ВЕРДИКТ: разрыв подтверждён — в stream_turn (:1560–1733) нет commit_tick_result/unlock_tick/execute_pending (коммиты :1035/:1202/:1479, анлоки :1046/:1290/:1510 — все вне WS-метода). Сцена лочится в _prepare_and_lock_scene (_run_pipeline:2338); в WS-пути не коммитится и не анлочится → при активации SSE: WS-тик не персистится (unlock = единственная точка персиста), pending_tasks не материализуются, Death-Guard early-return без unlock. Смягчение: фронтенд Direct-контракт SSE не поддерживает (api_client.py:585–587 NotImplementedError) → путь недостижим в проде; лок мягкий (lock_for_tick :242–248 возвращает None — паралича нет). Действие: при активации SSE — патч-зеркало PROBE 9.7 (commit + execute_pending + drain + unlock) до финального done-yield; до тех пор — кандидат REACH-03. Владелец: итерация «Пункт 5». Закрытие: галочка + строка журнала.
- [ ] **PH-1 (P2, прецедент):** test_player_turn_headless.py (эталон player-хода, послужил базой harness'а) мёртв под ADR-WRITE-GUARD: пост-конструкционные записи NPCState.drives/psyche/body_state из модуля tests.* → ArchitecturalViolationError (guard введён S212; скрипт — __main__-формат вне pytest-коллекции, падение никем не замечено). Действие: миграция прецедента на конструкторные kwargs или фабрику; прогон как отдельный гейт после GC-00. Владелец: итерация «Пункт 5». Закрытие: галочка + строка журнала.
- [ ] **SC-1 (P2, spatial/namespace, NEW из GC-00 baseline №2):** SHADOW_COMPILER «Node not found» в run_turn-пути: tavern:entrance (event_compiler:280), tavern:right_table (:155), tavern:fireplace (:280) — цели NPC не разрешаются в скомпилированном графе (namespace целей vs граф; см. расхождение tavern/tavern_silver_wolf из GC-00-археологии). Эффект: shadow-рельса пишет FAILED-записи позиций NPC, dual-rail компаризатор теряет материал. Действие: археология источника node-id (MovementIntent) vs компиляции графа; вердикт о namespace-каноне. Владелец: итерация «Пункт 5». Закрытие: галочка + строка журнала.
- [x] **AVID-1 (P2, avatar-in-idle, NEW из AG1-D5 зонда):** ✅ ЗАКРЫТ 2026-09-04 (Шаг 7, вердикт GAP): idle_tick не передавал all_npcs_raw оркестратору (S113-контракт «включая аватара» выполнялся только в REST) — инъекция ADR-030 была транзитом, аватар не укоренялся. Фикс: проводка в idle-вызове + harness-реставрация upsert_character. Доказательство: S198 count=7 с 'player' ×3 тика, срезы 7/7/7, GC-00 4/4, IPT 45/45. Idle-мир (CFL/восприятие/соцполе) теперь видит аватара.
| 2026-09-04 | S240 (W-трек, DEBT-W-AUDIT, вариант B — вердикт Мастера) | docs/AUDIT_W_TRACK_COUPLINGS.md (ТЗ §18.3 / DoD п.25) | ✅ deliverable закрыт: §1 граф + §2 реестр (FACT/INTERPRETATION/RECOMMENDATION) + §4 входной ограничитель G3; IPT 45/45 вход/выход; 0 .py-патчей, 0 ADR, 0 runtime-прогонов | B1.4-канал = главный риск-узел (anti-writer G3; релеи R1–R6 чужим сериям); W-граница: spawn=единственный writer, relations/transitions=0 callers, типовая G3-op отсутствует → мини-ADR. Процесс-урок: патч-гвард применённости обязателен перед терминальным коммитом — роадмап-патч S240 не был применён, коммит 2c4dfd9d обещал его в сообщении; закрыто док-коммитом |

- [x] **FT-1 (P1, адресация):** ✅ ЗАКРЫТ 2026-09-05 (S245): точка подмены — PlayerTargetExtractor.extract() (:638): name_forms-матч не знает npc_id (латиница клиентов) → sticky-захват прежней цели через ADDRESS_LEMMAS («обращаясь»→«обращаться»). Фикс: npc_id-ветка прямого матча. Доказано: stash-дифференциал (thief_shadow→maid_lusya на идентичном входе) + зонды 3/3 + IPT 45/45. Полевая конфигурация: «люся:» → id в скобке → промах → sticky=Торнин. — кокпит-парсер понял адресата (текст сохранил «[обращаясь к maid_lusya] привет»), player_target_pipeline выбрал Торнина (dist 0.0; suspicion: прокс-приоритет ближайшего). DM ответил за не-адресата; запись в памяти всех NPC — «player → tavern_keeper_tornin». Действие: археология резолва (player_target_pipeline vs адресный префикс кокпита); зонд (два адресных хода к разным NPC, target≠nearest). Владелец: следующая сессия.
- [ ] **FT-2 (P1, FLEE+позиции, NEW):** wait-тики: FLEE_NAV «threat=maid_lusya not found in npc_positions! Flee blocked» ×12 — NPC решает бежать от Люси каждый тик, исполнение заблокировано; сама Люся отсутствует в npc_positions idle-тиков (SPATIAL_DATA 6/7→5/6). Живая склейка RE-D4 (FLEE-массовость) + Н-53 (GROUND_TRUTH location_id). Действие: локализовать беглеца и причину исчезновения Люси из позиций (post-mortem по scene_changes_*.jsonl); зонд. Владелец: следующая сессия.
- [ ] **FT-3 (P2, память):** пусто-текстовые speech-эпизоды imp=0.80 («merchant_goran → player: ''») — речь материализуется, текст пуст. Действие: трасса producer→payload (working_memory_tick/materializer пустой text?). Владелец: следующая сессия.
| 2026-09-05 | Шаг 9 / S245 (FT-1 закрыт) | player_target_extractor.py (npc_id-ветка прямого матча) + test_ft1_target_resolution.py | ✅ ЗАКРЫТ:
| 2026-09-05 | S247 (BC-1, реализация/приёмка — ADR-O-381 dormant; вердикт P=BC-1, AG1-D8p отложен) | bc1_conclusion_test (новый SUPERBOX); IPT 45/45 (после L4-фикса INV-SILENT-FAILURE, было 44/45); ruff 6/6; causal_state_test обе серии: Люся полный parity, Горан seed-parity (PYTHONHASHSEED=0: дрожь 0.706↔0.707 = процессный hash-недетерминизм perceiving_ids, D11-класс, не регрессия) | ✅ 6/6 GREEN: A — (maid_lusya, player, is_dangerous, conf=0.8, evidence=[id]) прод-путём; B — NO-VACUUM тройной контроль (0/0/0); C — state-канал, conf=0.8, concordance; D — REJECTED; E — round-trip; OFF — dormant (store=None, scene_key=absent) | ROOT_CAUSE (дифференциал git-stash на идентичном входе: без патча id=thief_shadow/sticky-захват, с патчем maid_lusya через [S.0 MATCH] npc_id; в поле — sticky=Торнин с праймер-хода «наблюдение» + fallback-nearest). Механика: клиенты кладут резолвнутый адресат в текст латинским npc_id → name_forms-матч (кириллица) слеп → has_address_signal (лемма «обращаться») → sticky переносит прежнюю цель. Фикс: npc_id = форма прямого упоминания (предлоговая косвенность к npc_id неприменима — адресация и есть «к»). Вердикты: production-зонды 3/3 ×2 (213.51s/205.05s: id-адресация/кириллица-контроль/симметрия), GC-00 4/4 (95.08s), IPT 45/45. Честная оговорка: оба отчёта ft1_probe_* — ПОСТпатчевые прогоны (одно-блоковый протокол Мастера, «ДО» не исполнялось); красное доказательство = stash-дифференциал. Патч каноничен независимо (канонический идентификатор = легитимная форма прямого обращения) |
| 2026-09-05 | S248 (RE-D2 + FT-3 — двойное forensic из живой сессии) | router.py (fail-fast guard), working_memory_tick.py (гвард пустого хвоста), 2 детектора, evidence-лог (c1d39236) | ✅ ЗАКРЫТЫ: RE-D2 self-deadlock request_for_agent (60.03с глобальная заморозка при живой LLM 3.3–4.3с/вызов; интермиттентность = asyncness эндпоинта: game_action/game_turn async→петля→дедлок vs idle_tick def→threadpool→worker; зомби-round-trip; «тяжёлые промты» опровергнуты данными) + FT-3 producer write_npc_reactions_to_memory: пустой хвост «Имя:» в ОБА стока без фильтров (NPC_SPOKE content=""; STM-ход (npc, player) + консолидация в L2); материализатор оправдан | Хвосты: DEBT-RE-D2A (P1-арх: intelligence queue = production-форма ADR-O-377, формальный ADR там), F-NS1 (P2), O1-аудит _request_in_progress, M-08 (P3), B1/B3 design-q, avatar×2, imp=0.80-lead; BC-1 HOLD снят; _cache-эскалация RE-01; CONFIG-DEBT корроборирован (фактически Q5). IPT 44/45 (единственный red — чужой, атрибутирован) |
| 2026-09-05 | GC-09A Body Runtime (§5a.9-реестр, вердикт Мастера: Body Simulation ≠ Embodied Agency; A/B-сплит) | test_gc09_body_causality (A) + harness.read_body | ✅ GREEN: 25 production-тиков, one-way-оси живого контура сместились у обоих субъектов (blacksmith hydration 98.8→92.8 / nutrition 99.7→98.3 при load=0 — клампы fatigue/energy; maid_lusya hydration 98.5→91.0 / nutrition 99.7→98.1 + fatigue 0.375→2.25, energy 99.5→97.0 при load≈0.5 — тело персонифицированно дифференцировано) — BodyEngine→StateApplicator production-провод жив, не unit-only | Коммит 7f369e54 |
| 2026-09-05 | GC-09B Embodied Constraint (RED-детектор; вердикт Мастера: «state exists ≠ state has consequence») | test_gc09_body_causality (B) — авторизованная дельта fatigue+90/energy−90 через production StateApplicator на from_legacy-копиях живого maid_lusya; гвард мутации зелёный (fatigue 2.2→90.2) | 🔴 RED = НАХОДКА (документированное доказательство, не провал): availability A≡B — 10 интентов идентичны (approach…warn) при предельном износе; causal edge BODY→DECISION AVAILABILITY для осей выносливости отсутствует; единственный body-edge = Vital State Guard (смерть/бессознательность, compute:440). STATE→BEHAVIOR GAP — второй домен после отношений (архитектурная гипотеза State Consumer Gap, выборка 2). Звено 3 = ADR-фронт BodyConstraintResolver (BodyState→ActionConstraints→DecisionHub), НЕ патч _is_intent_available | Коммит a6708f46 (amended) |


## 6. Гейты и Stop-criteria

  ---------------------------------------------------------------------
  Переход             Stop-criteria (все ✅)
  ------------------- -------------------------------------------------
  Фаза 0 → 1          Симуляция жива: decisions \> 0 стабильно ×3
                      сессии · tracebacks \~0 · SHI=100% честно
                      (перепроверено по `scene_changes_*.jsonl`) · IPT
                      45/45

  Фаза 1 → 2          RE-01 M2/D зелёный · RelationshipWriteGate
                      покрывает 100% writers · линтер
                      `lint_relationship_engine.py` в CI · Replay
                      exact-match

  Фаза 2 → 3          §19 surprise измеряется · Prophecy green ·
                      Vertical Slice играбелен

  Фаза 3 → 4          WorldChronicle persistence green · 3 времени
                      консистентны

  Фаза 4 → 5          50+ NPC × 30+ мин стабильно

  Фаза 5 → 6          §18 активен после Belief Layer

  **Gameplay Closure  **GC-00...28, required NEG/REACH,
  (стадийный слой)    **+ назначенные acceptance-гейты стадий
                       (реестр §5a.9) зелёные для закрываемого
                       фронта; форма доказательства — по природе
                       механизма (§5a.9)**
  → дальнейшее        persistence/replay и MVP Tavern acceptance
  расширение**        зелёные; нет blocker AUD debt**
  ---------------------------------------------------------------------

### Красные флаги --- STOP

1.  DNA врут (SHI=100% при неподвижных NPC) → проверять по jsonl-логам.
2.  `PlayerBeliefModel` ≠ NPC ToM (нужен second-order BELIEVES).
3.  `MockProvider` в production-пути.
4.  Observability мутирует state.
5.  §18 до Belief Layer.
6.  Version desync (`version.txt` ↔ `pyproject.toml` ↔
    frontend-константы).
7.  `random.*`/`time.time()` в kernel-слое.
8.  **(новый)** Writer потребностей/отношений в обход
    `RelationshipWriteGate` / `update_needs` --- прямая мутация
    RelationshipStateStore запрещена (single-writer, caller-guard).
9.  **(новый)** Фронтенд/симуляция читает состояние из renderer ---
    Architectural Violation (W-TRACK контракт).
10. **(новый)** Введение состояния-сущности для
    «идеализация/влюблённость/адаптация» без anti-Bond теста (Р17-П1).

------------------------------------------------------------------------

## 7. Quick recovery --- если зашёл в тупик

  ---------------------------------------------------------------------------------
  Симптом                  Что делать
  ------------------------ --------------------------------------------------------
  0 decisions/tick         `backend/app/services/npc/decision_hub.py` --- веса
  (симуляция заморожена)   решений, связь с RelationshipStore/WriteGate; `git log`
                           на недавние писатели

  LLM молчит               `backend/logs/cds_session_*.log`;
                           `scripts/llm_server_manager.py`; LOG-GATE-UI на splash

  `movement_traversal ⏸`   `local_traversal_planner.py` +
                           `traversability_evaluator.py` + `geometry_kernel.py`

  IPT падает               какой инвариант красный в `IPT.py`; профильные линтеры
                           `scripts/lint_*.py`

  Регрессия, непонятно где `git bisect`; marker ---
                           `pytest backend/tests/canary/test_full_playthrough.py`

  Сломан контракт RE       `scripts/lint_relationship_engine.py` +
                           `architecture/relationship_engine.yaml`

  Сломан WORLD-контракт    `backend/tests/test_world_object_topology.py` +
                           `architecture/world.yaml`

  Version desync           `version.txt` + `pyproject.toml` + frontend-константы
                           синхронизировать
  ---------------------------------------------------------------------------------

------------------------------------------------------------------------

## 8. Ресурсы и ключевые файлы кода

  ---------------------------------------------------------------------------
  Подсистема                Файл (проверено)
  ------------------------- -------------------------------------------------
  Tick pipeline             `backend/app/core/tick_orchestrator.py`

  DecisionHub               `backend/app/services/npc/decision_hub.py`
                            (переехал из `cognition/`)

  DM-agent                  `backend/app/agents/dm_agent.py` (переехал из
                            корня `app/`); фаза DM ---
                            `backend/app/services/game_loop/dm_phase.py`

  Dialogue                  `backend/app/dialogue/dialogue_router.py`,
                            `backend/app/services/verbalization/`

  Relationship Engine v2    `architecture/relationship_engine.yaml`;
                            стор/gate --- см. `git show 73e0539f`
                            (RelationshipWriteGate), `53183000` (адаптер),
                            `17930e9f` (RelationshipStateStore)

  WORLD-домен               `architecture/world.yaml`, WorldObjectStore
                            (ADR-O-371)

  Movement/Spatial          `backend/app/services/spatial/`
                            (`spatial_service`, `spatial_runtime`,
                            `spatial_query_service`, `graph_compiler`) ---
                            **mypy --strict: 0 ошибок** (было 79 каскадных из
                            npc_state.py, graph_compiler.py,
                            spatial_query_service.py)

  Impact/Physiology         `backend/app/services/combat/impact_engine.py`,
                            `backend/app/domain/vital_state.py`

  Kernel RNG                `backend/app/core/kernel_rng.py`

  Tests (IPT)               `backend/tests/IPT.py` (45/45, Ruff clean:
                            `All checks passed!` --- 24 pre-existing
                            нарушения устранены)

  Canary                    `backend/tests/canary/test_full_playthrough.py`

  Lint-гейты                `scripts/lint_*.py` (13 линтеров)

  LLM-менеджер              `scripts/llm_server_manager.py`

  Session data              `backend/data/logs/scene_changes_*.jsonl`,
                            `reports/dna_history.jsonl`

  Architecture YAML         `architecture/*.yaml` (23 файла: authority,
                            body_topology, calibration, economy, frontend,
                            identity, input, memory, perception, physiology,
                            pipeline, player_cognition, relationship_engine,
                            spatial, state, temporal, verbalization, world,
                            ...)
  ---------------------------------------------------------------------------

------------------------------------------------------------------------

**Документ завершён. Фактический следующий шаг (два параллельных
фронта): (1) AG1: E2.0-c каузальный экзамен → BC-1 Conclusion (триплеты,
не фразы) --- §2a; (2) RE-01 M1b.5 → M2/D → causal
hardening/DEBT-QUIESCE. Сходятся в Фазе 1.5:
Experience→Conclusion→Expectation→Decision→Experience и Social
Testimony. После доказательства этого контура --- Unified
Appraisal/«палитра эмоций» и Predictive Perception. Active Inference,
Counterfactual, Society/SDK и масштабирование --- позже. MASTER TODO в
§5 является полным реестром, а не последовательностью немедленной
реализации. Реестр долгов сессии AG1 --- §4a (не блокирует, но не
оставлять без присвоенного владельца).**
