"""path: /frontend/map_editor/ui/blueprint_inspector.py

Назначение: BlueprintInspectorPanel — read-only инспектор Blueprint (ME-2.1-G-3).
    Первый интеграционный тест архитектуры редактирования: UI управляет сессией
    через BlueprintEditor/EditSession, НЕ получая доступа к AssetStore.

    Контракт Master (G-3, read-only):
    - Double-click по карточке каталога → открыть инспектор
    - Сессия через BlueprintEditor.open(bp_id) → EditSession
    - Данные через session.get_data() / session.get_field() (deepcopy — UI не
      получает ссылку на working)
    - Валидация через session.validate() (errors/warnings раздельно)
    - Dirty indicator через session.dirty
    - Закрытие → session.close() (сессия завершена)
    - Повторное открытие → новая сессия с актуальным состоянием AssetStore

    G-3 НЕ включает: set_field, save, cancel через UI (это G-4).

Зависимости: assets.blueprint_editor (BlueprintEditor, EditSession, SessionState),
    assets.resource_validator (ValidationResult), pygame. Backend не импортируется.

Основные сущности: BlueprintInspectorPanel.
"""

from __future__ import annotations

from typing import Optional

import pygame
from assets.blueprint_editor import BlueprintEditor, EditSession, SessionState


