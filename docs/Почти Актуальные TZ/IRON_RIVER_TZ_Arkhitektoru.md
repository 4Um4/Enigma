# ОПЕРАЦИЯ «IRON RIVER» — ТЗ ДЛЯ АРХИТЕКТОРА

**Determinism & DriftLab Acceleration → Architect Specification**
Статус: CODE RESEARCH + RUNTIME MEASUREMENT → ARCHITECTURAL SPECIFICATION. Код продукта не изменён.
Дата: 2026-09-11. База: Enigma V.0.5.4.0.0 (`/home/z/my-project/enigma_extract/Enigma-V.0.5.4.0.0_-_2`).

**Метод.** Волна A–E: 9 read-only агентов (случайность / wall-clock / порядок / 14 фаз / мутации / persistence / копии / presentation / fast-forward), каждое утверждение с `file:line`. Волна измерений: реальный прогон DriftLab через production-стек (`build_game_loop()` → `GameLoop.idle_tick()`), 10 прогонов × 150–200 тиков, cProfile, D0/D1/D2-батарея детерминизма (один процесс = один прогон, сравнение канонического хеша лаборатории `drift_laboratory.py:758-776`), F1 A/B presentation-off. Окружение: Linux, Python 3.12, без llama-server (idle-путь LLM не потребляет); env-флаги фиксированы, прогоны изолированы temp-директориями лаборатории.

**Неприкосновенные законы соблюдены:** LAW-1 (LLM ≠ causal authority) подтверждён кодом — фазы 0–10 LLM не вызывают, вызов только DialogueExecutor ≤1/тик (`game_loop/__init__.py:1350-1351`); LAW-5 (DriftLab = та же физика) подтверждён — лаборатория использует реальный `TickOrchestrator` (`drift_laboratory.py:296-313`).

---

## I. VERIFIED CURRENT STATE

### I.1. Как реально работает DriftLab

| Факт | Доказательство |
|---|---|
| Вход: `python -m tests.sandbox.SUPERBOX.run drift <mode>` | `backend/tests/sandbox/SUPERBOX/run.py:43-47` |
| Стек = production: `build_game_loop(data_dir=...)`, тик = `GameLoop.idle_tick()` | `drift_laboratory.py:296, 502-518`; `game_loop/__init__.py:1168-1406` |
| Изолируется ТОЛЬКО `saves_dir` (+удаление `*.db`); `data/` (sessions, replay.db, logs) — общий | `drift_laboratory.py:244-296`; `temporal_engine.py:149` |
| Режимы: quick_debug / mass_traversal(200) / save_load_storm(5k) / chunk_migration(10k) / long_horizon(100k) / replay_determinism(2×10k) / projection_parity(10k) / idle_stability(1k) / replay_compare | `drift_laboratory.py:194-206` |
| Фактических фаз тика — 16 точек диспетча (PRE + 0, 0.6, 0.5, 1.1–1.3, 2–10), а не 14; «14-фазный» в коде не встречается | `tick_orchestrator.py:760-976`, docstring `:13-25` |
| Dual Rail shadow-валидация жива и ЗЕЛЕНАЯ во всех прогонах (0 drift A–E) | `traversal.py:144-250`; замеры: total_comparisons≈314/150 тиков, drift_A..E = 0 |
| Replay-рекордер включён ПО УМОЛЧАНИЮ (`replay_mode="passive"`) → 3×(json+zlib+INSERT+COMMIT) на тик | `config.py:56`; `game_loop/__init__.py:247-261`; `replay_store.py:136-158` |
| Деньги за простую конфигурацию: `AIDM_REPLAY_MODE=off` + `ENIGMA_DISABLE_FILE_LOGS=1` | `config.py:56`; `log_gate.py:21-33` |

### I.2. Измеренный baseline (этот сеанс + верифицированные исторические артефакты)

