# ENIGMA RESEARCH SWARM
## ОПЕРАЦИЯ «COUPLING RATIFICATION»
### Техническое задание архитектору (формат md) — ратификация C1–C8

**Прецедент:** THE EMERGENCE GAP (PRIMARY BOTTLENECK = MISSING COUPLING; secondary = MISSING OBSERVABILITY).
**Объект:** Enigma V.0.5.4.0.0, срез кода `backend/app/services/` (~375 файлов). Git-история недоступна (zip-выгрузка) — археология выполнена по `docs/audits/` (ADR), `docs/MUTATIONS.md`, `reports/`, `architecture/*.yaml`, комментариям и меткам аудита в коде.
**Метод:** 8 кандидатов × 8 ворот. 6 ратификационных агентов (R1–R6) + независимая верификация 12 критических точек главным агрегатором (все 12 подтверждены дословно).
**Правило операции соблюдено:** «найден writer и найден reader» ≠ «их нужно соединить». Ни один кандидат не прошёл автоматически.

---

## I. RATIFICATION TABLE

### 1.1. Сводная матрица ворот

Легенда: ✅ PASS · ⚠️ PASS с условием/оговоркой · ❌ FAIL · ◐ частично · — неприменимо.
Полное доказательство каждого статуса (файл:строка, цитаты) — в V. ARCHITECT TASK PACKAGE.

| Канд. | G1 Семантика | G2 Writer | G3 Reader | G4 Дубль-путь | G5 Петля | G6 Детерминизм | G7 Payoff | G8 Вставка | ВЕРДИКТ |
|---|---|---|---|---|---|---|---|---|---|
| **C1** player_beliefs → DTO | ✅ | ✅ | ✅ | ✅ | ✅ read-only | ⚠️ нужен `sorted()` | ✅ вкладка «Убеждения» оживает | ✅ существующее поле DTO | **🟢 RATIFIED** |
| **C2** observed_facts → /game/action | ✅ | ✅ | ❌ читателя нет | ❌ 3-й дубль (уже в player_perception) | ✅ | ✅ | ❌ (верхний ключ) | ⚠️ «в никуда» | **🟡 EXPERIMENT ONLY** |
| **C3** conclusions → consumer | ✅ | ✅ | ◐ только round-trip | ✅ | ✅ | ✅ | ❌ | — | **🔴 REJECTED** |
| **C4** npc_deltas → RelationshipStore | ⚠️ см. 1.5 | ✅ санкционирован 2 authorities | ✅ apply_batch живой | ⚠️ двойной счёт без дедупа; стратегия установлена (обязательна) | ⚠️ гасители есть, дедуп обязателен | ✅ | ✅ | ✅ existing weight | **🟢 RATIFIED** *(условный — предусловия вшиты в ТЗ)* |
| **C5** social_input_ema → social behavior | ⚠️ см. 1.6 | ⚠️ presence-канал разорван ключами | ⚠️ reader существует, отключён 1 строкой | ✅ (модуляция, не дубль) | ⚠️ нужен гистерезис порога | ✅ | ✅ после оживления | ✅ существующий слот score + существующий коэффициент | **🟢 RATIFIED** *(условный)* |
| **C6** causal event → risk_zones | ✅ одна семантика в 2 координатах | ❌ writer мёртв (wiring None) | ✅ A*/resolve_node ждут, веса стоят | ✅ ортогонален threat_gradient | ✅ отрицательная петля; нужен clamp стека | ⚠️ A* tie-break pre-existing | ✅ обход опасного места виден | ⚠️ проекция = новая политика | **🟡 EXPERIMENT ONLY** (декомпозиция: C6a-разморозка 🟢-безопасна, C6b-проекция → sandbox) |
| **C7** DESIRES + ACTIVITY_LIFECYCLE | ✅ Desire = персистентный L2.8, не L3-драйв | ✅ типизированные операции WorldObjectStore | ✅ r3 + HUD-каналы живы | ✅ AND-гейт исключает двойное насыщение | ⚠️ content-дыра: 3 порции без respawn | ✅ OFF = байт-идентичный no-op (доказано тестами) | ✅ это и есть цель контура | ⚠️ конфиг-точки включения в продукте НЕТ | **🟡 EXPERIMENT ONLY** (DESIRES = READY; ACTIVITY_LIFECYCLE = EXPERIMENTAL) |
| **C8** workplace tag mismatch | ⚠️ triple authority (§13.3) | ✅ данные писались под archetype-ключ | ✅ один reader, fallback глотает miss | ✅ приоритет жёсткий (activity_map ≫ теги) | ✅ петли нет | ✅ | ⚠️ превентивный (латентный) | ✅ modifier ~8 строк | **🟢 RATIFIED** (низкий приоритет, гигиена контракта) |

**Итог: 🟢 × 4 (C1, C4*, C5*, C8) · 🟡 × 3 (C2, C6, C7) · 🔴 × 1 (C3). E6/E7 (Schelling, habit) — OUT OF SCOPE, как предписано.**

### 1.2. Ключевые пере-оценки против исходного списка KEEP (EMERGENCE GAP)

| Прошлый вывод | Ратификация | Что изменилось |
|---|---|---|
| «player_beliefs вычисляется, но не кладётся в DTO» | 🟢 подтверждено и уточнено | Цепь сломана в **трёх** местах: (1) `_player_beliefs` не передан в конструктор; (2) production-вызов вообще не передаёт `epistemic_store` в builder; (3) инъекция S189 мертва — параметр не попадает в `_TickContext`. Но читатель (вкладка), поле DTO и доктрина (§IV/§XII, §18 Устава) существуют → чистый wire-fix |
| «маршрутизация npc_deltas» | 🟢 условно | Главный риск не «проводка», а **двойной счёт**: ReactionSubscriber и NpcDialogueSubscriber уже покрывают те же (npc, target, событие); `aggregate_deltas` суммирует, не дедуплицирует. Gate 4 требует source-identity — установлено: `StateDeltas.source` = имя канала, не event.id → нужен `event_id` |
| «social_urge ← EMA» | 🟢 условно | Обнаружен **разорванный presence-канал**: детектор шлёт `npc_a/npc_b`, projector читает `source_id/target_id` → вклад присутствия в EMA = 0 всегда. Оживление reader — 1 строка (`decision_hub.py:1311`), но без починки writer-контракта EMA останется каузально инертной |
| «память насилия risk_zones» | 🟡 понижено | Писатель не «не подключён», а **мёртв кодом**: единственный call-site жёстко передаёт `dynamic_field=None` (reduction.py:227-229), притом оркестратор честно передаёт поле (:2112). Плюс два несоединённых store (traces ↔ SpatialOverlay) и нулевой тестовый контур. Поведенческую проекцию в prod без sandbox — нельзя |
| «включение desires+activity» | 🟡 подтверждено с оговорками | Причины OFF установлены: срез EAT-only, content-дыра (3 порции без respawn → перманентный голод), незакрытая проводка outcome→память, отсутствие конфиг-точки, доктрина «Флаги вместо решений» требует dev-приёмки |
| «наблюдаемость-проводки» | 🟢/🔴 разделено | C1 — да; C2 — нет (дубль); C3 — **осознанный dormant**, проводка потребителя раньше источника нарушит дисциплину BC-1/BC-2 |

---

### 1.3. ОСОБАЯ ЗАДАЧА: OFF-ФЛАГИ (§3 ТЗ) — WHY IS IT OFF?

