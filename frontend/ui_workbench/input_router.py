"""
path: /frontend/ui_workbench/input_router.py
Назначение: Диспетчер ввода. Единая точка решения «окно или сцена».
Зависимости: pygame, ui_workbench.registry
Основные сущности: InputDispatcher, RouteResult
"""
from dataclasses import dataclass
from typing import Dict, Optional

import pygame

from ui_workbench.registry import WindowRegistry


@dataclass(frozen=True)
class RouteResult:
    consumed: bool = False
    window_id: Optional[str] = None


class InputDispatcher:
    """Маршрутизирует события по декларативным InputBinding манифестов."""

    def __init__(self, registry: WindowRegistry) -> None:
        self._registry = registry
        self._hotkeys: Dict[int, str] = {}
        self._title_rects: Dict[str, pygame.Rect] = {}
        # Ревизия хоткеев: конфликт = баг конфига, fail-fast.
        for wid in registry.all_ids():
            hk = registry.manifest(wid).binding.hotkey
            if hk is not None:
                if hk in self._hotkeys:
                    raise ValueError(
                        f"InputDispatcher: hotkey-конфликт '{self._hotkeys[hk]}' и '{wid}'"
                    )
                self._hotkeys[hk] = wid

    def route(self, event) -> RouteResult:
        """Только hotkeys. Клик-логика заголовков уехала в WorkbenchScreen:
        клик-vs-drag различается порогом движения (клик = toggle, движение =
        drag) — это состояние между событиями, диспетчеру оно не принадлежит."""
        if event.type == pygame.KEYDOWN and event.key in self._hotkeys:
            wid = self._hotkeys[event.key]
            self._registry.toggle(wid)
            return RouteResult(consumed=True, window_id=wid)
        return RouteResult()

    def bind_title_rect(self, window_id: str, rect) -> None:
        """Рендерер отчитывается о геометрии заголовка (SSOT геометрии — рендер)."""
        self._title_rects[window_id] = rect
