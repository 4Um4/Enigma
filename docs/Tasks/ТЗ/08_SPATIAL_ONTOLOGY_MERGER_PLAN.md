# ТЕХНИЧЕСКИЙ ПЛАН: Слияние трёх пространственных онтологий

**Проблема:** Три параллельные вселенные, которые не разговаривают  
**Виновник:** Editor, Runtime и Frontend создали независимые онтологии одного и того же пространства  
**Статус:** Критический раскол, требует срочного слияния  
**Решение:** v2.2 Mutation Pipeline как единая точка консистентности

---

## ДИАГНОЗ: ТРИ ПАРАЛЛЕЛЬНЫЕ ВСЕЛЕННЫЕ

### Universe 1: Editor (Map Editor / JSON конфигурация)

```json
{
  "locations": [
    {
      "id": "inn_rooms",
      "name": "спальни",
      "npcs": [
        {
          "id": "lucy_maid",
          "position": {"x": 10, "y": 5},
          "schedule": {
            "08:00": "serving_table_3",      // ← Имя из Editor
            "14:00": "main_hall",            // ← Имя из Editor
          }
        }
      ]
    }
  ]
}
```

**Характеристики:**
- Оперирует **микро-локациями** (`serving_table_3`, `main_hall`)
- Плоская геометрия: `{x: int, y: int}`
- Имена из рук человека (устаревают, меняются)
- Статичные координаты

---

### Universe 2: Runtime (SpatialService / CFRM)

```python
class ClusterGraph:
    """Граф узлов кластера"""
    nodes = {
        "hall_center": {"x": 50.5, "y": 45.2},      # ← Имя из Runtime
        "entrance": {"x": 0, "y": 0},               # ← Имя из Runtime
    }
    
    edges = {
        ("hall_center", "entrance"): 5.0,
    }
    
class SpatialService:
    """Истина о координатах"""
    graphs = {
        "inn_rooms": ClusterGraph(...),
        "tavern": ClusterGraph(...),
    }
```

**Характеристики:**
- Оперирует **макро-графами** и семантическими узлами
- Вложенная геометрия: `local_position: {x: float, y: float}`
- Имена из кода/архитектуры (стабильные)
- Граф-структуры (рёбра, расстояния)

---

### Universe 3: Frontend (game_screen.py)

```python
npc_data = {
    "npc_id": "lucy_maid",
    "x": 0,                           # ← Плоское поле
    "y": 0,
    "local_position": {               # ← Вложенное поле
        "x": 10.5,
        "y": 5.2
    },
    "cluster_id": "inn_rooms",
    "animation_state": "idle"
}

# Фронтенд рендерит:
render_npc(
    x=npc_data.get("local_position", {"x": 0, "y": 0})["x"],
    y=npc_data.get("local_position", {"x": 0, "y": 0})["y"]
)
# Если local_position отсутствует → (0, 0) → NPC в углу карты
```

**Характеристики:**
- Оперирует **DTO на границе API**
- Ожидает вложенную структуру: `local_position: {x, y}`
- Падает в дефолты при несоответствии
- Отрисовывает кэшированное состояние

---

## ПОЧЕМУ ОНИ КОНФЛИКТУЮТ

### Конфликт 1: Имена узлов

| Universe | Имя | Статус |
|----------|-----|--------|
| Editor | `serving_table_3` | Расписание из JSON |
| Runtime | `table_nw_inner` | Граф узлов |
| Frontend | `local_position: {10.5, 5.2}` | DTO |

**Когда Люся нужно подойти к `serving_table_3` (из Editor):**
1. Runtime ищет узел `serving_table_3` в графе `inn_rooms`
2. Узла с таким именем нет (он называется `table_nw_inner` в Runtime)
3. `MovementEngine` возвращает `None` или бросает исключение
4. NPC парализован (не может найти маршрут)

---

### Конфликт 2: Геометрия

| Universe | Формат | Отвечает за |
|----------|--------|------------|
| Editor | `{x: int, y: int}` | Исходные позиции в конфиге |
| Runtime | `local_position: {x: float, y: float}` | Текущее положение в симуляции |
| Frontend | Ожидает `local_position` | Рендеринг |

