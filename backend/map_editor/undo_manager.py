"""
map_editor/undo_manager.py
Система отмены/повтора действий (Undo/Redo)
Каждая мутация данных оборачивается в команду с do()/undo()

path: /backend/map_editor/undo_manager.py
Зависимости: dataclasses, copy, typing
Основные сущности: Command (база), AddWallCommand, RemoveWallCommand, AddRoomCommand, RemoveRoomCommand,
AddNodeCommand, RemoveNodeCommand, AddObjectCommand, RemoveObjectCommand,
TogglePassabilityCommand, UndoManager.
"""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from copy import deepcopy


class Command:
    """Базовая команда для undo/redo — НЕ dataclass, чтобы не съедать первый позиционный аргумент наследников"""
    label: str = ""

    def do(self) -> Any:
        return None

    def undo(self) -> Any:
        return None


@dataclass
class AddWallCommand(Command):
    """Добавление стены"""
    dm: Any = None
    filename: str = ""
    x1: float = 0.0
    y1: float = 0.0
    x2: float = 0.0
    y2: float = 0.0
    wall_type: str = "wall"
    thickness: float = 0.2
    wall_id: str = ""

    def __post_init__(self):
        self.label = "Стена"

    def do(self) -> str:
        self.wall_id = self.dm.add_wall(
            self.filename, self.x1, self.y1, self.x2, self.y2,
            self.wall_type, self.thickness
        )
        return self.wall_id

    def undo(self):
        if self.wall_id:
            self.dm.remove_wall(self.filename, self.wall_id)


@dataclass
class RemoveWallCommand(Command):
    """Удаление стены с сохранением данных для восстановления"""
    dm: Any = None
    filename: str = ""
    wall_data: Dict = field(default_factory=dict)

    def __post_init__(self):
        self.label = "Удалить стену"

    def do(self):
        if self.wall_data.get("id"):
            self.dm.remove_wall(self.filename, self.wall_data["id"])

    def undo(self):
        if self.wall_data.get("id"):
            loc = self.dm.locations[self.filename]
            loc["walls"].append(deepcopy(self.wall_data))


@dataclass
class AddPassageCommand(Command):
    """Создание прохода в стене"""
    dm: Any = None
    filename: str = ""
    wall_id: str = ""
    passage_type: str = "door"
    position: Dict = field(default_factory=dict)
    passage_id: str = ""

    def __post_init__(self):
        self.label = f"Проход: {self.passage_type}"

    def do(self) -> str:
        self.passage_id = self.dm.add_passage(
            self.filename, self.wall_id, self.passage_type, self.position)
        return self.passage_id

    def undo(self):
        if self.passage_id:
            self.dm.remove_passage(self.filename, self.passage_id)


@dataclass
class RemovePassageCommand(Command):
    """Удаление прохода с сохранением данных для восстановления"""
    dm: Any = None
    filename: str = ""
    passage_data: Dict = field(default_factory=dict)

    def __post_init__(self):
        self.label = "Удалить проход"

    def do(self):
        if self.passage_data.get("id"):
            self.dm.remove_passage(self.filename, self.passage_data["id"])

    def undo(self):
        if self.passage_data.get("id"):
            loc = self.dm.locations[self.filename]
            loc["passages"].append(deepcopy(self.passage_data))


@dataclass
class AddRoomCommand(Command):
    """Добавление комнаты"""
    dm: Any = None
    filename: str = ""
    name: str = ""
    x: float = 0.0
    y: float = 0.0
    width: float = 0.0
    height: float = 0.0
    room_id: str = ""
    polygon: Optional[List[Tuple[float, float]]] = None
    area_sqm: Optional[float] = None

    def __post_init__(self):
        self.label = "Комната"

    def do(self) -> str:
        self.room_id = self.dm.add_room(
            self.filename, self.name, self.x, self.y, self.width, self.height,
            polygon=self.polygon, area_sqm=self.area_sqm
        )
        return self.room_id

    def undo(self):
        if self.room_id:
            self.dm.remove_room(self.filename, self.room_id)


@dataclass
class RemoveRoomCommand(Command):
    """Удаление комнаты с сохранением данных для восстановления"""
    dm: Any = None
    filename: str = ""
    room_data: Dict = field(default_factory=dict)

    def __post_init__(self):
        self.label = "Удалить комнату"

    def do(self):
        if self.room_data.get("id"):
            self.dm.remove_room(self.filename, self.room_data["id"])

    def undo(self):
        if self.room_data.get("id"):
            loc = self.dm.locations[self.filename]
            loc["rooms"].append(deepcopy(self.room_data))


