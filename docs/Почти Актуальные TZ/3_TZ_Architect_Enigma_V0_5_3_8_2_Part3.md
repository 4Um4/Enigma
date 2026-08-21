# Техническое задание для архитектора (ТЗ-А3)

**Проект:** Enigma — каузальное ядро симуляции NPC  
**Версия проекта:** V0.5.3.8.2  
**Версия документа:** 1.0 (продолжение ТЗ-А1 и ТЗ-А2 от 2026-08-18)  
**Дата составления:** 2026-08-18  
**Адресат:** Архитектор систем симуляции / tech-lead backend  
**Автор верификации:** AI-аудит (на основе исходного кода `backend/app/services/...`)  
**Статус верификации:** все 20 проблем (№41–60) сверены с исходным кодом архива `Enigma-V.0.5.3.8.2_-.zip`

---

## 1. Назначение документа

Настоящий документ является третьей частью аудиторской серии (ТЗ-А1 → ТЗ-А2 → ТЗ-А3) и описывает 20 дополнительных архитектурных проблем (№41–60), выявленных при глубоком аудите четырёх ключевых компонентов: `StateInterpreter` (вербализация), `MemoryManager` (память), `EventBus` (события) и `SpatialService` (навигация). Документ сохраняет структуру ТЗ-А1/А2: фиксированные архитектурные домены, приоритизация P0/P1/P2, формальные Definition of Done для каждой проблемы и этапы реализации.

Документ самостоятелен: проблемы 41–60 не дублируют проблемы 1–40, а раскрывают инфраструктурный слой архитектурного долга (событийная шина, pathfinding, кэши, персистентность памяти). При чтении вместе с ТЗ-А1 и ТЗ-А2 даёт полную картину из 60 верифицированных проблем.

## 2. Контекст и обоснование

ТЗ-А1 зафиксировало фундаментальные нарушения эпистемической изоляции и каузальной замкнутости. ТЗ-А2 раскрыло проблемы калибровки, concurrency и формальных спецификаций. Расширенный аудит четырёх инфраструктурных компонентов выявил третий класс проблем: синхронная обработка в `EventBus` без таймаутов, «чёрная дыра» Dead Letter Queue, хрупкие строковые ключи STM, отсутствие защиты от бесконечных циклов в A*, O(n) zone detection, статичность boundary-узлов, недоступность semantic tags для downstream, отсутствие cooldown для resonance detection и др.

Особенность этого блока: проблемы концентрируются в инфраструктурных слоях (events, memory, spatial), которые пересекают все домены из ТЗ-А1/А2. Без их устранения любые точечные исправления в NPC-пайплайне будут разбиваться о ненадёжную инфраструктуру: даже идеально изолированный эпистемически NPC будет страдать от потери диалогов при crash, от зависания системы из-за медленного handler'а, от ложных путей из-за статичных boundary-узлов.

Аудит также зафиксировал ряд сильных сторон архитектуры (см. §5.13), которые должны быть сохранены при рефакторинге: `StateInterpreter` как мост между числами и словами, слоистая память, система секретов с трещинами, трёхслойная модель `SpatialService`, overlay-система, affordance-объекты, causal purity decay и boundary-узлы.

## 3. Глоссарий (дополнение к ТЗ-А1/А2)

| Термин | Определение |
|---|---|
| `StateInterpreter` | Слой вербализации: единственный мост между числовым состоянием и human-readable описанием для LLM |
| `MemoryManager` | Менеджер памяти NPC: STM, working memory, narrative cache, identity cache, resonance |
| `EventBus` | Синхронная шина событий: `publish()` вызывает всех подписчиков последовательно |
| `SpatialService` | Навигационный сервис: geometry → topology → semantics, A* pathfinding |
| `_dlq` | Dead Letter Queue — события, упавшие после 2 попыток, накапливаются без повторной обработки |
| `DialogueConsolidator` | Компонент суммаризации STM-сессии в EventMemory при `clear_dialogue_session()` |
| `_path_cache` | LRU-кэш путей A* в `SpatialService`, инвалидируется при смене overlay hash |
| `boundary_map` | Статичная карта узлов перехода между локациями |
| `SpatialOverlay` | Динамический слой поверх графа: crowd density, risk zones, light levels, blocked nodes |
| `resolve_affordance` | Поиск объекта с нужным affordance (например, «кровать» → sleep) |
| `get_zone_id` | Определение полигона (комнаты) по координатам через ray casting |
| `_PRESSURE_STRENGTH` | Таблица типов давления для discovery_check: physical/threat/intimidation/question |
| `WORKING_MEMORY_SIZE` | Размер working memory, hardcoded = 20 |
| `EventSemanticTagger` | Компонент, конвертирующий event_type в социальные теги (social:aggression и др.) |
| `MemoryPromotionEngine` | Компонент сжатия похожих событий в абстракции |
| `ResonanceEngine` | Детектор паттернов в working memory, формирует trait deltas |
| `_SHORT_FORM_FEMALE` | Словарь исключений для pymorphy3 (краткие причастия женского рода) |
| `Causal Purity decay` | Decay rate, определяемый importance события, а не emotion tags |
| STM session key | Строковый ключ формата `campaign_id:npc_a:npc_b` с сортировкой пары |

---

## 4. Архитектурные принципы (дополнение к ТЗ-А1/А2)

К принципам из ТЗ-А1 §4 и ТЗ-А2 §4 добавляются следующие, актуальные для блока 41–60:

16. **No blocking handlers in EventBus** — ни один handler шины событий не имеет права выполняться синхронно без таймаута; долгие операции (LLM, I/O) обязаны идти через async-пул.
17. **Dead Letter Queue is observable** — любая DLQ должна иметь механизм повторной обработки, алертинга и анализа причин падения; «чёрная дыра» недопустима.
18. **Type-safe keys** — ключи персистентных структур (STM-сессии, identity_cache) обязаны быть типизированными структурами, а не строками с разделителями; хрупкие строковые форматы запрещены.
19. **Crash-safe consolidation** — любая операция консолидации/компрессии памяти обязана быть атомарной; потеря данных при crash недопустима.
20. **Cache granularity** — инвалидация кэша должна быть минимальной (по ключу, по подобласти), а не грубой (весь кэш при любом изменении overlay).
21. **Bounded algorithms** — любой алгоритм с циклом `while` обязан иметь максимальное число итераций; бесконечные циклы недопустимы.
22. **Spatial indexing** — частые операции (zone detection, nearest-node) обязаны использовать пространственные индексы (R-tree, quadtree), а не O(n) перебор.
23. **Affordance accessibility** — выбор affordance-объекта обязан учитывать достижимость (path exists), занятость (reserved), физическую доступность (не за стеной).
24. **Dynamic topology** — топология графа (boundary nodes, connections) обязана поддерживать динамические изменения во время gameplay; статичность запрещена.
25. **Semantic tags must flow downstream** — любая семантическая разметка (threat/social/anomaly) обязана потребляться downstream-компонентами; декораторы без эффекта запрещены.
26. **Cooldown for pattern detection** — любой детектор паттернов (resonance, anomalies) обязан иметь cooldown для предотвращения rapid drift.
27. **Adaptive sizing** — размеры структур данных (working memory, caches) обязаны адаптироваться к характеристикам NPC (intelligence, memory capacity), а не быть фиксированными.

---

## 5. Каталог архитектурных проблем (продолжение)

Каждая проблема описана по шаблону из ТЗ-А1: ID → Категория → Severity → Статус верификации → Описание → Локализация → Нарушенный контракт → Definition of Done → Зависимости.

### 5.12. P0 — EventBus и обработка событий

---

#### ENIGMA-ARCH-041: EventBus блокирует весь pipeline при медленном обработчике

- **Категория:** EventBus / Concurrency
- **Severity:** P0
- **Статус верификации:** ✅ Подтверждено (`event_bus.py` строки 94–153 — `publish()` синхронно вызывает handlers в цикле)
- **Описание:** `EventBus.publish()` вызывает все обработчики синхронно в цикле. Если один обработчик зависает или выполняется долго (например, LLM-вызов), вся система обработки событий блокируется. Нет механизма timeout для отдельных handlers.
- **Локализация:** `backend/app/services/events/event_bus.py`, строки 94–153:
  ```python
  def publish(self, event: EventDTO) -> List[EventDTO]:
      """Публикует событие — вызывает всех подписчиков синхронно.
      Закон 2.1.1: publish() принимает только EventDTO. Всё остальное — TypeError.
      """
      ...
      handlers = self._handlers.get(_evt_type, [])
      for handler in handlers:
          # V8-DEC-11 FIX: Retry (1 attempt) + DLQ on final failure
          _success = False
          for _attempt in range(2):
              ...
  ```
