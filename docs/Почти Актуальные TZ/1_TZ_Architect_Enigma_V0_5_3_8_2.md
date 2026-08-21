# Техническое задание для архитектора (ТЗ-А)

**Проект:** Enigma — каузальное ядро симуляции NPC  
**Версия проекта:** V0.5.3.8.2  
**Версия документа:** 1.0  
**Дата составления:** 2026-08-18  
**Адресат:** Архитектор систем симуляции / tech-lead backend  
**Автор верификации:** AI-аудит (на основе исходного кода `backend/app/services/...`)  
**Статус верификации:** все 20 проблем сверены с исходным кодом архива `Enigma-V.0.5.3.8.2_-.zip`

---

## 1. Назначение документа

Настоящий документ является техническим заданием (ТЗ) для архитектора, описывающим 20 обнаруженных архитектурных проблем в подсистемах NPC-пайплайна, эпистемической изоляции, каузальной замкнутости и персистентности состояния проекта Enigma. Документ структурирует проблемы по архитектурным доменам, присваивает приоритет и формулирует проверяемые критерии приёмки (Definition of Done) для каждой проблемы, а также определяет этапы реализации и сквозные работы.

Документ не является спецификацией API и не описывает точные сигнатуры классов; его задача — зафиксировать архитектурные контракты, инварианты и границы ответственности, в рамках которых разработчики должны спроектировать конкретные реализации.

## 2. Контекст и обоснование

Проект Enigma реализует детерминированное каузальное ядро симуляции NPC с заявленными принципами эпистемической изоляции (NPC не должен знать то, что он не воспринял), каузальной замкнутости (каждое изменение состояния имеет причину), детерминированности (одинаковый `TickState` → одинаковый `TickMutation`) и формального разделения объективной истины и субъективного восприятия.

Аудит кодовой базы версии V0.5.3.8.2 выявил системные отклонения от этих принципов: прямые чтения глобального state из NPC-пайплайна, незакрытые TODO в критическом пути принятия решений, отсутствие decay для убеждений, эвристики вместо формальных контрактов в ряде модификаторов, отсутствие глобальных инвариантных тестов и недостаточное покрытие персистентности. Без устранения этих проблем дальнейшее развитие проекта приведёт к накоплению архитектурного долга и невозможности верифицировать заявленные свойства системы.

## 3. Глоссарий

| Термин | Определение |
|---|---|
| `TickState` | Иммутабельный снапшот состояния мира на начало тика |
| `TickMutation` | Дельта состояния, порождаемая пайплайном и применяемая оркестратором |
| `NpcTickPipeline` | Чистая функция обработки одного NPC за тик |
| `TickOrchestrator` | Оркестратор, координирующий тики локаций и применение мутаций |
| Epistemic isolation | Принцип: NPC имеет доступ только к результатам собственного восприятия, не к глобальному `scene_state` |
| Causal closure | Принцип: каждое изменение состояния каузально обосновано событием, видимым для агента |
| `ExpectationStore` | Хранилище ожиданий NPC (Active Inference), объявлено, но не интегрировано |
| `PerceptionEngine` | Движок оценки социального статуса игрока, объявлен, но не интегрирован |
| `PerceptionProjector` | Слой проекции состояния в восприятие UI; работает ПОСЛЕ тика, для frontend |
| `EpistemicStore` | Хранилище убеждений NPC с `confidence`, без decay |
| `CrystallizedBeliefStore` | Хранилище кристаллизованных убеждений (R8), SQLite-персистентное |
| R7 / R8 | R7 — событийный belief-модификатор; R8 — кристаллизованный (накопленный) |
| `WillpowerGate` | Гейт сопротивления аватара давлению идентичности |
| `nearby_npcs` | Список NPC, передаваемый в `TickState` из внешнего источника (DM SceneBuilder) |
| `SUPERBOX` | Набор интеграционных сценариев для проверки каузальных контрактов |

## 4. Архитектурные принципы, подлежащие восстановлению

Архитектор должен исходить из того, что любая реализация должна восстанавливать следующие принципы, формально нарушенные в текущей кодовой базе:

1. **Epistemic boundary** — NPC-пайплайн не имеет права читать `scene_state["npc_positions"]` напрямую. Единственный источник позиции сущности для NPC — `spatial_query.get_entity_position(eid)` с обязательной проверкой восприятия (LOS/sound).
2. **Type-level separation of Objective vs Subjective** — объективная истина (`scene_state`, `npc_positions`) и субъективное восприятие NPC должны быть разными типами; компилятор/тайп-чекер должен физически запрещать передачу объективных структур в NPC-домен.
3. **Causal closure per tick** — каждое изменение `TickMutation` должно иметь формально зарегистрированную причину (событие, восприятие или внутренний драйв). Не должно быть «спонтанных» изменений состояния.
4. **Determinism as invariant** — детерминизм должен быть не свойством реализации, а проверяемым контрактом: тест воспроизводимости `TickState → TickMutation` обязателен в CI.
5. **No silent failures** — ошибки восприятия, памяти и belief-движков не должны проглатываться через `try/except → logger.warning → continue`; они обязаны либо отказывать тик, либо эмитировать восстанавливаемое событие ошибки в `EventBus`.
6. **Decay as first-class citizen** — все накопленные величины (confidence убеждений, memory weights, threat levels) обязаны иметь явный decay-контракт; бесконечно живущих убеждений быть не должно.
7. **Single perception component for NPC** — восприятие NPC должно формироваться одним компонентом до принятия решений, а не двумя разнесёнными (`PerceptionProjector` для UI и ad-hoc чтения `npc_positions` для NPC).
8. **Formal definition of "nearby"** — понятие «nearby» должно быть алгоритмически определено (радиус, графовая достижимость, LOC-фильтр) и не должно зависеть от источника данных.

---

## 5. Каталог архитектурных проблем

Каждая проблема описана по единому шаблону:

- **ID** — стабильный идентификатор проблемы
- **Категория** — архитектурный домен
- **Severity** — P0 (критично для заявленных принципов) / P1 (блокирует развитие) / P2 (долг)
- **Статус верификации** — подтверждено/уточнено по коду
- **Описание** — суть проблемы
- **Локализация** — путь к файлу и строки кода
- **Нарушенный контракт** — какие принципы из §4 нарушены
- **Definition of Done (DoD)** — проверяемые критерии закрытия
- **Зависимости** — ссылки на другие проблемы

### 5.1. P0 — Эпистемическая изоляция и каузальная замкнутость

---

#### ENIGMA-ARCH-001: Прямой доступ NPC к глобальному state

