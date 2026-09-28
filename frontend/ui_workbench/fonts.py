"""
path: /project/frontend/ui_workbench/fonts.py
Назначение: FontProvider — S1/S2 стилизации. Рекурсивный скан
    assets/fonts (паки с подпапками/лицензиями/превью — фильтр по
    расширению .ttf/.otf; мусор игнорируется, удалять не нужно).
    Кэш Font-объектов; fallback SysFont consolas. Роли: title/text/ui.
Зависимости: pygame, pathlib, typing
Основные сущности: FontProvider
"""
from pathlib import Path
from typing import Dict, Tuple

import pygame

_FONT_ROOT = Path(__file__).parent.parent / "assets" / "fonts"
_BASE_SIZES = {"title": 16, "text": 14, "ui": 12}


class FontProvider:
    def __init__(self) -> None:
        self._files: Dict[str, Path] = {}          # имя → путь
        self._cyr_cache: Dict[str, bool] = {}      # имя → умеет ли кириллицу
        self._cache: Dict[Tuple[str, int, bool, bool], pygame.font.Font] = {}
        self.scan()

    def scan(self) -> None:
        """Рекурсивный перескан (при каждом enter F12 — паки накидываются
        без перезапуска). Только .ttf/.otf; имя = stem, коллизия stem'ов
        (одинаковые имена разных форматов) — stem + расширение."""
        self._files.clear()
        if not _FONT_ROOT.exists():
            return
        for f in sorted(_FONT_ROOT.rglob("*")):
            if f.suffix.lower() not in (".ttf", ".otf") or not f.is_file():
                continue
            name = f.stem
            if name in self._files:
                name = f"{f.stem}{f.suffix.lower()}"
            self._files[name] = f

    def names(self) -> list:
        return [""] + sorted(self._files.keys())   # "" = системный consolas

    def supports_cyrillic(self, font_file: str) -> bool:
        """S2: есть ли у шрифта кириллица — по cmap TTF (авторитетный
        источник: то, что шрифт ДЕКЛАРИРУЕТ). Рендер-трюки врут: шрифты
        с формальной кириллицей-пустышкой и сабсеты без неё неотличимы
        пикселями. Читаем cmap через freetype-py (идёт с pygame).
        Проверка: все 66 букв А-Я/а-я объявлены в шрифте."""
        if not font_file:
            return True  # системный consolas — умеет
        if font_file in self._cyr_cache:
            return self._cyr_cache[font_file]
        ok = False
        path = self._files.get(font_file)
        if path:
            try:
                import freetype
                face = freetype.Face(str(path))
                # Без выбранного charmap get_char_index возвращает 0 на всё
                # (симптом «у всех нет кириллицы») — выбираем Unicode-таблицу.
                for _enc in ("unicode", "adobe_custom", "apple_unicode"):
                    try:
                        face.select_charmap(getattr(freetype, f"FT_ENCODING_{_enc.upper()}"))
                        break
                    except Exception:
                        continue
                _need = [ord(c) for c in
                         "АБВГДЕЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯабвгдежзийклмнопрстуфхцчшщъыьэюя"]
                ok = all(face.get_char_index(cp) != 0 for cp in _need)
            except Exception:
                ok = False
        self._cyr_cache[font_file] = ok
        return ok

    def get(self, role: str, font_file: str = "", size_delta: int = 0,
            bold: bool = False, italic: bool = False) -> pygame.font.Font:
        base = _BASE_SIZES.get(role, 14)
        size = max(8, base + size_delta)
        path = self._files.get(font_file) if font_file else None
        key = (str(path) if path else "", size, bold, italic)
        if key not in self._cache:
            if path:
                font = pygame.font.Font(str(path), size)
            else:
                font = pygame.font.SysFont("consolas", size)
            font.set_bold(bold)
            font.set_italic(italic)
            self._cache[key] = font
        return self._cache[key]
