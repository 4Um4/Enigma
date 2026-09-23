"""
path: /frontend/ui_workbench/snap_engine.py
Назначение: Магнитное прилипание окон к граням соседей и границам зоны.
Паттерн перенесён из slick-window-arrangement (Windhawk, m417z, GPLv3):
magnet-targets на 4 стороны + выбор ближайшего конфликта + проверка
«заголовок остаётся в зоне». WinAPI-специфика оригинала (DPI, хуки,
субклассинг) не нужна: у нас один кадр рендера и список rect'ов.
Зависимости: pygame
Основные сущности: SnapEngine
"""
from typing import List, Optional, Tuple

import pygame

_Edge = Tuple[int, int, int]  # (координата-линия, начало попер. оси, конец попер. оси)


class SnapEngine:
    """Прилипание drag'а к граням. Собирается заново на каждый MOUSEBUTTONDOWN
    (лёгкая структура), используется на каждый MOUSEMOTION."""

    def __init__(self, magnet_pixels: int = 14) -> None:
        self._magnet = magnet_pixels
        self._edges: List[Tuple[str, _Edge]] = []  # ("left"|"right"|"top"|"bottom", edge)

    def build(self, zone: pygame.Rect, others: List[pygame.Rect]) -> None:
        """Цели = границы зоны (safe-area) + грани всех прочих окон."""
        self._edges = [
            ("left", (zone.left, zone.top, zone.bottom)),
            ("right", (zone.right, zone.top, zone.bottom)),
            ("top", (zone.top, zone.left, zone.right)),
            ("bottom", (zone.bottom, zone.left, zone.right)),
        ]
        for rc in others:
            self._edges.append(("left", (rc.left, rc.top, rc.bottom)))
            self._edges.append(("right", (rc.right, rc.top, rc.bottom)))
            self._edges.append(("top", (rc.top, rc.left, rc.right)))
            self._edges.append(("bottom", (rc.bottom, rc.left, rc.right)))

    def _closest(self, side: str, source: int, a_start: int, a_end: int) -> Optional[int]:
        """Ближайшая цель side в радиусе magnet, пересекающаяся по поперечной оси
        [a_start, a_end] (прямой аналог FindClosestTarget оригинала)."""
        best: Optional[int] = None
        for s, (line, b, c) in self._edges:
            if s != side:
                continue
            if not (a_start < c and a_end > b):  # нет перекрытия по поперечной оси
                continue
            d = abs(source - line)
            if d <= self._magnet and (best is None or d < abs(source - best)):
                best = line
        return best

    def snap_delta(self, drag: pygame.Rect) -> Tuple[int, int]:
        """Поправка (dx, dy) к позиции drag: прилипание к ближайшим граням.
        Конфликт двух сторон одной оси решается минимальной дистанцией
        (аналог ветки targetLeft/targetRight оригинала)."""
        dx = 0
        left = self._closest("left", drag.right, drag.top, drag.bottom)
        right = self._closest("right", drag.left, drag.top, drag.bottom)
        if left is not None and right is not None:
            dx = left - drag.right if abs(left - drag.right) < abs(right - drag.left) else right - drag.left
        elif left is not None:
            dx = left - drag.right
        elif right is not None:
            dx = right - drag.left

        dy = 0
        top = self._closest("top", drag.bottom, drag.left, drag.right)
        bottom = self._closest("bottom", drag.top, drag.left, drag.right)
        if top is not None and bottom is not None:
            dy = top - drag.bottom if abs(top - drag.bottom) < abs(bottom - drag.top) else bottom - drag.top
        elif top is not None:
            dy = top - drag.bottom
        elif bottom is not None:
            dy = bottom - drag.top

        return dx, dy

    def clamp_title_inside(self, new_rect: pygame.Rect, zone: pygame.Rect) -> bool:
        """Аналог IsRectInWorkArea: заголовок (верх окна) обязан остаться в зоне —
        иначе окно станет незахватываемым."""
        return zone.colliderect(pygame.Rect(new_rect.x, new_rect.y, new_rect.width, 1))

    @staticmethod
    def resolve_overlap(moved: pygame.Rect, others: List[pygame.Rect]) -> pygame.Rect:
        """Выталкивание: если moved наложился на соседа — сдвиг к его ближайшей
        грани по оси минимального проникновения (окна не наслаиваются)."""
        for rc in others:
            if not moved.colliderect(rc):
                continue
            push_left = rc.left - moved.right      # < 0
            push_right = rc.right - moved.left     # > 0
            push_up = rc.top - moved.bottom
            push_down = rc.bottom - moved.top
            # Минимальная сдвижка из четырёх направлений
            candidates = [
                (abs(push_left), push_left, 0),
                (abs(push_right), push_right, 0),
                (abs(push_up), 0, push_up),
                (abs(push_down), 0, push_down),
            ]
            _, mx, my = min(candidates, key=lambda c: c[0])
            moved = moved.move(mx, my)
        return moved