| Метрика | Значение | Источник |
|---|---|---|
| Чистый тик (idle, N≈6-7 NPC, 1 локация) | **p50 ≈ 103–108 мс**, mean 121–132 мс | 8 прогонов этого сеанса; исторически p50 104.6 мс (`worklog`, регрессия по 306 точкам ±2%) |
| 1 000 тиков | ≈ 140 с | worklog (верифицировано) |
| 10 000 тиков | **≈ 54–68 мин** (slope **+0.0555 мс/тик²**) | `labram_10k_partial_series.json` (3060 тиков за 575 с, kill) |
| Wall vs CPU | wall == cpu во всех прогонах — **CPU-bound, не I/O** | cProfile этого сеанса + worklog |
| RSS | ~140 МБ, стабилен | замеры этого сеанса |
| Профиль (100 тиков, 33.5 с под cProfile) | **deepcopy 71.2% cum** (15.14M вызовов ≈ 151K/тик); регидратация сцены 12.7%; Фаза 10 persistence 5.6%; json 4.5%; **честная логика решений 3.4%** | `prof_iron_river.txt` |
| F1: presentation-off (replay off + file logs off) | **−4.9%** (p50 108.2 → 102.9 мс) | A/B 2×200 тиков этого сеанса |

### I.3. D0/D1/D2 — детерминизм измерен (впервые кросс-процессно)

6 прогонов × 150 тиков, унифицированное окружение, канонический хеш лаборатории:

| Эксперимент | Условие | Результат |
|---|---|---|
| **D0 ×3** | одинаковый ambient seed 54321, PYTHONHASHSEED=0, свежие процессы | **MISMATCH — все три хеша разные**; дивергенция уже на тике ≤10 |
| **D1** | другой ambient seed 999999 | divergence присутствует так же → глобальный `random` в idle-пути не потребляется (изоляция KernelRNG подтверждена) |
| **D2 ×2** | PYTHONHASHSEED=1, 2 | divergence присутствует (на фоне D0 изолировать hash-order в этом эксперименте нельзя — см. Честные ограничения) |

Структурный диф двух полных состояний мира: **50 расхождений = 3 каузальных + 47 шумовых**:

1. `npcs[].routine._sleep_start_tick`: 10020 vs 10170 — **Δ=150 = ровно длина прогона**: глобальный счётчик тиков `world_tick.json` (`backend/data/sessions/Open_road/world_tick.json`, `temporal_engine.py:149`) НЕ изолируется лабораторией и накапливается между прогонами.
2. `scene.npc_positions.blacksmith_orm.stress_delta` — только в прогоне A; `merchant_goran.stress_delta` — только в B: реальная разница causal-траектории. Основной подозреваемый — SpeechScheduler, гейтящий ambient-диалоги по wall-clock pacing/DEDUP 2с/4с (`speech_scheduler.py:23-24, 53-69`).
3. `scene.recent_dialogues[*].timestamp` = `time.time()` — 47 дифов: wall-clock пишется ВНУТРЬ состояния сцены (`task_scheduler.py:382`) → бит-в-бит проверка невозможна даже при каузальной идентичности.

**Вывод I.3:** контракт D («same seed → same causal trajectory») **сегодня не выполняется даже в idle-ядре** при выходе за пределы одного процесса. Исторический «MATCH» Mode E — артефакт протокола: оба прогона в одном процессе (`drift_laboratory.py:842, 874`), с общим счётчиком тиков и общим wall-clock темпом.

### I.4. Что уже правильно (якоря, которые нельзя сломать)

- **KernelRNG**: seed = sha256(tick:npc_id:salt), свежий `random.Random` на каждый (тик, NPC, систему) — сдвиг одного потребителя не сдвигает чужие потоки; 17 call-sites (`kernel_rng.py:43-53`; полный реестр в отчёте A1).
- **Порядок NPC стабилен**: sorted-glob → кэш LifeEngine → list-фильтры (`npc_loader.py:316`; `life_engine.py:548`; `tick_orchestrator.py:789-799`).
- **EventBus**: строгий FIFO + фиксированный порядок подписчиков (`event_bus.py:48, 80, 114-121`).
- **StateApplicator**: детерминированный порядок доменов при `apply_batch` (`state_applicator.py:1388-1400`); RelationshipWriteGate — 0 записей мимо гейта (grep-инвариант подтверждён).
- **Tick = Pure Function Evaluation**: deepcopy сцены на входе оркестратора, одна транзакция `atomic_commit_all` на тик (`tick_utils.py:394`; `scene_state_manager.py:270-302`).
- **TimeSkipExecutor / macro_simulate / reconcile_state** — готовые каркасы closed-form (`time_skip_executor.py:492-585`; `life_engine.py:311-392, 464-512`).

---

## II. DETERMINISM BREAKERS

