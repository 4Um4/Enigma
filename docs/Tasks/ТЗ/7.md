## ТЗ-02: SpatialRegistry — кросс-локационная навигация

**Статус:** ⚠️ РАБОТАЕТ ЧАСТИЧНО | **Критичность:** HIGH | **Волна:** 3 (зависит от ТЗ-06)

---

### Суть проблемы одной строкой

SpatialService работает отлично внутри одной комнаты, но когда NPC хочет выйти из таверны на рынок — `get_node()` возвращает `None`, и движение молча отменяется. NPC застревают в одной локации навсегда.

---

### Что происходит сейчас

**Файл:** `backend/app/services/spatial/movement_engine.py` строки 153-180

```python
# СЕЙЧАС (сломано):
def _resolve_spatial_service(self, location_id: str) -> SpatialService:
    """Построить SpatialService для локации"""
    # Строит граф ТОЛЬКО для текущей локации
    graph = self._build_location_graph(location_id)
    return SpatialService(graph)

async def move_entity(self, npc_id: str, target_node_id: str):
    service = self._resolve_spatial_service(current_location_id)
    target = service.get_node(target_node_id)
    # Если target_node_id из другой локации:
    #   target = None
    #   movement silently dropped ← NPC никуда не идёт
```

**Визуально:**

```
Таверна (graph_tavern):          Рынок (graph_market):
  ┌─────────────┐                ┌─────────────┐
  │ bar  door_main│───???───│gate_tavern  market│
  │ table  door_back│───???───│alley        well│
  └─────────────┘                └─────────────┘
  
  NPC у door_main:               NPC у gate_tavern:
  "Хочу на рынок"                "Хочу в таверну"
  → get_node("gate_tavern")      → get_node("door_main")  
  → None ← НЕТ В ДАННОМ ГРАФЕ   → None ← НЕТ В ДАННОМ ГРАФЕ
  → движение отменено            → движение отменено
```

---

### Пошаговый план исправления

#### Шаг 1: Расширить SpatialService.find_path() для кросс-локационного поиска

**Файл:** `backend/app/services/spatial/spatial_service.py`

```python
from dataclasses import dataclass
from typing import Optional, List

@dataclass
class CrossLocationPath:
    """Маршрут через границу локаций"""
    # Часть 1: путь в текущей локации до boundary-узла
    local_path: List[str]           # список node_id в текущей локации
    boundary_edge: BoundaryEdge     # переход (из ТЗ-06)
    # Часть 2: входной узел в целевой локации
    target_entry_node: str
    target_location_id: str

class SpatialService:
    # ... существующий код ...
    
    def find_path(
        self,
        from_node: str,
        to_node: str,
        boundary_map: Optional[BoundaryMap] = None,
        allow_cross_location: bool = False,
    ) -> Union[List[str], CrossLocationPath, None]:
        """
        Найти путь. Если to_node не в текущем графе и
        allow_cross_location=True — попробовать через boundary_map.
        """
        # 1. Попробовать локальный путь
        local_path = self._find_local_path(from_node, to_node)
        if local_path is not None:
            return local_path
        
        # 2. Если кросс-локация разрешена и boundary_map есть
        if not allow_cross_location or boundary_map is None:
            return None
        
        # 3. Найти, через какой boundary-узел можно выйти
        for edge in boundary_map.edges.values():
            # Есть ли путь от from_node до boundary-узла в текущем графе?
            path_to_boundary = self._find_local_path(from_node, edge.from_node_id)
            if path_to_boundary is not None:
                return CrossLocationPath(
                    local_path=path_to_boundary,
                    boundary_edge=edge,
                    target_entry_node=edge.to_node_id,
                    target_location_id=edge.target_location_id,
                )
        
        return None  # нет доступного перехода
```

---

#### Шаг 2: Обновить MovementEngine для обработки CrossLocationPath

**Файл:** `backend/app/services/spatial/movement_engine.py`

