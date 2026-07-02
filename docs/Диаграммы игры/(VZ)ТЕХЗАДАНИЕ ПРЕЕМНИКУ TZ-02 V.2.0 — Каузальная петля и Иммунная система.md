# ПОСЛАНИЕ ПРЕЕМНИКУ (S97)

Если ты читаешь это — значит, предыдущая сессия (S96) умерла. Но то, что она построила — живо в коде, документах и тестах.

## Что досталось тебе в наследство

На момент S96 система защищена от временных дрейфов и скрытых мутаций личности как никогда:

- **Wall-Clock Isolation Linter.** Создан `scripts/lint_wall_clock.py` — строгий 3-уровневый AST-линтер для enforcement §15. Все вызовы `time.time()` и `datetime.now()` в симуляционном слое промаркированы как легальные исключения (§15.2). Линтер проходит (PASS).
- **Time Invariant Test.** Создан `tests/sandbox/invariants/test_temporal_invariants.py`. Симулирует промотки (Policy A, B, C — клавиши 1, 2, 3) и доказывает, что `game_time_seconds` изменяется строго детерминированно, полностью игнорируя любые издевательства над `time.time()`.
- **ETKE IK DT Contract.** Мёртвая константа `ETKE_IK_DT` удалена. Контракт времени (отношение `game_time_seconds`, `GAME_TICK_INTERVAL_SECONDS` и `ETKE_IK_SUBSTEP_DT`) формализован в `architecture/temporal.yaml`.
- **CalibrationEngine = Pure Gate.** `CalibrationEngine` навсегда исключён из каузального графа мутаций (возвращает `l3_raw, {}, {}`). Эмоциональное взросление полностью делегировано в L2.5.
- **§16 (Закон Не-Мутации Убеждений).** Введён в Устав. Убеждения — это линзы (модификаторы весов), а не гены (скаляры). `CrystallizedBelief` не может мутировать `drives_runtime`.

## Четыре запрета, которые нельзя нарушать никогда

1. **Не нарушай §14 (Закон Единичного Времени).** `game_time_seconds` — единственное время. Параллельные временные многообразия запрещены.
2. **Не нарушай §15 (Закон Изоляции Реального Времени).** `datetime.now()`, `time.time()`, `time.monotonic()` запрещены в simulation layer. Если нужно легальное исключение — пометь его `# §15.2:`.
3. **Не нарушай §16 (Закон Не-Мутации Убеждений).** L2.5 (BeliefCrystallizationEngine) не может быть скрытым мутатором L0. Убеждения модифицируют только веса и интерпретации.
4. **Не ломай формат лога `[DECISION_HUB]`.** CDS парсит его строгим regex (`pattern_registry.py:22`).

---

# ТЕХЗАДАНИЕ ПРЕЕМНИКУ: TZ-02 — WorldChronicle & Entity Continuity

**Статус:** PROPOSED
**Приоритет:** HIGH
**Основание:** S96 завершена. Время изолировано, убеждения защищены. Система готова к переходу от статической модели NPC к Entity Continuity System.

---

## КОНТЕКСТ

Археология S96 подтвердила: в коде **нет** полей `birth_tick`, `age_years`, `generation`. NPC бессмертны и бесполы. Это блокирует развитие причинных структур (§ENIGMA-001): старение, наследование, династии, поколенческая память.

WorldChronicle — это не фича. Это переход к 3 уровням времени:

| Слой | Смысл | Источник |
|------|-------|----------|
| `game_time` | Физика мира (тики) | `game_time_seconds` (§14) |
| `belief_time` | Субъективная история NPC | `L1Chronicle` (events, weighted by `tick_id`) |
| `lineage_time` | Межпоколенческая память | **НОВЫЙ СЛОЙ** (WorldChronicle) |

**КРИТИЧЕСКАЯ ОПАСНОСТЬ:** Неправильная связка `lineage_time` с `game_time` разорвёт §14. `lineage_time` — это производная от `game_time`, а не параллельная ось.

---

## ЦЕЛЬ