| Priority | Breaker | Evidence | Consequence |
|---|---|---|---|
| **P0-1** | Wall-clock в состоянии сцены: `recent_dialogues[*].timestamp = time.time()` | `task_scheduler.py:382` (write), замер: 47/50 дифов | Бит-в-бит replay-верификация невозможна в принципе; Mode E даст ложный MISMATCH при первом же ambient-диалоге |
| **P0-2** | SpeechScheduler гейтит допуск диалогов по wall-clock (pacing 2с, DEDUP 4с, DEDUP убивает задачу → CANCELLED в реестре обязательств) | `speech_scheduler.py:23-24, 53-69, 90-97`; `task_scheduler.py:234, 248-253`; замер: stress_delta-асимметрия | Допуск реплики — функция реального времени, не (state, seed) → диалоговая память/отношения дивергируют между прогонами |
| **P0-3** | Боевой RNG вне KernelRNG: `hash((str(uuid4()), actor, target))` → seed d20 | `tick_orchestrator.py:1340` (uuid4 id события) → `combat_subscriber.py:222-229` → `impact_engine.py:131` | Первая атака игрока расходится между ЛЮБЫМИ двумя прогонами, даже в одном процессе; idle-режим лаборатории это не видит |
| **P0-4** | DriftLab не изолирует `data/sessions/world_tick.json` (глобальный счётчик тиков) | `drift_laboratory.py:244-296` изолирует только saves; `temporal_engine.py:149`; замер: Δ=150 | Кросс-прогонное наследование счётчика → `_sleep_start_tick` и любые абсолютные тик-метки невалидны для сравнения; эксперименты лаборатории загрязняются |
| **P1-1** | `list(set(...))` → порядок тикования локаций от PYTHONHASHSEED | `game_loop/__init__.py:1209` → `tick_orchestrator.py:498-503, 579, 549` | Кросс-процессный порядок мутаций мира невоспроизводим; PYTHONHASHSEED нигде не фиксируется (grep: 0 совпадений) |
| **P1-2** | `witnesses = list(set - {target})` → порядок BFS слухов → carrier слуха и порядок некоммутативных дельт | `propagation.py:84-93`; `relationship_store.py:112-116` | Разные trust/stress у разных свидетелей при одинаковом seed |
| **P1-3** | Итерация set в реакциях/CFRM/L1-дельтах | `reaction_subscriber.py:293` (собственный TODO признаёт), `cfrm.py:68-80, 290-292` + `local_causal_solver.py:284-298, 437`, `tick_orchestrator.py:2193-2201` | Порядок реакционных дельт, феноменологии, TraitDriftEvent — hash-зависим |
| **P1-4** | REAL_TIME_BRIDGE: `_time.time() - last_save_ts > 60` → `reconcile_state()` мутирует stress/hunger | `scene_init.py:126-134` → `life_engine.py:464-512`; writer уже пишет 0.0 (`scene_state_manager.py:1614-1616`), но легаси-сейвы с реальным timestamp живы | Загрузка старого сейва невоспроизводима по определению |
| **P1-5** | Порядок recall памяти = `ORDER BY timestamp` (wall-clock ISO) | `sqlite_store.py:190, 212`; `:469` ties без tie-breaker | При заморозке часов / интерливинге потоков порядок «recent» произволен |
| **P1-6** | Mode E слеп: оба прогона в одном процессе, `random.seed()` не покрывает uuid4/hash-order/wall-clock | `drift_laboratory.py:817-915` | Зелёный MATCH — необходимое, но недостаточное доказательство контракта D |
| **P1-7** | Mode F (RCOC-гвард) мёртв: `_RNGCounter` не определён (NameError), режим отсутствует в mode_map | `drift_laboratory.py:1324, 194-206` | Контракт потребления RNG ничем не инструментирован |
| **P2-1** | uuid4-ids в состоянии (фолбэки thread_id/commitment_id, нарративные объекты/факты) | `post_decision.py:102, 293-295`; `narrative_extractor.py:421, 439`; `fact_extractor.py:85`; `inference_engine.py:73` | Шум state-диффов; потенциальное ветвление по ключам |
| **P2-2** | SELECT без ORDER BY в каузальном пути | `crystallized_belief_store.py:56-61`; `sqlite_store.py:318, 376, 467-471`; `sqlite_persistence_adapter.py:222`; `l1_chronicle.py:150-155` | Порядок строк формально не специфицирован (SQLite) |
| **P2-3** | env-флаги включают каузальные подсистемы, читаются при импорте; манифеста окружения нет | `desire_generator.py:24`; `activity_lifecycle_service.py:36`; `conclusion_runtime.py:25`; `intelligence_queue.py:40`; `commitment_arbiter.py:36`; `config.py:172-174` (префикс AIDM_ + .env) | «Тот же seed» на другой машине ≠ тот же мир; 9 флагов каузальны |
| **P2-4** | time_freezer не замораживает `datetime` при `from datetime import datetime` | `time_freezer.py:22-27`; `sqlite_store.py:23`; `world_scheduler.py:2`; `temporal_engine.py:35`; `scene_state_manager.py:39` | Replay-плеер видит «половинный» фриз времени |
| **P2-5** | Фоновый ThreadPool публикует NPC_SPOKE/scene-записи вне тиковой транзакции | `task_scheduler.py:64, 258, 364, 389`; `game_loop/__init__.py:1350-1356` | Интерливинг по таймингу ОС; часть каузальной цепочки живёт после Phase 10 |