- **Категория:** Epistemic boundary
- **Severity:** P0
- **Статус верификации:** ✅ Подтверждено
- **Описание:** В `NpcTickPipeline.run()` NPC получает позиции других агентов напрямую из `state.scene_state.get("npc_positions", {})`, включая позицию игрока (`"player"`). Это позволяет NPC знать точные координаты сущностей, которых он физически не воспринимает, нарушая принцип эпистемической изоляции.
- **Локализация:** `backend/app/services/npc/npc_tick_pipeline.py`, строка 174:
  ```python
  _player_pos_dict = state.scene_state.get("npc_positions", {}).get("player", {}).get("local_position", {"x": 0.0, "y": 0.0})
  ```
  А также строки 51, 77–78, 1049–1053.
- **Нарушенный контракт:** §4.1 (Epistemic boundary), §4.3 (Causal closure per tick).
- **Definition of Done:**
  1. В `NpcTickPipeline.run()` отсутствуют вызовы `scene_state.get("npc_positions")`.
  2. Позиции всех сущностей, используемые NPC, получаются исключительно через `spatial_query` с проверкой LOS/sound/recognition.
  3. В CI работает статический линтер, запрещающий `scene_state.get("npc_positions")` в модулях `app/services/npc/*` (расширение существующего `lint_epistemic_boundary.py`).
  4. Тест `test_telepathy_epistemic_barrier.py` расширен: NPC, не имеющий LOS к игроку, не использует позицию игрока в своём DecisionHub.
- **Зависимости:** ENIGMA-ARCH-002, ENIGMA-ARCH-005, ENIGMA-ARCH-014.

---

#### ENIGMA-ARCH-002: Fallback на глобальный state в spatial helpers

- **Категория:** Epistemic boundary
- **Severity:** P0
- **Статус верификации:** ✅ Подтверждено (включая комментарий, признающий нарушение ADR-048)
- **Описание:** В `_resolve_reactive_movement()` функция `_pos()` имеет fallback: `return scene_state.get("npc_positions", {}).get(eid, {})`. Если `spatial_query` отсутствует или возвращает None, NPC получает прямой доступ к глобальным позициям без проверки восприятия. В коде прямо написано: «Чтение npc_positions из scene_state ЗАПРЕЩЕНО для decisions (ADR-048 Этап 1)» — но fallback остаётся.
- **Локализация:** `backend/app/services/npc/npc_tick_pipeline.py`, строки 1047–1053:
  ```python
  # ADR-048: Spatial Authority. Единственный источник пространственной истины.
  # Чтение npc_positions из scene_state ЗАПРЕЩЕНО для decisions (ADR-048 Этап 1).
  def _pos(eid: str) -> Dict[str, Any]:
      if spatial_query:
          return spatial_query.get_entity_position(eid) or {}
      return scene_state.get("npc_positions", {}).get(eid, {})
  ```
- **Нарушенный контракт:** §4.1 (Epistemic boundary), §4.2 (Type-level separation — отсутствие гарантии).
- **Definition of Done:**
  1. Функция `_pos()` удалена либо переписана так, что при отсутствии `spatial_query` возвращает `None`/поднимает `SpatialAuthorityViolation`.
  2. Любой путь, в котором `spatial_query` равен None, трактуется как инцидент, а не как допустимое состояние.
  3. Добавлен тест: при `spatial_query=None` NPC не двигается и логируется отказ с уровнем ERROR, не WARNING.
- **Зависимости:** ENIGMA-ARCH-001, ENIGMA-ARCH-014.

---

#### ENIGMA-ARCH-005: PerceptionProjector предназначен для UI, а не для NPC

- **Категория:** Perception architecture
- **Severity:** P0
- **Статус верификации:** ✅ Подтверждено (`perception_projector.py` строка 17–21)
- **Описание:** `PerceptionProjector` вызывается frontend'ом ПОСЛЕ завершения тика и предназначен для отображения мира игроку, а не для формирования субъективного восприятия NPC. Это создает путаницу в архитектуре: нет единого компонента, который формирует восприятие для самих NPC.
- **Локализация:** `backend/app/services/perception/perception_projector.py`:
  ```python
  class PerceptionProjector:
      """Reads state_t+1, builds perception. OUTSIDE kernel.
      Kernel produces state. UI reads state → builds perception.
      This class is called by game_screen / frontend, NOT by tick_orchestrator.
      """
  ```
- **Нарушенный контракт:** §4.7 (Single perception component for NPC).
- **Definition of Done:**
  1. Спроектирован и реализован отдельный компонент `NpcPerceptionCompiler` (рабочее имя), формирующий субъективное восприятие NPC до DecisionHub на основе `spatial_query`, `line_of_sight`, `sound_reach` и `recognition`-маркеров.
  2. `PerceptionProjector` явно документирован как UI-only, его импорт в `app/services/npc/*` запрещён линтером.
  3. Пайплайн NPC имеет единый вход восприятия: `perception = NpcPerceptionCompiler.compile(npc_id, tick_state)`; никакие другие чтения позиций/событий недопустимы.
- **Зависимости:** ENIGMA-ARCH-001, ENIGMA-ARCH-002, ENIGMA-ARCH-006, ENIGMA-ARCH-014.

---

#### ENIGMA-ARCH-007: Отсутствие проверки восприятия в proactive movement

- **Категория:** Epistemic boundary
- **Severity:** P0
- **Статус верификации:** ✅ Подтверждено
- **Описание:** В `_resolve_proactive_target()` для социальных intents (`seek_ally`, `call_for_help`, `spread_rumor`, `talk`) NPC ищет ближайшего NPC по глобальному списку `npc_positions` без проверки, может ли он физически воспринять этого NPC.
- **Локализация:** `backend/app/services/npc/npc_tick_pipeline.py`, строки 76–78:
  ```python
  if intent_value in ("seek_ally", "call_for_help", "spread_rumor", "talk"):
      npc_positions = scene_state.get("npc_positions", {})
      my_pos = npc_positions.get(npc_id, {}).get("local_position", {"x": 0, "y": 0})
  ```
- **Нарушенный контракт:** §4.1 (Epistemic boundary), §4.3 (Causal closure per tick).
- **Definition of Done:**
  1. Поиск цели для социальных intents осуществляется только по NPC, для которых в текущем тике установлено восприятие (LOS или sound, либо кристаллизованное знание о локации).
  2. NPC без воспринимаемых целей получает intent `wander` / `idle` вместо `seek_ally` к «невидимому» NPC.
  3. Тест: NPC в изолированной комнате не вызывает `seek_ally` к NPC в соседней локации.
- **Зависимости:** ENIGMA-ARCH-001, ENIGMA-ARCH-005.

---

#### ENIGMA-ARCH-014: Нет формального разделения между «объективной истиной» и «субъективным восприятием» в типах

