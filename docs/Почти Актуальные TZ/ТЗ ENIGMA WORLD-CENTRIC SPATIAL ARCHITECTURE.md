# ТЗ: ENIGMA WORLD-CENTRIC SPATIAL ARCHITECTURE

## Статус

**Тип:** фундаментальная архитектурная миграция
**Цель:** переход от `location-centric` к `world-centric` пространству
**Главный принцип:** Editor является первичным авторингом мира; runtime никогда не редактирует и не переопределяет canonical world geometry.

---

# I. Главный архитектурный сдвиг

## Было

```text
Campaign
 └── locations/
      ├── tavern.json
      ├── market_square.json
      └── city_gate.json

location
 ├── origin
 ├── size
 ├── rooms
 ├── walls
 ├── nodes
 ├── objects
 └── portals
```

Runtime:

```text
location_id
    ↓
load location JSON
    ↓
SpatialService
    ↓
local graph
```

И это породило значительную часть нынешней сложности.

Например, в текущем `SpatialRegistryBuilder` **каждый `location.json` объявляется chunk'ом**. Реестр строит `ChunkDescriptor` непосредственно из `origin + size`, а adjacency вычисляет между этими прямоугольниками.

Более того, текущий `WorldContext` потом делает:

```text
world position
   ↓
find_chunks()
   ↓
load location JSON
   ↓
ChunkSpatialData
```

То есть `location == chunk`.

Это необходимо устранить.

---

# II. Новая онтология

Вводится:

```text
CANONICAL WORLD
│
├── WorldEntity
│
├── SpatialRegion
│
├── SpatialBoundary
│
├── SpatialOpening
│
├── SpatialObject
│
├── SemanticAnchor
│
├── Agent
│
└── WorldState
```

А runtime-представление:

```text
CANONICAL WORLD
       │
       ▼
SPATIAL COMPILER
       │
       ├── World Index
       ├── Runtime Chunks
       ├── Navigation Tiles
       ├── Collision Tiles
       ├── Perception Index
       ├── Semantic Index
       └── Simulation Regions
```

**Chunk больше не является объектом авторинга.**

Chunk — это **индекс хранения и вычисления**.

---

# III. Правило №1: один мир в редакторе

Editor больше не должен иметь:

```text
WORLD MODE
    ↓
location A

LOCAL MODE
    ↓
location A internals
```

как две разные реальности.

Новый редактор:

```text
WORLD CANVAS
```

и всё существует одновременно.

Пользователь может видеть:

```text
деревню
улицу
таверну
рынок
кузницу
лес
реку
NPC
стены
объекты
комнаты
дороги
semantic anchors
```

на **одной мировой системе координат**.

Zoom определяет детализацию представления, а не переключение между мирами.

Это принципиально.

---

# IV. Новый canonical файл

Предлагаю:

```text
campaigns/<campaign>/world.json
```

Он становится **единственным canonical authoring artifact пространства**.

`campaign.json` остаётся метаданными кампании.

Новая структура:

```json
{
  "schema": "enigma.world",
  "version": 1,

  "world": {
    "origin": {
      "x": 0,
      "y": 0
    },

    "coordinate_system": "world_2d_meters",

    "entities": []
  }
}
```

Но я бы не складывал буквально миллион объектов в один JSON-монолит.

Поэтому:

### Логическая модель

```text
world
```

### Физическое хранение

может быть:

```text
world/
    manifest.json
    entities/
    geometry/
    semantics/
```

Но **для Editor это всё равно один World Dataset**.

То есть Editor не должен заставлять человека думать:

> «сейчас я редактирую `tavern.json`».

---

# V. Главное правило хранения

**Не копировать одну и ту же геометрию в несколько мест.**

Canonical:

```text
world authoring data
```

Derived:

```text
compiled/
```

Runtime:

```text
runtime/
```

Например:

```text
campaign/
│
├── campaign.json
│
├── world.json                 ← CANONICAL
│
├── authoring/
│
├── compiled/
│   ├── world_manifest.json
│   ├── spatial_index.json
│   ├── nav/
│   ├── collision/
│   ├── perception/
│   └── simulation/
│
└── runtime/
    └── ...
```

**Runtime files никогда не становятся источником истины.**

---

# VI. Что делать со старыми `locations/*.json`

Не удалять сразу.

Ввести:

```text
legacy importer
```

который делает:

```text
locations/*.json
        ↓
WorldImporter
        ↓
world.json
```

После успешной миграции:

```text
location_id
```

сохраняется как **semantic identity**, но больше не является физическим контейнером.

Например:

```json
{
  "entity_id": "building_tavern_silver_wolf",
  "semantic": {
    "kind": "building",
    "name": "Таверна Серебряного Волка"
  }
}
```

---

# VII. Очень важное решение: `location_id` не уничтожать

Он просто меняет смысл.

### Было

```text
location_id = storage unit + spatial zone + graph zone
```

### Станет

```text
location_id = semantic/world region identity
```

То есть:

```text
tavern
```

может иметь:

```text
world bounds
```

но runtime chunk может разрезать её пополам.

И это нормально.

---

# VIII. Пространственная модель

Я предлагаю четыре фундаментальных геометрических типа.

## 1. Region

Область:

```text
village
forest
building
room
road
river
district
```

## 2. Boundary

Физическая граница:

```text
wall
cliff
riverbank
fence
```

## 3. Opening

Изменяемая граница:

```text
door
gate
bridge
window
broken_wall
```

## 4. Object

Объект внутри пространства:

```text
table
bed
forge
tree
rock
chest
```

---

# IX. Стены больше не должны быть primary topology

Это один из главных пунктов.

Сейчас у тебя:

```text
rooms
+
walls
+
nodes
+
passages
```

и compiler пытается определить, как они согласуются.

`graph_compiler.py` сейчас даже содержит специальную `_validate_navigation_geometry()`, которая обнаруживает:

> navigation edge пересекает wall → удалить edge.

Это уже не фундаментальная защита, а **компенсация несовершенной авторской модели**.

Новая модель:

```text
canonical geometry
       ↓
compiler
       ↓
collision
       ↓
navigation
       ↓
LOS
       ↓
sound
```

---

# X. Room становится Region

Существующие:

```text
rooms[]
```

не удаляются.

Но превращаются в:

```text
regions[]
```

Например:

```json
{
  "id": "main_hall",
  "kind": "room",

  "geometry": {
    "type": "polygon",
    "points": [...]
  },

  "semantic": {
    "name": "Главный зал"
  }
}
```