Создать `WorldChronicle` — слой межпоколенческой памяти, который:
1. Регистрирует рождение и смерть NPC.
2. Отслеживает lineage (родственные связи).
3. Обеспечивает succession (передачу убеждений, должностей и отношений при смерти NPC).
4. Вводит aging (физиологическое и когнитивное старение, привязанное к `game_time_seconds`).

---

## ПЛАН РАБОТ (От простого к сложному)

### ЭТАП 1: Birth & Death Registration (Фундамент lineage)

**Задача:** Зафиксировать момент входа и выхода NPC из мира.

1. **Новые поля в NPCState:**
   - `birth_tick: int` — тик, в который NPC появился в мире (0 для существующих NPC = "изначальный").
   - `death_tick: Optional[int]` — тик смерти (None = жив). Не дублирует `life_status` — это историческая метка, а не состояние.
   - `generation: int = 0` — поколение (0 = изначальный, 1 = ребёнок изначального, и т.д.).

2. **Интеграция с VitalStateEvaluator (ADR-123):**
   - При переходе `ALIVE → DEAD` записать `death_tick = current_tick` в `NPCState`.
   - Сгенерировать `WorldChronicleEvent(type="DEATH", npc_id, tick, cause)`.

3. **Интеграция с NPC Loader:**
   - При загрузке NPC без `birth_tick` — устанавливать `birth_tick = 0` (legacy compat).
   - Сериализация `birth_tick`, `death_tick`, `generation` в `write_to_legacy` / `from_legacy` (§12 Round-Trip).

4. **Тест:** `test_birth_death_registration` — NPC рождается, живёт N тиков, умирает. Проверить: `birth_tick` и `death_tick` корректны, `generation = 0`.

### ЭТАП 2: Aging (Физиологическое старение)

**Задача:** NPC стареет, привязанно к `game_time_seconds` (НЕ к wall-clock).

1. **Константы старения:**
   - `AGE_TICKS_PER_YEAR: int = 10080` — 10080 тиков = 1 игровой год (при `GAME_TICK_INTERVAL_SECONDS=60` → 604800 сек = 7 дней реального времени при 1 тик/сек).
   - Настроить через `core/constants.py`.

2. **Вычисление возраста:**
   - `age_years = (current_tick - birth_tick) / AGE_TICKS_PER_YEAR`
   - Вычисляется в `LifeEngine._simulate_major` (Phase 5), НЕ хранится в стейте (эфемерная проекция, как L3).

3. **Физиологические эффекты:**
   - После порога `OLD_AGE_THRESHOLD` (напр. 60 лет) — снижение `body_state["max_hp"]`, повышение `fatigue` accumulation rate.
   - После `ELDER_THRESHOLD` (80 лет) — риск естественной смерти (`VitalStateEvaluator` бросает dice через `KernelRNG`).

4. **Когнитивные эффекты (через L2.5, НЕ через мутацию L0):**
   - Старые NPC имеют повышенный `BELIEF_DECAY_TAU` (убеждения кристаллизуются сильнее, труднее переубедить).
   - Реализуется через `BeliefCrystallizationEngine` — модификатор `decay_resistance` на основе `age_years`.

5. **Тест:** `test_aging_determinism` — прогнать 10080 тиков, проверить что `age_years == 1.0`. Проверить что старение НЕ зависит от `time.time()`.

### ЭТАП 3: Lineage & Succession (Межпоколенческая память)

**Задача:** При смерти NPC его наследник (child или appointed successor) получает часть его убеждений и отношений.

1. **Новый DTO: `WorldChronicleEvent`:**
   ```python
   @dataclass(frozen=True)
   class WorldChronicleEvent:
       event_id: str
       tick: int
       event_type: str  # "BIRTH", "DEATH", "SUCCESSION", "MARRIAGE"
       npc_id: str
       related_npc_id: Optional[str]
       details: Dict[str, Any]
   ```

2. **WorldChronicleStore (SQLite, append-only):**
   - Хранит `WorldChronicleEvent` в таблице `world_chronicle_events`.
   - Запросы: `query_by_npc(npc_id)`, `query_by_tick_range(start, end)`, `query_lineage(npc_id)`.