- **Нарушенный контракт:** §4.16 (No blocking handlers in EventBus); §4.10 (Concurrency by design).
- **Definition of Done:**
  1. Введён `HandlerTimeout` — каждый handler выполняется с таймаутом (настраиваемым per event_type); при превышении handler прерывается, эмитится `HandlerTimeoutEvent`.
  2. Долгие handlers (LLM, I/O) помечаются как `async=True` и выполняются через пул; `publish()` не ждёт их завершения.
  3. Введён `HandlerPriority` — критические handlers (combat, perception) выполняются первыми; narrative/logging handlers — последними.
  4. Тесты: `test_event_bus_timeout.py`, `test_event_bus_async_handler.py`, `test_event_bus_priority_order.py`.
  5. Метрика `handler_stall_seconds` экспортируется в CI; alert при > 1 сек.
- **Зависимости:** ENIGMA-ARCH-022 (ТЗ-А2), ENIGMA-ARCH-042, ENIGMA-ARCH-055.

---

#### ENIGMA-ARCH-042: Dead Letter Queue не имеет механизма повторной обработки

- **Категория:** EventBus / Robustness
- **Severity:** P0
- **Статус верификации:** ✅ Подтверждено (`event_bus.py` строки 52–53, 137–140 — `_dlq` только накапливает, нет reprocessing)
- **Описание:** События, упавшие после 2 попыток, попадают в `_dlq`, но нет механизма их повторной обработки, анализа причин падения или алертинга. Это «чёрная дыра» для событий.
- **Локализация:** `backend/app/services/events/event_bus.py`, строки 52–53, 137–140:
  ```python
  # V8-DEC-11 FIX: Dead Letter Queue для событий, упавших после retry
  self._dlq: List[EventDTO] = []
  ...
  if not _success:
      self._dlq.append(event)
      if len(self._dlq) > 100:  # Ограничиваем размер DLQ
          self._dlq.pop(0)
  ```
- **Нарушенный контракт:** §4.17 (Dead Letter Queue is observable).
- **Definition of Done:**
  1. Введён `DlqReprocessor` — компонент, периодически анализирующий `_dlq` и пытающийся повторно обработать события после устранения причины.
  2. Каждое событие в DLQ имеет: `failure_reason`, `attempts_count`, `last_attempt_tick`, `next_retry_tick`.
  3. Введён `DlqAlerting` — при накоплении > N событий одного типа эмитится alert в CI-отчёт.
  4. Введён debug-эндпоинт `GET /debug/dlq` для инспекции содержимого.
  5. Тесты: `test_dlq_reprocessing.py`, `test_dlq_alerting.py`, `test_dlq_persistence.py`.
  6. Метрика `dlq_size` и `dlq_reprocess_success_rate` экспортируются.
- **Зависимости:** ENIGMA-ARCH-041, ENIGMA-ARCH-055.

---

#### ENIGMA-ARCH-055: Handler execution order undefined

- **Категория:** EventBus / Ordering
- **Severity:** P0
- **Статус верификации:** ✅ Подтверждено (`event_bus.py` — handlers в `_handlers` хранятся как список, порядок insertion; нет явных dependencies/priorities)
- **Описание:** Handlers в EventBus выполняются в порядке insertion, но нет way to specify dependencies (handler B должен выполниться после A) или priorities. Это может привести к race conditions.
- **Локализация:** `backend/app/services/events/event_bus.py` — `self._handlers: Dict[str, List[Callable]]`; порядок = insertion order.
- **Нарушенный контракт:** §4.16 (No blocking handlers); каузальная замкнутость (порядок влияния на состояние).
- **Definition of Done:**
  1. Введён `HandlerSpec` с полями: `priority: int`, `depends_on: List[handler_id]`, `async: bool`, `timeout_sec: float`.
  2. `subscribe()` принимает `HandlerSpec`; handlers сортируются по `priority` и топологически по `depends_on`.
  3. При циклической зависимости в `depends_on` эмитится `DependencyCycleEvent` и подписка отклоняется.
  4. Тесты: `test_handler_priority.py`, `test_handler_dependencies.py`, `test_handler_cycle_detection.py`.
  5. Документ: таблица всех handlers с их приоритетами и зависимостями.
- **Зависимости:** ENIGMA-ARCH-041.

### 5.13. P0 — Memory и персистентность

---

#### ENIGMA-ARCH-043: STM session keys хрупкие и подвержены ошибкам

- **Категория:** Memory / Type safety
- **Severity:** P0
- **Статус верификации:** ✅ Подтверждено (`memory_manager.py` строки 76–83, 100–145 — строковый ключ с сортировкой, множество fix-комментариев V8-DLG-13, BUG-DLG-007, BUG-DLG-008)
- **Описание:** Формат ключа `campaign_id:npc_a:npc_b` с сортировкой для изоляции пар A↔B от A↔C. В коде видно множество фиксов (V8-DLG-13, BUG-DLG-007, BUG-DLG-008), связанных с этим форматом. Это признак over-engineering без type-safe гарантий.
- **Локализация:** `backend/app/services/memory/memory_manager.py`, строки 76–83, 100–145:
  ```python
  def get_dialogue_session(self, campaign_id, npc_id, partner_id="player"):
      # V8-DLG-13 FIX: Используем сортированный ключ для изоляции пар A↔B от A↔C
      pair_key = tuple(sorted((npc_id, partner_id)))
      key = f"{campaign_id}:{pair_key[0]}:{pair_key[1]}"
      ...
  def clear_dialogue_session(self, ...):
      # BUG-DLG-007 FIX: Используем симметричный сортированный ключ
      ...
  def clear_all_dialogue_sessions(self, ...):
      # BUG-DLG-008 FIX: Извлекаем npc_a и npc_b из ключа "campaign_id:npc_a:npc_b"
      parts = key.split(":")
      if len(parts) >= 3:
          _, npc_a, npc_b = parts[0], parts[1], parts[2]
      ...
  ```
- **Нарушенный контракт:** §4.18 (Type-safe keys).
- **Definition of Done:**
  1. Введён `DialogueSessionKey` — `@dataclass(frozen=True)` с полями `campaign_id: str`, `participants: frozenset[str, str]` (ровно 2 участника).
  2. `_dialogue_sessions: Dict[DialogueSessionKey, DialogueSession]` — типизированный словарь.
  3. Все строковые операции `key.split(":")` удалены; доступ только через методы класса.
  4. Тест `test_session_key_immutability.py` — ключ нельзя создать с одним участником или с тремя.
  5. Миграция: существующие строковые ключи конвертируются в `DialogueSessionKey` при первом доступе.
- **Зависимости:** ENIGMA-ARCH-045, ENIGMA-ARCH-030 (ТЗ-А2).

---

#### ENIGMA-ARCH-044: Secret discovery formula непрозрачна

- **Категория:** Memory / Documentation
- **Severity:** P0
- **Статус верификации:** ✅ Подтверждено (`memory_manager.py` строки 395–456 — `_PRESSURE_STRENGTH`, `discovery_check`, `resistance = importance * 0.8`)
- **Описание:** Метод `discovery_check()` имеет сложную формулу с множителями: `resistance = importance * 0.8`, `_PRESSURE_STRENGTH` таблица, модификаторы trust/stress. Нет документации ожидаемого поведения или unit tests для граничных случаев (что если NPC с high trust и low stress?).
- **Локализация:** `backend/app/services/memory/memory_manager.py`, строки 395–456:
  ```python
  _PRESSURE_STRENGTH: dict[str, float] = {
      "physical": 0.45,
      "threat": 0.35,
      "intimidation": 0.20,
      "question": 0.02,
  }
  ...
  def discovery_check(self, memory, *, pressure_type, pressure_count, npc_trust, npc_stress):
      strength = self._PRESSURE_STRENGTH.get(pressure_type, 0.0)
      ...
      resistance = memory.importance * 0.8
      trust_modifier = max(0.0, -npc_trust) * 0.15 if npc_trust < 0 else 0.0
      stress_modifier = ...
  ```
