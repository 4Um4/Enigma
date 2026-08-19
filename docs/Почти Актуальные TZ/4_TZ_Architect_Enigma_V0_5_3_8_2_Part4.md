# Техническое задание для архитектора (ТЗ-А4)

**Проект:** Enigma — каузальное ядро симуляции NPC  
**Версия проекта:** V0.5.3.8.2  
**Версия документа:** 1.0 (продолжение ТЗ-А1, ТЗ-А2, ТЗ-А3 от 2026-08-18)  
**Дата составления:** 2026-08-18  
**Адресат:** Архитектор систем симуляции / tech-lead backend  
**Автор верификации:** AI-аудит (на основе исходного кода `backend/app/services/...`)  
**Статус верификации:** все 20 проблем (№61–80) сверены с исходным кодом архива `Enigma-V.0.5.3.8.2_-.zip`

---

## 1. Назначение документа

Настоящий документ является четвёртой частью аудиторской серии (ТЗ-А1 → ТЗ-А2 → ТЗ-А3 → ТЗ-А4) и описывает 20 дополнительных архитектурных проблем (№61–80), выявленных при глубоком аудите трёх слоёв: `MovementEngine` (физическая симуляция и execution), `PerceptionFilter` (формирование восприятия NPC) и `DialogueExecutor` (LLM-интеграция). Документ сохраняет структуру предыдущих частей: фиксированные архитектурные домены, приоритизация P0/P1/P2, формальные Definition of Done для каждой проблемы и этапы реализации.

Документ самостоятелен: проблемы 61–80 не дублируют проблемы 1–60, а раскрывают архитектурный долг в execution-слое (movement, perception, LLM dialogue). При чтении вместе с ТЗ-А1/А2/А3 даёт полную картину из 80 верифицированных проблем.

## 2. Контекст и обоснование

ТЗ-А1 зафиксировало фундаментальные нарушения эпистемической изоляции и каузальной замкнутости. ТЗ-А2 раскрыло проблемы калибровки, concurrency и формальных спецификаций. ТЗ-А3 выявило инфраструктурный долг в EventBus, Memory и SpatialService. Расширенный аудит трёх execution-слоёв выявил четвёртый класс проблем: каскады fallback'ов без circuit breakers в cross-location routing, string-based классификация вместо semantic tagging, hardcoded thresholds в физической симуляции и восприятии, отсутствие timeout в traversal planning, отсутствие relevance filtering при LLM prompt assembly, отсутствие confidence scoring в валидации LLM-ответов и verification в confession parsing.

Особенность этого блока: проблемы концентрируются в «последней миле» между ядром симуляции и внешним миром (LLM, физика, восприятие). Даже идеально изолированное эпистемически ядро (ТЗ-А1) с надёжной инфраструктурой (ТЗ-А3) будет выдавать некачественный результат, если execution-слой хрупок: NPC будет «смотреть сквозь стены» (068), видеть события за спиной (069), получать нерелевантные beliefs в prompt (077), и признания будут записываться по keyword overlap без проверки сарказма (080).

Аудит также зафиксировал ряд сильных сторон execution-слоя (см. §5.17), которые должны быть сохранены при рефакторинге: Spatial Intent Gate, LOD separation, Traversal planning с честной физикой, Perception membrane, Hard Contract для STM, ResponseValidator.

Синтез трёх recurring patterns (см. §6.2): (1) string-based classification вместо semantic tagging, (2) hardcoded thresholds без parameterization, (3) fallback cascades без circuit breakers. Эти паттерны — системные; их устранение требует не точечных правок, а архитектурных решений.

## 3. Глоссарий (дополнение к ТЗ-А1/А2/А3)

| Термин | Определение |
|---|---|
| `MovementEngine` | Слой 2 execution: физическое перемещение NPC, cross-location routing |
| `process_intents` | Главный метод `MovementEngine`: обрабатывает movement intents |
| `CROSS_LOC_INTERCEPT` | Блок перехвата cross-location intents в `MovementEngine` |
| `CROSS_LOC_MATERIALIZE` | Блок материализации NPC в новой локации |
| `SimulationIntegrityError` | Критическое исключение: нарушение инварианта симуляции (fail-loud) |
| `SpatialIntentGate` | Единая точка арбитража для всех movement intents |
| `LocalTraversalPlanner` | Компилятор последовательности переходов (WALK, JUMP) с честной физикой |
| `TraversalProposal` | DTO: `path_waypoints`, `segment_modes`, `duration_ticks` |
| `_fallback_to_astar` | Fallback на A* при REJECTED от `LocalTraversalPlanner` |
| `PerceptionFilter` | Фильтр восприятия: какие NPC видят/слышат событие |
| `_can_see` / `_can_hear` | Базовые проверки восприятия в `PerceptionFilter` |
| `calculate_clarity` | Вычисление clarity события для NPC: distance, light, stress |
| `_npc_is_conscious` | Проверка, что NPC в сознании (не dead/unconscious/sleeping) |
| `_LIGHT_LEVELS` | Словарь: dark/dim/torchlit/natural/bright → int |
| `_MIN_LIGHT_FOR_SIGHT` | Минимальный уровень света для зрения (hardcoded = «dim») |
| `_TEMPLATES` | Словарь event_type → текстовое описание для perception context |
| `DialogueExecutor` | Компонент выполнения canonical dialogue через LLM |
| `NpcContract` | DTO контракта LLM-вызова: `system_prompt`, `user_prompt`, `max_sentences` |
| `requires_dialogue_context` | Функция: требует ли intent_type STM-контекст |
| `ResponseValidator` | Валидатор LLM-ответа: отсечение 4-й стены, non-Russian, forbidden actions |
| `is_fallback` | Boolean-флаг валидации: True = LLM-ответ отвергнут, используется fallback |
| `ConfessionParser` | Парсер признаний NPC: keyword overlap + PropositionMatcher |
| `PropositionMatcher` | Семантический матч пропозиций (не keyword overlap) |
| `confession_keywords` | Tuple ключевых слов для парсинга признаний (per secret) |
| LOD0 / LOD1 | Level of Detail: LOD0 — micro jitter (collision avoidance), LOD1 — macro A* |
| Spatial Intent Gate | Единая точка арбитража movement intents с приоритизацией |

---

## 4. Архитектурные принципы (дополнение к ТЗ-А1/А2/А3)

К принципам из ТЗ-А1 §4, ТЗ-А2 §4 и ТЗ-А3 §4 добавляются следующие, актуальные для блока 61–80:

28. **Single cross-location contract** — cross-location переходы обязаны иметь единый контракт; каскады fallback'ов (intercept → boundary → materialize → entry_hint → error) запрещены.
29. **Semantic classification over string matching** — классификация intents, events, states обязана идти через typed enums / semantic tags, а не через поиск подстрок в строковых полях.
30. **Bounded planners** — любой planner (traversal, pathfinding) обязан иметь timeout и максимальное число итераций; зависание недопустимо.
31. **Physics-aware movement** — движение NPC (heading, collision avoidance) обязано учитывать физические препятствия; «смотрение сквозь стену» запрещено.
32. **Validation layer for proposals** — любой DTO-предложение (TraversalProposal, MovementPlan) обязано проходить runtime validation перед применением.
33. **Circuit breakers for fallback cascades** — любой каскад fallback'ов обязан иметь circuit breaker: если все fallback'ы провалились, система fail-loud эмитит alert, не silent REJECTED.
34. **Facing-aware perception** — восприятие NPC обязано учитывать facing direction; NPC не «видит» события за спиной (если не имеет awareness trait).
35. **Trait-aware perception** — clarity расчёт обязан учитывать индивидуальные traits NPC (eyesight, hearing); единая формула для всех NPC запрещена.
36. **Dynamic perception templates** — текстовые шаблоны восприятия обязаны поддерживать кастомизацию per NPC personality, а не быть hardcoded.
37. **Personality-injected LLM prompts** — system prompt LLM обязан включать personality traits, voice profile, backstory NPC; единый prompt для всех NPC запрещён.
38. **Graceful STM degradation** — при отсутствии STM система обязана поддерживать partial context, а не демотировать intent к «approach».
39. **Relevance filtering for prompt injection** — beliefs, memories, context, инжектируемые в LLM prompt, обязаны проходить relevance filtering по текущему topic.
40. **Confidence-graded validation** — валидация LLM-ответов обязана возвращать confidence score, а не boolean; partial validity поддерживается.
41. **Adaptive LLM params** — `max_tokens`, temperature, top_p обязаны адаптироваться к intent_type и dialogue phase, а не быть hardcoded.
42. **Verified LLM side-effects** — любые side-effects LLM (confession, promise, threat) обязаны проходить verification перед записью в state.

---

## 5. Каталог архитектурных проблем (продолжение)

Каждая проблема описана по шаблону из ТЗ-А1: ID → Категория → Severity → Статус верификации → Описание → Локализация → Нарушенный контракт → Definition of Done → Зависимости.

### 5.17. P0 — MovementEngine: cross-location и fallback cascades

---

#### ENIGMA-ARCH-061: Cross-location routing имеет 6+ fallback путей

