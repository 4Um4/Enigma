"""
path: /frontend/ui_workbench/theme.py
Назначение: Токены темы. Цвета окон ссылаются на токены, не на RGB-литералы.
Зависимости: json, pathlib, pygame
Основные сущности: Theme, ThemeLoader
"""
import json
from pathlib import Path
from typing import Dict, Tuple

Color = Tuple[int, int, int]

# Дефолтные токены = первая тема ENIGMA (значения из текущего стиля журнала/HUD).
# Профили тем — папка presets/ рядом с theme.json (Шаг Style-редактора).
_DEFAULT_TOKENS: Dict[str, Color] = {
    "surface_panel": (20, 20, 30),
    "surface_title": (30, 30, 45),
    "border": (70, 70, 95),
    "border_accent": (200, 170, 90),
    "text_primary": (220, 220, 225),
    "text_muted": (140, 140, 150),
    "accent": (230, 190, 90),
    "danger": (196, 84, 84),
}


class Theme:
    """Иммутабельный срез токенов. Окна читают theme.token("border") —
    смена профиля перекрашивает все окна без правки их кода."""

    def __init__(self, tokens: Dict[str, Color]) -> None:
        self._tokens = dict(tokens)

    def token(self, name: str) -> Color:
        if name not in self._tokens:
            raise KeyError(f"Theme: неизвестный токен '{name}' (L0: fail-fast, не тихий серый)")
        return self._tokens[name]


class ThemeLoader:
    """Загрузчик темы. Отсутствие файла = дефолт (легальная первая загрузка);
    битый файл = громкая ошибка (молчаливый fallback = ложь темы, L4)."""

    def __init__(self, theme_path: Path) -> None:
        self._path = theme_path

    def load(self) -> Theme:
        if not self._path.exists():
            return Theme(_DEFAULT_TOKENS)
        try:
            data = json.loads(self._path.read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError as e:
            raise ValueError(f"ThemeLoader: битый theme.json ({self._path}): {e}")
        tokens = dict(_DEFAULT_TOKENS)
        tokens.update({k: tuple(v) for k, v in data.get("tokens", {}).items()})
        return Theme(tokens)