Причём Region **не обязан быть прямоугольником**.

Это важно.

---

# XI. Почему я не предлагаю делать комнату кубом

Твоя первоначальная идея была правильна на уровне направления, но canonical representation лучше сделать:

> **region volume / polygon**, а не boolean cube.

Потому что:

```text
rectangle
polygon
L-shaped room
courtyard
irregular cave
street
forest clearing
```

должны быть одинаково естественными.

А Boolean/CSG можно добавить как editor operation:

```text
Union
Subtract
Split
Extrude
```

но не делать CSG runtime authority.

---

# XII. Дверь

Дверь теперь:

```text
SpatialOpening
```

Она принадлежит boundary:

```text
Boundary W17
   │
   └── Opening D4
```

Её состояние:

```text
open
closed
locked
blocked
destroyed
barricaded
```

Но:

**дверь не является отдельным графовым переходом, который дизайнер обязан вручную соединять.**

Compiler сам получает:

```text
solid boundary
+
opening
=
traversable gap
```

---

# XIII. Межлокационных порталов в editor больше нет

Именно это соответствует твоей концепции.

Редактор не показывает:

```text
Tavern
   ↓ portal
Market
```

Он показывает:

```text
Tavern физически находится здесь.
Market физически находится здесь.
Road физически проходит здесь.
```

Если между ними есть физическая связь — compiler её обнаруживает.

Portals/boundaries могут существовать **в compiled topology**, но пользователь не обязан авторить их как основной механизм.

---

# XIV. Spatial Compiler

Нужен новый центральный компонент:

```text
backend/app/services/spatial/world_compiler.py
```

или, если хочешь сохранить разделение frontend/backend:

```text
frontend/map_editor/world_compiler.py
```

с чистым контрактом.

Я бы предпочёл:

```text
shared/domain/world_schema.py
shared/compiler/
```

если проект постепенно позволит создать shared layer.

Но пока, с учётом твоего правила frontend/backend isolation:

```text
frontend/map_editor/world_compiler.py
backend/app/services/spatial/world_runtime_compiler.py
```

не должны иметь две разные геометрические логики.

Лучше один canonical compiler contract.

---

# XV. Compiler Pipeline

Новый compiler:

```text
WorldAuthoring
      │
      ▼
Schema Validation
      │
      ▼
Geometry Normalization
      │
      ▼
Topology Extraction
      │
      ▼
Semantic Region Extraction
      │
      ▼
Spatial Partitioning
      │
      ├── Collision
      ├── Navigation
      ├── Perception
      ├── Sound
      └── Simulation
```

---

# XVI. Spatial Partition

Вот здесь начинается ключевая часть.

Я бы **не использовал старые `location.json` как chunks вообще**.

Создаётся:

```text
SpatialPartitioner
```

который получает:

```text
world geometry
```

и создаёт runtime grid.

Например:

```text
        0       64      128     192
        │        │        │       │
    ────┼────────┼────────┼───────
        │ C0,0   │ C1,0   │ C2,0
    ────┼────────┼────────┼───────
        │ C0,1   │ C1,1   │ C2,1
    ────┼────────┼────────┼───────
```

Но **границы chunks ничего не значат для физического мира**.

---

# XVII. Один объект может пересекать несколько chunks

Например:

```text
        C1
┌───────────────┐
│      ┌────────────┐
│      │  TAVERN    │
├──────┤            │
│      └────────────┘
│ C2
└───────────────
```

Compiler создаёт:

```text
Tavern
  → geometry fragments
      → C1
      → C2
```

Но entity ID остаётся:

```text
tavern_silver_wolf
```

Это **критично** для persistence.

---

# XVIII. Runtime chunk должен содержать не только geometry

Новая структура:

```text
RuntimeChunk
│
├── geometry
├── collision
├── navigation
├── visibility_index
├── sound_index
├── semantic_index
├── entity_refs
└── simulation_metadata
```

---

# XIX. Не одна дистанция загрузки

Вот это я считаю одним из самых важных улучшений.

Твоя фраза:

> «делится на части по глубине восприятия»

правильная.

Но я бы сделал **Depth-of-World**, а не просто `view_radius`.

---

# XX. Предлагаю 6 spatial depth tiers

## D0 — Immediate

```text
0–8 м
```

Полная геометрия.

Используется:

* collision;
* movement;
* precise LOS;
* objects;
* agents;
* interaction;
* sound geometry.

---

## D1 — Perceptual

```text
8–30 м
```

Полная geometry, но часть дорогих вычислений кэшируется.

Используется:

* визуальное восприятие;
* sound;
* nearby NPC;
* environment.

---

## D2 — Context

```text
30–100 м
```

Не нужна вся мебель.

Нужны:

```text
regions
roads
buildings
large obstacles
semantic anchors
NPC summaries
```

---

## D3 — Tactical / Social

```text
100–500 м
```

NPC знают:

```text
кто где находится
какие районы рядом
какие маршруты существуют
где опасно
```

Но физическая geometry не загружена.

---

## D4 — World

```text
500 м – несколько км
```

Работает:

```text
macro navigation
economy
travel
events
social propagation
```

---

## D5 — Abstract

Дальний мир.

```text
region state
population
economy
major events
travel progress
causal state
```

Без геометрии.

---

# XXI. И это НЕ обычный graphical LOD

Это важно.

Unreal имеет World Partition и HLOD: геометрия мира разбивается на streaming cells, а дальние необязательные объекты могут заменяться HLOD-представлениями. ([Epic Games Developers][1])

Но ENIGMA должна сделать **ещё один слой сверху**:

```text
Geometry LOD
+
Navigation LOD
+
Perception LOD
+
Simulation LOD
+
Cognition LOD
```

Simulation LOD — давно известная идея в multi-agent simulation: вместо полной модели агента можно передавать контроллеру более дешёвое представление, сохраняя масштаб поведения. ([publications.ri.cmu.edu][2])

А современные подходы к AI LOD уже прямо исследуют distance-aware изменение вычислительной сложности AI-моделей. ([arXiv][3])

Для ENIGMA это надо довести до **World Cognition LOD**.

---

# XXII. Самая важная мысль

**Расстояние не должно определять только загрузку geometry.**

Оно должно определять:

```text
какую часть мира мы знаем
какую часть мира мы вычисляем
какую часть мира мы физически держим
какую часть мира мы показываем
какую часть мира агент способен воспринимать
```

Это огромная разница.

---

# XXIII. Для каждого агента — собственный World Context

