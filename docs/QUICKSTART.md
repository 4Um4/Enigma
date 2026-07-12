# ENIGMA QUICKSTART (Архитектурный гайд)

> **Назначение:** Этот документ — точка входа для разработчиков и LLM-ассистентов.
> Он объясняет, как устроен проект, где искать код и как работает один тик симуляции.

---

## §0. КАК ЧИТАТЬ ФАЙЛЫ (читать ПЕРВЫМ, до любых действий)

### ⚠️ Жёсткое правило: читать ЦЕЛИКОМ, не последние N строк

**ЗАПРЕЩЕНО** читать `.md` и `.py` файлы через:
```powershell
Get-Content path | Select-Object -Last 60      # ❌ НЕПРАВИЛЬНО
Get-Content path | Select-Object -First 60     # ❌ НЕПРАВИЛЬНО
Get-Content path | Select-Object -Index (N..M) # ❌ НЕПРАВИЛЬНО (для .md)
```

**ОБЯЗАТЕЛЬНО** читать ЦЕЛИКОМ:
```powershell
Get-Content docs/MUTATIONS.md                   # ✅ ПРАВИЛЬНО (без пайпов)
Get-Content "docs/ADR (Architecture Decision Records).md"  # ✅ ПРАВИЛЬНО
```

**Почему:** 60 строк из 700 = 8% файла. LLM видит хвост, не видит структуру, нумерацию, начало секций. Результат — сломанные документы: дублирующая нумерация (два раздела 3.7), разбитые таблицы (5 строк на одной линии), незакрытые code fences, вставка блока не в ту секцию.

**Исключение:** Файлы длиннее 2000 строк — читать по частям через `Select-Object -Index (0..499)`, `(500..999)`, и т.д. Но ОБЯЗАТЕЛЬНО все части, от начала до конца. `Select-Object -Last` запрещён ВСЕГДА.

### Порядок чтения для НОВОЙ сессии (Шаг 0: Синхронизация реальности)

Перед любым изменением кода прочитать ЦЕЛИКОМ:

1. `docs/MUTATIONS.md` — что сделали другие архитекторы (последняя сессия S##).
2. `docs/ADR (Architecture Decision Records).md` — новые запреты и онтология.
3. `docs/DTO Registry (Реестр контрактов).md` — актуальные поля DTO.
4. `reports/LAST_SESSION.md` — красные инварианты, DNA-метрики.
5. Целевые файлы для изменения — ЦЕЛИКОМ, не последние 30 строк.

**ЗАПРЕЩЕНО** предлагать изменения на основе памяти из прошлой сессии. Только живая верификация через полное чтение.

---

## 1. Карта файлов (Что читать первым)

Если ты открыл проект, начни с этих файлов в строгом порядке:

1. **`docs/00_CAUSAL_CONTRACT_v2.0.md`** — Высший закон. Архитектурные запреты и онтология.
2. **`docs/АРХИТЕКТУРНЫЙ_УСТАВ_ENIGMA.md`** — Устав. Иерархия слоёв, фазовая модель, законы сериализации, эпистемического обоснования, единичного времени.
3. **`backend/app/services/tick_orchestrator.py`** — Сердце игры. Оркестрирует 13 фаз тика. Читает состояние, запускает фазы, возвращает `TickResultDTO`.
4. **`backend/app/services/npc/life_engine.py`** — Мозг NPC. Генерирует интенты (желания) на основе потребностей и расписания.
5. **`backend/app/services/npc/npc_tick_pipeline.py`** — Pure reducer (ADR-TZ09-1). Принимает `TickState`, возвращает `TickMutation`. Единственный execution kernel.
6. **`backend/app/services/npc/decision_hub.py`** — Воля NPC. Оценивает интенты через Utility-скоринг.
7. **`backend/app/services/scene_state_manager.py`** — Физика мира. Владеет позициями, транзитами (FSM `transition_traversal`), применяет `SceneChange`.
8. **`backend/app/services/game_loop/task_scheduler.py`** — Materialization layer (ADR-O-313). Исполняет `QueuedTask` (диалоги, торговля) через `TaskExecutor`, публикует `WorldEvent` через `Materializer`.
9. **`frontend/game_screen.py`** — Глаза игрока. Главный цикл Pygame, обработка ввода, рендер, speech bubbles.

---

## 2. Один ход игрока (End-to-End Trace)

Что происходит, когда игрок нажимает Enter, введя «подойди ко мне»?

```text
1. Frontend (game_screen.py)
   Игрок вводит текст → api_client.py отправляет POST /api/game/action на бэкенд.

2. API (routes.py)
   Бэкенд принимает request → собирает ChatTurnRequest → вызывает GameLoop.run_turn().

3. Pre-Kernel (game_loop/phase_1_input.py)
   Текст сжимается в IntentSemanticField (MOVE, target="player").
   IntentPressureResolver вычисляет нагрузку на психику.
   Собирается MovementRequest(actor_id, target_actor_id) — ADR-O-314.
   Формируется InterventionEvent (ADR-TZ08-1). Ядро не знает 'player'.

4. Ядро (TickOrchestrator.execute())
   - Фаза 0: LifeEngine.tick() → SceneChange (cognitive) + MovementIntent.
   - Фаза 0.5: Time Decay (game_time_seconds += 60). Время не останавливается.
   - Фаза 1: InterventionEvent → DirectiveInterpretationSubscriber → WillpowerGate.
   - Фаза 5: TickState → NpcTickPipeline.run() (pure reducer) → TickMutation.
     MovementEngine (Movement Bridge) → SceneChange → apply_with_shadow_observation (Dual Rail).
   - Фаза 6: CommunicationIntent → EventDTO. ATTACK → ActionWindup (2 тика подготовки).
   - Фаза 8: Layered Reduction → delta_buffer → StateApplicator.apply_batch().
   - Фаза 9: WorldSnapshotBuilder → WorldSnapshotDTO.
   - Фаза 10: SQLitePersistenceAdapter.atomic_commit().

5. Post-Kernel (game_loop)
   PerceptionProjector → PlayerPerceptionDTO (peripheral_cues, manifestations).
   DM-агент генерирует нарратив через LLM.

6. Frontend (game_screen.py)
   Получает WorldSnapshotDTO → scene_renderer.py:
   - velocity (ETKE-IK) → интерполяция по инерции.
   - active_traversals (FSM) → интерполяция по path_waypoints.
   - speech_bubbles → облачка реплик над NPC.
   - peripheral_cues → цветной текст под именем NPC («Замер на месте»).
   Pygame рисует кадр.
```

---

## 3. Триаж багов (Если что-то сломалось)

| Симптом | Где искать | Что проверять |
|---------|------------|---------------|
| **Время застыло** | `tick_orchestrator.py` (`_advance_idle_time`), `scene_init.py` | Растёт ли `game_time_seconds`? Возвращается ли `final_scene_state` из ядра (ADR-311)? Читается ли время из `scene_state`, а не из `shared_context`? |
| **NPC не двигаются** | `life_engine.py`, `movement_engine.py`, `tick_orchestrator.py` (`_process_traversals`) | Генерируются ли `MovementIntent`? Создаётся ли `TraversalState`? Не блокирует ли `SpatialIntentGate` (same-node collapse)? |
| **NPC телепортируются** | `frontend/scene_renderer.py`, `game_screen.py` (`_resolve_visual_xy`) | Работает ли MotionRenderRouter (velocity vs waypoints)? Приходит ли `velocity` от бэкенда (ETKE-IK)? Не перетирает ли frontend `local_position` для NPC в `MOVING`? |
| **LLM генерирует мусор** | `response_validator.py`, `dm_agent.py`, `dm_response_normalizer.py` | Проходит ли текст валидацию? Не обрезает ли валидатор нормальные реплики (CJK, 4-я стена, повторы)? Не фолбэчит ли на «Ничего не произошло»? |
| **Реплики NPC не видны** | `task_scheduler.py`, `dialogue_executor.py`, `game_screen.py` | Публикуется ли `NPC_SPOKE` в EventBus? Попадает ли в `recent_dialogues`? Совпадают ли timestamp-ы (game_time vs wall-clock)? |
| **Падает IPT** | `backend/tests/IPT.py` | Какой инвариант упал? Смотреть `suspect_files` в выводе. |
| **Тики не идут (PFI=100%)** | `tick_orchestrator.py`, `pipeline_runner.py` | Не падает ли `NpcTickPipeline.run()`? Нет ли `NameError`/`AttributeError`? Прогнать `DriftLaboratory` (3 тика). |
| **Красные инварианты в LAST_SESSION** | `reports/LAST_SESSION.md` | Какой INV-XXX красный? Смотреть `suspect_files`. Чинить ПЕРВЫМ, до новых фич. |

---

## 4. Глоссарий (28 ключевых терминов)

### Базовые концепции

- **Tick (Тик)** — Один дискретный шаг симуляции (60 секунд игрового времени, `GAME_TICK_INTERVAL_SECONDS`).
- **game_time_seconds** — Единственный источник времени в симуляции (ADR-O-302). Монотонно растёт. Wall-clock (`time.time()`) запрещён в simulation layer.
- **TickOrchestrator** — Оркестратор, управляющий всеми 13 фазами тика. Единственная точка входа — `execute()`.
- **InterventionEvent** — Внешнее событие (действие игрока), попадающее в ядро. Заменило `dm_ctx` (ADR-TZ08-1). Ядро не знает слова 'player'.
- **TickState** — Immutable snapshot состояния мира для передачи в reducer (ADR-TZ09-1). Содержит preloaded data + read-only сервисы.
- **TickMutation** — Pure result работы `NpcTickPipeline.run()`. Содержит `npc_deltas`, `communication_intents`, `movement_intents`, `l1_drift_events`, `memory_events`.
- **TickResultDTO** — Единый результат тика ядра. Возвращает `status`, `world_snapshot`, `npc_contexts`, `final_scene_state` (ADR-311).

### Перемещение и пространство

- **TraversalState** — Состояние перемещения NPC (от узла А к узлу Б). Lifecycle: PENDING → MOVING → COMPLETED/CANCELLED. Управляется `SceneStateManager` через FSM `transition_traversal()` (ADR-TRAV-FSM).
- **SceneChange** — Проекция свершившегося физического изменения. Не триггер, а результат.
- **MovementEngine** — Слой 2 Execution. Конвертирует `MovementIntent` в `SceneChange`. Единственный владелец — `TickOrchestrator` (ADR-066).
- **SpatialService** — Единый авторитет по пространственной геометрии графа. Собирается через `SpatialFactory.build_for_campaign()` (ADR-TZ04-4).
- **Boundary Node** — Граница между локациями (дверь, выход из города). Интерфейс, не место обитания (ADR-145).
- **ETKE-IK** — Система непрерывной кинематики (микроперемещения внутри узла через `DriveVector` → `velocity`). Параллельная ветка `MovementIntent` (ADR-ETKE-ACT1).
- **MotionRenderRouter** — Фронтенд-диспетчер: `velocity` (ETKE-IK) → инерция; `active_traversals` (FSM) → waypoints (ADR-S90.4).

### Состояние и мутация

- **DeltaBuffer** — Буфер дельт. Все изменения состояния сначала падают сюда, затем применяются атомарно через `StateApplicator.apply_batch()`.
- **StateApplicator** — Единый мутатор состояния. Выполняет L5 Post-Commit Validation (`sum(drives)==1.0`, bounds, NaN, ADR-O-207).
- **PerceptualKernel** — Субъективная модель восприятия NPC (угрозы, неопределённость, `somatic_urgency`). Затухает в idle (Rule 38).
- **DecisionHub** — Единственное место, где NPC принимает решение (Utility-скоринг). Принимает `rng: KernelRNG` (ADR-O-301).
- **WillpowerGate** — Шлюз проверки конфликта воли (подчинится ли NPC приказу игрока). Вызывается ОДИН раз за цикл.
- **KernelRNG** — Единственный источник случайности в kernel layer. Привязан к `(tick, npc_id, salt)` (ADR-O-301). `random.*` запрещён.

### Идентичность и память

- **L1Chronicle** — Append-only SQLite-персистентная история деформации личности NPC (ADR-O-208). Удаление запрещено.
- **BeliefCrystallizationEngine** — L2.5. Проецирует `EvidenceOfPersistence` (L1.5 статистика) в `CrystallizedBelief` (fear/trust). Асимметричная травма ×6 (ADR-O-307).
- **EffectiveDrives (L3)** — Эфемерная проекция драйвов. Рождается каждый тик, умирает в конце. Кэширование запрещено (L3-P1).
- **CFRM (Causal Field Resolution Model)** — Локальная модель причинности NPC. `LocalCausalSolver`, `FieldDisturbance`, `EventBuffer`.

### Materialization и задачи

- **TaskScheduler** — Materialization layer (ADR-O-313). Живёт в `game_loop`. Потребляет `QueuedTask` из `scene_state["pending_tasks"]`, исполняет через `TaskExecutor`.
- **ActionWindup** — Окно подготовки атаки (2 тика). `held_intent_id` → release в Фазе 7 (ADR-O-310). Stale Intent Validation: actor/target живы?

### Архитектурные принципы

- **Embodiment** — Воплощение. Игрок подчиняется тем же физическим законам, что и NPC.
- **DOUBLE TRUTH** — Архитектурный баг, когда данные хранятся в двух местах и рассинхронизируются.
- **SSOT (Single Source of Truth)** — Единый источник истины (например, `body_state["current_hp"]` для HP, ADR-HP-UNIFICATION).
- **Dual Rail Execution** — Legacy + Shadow parallel execution. `EventCompiler` (shadow) и `SceneStateManager` (legacy) работают параллельно; `EquivalenceValidator` сравнивает (ADR-O-201).

### Тестирование и наблюдение

- **IPT (Invariant Probe Tests)** — Быстрые тесты ядра (`backend/tests/IPT.py`). 5 секунд, без LLM. Запускать перед каждым фиксом и после.
- **CDS (Causal Diagnostic System)** — Пассивный аудитор симуляции. `CausalObserver` пишет `reports/LAST_SESSION.md` с DNA-метриками (SHI, NPI, OBI, SCF, CVS, PFI) и красными инвариантами.
- **DriftLaboratory** — Прогон тиков без pygame/LLM/клиента. `cd backend && python -m tests.sandbox.SUPERBOX.run drift quick_debug` (3 тика) или `mass_traversal` (200 тиков).
- **OntologyViolationError** — Критическая ошибка, убивающая тик, если состояние мира стало невалидным (`NaN`, `sum(drives)!=1.0`, bounds violation). ADR-O-207.
- **SimulationIntegrityError** — Runtime-исключение при нарушении инварианта. Перехват через `try/except` в пайплайне запрещён — игра должна упасть громко (ADR-INV-DEF).

---

## 5. Быстрый старт (Что запустить)

| Что | Команда | Время |
|-----|---------|-------|
| Проверить baseline | `python backend/tests/IPT.py` | ~5 сек |
| Прогнать 3 тика без UI | `cd backend && python -m tests.sandbox.SUPERBOX.run drift quick_debug` | ~10 сек |
| Прогнать 200 тиков (rate) | `cd backend && python -m tests.sandbox.SUPERBOX.run drift mass_traversal` | ~60 сек |
| Запустить игру | `python game_launcher.py` | — |
| Все unit-тесты | `cd backend && python -m pytest tests/ -v` | ~30 сек |
| Проверить wall-clock | `python scripts/lint_wall_clock.py` | ~2 сек |
| Граф импортов | `python scripts/APS.py` | ~10 сек |

---

## 6. Если ничего не помогает

1. Открой `reports/LAST_SESSION.md` — секция «🔴 КРАСНЫЕ ИНВАРИАНТЫ».
2. Открой `docs/Правила Фикса БАГОВ.md` — протокол разбора.
3. Открой `docs/РЕЖИМ РАБОТЫ.md` — режим работы LLM-архитектора.
4. Запусти `python backend/tests/IPT.py` — узнаешь, жив ли baseline.
5. Запусти DriftLaboratory (3 тика) — увидишь GATE-flow.
6. Если красные инварианты есть — ** чини их первыми, до любых новых фич**.