- **Категория:** Type system / Architecture
- **Severity:** P0
- **Статус верификации:** ✅ Подтверждено
- **Описание:** В коде используются одни и те же структуры данных (`scene_state`, `npc_positions`) как для объективного мира, так и для субъективного восприятия. Нет type-level гарантии, что NPC не получит доступ к объективной истине.
- **Локализация:** `backend/app/domain/tick.py` (структура `TickState`), `backend/app/services/npc/npc_tick_pipeline.py` (использование `scene_state`).
- **Нарушенный контракт:** §4.2 (Type-level separation of Objective vs Subjective).
- **Definition of Done:**
  1. Введены типы `ObjectiveSceneState` (для `TickOrchestrator`, `SpatialService`) и `SubjectivePerception` (для `NpcTickPipeline`, `DecisionHub`). Наследование/алиасинг запрещён.
  2. В `TickState` поле `scene_state` имеет тип `ObjectiveSceneState` и не передаётся в NPC-домен; вместо него передаётся `subjective_perception: SubjectivePerception`.
  3. Линтер уровня типов (mypy + custom plugin или отдельный AST-чекер) запрещает импорт `ObjectiveSceneState` в `app/services/npc/*`.
  4. Документ `АРХИТЕКТУРНЫЙ_УСТАВ_ENIGMA.md` обновлён разделом о типовой изоляции.
- **Зависимости:** ENIGMA-ARCH-001, ENIGMA-ARCH-002, ENIGMA-ARCH-005.

---

#### ENIGMA-ARCH-019: Отсутствует верификация каузальной замкнутости

- **Категория:** Causal closure
- **Severity:** P0
- **Статус верификации:** ✅ Частично — существует `test_causal_closure.py` для отдельных сценариев, но не глобальный инвариант.
- **Описание:** Нет проверки того, что каждое изменение состояния имеет каузальную причину. Например, если NPC внезапно меняет позицию или отношение, система не проверяет, было ли это вызвано допустимым событием.
- **Локализация:** `backend/tests/sandbox/system/test_causal_closure.py` — сценарийный, не инвариантный.
- **Нарушенный контракт:** §4.3 (Causal closure per tick).
- **Definition of Done:**
  1. Введён `CausalClosureInvariant` — утверждение: для каждого поля `TickMutation` существует каузальное событие в `EventBus` или восприятии в текущем тике.
  2. Инвариант проверяется в CI на всех `SUPERBOX`-сценариях (см. ENIGMA-ARCH-010).
  3. Нарушения инварианта приводят к fail-у тика с диагностикой: какое поле, какой NPC, какое ожидаемое событие отсутствует.
- **Зависимости:** ENIGMA-ARCH-010, ENIGMA-ARCH-020.

### 5.2. P0 — Незакрытые TODO в критическом пути

---

#### ENIGMA-ARCH-003: Незавершённая интеграция ExpectationStore (Active Inference)

- **Категория:** Cognitive architecture
- **Severity:** P0
- **Статус верификации:** ✅ Подтверждено (`npc_tick_pipeline.py` строки 369–372)
- **Описание:** В критическом пути принятия решений есть TODO: «Интеграция ExpectationStore (Active Inference). Здесь должен вычисляться prediction_error и добавляться drive_modifiers на основе ожиданий NPC». NPC не формирует предсказаний о будущих событиях, что ограничивает глубину когнитивной архитектуры.
- **Локализация:** `backend/app/services/npc/npc_tick_pipeline.py`, строки 369–372:
  ```python
  # TODO (Фаза 2 / Эпоха 7): Интеграция ExpectationStore (Active Inference).
  # Здесь должен вычисляться prediction_error и добавляться drive_modifiers
  # на основе ожиданий NPC (награда/угроза).
  # Ожидания (EMA) хранятся в ExpectationStore (SQLite, Single Writer).
  ```
  Сам класс: `backend/app/services/npc/expectation_store.py`.
- **Нарушенный контракт:** Завершённость когнитивной архитектуры; заявленный в ADR-O-211 принцип предиктивного восприятия.
- **Definition of Done:**
  1. В пайплайн NPC добавлен шаг `expectation_evaluation`: читаются текущие ожидания NPC из `ExpectationStore`, сравниваются с фактом из `perception`, вычисляется `prediction_error: float`.
  2. `prediction_error` конвертируется в `drive_modifiers` (например, неожиданная угроза → буст `fear`/`flee`).
  3. Обновлённые ожидания записываются в `ExpectationStore` через `TickMutation` (без I/O внутри пайплайна).
  4. Добавлены тесты: `test_expectation_prediction_error.py`, `test_expectation_drive_modifier_attribution.py`.
- **Зависимости:** ENIGMA-ARCH-004, ENIGMA-ARCH-013.

---

#### ENIGMA-ARCH-004: Незавершённая интеграция PerceptionEngine (Социальный статус)

- **Категория:** Cognitive architecture / Social physics
- **Severity:** P0
- **Статус верификации:** ✅ Подтверждено (`npc_tick_pipeline.py` строки 374–377)
- **Описание:** Второй TODO: «Интеграция PerceptionEngine (Социальный статус). Здесь должен вызываться `assess_status(state.player_markers)` и `get_social_permissions()`». NPC не оценивает социальный статус игрока, что влияет на правдоподобность социальных взаимодействий.
- **Локализация:** `backend/app/services/npc/npc_tick_pipeline.py`, строки 374–377:
  ```python
  # TODO (Фаза 2 / Эпоха 7): Интеграция PerceptionEngine (Социальный статус).
  # Здесь должен вызываться assess_status(state.player_markers) и
  # get_social_permissions() для формирования модификаторов для DecisionHub.
  ```
  Сам класс: `backend/app/services/npc/perception_engine.py`.
- **Нарушенный контракт:** Социальная физика (заявленная в ADR-209-210-211-212).
- **Definition of Done:**
  1. В пайплайн добавлен шаг `social_status_evaluation`: `PerceptionEngine.assess_status(player_markers)` возвращает `SocialStatus` (LOW/MEDIUM/HIGH/CRITICAL).
  2. `get_social_permissions()` конвертирует статус в модификаторы для `DecisionHub`: низкий статус → буст ATTACK/IGNORE; высокий → буст OBEY/TRADE.
  3. Модификаторы проходят через `epistemic_modifiers` (ADR-O-355), а не инжектируются напрямую в `drive_modifiers`.
  4. Тесты: `test_perception_engine_status_assessment.py`, `test_perception_engine_modifiers.py`.
- **Зависимости:** ENIGMA-ARCH-003, ENIGMA-ARCH-005.

### 5.3. P1 — Каузальные контракты и детерминизм

---

#### ENIGMA-ARCH-008: Потенциальные race conditions при переходах между локациями

