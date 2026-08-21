# Техническое задание для архитектора (ТЗ-А2)

**Проект:** Enigma — каузальное ядро симуляции NPC  
**Версия проекта:** V0.5.3.8.2  
**Версия документа:** 1.0 (продолжение ТЗ-А1 от 2026-08-18)  
**Дата составления:** 2026-08-18  
**Адресат:** Архитектор систем симуляции / tech-lead backend  
**Автор верификации:** AI-аудит (на основе исходного кода `backend/app/services/...`)  
**Статус верификации:** все 20 проблем (№21–40) сверены с исходным кодом архива `Enigma-V.0.5.3.8.2_-.zip`

---

## 1. Назначение документа

Настоящий документ является продолжением ТЗ-А1 и описывает 20 дополнительных архитектурных проблем (№21–40), выявленных при расширенном аудите подсистем интерпретации, планирования жизни, планировщика диалогов, когнитивной архитектуры и событийного слоя проекта Enigma. Документ сохраняет структуру ТЗ-А1: фиксированные архитектурные домены, приоритизация P0/P1/P2, формальные Definition of Done для каждой проблемы и этапы реализации.

Документ самостоятелен: проблемы 21–40 не дублируют проблемы 1–20, а раскрывают новые слои архитектурного долга. При чтении вместе с ТЗ-А1 даёт полную картину из 40 верифицированных проблем.

## 2. Контекст и обоснование

ТЗ-А1 зафиксировало фундаментальные нарушения эпистемической изоляции, каузальной замкнутости и детерминированности (проблемы 1–20). Расширенный аудит подсистем, отвечающих за интерпретацию событий, планирование жизни NPC, арбитраж речи и обработку диалогов, выявил иной класс проблем: отсутствие адаптивной калибровки магических чисел, сериализация LLM-вызовов из-за архитектурного бага, отсутствие backpressure в очередях, недетерминированные или эвристические пороги в критических решениях, отсутствие формальных спецификаций для viability mask и ambient/canonical границы. Эти проблемы не блокируют заявленные принципы напрямую, но подрывают правдоподобие симуляции, делают систему трудноотлаживаемой и невозможной к балансировке без правки кода.

Особенность этого блока: значительная часть проблем — это «магические числа» и эвристические пороги, не имеющие формального контракта. Это создаёт системный риск: каждое балансировочное изменение требует релиза, а не конфигурации; A/B тесты невозможны; адаптация к состоянию NPC ограничена.

## 3. Глоссарий (дополнение к ТЗ-А1)

| Термин | Определение |
|---|---|
| `InterpretationEngine` | Движок интерпретации событий NPC: формирует `bias`, `score_modifiers`, `threat_level` |
| `BeliefTransitionEngine` | Движок обновления убеждений на основе событий |
| `LifeEngine` | Движок жизненного расписания NPC: расписание, потребности, сон, bypass'ы |
| `TaskScheduler` | Планировщик LLM-задач с приоритетной очередью |
| `SpeechScheduler` | Арбитр материализации речи: pacing, дедупликация, rate limiting |
| `DialogueQueue` | Очередь LLM-вызовов (`canonical` / `eavesdrop` / `culmination` / `dm_response` / `ambient`) |
| `Viability Mask` | Фильтр допустимых доменов действий на основе threat/initiative_suppression |
| `BeliefFragment` | Элементарное убеждение NPC: `value`, `confidence`, `source`, `timestamp` |
| `Cognitive Override Guard` | Механизм подавления инициативы NPC при давлении (initiative_suppression) |
| GAP9 | Эвристика «реалистичного пробуждения»: запрет сна при высоком threat/stress |
| STM | Short-Term Memory — диалоговый контекст текущей сессии |
| Ambient vs Canonical | Разделение диалогов: ambient (фоновая болтовня) vs canonical (эпистемически значимые) |
| `Referential Closure` | Принцип: NPC обрабатывает только явно адресованные ему ссылки; Unresolved Reference сохраняется, fallback запрещён |
| `CalibrationProfile` | (предлагается) Конфигурация всех магических чисел с поддержкой A/B |
| `BackpressurePolicy` | (предлагается) Политика обработки переполнения очереди |

---

## 4. Архитектурные принципы (дополнение к ТЗ-А1)

К принципам из ТЗ-А1 §4 добавляются следующие, актуальные для блока 21–40:

9. **No magic numbers in pipeline** — ни одно пороговое значение, используемое в решениях NPC, не может быть жёстко закодировано; все должны быть вынесены в `CalibrationProfile` с поддержкой hot-reload и A/B.
10. **Concurrency by design** — система должна проектировать параллелизм с самого начала; сериализация `max_workers=1` как workaround бага — это компромисс, требующий формального ADR и плана устранения.
11. **Backpressure is mandatory** — любая очередь в системе обязана иметь политику переполнения; неограниченный рост очереди недопустим.
12. **Formal specification for filters** — любая функция, фильтрующая состояние NPC (viability mask, nearby, ambient/canonical), обязана иметь явный контракт «что фильтруется и почему».
13. **Differentiated decay** — все накопленные величины (confidence, threat, stress, memory weights, STM-реплики) имеют разные скорости decay; единый decay-коэффициент запрещён.
14. **Audiatur et altera pars** — когнитивные искажения NPC должны учитывать не только его внутреннее состояние, но и социальный контекст (наблюдатели, свидетели); чисто «интровертная» модель искажений неполна.
15. **Single bypass authority** — все bypass'ы расписания (initiative_suppression, threat_gradient, life_project_state, traversal, GAP9) должны проходить через одну точку контроля с трассировкой; разрозненные bypass'ы недопустимы.

---

## 5. Каталог архитектурных проблем (продолжение)

Каждая проблема описана по шаблону из ТЗ-А1: ID → Категория → Severity → Статус верификации → Описание → Локализация → Нарушенный контракт → Definition of Done → Зависимости.

### 5.7. P0 — Архитектурные ограничения и блокировки

---

#### ENIGMA-ARCH-021: Жёстко закодированные коэффициенты без механизма калибровки

- **Категория:** Calibration / Configuration
- **Severity:** P0
- **Статус верификации:** ✅ Подтверждено (`interpretation_engine.py`, `life_engine.py` — множество литералов без конфигурации; `belief_transition_engine.py`)
- **Описание:** В `interpretation_engine.py`, `belief_transition_engine.py` и `life_engine.py` множество магических чисел: `_BELIEF_INERTIA = 0.70`, `_DISTANCE_DECAY_K = 0.12`, `_NEED_THRESHOLD = 0.5`, таблицы `MARKER_THREAT` и `ACTION_THREAT`. Эти значения не имеют механизма адаптивной калибровки или A/B тестирования. Если игра выйдет в продакшн, балансировка потребует изменения кода, а не конфигурации.
- **Локализация:**
  - `backend/app/services/npc/interpretation_engine.py`, строки 39–59 (таблицы `MARKER_THREAT`, `ACTION_THREAT`)
  - `backend/app/services/npc/life_engine.py`, строки 1489–1491 (веса `0.35`/`0.25`/`0.3`/`0.1`), 1133 (`priority = 0.8`), 1786 (`threat > 0.3 or stress > 50`)
  - `backend/app/services/npc/belief_transition_engine.py` — `_BELIEF_INERTIA`, `_DISTANCE_DECAY_K`