**Когда Runtime обновляет позицию через `SceneChange`:**
```python
# Бэкенд (ошибка):
scene_change.position = (15, 10)  # Плоское поле

# Фронтенд ожидает:
npc_data["local_position"] = {"x": 15, "y": 10}

# Результат: Фронтенд не находит local_position → дефолт {0, 0}
```

NPC телепортируется в угол.

---

### Конфликт 3: Архетип теряется

| Universe | Архетип | Используется для |
|----------|---------|------------------|
| Editor | `_archetype: "maid"` | Социальная физика (легитимность приказа) |
| Runtime | Нет, поле не сохраняется | - |
| Социальная физика | Ищет `_archetype` | Считает ObediencePressure |

**Когда Люся получает приказ:**
1. Runtime не знает, что она служанка (потеряно при загрузке)
2. Социальная физика считает легитимность только по страху
3. `ObediencePressure = 0.00` (потому что `fear = 0.18 < threshold = 0.3`)
4. Люся игнорирует приказ

---

## КАУЗАЛЬНЫЙ РАЗРЫВ: AgentAction.intent

**Файл:** `backend/app/services/npc/npc_tick_pipeline.py:474`

```python
# Код пытается сделать это:
decision.intent = Intent.APPROACH

# Но AgentAction определён так:
@dataclass
class AgentAction:
    @property
    def intent(self) -> Intent:
        return self.decision.intent  # ← Свойство без сеттера!
    
    # НЕТ сеттера:
    # @intent.setter
    # def intent(self, value: Intent): ...
```

**Результат:**
```python
AttributeError: property 'intent' of 'AgentAction' object has no setter
# Exception глушится в try/except
# NPC не получает решения
```

**Следствие:** SHI = 0% (NPC не принимают решений вообще).

---

## v2.2 РЕШЕНИЕ: Единая Mutation Pipeline

### Принцип: "Только Apply меняет состояние"

```
Event (Editor, Runtime, Frontend)
    ↓ (Signal)
Signal (распарсить, нормализовать)
    ↓ (Evaluation)
Evaluation (проверить, относится ли к нам)
    ↓ (Proposal)
MutationProposal (что именно менять?)
    ↓ (Validation через MIK)
Validation (совместимо ли с инвариантами?)
    ↓ (Apply → ЕДИНСТВЕННАЯ точка мутации)
Apply (менять состояние ЗДЕСЬ И ТОЛЬКО ЗДЕСЬ)
    ↓ (Causal History)
CausalHistory (записать, почему изменилось)
```

---

## ПРАКТИЧЕСКИЙ ПЛАН

### Шаг 1: Унификация пространства (Alias Map)

```python
class SpatialAliasMap:
    """Мост между Editor именами и Runtime узлами"""
    
    mapping = {
        # Editor → Runtime
        "serving_table_3": "table_nw_inner",
        "main_hall": "hall_center",
        "entrance": "entrance",
        "sleeping_alcove_1": "bed_nw_1",
    }
    
    def resolve(self, editor_name: str, location_id: str) -> NodeRef:
        """Преобразовать имя Editor в валидный NodeRef"""
        if editor_name not in self.mapping:
            raise ValueError(f"Unknown location: {editor_name}")
        
        runtime_name = self.mapping[editor_name]
        
        # Проверить, что узел существует в целевой локации
        if not SpatialService.has_node(location_id, runtime_name):
            raise ValueError(
                f"Node {runtime_name} not found in {location_id}"
            )
        
        return NodeRef(location_id=location_id, node_id=runtime_name)
```

**Использование в расписаниях:**
```python
# Было (Editor):
schedule = {
    "08:00": "serving_table_3",  # Строка, может быть неправильной
}

# Стало (Runtime):
schedule = {
    "08:00": SpatialAliasMap.resolve("serving_table_3", "inn_rooms"),
    # → NodeRef(location_id="inn_rooms", node_id="table_nw_inner")
}
```

---

### Шаг 2: Строгий DTO контракт (local_position)

