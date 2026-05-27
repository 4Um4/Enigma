# Сравнение за день: V.0.5.3.1.2_Пространство_и_время_2 -> V.0.5.3.1.3_Пространство_и_время_3

## 0. Метод

Сравнение сделано не по объему строк, а по функциональным узлам pipeline.

- База: `origin/V.0.5.3.1.2_Пространство_и_время_2`
- Новая ветка: `V.0.5.3.1.3_Пространство_и_время_3`
- Дата фиксации: 2026-05-23
- Трекнутый diff до документирования: 58 файлов, около 1280 добавлений и 4840 удалений.
- Новые нетрекнутые артефакты до сохранения: 58 файлов.

Большая часть "удалений" не является потерей функциональности: старые ТЗ/отчеты и временные документы перенесены/уплотнены, а ценное смещение дня находится в runtime-связках: воля, директивы, движение, spatial authority, тесты и диагностика.

---

## 1. PIPELINE_OBJECT

Главный объект дня:

```text
Player/NPC embodied action
```

Рабочая цепь:

```text
raw text / semantic action
-> IntentParametersDTO / EventDTO
-> DirectiveInterpretationSubscriber
-> Will / LegitimacyGate
-> DecisionHub / LifeEngine.tick_decisions
-> MovementIntent
-> MovementEngine
-> SceneChange
-> SceneStateManager.apply_changes
-> world/session/frontend projection
```

Это уже не "NPC сказал" и не "NPC имеет внутреннее состояние". Это контур, где социальная команда, страх, долг, позиция в сцене и движение начинают проходить через один наблюдаемый pipeline.

---

## 2. OWNER

| Контур | OWNER | Что изменилось |
|---|---|---|
| Пространственная истина | `SpatialService` / `SpatialQueryService` / `SceneStateManager` | Оркестратор получил единый `_resolve_spatial_service()`. |
| Решение NPC | `DecisionHub` через `LifeEngine` и `npc_tick_pipeline` | Решения могут порождать movement intents, а не только communication/state deltas. |
| Социальная директива | `DirectiveInterpretationSubscriber` | MOVE/ORDER/HALT идут через legitimacy, fear/trust и профессиональный archetype. |
| Воля | `backend/app/services/will.py` | Социальные и пространственные команды учитываются как pressure profile. |
| Проекция | frontend / world snapshot | Игрок участвует в spatial truth, но не рендерится как NPC. |
| Проверка | sandbox tests / diagnostics | Добавлены causal bridge, LOD arbitration, phenomenology tests, dependency graphs. |

---

## 3. CREATE -> READ -> TRANSFORM -> APPLY -> COMMIT -> PROJECT

### CREATE

- `phase_1_input.py` сохраняет `UNCERTAIN` как явный semantic action, а не превращает его в отсутствие действия.
- `DirectiveInterpretationSubscriber` резолвит цель по `npc_id` или `id`.
- `MemoryManager` сохраняет raw реальность (`raw_input`/`content`), если summary отсутствует.

### READ

- `GameLoop` пробрасывает реальный `scene_state` в `shared_context`.
- `build_spatial_data_for_dm()` читает `npc_positions`, `player_distances` и координаты игрока.
- `scene_init.py` сохраняет нулевое время как валидное значение, а не теряет его из-за truthy-проверок.

### TRANSFORM

- `DirectiveInterpretationSubscriber` превращает MOVE-директивы в obedience/resistance через legitimacy.
- `Will` получает pressure profile для `player_social`, `player_moves`, `move`, `approach`, `halt`, `order`.
- `LifeEngine.tick_decisions()` трансформирует APPROACH/FLEE в `MovementIntent`.

### APPLY

- `TickOrchestrator` выполняет cognitive movement через `MovementEngine`.
- LOD0/LOD1 intents сортируются до исполнения: macro-маршрут идет раньше micro-коррекции.
- `SceneStateManager` восстанавливает координаты NPC, если active traversal есть, а координат нет.

### COMMIT

- `SceneStateManager.apply_changes()` остается точкой применения spatial changes.
- `world_tick.json`, `Open_road.json`, relationship truth обновлены как runtime state.

### PROJECT

