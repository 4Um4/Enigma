"""path: /frontend/map_editor/assets/resource_formats.py

ME-2.1-H-2: Единый источник истины для поддерживаемых форматов ресурсов.

Контракт Master (уточнение 2): whitelist используется и AssetStore, и
ResourceValidator. Не допускается двух независимо редактируемых списков.

Этот модуль — единственное место, где определены:
- SUPPORTED_RESOURCE_FORMATS — множество расширений (с точкой, lowercase).
- MAGIC_BYTES — соответствие расширения сигнатуре содержимого (L3).
- normalize_format() — нормализация расширения в формат (без точки, lowercase).

Зависимости: только стандартная библиотека. НЕ импортирует pygame, asset_store,
resource_validator (иначе цикл).

Основные сущности: SUPPORTED_RESOURCE_FORMATS, MAGIC_BYTES, normalize_format.
"""

from __future__ import annotations

__all__ = [
    "MAGIC_BYTES",
    "SUPPORTED_RESOURCE_FORMATS",
    "is_supported_format",
    "normalize_format",
]


# Whitelist поддерживаемых форматов (расширения с точкой, lowercase).
# Расширение списка — отдельное осознанное изменение с тестами (G2 Master).
# Никакого автоматического принятия любого файла из resources/.
SUPPORTED_RESOURCE_FORMATS: frozenset[str] = frozenset({".png", ".jpg", ".jpeg"})

# Magic bytes для L3 проверки (соответствие расширения сигнатуре содержимого).
# Ключ — расширение с точкой (lowercase). Значение — префикс байтов файла.
# PNG: \x89PNG\r\n\x1a\n (8 байт)
# JPEG: \xff\xd8\xff (3 байта, SOI + маркер)
MAGIC_BYTES: dict[str, bytes] = {
    ".png": b"\x89PNG\r\n\x1a\n",
    ".jpg": b"\xff\xd8\xff",
    ".jpeg": b"\xff\xd8\xff",
}


def normalize_format(suffix: str) -> str:
    """Нормализовать расширение в формат (без точки, lowercase).

    Args:
        suffix: расширение файла (с точкой или без). ".PNG", "png", ".jpg".

    Returns:
        Нормализованный формат: "png", "jpg", "jpeg" (без точки, lowercase).
        Пустая строка если suffix пустой.

    Examples:
        >>> normalize_format(".PNG")
        'png'
        >>> normalize_format("jpg")
        'jpg'
        >>> normalize_format(".jpeg")
        'jpeg'
        >>> normalize_format("")
        ''
    """
    if not suffix:
        return ""
    s = suffix.lower()
    if not s.startswith("."):
        s = "." + s
    return s[1:]


def is_supported_format(suffix: str) -> bool:
    """Проверить, входит ли расширение в whitelist поддерживаемых форматов.

    Args:
        suffix: расширение файла (с точкой). ".png", ".jpg", ".gif".

    Returns:
        True если расширение поддерживается (PNG/JPG/JPEG, case-insensitive).
    """
    if not suffix:
        return False
    return suffix.lower() in SUPPORTED_RESOURCE_FORMATS