- **Категория:** Movement / Cross-location
- **Severity:** P0
- **Статус верификации:** ✅ Подтверждено (`movement_engine.py` строки 259–373 — каскад `CROSS_LOC_INTERCEPT` → boundary → `CROSS_LOC_MATERIALIZE` → `entry_node_hint` → `SimulationIntegrityError`)
- **Описание:** В `process_intents()` логика перехода между локациями содержит: `CROSS_LOC_INTERCEPT` → `boundary_node` → `CROSS_LOC_MATERIALIZE`; поиск в смежных локациях через `adjacency`; `entry_node_hint` fallback; `SimulationIntegrityError` если целевой узел не найден. Это признак того, что cross-location переходы не имеют единого контракта. Каждый edge case добавляет новый bypass.
- **Локализация:** `backend/app/services/spatial/movement_engine.py`, строки 259–373:
  ```python
  # CROSS_LOC_INTERCEPT block
  boundary_node = current_svc.get_boundary_to_neighbor(target_loc)
  if boundary_node:
      if not target_loc:
          logger.error(...)
          continue
      _is_at_boundary = (_npc_pos_data.get("position", "") == boundary_node.node_id)
      if _is_at_boundary or _dist_to_boundary < 1.5:
          # CROSS_LOC_MATERIALIZE
          target_svc = self._resolve_spatial_service(target_loc, ...)
          if not target_svc:
              continue
          target_node_obj = target_svc.get_node(...)
          if not target_node_obj:
              # entry_node_hint fallback
              _b_info = current_svc.get_boundary_info(boundary_node.node_id) or {}
              _entry_hint = _b_info.get("entry_node_hint", "")
              if _entry_hint:
                  target_node_obj = ...
              if not target_node_obj:
                  # SimulationIntegrityError
                  raise SimulationIntegrityError(...)
  ```
- **Нарушенный контракт:** §4.28 (Single cross-location contract); §4.33 (Circuit breakers for fallback cascades).
- **Definition of Done:**
  1. Введён `CrossLocationContract` — единый DTO: `source_loc`, `target_loc`, `boundary_node`, `entry_node`, `materialization_strategy`.
  2. `CrossLocationRouter` — единственный компонент, реализующий переход; fallback'и инкапсулированы внутри с явной иерархией.
  3. Каждый fallback логируется с указанием, какой уровень каскада сработал.
  4. `SimulationIntegrityError` сохраняется как final circuit breaker (fail-loud).
  5. Тесты: `test_cross_loc_single_contract.py`, `test_cross_loc_fallback_trace.py`, `test_cross_loc_integrity_error.py`.
  6. Метрика `cross_loc_fallback_level_distribution` экспортируется.
- **Зависимости:** ENIGMA-ARCH-050 (ТЗ-А3), ENIGMA-ARCH-064, ENIGMA-ARCH-067.

---

#### ENIGMA-ARCH-062: Spatial Intent Gate приоритизация через string matching

- **Категория:** Movement / Classification
- **Severity:** P0
- **Статус верификации:** ✅ Подтверждено (`movement_engine.py` строки 148–157 — `"schedule" in _reason`, `"flee" in _reason or "combat" in _reason`)
- **Описание:** Spatial Intent Gate приоритизация через string matching: `_is_schedule = "schedule" in _reason`, `_is_reactive = "flee" in _reason or "combat" in _reason`. Приоритеты (Reactive > Schedule > Social) определяются через поиск подстрок в `reason`. Это хрупко: если reason изменится на «fleeing_from_threat», логика сломается.
- **Локализация:** `backend/app/services/spatial/movement_engine.py`, строки 148–157:
  ```python
  _reason = getattr(intent, "reason", "")
  _is_schedule = "schedule" in _reason
  _is_reactive = "flee" in _reason or "combat" in _reason or "reactive" in _reason
  ...
  _existing_is_schedule = "schedule" in _existing_reason
  _existing_is_reactive = "flee" in _existing_reason or "combat" in _existing_reason or "reactive" in _existing_reason
  ```
- **Нарушенный контракт:** §4.29 (Semantic classification over string matching).
- **Definition of Done:**
  1. Введён `IntentCategory` enum: `REACTIVE`, `SCHEDULE`, `SOCIAL`, `NEED`, `IDLE`.
  2. `MacroMovementGoal` имеет поле `category: IntentCategory` вместо (или в дополнение к) `reason: str`.
  3. Приоритизация идёт через `category`, не через string matching.
  4. Миграция: existing `reason` strings парсятся в `IntentCategory` через mapping table.
  5. Тесты: `test_intent_category_priority.py`, `test_intent_category_migration.py`.
  6. Линтер запрещает `"schedule" in reason`, `"flee" in reason` и т.д.
- **Зависимости:** ENIGMA-ARCH-061, ENIGMA-ARCH-071, ENIGMA-ARCH-073.

---

#### ENIGMA-ARCH-063: LocalTraversalPlanner не имеет timeout

- **Категория:** Movement / Safety
- **Severity:** P0
- **Статус верификации:** ✅ Подтверждено (`movement_engine.py` строка 642 `self._planner.compile_plan(query, geometry)` без timeout; `local_traversal_planner.py` метод `compile_plan` без лимита)
- **Описание:** `_compile_traversal_plan()` вызывает `self._planner.compile_plan()`, который может зависнуть на сложной геометрии. Нет механизма прерывания или timeout.
- **Локализация:** `backend/app/services/spatial/movement_engine.py`, строка 642:
  ```python
  plan: TraversalPlan = self._planner.compile_plan(query, geometry)
  ```
  `backend/app/services/spatial/local_traversal_planner.py`, метод `compile_plan` — циклы по obstacles/walls без лимита итераций.
- **Нарушенный контракт:** §4.30 (Bounded planners); §4.21 (Bounded algorithms — из ТЗ-А3).
- **Definition of Done:**
  1. Введён `MAX_TRAVERSAL_PLANNER_ITERATIONS` (настраиваемый).
  2. `compile_plan()` принимает `deadline_tick` или `max_iterations`; при превышении возвращает `TraversalPlan(possible=False, reason="PLANNER_TIMEOUT")`.
  3. Введён `PlannerTimeoutEvent` в `EventBus`.
  4. Circuit breaker: при N последовательных timeout'ов для одного NPC эмитится `PlannerStuckEvent` и NPC переводится в `idle`.
  5. Тесты: `test_traversal_planner_timeout.py`, `test_traversal_planner_circuit_breaker.py`.
  6. Метрика `traversal_planner_timeout_events` экспортируется.
- **Зависимости:** ENIGMA-ARCH-047 (ТЗ-А3), ENIGMA-ARCH-067.

---

#### ENIGMA-ARCH-064: Boundary node deadlock protection через hardcoded distance

- **Категория:** Movement / Calibration
- **Severity:** P0
- **Статус верификации:** ✅ Подтверждено (`movement_engine.py` строка 289 — `if _is_at_boundary or _dist_to_boundary < 1.5:`)
- **Описание:** Boundary node deadlock protection через hardcoded distance: `if _dist_to_boundary < 1.5:`. Threshold 1.5 метра hardcoded. Если NPC движется медленно или граф имеет большие узлы, это может не сработать.
- **Локализация:** `backend/app/services/spatial/movement_engine.py`, строка 289:
  ```python
  # S-145 FIX: Материализация если NPC стоит на boundary node ИЛИ очень близко к ней.
  _is_at_boundary = (_npc_pos_data.get("position", "") == boundary_node.node_id)
  if _is_at_boundary or _dist_to_boundary < 1.5:
      logger.info(f"[CROSS_LOC_MATERIALIZE] npc={intent.actor_id} crossing ...")
  ```
- **Нарушенный контракт:** §4.9 (No magic numbers — из ТЗ-А2); §4.28 (Single cross-location contract).
- **Definition of Done:**
  1. Порог `1.5` вынесен в `CalibrationProfile` (см. ENIGMA-ARCH-021 ТЗ-А2) как `boundary_materialization_distance`.
  2. Порог адаптивен: учитывает `node_size` графа (большие узлы → больший порог) и `npc_speed` (медленный NPC → меньший порог, чтобы не пропустить момент).
  3. ADR с обоснованием выбора `1.5` (почему не 1.0 или 2.0).
  4. Тесты: `test_boundary_distance_threshold.py`, `test_boundary_adaptive_slow_npc.py`, `test_boundary_adaptive_large_nodes.py`.
  5. Метрика `boundary_materialization_failures` (NPC не успел материализоваться) = 0.
- **Зависимости:** ENIGMA-ARCH-021 (ТЗ-А2), ENIGMA-ARCH-061.

---

#### ENIGMA-ARCH-065: Collision avoidance использует random sampling

