"""
path: /frontend/campaign_select.py
Экран выбора кампании — полностью самодостаточен, без зависимостей от map_editor и app/.
Читает метаданные из data/campaigns/*/campaign.json напрямую.

Назначение: Экран выбора кампании — читает папку data/campaigns, показывает список, возвращает выбранную кампанию или None (назад)
Зависимости: pygame, pathlib, json (только стандартная библиотека)
Основные сущности: CampaignEntry, CampaignSelectScreen
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import json

import pygame
from i18n import t


# Путь к кампаниям — исходники из редактора
_CAMPAIGNS_DIR = Path(__file__).parent / "map_editor" / "campaigns"

# Цветовая схема — дублируем из game_menu для изоляции (TODO: вынести в общий ui_theme.py)
_COLORS = {
    "bg_dark": (18, 18, 23),
    "bg_panel": (28, 28, 33),
    "bg_selected": (40, 55, 75),
    "bg_hover": (35, 45, 60),
    "text": (220, 220, 220),
    "text_dim": (140, 140, 140),
    "text_highlight": (255, 255, 255),
    "btn_primary": (70, 100, 130),
    "btn_primary_hover": (90, 130, 160),
    "btn_danger": (150, 60, 60),
    "btn_danger_hover": (180, 80, 80),
    "btn_secondary": (80, 80, 90),
    "btn_secondary_hover": (100, 100, 110),
    "border": (60, 60, 70),
    "border_highlight": (100, 180, 255),
    "accent_blue": (70, 170, 255),
    "accent_yellow": (255, 200, 80),
}


@dataclass
class CampaignEntry:
    """Метаданные одной кампании из campaign.json"""

    folder: str
    name: str
    description: str
    location_count: int


def _load_campaigns() -> list[CampaignEntry]:
    """Читает все кампании из файловой системы"""
    entries: list[CampaignEntry] = []
    if not _CAMPAIGNS_DIR.exists():
        return entries

    for d in sorted(_CAMPAIGNS_DIR.iterdir()):
        if not d.is_dir():
            continue
        meta_file = d / "campaign.json"
        if not meta_file.exists():
            continue
        try:
            with open(meta_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            loc_dir = d / "locations"
            loc_count = len(list(loc_dir.glob("*.json"))) if loc_dir.exists() else 0
            entries.append(
                CampaignEntry(
                    folder=d.name,
                    name=data.get("name", d.name),
                    description=data.get("description", ""),
                    location_count=loc_count,
                )
            )
        except Exception:
            entries.append(
                CampaignEntry(
                    folder=d.name,
                    name=d.name,
                    description="(ошибка чтения)",
                    location_count=0,
                )
            )
    return entries


class CampaignSelectScreen:
    """Экран выбора кампании — возвращает имя папки выбранной кампании или None"""

    def __init__(self, screen: pygame.Surface, clock: pygame.time.Clock):
        self.screen = screen
        self.clock = clock
        self._result: Optional[str] = None  # folder name или None (назад)

        # Двойной клик
        self._last_click_time: float = 0.0
        self._last_click_pos: tuple[int, int] = (0, 0)

        # Шрифты
        self.font_title = pygame.font.SysFont("consolas", 32, bold=True)
        self.font_name = pygame.font.SysFont("consolas", 18, bold=True)
        self.font_desc = pygame.font.SysFont("consolas", 14)
        self.font_button = pygame.font.SysFont("consolas", 18, bold=True)
        self.font_small = pygame.font.SysFont("consolas", 13)

        # Данные
        self._campaigns = _load_campaigns()
        self._selected_index: int = -1

        # Размеры списка
        self._item_height = 70
        self._list_padding = 12
        self._list_rect = pygame.Rect(0, 0, 0, 0)

        # Кнопки
        self._btn_back_rect = pygame.Rect(0, 0, 0, 0)
        self._btn_play_rect = pygame.Rect(0, 0, 0, 0)

        self._layout()

    def _layout(self) -> None:
        """Пересчитывает позиции элементов при изменении размера окна"""
        w, h = self.screen.get_size()

        # Заголовок — сверху с отступом
        self._title_y = 40

        # Область списка
        list_top = 90
        list_bottom = h - 70
        self._list_rect = pygame.Rect(
            w // 2 - 320, list_top, 640, max(0, list_bottom - list_top)
        )

        # Кнопки — под списком
        btn_y = h - 55
        self._btn_back_rect = pygame.Rect(w // 2 - 290, btn_y, 130, 40)
        self._btn_play_rect = pygame.Rect(w // 2 + 160, btn_y, 130, 40)

    def run(self) -> Optional[str]:
        """Запускает цикл экрана, возвращает folder name кампании или None"""
        self._result = None
        self._selected_index = 0 if self._campaigns else -1

        while self._result is None:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return None
                elif event.type == pygame.VIDEORESIZE:
                    self.screen = pygame.display.set_mode(
                        (event.w, event.h), pygame.RESIZABLE
                    )
                    self._layout()
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    import time

                    now = time.time()
                    dx = abs(event.pos[0] - self._last_click_pos[0])
                    dy = abs(event.pos[1] - self._last_click_pos[1])
                    is_double = (now - self._last_click_time < 0.4) and (
                        dx < 5 and dy < 5
                    )
                    self._last_click_time = now
                    self._last_click_pos = event.pos

                    self._handle_click(event.pos)

                    # Двойной клик по списку = войти
                    if is_double and 0 <= self._selected_index < len(self._campaigns):
                        if self._list_rect.collidepoint(event.pos):
                            self._result = self._campaigns[self._selected_index].folder
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        return None
                    elif event.key == pygame.K_UP:
                        if self._selected_index > 0:
                            self._selected_index -= 1
                    elif event.key == pygame.K_DOWN:
                        if self._selected_index < len(self._campaigns) - 1:
                            self._selected_index += 1
                    elif event.key == pygame.K_RETURN:
                        if 0 <= self._selected_index < len(self._campaigns):
                            self._result = self._campaigns[self._selected_index].folder

            self._draw()
            pygame.display.flip()
            self.clock.tick(60)

        return self._result

    def _handle_click(self, pos: tuple[int, int]) -> None:
        """Обрабатывает клик по списку и кнопкам"""
        # Кнопка «Назад»
        if self._btn_back_rect.collidepoint(pos):
            self._result = None
            return

        # Кнопка «Играть»
        if self._btn_play_rect.collidepoint(pos) and 0 <= self._selected_index < len(
            self._campaigns
        ):
            self._result = self._campaigns[self._selected_index].folder
            return

        # Список кампаний
        if self._list_rect.collidepoint(pos):
            relative_y = pos[1] - self._list_rect.top
            index = relative_y // self._item_height
            if 0 <= index < len(self._campaigns):
                self._selected_index = index

    def _draw(self) -> None:
        """Отрисовка экрана"""
        self.screen.fill(_COLORS["bg_dark"])
        w, _ = self.screen.get_size()

        # Заголовок
        title_surf = self.font_title.render(
            t("ui:campaign_select_title"), True, _COLORS["accent_blue"]
        )
        self.screen.blit(
            title_surf, (w // 2 - title_surf.get_width() // 2, self._title_y)
        )

        # Область списка — фон
        if self._campaigns:
            pygame.draw.rect(
                self.screen, _COLORS["bg_panel"], self._list_rect, border_radius=8
            )
            pygame.draw.rect(
                self.screen, _COLORS["border"], self._list_rect, 1, border_radius=8
            )

            # Обрезаем отрисовку элементов по области списка
            clip = self.screen.get_clip()
            self.screen.set_clip(self._list_rect)

            for i, entry in enumerate(self._campaigns):
                item_rect = pygame.Rect(
                    self._list_rect.x + self._list_padding,
                    self._list_rect.y + i * self._item_height + 4,
                    self._list_rect.width - self._list_padding * 2,
                    self._item_height - 8,
                )

                # Фон элемента
                is_hovered = item_rect.collidepoint(pygame.mouse.get_pos())
                if i == self._selected_index:
                    bg = _COLORS["bg_selected"]
                    border = _COLORS["border_highlight"]
                elif is_hovered:
                    bg = _COLORS["bg_hover"]
                    border = None
                else:
                    bg = None
                    border = None

                if bg:
                    pygame.draw.rect(self.screen, bg, item_rect, border_radius=6)
                if border:
                    pygame.draw.rect(self.screen, border, item_rect, 1, border_radius=6)

                # Имя кампании
                name_color = (
                    _COLORS["text_highlight"]
                    if i == self._selected_index
                    else _COLORS["text"]
                )
                name_surf = self.font_name.render(entry.name, True, name_color)
                self.screen.blit(name_surf, (item_rect.x + 10, item_rect.y + 8))

                # Описание
                desc_surf = self.font_desc.render(
                    entry.description, True, _COLORS["text_dim"]
                )
                self.screen.blit(desc_surf, (item_rect.x + 10, item_rect.y + 30))

                # Счётчик локаций — справа
                loc_text = f"{entry.location_count} лок."
                loc_surf = self.font_small.render(loc_text, True, _COLORS["text_dim"])
                self.screen.blit(
                    loc_surf,
                    (item_rect.right - loc_surf.get_width() - 10, item_rect.y + 10),
                )

            self.screen.set_clip(clip)
        else:
            # Нет кампаний
            empty_surf = self.font_desc.render(
                t("ui:campaign_not_found"),
                True,
                _COLORS["text_dim"],
            )
            self.screen.blit(
                empty_surf,
                (
                    w // 2 - empty_surf.get_width() // 2,
                    self._list_rect.y + 30,
                ),
            )

        # Кнопка «Назад»
        back_hovered = self._btn_back_rect.collidepoint(pygame.mouse.get_pos())
        back_color = (
            _COLORS["btn_secondary_hover"] if back_hovered else _COLORS["btn_secondary"]
        )
        pygame.draw.rect(self.screen, back_color, self._btn_back_rect, border_radius=6)
        back_surf = self.font_button.render(t("ui:btn_back"), True, _COLORS["text"])
        self.screen.blit(
            back_surf, back_surf.get_rect(center=self._btn_back_rect.center)
        )

        # Кнопка «Играть»
        can_play = 0 <= self._selected_index < len(self._campaigns)
        if can_play:
            play_hovered = self._btn_play_rect.collidepoint(pygame.mouse.get_pos())
            play_color = (
                _COLORS["btn_primary_hover"] if play_hovered else _COLORS["btn_primary"]
            )
            play_text_color = _COLORS["text_highlight"]
        else:
            play_color = (50, 50, 55)
            play_text_color = _COLORS["text_dim"]
        pygame.draw.rect(self.screen, play_color, self._btn_play_rect, border_radius=6)
        play_surf = self.font_button.render(t("ui:btn_play"), True, play_text_color)
        self.screen.blit(
            play_surf, play_surf.get_rect(center=self._btn_play_rect.center)
        )