Сейчас у тебя:

```text
ContextResolver(player position)
```

в `frontend/world_context.py`.

Его нужно поднять на уровень:

```text
WorldContextResolver
```

с контрактом:

```python
resolve(
    actor_id,
    world_position,
    perception_profile,
    simulation_profile
)
```

Например:

```text
Player:
  perception = 30m
  interaction = 4m

NPC Orm:
  perception = 20m
  hearing = 35m

NPC Guard:
  vision = 40m
  tactical_context = 150m

Distant NPC:
  simulation = abstract
```

---

# XXIV. Но здесь есть принципиальный epistemic firewall

Для NPC:

```text
WORLD
```

не равно:

```text
BELIEF
```

WorldContext должен возвращать:

```text
physical facts available to perception
```

а не:

```text
global truth
```

То есть:

```text
World Geometry
      ↓
Perception Kernel
      ↓
ObservedSignal
      ↓
ObservedFact
      ↓
Inference
      ↓
Belief
```

Это уже существует у тебя концептуально.

Мы просто должны сделать spatial subsystem совместимым с этой моделью.

---

# XXV. NPC далеко от игрока

Вот здесь возникает действительно новая архитектура ENIGMA.

NPC вне loaded geometry **не должны исчезать из мира**.

Они переходят:

```text
FULL
 ↓
REDUCED
 ↓
ABSTRACT
```

Например:

### Full

```text
position
velocity
collision
LOS
perception
decision
memory
belief
```

### Reduced

```text
position
route
intent
major needs
social events
```

### Abstract

```text
location/region
activity
goal
time-to-arrival
important state
```

Это не теория ради оптимизации.

Это уже используется в различных open-world NPC systems: близкие NPC получают полную AI/navigation simulation, дальние — более дешёвую offline/macro simulation. ([Fab.com][4])

---

# XXVI. Но ENIGMA должна сделать следующий шаг

Когда NPC возвращается в D0:

```text
Abstract state
    ↓
Reification
    ↓
Detailed simulation
```

Например:

```text
Орм был в кузнице.
Прошло 2 часа.
Он должен быть на рынке.
```

Runtime:

```text
abstract schedule
    ↓
macro route
    ↓
spawn/reify at valid world point
    ↓
full simulation
```

Но это не телепорт.

Это **continuity-preserving reconstruction**.

---

# XXVII. Для этого нужен новый сервис

```text
backend/app/services/world_simulation_lod.py
```

или:

```text
backend/app/services/simulation_lod/
    manager.py
    tier_policy.py
    reifier.py
    abstract_simulator.py
```

Я бы выбрал второй вариант.

---

# XXVIII. Навигация

Текущий `GraphCompiler` должен перестать быть генератором:

```text
nodes → edges
```

как primary navigation.

Вместо этого:

```text
World Geometry
       ↓
Navigation Compiler
       ↓
Navigation Tiles
       ↓
Hierarchical Navigation
```

---

# XXIX. Но твои semantic nodes сохранить

Это важно.

Текущий:

```text
nodes:
  bar_area
  kitchen
  fireplace
  entrance
```

не выбрасывать.

Они становятся:

```text
SemanticAnchor
```

а не физическими waypoint.

Например:

```json
{
  "id": "forge",
  "kind": "semantic_anchor",
  "position": [127.2, 89.4],
  "roles": ["workbench", "blacksmith"]
}
```

Navigation itself:

> генерируется из geometry.

---

# XXX. Navigation должна быть иерархической

Например:

```text
WORLD NAV
   │
   ├── Region Graph
   │
   ├── Chunk Graph
   │
   ├── Navigation Tile
   │
   └── Local Steering
```

Для дальнего NPC:

```text
Village
 ↓
Market
 ↓
Tavern
```

Для ближнего:

```text
NavMesh / local graph
 ↓
steering
 ↓
MotionIntegrator
```

Это идеально совпадает с твоим уже существующим:

```text
MacroMovementGoal
LocalSteeringGoal
```

---

# XXXI. Это означает, что твой существующий LOD1/LOD0 наконец получает настоящий фундамент

Сейчас architecture/spatial.yaml уже говорит:

```text
MacroMovementGoal (LOD1)
LocalSteeringGoal (LOD0)
```

Но spatial storage ещё location-centric.

После миграции:

```text
LOD2 = world navigation
LOD1 = regional navigation
LOD0 = local physical navigation
```

Получается настоящая иерархия.

---

# XXXII. Динамическая геометрия

Вот здесь твой `DynamicAffordanceField` становится чрезвычайно важным.

Сейчас он уже имеет:

```text
Hard Override Layer
Soft Trace Layer
```

Не надо ломать это.

Нужно изменить его область действия.

Сейчас:

```text
region = location_id
```

Должно стать:

```text
region = SpatialRegionId / RuntimeRegionId
```

и дополнительно:

```text
affected_chunks
```

---

# XXXIII. Разрушение стены

Например:

```text
Wall W17
```

разрушена.

Не делать:

```text
reload tavern.json
rebuild tavern
```

Вместо:

```text
WorldEvent
   ↓
GeometryMutation
   ↓
Dirty AABB
   ↓
SpatialIndex invalidation
   ↓
Navigation tiles dirty
   ↓
Collision patch dirty
   ↓
LOS cache dirty
   ↓
Sound propagation dirty
```

Только затронутая область.

---

# XXXIV. Нужен `SpatialMutationSystem`

Создать:

```text
backend/app/services/spatial/spatial_mutation.py
```

Контракт:

```text
apply_mutation(mutation)
```

Мутации:

```text
CREATE
DESTROY
MOVE
ROTATE
OPEN
CLOSE
BLOCK
UNBLOCK
DEFORM
SPLIT
MERGE
```

---

# XXXV. Dirty-region model

Каждая мутация создаёт:

```text
DirtyRegion
```

например:

```json
{
  "min_x": 120,
  "min_y": 80,
  "max_x": 124,
  "max_y": 84
}
```

Compiler/runtime определяет:

```text
affected chunks
affected nav tiles
affected perception cells
affected sound cells
```

---

# XXXVI. Нельзя перестраивать весь мир

Это жёсткий invariant:

> **Mutation complexity ∝ affected spatial region, not world size.**

Именно так нужно проектировать.

Современные world-partitioned navigation systems тоже ограничивают runtime navigation generation загруженным пространством и используют chunked navigation data. ([Epic Games Developers][5])

---

# XXXVII. Spatial index

