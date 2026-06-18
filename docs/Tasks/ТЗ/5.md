## ТЗ-06: WorldSnapshot — отсутствует boundary_map

**Статус:** ⚠️ РАБОТАЕТ БЕЗ BOUNDARY_MAP | **Критичность:** HIGH | **Волна:** 2

---

### Суть проблемы одной строкой

Архитектура требует `boundary_map` в WorldSnapshot, но его нет. Без него NPC не могут переходить между локациями, а весь spatial-слой работает только внутри одной комнаты.

---

### Что говорит архитектура

**`architecture/state.yaml`:**
> WorldSnapshot MUST include: boundary_map, spatial_graph, rng_seed

**`architecture/spatial.yaml`:**
> boundary_map — карта переходов между локациями, содержит BoundaryEdge с target_location_id, transition_node_id

**`architecture/pipeline.yaml`:**
> Фаза 7 должна собирать полный WorldSnapshot для CausalValidator

---

### Что есть сейчас

**Файл:** `backend/app/models/world_snapshot.py`

```python
# СЕЙЧАС (неполный):
@dataclass(frozen=True)
class WorldSnapshot:
    snapshot_id: str
    created_at: str
    tick: int
    campaign_id: str
    location_id: str
    spatial_service: object       # ← ссылка на объект, НЕ переживает сериализацию
    npc_positions: Dict[str, Tuple[int, int]]
    active_traversals: List
    spatial_walls: List
    spatial_obstacles: List
    rng_seed: int
    # boundary_map: ???            ← ОТСУТСТВУЕТ
    # spatial_graph: ???           ← ОТСУТСТВУЕТ (заменён ссылкой на объект)
```

**Что ломается без boundary_map:**

| Проблема | Почему |
|----------|--------|
| NPC не переходят между локациями | MovementEngine не знает, куда идти |
| SemanticIndex невозможен | Нет связи между локациями |
| WorldSnapshot не переживает сериализацию | `spatial_service` — ссылка на объект, не данные |
| CausalValidator не может проверить мир | Нет полного состояния |
| ТЗ-02 и ТЗ-14 заблокированы | Оба зависят от boundary_map |

---

### Пошаговый план исправления

#### Шаг 1: Определить модель BoundaryEdge

**Файл:** `backend/app/models/spatial_contracts.py` — добавить:

```python
from dataclasses import dataclass
from typing import Optional

@dataclass(frozen=True)
class BoundaryEdge:
    """Переход между двумя локациями"""
    edge_id: str                        # уникальный ID перехода
    target_location_id: str             # куда ведёт переход
    from_node_id: str                   # узел-выход в текущей локации (дверь, ворота)
    to_node_id: str                     # узел-вход в целевой локации
    bidirectional: bool = True          # можно ли вернуться обратно
    travel_time_ticks: int = 1          # сколько тиков занимает переход
    visibility: str = "visible"         # visible / hidden / conditional
    condition: Optional[str] = None     # условие перехода (ключ, квест и т.д.)

@dataclass(frozen=True)
class BoundaryMap:
    """Карта всех переходов из текущей локации"""
    location_id: str
    edges: Dict[str, BoundaryEdge]      # edge_id → BoundaryEdge
    
    def get_transitions(self) -> List[BoundaryEdge]:
        """Все доступные переходы"""
        return list(self.edges.values())
    
    def get_transition_to(self, target_location_id: str) -> Optional[BoundaryEdge]:
        """Найти переход в конкретную локацию"""
        for edge in self.edges.values():
            if edge.target_location_id == target_location_id:
                return edge
        return None
    
    def get_node_exits(self) -> List[str]:
        """Все узлы-выходы (для отображения на карте)"""
        return [edge.from_node_id for edge in self.edges.values()]
```

---

#### Шаг 2: Добавить boundary_map в WorldSnapshot

**Файл:** `backend/app/models/world_snapshot.py` — обновить:

```python
from app.models.spatial_contracts import BoundaryMap

@dataclass(frozen=True)
class WorldSnapshot:
    snapshot_id: str
    created_at: str
    tick: int
    campaign_id: str
    location_id: str
    npc_positions: Dict[str, Tuple[int, int]]
    active_traversals: List
    spatial_walls: List
    spatial_obstacles: List
    rng_seed: int
    
    # НОВЫЕ ПОЛЯ:
    boundary_map: Optional[BoundaryMap] = None      # ← ДОБАВИТЬ
    spatial_graph_data: Optional[Dict] = None        # ← сериализуемый граф (вместо объекта)
```

**Почему `spatial_graph_data` вместо `spatial_service`:** Ссылка на объект Python не сериализуется. Нужно хранить граф как примитивы (dict со списками узлов и рёбер), чтобы WorldSnapshot можно было сохранить/загрузить.

---

#### Шаг 3: Заполнять boundary_map при сборке снепшота

**Файл:** `backend/app/services/integration/world_snapshot_builder.py`

