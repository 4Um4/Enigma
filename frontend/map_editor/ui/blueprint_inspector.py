"""path: /frontend/map_editor/ui/blueprint_inspector.py

Назначение: BlueprintEditorPanel — редактор Blueprint через EditSession (ME-2.1-G-4).
    UI управляет сессией через BlueprintEditor/EditSession, НЕ получая доступа
    к AssetStore. Типизированные элементы управления для полей Blueprint.

    Контракт Master (G-4):
    - Редактирование через session.set_field()
    - Live validation после каждого изменения
    - Dirty indicator через session.dirty
    - Save только через session.save() (заблокирован при ошибках)
    - Cancel через session.cancel() (настоящая отмена, не попадает в AssetStore)
    - Save disabled при ошибках валидации
    - VersionConflict: сохранить рабочую копию, показать конфликт, не перезаписывать
    - Unknown fields сохраняются (set_field не трогает неизвестные поля)
    - После успешного save: обновить состояние, dirty=False
    - Повторное открытие: актуальные данные AssetStore

Зависимости: assets.blueprint_editor, assets.resource_validator, ui.components, pygame.

Основные сущности: BlueprintEditorPanel.
"""

from __future__ import annotations

from typing import Optional

import pygame
from assets.blueprint_editor import BlueprintEditor, EditSession, SessionState

from ui.components import Button, Dropdown, TextInput


class _FieldControl:
    """Базовый класс для типизированного контрола поля Blueprint."""

    def __init__(self, path: str, label: str, widget):
        self.path = path
        self.label = label
        self.widget = widget

    def set_value(self, value) -> None:
        raise NotImplementedError

    def get_value(self):
        raise NotImplementedError

    def handle_event(self, event) -> bool:
        return self.widget.handle_event(event)

    def draw(self, screen, font, font_small, x: int, y: int) -> int:
        """Отрисовать label + widget. Вернуть высоту занятой области."""
        raise NotImplementedError


class _TextInputField(_FieldControl):
    """Текстовое поле (string или float через валидацию)."""

    def __init__(self, path: str, label: str, x: int, y: int, w: int, is_float: bool = False):
        widget = TextInput(x, y, w, 22)
        super().__init__(path, label, widget)
        self._is_float = is_float
        self._original_value = None

    def set_value(self, value) -> None:
        self._original_value = value
        if self._is_float:
            self.widget.text = str(value) if value is not None else ""
        else:
            self.widget.text = str(value) if value is not None else ""

    def get_value(self):
        text = self.widget.text.strip()
        if not text:
            return None
        if self._is_float:
            try:
                return float(text)
            except ValueError:
                return self._original_value  # невалидный float — вернуть исходный
        return text

    def draw(self, screen, font, font_small, x: int, y: int) -> int:
        label_surf = font_small.render(self.label, True, (140, 140, 140))
        screen.blit(label_surf, (x, y))
        self.widget.rect.x = x
        self.widget.rect.y = y + 14
        self.widget.draw(screen, font_small)
        return 38


class _BoolField(_FieldControl):
    """Checkbox для bool полей (ручная отрисовка)."""

    def __init__(self, path: str, label: str, x: int, y: int):
        super().__init__(path, label, None)
        self._toggled = False
        self._checkbox_rect = pygame.Rect(x + 150, y, 22, 22)

    def set_value(self, value) -> None:
        self._toggled = bool(value)

    def get_value(self):
        return self._toggled

    def handle_event(self, event) -> bool:
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            mx, my = pygame.mouse.get_pos()
            if self._checkbox_rect.collidepoint(mx, my):
                self._toggled = not self._toggled
                return True
        return False

    def draw(self, screen, font, font_small, x: int, y: int) -> int:
        label_surf = font_small.render(self.label, True, (140, 140, 140))
        screen.blit(label_surf, (x, y + 3))
        self._checkbox_rect.x = x + 150
        self._checkbox_rect.y = y
        color = (80, 200, 80) if self._toggled else (50, 50, 65)
        pygame.draw.rect(screen, color, self._checkbox_rect, border_radius=4)
        pygame.draw.rect(screen, (60, 60, 80), self._checkbox_rect, 1, border_radius=4)
        if self._toggled:
            state_surf = font_small.render("✓", True, (30, 30, 30))
            screen.blit(state_surf, (self._checkbox_rect.x + 6, self._checkbox_rect.y + 2))
        return 26


class _DropdownField(_FieldControl):
    """Dropdown для enum-полей (rotation_mode)."""

    def __init__(self, path: str, label: str, x: int, y: int, w: int, options: list):
        widget = Dropdown(x, y, w, 22, options)
        super().__init__(path, label, widget)

    def set_value(self, value) -> None:
        if value in self.widget.options:
            self.widget.selected = value

    def get_value(self):
        return self.widget.selected

    def draw(self, screen, font, font_small, x: int, y: int) -> int:
        label_surf = font_small.render(self.label, True, (140, 140, 140))
        screen.blit(label_surf, (x, y))
        self.widget.rect.x = x
        self.widget.rect.y = y + 14
        self.widget.draw(screen, font_small)
        return 38