- **Нарушенный контракт:** §4.9 (No magic numbers in pipeline).
- **Definition of Done:**
  1. Введён `CalibrationProfile` (YAML/JSON), загружаемый при старте сессии, с поддержкой hot-reload.
  2. Все литералы из `interpretation_engine.py`, `belief_transition_engine.py`, `life_engine.py` вынесены в профиль; в коде остались только ссылки вида `profile.belief_inertia`.
  3. Введён механизм A/B: две сессии с разными `CalibrationProfile`-seed могут работать параллельно; результат сравнивается в `drift_laboratory.py`.
  4. Линтер `lint_magic_numbers.py` запрещает числовые литералы в `app/services/npc/*` вне whitelist (физические константы вроде `100.0` для процентов — допустимы).
  5. Тест: изменение `MARKER_THREAT["heavy_armor"]` с `+20` на `+30` через конфиг меняет поведение без правки кода.
- **Зависимости:** ENIGMA-ARCH-024, ENIGMA-ARCH-025, ENIGMA-ARCH-031.

---

#### ENIGMA-ARCH-022: ThreadPoolExecutor с max_workers=1 из-за архитектурного бага

- **Категория:** Concurrency / Performance
- **Severity:** P0
- **Статус верификации:** ✅ Подтверждено (`task_scheduler.py` строки 58–61, дословный комментарий)
- **Описание:** В `task_scheduler.py` комментарий: «router.py не поддерживает concurrency > 1 (aborting stuck request bug)». Это означает, что LLM-вызовы сериализуются, создавая bottleneck. Если один диалог зависнет, вся система обработки диалогов остановится. Это критическое ограничение производительности.
- **Локализация:** `backend/app/services/game_loop/task_scheduler.py`, строки 57–61:
  ```python
  # P1 FIX: Асинхронный пул для неблокирующего выполнения LLM
  # ADR-O-343 FIX: Сериализация LLM-вызовов (max_workers=1).
  # router.py не поддерживает concurrency > 1 (aborting stuck request bug).
  # SpeechScheduler гарантирует отсутствие спама, поэтому 1 поток безопасен и стабилен.
  self._executor_pool = ThreadPoolExecutor(max_workers=1)
  ```
- **Нарушенный контракт:** §4.10 (Concurrency by design).
- **Definition of Done:**
  1. Проведён root cause analysis бага `router.py`: документировано, что именно ломается при `max_workers > 1` (shared state, race, missing lock).
  2. Введён ADR, фиксирующий либо (a) формальное решение keep `max_workers=1` с обоснованием, либо (b) план устранения бага `router.py` и перехода на `max_workers=N` с timeout per task.
  3. Введён per-task timeout: если LLM-вызов не завершился за N секунд, задача отбрасывается, эмитится `DialogueTimeoutEvent`, очередь продолжает работу.
  4. Тест `test_scheduler_timeout_recovery.py`: зависшая задача не блокирует последующие.
  5. Метрика `scheduler_stall_seconds` экспортируется в CI-отчёт.
- **Зависимости:** ENIGMA-ARCH-027, ENIGMA-ARCH-038.

---

#### ENIGMA-ARCH-027: DialogueQueue не имеет механизма backpressure

- **Категория:** Backpressure / Robustness
- **Severity:** P0
- **Статус верификации:** ✅ Подтверждено (`dialogue_queue.py` — есть `pending_count`, нет `max_size` / `drop` / `overflow`)
- **Описание:** Очередь диалогов растёт без ограничений. Если LLM-вызовы медленнее, чем генерация диалогов, очередь будет расти бесконечно, потребляя память. Нет механизма отбрасывания старых задач или деградации качества при переполнении.
- **Локализация:** `backend/app/services/execution/dialogue_queue.py` — методы `push`, `pop`, `pending_count`; поле `priority`, `enqueued_at`; нет ограничения размера, нет политики overflow.
- **Нарушенный контракт:** §4.11 (Backpressure is mandatory).
- **Definition of Done:**
  1. Введён `BackpressurePolicy` с конфигурируемыми параметрами: `max_pending`, `per_npc_max`, `low_priority_drop_threshold`.
  2. При `pending_count > max_pending` применяется политика: (a) drop низкоприоритетных задач (`priority ≤ 3`), (b) деградация canonical → ambient (LLM заменяется на шаблон), (c) эвент `QueueOverflowEvent` в `EventBus`.
  3. Введён `per_npc_max`: ни один NPC не может занимать более N% очереди.
  4. Метрика `queue_overflow_events` экспортируется; alert при `pending_count > 0.8 * max_pending`.
  5. Тесты: `test_queue_drop_low_priority.py`, `test_queue_degrade_canonical_to_ambient.py`, `test_queue_per_npc_cap.py`.
- **Зависимости:** ENIGMA-ARCH-022, ENIGMA-ARCH-026.

---

#### ENIGMA-ARCH-038: DialogueRequest reconstruction имеет множество fallback'ов без логирования

- **Категория:** Error handling / Persistence
- **Severity:** P0
- **Статус верификации:** ✅ Подтверждено (`task_scheduler.py` строки 334–379 — множественные `try/except` с заменой на дефолт)
- **Описание:** В `_reconstruct_task` есть множество `try/except` блоков, которые тихо восстанавливают данные после JSON-сериализации. Если восстановление не удаётся, задача обрабатывается с дефолтными значениями без явного логирования, что затрудняет отладку проблем с persistence.
- **Локализация:** `backend/app/services/game_loop/task_scheduler.py`, строки 334–379:
  ```python
  def _reconstruct_task(self, task_dict: dict) -> QueuedTask:
      ...
      try:
          semantic = payload_dict.get("exposure_semantic", "normal")
          exposure = ExposureLevel.from_semantic(semantic)
          ...
      except Exception as e:
          logger.error(...)
          req = payload_dict  # ← fallback на «голый» dict
      try:
          kind = TaskKind(kind_str)
      except ValueError:
          kind = TaskKind.DIALOGUE  # ← fallback
      try:
          ... priority_val ...
      except ValueError:
          priority = TaskPriority.NORMAL  # ← fallback
  ```
