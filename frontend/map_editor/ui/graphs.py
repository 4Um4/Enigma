"""
path: frontend/map_editor/ui/graphs.py
Назначение: Нативные Pygame-графики Лаборатории калибровки (M1/Задача 3).
    Чистые рендереры БЕЗ состояния: история значений принадлежит LabScreen,
    графики только рисуют. Строго pygame.draw; русский UI; без эмодзи
    (стандартный шрифт рендерит «?» — правило S217).
Зависимости: pygame, typing. Палитра передаётся извне (COLORS из
    ui.components — ключи подтверждены использованием в lab_screen).
Основные сущности: LineGraph, BarChart.
"""
from __future__ import annotations

from typing import Dict, Sequence, Tuple

import pygame


class LineGraph:
    """Линейный график одного параметра по тикам эксперимента.

    min_val/max_val задают шкалу (доверие: -100..100 — нулевая линия
    рисуется явно). values — история от старых к новым.
    """

    def __init__(self, title: str, min_val: float, max_val: float, color_key: str) -> None:
        self.title = title
        self.min_val = float(min_val)
        self.max_val = float(max_val)
        self.color_key = color_key

    def draw(
        self,
        screen: pygame.Surface,
        rect: Tuple[int, int, int, int],
        values: Sequence[float],
        colors: Dict[str, Tuple[int, int, int]],
        font_small,
        font_bold,
    ) -> None:
        panel = pygame.Rect(rect)
        pygame.draw.rect(screen, colors["bg_panel"], panel, border_radius=6)
        pygame.draw.rect(screen, colors["border"], panel, 1, border_radius=6)

        title_surf = font_bold.render(self.title, True, colors["text_highlight"])
        screen.blit(title_surf, (panel.x + 10, panel.y + 6))

        # Область графика: слева место под подписи шкалы, сверху — заголовок
        gx = panel.x + 44
        gy = panel.y + 30
        gw = panel.w - 44 - 12
        gh = panel.h - 30 - 12
        if gw < 20 or gh < 20:
            return

        def _y_of(value: float) -> int:
            clamped = max(self.min_val, min(self.max_val, value))
            frac = (clamped - self.min_val) / (self.max_val - self.min_val)
            return gy + gh - int(gh * frac)  # ось Y инвертирована

        # Сетка: 3 линии + подписи шкалы
        for frac in (0.0, 0.5, 1.0):
            line_y = gy + gh - int(gh * frac)
            pygame.draw.line(screen, colors["bg_input"], (gx, line_y), (gx + gw, line_y), 1)
            val = self.min_val + (self.max_val - self.min_val) * frac
            label = font_small.render(f"{val:.0f}", True, colors["text"])
            screen.blit(label, (panel.x + 6, line_y - 7))

        # Нулевая линия для двуполярной шкалы (доверие)
        if self.min_val < 0 < self.max_val:
            pygame.draw.line(screen, colors["border"], (gx, _y_of(0)), (gx + gw, _y_of(0)), 1)

        if not values:
            hint = font_small.render("нет данных", True, colors["text"])
            screen.blit(hint, (gx + 10, gy + gh // 2 - 7))
            return

        color = colors[self.color_key]
        n = len(values)
        if n == 1:
            pygame.draw.circle(screen, color, (gx + gw // 2, _y_of(values[0])), 3)
        else:
            step = gw / (n - 1)
            points = [(gx + int(step * i), _y_of(v)) for i, v in enumerate(values)]
            pygame.draw.lines(screen, color, False, points, 2)

        # Текущее значение — правый верхний угол панели
        cur_surf = font_small.render(f"{values[-1]:.1f}", True, color)
        screen.blit(cur_surf, (panel.x + panel.w - cur_surf.get_width() - 10, panel.y + 8))


class BarChart:
    """Горизонтальные полосы текущих значений (драйвы выбранного NPC)."""

    def __init__(self, title: str) -> None:
        self.title = title

    def draw(
        self,
        screen: pygame.Surface,
        rect: Tuple[int, int, int, int],
        items: Sequence[Tuple[str, float, str]],  # (подпись, значение, color_key)
        colors: Dict[str, Tuple[int, int, int]],
        font_small,
        font_bold,
        max_val: float = 1.0,
    ) -> None:
        panel = pygame.Rect(rect)
        pygame.draw.rect(screen, colors["bg_panel"], panel, border_radius=6)
        pygame.draw.rect(screen, colors["border"], panel, 1, border_radius=6)

        title_surf = font_bold.render(self.title, True, colors["text_highlight"])
        screen.blit(title_surf, (panel.x + 10, panel.y + 6))

        if not items:
            hint = font_small.render("нет данных", True, colors["text"])
            screen.blit(hint, (panel.x + 12, panel.y + 34))
            return

        rows_top = panel.y + 32
        row_h = 22
        bar_x = panel.x + 110
        bar_w_max = max(30, panel.w - 110 - 60)
        for idx, (label, value, color_key) in enumerate(items):
            row_y = rows_top + idx * row_h
            if row_y + 14 > panel.y + panel.h - 4:
                break
            label_surf = font_small.render(label, True, colors["text"])
            screen.blit(label_surf, (panel.x + 10, row_y))
            frac = max(0.0, min(1.0, float(value) / max_val)) if max_val > 0 else 0.0
            fill_w = int(bar_w_max * frac)
            pygame.draw.rect(screen, colors["bg_input"], (bar_x, row_y + 2, bar_w_max, 12), border_radius=2)
            if fill_w > 0:
                pygame.draw.rect(screen, colors[color_key], (bar_x, row_y + 2, fill_w, 12), border_radius=2)
            val_surf = font_small.render(f"{float(value):.2f}", True, colors["text"])
            screen.blit(val_surf, (bar_x + bar_w_max + 8, row_y))