```python
class NPCPositionDTO:
    """Граница между Runtime и Frontend"""
    
    npc_id: str
    location_id: str
    cluster_id: str
    
    # ВСЕГДА обновляем обе координаты синхронно:
    position_global: {"x": float, "y": float}      # Глобальная
    local_position: {"x": float, "y": float}       # Локальная (для рендеринга)
    
    # Флаги для фронтенда:
    is_valid: bool  # Если False → дефолт, не рендер
    animation_state: str
    
    # ЗАПРЕТ на плоские x/y (устаревшие):
    # x: float  ← НЕ ИСПОЛЬЗУЕТСЯ
    # y: float  ← НЕ ИСПОЛЬЗУЕТСЯ

# Валидация на Apply:
def apply_position_mutation(npc_id: str, new_position: Vector2) -> NPCPositionDTO:
    """ЕДИНСТВЕННОЕ место, где обновляется позиция"""
    
    # 1. Проверить через MIK (владелец = SpatialService)
    if owner_of("position") != "SpatialService":
        raise ArchitectureError("Only SpatialService can change position")
    
    # 2. Обновить ОБЯЗАТЕЛЬНО обе координаты
    npc = get_npc(npc_id)
    npc.position_global = new_position
    npc.local_position = SpatialService.to_local_coordinates(
        new_position, 
        npc.location_id
    )
    
    # 3. Создать DTO для фронтенда
    return NPCPositionDTO(
        npc_id=npc_id,
        location_id=npc.location_id,
        cluster_id=npc.location_id,
        position_global=npc.position_global,
        local_position=npc.local_position,
        is_valid=True,
        animation_state=npc.animation.current_state
    )
```

---

### Шаг 3: Инъекция архетипа в Runtime

```python
class NPCState:
    """Runtime состояние NPC"""
    
    npc_id: str
    location_id: str
    
    # Архетип ВСЕГДА присутствует (инъектирован при загрузке)
    archetype: str = None  # "maid", "guard", "thief", etc.
    
    # Социальная физика может на него опираться
    obedience_pressure: float = 0.0

def load_npc_from_config(config: dict) -> NPCState:
    """При загрузке из конфига сохранить архетип"""
    
    npc = NPCState(
        npc_id=config["id"],
        location_id=config.get("location"),
        archetype=config.get("_archetype", "commoner"),  # ← Инъекция
    )
    
    return npc

# Социальная физика:
def calculate_obedience_pressure(npc: NPCState, command: Order) -> float:
    """Легитимность приказа"""
    
    # Служанка ОБЯЗАНА подчиняться (независимо от страха)
    if npc.archetype == "maid":
        return 1.0  # Максимальная легитимность
    
    # Охранник обязан подчиняться командиру
    elif npc.archetype == "guard":
        # Зависит от рангов, контекста
        return calculate_guard_obedience(npc, command)
    
    # Остальные подчиняются по страху и социальному давлению
    else:
        fear_component = npc.drives.survival
        social_component = npc.social_pressure
        return (fear_component + social_component) / 2
```

---

### Шаг 4: Исправление AgentAction.intent

**Было (неправильно):**
```python
@dataclass
class AgentAction:
    @property
    def intent(self) -> Intent:
        return self.decision.intent
    # НЕТ СЕТТЕРА!
```

**Стало (правильно):**
```python
@dataclass
class AgentAction:
    decision: DecisionResult  # Mutable dataclass
    
    def get_intent(self) -> Intent:
        """Получить текущее намерение"""
        return self.decision.intent
    
    def set_intent(self, new_intent: Intent) -> "AgentAction":
        """Создать новый AgentAction с обновленным intent"""
        import dataclasses
        
        new_decision = dataclasses.replace(
            self.decision,
            intent=new_intent
        )
        
        return dataclasses.replace(
            self,
            decision=new_decision
        )
```

**Или переписать весь пайплайн чтобы не мутировать:**
```python
def apply_reflex_move_intent(decision: DecisionResult) -> DecisionResult:
    """Не мутируем, создаем новый decision"""
    
    # Старое (ошибка):
    # decision.intent = Intent.APPROACH  # ← КРАШ
    
    # Новое (правильно):
    return dataclasses.replace(
        decision,
        intent=Intent.APPROACH
    )
```

---

## СПРИНТ РЕАЛИЗАЦИИ