- **Категория:** Movement / Collision avoidance
- **Severity:** P0
- **Статус верификации:** ✅ Подтверждено (`movement_engine.py` строки 481–503 — `for _ in range(10): angle = rng.uniform(0, 2 * math.pi); radius = rng.uniform(collision_radius, 1.5)`)
- **Описание:** Collision avoidance использует random sampling: 10 итераций random sampling для нахождения свободной точки. В плотных толпах это может не найти решение, и NPC застрянет.
- **Локализация:** `backend/app/services/spatial/movement_engine.py`, строки 481–503:
  ```python
  if npc_positions:
      import math
      for _ in range(10):  # Увеличено с 5 для стабильности обхода коллизий
          angle = rng.uniform(0, 2 * math.pi)
          radius = rng.uniform(collision_radius, 1.5)
          cx = tx + radius * math.cos(angle)
          cy = ty + radius * math.sin(angle)
          ...
          break
  else:
      best_x = tx + rng.uniform(-1.5, 1.5)
      best_y = ty + rng.uniform(-1.5, 1.5)
  ```
- **Нарушенный контракт:** §4.21 (Bounded algorithms — детерминированный алгоритм вместо random); производительность.
- **Definition of Done:**
  1. Random sampling заменён на детерминированный алгоритм: spiral search (расходящиеся кольца с фиксированными углами) или grid-based candidate generation.
  2. Если ни одна кандидатная точка не найдена после полного sweep'а, эмитится `CollisionStuckEvent` и NPC переводится в `wait` state.
  3. Количество итераций вынесено в `CalibrationProfile` как `collision_avoidance_max_attempts`.
  4. Тесты: `test_collision_avoidance_dense_crowd.py`, `test_collision_avoidance_deterministic.py`, `test_collision_avoidance_stuck_event.py`.
  5. Метрика `collision_stuck_events` экспортируется; alert при росте.
- **Зависимости:** ENIGMA-ARCH-021 (ТЗ-А2), ENIGMA-ARCH-066.

---

#### ENIGMA-ARCH-066: Traversal proposal не имеет validation layer

- **Категория:** Movement / Validation
- **Severity:** P0
- **Статус верификации:** ✅ Подтверждено (`domain/movement.py` — `TraversalProposal` создаётся с `path_waypoints`, `segment_modes`, `duration_ticks` без runtime validation)
- **Описание:** `TraversalProposal` создается с `path_waypoints`, `segment_modes`, `duration_ticks`, но нет runtime validation, что waypoints физически достижимы или duration реалистичен.
- **Локализация:** `backend/app/domain/movement.py` — `TraversalProposal` dataclass; `movement_engine.py` — создание proposal без validation.
- **Нарушенный контракт:** §4.32 (Validation layer for proposals); каузальная замкнутость (недостижимые waypoints создают invalid state).
- **Definition of Done:**
  1. Введён `TraversalProposalValidator` — компонент, проверяющий: (a) каждый waypoint достижим из предыдущего (через `find_path` с лимитом), (b) `duration_ticks` в реалистичном диапазоне (min/max per body capability), (c) `segment_modes` согласованы с `body.can_jump`.
  2. При невалидности эмитится `InvalidProposalEvent` и proposal отбрасывается.
  3. Введён `ProposalValidationReport` — отладочный DTO с указанием невалидных полей.
  4. Тесты: `test_traversal_proposal_validation.py`, `test_traversal_proposal_invalid_waypoints.py`, `test_traversal_proposal_unrealistic_duration.py`.
  5. Метрика `invalid_proposal_events` экспортируется.
- **Зависимости:** ENIGMA-ARCH-063, ENIGMA-ARCH-067.

---

#### ENIGMA-ARCH-067: A* fallback не имеет circuit breaker

- **Категория:** Movement / Fallback cascade
- **Severity:** P0
- **Статус верификации:** ✅ Подтверждено (`movement_engine.py` строки 547–566, 624–648 — `_fallback_to_astar` вызывается при REJECTED от planner; если A* тоже fails, возвращается `REJECTED` без retry/alternative)
- **Описание:** A* fallback не имеет circuit breaker: `_fallback_to_astar()` вызывается если `LocalTraversalPlanner` вернул `REJECTED`. Но если A* тоже fails, возвращается `REJECTED` без retry logic или alternative routing.
- **Локализация:** `backend/app/services/spatial/movement_engine.py`, строки 547–566, 624–648:
  ```python
  def _fallback_to_astar(self, ...):
      ...
      if not path or len(path) < 2:
          return MovementPlanResult(
              status=MovementPlanStatus.REJECTED,
              reason="NO_GEOMETRY_AND_NO_A_STAR_PATH"
          )
  ...
  if not plan.possible:
      return MovementPlanResult(
          status=MovementPlanStatus.REJECTED,
          reason=plan.reason or "TRAVERSAL_IMPOSSIBLE"
      )
  ```
- **Нарушенный контракт:** §4.33 (Circuit breakers for fallback cascades).
- **Definition of Done:**
  1. При `REJECTED` от обоих (planner + A*) эмитится `RoutingCircuitBreakerEvent` с указанием NPC, source, target, причин отказа.
  2. Введён `AlternativeRouter` — пытается найти альтернативный target (ближайший достижимый узел с той же ролью).
  3. Если alternative найден — NPC перенаправляется; если нет — NPC переводится в `idle` с `RoutingStuckTrait`.
  4. Circuit breaker: при N последовательных REJECTED для одного NPC эмитится `RoutingStuckEvent` и NPC помечается `spatially_stuck` для debug.
  5. Тесты: `test_routing_circuit_breaker.py`, `test_routing_alternative_target.py`, `test_routing_stuck_event.py`.
  6. Метрика `routing_circuit_breaker_events` и `routing_stuck_npcs` экспортируются.
- **Зависимости:** ENIGMA-ARCH-063, ENIGMA-ARCH-066, ENIGMA-ARCH-061.

---

#### ENIGMA-ARCH-068: Body heading calculation не учитывает obstacles

- **Категория:** Movement / Physics
- **Severity:** P0
- **Статус верификации:** ✅ Подтверждено (`movement_engine.py` строки 524–526, 864 — `_heading = math.atan2(ty - _cy, tx - _cx)` без проверки LOS)
- **Описание:** Body heading calculation не учитывает obstacles: `_heading = math.atan2(ty - _cy, tx - _cx)`. NPC поворачивается к цели по прямой, даже если между ним и целью стена. Это создает «неестественное» поведение (NPC смотрит сквозь стену).
- **Локализация:** `backend/app/services/spatial/movement_engine.py`, строки 524–526, 864:
  ```python
  _heading = (
      math.atan2(ty - _cy, tx - _cx) if (tx != _cx or ty != _cy) else 1.5708
  )
  ...
  _heading = math.atan2(target_xy[1] - source_xy[1], target_xy[0] - source_xy[0])
  ```
- **Нарушенный контракт:** §4.31 (Physics-aware movement); правдоподобие.
- **Definition of Done:**
  1. Введён `HeadingCalculator` — вычисляет heading с учётом obstacles: если прямой LOS заблокирован, heading направлен на первый waypoint path'а (не на конечную цель).
  2. Если path'а нет (NPC idle) — heading остаётся прежним (NPC не «крутится» к недостижимой цели).
  3. Введён `FacingObstacleEvent` при обнаружении «смотрения сквозь стену» (для debug).
  4. Тесты: `test_heading_obstacle_aware.py`, `test_heading_path_following.py`, `test_heading_idle_no_rotation.py`.
  5. Метрика `facing_obstacle_events` = 0 в типичной сессии.
- **Зависимости:** ENIGMA-ARCH-066, ENIGMA-ARCH-049 (ТЗ-А3).

### 5.18. P0 — PerceptionFilter: восприятие и контекст

---

#### ENIGMA-ARCH-069: Perception filter не учитывает facing direction

- **Категория:** Perception / Facing
- **Severity:** P0
- **Статус верификации:** ✅ Подтверждено (`perception_filter.py` `_can_see()` — проверяет `_npc_is_conscious`, distance, light level; не проверяет facing direction)
- **Описание:** Perception filter не учитывает facing direction: `_can_see()` проверяет distance и light level, но не проверяет, смотрит ли NPC в направлении события. NPC «видит» всё в радиусе 15м, даже если отвернулся.
- **Локализация:** `backend/app/services/npc/perception_filter.py`, функция `_can_see` (строки 119–147):
  ```python
  def _can_see(npc_id, spatial_query, radius, scene_state):
      if not _npc_is_conscious(npc_id, scene_state):
          return False
      # distance check
      # light level check
      return _LIGHT_LEVELS.get(light, 1) >= _LIGHT_LEVELS[_MIN_LIGHT_FOR_SIGHT]
  ```
- **Нарушенный контракт:** §4.34 (Facing-aware perception); §4.1 (Epistemic boundary — из ТЗ-А1).
- **Definition of Done:**
  1. `_can_see()` принимает `npc_facing` (radians) и `event_angle` (radians относительно NPC).
  2. Введён `FieldOfView` profile: `fov_degrees` (по умолчанию 120°), `peripheral_fov_degrees` (180°, с пониженной clarity).
  3. События вне FOV не воспринимаются (если NPC не имеет `awareness_trait` или `paranoid_trait`).
  4. События в peripheral FOV воспринимаются с пониженной clarity (умножается на 0.5).
  5. Тесты: `test_perception_facing_in_fov.py`, `test_perception_facing_outside_fov.py`, `test_perception_peripheral_reduced_clarity.py`, `test_perception_awareness_trait.py`.
  6. Метрика `perception_facing_blocks` экспортируется.