- **Нарушенный контракт:** §4.12 (Formal specification for filters); тестируемость граничных случаев.
- **Definition of Done:**
  1. Формула discovery задокументирована в ADR с примерами для всех комбинаций (high trust + low stress, low trust + high stress, и т.д.).
  2. Все коэффициенты вынесены в `CalibrationProfile` (см. ENIGMA-ARCH-021 ТЗ-А2) как `DiscoveryFormulaProfile`.
  3. Unit-тесты покрывают все граничные случаи: `test_discovery_high_trust_low_stress.py`, `test_discovery_low_trust_high_stress.py`, `test_discovery_neutral.py`, `test_discovery_extreme_pressure.py`.
  4. Введён `DiscoveryTrace` — отладочный DTO, выводящий каждый шаг вычисления (resistance, modifiers, threshold, result).
  5. Тесты проверяют ожидаемое поведение (CRACK/PARTIAL/BROKEN) для каждой комбинации.
- **Зависимости:** ENIGMA-ARCH-021 (ТЗ-А2), ENIGMA-ARCH-035 (ТЗ-А2).

---

#### ENIGMA-ARCH-045: Dialogue consolidation может потеряться при crash

- **Категория:** Memory / Persistence
- **Severity:** P0
- **Статус верификации:** ✅ Подтверждено (`memory_manager.py` строки 100–130 — `clear_dialogue_session()` вызывает `consolidate()` и `pop()`; нет WAL/transaction)
- **Описание:** При `clear_dialogue_session()` вызывается `DialogueConsolidator.consolidate()` для суммаризации STM в EventMemory. Но если игра крашится до этого момента, весь диалог теряется без следа.
- **Локализация:** `backend/app/services/memory/memory_manager.py`, строки 100–130:
  ```python
  def clear_dialogue_session(self, campaign_id, npc_id, partner_id="player"):
      ...
      session = self._dialogue_sessions.get(key)
      if session is None:
          return
      # BUG-DL-07: Consolidation в EventMemory перед discard
      if summary := self._dialogue_consolidator.consolidate(session):
          self._pending_dialogue_memories.append(EventDTO.create(...))
      session.clear()
      self._dialogue_sessions.pop(key, None)
  ```
- **Нарушенный контракт:** §4.19 (Crash-safe consolidation); §4.5 (No silent failures).
- **Definition of Done:**
  1. Введён `IncrementalConsolidator` — реплики суммаризуются постепенно (каждые N реплик), а не только при `clear_dialogue_session()`.
  2. `EventMemory`-консолидация пишется в SQLite через WAL (write-ahead log) перед `session.clear()`.
  3. При restart системы проверяется `_pending_dialogue_memories` и применяется к `LayeredMemory`.
  4. Тесты: `test_consolidation_crash_recovery.py` (crash между consolidate и pop), `test_consolidation_incremental.py`, `test_consolidation_wal.py`.
  5. Метрика `consolidation_loss_events` (потери при crash) = 0.
- **Зависимости:** ENIGMA-ARCH-043, ENIGMA-ARCH-059.

---

#### ENIGMA-ARCH-058: Memory compression не имеет verification

- **Категория:** Memory / Verification
- **Severity:** P0
- **Статус верификации:** ✅ Подтверждено (`promotion_engine.py` — `compress()` создаёт абстракцию, нет проверки корректности)
- **Описание:** `MemoryPromotionEngine.compress()` сжимает похожие события в абстракции, но нет механизма проверки, что compressed memory корректно отражает оригинальные события. Возможна lossy compression без way to recover.
- **Локализация:** `backend/app/services/memory/promotion_engine.py`, класс `MemoryPromotionEngine`, метод `compress()`:
  ```python
  class MemoryPromotionEngine:
      """Сжатие памяти + генерация мета-черт (Этапы 9-10)."""
      def compress(self, events: Sequence[EventMemory]) -> List[CompressionResult]:
          # Фильтруем кандидатов: importance < 0.5, не секреты, не сжатые
          ...
          compressed = EventMemory(
              event_type="compressed",
              ...
              is_compressed=True,
              compressed_from=tuple(...),
          )
  ```
- **Нарушенный контракт:** Каузальная замкнутость памяти; возможность верификации.
- **Definition of Done:**
  1. Введён `CompressionVerifier` — компонент, проверяющий, что compressed memory содержит все ключевые факты оригиналов (actor, target, tags, importance range, temporal span).
  2. При расхождении эмитится `CompressionMismatchEvent` с указанием потерянных фактов.
  3. Сжатые события сохраняют `compressed_from` (ID оригиналов) — уже есть, но добавляется `compressed_hash` для целостности.
  4. Введён `DecompressionRecovery` — возможность восстановить оригинальные события из compressed (для debug/legal-mode).
  5. Тесты: `test_compression_verifier.py`, `test_compression_recovery.py`, `test_compression_lossless.py`.
- **Зависимости:** ENIGMA-ARCH-045, ENIGMA-ARCH-035 (ТЗ-А2).

---

#### ENIGMA-ARCH-059: Identity cache persistence gap

- **Категория:** Memory / Persistence
- **Severity:** P0
- **Статус верификации:** ✅ Подтверждено (`memory_manager.py` строки 52–57 — дословный комментарий «Safe call: SqliteMemoryStore may not have load_state (legacy gap)»)
- **Описание:** V8-MEM-7 добавил persistence для identity_cache, но комментарий «Safe call: SqliteMemoryStore may not have load_state (legacy gap)» указывает на incomplete migration. Некоторые NPC могут терять accumulated traits после restart.
- **Локализация:** `backend/app/services/memory/memory_manager.py`, строки 52–57:
  ```python
  # V8-MEM-7 FIX: Загружаем identity_cache из SQLite/JSON при старте
  # Safe call: SqliteMemoryStore может не иметь load_state (legacy gap)
  if hasattr(self._layered.store, "load_state"):
      self._identity_cache: Dict[str, Dict[str, float]] = self._layered.store.load_state("identity_cache")
  else:
      self._identity_cache: Dict[str, Dict[str, float]] = {}
  ```
- **Нарушенный контракт:** §4.19 (Crash-safe consolidation); завершённость миграции.
- **Definition of Done:**
  1. `SqliteMemoryStore` (и все реализации `MemoryStore`) обязаны иметь `load_state` / `save_state` — интерфейс сделан формальным (Protocol/ABC).
  2. `hasattr` check удалён; отсутствие `load_state` — ошибка инициализации, не silent fallback.
  3. Тест `test_identity_cache_persistence.py`: накопленные traits переживают restart.
  4. Миграционный скрипт: старые store'ы без `load_state` обновляются автоматически.
  5. Метрика `identity_cache_loss_events` = 0 после миграции.
- **Зависимости:** ENIGMA-ARCH-016 (ТЗ-А1), ENIGMA-ARCH-045.

---

#### ENIGMA-ARCH-060: Resonance detection не имеет cooldown

- **Категория:** Memory / Personality drift
- **Severity:** P0
- **Статус верификации:** ✅ Подтверждено (`memory_manager.py` строки 762+, `resonance_engine.py` — `detect()` вызывается каждый тик без cooldown)
- **Описание:** `detect_resonance()` ищет patterns в working memory, но нет cooldown period. Если NPC переживает повторяющиеся события (например, daily routine), resonance может triggered каждый тик, приводя к rapid personality drift.
- **Локализация:** `backend/app/services/memory/memory_manager.py` строка 762 (`detect_resonance`), `backend/app/services/memory/resonance_engine.py` — метод `detect()`; вызывается из `working_memory_tick.py` строки 122 и `phases/memory.py` строки 121 каждый тик.
- **Нарушенный контракт:** §4.26 (Cooldown for pattern detection); стабильность личности NPC.
- **Definition of Done:**
  1. Введён `ResonanceCooldown` — после срабатывания pattern, повторная детекция того же pattern'а для того же NPC блокируется на N тиков.
  2. Cooldown конфигурируется per-pattern-type (`betrayal_chain` → длинный cooldown, `chronic_help` → короткий).
  3. Введён `ResonanceDriftGuard` — максимальный delta trait per tick; при превышении delta обрезается и эмитится `RapidDriftEvent`.
  4. Тесты: `test_resonance_cooldown.py`, `test_resonance_drift_guard.py`, `test_resonance_routine_no_trigger.py`.
  5. Метрика `resonance_triggers_per_tick` экспортируется; alert при > threshold.
