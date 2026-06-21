# ENIGMA / The Fool
## Chronicle of a Distributed Reality Simulation (2026-03-06 -> 2026-05-23)

ENIGMA больше не является "игрой с ИИ-диалогом".
Это проект по построению **distributed reality simulation**, где:
- истина распределена по доменам и фазам,
- состояние рождается из причинности, а не из текста,
- LLM озвучивает реальность, но не определяет ее.

---

## 1) Origin (March 6-19, 2026): from local DM to stateful loop

**Ветки/вехи:** `V.0.1_alfa1`, `V.0.2_alfa1`, `V.0.3A_alfa1`.

Система прошла базовый переход:
- от "LLM-оркестратора" к рабочему игровому циклу,
- от статических реплик к состоянию NPC,
- от линейного ответа к модели поведения с памятью и психикой.

Это был этап появления **первичного ядра причинности**: сначала считать мир, потом говорить.

---

## 2) Resuscitation (March 22 - April 25): runtime as a living process

**Ветки/вехи:** `V.0.4A_alfa2` -> `V.0.5.1.3`.

Главная трансформация:
- "снэпшотный" код превращен в time-driven runtime,
- добавлены контуры памяти/сцены/сервисной декомпозиции,
- подготовлена почва для фазового оркестратора.

Проект перестал быть набором механик и начал вести себя как **процесс во времени**.

---

## 3) Orchestrator Surgery (April 26 - May 1): decomposition of control

**Ветки/вехи:** `V.0.5.1.4` -> `V.0.5.2.1`.

Ключевой сдвиг:
- управление собралось вокруг `TickOrchestrator`,
- появились жесткие фазовые границы,
- мутации состояния стали продвигаться через контролируемые контракты.

Это первая точка, где архитектура выбрала **управляемую причинность вместо импровизации**.

---

## 4) Ontology Breakpoint (May 2-9): typed domains, narrative layer, temporal law

**Ветки/вехи:** `V.0.5.2.2` -> `V.0.5.2.9`.

Что изменилось по сути:
- `StateDeltas v2` и доменная типизация изменений,
- narrative/presentation отделены от state-truth,
- время перестало быть счетчиком и стало физикой процесса.

Здесь ENIGMA разошлась с типовой RPG-архитектурой: не "механики+контент", а **онтология+редукция+интеграция**.

---

## 5) New Reality (May 10-14): CFRM and observed causality

**Ветки/вехи:** `V.0.5.3.0.1` -> `V.0.5.3.0.6`.

Сформирован текущий вектор:
- CFRM (локальные причинные поля),
- PerceptualKernel и геометрия решения,
- social pressure как деформация utility-space,
- sandbox/observatory как проверка причинности, а не только состояния.

Это переход к **наблюдаемой причинности**: симуляция истинна там, где есть каузальное наблюдение.

---

## 6) Space and Time (May 21-23): The Fool as embodied simulation

**Ветки/вехи:** `V.0.5.3.1.1_Пространство_и_время` -> `V.0.5.3.1.3_Пространство_и_время_3`.

Текущий этап переводит The Fool из набора игровых намерений в проверяемый embodied runtime:
- player turn больше не теряет реальный `scene_state`;
- NPC получают пространственный контекст через `npc_positions`, `position` и `SpatialService`;
- воля и директивы начинают учитывать социальное давление, страх, доверие и профессиональный долг;
- когнитивные решения NPC могут порождать `MovementIntent`, а не только текст или внутренний state;
- LOD0/LOD1 movement проходит через арбитраж, чтобы микро-реакции не уничтожали маршрут;
- память сохраняет сырое событие, если смысловая сводка ещё не кристаллизована.

Практический смысл для игры The Fool:
мир начинает отвечать не только репликой, но телом. Приказ "подойди", страх, служебная роль, позиция игрока и координаты сцены становятся частью одной причинной цепи: **текст -> intent -> directive pressure -> will/legitimacy -> decision -> movement -> scene mutation -> projection**.

---

## Architectural Point-of-No-Return (ADR landmarks)

