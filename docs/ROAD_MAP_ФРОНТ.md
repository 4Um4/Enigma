Вот финальная, архитектурно выверенная инструкция для LLM-строителя. Все 5 зазоров закрыты. Глобальные координаты сохранены. Трёхслойная модель зацементирована. Готово к копипасту.

---

# 📜 ИНСТРУКЦИЯ ДЛЯ LLM-СТРОИТЕЛЯ: SpatialService v1.2 (Production-Ready)

## 🎯 Контекст и реальность
В проекте существует `map_editor`, экспортирующий узлы в **абсолютных мировых координатах** `(x, y)` относительно `(0,0)`. Все локации и объекты уже размещены в едином глобальном пространстве.  
**Задача:** построить `SpatialService`, который работает нативно с мировыми координатами, но управляет навигацией через **трёхслойную модель**: Геометрия `(x,y)` → Топология `zone_id/level` → Семантика `role/tags`.  
Сервис — **чистый механизм**. Политика (куда идти, зачем, когда менять путь) живёт в `DecisionHub`/`LifeEngine`/`MovementEngine`.

## 🚫 ЖЁСТКИЕ ЗАПРЕТЫ
- ❌ Локальные координаты, смещения, трансформации систем координат
- ❌ Мутации состояния внутри сервиса (только READ)
- ❌ Принятие решений (policy) в сервисе
- ❌ Прямой доступ к графу вне `SpatialService`
- ❌ Игнорирование топологии при поиске (геометрия вторична)
- ❌ Хранение путей или состояния NPC внутри сервиса
- ❌ Глобальные переменные, синглтоны, скрытые зависимости

## 📦 Целевые файлы
```
backend/app/models/spatial_contracts.py      # Типы, Enum, dataclass
backend/app/services/spatial/role_resolver.py # Семантический маппинг
backend/app/services/spatial/graph_compiler.py # editor JSON → runtime graph + alias_map
backend/app/services/spatial/spatial_service.py # Единый API (ядро)
backend/app/services/spatial/spatial_overlay.py # Динамическое состояние + резервации
```

## 🔑 Контракты (реализовать точно)
```python
# spatial_contracts.py
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, Set, List, Dict, Tuple

class NodeRole(Enum):
    BAR = "bar"
    BED = "bed"
    ENTRANCE = "entrance"
    TABLE = "table"
    WORKBENCH = "workbench"
    MARKET = "market"
    TRANSITION = "transition"  # Лестницы, двери, люки
    DEFAULT = "default"

class Urgency(Enum):
    NORMAL = "normal"
    URGENT = "urgent"

@dataclass(frozen=True)
class NodeRef:
    node_id: str          # Канонический: "location_id:editor_id"
    role: NodeRole
    tags: List[str]
    x: float              # АБСОЛЮТНАЯ мировая координата
    y: float
    zone_id: str          # Топология: всегда = location_id
    level: Optional[str]  # Вертикальность: ground, basement, floor_2

@dataclass
class SpatialOverlay:
    """Динамическое состояние сцены. Не сериализуется в граф."""
    blocked_nodes: Set[str] = field(default_factory=set)
    open_doors: Set[str] = field(default_factory=set)
    crowd_density: Dict[str, float] = field(default_factory=dict)
    risk_zones: Dict[str, float] = field(default_factory=dict)
    light_levels: Dict[str, float] = field(default_factory=dict)
    reserved_nodes: Dict[str, str] = field(default_factory=dict)  # node_id → npc_id

@dataclass
class NPCPathState:
    """Хранится в NPCState/MovementEngine, НЕ в SpatialService."""
    active_path: List[NodeRef] = field(default_factory=list)
    path_index: int = 0
    target_node: Optional[NodeRef] = None
    overlay_hash_at_compute: str = ""
```

## 🧠 Ядро логики (закрытые зазоры)

### 1. RoleResolver (приоритетная трансляция)
```python
# role_resolver.py
def resolve_role(node_label: str, editor_tags: Optional[List[str]] = None, manifest_override: Optional[NodeRole] = None) -> NodeRole:
    if manifest_override: return manifest_override
    if editor_tags: ... # будущий слой
    label_lower = node_label.lower()
    if any(k in label_lower for k in ["стойка", "бар", "bar"]): return NodeRole.BAR
    if any(k in label_lower for k in ["кровать", "спальня", "bed"]): return NodeRole.BED
    if any(k in label_lower for k in ["вход", "дверь", "entrance", "люк"]): return NodeRole.ENTRANCE
    if any(k in label_lower for k in ["стол", "table"]): return NodeRole.TABLE
    return NodeRole.DEFAULT
```

### 2. Нормализация ID (обратная совместимость)
- Внутри системы **ТОЛЬКО** канонические ID: `f"{location_id}:{editor_id}"`
- На входе: `normalize_id(raw_id, alias_map) → canonical_id`
- `alias_map` строится в `graph_compiler` из legacy-данных (`{"bar_area": "tavern:bar_area"}`)
- На выходе денормализация запрещена, кроме явных legacy-мостов с `@deprecated`