- **Зависимости:** ENIGMA-ARCH-052, ENIGMA-ARCH-058.

### 5.14. P0 — SpatialService и навигация

---

#### ENIGMA-ARCH-046: Path cache инвалидация слишком грубая

- **Категория:** Spatial / Performance
- **Severity:** P0
- **Статус верификации:** ✅ Подтверждено (`spatial_service.py` строки 214–220 — `set_overlay()` очищает весь `_path_cache` при любом изменении overlay hash)
- **Описание:** `SpatialService._path_cache` инвалидируется при изменении overlay hash. Но overlay обновляется каждый тик (crowd density, risk zones, light levels), что приводит к постоянным cache misses. A* pathfinding становится expensive.
- **Локализация:** `backend/app/services/spatial/spatial_service.py`, строки 214–220:
  ```python
  def set_overlay(self, overlay: SpatialOverlay) -> None:
      """Обновляет overlay. Инвалидирует кэш путей при изменении."""
      new_hash = overlay.compute_hash()
      old_hash = self._overlay.compute_hash()
      if new_hash != old_hash:
          self._path_cache.clear()  # ← ГРУБАЯ ИНВАЛИДАЦИЯ
      self._overlay = overlay
  ```
- **Нарушенный контракт:** §4.20 (Cache granularity); производительность.
- **Definition of Done:**
  1. Кэш путей инвалидируется не по полному hash, а по изменению конкретных полей: `blocked_nodes` (полная инвалидация затронутых путей), `crowd_density` / `risk_zones` / `light_levels` (частичная — путь остаётся валидным, но cost пересчитывается при извлечении).
  2. Введён `PathCacheKey` с версией `blocked_nodes_hash`; кэш хранит пути с версией, при несовпадении — пересчёт.
  3. Для `crowd_density` / `risk_zones` введён `cost_recompute_threshold` — путь пересчитывается только если cost изменился более чем на N%.
  4. Тесты: `test_path_cache_partial_invalidation.py`, `test_path_cache_blocked_nodes.py`, `test_path_cache_cost_recompute.py`.
  5. Метрика `path_cache_hit_rate` ≥ 60% в типичной сессии.
- **Зависимости:** ENIGMA-ARCH-047, ENIGMA-ARCH-048.

---

#### ENIGMA-ARCH-047: A* не имеет protection от infinite loops

- **Категория:** Spatial / Safety
- **Severity:** P0
- **Статус верификации:** ✅ Подтверждено (`spatial_service.py` строки 565–600 — цикл `while open_set:` без лимита итераций)
- **Описание:** Метод `find_path()` имеет цикл `while open_set:`, но нет максимального лимита итераций. На pathological графах или при багах в `_connections` это может hang the game.
- **Локализация:** `backend/app/services/spatial/spatial_service.py`, строки 565–600:
  ```python
  while open_set:
      _, _, current_id = heapq.heappop(open_set)
      if current_id == target_id:
          # Восстановление пути
          path = self._reconstruct_path(came_from, current_id)
          ...
          return path
      ...
  ```
- **Нарушенный контракт:** §4.21 (Bounded algorithms); safety.
- **Definition of Done:**
  1. Введён `MAX_ASTAR_ITERATIONS` (настраиваемый, по умолчанию `10 * len(graph.nodes)`).
  2. При превышении лимита: эмитится `PathfindingTimeoutEvent`, `find_path()` возвращает `[]` (пустой путь), NPC fallback на `idle`/`wander`.
  3. Введён детектор циклов в `came_from` — если узел посещается дважды с тем же g_score, эмитится `GraphCycleEvent`.
  4. Тесты: `test_astar_max_iterations.py`, `test_astar_graph_cycle.py`, `test_astar_pathological_graph.py`.
  5. Метрика `astar_timeout_events` экспортируется; alert при > 0.
- **Зависимости:** ENIGMA-ARCH-046, ENIGMA-ARCH-050.

---

#### ENIGMA-ARCH-048: Zone detection O(n) per polygon

- **Категория:** Spatial / Performance
- **Severity:** P0
- **Статус верификации:** ✅ Подтверждено (`spatial_service.py` строки 246–270 — `get_zone_id()` перебирает все полигоны с ray casting)
- **Описание:** Метод `get_zone_id()` использует ray casting algorithm, который O(n) для каждого полигона. Если комната имеет сложный shape с 100+ vertices и вызывается часто (каждый тик для каждого NPC), это bottleneck.
- **Локализация:** `backend/app/services/spatial/spatial_service.py`, строки 246–270:
  ```python
  def get_zone_id(self, x: float, y: float) -> Optional[str]:
      if not self._rooms_geometry:
          return None
      for zone_id, polygon in self._rooms_geometry.items():
          # Алгоритм Ray Casting (even-odd rule)
          n = len(polygon)
          inside = False
          p1x, p1y = polygon[0]
          for i in range(n + 1):
              p2x, p2y = polygon[i % n]
              ...
  ```
- **Нарушенный контракт:** §4.22 (Spatial indexing); производительность.
- **Definition of Done:**
  1. Введён пространственный индекс (R-tree через `rtree` library или quadtree) над полигонами зон.
  2. `get_zone_id()` сначала запрашивает candidate polygons из R-tree (O(log n)), затем ray casting только для candidates.
  3. Кэш `last_zone_id` per NPC — если NPC не двигался, зона та же.
  4. Тесты: `test_zone_detection_rtree.py`, `test_zone_detection_cache.py`, `test_zone_detection_100_polygons.py` (benchmark).
  5. Метрика `zone_detection_avg_ms` ≤ 0.1 мс при 50 NPC.
- **Зависимости:** ENIGMA-ARCH-046.

---

#### ENIGMA-ARCH-049: Affordance resolution игнорирует accessibility

- **Категория:** Spatial / Affordances
- **Severity:** P0
- **Статус верификации:** ✅ Подтверждено (`spatial_service.py` строки 331–395 — `resolve_affordance()` ищет ближайший объект, проверяет reservation, но не проверяет path existence)
- **Описание:** `resolve_affordance()` находит ближайший объект с нужным affordance (например, кровать), но не проверяет: есть ли путь к нему? Занят ли он другим NPC? Доступен ли физически (не за стеной)?
- **Локализация:** `backend/app/services/spatial/spatial_service.py`, строки 331–395 (`resolve_affordance`) и строки 464–500 (`_compute_score` — проверяет `reserved_nodes`, `crowd_density`, `risk_zones`, но не path existence).
- **Нарушенный контракт:** §4.23 (Affordance accessibility).
- **Definition of Done:**
  1. `resolve_affordance()` добавляет проверку path existence: для top-N кандидатов вызывается `find_path()` (с лимитом итераций); недостижимые кандидаты отбрасываются.
  2. Проверка занятости уже есть (`reserved_nodes`) — сохраняется и расширяется: проверяется не только node-level reservation, но и physical occupancy (NPC стоит у объекта).
  3. Введён `AffordanceAccessibilityCache` — кэш достижимости объектов, обновляемый при изменении `blocked_nodes`.
  4. Тесты: `test_affordance_accessibility_path.py`, `test_affordance_accessibility_occupied.py`, `test_affordance_accessibility_blocked.py`.
  5. Метрика `affordance_inaccessible_events` экспортируется.
- **Зависимости:** ENIGMA-ARCH-046, ENIGMA-ARCH-047, ENIGMA-ARCH-050.

---

#### ENIGMA-ARCH-050: Boundary nodes статичны

- **Категория:** Spatial / Topology
- **Severity:** P0
- **Статус верификации:** ✅ Подтверждено (`spatial_service.py` строки 76–133 — `boundary_map` загружается в `build_for_location` и никогда не обновляется; `_boundary_map = boundary_map or {}`)
- **Описание:** `boundary_map` загружается один раз при `build_for_location` и никогда не обновляется. Если дверь заблокирована или стена разрушена во время gameplay, NPC продолжают пытаться использовать несуществующие transitions.
- **Локализация:** `backend/app/services/spatial/spatial_service.py`, строки 76–133 — `boundary_map` передаётся в `__init__` и сохраняется в `self._boundary_map`; методов обновления нет.
- **Нарушенный контракт:** §4.24 (Dynamic topology); каузальная замкнутость (NPC использует несуществующий переход).
- **Definition of Done:**
  1. Введён `BoundaryMapMutator` — компонент для динамического обновления `boundary_map` во время gameplay.
  2. Поддерживаемые операции: `block_boundary(node_id, reason)`, `unblock_boundary(node_id)`, `add_boundary(node_id, info)`, `remove_boundary(node_id)`.
  3. Изменения эмитят `BoundaryChangedEvent` в `EventBus`; подписчики (`MovementEngine`, `WorldTopologyProvider`) обновляют кэши.
  4. Path cache инвалидируется для путей, затрагивающих изменённые boundary-узлы.
  5. Тесты: `test_boundary_block.py`, `test_boundary_unblock.py`, `test_boundary_dynamic_add.py`.
  6. Метрика `boundary_changes_per_session` экспортируется.