- **Категория:** Concurrency / State management
- **Severity:** P1
- **Статус верификации:** ✅ Подтверждено (`tick_orchestrator.py` строка 89, 345, 497, 739–743, 914)
- **Описание:** В `tick_orchestrator.py` есть `_pending_transfers` для NPC, перемещающихся между локациями. Если тик одной локации обрабатывается одновременно с тиком другой, NPC может оказаться в «промежуточном» состоянии, где он не принадлежит ни одной локации.
- **Локализация:** `backend/app/services/tick_orchestrator.py`:
  - строка 89: объявление `self._pending_transfers: Dict[str, Dict[str, dict]] = {}`
  - строки 345–347: проверка `_is_in_transfer` для запрета «призраков»
  - строки 497–499: синхронизация runtime-локаций
  - строки 739–743: инжект transfer-очереди в начале тика локации
  - строка 914: помещение NPC в очередь трансферов
- **Нарушенный контракт:** Каузальная замкнутость; детерминизм (состояние transfer-очереди зависит от порядка тиков локаций).
- **Definition of Done:**
  1. Документирована модель исполнения: либо строго последовательный тик локаций, либо явный протокол 2PC (two-phase commit) для transfers.
  2. Введён инвариант: для любого момента времени каждый живой NPC либо находится в `npc_positions` одной локации, либо находится в `_pending_transfers` ровно один раз (но не в обоих местах и нигде).
  3. Тест `test_transfer_atomicity.py` проверяет инвариант при конкурентной обработке двух локаций.
  4. Введён `TraversalFSMProbe` (уже существует) расширением проверки «NPC всегда либо в source, либо в target, либо в transfer-queue».
- **Зависимости:** ENIGMA-ARCH-010, ENIGMA-ARCH-019.

---

#### ENIGMA-ARCH-010: Отсутствие формальной верификации каузальных контрактов

- **Категория:** Verification / Tests
- **Severity:** P1
- **Статус верификации:** ✅ Подтверждено — `SUPERBOX` существует, глобального инвариантного теста нет.
- **Описание:** Несмотря на наличие `SUPERBOX` сценариев, нет автоматической проверки того, что все каузальные контракты выполняются при каждом тике. Тесты проверяют отдельные сценарии, но не глобальную инвариантность.
- **Локализация:** `backend/tests/sandbox/SUPERBOX/` — сценарии запускаются вручную/по расписанию, отчёты в `reports/дрейф_*.log`.
- **Нарушенный контракт:** §4.3 (Causal closure per tick), §4.4 (Determinism as invariant).
- **Definition of Done:**
  1. Каждый `SUPERBOX`-сценарий обёрнут в assertion-layer, проверяющий: (a) `CausalClosureInvariant` (см. ENIGMA-ARCH-019), (b) `EpistemicBoundaryInvariant` (NPC не читает `npc_positions`), (c) `DeterminismInvariant` (повторный прогон с тем же `TickState` даёт тот же `TickMutation`).
  2. Инвариантные проверки запускаются в CI на каждом PR.
  3. Отчёт о нарушениях инвариантов выводится в структурированном виде (JSON) с указанием NPC, тика, поля, причины.
- **Зависимости:** ENIGMA-ARCH-015, ENIGMA-ARCH-019.

---

#### ENIGMA-ARCH-015: Отсутствует верификация детерминизма

- **Категория:** Verification / Tests
- **Severity:** P1
- **Статус верификации:** ✅ Подтверждено — существует узкий `test_cfrm_models.py:TestClassifyEventDeterministic`, существует `дрейф_replay_determinism.csv`, но нет глобального assertion-теста на уровне `TickState → TickMutation`.
- **Описание:** Несмотря на заявленную детерминированность, нет автоматической проверки того, что одинаковый `TickState` всегда производит одинаковый `TickMutation`. Использование `KernelRNG` с `salt="decision_hub"` помогает, но не гарантирует полной детерминированности.
- **Локализация:** `backend/app/services/npc/kernel_rng.py`, `backend/tests/sandbox/SUPERBOX/reports/дрейф_replay_determinism_*.log` — ручной режим.
- **Нарушенный контракт:** §4.4 (Determinism as invariant).
- **Definition of Done:**
  1. Введён тест `test_tick_determinism_global.py`: для 100 случайных `TickState` (seeded) выполняется два прогона; `TickMutation` обязан быть побитово равным.
  2. Источники недетерминированности инвентаризированы: `dict` iteration order (использовать sorted keys), `set` (заменить на `frozenset` или `sorted(set(...))`), `time.time()` (уже изолирован через `get_clock()`), `random` (заменить на `KernelRNG`), `id()` (заменить на явные ID).
  3. Линтер `lint_wall_clock.py` расширен запретом `random.*` и `set()` в `app/services/npc/*` и `app/services/phases/*`.
  4. Результаты теста выводятся в отчёт `determinism_audit.json`.
- **Зависимости:** ENIGMA-ARCH-010.

### 5.4. P1 — Модификаторы и belief-система

---

#### ENIGMA-ARCH-009: Конфликт между R7 и R8 belief модификаторами

- **Категория:** Belief system
- **Severity:** P1
- **Статус верификации:** ✅ Подтверждено (`npc_tick_pipeline.py` строки 388–417, дословная цитата комментария)
- **Описание:** В коде есть комментарий: «R7 (событийный) и R8 (кристаллизованный) описывают частично одно и то же явление. Простое сложение даёт нелинейное усиление». Хотя есть доминант-логика (`if abs(_cv) > abs(_existing)`), это эвристика, а не формальное решение.
- **Локализация:** `backend/app/services/npc/npc_tick_pipeline.py`, строки 388–417:
  ```python
  # Сбор belief-модификаторов в изолированный слой (R7 + R8).
  # R7 (событийный) и R8 (кристаллизованный) описывают частично одно и то же
  # явление (страх/угроза от источника). Простое сложение даёт нелинейное
  # усиление — доминирующий сигнал должен поглощать слабый, а не удваивать его.
  ...
  # Dominant-take-all: берём значение с большей абсолютной величиной.
  if abs(_cv) > abs(_existing):
      _belief_layer_mods[_ck] = _cv
  ```
- **Нарушенный контракт:** Формальная модель belief-модификаторов; отсутствие каузы для выбора «доминанты».
- **Definition of Done:**
  1. Спроектирована формальная модель композиции R7/R8: либо `max_by_magnitude` (текущая эвристика, формализованная), либо `weighted_blend` с явными весами, либо `causal_attribution` (R7 каузально предшествует R8; R8 усиливает R7 только при подтверждении). Решение зафиксировано в ADR.
  2. Выбор модели обоснован и протестирован: `test_belief_composition_r7_r8.py` покрывает кейсы «R7 и R8 согласованы», «R7 и R8 противоречивы», «R7 сильнее R8», «R8 сильнее R7».
  3. Тест `modifier_commutativity_test.py` (существует) расширен до формального утверждения о коммутативности/ассоциативности композиции.
- **Зависимости:** ENIGMA-ARCH-013, ENIGMA-ARCH-016.

---

#### ENIGMA-ARCH-013: Отсутствие decay для EpistemicStore

