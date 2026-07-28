# ENIGMA — УМНЫЙ РЕДАКТОР КАРТ И ПОЧИНКА СНА NPC

**Дата:** 2026-07-28
**Версия:** 2.0 (полная переработка кроватей + все шаги для сна)
**Цель:** Сделать так, чтобы все 6 NPC спали в своих койкоместах, и чтобы редактор карт не позволял создавать сломанные миры. NPC распределяют кровати по правилам (не псевдослучайно), дизайнер может вручную назначать кровати через UI редактора.

**Принцип:** Никаких ручных правок JSON. Редактор умнее — он режет стены под дверями сам, он валидирует всё при сохранении, он говорит по-русски, что сломано. Кровати распределяются по правилам приоритета (архетип → локация → fallback), с возможностью ручного назначения в редакторе.

---

## §0. ФИЛОСОФИЯ — ПЯТЬ ПРИНЦИПОВ

### Принцип 1: Источник истины — редактор, не JSON

JSON — это сериализованное состояние редактора, не первичный источник. Любая ошибка, которую можно поймать в редакторе, должна ловиться там, а не в runtime. NPC не должны молча не спать из-за того, что дверь забыли привязать к стене.

### Принцип 2: Геометрия важнее топологии

Связи между узлами — это намерение дизайнера. Геометрия (стены, объекты) — это физическая реальность. Если связь пересекает стену — связь неверна, и редактор показывает это визуально красной линией на канвасе, до сохранения.

### Принцип 3: Кровати по правилам, не псевдослучайно

NPC занимают кровати по **правилам приоритета**, основанным на архетипе и локации. Трактирщик и служанка спят в трактире. Стражник спит в караульне. Остальные — в палатках. Если «своя» кровать занята или недостижима — fallback по чётким правилам, не случайность.

### Принцип 4: Ручное назначение как override

Дизайнер может кликнуть на кровать в редакторе и выбрать NPC из списка. Это **override** — он имеет приоритет над правилами. Сохраняется в JSON как `owner_npc_id`. В будущем логика правил улучшится, и override станет опциональным.

### Принцип 5: Save = Contract

Кнопка «Сохранить кампанию» — это контракт, что мир играбелен. Если сохранение прошло — NPC гарантированно смогут спать. Любая ошибка, несовместимая с этим контрактом, блокирует сохранение.

---

## §1. АВТО-РЕЗКА СТЕН ПОД ДВЕРЯМИ (вместо ручного `wall_id`)

### Проблема

Сейчас, чтобы дверь «пробила» стену, нужно знать ID стены и добавить объекту-двери поле `wall_id: "wall_6_vertical"`. Если ID дублируется (как `wall_6` в `tavern.json` — вертикальная и горизонтальная), компилятор не понимает, в какой стене резать, и не режет ни в одной. Результат: глухая стена, изолированные узлы, NPC не спят.

### Решение

Дверь сама находит свою стену по координатам. Редактор при сохранении автоматически:

1. Находит все стены, проходящие через точку `(door.x, door.y)`
2. Если таких стен 0 — ошибка валидации: «Дверь не пересекает ни одной стены»
3. Если таких стен 1 — режет её: разбивает на два сегмента с gap для двери
4. Если таких стен 2+ — ошибка валидации: «Дверь пересекает несколько стен»

### Алгоритм

```python
# backend/map_editor/validators/wall_door_resolution.py

def resolve_door_openings(walls: List[Wall], doors: List[Door]) -> Tuple[List[Wall], List[ValidationError]]:
    errors = []
    result_walls = list(walls)
    
    for door in doors:
        intersected = [
            wall for wall in result_walls
            if point_on_segment(door.x, door.y, wall.x1, wall.y1, wall.x2, wall.y2, eps=0.5)
        ]
        
        if len(intersected) == 0:
            errors.append(ValidationError(
                severity=Severity.ERROR,
                code="DOOR_WITHOUT_WALL",
                message=f"Дверь '{door.name}' ({door.x}, {door.y}) не пересекает ни одной стены. "
                        f"Дверь должна стоять на стене — иначе она бесполезна.",
                fix_hint="Перетащите дверь на ближайшую стену или удалите её"
            ))
            continue
        
        if len(intersected) > 1:
            wall_names = ", ".join(w.id for w in intersected)
            errors.append(ValidationError(
                severity=Severity.ERROR,
                code="DOOR_CROSSES_MULTIPLE_WALLS",
                message=f"Дверь '{door.name}' пересекает {len(intersected)} стен: {wall_names}. "
                        f"Дверь должна пересекать только ОДНУ стену.",
                fix_hint=f"Переместите дверь на {intersected[0].id} или удалите лишние стены"
            ))
            continue
        
        # Точно одна стена — режем
        wall = intersected[0]
        split_walls = split_wall_at_point(wall, door.x, door.y, door_width=1.0)
        idx = result_walls.index(wall)
        result_walls.pop(idx)
        result_walls.insert(idx, split_walls[0])
        result_walls.insert(idx + 1, split_walls[1])
    
    return result_walls, errors
```

### Что меняется для дизайнера

**До:** Ставишь дверь на стену → открываешь JSON → пишешь `wall_id` → молишься.

**После:** Ставишь дверь на стену → редактор сам режет → готово. Старые JSON с `wall_id` конвертируются при первом открытии.

---

## §2. ЛОГИКА РАСПРЕДЕЛЕНИЯ КРОВАТЕЙ (по правилам, не псевдослучайно)

### 2.1. Контекст — кто где должен спать

Из анализа NPC configs и архетипов:

| NPC | Архетип | Локация работы | Текущая sleeping position | Логика |
|---|---|---|---|---|
| **tavern_keeper_tornin** | tavern_keeper | tavern | tavern/kitchen_bed_2 | Спит в трактире (владелец) |
| **maid_lusya** | maid | tavern | tavern/kitchen_bed_1 | Спит в трактире (живёт там) |
| **guard_borko** | guard | city_gate | city_gate/guard_bed | Спит в караульне (стражник) |
| **thief_shadow** | thief | tavern | city_gate/tent_3 | Спит в палатке (гость) |
| **blacksmith_orm** | blacksmith | market_square | city_gate/tent_1 | Спит в палатке (гость) |
| **merchant_goran** | merchant | tavern | city_gate/tent_2 | Спит в палатке (гость) |

### 2.2. Правила приоритета (концепция «личного» в зачатке)

Каждая кровать имеет **тип** (по локации и объекту), который определяет, кто в ней может спать:

| Тип кровати | Локация | Кто может спать | Приоритет |
|---|---|---|---|
| **inn_bed** | tavern | tavern_keeper, maid | 1 (только свои) |
| **guard_bed** | city_gate/guard_bed | guard | 1 (только стражник) |
| **tent** | city_gate/tent_N | любой NPC | 2 (публичная) |
| **floor** | любая | любой NPC | 3 (fallback) |

**Правила распределения:**

1. **Сначала «свои» кровати:** NPC ищет кровать своего архетипа в своей локации сна.
   - tavern_keeper → `inn_bed` в tavern
   - maid → `inn_bed` в tavern
   - guard → `guard_bed` в city_gate
   - thief/blacksmith/merchant → `tent` в city_gate (нет «своей» кровати, сразу в палатки)

2. **Если своя кровать занята или недостижима — fallback:**
   - tavern_keeper/maid → если в трактире 1 кровать, спит только tavern_keeper (он владелец); maid fallback на tent
   - guard → если guard_bed занят или нет пути, fallback на tent
   - Любой → если tent занят, fallback на пол (`sleeping_on_floor` activity)

3. **Если кроватей в трактире хватает на обоих (tavern_keeper + maid) — спят оба.**

4. **Если кровать в трактире всего одна — спит только tavern_keeper.** Maid идёт в палатку.

