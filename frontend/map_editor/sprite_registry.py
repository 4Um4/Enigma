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
from typing import Dict, Optional, Tuple

import pygame

# ME-D5: дома определений спрайтов (деривация ниже; цикла нет — data_manager
# не импортирует sprite_registry, проверено S348 командой 91/92)
from data.npc_data import NPC_SPRITE_MAP
from data_manager import NPC_PRESETS, OBJECT_PRESETS

# Базовая директория с палитрами (NEW-MVP-007 FIX: 2-Bit Pack не существует, используем pixels)
_BASE_DIR = os.path.join(os.path.dirname(__file__), "pixels")
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

        # S176 FIX: Поддержка произвольной вложенности папок (Pers/traktir/Трактирщик)
        parts = sheet_key.replace("\\", "/").strip("/").split("/")
        if not parts:
            return None

        path = os.path.join(self.base_dir, *parts)

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

    def get(self, sheet_key: str, col: int, row: int, tile_w: int = 16, tile_h: int = 16) -> Optional[pygame.Surface]:
        """Возвращает тайл из спрайтшита по сетке.

        Args:
            sheet_key: Путь относительно папки pixels, например "Deadbeat/deadbeat_b.png"
            col: Столбец тайла (начиная с 0)
            row: Ряд тайла (начиная с 0)
            tile_w: Ширина тайла (по умолчанию 16)
            tile_h: Высота тайла (по умолчанию 16)
        """
        # Нормализуем ключ (убираем .png если передали)
        clean_key = sheet_key if not sheet_key.endswith(".png") else sheet_key[:-4]
        tile_key = f"{clean_key}:{col}:{row}:{tile_w}:{tile_h}"

        if tile_key in self._tiles:
            return self._tiles[tile_key]

        sheet = self._load_sheet(clean_key)
        if not sheet:
            return None

        x, y = col * tile_w, row * tile_h

        # Защита от выхода за границы листа
        if x + tile_w > sheet.get_width() or y + tile_h > sheet.get_height():
            return None

        tile = sheet.subsurface(pygame.Rect(x, y, tile_w, tile_h)).copy()
        self._tiles[tile_key] = tile
        return tile

    def get_rect(self, sheet_key: str, x: int, y: int, w: int, h: int, threshold: int = 220, outline: int = 1) -> Optional[pygame.Surface]:
        """S176: Возвращает тайл по точным пиксельным координатам с настройкой фона и обводки."""
        clean_key = sheet_key if not sheet_key.endswith(".png") else sheet_key[:-4]
        tile_key = f"{clean_key}:R:{x}:{y}:{w}:{h}:{threshold}:{outline}"

        if tile_key in self._tiles:
            return self._tiles[tile_key]

        sheet = self._load_sheet(clean_key)
        if not sheet:
            return None

        rect = pygame.Rect(x, y, w, h)
        if rect.right > sheet.get_width() or rect.bottom > sheet.get_height():
            return None

        tile = sheet.subsurface(rect).copy()
        # S176 FIX: Тотальное удаление белого гало через NumPy
        result = tile.convert_alpha()
        
        try:
            import numpy as np
            arr = pygame.surfarray.pixels3d(result)
            alpha = pygame.surfarray.pixels_alpha(result)
            
            # Удаление фона по порогу (легаси S176)
            mask = (arr[:,:,0] > threshold) & (arr[:,:,1] > threshold) & (arr[:,:,2] > threshold)

            # FIX BUG-07 (В1б, решение Мастера): авто-детект фона по угловым
            # пикселям тайла. Порог из данных (часто дефолт 220) не берёт
            # нестандартные фоны (бежевый 226,232,189: синий канал < 220).
            # Если 4 угла однородны (допуск 24/канал) и непрозрачны — фон
            # удаляется по цвету угла независимо от threshold; порог остаётся
            # страховочной маской. Альфа-листы (углы прозрачны) не трогаем.
            _corner_alphas = [int(alpha[0, 0]), int(alpha[0, -1]), int(alpha[-1, 0]), int(alpha[-1, -1])]
            if any(_corner_alphas):
                _ref = [int(arr[0, 0, 0]), int(arr[0, 0, 1]), int(arr[0, 0, 2])]
                _uniform = all(
                    max(abs(int(arr[cy, cx, i]) - _ref[i]) for i in range(3)) <= 24
                    for cy, cx in ((0, 0), (0, -1), (-1, 0), (-1, -1))
                )
                if _uniform:
                    _bg_dist = (
                        (arr[:, :, 0].astype(int) - _ref[0]) ** 2
                        + (arr[:, :, 1].astype(int) - _ref[1]) ** 2
                        + (arr[:, :, 2].astype(int) - _ref[2]) ** 2
                    )
                    mask = mask | (_bg_dist <= 24 * 24 * 3)
            alpha[mask] = 0
            
            # Прозрачным пикселям задаем чёрный цвет (убирает гало при масштабировании)
            alpha_mask = alpha == 0
            arr[alpha_mask] = [0, 0, 0]
            
            # S176 FIX: Внутренняя обводка (эрозия альфа-канала)
            if outline > 0:
                eroded = alpha.copy()
                for _ in range(outline):
                    temp_eroded = eroded.copy()
                    for dx, dy in [(-1,0), (1,0), (0,-1), (0,1)]:
                        shifted = np.roll(eroded, (dx, dy), axis=(0,1))
                        temp_eroded = np.minimum(temp_eroded, shifted)
                    eroded = temp_eroded
                
                # Маска края: внутри спрайта, но эродирована
                edge_mask = (alpha > 0) & (eroded == 0)
                arr[edge_mask] = [0, 0, 0]
                
            del arr, alpha
        except Exception:
            result.set_colorkey((255, 255, 255), pygame.RLEACCEL)
            
        self._tiles[tile_key] = result
        return result

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
# ═══════════════════════════════════════════════════════════════════
# Маппинг типов сущностей — ДЕРИВАЦИЯ из домов определений (ME-D5, S348)
# Объекты: OBJECT_PRESETS[t]["sprite"] · Архетипы NPC: NPC_PRESETS[t]["sprite"]
# Персональные NPC: NPC_SPRITE_MAP (data/npc_data.py)
# Правка спрайта = правка в доме; здесь спрайт-литералов нет.
# ═══════════════════════════════════════════════════════════════════
# 7 типов без sprite в пресете (bar/gap — TODO-заглушки, MISSING_TEXTURES.md).
# Перенос в пресеты — часть текстурных работ (ME-R-627); после переноса — удалить.
_PRESET_SPRITE_FALLBACK: Dict[str, Tuple[str, int, int]] = {
    "bar": ("Deadbeat/deadbeat_b", 5, 11),
    "decoration": ("Deadbeat/deadbeat_b", 3, 9),
    "window": ("Deadbeat/deadbeat_b", 6, 9),
    "stairs_up": ("Deadbeat/deadbeat_b", 0, 9),
    "stairs_down": ("Deadbeat/deadbeat_b", 0, 9),
    "ladder": ("Deadbeat/deadbeat_b", 0, 9),
    "portal_magic": ("Deadbeat/deadbeat_b", 6, 2),
}


def _derive_entity_sprite_map() -> Dict[str, Tuple[str, int, int]]:
    derived: Dict[str, Tuple[str, int, int]] = dict(_PRESET_SPRITE_FALLBACK)
    for _t, _p in OBJECT_PRESETS.items():
        if "sprite" in _p:
            derived[_t] = tuple(_p["sprite"])
    for _a, _p in NPC_PRESETS.items():
        if "sprite" in _p:
            derived[_a] = tuple(_p["sprite"])
    derived.update(NPC_SPRITE_MAP)
    return derived


ENTITY_SPRITE_MAP: Dict[str, Tuple[str, int, int]] = _derive_entity_sprite_map()


def get_entity_sprite(entity_type: str) -> Optional[pygame.Surface]:
    """Возвращает тайл для типа сущности из кэша или с диска (через глобальный реестр)."""
    sprite_info = ENTITY_SPRITE_MAP.get(entity_type)
    if not sprite_info:
        return None
    sheet_key, col, row = sprite_info
    return sprite_registry.get(sheet_key, col, row)


# Глобальный экземпляр реестра
sprite_registry = SpriteRegistry()