Честные ограничения: P1-1/P1-2 не изолированы экспериментально в этом сеансе (D0 дивергирует и без них) — статус «статически доказано, экспериментально не изолировано»; изоляция каждого брейкера = часть P0-работы (см. V).

---

## III. PERFORMANCE BOTTLENECKS

| Rank | Hot path | Measured cost | Why |
|---|---|---|---|
| **1** | **Deepcopy-шторм («оборонительное копирование»)** | **71.2% cum** (23.9/33.5 с); 15.14M вызовов/100 тиков ≈ **151K/тик**; ~17–19 полных проходов мира на тик | Изоляция read-only фаз решена копированием, не владением: per-NPC копии ПОЛНОЙ сцены `npc_tick_pipeline.py:243, 750, 763, 815`; 11 deepcopy в `build_tick_state` вкл. дубликат nearby_npcs `pipeline_runner.py:59-80`; `create_tick_context` ×2 `tick_utils.py:394` (вызовы `tick_orchestrator.py:552, 582`); двойной коммит-копию `SSM.commit:1636-1638` + `commit_tick_result:328` |
| **2** | **Регидратация сцены 5×/тик + перечитывание editor-JSON** | 12.7% (4.25 с); `get_scene_state` 500 вызовов/100 тиков; `read_text` 1547 вызовов | Чтения до `lock_all_for_tick` идут мимо tick-scoped кэша (`scene_init.py:370-433` ×3, `game_loop/__init__.py:1194`, verify-readback `SSM:292-300`); `_find_editor_location` без mtime-кэша `SSM:728-769` |
| **3** | **Ненасыщаемый рост сцены** | slope **+0.0555 мс/тик** → 10k ≈ 62 мин; каждый из ~19 проходов дорожает | `scene_state["recent_dialogues"].append` без подрезки `task_scheduler.py:389-392` (TTL чистит только шедулерный кэш `:122-125`) |
| **4** | Persistence-конвой | Фаза 10: 5.6%; 5–15 COMMIT/тик; replay по умолчанию 3×zlib(json(сцена))/тик | `commit_phase.py:51-119`; `replay_recorder.py:19-62`; per-event COMMIT памяти `memory_manager.py:340-344` (батч-API существует и не подключён `sqlite_store.py:488-547`); fsync на каждый SceneChange `SSM:92-95` |
| **5** | INV-TEMPORAL-ISOLATION хеш | ~2.4% (2 × `json.dumps(sort_keys=True)` всего мира/тик) | `tick_orchestrator.py:1957, 1963` — проба без гейта частоты |
| **6** | Двойная гидратация L2 + NPCState round-trip | 2622 вызова `load_l2`/100 тиков; N×(2 гидратации + deepcopy×2)/тик | `npc_tick_pipeline.py:225-230` — `load_l2_state_from_runtime_dict` вызван дважды подряд, второй затирает SQLite-кэш первого; `state_applicator.py:1429` from_legacy+to_persistence_dict на каждую дельту |
| **7** | Честная симуляционная логика | **≈8%** (DecisionHub._score_all 3.4%, LifeEngine <0.5%, risk/economy ~2%) | `decision_hub.py:973-1188`; `life_engine.py` — сам «ум» НЕ является узким местом |

