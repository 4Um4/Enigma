"""
Назначение: Главное меню игры — полностью изолировано от map_editor, содержит собственные минимальные UI-примитивы
Зависимости: pygame (только стандартная библиотека + pygame)
Основные сущности: MenuAction, GameMenu, _MenuButton

path: /frontend/game_menu.py

Главное меню игры — полностью самодостаточно, не зависит от map_editor.
Содержит собственные минимальные UI-примитивы (цвета, кнопка).
"""

from enum import Enum, auto
from typing import Callable, Optional

import pygame
from i18n import t


class MenuAction(Enum):
    """Действия, которые может выбрать игрок в меню"""

    NEW_GAME = auto()
    CONTINUE = auto()
    EDITOR = auto()
    SETTINGS = auto()
    EXIT = auto()


# === Минимальная цветовая схема меню ===
# Целостность с общим стилем проекта, но без зависимости от map_editor/ui_components.py
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
}


class _MenuButton:
    """Минимальная кнопка для меню — только то, что нужно, без лишней абстракции"""

    def __init__(
        self,
        x: int,
        y: int,
        width: int,
        height: int,
        text: str,
        color: tuple,
        color_hover: tuple,
        on_click: Callable[[], None],
    ):
        self.rect = pygame.Rect(x, y, width, height)
        self.text = text
        self.color = color
        self.color_hover = color_hover
        self.on_click = on_click
        self.hovered = False

    def handle_event(self, event: pygame.event.Event) -> bool:
        if event.type == pygame.MOUSEMOTION:
            self.hovered = self.rect.collidepoint(event.pos)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.rect.collidepoint(event.pos):
                self.on_click()
                return True
        return False

    def draw(self, screen: pygame.Surface, font: pygame.font.Font) -> None:
        color = self.color_hover if self.hovered else self.color
        pygame.draw.rect(screen, color, self.rect, border_radius=6)
        pygame.draw.rect(screen, _MENU_COLORS["border"], self.rect, 1, border_radius=6)

        text_surf = font.render(self.text, True, _MENU_COLORS["text"])
        text_rect = text_surf.get_rect(center=self.rect.center)
        screen.blit(text_surf, text_rect)