- **Зависимости:** ENIGMA-ARCH-068, ENIGMA-ARCH-072, ENIGMA-ARCH-005 (ТЗ-А1).

---

#### ENIGMA-ARCH-070: Light level thresholds магические

- **Категория:** Perception / Calibration
- **Severity:** P0
- **Статус верификации:** ✅ Подтверждено (`perception_filter.py` строки 33–47 — `_MIN_LIGHT_FOR_SIGHT = "dim"`, `_LIGHT_LEVELS` словарь)
- **Описание:** Light level thresholds магические: `_LIGHT_LEVELS = {"dark": 0, "dim": 1, "torchlit": 2, "natural": 3, "bright": 4}`, `_MIN_LIGHT_FOR_SIGHT = "dim"`. Почему `dim` — минимальный уровень? Нет документации или mechanism для tuning.
- **Локализация:** `backend/app/services/npc/perception_filter.py`, строки 33–47:
  ```python
  _MIN_LIGHT_FOR_SIGHT = "dim"  # dark → не видит, dim/bright/natural → видит
  _LIGHT_LEVELS = {
      "dark": 0,
      "dim": 1,
      "torchlit": 2,
      "natural": 3,
      "bright": 4,
  }
  ```
- **Нарушенный контракт:** §4.9 (No magic numbers — из ТЗ-А2); документируемость.
- **Definition of Done:**
  1. `_LIGHT_LEVELS` и `_MIN_LIGHT_FOR_SIGHT` вынесены в `CalibrationProfile` (см. ENIGMA-ARCH-021 ТЗ-А2) как `LightPerceptionProfile`.
  2. Введён `LightLevel` enum вместо строковых ключей.
  3. ADR с обоснованием выбора `dim` как минимального уровня (почему не `torchlit`).
  4. Поддержка per-NPC адаптации: NPC с `low_light_vision_trait` видит в `dark`.
  5. Тесты: `test_light_level_threshold.py`, `test_light_level_per_npc.py`, `test_light_level_low_light_trait.py`.
  6. Линтер `lint_magic_numbers.py` расширен для perception_filter.
- **Зависимости:** ENIGMA-ARCH-021 (ТЗ-А2), ENIGMA-ARCH-069, ENIGMA-ARCH-072.

---

#### ENIGMA-ARCH-071: Sound events hardcoded list

- **Категория:** Perception / Semantic
- **Severity:** P0
- **Статус верификации:** ✅ Подтверждено (`perception_filter.py` строки 216–223 — `sound_events = {"SOUND_EMITTED", "OBJECT_DESTROYED", "PLAYER_ATTACKED", "PLAYER_SPOKE"}`)
- **Описание:** Sound events hardcoded list: `sound_events = {"SOUND_EMITTED", "OBJECT_DESTROYED", "PLAYER_ATTACKED", "PLAYER_SPOKE"}`. Если добавится новый тип звукового события, нужно вручную добавить в этот set. Нет mechanism для semantic tagging (все events с tag «audible» автоматически sound events).
- **Локализация:** `backend/app/services/npc/perception_filter.py`, строки 216–223:
  ```python
  sound_events = {
      "SOUND_EMITTED",
      "OBJECT_DESTROYED",
      "PLAYER_ATTACKED",
      "PLAYER_SPOKE",
  }
  if event_type.upper() in sound_events:
      if _can_hear(npc_id, spatial_query, radius, scene_state):
          perceiving.append(npc_id)
  ```
- **Нарушенный контракт:** §4.29 (Semantic classification over string matching); расширяемость.
- **Definition of Done:**
  1. Sound events определяются через semantic tags: любой event с тегом `audible` (или `perception:sound`) автоматически является sound event.
  2. `EventSemanticTagger` (см. ENIGMA-ARCH-057 ТЗ-А3) расширен тегом `audible`.
  3. `perception_filter` читает tags из `EventDTO`, не hardcoded set.
  4. Тесты: `test_sound_event_semantic_tag.py`, `test_sound_event_custom_type.py`, `test_sound_event_tag_isolation.py`.
  5. Метрика `sound_event_types` показывает разнообразие (не только 4 hardcoded).
- **Зависимости:** ENIGMA-ARCH-057 (ТЗ-А3), ENIGMA-ARCH-062, ENIGMA-ARCH-073.

---

#### ENIGMA-ARCH-072: Clarity calculation не учитывает NPC traits

- **Категория:** Perception / Individualization
- **Severity:** P0
- **Статус верификации:** ✅ Подтверждено (`perception_filter.py` `calculate_clarity()` — учитывает distance, light, stress; не учитывает individual traits)
- **Описание:** Clarity calculation не учитывает NPC traits: `calculate_clarity()` учитывает distance, light, stress, но не учитывает individual traits (например, NPC с good eyesight видит лучше, NPC с poor hearing слышит хуже).
- **Локализация:** `backend/app/services/npc/perception_filter.py`, функция `calculate_clarity(distance, light_level, ...)` — формула без trait-модификаторов.
- **Нарушенный контракт:** §4.35 (Trait-aware perception); индивидуализация.
- **Definition of Done:**
  1. `calculate_clarity()` принимает `npc_traits: TraitProfile` (eyesight, hearing, awareness).
  2. Введены модификаторы: `eyesight_modifier` (0.5–1.5), `hearing_modifier` (0.5–1.5), `awareness_modifier` (0.8–1.2).
  3. Trait-модификаторы вынесены в `NPCProfile` (immutable), не в runtime state.
  4. Тесты: `test_clarity_good_eyesight.py`, `test_clarity_poor_hearing.py`, `test_clarity_awareness_trait.py`.
  5. Метрика `clarity_distribution` показывает разнообразие per NPC.
- **Зависимости:** ENIGMA-ARCH-069, ENIGMA-ARCH-070, ENIGMA-ARCH-052 (ТЗ-А3).

---

#### ENIGMA-ARCH-073: Consciousness check через string matching

- **Категория:** Perception / Type safety
- **Severity:** P0
- **Статус верификации:** ✅ Подтверждено (`perception_filter.py` строки 110–116 — `incap = {"dead", "unconscious", "sleeping", "спит", "без сознания", "мёртв"}`)
- **Описание:** Consciousness check через string matching: `incap = {"dead", "unconscious", "sleeping", "спит", "без сознания", "мёртв"}`. Fragile: если добавится новое состояние «paralyzed» или «stunned», нужно вручную добавить в set.
- **Локализация:** `backend/app/services/npc/perception_filter.py`, строки 110–116:
  ```python
  def _npc_is_conscious(npc_id, scene_state):
      pos = scene_state.get("npc_positions", {}).get(npc_id, {})
      state = pos.get("state", "").lower()
      activity = pos.get("activity", "").lower()
      incap = {"dead", "unconscious", "sleeping", "спит", "без сознания", "мёртв"}
      return state not in incap and activity not in {"sleeping", "спит"}
  ```
- **Нарушенный контракт:** §4.29 (Semantic classification over string matching); type safety.
- **Definition of Done:**
  1. Введён `ConsciousnessState` enum: `CONSCIOUS`, `UNCONSCIOUS`, `SLEEPING`, `DEAD`, `PARALYZED`, `STUNNED`.
  2. `npc_positions[npc_id]["state"]` имеет тип `ConsciousnessState`, не `str`.
  3. `_npc_is_conscious` проверяет `state not in {UNCONSCIOUS, SLEEPING, DEAD, PARALYZED, STUNNED}`.
  4. Смешение русского и английского в одном set устранено (единый enum).
  5. Тесты: `test_consciousness_state_enum.py`, `test_consciousness_new_state_paralyzed.py`, `test_consciousness_migration.py`.
  6. Линтер запрещает строковые сравнения для consciousness.
- **Зависимости:** ENIGMA-ARCH-062, ENIGMA-ARCH-071.

---

#### ENIGMA-ARCH-074: Perception context templates hardcoded

- **Категория:** Perception / Verbalization
- **Severity:** P0
- **Статус верификации:** ✅ Подтверждено (`perception_filter.py` строки 271–281 — `_TEMPLATES = {"OBJECT_DESTROYED": f"...", "PLAYER_ATTACKED": f"...", ...}`)
- **Описание:** Perception context templates hardcoded: `_TEMPLATES = {"OBJECT_DESTROYED": f"Ты слышишь треск...", "PLAYER_ATTACKED": f"Ты видишь как {actor}...", ...}`. Templates hardcoded для каждого event type. Нет mechanism для dynamic generation или customization per NPC personality.
- **Локализация:** `backend/app/services/npc/perception_filter.py`, строки 271–281:
  ```python
  _TEMPLATES = {
      "OBJECT_DESTROYED": f"Ты слышишь треск и грохот {dist_str} — что-то уничтожили.",
      "OBJECT_CHANGED": f"Ты замечаешь что {params.get('target_name', 'объект')} изменился {dist_str}.",
      ...
  }
  return _TEMPLATES.get(event_type, f"Ты замечаешь событие: {event_type} {dist_str}.")
  ```