```python
class MovementEngine:
    
    async def move_entity(
        self,
        npc_id: str,
        target_node_id: str,
        boundary_map: Optional[BoundaryMap] = None,
        allow_cross_location: bool = False,
    ) -> MovementResult:
        """Переместить NPC. Поддерживает кросс-локационные переходы."""
        
        current_location = self._get_npc_location(npc_id)
        service = self._resolve_spatial_service(current_location)
        current_node = self._get_npc_position(npc_id)
        
        path = service.find_path(
            from_node=current_node,
            to_node=target_node_id,
            boundary_map=boundary_map,
            allow_cross_location=allow_cross_location,
        )
        
        if path is None:
            return MovementResult(success=False, reason="no_path")
        
        # ЛОКАЛЬНЫЙ путь (внутри одной локации)
        if isinstance(path, list):
            next_node = path[1] if len(path) > 1 else path[0]
            self._set_npc_position(npc_id, next_node)
            return MovementResult(
                success=True,
                new_position=next_node,
                location_changed=False,
            )
        
        # КРОСС-ЛОКАЦИОННЫЙ путь
        if isinstance(path, CrossLocationPath):
            # Шаг А: довести NPC до boundary-узла в текущей локации
            boundary_node = path.boundary_edge.from_node_id
            self._set_npc_position(npc_id, boundary_node)
            
            # Шаг Б: переключить локацию
            old_location = current_location
            new_location = path.target_location_id
            self._set_npc_location(npc_id, new_location)
            
            # Шаг В: установить позицию в entry-узле новой локации
            self._set_npc_position(npc_id, path.target_entry_node)
            
            # Шаг Г: сгенерировать событие перехода
            await self.event_bus.publish(SpatialEvent(
                event_type="CROSS_LOCATION_TRANSITION",
                npc_id=npc_id,
                data={
                    "from_location": old_location,
                    "to_location": new_location,
                    "from_node": boundary_node,
                    "to_node": path.target_entry_node,
                    "travel_time": path.boundary_edge.travel_time_ticks,
                },
            ))
            
            return MovementResult(
                success=True,
                new_position=path.target_entry_node,
                location_changed=True,
                old_location=old_location,
                new_location=new_location,
            )
```

---

#### Шаг 3: Передавать boundary_map в MovementEngine из TickContext

**Файл:** `backend/app/services/game_loop/tick_context.py`

```python
# ДОБАВИТЬ в TickContext / TickInput:
boundary_map: Optional[BoundaryMap] = None
```

**Файл:** `backend/app/services/npc/npc_tick_pipeline.py`

```python
# При вызове movement_engine:
result = await self.movement_engine.move_entity(
    npc_id=npc_id,
    target_node_id=target_node,
    boundary_map=ctx.boundary_map,       # ← из WorldSnapshot
    allow_cross_location=True,            # ← разрешить переходы
)
```

---

#### Шаг 4: Реализовать SemanticIndex (ADR-301)

NPC должен уметь говорить «хочу в кузницу», а не «хочу в location_id=smithy_01». SemanticIndex переводит семантические запросы в location_id.

**Новый файл:** `backend/app/services/spatial/semantic_index.py`