**Сводная карта тика (p50 ≈ 105 мс):** транспорт состояния (копии + JSON + регидратация) ≈ 85–90%; persistence/логи ≈ 5% (после F1 ≈ 0%); честная причинность ≈ 8%. Прогноз Python-фиксов: **p50 45–55 мс (2.1–2.4×)**, с устранением роста → 10k ≈ **10–25 мин** (верифицированная регрессия worklog, воспроизведена ±2%).

---

## IV. PROPOSED ARCHITECTURAL CHANGES

### Задача D-1. «Determinism Foundation: убрать энтропию из причинного контура»

- **CURRENT**: wall-clock в scene_state (`task_scheduler.py:382`), wall-clock гейты речи (`speech_scheduler.py:23-24`), боевой seed = hash(uuid4) (`combat_subscriber.py:222-229`), порядок из set (`game_loop/__init__.py:1209`, `propagation.py:84-93`, `reaction_subscriber.py:293`, `tick_orchestrator.py:2193-2201`), REAL_TIME_BRIDGE (`scene_init.py:126-134`).
- **TARGET**: всё время-подобное → оси тика (game_time/тик-счётчик); все порядки итераций, питающие решения/мутации → `sorted(..., key=npc_id/стабильный ключ)`; боевой seed → `KernelRNG(tick, actor_id, "combat")`; легаси-`last_save_real_time` принудительно 0.0 при загрузке.
- **Purpose**: сделать контракт D исполнимым: same seed + same inputs → same trajectory, кросс-процессно.
- **Exact files**: `game_loop/task_scheduler.py`, `game_loop/speech_scheduler.py`, `combat/combat_subscriber.py`, `tick_orchestrator.py:1340`, `game_loop/__init__.py:1209`, `social/propagation.py`, `events/reaction_subscriber.py`, `game_loop/scene_init.py`, `memory/sqlite_store.py` (порядок recall → `(tick, seq)`), `scene_state_manager.py:743,785` + `spatial/graph_compiler.py:820` (sorted glob).
- **Existing authority**: SSM = SSOT мира (`scene_state_manager.py:1591`); StateApplicator = единственный мутатор NPCState (`state_applicator.py:5`); RCOC (`drift_laboratory.py:147-158`).
- **What must NOT change**: KernelRNG-деривация; порядок фаз; FIFO EventBus; законы L1–L5; SSOT-границы.
- **Determinism impact**: прямой предмет задачи.
- **Performance impact**: нейтральный (сортировки O(N log N) на малых N).
- **Risk**: изменение RNG-потребления боевого контура = осознанное RCOC-2 ADR; перевод SpeechScheduler на game-time меняет темп диалогов → калибровочные прогоны.

### Задача D-2. «Replay Gate: кросс-процессная проверка контракта D»

- **CURRENT**: Mode E — 2 прогона в одном процессе (`drift_laboratory.py:817-915`), слеп к uuid4/hash-order/wall-clock/наследованию счётчика; Mode F мёртв (`:1324`).
- **TARGET**: Mode E → протокол «2 подпроцесса» (PYTHONHASHSEED фиксирован, ambient seed фиксирован, temp-окружение полное: saves + sessions + data) + канонический хеш **v2** (исключить/нормализовать шумовые поля: recent_dialogues timestamps, uuid-ids) + отчёт «первый дивергентный тик и структурный диф» (прототип реализован в этом сеансе: харнесс 6×150 тиков, диф 50 полей).
- **Purpose**: гейт P1→P2 в порядке внедрения: без красно-зелёного replay-теста нельзя отличить «починили» от «казалось».
- **Exact files**: `drift_laboratory.py` (mode_map, `_mode_replay_determinism`, `_canonical_hash`, `_EXCLUDE_FROM_SCENE_HASH:138-145`), `temporal_engine.py:149` (изоляция sessions).
- **Existing authority**: RCOC-1/2/3; `phase3_ready`-критерий (`drift_laboratory.py:121-131`).
- **What must NOT change**: production-путь; сам критерий MATCH (только расширяется валидность протокола).
- **Determinism impact**: измерительный контур.
- **Performance impact**: ноль для продакшна.
- **Risk**: низкий; канон-хеш v2 должен быть согласован (список исключений — ADR).

