"""
path: /frontend/sprite_resolver.py

Единственный источник маппинга тип объекта → спрайт.
Независим от map_editor — сам загружает тайлы из общей папки пикселей.

Назначение: Разрешение типа сущности в pygame.Surface для рендерера
Зависимости: pygame, typing, os
Основные сущности: ENTITY_SPRITE_MAP, get_entity_sprite
"""
import os
from typing import Dict, Optional, Tuple

import pygame

# Путь к папке с палитрами — рядом с map_editor
_BASE_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "map_editor", "pixels", "2-Bit Pack")
)
_TILE_SIZE = 16

# Кэш спрайтшитов: ключ "Папка/Файл" → Surface
_sheets: Dict[str, pygame.Surface] = {}
# Кэш тайлов: ключ "Папка/Файл:col:row" → Surface
_tiles: Dict[str, pygame.Surface] = {}

# === Маппинг типа объекта на спрайт (sheet_key, col, row) ===
ENTITY_SPRITE_MAP: Dict[str, Tuple[str, int, int]] = {
    # Мебель
    "table": ("Deadbeat/deadbeat_b", 5, 11),
    "chair": ("Deadbeat/deadbeat_b", 8, 17),
    "stool": ("Deadbeat/deadbeat_b", 9, 19),
    "bar": ("Deadbeat/deadbeat_b", 5, 11),  # TODO: временная заглушка, будет удалено после: добавления уникального спрайта для bar
    "bed": ("Deadbeat/deadbeat_b", 8, 16),
    "bookshelf": ("Deadbeat/deadbeat_b", 7, 16),
    # Двери и проходы
    "door": ("Deadbeat/deadbeat_b", 3, 9),
    "window": ("Deadbeat/deadbeat_b", 6, 9),
    "gap": ("Deadbeat/deadbeat_b", 3, 9),  # TODO: временная заглушка, будет удалено после: добавления уникального спрайта для gap
    "ladder": ("Deadbeat/deadbeat_b", 0, 9),
    "hatch": ("Deadbeat/deadbeat_b", 11, 16),
    "stairs_up": ("Deadbeat/deadbeat_b", 0, 9),  # TODO: временная заглушка
    "stairs_down": ("Deadbeat/deadbeat_b", 0, 9),  # TODO: временная заглушка
    "door_transition": ("Deadbeat/deadbeat_b", 3, 9),  # TODO: временная заглушка
    "portal_magic": ("Deadbeat/deadbeat_b", 6, 2),
    # Природа
    "tree": ("Deadbeat/deadbeat_b", 6, 0),
    "spruce": ("Deadbeat/deadbeat_b", 6, 3),
    "apple_tree": ("Deadbeat/deadbeat_b", 7, 4),
    "palm": ("Deadbeat/deadbeat_b", 7, 7),
    "grass": ("Deadbeat/deadbeat_b", 7, 0),
    "rocks": ("Deadbeat/deadbeat_b", 6, 18),
    # Интерьер
    "tent": ("Deadbeat/deadbeat_b", 8, 15),
    "toilet": ("Deadbeat/deadbeat_b", 7, 21),
    "cauldron": ("Deadbeat/deadbeat_b", 11, 17),
    "campfire": ("Deadbeat/deadbeat_b", 4, 15),
    # Декорации
    "sign_flophouse": ("Deadbeat/deadbeat_b", 11, 4),
    "bones": ("Deadbeat/deadbeat_b", 22, 13),
    "heart": ("Deadbeat/deadbeat_b", 22, 12),
    "heart_empty": ("Deadbeat/deadbeat_b", 22, 12),  # TODO: временная заглушка
    "decoration": ("Deadbeat/deadbeat_b", 3, 9),  # TODO: временная заглушка
    # NPC
    "mage": ("Deadbeat/deadbeat_b", 23, 22),
    "warrior": ("Deadbeat/deadbeat_b", 25, 21),
    "person": ("Deadbeat/deadbeat_b", 23, 21),
    "thief": ("Deadbeat/deadbeat_b", 25, 22),
    "cow": ("Deadbeat/deadbeat_b", 25, 28),
    "knight": ("Deadbeat/deadbeat_b", 26, 21),
}


def _load_sheet(sheet_key: str) -> Optional[pygame.Surface]:
    """Загружает спрайтшит с диска в кэш."""
    if sheet_key in _sheets:
        return _sheets[sheet_key]
    
    parts = sheet_key.replace("\\", "/").split("/")
    if len(parts) != 2:
        return None
    
    palette_dir, file_name = parts
    path = os.path.join(_BASE_DIR, palette_dir, file_name)
    
    if not os.path.exists(path):
        path_png = path + ".png"
        if not os.path.exists(path_png):
            return None
        path = path_png
    
    try:
        sheet = pygame.image.load(path).convert_alpha()
        _sheets[sheet_key] = sheet
        return sheet
    except pygame.error:
        return None


def get_entity_sprite(entity_type: str) -> Optional[pygame.Surface]:
    """Возвращает тайл для типа сущности из кэша или с диска."""
    sprite_info = ENTITY_SPRITE_MAP.get(entity_type)
    if not sprite_info:
        return None
    
    sheet_key, col, row = sprite_info
    tile_key = f"{sheet_key}:{col}:{row}"
    
    if tile_key in _tiles:
        return _tiles[tile_key]
    
    sheet = _load_sheet(sheet_key)
    if not sheet:
        return None
    
    ts = _TILE_SIZE
    x, y = col * ts, row * ts
    
    # Защита от выхода за границы листа
    if x + ts > sheet.get_width() or y + ts > sheet.get_height():
        return None
    
    tile = sheet.subsurface(pygame.Rect(x, y, ts, ts)).copy()
    _tiles[tile_key] = tile
    return tile