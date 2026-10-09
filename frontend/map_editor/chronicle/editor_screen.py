"""
path: /frontend/map_editor/chronicle/editor_screen.py
Назначение: полноэкранный режим F7 — ТОНКАЯ обёртка над единым ядром
            chronicle_editor.chronicle_app.ChronicleEditorCore (вердикт
            «один редактор — два входа»; кода интерфейса один экземпляр).
            Кампания — открытая в Map Editor (cm.campaign_path.name);
            ESC/F7 — выход в MODE_WORLD (паттерн MODE_LAB).
Зависимости: pygame, chronicle_editor.{api,chronicle_app}, tools.constants
Основные сущности: ChronicleScreen
"""
from __future__ import annotations

import sys
from pathlib import Path

import pygame

# Двойной корень (урок S337): файл живёт в map_editor/ (отсюда tools.*),
# но тянет chronicle_editor из frontend/. Пути от __file__, не от CWD.
_MAP_EDITOR = Path(__file__).resolve().parents[1]
_FRONTEND = Path(__file__).resolve().parents[2]
for _p in (str(_FRONTEND), str(_MAP_EDITOR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from chronicle_editor.api import ChronicleApi  # noqa: E402
from chronicle_editor.chronicle_app import ChronicleEditorCore  # noqa: E402
from tools.constants import MODE_WORLD  # noqa: E402


class ChronicleScreen:
    def __init__(self, core) -> None:
        self._core = core
        self._editor = ChronicleEditorCore(ChronicleApi(), self._campaign_of(core))

    @staticmethod
    def _campaign_of(core) -> str:
        """Кампания — из открытой сессии редактора карт (cm.campaign_path.name).
        Поправка S345-хвост: прежний getattr(core,'campaign_id') атрибута не
        находил и молча давал silver_wolf даже на Open_road. Нет сессии →
        дефолт Мастера (инструмент отображения, статус виден на экране)."""
        _cm = getattr(core, "cm", None)
        if _cm is None:
            return "silver_wolf"
        _cp = getattr(_cm, "campaign_path", None)
        if _cp is None:
            return "silver_wolf"
        return _cp.name

    def enter(self) -> None:
        """Вход в режим (паттерн lab_screen.enter())."""

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.KEYDOWN and event.key == pygame.K_F7:
            # F7 — переключатель: повторное нажатие возвращает в карту.
            self._core.mode = MODE_WORLD
            return
        self._editor.handle_event(event)
        if self._editor.exit_requested:
            self._editor.exit_requested = False
            self._core.mode = MODE_WORLD

    def update(self) -> None:
        pass

    def draw(self, surface) -> None:
        self._editor.draw(surface)