- **Нарушенный контракт:** §4.36 (Dynamic perception templates); индивидуализация.
- **Definition of Done:**
  1. `_TEMPLATES` вынесены в `config/perception/templates.yaml` с поддержкой hot-reload.
  2. Введён `PerceptionTemplateEngine` — компонент, рендерящий template с учётом NPC personality (voice profile, vocabulary).
  3. Поддержка per-NPC templates: NPC с `gruff_veteran` voice использует другие формулировки, чем `nervous_submissive`.
  4. Template variables: `{actor}`, `{target_name}`, `{dist_str}`, `{npc_emotion}`.
  5. Тесты: `test_perception_template_yaml.py`, `test_perception_template_per_voice.py`, `test_perception_template_variables.py`.
  6. Метрика `perception_template_diversity` показывает использование разных templates.
- **Зависимости:** ENIGMA-ARCH-056 (ТЗ-А3), ENIGMA-ARCH-075, ENIGMA-ARCH-021 (ТЗ-А2).

### 5.19. P0 — DialogueExecutor: LLM-интеграция

---

#### ENIGMA-ARCH-075: System prompt не учитывает NPC personality

- **Категория:** Dialogue / LLM prompts
- **Severity:** P0
- **Статус верификации:** ✅ Подтверждено (`dialogue_executor.py` строки 157–165 — единый `system_prompt` для всех NPC)
- **Описание:** System prompt не учитывает NPC personality: `system_prompt = "Ты — NPC в мире ENIGMA (тёмное фэнтези)..."`. Одинаковый system prompt для всех NPC. Нет injection of personality traits, voice profile, или backstory в system prompt (только в user prompt).
- **Локализация:** `backend/app/services/execution/dialogue_executor.py`, строки 157–165:
  ```python
  system_prompt = (
      "Ты — NPC в мире ENIGMA (тёмное фэнтези). Твоя задача — сказать одну короткую реплику (1-2 предложения). "
      "Говори ТОЛЬКО на русском языке. Не используй китайские иероглифы, английский текст или системные теги. "
      "Не описывай свои действия (например, 'идёт к двери'). Только прямая речь. "
      ...
  )
  ```
- **Нарушенный контракт:** §4.37 (Personality-injected LLM prompts); индивидуализация.
- **Definition of Done:**
  1. Введён `SystemPromptBuilder` — компонент, собирающий system prompt из: (a) базового contract (язык, формат), (b) NPC personality traits, (c) voice profile (vocabulary, syntax patterns), (d) backstory summary.
  2. Personality injection: `f"Ты — {npc_name}. Твои черты: {traits_summary}. Твой голос: {voice_profile}."`
  3. Voice profiles загружаются из `config/npc/voice_archetypes/` (уже есть в проекте).
  4. Backstory берётся из `NPCProfile` (L0).
  5. Тесты: `test_system_prompt_personality_injection.py`, `test_system_prompt_voice_profile.py`, `test_system_prompt_backstory.py`.
  6. Метрика `system_prompt_diversity` показывает разнообразие per NPC.
- **Зависимости:** ENIGMA-ARCH-074, ENIGMA-ARCH-077, ENIGMA-ARCH-076.

---

#### ENIGMA-ARCH-076: STM hard contract не имеет graceful degradation

- **Категория:** Dialogue / STM
- **Severity:** P0
- **Статус верификации:** ✅ Подтверждено (`dialogue_executor.py` строки 197–201 — `if not _stm_text and req.intent_type not in ("greeting", "approach") and requires_dialogue_context(req.intent_type): req = _dc_replace(req, intent_type="approach")`)
- **Описание:** STM hard contract не имеет graceful degradation: если STM пуст, intent demoted to «approach». Но нет mechanism для partial context (например, «помню, что мы говорили, но не детали»).
- **Локализация:** `backend/app/services/execution/dialogue_executor.py`, строки 197–201:
  ```python
  if not _stm_text and req.intent_type not in ("greeting", "approach") and requires_dialogue_context(req.intent_type):
      logger.warning(f"[DIALOGUE_EXEC] No STM for {task.owner_id} -> {req.target_id}, "
                     f"intent '{req.intent_type}' demoted to 'approach' (auto-recover).")
      from dataclasses import replace as _dc_replace
      req = _dc_replace(req, intent_type="approach")
  ```
- **Нарушенный контракт:** §4.38 (Graceful STM degradation); правдоподобие диалога.
- **Definition of Done:**
  1. Введён `PartialContextProvider` — при пустом STM предоставляет partial context из `narrative_cache` / `crystallized_beliefs` (помнит, что говорил с этим NPC, но не детали).
  2. Intent не демотируется к `approach` автоматически; вместо этого в prompt инжектируется `f"Ты смутно помнишь, что уже говорил с {_target_name}, но не помнишь детали."`.
  3. Введён `ContextLevel` enum: `FULL_STM`, `PARTIAL_NARRATIVE`, `CRYSTALLIZED_ONLY`, `NONE`.
  4. При `NONE` intent демотируется (как сейчас), при `PARTIAL_*` — продолжает с modified prompt.
  5. Тесты: `test_stm_degradation_partial_context.py`, `test_stm_degradation_narrative_fallback.py`, `test_stm_degradation_crystallized_fallback.py`, `test_stm_degradation_none_demote.py`.
  6. Метрика `stm_degradation_levels` показывает распределение уровней.
- **Зависимости:** ENIGMA-ARCH-045 (ТЗ-А3), ENIGMA-ARCH-030 (ТЗ-А2), ENIGMA-ARCH-077.

---

#### ENIGMA-ARCH-077: Beliefs injection не имеет relevance filtering

- **Категория:** Dialogue / Prompt assembly
- **Severity:** P0
- **Статус верификации:** ✅ Подтверждено (`dialogue_executor.py` строки 170–180 — `_target_beliefs = [b for b in _all_beliefs if b.source_id == req.target_id]`; все beliefs о target injected без relevance filtering)
- **Описание:** Beliefs injection не имеет relevance filtering: `_target_beliefs = [b for b in _all_beliefs if b.source_id == req.target_id]`. Все beliefs о target injected в prompt, даже если они не релевантны текущему topic. Это может перегрузить prompt нерелевантной информацией.
- **Локализация:** `backend/app/services/execution/dialogue_executor.py`, строки 170–180:
  ```python
  _all_beliefs = self._belief_store.get_beliefs(task.owner_id)
  _target_beliefs = [b for b in _all_beliefs if b.source_id == req.target_id]
  ...
  for b in _target_beliefs:
      _phrase = _TRAIT_TO_TEXT.get(b.trait, f"Ты относишься к {_target_name} как к {b.trait}")
      _beliefs_text += f"{_phrase} {_target_name} (уверенность: {b.weight:.2f}). "
  ```
- **Нарушенный контракт:** §4.39 (Relevance filtering for prompt injection); token efficiency.
- **Definition of Done:**
  1. Введён `BeliefRelevanceScorer` — компонент, вычисляющий relevance между belief и текущим topic (intent_type, target, recent events).
  2. Relevance учитывает: trait match (fear для `intimidate`, loyalty для `betrayal`), temporal proximity (свежие beliefs приоритетнее), weight (высокий weight приоритетнее).
  3. В prompt инжектируются только top-N relevant beliefs (N = configurable, по умолчанию 3).
  4. При превышении token budget beliefs отбрасываются по low relevance.
  5. Тесты: `test_belief_relevance_filtering.py`, `test_belief_relevance_topic_match.py`, `test_belief_relevance_token_budget.py`.
  6. Метрика `belief_injection_count` (среднее beliefs per prompt) ≤ 3.
- **Зависимости:** ENIGMA-ARCH-075, ENIGMA-ARCH-053 (ТЗ-А3), ENIGMA-ARCH-035 (ТЗ-А2).

---

#### ENIGMA-ARCH-078: ResponseValidator не имеет confidence scoring

- **Категория:** Dialogue / Validation
- **Severity:** P0
- **Статус верификации:** ✅ Подтверждено (`dialogue_executor.py` строки 240–244 — `validation = self._validator.validate(raw); if validation.is_fallback: ...`; boolean, не confidence)
- **Описание:** ResponseValidator не имеет confidence scoring: `validation.is_fallback` — boolean. Нет confidence score или gradation (например, «частично валидно, но содержит forbidden action»).
- **Локализация:** `backend/app/services/execution/dialogue_executor.py`, строки 240–244:
  ```python
  validation = self._validator.validate(raw)
  if validation.is_fallback:
      logger.info(f"[DIALOGUE_EXEC] LLM response rejected ({validation.violation}). Using fallback.")
  ```
  `backend/app/services/verbalization/response_validator.py` — `is_fallback: bool`, `violation: str`.
- **Нарушенный контракт:** §4.40 (Confidence-graded validation); granularity.
- **Definition of Done:**
  1. `ValidationResult` имеет поля: `confidence: float` (0.0–1.0), `violations: List[Violation]`, `severity: Severity` (INFO/WARN/ERROR).
  2. `is_fallback` заменён на `confidence < threshold` (настраиваемый).
  3. Partial validity: при `confidence >= 0.7` ответ принимается с пометкой `partially_valid`; при `confidence < 0.7` — fallback.
  4. Каждое violation имеет категорию: `NON_RUSSIAN_TEXT`, `FOURTH_WALL`, `FORBIDDEN_ACTION`, `SYSTEM_TAG`, `TOO_LONG`.
  5. Тесты: `test_validation_confidence_scoring.py`, `test_validation_partial_validity.py`, `test_validation_violation_categories.py`.
  6. Метрика `validation_confidence_distribution` и `validation_violation_categories` экспортируются.