5. **Стражник спит в караульне один.** Если guard_bed занят другим NPC (через override), стражник fallback на tent.

6. **Палатки — публичные.** Любой NPC может занять свободную палатку.

### 2.3. Тип кровати — как определяется

Не через хардкод в JSON, а через **метаданные объекта** в редакторе:

```json
// location JSON — объект кровати
{
    "id": "obj_36",
    "name": "Кровать №1",
    "type": "bed",
    "x": 14.92, "y": 5.15,
    "passability": {"walk": false, "jump_over": false},
    "bed_properties": {
        "bed_type": "inn_bed",           ← тип кровати
        "capacity": 1,
        "comfort_level": 1.2,
        "allowed_archetypes": ["tavern_keeper", "maid"]  ← кто может спать
    }
}
```

```json
// guard_bed
{
    "id": "obj_69",
    "name": "Кровать стражника",
    "type": "bed",
    "x": 31.0, "y": 0.67,
    "bed_properties": {
        "bed_type": "guard_bed",
        "capacity": 1,
        "comfort_level": 1.0,
        "allowed_archetypes": ["guard"]
    }
}
```

```json
// tent
{
    "id": "obj_55",
    "name": "Палатка №1",
    "type": "tent",
    "x": 32.35, "y": 7.93,
    "bed_properties": {
        "bed_type": "tent",
        "capacity": 1,
        "comfort_level": 0.8,
        "allowed_archetypes": []  ← пустой = любой
    }
}
```

**Редактор при создании кровати** спрашивает тип:
- «Кровать в трактире» → `bed_type: "inn_bed"`, `allowed_archetypes: ["tavern_keeper", "maid"]`
- «Кровать стражника» → `bed_type: "guard_bed"`, `allowed_archetypes: ["guard"]`
- «Палатка» → `bed_type: "tent"`, `allowed_archetypes: []`
- «Свободная кровать» → `bed_type: "inn_bed"`, `allowed_archetypes: []` (любой)

### 2.4. BedRegistry — runtime-логика

```python
# backend/app/services/spatial/bed_registry.py

from dataclasses import dataclass, field
from typing import Dict, Set, Optional, List
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class BedType(Enum):
    INN_BED = "inn_bed"           # кровать в трактире (tavern_keeper, maid)
    GUARD_BED = "guard_bed"       # караульная (только guard)
    TENT = "tent"                 # палатка (любой)
    FLOOR = "floor"               # fallback


# Приоритет fallback: если своя кровать недоступна, куда идти
FALLBACK_CHAIN = {
    "tavern_keeper": [BedType.INN_BED, BedType.TENT, BedType.FLOOR],
    "maid":          [BedType.INN_BED, BedType.TENT, BedType.FLOOR],
    "guard":         [BedType.GUARD_BED, BedType.TENT, BedType.FLOOR],
    "thief":         [BedType.TENT, BedType.FLOOR],
    "blacksmith":    [BedType.TENT, BedType.FLOOR],
    "merchant":      [BedType.TENT, BedType.FLOOR],
}

# Архетипы, для которых INN_BED приоритетна (трактирщик и служанка)
INN_BED_PRIORITY = {"tavern_keeper", "maid"}


@dataclass
class Bed:
    bed_id: str                       # "tavern:obj_36"
    location_id: str                  # "tavern"
    node_id: str                      # "kitchen_bed_1" (ближайший walkable узел)
    bed_type: BedType
    capacity: int = 1
    comfort_level: float = 1.0
    allowed_archetypes: List[str] = field(default_factory=list)  # пустой = любой
    owner_npc_id: Optional[str] = None  # ручное назначение дизайнером (override)
    current_occupants: Set[str] = field(default_factory=set)
    reserved_until: Optional[int] = None  # tick_number


class BedRegistry:
    """Распределяет кровати по правилам приоритета."""
    
    def __init__(self):
        self._beds: Dict[str, Bed] = {}
    
    def register_bed(
        self,
        bed_id: str,
        location_id: str,
        node_id: str,
        bed_type: BedType,
        capacity: int = 1,
        comfort: float = 1.0,
        allowed_archetypes: List[str] = None,
        owner_npc_id: Optional[str] = None,
    ):
        self._beds[bed_id] = Bed(
            bed_id=bed_id, location_id=location_id, node_id=node_id,
            bed_type=bed_type, capacity=capacity, comfort_level=comfort,
            allowed_archetypes=allowed_archetypes or [],
            owner_npc_id=owner_npc_id,
        )
        logger.debug(
            f"[BED_REGISTRY] Registered bed {bed_id} "
            f"type={bed_type.value} allowed={allowed_archetypes} "
            f"owner={owner_npc_id}"
        )
    
    def claim_bed(
        self,
        npc_id: str,
        npc_archetype: str,
        npc_current_location: str,
        current_tick: int,
        preferred_location: Optional[str] = None,
        preferred_node: Optional[str] = None,
    ) -> Optional[Bed]:
        """NPC просит кровать. Возвращает Bed или None (спать на полу).
        
        Алгоритм:
        1. Если у NPC есть owner_npc_id на какой-то кровати — идти туда
        2. Иначе — по FALLBACK_CHAIN для архетипа:
           a. Найти все кровати своего типа
           b. Отфильтровать по allowed_archetypes
           c. Отфильтровать свободные
           d. Если preferred_node указан и свободен — занять
           e. Иначе — ближайшую свободную
        3. Если тип недоступен — следующий в цепочке
        """
        
        # Шаг 1: owner override
        for bed in self._beds.values():
            if bed.owner_npc_id == npc_id:
                if self._is_available(bed, current_tick):
                    self._occupy(bed, npc_id, current_tick)
                    return bed
                else:
                    logger.warning(
                        f"[BED_REGISTRY] {npc_id}'s owner-bed {bed.bed_id} "
                        f"occupied by {bed.current_occupants} — fallback"
                    )
        
        # Шаг 2: по цепочке fallback
        fallback_chain = FALLBACK_CHAIN.get(npc_archetype, [BedType.TENT, BedType.FLOOR])
        
        for bed_type in fallback_chain:
            bed = self._try_claim_by_type(
                npc_id=npc_id,
                npc_archetype=npc_archetype,
                bed_type=bed_type,
                preferred_location=preferred_location,
                preferred_node=preferred_node,
                current_tick=current_tick,
            )
            if bed is not None:
                return bed
        
        # Все типы недоступны — спим на полу
        logger.warning(
            f"[BED_REGISTRY] {npc_id} (archetype={npc_archetype}) "
            f"could not claim any bed — sleeping on floor"
        )
        return None  # caller обработает как sleeping_on_floor
    
    def _try_claim_by_type(
        self,
        npc_id: str,
        npc_archetype: str,
        bed_type: BedType,
        preferred_location: Optional[str],
        preferred_node: Optional[str],
        current_tick: int,
    ) -> Optional[Bed]:
        """Ищет свободную кровать указанного типа для NPC."""
        
        candidates = []
        for bed in self._beds.values():
            if bed.bed_type != bed_type:
                continue
            
            # Проверка allowed_archetypes
            if bed.allowed_archetypes and npc_archetype not in bed.allowed_archetypes:
                continue
            
            # Проверка owner (если у кровати есть owner и это не мы — пропускаем)
            if bed.owner_npc_id and bed.owner_npc_id != npc_id:
                continue
            
            # Проверка свободы
            if not self._is_available(bed, current_tick):
                continue
            
            # Приоритет по локации
            location_match = (
                preferred_location is None or 
                bed.location_id == preferred_location
            )
            
            # Приоритет по node (если указан preferred_node)
            node_match = (
                preferred_node is None or 
                bed.node_id == preferred_node
            )
            
            candidates.append((bed, location_match, node_match))
        
        if not candidates:
            return None
        
        # Сортировка: 1) preferred_node match 2) preferred_location match 3) comfort
        candidates.sort(key=lambda x: (
            not x[2],  # preferred_node match first (False=0 sorts first)
            not x[1],  # then preferred_location match
            -x[0].comfort_level,  # then higher comfort
        ))
        
        chosen = candidates[0][0]
        self._occupy(chosen, npc_id, current_tick)
        return chosen
    
    def _is_available(self, bed: Bed, current_tick: int) -> bool:
        if len(bed.current_occupants) >= bed.capacity:
            return False
        if bed.reserved_until is not None and bed.reserved_until > current_tick:
            return False
        return True
    
    def _occupy(self, bed: Bed, npc_id: str, current_tick: int):
        bed.current_occupants.add(npc_id)
        # Резервируем до утра (08:00 следующего дня)
        ticks_until_morning = _ticks_until_next_hour(8, current_tick)
        bed.reserved_until = current_tick + ticks_until_morning
        logger.info(
            f"[BED_REGISTRY] {npc_id} → bed {bed.bed_id} "
            f"(type={bed.bed_type.value}, comfort={bed.comfort_level}, "
            f"until tick {bed.reserved_until})"
        )
    
    def release_bed(self, npc_id: str):
        """NPC проснулся — освободить кровать."""
        for bed in self._beds.values():
            if npc_id in bed.current_occupants:
                bed.current_occupants.discard(npc_id)
                bed.reserved_until = None
                logger.info(f"[BED_REGISTRY] {npc_id} released bed {bed.bed_id}")
                return
    
    def get_bed_for_npc(self, npc_id: str) -> Optional[Bed]:
        for bed in self._beds.values():
            if npc_id in bed.current_occupants:
                return bed
        return None
    
    def serialize(self) -> dict:
        """Для сохранения в scene_state."""
        return {
            "beds": [
                {
                    "bed_id": bed.bed_id,
                    "occupants": list(bed.current_occupants),
                    "reserved_until": bed.reserved_until,
                }
                for bed in self._beds.values()
                if bed.current_occupants or bed.reserved_until
            ]
        }
    
    def deserialize(self, data: dict):
        """Восстановление из scene_state."""
        for entry in data.get("beds", []):
            bed = self._beds.get(entry["bed_id"])
            if bed:
                bed.current_occupants = set(entry["occupants"])
                bed.reserved_until = entry["reserved_until"]


def _ticks_until_next_hour(hour: int, current_tick: int) -> int:
    """Сколько тиков до указанного часа (по игровому времени)."""
    # Заглушка — реальная реализация зависит от GAME_TICK_INTERVAL
    # Если 1 tick = 1 game hour, то просто (hour - current_tick % 24) % 24
    current_hour = current_tick % 24
    delta = (hour - current_hour) % 24
    if delta == 0:
        delta = 24
    return delta
```