**DESIRES_ENABLED — вердикт: READY** (как продюсер данных; смысл только в паре).
- Guard: `desire_generator.py:24-39`, call-time чтение env; OFF доказан тестом `test_off_is_byte_identical_noop` — ключ `npc["desires"]` даже не создаётся; отказ = warning, тик живёт (G2-паттерн ADR-O-378).
- При ON: идемпотентный upsert `desire_id="d:<subject>"`, urgency=clamp01(need), provenance, born_tick. Сам по себе не меняет поведения (конвертер гейтнут вторым флагом) — мёртвые данные при соло-включении.

**ACTIVITY_LIFECYCLE_ENABLED — вердикт: EXPERIMENTAL.**
- Guard: `activity_lifecycle_service.py:36-74`; Фаза 0.7; движение — через существующий рельс MovementEngine ДО Гейта①.
- Почему НЕ prod-default (улики): (1) каталог из одной записи EAT; (2) **content-дыра**: 3 порции (obj_42-44 tavern.json), respawn нет → длинная сессия = перманентный голод 1.0; (3) открытый пункт CONSEQUENCE_REACHES_MEMORY (`activity_outcome` публикуется, подписчиков нет); (4) INTERRUPT/возобновление не покрыто прогоном; (5) `_ONSET_URGENCY=0.5` — самопризнанный CALIBRATION_CANDIDATE; (6) приёмочные метрики ТЗ 9.2 не замерены живой сессией; (7) сырых логов прогонов в снапшоте нет (git утрачен) — claim «IPT 45/45, SUPERBOX 12/12» держится на записях MUTATIONS S252/ADR-O-384.
- **AND-семантика пары** (`activity_lifecycle_service.py:77-100`): `living_activity_owns_needs()` = ACTIVITY ∧ DESIRES — защита от «спирали голода» (владение насыщением без исполнителя). Флаги включаются ТОЛЬКО парой.
- **Отчёты ab_on/ab_off — чужие**: это Drift Laboratory (ADR-O-201), A/B-доказательств для C7 в reports/ НЕТ.

**Археология причин OFF (сводка):** сознательный карантин по доктрине ТЗ Living Activity («анти-паттерн "Флаги вместо решений"»); фон хрупкости потребностного трека (серия ADR-147–159, напр. ADR-159 shelter_urge→1.0 навсегда); легаси-осциллятор hunger («пила» 0.56, 25.9% пустых прибытий, пинг-понг ×79) заменён терминалом outcome — поведение needs-канала меняется, что требует замеров NEI/DNA. ЗАПРЕЩЁННЫЙ вывод «код существует → включаем» не сделан: prod-включение только после закрытия respawn + memory + метрик.

---

### 1.4. ОСОБАЯ ЗАДАЧА: SPATIAL MEMORY (§5 ТЗ) — контракт WORLD EVENT → SPATIAL CONSEQUENCE

```
[1] VIOLENT EVENT → EventBus → CombatSubscriber          🟢 живо (tick_orchestrator.py:129)
[2] Фаза 8 reduction: execute_reduction_phase(…, dynamic_field=…)  🟢 оркестратор передаёт (:2112)
    → _execute_handler → _apply_handler_result(dynamic_field=None, …)  🔴 РАЗРЫВ (reduction.py:227-229)
[3] RISK TRACE: TracePayload(safety_confidence, −0.2, ttl=100) → DynamicAffordanceField.apply_trace
    🔴 DEAD CODE — блок недостижим (reduction.py:263-292)
[4] SPATIAL OVERLAY: SpatialOverlay.risk_zones (0..1) — писателей 0, читается только build_overlay_from_scene
    🔴 два несоединённых store (traces ↔ overlay), моста нет
[5] TTL/DECAY: step_decay ×0.9/тик, delete <0.01 (Фаза 0.5, каждый тик)  🟢 живо
    ⚠️ поле TracePayload.ttl нигде не читается — «TTL=100» в доках не соответствует действительности
[6] NAVIGATION: A* cost += risk*4.0 (spatial_service.py:621); resolve_node −risk*4.0 (:511)
    🟢 читатели живы и ждут; риск всегда 0.0 → no-op
[7] OCCUPANCY: движение → crowd_density → cost; movement_density → drag → скорость  🟢 живо
```

Контракт ратифицируемой проекции (C6b, sandbox): `node_id = normalize_id(zone_id)`;
`risk[node] = clamp(−trace × k, 0, 1)`, k=0.5 (1 удар → risk 0.1 → +0.4 к cost ребра);
stacking: clamp в apply_trace (|v| ≤ 5.0) или только в проекции; TTL фактический = decay-хвост ≈ 37–44 тика;
removal = deletion-порог 0.01. Запись через `scene_state["spatial_overlay"]` — ЗАПРЕЩЕНА (W-Track RT2: Direct-rail FE-пуш вытирает незащищённые ключи). Только runtime `svc.set_overlay()` с hash-инвалидацией кэша путей. Новый spatial brain не создаётся — всё на существующих DynamicAffordanceField + SpatialService.

Различение трёх «опасностей» (Gate 4-доказательство): `risk_zones` = свойство места (безличное, 0..1, A*);
`safety_confidence` trace = та же семантика в координатах стигмергии (накопительный float, «уверенность↓», комната-грейн);
`threat_gradient` = психика конкретного NPC (per-NPC, decay 0.05/тик) — **семантически ортогонален**, дублирования нет.

---

### 1.5. ОСОБАЯ ЗАДАЧА: NPC↔NPC SOCIAL LOOP (§6 ТЗ) — полный аудит C4

**Карта всех путей записи отношений (Gate 4, исчерпывающе):**

```
SOURCES: [S1] player/combat-события · [S2] NPC↔NPC реплики/действия · [S3] слухи
                    │
        ВСЕ ЗАПИСИ ЧЕРЕЗ ОДИН ГЕЙТ: RelationshipWriteGate.apply()
        whitelist {trust, fear, debt, respect, attraction}, NaN-guard, clamp
                    │
        StateApplicator.apply_batch (SOCIAL=40) → RelationshipStore.update()
        headroom-сатурация Δ×(100−|v|)/100, clamp ±100
                    │
W1a ReactionSubscriber (свидетели+ЦЕЛЬ, Фаза 8)   ПРИМЕНЯЕТСЯ   дедуп: НЕТ, source="reaction"
W1b SocialSubscriber (слухи + NPC_SPOKE fallback) ПРИМЕНЯЕТСЯ   trust_delta×100
W1c SocialDecayHandler (0.01/тик к base)          ПРИМЕНЯЕТСЯ   стабилизатор петли
W2  NpcDialogueSubscriber (та же _BASE_DELTAS SSOT!) ПРИМЕНЯЕТСЯ  ambient ×0.2
W3  RulesSubscriber (GIVE_MONEY +5 и пр.)         ПРИМЕНЯЕТСЯ
W4  ActionConsequenceCompiler (HELP +20/−10…)     ПРИМЕНЯЕТСЯ
W5  MemoryManager-фасад                           ПРИМЕНЯЕТСЯ
─────────────────────────────────────────────────
W6  ✖ РАЗОРВАН: SocialDeltaEngine → DecisionResult.deltas → TickMutation.npc_deltas
    → ctx.significant_events (pipeline_runner.py:138) → commit() ИГНОРИРУЕТ
    (scene_state_manager.py:1624-1629 «AUDIT #10 VERDICT=OFF 2026-08, _SHADOW_CAUSALITY_DISABLED»)
    Остаточные read-only потребители: TimeSkip SignificanceDetector, сбор npc_id для L1, INV-CAUSAL-PROVENANCE
```

