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
    "open_board": "b",           # Phase 4 Investigation Board (Workbench)
    "dialogue_open": "tab",      # Вызов диалогового окна ввода (раньше был захардкожен)
    "pause": "escape",
    "console_enter": "return",
    "console_escape": "escape",
    # AUDIT #12: ранее дёргались литералами клавиш мимо биндов
    "toggle_inventory": "i",
    "skip_time_short": "1",
    "skip_time_long": "2",
    # D6: миграция прямых K_*-литералов из event-loop (конвенция AUDIT #12)
    "skip_time_500": "3",
    "skip_time_2000": "4",
    "observations": "backquote",
}

_KEYBINDS_FILE = Path(__file__).parent / "keybinds.json"

_KEYBINDS_CACHE: dict | None = None  # D6: мемоизация — event-loop звал чтение JSON на каждый KEYDOWN


def load_keybinds() -> dict:
    """Загружает клавиши из файла, или возвращает дефолтные.

    D6: мемоизировано — 7 call-site'ов в event-loop game_screen читали
    keybinds.json с диска на КАЖДОЕ нажатие клавиши. Инвалидация —
    только в save_keybinds (единственный писатель). Возврат — копия:
    потребитель-мутация не протекает в кэш."""
    global _KEYBINDS_CACHE
    if _KEYBINDS_CACHE is not None:
        return _KEYBINDS_CACHE.copy()
    if _KEYBINDS_FILE.exists():
        try:
            with open(_KEYBINDS_FILE, "r", encoding="utf-8") as f:
                _loaded = json.load(f)
            _KEYBINDS_CACHE = _loaded
            return _loaded.copy()
        except Exception:
            pass
    _KEYBINDS_CACHE = DEFAULT_KEYBINDS.copy()
    return DEFAULT_KEYBINDS.copy()

def save_keybinds(keybinds: dict) -> None:
    """Сохраняет клавиши в файл. D6: инвалидация кэша — ребинд сразу
    жив для всех потребителей (save — единственный писатель)."""
    global _KEYBINDS_CACHE
    try:
        with open(_KEYBINDS_FILE, "w", encoding="utf-8") as f:
            json.dump(keybinds, f, indent=4)
        _KEYBINDS_CACHE = keybinds.copy()
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