### 2.5. Интеграция с life_engine

В `life_engine._resolve_position(npc, "sleeping", current_tick)`:

```python
def _resolve_position(self, npc, activity: str, current_tick: int):
    if activity == "sleeping":
        # preferred_location и preferred_node из activity_map (если есть)
        preferred = npc.activity_map.get("sleeping")
        if preferred:
            preferred_loc = preferred["location_id"]
            preferred_node = preferred["position"]
        else:
            preferred_loc = npc.current_location_id
            preferred_node = None
        
        # Просим BedRegistry
        bed = self._bed_registry.claim_bed(
            npc_id=npc.npc_id,
            npc_archetype=npc.archetype,  # "guard", "maid", "tavern_keeper", etc.
            npc_current_location=npc.current_location_id,
            current_tick=current_tick,
            preferred_location=preferred_loc,
            preferred_node=preferred_node,
        )
        
        if bed is None:
            # Fallback: спим на полу у ближайшего walkable узла
            floor_node = _nearest_walkable_node(preferred_loc, npc.position)
            return (preferred_loc, floor_node, "sleeping_on_floor")
        
        return (bed.location_id, bed.node_id, "sleeping")
    
    # ... другие activity
```

### 2.6. Конкретные сценарии для 6 NPC

**Сценарий 1: Все кровати на месте, все доступны.**
- 22:00 → tornin (tavern_keeper) → `tavern:kitchen_bed_2` (inn_bed, owner override или правило)
- 22:00 → borko (guard) → `city_gate:guard_bed` (guard_bed)
- 22:00 → orm (blacksmith) → `city_gate:tent_1` (tent)
- 22:00 → goran (merchant) → `city_gate:tent_2` (tent)
- 06:00 → shadow (thief) → `city_gate:tent_3` (tent, nocturnal schedule)
- 21:00 → lusya (maid) → `tavern:kitchen_bed_1` (inn_bed)

**Сценарий 2: В трактире только 1 кровать (kitchen_bed_2).**
- 21:00 → lusya пытается `kitchen_bed_1` — нет такой кровати → fallback на tent
- 22:00 → tornin → `kitchen_bed_2` (своя, приоритет)
- lusya идёт в `city_gate:tent_3` (если свободна) или другую tent

**Сценарий 3: guard_bed занят (через override назначен другому).**
- 22:00 → borko пытается `guard_bed` — занят → fallback на tent
- borko идёт в `city_gate:tent_1` (или ближайшую свободную tent)

**Сценарий 4: Все tents заняты.**
- NPC идёт по цепочке: своя → tent → floor
- Спит на полу (`sleeping_on_floor` activity), stress recovery 50%

### 2.7. Сериализация и сохранение

`BedRegistry` сериализуется в `scene_state["bed_registry"]`:
```json
{
    "beds": [
        {
            "bed_id": "tavern:obj_36",
            "occupants": ["maid_lusya"],
            "reserved_until": 192
        },
        {
            "bed_id": "tavern:obj_37",
            "occupants": ["tavern_keeper_tornin"],
            "reserved_until": 192
        },
        {
            "bed_id": "city_gate:obj_69",
            "occupants": ["guard_borko"],
            "reserved_until": 192
        }
    ]
}
```

При загрузке — `bed_registry.deserialize(scene_state["bed_registry"])`.

---

## §3. РУЧНОЕ НАЗНАЧЕНИЕ КРОВАТЕЙ В РЕДАКТОРЕ (override)

### 3.1. UX — клик на кровать → выбор NPC

Когда дизайнер кликает на объект кровати в редакторе, открывается панель свойств (или модалка):

```
┌──────────────────────────────────────────────────────┐
│  Свойства кровати: «Кровать №1» (obj_36)              │
│  Локация: tavern • Позиция: (14.92, 5.15)              │
│  Ближайший узел: kitchen_bed_1                        │
│                                                       │
│  Тип кровати:                                         │
│  ○ Кровать в трактире (inn_bed)                       │
│    — могут спать: tavern_keeper, maid                 │
│  ○ Кровать стражника (guard_bed)                      │
│    — может спать: guard                               │
│  ○ Палатка (tent)                                     │
│    — может спать: любой NPC                           │
│  ○ Свободная кровать (inn_bed, любой)                 │
│    — может спать: любой NPC                           │
│                                                       │
│  ─────────────────────────────────────────────────── │
│                                                       │
│  Кто спит в этой кровати?                             │
│                                                       │
│  ○ По правилам (авто-распределение)                  │
│    — кровать будет занята по правилам приоритета     │
│                                                       │
│  ○ Назначить вручную:                                 │
│    [dropdown: выберите NPC ▾]                         │
│      • tavern_keeper_tornin (Торнин)                  │
│      • maid_lusya (Люся)                              │
│      • guard_borko (Борко)                            │
│      • thief_shadow (Тень)                            │
│      • blacksmith_orm (Орм)                           │
│      • merchant_goran (Горан)                         │
│      • (никто — кровать свободна для правил)          │
│                                                       │
│  [Отмена]                            [Применить]      │
└──────────────────────────────────────────────────────┘
```