- `frontend/game_screen.py` больше не рисует игрока как NPC.
- `DataManager` enforced `location_id` при сохранении локации.
- README и Architectural DNA обновлены под текущий фактический контур The Fool.

---

## 4. FAIL_STAGE предыдущего состояния

FAIL_STAGE: `TRANSFORM -> APPLY`

Причина:

`DecisionHub` и social/directive logic могли произвести смысловое решение, но spatial application не был гарантирован как часть того же causal chain. В player-turn также был риск пустого или неактуального `scene_state`, из-за чего DM/spatial слой видел мир без NPC или без корректной позиции игрока.

Симптомы, которые это объясняет:

- NPC не подходил, хотя директива была распознана.
- DM мог получать пустой nearby-NPC контекст.
- Игрок мог попадать в `npc_positions`, но frontend мог трактовать его как NPC.
- `LifeEngine` возвращал decisions/comms, но не возвращал movement intents.
- LOD0 micro-механика могла конфликтовать с LOD1 маршрутом.

---

## 5. Что реально было сделано за день

### 5.1 Causal Bridge: cognition -> movement

`LifeEngine.tick_decisions()` теперь возвращает три потока:

```text
decisions, communication_intents, movement_intents
```

Ценность:
NPC может не только "решить", но и физически начать действовать через тот же tick. Это важнее строк кода: появилось новое поведенческое звено.

Оценка функции: крупная системная функция.

### 5.2 ADR-048 Spatial Authority Resolver

`TickOrchestrator._resolve_spatial_service()` централизует получение `SpatialService`.

Ценность:
движение игрока, idle NPC и cognitive movement читают один spatial authority path. Это снижает риск второго источника пространственной истины.

Оценка функции: архитектурная стабилизация.

### 5.3 LegitimacyGate для приказов движения

`DirectiveInterpretationSubscriber` теперь учитывает:

- `npc_id` и `id`;
- `social_stats.fear_of_player`;
- `drives.fear`;
- `social_stats.trust`;
- `psyche.loyalty_true`;
- `_archetype` для service-role obedience.

Ценность:
"подойди" становится не скриптовой командой, а социальным давлением. NPC может подчиниться, сопротивляться или изменить инициативу по причинам, а не по if-ветке.

Оценка функции: новая социально-поведенческая механика.

### 5.4 Will pressure для социальных и spatial-команд

`will.py` получил pressure profile для `move`, `approach`, `halt`, `order`.

Ценность:
воля перестала быть слепой к командам перемещения. Это закрывает дыру между directive interpretation и внутренней агентностью NPC.

Оценка функции: расширение модели воли.

### 5.5 Player as spatial actor, not NPC presentation

Игрок теперь корректнее присутствует в spatial truth:

- `scene_init.py` переносит `player_spatial.position` в `npc_positions.player.position`;
- `frontend/game_screen.py` фильтрует `player` из NPC-render loop;
- `build_spatial_data_for_dm()` исключает `player` из nearby NPC.

Ценность:
игрок нужен для расстояний, целей и movement, но не должен ломать NPC-проекцию.

Оценка функции: исправление ownership projection.

### 5.6 LOD0/LOD1 arbitration

Добавлен и протестирован порядок:

```text
MacroMovementGoal / LOD1 -> LocalSteeringGoal / LOD0
```

Ценность:
микро-уклонение не уничтожает маршрут. Это делает movement-layer пригодным для роста, а не только для одиночной демо-сцены.

Оценка функции: runtime safety для движения.

### 5.7 Memory truth preservation

`MemoryManager` больше не теряет событие, если нет готового summary.

Ценность:
память не обязана ждать красивой смысловой сводки; она сохраняет raw reality. Это поддерживает принцип: LLM кристаллизует смысл, но не является единственным источником события.

Оценка функции: защита memory pipeline.

### 5.8 Diagnostic and audit layer

Добавлены:

- dependency graphs: `deps.json`, `deps_compressed.json`, `deps_stats.json`, SVG-графы;
- `backend/analysis/cds_map.md`;
- scripts: `APS.py`, `causal_audit.ps1`, `smoke_test.ps1`, `clean_cache.ps1`;
- git hooks для cache hygiene.

Ценность:
проект получил инструменты контроля связности и санитарии, а не только ручную интуицию.

Оценка функции: observability/governance increment.

### 5.9 Sandbox and phenomenology coverage