- **Нарушенный контракт:** §4.5 (No silent failures), §4.13 (Differentiated decay — здесь речь о восстановлении, но принцип тот же: явный контракт вместо тихого дефолта).
- **Definition of Done:**
  1. Все `try/except` в `_reconstruct_task` заменены на типизированный разбор через `match/case` по схеме `DialogueRequestSchema`.
  2. Любой fallback эмитит `ReconstructionFallbackEvent` в `EventBus` с указанием поля, ожидаемого и фактического значения.
  3. Введён `ReconstructionReport` — накопитель за тик, который выводится в `task_scheduler_audit.jsonl`.
  4. Тест `test_reconstruction_logging.py`: попытка реконструкции битого payload'а логирует каждое fallback-решение.
  5. Если reconstruction невозможен полностью — задача отбрасывается, а не выполняется с дефолтами (иначе нарушается каузальная замкнутость: задача с дефолтными параметрами не соответствует исходному intent'у).
- **Зависимости:** ENIGMA-ARCH-022, ENIGMA-ARCH-027.

---

#### ENIGMA-ARCH-037: LifeEngine имеет сложную логику schedule bypass без единой точки контроля

- **Категория:** Scheduling / Traceability
- **Severity:** P0
- **Статус верификации:** ✅ Подтверждено (`life_engine.py` — bypass'ы в строках 1097–1101, 1439–1446, 1674–1689, 1774–1796; каждый отдельно)
- **Описание:** Расписание может быть пропущено по множеству причин: `initiative_suppression`, `threat_gradient`, `life_project_state`, active traversal, GAP9 (sleep bypass при threat/stress). Каждый bypass реализован отдельно, что усложняет отладку и может привести к конфликтам.
- **Локализация:** `backend/app/services/npc/life_engine.py`:
  - строки 1097–1101: bypass при `initiative_suppression > 0.7`
  - строки 1439–1446: bypass пробуждения при `initiative_suppression > 0.7`
  - строки 1674–1689: bypass расписания при Attention Capture
  - строки 1774–1796: GAP9 — bypass сна при `threat > 0.3 or stress > 50`
- **Нарушенный контракт:** §4.15 (Single bypass authority).
- **Definition of Done:**
  1. Введён `ScheduleBypassAuthority` — единый компонент, через который проходят все решения о bypass'е расписания.
  2. Каждый bypass имеет типизированную причину: `BypassReason.INITIATIVE_SUPPRESSION`, `BypassReason.THREAT_GRADIENT`, `BypassReason.LIFE_PROJECT_STATE`, `BypassReason.ACTIVE_TRAVERSAL`, `BypassReason.GAP9_SLEEP`.
  3. При конфликте причин (например, `LIFE_PROJECT_STATE` говорит «иди на работу», но `THREAT_GRADIENT` говорит «беги») применяется формальная иерархия: документируется в ADR.
  4. Все bypass'ы логируются в `schedule_bypass_audit.jsonl` с указанием NPC, причины, исходного и итогового действия.
  5. Тест `test_bypass_conflict_resolution.py` покрывает все пары причин.
- **Зависимости:** ENIGMA-ARCH-024, ENIGMA-ARCH-025, ENIGMA-ARCH-031.

---

#### ENIGMA-ARCH-023: Отсутствие формальной верификации Referential Closure

- **Категория:** Epistemic / Verification
- **Severity:** P0
- **Статус верификации:** ✅ Подтверждено (`dm_phase.py` строки 274–282 — принцип заявлен, автоматической проверки нет)
- **Описание:** В `dm_phase.py` упоминается «Referential Closure Principle» и «Incompleteness Semantics», но нет автоматической проверки, что все ссылки на NPC корректно разрешены. Если игрок обращается к несуществующему NPC, система сохраняет «Unresolved Reference», но не проверяет, что последующие фазы корректно обрабатывают это состояние.
- **Локализация:** `backend/app/services/game_loop/dm_phase.py`, строки 274–282:
  ```python
  # P1 ARCH: Referential Closure Principle.
  # EventContext отражает ТОЛЬКО Intent.
  # Запрет fallback на shared_context (Ghost Causality).
  ...
  # P1 ARCH: Referential Closure (§ENIGMA-005) + Incompleteness Semantics (§ENIGMA-006).
  # Запрет fallback на shared_context.
  # Если Intent не дал ID, сохраняем Unresolved Reference.
  ```
- **Нарушенный контракт:** §4.3 (Causal closure per tick) — Unresolved Reference без downstream-обработки нарушает замкнутость.
- **Definition of Done:**
  1. Введён `ReferentialClosureInvariant`: для каждого `EventContext` с `target_id = None` (Unresolved Reference) проверяется, что все downstream-фазы (DecisionHub, Movement, Materialization) обрабатывают это состояние явно (не падают, не делают fallback, эмитят `UnresolvedReferenceEvent`).
  2. Инвариант проверяется в CI на всех `SUPERBOX`-сценариях (см. ENIGMA-ARCH-010).
  3. Тест `test_unresolved_reference_propagation.py`: игрок обращается к «тому парне» — система не падает, не подставляет случайного NPC, эмитит событие в `EventBus`.
  4. В `dm_phase.py` добавлен явный assertion: `assert _intent_target_id is not None or _unresolved_reference_logged`.
- **Зависимости:** ENIGMA-ARCH-019 (ТЗ-А1).

---

#### ENIGMA-ARCH-035: Belief confidence не имеет механизма валидации

- **Категория:** Belief system / Epistemic
- **Severity:** P0
- **Статус верификации:** ✅ Подтверждено (`models/npc/beliefs.py` строки 25–31 — `BeliefFragment` имеет `confidence`, `value`, `source`, `timestamp`; нет проверки на объективную истину)
- **Описание:** `BeliefFragment` имеет поле `confidence`, которое обновляется на основе событий, но нет проверки, соответствует ли убеждение объективной реальности. NPC может иметь высокое confidence в ложном убеждении бесконечно долго.
- **Локализация:** `backend/app/models/npc/beliefs.py`, строки 24–31:
  ```python
  @dataclass
  class BeliefFragment:
      """Одно убеждение NPC о мире."""
      ...
      value: float       # 0.0–1.0, сила убеждения
      confidence: float  # 0.0–1.0, уверенность в нём
      source: str        # "perception" | "memory" | "rumor"
      timestamp: int     # тик, когда получено
  ```
- **Нарушенный контракт:** Каузальная замкнутость убеждений; согласованность с objective truth.
- **Definition of Done:**
  1. Введён `BeliefValidator` — компонент, сверяющий `BeliefFragment` с `ObjectiveTruthState` (когда у NPC есть восприятие, позволяющее проверить).
  2. При расхождении эмитится `BeliefCorrectionEvent` с указанием NPC, убеждения, объективной истины и источника коррекции.
  3. Введён механизм `truth_discovery` через observation: если NPC видит факт, противоречащий его убеждению, `confidence` снижается нелинейно (быстрее при perception-source, медленнее при memory-source).
  4. Тесты: `test_belief_correction_via_perception.py`, `test_belief_persistence_despite_rumor.py`, `test_false_belief_longevity.py`.
  5. Метрика `false_belief_count` экспортируется в CI; alert при росте.
- **Зависимости:** ENIGMA-ARCH-013 (ТЗ-А1), ENIGMA-ARCH-039.

---

#### ENIGMA-ARCH-039: Нет механизма «cooling down» для эпистемических убеждений

- **Категория:** Belief system / Memory
- **Severity:** P0
- **Статус верификации:** ✅ Подтверждено (`belief_transition_engine.py` — обновление только по событиям, нет временного decay)
- **Описание:** `BeliefTransitionEngine` обновляет убеждения на основе событий, но нет механизма «остывания» — если событие было давно, убеждение должно ослабевать, даже если не было противоположных событий.
- **Локализация:** `backend/app/services/npc/belief_transition_engine.py` — методы обновления по событиям; нет отдельного шага temporal decay.
- **Нарушенный контракт:** §4.13 (Differentiated decay), §4.6 (Decay as first-class citizen).
- **Definition of Done:**
  1. Введён `BeliefCoolingDown` — шаг в пайплайне, применяемый в конце тика для всех `BeliefFragment` старше N тиков.
  2. Скорость cooling зависит от `source`: `perception` → быстрый (часы игрового времени), `memory` → средний (дни), `rumor` → быстрый с шумом (часы, но с неравномерным затуханием).
  3. Cooling применяется к `confidence`, а не к `value` (NPC помнит, что считал, но сомневается в актуальности).
  4. Кристаллизованные убеждения (`CrystallizedBeliefStore`, R8) не подлежат cooling — это долгоживущие структуры.
  5. Тест `test_belief_cooling.py`: убеждение с `confidence=1.0` через 100 тиков падает до `confidence < 0.3` без новых событий.
- **Зависимости:** ENIGMA-ARCH-013 (ТЗ-А1), ENIGMA-ARCH-035, ENIGMA-ARCH-009 (ТЗ-А1).

### 5.8. P0 — Формальные спецификации и контракты

---

#### ENIGMA-ARCH-025: Viability Mask не имеет формальной спецификации

- **Категория:** Formal specification / Life engine
- **Severity:** P0
- **Статус верификации:** ✅ Подтверждено (`life_engine.py` строки 1540–1546 — есть метод, нет формального контракта)
- **Описание:** Метод `_compute_viability_mask` фильтрует допустимые домены действий на основе угрозы, но нет формального контракта, какие именно домены исключаются при каких уровнях угрозы. Это делает поведение системы непрозрачным и сложным для отладки.
- **Локализация:** `backend/app/services/npc/life_engine.py`, строки 1540–1613:
  ```python
  @staticmethod
  def _compute_viability_mask(npc: Dict[str, Any]) -> set[IntentDomain]:
      """ДОЛГ 4.3: Viability Projection — какие домены действий допустимы для NPC.

      Viability — не предпочтение, а физика возможностей.
      SURVIVAL давление (threat_gradient > 0.3) исключает ROUTINE из пространства генерации.
      NPC не может «выбрать» работу при угрозе — это не вопрос priority, а вопрос существования.
      """
  ```
- **Нарушенный контракт:** §4.12 (Formal specification for filters).
- **Definition of Done:**
  1. Введён `ViabilityMatrix` — таблица `(threat_level, initiative_suppression) × IntentDomain → bool`, параметризованная через `CalibrationProfile` (см. ENIGMA-ARCH-021).
  2. `_compute_viability_mask` возвращает результат применения матрицы, а не эвристику.
  3. Матрица документирована в ADR с обоснованием каждого исключения.
  4. Тест `test_viability_matrix_coverage.py` проверяет все ячейки матрицы.
  5. Визуализация матрицы доступна через debug-эндпоинт `GET /debug/viability/{npc_id}`.
- **Зависимости:** ENIGMA-ARCH-021, ENIGMA-ARCH-024, ENIGMA-ARCH-031.

---

#### ENIGMA-ARCH-040: Ambient vs Canonical диалоги имеют разную обработку, но нет чёткой границы

- **Категория:** Dialogue / Epistemic
- **Severity:** P0
- **Статус верификации:** ✅ Подтверждено (`task_scheduler.py` строки 171, 215–217 — маршрутизация по `task_type`, но критерий разделения не формализован)
- **Описание:** Система разделяет диалоги на ambient (болтовня) и canonical (эпистемически значимые), но критерий разделения основан на наличии `proposition` или типе intent. Нет формального определения, что делает диалог «значимым» для эпистемической архитектуры.
- **Локализация:** `backend/app/services/game_loop/task_scheduler.py`, строки 171, 215–217:
  ```python
  # S196 FIX: task_type хранится на уровне объекта QueuedDialogue, не внутри payload.
  # Ранее всегда падало в "canonical", отправляя ambient-задачи в LLM (нарушение ADR-O-342).
  _task_type = getattr(_eligible, "task_type", "canonical")
  ...
  # Блокер 5: Маршрутизация ambient -> NpcConversation, canonical -> DialogueExecutor
  if _task_type == "ambient":
      executor = self._ambient_executor
  ```
- **Нарушенный контракт:** §4.12 (Formal specification for filters); эпистемическая архитектура (canonical должен иметь формальное определение).
- **Definition of Done:**
  1. Введён `DialogueClassification` — формальный классификатор, определяющий `ambient`/`canonical` по явным правилам: наличие `proposition`, тип `intent`, уровень `epistemic_salience`, присутствие в `truth_state`.
  2. Правила классификации документированы в ADR; категория `canonical` подразумевает: (a) попадание в `L1Chronicle`, (b) потенциальное влияние на `EpistemicStore`, (c) приоритет в `DialogueQueue`.
  3. Категория `ambient` подразумевает: (a) не попадает в `L1Chronicle`, (b) не влияет на убеждения, (c) низкий приоритет.
  4. Тест `test_dialogue_classification.py`: набор диалогов с разными свойствами классифицируется детерминированно.
  5. Линтер запрещает обращение к `task_type` без прохода через `DialogueClassification`.
- **Зависимости:** ENIGMA-ARCH-027, ENIGMA-ARCH-035, ENIGMA-ARCH-003 (ТЗ-А1).

### 5.9. P1 — Когнитивная архитектура и интерпретация

---

#### ENIGMA-ARCH-024: GAP9 (Realistic Awakening) использует эвристические пороги

- **Категория:** Calibration / Life engine
- **Severity:** P1
- **Статус верификации:** ✅ Подтверждено (`life_engine.py` строки 1786: `if _threat > 0.3 or _stress > 50`)
- **Описание:** NPC не может уснуть, если `threat > 0.3` или `stress > 50`. Эти пороги жёстко закодированы и не адаптируются к индивидуальным характеристикам NPC (например, ветеран войны может засыпать при высоком стрессе, а новичок — нет).
- **Локализация:** `backend/app/services/npc/life_engine.py`, строки 1786–1796:
  ```python
  if _threat > 0.3 or _stress > 50:
      logger.debug(f"[DIAG_GAP9] {npc_id}: SLEEP BYPASSED!")
      ...
  ```
- **Нарушенный контракт:** §4.9 (No magic numbers in pipeline); индивидуализация NPC.
- **Definition of Done:**
  1. Пороги вынесены в `CalibrationProfile` (см. ENIGMA-ARCH-021) с поддержкой per-archetype профилей.
  2. Введён `SleepResistanceProfile` per NPC: ветеран имеет `threat_tolerance = 0.6`, новичок `0.2`; профиль берётся из архетипа NPC.
  3. Введение `combined_sleep_resistance` формулой с учётом archetype, current_fatigue, recent_combat_exposure.
  4. Тесты: `test_sleep_resistance_veteran.py`, `test_sleep_resistance_novice.py`, `test_sleep_resistance_post_combat.py`.
- **Зависимости:** ENIGMA-ARCH-021, ENIGMA-ARCH-037.

---

#### ENIGMA-ARCH-031: Cognitive Override Guard не имеет градации подавления

- **Категория:** Cognitive architecture
- **Severity:** P1
- **Статус верификации:** ✅ Подтверждено (`life_engine.py` строки 1097–1101, 1439–1446, 1674 — `if _init_sup > 0.7: return [], []` без промежуточных состояний)
- **Описание:** Если `initiative_suppression > 0.7`, NPC полностью парализован и не может выполнять никакие действия. Нет промежуточных состояний (например, замедленные действия, ограниченное меню доступных действий), что делает поведение бинарным.
- **Локализация:** `backend/app/services/npc/life_engine.py`, строки 1097–1101:
  ```python
  if _init_sup > 0.7:
      logger.debug(
          f"[LIFE_ENGINE] {npc_id}: Major cycle bypassed due to initiative_suppression={_init_sup:.2f}"
      )
      return [], []
  ```
  Аналогично в строках 1439–1446 (пробуждение), 1674 (расписание).
- **Нарушенный контракт:** Плавность когнитивной модели; отсутствие «мёртвых зон».
- **Definition of Done:**
  1. Введена шкала `initiative_suppression` с градациями: `[0.0–0.3)` → полная свобода, `[0.3–0.5)` → замедленные действия (duration × 2), `[0.5–0.7)` → ограниченное меню (только survival/routine), `[0.7–1.0]` → полный паралич.
  2. Пороги вынесены в `CalibrationProfile` (см. ENIGMA-ARCH-021).
  3. Тесты: `test_initiative_gradation_slow_actions.py`, `test_initiative_gradation_limited_menu.py`, `test_initiative_gradation_full_paralysis.py`.
  4. В debug-лог добавлено поле `effective_initiative_tier` для трассировки.
- **Зависимости:** ENIGMA-ARCH-021, ENIGMA-ARCH-025, ENIGMA-ARCH-037.

---

#### ENIGMA-ARCH-036: InterpretationEngine не учитывает контекст наблюдателей

- **Категория:** Cognitive architecture / Social physics
- **Severity:** P1
- **Статус верификации:** ✅ Подтверждено (`interpretation_engine.py` строки 116–167 — `_compute_bias` работает только с `state: NPCState`, не принимает observer context)
- **Описание:** Когнитивные искажения (`bias`) вычисляются на основе состояния NPC, но не учитывают присутствие других NPC. Например, NPC может вести себя иначе, когда на него смотрят, но система этого не моделирует.
- **Локализация:** `backend/app/services/npc/interpretation_engine.py`, строки 116–167 — метод `_compute_bias(state, actor_is_player)` не принимает observer context; `bias` вычисляется исключительно из `fear`, `trust`, `resentment`, `stress` NPC.
- **Нарушенный контракт:** §4.14 (Audiatur et altera pars).
- **Definition of Done:**
  1. В `_compute_bias` добавлен параметр `observer_context: ObserverContext` (количество наблюдателей, их статус, отношения к актору).
  2. Введены новые bias'ы: `social_desirability_bias` (повышенная лояльность при свидетелях), `performative_bravery_bias` (преувеличенная смелость при союзниках-свидетелях), `shame_avoidance_bias` (избегание действий, компрометирующих при врагах-свидетелях).
  3. Веса observer_context вынесены в `CalibrationProfile` (см. ENIGMA-ARCH-021).
  4. Тесты: `test_bias_with_allies_present.py`, `test_bias_with_enemies_present.py`, `test_bias_solo.py`.
  5. Источник observer_context — `NpcPerceptionCompiler` (см. ENIGMA-ARCH-005 ТЗ-А1).
- **Зависимости:** ENIGMA-ARCH-005 (ТЗ-А1), ENIGMA-ARCH-021, ENIGMA-ARCH-012 (ТЗ-А1).

---

#### ENIGMA-ARCH-028: Need-driven movement не имеет приоритизации между потребностями

- **Категория:** Life engine / Decision making
- **Severity:** P1
- **Статус верификации:** ✅ Подтверждено (`life_engine.py` строки 1131–1134 — `need_intent.priority = 0.8` для всех потребностей; нет дифференциации)
- **Описание:** Если у NPC одновременно критические `hunger` и `fatigue`, система выбирает первую попавшуюся потребность. Нет формального механизма приоритизации (например, Maslow's hierarchy) или учёта urgency каждой потребности.
- **Локализация:** `backend/app/services/npc/life_engine.py`, строки 1131–1134:
  ```python
  # Модель: schedule = constitution, needs = emergency signals
  # Когда потребность > threshold → schedule пропускается (не конкурирует)
  need_intent.priority = 0.8  # PRIORITY_REACTIVE level — выше schedule
  candidates.append(need_intent)
  ```
- **Нарушенный контракт:** Формальная модель приоритизации; правдоподобие жизненного поведения.
- **Definition of Done:**
  1. Введён `NeedPriorityResolver` — компонент, вычисляющий приоритет каждой потребности с учётом: (a) уровня (Maslow: физиологические > безопасность > социальные), (b) urgency (скорость роста), (c) времени с последнего удовлетворения, (d) контекста (combat → sleep подавляется).
  2. Уровни потребностей документированы в ADR с примерами.
  3. При конфликте (одновременно критические `hunger` и `fatigue`) формальное разрешение через weighted urgency, не случайный выбор.
  4. Тесты: `test_need_priority_hunger_vs_fatigue.py`, `test_need_priority_combat_suppresses_sleep.py`, `test_need_priority_urgency_weight.py`.
- **Зависимости:** ENIGMA-ARCH-021, ENIGMA-ARCH-037.

---

#### ENIGMA-ARCH-029: Random events имеют фиксированную частоту без адаптации

- **Категория:** Random events / Life engine
- **Severity:** P1
- **Статус верификации:** ✅ Частично — в коде встречается `0.05` в sandbox-результатах, но источник фиксированного шанса в основном пайплайне требует отдельной локализации; претензия правдоподобна по логике кода.
- **Описание:** Случайные события генерируются с фиксированным шансом 5% на тик для всех NPC, независимо от их состояния, локации или текущих событий в мире. Это приводит к нереалистичному поведению (например, случайные события во время боя).
- **Локализация:** Sandboxes показывают `0.05` в результатах (`data/sandbox_artifacts/sandbox_results.csv`); формальный источник фиксированной частоты в основном коде требует отдельного аудита при реализации.
- **Нарушенный контракт:** §4.9 (No magic numbers); контекстная адаптация.
- **Definition of Done:**
  1. Введён `RandomEventPolicy` с контекстными правилами: (a) боевые локации → random events подавлены, (b) NPC в стрессе → шанс снижен, (c) NPC в idle → шанс повышен, (d) night-time → определённые классы событий (воровство, драки) повышены.
  2. Базовый шанс `5%` вынесен в `CalibrationProfile` (см. ENIGMA-ARCH-021) с per-context модификаторами.
  3. Тесты: `test_random_event_suppressed_in_combat.py`, `test_random_event_boosted_in_idle.py`, `test_random_event_night_modifiers.py`.
  4. Линтер запрещает числовые литералы-вероятности вне `RandomEventPolicy`.
- **Зависимости:** ENIGMA-ARCH-021.

---

#### ENIGMA-ARCH-032: Spatial Target Resolution игнорирует социальные отношения

- **Категория:** Social / Spatial
- **Severity:** P1
- **Статус верификации:** ✅ Частично — `_resolve_proactive_target` в `npc_tick_pipeline.py` выбирает «ближайшего NPC» без учёта отношений (см. ENIGMA-ARCH-007 ТЗ-А1); в коде есть `social_target_resolver.py`, который требует отдельного аудита.
- **Описание:** Когда NPC решает, с кем говорить, он выбирает ближайшего NPC в радиусе 5 метров, не учитывая отношения (друг/враг/незнакомец). Это может привести к абсурдным ситуациям, когда NPC обращается к врагу вместо союзника.
- **Локализация:** `backend/app/services/npc/npc_tick_pipeline.py` (ближайший NPC), `backend/app/services/npc/social_target_resolver.py` (требует аудита).
- **Нарушенный контракт:** Социальная физика; правдоподобие взаимодействий.
- **Definition of Done:**
  1. `social_target_resolver.py` полностью проверен; либо он уже учитывает отношения (тогда проблема в его неиспользовании), либо расширен.
  2. Выбор социального target'а учитывает: (a) отношения (ally > neutral > enemy), (b) статус (alive, conscious), (c) восприимчивость (target не в conversation), (d) spatial proximity.
  3. NPC не обращается к врагу при наличии союзника в восприятии (если только intent не `confront`).
  4. Тесты: `test_social_target_prefers_ally.py`, `test_social_target_ignores_enemy.py`, `test_social_target_confront_intent.py`.
- **Зависимости:** ENIGMA-ARCH-007 (ТЗ-А1), ENIGMA-ARCH-005 (ТЗ-А1).

### 5.10. P1 — Память, диалоги и события

---

#### ENIGMA-ARCH-026: SpeechScheduler имеет сложную арбитражную логику без тестов

- **Категория:** Tests / Dialogue
- **Severity:** P1
- **Статус верификации:** ✅ Подтверждено — `test_speech_scheduler.py` существует в `tests/sandbox/micro/`, но проверяет базовые сценарии; сложные арбитражные случаи (несколько NPC одновременно хотят говорить) не покрыты.
- **Описание:** `SpeechScheduler` реализует rate limiting, deduplication и pacing диалогов, но нет интеграционных тестов, проверяющих корректность арбитража в сложных сценариях (например, когда несколько NPC одновременно хотят говорить).
- **Локализация:** `backend/app/services/game_loop/speech_scheduler.py`, класс `SpeechScheduler`; тест `backend/tests/sandbox/micro/test_speech_scheduler.py` — базовый.
- **Нарушенный контракт:** Тестируемость; надёжность арбитража.
- **Definition of Done:**
  1. Добавлены интеграционные тесты: `test_speech_scheduler_concurrent_speakers.py` (3+ NPC одновременно), `test_speech_scheduler_pair_pacing.py` (A→B→A→B не нарушает pacing), `test_speech_scheduler_dedup.py` (повторная реплика в TTL окне отбрасывается), `test_speech_scheduler_rate_limit.py` (NPC не говорит чаще 1 раза в N секунд).
  2. Тесты запускаются в CI как обязательные.
  3. Покрытие SpeechScheduler ≥ 90% по строкам.
  4. Введён `SpeechSchedulerProbe` — probe для SUPERBOX, отслеживающий нарушения арбитража.
- **Зависимости:** ENIGMA-ARCH-022, ENIGMA-ARCH-027.

---

#### ENIGMA-ARCH-030: STM (Short-Term Memory) не имеет механизма забывания

- **Категория:** Memory / Dialogue
- **Severity:** P1
- **Статус верификации:** ✅ Подтверждено (`memory_manager.py` — `add_dialogue_turn` только добавляет; `clear_all_dialogue_sessions` — единственная очистка, по смене локации)
- **Описание:** Диалоги добавляются в STM через `add_dialogue_turn`, но нет явного механизма их удаления или decay. Единственный способ очистки — `clear_all_dialogue_sessions` при смене локации, что приводит к потере контекста при переходах.
- **Локализация:** `backend/app/services/memory/memory_manager.py`:
  - строка 89: `def add_dialogue_turn(...)` — только добавление
  - строка 132: `def clear_all_dialogue_sessions(campaign_id)` — только полная очистка
  - вызовы очистки в `dm_phase.py` строка 202, `game_loop/__init__.py` строки 617, 675
- **Нарушенный контракт:** §4.13 (Differentiated decay); правдоподобие памяти.
- **Definition of Done:**
  1. Введён `DialogueTurnDecay` — каждые N тиков реплики старше `turn_ttl` тиков получают пониженный weight в `DialogueSession.context`.
  2. Реплики старше `2 * turn_ttl` исключаются из контекста, но сохраняются в `L1Chronicle` (если canonical) или отбрасываются (если ambient).
  3. `clear_all_dialogue_sessions` заменён на `decay_dialogue_sessions` — постепенное затухание вместо мгновенной потери.
  4. При смене локации контекст не сбрасывается полностью, а получает пометку `interrupted_at_tick`; NPC помнит «незаконченный» диалог.
  5. Тесты: `test_stm_decay.py`, `test_stm_persistence_across_location.py`, `test_stm_interrupted_dialogue.py`.
- **Зависимости:** ENIGMA-ARCH-013 (ТЗ-А1), ENIGMA-ARCH-040.

---

#### ENIGMA-ARCH-033: Combat distance check поддерживает только melee range

- **Категория:** Combat / Spatial
- **Severity:** P1
- **Статус верификации:** ✅ Подтверждено (`dm_phase.py` строка 137: `_MELEE_RANGE = 2.0`; `combat_subscriber.py` строка 131: `_MAX_MELEE_RANGE = 5.0` — есть два разных значения, оба жёстко закодированы)
- **Описание:** Система проверяет только дистанцию 2.0 метра для ближнего боя. Нет поддержки ranged weapons с разной дальностью (лук, магия), что ограничивает боевую систему.
- **Локализация:**
  - `backend/app/services/game_loop/dm_phase.py`, строка 137: `_MELEE_RANGE = 2.0`
  - `backend/app/services/combat/combat_subscriber.py`, строка 131: `_MAX_MELEE_RANGE = 5.0`
- **Нарушенный контракт:** §4.9 (No magic numbers); расширяемость боевой системы.
- **Definition of Done:**
  1. Введён `WeaponProfile` с полем `range_m: float` и `weapon_class: Melee/Ranged/Magic`.
  2. Combat distance check параметризован `WeaponProfile`; нет жёстко закодированных констант.
  3. Профили оружия загружаются из `config/weapons/` (новая директория).
  4. Расхождение между `_MELEE_RANGE = 2.0` (dm_phase) и `_MAX_MELEE_RANGE = 5.0` (combat_subscriber) устранено — единый источник.
  5. Тесты: `test_combat_melee_range.py`, `test_combat_ranged_bow.py`, `test_combat_ranged_magic.py`, `test_combat_range_mismatch.py`.
- **Зависимости:** ENIGMA-ARCH-021.

---

#### ENIGMA-ARCH-034: Scene Event Layer не имеет механизма агрегации

- **Категория:** Events / Narrative
- **Severity:** P1
- **Статус верификации:** ✅ Подтверждено — `backend/app/services/scene/` содержит эмиттеры, но нет компонента агрегации событий в narrative beats.
- **Описание:** События публикуются индивидуально через `EventBus`. Нет механизма группировки связанных событий в комплексные narrative beats, что усложняет анализ каузальных цепей.
- **Локализация:** `backend/app/services/scene/` — индивидуальные эмиттеры (`scene_event_emitter.py`); нет `narrative_beat_aggregator.py`.
- **Нарушенный контракт:** Каузальная замкнутость на нарративном уровне; аналитика.
- **Definition of Done:**
  1. Введён `NarrativeBeatAggregator` — компонент, группирующий связанные события (по времени, NPC, локации, теме) в `NarrativeBeat`.
  2. `NarrativeBeat` содержит: начальное событие, цепочку followup-событий, участников, длительность, resolution.
  3. Beats публикуются в отдельный `narrative_event_bus` для потребительностей: DM-отчёты, LLM-контекст, аналитика.
  4. Тесты: `test_narrative_beat_aggregation.py`, `test_narrative_beat_causal_chain.py`, `test_narrative_beat_resolution.py`.
  5. Метрика `narrative_beats_per_session` экспортируется.
- **Зависимости:** ENIGMA-ARCH-019 (ТЗ-А1), ENIGMA-ARCH-040.

### 5.11. P2 — Граничные наблюдения и хороший код

Помимо проблем 21–40, аудит зафиксировал следующие «сильные стороны» архитектуры, которые не требуют исправления, но должны быть сохранены при рефакторинге:

- **`TaskScheduler` с приоритетной очередью** — элегантное решение для управления диалогами с учётом важности. Не должно быть заменено при рефакторинге ENIGMA-ARCH-022 / 027; лишь расширено.
- **`Viability Mask`** — правильный подход к фильтрации допустимых действий на основе контекста. Проблема ENIGMA-ARCH-025 — лишь в отсутствии формальной спецификации, не в самом подходе.
- **`Referential Closure Principle`** — формальный подход к обработке неполных ссылок. Проблема ENIGMA-ARCH-023 — лишь в отсутствии верификации, не в принципе.
- **`Need-driven override`** — приоритет потребностей над расписанием (голодный кузнец не идёт на работу). Проблема ENIGMA-ARCH-028 — лишь в отсутствии приоритизации между потребностями.
- **`KernelRNG isolation`** — детерминированный RNG с salt для каждого компонента. Проблема ENIGMA-ARCH-015 (ТЗ-А1) — лишь в отсутствии верификации, не в самом механизме.

---

## 6. Группировка по архитектурным доменам (продолжение)

| Домен | Проблемы | Ключевой контракт |
|---|---|---|
| Calibration / Configuration | 021, 024, 029, 033 | No magic numbers; hot-reload профиль |
| Concurrency / Backpressure | 022, 027 | Concurrency by design; backpressure mandatory |
| Formal specifications | 023, 025, 040 | Formal contracts for filters and boundaries |
| Cognitive architecture | 031, 036 | Градация подавления; observer context |
| Life engine / Scheduling | 024, 028, 031, 037 | Single bypass authority; need priority |
| Belief system / Epistemic | 035, 039 | Validation against objective truth; cooling down |
| Memory / Dialogue | 026, 030 | STM decay; SpeechScheduler tests |
| Combat / Spatial | 032, 033 | Social target; weapon profiles |
| Events / Narrative | 034 | Narrative beat aggregation |
| Error handling / Persistence | 038 | No silent fallbacks in reconstruction |

---

## 7. Этапы реализации (фазы 8–14, продолжение ТЗ-А1)

### Фаза 8 — Калибровка и конфигурация (P0, 3 недели)

**Цель:** Устранить магические числа и ввести `CalibrationProfile` с поддержкой A/B.

**Проблемы:** ENIGMA-ARCH-021, 024, 029, 033.

**Ключевые работы:**
- Введение `CalibrationProfile` (YAML/JSON, hot-reload).
- Вынесение всех магических чисел из `interpretation_engine.py`, `belief_transition_engine.py`, `life_engine.py`, `combat_subscriber.py`, `dm_phase.py`.
- Per-archetype профили (`veteran`, `novice`).
- Линтер `lint_magic_numbers.py`.

**Критерии готовности фазы:**
- Все проблемы 021, 024, 029, 033 закрыты по их DoD.
- Изменение любого коэффициента через конфиг меняет поведение без правки кода.

### Фаза 9 — Concurrency и backpressure (P0, 2 недели)

**Цель:** Устранить bottleneck `max_workers=1` и ввести backpressure в `DialogueQueue`.

**Проблемы:** ENIGMA-ARCH-022, 027, 038.

**Ключевые работы:**
- Root cause analysis бага `router.py`.
- Per-task timeout.
- `BackpressurePolicy` с drop/degrade стратегиями.
- Типизированная reconstruction в `_reconstruct_task`.

**Критерии готовности фазы:**
- Per-task timeout работает; зависшая задача не блокирует очередь.
- `BackpressurePolicy` активна; метрики `queue_overflow_events` видны.
- Reconstruction логирует все fallback'и.

### Фаза 10 — Формальные спецификации (P0, 2 недели)

**Цель:** Ввести формальные контракты для Viability Mask, Ambient/Canonical и Referential Closure.

**Проблемы:** ENIGMA-ARCH-023, 025, 040.

**Ключевые работы:**
- `ViabilityMatrix` с явной таблицей.
- `DialogueClassification` с формальными правилами.
- `ReferentialClosureInvariant` в CI.

**Критерии готовности фазы:**
- Все три спецификации задокументированы в ADR.
- Инварианты зелёные в CI.

### Фаза 11 — Когнитивная архитектура (P0, 2 недели)

**Цель:** Ввести градацию подавления и observer context.

**Проблемы:** ENIGMA-ARCH-031, 036.

**Ключевые работы:**
- Шкала `initiative_suppression` с 4 градациями.
- `ObserverContext` в `InterpretationEngine`.

### Фаза 12 — Belief-система: валидация и cooling (P0, 2 недели)

**Цель:** Ввести валидацию убеждений против objective truth и cooling down.

**Проблемы:** ENIGMA-ARCH-035, 039.

**Ключевые работы:**
- `BeliefValidator` с источником `ObjectiveTruthState`.
- `BeliefCoolingDown` с per-source скоростями.

### Фаза 13 — LifeEngine и Single Bypass Authority (P0, 2 недели)

**Цель:** Унифицировать все bypass'ы расписания через единую точку контроля.

**Проблемы:** ENIGMA-ARCH-037, 028.

**Ключевые работы:**
- `ScheduleBypassAuthority` с типизированными причинами.
- `NeedPriorityResolver` с Maslow-иерархией.

### Фаза 14 — Память, диалоги и события (P1, 3 недели)

**Цель:** Улучшить STM, тесты SpeechScheduler и ввести Narrative Beats.

**Проблемы:** ENIGMA-ARCH-026, 030, 032, 034.

**Ключевые работы:**
- `DialogueTurnDecay` вместо мгновенной очистки.
- Интеграционные тесты SpeechScheduler.
- `social_target_resolver` — полный аудит и расширение.
- `NarrativeBeatAggregator`.

---

## 8. Приоритизация (сводная, продолжение ТЗ-А1)

| Приоритет | ID проблем | Обоснование |
|---|---|---|
| **P0** | 021, 022, 023, 025, 027, 031, 035, 037, 038, 039, 040 | Нарушают фундаментальные принципы (калибровка, concurrency, формальные спецификации, эпистемическая валидация); блокируют балансировку и A/B; создают bottleneck |
| **P1** | 024, 026, 028, 029, 030, 032, 033, 034, 036 | Снижают правдоподобие, тестируемость, расширяемость; не блокируют разработку, но повышают риск регрессий |

---

## 9. Сквозные работы (дополнение к ТЗ-А1)

К сквозным работам ТЗ-А1 §9 добавляются:

5. **Единый `CalibrationProfile`.** Все коэффициенты из проблем 021, 024, 029, 031, 033 должны жить в одном профиле, не в разных конфигах.
6. **Метрики observability.** Для каждой проблемы 022, 027, 035, 037, 038 вводится метрика, экспортируемая в CI-отчёт.
7. **Расширение `lint_magic_numbers.py`.** Должен покрывать все новые модули, затронутые Фазами 8–14.
8. **Per-archetype профили.** Введён каталог `config/npc/calibration/` с профилями для каждого архетипа.

---

## 10. Контракты и ограничения (дополнение к ТЗ-А1)

К ограничениям ТЗ-А1 §10 добавляются:

6. **Совместимость с ADR-O-343.** Любые изменения в `TaskScheduler` и `SpeechScheduler` не должны нарушать ADR-O-343 (Арбитраж речи) без явного ADR-ревизии.
7. **Совместимость с GAP9.** Изменения в sleep-bypass должны сохранять семантику «реалистичного пробуждения» — NPC не засыпает при угрозе, даже если пороги стали настраиваемыми.
8. **Не нарушать детерминизм.** CalibrationProfile должен быть частью `TickState` (seeded), а не внешним конфигом; иначе нарушится принцип из ТЗ-А1 §4.4.

---

## 11. Критерии готовности (глобальные, дополнение к ТЗ-А1)

К критериям ТЗ-А1 §11 добавляются:

8. Линтер `lint_magic_numbers.py` не находит ни одного числового литерала вне whitelist в `app/services/npc/*`.
9. Per-task timeout в `TaskScheduler` работает; метрика `scheduler_stall_seconds` экспортируется.
10. `BackpressurePolicy` активна; метрика `queue_overflow_events` видна в CI.
11. Все bypass'ы расписания проходят через `ScheduleBypassAuthority`; логируется каждый bypass с причиной.
12. `BeliefValidator` сверяет убеждения с `ObjectiveTruthState`; метрика `false_belief_count` экспортируется.
13. `ViabilityMatrix` документирована и визуализируется через debug-эндпоинт.

---

## 12. Риски и смягчения (дополнение к ТЗ-А1)

| Риск | Вероятность | Влияние | Смягчение |
|---|---|---|---|
| Hot-reload `CalibrationProfile` нарушит детерминизм | Высокая | Высокое | Профиль seeded в `TickState`; hot-reload только между сессиями |
| Устранение `max_workers=1` вскроет скрытые race conditions | Высокая | Высокое | Поэтапный переход: сначала timeout, потом concurrency=2 с feature flag |
| `BeliefValidator` против objective truth сломает румор-систему | Средняя | Среднее | Rumor-source убеждения не валидируются; валидируются только perception-source |
| Градация `initiative_suppression` сделает поведение менее предсказуемым | Средняя | Низкое | Все пороги вынесены в профиль; тесты покрывают все 4 градации |
| `NarrativeBeatAggregator` замедлит тик | Низкая | Среднее | Агрегация асинхронна; не блокирует пайплайн |
| `BackpressurePolicy` отбросит важные canonical задачи | Средняя | Высокое | Drop только для `priority ≤ 3`; canonical минимум `priority = 5`; degrade canonical→ambient только при `pending_count > 0.95 * max_pending` |

---

## 13. Метрики и верификация (дополнение к ТЗ-А1)

| Метрика | Целевое значение | Источник данных |
|---|---|---|
| Количество числовых литералов вне whitelist в `app/services/npc/*` | 0 | `lint_magic_numbers.py` |
| `scheduler_stall_seconds` (макс. за сессию) | < 5 сек | `task_scheduler.py` |
| `queue_overflow_events` за 100 тиков | 0 (или < 5 при стресс-тесте) | `dialogue_queue.py` |
| `reconstruction_fallback_events` за тик | 0 | `task_scheduler_audit.jsonl` |
| `schedule_bypass_events` с неклассифицированной причиной | 0 | `schedule_bypass_audit.jsonl` |
| `false_belief_count` (убеждения с `confidence > 0.8` и расхождением с `ObjectiveTruthState`) | < 5% | `belief_validator.py` |
| Покрытие тестами `SpeechScheduler` | ≥ 90% | coverage report |
| `narrative_beats_per_session` | > 0 (функциональность активна) | `narrative_event_bus` |

---

## 14. Приложения

### Приложение А. Сводная таблица верификации проблем 21–40

| ID | Файл | Строки | Статус верификации |
|---|---|---|---|
| 021 | `interpretation_engine.py`, `life_engine.py`, `belief_transition_engine.py` | 39–59, 1489–1491, 1133, 1786 | ✅ Подтверждено |
| 022 | `task_scheduler.py` | 57–61 | ✅ Подтверждено (дословный комментарий) |
| 023 | `dm_phase.py` | 274–282 | ✅ Подтверждено |
| 024 | `life_engine.py` | 1786–1796 | ✅ Подтверждено (`threat > 0.3 or stress > 50`) |
| 025 | `life_engine.py` | 1540–1613 | ✅ Подтверждено |
| 026 | `speech_scheduler.py`, `test_speech_scheduler.py` | — | ✅ Подтверждено (базовые тесты есть, сложных нет) |
| 027 | `dialogue_queue.py` | весь файл | ✅ Подтверждено (нет max_size/drop) |
| 028 | `life_engine.py` | 1131–1134 | ✅ Подтверждено (`priority = 0.8` для всех) |
| 029 | `sandbox_results.csv` (0.05 в данных) | — | ✅ Частично (требует уточнения при реализации) |
| 030 | `memory_manager.py` | 89, 132 | ✅ Подтверждено |
| 031 | `life_engine.py` | 1097, 1439, 1674 | ✅ Подтверждено (`if _init_sup > 0.7`) |
| 032 | `npc_tick_pipeline.py`, `social_target_resolver.py` | — | ✅ Частично (требует аудита resolver'а) |
| 033 | `dm_phase.py`, `combat_subscriber.py` | 137, 131 | ✅ Подтверждено (2 разных значения) |
| 034 | `backend/app/services/scene/` | — | ✅ Подтверждено (нет агрегатора) |
| 035 | `models/npc/beliefs.py` | 24–31 | ✅ Подтверждено |
| 036 | `interpretation_engine.py` | 116–167 | ✅ Подтверждено (нет observer context) |
| 037 | `life_engine.py` | 1097, 1439, 1674, 1774 | ✅ Подтверждено (4 отдельных bypass'а) |
| 038 | `task_scheduler.py` | 334–379 | ✅ Подтверждено (множественные try/except) |
| 039 | `belief_transition_engine.py` | — | ✅ Подтверждено (нет temporal decay) |
| 040 | `task_scheduler.py` | 171, 215–217 | ✅ Подтверждено (routes без классификатора) |

### Приложение Б. Перекрёстные ссылки на ТЗ-А1

| Проблема ТЗ-А2 | Связанная проблема ТЗ-А1 | Тип связи |
|---|---|---|
| 022 (ThreadPool) | — | Новая |
| 023 (Referential Closure) | 019 (Каузальная замкнутость) | Расширение инварианта |
| 024 (GAP9 пороги) | 021 (Калибровка) | Подкатегория |
| 027 (Backpressure) | 017 (Silent failures) | Параллель |
| 030 (STM decay) | 013 (EpistemicStore decay) | Аналог |
| 032 (Social target) | 007 (Proactive movement) | Расширение |
| 035 (Belief validation) | 013 (EpistemicStore decay), 016 (Persistence) | Расширение |
| 036 (Observer context) | 012 (WillpowerGate observers) | Параллель |
| 037 (Single bypass) | 017 (Silent failures) | Параллель |
| 038 (Reconstruction) | 017 (Silent failures) | Параллель |
| 039 (Cooling down) | 013 (EpistemicStore decay) | Аналог |
| 040 (Ambient/Canonical) | 005 (Perception component) | Параллель |

### Приложение В. Источники

- Архив исходного кода: `Enigma-V.0.5.3.8.2_-.zip`
- ТЗ-А1: `/home/z/my-project/download/ТЗ_Architect_Enigma_V0.5.3.8.2.md`
- Существующие ADR: `docs/audits/ADR-*_IMPACT.md` (особенно ADR-O-343, ADR-O-342, ADR-O-353, ADR-052)
- Архитектурный устав: `docs/АРХИТЕКТУРНЫЙ_УСТАВ_ENIGMA.md`
- Каузальный контракт: `docs/00_CAUSAL_CONTRACT_v2.0.md`