### 3.2. Что сохраняется в JSON

Если выбрано «По правилам» — `owner_npc_id: null` (или поле отсутствует):
```json
{
    "id": "obj_36",
    "type": "bed",
    "bed_properties": {
        "bed_type": "inn_bed",
        "allowed_archetypes": ["tavern_keeper", "maid"],
        "owner_npc_id": null
    }
}
```

Если выбран конкретный NPC — `owner_npc_id`:
```json
{
    "id": "obj_36",
    "type": "bed",
    "bed_properties": {
        "bed_type": "inn_bed",
        "allowed_archetypes": ["tavern_keeper", "maid"],
        "owner_npc_id": "maid_lusya"
    }
}
```

### 3.3. Валидация ручного назначения

При сохранении редактор проверяет:
- `owner_npc_id` существует в NPC configs (не orphan)
- `owner_npc_id` соответствует `allowed_archetypes` (нельзя назначить guard на inn_bed, если allowed только tavern_keeper/maid) — WARN, можно обойти
- Один NPC не назначен на 2+ кровати одновременно — ERROR

**Пример ошибки:**
> ❌ **NPC назначен на две кровати**
> NPC `maid_lusya` назначен как owner на:
> 1. `obj_36` «Кровать №1» в tavern
> 2. `obj_55` «Палатка №1» в city_gate
>
> NPC может владеть только одной кроватью. Уберите owner с одной из них.

### 3.4. Логика в runtime — приоритет override

В `BedRegistry.claim_bed` (см. §2.4) — первый шаг:
```python
# Шаг 1: owner override
for bed in self._beds.values():
    if bed.owner_npc_id == npc_id:
        if self._is_available(bed, current_tick):
            self._occupy(bed, npc_id, current_tick)
            return bed
        else:
            logger.warning(f"...")
```

Это значит: если дизайнер назначил кровать NPC, NPC идёт туда в первую очередь. Если занята (другой NPC уже занял по правилам) — fallback на правила.

### 3.5. Будущее — улучшение правил

Сейчас: `allowed_archetypes` + `owner_npc_id` — зачаточная концепция «личного».

Будущее (post-MVP):
- **Affinity-система:** NPC запоминает, где спал, и предпочитает ту же кровать.
- **Drama-система:** NPC может «захватить» чужую кровать (если drunk или aggressive).
- **Динамика:** NPC может временно спать не у себя (если напился в трактире и не дошёл до палатки).

Это будет расширять `BedRegistry` — фундамент уже заложен.

---

## §4. ВСЕ ШАГИ ДЛЯ ПОЧИНКИ СНА NPC

Полный список шагов, чтобы все 6 NPC спали. Включает фиксы геометрии, конфигов, кода и редактора.

### Шаг 1: Исправить дублирующий `wall_6` в `tavern.json` [КРИТИЧНО]

**Проблема:** ID `wall_6` используется дважды — для вертикальной стены (14,12→14,1) и горизонтальной (14,8→19,8). Дверь `obj_38` не понимает, какую резать.

**Где:** `frontend/map_editor/campaigns/Open_road/locations/tavern.json`

**Решение:** Это делается автоматически после реализации §1 (авто-резка стен). Дизайнер просто открывает редактор, видит ошибку «Дублирующийся ID стены», переименовывает одну из стен через UI. Редактор сам разрезает стену под дверью при сохранении.

**Временный фикс (до реализации §1):** Переименовать в JSON вручную:
- Вертикальную: `"id": "wall_6_vertical"`
- Горизонтальную: `"id": "wall_6_horizontal_north"`
- Двери добавить `"wall_id": "wall_6_vertical"`

### Шаг 2: Сдвинуть sleep nodes из кроватей [КРИТИЧНО]

**Проблема:** Sleep nodes размещены ВНУТРИ объектов кроватей:
- `kitchen_bed_1` (15.0, 5.0) внутри `obj_36` (14.92, 5.15) — расстояние 0.16м
- `kitchen_bed_2` (17.5, 5.0) внутри `obj_37` (17.54, 5.17) — расстояние 0.17м
- `guard_bed` (31.08, 1.11) внутри `obj_69` (31.0, 0.67) — расстояние 0.45м

Все три кровати имеют `passability.walk = false` → NPC не может встать на sleep node.

**Решение:** Sleep node — это **точка взаимодействия** с кроватью (где NPC стоит рядом, перед тем как лечь), а не сама кровать. Сдвинуть на 0.5-1.0м в свободное пространство.

**Где:** `tavern.json` (для kitchen_bed_1/2), `city_gate.json` (для guard_bed)

**В редакторе:** После реализации §5 валидатор поймает это автоматически (Проверка 3: Sleep Node Geometric Safety). Дизайнер увидит ошибку и сдвинет узел через UI.

**Временный фикс (до редактора):** В JSON сдвинуть координаты:
```json
"kitchen_bed_1": { "x": 15.0, "y": 6.0 },  ← было y=5.0
"kitchen_bed_2": { "x": 17.5, "y": 6.0 }   ← было y=5.0
```
И в `city_gate.json`:
```json
"guard_bed": { "x": 31.0, "y": 1.8 }       ← было y=1.11
```

### Шаг 3: Переместить spawn Борко со стола [ВЫСОКИЙ]

**Проблема:** Борко спавнится в (12.025, 7.85) — внутри объекта `obj_2` «Стол №3». В логах:
```
[S-03_OBSTACLE_RECOVERY] NPC 'guard_borko' застрял внутри препятствия 'obj_2'.
```

**Решение:** Изменить начальную позицию Борко в NPC config или scene_state initial.

**Где:** `config/npc/individuals/borko.json` (если есть поле spawn) или `backend/test_data/.../initial_scene_state.json`

**В редакторе:** После реализации §5 валидатор поймает это автоматически (Проверка 10: NPC Spawn Safety).

**Временный фикс:** Установить spawn в (10.0, 7.0) или другой walkable узел рядом.

### Шаг 4: Починить расписание Люси [ВЫСОКИЙ]

**Проблема:** В `lusya.json` строки 65-72 — 4 перекрывающихся записи:
```json
"schedule": {
    "07:00-21:00": "working",
    "21:00-07:00": "sleeping",
    "14:00-06:00": "sleeping",   ← конфликт с 14:00-21:00
    "06:00-14:00": "working"     ← конфликт с 06:00-07:00
}
```

**Решение:** Заменить на две чистые:
```json
"schedule": {
    "06:00-21:00": "working",
    "21:00-06:00": "sleeping"
}
```

**В редакторе:** После реализации §5 валидатор поймает это автоматически (Проверка 5: Schedule Consistency).

### Шаг 5: Реализовать BedRegistry с правилами приоритета [ВЫСОКИЙ]

**Проблема:** Сейчас `resolve_affordance("sleep")` возвращает ближайшую кровать без проверки владельца. В логах Люсю маршрутизируют на `kitchen_bed_2` (Торнина) вместо её `kitchen_bed_1`.

**Решение:** Реализовать `BedRegistry` (см. §2.4) с правилами приоритета:
- inn_bed → tavern_keeper, maid
- guard_bed → guard
- tent → любой
- floor → fallback

**Где:** Новый файл `backend/app/services/spatial/bed_registry.py` + интеграция в `life_engine._resolve_position`.

### Шаг 6: Умный редактор карт с валидацией при сохранении [ОСНОВНОЙ]

См. §5 — полный раздел. Редактор не даёт сохранить сломанную кампанию, говорит по-русски, что не так.

### Шаг 7: Исправить orphan `guard_post` [СРЕДНИЙ]