- **Категория:** Belief system / Memory
- **Severity:** P1
- **Статус верификации:** ✅ Подтверждено (`epistemic_store.py` — есть `confidence`, нет методов `decay`/`age`/`expire`)
- **Описание:** Убеждения в `EpistemicStore` имеют `confidence`, но нет механизма их затухания со временем. NPC может помнить убеждение с `confidence=1.0` бесконечно, даже если прошло много игрового времени.
- **Локализация:** `backend/app/services/npc/epistemic_store.py` — только методы `get`, `get_all_for_agent`, `upsert`, `to_dict`, `from_dict`; поле `confidence` хранится без обновления.
- **Нарушенный контракт:** §4.6 (Decay as first-class citizen).
- **Definition of Done:**
  1. В `EpistemicStore` добавлен метод `decay(tick_delta: int, decay_rate: float)` либо декоратор, применяемый в конце тика.
  2. Параметр `decay_rate` конфигурируется per-proposition-type (visual → быстрый decay, eavesdrop → медленный, crystallized → нулевой).
  3. Убеждения с `confidence < threshold` автоматически вытесняются.
  4. Тест `test_epistemic_decay.py` покрывает сценарий: NPC получил убеждение с `confidence=1.0`, через N тиков `confidence < threshold`.
- **Зависимости:** ENIGMA-ARCH-009, ENIGMA-ARCH-016.

---

#### ENIGMA-ARCH-011: Memory weights применяются только при наличии LOS/sound

- **Категория:** Memory / Perception
- **Severity:** P1
- **Статус верификации:** ✅ Подтверждено (`npc_tick_pipeline.py` строки 257–270)
- **Описание:** В цикле обработки `memory_weights_map` NPC обновляет `relationship_cache` только для тех, кого видит или слышит. Это правильно, но может привести к ситуации, где NPC «забывает» о существах, которых давно не видел, даже если у него есть воспоминания о них.
- **Локализация:** `backend/app/services/npc/npc_tick_pipeline.py`, строки 257–270:
  ```python
  for _nearby_npc in state.nearby_npcs:
      ...
      _has_los = line_of_sight(...)
      _has_sound = sound_reach(15.0, ...) >= _dist
      if not _has_los and not _has_sound:
          continue
      ...
      state_l2.relationship_cache.setdefault(_nearby_id, {}).update(_npc_weights)
  ```
- **Нарушенный контракт:** Полная модель памяти; присутствует частичная амнезия при отсутствии восприятия.
- **Definition of Done:**
  1. Введено различие между `active_relationship` (обновляется при восприятии) и `remembered_relationship` (кристаллизованное убеждение, не требует восприятия).
  2. `relationship_cache` разделён: `active` (текущий тик, обновляется при LOS/sound) и `remembered` (исторический, убывает по decay-закону).
  3. DecisionHub имеет доступ к `remembered`, но с модификатором `uncertainty`, растущим со временем последнего восприятия.
  4. Тест `test_memory_persistence_without_perception.py`: NPC, не видевший другого NPC 100 тиков, всё ещё «помнит» его, но с пониженной уверенностью.
- **Зависимости:** ENIGMA-ARCH-013, ENIGMA-ARCH-016.

---

#### ENIGMA-ARCH-012: WillpowerGate не учитывает контекст наблюдения

- **Категория:** Will / Social physics
- **Severity:** P1
- **Статус верификации:** ✅ Подтверждено (`app/models/will.py` — `IntentPressureProfile` и `WillState` не содержат поля observer/witness/social_context)
- **Описание:** `WillpowerGate` вычисляет сопротивление аватара на основе `identity_pressure`, но не учитывает, наблюдает ли кто-то за действиями игрока. Аватар может сопротивляться по-разному в зависимости от социального контекста.
- **Локализация:** `backend/app/models/will.py` — DTO `IntentPressureProfile`, `WillState`, `WillResponseDTO`.
- **Нарушенный контракт:** Социальная физика; правдоподобие волевого поведения.
- **Definition of Done:**
  1. В `IntentPressureProfile` добавлено поле `observer_context: ObserverContext` (количество наблюдателей, их социальный статус, отношение к игроку).
  2. `WillpowerGate.compute()` использует `observer_context` как множитель: при свидетелях с высоким статусом сопротивление ниже (социальное давление), при отсутствии свидетелей — выше (анонимность).
  3. Тесты: `test_willpower_with_witnesses.py`, `test_willpower_solo.py`, `test_willpower_high_status_witness.py`.
- **Зависимости:** ENIGMA-ARCH-004, ENIGMA-ARCH-005.

### 5.5. P1 — Perception protocol и graceful degradation

---

#### ENIGMA-ARCH-006: Итерация по nearby_npcs без предварительной фильтрации

- **Категория:** Performance / Perception
- **Severity:** P1
- **Статус верификации:** ✅ Подтверждено (`npc_tick_pipeline.py` строка 257, `nearby_npcs` — список)
- **Описание:** В цикле обработки memory weights NPC итерирует по всему списку `state.nearby_npcs`, вычисляя LOS и sound для каждого. Это работает, но неэффективно: NPC «видит» список всех потенциальных соседей до того, как проверяет возможность их восприятия.
- **Локализация:** `backend/app/services/npc/npc_tick_pipeline.py`, строки 257–270; источник `nearby_npcs` — `dm_result.scene_context.nearby_npcs` (`npc_tick_contracts.py` строка 47).
- **Нарушенный контракт:** §4.7 (Single perception component for NPC) — фильтрация должна происходить до передачи в пайплайн.
- **Definition of Done:**
  1. Цикл заменён на итерацию по `perception.perceived_entities` (результат `NpcPerceptionCompiler`, см. ENIGMA-ARCH-005), уже отфильтрованному.
  2. LOS/sound вычисляются один раз на тик для каждой пары (NPC, target), кэшируются в `perception`.
  3. Тест производительности: при 50 NPC в локации время тика снижается минимум на 30% по сравнению с baseline.
- **Зависимости:** ENIGMA-ARCH-005, ENIGMA-ARCH-018.

---

#### ENIGMA-ARCH-017: Отсутствие graceful degradation при ошибках восприятия

- **Категория:** Error handling / Robustness
- **Severity:** P1
- **Статус верификации:** ✅ Подтверждено — множественные `try/except → logger.warning → continue` паттерны в `npc_tick_pipeline.py` (строки 194–197, 271–275, 292–295, 320–323, 495–498, 690–691, 734–735).
- **Описание:** Если `apply_perception_memory()` или `line_of_sight()` выбрасывает исключение, код логирует предупреждение и продолжает выполнение. Это может привести к ситуации, где NPC «не воспринимает» событие из-за ошибки, но игра продолжается без уведомления.
- **Локализация:** `backend/app/services/npc/npc_tick_pipeline.py` — например:
  ```python
  except Exception as _perc_mem_err:
      logger.warning(f"[MEMORY] hearing perception apply failed for {npc_id}: {_perc_mem_err}")
  continue
  ```
  Аналогично в строках 271–275, 292–295, 320–323, 495–498.
