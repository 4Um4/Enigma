"""Реестр спрайтов для работы с тайлсетами и палитрами.

path: /frontend/map_editor/sprite_registry.py

Назначение: Универсальный кэширующий провайдер тайлов из спрайтшитов. Поддерживает произвольные паки палитр.
Зависимости: pygame, typing
Основные сущности: SpriteRegistry (singleton через модуль)

Позволяет получать любой тайл из спрайтшита по ключу:
    registry.get("Deadbeat/deadbeat_b", col, row)

Синглтон создается на уровне модуля: sprite_registry
"""

import os
import pygame
from typing import Dict, Optional, Tuple

# Базовая директория с палитрами
_BASE_DIR = os.path.join(os.path.dirname(__file__), "pixels", "2-Bit Pack")
# Стандартный размер тайла для 2-Bit стилей
_DEFAULT_TILE_SIZE = 16


class SpriteRegistry:
    """Кэширующий провайдер тайлов из спрайтшитов."""

    def __init__(self, base_dir: str = _BASE_DIR, tile_size: int = _DEFAULT_TILE_SIZE):
        self.base_dir = base_dir
        self.tile_size = tile_size
        # Кэш: ключ "Папка/Файл" -> pygame.Surface (весь лист)
        self._sheets: Dict[str, pygame.Surface] = {}
        # Кэш: ключ "Папка/Файл:col:row" -> pygame.Surface (отдельный тайл)
        self._tiles: Dict[str, pygame.Surface] = {}

    def _load_sheet(self, sheet_key: str) -> Optional[pygame.Surface]:
        """Загружает спрайтшит с диска, если его нет в кэше."""
        if sheet_key in self._sheets:
            return self._sheets[sheet_key]

        parts = sheet_key.replace("\\", "/").split("/")
        if len(parts) != 2:
            return None

        palette_dir, file_name = parts
        path = os.path.join(self.base_dir, palette_dir, file_name)

        if not os.path.exists(path):
            path_png = path + ".png"
            if not os.path.exists(path_png):
                return None
            path = path_png

        try:
            sheet = pygame.image.load(path).convert_alpha()
            self._sheets[sheet_key] = sheet
            return sheet
        except pygame.error:
            return None

    def get(self, sheet_key: str, col: int, row: int) -> Optional[pygame.Surface]:
        """Возвращает тайл из спрайтшита.

        Args:
            sheet_key: Путь относительно папки pixels, например "Deadbeat/deadbeat_b.png"
            col: Столбец тайла (начиная с 0)
            row: Ряд тайла (начиная с 0)
        """
        # Нормализуем ключ (убираем .png если передали)
        clean_key = sheet_key if not sheet_key.endswith(".png") else sheet_key[:-4]
        tile_key = f"{clean_key}:{col}:{row}"

        if tile_key in self._tiles:
            return self._tiles[tile_key]

        sheet = self._load_sheet(clean_key)
        if not sheet:
            return None

        ts = self.tile_size
        x, y = col * ts, row * ts

        # Защита от выхода за границы листа
        if x + ts > sheet.get_width() or y + ts > sheet.get_height():
            return None

        tile = sheet.subsurface(pygame.Rect(x, y, ts, ts)).copy()
        self._tiles[tile_key] = tile
        return tile

    def get_sheet_info(self, sheet_key: str) -> Optional[Dict[str, int]]:
        """Возвращает информацию о листе: размер, количество столбцов и строк."""
        clean_key = sheet_key if not sheet_key.endswith(".png") else sheet_key[:-4]
        sheet = self._load_sheet(clean_key)
        if not sheet:
            return None
        ts = self.tile_size
        return {
            "width": sheet.get_width(),
            "height": sheet.get_height(),
            "cols": sheet.get_width() // ts,
            "rows": sheet.get_height() // ts,
        }

    def clear_cache(self) -> None:
        """Очищает кэш (например, при смене палитры)."""
        self._sheets.clear()
        self._tiles.clear()


# ═══════════════════════════════════════════════════════════════════
# Маппинг типов сущностей (используется рендерером)
# ═══════════════════════════════════════════════════════════════════
ENTITY_SPRITE_MAP: Dict[str, Tuple[str, int, int]] = {
    # Мебель
    "table": ("Deadbeat/deadbeat_b", 5, 11),
    "chair": ("Deadbeat/deadbeat_b", 8, 17),
    "stool": ("Deadbeat/deadbeat_b", 9, 19),
    "bar": ("Deadbeat/deadbeat_b", 5, 11),  # TODO: временная заглушка
    "bed": ("Deadbeat/deadbeat_b", 8, 16),
    "bookshelf": ("Deadbeat/deadbeat_b", 7, 16),
    # Двери и проходы
    "door": ("Deadbeat/deadbeat_b", 3, 9),
    "window": ("Deadbeat/deadbeat_b", 6, 9),
    "gap": ("Deadbeat/deadbeat_b", 3, 9),  # TODO: временная заглушка
    "ladder": ("Deadbeat/deadbeat_b", 0, 9),
    "hatch": ("Deadbeat/deadbeat_b", 11, 16),
    "stairs_up": ("Deadbeat/deadbeat_b", 0, 9),
    "stairs_down": ("Deadbeat/deadbeat_b", 0, 9),
    "door_transition": ("Deadbeat/deadbeat_b", 3, 9),
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
    "heart_empty": ("Deadbeat/deadbeat_b", 22, 12),
    "decoration": ("Deadbeat/deadbeat_b", 3, 9),
    # NPC
    "mage": ("Deadbeat/deadbeat_b", 23, 22),
    "warrior": ("Deadbeat/deadbeat_b", 25, 21),
    "person": ("Deadbeat/deadbeat_b", 23, 21),
    "thief": ("Deadbeat/deadbeat_b", 25, 22),
    "cow": ("Deadbeat/deadbeat_b", 25, 28),
    "knight": ("Deadbeat/deadbeat_b", 26, 21),
}


def get_entity_sprite(entity_type: str) -> Optional[pygame.Surface]:
    """Возвращает тайл для типа сущности из кэша или с диска (через глобальный реестр)."""
    sprite_info = ENTITY_SPRITE_MAP.get(entity_type)
    if not sprite_info:
        return None
    sheet_key, col, row = sprite_info
    return sprite_registry.get(sheet_key, col, row)


# Глобальный экземпляр реестра
sprite_registry = SpriteRegistry()