**Проблема:** В `borko.json` activity `guarding_gate` ссылается на `position: "guard_post"`, но в `city_gate.json` нет узла `guard_post`. Борко не знает, куда идти на дежурство (не влияет на сон, но влияет на дневную активность).

**Решение:** Либо добавить узел `guard_post` в `city_gate.json`, либо изменить `position` в `borko.json` на существующий узел (`gate_arch` или `entrance`).

**В редакторе:** После реализации §5 валидатор поймает это автоматически (Проверка 4: Cross-Reference Integrity).

### Шаг 8: Boundary node isolation → HARD ERROR [КРИТИЧНО, ЗАЩИТА]

**Проблема:** `graph_compiler._validate_connectivity` логирует WARNING для изолированных узлов, но не падает. Изолированный `exit_east` (блокер №2 из логов) пропустил компиляцию, и NPC 5 месяцев не могли выйти из таверны.

**Решение:** Если BOUNDARY node изолирован → `raise SimulationIntegrityError`. Boundary nodes — единственные выходы из локации; изоляция ломает cross-location navigation.

**Где:** `backend/app/services/spatial/graph_compiler.py:_validate_connectivity` (строки 737-756)

```python
for isolated_node in isolated:
    node_ref = self._graph.get(isolated_node)
    if node_ref and NodeRole.BOUNDARY in (node_ref.roles or []):
        raise SimulationIntegrityError(
            f"BOUNDARY node {isolated_node} is isolated — "
            "cross-location navigation is broken. "
            "Check walls/obstacles overlap with boundary node coordinates.",
            severity="CRITICAL"
        )
    logger.warning(f"Isolated node: {isolated_node}")
```

### Шаг 9: Удалить stale `tavern_silver_wolf` ссылки [СРЕДНИЙ]

**Проблема:** В Python коде остались захардкоженные дефолты `tavern_silver_wolf`:
- `backend/app/api/routes.py:887` — `location_id = payload.get("location_id", "tavern_silver_wolf")`
- `frontend/game_loop_bridge.py:107, 127` — `location: str = "tavern_silver_wolf"`

И в `truth_state_tavern.json` — `campaign_id: "silver_wolf"` (должно быть `"Open_road"`).

**Решение:** Заменить `tavern_silver_wolf` → `tavern`. Заменить `silver_wolf` → `Open_road` (campaign_id).

**В редакторе:** После реализации §5 валидатор поймает это автоматически (Проверки 13, 14).

### Шаг 10: Пересобрать spatial_registry [ОБЯЗАТЕЛЬНО после Шагов 1-2]

После любых изменений в `tavern.json` / `city_gate.json` — обязательно пересобрать:
```bash
python build_graph.py
```
или через Map Editor → Compile (после реализации §6).

Без этого изменения не подхватятся.

### Шаг 11: Проверить Shadow отдельно [НИЗКИЙ]

**Контекст:** Shadow — единственный nocturnal NPC (спит 06:00-18:00). Это намеренно (вор, работает ночью). Все другие NPC спят ночью.

**Действие:** Не чинить расписание Shadow — оно правильное. Но в Day 1 тесте睡眠 migration исключить Shadow из 22:00 теста и добавить отдельный 06:00 тест для неё.

### Шаг 12: wall_id auto-resolve (§1) [СРЕДНИЙ]

Реализовать авто-резку стен под дверями (см. §1), чтобы дизайнер не указывал `wall_id` вручную. Это сделает Шаг 1 ненужным в будущем.

---

## §5. РЕДАКТОР КАРТ: ПОЛНАЯ ВАЛИДАЦИЯ ПРИ СОХРАНЕНИИ

### 5.1. Архитектура валидатора

```
backend/map_editor/
├── validators/
│   ├── __init__.py
│   ├── base.py                  # ValidationError, ValidationResult
│   ├── id_consistency.py        # ID/имена/названия совпадают
│   ├── geometry_validator.py    # стены, двери, препятствия
│   ├── node_graph_validator.py  # изоляция, достижимость
│   ├── npc_config_validator.py  # schedule, activity_map
│   ├── cross_reference.py       # NPC → location → node, кровати
│   ├── schedule_validator.py    # перекрытия, временные слоты
│   ├── bed_validator.py         # типы кроватей, owner consistency
│   └── campaign_validator.py    # оркестратор
└── save_handler.py              # вызывает campaign_validator, показывает ошибки
```

### 5.2. Базовые типы

```python
# backend/map_editor/validators/base.py

from enum import Enum
from dataclasses import dataclass
from typing import List, Optional

class Severity(Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"

@dataclass
class ValidationError:
    severity: Severity
    code: str
    message: str           # по-русски
    file_path: str
    object_id: Optional[str] = None
    line: Optional[int] = None
    fix_hint: Optional[str] = None
    visual_coords: Optional[tuple] = None

@dataclass
class ValidationResult:
    errors: List[ValidationError]
    warnings: List[ValidationError]
    
    @property
    def is_valid(self) -> bool:
        return len(self.errors) == 0
    
    def has_blocking(self) -> bool:
        return any(e.severity == Severity.ERROR for e in self.errors)
```

### 5.3. Типы проверок (полный список — 15 проверок)

#### Проверка 1: ID Consistency — уникальность ID

Все `nodes`, `walls`, `objects` в локации имеют уникальные ID. Все `location_id` в кампании уникальны. Все `npc_id` уникальны.

**Пример ошибки:**
> ❌ **Дублирующийся ID стены**
> В локации «Таверна» ID `wall_6` используется дважды:
> 1. Стена (14.0, 12.0) → (14.0, 1.0) — вертикальная
> 2. Стена (14.0, 8.0) → (19.0, 8.0) — горизонтальная
>
> Двери не смогут правильно «разрезать» стену.
>
> 💡 Переименуйте вторую стену в `wall_6_horizontal_north`.

#### Проверка 2: Door-Wall Resolution — дверь на стене

Каждая дверь пересекает ровно одну стену (после авто-резки §1).

**Пример ошибки:**
> ❌ **Дверь не на стене**
> Дверь «Дверь №1» (14.0, 3.0) не пересекает ни одной стены.
>
> 💡 Перетащите дверь на ближайшую стену или удалите её.

#### Проверка 3: Sleep Node Geometric Safety — sleep node вне кровати

Sleep node (узел, упомянутый в `activity_map.sleeping` любого NPC) не находится внутри объекта с `passability.walk = false`.

**Пример ошибки:**
> ❌ **Узел сна внутри кровати**
> Узел `kitchen_bed_2` (17.5, 5.0) в локации «Таверна» находится внутри объекта `obj_37` «Кровать №2» (17.54, 5.17), расстояние 0.17м.
>
> Объект «Кровать №2» имеет `passability.walk = false` — NPC не сможет встать на эту точку.
>
> 💡 Сдвиньте узел на 0.5-1.0м от кровати. Например, на (17.5, 6.0).

#### Проверка 4: Cross-Reference Integrity — NPC ↔ location ↔ node

- Каждый `activity_map[X].position` существует как node в указанной локации
- Каждый `activity_map[X].location_id` существует как location в кампании
- Каждый `schedule[X]` имеет запись в `activity_map`

**Пример ошибки:**
> ❌ **NPC ссылается на несуществующий узел**
> NPC `guard_borko` в activity `guarding_gate` ссылается на позицию `guard_post` в локации `city_gate`. Но в локации «Городские ворота» нет узла с ID `guard_post`.
>
> Существующие узлы: gate_road, gate_arch, guard_bed, gate_courtyard, entrance, tent_1, tent_2, tent_3...
>
> 💡 Добавьте узел `guard_post` или измените `position` на `gate_arch`.

#### Проверка 5: Schedule Consistency — перекрытия и пробелы

В расписании нет перекрывающихся интервалов.