class BlueprintInspectorPanel:
    """Read-only инспектор Blueprint через EditSession (ME-2.1-G-3).

    UI-контракт:
    - НЕ получает BlueprintRecord.data (только через session.get_data/get_field)
    - НЕ вызывает save_blueprint_atomic (нет save в read-only)
    - НЕ пишет файлы (нет write_text/json.dump)
    - НЕ мутирует _blueprints (нет доступа к AssetStore._blueprints)
    - НЕ создаёт собственную логику валидации (использует session.validate())
    """

    # Слои Blueprint для отображения (порядок важен)
    _SECTIONS = [
        ("blueprint_id", "ID"),
        ("version", "Version"),
        ("type", "Type"),
        ("category", "Category (legacy)"),
        ("categories", "Categories"),
        ("tags", "Tags"),
    ]

    _LAYER_FIELDS = [
        ("geometry", "Geometry", ["source", "size.w", "size.h", "size.d", "rotation_mode", "requires_wall"]),
        ("appearance", "Appearance", ["sprite", "color", "show_name"]),
        ("physics", "Physics", ["cover", "height", "passability.walk", "passability.jump_over"]),
        ("function", "Function", ["components"]),
        ("semantics", "Semantics", []),
        ("metadata", "Metadata", ["label", "icon"]),
    ]

    def __init__(
        self,
        x: int,
        y: int,
        w: int,
        h: int,
        blueprint_editor: BlueprintEditor,
    ) -> None:
        self.rect = pygame.Rect(x, y, w, h)
        self._editor = blueprint_editor
        self.active = False
        self._session: Optional[EditSession] = None
        self._validation = None  # ValidationResult (не типизирован — duck typing)

        # Layout
        pad = 8
        self._close_rect = pygame.Rect(w - 24 - pad, pad, 24, 22)
        self._content_y = pad + 26
        self._content_h = h - self._content_y - pad

        # Colors (соответствуют CatalogPanel)
        self._bg = (30, 30, 40)
        self._border = (60, 60, 80)
        self._text = (200, 200, 220)
        self._text_dim = (120, 120, 140)
        self._text_error = (220, 80, 80)
        self._text_warn = (220, 180, 80)
        self._text_ok = (80, 200, 80)
        self._text_dirty = (220, 180, 80)
        self._text_clean = (80, 200, 80)
        self._section_bg = (40, 40, 55)
        self._btn_bg = (50, 50, 65)

    # ===== Жизненный цикл =====

    def open(self, blueprint_id: str) -> None:
        """Открыть инспектор для blueprint_id через BlueprintEditor.open().

        Создаёт новую EditSession с deepcopy snapshot. Если уже открыта —
        закрывает предыдущую сессию (session.close()), затем открывает новую.
        """
        if self._session is not None:
            self._session.close()
        self._session = self._editor.open(blueprint_id)
        self._validation = self._session.validate()
        self.active = True

    def close(self) -> None:
        """Закрыть инспектор. Завершает сессию через session.close().

        После close сессия непригодна (state=CANCELLED, working/original очищены).
        Повторное открытие создаст новую сессию.
        """
        if self._session is not None:
            self._session.close()
            self._session = None
        self._validation = None
        self.active = False

    # ===== События =====

    def handle_event(self, event: pygame.event.Event) -> bool:
        """Обработать событие. Вернуть True если поглощено.

        G-3 (read-only): обрабатывает только закрытие (Esc/F4/крестик).
        Никаких set_field/save/cancel — это G-4.
        """
        if not self.active or self._session is None:
            return False

        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_ESCAPE, pygame.K_F4):
                self.close()
                return True

        elif event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1:
                mx, my = pygame.mouse.get_pos()
                close_abs = self._close_rect.move(self.rect.x, self.rect.y)
                if close_abs.collidepoint(mx, my):
                    self.close()
                    return True

        return False

    # ===== Отрисовка =====

    def draw(self, screen: pygame.Surface, font, font_small, font_bold) -> None:
        """Отрисовать инспектор. Read-only: только отображение."""
        if not self.active or self._session is None:
            return

        # Фон
        pygame.draw.rect(screen, self._bg, self.rect)
        pygame.draw.rect(screen, self._border, self.rect, 1)

        rx = self.rect.x
        ry = self.rect.y

        # Заголовок: blueprint_id + dirty indicator
        title = self._session.blueprint_id
        dirty_text = " *изменено" if self._session.dirty else " чисто"
        dirty_color = self._text_dirty if self._session.dirty else self._text_clean
        title_surf = font_bold.render(f"📋 {title}", True, self._text)
        screen.blit(title_surf, (rx + 8, ry + 6))
        dirty_surf = font_small.render(dirty_text, True, dirty_color)
        screen.blit(dirty_surf, (rx + 8 + title_surf.get_width() + 8, ry + 10))

        # Кнопка закрытия
        close_abs = self._close_rect.move(rx, ry)
        pygame.draw.rect(screen, self._btn_bg, close_abs)
        pygame.draw.rect(screen, self._border, close_abs, 1)
        close_label = font_small.render("✕", True, self._text)
        screen.blit(close_label, (close_abs.x + 8, close_abs.y + 3))

        # Состояние сессии
        state_text = f"Состояние: {self._session.state.value}"
        state_color = self._text_dim if self._session.state == SessionState.OPEN else self._text_warn
        state_surf = font_small.render(state_text, True, state_color)
        screen.blit(state_surf, (rx + 8, ry + 32))

        # Валидация (errors/warnings раздельно)
        self._draw_validation(screen, font_small, font_bold, rx, ry + 52)

        # Контент — скроллируемая область
        content_y = ry + self._content_y + 60
        self._draw_sections(screen, font, font_small, font_bold, rx, content_y)

    def _draw_validation(self, screen, font_small, font_bold, x: int, y: int) -> None:
        """Отрисовать errors/warnings раздельно."""
        if self._validation is None:
            label = font_small.render("Валидация: нет валидатора", True, self._text_dim)
            screen.blit(label, (x + 8, y))
            return

        errors = self._validation.errors
        warnings = self._validation.warnings

        # Errors
        err_text = f"Ошибки: {len(errors)}"
        err_color = self._text_error if errors else self._text_ok
        err_surf = font_small.render(err_text, True, err_color)
        screen.blit(err_surf, (x + 8, y))

        # Warnings
        warn_text = f"Предупреждения: {len(warnings)}"
        warn_color = self._text_warn if warnings else self._text_ok
        warn_surf = font_small.render(warn_text, True, warn_color)
        screen.blit(warn_surf, (x + 120, y))

        # Первые 3 ошибки (если есть)
        for i, issue in enumerate(errors[:3]):
            msg = issue.message[:60]
            surf = font_small.render(f"  • {msg}", True, self._text_error)
            screen.blit(surf, (x + 8, y + 18 + i * 14))

    def _draw_sections(self, screen, font, font_small, font_bold, x: int, y: int) -> None:
        """Отрисовать секции Blueprint (read-only)."""
        if self._session is None:
            return

        cy = y
        max_y = self.rect.y + self.rect.h - 8

        # Верхние поля
        for key, label in self._SECTIONS:
            if cy >= max_y:
                break
            try:
                value = self._session.get_field(key)
            except (KeyError, Exception):
                continue
            label_surf = font_small.render(label, True, self._text_dim)
            screen.blit(label_surf, (x + 8, cy))
            value_str = self._format_value(value)
            value_surf = font_small.render(value_str, True, self._text)
            screen.blit(value_surf, (x + 140, cy))
            cy += 16

        cy += 6

        # Слои
        for layer_key, layer_label, fields in self._LAYER_FIELDS:
            if cy >= max_y:
                break
            # Заголовок слоя
            header_surf = font_bold.render(f"── {layer_label} ──", True, self._text_dim)
            screen.blit(header_surf, (x + 8, cy))
            cy += 18

            # Поля слоя
            for field_path in fields:
                if cy >= max_y:
                    break
                full_path = f"{layer_key}.{field_path}"
                try:
                    value = self._session.get_field(full_path)
                except (KeyError, Exception):
                    continue
                label_surf = font_small.render(field_path, True, self._text_dim)
                screen.blit(label_surf, (x + 16, cy))
                value_str = self._format_value(value)
                value_surf = font_small.render(value_str, True, self._text)
                screen.blit(value_surf, (x + 150, cy))
                cy += 14
            cy += 4

    def _format_value(self, value) -> str:
        """Форматировать значение для отображения."""
        if value is None:
            return "—"
        if isinstance(value, bool):
            return "да" if value else "нет"
        if isinstance(value, (list, tuple)):
            if len(value) == 0:
                return "[]"
            if len(value) <= 3:
                return str(list(value))
            return f"[{len(value)} элементов]"
        if isinstance(value, dict):
            if len(value) == 0:
                return "{}"
            return f"{{ {len(value)} ключей }}"
        return str(value)[:40]