class BlueprintInspectorPanel:
    """Редактор Blueprint через EditSession (ME-2.1-G-4).

    UI-контракт:
    - НЕ получает BlueprintRecord.data (только через session)
    - НЕ вызывает save_blueprint_atomic (только session.save())
    - НЕ пишет файлы
    - НЕ мутирует _blueprints
    - Использует типизированные виджеты (TextInput/ToggleButton/Dropdown)
    - Save заблокирован при ошибках валидации
    - Cancel восстанавливает original (session.cancel())
    - VersionConflict: сохранить рабочую копию, показать конфликт
    """

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
        self._validation = None
        self._status_message = ""
        self._status_color = (140, 140, 140)

        # Layout
        pad = 8
        self._close_rect = pygame.Rect(w - 24 - pad, pad, 24, 22)

        # Кнопки Save / Cancel (внизу панели)
        btn_y = h - 36
        self._btn_save = Button(pad, btn_y, 100, 28, "Сохранить", color_key="btn_success")
        self._btn_cancel = Button(pad + 110, btn_y, 100, 28, "Отмена", color_key="btn_danger")

        # Поле контроля (создаются в open())
        self._controls: list[_FieldControl] = []
        self._active_control: Optional[_FieldControl] = None

        # Colors
        self._bg = (30, 30, 40)
        self._border = (60, 60, 80)
        self._text = (200, 200, 220)
        self._text_dim = (120, 120, 140)
        self._text_error = (220, 80, 80)
        self._text_warn = (220, 180, 80)
        self._text_ok = (80, 200, 80)
        self._section_bg = (40, 40, 55)
        self._btn_bg = (50, 50, 65)

    def open(self, blueprint_id: str) -> None:
        """Открыть редактор для blueprint_id через BlueprintEditor.open()."""
        if self._session is not None:
            self._session.close()
        self._session = self._editor.open(blueprint_id)
        self._validation = self._session.validate()
        self._build_controls()
        self._refresh_controls()
        self._status_message = ""
        self.active = True

    def close(self) -> None:
        """Закрыть редактор. Завершает сессию через session.close()."""
        if self._session is not None:
            self._session.close()
            self._session = None
        self._validation = None
        self._controls = []
        self._active_control = None
        self._status_message = ""
        self.active = False

    def _build_controls(self) -> None:
        """Создать виджеты для редактируемых полей."""
        self._controls = []
        if self._session is None:
            return

        x = self.rect.x + 16
        w = self.rect.w - 32
        y = self.rect.y + 100  # после заголовка + валидации

        # Geometry
        self._controls.append(
            _DropdownField("geometry.rotation_mode", "Rotation", x, y, w, ["free", "mirror", "fixed"])
        )
        y += 42
        self._controls.append(_TextInputField("geometry.size.w", "Width (W)", x, y, w, is_float=True))
        y += 42
        self._controls.append(_TextInputField("geometry.size.h", "Height (H)", x, y, w, is_float=True))
        y += 42
        self._controls.append(_TextInputField("geometry.size.d", "Depth (D)", x, y, w, is_float=True))
        y += 42
        self._controls.append(_BoolField("geometry.requires_wall", "Requires Wall", x, y))
        y += 30

        # Appearance
        self._controls.append(_TextInputField("appearance.color", "Color (HEX)", x, y, w))
        y += 42
        self._controls.append(_BoolField("appearance.show_name", "Show Name", x, y))
        y += 30

        # Physics
        self._controls.append(_TextInputField("physics.cover", "Cover (0-1)", x, y, w, is_float=True))
        y += 42
        self._controls.append(_TextInputField("physics.height", "Height (m)", x, y, w, is_float=True))
        y += 42
        for field in ["walk", "jump_over", "crawl_under", "climb_on", "walk_around"]:
            self._controls.append(_BoolField(f"physics.passability.{field}", field.replace("_", " ").title(), x, y))
            y += 26

        # Metadata
        self._controls.append(_TextInputField("metadata.label", "Label", x, y, w))

    def _refresh_controls(self) -> None:
        """Обновить виджеты из session.get_field()."""
        if self._session is None:
            return
        for control in self._controls:
            try:
                value = self._session.get_field(control.path)
                control.set_value(value)
            except (KeyError, Exception):
                pass

    def _on_field_changed(self, control: _FieldControl) -> None:
        """Вызывается когда виджет изменил значение. Live validation."""
        if self._session is None or self._session.state != SessionState.OPEN:
            return
        value = control.get_value()
        if value is not None:
            self._session.set_field(control.path, value)
            self._validation = self._session.last_validation
            self._status_message = ""

    def _can_save(self) -> bool:
        """Save доступен если: сессия OPEN, dirty, нет ошибок валидации."""
        if self._session is None or self._session.state != SessionState.OPEN:
            return False
        if not self._session.dirty:
            return False
        if self._validation is not None and len(self._validation.errors) > 0:
            return False
        return True

    def _on_save(self) -> None:
        """Сохранить через session.save() → G-1. Обработать конфликты."""
        if self._session is None or not self._can_save():
            return
        try:
            result = self._session.save()
            self._status_message = f"✓ Сохранено v{result.version}"
            self._status_color = self._text_ok
            # Обновить controls из актуальной сессии (после save state=SAVED)
            # Повторное открытие для новой сессии
            bp_id = self._session.blueprint_id
            self.open(bp_id)
        except Exception as e:
            # VersionConflict или SaveBlocked или AssetStoreError
            self._status_message = f"✗ {e}"
            self._status_color = self._text_error
            # Сессия остаётся OPEN, рабочая копия цела (G-2 гарантирует)

    def _on_cancel(self) -> None:
        """Отмена через session.cancel(). Закрыть панель."""
        if self._session is not None:
            self._session.cancel()
        self.close()

    def handle_event(self, event: pygame.event.Event) -> bool:
        """Обработать событие."""
        if not self.active or self._session is None:
            return False

        # Esc/F4 — закрыть
        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_ESCAPE, pygame.K_F4):
                self.close()
                return True

        # Кнопка закрытия
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            mx, my = pygame.mouse.get_pos()
            close_abs = self._close_rect.move(self.rect.x, self.rect.y)
            if close_abs.collidepoint(mx, my):
                self.close()
                return True

            # Save / Cancel кнопки
            if self._btn_save.enabled:
                save_abs = self._btn_save.rect.move(self.rect.x, self.rect.y)
                if save_abs.collidepoint(mx, my):
                    self._on_save()
                    return True
            cancel_abs = self._btn_cancel.rect.move(self.rect.x, self.rect.y)
            if cancel_abs.collidepoint(mx, my):
                self._on_cancel()
                return True

        # Виджеты полей
        for control in self._controls:
            if control.handle_event(event):
                self._on_field_changed(control)
                return True

        return False

    def draw(self, screen: pygame.Surface, font, font_small, font_bold) -> None:
        """Отрисовать редактор."""
        if not self.active or self._session is None:
            return

        # Фон
        pygame.draw.rect(screen, self._bg, self.rect)
        pygame.draw.rect(screen, self._border, self.rect, 1)

        rx = self.rect.x
        ry = self.rect.y

        # Заголовок
        title = self._session.blueprint_id
        dirty_text = " *изменено" if self._session.dirty else " чисто"
        dirty_color = self._text_warn if self._session.dirty else self._text_ok
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

        # Валидация
        self._draw_validation(screen, font_small, font_bold, rx + 8, ry + 32)

        # Состояние сессии
        state_text = f"Состояние: {self._session.state.value}"
        state_color = self._text_dim if self._session.state == SessionState.OPEN else self._text_warn
        state_surf = font_small.render(state_text, True, state_color)
        screen.blit(state_surf, (rx + 8, ry + 78))

        # Поля (контролы)
        for control in self._controls:
            try:
                self._session.get_field(control.path)
            except (KeyError, Exception):
                continue
            # Контрол уже отрисован в handle_event? Нет — draw отдельно
            # Контролы хранят абсолютные позиции, установленные в _build_controls
            # Но rect.x/y сбрасывается — обновим
            control.draw(
                screen,
                font,
                font_small,
                control.widget.rect.x,
                control.widget.rect.y - (14 if isinstance(control, (_TextInputField, _DropdownField)) else 0),
            )

        # Status message
        if self._status_message:
            status_surf = font_small.render(self._status_message, True, self._status_color)
            screen.blit(status_surf, (rx + 8, self.rect.h - 50))

        # Save / Cancel кнопки (внизу)
        self._btn_save.enabled = self._can_save()
        save_abs = self._btn_save.rect.move(rx, ry)
        old_save_rect = self._btn_save.rect
        self._btn_save.rect = save_abs
        self._btn_save.draw(screen, font_small)
        self._btn_save.rect = old_save_rect

        cancel_abs = self._btn_cancel.rect.move(rx, ry)
        old_cancel_rect = self._btn_cancel.rect
        self._btn_cancel.rect = cancel_abs
        self._btn_cancel.draw(screen, font_small)
        self._btn_cancel.rect = old_cancel_rect

    def _draw_validation(self, screen, font_small, font_bold, x: int, y: int) -> None:
        """Отрисовать errors/warnings."""
        if self._validation is None:
            label = font_small.render("Валидация: нет валидатора", True, self._text_dim)
            screen.blit(label, (x, y))
            return

        errors = self._validation.errors
        warnings = self._validation.warnings

        err_text = f"Ошибки: {len(errors)}"
        err_color = self._text_error if errors else self._text_ok
        screen.blit(font_small.render(err_text, True, err_color), (x, y))

        warn_text = f"Предупреждения: {len(warnings)}"
        warn_color = self._text_warn if warnings else self._text_ok
        screen.blit(font_small.render(warn_text, True, warn_color), (x + 120, y))

        for i, issue in enumerate(errors[:2]):
            msg = issue.message[:50]
            screen.blit(font_small.render(f"  • {msg}", True, self._text_error), (x, y + 16 + i * 14))