**Пример ошибки:**
> ❌ **Перекрытие в расписании NPC**
> NPC `maid_lusya` имеет перекрывающиеся интервалы:
> 1. `06:00-14:00`: working
> 2. `07:00-21:00`: working
>
> Интервал 07:00-14:00 покрыт дважды.
>
> 💡 Объедините в одно: `06:00-21:00: working`.

#### Проверка 6: Boundary Node Reachability — выходы достижимы

Каждый boundary node достижим из хотя бы одного «центрального» node локации.

**Пример ошибки:**
> ❌ **Изолированный выход из локации**
> Boundary node `tavern:exit_east` (выход на восток к «Городским воротам») изолирован.
>
> Это значит, что NPC не смогут выйти из таверны на восток. Сон в `city_gate` (Борко, Тень, Орм, Горан) будет невозможен.
>
> **Причина скорее всего:** Рядом с boundary node есть стена или объект, который блокирует все рёбра.
>
> 💡 Проверьте геометрию вокруг (17.5, 5.0). Убедитесь, что ближайший навигационный узел имеет walkable путь к boundary.

#### Проверка 7: Wall ID Migration — обратная совместимость

Старые JSON с `wall_id` на дверях — warning (не error). При сохранении конвертируются в новый формат.

#### Проверка 8: Faction ID Consistency — язык ID

Если NPC config ссылается на faction_id — этот ID существует в `factions.json`. Все faction IDs одного языка.

**Пример ошибки:**
> ❌ **NPC ссылается на несуществующую фракцию**
> NPC `guard_borko` имеет `faction_membership: "thieves_guild"`. Но в `factions.json` фракций с английскими ID нет — все на русском: `гильдия_воров`, `городская_стража`...
>
> 💡 Измените `faction_membership` на `городская_стража`.

#### Проверка 9: Spatial Registry Refresh — freshness

`compiled/spatial_registry.json` новее, чем все `locations/*.json`.

#### Проверка 10: NPC Spawn Safety — не внутри препятствия

Начальная позиция NPC не внутри объекта с `walk = false`.

**Пример ошибки:**
> ❌ **NPC спавнится внутри препятствия**
> NPC `guard_borko` имеет начальную позицию (12.025, 7.85). Эта точка находится внутри объекта `obj_2` «Стол №3».
>
> 💡 Измените начальную позицию на (10.0, 7.0).

#### Проверка 11: Bed Capacity vs NPC Count

В каждой локации, где NPC спят, количество кроватей ≥ количеству NPC, которые спят в этой локации (по правилам приоритета).

**Пример warning:**
> ⚠️ **Недостаточно кроватей**
> В локации «Таверна» 1 кровать, но 2 NPC хотят здесь спать: `maid_lusya`, `tavern_keeper_tornin`.
>
> По правилам приоритета, `tavern_keeper_tornin` (владелец) получит кровать, `maid_lusya` fallback на палатку.
>
> 💡 Добавьте 2-ю кровать в локацию «Таверна», либо укажите `maid_lusya` спать в `city_gate`.

#### Проверка 12: Truth State Secret IDs ↔ ActionSemanticResolver

Каждый `secret_id`, который может вернуть `ActionSemanticResolver`, существует в `truth_state_tavern.json`.

#### Проверка 13: campaign_id Consistency

`campaign_id` в `truth_state_tavern.json` совпадает с ID кампании.

**Пример ошибки:**
> ❌ **Несовпадение campaign_id**
> `truth_state_tavern.json` имеет `campaign_id: "silver_wolf"`. Но игра запускается с кампанией `"Open_road"`.
>
> 💡 Измените `campaign_id` в `truth_state_tavern.json` на `"Open_road"`.

#### Проверка 14: Stale Location References — `tavern_silver_wolf`

Ни в одном JSON-файле кампании нет ссылок на `tavern_silver_wolf`.

**Пример ошибки:**
> ❌ **Устаревшая ссылка на локацию**
> Файл `backend/data/locations/location_templates.json` строка 167: ссылается на `tavern_silver_wolf`. Эта локация не существует — правильный ID `tavern`.
>
> 💡 Замените `tavern_silver_wolf` → `tavern`.

#### Проверка 15: Bed Type Consistency — кровать имеет правильный тип

Каждый объект с `type: "bed"` или `type: "tent"` имеет `bed_properties` с корректным `bed_type`. Если `bed_type: "guard_bed"` — `allowed_archetypes` должен содержать `"guard"`.

**Пример ошибки:**
> ❌ **Несогласованный тип кровати**
> Объект `obj_69` «Кровать стражника» имеет `bed_type: "guard_bed"`, но `allowed_archetypes: ["tavern_keeper"]`. Это противоречие — guard_bed только для guard.
>
> 💡 Измените `allowed_archetypes` на `["guard"]` или `bed_type` на `"inn_bed"`.

### 5.4. UX в редакторе — модалка при сохранении

```
┌─────────────────────────────────────────────────────────────┐
│  ❌ Кампания не может быть сохранена                          │
│                                                              │
│  Найдено 4 ошибок, 2 предупреждений:                          │
│                                                              │
│  ❌ ОШИБКИ:                                                   │
│                                                              │
│  1. Дублирующийся ID стены                                   │
│     Локация: Таверна • Файл: tavern.json                     │
│     ID 'wall_6' используется дважды.                          │
│     💡 Переименуйте вторую стену                              │
│     [Показать на карте]  [Открыть файл]                      │
│                                                              │
│  2. Узел сна внутри кровати                                  │
│     Локация: Таверна • Узел: kitchen_bed_2                   │
│     💡 Сдвиньте узел на 0.5-1.0м                              │
│     [Показать на карте]                                      │
│                                                              │
│  3. NPC ссылается на несуществующий узел                     │
│     NPC: guard_borko • Activity: guarding_gate               │
│     💡 Измените position на 'gate_arch'                      │
│     [Открыть NPC config]                                    │
│                                                              │
│  4. Изолированный выход из локации                           │
│     Локация: Таверна • Boundary: exit_east                  │
│     💡 Проверьте геометрию вокруг (17.5, 5.0)                │
│     [Показать на карте]                                      │
│                                                              │
│  ⚠️ ПРЕДУПРЕЖДЕНИЯ:                                           │
│                                                              │
│  1. Недостаточно кроватей в «Таверне»                        │
│  2. Пространственный реестр устарел                          │
│     [Пересобрать граф]                                       │
│                                                              │
│  [Закрыть]                              [Сохранить принудительно] │
└─────────────────────────────────────────────────────────────┘
```

Кнопка «Показать на карте» центрирует канвас на координатах ошибки, подсвечивает объект красным.

Кнопка «Сохранить принудительно» — с подтверждением и комментарием в JSON: `__validation_overridden`.

### 5.5. Live-валидация на канвасе

Не ждать «Сохранить» — показывать проблемы сразу:
- Стена с дублирующим ID → мерцает жёлтым
- Дверь не на стене → красный контур + иконка ❌
- Sleep node внутри объекта → фиолетовый контур + 🛏️❌
- Изолированный boundary node → красный круг
- NPC spawn внутри объекта → красная иконка ❌

Sidebar справа: «Проблемы (4)». Клик → центрирует канвас. Авто-обновление (debounce 500ms).

### 5.6. Оркестратор

```python
# backend/map_editor/validators/campaign_validator.py

class CampaignValidator:
    def __init__(self, campaign_root: Path):
        self.campaign_root = campaign_root
        self.validators = [
            IDConsistencyValidator(),
            GeometryValidator(),
            NodeGraphValidator(),
            NPCConfigValidator(),
            CrossReferenceValidator(),
            ScheduleValidator(),
            BedValidator(),
        ]
    
    def validate(self) -> ValidationResult:
        all_errors = []
        all_warnings = []
        
        campaign_data = self._load_campaign()
        
        for validator in self.validators:
            result = validator.validate(campaign_data)
            all_errors.extend(result.errors)
            all_warnings.extend(result.warnings)
        
        cross_errors = self._cross_validate(campaign_data)
        all_errors.extend(cross_errors)
        
        return ValidationResult(errors=all_errors, warnings=all_warnings)
```

