"""
map_editor/ui_components.py
UI компоненты: кнопки, модальные окна, панели, выпадающие списки
"""

from typing import Any, Callable, Dict, List, Optional, Tuple

import pygame

# === Цветовая схема ===
COLORS = {
    "bg_dark": (18, 18, 23),
    "bg_panel": (28, 28, 33),
    "bg_menu": (35, 35, 42),
    "bg_hover": (55, 75, 100),
    "bg_input": (45, 45, 55),
    "bg_input_active": (55, 65, 80),
    "text": (220, 220, 220),
    "text_dim": (140, 140, 140),
    "text_highlight": (255, 255, 255),
    "btn_primary": (70, 100, 130),
    "btn_primary_hover": (90, 130, 160),
    "btn_secondary": (80, 80, 90),
    "btn_secondary_hover": (100, 100, 110),
    "btn_danger": (150, 60, 60),
    "btn_danger_hover": (180, 80, 80),
    "btn_success": (60, 130, 60),
    "btn_success_hover": (80, 160, 80),
    "border": (60, 60, 70),
    "border_highlight": (100, 180, 255),
    "grid_major": (45, 45, 55),
    "grid_minor": (35, 35, 45),
    "accent_blue": (70, 170, 255),
    "accent_green": (100, 200, 100),
    "accent_yellow": (255, 200, 80),
    "accent_red": (255, 100, 100),
}


class Button:
    """Кнопка с текстом или иконкой"""

    def __init__(
        self,
        x: int,
        y: int,
        width: int,
        height: int,
        text: str = "",
        icon: str = "",
        color_key: str = "btn_primary",
        on_click: Optional[Callable] = None,
        tooltip: str = "",
    ):
        self.rect = pygame.Rect(x, y, width, height)
        self.text = text
        self.icon = icon
        self.color_key = color_key
        self.on_click = on_click
        self.tooltip = tooltip
        self.hovered = False
        self.visible = True
        self.enabled = True

    def draw(self, screen: pygame.Surface, font: pygame.font.Font):
        if not self.visible:
            return

        # Выбор цвета
        if not self.enabled:
            color = (50, 50, 55)
        elif self.hovered:
            color = COLORS.get(f"{self.color_key}_hover", COLORS["btn_primary_hover"])
        else:
            color = COLORS.get(self.color_key, COLORS["btn_primary"])

        # Фон кнопки
        pygame.draw.rect(screen, color, self.rect, border_radius=6)
        pygame.draw.rect(screen, COLORS["border"], self.rect, 1, border_radius=6)

        # Текст/иконка
        text_to_render = self.icon if self.icon else self.text
        text_color = (
            COLORS["text_dim"] if not self.enabled else COLORS["text_highlight"]
        )
        text_surf = font.render(text_to_render, True, text_color)
        text_rect = text_surf.get_rect(center=self.rect.center)
        screen.blit(text_surf, text_rect)

    def handle_event(self, event: pygame.event.Event) -> bool:
        if not self.visible or not self.enabled:
            return False

        if event.type == pygame.MOUSEMOTION:
            self.hovered = self.rect.collidepoint(event.pos)

        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.rect.collidepoint(event.pos):
                if self.on_click:
                    self.on_click()
                return True
        return False


class ToggleButton(Button):
    """Кнопка-переключатель (вкл/выкл)"""

    def __init__(
        self,
        x: int,
        y: int,
        width: int,
        height: int,
        text: str = "",
        icon: str = "",
        on_toggle: Optional[Callable[[bool], None]] = None,
        initial_state: bool = False,
    ):
        super().__init__(x, y, width, height, text, icon, "btn_secondary")
        self.state = initial_state
        self.on_toggle = on_toggle

    def draw(self, screen: pygame.Surface, font: pygame.font.Font):
        self.color_key = "btn_primary" if self.state else "btn_secondary"
        super().draw(screen, font)

    def handle_event(self, event: pygame.event.Event) -> bool:
        if not self.visible or not self.enabled:
            return False

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.rect.collidepoint(event.pos):
                self.state = not self.state
                if self.on_toggle:
                    self.on_toggle(self.state)
                return True
        return False