- **Нарушенный контракт:** §4.5 (No silent failures).
- **Definition of Done:**
  1. Введён `PerceptionError` — типизированное исключение с категориями (Spatial, Memory, Belief, Epistemic).
  2. Каждая категория имеет политику: `Spatial` → fail-у тика (NPC не должен работать без позиции); `Memory` → degrade (NPC продолжается без памяти, но эмитится событие в `EventBus`); `Belief` → degrade.
  3. Все `try/except` блоки в пайплайне заменены на `match/case` по категориям с явной политикой.
  4. Линтер `lint_silent_failures.py` (существует) расширен: любой `except Exception` без `raise` или эвента в `EventBus` блокирует CI.
- **Зависимости:** ENIGMA-ARCH-010, ENIGMA-ARCH-019.

---

#### ENIGMA-ARCH-018: Нет формального определения «соседства» (nearby)

- **Категория:** Spatial / Perception
- **Severity:** P1
- **Статус верификации:** ✅ Подтверждено — `nearby_npcs` приходит из `dm_result.scene_context.nearby_npcs`, фильтруется `_filter_by_visibility` в `dm_scene_builder.py`, но формального контракта нет.
- **Описание:** `state.nearby_npcs` формируется где-то вне `NpcTickPipeline`, но нет явного определения, что значит «nearby». Это может привести к несогласованности: NPC может быть «nearby» для одного тика, но не для другого, без объяснения почему.
- **Локализация:** `backend/app/services/npc/npc_tick_contracts.py` строка 47 (комментарий «Из dm_result.scene_context.nearby_npcs»), `backend/app/services/action/dm_scene_builder.py` строки 54–56 (`_filter_by_visibility`).
- **Нарушенный контракт:** §4.8 (Formal definition of «nearby»).
- **Definition of Done:**
  1. Введён контракт `NearbyContract`: `{ radius_m: float, location_id: str, lod_filter: LODLevel, perception_required: bool }`.
  2. `dm_scene_builder._filter_by_visibility` параметризован контрактом, а не магическими числами.
  3. Тест: один и тот же NPC при одинаковых условиях всегда входит или не входит в `nearby_npcs` одного игрока.
- **Зависимости:** ENIGMA-ARCH-005, ENIGMA-ARCH-006.

---

#### ENIGMA-ARCH-020: Нет формального протокола для «слуховых» событий

- **Категория:** Perception / Event protocol
- **Severity:** P1
- **Статус верификации:** ✅ Подтверждено (`npc_tick_pipeline.py` строка 188: жёстко закодированная строка `"(обрывки разговора)"`; `auditory_distortion_policy.py` существует, но вызывается только в UI-слое, не в NPC).
- **Описание:** Когда NPC слышит событие, он получает обобщённую информацию («обрывки разговора»), но нет формального определения, какую именно информацию он может извлечь из звука. Это может привести к несогласованности в том, что разные NPC «слышат» из одного и того же события.
- **Локализация:** `backend/app/services/npc/npc_tick_pipeline.py` строка 188:
  ```python
  _p_target = state.player_target_id or "player"
  _mem_evt = apply_perception_memory(
      None, state_l2, state.hub_event,
      npc_id, _p_target,
      "(обрывки разговора)", # Обобщённый текст для слуха
      ...
  )
  ```
  UI-слой: `backend/app/services/perception/auditory_distortion_policy.py` — distortion применяется только к UI.
- **Нарушенный контракт:** Каузальная замкнутость (разные NPC слышат разное из одного события без формальной модели); §4.3.
- **Definition of Done:**
  1. Введён `AuditoryEvent` DTO с полями: `event_id`, `source_id`, `audible_content: AudibleContent` (semantic_core, distortion_level, intelligibility).
  2. `AuditoryDistortionPolicy` перенесён из UI-слоя в perception-слой и применяется до DecisionHub (см. ENIGMA-ARCH-005).
  3. Все NPC, слышащие одно событие, получают `AuditoryEvent` с одинаковым `semantic_core`, но разным `intelligibility` в зависимости от расстояния/преград.
  4. Тест `test_auditory_event_consistency.py`: три NPC на разном расстоянии от одного звука получают разные `intelligibility`, но один и тот же `semantic_core`.
- **Зависимости:** ENIGMA-ARCH-005, ENIGMA-ARCH-017, ENIGMA-ARCH-019.

### 5.6. P2 — Персистентность и покрытие тестами

---

#### ENIGMA-ARCH-016: Persistence не покрывает все типы убеждений

- **Категория:** Persistence / Tests
- **Severity:** P2
- **Статус верификации:** ✅ Подтверждено — существует только `backend/tests/sandbox/persistence/test_crystallized_belief_persistence.py`; тестов для `EpistemicStore`, `relationship_cache`, `memory_weights_map` нет.
- **Описание:** Тест `test_crystallized_belief_persistence.py` проверяет только `CrystallizedBeliefStore`, но нет тестов для персистентности `EpistemicStore`, `relationship_cache`, или `memory_weights_map`.
- **Локализация:** `backend/tests/sandbox/persistence/test_crystallized_belief_persistence.py` — единственный; нет `test_epistemic_store_persistence.py`, нет `test_relationship_cache_persistence.py`, нет `test_memory_weights_persistence.py`.
- **Нарушенный контракт:** Завершённость модели персистентности; replay-детерминизм после рестарта.
- **Definition of Done:**
  1. Добавлены тесты: `test_epistemic_store_persistence.py`, `test_relationship_cache_persistence.py`, `test_memory_weights_persistence.py`, `test_expectation_store_persistence.py`.
  2. Каждый тест: состояние сохраняется в SQLite, инстанс перезагружается, состояние восстанавливается с точностью до полей.
  3. CI-гейт: PR без теста персистентности для нового типа состояния блокируется.
- **Зависимости:** ENIGMA-ARCH-003, ENIGMA-ARCH-013.

---

## 6. Группировка по архитектурным доменам

| Домен | Проблемы | Ключевой контракт |
|---|---|---|
| Epistemic boundary | 001, 002, 005, 007, 014 | NPC не читает глобальный state |
| Cognitive architecture | 003, 004 | ExpectationStore + PerceptionEngine интегрированы |
| Causal closure & verification | 008, 010, 015, 019 | Инварианты проверяются в CI |
| Belief system | 009, 011, 013 | Формальная модель композиции + decay |
| Will / Social physics | 012 | WillpowerGate контекстно-зависимый |
| Perception protocol | 006, 018, 020 | Единый perception component + формальный nearby + auditory protocol |
| Error handling | 017 | No silent failures |
| Persistence & tests | 016 | Покрытие всех типов состояния |