```python
# ДОБАВИТЬ в метод build_snapshot():

def build_snapshot(self, ctx: TickContext) -> WorldSnapshot:
    # ... существующий код ...
    
    # НОВОЕ: собрать boundary_map из spatial_registry
    boundary_map = self._build_boundary_map(
        campaign_id=ctx.campaign_id,
        location_id=ctx.location_id,
    )
    
    # НОВОЕ: сериализовать spatial_graph
    spatial_graph_data = self._serialize_spatial_graph(ctx.spatial_service)
    
    return WorldSnapshot(
        snapshot_id=generate_id(),
        created_at=utc_now_iso(),
        tick=ctx.current_tick,
        campaign_id=ctx.campaign_id,
        location_id=ctx.location_id,
        npc_positions=ctx.npc_positions,
        active_traversals=ctx.active_traversals,
        spatial_walls=ctx.walls,
        spatial_obstacles=ctx.obstacles,
        rng_seed=ctx.rng_seed,
        boundary_map=boundary_map,            # ← НОВОЕ
        spatial_graph_data=spatial_graph_data, # ← НОВОЕ
    )

def _build_boundary_map(self, campaign_id: str, location_id: str) -> BoundaryMap:
    """Собрать карту переходов из скомпилированных данных"""
    registry = self.spatial_registry.get_compiled(campaign_id)
    location_data = registry.get_location(location_id)
    
    edges = {}
    for transition in location_data.get("transitions", []):
        edge_id = transition["id"]
        edges[edge_id] = BoundaryEdge(
            edge_id=edge_id,
            target_location_id=transition["target_location_id"],
            from_node_id=transition["from_node_id"],
            to_node_id=transition["to_node_id"],
            bidirectional=transition.get("bidirectional", True),
            travel_time_ticks=transition.get("travel_time_ticks", 1),
            visibility=transition.get("visibility", "visible"),
            condition=transition.get("condition"),
        )
    
    return BoundaryMap(location_id=location_id, edges=edges)

def _serialize_spatial_graph(self, spatial_service) -> Dict:
    """Сериализовать граф в примитивы для хранения"""
    return {
        "nodes": [
            {"id": n.id, "x": n.x, "y": n.y, "type": n.type}
            for n in spatial_service.get_all_nodes()
        ],
        "edges": [
            {"from": e.from_id, "to": e.to_id, "weight": e.weight}
            for e in spatial_service.get_all_edges()
        ],
    }
```

---

#### Шаг 4: Заполнять boundary_map при компиляции кампании

**Файл:** `backend/app/services/spatial/graph_compiler.py` или `spatial_registry.py`

Данные переходов должны браться из location JSON. Нужно добавить формат переходов в карту:

```json
// frontend/map_editor/campaigns/my_cam/locations/tavern.json
// ДОБАВИТЬ секцию "transitions":

{
  "location_id": "tavern_silver_wolf",
  "rooms": [...],
  "nodes": [...],
  "transitions": [
    {
      "id": "tavern_to_market",
      "target_location_id": "market_square",
      "from_node_id": "door_main",
      "to_node_id": "gate_tavern_side",
      "bidirectional": true,
      "travel_time_ticks": 1,
      "visibility": "visible"
    },
    {
      "id": "tavern_to_street",
      "target_location_id": "city_street",
      "from_node_id": "door_back",
      "to_node_id": "alley_tavern_exit",
      "bidirectional": true,
      "travel_time_ticks": 2,
      "visibility": "hidden",
      "condition": "has_key_back_entrance"
    }
  ]
}
```

```python
# В graph_compiler.py — парсить transitions из JSON:

def compile_location(self, location_path: Path) -> CompiledLocation:
    with open(location_path) as f:
        data = json.load(f)
    
    # Существующий код: парсинг rooms, nodes, edges...
    
    # НОВОЕ: парсинг transitions
    transitions = data.get("transitions", [])
    
    return CompiledLocation(
        location_id=data["location_id"],
        graph=graph,
        walls=walls,
        obstacles=obstacles,
        transitions=transitions,  # ← НОВОЕ
    )
```

---

#### Шаг 5: Добавить переходы в default tavern

**Файл:** `frontend/map_editor/campaigns/default/locations/tavern.json`

Это кампания по умолчанию. Нужно:
1. Поставить `location_id: "tavern_silver_wolf"` (сейчас пустой!)
2. Добавить секцию `transitions` с выходами из таверны

---

### Как проверить

```python
# Тест: boundary_map заполнен и содержит переходы
def test_world_snapshot_has_boundary_map():
    snapshot = world_snapshot_builder.build_snapshot(ctx)
    
    assert snapshot.boundary_map is not None
    assert len(snapshot.boundary_map.edges) > 0
    
    edge = snapshot.boundary_map.get_transition_to("market_square")
    assert edge is not None
    assert edge.from_node_id == "door_main"
    assert edge.to_node_id == "gate_tavern_side"
    assert edge.bidirectional == True

# Тест: boundary_map переживает сериализацию
def test_boundary_map_round_trip():
    snapshot = world_snapshot_builder.build_snapshot(ctx)
    data = snapshot_to_dict(snapshot)
    restored = snapshot_from_dict(data)
    
    assert restored.boundary_map is not None
    assert len(restored.boundary_map.edges) == len(snapshot.boundary_map.edges)
```

---

### Связь с другими ТЗ

| ТЗ | Как зависит |
|-----|------------|
| **ТЗ-02** SpatialRegistry | Нужен boundary_map для find_path() между локациями |
| **ТЗ-14** Cross-location Navigation | Нужен boundary_map для TRANSIT intent |
| **ТЗ-15** Phase 7 State Commit | Нужен полный WorldSnapshot для атомарного коммита |

**Это ТЗ — фундамент для ТЗ-02 и ТЗ-14. Без него кросс-локационная навигация невозможна.**

---

### Порядок исправления

| # | Шаг | Время |
|---|-----|-------|
| 1 | Создать BoundaryEdge + BoundaryMap модели | 20 мин |
| 2 | Добавить поля в WorldSnapshot | 10 мин |
| 3 | _build_boundary_map() в snapshot builder | 30 мин |
| 4 | Формат transitions в location JSON | 20 мин |
| 5 | Парсинг transitions в graph_compiler | 20 мин |
| 6 | Исправить tavern.json (location_id + transitions) | 15 мин |
| 7 | Написать тесты | 20 мин |

**Итого:** ~2.5 часа

---

Давать следующее? Это **ТЗ-08: CalibrationEngine** (pass-through → EMA + strain).