Добавлены тесты:

- causal bridge integration;
- LOD arbitration;
- directive obedience pipeline;
- will absolute obedience / directive conflict;
- memory fixation / truth decay / absurd fixation.

Ценность:
появились проверки не только финальных значений, но и поведенческих законов: подчинение, сопротивление, память, движение.

Оценка функции: тестовый каркас для simulation laws.

---

## 6. Сколько новых функций было добавлено

Не считая документацию и диагностические артефакты, добавлено примерно:

1. Causal bridge `DecisionHub/LifeEngine -> MovementIntent -> MovementEngine`.
2. Central spatial service resolver в `TickOrchestrator`.
3. LegitimacyGate enhancement для movement/order-директив.
4. Will pressure profile для социальных и spatial-команд.
5. Player spatial actor без NPC-render pollution.
6. LOD0/LOD1 movement arbitration.
7. Memory raw-event preservation.
8. Data/location schema enforcement для `location_id`.
9. Dependency/causal diagnostics and hooks.
10. Sandbox/phenomenology validation suite.

Итого: **около 8-10 смысловых функций/механик**, из них **5-6 напрямую влияют на gameplay/runtime The Fool**, остальные усиливают проверяемость и архитектурную управляемость.

---

## 7. Ценность для The Fool

Главная ценность дня:

```text
The Fool начал становиться embodied game,
а не интерфейсом поверх текстовой симуляции.
```

Что стало важным:

- игрок имеет позицию как физический объект;
- NPC слышит директиву как социальный акт;
- воля оценивает давление команды;
- DecisionHub остается вычислителем, но движение применяется через spatial pipeline;
- frontend видит результат, а не изобретает реальность;
- tests начинают фиксировать законы поведения.

Это шаг от "LLM рассказывает, что NPC подошел" к "система провела NPC через причину, решение, движение и commit".

---

## 8. Риски

### R1. Diagnostic fallback может стать скрытой архитектурой

В коде есть аварийная сборка `SpatialService` и диагностические fallback-ветки.

Риск:
если они останутся постоянным путем, ADR-048 ослабнет.

Контроль:
считать их evidence collectors и постепенно заменить гарантированной инъекцией через GameLoop/NpcTickServices.

### R2. `LifeEngine.tick_decisions()` расширил контракт

Было:

```text
decisions, communication_intents
```

Стало:

```text
decisions, communication_intents, movement_intents
```

Риск:
не все consumers могут быть обновлены.

Контроль:
поиск всех вызовов `tick_decisions()` и регрессионный тест полного tick loop.

### R3. Social obedience может стать слишком сильной

Профессиональный archetype повышает legitimacy до 0.7 для service NPC.

Риск:
служебные NPC станут слишком послушными и потеряют agency.

Контроль:
добавить тесты для отказа при конфликте identity/fear/duty.

### R4. Большой объем документальных удалений

Diff показывает много удалений старых task/history файлов.

Риск:
потерять трассу решений.

Контроль:
если это cleanup, оставить индекс/README в `docs/Tasks/ТЗ`; если нет, проверить перед merge.

---

## 9. Альтернативные сценарии

### A. Это не новая механика, а только диагностика

Вероятность: 20%.

Почему не основная гипотеза:
появился реальный новый runtime contract (`movement_intents`) и его применение через `MovementEngine`.

### B. Это локальный фикс движения без архитектурного сдвига

Вероятность: 25%.

Почему не основная гипотеза:
изменены не только movement-файлы, но и will, directive, LifeEngine, orchestrator, scene init, frontend projection и tests.

### C. Это переход к embodied simulation

Вероятность: 75%.

Почему:
изменение проходит через CREATE->READ->TRANSFORM->APPLY->PROJECT, а не застревает в одном слое.

---

## 10. Итог

За день сделан не "прирост строк", а системный переход:

```text
directive/social meaning
-> will pressure
-> cognitive decision
-> movement intent
-> authoritative spatial mutation
-> frontend projection
```

Минимальная оценка: **5 крупных runtime улучшений**.

Расширенная оценка с тестами и диагностикой: **8-10 новых смысловых функций**.

Главная ценность:
The Fool стал ближе к игре, где NPC существуют в пространстве и времени, а не только в тексте.
