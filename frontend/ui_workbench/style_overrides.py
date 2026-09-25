"""
path: /project/frontend/ui_workbench/style_overrides.py
Назначение: Per-window style-оверрайды поверх токенов темы (Style-редактор
    F12, очередь №3). Единственный владелец чтения/записи
    style_overrides.json (версионированный, паттерн persistence.py).
Зависимости: json, pathlib
Основные сущности: StyleOverrides
"""
import json
from pathlib import Path
from typing import Dict, Tuple

Color = Tuple[int, int, int]
_VERSION = 1
_K_VERSION = "_version"
_K_OVERRIDES = "overrides"
# Ключ "*" = глобальные оверрайды (применяются ко всем окнам).
_GLOBAL = "*"

# Редактируемые характеристики v1 (токены — из theme._DEFAULT_TOKENS;
# шрифт — имена файлов из assets/fonts; размер — px).
EDITABLE_TOKENS = ("surface_panel", "surface_title", "border",
                   "border_accent", "text_primary", "text_muted", "accent")


class StyleOverrides:
    """Читает/пишет style_overrides.json; резолвит цвет для (wid, token).
    Не знает о pygame и рендере — чистые данные."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._data: Dict[str, Dict[str, object]] = {}
        self.load()

    def load(self) -> None:
        if not self._path.exists():
            self._data = {}
            return
        data = json.loads(self._path.read_text(encoding="utf-8-sig"))
        if data.get(_K_VERSION) != _VERSION:
            raise ValueError(f"StyleOverrides: несовместимая версия {data.get(_K_VERSION)} в {self._path}")
        self._data = data.get(_K_OVERRIDES, {})

    def save(self) -> None:
        payload = {_K_VERSION: _VERSION, _K_OVERRIDES: self._data}
        self._path.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                              encoding="utf-8")

    # ── Цвета ──
    def resolve_color(self, wid: str, token: str, base: Color) -> Color:
        for key in (wid, _GLOBAL):
            ov = self._data.get(key, {})
            v = ov.get(token)
            if isinstance(v, (list, tuple)) and len(v) == 3:
                return tuple(int(c) for c in v)
        return base

    def set_color(self, wid: str, token: str, value: Color) -> None:
        self._data.setdefault(wid, {})[token] = list(value)

    def clear(self, wid: str) -> None:
        self._data.pop(wid, None)

    def has_overrides(self, wid: str) -> bool:
        return bool(self._data.get(wid))

    # ── Шрифт ──
    def resolve_font(self, wid: str) -> Tuple[str, int]:
        """(font_path|"", size); "" = системный SysFont."""
        ov = self._data.get(wid, {})
        return (str(ov.get("font_file", "")), int(ov.get("font_size", 0) or 0))

    def set_font(self, wid: str, font_file: str, size: int) -> None:
        ov = self._data.setdefault(wid, {})
        if font_file:
            ov["font_file"] = font_file
        else:
            ov.pop("font_file", None)
        if size:
            ov["font_size"] = int(size)

    def keys(self) -> list:
        return list(self._data.keys())