**Ответы на 6 вопросов ТЗ:**
- **A. Почему не применяются?** Трёхзвенно: (1) S1-рефактор «pure reducer» — StateApplicator убран из ядра, обещание «мутация будет выполнена TickOrchestrator'ом» (npc_tick_pipeline.py:784-785) не выполнено; (2) AUDIT #10 отключил единственный persistence-потребитель (WorldProjectionBuffer); (3) типовое несоответствие — буфер ждёт dict с `.get("type")`, дельты — StateDeltas-объекты.
- **B. Ошибка или сознательное исключение?** Гибрид: отключение потребителя — сознательное (датированный вердикт аудита); выброс самих дельт — **потерянный write-маршрут**, противоречащий трём authorities: `relationship_engine.yaml:99-110` («writable: state_applicator_only», «update_phase: events — SocialDeltaEngine»), `authority.yaml:761-767` («runtime mutations via DeltaBuffer»), обещанию в коде.
- **C. Совместимость полей:** trust/fear — буквальная (шкалы ±100, знаки совпадают, SDE pre-saturation ±100); SDE не эмитит debt/respect/attraction; `affection_delta` вне whitelist гейта (не переносить).
- **D. Уже применяются другим каналом:** ReactionSubscriber (те же события, цель НЕ исключена — :295), NpcDialogueSubscriber (общая SSOT-таблица `_BASE_DELTAS`), RulesSubscriber/ACC (частичное пересечение по help/insult). Наивное включение = систематический двойной счёт.
- **E. Source tag:** ОБЯЗАТЕЛЕН. Сейчас `source` = имя канала/event_type, event.id не переносится → «одно событие, два канала» неотличимо от «два события». Прецедент уже в коде: `trace_id = f"{event.id}:{target}:player"` (DeltaGate).
- **F. Где дедуп:** ТОЛЬКО в архитектурно легитимной authority — продюсерская маршрутизация в Фазе 10 (`commit_phase.execute_persistence` до flush delta_buffer) + политика в `aggregate_deltas` (единственное место редукции). ЗАПРЕЩЕНО: второй писатель мимо гейта (D2-инвариант), дедуп в WriteGate («routing-слой, не хранилище»), дедуп в DecisionHub (запретное ребро по `lint_relationship_engine.py:51-61`). Интеграция линтер не нарушает (не онтология, не новое ребро).

**Петля (Gate 5):** EVENT → дельта → Store → relationship_cache → DecisionHub scoring/SocialTargetResolver (hostile-порог trust<−50) → новый интент → новые события. Тип — усиливающая в минус (страх/месть). Гасители существуют: headroom-сатурация, clamp ±100, SocialDecayHandler 0.01/тик, hysteresis BehaviorMask, causal_ledger cap 20. Достаточно ТОЛЬКО при дедупе — двойной счёт ускорил бы петлю ×2 систематически.

---

### 1.6. ОСОБАЯ ЗАДАЧА: SOCIAL_URGE (§4 ТЗ) — семантическая модель

| Уровень | Измеряется? | Где | Единицы |
|---|---|---|---|
| SOCIAL EXPOSURE (присутствие) | ⚠️ измеряется, **но не доставляется** (битый контракт ключей: `npc_a/npc_b` vs `source_id/target_id`) | spatial_event_detector.py:29-30,124-127 → social_input_projector.py:71-76 | порог 2.0/3.5 м; вклад был бы 0.05 |
| MEANINGFUL CONTACT (диалог) | ◐ частично: listen=0.15 жив; speak зависит от продюсера; `_INPUT_INTERACT=0.20` мёртвая константа | social_input_projector.py:78-114 | прирост EMA 0..1, clamp |
| RELATIONSHIP QUALITY | ✅ но ВНЕ EMA — SocialPayload идентичностно-слеп (нет поля «от кого»), trust/fear не входят | relationship_engine.yaml SSOT | trust/fear −100..100 |
| SOCIAL DEPRIVATION | ❌ не интегрируется нигде; `_SOCIAL_PRESSURE_SCALE=1.5`, `_SOCIAL_RELAXATION_RATE=0.05` — мёртвые (satiation удалён по ADR-O-312) | behavior_modifiers.py:39-42 (на лету) | — |
| SOCIAL NEED | 🔴 расщеплён на 2 несвязанные ветки: `social_urge` = линейный таймер 0.08/тик (не от людей); `social_outgoing` = вычисляется из EMA, но читатель мёртв | life_engine.py:1282-1291; decision_hub.py:1311 | 0..1; ≤0.5 |