### Задача D-3. «Изоляция лаборатории: полное temp-окружение»

- **CURRENT**: изолируется только saves_dir; `data/sessions/world_tick.json`, replay.db, jsonl-логи пишутся в реальный `data/` (`drift_laboratory.py:244-296`; `game_loop/__init__.py:251`; `SSM:59-64`).
- **TARGET**: temp-окружение = saves + sessions + logs + replay.db (data_dir override целиком); дефолты лаборатории: `AIDM_REPLAY_MODE=off`, `ENIGMA_DISABLE_FILE_LOGS=1` (кроме режимов, тестирующих persistence).
- **Purpose**: чистота экспериментов + устранение измеренного загрязнения счётчика тиков (Δ150).
- **Exact files**: `drift_laboratory.py` (_setup/_teardown), `temporal_engine.py` (путь из settings).
- **Existing authority**: Execution Boundary Lock (`drift_laboratory.py:226-235`).
- **What must NOT change**: production-конфигурацию; SSOT.
- **Determinism impact**: устраняет P0-4.
- **Performance impact**: лабораторные прогоны −5% (измерено), прод — ноль.
- **Risk**: минимальный.

### Задача P-1. «Frozen Snapshot: один снимок на тик вместо 19 копий» (главный рычаг скорости)

- **CURRENT**: ~17–19 полных deepcopy мира/тик (III.1); 151K вызовов deepcopy/тик; 71% времени.
- **TARGET**: (а) `create_tick_context` — один снапшот на тик, переиспользуемый (`tick_orchestrator.py:552, 582` → 1 вызов); (б) `build_tick_state` — nearby_npcs = alias (не вторая копия), 7 карт модификаторов — по ссылке (редьюсер чистый, INV-TEMPORAL-ISOLATION уже доказывает отсутствие мутаций: `tick_orchestrator.py:1943-1973`); (в) per-NPC копии полной сцены (`npc_tick_pipeline.py:243, 750, 763, 815`) → передача read-only срезов (npc_positions + затронутые поля); (г) коммит — move-semantics вместо двойного deepcopy (`SSM:1636-1638` + `:328`).
- **Purpose**: убрать 60–70% времени тика БЕЗ смены языка.
- **Exact files**: `tick_utils.py:364-397`, `pipeline_runner.py:22-80`, `npc_tick_pipeline.py:117-831`, `scene_state_manager.py:304-344, 1580-1639`, `phases/integration.py:43`, `phases/affective.py:61`.
- **Existing authority**: «S-143 FIX: Deep copy to prevent TickState mutation» (`pipeline_runner.py:59`) — историческая причина; INV-TEMPORAL-ISOLATION и INV-пробы — уже существующие трипвайры безопасности; Устав 4.2.1 (коммит — единственная точка).
- **What must NOT change**: семантика изоляции фаз (копия → неизменяемое владение, не «общий мутируемый мир»); порядок фаз; результаты `apply_batch` (`state_applicator.py:1388-1400`).
- **Determinism impact**: нулевой при сохранении значений (копия → freeze); проверяется D-2 гейтом по каждому шагу.
- **Performance impact**: по этапам: (а)+(б) ≈ −9–10 мс; (в) ≈ −34 мс; (г) ≈ −7 мс; итого p50 → ~55 мс (консервативно, верифицированная регрессия).
- **Risk**: по одному сайту за PR; S-143-копии появились ИЗ-ЗА исторических мутаций → проба INV как трипвайр, fallback — вернуть одну копию. Отдельно зафиксировать выбор по `npc_tick_pipeline.py:230`: чистый вариант (b) удалить инъект+SELECT (нулевая семантика) vs семантический (a) — отдельный PR с новым baseline.

### Задача P-2. «Гигиена состояния: остановить рост и лишние проходы»

