"""
map_editor/undo_manager.py
Система отмены/повтора действий (Undo/Redo)
Каждая мутация данных оборачивается в команду с do()/undo()

path: /backend/map_editor/undo_manager.py
Зависимости: dataclasses, copy, typing
Основные сущности: Command (база), AddWallCommand, RemoveWallCommand, AddRoomCommand, RemoveRoomCommand,
AddNodeCommand, RemoveNodeCommand, AddObjectCommand, RemoveObjectCommand, AddPortalCommand, RemovePortalCommand,
TogglePassabilityCommand, UndoManager.
"""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
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

    def __post_init__(self):
        self.label = "Комната"

    def do(self) -> str:
        self.room_id = self.dm.add_room(
            self.filename, self.name, self.x, self.y, self.width, self.height
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
    obj_id: str = ""

    def __post_init__(self):
        self.label = f"Объект: {self.obj_type}"

    def do(self) -> str:
        self.obj_id = self.dm.add_object(
            self.filename, self.obj_type, self.x, self.y,
            self.width, self.height, self.rotation
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
class AddPortalCommand(Command):
    """Добавление портала"""
    dm: Any = None
    filename: str = ""
    portal_type: str = ""
    x: float = 0.0
    y: float = 0.0
    label: str = ""
    target: str = ""
    portal_id: str = ""

    def __post_init__(self):
        self.label = f"Портал: {self.portal_type}"

    def do(self) -> str:
        self.portal_id = self.dm.add_portal(
            self.filename, self.portal_type, self.x, self.y, self.label, self.target
        )
        return self.portal_id

    def undo(self):
        if self.portal_id:
            self.dm.remove_portal(self.filename, self.portal_id)


@dataclass
class RemovePortalCommand(Command):
    """Удаление портала с сохранением данных для восстановления"""
    dm: Any = None
    filename: str = ""
    portal_data: Dict = field(default_factory=dict)

    def __post_init__(self):
        self.label = "Удалить портал"

    def do(self):
        if self.portal_data.get("id"):
            self.dm.remove_portal(self.filename, self.portal_data["id"])

    def undo(self):
        if self.portal_data.get("id"):
            loc = self.dm.locations[self.filename]
            loc["portals"].append(deepcopy(self.portal_data))


@dataclass
class RotateObjectCommand(Command):
    """Поворот объекта на заданный угол"""
    dm: Any = None
    filename: str = ""
    obj_index: int = -1
    old_rotation: float = 0
    delta: float = 45

    def __post_init__(self):
        self.label = "Поворот"

    def do(self):
        loc = self.dm.locations[self.filename]
        loc["objects"][self.obj_index]["rotation"] = (self.old_rotation + self.delta) % 360

    def undo(self):
        loc = self.dm.locations[self.filename]
        loc["objects"][self.obj_index]["rotation"] = self.old_rotation


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


class TogglePassabilityCommand(Command):
    """Переключение флага проходимости объекта"""
    dm: Any = None
    filename: str = ""
    obj_index: int = -1
    flag: str = ""
    old_value: bool = False

    def __post_init__(self):
        self.label = f"Проходимость: {self.flag}"

    def do(self):
        loc = self.dm.locations[self.filename]
        obj = loc["objects"][self.obj_index]
        obj["passability"][self.flag] = not self.old_value

    def undo(self):
        loc = self.dm.locations[self.filename]
        obj = loc["objects"][self.obj_index]
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