class TextInput:
    """Поле ввода текста"""

    def __init__(
        self,
        x: int,
        y: int,
        width: int,
        height: int = 32,
        label: str = "",
        placeholder: str = "",
        value: str = "",
        numeric: bool = False,
    ):
        self.rect = pygame.Rect(x, y, width, height)
        self.label = label
        self.placeholder = placeholder
        self.value = value
        self.numeric = numeric
        self.active = False
        self.cursor_pos = len(value)
        self.visible = True

    def draw(
        self,
        screen: pygame.Surface,
        font: pygame.font.Font,
        small_font: pygame.font.Font,
    ):
        if not self.visible:
            return

        y_offset = 0  # noqa: F841

        # Метка
        if self.label:
            label_surf = small_font.render(self.label, True, COLORS["text"])
            screen.blit(label_surf, (self.rect.x, self.rect.y - 18))
            y_offset = 0  # noqa: F841

        # Поле ввода
        color = COLORS["bg_input_active"] if self.active else COLORS["bg_input"]
        pygame.draw.rect(screen, color, self.rect, border_radius=4)
        border_color = COLORS["border_highlight"] if self.active else COLORS["border"]
        pygame.draw.rect(
            screen, border_color, self.rect, 2 if self.active else 1, border_radius=4
        )

        # Текст
        display_text = self.value
        if self.active:
            display_text += "|"
        elif not self.value:
            display_text = self.placeholder

        text_color = (
            COLORS["text"] if (self.value or self.active) else COLORS["text_dim"]
        )
        text_surf = font.render(display_text, True, text_color)
        # Обрезаем текст если не влезает
        if text_surf.get_width() > self.rect.width - 16:
            text_surf = font.render("..." + display_text[-20:], True, text_color)
        screen.blit(text_surf, (self.rect.x + 8, self.rect.y + 8))

    def handle_event(self, event: pygame.event.Event) -> bool:
        if not self.visible:
            return False

        if event.type == pygame.MOUSEBUTTONDOWN:
            was_active = self.active
            self.active = self.rect.collidepoint(event.pos)
            if self.active != was_active:
                return True

        elif event.type == pygame.KEYDOWN and self.active:
            if event.key == pygame.K_BACKSPACE:
                if self.cursor_pos > 0:
                    self.value = (
                        self.value[: self.cursor_pos - 1]
                        + self.value[self.cursor_pos :]
                    )
                    self.cursor_pos -= 1
            elif event.key == pygame.K_DELETE:
                if self.cursor_pos < len(self.value):
                    self.value = (
                        self.value[: self.cursor_pos]
                        + self.value[self.cursor_pos + 1 :]
                    )
            elif event.key == pygame.K_LEFT:
                self.cursor_pos = max(0, self.cursor_pos - 1)
            elif event.key == pygame.K_RIGHT:
                self.cursor_pos = min(len(self.value), self.cursor_pos + 1)
            elif event.key == pygame.K_HOME:
                self.cursor_pos = 0
            elif event.key == pygame.K_END:
                self.cursor_pos = len(self.value)
            elif event.unicode.isprintable():
                if self.numeric and not (
                    event.unicode.isdigit() or event.unicode in "-.+"
                ):
                    return True
                self.value = (
                    self.value[: self.cursor_pos]
                    + event.unicode
                    + self.value[self.cursor_pos :]
                )
                self.cursor_pos += 1
            return True
        return False

    def get_value(self) -> str:
        return self.value

    def get_int(self) -> int:
        try:
            return int(self.value)
        except ValueError:
            return 0

    def get_float(self) -> float:
        try:
            return float(self.value)
        except ValueError:
            return 0.0