- **Зависимости:** ENIGMA-ARCH-079, ENIGMA-ARCH-080, ENIGMA-ARCH-017 (ТЗ-А1).

---

#### ENIGMA-ARCH-079: LLM max_tokens hardcoded

- **Категория:** Dialogue / LLM params
- **Severity:** P0
- **Статус верификации:** ✅ Подтверждено (`dialogue_executor.py` строка 236 — `params=GenerationParams(max_tokens=100)`)
- **Описание:** LLM max_tokens hardcoded: `params=GenerationParams(max_tokens=100)`. 100 tokens для всех диалогов. Короткие greetings и длинные explanations имеют одинаковый лимит.
- **Локализация:** `backend/app/services/execution/dialogue_executor.py`, строка 236:
  ```python
  raw = self._router.request_for_agent(
      agent_name="npc",
      prompt=user_prompt,
      system_prompt=system_prompt,
      params=GenerationParams(max_tokens=100)
  )
  ```
- **Нарушенный контракт:** §4.41 (Adaptive LLM params); §4.9 (No magic numbers — из ТЗ-А2).
- **Definition of Done:**
  1. `max_tokens` адаптируется к `intent_type`: `greeting` → 50, `explain` → 200, `confession` → 300, `threat` → 100.
  2. Параметры вынесены в `config/dialogue/llm_params.yaml` per intent_type.
  3. Введён `LLMParamsResolver` — компонент, возвращающий `GenerationParams` по intent_type и dialogue phase.
  4. Поддержка per-NPC адаптации: NPC с `verbose_trait` получает +50% max_tokens.
  5. Тесты: `test_llm_params_intent_type.py`, `test_llm_params_per_npc.py`, `test_llm_params_config_reload.py`.
  6. Метрика `llm_max_tokens_distribution` показывает разнообразие.
- **Зависимости:** ENIGMA-ARCH-021 (ТЗ-А2), ENIGMA-ARCH-075.

---

#### ENIGMA-ARCH-080: ConfessionParser не имеет verification

- **Категория:** Dialogue / Verification
- **Severity:** P0
- **Статус верификации:** ✅ Подтверждено (`npc_confession_parser.py` — `parse_and_record()` использует keyword overlap + PropositionMatcher, но без проверки сарказма/контекста; `dialogue_executor.py` строки 122–124 — вызов без verification)
- **Описание:** ConfessionParser не имеет verification: `confession_parser.parse_and_record()` вызывается после LLM generation, но нет verification, что confession действительно произошло (LLM мог сгенерировать «Я признаюсь...» в шутку или сарказме).
- **Локализация:** `backend/app/services/player_cognition/npc_confession_parser.py`, метод `parse_and_record` — использует `PropositionMatcher` (семантический матч) и keyword overlap, но не проверяет контекст (сарказм, шутка, цитата). `backend/app/services/execution/dialogue_executor.py`, строки 122–124:
  ```python
  if self._confession_parser:
      try:
          self._confession_parser.parse_and_record(
              npc_id=task.owner_id,
              reply_text=text,
              ...
          )
  ```
- **Нарушенный контракт:** §4.42 (Verified LLM side-effects); каузальная замкнутость (ложные признания создают invalid state).
- **Definition of Done:**
  1. Введён `ConfessionVerifier` — компонент, проверяющий контекст признания: (a) tone analysis (сарказм/шутка через LLM second-pass или heuristic), (b) dialogue phase (признание во время боя подозрительно), (c) NPC state (NPC в страхе = правдивее, NPC в сарказме = ложно).
  2. `parse_and_record` возвращает `ConfidenceScore` (0.0–1.0); при `confidence < threshold` признание помечается `unverified` и не применяется к `truth_state` сразу.
  3. `unverified` признания попадают в `pending_confessions` queue; подтверждаются при следующих корреляциях (второе признание, physical evidence).
  4. Введён `FalseConfessionEvent` при обнаружении ложного признания (для analytics).
  5. Тесты: `test_confession_verifier_sarcasm.py`, `test_confession_verifier_combat_context.py`, `test_confession_verifier_pending_queue.py`, `test_confession_verifier_false_positive.py`.
  6. Метрика `false_confession_rate` и `pending_confessions_count` экспортируются.
- **Зависимости:** ENIGMA-ARCH-078, ENIGMA-ARCH-035 (ТЗ-А2), ENIGMA-ARCH-044 (ТЗ-А3).

### 5.20. P2 — Сильные стороны execution-слоя (сохранить при рефакторинге)

Аудит зафиксировал следующие сильные стороны, которые не требуют исправления, но должны быть сохранены:

1. **Spatial Intent Gate** — единая точка арбитража для всех movement intents с чёткой приоритизацией. Рефакторинг ENIGMA-ARCH-062 не должен нарушать этот принцип; лишь заменять string matching на typed enums.
2. **LOD separation** — LOD0 (micro jitter) vs LOD1 (macro A*) с чётким separation of concerns. Проблемы 065/066 — implementation details, не архитектурные.
3. **Traversal planning с честной физикой** — `LocalTraversalPlanner` проверяет физическую проходимость (стены, jump capability). Проблема 063 — лишь отсутствие timeout, не в подходе.
4. **Perception membrane** — NPC физически не могут воспринимать события за пределами radius/LOS. Проблемы 069/072 — расширения, не замены.
5. **Hard Contract для STM** — нет context = нет dialogue (предотвращает LLM hallucination). Проблема 076 — лишь в отсутствии graceful degradation, не в самом принципе.
6. **ResponseValidator** — отсечение 4-й стены, non-Russian text, forbidden actions. Проблема 078 — расширение до confidence scoring, не замена.

---

## 6. Синтез: recurring patterns (продолжение ТЗ-А3)

### 6.1. Три recurring patterns из аудита execution-слоя

Аудит выявил три системных паттерна, повторяющихся в проблемах 61–80:

#### Pattern 1: String-based classification вместо semantic tagging

**Примеры:**
- `"schedule" in _reason`, `"flee" in _reason` (062)
- `event_type.upper() in sound_events` (071)
- `state not in {"dead", "sleeping", "спит"}` (073)

**Проблема:** добавление нового варианта требует manual updates в multiple places; хрупкость к переименованию.

**Решение:** typed enums (`IntentCategory`, `ConsciousnessState`), semantic tags (`audible`, `social:aggression`).

#### Pattern 2: Hardcoded thresholds без parameterization

**Примеры:**
- `_dist_to_boundary < 1.5` (064)
- `distance >= 15.0` (069)
- `max_tokens=100` (079)
- `for _ in range(10)` (065)
- `_MIN_LIGHT_FOR_SIGHT = "dim"` (070)

**Проблема:** каждый threshold — потенциальная точка для tuning, но все hardcoded; A/B тесты невозможны.

**Решение:** `CalibrationProfile` (из ТЗ-А2) с hot-reload и per-archetype адаптацией.

#### Pattern 3: Fallback cascades без circuit breakers

**Примеры:**
- `LocalTraversalPlanner` → A* → `REJECTED` (067)
- Cross-loc routing → boundary → materialize → entry_hint → error (061)
- STM empty → demote intent → silent failure (076)

**Проблема:** нет mechanism для «если все fallback'ы провалились, fail loudly и alert».

**Решение:** circuit breakers с `RoutingCircuitBreakerEvent`, `RoutingStuckEvent`, fail-loud вместо silent REJECTED.

### 6.2. Группировка по архитектурным доменам (продолжение)

| Домен | Проблемы | Ключевой контракт |
|---|---|---|
| Movement / Cross-location | 061, 064, 067 | Single contract; circuit breakers |
| Movement / Classification | 062 | Semantic classification over string matching |
| Movement / Safety | 063, 065, 066 | Bounded planners; validation layer |
| Movement / Physics | 068 | Physics-aware movement |
| Perception / Facing | 069 | Facing-aware perception |
| Perception / Calibration | 070, 072 | Trait-aware; no magic numbers |
| Perception / Semantic | 071, 073 | Semantic tags; typed enums |
| Perception / Verbalization | 074 | Dynamic templates |
| Dialogue / LLM prompts | 075, 079 | Personality injection; adaptive params |
| Dialogue / STM | 076 | Graceful degradation |
| Dialogue / Prompt assembly | 077 | Relevance filtering |
| Dialogue / Validation | 078, 080 | Confidence scoring; verified side-effects |

---

## 7. Этапы реализации (фазы 21–26, продолжение ТЗ-А1/А2/А3)

### Фаза 21 — MovementEngine: single contract и circuit breakers (P0, 3 недели)

**Цель:** Унифицировать cross-location routing и ввести circuit breakers в fallback cascades.

**Проблемы:** ENIGMA-ARCH-061, 062, 064, 066, 067.