**Ответы на 5 вопросов §4:** (1) из пяти уровней реально измеряются только контакт-диалог (частично) и качество отношений (вне EMA); (2) `social_input_ema` — EMA **речевого внимания** с полураспадом 50 тиков, вклад присутствия = 0 (битый контракт), качество и идентичность собеседника не входят; (3) присутствие сейчас НЕ удовлетворяет social need — need удовлетворяется **местом/ярлыком** («socializing»→сброс), а не контактом; (4) качество (trust) не должно входить в EMA напрямую (сохраняем идентичностную слепоту EMA как «сырое внимание»), доверие уже модулирует выбор цели отдельно (trust-фильтр resolver'а) — смешение создало бы дубль; (5) минимальная точка интеграции — существующий слот `"social"` скоринга + существующий коэффициент `_NEED_DECAY_PER_TICK=0.08` (модуляция, не новый канал).

**Личность:** setpoint = 0.2 + 0.6·gregariousness существует, но ни один конфиг NPC не задаёт gregariousness → у всех 0.5, интровертов/экстравертов нет. Петля без конфигурации личностей была бы синхронной (все идут в таверну одной волной).

**Числа петли (Gate 5):** при EMA≈0.6 → порог 0.4 за ≈29 тиков; период осцилляции ≈45–60 тиков (медленные видимые волны «к таверне — от таверны»); текущий таймер: 0→0.5 за 6.25 тика, bang-bang без гистерезиса, синхронно у всех. Не хватает: гистерезис вход/выход порога (0.5/0.2) + cooldown повторного интента. Прецедент срыва — ADR-159 (shelter_urge без BED → вечная 1.0).

---
## II. DEPENDENCY GRAPH

Порядок работ построен заново (не из прошлого отчёта): сначала нулевое-поведенческое wiring, затем каузальные связки, затем долгие эксперименты, затем наблюдаемость. E6/E7 — вне графика до отдельной ратификации.

```
УРОВЕНЬ 0 — SAFE WIRING (нулевое изменение поведения мира; контракт/проводка/диагностика)
├─ T1  C1: player_beliefs → WorldSnapshotDTO.player_beliefs (+sorted)        [зависимостей нет]
├─ T2  C6a: разморозка писателя S91 (проброс dynamic_field в reduction)      [зависимостей нет]
│        след пишетcя, читателя нет → поведение мира НЕ меняется; открывает диагностику
├─ T3  C8: workplace-нормализация (цепочка кандидатов npc_id→archetype) + гигиена  [зависимостей нет]
└─ T4  C4-шаг0: лог-зонд масштаба дублей SDE×Reaction в execute_persistence  [зависимостей нет]
         (данные для дедупа; ноль мутаций)
                 │
УРОВЕНЬ 1 — CAUSAL COUPLING (изменение поведения; каждое — за env-флагом/откатом)
├─ T5  C4: event_id → маршрутизация npc_deltas → дедуп → A/B-катание         [зависит: T4]
│        (NPC↔NPC социальная память; sandbox → prod)
└─ T6  C5: починка presence-контракта → оживление слота social → need-модуляция
         + гистерезис порога + gregariousness в 2-3 конфига                  [зависимостей нет; sandbox → prod]
                 │
УРОВЕНЬ 2 — LONG-RUN EXPERIMENT (только dev-профиль, приёмка по метрикам)
├─ T7  C6b: проекция trace→risk_zones (k, clamp) → set_overlay              [зависит: T2]
│        sandbox-тесты T1-T5 → A/B сравнение путей → prod
└─ T8  C7: конфиг-точка env + respawn food_portion + memory-подписка
         → пара флагов ON в dev → метрики ТЗ 9.2 → NEI/DNA-приёмка           [зависит: T6 частично (social-срез позже)]
                 │
УРОВЕНЬ 3 — OBSERVABILITY (презентационный слой)
└─ T9  C2-эксперимент: вкладка «Факты» читает существующий
         world_snapshot.player_perception.observed_facts (frontend-only)     [зависит: ничего; от бэкенда не зависит]
                 │
УРОВЕНЬ 4 — OPTIONAL EMERGENCE RULES
└─ E6/E7 (Schelling-слагаемое, habit law) — ОТЛОЖЕНО до ратификации после стабилизации T5-T8
```

### Реестр задач (dependency / rollback / success / kill)

| ID | Задача | Dependency | Rollback | Measurable success | Kill condition |
|---|---|---|---|---|---|
| T1 | C1 wire-fix | — | удалить 1 аргумент конструктора | /game/action `world_snapshot.player_beliefs` == записям стора (agent_id=="player"); вкладка рендерит записи | утечка NPC-записей в поле игрока (тест-барьер) |
| T2 | C6a wiring | — | вернуть `dynamic_field=None` (1 строка) | combat-событие → `_traces[loc][zone]["safety_confidence"] < 0`; поведение A* побайт-идентично пустым трейсам | изменение путей A* при пустом overlay (тест T5 regress) |
| T3 | C8 hygiene | — | git revert 1 файла | тег-путь находит узел по archetype для боевых id; test_workplace_affordance не вакуусно-зелёный | коллизия 2 NPC одного archetype в зоне без детерминированного tie-break |
| T4 | C4-зонд | — | удалить лог | окно 30 мин: счётчики (event_id, npc, target) пересечений > 0 подтверждены/опровергнуты | — (read-only) |
| T5 | C4 интеграция | T4 | env-флаг OFF + ADR-зеркало «VERDICT=OFF» | player_attacks → trust цели изменён РОВНО ОДИН раз (не −8−10); Drift Lab: дрейф C/D/E = 0 при ON | двойной счёт в прогоне; дрейф > 0; замедление петли страха/мести не подтверждено метриками |
| T6 | C5 интеграция | — | env-флаг OFF (guard по образцу C7) | A/B: score(TALK) Δ≥0.3 при social_outgoing=0.3; период колебаний 30–80 тиков, амплитуда не растёт; 2 NPC с разным greg ходят в разной фазе | синхронная волна всех NPC; амплитуда растёт (runaway); NEI-аномалии |
| T7 | C6b проекция | T2 | пересборка overlay без risk (k=0) | risk=1.0 на промежуточном узле → find_path обходит; hash кэша инвалидируется; decay <0.01 за ≤44 тика | NPC массово избегают НЕопасных зон (порог по occupancy-метрике); set-итерация дала разные пути при разных PYTHONHASHSEED |
| T8 | C7 включение | T6 (для social-среза каталога) | снять env, рестарт | пустые прибытия ≤10%, пинг-понг ≤×5, r3-строка «Торнин: ест» ≥1/сессию, NEI ≠ 0 и возвращается к 0 после еды | спираль голода; [ACTIVITY] fault чаще N/тик; дубль-писатели в npc_positions.activity |
| T9 | C2 frontend-эксперт | — | скрыть вкладку | вкладка «Факты» рендерит player_perception.observed_facts; юзабилити-приёмка | дубль визуального канала (факты повторяют то, что видно сцены) |

---

## III. TOP 3 RATIFIED CHANGES

### ГЛАВНЫЙ ВОПРОС ОПЕРАЦИИ (§10): какое минимальное изменение даёт максимальный переход от «SIMULATION COMPUTES» к «WORLD BEHAVES»?

**PRIMARY CHANGE — T5 (C4): замыкание NPC↔NPC социального контура** — маршрутизация `TickMutation.npc_deltas` → `delta_buffer` → `StateApplicator.apply_batch` с event-identity и дедупом.

Почему именно это:
1. **Это единственный кандидат, санкционированный двумя authorities + обещанием в коде** (`relationship_engine.yaml:99-110`, `authority.yaml:761-767`, npc_tick_pipeline.py:784-785) — его ратификация не создаёт новое право, а восстанавливает нарушенный контракт causal spine.
2. **Это последний разорванный каузальный цикл межагентной памяти**: NPC-поступок → personality-модулированная дельта (fanatic/coward ×2.12 разброс — уникальный вклад SocialDeltaEngine, которого нет у witness-правилок) → SSOT отношений → следующие решения ТРЕТЬИХ NPC (SocialTargetResolver отсекает hostile, trust модулирует интенты) → новые поступки. Сегодня решатель честно считает дельты, которые тихо умирают в commit() — буквальный «SIMULATION COMPUTES» без «WORLD BEHAVES».
3. Минимальная дельта — класс «existing weight»: маршрут через живой `apply_batch`, ноль новых сторов/полей/подсистем; гасители петли уже в контуре (headroom, clamp, decay 0.01/тик).
4. Payoff виден без нового UI: цели диалогов/помощи/угроз у NPC меняются от их истории взаимодействий друг с другом — игрок читает это в поведении и end_screen relationship_texts.

**SECONDARY CHANGE 1 — T1 (C1): проводка player_beliefs → DTO.** Самое дешёвое ратифицированное изменение (существующее поле + существующий читатель + доктринальное разрешение): вкладка журнала «Мои убеждения» оживает без единого изменения поведения мира. Даёт игроку учетную книгу причинно-следственных выводов — максимум наблюдаемости за одну строку кода (+sorted).

**SECONDARY CHANGE 2 — T6 (C5): оживление социального гомеостаза.** Три точечных фикса на существующих весах: presence-контракт (2 ключа), слот `social` (1 строка на месте `= 0.0`), модуляция `_NEED_DECAY_PER_TICK` дефицитом. Переводит социальность из синхронного таймера в медленные (45–60 тиков) гетерогенные волны «одинокий идёт к людям, сытый расходится» — первый паттерн, который игрок читает как «город живёт своей жизнью», а не «NPC выполняют расписание».

**Что сознательно НЕ в тройке:** C6b (память насилия) — самый фотогеничный паттерн, но требует новой проекционной политики (k, clamp, стекинг) и sandbox-цикла; идёт вторым эшелоном после T2. C7 — контур доказан, но prod-включение блокировано content-дырой и незакрытой памятью outcome.

---

## IV. REJECTED CHANGES

| Что отклонено | Кандидат | Основание (ворота) | Условие возврата |
|---|---|---|---|
| Проводка `observed_facts` в верхний ключ ответа /game/action | C2 | G3 FAIL (читателя нет), G4 FAIL (3-й дубль: те же строки уже в `world_snapshot.player_perception.observed_facts`), G7 FAIL | фронтенд-эксперимент докажет ценность вкладки «Факты» → тогда 1 ключ + читатель одним коммитом |
| Подключение DM/UI-потребителей к `scene_state["conclusions"]` / epistemic_records | C3 | G3 PARTIAL (только round-trip), G7 FAIL; dormant-статус спроектирован: «CONCLUSION──X──>EXPECTATION закрыт до BC-2» (MUTATIONS:914,950), `conclusion_delta` зарезервирован DeltaGate; проводка создала бы потребителя раньше источника | созревание BC-2 (Expectation) → новый цикл ратификации с доказательством читателя |
| Запись risk через `scene_state["spatial_overlay"]` | C6 | W-Track RT2: Direct-rail FE-пуш заменяет сцену целиком и вытирает незащищённые ключи; нарушение «builder читает только финальное состояние» | только runtime-путь `svc.set_overlay()` |
| Prod-default включение пары DESIRES/ACTIVITY_LIFECYCLE | C7 | G5 content-дыра (перманентный голод без respawn), незакрытый CONSEQUENCE_REACHES_MEMORY, отсутствие конфиг-точки, анти-паттерн «Флаги вместо решений» | закрыть respawn + memory-подписку + метрики ТЗ 9.2 в dev-профиле |
| Переименование тегов мест в npc-id (вариант A) | C8 | рантайм-эффект нулевой (путь мёртв), теряется семантика «место роли» для будущих NPC | не требуется — вариант B закрывает контракт в обе стороны |
| Новый store персональных рабочих мест (binding-таблица) | C8 | оверкилл для 6 NPC (нижняя ступень шкалы вставки) | — |
| Перенос дедупликации в WriteGate / DecisionHub / RelationshipStore | C4 | WriteGate — «routing-слой, не хранилище» (write_gate.py:10-20); DecisionHub — запретное ребро (lint_relationship_engine.py:51-61); Store — нарушение D2-инварианта single-writer | только продюсерская маршрутизация Фазы 10 + политика aggregate_deltas |
| Перенос `affection_delta` из SDE в Store | C4 | поле вне whitelist гейта → ContractValidationError; не извлекается StateApplicator | отдельная ратификация с расширением whitelist |
| KILL-кандидаты прошлой операции (подтверждено) | E6/E7, memetic, expectation_store, LLM-in-core, ETKE-IK | вне скоупа операции; выводы EMERGENCE GAP остаются в силе | отдельная операция |

---
## V. ARCHITECT TASK PACKAGE

Формат §8 ТЗ. Полные пакеты — только для 🟢 RATIFIED (C1, C4, C5, C8). Для 🟡-кандидатов — краткие EXPERIMENT BRIEFS в конце раздела.

---

### R-01 · C1: Проводка player_beliefs в WorldSnapshotDTO

**TASK ID:** R-01 (T1, уровень SAFE WIRING)

**PROBLEM:** Убеждения игрока вычисляются каждый тик, но не достигают единственного спроектированного читателя — вкладки журнала «Мои убеждения». Вкладка вечно пуста; фича Phase 8.2 (S199) существует только на бумаге DTO и фронтенда.

**CODE EVIDENCE:**
- `backend/app/services/integration/world_snapshot_builder.py:96-98` — `_player_beliefs = [r for r in epistemic_store.to_dict() if r.get("agent_id") == "player"]`;
- `world_snapshot_builder.py:114-138` — в конструктор `WorldSnapshotDTO(...)` аргумент НЕ передан (мёртвая локальная переменная);
- `backend/app/domain/snapshot.py:247-249` — поле `player_beliefs: list = field(default_factory=list)` существует, комментарий ссылается на §IV/§XII;
- `frontend/game_screen.py:2181` — `self.current_snapshot.get("player_beliefs", [])`; `frontend/analysis_renderer.py:75-108` — рендер формата EpistemicStore.to_dict() готов;
- Устав §18 (АРХИТЕКТУРНЫЙ_УСТАВ:751-760): EpistemicStore — единственный belief substrate для ВСЕХ агентов, включая player.

**ROOT CAUSE:** Незавершённая интеграция S189/Phase 8.2: проекция обрывается трижды — (1) аргумент не передан в конструктор; (2) production-вызов `phases/integration.py:613-623` не передаёт `epistemic_store` в builder; (3) инъекция S189 мертва — `tick_utils.create_tick_context` принимает store (:377,390), но не кладёт в `_TickContext` (dto.py:426-456).

**ARCHITECTURAL CONTRACT:** builder — чистый маппер «читает только финальное состояние» (доктрина 3.4, комментарий builder:5-6); убеждения НЕ мутируют World State (CAUSAL_CONTRACT:45); UI_DOCTRINE §IV запрещает выдачу убеждений NPC, §XII разрешает журнал игрока; эпистемический барьер by design (r3_direct_builder.py:144) не задевается — проводка направлена игроку о нём самом, единственная защита — фильтр `agent_id == "player"`.

**ALLOWED FILES:** `backend/app/services/integration/world_snapshot_builder.py`; опционально `backend/app/services/dto.py`, `backend/app/services/npc/tick_utils.py`, `backend/app/services/phases/integration.py` (для свежести того же тика). Тесты: `backend/tests/`.

**FORBIDDEN CHANGES:** не удалять фильтр `agent_id == "player"`; не менять EpistemicStore/ConclusionStore; не добавлять новые поля онтологии; не проводить NPC-убеждения в этот же канал; не менять WorldSnapshotDTO обратно-несовместимо; не включать сюда C3 (conclusions — отдельный вердикт 🔴).

**IMPLEMENTATION DIRECTION:** Вариант А (канонический): в builder при отсутствии параметра читать `scene_state.get("epistemic_records", [])` с тем же фильтром → `player_beliefs=sorted(records, key=(last_updated_tick, subject_id, predicate))` → аргумент конструктора. Опционально: поле `epistemic_store` в `_TickContext` + проброс в `phases/integration.py:613` (закрывает и мёртвую S189-инъекцию). Вариант Б (инъекция через Phase9IntegrationDeps) — отклонить: противоречит уставу builder.

**ACCEPTANCE CRITERIA:** /game/action и /world_state возвращают `world_snapshot.player_beliefs`, побайтно равные отфильтрованным записям стора; порядок стабилен между процессами; пустой store → `[]` (не None); фронтенд рендерит запись с полосой confidence.

**REQUIRED TESTS:** (1) unit: фильтрация agent_id; (2) контрактный: wire-поле == стор; (3) детерминизм: разные PYTHONHASHSEED / порядок upsert → идентичный порядок; (4) round-trip пустого стора; (5) барьер: NPC-записи отсутствуют в поле.

**DETERMINISM GATE:** `sorted()` обязателен — to_dict() insertion-order, порядок upsert зависит от set-итерации слушателей (инцидент S247/4, MUTATIONS:954). Wall clock/рандом в пути отсутствуют.

**OWNERSHIP GATE:** писатель проекции — оркестратор (S83.1/S193-паттерн); builder — projection-only; UI-читатель — analysis_renderer. Дублей нет (end_screen/perceived_narratives/диалоги — другие данные).

**OBSERVABILITY PAYOFF:** CAUSE (NPC заявил/игрок увидел кражу) → WORLD CHANGE (EpistemicRecord) → VISIBLE PATTERN (строка + полоса уверенности в журнале, клавиша J) → PLAYER INFERENCE (учёт, кому верил). Замечание для владельца UI: рендер показывает `subject predicate` без object_id и локализации предиката — косметика вне скоупа.

---

### R-02 · C4: Маршрутизация npc_deltas в RelationshipStore (замыкание NPC↔NPC контура)

**TASK ID:** R-02 (T4+T5, уровни SAFE WIRING → CAUSAL COUPLING)

**PROBLEM:** Personality-модулированные социальные дельты решателя (SocialDeltaEngine) собираются в TickMutation.npc_deltas и тихо выбрасываются: commit() их игнорирует, единственный persistence-потребитель отключён вердиктом AUDIT #10. Контракт authorities нарушен; NPC↔NPC память о поступках неполна.

**CODE EVIDENCE:**
- `backend/app/services/npc/decision/social_deltas.py:112-207` — SDE: `SocialPayload(trust_delta, fear_delta)`, apply_saturation ±100, npc_* → target=actor_id, source=event_type;
- `backend/app/services/npc/npc_tick_pipeline.py:783-791,824` — сборка npc_deltas; обещание «мутация relationship_store… будет выполнена TickOrchestrator'ом»;
- `backend/app/services/pipeline_runner.py:138` — `ctx.significant_events = mutation.npc_deltas or []`;
- `backend/app/services/scene_state_manager.py:1624-1629` — «AUDIT #10 VERDICT=OFF (2026-08)… _SHADOW_CAUSALITY_DISABLED»;
- `backend/app/services/npc/state_applicator.py:1344-1414` — `apply_batch` живой, SOCIAL=40;
- `backend/app/services/social/relationship_write_gate.py:40-42` — whitelist trust/fear/debt/respect/attraction;
- `architecture/relationship_engine.yaml:99-110`, `architecture/authority.yaml:761-767` — санкционирование;
- `docs/MUTATIONS.md:199,204` — «StateApplicator mutation — зафиксировано как долг S1».

**ROOT CAUSE:** Сознательное отключение потребителя (AUDIT #10) + незакрытый долг S1 по второму маршруту = де-факто регрессия контракта. Плюс типовое несоответствие: WorldProjectionBuffer ждёт `List[Dict]` с `.get("type")`, дельты — StateDeltas-объекты.

**ARCHITECTURAL CONTRACT:** ALL WRITES → ONE GATE → STORE (write_gate.py:3-5; D2-греп-тест вечный); мутации только через StateApplicator (relationship_engine.yaml N5); WriteGate — routing-слой, не хранилище; DecisionHub не пишет Store (запретное ребро lint_relationship_engine.py:51-61); «одна дельта = один домен» (ADR-013); significant_events остаются read-only для TimeSkip/проб.

**ALLOWED FILES:** `backend/app/services/phases/commit_phase.py` (маршрутизация Фазы 10); `backend/app/services/tick_utils.py` (aggregate_deltas — политика дедупа); `backend/app/domain/models/state_delta.py` (поле event_id); `backend/app/services/npc/decision/social_deltas.py` (проброс event.id в source-контекст). Тесты: `backend/tests/`.

**FORBIDDEN CHANGES:** любая запись в RelationshipStore мимо Gate/StateApplicator; дедуп внутри WriteGate или RelationshipStore; новая онтология RE / новые узлы (линтер закрытого канона 37+8 узлов); правка allowlist D2-грепа; перенос дедупа в DecisionHub; включение WorldProjectionBuffer (AUDIT #10 остаётся OFF); перенос `affection_delta` без отдельной ратификации.

**IMPLEMENTATION DIRECTION (этапы):**
1. Шаг 0 (T4, ноль риска): лог-зонд в `execute_persistence` — считать SOCIAL-дельты tick_mutation.npc_deltas и пересечения с delta_buffer по (npc_id, target, source) за тик → масштаб дублей подтверждён на живом прогоне.
2. Шаг 1: `StateDeltas.event_id` (или переиспользование trace_id-прецедента DeltaGate `f"{event.id}:{target}:{npc_id}"`); source = канал (канонизировать: "sde"/"reaction"/"social_decay").
3. Шаг 2 (T5): в `commit_phase.execute_persistence` до flush — SOCIAL-дельты `ctx.tick_mutation.npc_deltas` → `ctx.delta_buffer`; значимые события для TimeSkip оставить как слепок.
4. Шаг 3: дедуп в маршрутизации + политика в `aggregate_deltas`: ключ `(event_id, npc_id, target, field)` → первая запись wins по приоритету канала (direct SDE > witness-reaction); разные события — существующая ADDITIVE-редукция.
5. Шаг 4: env-флаг канона (default OFF → smoke A/B → ON) + зеркало аудита с возвратной точкой.
6. Двойная сатурация (SDE pre-saturation + Store headroom): прогнать калибровку D3-стиля SDE↔Store; при искажении масштаба — выбрать одно место сатурации (решение фиксировать в ADR).

**ACCEPTANCE CRITERIA:** одно событие player_attacks изменяет trust цели РОВНО один раз; npc_*-реплика меняет npc-пару ровно один раз; Drift Lab (quick_debug) дрейф классов C/D/E = 0 при ON; TimeSkip SignificanceDetector и INV-CAUSAL-PROVENANCE зелёные; IPC/DNA-метрики без регресса; скорость петли страха/мести (тройка «агрессия→fear→hostile-порог→избегание») соответствует калибровке, не ускорена ×2.

**REQUIRED TESTS:** `test_npc_deltas_reach_relationship_store`; `test_no_double_count_reaction_vs_solver` (одно событие → одна база, дедуп по event_id); `test_dedup_across_channels_dialogue` (NPC_SPOKE tone npc_insults → ровно одно изменение); `test_significant_events_consumers_unchanged`; `test_determinism_apply_batch_social` (два прогона → побайтно равный JSON стора); регресс D2-грепа + D3-паритета (существующие, не трогать allowlist).

**DETERMINISM GATE:** apply_batch детерминирован (стабильная сортировка _DOMAIN_APPLICATION_ORDER, SOCIAAL=40, без RNG); сатурация порядкозависима — порядок закреплён контрактом; set-итерация perceiving_ids (PYTHONHASHSEED) на результат per-pair не влияет, но seed-политику IPT зафиксировать.

**OWNERSHIP GATE:** SDE — канонический обновляющий сценарий TrustFearScalars (relationship_engine.yaml:107); StateApplicator — единственный писатель; дедуп — в продюсерской маршрутизации Фазы 10 + политике aggregate_deltas; линтер не нарушается (механика, не онтология).

**OBSERVABILITY PAYOFF:** CAUSE (поступок NPC A против B) → WORLD CHANGE (trust/fear пары в SSOT) → VISIBLE PATTERN (B избегает/преследует A; выбор собеседников сдвигается; реплики диалогов и end_screen relationship_texts отражают историю) → PLAYER INFERENCE («после той стычки они не здороваются»). Прирост против статус-кво: цель получает personality-модулированную реакцию вместо плоской witness-правилки.

---

### R-03 · C5: Оживление социального гомеостаза (EMA → поведение)

**TASK ID:** R-03 (T6, уровень CAUSAL COUPLING)

**PROBLEM:** social_input_ema каузально инертен: инфраструктура sensor→delta→clamp→persist→decay работает и DecisionContext.social_outgoing/social_incoming доезжают до DecisionHub каждый тик, но слот скоринга захардкожен в 0.0, need-канал — независимый таймер, а вклад присутствия в EMA всегда 0 из-за разорванного контракта ключей. Одиночество NPC не влияет на поведение.

**CODE EVIDENCE:**
- `backend/app/services/spatial/spatial_event_detector.py:124-127` — payload `{npc_a, npc_b, distance}`;
- `backend/app/services/events/social_input_projector.py:71-76` — читает `payload["source_id"]/["target_id"]` → оба None → 0 дельт (presence мёртв); `_INPUT_PRESENCE=0.05` не срабатывает никогда;
- `backend/app/services/npc/decision_hub.py:1311` — `social_mod = 0.0  # ADR-O-312…` ; `:1167-1186` — `_removed_social_satiation_modifier` определён, вызовов 0;
- `backend/app/services/npc/life_engine.py:98-101,1282-1291` — `social_urge` +0.08/тик, порог 0.5, сброс по ярлыку (bang-bang);
- `backend/app/services/npc/behavior_modifiers.py:39-56` — setpoint=0.2+0.6·gregariousness, tolerance 0.1, cap 0.5;
- `backend/app/services/npc/homeostasis_projector.py:22,57-71` — decay −EMA·ln2/50;
- `backend/app/services/npc/npc_state.py:718` — `social_input_ema: float = 0.0` (persist/restore :1100-1101,1246-1247).

**ROOT CAUSE:** Трёхточечный разрыв контура: (1) мёртвый reader — ADR-O-312 делегировал EMA «behavior_modifiers», чьи выводы никто не читает; (2) мёртвый presence-канал writer'а — несовпадение ключей payload; (3) несвязанность need-канала (таймер вместо функции дефицита). Замечание: test_social_homeostasis.py:103 вручную подкладывает speaker_id — маскирует разрыв.

**ARCHITECTURAL CONTRACT:** EMA — идентичностно-слепое «сырое речевое внимание» (качество/trust НЕ входят — доверие уже модулирует выбор цели отдельно; смешение = дубль); setpoint — от личности (gregariousness); P-регулятор с tolerance-полосой; ADR-O-312: слот social скоринга = точка возврата гомеостаза в скоринг; ADR-159-урок: need-порог обязан иметь гистерезис.

**ALLOWED FILES:** `backend/app/services/events/social_input_projector.py` (ключи payload); `backend/app/services/npc/decision_hub.py` (1 строка слота); `backend/app/services/npc/life_engine.py` (модуляция коэффициента + гистерезис порога, только social_urge); `config/npc/individuals/{2-3 файла}.json` (gregariousness). Тесты: `backend/tests/`.

**FORBIDDEN CHANGES:** не менять SSOT отношений; не добавлять trust/identity в SocialPayload; не трогать `_INPUT_INTERACT` (0.20 — мёртвая константа, отдельное решение); не создавать новый need/store/подсистему; не менять физиологию других needs; не удалять decay-подписку Фазы 0.5.

**IMPLEMENTATION DIRECTION:**
1. Presence-контракт: для NPC_PROXIMITY_CLOSE читать `npc_a/npc_b` (fallback на старые ключи) → воскрешение `_INPUT_PRESENCE`.
2. Reader (1 строка): `social_mod = self._removed_social_satiation_modifier(intent, decision_ctx)` вместо `= 0.0`.
3. Need-модуляция (только social_urge): `deficit = max(0, setpoint − ema)`; `setpoint = 0.2+0.6·greg`; рост `+0.08·min(1, deficit/0.6)`; при ema>setpoint — мягкий разряд `−0.04` вместо bang-bang сброса.
4. Гистерезис порога: вход 0.5 / выход 0.2.
5. Конфиг: `psyche.gregariousness` у 2-3 NPC (интроверт ~0.2, экстраверт ~0.8) — иначе волна синхронна.
6. Флаг канона (default OFF) + A/B-катание.

**ACCEPTANCE CRITERIA:** proximity-событие даёт 2 дельты ×0.05 (сейчас 0 — red-тест); score(TALK) Δ≥0.3 при social_outgoing=0.3; 200-тиковый прогон: период колебаний EMA/urge 30–80 тиков, амплитуда не растёт; 2 NPC с разным greg — разные фазы; реплей идентичен.

**REQUIRED TESTS:** T1 A/B скоринга; T2 urge при (ema=0.9, greg=0.2) не растёт, при (ema=0.0, greg=0.8) растёт 0.08/тик; T3 presence red→green; T4 анти-осцилляция (аналог test_homeostatic_stability — заметить: sandbox-версия дублирует УСТАРЕВШУЮ модель с social_satiation — синхронизировать); T5 replay-детерминизм trace EMA.

**DETERMINISM GATE:** порядок итерации гомеостаза по all_npcs_raw — loader сортирует (npc_loader.py:316); события — FIFO; пары proximity — insertion-order npc_positions (player добавляется последним) — детерминировано при фиксированном порядке загрузки, явную сортировку пар зафиксировать тестом. Разрешить UNKNOWN тик-интервала: GAME_TICK_INTERVAL_SECONDS=10 (constants.py:212) против комментариев «60 сек/тик» — влияет на интерпретацию периодов, не на код.

**OWNERSHIP GATE:** writer — SocialInputProjector (Phase8Handler, легитимный); reader — DecisionHub-слот (точка, предусмотренная ADR-O-312) + LifeEngine-коэффициент; дублей нет (need-канал модулируется, не дублируется; trust-фильтр остаётся отдельным).

**OBSERVABILITY PAYOFF:** CAUSE (EMA ниже setpoint−0.1) → WORLD CHANGE (NPC идёт к людям / не уходит; перегруз штрафует социальные интенты) → VISIBLE PATTERN (медленные волны «к таверне — от таверны», гетерогенные по личностям; traversals + activity-ярлыки видны в wire) → PLAYER INFERENCE («трактирщик толчётся к людям, вор жмётся по углам»).

---

### R-04 · C8: Нормализация workplace-идентичности

**TASK ID:** R-04 (T3, уровень SAFE WIRING)

**PROBLEM:** Контракт ADR-O-326 (`workplace:<npc_id>`) никогда не был реализован в данных: локации размечены archetype-ключами (`workplace:tavern_keeper|maid|thief|guard`), код ищет npc-ключи (`workplace:merchant_goran` …). Mismatch тотален (0/6 NPC), но латентен — тег-слой не достигается, все 6 NPC попадают на места через activity_map.

**CODE EVIDENCE:**
- `backend/app/services/npc/life_engine.py:2009-2026` — `_workplace_tag = f"workplace:{_npc_id}"`; точный фильтр `all(t in n.tags)` (spatial_service.py:434-437) → miss → fallback «любой узел роли» (:2028-2031);
- локации: `frontend/map_editor/campaigns/Open_road/locations/tavern.json:236,263,290` (`workplace:tavern_keeper/thief/maid`), `city_gate.json:2043` (`workplace:guard`), market_square — тегов нет вовсе;
- конфиги: id = `merchant_goran|maid_lusya|guard_borko|thief_shadow|tavern_keeper_tornin|blacksmith_orm`; поля occupation НЕ существует;
- окаменелость: `role_resolver.py:28-29` — `"workplace:lusya"` (короткий legacy-id, не существует); артефакт `tavern.json:318-320` (`"kitchen bed 2$; bed; bed 2"`);
- контракт: `docs/MUTATIONS.md:58-59`, `ENIGMA_EPOCHS_REPORT.md:446-453` (S147/ADR-O-326).

**ROOT CAUSE:** Данные писались под archetype-ключ при npc-контракте кода; расхождение не замечено, потому что путь мёртв (activity_map приоритетен по ADR-150-правилу). Тест test_workplace_affordance.py закрепляет mismatch фиктивными короткими id ("guard"/"maid") — вакуусно-зелёный.

**ARCHITECTURAL CONTRACT:** §13.3 Устава — множественные писатели в одно поле = DOUBLE TRUTH; ADR-150: activity_map = приоритетный авторитет, SpatialService = fallback; решение G1: activity_map = SSOT персональной привязки; workplace-теги = role-affordance слой МЕСТА (archetype-ключ); правило фиксируется в authority.yaml.

**ALLOWED FILES:** `backend/app/services/npc/life_engine.py` (цепочка кандидатов, ~8 строк); `backend/app/services/npc/role_resolver.py` (удаление мёртвых записей); `frontend/map_editor/campaigns/Open_road/locations/tavern.json` (артефакт-тег); `backend/tests/test_workplace_affordance.py`. Опционально `architecture/authority.yaml` (ownership-правило).

**FORBIDDEN CHANGES:** переименование тегов локаций в npc-id (теряет семантику «место роли»); новый binding-store; правки graph_compiler (сквозной транзит тегов — не автор); правки map_editor-валидации вне скоупа.

**IMPLEMENTATION DIRECTION:** (1) `_tag_candidates = [workplace:{npc_id}] + [workplace:{_archetype}]`, перебор до первого hit; (2) гигиена: удалить `"workplace:maid"/"workplace:lusya"` из _TAG_ROLE_MAP (роль узла задана JSON role — manifest_override приоритетнее), почистить мусорный тег `kitchen_bed_2`; (3) задекларировать ownership в authority.yaml; (4) дополнить тест кейсами с боевыми id (`maid_lusya`) и без activity_map-записи.

**ACCEPTANCE CRITERIA:** NPC без activity_map-записи резолвится на узел по archetype-тегу (Люся→kitchen по `workplace:maid`, Борко→guard_post по `workplace:guard`); для 6 боевых NPC резолв позиций не изменяется (arb-лог побайтно идентичен); коллизия двух NPC одного archetype разрешается детерминированно (скоринг → node_id↑).

**REQUIRED TESTS:** расширенный test_workplace_affordance (боевые id + fallback-цепочка + коллизия); регресс test_life_engine/test_spatial_service.

**DETERMINISM GATE:** resolve_node завершает `sort(key=(-score, node_id))` — детерминировано; candidate-перебор — фиксированный порядок списка.

**OWNERSHIP GATE:** writer тегов — человек в map_editor (free-text) + шаблоны; код — читатель с fallback-иерархией; activity_map — SSOT привязки NPC↔узел.

**OBSERVABILITY PAYOFF:** превентивный: новые NPC/калибровочные пресеты без activity_map не «уезжают» на TRANSITION-узлы или «9 палаток → tent_1 для всех»; debugging payoff — контракт ADR-O-326 замыкается в обе стороны, вакуусный тест становится содержательным.

---

### EXPERIMENT BRIEFS (🟡 — только sandbox/dev, полный пакет после приёмки)

**X-01 · C6b — проекция памяти насилия** (зависит от T2-разморозки; sandbox → prod).
Суть: `risk[node] = clamp(−trace·0.5, 0, 1)` по zone→node (`normalize_id`), через `svc.set_overlay()` (hash-инвалидация готова). Политика: clamp стека в apply_trace (|v|≤5.0) или в проекции; TTL фактический = decay-хвост 37–44 тика (поле ttl либо читать, либо удалить — решение в ADR); light_levels не трогать (отдельный кандидат, писателей 0); movement_density не трогать, но зафиксировать соседний латентный freeze-дефект drag≥1.0 при N≥10 (motion_pipeline.py:199, без clamp) отдельным релеем. Тесты T1-T5: wiring-red, проекция+клип, обход маршрутом, decay-детерминизм (PYTHONHASHSEED), A* bit-идентичен на пустых трейсах. Kill: массовое избегание неопасных зон; расхождение путей между процессами.

**X-02 · C7 — включение Living Activity** (dev-профиль; срез EAT).
Суть: пара флагов ТОЛЬКО вместе (`living_activity_owns_needs`); предусловия: конфиг-точка env (сегодня флаг негде выставить в продукте), respawn/пополнение food_portion, MemoryManager-подписка на `activity_outcome`. Лестница: 39 unit-тестов → SUPERBOX eat_vertical 12/12 → IPT → Drift Lab ON-vs-OFF (дрейф C/D/E = 0) → метрики ТЗ 9.2 (пустые прибытия ≤10%, пинг-понг ≤×5) → живая LLM-сессия (NEI ≠ 0, возврат к 0 после еды). Kill: спираль голода; [ACTIVITY] fault-шторм; дубль-писатели ярлыка.

**X-03 · C2 — фронтенд-эксперимент «Факты»** (нулевая бэкенд-дельта).
Суть: вкладка читает существующий `world_snapshot.player_perception.observed_facts` (механизм game_screen.py:2181). Верхний ключ в routes.py НЕ добавлять. Критерий продолжения: факты не дублируют видимый визуал сцены и несут расследовательскую ценность; иначе — закрыть вкладку-заглушку.

---

### РЕЕСТР UNKNOWN (передаётся владельцу, не блокирует 🟢-задачи)

1. Тик-интервал: 10 сек (constants.py:212) vs комментарии «60 сек/тик» — интерпретация периодов петель.
2. Масштаб пересечения SDE×Reaction на живом тике — закрывается зондом T4.
3. Двойная сатурация SDE+Store не калибрована (D3 покрывал Gate↔Store).
4. Судьба AUDIT #10-документа: вердикт живёт только в комментарии (полный текст, вероятно, в утраченной git-истории).
5. PYTHONHASHSEED в проде (влияет на tie-break A* через set-итерацию — pre-existing, вне скоупа, зафиксировать отдельно).
6. ADR-O-360 (унификация light/density/danger) — ревизия не найдена в выгрузке; может быть рамкой для C6b.
7. Статус тройного притязания на социальную истину: VillageMemoryField (ADR-O-212) vs RelationshipStore-SSOT (S135) vs EMA-канал.
8. Запланирован ли для вкладок «Гипотезы»/«Факты» PlayerBeliefModel/InferenceEngine (DEBT-E1); замечено попутно: `_all_inferences` (integration.py:553) вычисляется и теряется.

---

### ЭПИЛОГ ОПЕРАЦИИ

Ратификация подтвердила центральный диагноз EMERGENCE GAP, но уточнила его природу: **это не «несоединённые фрагменты», а преимущественно нарушенные собственные контракты** — обещание оркестратору в коде (C4), спроектированный и брошенный на середине проводки слот (C5, C1), размороженный wiring'ом писатель (C6), контракт ADR-O-326 без данных (C8). Единственный кандидат, где «соединить» означало бы «создать потребителя раньше источника» — C3 — отвергнут. Мир Enigma не ждёт новых подсистем: он ждёт, пока четыре легитимных контура дойдут до конца своих собственных чертежей.

**ФИНАЛЬНЫЙ ОТВЕТ §10:** PRIMARY = T5/C4 (NPC↔NPC социальная память через санкционированный маршрутизацией StateApplicator); SECONDARY = T1/C1 (оживление журнала убеждений) и T6/C5 (гомеостатическая социальность). Всё остальное — уровни ниже по dependency graph, каждый со своим rollback и kill-condition.
