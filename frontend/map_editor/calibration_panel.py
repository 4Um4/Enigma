"""
map_editor/calibration_panel.py
Панель калибровки психики NPC (M0)
"""

import pygame
from typing import Callable, Dict, Optional

from ui_components import Button, COLORS, Slider


class CalibrationPanel:
    """Модальная панель для редактирования psyche и drives NPC"""

    def __init__(
        self,
        screen: pygame.Surface,
        npc_id: str,
        npc_name: str,
        psyche: Dict,
        drives: Dict,
    ):
        self.screen = screen
        self.npc_id = npc_id
        self.npc_name = npc_name
        self.active = True

        self.width = 500
        self.height = 480
        screen_w, screen_h = screen.get_size()
        self.rect = pygame.Rect(
            (screen_w - self.width) // 2,
            (screen_h - self.height) // 2,
            self.width,
            self.height,
        )

        self.title = f"Калибровка психики: {self.npc_name}"

        # Слайдеры
        self.sliders = []
        y = self.rect.y + 60

        # Psyche
        self.sliders.append(
            Slider(
                self.rect.x + 20,
                y,
                460,
                20,
                0,
                100,
                psyche.get("willpower", 50),
                "Воля (willpower)",
                is_float=False,
            )
        )
        y += 50
        self.sliders.append(
            Slider(
                self.rect.x + 20,
                y,
                460,
                20,
                0,
                100,
                psyche.get("breakpoint", 65),
                "Порог слома (breakpoint)",
                is_float=False,
            )
        )
        y += 50
        self.sliders.append(
            Slider(
                self.rect.x + 20,
                y,
                460,
                20,
                0.0,
                1.0,
                psyche.get("loyalty_true", 0.0),
                "Истинная лояльность (loyalty_true)",
            )
        )
        y += 60

        # Drives
        self.sliders.append(
            Slider(
                self.rect.x + 20,
                y,
                460,
                20,
                0.0,
                1.0,
                drives.get("control", 0.3),
                "Контроль (control)",
            )
        )
        y += 50
        self.sliders.append(
            Slider(
                self.rect.x + 20,
                y,
                460,
                20,
                0.0,
                1.0,
                drives.get("significance", 0.3),
                "Значимость (significance)",
            )
        )
        y += 50
        self.sliders.append(
            Slider(
                self.rect.x + 20,
                y,
                460,
                20,
                0.0,
                1.0,
                drives.get("fear", 0.3),
                "Страх (fear)",
            )
        )
        y += 50
        self.sliders.append(
            Slider(
                self.rect.x + 20,
                y,
                460,
                20,
                0.0,
                1.0,
                drives.get("desire", 0.3),
                "Желание (desire)",
            )
        )

        # Кнопки
        self.btn_save = Button(
            self.rect.x + 250, self.rect.y + 420, 100, 35, "Сохранить"
        )
        self.btn_cancel = Button(
            self.rect.x + 360, self.rect.y + 420, 100, 35, "Отмена"
        )

        self.on_save: Optional[Callable[[Dict, Dict], None]] = None

    def handle_event(self, event: pygame.event.Event) -> None:
        if not self.active:
            return

        for slider in self.sliders:
            slider.handle_event(event)

        if event.type == pygame.MOUSEBUTTONDOWN:
            if self.btn_save.rect.collidepoint(event.pos):
                self._save()
            elif self.btn_cancel.rect.collidepoint(event.pos):
                self.active = False

    def _save(self) -> None:
        if self.on_save:
            psyche = {
                "willpower": self.sliders[0].value,
                "breakpoint": self.sliders[1].value,
                "loyalty_true": self.sliders[2].value,
            }
            drives = {
                "control": self.sliders[3].value,
                "significance": self.sliders[4].value,
                "fear": self.sliders[5].value,
                "desire": self.sliders[6].value,
            }
            self.on_save(psyche, drives)
        self.active = False

    def draw(self, font: pygame.font.Font, small_font: pygame.font.Font) -> None:
        if not self.active:
            return

        # Затемнение фона
        overlay = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 100))
        self.screen.blit(overlay, (0, 0))

        # Панель
        pygame.draw.rect(self.screen, COLORS["bg_panel"], self.rect, border_radius=8)
        pygame.draw.rect(self.screen, COLORS["border"], self.rect, 2, border_radius=8)

        # Заголовок
        title_surf = font.render(self.title, True, COLORS["text_highlight"])
        self.screen.blit(title_surf, (self.rect.x + 20, self.rect.y + 15))

        # Слайдеры
        for slider in self.sliders:
            slider.draw(self.screen, small_font)

        # Кнопки
        self.btn_save.draw(self.screen, small_font)
        self.btn_cancel.draw(self.screen, small_font)