**Ключевые работы:**
- `CrossLocationContract` + `CrossLocationRouter`.
- `IntentCategory` enum; миграция с string matching.
- `TraversalProposalValidator`.
- `AlternativeRouter` + circuit breakers.
- Пороги в `CalibrationProfile`.

**Критерии готовности фазы:**
- Метрика `cross_loc_fallback_level_distribution` показывает доминирование level 0 (нормальный путь).
- Метрика `routing_circuit_breaker_events` и `routing_stuck_npcs` экспортируются.
- Тесты на single contract, circuit breaker, alternative routing — зелёные.

### Фаза 22 — MovementEngine: bounded planners и physics (P0, 2 недели)

**Цель:** Ввести timeout в planners и physics-aware heading.

**Проблемы:** ENIGMA-ARCH-063, 065, 068.

**Ключевые работы:**
- `MAX_TRAVERSAL_PLANNER_ITERATIONS` + `PlannerTimeoutEvent`.
- Детерминированный collision avoidance (spiral search).
- `HeadingCalculator` с учётом obstacles.

**Критерии готовности фазы:**
- Метрика `traversal_planner_timeout_events` = 0 в типичной сессии.
- Метрика `collision_stuck_events` = 0.
- Метрика `facing_obstacle_events` = 0.

### Фаза 23 — PerceptionFilter: facing, traits, semantic tags (P0, 3 недели)

**Цель:** Ввести facing-aware perception, trait-aware clarity и semantic classification.

**Проблемы:** ENIGMA-ARCH-069, 070, 071, 072, 073.

**Ключевые работы:**
- `FieldOfView` profile + facing direction в `_can_see`.
- `LightLevel` enum + `LightPerceptionProfile`.
- Semantic tags `audible` для sound events.
- `TraitProfile` в `calculate_clarity`.
- `ConsciousnessState` enum.

**Критерии готовности фазы:**
- Метрика `perception_facing_blocks` > 0 (функциональность активна).
- Метрика `clarity_distribution` показывает разнообразие per NPC.
- Линтер запрещает строковые сравнения для consciousness и event types.

### Фаза 24 — PerceptionFilter: dynamic templates (P0, 2 недели)

**Цель:** Вынести perception templates в конфиг и ввести per-NPC кастомизацию.

**Проблемы:** ENIGMA-ARCH-074.

**Ключевые работы:**
- `config/perception/templates.yaml` с hot-reload.
- `PerceptionTemplateEngine` с per-voice поддержкой.
- Template variables.

**Критерии готовности фазы:**
- Метрика `perception_template_diversity` показывает использование разных templates.

### Фаза 25 — DialogueExecutor: personality и graceful degradation (P0, 3 недели)

**Цель:** Ввести personality injection, graceful STM degradation и relevance filtering.

**Проблемы:** ENIGMA-ARCH-075, 076, 077, 079.

**Ключевые работы:**
- `SystemPromptBuilder` с personality/voice/backstory injection.
- `PartialContextProvider` с `ContextLevel` enum.
- `BeliefRelevanceScorer` с top-N filtering.
- `LLMParamsResolver` с adaptive `max_tokens`.

**Критерии готовности фазы:**
- Метрика `system_prompt_diversity` показывает разнообразие.
- Метрика `stm_degradation_levels` показывает использование partial context.
- Метрика `belief_injection_count` ≤ 3.
- Метрика `llm_max_tokens_distribution` показывает разнообразие.

### Фаза 26 — DialogueExecutor: validation и verification (P0, 2 недели)

**Цель:** Ввести confidence scoring в валидацию и verification в confession parsing.

**Проблемы:** ENIGMA-ARCH-078, 080.

**Ключевые работы:**
- `ValidationResult` с `confidence: float` и `violations: List[Violation]`.
- `ConfessionVerifier` с tone analysis и context checks.
- `pending_confessions` queue для unverified признаний.

**Критерии готовности фазы:**
- Метрика `validation_confidence_distribution` показывает gradation.
- Метрика `false_confession_rate` < 5%.
- Метрика `pending_confessions_count` observable.

---

## 8. Приоритизация (сводная, продолжение ТЗ-А1/А2/А3)

| Приоритет | ID проблем | Обоснование |
|---|---|---|
| **P0** | 061, 062, 063, 064, 065, 066, 067, 068, 069, 070, 071, 072, 073, 074, 075, 076, 077, 078, 079, 080 | Все 20 проблем — P0: нарушают фундаментальные принципы (single contract, semantic classification, bounded planners, physics-aware movement, facing-aware perception, personality injection, verified side-effects); создают хрупкость, зависания, ложные признания; блокируют production readiness |

Примечание: в отличие от ТЗ-А1/А2/А3, где часть проблем была P1/P2, в ТЗ-А4 все 20 проблем оценены как P0. Причина: execution-слой — «последняя миля» к пользователю; хрупкость здесь напрямую влияет на UX и правдоподобие, а refactor остальных слоёв (ТЗ-А1/А2/А3) не имеет смысла без надёжного execution.

---

## 9. Сквозные работы (дополнение к ТЗ-А1/А2/А3)

К сквозным работам ТЗ-А1 §9, ТЗ-А2 §9 и ТЗ-А3 §9 добавляются:

14. **Единый `CalibrationProfile`.** Все коэффициенты из проблем 064, 065, 070, 079 должны жить в одном профиле с проблемами 021/024/029/033/051/054 (ТЗ-А2/А3).
15. **Метрики observability.** Для каждой проблемы 061–080 вводится метрика в CI-отчёт.
16. **Расширение `lint_magic_numbers.py`.** Должен покрывать `movement_engine.py`, `perception_filter.py`, `dialogue_executor.py`, `npc_confession_parser.py`.
17. **Type-safe enums across system.** Помимо `IntentCategory` (062), `ConsciousnessState` (073), `LightLevel` (070), `ContextLevel` (076) — аудит всех строковых полей в execution-слое; замена на typed enums.
18. **Semantic tags propagation.** Расширение `EventSemanticTagger` (ТЗ-А3) тегами `audible`, `visible`, `movement:reactive`, `movement:schedule`; потребление в `PerceptionFilter` и `MovementEngine`.
19. **Circuit breakers everywhere.** Все fallback cascades (061, 067, 076) получают circuit breakers с fail-loud events.

---

## 10. Контракты и ограничения (дополнение к ТЗ-А1/А2/А3)

К ограничениям ТЗ-А1 §10, ТЗ-А2 §10 и ТЗ-А3 §10 добавляются:

14. **Совместимость с ADR-O-315 (body_heading).** Изменения в `HeadingCalculator` (068) не должны нарушать ADR-O-315 без явного ADR-ревизии.
15. **Сохранение Spatial Intent Gate.** Рефакторинг 062 не должен нарушать единую точку арбитража; лишь заменять string matching на typed enums.
16. **Сохранение Hard Contract для STM.** Рефакторинг 076 не должен позволять LLM hallucination при пустом STM; partial context — расширение, не замена hard contract.
17. **Не нарушать детерминизм.** `HeadingCalculator` и collision avoidance (065) должны быть детерминированными; random sampling заменяется на seeded spiral search.
18. **Сохранение LOD separation.** Изменения в LOD0 (collision avoidance) и LOD1 (A*) не должны нарушать разделение обязанностей.
19. **LLM-side-effects verification.** Любой side-effect LLM (confession, promise, threat, commitment) обязан проходить verification перед записью в state.

---

## 11. Критерии готовности (глобальные, дополнение к ТЗ-А1/А2/А3)

К критериям ТЗ-А1 §11, ТЗ-А2 §11 и ТЗ-А3 §11 добавляются:

22. Линтер `lint_magic_numbers.py` не находит ни одного числового литерала вне whitelist в `movement_engine.py`, `perception_filter.py`, `dialogue_executor.py`, `npc_confession_parser.py`.
23. Линтер запрещает string matching (`"schedule" in reason`, `event_type.upper() in sound_events`, `state not in {...}`) в execution-слое.
24. `MovementEngine` не имеет fallback cascades без circuit breaker; метрика `routing_circuit_breaker_events` observable.
25. `LocalTraversalPlanner` имеет `MAX_TRAVERSAL_ITERATIONS`; метрика `traversal_planner_timeout_events` = 0 в типичной сессии.
26. `PerceptionFilter` учитывает facing direction; метрика `perception_facing_blocks` > 0.
27. `DialogueExecutor` использует `SystemPromptBuilder` с personality injection; метрика `system_prompt_diversity` показывает разнообразие.
28. `ResponseValidator` возвращает `confidence: float`; метрика `validation_confidence_distribution` показывает gradation.
29. `ConfessionParser` имеет `ConfessionVerifier`; метрика `false_confession_rate` < 5%.

---

## 12. Риски и смягчения (дополнение к ТЗ-А1/А2/А3)