class Dropdown:
    """Выпадающий список"""

    def __init__(
        self,
        x: int,
        y: int,
        width: int,
        height: int = 32,
        options: List[str] = None,
        label: str = "",
    ):
        self.rect = pygame.Rect(x, y, width, height)
        self.options = options or []
        self.selected = 0 if options else -1
        self.label = label
        self.opened = False
        self.visible = True
        self.on_select: Optional[Callable[[int, str], None]] = None

    def draw(
        self,
        screen: pygame.Surface,
        font: pygame.font.Font,
        small_font: pygame.font.Font,
    ):
        if not self.visible:
            return

        # Метка
        if self.label:
            label_surf = small_font.render(self.label, True, COLORS["text"])
            screen.blit(label_surf, (self.rect.x, self.rect.y - 18))

        # Основное поле
        pygame.draw.rect(screen, COLORS["bg_input"], self.rect, border_radius=4)
        pygame.draw.rect(screen, COLORS["border"], self.rect, 1, border_radius=4)

        # Выбранный текст
        if 0 <= self.selected < len(self.options):
            text = self.options[self.selected]
        else:
            text = "Выберите..."
        text_surf = font.render(text, True, COLORS["text"])
        screen.blit(text_surf, (self.rect.x + 8, self.rect.y + 8))

        # Стрелка
        arrow = "▼" if self.opened else "▶"
        arrow_surf = font.render(arrow, True, COLORS["text_dim"])
        screen.blit(arrow_surf, (self.rect.right - 20, self.rect.y + 8))

        # Выпадающий список
        if self.opened:
            list_height = len(self.options) * 28
            list_rect = pygame.Rect(
                self.rect.x, self.rect.bottom, self.rect.width, list_height
            )
            pygame.draw.rect(screen, COLORS["bg_panel"], list_rect, border_radius=4)
            pygame.draw.rect(screen, COLORS["border"], list_rect, 1, border_radius=4)

            for i, option in enumerate(self.options):
                opt_rect = pygame.Rect(
                    self.rect.x, self.rect.bottom + i * 28, self.rect.width, 28
                )
                if opt_rect.collidepoint(pygame.mouse.get_pos()):
                    pygame.draw.rect(screen, COLORS["bg_hover"], opt_rect)
                opt_surf = font.render(option, True, COLORS["text"])
                screen.blit(opt_surf, (opt_rect.x + 8, opt_rect.y + 6))

    def handle_event(self, event: pygame.event.Event) -> bool:
        if not self.visible:
            return False

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.rect.collidepoint(event.pos):
                self.opened = not self.opened
                return True
            elif self.opened:
                # Проверяем клик по опциям
                for i, option in enumerate(self.options):
                    opt_rect = pygame.Rect(
                        self.rect.x, self.rect.bottom + i * 28, self.rect.width, 28
                    )
                    if opt_rect.collidepoint(event.pos):
                        self.selected = i
                        self.opened = False
                        if self.on_select:
                            self.on_select(i, option)
                        return True
                self.opened = False
        return False

    def get_selected(self) -> Tuple[int, str]:
        if 0 <= self.selected < len(self.options):
            return self.selected, self.options[self.selected]
        return -1, ""


class ModalDialog:
    """Модальное окно с формой"""

    def __init__(
        self,
        screen: pygame.Surface,
        title: str,
        fields: List[Dict[str, Any]],
        on_confirm: Callable[[Dict[str, str]], None],
        on_cancel: Optional[Callable] = None,
    ):
        self.screen = screen
        self.title = title
        self.on_confirm = on_confirm
        self.on_cancel = on_cancel
        self.active = True

        # Размеры окна
        self.width = 420
        self.field_height = 55
        self.button_height = 50
        self.padding = 20
        self.height = 80 + len(fields) * self.field_height + self.button_height

        screen_w, screen_h = screen.get_size()
        self.rect = pygame.Rect(
            (screen_w - self.width) // 2,
            (screen_h - self.height) // 2,
            self.width,
            self.height,
        )

        # Создаём поля ввода
        self.inputs: Dict[str, Any] = {}
        y = self.rect.y + 60
        for field in fields:
            key = field["key"]
            if field.get("type") == "choice":
                # S143: Выпадающий список для выбора из options
                self.inputs[key] = Dropdown(
                    self.rect.x + self.padding,
                    y,
                    self.width - self.padding * 2,
                    32,
                    options=field.get("options", []),
                    label=field.get("label", key),
                )
            else:
                self.inputs[key] = TextInput(
                    self.rect.x + self.padding,
                    y,
                    self.width - self.padding * 2,
                    32,
                    label=field.get("label", key),
                    placeholder=field.get("placeholder", ""),
                    value=str(field.get("value", "")),
                    numeric=field.get("type") in ("int", "float"),
                )
            y += self.field_height

        # Кнопки
        btn_y = self.rect.bottom - 45
        self.btn_ok = Button(
            self.rect.right - 180,
            btn_y,
            80,
            35,
            "OK",
            color_key="btn_primary",
            on_click=self._on_ok,
        )
        self.btn_cancel = Button(
            self.rect.right - 90,
            btn_y,
            80,
            35,
            "Отмена",
            color_key="btn_danger",
            on_click=self._on_cancel,
        )

    def _on_ok(self):
        result = {}
        for k, v in self.inputs.items():
            if isinstance(v, Dropdown):
                _, val = v.get_selected()
                result[k] = val
            else:
                result[k] = v.get_value()
        self.on_confirm(result)
        self.active = False

    def _on_cancel(self):
        if self.on_cancel:
            self.on_cancel()
        self.active = False

    def draw(self, font: pygame.font.Font, small_font: pygame.font.Font):
        if not self.active:
            return

        # Затемнение фона
        overlay = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 150))
        self.screen.blit(overlay, (0, 0))

        # Окно
        pygame.draw.rect(self.screen, COLORS["bg_panel"], self.rect, border_radius=10)
        pygame.draw.rect(self.screen, COLORS["border"], self.rect, 2, border_radius=10)

        # Заголовок
        title_surf = font.render(self.title, True, COLORS["text_highlight"])
        self.screen.blit(title_surf, (self.rect.x + self.padding, self.rect.y + 15))

        # Поля ввода
        for inp in self.inputs.values():
            if isinstance(inp, Dropdown):
                inp.draw(self.screen, font, small_font)
            else:
                inp.draw(self.screen, font, small_font)

        # Кнопки
        self.btn_ok.draw(self.screen, font)
        self.btn_cancel.draw(self.screen, font)

    def handle_event(self, event: pygame.event.Event) -> bool:
        if not self.active:
            return False

        # Клик вне окна - закрыть
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if not self.rect.collidepoint(event.pos):
                # S143 FIX: Если открыт Dropdown, клик вне окна закрывает список, а не диалог
                is_dropdown_opened = any(
                    hasattr(inp, 'opened') and inp.opened 
                    for inp in self.inputs.values()
                )
                if is_dropdown_opened:
                    for inp in self.inputs.values():
                        if hasattr(inp, 'opened'):
                            inp.opened = False
                    return True
                else:
                    self._on_cancel()
                    return True

        # Поля ввода
        for inp in self.inputs.values():
            if inp.handle_event(event):
                return True

        # Кнопки
        if self.btn_ok.handle_event(event) or self.btn_cancel.handle_event(event):
            return True

        return False