Текущий `SpatialRegistry` делает:

```python
for chunk in self._chunks:
```

на `find_chunks()`.

Для десятков объектов это нормально.

Для настоящего мира:

```text
100 000 chunks/entities
```

это уже неправильная асимптотика.

Нужен:

```text
SpatialIndex
```

на базе:

```text
uniform grid / loose grid
```

для fixed runtime chunks,

и при необходимости:

```text
R-tree
```

для irregular region/entity queries.

R-tree давно используется как динамический пространственный индекс для range/intersection queries; современные работы также рассматривают его как основу многоуровневых spatial hierarchies. ([Научный мир][6])

Для ENIGMA я бы **не начинал с R-tree**.

Начать:

```text
fixed world grid
```

потом добавить hierarchical index только если профилирование покажет необходимость.

---

# XXXVIII. Новый `SpatialRegistry`

Сейчас:

```text
ChunkDescriptor
 └── location_id
```

Новый:

```text
WorldSpatialRegistry
│
├── WorldBounds
├── ChunkDescriptor
├── RegionDescriptor
├── EntityDescriptor
├── NavigationDescriptor
├── SemanticDescriptor
└── SimulationDescriptor
```

---

# XXXIX. `ChunkDescriptor` должен выглядеть примерно так

```text
ChunkDescriptor

chunk_id
grid_x
grid_y

bounds

source_entities
source_regions

geometry_artifact
collision_artifact
navigation_artifact
perception_artifact
simulation_artifact

lod_levels
content_hash
```

**Никакого `location_id` как обязательного primary key.**

---

# XL. `SpatialRegistryBuilder` больше не должен читать `locations/*.json`

Сейчас:

```text
_collect_chunks()
    ↓
locations/*.json
```

Это один из первых файлов, который надо переписать.

Новая цепочка:

```text
world.json
    ↓
WorldCompiler
    ↓
SpatialRegistryArtifact
```

---

# XLI. `WorldContext` — один из самых важных файлов миграции

Сейчас:

```text
SpatialDataLoader
    ↓
_find_editor_json(campaign_id, location_id)
```

Это надо полностью убрать.

Новая:

```text
SpatialDataLoader
    ↓
load_chunk(chunk_id)
```

и:

```text
ChunkArtifactStore
```

читает:

```text
compiled/chunks/<chunk_id>.json
```

---

# XLII. Но Editor JSON никогда не исчезает из authoring

То есть:

```text
Editor
  ↓
world canonical
  ↓
compile
  ↓
runtime chunks
```

А не:

```text
Editor
  ↓
chunks
```

---

# XLIII. Lazy loading

`WorldContext` становится:

```text
WorldStreamingContext
```

и получает:

```python
resolve(
    actor_position,
    perception_profile,
    simulation_profile
)
```

Он возвращает:

```text
WorldContext
├── loaded_geometry
├── visible_geometry
├── collidable_geometry
├── nearby_agents
├── regional_context
└── abstract_context
```

---

# XLIV. Загрузка должна быть asynchronous / staged

Не:

```text
move
 ↓
load 30 files
 ↓
freeze
```

А:

```text
position changed
 ↓
streaming request
 ↓
prefetch
 ↓
load manifest
 ↓
load geometry
 ↓
load nav
 ↓
activate simulation
```

Можно использовать несколько очередей:

```text
HIGH:
current chunk

MEDIUM:
neighbor chunks

LOW:
perception halo

BACKGROUND:
regional data
```

---

# XLV. Player streaming source

Player — один streaming source.

Но не единственный.

Нужны:

```text
StreamingSource
├── Player
├── NPC
├── Camera
├── Event
└── Debug
```

Это важно для агентов.

Если Орм находится в 200 м от игрока, но его действие должно вызвать событие в деревне, нужный simulation context должен быть загружен/активирован независимо от камеры.

---

# XLVI. Agent streaming

Например:

```text
Player:
D0 = 8
D1 = 30
D2 = 100

Orm:
D0 = 8
D1 = 25
D2 = 150

Guard:
D0 = 10
D1 = 50
D2 = 300
```

Streaming manager объединяет запросы:

```text
union(all streaming sources)
```

---

# XLVII. Это очень хорошо сочетается с твоей perception architecture

У тебя уже есть:

```text
Reality
 ↓
ManifestationState
 ↓
ObservationRelation
 ↓
PerceivedSignal
 ↓
ObservedFact
 ↓
Inference
 ↓
Memory / Belief
```

Теперь spatial subsystem:

```text
World Geometry
 ↓
Spatial Query
 ↓
Agent-specific Spatial Context
 ↓
ObservationRelation
```

То есть пространство **становится частью epistemology**, а не просто collision layer.

---

# XLVIII. Frontend

## `frontend/game_screen.py`

Нужно убрать логику:

```text
location_id
→ local_position
→ location origin
→ current location reconciliation
```

из основной логики рендера.

GameScreen должен получать:

```text
WorldRenderContext
```

примерно:

```text
player_world_position

visible_geometry
visible_entities

camera
perception

world_revision
```

---

# XLIX. `frontend/scene_renderer.py`

Уже почти готов к этому.

Он уже умеет:

```text
floor_rects
walls
obstacles
world coordinates
```

и комментирует:

> `S80.3b: Multi-chunk floors`

То есть этот файл не нужно ломать.

Его нужно перевести:

```text
SceneRenderer.render(
    PerceivedScene,
    WorldRenderContext
)
```

вместо:

```text
walls + obstacles + scene_w + scene_h
```

---

# L. `frontend/world_context.py`

Переименовать концептуально:

```text
world_context.py
```

оставить.

Но превратить в:

```text
WorldStreamingContext
WorldViewContext
WorldSimulationContext
```

или один фасад:

```text
WorldContextService
```

с тремя проекциями.

---

# LI. `frontend/game_loop_bridge.py`

Очень важный файл.

Сейчас там есть:

```text
world_x/world_y
→ SpatialRegistry
→ confirmed_location_id
```

После миграции:

```text
world_x/world_y
→ WorldSpatialOracle
→ spatial context
```

`confirmed_location_id` больше не должен быть главным spatial truth.

Можно оставить:

```text
confirmed_regions
```

например:

```text
building = tavern
district = silver_wolf_quarter
city = ...
```

---

# LII. `WorldSnapshot`

Текущий:

```text
location_id
spatial_walls
spatial_obstacles
npc_positions
```

слишком location-centric.

Новый Snapshot:

```text
world_revision

player:
  world_position

spatial_context:
  primary_region
  visible_regions

geometry:
  walls
  obstacles
  surfaces

entities:
  ...

perception:
  ...

simulation:
  ...
```

`location_id` можно оставить как compatibility field.

---

# LIII. API

`GET /api/world_state`

не должен означать:

> «дай мне состояние локации».

Он должен означать:

> «дай мне текущую world projection для этого actor».

Новый контракт:

```text
GET /api/world_state
    campaign_id
    actor_id
    world_x
    world_y
```

И сервер сам определяет:

```text
what should be loaded
what should be simulated
what should be returned
```

---

# LIV. API для streaming

Я бы добавил:

```text
GET /api/world/context
```

и:

```text
GET /api/world/chunks/{chunk_id}
```

но **frontend не должен сам решать, какие chunks ему нужны**.

Он говорит:

```text
actor position
perception profile
```

а backend возвращает context.

---

# LV. Для Editor API

Нужен отдельный:

```text
World Authoring API
```

Но пока editor локальный pygame, можно оставить filesystem.

Главное:

```text
Editor writes canonical world.
```

---

# LVI. Map Editor: новая архитектура

Текущий:

```text
EditorCore
 ├── MODE_WORLD
 └── MODE_LOCAL
```

надо преобразовать.

### Было

```text
WORLD
LOCAL
```

### Станет

```text
WORLD CANVAS
```

с уровнями:

```text
Overview
Region
Geometry
Semantic
Entities
Navigation Debug
Simulation Debug
```

Это **режимы представления**, а не разные пространства.

---

# LVII. `editor_core.py` — главный рефактор

Сейчас он огромный — порядка **178 KB**.

Я бы не продолжал наращивать его.

Разделить:

```text
frontend/map_editor/
    editor_core.py

    world_canvas.py
    world_camera.py
    world_selection.py

    tools/
        geometry_tool.py
        object_tool.py
        region_tool.py
        opening_tool.py
        entity_tool.py
        semantic_tool.py

    render/
        world_renderer.py
        geometry_renderer.py
        entity_renderer.py
        debug_renderer.py

    authoring/
        world_document.py
        world_serializer.py
        world_migrator.py

    validation/
        world_validator.py
        geometry_validator.py
        navigation_validator.py
```

`EditorCore` должен стать orchestrator, а не бог-объектом.

---

# LVIII. Editor должен показывать весь мир

На zoom 0.1:

```text
WORLD
├── cities
├── roads
├── forests
├── rivers
└── buildings
```

На zoom 1:

```text
district
├── street
├── tavern
└── houses
```

На zoom 10:

```text
tavern
├── room
├── furniture
├── doors
└── NPC
```

На zoom 30:

```text
wall geometry
collision
opening
semantic anchor
```

То есть:

> **zoom ≠ камера. Zoom становится запросом на spatial detail.**

---

# LIX. И вот здесь появляется очень сильная возможность

Editor может иметь:

```text
LOD Preview
```

и показывать:

```text
D0 geometry
D1 geometry
D2 semantic
D3 regional
D4 abstract
```

Это позволит тебе **видеть мир глазами runtime**.

Для ENIGMA это чрезвычайно полезный debug-инструмент.

---

# LX. World Validator

Новый:

```text
frontend/map_editor/validation/world_validator.py
```

должен проверять:

### Geometry

```text
INV-WORLD-001
Все сущности имеют уникальный world_id.

INV-WORLD-002
Все геометрические координаты принадлежат canonical world space.

INV-WORLD-003
Нет NaN/Inf координат.

INV-WORLD-004
Нет неразрешённых геометрических конфликтов.
```

### Openings

```text
INV-WORLD-010
Opening принадлежит boundary.

INV-WORLD-011
Opening не имеет нулевой ширины.

INV-WORLD-012
Traversable opening имеет valid walkable space с обеих сторон.
```

### Navigation

```text
INV-WORLD-020
Generated navigation не пересекает solid geometry.

INV-WORLD-021
Каждая reachable region имеет navigation representation.
```

### Partition

```text
INV-WORLD-030
Каждый runtime chunk имеет deterministic bounds.

INV-WORLD-031
Chunk boundary не создаёт физического барьера.

INV-WORLD-032
Entity, пересекающая несколько chunks, имеет единственный canonical ID.
```

---

# LXI. Особый invariant для ENIGMA

```text
INV-EPISTEMIC-SPATIAL-001

World spatial truth MUST NOT be directly injected
into NPC belief state.

Only perception/observation pipeline may cross
the physical → epistemic boundary.
```

Это очень важно.

Иначе новый world streaming случайно сделает NPC всезнающими.

---

# LXII. Навигация при отсутствии загруженной geometry

Это критический вопрос.

Если NPC находится:

```text
D4
```

и geometry не загружена, он всё равно должен уметь:

```text
Village A
    ↓
Road
    ↓
Market
    ↓
Tavern
```

по abstract navigation graph.

Это:

```text
MacroNavigationGraph
```

который компилируется отдельно.

---

# LXIII. Когда NPC входит в D1

```text
Macro route
    ↓
regional route
    ↓
local nav
```

Когда входит в D0:

```text
local nav
    ↓
steering
    ↓
motion
```

Именно это должно связать:

```text
MacroMovementGoal
```

с:

```text
LocalSteeringGoal
```

---

# LXIV. Dynamic replanning

При разрушении стены:

```text
DirtyRegion
   ↓
navigation tile invalid
```

Ближний NPC:

```text
replan immediately
```

NPC D3:

```text
macro graph update
```

NPC D5:

```text
не обязательно немедленно менять route,
если событие ещё не влияет на его abstract state
```

То есть **LOD определяет не только точность пространства, но и частоту реакции на изменения**.

---

# LXV. Это принципиально отличается от обычного streaming

Обычный:

```text
load/unload
```

ENIGMA:

```text
LOAD
SIMULATE
PERCEIVE
INFER
REMEMBER
REACT
```

на разных уровнях детализации.

И это я бы считал одной из главных уникальных архитектурных частей ENIGMA.

---

# LXVI. Конкретный порядок миграции

Теперь самое важное — **не делать всё сразу**.

Я бы дал архитектору следующие спринты.

---

## PHASE 0 — Freeze

### Задача

Не менять runtime.

Создать:

```text
docs/architecture/world_centric_spatial.md
```

и ADR:

```text
ADR-WORLD-001
```

Зафиксировать:

```text
World is canonical.
Locations are semantic regions.
Chunks are derived runtime partitions.
```