- **CURRENT**: recent_dialogues растёт бесконечно (slope +0.0555 мс/тик); сцена регидратируется 5×/тик; editor-JSON перечитывается без кэша; INV-хеш 2×/тик.
- **TARGET**: подрезка recent_dialogues (TTL по тикам, константа); regidratация только через tick-scoped identity (чтения до лока → кэш); editor-JSON кэш по mtime; INV-хеш гейт 1/100 тиков.
- **Purpose**: убрать slope (10k 62 мин → ~25 мин уже после этого) и ~15% константы.
- **Exact files**: `task_scheduler.py:389-392`; `scene_init.py:370-433`; `game_loop/__init__.py:1194`; `SSM:292-300, 728-769`; `tick_orchestrator.py:1957-1963`.
- **Existing authority**: TTL-паттерн уже есть (`task_scheduler.py:122-125`); TICK-SCOPED IDENTITY (`SSM:229-235, 441-446`).
- **What must NOT change**: содержимое состояния для решений (подрезка — только для UI-зеркала recent_dialogues; читателей решений не обнаружено — проверить grep-инвариантом перед PR).
- **Determinism impact**: положительный (меньше шума в хеше).
- **Performance impact**: slope → ~0.01 мс/тик; −6–8% константы.
- **Risk**: низкий; подрезка меняет размер сцены в JSON → старые сейвы совместимы (поле просто короче).

### Задача P-3. «Persistence: HOT/COLD разделение» (после P-1/P-2, по профилю)

- **CURRENT**: 5–15 COMMIT/тик; per-event COMMIT памяти; fsync на каждый SceneChange; replay 3×полная сериализация/тик по умолчанию.
- **TARGET**: in-memory authoritative runtime + одна checkpoint-транзакция/тик (уже существует: `unlock_tick → atomic_commit_all`); COLD-писатели (replay, memory-batch, L1, кристаллизация, relationships.json, fsync-журнал) → deferred/batched флаш; для лаборатории — replay off по умолчанию.
- **Purpose**: интерактивная и лабораторная скорость; SSOT не трогается.
- **Exact files**: `replay_recorder.py`, `memory_manager.py:340` → `sqlite_store.py:488-547` (готовый batch-API), `l1_chronicle.py:212-225`, `crystallized_belief_store.py:103-121`, `relationship_store.py:82-92`, `SSM:92-95`, `campaign_state_service.py:66`, `spatial_factory.py:56`.
- **Existing authority**: `unlock_tick` — единственный persist (`SSM:270-302`); инвариант: ни один COLD-поток не является входом решений в пределах тика (проверено статически: решения читают RAM).
- **What must NOT change**: SSOT-носители; порядок применения дельт; crash-семантику (checkpoint после полного тика).
- **Determinism impact**: нулевой (все COLD-потоки — наблюдение/восстановление).
- **Performance impact**: до −5% на прод-тике; главный эффект — на длинных прогонах и в лаборатории.
- **Risk**: средний (crash-окно потери COLD-данных расширяется до 1 тика — приемлемо, документировать).

### Задача F-1. «Fast-forward: closed-form слой над ядром» (P5, исследование)

- **CURRENT**: TimeSkipExecutor — поштучный прогон с политиками наблюдения (`time_skip_executor.py:492-585`); macro_simulate вырожден (`life_engine.py:311-392`); reconcile_state — работающий прецедент closed-form (`:464-512`).
- **TARGET** (исследовательский протокол, не внедрение): closed-form-слой для монотонных decay/EMA (полный список уравнений и порогов — в отчёте E: needs, stress/fatigue, affective load, imprints, physiology exp-decay, perceptual decay, social/reputation drift, homeostasis EMA, memory decay, traversal position); next-event scheduling по вычислимым точкам (schedule-границы, wake T*, %10 decay, %500 архив, traversal arrivals); запрет прыжка при активных диалогах/эмоциональной памяти EWMA (нелинейна, `affective_integrator.py:66-72`).
- **Purpose**: ×10–100 на «спящих» участках без изменения причинности; ядро не трогается.
- **Exact files**: новый слой над `world/time_skip_executor.py` (kernel не меняется); чтение уравнений: `social_decay_handler.py:73-82`, `reputation_engine.py:263`, `homeostasis_projector.py:22,58`, `physiology_decay_handler.py:132-179`, `idle_services.py:144-154`, `memory_manager.py:784-812`, `traversal_execution_system.py:76-111`.
- **Existing authority**: RCOC-3 (детерминизм приоритетнее равенства числа вызовов — пропуск целых тиков не ломает per-tick-независимый KernelRNG); SignificanceDetector как стоп-множество (`time_skip_executor.py:81-98`).
- **What must NOT change**: сам TickOrchestrator/Kernel; семантика событий.
- **Determinism impact**: чек-лист эквивалентности из 8 пунктов (отчёт E §5): closed-form покрытие, монотонность/точка пересечения, ноль событий в окне, нет внешних входов, RNG-гигиена целых тиков, согласованность производных, финальная идентичность (верификация Mode E/projection_parity), корректный prev_load для edge-триггеров.
- **Performance impact**: потенциал ×10–100 на idle-окнах; ~1–2× в активном социальном мире.
- **Risk**: высокий без гейта эквивалентности; поэтому P5 — после стабильного D-2 гейта.