class DropDownMenu:
    """Выпадающее меню с пунктами и разделителями"""

    def __init__(self, x: int, y: int, items: List[Dict[str, Any]]):
        """
        items: [{"label": "Сохранить", "action": lambda: ..., "shortcut": "Ctrl+S"},
                {"type": "separator"}, ...]
        """
        self.items = items
        self.item_height = 28
        self.padding = 4
        self.active = True

        # вычисляем ширину по самому длинному пункту
        max_w = 160
        for item in self.items:
            if item.get("type") == "separator":
                continue
            text = item.get("label", "")
            sc = item.get("shortcut", "")
            w = len(text) * 8 + len(sc) * 8 + 40
            if w > max_w:
                max_w = w

        visible_count = sum(1 for i in self.items if i.get("type") != "separator")
        self.height = (
            visible_count * self.item_height
            + (len(self.items) - visible_count) * 10
            + self.padding * 2
        )
        self.width = max_w
        self.rect = pygame.Rect(x, y, self.width, self.height)

    def draw(self, screen: pygame.Surface, font: pygame.font.Font):
        if not self.active:
            return

        # фон
        bg = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        bg.fill((35, 35, 42, 245))
        screen.blit(bg, self.rect.topleft)
        pygame.draw.rect(screen, COLORS["border"], self.rect, 1, border_radius=4)

        mx, my = pygame.mouse.get_pos()
        y = self.rect.y + self.padding

        for item in self.items:
            if item.get("type") == "separator":
                pygame.draw.line(
                    screen,
                    COLORS["border"],
                    (self.rect.x + 8, y + 4),
                    (self.rect.right - 8, y + 4),
                )
                y += 10
                continue

            item_rect = pygame.Rect(self.rect.x, y, self.width, self.item_height)

            # подсветка при наведении
            if item_rect.collidepoint(mx, my):
                pygame.draw.rect(screen, COLORS["bg_hover"], item_rect, border_radius=3)

            # метка
            label = item.get("label", "")
            disabled = item.get("disabled", False)
            color = COLORS["text_dim"] if disabled else COLORS["text"]
            text_surf = font.render(label, True, color)
            screen.blit(text_surf, (item_rect.x + 12, item_rect.y + 6))

            # горячая клавиша
            sc = item.get("shortcut", "")
            if sc:
                sc_surf = font.render(sc, True, COLORS["text_dim"])
                screen.blit(
                    sc_surf,
                    (item_rect.right - sc_surf.get_width() - 12, item_rect.y + 6),
                )

            y += self.item_height

    def handle_event(self, event: pygame.event.Event) -> Optional[str]:
        """Возвращает action если пункт выбран, 'close' если клик вне меню"""
        if not self.active:
            return None

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if not self.rect.collidepoint(event.pos):
                self.active = False
                return "close"

            y = self.rect.y + self.padding
            for item in self.items:
                if item.get("type") == "separator":
                    y += 10
                    continue
                item_rect = pygame.Rect(self.rect.x, y, self.width, self.item_height)
                if item_rect.collidepoint(event.pos):
                    self.active = False
                    if item.get("disabled"):
                        return None
                    action = item.get("action")
                    if action:
                        action()
                    return "selected"
                y += self.item_height

        return None