---

## 7. Этапы реализации (фазы)

### Фаза 0 — Стабилизация эпистемической границы (P0, 2–3 недели)

**Цель:** Устранить прямой доступ NPC к глобальному state и ввести type-level разделение.

**Проблемы:** ENIGMA-ARCH-001, 002, 014.

**Ключевые работы:**
- Введение типов `ObjectiveSceneState` / `SubjectivePerception`.
- Удаление `scene_state.get("npc_positions")` из `npc_tick_pipeline.py`.
- Расширение `lint_epistemic_boundary.py` до блокировки CI при нарушении.

**Критерии готовности фазы:**
- Линтер `lint_epistemic_boundary.py` зелёный в CI.
- Тест `test_telepathy_epistemic_barrier.py` расширен и зелёный.

### Фаза 1 — Единый perception component (P0, 2 недели)

**Цель:** Спроектировать и внедрить `NpcPerceptionCompiler`, формирующий субъективное восприятие NPC до DecisionHub.

**Проблемы:** ENIGMA-ARCH-005, 006, 018, 020.

**Ключевые работы:**
- Введение `NpcPerceptionCompiler` и `NearbyContract`.
- Перенос `AuditoryDistortionPolicy` из UI в perception-слой.
- Замена итерации по `nearby_npcs` на `perception.perceived_entities`.

**Критерии готовности фазы:**
- В пайплайне NPC единственный источник восприятия — `NpcPerceptionCompiler`.
- `PerceptionProjector` явно помечен UI-only.

### Фаза 2 — Завершение когнитивной архитектуры (P0, 3–4 недели)

**Цель:** Интегрировать `ExpectationStore` и `PerceptionEngine` в критический путь.

**Проблемы:** ENIGMA-ARCH-003, 004.

**Ключевые работы:**
- Реализация шага `expectation_evaluation` (prediction_error → drive_modifiers).
- Реализация шага `social_status_evaluation` (status → epistemic_modifiers).
- Тесты на attribution и drive-modifier attribution.

**Критерии готовности фазы:**
- Оба TODO в `npc_tick_pipeline.py` удалены.
- Тесты `test_expectation_prediction_error.py` и `test_perception_engine_modifiers.py` зелёные.

### Фаза 3 — Каузальные инварианты и детерминизм (P1, 3 недели)

**Цель:** Ввести автоматическую проверку каузальной замкнутости и детерминизма в CI.

**Проблемы:** ENIGMA-ARCH-008, 010, 015, 019.

**Ключевые работы:**
- Введение `CausalClosureInvariant`, `EpistemicBoundaryInvariant`, `DeterminismInvariant`.
- Обёртывание `SUPERBOX`-сценариев assertion-layer.
- Тест `test_tick_determinism_global.py` на 100 seeded-состояний.

**Критерии готовности фазы:**
- Все инвариантные проверки зелёные в CI.
- Отчёт `determinism_audit.json` генерируется на каждом PR.

### Фаза 4 — Belief-система и decay (P1, 2 недели)

**Цель:** Формализовать композицию R7/R8 и ввести decay для всех накопленных величин.

**Проблемы:** ENIGMA-ARCH-009, 011, 013.

**Ключевые работы:**
- ADR по формальной модели композиции R7/R8.
- Decay для `EpistemicStore`, разделение `active`/`remembered` relationship.

**Критерии готовности фазы:**
- ADR принят и реализован.
- Тесты `test_belief_composition_r7_r8.py`, `test_epistemic_decay.py`, `test_memory_persistence_without_perception.py` зелёные.

### Фаза 5 — WillpowerGate и social context (P1, 1 неделя)

**Цель:** Добавить `observer_context` в `WillpowerGate`.

**Проблемы:** ENIGMA-ARCH-012.

**Ключевые работы:**
- Расширение `IntentPressureProfile` полем `observer_context`.
- Тесты с различными социальными контекстами.

### Фаза 6 — Error handling и graceful degradation (P1, 2 недели)

**Цель:** Устранить silent failures и ввести типизированные политики обработки ошибок.

**Проблемы:** ENIGMA-ARCH-017.

**Ключевые работы:**
- Введение `PerceptionError` с категориями.
- Замена `try/except` на `match/case` по категориям.
- Расширение `lint_silent_failures.py`.

### Фаза 7 — Персистентность (P2, 1 неделя)

**Цель:** Покрыть тестами персистентность всех типов состояния.

**Проблемы:** ENIGMA-ARCH-016.

---

## 8. Приоритизация (сводная)

| Приоритет | ID проблем | Обоснование |
|---|---|---|
| **P0** | 001, 002, 003, 004, 005, 007, 014, 019 | Нарушают фундаментальные заявленные принципы (epistemic isolation, causal closure); блокируют развитие когнитивной архитектуры; подрывают доверие к детерминизму |
| **P1** | 006, 008, 009, 010, 011, 012, 013, 015, 017, 018, 020 | Снижают правдоподобие, затрудняют верификацию, создают race conditions и silent failures |
| **P2** | 016 | Долг по покрытию тестов; не блокирует разработку, но повышает риск регрессий |

---

## 9. Сквозные работы (cross-cutting)

Независимо от фаз, архитектор должен инициировать следующие сквозные работы:

1. **Расширение линтеров.** Существующие `lint_epistemic_boundary.py`, `lint_silent_failures.py`, `lint_kernel_rng.py`, `lint_wall_clock.py`, `lint_position_mutation.py`, `lint_domain_purity.py` должны быть объединены в pre-commit + CI gate с единым отчётом.
2. **Унификация типов состояния.** Ввести реестр `DTO Registry` (упоминается в `docs/DTO Registry (Реестр контрактов).md`) как единственный источник правды для всех типов состояния.
3. **Документация архитектурных контрактов.** Обновить `docs/АРХИТЕКТУРНЫЙ_УСТАВ_ENIGMA.md` и `docs/00_CAUSAL_CONTRACT_v2.0.md` разделами, явно фиксирующими принципы из §4 настоящего ТЗ.
4. **ADRs.** На каждое архитектурное решение, принимаемое в рамках реализации ТЗ, должен быть заведён ADR по существующему шаблону `docs/audits/ADR-*_IMPACT.md`.

---

## 10. Контракты и ограничения

При реализации ТЗ обязательны следующие ограничения:

1. **Никаких inline-скриптов генерации.** Все изменения применяются через код в `app/services/...`; test-fixtures и тесты живут в `backend/tests/...`.
2. **Совместимость с существующими ADR.** Реализация не должна нарушать уже принятые ADR без явного ADR-ревизии (ADR-O-211, ADR-048, ADR-O-355 и др.).
3. **Совместимость с SUPERBOX-сценариями.** Существующие `SUPERBOX`-сценарии должны проходить без модификации (или с минимальной, документированной в ADR).
4. **Не вводить новые источники недетерминизма.** Запрещены `random.*`, `time.time()` (кроме `get_clock()`), `id()`, итерация по `set`/неупорядоченному `dict` без `sorted()`.
5. **Персистентность по умолчанию.** Любое новое состояние, способное пережить тик, должно иметь SQLite-персистентность с первого дня.