### 3. Резервация узлов (конкуренция)
- `resolve_node` фильтрует `overlay.reserved_nodes`. Узел, занятый другим NPC, исключается из кандидатов.
- Исключение: `urgency == URGENT` или `requesting_npc_id == reserved_npc_id`

### 4. Pathfinding & Active Path (производительность)
- `SpatialService.find_path()` вычисляет маршрут **один раз**.
- NPC хранит результат в `NPCPathState.active_path` и шагает по нему (`path_index += 1`).
- Пересчёт только при: смене intent, инвалидации overlay (`overlay_hash` изменился), блокировке текущего пути.
- Кэш путей вторичен. Ключ: `(start_id, target_id, overlay_hash, urgency)`.

### 5. Скоринг целей (семантика > геометрия)
`resolve_node` использует взвешенный скоринг, не чистую дистанцию:
```
score = 
  dist_weight(euclidean) +
  tag_match_bonus +
  safety_penalty(risk, light) +
  reservation_penalty
```
Топологический фильтр (`zone_id`, `level`) применяется **до** скоринга.

## 🛠️ Пошаговый план реализации

### Шаг 1: `graph_compiler.py`
- Читает editor JSON. Сохраняет абсолютные `x, y`.
- `zone_id = location_id` (всегда).
- Вызывает `RoleResolver` для каждого узла.
- Генерирует канонические ID. Строит `alias_map` из legacy-форматов.
- Валидирует связность (BFS). Логирует изолированные узлы.
- Экспортирует `runtime/spatial_graph.json` + `alias_map.json`.

### Шаг 2: `spatial_overlay.py`
- Инициализируется из `scene_state` каждый тик.
- Содержит `reserved_nodes`. Метод `try_reserve(node_id, npc_id) -> bool`.
- Метод `compute_hash() -> str` для инвалидации путей.

### Шаг 3: `spatial_service.py` (ядро)
- `__init__(graph, overlay, alias_map)`
- `normalize_id(raw) -> canonical`
- `resolve_node(role, origin_xy, origin_zone, origin_level, filters, urgency, requesting_npc_id) -> Optional[NodeRef]`
  - Фильтр по топологии → фильтр по резервациям → скоринг → возврат лучшего
- `find_path(start_xy, target_node, urgency) -> List[NodeRef]`
  - A* с динамической стоимостью рёбер (`crowd`, `risk`, `light`, `blocked`)
  - `urgency` снижает штрафы, но не обнуляет их. Стены/блокировки остаются дорогими.
- `is_reachable(node, urgency) -> bool`
- Все методы чистые, детерминированные, без побочных эффектов.

### Шаг 4: Интеграция (мосты)
- `LifeEngine`: `activity_map` использует `NodeRole`. Вызывает `resolve_node()`.
- `MovementEngine`: хранит `NPCPathState`. Запрашивает `find_path()` только при смене цели или инвалидации overlay. Шагает по `active_path`.
- `DecisionHub`: передаёт `urgency` при `FLEE`/`stress>80`.
- Прямые обращения к графу помечаются `# @deprecated: use SpatialService`.

## ✅ Критерии приёмки
1. `grep -rn "\.graph\|graph\[" backend/app/services/ | grep -v spatial_service.py | grep -v graph_compiler.py` → **0**
2. Все `x,y` абсолютные. Нет `local_`, `offset`, `transform`.
3. `zone_id` всегда равен `location_id`. Поиск никогда не пересекает зоны без `TRANSITION` узла.
4. `alias_map` корректно транслирует legacy-ID в канонические. Внутри системы только канонические.
5. `reserved_nodes` блокирует выбор узла другим NPC. `URGENT` снижает штраф, но не ломает логику.
6. `find_path` возвращает валидный маршрут. NPC хранит `active_path` и не вызывает A* каждый тик.
7. Тесты проходят:
   - `test_role_resolver_priority`
   - `test_topology_filtering`
   - `test_reservation_exclusion`
   - `test_urgency_weight_modification`
   - `test_path_computation_once`
   - `test_alias_normalization`
8. Ядро `spatial_service.py` < 300 строк.

## ⚠️ Edge Cases
- Граф несвязный → fallback на ближайший `TRANSITION` или `DEFAULT` узел + `logger.warning`
- `resolve_node` возвращает `None` → `LifeEngine` → `IDLE`/`OBSERVE`
- Overlay пустой → работа на baseline graph
- `origin_xy` не передан → детерминированный fallback (сортировка по ID)
- Путь заблокирован посередине → `MovementEngine` ловит `is_reachable(next_node)==False` → запрашивает пересчёт

## 📌 Финальное правило
**SpatialService = механизм. DecisionHub/LifeEngine = политика.**  
Сервис отвечает на вопросы: «Где узел с ролью X в моей зоне?», «Как дойти с учётом толпы/риска/резерваций?», «Сколько это стоит?».  
Он не решает, куда идти. Не хранит пути NPC. Не мутирует мир.  
Геометрия — для рендера и дистанций. Топология — для связности. Семантика — для поведения.  
Все координаты глобальные. Все ID канонические. Все пути кэшируются на стороне NPC.

Если всё сходится → генерируй код. Не импровизируй с архитектурой. Следуй контрактам буквально. При неоднозначности → спроси до генерации.