```python
class SemanticIndex:
    """Поиск локаций по семантическим тегам"""
    
    def __init__(self):
        # tag → List[location_id]
        self._index: Dict[str, List[str]] = {}
    
    def index_campaign(self, campaign_data: dict):
        """Индексировать все локации кампании"""
        for loc_id, loc_data in campaign_data.get("locations", {}).items():
            tags = loc_data.get("tags", [])
            name = loc_data.get("name", "").lower()
            
            # Автоматические теги из имени
            auto_tags = self._extract_tags(name)
            all_tags = set(tags + auto_tags)
            
            # Добавить NPC-типы, которые обычно здесь бывают
            npc_types = loc_data.get("npc_types", [])
            for npc_type in npc_types:
                all_tags.add(f"work_{npc_type}")
            
            for tag in all_tags:
                if tag not in self._index:
                    self._index[tag] = []
                self._index[tag].append(loc_id)
    
    def find_location(self, query: str) -> Optional[str]:
        """Найти location_id по семантическому запросу"""
        query_lower = query.lower().strip()
        
        # Прямой поиск по тегу
        if query_lower in self._index:
            return self._index[query_lower][0]  # первый результат
        
        # Fuzzy matching: частичное совпадение
        for tag, locations in self._index.items():
            if query_lower in tag or tag in query_lower:
                return locations[0]
        
        return None
    
    def _extract_tags(self, name: str) -> List[str]:
        """Извлечь семантические теги из названия локации"""
        tag_map = {
            "таверна": ["tavern", "drink", "food", "rest", "shelter"],
            "рынок": ["market", "trade", "shop", "buy"],
            "кузница": ["smithy", "forge", "craft", "repair"],
            "казармы": ["barracks", "guard", "sleep", "military"],
            "храм": ["temple", "pray", "heal", "shrine"],
            "склад": ["warehouse", "storage", "goods"],
            "улица": ["street", "travel", "outside"],
            "ворота": ["gate", "exit", "entrance"],
        }
        tags = []
        for keyword, tag_list in tag_map.items():
            if keyword in name:
                tags.extend(tag_list)
        return tags
```

**Подключение:**

```python
# В npc_tick_pipeline.py:
# Когда NPC формирует TRANSIT intent:
target_location = self.semantic_index.find_location("кузница")
# → "smithy_01"

# Или из NeedDrive:
if need_drive.drive_type == NeedType.TOOLS:
    target = self.semantic_index.find_location("smithy")
elif need_drive.drive_type == NeedType.FOOD:
    target = self.semantic_index.find_location("tavern")
elif need_drive.drive_type == NeedType.SHELTER:
    target = self.semantic_index.find_location("inn")
```

---

#### Шаг 5: Скомпилировать spatial_registry для my_cam

**Проблема:** Кампания `my_cam` не имеет `compiled/spatial_registry.json`.

```python
# Запустить компиляцию:
from backend.app.services.spatial.graph_compiler import SpatialCompilationOrchestrator

orchestrator = SpatialCompilationOrchestrator(
    campaigns_dir="frontend/map_editor/campaigns"
)
orchestrator.force_rebuild("my_cam")
# Создаёт compiled/spatial_registry.json + boundary_map
```

---

### Как проверить

```python
# Тест: кросс-локационное перемещение
async def test_cross_location_movement():
    # NPC в таверне, хочет на рынок
    npc = create_test_npc(location="tavern_silver_wolf", position="door_main")
    
    boundary_map = snapshot.boundary_map  # из ТЗ-06
    
    result = await movement_engine.move_entity(
        npc_id=npc.id,
        target_node_id="gate_tavern",  # узел в market_square
        boundary_map=boundary_map,
        allow_cross_location=True,
    )
    
    assert result.success == True
    assert result.location_changed == True
    assert result.old_location == "tavern_silver_wolf"
    assert result.new_location == "market_square"
    assert result.new_position == "gate_tavern"

# Тест: SemanticIndex
def test_semantic_index():
    index = SemanticIndex()
    index.index_campaign(campaign_data)
    
    assert index.find_location("кузница") == "smithy_01"
    assert index.find_location("tavern") == "tavern_silver_wolf"
    assert index.find_location("market") == "market_square"
```

---

### Порядок исправления

| # | Шаг | Время |
|---|-----|-------|
| 1 | CrossLocationPath модель + find_path() | 45 мин |
| 2 | MovementEngine обработка CrossLocationPath | 45 мин |
| 3 | boundary_map в TickContext | 15 мин |
| 4 | SemanticIndex реализация | 1 час |
| 5 | Подключение SemanticIndex к NeedDrive | 30 мин |
| 6 | Компиляция my_cam | 15 мин |
| 7 | Тесты | 30 мин |

**Итого:** ~3.5 часа

**Предпосылки:** ТЗ-06 (boundary_map) должен быть выполнен первым.

---

Давать следующее? Это **ТЗ-09: WorldScheduler — активация** (мир начинает тикать сам).