@dataclass
class RenameCommand(Command):
    """Универсальное переименование сущности"""
    dm: Any = None
    filename: str = ""
    entity_type: str = ""  # "room", "object", "portal"
    entity_id: str = ""
    old_name: str = ""
    new_name: str = ""

    def __post_init__(self):
        self.label = "Переименовать"

    def do(self):
        self.dm.rename_entity(self.filename, self.entity_type, self.entity_id, self.new_name)

    def undo(self):
        self.dm.rename_entity(self.filename, self.entity_type, self.entity_id, self.old_name)


@dataclass
class AddLabelCommand(Command):
    """Создание надписи"""
    dm: Any = None
    filename: str = ""
    x: float = 0.0
    y: float = 0.0
    text: str = "Надпись"
    label_id: str = ""

    def __post_init__(self):
        self.label = "Надпись"

    def do(self) -> str:
        self.label_id = self.dm.add_label(self.filename, self.x, self.y, self.text)
        return self.label_id

    def undo(self):
        if self.label_id:
            self.dm.remove_label(self.filename, self.label_id)


@dataclass
class RemoveLabelCommand(Command):
    """Удаление надписи с сохранением для восстановления"""
    dm: Any = None
    filename: str = ""
    label_data: Dict = field(default_factory=dict)

    def __post_init__(self):
        self.label = "Удалить надпись"

    def do(self):
        if self.label_data.get("id"):
            self.dm.remove_label(self.filename, self.label_data["id"])

    def undo(self):
        if self.label_data.get("id"):
            loc = self.dm.locations[self.filename]
            loc["labels"].append(deepcopy(self.label_data))


@dataclass
class AddNpcCommand(Command):
    """Размещение NPC на локации"""
    dm: Any = None
    filename: str = ""
    ref_id: str = ""
    x: float = 0.0
    y: float = 0.0
    room_id: str = ""
    npc_ref: str = ""

    def __post_init__(self):
        self.label = "Разместить NPC"

    def do(self) -> str:
        self.npc_ref = self.dm.add_npc(self.filename, self.ref_id, self.x, self.y, self.room_id)
        return self.npc_ref

    def undo(self):
        if self.npc_ref:
            self.dm.remove_npc(self.filename, self.ref_id)


@dataclass
class RemoveNpcCommand(Command):
    """Удаление NPC с сохранением для восстановления"""
    dm: Any = None
    filename: str = ""
    npc_data: Dict = field(default_factory=dict)

    def __post_init__(self):
        self.label = "Удалить NPC"

    def do(self):
        if self.npc_data.get("ref_id"):
            self.dm.remove_npc(self.filename, self.npc_data["ref_id"])

    def undo(self):
        if self.npc_data.get("ref_id"):
            loc = self.dm.locations[self.filename]
            loc["npcs"].append(deepcopy(self.npc_data))


@dataclass
class AddNodeCommand(Command):
    """Добавление навигационного узла"""
    dm: Any = None
    filename: str = ""
    node_id: str = ""
    x: float = 0.0
    y: float = 0.0
    label: str = ""

    def __post_init__(self):
        self.label = "Узел"

    def do(self) -> str:
        self.dm.add_node(self.filename, self.node_id, self.x, self.y, self.label)
        return self.node_id

    def undo(self):
        if self.node_id:
            self.dm.remove_node(self.filename, self.node_id)


@dataclass
class RemoveNodeCommand(Command):
    """Удаление узла с сохранением данных для восстановления"""
    dm: Any = None
    filename: str = ""
    node_id: str = ""
    node_data: Dict = field(default_factory=dict)

    def __post_init__(self):
        self.label = "Удалить узел"

    def do(self):
        if self.node_id:
            self.dm.remove_node(self.filename, self.node_id)

    def undo(self):
        if self.node_id:
            loc = self.dm.locations[self.filename]
            loc["nodes"][self.node_id] = deepcopy(self.node_data)


@dataclass
class AddObjectCommand(Command):
    """Добавление объекта (мебель, декор)"""
    dm: Any = None
    filename: str = ""
    obj_type: str = ""
    x: float = 0.0
    y: float = 0.0
    width: float = 1.0
    height: float = 1.0
    rotation: float = 0
    wall_id: str = ""
    obj_id: str = ""

    def __post_init__(self):
        self.label = f"Объект: {self.obj_type}"

    def do(self) -> str:
        self.obj_id = self.dm.add_object(
            self.filename, self.obj_type, self.x, self.y,
            self.width, self.height, self.rotation, self.wall_id
        )
        return self.obj_id

    def undo(self):
        if self.obj_id:
            self.dm.remove_object(self.filename, self.obj_id)


