"""
Назначение: Экран настроек игры (пока только переключатель контента)
Зависимости: pygame, app.core.config, app.core.content_policy
Основные сущности: SettingsScreen

path: /frontend/settings_screen.py
"""

import sys
from pathlib import Path
from typing import Optional

import pygame
import yaml

# Добавляем корень проекта в sys.path для импорта backend.app
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from app.core.config import settings
from app.core.content_policy import save_content_policy

# === Минимальная цветовая схема (как в game_menu.py) ===
_MENU_COLORS = {
    "bg_dark": (18, 18, 23),
    "text": (220, 220, 220),
    "text_dim": (140, 140, 140),
    "btn_primary": (70, 100, 130),
    "btn_primary_hover": (90, 130, 160),
    "btn_secondary": (80, 80, 90),
    "btn_secondary_hover": (100, 100, 110),
    "btn_danger": (150, 60, 60),
    "btn_danger_hover": (180, 80, 80),
    "border": (60, 60, 70),
    "accent_blue": (70, 170, 255),
    "accent_green": (80, 200, 120),
    "accent_yellow": (220, 180, 60),
}

class _SettingsButton:
    def __init__(self, x, y, w, h, text, color, color_hover, on_click, is_selected=False, tooltip=""):
        self.rect = pygame.Rect(x, y, w, h)
        self.text = text
        self.color = color
        self.color_hover = color_hover
        self.on_click = on_click
        self.hovered = False
        self.is_selected = is_selected
        self.tooltip = tooltip

    def handle_event(self, event):
        if event.type == pygame.MOUSEMOTION:
            self.hovered = self.rect.collidepoint(event.pos)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.rect.collidepoint(event.pos):
                self.on_click()
                return True
        return False

    def draw(self, screen, font):
        color = self.color_hover if self.hovered else self.color
        pygame.draw.rect(screen, color, self.rect, border_radius=6)
        
        border_color = _MENU_COLORS["accent_blue"] if self.is_selected else _MENU_COLORS["border"]
        border_width = 2 if self.is_selected else 1
        pygame.draw.rect(screen, border_color, self.rect, border_width, border_radius=6)
        
        text_surf = font.render(self.text, True, _MENU_COLORS["text"])
        text_rect = text_surf.get_rect(center=self.rect.center)
        screen.blit(text_surf, text_rect)

class SettingsScreen:
    """Экран настроек. Владеет своим циклом отрисовки."""
    
    def __init__(self, screen: pygame.Surface, clock: pygame.time.Clock):
        self.screen = screen
        self.clock = clock
        self._result: Optional[str] = None  # "back" or None
        
        self.font_title = pygame.font.SysFont("consolas", 36, bold=True)
        self.font_button = pygame.font.SysFont("consolas", 20, bold=True)
        self.font_small = pygame.font.SysFont("consolas", 14)
        
        self.current_preset = self._get_current_preset()
        self.buttons = self._build_buttons()

    def _get_current_preset(self) -> str:
        path = settings.user_settings_path
        if not path.exists():
            return "explicit"
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            return data.get("content", {}).get("preset", "explicit")
        except Exception:
            return "explicit"

    def _set_preset(self, preset: str):
        save_content_policy(settings, preset)
        self.current_preset = preset
        self.buttons = self._build_buttons() # Перестраиваем кнопки для обновления выделения

    def _build_buttons(self):
        screen_w, screen_h = self.screen.get_size()
        btn_w, btn_h = 400, 50
        gap = 20
        start_y = screen_h // 2 - (btn_h * 4 + gap * 3) // 2
        x = screen_w // 2 - btn_w // 2
        
        return [
            _SettingsButton(x, start_y, btn_w, btn_h, "Семейный (0+)",
                            _MENU_COLORS["btn_secondary"], _MENU_COLORS["btn_secondary_hover"],
                            lambda: self._set_preset("off"), self.current_preset == "off",
                            tooltip="Никакого мата, секса, детального насилия. Подходит для чувствительной аудитории."),
            _SettingsButton(x, start_y + btn_h + gap, btn_w, btn_h, "Подростковый (16+)",
                            _MENU_COLORS["btn_secondary"], _MENU_COLORS["btn_secondary_hover"],
                            lambda: self._set_preset("moderate"), self.current_preset == "moderate",
                            tooltip="Лёгкая ругань, намёки на секс, физиологичное насилие без садизма."),
            _SettingsButton(x, start_y + 2*(btn_h + gap), btn_w, btn_h, "Взрослый (18+)",
                            _MENU_COLORS["btn_secondary"], _MENU_COLORS["btn_secondary_hover"],
                            lambda: self._set_preset("explicit"), self.current_preset == "explicit",
                            tooltip="Полный 18+ контент: мат, explicit-секс, детальная жестокость, табу-практики."),
            _SettingsButton(x, start_y + 3*(btn_h + gap), btn_w, btn_h, "Назад",
                            _MENU_COLORS["btn_danger"], _MENU_COLORS["btn_danger_hover"],
                            lambda: setattr(self, "_result", "back")),
        ]

    def run(self):
        self._result = None
        while self._result is None:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    sys.exit()
                elif event.type == pygame.VIDEORESIZE:
                    self.screen = pygame.display.set_mode((event.w, event.h), pygame.RESIZABLE)
                    self.buttons = self._build_buttons()
                else:
                    for btn in self.buttons:
                        btn.handle_event(event)
                        
            self.screen.fill(_MENU_COLORS["bg_dark"])
            
            title_surf = self.font_title.render("Настройки Контента", True, _MENU_COLORS["text"])
            title_rect = title_surf.get_rect(center=(self.screen.get_width() // 2, 100))
            self.screen.blit(title_surf, title_rect)
            
            desc = "Выберите уровень разрешённого контента. Это повлияет на речь NPC и описание сцены."
            desc_surf = self.font_small.render(desc, True, _MENU_COLORS["text_dim"])
            desc_rect = desc_surf.get_rect(center=(self.screen.get_width() // 2, 150))
            self.screen.blit(desc_surf, desc_rect)
            
            for btn in self.buttons:
                btn.draw(self.screen, self.font_button)
            
            # Отрисовка тултипа для наведённой кнопки
            hovered_btn = next((b for b in self.buttons if b.hovered and b.tooltip), None)
            if hovered_btn:
                # Фон для тултипа
                tip_surf = self.font_small.render(hovered_btn.tooltip, True, _MENU_COLORS["text"])
                tip_rect = tip_surf.get_rect(center=(self.screen.get_width() // 2, self.screen.get_height() - 60))
                
                # Рамка
                pad = 10
                bg_rect = tip_rect.inflate(pad * 2, pad)
                pygame.draw.rect(self.screen, _MENU_COLORS["btn_secondary"], bg_rect, border_radius=4)
                pygame.draw.rect(self.screen, _MENU_COLORS["border"], bg_rect, 1, border_radius=4)
                self.screen.blit(tip_surf, tip_rect)
                
            pygame.display.flip()
            self.clock.tick(30)