class Toolbar:
    """Панель инструментов с группами кнопок"""

    def __init__(self, x: int, y: int, width: int, height: int = 40):
        self.rect = pygame.Rect(x, y, width, height)
        self.buttons: List[Button] = []
        self.groups: Dict[str, List[Button]] = {}
        self.current_group = ""

    def add_button(self, button: Button, group: str = ""):
        """Добавляет кнопку в тулбар"""
        self.buttons.append(button)
        if group:
            if group not in self.groups:
                self.groups[group] = []
            self.groups[group].append(button)

    def add_separator(self, x: int):
        """Добавляет разделитель"""
        pass  # Визуальный разделитель рисуется при отрисовке

    def draw(self, screen: pygame.Surface, font: pygame.font.Font):
        # Фон
        pygame.draw.rect(screen, COLORS["bg_menu"], self.rect)
        pygame.draw.line(
            screen,
            COLORS["border"],
            (self.rect.x, self.rect.bottom - 1),
            (self.rect.right, self.rect.bottom - 1),
        )

        # Кнопки
        for btn in self.buttons:
            btn.draw(screen, font)

    def handle_event(self, event: pygame.event.Event) -> bool:
        for btn in self.buttons:
            if btn.handle_event(event):
                return True
        return False


class Slider:
    """Слайдер для калибровки психики NPC (M0)"""

    def __init__(
        self,
        x: int,
        y: int,
        w: int,
        h: int,
        min_val: float,
        max_val: float,
        value: float,
        label: str,
        is_float: bool = True,
    ):
        self.rect = pygame.Rect(x, y, w, h)
        self.min_val = min_val
        self.max_val = max_val
        self.value = value
        self.label = label
        self.is_float = is_float
        self.dragging = False

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.MOUSEBUTTONDOWN:
            if self.rect.collidepoint(event.pos):
                self.dragging = True
                self._update_value_from_mouse(event.pos[0])
        elif event.type == pygame.MOUSEBUTTONUP:
            self.dragging = False
        elif event.type == pygame.MOUSEMOTION:
            if self.dragging:
                self._update_value_from_mouse(event.pos[0])

    def _update_value_from_mouse(self, mouse_x: int) -> None:
        rel_x = max(0, min(mouse_x - self.rect.x, self.rect.width))
        ratio = rel_x / self.rect.width if self.rect.width > 0 else 0
        new_val = self.min_val + (self.max_val - self.min_val) * ratio
        self.value = round(new_val, 2) if self.is_float else int(round(new_val))

    def draw(self, screen: pygame.Surface, font: pygame.font.Font) -> None:
        # Фон
        pygame.draw.rect(screen, COLORS["bg_panel"], self.rect, border_radius=4)
        # Заполнение
        val_range = self.max_val - self.min_val
        ratio = (self.value - self.min_val) / val_range if val_range != 0 else 0
        fill_w = int(self.rect.width * ratio)
        fill_rect = pygame.Rect(self.rect.x, self.rect.y, fill_w, self.rect.height)
        pygame.draw.rect(
            screen, COLORS.get("btn_info", COLORS["btn_primary"]), fill_rect, border_radius=4
        )
        # Рамка
        pygame.draw.rect(screen, COLORS["border"], self.rect, 2, border_radius=4)
        # Текст
        val_str = f"{self.value:.2f}" if self.is_float else str(self.value)
        label_surf = font.render(
            f"{self.label}: {val_str}", True, COLORS.get("text_default", COLORS["text_highlight"])
        )
        screen.blit(label_surf, (self.rect.x, self.rect.y - 22))