@dataclass
class RemoveObjectCommand(Command):
    """Удаление объекта с сохранением данных для восстановления"""
    dm: Any = None
    filename: str = ""
    obj_id: str = ""
    obj_data: Dict = field(default_factory=dict)

    def __post_init__(self):
        self.label = "Удалить объект"

    def do(self):
        if self.obj_id:
            self.dm.remove_object(self.filename, self.obj_id)

    def undo(self):
        if self.obj_data:
            loc = self.dm.locations[self.filename]
            loc["objects"].append(deepcopy(self.obj_data))


@dataclass
class RotateObjectCommand(Command):
    """Поворот объекта на заданный угол"""
    dm: Any = None
    filename: str = ""
    obj_id: str = ""
    old_rotation: float = 0
    delta: float = 45

    def __post_init__(self):
        self.label = "Поворот"

    def _find_obj(self) -> Optional[Dict]:
        for o in self.dm.locations[self.filename]["objects"]:
            if o.get("id") == self.obj_id:
                return o
        return None

    def do(self):
        obj = self._find_obj()
        if obj:
            try:
                obj["rotation"] = (float(self.old_rotation) + self.delta) % 360
            except (ValueError, TypeError):
                obj["rotation"] = self.delta % 360

    def undo(self):
        obj = self._find_obj()
        if obj:
            try:
                obj["rotation"] = float(self.old_rotation)
            except (ValueError, TypeError):
                obj["rotation"] = 0.0


@dataclass
class MirrorObjectCommand(Command):
    """Зеркальное отражение объекта (для дверей/окон в стенах)"""
    dm: Any = None
    filename: str = ""
    obj_id: str = ""
    old_mirrored: bool = False

    def __post_init__(self):
        self.label = "Зеркало"

    def _find_obj(self) -> Optional[Dict]:
        for o in self.dm.locations[self.filename]["objects"]:
            if o.get("id") == self.obj_id:
                return o
        return None

    def do(self):
        obj = self._find_obj()
        if obj:
            obj["mirrored"] = not obj.get("mirrored", False)

    def undo(self):
        obj = self._find_obj()
        if obj:
            obj["mirrored"] = self.old_mirrored


@dataclass
class MoveEntityCommand(Command):
    """Перемещение любой сущности (объект, стена, комната, узел, надпись)"""
    dm: Any = None
    filename: str = ""
    entity_type: str = ""
    entity_id: str = ""
    dx: float = 0.0
    dy: float = 0.0
    drag_wall: bool = False
    _skip_do: bool = False

    def __post_init__(self):
        self.label = "Перемещение"

    def _apply(self, dx: float, dy: float) -> None:
        loc = self.dm.locations[self.filename]
        if self.entity_type == "object":
            obj = next((o for o in loc["objects"] if o.get("id") == self.entity_id), None)
            if obj:
                obj["position"]["x"] += dx
                obj["position"]["y"] += dy
                if self.drag_wall and obj.get("wall_id"):
                    wall = next((w for w in loc["walls"] if w["id"] == obj["wall_id"]), None)
                    if wall:
                        wall["x1"] += dx; wall["y1"] += dy
                        wall["x2"] += dx; wall["y2"] += dy
        elif self.entity_type == "wall":
            wall = next((w for w in loc["walls"] if w["id"] == self.entity_id), None)
            if wall:
                wall["x1"] += dx; wall["y1"] += dy
                wall["x2"] += dx; wall["y2"] += dy
        elif self.entity_type == "room":
            room = next((r for r in loc["rooms"] if r["id"] == self.entity_id), None)
            if room:
                room["x"] += dx; room["y"] += dy
                if "polygon" in room:
                    for p in room["polygon"]:
                        p[0] += dx; p[1] += dy
        elif self.entity_type == "node":
            node = loc["nodes"].get(self.entity_id)
            if node:
                node["x"] += dx; node["y"] += dy
        elif self.entity_type == "label":
            lbl = next((l for l in loc.get("labels", []) if l.get("id") == self.entity_id), None)
            if lbl:
                lbl["x"] += dx; lbl["y"] += dy
        elif self.entity_type == "npc":
            npc = next((n for n in loc.get("npcs", []) if n.get("ref_id") == self.entity_id), None)
            if npc:
                npc["position"]["x"] += dx
                npc["position"]["y"] += dy
        elif self.entity_type == "spawn":
            spawn = loc.get("player_spawn")
            if spawn:
                spawn["x"] += dx
                spawn["y"] += dy

    def do(self):
        if not self._skip_do:
            self._apply(self.dx, self.dy)

    def undo(self):
        self._apply(-self.dx, -self.dy)


