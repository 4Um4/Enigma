"""
path: /frontend/ui_workbench/layout.py
Назначение: Анкерная геометрия. Позиции хранятся как anchor+offset+size_policy,
НЕ абсолютные пиксели (resolutions-устойчивость с первого дня).
Зависимости: pygame, ui_workbench.manifests
Основные сущности: AnchoredRect
"""
import pygame

from ui_workbench.manifests import WindowManifest

_ANCHORS = ("top_left", "top_right", "bottom_left", "bottom_right", "center")


class AnchoredRect:
    """Вычисляет pygame.Rect манифеста от текущего viewport. Вызывается каждый
    кадр (дёшево) → resize/fullscreen-устойчивость бесплатно."""

    @staticmethod
    def resolve(manifest: WindowManifest, viewport: pygame.Rect,
                collapsed: bool = False) -> pygame.Rect:
        if manifest.anchor not in _ANCHORS:
            raise ValueError(f"AnchoredRect[{manifest.window_id}]: неизвестный якорь '{manifest.anchor}'")

        vp_w, vp_h = viewport.size
        w = max(manifest.min_size[0], min(int(vp_w * manifest.size_policy[0]), manifest.max_size[0]))
        h = max(manifest.min_size[1], min(int(vp_h * manifest.size_policy[1]), manifest.max_size[1]))
        if collapsed:
            h = 34  # высота заголовка (токенизируется на Шаге Style)

        ox, oy = manifest.offset
        if manifest.anchor == "top_left":
            x, y = viewport.left + ox, viewport.top + oy
        elif manifest.anchor == "top_right":
            x, y = viewport.right - w - ox, viewport.top + oy
        elif manifest.anchor == "bottom_left":
            x, y = viewport.left + ox, viewport.bottom - h - oy
        elif manifest.anchor == "bottom_right":
            x, y = viewport.right - w - ox, viewport.bottom - h - oy
        else:  # center
            x, y = viewport.centerx - w // 2 + ox, viewport.centery - h // 2 + oy
        return pygame.Rect(x, y, w, h)