- **Зависимости:** ENIGMA-ARCH-046, ENIGMA-ARCH-049.

### 5.15. P1 — Вербализация, tags и калибровка

---

#### ENIGMA-ARCH-051: Condition severity thresholds магические

- **Категория:** Calibration / Verbalization
- **Severity:** P1
- **Статус верификации:** ✅ Подтверждено (`state_interpreter.py` строки 80–83, 321–352 — `_SPEECH_BLOCKING_CONDITIONS`, `_MOVEMENT_BLOCKING_CONDITIONS`, `severity > 0.3`)
- **Описание:** `_SPEECH_BLOCKING_CONDITIONS` и `_MOVEMENT_BLOCKING_CONDITIONS` проверяют `severity > 0.3`, но этот threshold не configurable и не documented. Почему именно 0.3, а не 0.5?
- **Локализация:** `backend/app/services/verbalization/state_interpreter.py`, строки 80–83, 321–352:
  ```python
  _SPEECH_BLOCKING_CONDITIONS = {"stunned", "confused", "silenced"}
  _MOVEMENT_BLOCKING_CONDITIONS = {"stunned", "paralyzed", "frozen"}
  ...
  for cond in conditions.values():
      if cond.severity > 0.3:  # ← MAGIC NUMBER
          ...
      if cond.type in _SPEECH_BLOCKING_CONDITIONS and cond.severity > 0.3:
          return False
      if cond.type in _MOVEMENT_BLOCKING_CONDITIONS and cond.severity > 0.3:
          return False
  ```
- **Нарушенный контракт:** §4.9 (No magic numbers — из ТЗ-А2); документируемость.
- **Definition of Done:**
  1. Порог `0.3` вынесен в `CalibrationProfile` (см. ENIGMA-ARCH-021 ТЗ-А2) как `condition_blocking_severity_threshold`.
  2. Введён `ConditionProfile` с per-condition-type порогами: `stunned_threshold`, `confused_threshold`, и т.д. (разные conditions могут иметь разные пороги).
  3. ADR с обоснованием выбора `0.3` (почему не 0.5) — анализ playtest-данных или экспертное обоснование.
  4. Тесты: `test_condition_threshold_boundary.py` (0.29 vs 0.30 vs 0.31), `test_condition_threshold_per_type.py`.
  5. Линтер `lint_magic_numbers.py` расширен для вербализации.
- **Зависимости:** ENIGMA-ARCH-021 (ТЗ-А2).

---

#### ENIGMA-ARCH-052: Working memory фиксированный размер

- **Категория:** Memory / Adaptive sizing
- **Severity:** P1
- **Статус верификации:** ✅ Подтверждено (`memory_manager.py` строка 38 — `WORKING_MEMORY_SIZE: int = 20` для всех NPC)
- **Описание:** `WORKING_MEMORY_SIZE = 20` hardcoded для всех NPC. Нет adaptive sizing на основе intelligence trait или memory capacity. Глупый NPC и гений имеют одинаковую кратковременную память.
- **Локализация:** `backend/app/services/memory/memory_manager.py`, строка 38:
  ```python
  class MemoryManager:
      WORKING_MEMORY_SIZE: int = 20
  ```
- **Нарушенный контракт:** §4.27 (Adaptive sizing); индивидуализация NPC.
- **Definition of Done:**
  1. `WORKING_MEMORY_SIZE` удалён как класс-константа; размер working memory определяется per-NPC через `NPCProfile.intelligence` и `NPCProfile.memory_capacity`.
  2. Введена формула: `working_memory_size = base_size * (0.5 + intelligence * 0.5)` (диапазон ~10–30).
  3. При смене размера existing memories сохраняются (truncate от least-important).
  4. Тесты: `test_working_memory_adaptive_genius.py`, `test_working_memory_adaptive_simple.py`, `test_working_memory_resize.py`.
  5. Метрика `working_memory_size_distribution` экспортируется для аудита.
- **Зависимости:** ENIGMA-ARCH-021 (ТЗ-А2), ENIGMA-ARCH-060.

---

#### ENIGMA-ARCH-053: Recall не имеет semantic relevance scoring

- **Категория:** Memory / Recall
- **Severity:** P1
- **Статус верификации:** ✅ Подтверждено (`memory_manager.py` строки 470–530 — `recall()` сортирует по importance / accessibility / target_npc_id, нет semantic relevance к текущему контексту)
- **Описание:** Метод `recall()` возвращает воспоминания отсортированные по importance или accessibility, но не вычисляет semantic relevance к текущему контексту/запросу. NPC может вспомнить важное, но нерелевантное событие.
- **Локализация:** `backend/app/services/memory/memory_manager.py`, строки 470–530:
  ```python
  def recall(self, narrative_cache, *, trigger_tags=None, target_npc_id=None, limit=5):
      """
      Три режима:
      1. Триггерный: тег совпал → сортировка по importance.
      2. По целевому NPC: target_npc_id совпал с target_id → сортировка по importance.
      3. Случайный: accessibility > 0.2 → сортировка по importance × accessibility.
      """
      ...
      triggered.sort(key=lambda m: m.importance, reverse=True)
      ...
      accessible.sort(key=lambda m: m.importance * m.accessibility, reverse=True)
  ```
- **Нарушенный контракт:** Правдоподобие памяти; контекстуальность.
- **Definition of Done:**
  1. Введён `SemanticRelevanceScorer` — компонент, вычисляющий relevance между memory и текущим контекстом (intent, target, location, recent events).
  2. Relevance учитывает: tag overlap, entity overlap (actor/target), temporal proximity, emotional valence match.
  3. `recall()` добавляет режим `semantic`: сортировка по `importance × accessibility × relevance`.
  4. Существующие режимы (triggered, target_npc_id, random) сохраняются для backward compatibility.
  5. Тесты: `test_recall_semantic_relevance.py`, `test_recall_context_match.py`, `test_recall_irrelevant_filtered.py`.
- **Зависимости:** ENIGMA-ARCH-052, ENIGMA-ARCH-057.

---

#### ENIGMA-ARCH-054: Node scoring weights hardcoded

- **Категория:** Calibration / Spatial
- **Severity:** P1
- **Статус верификации:** ✅ Подтверждено (`spatial_service.py` строки 464–512 — `5.0` для tag match, `4.0` для risk, `15.0` для reservation, `3.0`/`4.0` в `_safety_penalty`)
- **Описание:** В `_compute_score()` веса `5.0` для tag match, `4.0` для risk, `15.0` для reservation — magic numbers без mechanism для tuning или A/B testing.
- **Локализация:** `backend/app/services/spatial/spatial_service.py`, строки 464–512:
  ```python
  def _compute_score(self, node, origin_xy, filters, urgency, requesting_npc_id):
      ...
      if filters:
          match_count = sum(1 for t in filters if t in node.tags)
          score += match_count * 5.0  # ← MAGIC
      ...
      holder = self._overlay.reserved_nodes.get(node.node_id)
      if holder is not None and holder != requesting_npc_id:
          if urgency == Urgency.URGENT:
              score -= 3.0  # ← MAGIC
          else:
              score -= 15.0  # ← MAGIC
      crowd = self._overlay.crowd_density.get(node.node_id, 0.0)
      score -= crowd * 4.0  # ← MAGIC
      ...
  def _safety_penalty(self, node, urgency):
      risk = self._overlay.risk_zones.get(node.node_id, 0.0)
      light = self._overlay.light_levels.get(node.node_id, 0.8)
      base_penalty = -risk * 4.0 - (1.0 - light) * 2.0  # ← MAGIC
      ...
  ```