### День 1: Alias Map + Архетип
- [ ] Создать `SpatialAliasMap` класс
- [ ] Загружать архетип при инициализации NPC
- [ ] Обновить социальную физику

### День 2: DTO контракт
- [ ] Переписать `NPCPositionDTO` с обоими координатами
- [ ] Обновить `StateApplicator` (Apply через MIK)
- [ ] Добавить валидацию

### День 3: AgentAction fix
- [ ] Убить `@property` без сеттера
- [ ] Переписать пайплайн на `dataclasses.replace()`
- [ ] Протестировать все 6 NPC

### День 4: Интеграция + тесты
- [ ] CDS отслеживает все мутации
- [ ] Тесты для каждой Universe
- [ ] Проверить, что NPC подходят и решают

---

## ПРОВЕРОЧНЫЕ ТЕСТЫ

```python
def test_spatial_alias_resolution():
    """Имена Editor корректно маппируются на Runtime узлы"""
    node_ref = SpatialAliasMap.resolve("serving_table_3", "inn_rooms")
    assert node_ref.location_id == "inn_rooms"
    assert node_ref.node_id == "table_nw_inner"
    assert SpatialService.has_node(node_ref.location_id, node_ref.node_id)

def test_position_mutation_updates_both_coordinates():
    """Apply обновляет local_position, не оставляя дефолты"""
    npc = get_npc("lucy_maid")
    new_position = Vector2(20.0, 15.0)
    
    dto = apply_position_mutation("lucy_maid", new_position)
    
    assert dto.is_valid == True
    assert dto.local_position["x"] == 20.0
    assert dto.local_position["y"] == 15.0
    # Фронтенд ТОЧНО найдет координаты, не упадет в (0, 0)

def test_maid_obedience_pressure():
    """Служанка всегда подчиняется (архетип инъектирован)"""
    npc = get_npc("lucy_maid")
    assert npc.archetype == "maid"
    
    pressure = calculate_obedience_pressure(npc, Order("go to kitchen"))
    assert pressure == 1.0  # Максимальная легитимность

def test_agent_action_intent_not_crashing():
    """AgentAction.intent можно обновить без краша"""
    decision = DecisionResult(intent=Intent.IDLE)
    action = AgentAction(decision=decision)
    
    # Было (КРАШ):
    # action.intent = Intent.APPROACH
    
    # Стало (OK):
    new_action = action.set_intent(Intent.APPROACH)
    assert new_action.decision.intent == Intent.APPROACH
```

---

## ИТОГ

После реализации этого плана:

| Проблема | Статус |
|----------|--------|
| NPC парализованы (не находят узлы) | ✅ Исправлено (Alias Map) |
| NPC телепортируются в (0, 0) | ✅ Исправлено (обоязательный local_position) |
| SHI = 0% (решения не принимаются) | ✅ Исправлено (AgentAction fix) |
| Люся не подчиняется | ✅ Исправлено (архетип инъектирован) |

**Три параллельные вселенные сливаются в одну через Mutation Pipeline.**



## Что на самом деле нужно (если идти до конца)

Не AliasMap.

Не Mutation Pipeline.

А:

🔷 Spatial Ontology Layer (SOL)
SOL = единая модель места
class SpatialEntity:
    id: str
    semantic_name: str
    graph_node: NodeRef
    geometry: Polygon | Point
    aliases: set[str]
Тогда:
слой	роль
Editor	пишет aliases
Runtime	работает с graph_node
Frontend	читает projection
SOL	единственный источник смысла
8. Критическая разница
Сейчас:

ты переводишь между мирами

Правильная модель:

все миры читают один слой смысла

9. Самый опасный баг в твоём плане (AgentAction)

Ты прав в баге, но есть глубже:

проблема не в setter’е

а в том что:

DecisionResult и Intent принадлежат разным слоям ответственности

Сейчас у тебя смешано:
реакция
решение
действие
намерение
Это ведёт к:

невозможности построить причинную трассировку решений

10. Про архетипы (очень важно)

Твой фикс:

“инъектировать _archetype”

✔ правильный в прагматике
❌ но концептуально слабый

Потому что:

архетип — это не поле NPC

это:

слой интерпретации действия

иначе получится:
данные есть
но логика их не использует системно