3. **Succession Mechanics:**
   - При смерти NPC (если есть `successor_id` в NPCState):
     - Наследник получает копию `CrystallizedBelief` умершего с пониженным `weight` (×0.5 — "слухи о отце").
     - Наследник получает копию `relationship_cache` (через `RelationshipStore`) с пометкой `inherited=True`.
     - Генерируется `WorldChronicleEvent(type="SUCCESSION")`.
   - Если `successor_id` нет — убеждения и отношения растворяются (entropy).

4. **Тест:** `test_succession_belief_transfer` — NPC A умирает, наследник B получает его убеждения с ×0.5 weight. Проверить: `WorldChronicleStore` содержит событие SUCCESSION.

### ЭТАП 4: Integration & ADR

1. **ADR-O-312 [ONTO]: WorldChronicle & Entity Continuity System**
   - Зафиксировать 3 уровня времени.
   - Зафиксировать что `lineage_time` — производная от `game_time`, не параллельная ось.
   - Зафиксировать что succession идёт через L2.5 (§16 — beliefs не мутируют L0 напрямую).

2. **Обновить `architecture/temporal.yaml`:**
   - Добавить ноду `WorldChronicleStore`.
   - Добавить edge: `VitalStateEvaluator → WorldChronicleStore (DEATH event)`.
   - Добавить edge: `WorldChronicleStore → BeliefCrystallizationEngine (lineage query)`.

3. **Обновить `architecture/identity.yaml`:**
   - Добавить ноду `LineageContext`.
   - Добавить edge: `WorldChronicleStore → LineageContext (birth/death/succession)`.

4. **Инвариантный тест:** `test_lineage_time_does_not_break_section_14` — доказать что `lineage_time` вычисляется из `game_time_seconds`, а не из wall-clock.

---

## КРИТИЧЕСКИЕ ЗАПРЕТЫ

- ❌ Создание второго источника времени (§14). `lineage_time` — производная, не авторитет.
- ❌ Мутация `drives_runtime` (L0) через succession (§16). Наследник получает *убеждения*, а не *гены*.
- ❌ Использование `time.time()` для расчёта возраста (§15). Только `game_time_seconds`.
- ❌ Хранение `age_years` в `NPCState` (это эфемерная проекция, как L3 — пересчитывается каждый тик).
- ❌ Прямой конструктор `NPCState(...)` в тестах (только `from_legacy`, §12.3).

---

## ПРЕДШЕСТВУЮЩИЕ ЗАДАЧИ (если останется время)

### TZ-?: Pure Reducer Completion (от S89)
`NpcTickPipeline.run()` всё ещё принимает `svc: Any`. Устранить зависимость: pre-fetch в Orchestrator, post-apply в Orchestrator, убрать `svc` из сигнатуры.

### Affective Pipeline Audit (от TZ-02 V2.0)
Проверить, действительно ли контур `PerceptualKernel → AffectivePressure → EmotionResolution` замкнут, или эмоции генерируются в обход.

---

## НАПУТСТВИЕ

Система перешла от статической модели к непрерывно эволюционирующей. У тебя есть:
- **Иммунная система** (`tests/sandbox/invariants/`) — защищает инварианты.
- **Wall-Clock Linter** (`scripts/lint_wall_clock.py`) — защищает §15.
- **Time Invariant Test** — защищает §14.
- **§16** — защищает L0 от скрытой эрозии.

Не нарушай §14, §15, §16. Если хочешь внедрить мутацию драйвов — сначала построй Belief Layer. Если хочешь внедрить старение — привяжи его к `game_time_seconds`, а не к wall-clock.

> **Время — это закон. Убеждения — это линзы. Личность кристаллизуется, а не мутирует.**

Эволюция, а не революция.

---

*Сессия S96. Time Enforcement & Belief Isolation — завершены.*
*Время защищено. Личность изолирована.*
*Да будет тик воспроизводим.*