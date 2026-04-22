"""Реестр спрайтов для работы с тайлсетами и палитрами.

path: /backend/map_editor/sprite_registry.py
Назначение: Универсальный кэширующий провайдер тайлов из спрайтшитов. Поддерживает произвольные паки палитр.
Зависимости: pygame, typing
Основные сущности: SpriteRegistry (singleton через модуль)

Позволяет получать любой тайл из спрайтшита по ключу:
    registry.get("Deadbeat/deadbeat_b", col, row)

Синглтон создается на уровне модуля: sprite_registry
"""
import os
import pygame
from typing import Dict, Optional

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
            "rows": sheet.get_height() // ts
        }

    def clear_cache(self) -> None:
        """Очищает кэш (например, при смене палитры)."""
        self._sheets.clear()
        self._tiles.clear()


# Глобальный экземпляр реестра
sprite_registry = SpriteRegistry()