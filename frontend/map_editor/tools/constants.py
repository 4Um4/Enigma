"""
map_editor/tools/constants.py
Идентификаторы инструментов редактора карт.
"""

TOOL_SELECT = "select"
TOOL_WALL = "wall"  # Рисование стен
TOOL_ROOM = "room"  # Создание комнат
TOOL_OBJECT = "object"  # Размещение объектов
TOOL_PASSAGE = "passage"  # Создание прохода в стене
TOOL_LABEL = "label"  # Создание надписи
TOOL_NPC = "npc"  # Размещение NPC
TOOL_SPAWN = "spawn"  # Установка точки спавна игрока
TOOL_DELETE = "delete"  # Удаление
TOOL_NODE = "node"  # Создание и связывание навигационных узлов

MODE_WORLD = "world"
MODE_LOCAL = "local"