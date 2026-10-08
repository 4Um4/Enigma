"""
Файл: frontend/map_editor/chronicle/editor_screen.py
Назначение: полноэкранный режим F7 (CCH-3). Обёртка-делегат: держит инстанс
            ChronicleApi поверх Map Editor-сессии; вылет по ESC возвращает
            MODE_WORLD (паттерн MODE_LAB).
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
from tools.constants import MODE_WORLD  # noqa: E402


class ChronicleScreen:
    def __init__(self, core) -> None:
        self._core = core
        self._api = ChronicleApi()
        self._npcs = ["maid_lusya", "tavern_keeper_tornin", "guard_borko", "blacksmith_orm", "thief_shadow", "merchant_goran"]
        self._idx = 0
        self._doc = None
        self._items = []
        self._status = "F7: редактор хроник. ESC — выход в карту."
        self._reload()

    def _reload(self) -> None:
        campaign = getattr(self._core, "campaign_id", "silver_wolf") or "silver_wolf"
        self._doc = self._api.get_draft(campaign, self._npcs[self._idx])
        self._items = []
        self._status = f"{self._npcs[self._idx]}: {'draft загружен' if self._doc else 'черновика нет'}"

    def enter(self) -> None:
        """Вход в режим (паттерн lab_screen.enter())."""

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_ESCAPE, pygame.K_F7):
                self._core.mode = MODE_WORLD
                return
            if event.key == pygame.K_DOWN:
                self._idx = (self._idx + 1) % len(self._npcs)
                self._reload()
            elif event.key == pygame.K_UP:
                self._idx = (self._idx - 1) % len(self._npcs)
                self._reload()

    def update(self) -> None:
        pass  # MVP: без анимаций

    def draw(self, surface) -> None:
        surface.fill((18, 18, 23))
        font = pygame.font.SysFont("consolas", 16)
        big = pygame.font.SysFont("consolas", 22, bold=True)
        surface.blit(big.render("ХРОНИКИ (F7)", True, (180, 160, 90)), (20, 40))
        for i, npc in enumerate(self._npcs):
            color = (180, 160, 90) if i == self._idx else (220, 220, 220)
            surface.blit(font.render(npc, True, color), (20, 80 + i * 24))
        if self._doc:
            for j, e in enumerate((self._doc.get("entries") or [])[:30]):
                age = e.get("historical_age")
                line = f"[{age if age is not None else '?'}] {e.get('kind','')}: {str(e.get('payload', {}).get('summary',''))[:64]}"
                surface.blit(font.render(line, True, (220, 220, 220)), (260, 80 + j * 20))
        surface.blit(font.render(self._status[:120], True, (220, 220, 220)), (20, 760))