### Чего НЕ делать (запреты сохраняются)

- Не переписывать ENIGMA на Rust — вердикт KILL подтверждён измерениями: 71% — аллокации dict-графов, которые Rust-биндинг обязан снова материализовать в Python-объектах; честная логика 8%; граница (TickState — живые объекты) несёрбисна; экономика двойного стека не покрывается выигрышем (фальсификационная таблица worklog: все 7 Rust-кандидатов ≤10–15% total при лучшем случае).
- Не создавать второй симулятор/упрощённую физику лаборатории (LAW-5).
- Не переносить семантические правила в быстрый слой (TRUTH ≠ BELIEF, LLM ≠ causal authority).
- Не «оптимизировать» до D-2 гейта: без красно-зелёного кросс-процессного replay-теста любое ускорение неотличимо от поломки.

---

## V. IMPLEMENTATION ORDER

- **P0 — MEASURE (уже выполнено, зафиксировать как baseline-артефакт)**: карта стоимости тика (III), D0/D1/D2-протокол и харнесс (этот сеанс, `scripts/iron_river_run.py`), структурный диф состояний. Критерий готовности: любой PR воспроизводит p50 и хеш-батарею на 150 тиках за <60 с.
- **P1 — DETERMINISM FOUNDATION**: D-1 (энтропия из причинного контура) + D-3 (изоляция лаборатории). Критерий: структурный диф двух кросс-процессных прогонов = 0 полей (после канон-хеша v2 — 0 каузальных полей, шум исключён декларативно).
- **P2 — FIRST REPLAY GATE**: D-2 (Mode E → 2 подпроцесса + канон-хеш v2 + first-divergence-отчёт; починка Mode F или его удаление по ADR). Критерий: зелёный MATCH кросс-процессно на 2×1 000 тиков, красный при инъекции uuid4-поля (негативный тест гейта).
- **P3 — PERFORMANCE HOT PATHS**: P-1 (frozen snapshot, по одному сайту за PR, INV-пробы как трипвайр) → P-2 (гигиена состояния) → P-3 (HOT/COLD persistence). Критерий: p50 ≤ 55 мс; slope ≤ 0.01 мс/тик; 10 000 тиков ≤ 25 мин на том же железе.
- **P4 — ACCELERATED DRIFTLAB**: лабораторные дефолты (replay off, file logs off, полное temp-окружение), прогон 10 000 тиков как штатный инструмент, сравнение сценариев (веса, сиды) сериями. Критерий: пользовательский сценарий «десятки тысяч тиков за минуты» на пост-P3 профиле; цель контракта F (10k ≤ несколько минут) оценивается повторным MEASURE (P0-цикл) — при достижении 45–55 мс/тик 10k ≈ 8–10 мин, далее только F-1.
- **P5 — ADVANCED FAST-FORWARD RESEARCH**: F-1 по чек-листу эквивалентности, гейт — D-2 + projection_parity на парах «прыжок vs поштучно». Критерий: бит-в-бит равенство состояний после прыжка T→T+Δ и поштучных Δ тиков на трёх сценариях (ночной idle, полуактивный, активный).

**Стратегический итог.** Прогноз Мастера проверен измерением: «инфраструктура тормозит» — подтверждено, но с уточнением: тормозит не persistence/диск (≈5%, wall==cpu), а **оборонительное копирование и повторная регидратация состояния** (≈85%); «LifeEngine/social» — опровергнут (≈8%); «архитектурный множитель» — подтверждён в копировальной размерности (O(N×|scene|) per-NPC копии полной сцены + O(N)×рост сцены). Rust-гипотеза закрыта измерениями (KILL); детерминизм causal core — главный долг: контракт D сегодня не выполняется кросс-процессно даже в idle (3 каузальных поля из 50 дифов), и именно он, а не язык, является минимальным архитектурным шагом к «ENIGMA исследуется быстрее, чем меняется её архитектура».