### 5.7. Тест-кейсы

```python
class TestIDConsistencyValidator:
    def test_duplicate_wall_id_detected(self):
        """wall_6 дважды → ERROR."""
        data = make_test_campaign(walls=[
            Wall(id="wall_6", x1=14, y1=12, x2=14, y2=1),
            Wall(id="wall_6", x1=14, y1=8, x2=19, y2=8),
        ])
        result = IDConsistencyValidator().validate(data)
        assert any(e.code == "DUPLICATE_WALL_ID" for e in result.errors)


class TestGeometryValidator:
    def test_sleep_node_inside_bed_error(self):
        """Sleep node внутри кровати → ERROR."""
        data = make_test_campaign(
            locations=[Location(
                id="tavern",
                nodes={"kitchen_bed_2": Node(x=17.5, y=5.0)},
                objects=[Obj(id="bed_37", x=17.54, y=5.17, w=0.8, h=1.8, 
                            passability={"walk": False})]
            )],
            npcs=[NPC(npc_id="tornin", activity_map={
                "sleeping": {"location_id": "tavern", "position": "kitchen_bed_2"}
            })]
        )
        result = GeometryValidator().validate(data)
        assert any(e.code == "SLEEP_NODE_INSIDE_BED" for e in result.errors)


class TestBedValidator:
    def test_guard_bed_with_wrong_archetype(self):
        """guard_bed с allowed_archetypes=["tavern_keeper"] → ERROR."""
        data = make_test_campaign(objects=[
            Obj(id="bed_69", type="bed", bed_properties={
                "bed_type": "guard_bed",
                "allowed_archetypes": ["tavern_keeper"]  # wrong
            })
        ])
        result = BedValidator().validate(data)
        assert any(e.code == "BED_TYPE_ARCHETYPE_MISMATCH" for e in result.errors)
    
    def test_npc_assigned_to_two_beds_error(self):
        """maid_lusya назначена на 2 кровати → ERROR."""
        data = make_test_campaign(objects=[
            Obj(id="bed_1", bed_properties={"owner_npc_id": "maid_lusya"}),
            Obj(id="bed_2", bed_properties={"owner_npc_id": "maid_lusya"}),
        ])
        result = BedValidator().validate(data)
        assert any(e.code == "NPC_OWNS_TWO_BEDS" for e in result.errors)


class TestCrossReferenceValidator:
    def test_npc_references_missing_node(self):
        """borko.json → guard_post (не существует) → ERROR."""
        data = make_test_campaign(
            locations=[Location(id="city_gate", nodes={"gate_arch": Node(...)})],
            npcs=[NPC(npc_id="borko", activity_map={
                "guarding_gate": {"location_id": "city_gate", "position": "guard_post"}
            })]
        )
        result = CrossReferenceValidator().validate(data)
        assert any(e.code == "NPC_NODE_NOT_FOUND" for e in result.errors)
```

---

## §6. РОЛЬ `build_graph.py` — УТОЧНЕНИЕ

### Что это сейчас

CLI-обёртка вокруг `graph_compiler.compile_graph()`:
1. Читает `frontend/map_editor/campaigns/<campaign>/locations/*.json`
2. Компилирует в `compiled/spatial_registry.json`
3. Запускает валидацию геометрии
4. Печатает результат

### Что это НЕ делает

- Не правит JSON — только читает и компилирует
- Не интерактивный — CLI, не UI
- Не валидирует NPC configs — только locations

### Что нужно изменить

**Сейчас:** Любая ошибка → WARNING в логе, exit 0.

**Должно быть:**
- Изолированный BOUNDARY node → exit 1 (HARD FAIL)
- Стена блокирует единственный путь к sleep node → exit 1
- Дублирующиеся wall IDs → exit 1
- Sleep node внутри bed object → exit 1
- Изолированный обычный node → exit 0, WARNING

### Связь с редактором

Редактор **должен** вызывать `build_graph.py` (или его API) при каждом сохранении кампании. Если exit ≠ 0 — сохранение блокируется.

```python
# frontend/map_editor/save_handler.py
def save_campaign(campaign_id):
    save_locations(campaign_id)
    
    result = run_build_graph(campaign_id)
    
    if result.exit_code != 0:
        show_validation_errors(result.errors)
        return False
    
    other_errors = validate_npc_configs(campaign_id)
    if other_errors:
        show_validation_errors(other_errors)
        return False
    
    show_success("Кампания сохранена и валидна")
    return True
```

---

## §7. ПЛАН ВНЕДРЕНИЯ

### Этап 1: Быстрые фиксы для починки сна (1 день)

**Цель:** NPC спят уже завтра.

1. **Шаг 1** (15 мин): Переименовать `wall_6` в `tavern.json` (вручную в JSON, пока §1 не реализован)
2. **Шаг 2** (15 мин): Сдвинуть sleep nodes `kitchen_bed_1`, `kitchen_bed_2`, `guard_bed` из кроватей
3. **Шаг 3** (5 мин): Переместить spawn Борко
4. **Шаг 4** (5 мин): Починить расписание Люси
5. **Шаг 7** (5 мин): Заменить `guard_post` на `gate_arch` в `borko.json`
6. **Шаг 9** (10 мин): Удалить `tavern_silver_wolf` из Python кода
7. **Шаг 10** (2 мин): `python build_graph.py`
8. **Тест:** Запустить игру, дождаться 22:00 — все 6 NPC идут спать

**Результат:** Сон работает. Без новой архитектуры — просто фиксы данных.

### Этап 2: BedRegistry (1-2 дня)

1. Создать `backend/app/services/spatial/bed_registry.py` (см. §2.4)
2. Зарегистрировать все кровати из locations при загрузке
3. Интегрировать с `life_engine._resolve_position` (см. §2.5)
4. Сериализация/десериализация в scene_state
5. Тест: 7-й NPC сам находит кровать

### Этап 3: Базовый валидатор редактора (2 дня)

1. Создать `backend/map_editor/validators/` структуру
2. Реализовать `IDConsistencyValidator` (Проверка 1)
3. Реализовать `CrossReferenceValidator` (Проверки 4, 8, 12, 13, 14)
4. Реализовать `ScheduleValidator` (Проверка 5)
5. Реализовать `BedValidator` (Проверка 15)
6. Базовый UI: модалка при сохранении с текстом ошибок

### Этап 4: Геометрия и граф (2-3 дня)

1. Реализовать `GeometryValidator` (Проверки 2, 3, 10)
2. Реализовать `NodeGraphValidator` (Проверка 6)
3. Auto-resolve door-wall (§1) — `wall_door_resolution.py`
4. HARD FAIL в `build_graph.py` (Шаг 8)
5. Интеграция `build_graph.py` в редактор

### Этап 5: Визуализация (1-2 дня)

1. Подсветка проблемных объектов на канвасе
2. Sidebar с проблемами
3. Кнопки «Показать на карте» / «Открыть файл»
4. Live-валидация с debounce

### Этап 6: Ручное назначение кроватей (1 день)

1. UI: клик на кровать → выбор NPC (см. §3.1)
2. Сохранение `owner_npc_id` в JSON
3. Валидация: один NPC не на 2+ кроватях
4. Валидация: owner_npc_id существует в NPC configs

### Этап 7: Тесты и CI (1 день)

1. Юнит-тесты для каждого валидатора (см. §5.7)
2. Интеграционный тест: загрузить сломанную кампанию → все 15 типов ошибок ловятся
3. CI gate: `build_graph.py` exit 1 блокирует merge