- **Нарушенный контракт:** §4.9 (No magic numbers — из ТЗ-А2).
- **Definition of Done:**
  1. Все веса вынесены в `CalibrationProfile` (см. ENIGMA-ARCH-021 ТЗ-А2) как `NodeScoringProfile`.
  2. Введены именованные константы: `TAG_MATCH_WEIGHT`, `RISK_PENALTY`, `RESERVATION_PENALTY_NORMAL`, `RESERVATION_PENALTY_URGENT`, `CROWD_PENALTY`, `LIGHT_PENALTY`.
  3. ADR с обоснованием выбора весов (почему tag match = 5.0, а не 10.0).
  4. Тесты: `test_node_scoring_weights.py`, `test_node_scoring_a_b.py`.
  5. Линтер `lint_magic_numbers.py` расширен для spatial_service.
- **Зависимости:** ENIGMA-ARCH-021 (ТЗ-А2), ENIGMA-ARCH-046.

---

#### ENIGMA-ARCH-056: Gender inflection через pymorphy3 имеет incomplete coverage

- **Категория:** Verbalization / Localization
- **Severity:** P1
- **Статус верификации:** ✅ Подтверждено (`state_interpreter.py` строки 103–195 — `pymorphy3.MorphAnalyzer`, `_SHORT_FORM_FEMALE` словарь, silent failure в `_inflect_to_feminine`)
- **Описание:** `_SHORT_FORM_FEMALE` словарь содержит исключения для pymorphy3, но покрытие incomplete. Если добавить новое condition или emotion, нужно вручную добавлять feminine form.
- **Локализация:** `backend/app/services/verbalization/state_interpreter.py`, строки 103–195:
  ```python
  import pymorphy3
  _morph = pymorphy3.MorphAnalyzer()
  ...
  _SHORT_FORM_FEMALE: dict[str, str] = {
      "напуган": "напугана",
      ...
  }
  ...
  def _inflect_to_feminine(word: str) -> str:
      if word in _SHORT_FORM_FEMALE:
          return _SHORT_FORM_FEMALE[word]
      parsed = _morph.parse(word)
      ...
      try:
          inflected = variant.inflect({"femn", "nomn"})
          ...
      except Exception as e:
          logger.warning(f"[B5-FIX] silent failure suppressed: {e}")  # ← SILENT FAILURE
  ```
- **Нарушенный контракт:** §4.5 (No silent failures — из ТЗ-А1); полнота локализации.
- **Definition of Done:**
  1. `_SHORT_FORM_FEMALE` вынесен в конфигурационный файл `config/verbalization/short_forms_female.json` с поддержкой hot-reload.
  2. Silent failure в `_inflect_to_feminine` заменён на `InflectionFailureEvent` в `EventBus` с указанием слова и причины.
  3. При добавлении нового condition/emotion CI проверяет наличие feminine form (lint rule).
  4. Введён fallback на male form + эвент (не silent suppression).
  5. Тесты: `test_gender_inflection_coverage.py` (все conditions имеют feminine), `test_gender_inflection_failure_logging.py`.
  6. Метрика `inflection_failure_events` экспортируется.
- **Зависимости:** ENIGMA-ARCH-051, ENIGMA-ARCH-017 (ТЗ-А1).

---

#### ENIGMA-ARCH-057: Event semantic tagging изолирован от downstream

- **Категория:** Events / Semantic
- **Severity:** P1
- **Статус верификации:** ✅ Подтверждено (`event_semantic_tagger.py` — `EventSemanticTagger` добавляет теги, но в `InterpretationEngine` / `DecisionHub` теги не используются напрямую)
- **Описание:** `EventSemanticTagger` добавляет semantic tags (threat/social/anomaly), но эти tags не влияют на DecisionHub или InterpretationEngine. Это «decorator» без функционального эффекта.
- **Локализация:** `backend/app/services/memory/event_semantic_tagger.py` — `EventSemanticTagger.tag()` возвращает `Tuple[str, ...]` тегов; downstream-компоненты (`InterpretationEngine`, `DecisionHub`) не читают эти теги.
- **Нарушенный контракт:** §4.25 (Semantic tags must flow downstream); каузальная замкнутость (теги не влияют на решения).
- **Definition of Done:**
  1. `InterpretationEngine._compute_bias()` расширен: читает semantic tags события и применяет модификаторы (например, `social:aggression` → буст `threat_bias`).
  2. `DecisionHub` имеет доступ к semantic tags через `EventContext`; решения учитывают теги (например, `social:extreme_harm` → приоритет `flee`/`alert_guards`).
  3. `BeliefTransitionEngine` использует теги для attribution: `social:player_actor` → убеждение о игроке, `social:npc_actor` → убеждение о NPC.
  4. Тесты: `test_semantic_tags_interpretation.py`, `test_semantic_tags_decision_hub.py`, `test_semantic_tags_belief_attribution.py`.
  5. Метрика `semantic_tags_unused` (теги, не потреблённые downstream) = 0.
- **Зависимости:** ENIGMA-ARCH-036 (ТЗ-А2), ENIGMA-ARCH-003 (ТЗ-А1), ENIGMA-ARCH-004 (ТЗ-А1).

### 5.16. P2 — Сильные стороны архитектуры (сохранить при рефакторинге)

Аудит зафиксировал следующие сильные стороны, которые не требуют исправления, но должны быть сохранены:

1. **`StateInterpreter` как единственный мост между числами и словами** — LLM никогда не видит сырые цифры, только human-readable descriptions. Правильный abstraction boundary; рефакторинг ENIGMA-ARCH-051/056 не должен нарушать этот принцип.
2. **Layered memory architecture** — Working Memory → Narrative Cache → SQLite с чёткими boundaries и single responsibility. Проблемы 043/045/058/059 — инфраструктурные, не архитектурные.
3. **Secret discovery system** — Механика «трещин» в секретах под давлением (CRACK/PARTIAL/BROKEN) создаёт interesting narrative opportunities. Проблема 044 — лишь в прозрачности формулы, не в механике.
4. **`SpatialService` three-layer model** — Geometry → Topology → Semantics с чётким separation of concerns. Проблемы 046–050 — в implementation details, не в модели.
5. **Overlay system** — Динамические модификаторы (crowd density, risk zones, light levels) поверх статического графа. Правильный подход; проблема 046 — лишь в грубой инвалидации.
6. **Affordance objects** — Объекты мира имеют semantic meaning (кровать affordance «sleep»), а не просто collision boxes. Проблема 049 — в отсутствии accessibility check, не в концепции.
7. **Causal Purity decay** — Decay rate определяется важностью события, а не arbitrary emotion tags. Чем важнее событие, тем медленнее забывается. Правильный подход; проблема 039 (ТЗ-А2) — расширение, не замена.
8. **Boundary nodes для cross-location transitions** — Explicit mechanism для NPC перемещаться между локациями через defined exit points. Проблема 050 — в статичности, не в концепции.

---

## 6. Группировка по архитектурным доменам (продолжение)

| Домен | Проблемы | Ключевой контракт |
|---|---|---|
| EventBus / Concurrency | 041, 042, 055 | No blocking handlers; DLQ observable; handler ordering |
| Memory / Type safety | 043, 052, 058 | Type-safe keys; adaptive sizing; compression verification |
| Memory / Persistence | 045, 059 | Crash-safe consolidation; complete migration |
| Memory / Recall & Patterns | 053, 060 | Semantic relevance; cooldown for detection |
| Memory / Discovery | 044 | Transparent formula with documented edge cases |
| Spatial / Performance | 046, 048 | Cache granularity; spatial indexing |
| Spatial / Safety | 047, 050 | Bounded algorithms; dynamic topology |
| Spatial / Affordances | 049 | Accessibility-aware resolution |
| Calibration | 051, 054 | No magic numbers in verbalization and spatial |
| Verbalization / Localization | 056 | Complete gender inflection coverage |
| Events / Semantic | 057 | Tags flow downstream |

---

## 7. Этапы реализации (фазы 15–20, продолжение ТЗ-А1/А2)

### Фаза 15 — EventBus и DLQ (P0, 2 недели)

**Цель:** Устранить блокировку pipeline медленными handlers и сделать DLQ observable.

**Проблемы:** ENIGMA-ARCH-041, 042, 055.

**Ключевые работы:**
- `HandlerTimeout` + `HandlerPriority` + `HandlerSpec` с dependencies.
- Async-пул для долгих handlers.
- `DlqReprocessor` + `DlqAlerting`.
- Debug-эндпоинт `GET /debug/dlq`.