---

## 11. Критерии готовности (глобальные)

ТЗ считается реализованным, когда:

1. Все 20 проблем имеют статус «закрыто» по их индивидуальным Definition of Done.
2. CI зелёный на всех инвариантных проверках (`CausalClosureInvariant`, `EpistemicBoundaryInvariant`, `DeterminismInvariant`).
3. Все TODO-комментарии из `npc_tick_pipeline.py` (строки 369–377, 701, 916) удалены либо заменены на ADR-ссылки.
4. `lint_epistemic_boundary.py` не находит ни одного `scene_state.get("npc_positions")` в `app/services/npc/*`.
5. Тесты персистентности покрывают все типы состояния (см. ENIGMA-ARCH-016).
6. Документ `АРХИТЕКТУРНЫЙ_УСТАВ_ENIGMA.md` обновлён и отражает реализованные принципы.
7. Прогон 100 seeded-`TickState` даёт побитово одинаковый `TickMutation` (см. ENIGMA-ARCH-015).

---

## 12. Риски и смягчения

| Риск | Вероятность | Влияние | Смягчение |
|---|---|---|---|
| Введение `SubjectivePerception` сломает legacy-тесты | Высокая | Высокое | Поэтапная миграция: тип вводится как alias, затем ужесточается |
| Глобальный determinism-test выявит накопленные нарушения | Высокая | Высокое | Сначала inventory источников недетерминизма, потом исправление по priority |
| R7/R8 формализация приведёт к регрессиям в социальных сценариях | Средняя | Среднее | Тесты `modifier_commutativity_test.py` и `modifier_composition_test.py` — обязательный гейт |
| Decay для EpistemicStore приведёт к потере «долгой памяти» NPC | Средняя | Низкое | Дифференциация `decay_rate` по типам proposition; crystallized beliefs не decay |
| Перенос AuditoryDistortionPolicy в perception-слой сломает UI-проекцию | Низкая | Среднее | Сохранить UI-вызов для player-perception, добавить NPC-perception как параллельный путь |
| Race conditions в transfer-queue не воспроизводятся в тестах | Средняя | Высокое | Ввести `TraversalFSMProbe` с псевдо-случайным порядком тиков локаций |

---

## 13. Метрики и верификация

| Метрика | Целевое значение | Источник данных |
|---|---|---|
| Количество `scene_state.get("npc_positions")` в `app/services/npc/*` | 0 | `lint_epistemic_boundary.py` |
| Количество `except Exception` без `raise`/event в пайплайне | 0 | `lint_silent_failures.py` |
| Покрытие SUPERBOX-инвариантов в CI | 100% | `SUPERBOX/causal_validation.py` |
| Determinism test pass rate | 100% seeded-`TickState` | `test_tick_determinism_global.py` |
| Покрытие персистентности по типам состояния | 100% | `tests/sandbox/persistence/` |
| Количество TODO в `npc_tick_pipeline.py` | 0 | grep `TODO` |
| Среднее время тика при 50 NPC в локации | ≤ baseline × 0.7 после Фазы 1 | `scripts/check_population_flow.py` |

---

## 14. Приложения

### Приложение А. Сводная таблица верификации проблем

| ID | Файл | Строки | Статус верификации |
|---|---|---|---|
| 001 | `backend/app/services/npc/npc_tick_pipeline.py` | 174, 51, 77–78 | ✅ Подтверждено |
| 002 | `backend/app/services/npc/npc_tick_pipeline.py` | 1047–1053 | ✅ Подтверждено (комментарий ADR-048) |
| 003 | `backend/app/services/npc/npc_tick_pipeline.py` | 369–372 | ✅ Подтверждено (TODO) |
| 004 | `backend/app/services/npc/npc_tick_pipeline.py` | 374–377 | ✅ Подтверждено (TODO) |
| 005 | `backend/app/services/perception/perception_projector.py` | 16–21 | ✅ Подтверждено (UI-only) |
| 006 | `backend/app/services/npc/npc_tick_pipeline.py` | 257–270 | ✅ Подтверждено |
| 007 | `backend/app/services/npc/npc_tick_pipeline.py` | 76–78 | ✅ Подтверждено |
| 008 | `backend/app/services/tick_orchestrator.py` | 89, 345, 497, 739, 914 | ✅ Подтверждено |
| 009 | `backend/app/services/npc/npc_tick_pipeline.py` | 388–417 | ✅ Подтверждено (дословный комментарий) |
| 010 | `backend/tests/sandbox/SUPERBOX/` | — | ✅ Подтверждено (нет invariant-гейта) |
| 011 | `backend/app/services/npc/npc_tick_pipeline.py` | 263–270 | ✅ Подтверждено |
| 012 | `backend/app/models/will.py` | — | ✅ Подтверждено (нет `observer_context`) |
| 013 | `backend/app/services/npc/epistemic_store.py` | весь файл | ✅ Подтверждено (нет decay) |
| 014 | `backend/app/domain/tick.py`, `npc_tick_pipeline.py` | — | ✅ Подтверждено (общие типы) |
| 015 | `backend/tests/test_cfrm_models.py` | 196 | ✅ Частично (узкий тест) |
| 016 | `backend/tests/sandbox/persistence/` | — | ✅ Подтверждено (1 тест) |
| 017 | `backend/app/services/npc/npc_tick_pipeline.py` | 194, 271, 292, 320, 495, 690, 734 | ✅ Подтверждено (7 мест) |
| 018 | `backend/app/services/npc/npc_tick_contracts.py`, `dm_scene_builder.py` | 47, 54–56 | ✅ Подтверждено |
| 019 | `backend/tests/sandbox/system/test_causal_closure.py` | — | ✅ Частично (сценарий, не инвариант) |
| 020 | `backend/app/services/npc/npc_tick_pipeline.py`, `perception/auditory_distortion_policy.py` | 188 | ✅ Подтверждено (hardcoded + UI-only) |

### Приложение Б. Источники

- Архив исходного кода: `Enigma-V.0.5.3.8.2_-.zip`
- Корневая директория проекта: `Enigma-V.0.5.3.8.2_-/`
- Существующие ADR: `docs/audits/ADR-*_IMPACT.md`
- Архитектурный устав: `docs/АРХИТЕКТУРНЫЙ_УСТАВ_ENIGMA.md`
- Каузальный контракт: `docs/00_CAUSAL_CONTRACT_v2.0.md`
- Реестр DTO: `docs/DTO Registry (Реестр контрактов).md`
- Существующие ТЗ: `docs/Почти Актуальные TZ/`