@dataclass
class ResizeObjectCommand(Command):
    """Изменение размера объекта"""
    dm: Any = None
    filename: str = ""
    obj_id: str = ""
    old_w: float = 0.0
    old_h: float = 0.0
    new_w: float = 0.0
    new_h: float = 0.0

    def __post_init__(self):
        self.label = "Размер"

    def _find_obj(self) -> Optional[Dict]:
        for o in self.dm.locations[self.filename]["objects"]:
            if o.get("id") == self.obj_id:
                return o
        return None

    def do(self):
        obj = self._find_obj()
        if obj:
            obj["size"]["w"] = self.new_w
            obj["size"]["h"] = self.new_h

    def undo(self):
        obj = self._find_obj()
        if obj:
            obj["size"]["w"] = self.old_w
            obj["size"]["h"] = self.old_h


@dataclass
class PasteCommand(Command):
    """Вставка объектов и стен из буфера обмена"""
    dm: Any = None
    filename: str = ""
    walls: List[Dict] = field(default_factory=list)
    objects: List[Dict] = field(default_factory=list)
    wall_ids: List[str] = field(default_factory=list)
    obj_ids: List[str] = field(default_factory=list)

    def __post_init__(self):
        self.label = "Вставить"

    def do(self):
        self.wall_ids.clear()
        for wall in self.walls:
            wid = self.dm.add_wall(
                self.filename,
                wall["x1"], wall["y1"], wall["x2"], wall["y2"],
                wall.get("type", "wall"), wall.get("thickness", 0.2))
            self.wall_ids.append(wid)
        self.obj_ids.clear()
        for obj in self.objects:
            oid = self.dm.add_object(
                self.filename, obj["type"],
                obj["position"]["x"], obj["position"]["y"],
                obj["size"]["w"], obj["size"]["h"],
                obj.get("rotation", 0))
            self.obj_ids.append(oid)

    def undo(self):
        for oid in reversed(self.obj_ids):
            self.dm.remove_object(self.filename, oid)
        for wid in self.wall_ids:
            self.dm.remove_wall(self.filename, wid)


@dataclass
class TogglePassabilityCommand(Command):
    """Переключение флага проходимости объекта"""
    dm: Any = None
    filename: str = ""
    obj_id: str = ""
    flag: str = ""
    old_value: bool = False

    def __post_init__(self):
        self.label = f"Проходимость: {self.flag}"

    def _find_obj(self) -> Optional[Dict]:
        for o in self.dm.locations[self.filename]["objects"]:
            if o.get("id") == self.obj_id:
                return o
        return None

    def do(self):
        obj = self._find_obj()
        if obj:
            obj["passability"][self.flag] = not self.old_value

    def undo(self):
        obj = self._find_obj()
        if obj:
            obj["passability"][self.flag] = self.old_value


class CompoundCommand(Command):
    """Составная команда — группа подкоманд (комната + 4 стены)"""

    def __init__(self, label: str, commands: List[Command]):
        self.label = label
        self.commands = commands

    def do(self):
        for cmd in self.commands:
            cmd.do()

    def undo(self):
        for cmd in reversed(self.commands):
            cmd.undo()


class UndoManager:
    """Менеджер стека отмены/повтора"""

    def __init__(self, max_depth: int = 100):
        self.undo_stack: List[Command] = []
        self.redo_stack: List[Command] = []
        self.max_depth = max_depth

    def push(self, command: Command) -> Any:
        """Выполняет команду и добавляет в стек отмены"""
        result = command.do()
        self.undo_stack.append(command)
        # новое действие сбрасывает стек повтора
        self.redo_stack.clear()
        # ограничение глубины
        if len(self.undo_stack) > self.max_depth:
            self.undo_stack.pop(0)
        return result

    def undo(self) -> Optional[str]:
        """Отменяет последнее действие, возвращает метку"""
        if not self.undo_stack:
            return None
        command = self.undo_stack.pop()
        command.undo()
        self.redo_stack.append(command)
        return command.label

    def redo(self) -> Optional[str]:
        """Повторяет отменённое действие, возвращает метку"""
        if not self.redo_stack:
            return None
        command = self.redo_stack.pop()
        command.do()
        self.undo_stack.append(command)
        return command.label

    def clear(self):
        """Очищает оба стека (при смене локации)"""
        self.undo_stack.clear()
        self.redo_stack.clear()

    @property
    def can_undo(self) -> bool:
        return len(self.undo_stack) > 0

    @property
    def can_redo(self) -> bool:
        return len(self.redo_stack) > 0

    @property
    def undo_label(self) -> str:
        return self.undo_stack[-1].label if self.undo_stack else ""

    @property
    def redo_label(self) -> str:
        return self.redo_stack[-1].label if self.redo_stack else ""