Acceptance:

```text
старый runtime полностью работает.
```

---

# PHASE 1 — Canonical World Schema

Создать:

```text
frontend/map_editor/world_schema.py
```

и:

```text
backend/app/models/world_contracts.py
```

Типы:

```text
WorldDocument
WorldEntity
SpatialRegion
SpatialBoundary
SpatialOpening
SpatialObject
SemanticAnchor
WorldPosition
WorldBounds
```

Не менять renderer.

---

# PHASE 2 — Legacy Importer

Создать:

```text
frontend/map_editor/world_migrator.py
```

Функция:

```text
locations/*.json
        ↓
world.json
```

Acceptance:

> `tavern + market + city_gate` дают тот же spatial arrangement.

Проверять world coordinate equality.

---

# PHASE 3 — World Authoring Store

Создать:

```text
frontend/map_editor/world_document.py
```

`DataManager` постепенно перестаёт быть:

```text
locations Dict
```

и становится:

```text
WorldDocument
```

Но пока можно держать compatibility view:

```text
world_document.locations
```

---

# PHASE 4 — World Editor Canvas

Переписать:

```text
frontend/map_editor/editor_core.py
```

так, чтобы:

```text
MODE_WORLD
MODE_LOCAL
```

стали одним canvas.

Добавить:

```text
world_canvas.py
world_camera.py
```

Acceptance:

> Все существующие 3 location видны одновременно и имеют реальные world coordinates.

---

# PHASE 5 — Geometry Authoring

Добавить:

```text
regions
boundaries
openings
objects
```

Все редактируются в world coordinates.

Критический тест:

> Перетащить таверну на 100 м.

Должны переместиться её entities.

Но:

```text
не должно существовать "location shift"
```

Это теперь обычная entity transform.

---

# PHASE 6 — Убрать Room→Wall duplication

Это фундаментальный этап.

Сделать:

```text
Region Geometry
        ↓
Boundary Compiler
```

и перестать требовать ручного совпадения:

```text
room perimeter
=
wall segments
```

Старые walls импортируются как explicit boundaries.

После миграции новые стены должны генерироваться из geometry, если это выбранный тип региона.

---

# PHASE 7 — Opening Compiler

Создать:

```text
backend/app/services/spatial/opening_compiler.py
```

Он:

```text
boundary
+
opening
↓
solid fragments
+
walkable gap
```

Убрать дублирование `_split_wall_by_openings()` из:

```text
frontend/world_context.py
backend/scene_state_manager
```

Это очень важно.

**Одна реализация геометрического разрезания.**

---

# PHASE 8 — World Spatial Compiler

Создать:

```text
world_compiler.py
```

Он компилирует:

```text
WorldDocument
```

в:

```text
SpatialWorldArtifact
```

Пока можно генерировать старый `spatial_registry.json` для compatibility.

---

# PHASE 9 — Runtime Partition

Переделать:

```text
frontend/map_editor/spatial_registry_builder.py
```

с:

```text
locations → chunks
```

на:

```text
world geometry → chunks
```

Новый artifact:

```text
compiled/world_manifest.json
compiled/chunks/*.json
```

---

# PHASE 10 — SpatialRegistry v2

`backend/app/services/spatial/spatial_registry.py`

Добавить:

```text
WorldSpatialRegistry
```

Старый:

```text
SpatialRegistry
```

пока оставить compatibility adapter.

---

# PHASE 11 — WorldContext v2

Переделать:

```text
frontend/world_context.py
```

на:

```text
WorldStreamingContext
```

Метод:

```python
resolve_actor_context(...)
```

с уровнями:

```text
D0
D1
D2
D3
```

---

# PHASE 12 — Navigation Compiler

`graph_compiler.py` перестаёт строить primary navigation из ручных nodes.

Новый:

```text
navigation_compiler.py
```

строит:

```text
world nav
regional nav
local nav
```

А semantic nodes остаются отдельным слоем.

---

# PHASE 13 — Movement Engine

`backend/app/services/spatial/movement_engine.py`

перевести:

```text
location_id
```

на:

```text
world_position
region_id
navigation_context
```

Временно:

```text
location_id = compatibility projection
```

---

# PHASE 14 — Macro Navigation

Создать:

```text
backend/app/services/spatial/macro_navigation.py
```

Он работает без local geometry.

Это позволит NPC:

```text
перемещаться между регионами,
даже когда промежуточная геометрия выгружена.
```

---

# PHASE 15 — Simulation LOD

Создать:

```text
backend/app/services/simulation_lod/
    manager.py
    policy.py
    simulator.py
    reifier.py
```

Tiers:

```text
FULL
REDUCED
ABSTRACT
DORMANT
```

---

# PHASE 16 — Agent-specific spatial context

Расширить:

```text
backend/app/services/player_cognition/spatial_layer.py
```

и:

```text
backend/app/services/spatial/spatial_query_service.py
```

чтобы spatial facts формировались:

```text
actor-specific
```

а не:

```text
global scene_state
```

---

# PHASE 17 — World Snapshot v2

Переделать:

```text
backend/app/models/world_snapshot.py
```

и:

```text
backend/app/services/integration/world_snapshot_builder.py
```

на:

```text
WorldSnapshot
 ├── world_position
 ├── spatial_context
 ├── visible_geometry
 ├── perceived_entities
 ├── regional_context
 └── simulation_state
```

---

# PHASE 18 — Frontend rendering

`frontend/game_screen.py`

перевести:

```text
local_position
```

на:

```text
world_position
```

как primary.

`local_position` становится:

> render-local coordinate.

---

# PHASE 19 — SceneRenderer

Переделать API:

```python
render(
    perceived_scene,
    world_render_context
)
```

и убрать необходимость знать:

```text
location_id
```

---

# PHASE 20 — Delete location-centric runtime

Только теперь удалить:

```text
location_id as spatial authority
```

Удаляются/архивируются:

```text
BoundaryRouter
location-specific traversal assumptions
location-centric SpatialFactory
location-specific world loading
```

Но semantic region IDs остаются.

---

# LXVII. Какие существующие файлы затронуть

## Критические