class GameMenu:
    """Главное меню игры — владеет своим циклом отрисовки и возвращает выбранное действие"""

    def __init__(self, screen: pygame.Surface, clock: pygame.time.Clock):
        self.screen = screen
        self.clock = clock
        self._result: Optional[MenuAction] = None

        # Шрифты
        self.font_title = pygame.font.SysFont("consolas", 48, bold=True)
        self.font_subtitle = pygame.font.SysFont("consolas", 18)
        self.font_button = pygame.font.SysFont("consolas", 20, bold=True)
        self.font_small = pygame.font.SysFont("consolas", 14)

        # ADR-O-146: Фоновое изображение + анимация дыма
        self._bg_image = self._load_background()
        self._smoke_emitters: list = []
        self._init_smoke()

        self._buttons: list[_MenuButton] = []
        self._build_buttons()

    def _load_background(self) -> Optional[pygame.Surface]:
        """Загружает и масштабирует фоновое изображение меню."""
        try:
            from pathlib import Path

            # Приоритет: JPG (оптимизированный) > PNG (оригинал)
            bg_path = Path(__file__).parent / "menu_bg.jpg"
            if not bg_path.exists():
                bg_path = (
                    Path(__file__).parent / "map_editor" / "pixels" / "game_menu.png"
                )
            if not bg_path.exists():
                return None
            img = pygame.image.load(str(bg_path))
            return img.convert()  # Оптимизация: без alpha для скорости
        except Exception:
            return None

    def _init_smoke(self) -> None:
        """Инициализирует эммитеры дыма (трубы на фоне)."""
        try:
            from menu_effects import SmokeEmitter

            # Координаты труб в нормализованном виде (0-1)
            # Точные позиции подберём по реальному изображению
            self._smoke_emitters = [
                SmokeEmitter(0.22, 0.18, rate=6.0),  # Труба таверны
                SmokeEmitter(0.78, 0.25, rate=4.0),  # Дальняя труба
            ]
        except Exception:
            self._smoke_emitters = []

    def _build_buttons(self) -> None:
        """Пересчитывает позиции кнопок при изменении размера окна"""
        self._buttons.clear()

        w, h = self.screen.get_size()
        btn_w = 280
        btn_h = 50
        gap = 16
        total_h = 5 * btn_h + 4 * gap
        start_y = h // 2 - total_h // 2 + 40
        x = w // 2 - btn_w // 2

        C = _MENU_COLORS
        self._buttons = [
            _MenuButton(
                x,
                start_y,
                btn_w,
                btn_h,
                t("ui:menu_new_game"),
                C["btn_primary"],
                C["btn_primary_hover"],
                lambda: self._set_action(MenuAction.NEW_GAME),
            ),
            _MenuButton(
                x,
                start_y + btn_h + gap,
                btn_w,
                btn_h,
                t("ui:menu_continue"),
                C["btn_primary"],
                C["btn_primary_hover"],
                lambda: self._set_action(MenuAction.CONTINUE),
            ),
            _MenuButton(
                x,
                start_y + 2 * (btn_h + gap),
                btn_w,
                btn_h,
                t("ui:menu_editor"),
                C["btn_secondary"],
                C["btn_secondary_hover"],
                lambda: self._set_action(MenuAction.EDITOR),
            ),
            _MenuButton(
                x,
                start_y + 3 * (btn_h + gap),
                btn_w,
                btn_h,
                t("ui:menu_settings"),
                C["btn_secondary"],
                C["btn_secondary_hover"],
                lambda: self._set_action(MenuAction.SETTINGS),
            ),
            _MenuButton(
                x,
                start_y + 4 * (btn_h + gap),
                btn_w,
                btn_h,
                t("ui:menu_exit"),
                C["btn_danger"],
                C["btn_danger_hover"],
                lambda: self._set_action(MenuAction.EXIT),
            ),
        ]

    def _set_action(self, action: MenuAction) -> None:
        self._result = action

    def run(self) -> MenuAction:
        """Запускает цикл меню, блокирует до выбора действия"""
        self._result = None
        self._selected_idx = 0

        while self._result is None:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self._result = MenuAction.EXIT
                elif event.type == pygame.VIDEORESIZE:
                    self.screen = pygame.display.set_mode(
                        (event.w, event.h), pygame.RESIZABLE
                    )
                    self._build_buttons()
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_UP:
                        self._selected_idx = (self._selected_idx - 1) % len(
                            self._buttons
                        )
                    elif event.key == pygame.K_DOWN:
                        self._selected_idx = (self._selected_idx + 1) % len(
                            self._buttons
                        )
                    elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                        self._buttons[self._selected_idx].on_click()
                    elif event.key == pygame.K_ESCAPE:
                        self._result = MenuAction.EXIT
                else:
                    for btn in self._buttons:
                        if btn.handle_event(event):
                            break

            self._draw()
            pygame.display.flip()
            self.clock.tick(60)

        return self._result

    def _draw(self) -> None:
        w, h = self.screen.get_size()

        # Фоновое изображение — масштабирование с сохранением пропорций (cover)
        if self._bg_image is not None:
            bg_w, bg_h = self._bg_image.get_size()
            scale = max(w / bg_w, h / bg_h)
            scaled_w = int(bg_w * scale)
            scaled_h = int(bg_h * scale)
            scaled_bg = pygame.transform.smoothscale(
                self._bg_image, (scaled_w, scaled_h)
            )
            # Центрируем обрезку
            offset_x = (w - scaled_w) // 2
            offset_y = (h - scaled_h) // 2
            self.screen.blit(scaled_bg, (offset_x, offset_y))
            # Затемнение для читаемости текста
            overlay = pygame.Surface((w, h), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 120))
            self.screen.blit(overlay, (0, 0))
        else:
            self.screen.fill(_MENU_COLORS["bg_dark"])

        # Анимация дыма
        dt = self.clock.get_time() / 1000.0
        for emitter in self._smoke_emitters:
            emitter.update(dt)
            emitter.draw(self.screen, w, h)

        # Заголовок
        title_surf = self.font_title.render("ENIGMA", True, _MENU_COLORS["accent_blue"])
        title_rect = title_surf.get_rect(centerx=w // 2, y=h // 2 - 120)
        self.screen.blit(title_surf, title_rect)

        # Подзаголовок
        sub_surf = self.font_subtitle.render(
            "RPG Engine", True, _MENU_COLORS["text_dim"]
        )
        sub_rect = sub_surf.get_rect(centerx=w // 2, y=title_rect.bottom + 8)
        self.screen.blit(sub_surf, sub_rect)

        # Кнопки — подсвечиваем выбранную клавиатурой
        for i, btn in enumerate(self._buttons):
            btn.hovered = btn.hovered or (i == getattr(self, "_selected_idx", -1))
            btn.draw(self.screen, self.font_button)

        # Версия
        # ИСПРАВЛЕНО: версия берётся из constants.py, а не хардкодится.
        from constants import PROJECT_VERSION

        ver_surf = self.font_small.render(
            PROJECT_VERSION, True, _MENU_COLORS["text_dim"]
        )
        self.screen.blit(ver_surf, (w - ver_surf.get_width() - 12, h - 24))