| Риск | Вероятность | Влияние | Смягчение |
|---|---|---|---|
| Facing-aware perception сломает существующие сценарии (NPC «не видел» событие) | Высокая | Высокое | Поэтапный rollout: сначала informational, потом блокирующий; `awareness_trait` для NPC, которые должны «видеть» за спиной |
| Personality injection в system prompt превысит token budget | Высокая | Среднее | Token budget manager; personality summary ≤ 100 tokens; backstory ≤ 50 tokens |
| Graceful STM degradation создаст LLM hallucination | Средняя | Высокое | Partial context явно помечается в prompt; LLM инструктируется «не выдумывать детали» |
| `ConfessionVerifier` забракует legitimate признания | Средняя | Высокое | `pending_confessions` queue; подтверждаются при второй корреляции; manual override через debug |
| Замена random sampling на spiral search изменит поведение NPC | Средняя | Низкое | Seeded spiral search; тесты на determinism (ТЗ-А1) расширяются |
| `IntentCategory` миграция сломает existing intents | Высокая | Среднее | Mapping table с обратной совместимостью; `reason: str` сохраняется как deprecated поле |
| Circuit breakers создадут false positives (NPC застревает без причины) | Средняя | Высокое | Threshold configurable; `RoutingStuckTrait` автоматически снимается после успешного пути |
| Adaptive `max_tokens` превысит LLM context window | Низкая | Среднее | `max_tokens` capped per LLM model profile; fallback на default при превышении |

---

## 13. Метрики и верификация (дополнение к ТЗ-А1/А2/А3)

| Метрика | Целевое значение | Источник данных |
|---|---|---|
| `cross_loc_fallback_level_distribution` | level 0 ≥ 80% | `movement_engine.py` |
| `routing_circuit_breaker_events` за 100 тиков | < 5 | `movement_engine.py` |
| `routing_stuck_npcs` | 0 | `movement_engine.py` |
| `traversal_planner_timeout_events` | 0 в типичной сессии | `local_traversal_planner.py` |
| `collision_stuck_events` | 0 | `movement_engine.py` |
| `invalid_proposal_events` | 0 | `movement_engine.py` |
| `facing_obstacle_events` | 0 | `movement_engine.py` |
| `perception_facing_blocks` | > 0 (функциональность активна) | `perception_filter.py` |
| `clarity_distribution` | diverse per NPC | `perception_filter.py` |
| `sound_event_types` | > 4 (не только hardcoded) | `perception_filter.py` |
| `perception_template_diversity` | diverse per voice | `perception_filter.py` |
| `system_prompt_diversity` | diverse per NPC | `dialogue_executor.py` |
| `stm_degradation_levels` | partial context используется | `dialogue_executor.py` |
| `belief_injection_count` (среднее per prompt) | ≤ 3 | `dialogue_executor.py` |
| `llm_max_tokens_distribution` | diverse per intent_type | `dialogue_executor.py` |
| `validation_confidence_distribution` | показывает gradation | `response_validator.py` |
| `validation_violation_categories` | observable | `response_validator.py` |
| `false_confession_rate` | < 5% | `npc_confession_parser.py` |
| `pending_confessions_count` | observable | `npc_confession_parser.py` |

---

## 14. Приложения

### Приложение А. Сводная таблица верификации проблем 61–80

| ID | Файл | Строки | Статус верификации |
|---|---|---|---|
| 061 | `movement_engine.py` | 259–373 | ✅ Подтверждено (каскад CROSS_LOC_INTERCEPT → boundary → materialize → entry_hint → error) |
| 062 | `movement_engine.py` | 148–157 | ✅ Подтверждено (`"schedule" in _reason`, `"flee" in _reason`) |
| 063 | `movement_engine.py`, `local_traversal_planner.py` | 642, весь `compile_plan` | ✅ Подтверждено (нет timeout) |
| 064 | `movement_engine.py` | 289 | ✅ Подтверждено (`_dist_to_boundary < 1.5`) |
| 065 | `movement_engine.py` | 481–503 | ✅ Подтверждено (`for _ in range(10): rng.uniform(...)`) |
| 066 | `domain/movement.py`, `movement_engine.py` | — | ✅ Подтверждено (нет validation layer) |
| 067 | `movement_engine.py` | 547–566, 624–648 | ✅ Подтверждено (`_fallback_to_astar` → REJECTED без retry) |
| 068 | `movement_engine.py` | 524–526, 864 | ✅ Подтверждено (`math.atan2` без obstacle check) |
| 069 | `perception_filter.py` | 119–147 | ✅ Подтверждено (`_can_see` без facing) |
| 070 | `perception_filter.py` | 33–47 | ✅ Подтверждено (`_MIN_LIGHT_FOR_SIGHT = "dim"`, `_LIGHT_LEVELS`) |
| 071 | `perception_filter.py` | 216–223 | ✅ Подтверждено (hardcoded `sound_events` set) |
| 072 | `perception_filter.py` | 63+ | ✅ Подтверждено (`calculate_clarity` без traits) |
| 073 | `perception_filter.py` | 110–116 | ✅ Подтверждено (`incap = {"dead", "unconscious", "sleeping", "спит", ...}`) |
| 074 | `perception_filter.py` | 271–281 | ✅ Подтверждено (hardcoded `_TEMPLATES`) |
| 075 | `dialogue_executor.py` | 157–165 | ✅ Подтверждено (единый `system_prompt`) |
| 076 | `dialogue_executor.py` | 197–201 | ✅ Подтверждено (demote to `approach` без partial context) |
| 077 | `dialogue_executor.py` | 170–180 | ✅ Подтверждено (все beliefs о target без relevance filtering) |
| 078 | `dialogue_executor.py`, `response_validator.py` | 240–244 | ✅ Подтверждено (`is_fallback: bool`) |
| 079 | `dialogue_executor.py` | 236 | ✅ Подтверждено (`max_tokens=100`) |
| 080 | `npc_confession_parser.py`, `dialogue_executor.py` | 35–89, 122–124 | ✅ Подтверждено (keyword overlap + PropositionMatcher без verification) |

### Приложение Б. Перекрёстные ссылки на ТЗ-А1, ТЗ-А2, ТЗ-А3

| Проблема ТЗ-А4 | Связанная проблема | Тип связи |
|---|---|---|
| 061 (Cross-loc cascades) | 008 (ТЗ-А1: Race conditions transfers), 050 (ТЗ-А3: Static boundary) | Расширение |
| 062 (String classification) | 071, 073 (ТЗ-А4) | Pattern (string matching) |
| 063 (Planner timeout) | 047 (ТЗ-А3: A* infinite loop) | Параллель |
| 064 (Boundary distance) | 021 (ТЗ-А2: Calibration) | Подкатегория |
| 065 (Random sampling) | 015 (ТЗ-А1: Determinism) | Параллель (оба — determinism) |
| 066 (Proposal validation) | 067 (ТЗ-А4) | Связанные (validation + circuit breaker) |
| 067 (Circuit breaker) | 061 (ТЗ-А4) | Pattern (fallback cascade) |
| 068 (Heading obstacles) | 049 (ТЗ-А3: Affordance accessibility) | Параллель (оба — physics-aware) |
| 069 (Facing perception) | 005 (ТЗ-А1: Perception component), 072 (ТЗ-А4) | Расширение |
| 070 (Light thresholds) | 021 (ТЗ-А2: Calibration) | Подкатегория |
| 071 (Sound events) | 057 (ТЗ-А3: Semantic tags) | Расширение |
| 072 (Clarity traits) | 052 (ТЗ-А3: Adaptive sizing) | Параллель (оба — trait-aware) |
| 073 (Consciousness strings) | 062 (ТЗ-А4) | Pattern (string matching) |
| 074 (Perception templates) | 056 (ТЗ-А3: Gender inflection) | Параллель (оба — verbalization) |
| 075 (Personality prompt) | 056 (ТЗ-А3), 074 (ТЗ-А4) | Pattern (per-NPC customization) |
| 076 (STM degradation) | 030 (ТЗ-А2: STM decay), 045 (ТЗ-А3: Crash-safe consolidation) | Расширение |
| 077 (Belief relevance) | 053 (ТЗ-А3: Recall semantic), 035 (ТЗ-А2: Belief validation) | Параллель (оба — relevance) |
| 078 (Validation confidence) | 080 (ТЗ-А4), 017 (ТЗ-А1: Silent failures) | Расширение |
| 079 (Adaptive max_tokens) | 021 (ТЗ-А2: Calibration) | Подкатегория |
| 080 (Confession verification) | 035 (ТЗ-А2: Belief validation), 044 (ТЗ-А3: Discovery formula) | Параллель (оба — verification) |

### Приложение В. Источники

- Архив исходного кода: `Enigma-V.0.5.3.8.2_-.zip`
- ТЗ-А1: `/home/z/my-project/download/ТЗ_Architect_Enigma_V0.5.3.8.2.md`
- ТЗ-А2: `/home/z/my-project/download/ТЗ_Architect_Enigma_V0.5.3.8.2_Part2.md`
- ТЗ-А3: `/home/z/my-project/download/ТЗ_Architect_Enigma_V0.5.3.8.2_Part3.md`
- Существующие ADR: `docs/audits/ADR-*_IMPACT.md` (особенно ADR-O-315, ADR-056, ADR-O-330, ADR-O-342, V8-MVP-12, V8-PSY-30, S-145, S-04, S186)
- Архитектурный устав: `docs/АРХИТЕКТУРНЫЙ_УСТАВ_ENIGMA.md`
- Каузальный контракт: `docs/00_CAUSAL_CONTRACT_v2.0.md`