**Критерии готовности фазы:**
- Метрика `handler_stall_seconds` < 1 сек.
- Метрика `dlq_size` observable; `dlq_reprocess_success_rate` > 0.
- Тесты на timeout, priority, dependencies, cycle detection — зелёные.

### Фаза 16 — Memory persistence и type safety (P0, 3 недели)

**Цель:** Устранить хрупкие ключи STM, обеспечить crash-safe consolidation и завершить миграцию identity_cache.

**Проблемы:** ENIGMA-ARCH-043, 045, 058, 059.

**Ключевые работы:**
- `DialogueSessionKey` (frozen dataclass).
- `IncrementalConsolidator` с WAL.
- `CompressionVerifier` + `DecompressionRecovery`.
- Формальный `MemoryStore` Protocol; удаление `hasattr` checks.

**Критерии готовности фазы:**
- Метрика `consolidation_loss_events` = 0.
- Метрика `identity_cache_loss_events` = 0.
- Тесты crash recovery, compression verification — зелёные.

### Фаза 17 — SpatialService performance и safety (P0, 3 недели)

**Цель:** Устранить грубую инвалидацию кэша, бесконечные циклы в A*, O(n) zone detection и статичность boundary.

**Проблемы:** ENIGMA-ARCH-046, 047, 048, 049, 050.

**Ключевые работы:**
- `PathCacheKey` с версией `blocked_nodes_hash`.
- `MAX_ASTAR_ITERATIONS` + детектор циклов.
- R-tree индекс для zone detection.
- `AffordanceAccessibilityCache`.
- `BoundaryMapMutator` с динамическими операциями.

**Критерии готовности фазы:**
- Метрика `path_cache_hit_rate` ≥ 60%.
- Метрика `zone_detection_avg_ms` ≤ 0.1 мс.
- Метрика `astar_timeout_events` = 0 в типичной сессии.
- Тесты на bounded A*, dynamic boundary, accessibility — зелёные.

### Фаза 18 — Memory recall и resonance (P0, 2 недели)

**Цель:** Ввести semantic relevance scoring и cooldown для resonance detection.

**Проблемы:** ENIGMA-ARCH-053, 060, 052.

**Ключевые работы:**
- `SemanticRelevanceScorer`.
- `ResonanceCooldown` + `ResonanceDriftGuard`.
- Adaptive `WORKING_MEMORY_SIZE` per NPC.

**Критерии готовности фазы:**
- Метрика `resonance_triggers_per_tick` в норме.
- Метрика `working_memory_size_distribution` показывает разнообразие.
- Тесты на semantic recall, cooldown, drift guard — зелёные.

### Фаза 19 — Калибровка вербализации и spatial (P1, 2 недели)

**Цель:** Вынести все магические числа из `state_interpreter.py` и `spatial_service.py` в `CalibrationProfile`.

**Проблемы:** ENIGMA-ARCH-051, 054, 056.

**Ключевые работы:**
- `ConditionProfile` с per-type порогами.
- `NodeScoringProfile` с именованными весами.
- `_SHORT_FORM_FEMALE` → `config/verbalization/short_forms_female.json`.
- Замена silent failures на `InflectionFailureEvent`.

**Критерии готовности фазы:**
- Линтер `lint_magic_numbers.py` зелёный для `state_interpreter.py` и `spatial_service.py`.
- ADR с обоснованием весов и порогов.

### Фаза 20 — Semantic tags flow downstream (P1, 2 недели)

**Цель:** Обеспечить, что semantic tags из `EventSemanticTagger` влияют на `InterpretationEngine`, `DecisionHub` и `BeliefTransitionEngine`.

**Проблемы:** ENIGMA-ARCH-057, 044.

**Ключевые работы:**
- Расширение `InterpretationEngine._compute_bias()` semantic tags.
- `DecisionHub` доступ к semantic tags через `EventContext`.
- `BeliefTransitionEngine` attribution по тегам.
- Документация формулы discovery (проблема 044).

**Критерии готовности фазы:**
- Метрика `semantic_tags_unused` = 0.
- ADR по формуле discovery с граничными случаями.

---

## 8. Приоритизация (сводная, продолжение ТЗ-А1/А2)

| Приоритет | ID проблем | Обоснование |
|---|---|---|
| **P0** | 041, 042, 043, 044, 045, 046, 047, 048, 049, 050, 055, 058, 059, 060 | Нарушают фундаментальные принципы (no blocking handlers, type-safe keys, crash-safe persistence, bounded algorithms, dynamic topology); создают «чёрные дыры» и бесконечные циклы; блокируют production readiness |
| **P1** | 051, 052, 053, 054, 056, 057 | Снижают правдоподобие, тестируемость, локализацию; не блокируют разработку, но повышают риск регрессий и затрудняют балансировку |

---

## 9. Сквозные работы (дополнение к ТЗ-А1/А2)

К сквозным работам ТЗ-А1 §9 и ТЗ-А2 §9 добавляются:

9. **Единый `CalibrationProfile`.** Все коэффициенты из проблем 051, 054, 056 должны жить в одном профиле с проблемами 021/024/029/033 (ТЗ-А2).
10. **Метрики observability.** Для каждой проблемы 041, 042, 046, 047, 048, 049, 050, 056, 057, 058, 059, 060 вводится метрика в CI-отчёт.
11. **Расширение `lint_magic_numbers.py`.** Должен покрывать `state_interpreter.py`, `spatial_service.py`, `event_bus.py`, `memory_manager.py`.
12. **Пространственные индексы.** Введён общий `SpatialIndex` Protocol для R-tree/quadtree реализаций; используется в `get_zone_id`, `resolve_affordance`, `find_path` (для nearest-node queries).
13. **Type-safe keys across system.** Помимо `DialogueSessionKey` (043), аудит всех строковых ключей в `memory_manager.py`, `tick_orchestrator.py`, `game_loop` — замена на frozen dataclasses.

---

## 10. Контракты и ограничения (дополнение к ТЗ-А1/А2)

К ограничениям ТЗ-А1 §10 и ТЗ-А2 §10 добавляются:

9. **Совместимость с ADR-O-330 (Affordance).** Любые изменения в `resolve_affordance` не должны нарушать ADR-O-330 без явного ADR-ревизии.
10. **Совместимость с ADR-O-324 (Spatial Walls/Obstacles).** Изменения в `boundary_map` и `find_path` не должны нарушать ADR-O-324.
11. **Сохранение Causal Purity decay.** Любые изменения в memory decay (058, 060) не должны нарушать принцип «decay rate = f(importance)».
12. **Не нарушать детерминизм.** R-tree индекс должен быть детерминированным (sorted iteration); async handlers в EventBus не должны влиять на `TickMutation`.
13. **Сохранение `StateInterpreter` как abstraction boundary.** Рефакторинг 051/056 не должен позволять LLM видеть сырые числа.

---

## 11. Критерии готовности (глобальные, дополнение к ТЗ-А1/А2)

К критериям ТЗ-А1 §11 и ТЗ-А2 §11 добавляются:

14. Линтер `lint_magic_numbers.py` не находит ни одного числового литерала вне whitelist в `state_interpreter.py`, `spatial_service.py`, `event_bus.py`, `memory_manager.py`.
15. `EventBus.publish()` не блокирует pipeline дольше `handler_timeout_sec`; метрика `handler_stall_seconds` < 1 сек.
16. DLQ имеет `DlqReprocessor`; метрика `dlq_reprocess_success_rate` > 0.
17. Все строковые ключи в `memory_manager.py` заменены на frozen dataclasses; `hasattr` checks удалены.
18. `find_path()` имеет `MAX_ASTAR_ITERATIONS`; метрика `astar_timeout_events` = 0 в типичной сессии.
19. `get_zone_id()` использует пространственный индекс; метрика `zone_detection_avg_ms` ≤ 0.1 мс.
20. `boundary_map` поддерживает динамические изменения; метрика `boundary_changes_per_session` > 0 (функциональность активна).
21. Semantic tags из `EventSemanticTagger` потребляются downstream; метрика `semantic_tags_unused` = 0.

---

## 12. Риски и смягчения (дополнение к ТЗ-А1/А2)