| Файл                                                         | Судьба                                     |
| ------------------------------------------------------------ | ------------------------------------------ |
| `frontend/map_editor/editor_core.py`                         | **глубокий refactor**                      |
| `frontend/map_editor/data_manager.py`                        | **замена WorldDocument adapter'ом**        |
| `frontend/map_editor/campaign_manager.py`                    | **перевести на world authoring**           |
| `frontend/map_editor/spatial_registry_builder.py`            | **переписать**                             |
| `frontend/spatial_compilation_orchestrator.py`               | **расширить до WorldCompiler**             |
| `frontend/spatial_compilation_gateway.py`                    | **сохранить как entry point**              |
| `frontend/world_context.py`                                  | **глубокий refactor**                      |
| `frontend/game_screen.py`                                    | **глубокий refactor**                      |
| `frontend/scene_renderer.py`                                 | **адаптация**                              |
| `frontend/game_loop_bridge.py`                               | **migration**                              |
| `backend/app/services/spatial/spatial_registry.py`           | **v2**                                     |
| `backend/app/services/spatial/spatial_service.py`            | **world-aware**                            |
| `backend/app/services/spatial/graph_compiler.py`             | **замена navigation compiler**             |
| `backend/app/services/spatial/movement_engine.py`            | **world-space migration**                  |
| `backend/app/services/spatial/world_topology_provider.py`    | **расширить**                              |
| `backend/app/services/spatial/spatial_query_service.py`      | **world-space**                            |
| `backend/app/services/spatial/local_traversal_planner.py`    | **сохранить, но сделать local projection** |
| `backend/app/services/spatial/traversal_execution_system.py` | **адаптация**                              |
| `backend/app/models/spatial_contracts.py`                    | **расширить**                              |
| `backend/app/models/world_snapshot.py`                       | **v2**                                     |
| `backend/app/api/world_routes.py`                            | **world context API**                      |
| `backend/app/services/adaptive_tick_loader.py`               | **заменить на Simulation LOD**             |

---

# LXVIII. Что сохранить почти без изменений

Это тоже важно.

Не надо разрушать уже хорошие слои:

```text
Geometry Kernel
DynamicAffordanceField
WorldTopologyProvider
CollisionAvoidance
SteeringResolver
MotionIntegrator
TraversalTransitionKernel
SpatialEventDetector
EventCompiler
ProjectionEngine
WorldSnapshot
Perception architecture
Belief architecture
```

Они должны получить **новый spatial substrate**.

То есть мы не переписываем ENIGMA.

Мы меняем:

> **подложку пространства, на которой уже стоит остальная машина.**

---

# LXIX. Что особенно хорошо совпадает с твоей многофазной моделью Tick

Вот здесь я вижу очень сильную симметрию.

Сейчас:

```text
TICK
Phase 1
Phase 2
Phase 3
...
Phase 10
```

В будущем пространство тоже должно быть pipeline:

```text
WORLD COMPILATION

1. Authoring
2. Geometry normalization
3. Topology extraction
4. Region extraction
5. Partition
6. Collision projection
7. Navigation projection
8. Perception projection
9. Semantic projection
10. Simulation projection
```

И runtime:

```text
SPATIAL TICK

1. World mutations
2. Dirty region detection
3. Spatial state update
4. Partition activation
5. Navigation invalidation
6. Perception update
7. Agent context generation
8. Macro simulation
9. Local simulation
10. Snapshot projection
```

То есть **пространство само становится многофазной машиной**, а не набором функций `is_blocked()`.

---

# LXX. И я бы добавил ещё один фундаментальный слой

## Spatial Causality

Сейчас:

```text
geometry
```

в основном отвечает:

> где можно ходить?

Но для твоего мира пространство должно отвечать ещё:

```text
что где произошло?
что где слышно?
что где видно?
где кто обычно находится?
какие маршруты используются?
какие места опасны?
какие места считаются своими?
какие места являются социальными центрами?
```

То есть у spatial region появляется:

```text
physical
perceptual
social
semantic
historical
```

---

# LXXI. Region должен иметь causal affordances

Например:

```yaml
region:
  id: tavern_main_hall

  physical:
    walkable: true

  perceptual:
    visibility: 0.8
    sound_propagation: 0.9

  semantic:
    functions:
      - drinking
      - socializing
      - trading

  social:
    privacy: 0.2
    social_density: 0.8

  historical:
    events:
      - ...
```

Тогда пространственная модель становится частью мира, а не только collision map.

---

# LXXII. Это особенно важно для саморазвивающихся NPC

NPC может постепенно сформировать:

```text
"Таверна — место, где собираются люди."
```

не потому что:

```python region.kind == "tavern"
```

а потому что:

```text
наблюдения
+
повторяемость
+
люди
+
торговля
+
разговоры
+
память
```

дают ему inference.

И вот здесь canonical world semantics **не должны напрямую становиться cognition**.

---

# LXXIII. Поэтому я бы ввёл три spatial truths

### 1. Physical Truth

```text
где что реально находится
```

### 2. Operational Truth

```text
что сейчас физически доступно
```

Например дверь разрушена.

### 3. Epistemic Truth

```text
что конкретный NPC считает доступным
```

Эти три уровня нельзя смешивать.

---

# LXXIV. Почему эта архитектура масштабируется

Потому что разные системы могут работать на разных масштабах:

```text
Physical:
метры

Navigation:
десятки метров

Regional:
сотни метров

Social:
километры

Economic:
регионы

Historical:
весь мир
```

При этом все используют:

```text
WorldEntityID
WorldPosition
RegionID
WorldRevision
```

как общие якоря.

---

# LXXV. Что я считаю особенно важным из современных подходов

Современный World Partition подтверждает именно базовую идею:

> автор создаёт единый persistent world, а runtime автоматически разбивает его на streamable grid cells. ([Epic Games Developers][1])

World-partitioned NavMesh подтверждает следующий уровень:

> navigation тоже можно partitionировать независимо и загружать только нужные nav chunks; динамическая генерация ограничивается загруженным пространством. ([Epic Games Developers][5])

HLOD показывает третий уровень:

> даже выгруженное пространство может иметь более дешёвое представление. ([Epic Games Developers][7])

Data Layers показывают ещё один принцип:

> пространственный streaming и semantic/gameplay layers могут существовать независимо. ([Epic Games Developers][8])

А Simulation LOD для multi-agent systems подтверждает, что **сама симуляция**, а не только графика, должна иметь разные уровни детализации. ([publications.ri.cmu.edu][2])

---

# LXXVI. Но ENIGMA должна пойти на уровень глубже

Условно:

```text
UNREAL

World
 ↓
Partition
 ↓
Rendering LOD
 ↓
Navigation
```

ENIGMA:

```text
WORLD
 │
 ├── Geometry
 │
 ├── Partition
 │
 ├── Navigation
 │
 ├── Perception
 │
 ├── Simulation
 │
 ├── Social Context
 │
 ├── Memory Context
 │
 └── Epistemic Context
```

И у каждого агента:

```text
WORLD
  ↓
what physically exists
  ↓
what is loaded
  ↓
what is perceptible
  ↓
what is observed
  ↓
what is inferred
  ↓
what is believed
  ↓
what is remembered
  ↓
what is acted upon
```

**Вот это уже действительно является пространственным аналогом твоей многофазной модели Tick.**

---

# LXXVII. Главный критерий успеха миграции

После завершения нельзя иметь ситуацию:

```text
Editor world
    ≠
Runtime world
```

Должно быть:

```text
Editor World
     │
     │ compile
     ▼
Runtime World
```

где:

> Runtime World является **детерминированной проекцией Editor World**, а не отдельной картой.

И если архитектор изменил editor object:

```text
table_17
```

runtime должен воспроизвести:

```text
same entity_id
same world_position
same geometry
same semantic identity
```

в соответствующем chunk.

---

# LXXVIII. Acceptance Criteria всего перехода

Я бы поставил архитектору именно такие критерии.

### AC-01

Editor открывает весь мир одновременно.

### AC-02

Нет необходимости открывать `tavern.json` отдельно от `market_square.json`.

### AC-03

Все объекты редактируются в единой мировой системе координат.

### AC-04

Перемещение semantic region не требует ручного пересчёта её children.

### AC-05

Runtime chunks генерируются автоматически.

### AC-06

Chunk boundaries не влияют на физику.

### AC-07

Одна entity имеет один canonical ID даже при пересечении chunks.

### AC-08

Игрок получает world context по world position.

### AC-09

NPC получает **свой** world context.

### AC-10

Дальний NPC продолжает существовать в abstract simulation.

### AC-11

При приближении NPC происходит deterministic reification.

### AC-12

Разрушение объекта инвалидирует только затронутую область.

### AC-13

Navigation перестраивается локально.

### AC-14

LOS / sound / movement используют единую canonical geometry projection.

### AC-15

NPC belief никогда не получает global geometry напрямую.

### AC-16

1000+ runtime chunks не требуют загрузки целиком.

### AC-17

1000+ NPC не требуют полного D0 simulation.

### AC-18

Editor save → compile → game load не теряет ни одной authoring-сущности.

### AC-19

Legacy locations импортируются без изменения world coordinates.

### AC-20

После миграции `location_id` больше не является spatial authority.

---

# LXXIX. И вот где я вижу настоящий масштаб твоего проекта

Сейчас у тебя spatial architecture выглядит примерно так:

```text
location
  ↓
rooms
  ↓
walls
  ↓
nodes
  ↓
graph
  ↓
NPC
```

После перехода:

```text
                         CANONICAL WORLD
                               │
                 ┌─────────────┼─────────────┐
                 │             │             │
             Geometry       Entities      Semantics
                 │             │             │
                 └─────────────┼─────────────┘
                               ↓
                     SPATIAL COMPILER
                               │
        ┌──────────────┬──────┼──────┬──────────────┐
        ↓              ↓      ↓      ↓              ↓
     Chunks          Nav    LOS   Sound         Simulation
        │              │      │      │              │
        └──────────────┴──────┼──────┴──────────────┘
                               ↓
                     AGENT WORLD CONTEXT
                               │
                   ┌───────────┴───────────┐
                   ↓                       ↓
             Physical facts          Perceived facts
                                           │
                                      Observation
                                           │
                                        Inference
                                           │
                                         Belief
                                           │
                                        Decision
                                           │
                                         Action
                                           │
                                      World Event
                                           │
                                           └──────→ WORLD
```

**И вот это уже не «карта RPG».**

Это пространственный субстрат для автономного мира.

И самое существенное: я бы **не трогал сейчас TickOrchestrator ради этой миграции**. Наоборот — spatial world должен научиться вписываться в уже существующую многофазную машину Tick так же, как ты сейчас вписываешь physiology, perception, memory, decision и projection.

То есть не делать ещё один «великий движок внутри движка».

Нужно построить:

> **World → Spatial State → Spatial Projection → Agent Context**

как отдельную фундаментальную машину, которую Tick только оркестрирует.

Тогда твоя идея «глубокая многообразная логика мира» становится технически реализуемой: **геометрия, навигация, восприятие, звук, социальные пространства, память о местах, разрушение и перемещение становятся разными проекциями одного изменяемого World State**, а не набором независимых систем.

И именно это я считаю правильной конечной целью перехода.

[1]: https://dev.epicgames.com/documentation/en-us/unreal-engine/world-partition-in-unreal-engine?utm_source=chatgpt.com "World Partition in Unreal Engine | Unreal Engine 5.8 Documentation | Epic Developer Community"
[2]: https://publications.ri.cmu.edu/simulation-level-of-detail-for-multiagent-control?utm_source=chatgpt.com "Simulation level of detail for multiagent control - Robotics Institute Carnegie Mellon University"
[3]: https://arxiv.org/abs/2606.06565?utm_source=chatgpt.com "AI Level of Detail: Distance-Aware ML Model Precision Selection for Real-Time Human Motion Prediction in Games"
[4]: https://www.fab.com/listings/fd1d027d-171c-40a1-9e42-3de3747eda96?lang=ar&utm_source=chatgpt.com "Open World NPC Simulation System - Scalable Online / Offline NPCs | Fab"
[5]: https://dev.epicgames.com/documentation/unreal-engine/world-partitioned-navigation-mesh?lang=en-US&utm_source=chatgpt.com "World Partitioned Navigation Mesh | Unreal Engine 5.8 Documentation | Epic Developer Community"
[6]: https://www.sciencedirect.com/science/article/pii/S0164121200000789?utm_source=chatgpt.com "Optimizing storage utilization in R-tree dynamic index structure for spatial databases - ScienceDirect"
[7]: https://dev.epicgames.com/documentation/unreal-engine/world-partition---hierarchical-level-of-detail-in-unreal-engine?lang=en-US&utm_source=chatgpt.com "World Partition - Hierarchical Level of Detail in Unreal Engine | Unreal Engine 5.8 Documentation | Epic Developer Community"
[8]: https://dev.epicgames.com/documentation/unreal-engine/world-partition---data-layers-in-unreal-engine?lang=en-US&utm_source=chatgpt.com "World Partition - Data Layers in Unreal Engine | Unreal Engine 5.8 Documentation | Epic Developer Community"