Ключевые ADR, после которых проект стал другим:
- `ADR-013`: typed domain deltas (`StateDeltas v2`).
- `ADR-015`: physiology как давление на все домены, не "режим боя".
- `ADR-025`: CFRM и локальная редукция причинности.
- `ADR-031`: WillpowerGate (воля как инерционная динамика, не бинарный флаг).
- `ADR-043`: social directives как pressure field, а не прямые команды.
- `ADR-047`: observed causality, запрет ретро-симуляции.
- `ADR-048`: single spatial authority.
- `ADR-049`: DecisionContext geometry.
- `ADR-050`: causal observatory.
- `ADR-051` (через impact/task документы): de-godification LifeEngine.

---

## What ENIGMA Is Now

Текущее определение:

```text
Distributed Reality Simulation Engine
where:
  LLM = Voice Layer
  Python = Causal Core
```

Базовый поток:

```text
Input -> Intent Compression -> Event -> Pressure -> Decision Geometry
-> Domain Deltas -> Layered Reduction -> Snapshot Projection -> Persistence
```

Границы:
- frontend не владеет истиной;
- state меняется только через доменные контракты;
- события не обходят фазовый протокол;
- тестируется причинная замкнутость, а не только финальные значения.

---

## Repository Anchors (source-of-truth files)

- `docs/ADR (Architecture Decision Records).md`
- `docs/MUTATIONS.md`
- `docs/DTO Registry (Реестр контрактов).md`
- `docs/CAUSAL_CONTRACT.md`
- `docs/АРХИТЕКТУРНЫЙ_УСТАВ_ENIGMA.md`
- `docs/audits/ADR-048_IMPACT.md`
- `docs/audits/ADR-049_IMPACT.md`
- `docs/audits/ADR-050_IMPACT.md`
- `docs/audits/ADR-051_IMPACT.md`
- `docs/INFO/ENIGMA_global_table.md`

## Future Vector: The Fool, docs/Tasks and docs/audits

- `docs/Tasks` — оперативная карта развития. Здесь архитектурные идеи превращаются в задачи, контракты и ADR, которые задают будущее ENIGMA.
- `docs/audits` — enforcement layer: impact-отчёты, архитектурные показатели и ограничения, которые проверяют правильность изменений.
- `The Fool` в ENIGMA не просто игровая тема. Это шаблон мышления: мир задаётся не сюжетом, а структурой правил, причинностью и пространством, в котором LLM остаётся голосом, а не судьёй.
- Этот проект развивается так, чтобы будущий геймплей шёл от внутренних контрактов и наблюдаемой причинности, а не от внешнего повествования.

### V.0.5.3.0.8_ПЕСОЧНИЦЫ_5 (точка сборки)

В текущей песочнице зафиксирован следующий “вектор будущего”, который следует напрямую из обновлений `docs/Tasks` и `docs/audits`:
- **Legitimacy Gate → Directive Interpretation → Initiative Suppression** как единый state-механизм “молчания/сопротивления” или “обслуживания” директив.
- **Authoritative Spatial Spine (ADR-048)**: дистанции/позиции становятся консистентным источником через `SpatialQueryService`, а presentation — только проекция.
- **LOD0 Reactive Micro-Locomotion**: минимально-живой movement-контур, который не ломает причинность и не расходится между decision/perception/snapshot.

См. также:
- `COMPARISON_REPORT/COMPARISON_REPORT_V.0.5.3.0.8_ПЕСОЧНИЦЫ_5.md`


---

## Current Strategic Tension

Главный конфликт следующего шага:
- удержать causality-first архитектуру,
- не скатиться обратно в script-first поведение при росте embodied-фич,
- довести directive obedience, movement arbitration и player/NPC spatial projection без второго источника истины.

Если этот баланс удержан, ENIGMA останется симуляцией реальности.
Если нет, она откатится в RPG-пайплайн с иллюзией причинности.

---

## Current Snapshot: V.0.5.3.1.3_Пространство_и_время_3

Ключевая сборка дня:
- causal bridge: `DecisionHub`/`LifeEngine` -> `MovementIntent` -> `MovementEngine` -> `SceneStateManager`;
- ADR-048 enforcement: единый путь получения `SpatialService` через резолвер оркестратора;
- The Fool runtime: игрок не рендерится как NPC, но присутствует как spatial actor;
- LegitimacyGate: MOVE/ORDER/HALT входят в контур воли и социального давления;
- sandbox coverage: causal bridge, LOD arbitration, directive obedience, memory phenomenology;
- dependency/causal diagnostics: добавлены графы зависимостей, APS и causal audit scripts.

