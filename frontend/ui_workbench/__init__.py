"""
path: /frontend/ui_workbench/__init__.py
Назначение: UI Workbench ENIGMA — платформа пользовательского интерфейса.
Публичные экспорты. Пакет живёт ТОЛЬКО в frontend/ (INV-FRONTEND-ISOLATION).
Зависимости: pygame, json, pathlib
Основные сущности: WindowRegistry, Theme, InputDispatcher
"""
from ui_workbench.input_router import InputDispatcher
from ui_workbench.layout import AnchoredRect
from ui_workbench.manifests import InputBinding, WindowManifest, WindowState
from ui_workbench.persistence import WorkbenchPersistence
from ui_workbench.registry import WindowRegistry
from ui_workbench.theme import Theme, ThemeLoader

__all__ = [
    "WindowManifest", "WindowState", "InputBinding",
    "WindowRegistry", "Theme", "ThemeLoader",
    "AnchoredRect", "InputDispatcher", "WorkbenchPersistence",
]