**Итого:** 9-12 дней работы. После этого — ручные правки JSON больше не нужны.

---

## §8. ЧТО НЕ ДЕЛАТЬ (АНТИ-ПАТТЕРНЫ)

### 8.1. Не валидировать через `try/except` в runtime

Плохо: `try: load_npc() except: return None`. Хорошо: валидация при сохранении в редакторе.

### 8.2. Не делать «auto-fix» в runtime

Плохо: при загрузке автоматически сдвигать sleep node. Хорошо: отказать в сохранении, сказать дизайнеру.

### 8.3. Не дублировать валидацию

Редактор и `build_graph.py` используют одни и те же validator classes.

### 8.4. Не блокировать сохранение без объяснения

Всегда показывать конкретные ошибки с fix_hint.

### 8.5. Не возвращаться к хардкод `owner` тегов без override

Даже если BedRegistry не реализован — лучше временно использовать правила архетипов, чем хардкод `owner:maid_lusya` на каждой кровати.

### 8.6. Не делать псевдослучайное распределение кроватей

NPC выбирают кровать по правилам приоритета (архетип → тип кровати → fallback), не по `random.choice`. Это детерминировано и предсказуемо.

### 8.7. Не молчать о предупреждениях

Warning ≠ «всё ок». Если warning'ов много — они превращаются в шум. Группировка + суточный лимит (после 100 warning'ов одного типа → escalate to error).

---

## §9. МАТРИЦА ПОКРЫТИЯ — ЧТО ПОЧИНЯЕТ КАЖДАЯ ЧАСТЬ

| Проблема | Что чинит |
|---|---|
| Дублирующий `wall_6` | §1 (auto-resolve) + §5 Проверка 1 + Шаг 1 |
| Дверь без `wall_id` | §1 (auto-resolve, не нужен `wall_id`) |
| Sleep node внутри кровати | §5 Проверка 3 + Шаг 2 + §2 (BedRegistry находит ближайшую walkable) |
| Orphan `guard_post` | §5 Проверка 4 + Шаг 7 |
| Расписание Люси с перекрытием | §5 Проверка 5 + Шаг 4 |
| Изолированный `exit_east` | §5 Проверка 6 + Шаг 8 (HARD FAIL в `build_graph.py`) |
| Spawn Борко внутри стола | §5 Проверка 10 + Шаг 3 |
| Stale `tavern_silver_wolf` | §5 Проверка 14 + Шаг 9 |
| Orphan faction IDs | §5 Проверка 8 |
| Orphan secret IDs | §5 Проверка 12 |
| `campaign_id` mismatch | §5 Проверка 13 + Шаг 9 |
| NPC дерутся за кровати (псевдослучайно) | §2 (BedRegistry с правилами приоритета) |
| Designer хочет назначить NPC на кровать | §3 (click-on-bed UI в редакторе) |
| Designer правит JSON руками | §0 Принцип 1 + §5 (валидация при сохранении) |
| `build_graph.py` молчит об ошибках | §6 (HARD FAIL на критичные проблемы) + Шаг 8 |
| Bed type mismatch | §5 Проверка 15 |
| NPC назначен на 2 кровати | §5 Проверка 15 (NPC_OWNS_TWO_BEDS) |

**После внедрения:**
- Дизайнер не может сохранить сломанную кампанию
- NPC находят кровати по правилам приоритета (не случайно)
- Дизайнер может вручную назначать NPC на кровати через UI
- Двери автоматически режут стены
- `build_graph.py` блокирует deploy при геометрических проблемах
- Runtime работает с гарантированно валидными данными

---

## §10. КОНКРЕТНЫЙ СЦЕНАРИЙ — КАК ДОЛЖНО РАБОТАТЬ

### 10.1. Дизайнер создаёт новую кампанию

1. Открывает редактор карт
2. Рисует стены, ставит двери (двери сами режут стены)
3. Размещает узлы навигации
4. Ставит объекты-кровати, выбирает тип (inn_bed / guard_bed / tent)
5. (Опционально) Кликает на кровать, назначает конкретного NPC
6. Нажимает «Сохранить кампанию»

Если всё OK:
> ✅ Кампания сохранена. 6 NPC, 3 локации, 16 секретов, 6 кроватей (3 inn_bed, 1 guard_bed, 2 tent).

Если есть ошибки:
> ❌ Найдено 2 ошибок:
> 1. Узел сна внутри кровати (kitchen_bed_2)
> 2. Изолированный выход (exit_east)
> [Показать на карте] для каждой

### 10.2. Игрок запускает игру

1. 22:00 — tornin (tavern_keeper) идёт в tavern → kitchen_bed_2 (своя по правилам)
2. 22:00 — borko (guard) идёт в city_gate → guard_bed (своя по правилам)
3. 22:00 — orm (blacksmith) идёт в city_gate → tent_1 (tent, любой)
4. 22:00 — goran (merchant) идёт в city_gate → tent_2 (tent, любой)
5. 21:00 — lusya (maid) идёт в tavern → kitchen_bed_1 (своя по правилам)
6. 06:00 — shadow (thief) идёт в city_gate → tent_3 (tent, любой, после того как orm/goran проснулись)

### 10.3. Что если в трактире только 1 кровать

1. 21:00 — lusya пытается kitchen_bed_1 — нет такой кровати → fallback на tent
2. 22:00 — tornin → kitchen_bed_2 (своя, приоритет владельца)
3. lusya идёт в city_gate → tent_3 (если свободна)

### 10.4. Что если дизайнер override'нул кровать

1. Дизайнер кликает на `obj_36` (inn_bed), выбирает «Назначить manually → maid_lusya»
2. В JSON: `owner_npc_id: "maid_lusya"`
3. 21:00 — lusya идёт в `obj_36` (owner override имеет приоритет)
4. Если `obj_36` занята другим NPC (через правила) — lusya fallback на tent

### 10.5. Что если все tents заняты

1. NPC идёт по цепочке: своя → tent → floor
2. Спит на полу (`sleeping_on_floor` activity)
3. Stress recovery 50% от кровати
4. В логах: `[BED_REGISTRY] npc_X could not claim any bed — sleeping on floor`

---

## §11. СВЯЗЬ С ДРУГИМИ ДОКУМЕНТАМИ

- **ENIGMA_CLOSURE_CONTRACT_v7.md** — список багов N1-N15, которые эта система предотвратит в будущем
- **ENIGMA_SELF_HEALING_SYSTEM.md** — runtime invariants и canary tests
- **ТЗ-02 SpatialRegistry.md** — оригинальная спецификация (дополнить auto-resolve дверей)
- **ТЗ-03 MovementEngine.md** — спецификация движка (дополнить BedRegistry integration)

---

## §12. ИТОГ

**Принципы:**
1. Редактор умнее дизайнера — он режет стены, валидирует, говорит по-русски
2. Кровати по правилам, не случайно — архетип → тип кровати → fallback
3. Ручное назначение как override — клик на кровать, выбор NPC
4. Save = Contract — если сохранил, мир играбелен

**После внедрения:**
- Дизайнер не может сохранить сломанную кампанию
- NPC находят кровати по правилам (трактирщик/служанка → inn_bed, стражник → guard_bed, остальные → tent)
- Designer может вручную назначать NPC на кровати
- Двери автоматически режут стены
- `build_graph.py` блокирует deploy при проблемах
- Runtime работает с валидными данными

**План:** 9-12 дней. Сначала быстрые фиксы (1 день) → сон работает. Затем BedRegistry (1-2 дня) → кровати по правилам. Затем валидатор редактора (5-7 дней) → невозможно сохранить сломанный мир.

---

*Этот документ — спецификация. Принципы (редактор умнее, кровати по правилам, ручной override, save = contract) — неизменны. Реализация может корректироваться.*