| Риск | Вероятность | Влияние | Смягчение |
|---|---|---|---|
| Async handlers в EventBus нарушат детерминизм | Высокая | Высокое | Async только для non-state-mutating handlers (logging, narrative); state mutations остаются sync |
| R-tree индекс введёт недетерминированный порядок итерации | Средняя | Высокое | R-tree queries возвращают sorted results; тест на determinism (ENIGMA-ARCH-015 ТЗ-А1) расширен |
| Динамическое обновление `boundary_map` создаст race conditions | Средняя | Высокое | Все мутации через `BoundaryMapMutator` с lock; `BoundaryChangedEvent` синхронный |
| `CompressionVerifier` забракует существующие сжатые памяти | Высокая | Среднее | Migration script: старые сжатые памяти помечаются `unverified` и не блокируют систему |
| `ResonanceCooldown` подавит legitimate personality drift | Средняя | Среднее | Cooldown только для повторных pattern'ов того же типа; новые pattern'ы не подавляются |
| Adaptive `WORKING_MEMORY_SIZE` сделает recall недетерминированным | Низкая | Среднее | Размер зависит только от `NPCProfile` (immutable), не от runtime-состояния |
| Удаление `_SHORT_FORM_FEMALE` silent failure сломает вербализацию | Средняя | Высокое | Fallback на male form + эвент; CI проверяет покрытие всех conditions |
| `DlqReprocessor` создаст duplicate events | Средняя | Высокое | Каждое событие имеет `event_id`; duplicate detection через `event_log` |

---

## 13. Метрики и верификация (дополнение к ТЗ-А1/А2)

| Метрика | Целевое значение | Источник данных |
|---|---|---|
| `handler_stall_seconds` (макс. за сессию) | < 1 сек | `event_bus.py` |
| `dlq_size` (макс. за сессию) | < 10 | `event_bus.py` |
| `dlq_reprocess_success_rate` | > 0.5 | `dlq_reprocessor.py` |
| `path_cache_hit_rate` | ≥ 60% | `spatial_service.py` |
| `astar_timeout_events` за 100 тиков | 0 | `spatial_service.py` |
| `zone_detection_avg_ms` | ≤ 0.1 мс | `spatial_service.py` |
| `affordance_inaccessible_events` за тик | < 5% от запросов | `spatial_service.py` |
| `boundary_changes_per_session` | > 0 (функциональность активна) | `boundary_map_mutator.py` |
| `consolidation_loss_events` | 0 | `memory_manager.py` |
| `identity_cache_loss_events` | 0 | `memory_manager.py` |
| `compression_mismatch_events` | 0 | `compression_verifier.py` |
| `resonance_triggers_per_tick` (макс.) | < 5% от NPC count | `resonance_engine.py` |
| `working_memory_size_distribution` | diverse (не все 20) | `memory_manager.py` |
| `inflection_failure_events` | < 1% от вербализаций | `state_interpreter.py` |
| `semantic_tags_unused` | 0 | `event_semantic_tagger.py` + downstream |

---

## 14. Приложения

### Приложение А. Сводная таблица верификации проблем 41–60

| ID | Файл | Строки | Статус верификации |
|---|---|---|---|
| 041 | `event_bus.py` | 94–153 | ✅ Подтверждено (sync for loop) |
| 042 | `event_bus.py` | 52–53, 137–140 | ✅ Подтверждено (DLQ без reprocessing) |
| 043 | `memory_manager.py` | 76–83, 100–145 | ✅ Подтверждено (3 fix-комментария) |
| 044 | `memory_manager.py` | 395–456 | ✅ Подтверждено (`_PRESSURE_STRENGTH`, `importance * 0.8`) |
| 045 | `memory_manager.py` | 100–130 | ✅ Подтверждено (consolidate перед pop, без WAL) |
| 046 | `spatial_service.py` | 214–220 | ✅ Подтверждено (`_path_cache.clear()`) |
| 047 | `spatial_service.py` | 565–600 | ✅ Подтверждено (`while open_set:` без лимита) |
| 048 | `spatial_service.py` | 246–270 | ✅ Подтверждено (ray casting O(n) per polygon) |
| 049 | `spatial_service.py` | 331–395 | ✅ Подтверждено (нет path existence check) |
| 050 | `spatial_service.py` | 76–133 | ✅ Подтверждено (`boundary_map` статичен) |
| 051 | `state_interpreter.py` | 80–83, 321–352 | ✅ Подтверждено (`severity > 0.3`) |
| 052 | `memory_manager.py` | 38 | ✅ Подтверждено (`WORKING_MEMORY_SIZE = 20`) |
| 053 | `memory_manager.py` | 470–530 | ✅ Подтверждено (sort by importance/accessibility) |
| 054 | `spatial_service.py` | 464–512 | ✅ Подтверждено (`5.0`, `4.0`, `15.0`, `3.0`) |
| 055 | `event_bus.py` | весь файл | ✅ Подтверждено (insertion order, no deps) |
| 056 | `state_interpreter.py` | 103–195 | ✅ Подтверждено (pymorphy3 + silent failure) |
| 057 | `event_semantic_tagger.py` | весь файл | ✅ Подтверждено (tags не используются downstream) |
| 058 | `promotion_engine.py` | весь файл | ✅ Подтверждено (compress без verification) |
| 059 | `memory_manager.py` | 52–57 | ✅ Подтверждено (дословный «legacy gap») |
| 060 | `memory_manager.py`, `resonance_engine.py` | 762+, весь | ✅ Подтверждено (detect каждый тик без cooldown) |

### Приложение Б. Перекрёстные ссылки на ТЗ-А1 и ТЗ-А2

| Проблема ТЗ-А3 | Связанная проблема | Тип связи |
|---|---|---|
| 041 (EventBus blocking) | 022 (ТЗ-А2: ThreadPool max_workers=1) | Параллель (оба — concurrency bottleneck) |
| 042 (DLQ black hole) | 017 (ТЗ-А1: Silent failures), 038 (ТЗ-А2: Reconstruction fallbacks) | Параллель |
| 043 (STM keys) | 030 (ТЗ-А2: STM decay) | Расширение |
| 044 (Discovery formula) | 021 (ТЗ-А2: Magic numbers), 035 (ТЗ-А2: Belief validation) | Подкатегория |
| 045 (Crash-safe consolidation) | 016 (ТЗ-А1: Persistence), 059 | Параллель |
| 046 (Cache invalidation) | 047, 048 | Связанные (spatial perf) |
| 047 (A* infinite loop) | — | Новая |
| 048 (Zone detection O(n)) | 046 | Связанные (spatial perf) |
| 049 (Affordance accessibility) | 007 (ТЗ-А1: Proactive movement) | Расширение |
| 050 (Static boundary) | 008 (ТЗ-А1: Race conditions transfers) | Параллель (оба — topology issues) |
| 051 (Condition thresholds) | 021 (ТЗ-А2: Calibration) | Подкатегория |
| 052 (Working memory size) | 021 (ТЗ-А2: Calibration) | Подкатегория |
| 053 (Recall semantic) | 035 (ТЗ-А2: Belief validation) | Параллель (оба — memory correctness) |
| 054 (Node scoring weights) | 021 (ТЗ-А2: Calibration) | Подкатегория |
| 055 (Handler order) | 041 | Связанные (EventBus) |
| 056 (Gender inflection) | 017 (ТЗ-А1: Silent failures), 051 | Параллель |
| 057 (Tags isolated) | 036 (ТЗ-А2: Observer context), 003/004 (ТЗ-А1) | Расширение |
| 058 (Compression verification) | 035 (ТЗ-А2: Belief validation), 045 | Параллель |
| 059 (Identity cache gap) | 016 (ТЗ-А1: Persistence) | Расширение |
| 060 (Resonance cooldown) | 039 (ТЗ-А2: Cooling down), 052 | Параллель |

### Приложение В. Источники

- Архив исходного кода: `Enigma-V.0.5.3.8.2_-.zip`
- ТЗ-А1: `/home/z/my-project/download/ТЗ_Architect_Enigma_V0.5.3.8.2.md`
- ТЗ-А2: `/home/z/my-project/download/ТЗ_Architect_Enigma_V0.5.3.8.2_Part2.md`
- Существующие ADR: `docs/audits/ADR-*_IMPACT.md` (особенно ADR-O-330, ADR-O-324, ADR-048, V8-DEC-11, V8-MEM-7, V8-DLG-13, BUG-DLG-007/008, BUG-DL-07)
- Архитектурный устав: `docs/АРХИТЕКТУРНЫЙ_УСТАВ_ENIGMA.md`
- Каузальный контракт: `docs/00_CAUSAL_CONTRACT_v2.0.md`