class PropertyPanel:
    """Панель свойств выбранного объекта"""

    def __init__(self, x: int, y: int, width: int, height: int):
        self.rect = pygame.Rect(x, y, width, height)
        self.title = "СВОЙСТВА"
        self.content: List[Dict[str, Any]] = []
        self.buttons: List[Button] = []
        self.scroll_y = 0

    def set_content(self, title: str, items: List[Dict[str, Any]]):
        """Устанавливает содержимое панели"""
        self.title = title
        self.content = items
        self.buttons.clear()

        # Создаём кнопки для действий
        y = self.rect.y + 60
        for item in items:
            if item.get("type") in ("toggle", "button"):
                btn = Button(
                    self.rect.x + 15,
                    y,
                    110,
                    28,
                    text=item["label"],
                    color_key="btn_success" if item.get("value") else "btn_danger",
                )
                self.buttons.append((btn, item))
            if item.get("type") == "image":
                y += item.get("h", 64) + 10
            else:
                y += 32

    def draw(
        self,
        screen: pygame.Surface,
        font: pygame.font.Font,
        small_font: pygame.font.Font,
    ):
        # Фон
        pygame.draw.rect(screen, COLORS["bg_panel"], self.rect)
        pygame.draw.line(
            screen,
            COLORS["border"],
            (self.rect.left, self.rect.y),
            (self.rect.left, self.rect.bottom),
            2,
        )

        # Заголовок
        title_surf = font.render(self.title, True, COLORS["text_highlight"])
        screen.blit(title_surf, (self.rect.x + 15, self.rect.y + 15))

        # Содержимое
        if not self.content:
            hint = small_font.render("Выберите объект", True, COLORS["text_dim"])
            screen.blit(hint, (self.rect.x + 15, self.rect.y + 50))
            return

        y = self.rect.y + 50
        for item in self.content:
            if item.get("type") == "label":
                # Простая метка
                text = item.get("text", "")
                color = COLORS["text"] if item.get("important") else COLORS["text_dim"]
                surf = font.render(text, True, color)
                screen.blit(surf, (self.rect.x + 15, y))
                y += 22

            elif item.get("type") == "value":
                # Пара значений
                label = item.get("label", "")
                value = str(item.get("value", ""))
                label_surf = small_font.render(label + ":", True, COLORS["text_dim"])
                value_surf = font.render(value, True, COLORS["text"])
                screen.blit(label_surf, (self.rect.x + 15, y))
                screen.blit(value_surf, (self.rect.x + 100, y))
                y += 24

            elif item.get("type") == "image":
                # S171: Превью портрета (Спрайтшит)
                surf = item.get("surface")
                w = item.get("w", 64)
                h = item.get("h", 64)
                if surf:
                    try:
                        scaled = pygame.transform.scale(surf, (w, h))
                        screen.blit(scaled, (self.rect.x + 15, y))
                    except Exception:
                        pass
                y += h + 10

            elif item.get("type") == "section":
                # Раздел
                y += 5
                pygame.draw.line(
                    screen,
                    COLORS["border"],
                    (self.rect.x + 10, y),
                    (self.rect.right - 10, y),
                )
                y += 8
                sect_surf = font.render(
                    item.get("text", ""), True, COLORS["text_highlight"]
                )
                screen.blit(sect_surf, (self.rect.x + 15, y))
                y += 26

            elif item.get("type") in ("toggle", "button"):
                # Переключатель или Кнопка
                y += 5
                if item.get("type") == "button":
                    color = COLORS.get("btn_primary", (50, 90, 130))
                else:
                    color = (
                        COLORS["btn_success"] if item.get("value") else COLORS["btn_danger"]
                    )
                btn_rect = pygame.Rect(self.rect.x + 15, y, 180, 28)
                pygame.draw.rect(screen, color, btn_rect, border_radius=4)
                text_surf = font.render(item["label"], True, COLORS["text_highlight"])
                screen.blit(text_surf, (btn_rect.x + 10, btn_rect.y + 6))
                y += 35

            y += 5

    def handle_event(self, event: pygame.event.Event) -> Optional[str]:
        """Возвращает ключ действия если кнопка нажата. Y-позиции должны совпадать с draw()."""
        if event.type != pygame.MOUSEBUTTONDOWN or event.button != 1:
            return None

        y = self.rect.y + 50
        for item in self.content:
            if item.get("type") in ("toggle", "button"):
                y += 5  # отступ перед toggle — как в draw
                btn_rect = pygame.Rect(self.rect.x + 15, y, 110, 28)
                if btn_rect.collidepoint(event.pos):
                    return item.get("action")
                y += 35
            elif item.get("type") == "label":
                y += 22
            elif item.get("type") == "value":
                y += 24
            elif item.get("type") == "image":
                y += item.get("h", 64) + 10
            elif item.get("type") == "section":
                y += 5 + 8 + 26  # разделитель + линия + текст — как в draw
            y += 5  # общий отступ после каждого элемента — как в draw
        return None
