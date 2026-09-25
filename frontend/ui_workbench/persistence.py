"""
path: /frontend/ui_workbench/persistence.py
Назначение: Versioned-персист layouts. Уроки S217 (валидация целостности
файлов) и миграций visual_casting ("_version" с первого дня).
Зависимости: json, pathlib
Основные сущности: WorkbenchPersistence
"""
import json
from pathlib import Path
from typing import Dict

_SCHEMA_VERSION = 1


class WorkbenchPersistence:
    """Загрузка/сохранение window_layout.json. Дефолты легальны при первом
    запуске; битый файл = громкая ошибка (тихий fallback = потеря раскладки)."""

    def __init__(self, layout_path: Path) -> None:
        self._path = layout_path

    def load_window_states(self) -> Dict[str, dict]:
        """{window_id: {"state": ..., "free_rect": [x,y,w,h] | None}}.
        v3a: free_rect — пользовательская геометрия из SnapEngine."""
        if not self._path.exists():
            return {}
        try:
            data = json.loads(self._path.read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError as e:
            raise ValueError(f"WorkbenchPersistence: битый window_layout.json: {e}")
        if data.get("_version") != _SCHEMA_VERSION:
            raise ValueError(
                f"WorkbenchPersistence: версия схемы {data.get('_version')} ≠ {_SCHEMA_VERSION} "
                f"(миграция required — см. визуальный кастинг прецедент)"
            )
        return data.get("window_states", {})

    def save_window_states(self, states: Dict[str, dict]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"_version": _SCHEMA_VERSION, "window_states": states}
        self._path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
