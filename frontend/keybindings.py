"""
path: /frontend/keybindings.py
Назначение: Управление клавишами управления (Keybinds). Загрузка, сохранение, дефолты.
Зависимости: json, pathlib
Основные сущности: DEFAULT_KEYBINDS, load_keybinds(), save_keybinds()
"""
import json
from pathlib import Path

# Дефолтные клавиши (строковые имена pygame.keys)
DEFAULT_KEYBINDS = {
    "move_up": "w",
    "move_down": "s",
    "move_left": "a",
    "move_right": "d",
    "interact": "e",
    "open_journal": "j",
    "dialogue_open": "tab",      # Вызов диалогового окна ввода (раньше был захардкожен)
    "pause": "escape",
    "console_enter": "return",
    "console_escape": "escape"
}

_KEYBINDS_FILE = Path(__file__).parent / "keybinds.json"

def load_keybinds() -> dict:
    """Загружает клавиши из файла, или возвращает дефолтные."""
    if _KEYBINDS_FILE.exists():
        try:
            with open(_KEYBINDS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return DEFAULT_KEYBINDS.copy()

def save_keybinds(keybinds: dict) -> None:
    """Сохраняет клавиши в файл."""
    try:
        with open(_KEYBINDS_FILE, "w", encoding="utf-8") as f:
            json.dump(keybinds, f, indent=4)
    except Exception as e:
        print(f"Failed to save keybinds: {e}")

def get_key(keybinds: dict, action: str) -> int:
    """Возвращает pygame.K_ код клавиши для действия.

    FIX(имена): конвенция pygame несимметрична — буквы lowercase (K_w),
    спец-клавиши UPPERCASE (K_TAB, K_ESCAPE, K_RETURN). pygame.key.name()
    и дефолты хранят lowercase ("tab") → старый одиночный getattr молча
    резолвил ВСЕ спец-клавиши в K_UNKNOWN (dialogue_open/pause/console_enter
    были мертвы и до, и после ребинда). Двухкандидатный lookup закрывает
    оба семейства без карты-исключений.
    """
    import pygame
    key_name = keybinds.get(action, DEFAULT_KEYBINDS.get(action, ""))
    if not key_name:
        return pygame.K_UNKNOWN
    for _cand in (f"K_{key_name}", f"K_{key_name.upper()}"):
        if hasattr(pygame, _cand):
            return getattr(pygame, _cand)
    print(f"[KEYBINDINGS] неизвестная клавиша '{key_name}' для '{action}'")
    return pygame.K_UNKNOWN