См. новый разбор:
- `COMPARISON_REPORT/COMPARISON_REPORT_V.0.5.3.1.2_Пространство_и_время_2_vs_V.0.5.3.1.3_Пространство_и_время_3.md`

---

## Current Snapshot: V.0.5.3.1.4_Чиним_НЕРВЫ_1

Сборка фиксирует нервный слой The Fool: момент, где текстовая воля игрока, точная позиция тела, социальное давление NPC и физическое движение должны проходить через один контур.

Ключевые изменения:
- `llama-server` больше не убивается чужим backend-процессом: shutdown завершает только тот сервер, который был поднят этим приложением;
- `will_conflict_data` проброшен из backend API во frontend как данные для Resistance Medium;
- frontend обновляет `avatar_state` после действия и может заражать поле ввода импульсом конфликта воли;
- реактивный `APPROACH` резолвит игрока через `local_position`, а не только через протухший macro node;
- `MovementIntent` получил `target_local_xy` и защиту от двойной обработки;
- `MovementEngine -> SceneChange -> SceneStateManager` передает точные координаты цели, если они есть;
- `npc_orchestration` перестал исполнять movement напрямую: исполнение возвращено владельцу `TickOrchestrator`;
- `SceneStateManager` восстанавливает невалидный `from_xy` из текущего узла и синхронизирует позиционную истину игрока в `npc_positions`;
- архитектурные документы сжаты в доменно-каузальный формат, чтобы уменьшить шум для следующих проходов.

Практический смысл:
The Fool стал ближе к embodied simulation: NPC теперь не просто "соглашается" или "отвечает", а получает более точный пространственный адрес для реакции на игрока. Главный остаточный риск не в отсутствии фич, а в ownership: позиция игрока, `player_spatial`, `npc_positions.player`, `MovementIntent` и frontend projection все еще требуют жесткого единого контракта.

См. новый разбор:
- `COMPARISON_REPORT/COMPARISON_REPORT_V.0.5.3.1.3_Пространство_и_время_3_vs_V.0.5.3.1.4_Чиним_НЕРВЫ_1.md`

---

## Current Snapshot: V.0.5.3.1.7_ВЕЛИЧИЕ_НЕБА_И_ЗЕМЛИ_2

Сборка фиксирует переход ENIGMA/The Fool от embodied runtime к более явному удержанию identity, projection, spatial compilation and scheduler readiness.

Ключевые изменения:
- добавлен explicit identity контур: `identity_events`, `l1_chronicle`, `drive_resolver`, `architecture/identity.yaml`;
- DecisionHub разгружен в локальные decision-модули: profile math, risk, relationship profile, social deltas;
- добавлены `EventCompiler`, `ProjectionEngine`, `WorldSnapshot` and `ThickSceneChange` как явные transform/projection объекты;
- spatial runtime усилен `SpatialRegistry`, backend graph compilation and frontend spatial compilation gateway/orchestrator;
- frontend получил world context, menu/effects/i18n and renderer updates for more observable play;
- sandbox/test surface вырос: calibration, SUPERBOX, causal kernel, projection engine, event compiler, social phase tests;
- repository mass compressed: файлов стало больше, но общий текстовый объем уменьшился за счет удаления/архивации старого report/reference шума.

Размер относительно предыдущей сохраненной ветки `V.0.5.3.1.6_ВЕЛИЧИЕ_НЕБА_И_ЗЕМЛИ_1`:

|Metric|Previous|Current|Delta|
|---|---:|---:|---:|
|Project files|2,760|2,848|+88|
|Text/source files|1,167|1,246|+79|
|Total text lines|239,507|154,071|-85,436|
|Python files|442|485|+43|
|Markdown files|561|589|+28|

Практический смысл:
The Fool получил более сильный контур `state -> compiled event -> projection -> spatial observation -> frontend/DM output`. Это не просто объем работы; это укрепление ownership между реальностью backend, картой пространства, наблюдаемой сценой и голосом LLM.

Главный риск следующего шага:
не дать projection, frontend spatial compiler или scheduler стать вторыми источниками истины. Execution должен исполнять фазы, Projection должен читать, DecisionHub должен оценивать.

Подробный DNA-разбор:
- `docs/INFO/ENIGMA_ARCHITECTURAL_DNA.md`
