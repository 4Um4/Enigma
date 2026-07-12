from typing import Any, Dict, List, Optional
# backend/app/services/verbalization/prompt_loader.py
"""
Загрузчик системных промптов.

Единственная живая функция: load_system_prompt — для dm_agent.py
"""

from pathlib import Path

from app.core.config import settings

# Кэш загруженных промптов
_prompt_cache: dict[str, str] = {}


def load_system_prompt(filename: str, use_cache: bool = True) -> str:
    """
    Загружает системный промпт из файла (текстовый).

    Args:
        filename: Путь к файлу промпта (абсолютный или относительный)
        use_cache: Использовать кэширование

    Returns:
        Содержимое файла промпта
    """
    if use_cache and filename in _prompt_cache:
        return _prompt_cache[filename]

    # Абсолютный или относительный путь
    path = Path(filename)
    if not path.is_absolute():
        path = Path(settings.BASE_DIR) / filename

    if not path.exists():
        raise FileNotFoundError(f"Файл промпта не найден: {path}")

    with open(path, "r", encoding="utf-8") as f:
        content = f.read().strip()

    if use_cache:
        _prompt_cache[filename] = content

    return content
