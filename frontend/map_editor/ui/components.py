"""
map_editor/ui/components.py
Базовые атомарные виджеты UI: Button, TextInput, Dropdown, Slider и т.д.
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
    def __init__(self, x: int, y: int, width: int, height: int, text: str = "", icon: str = "", color_key: str = "btn_primary", on_click: Optional[Callable] = None, tooltip: str = ""):
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
        if not self.visible: return
        if not self.enabled: color = (50, 50, 55)
        elif self.hovered: color = COLORS.get(f"{self.color_key}_hover", COLORS["btn_primary_hover"])
        else: color = COLORS.get(self.color_key, COLORS["btn_primary"])
        pygame.draw.rect(screen, color, self.rect, border_radius=6)
        pygame.draw.rect(screen, COLORS["border"], self.rect, 1, border_radius=6)
        text_to_render = self.icon if self.icon else self.text
        text_color = COLORS["text_dim"] if not self.enabled else COLORS["text_highlight"]
        text_surf = font.render(text_to_render, True, text_color)
        text_rect = text_surf.get_rect(center=self.rect.center)
        screen.blit(text_surf, text_rect)

    def handle_event(self, event: pygame.event.Event) -> bool:
        if not self.visible or not self.enabled: return False
        if event.type == pygame.MOUSEMOTION: self.hovered = self.rect.collidepoint(event.pos)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.rect.collidepoint(event.pos):
                if self.on_click: self.on_click()
                return True
        return False

class ToggleButton(Button):
    """Кнопка-переключатель (вкл/выкл)"""
    def __init__(self, x: int, y: int, width: int, height: int, text: str = "", icon: str = "", on_toggle: Optional[Callable[[bool], None]] = None, initial_state: bool = False):
        super().__init__(x, y, width, height, text, icon, "btn_secondary")
        self.state = initial_state
        self.on_toggle = on_toggle

    def draw(self, screen: pygame.Surface, font: pygame.font.Font):
        self.color_key = "btn_primary" if self.state else "btn_secondary"
        super().draw(screen, font)

    def handle_event(self, event: pygame.event.Event) -> bool:
        if not self.visible or not self.enabled: return False
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.rect.collidepoint(event.pos):
                self.state = not self.state
                if self.on_toggle: self.on_toggle(self.state)
                return True
        return False

class TextInput:
    """Поле ввода текста"""
    def __init__(self, x: int, y: int, width: int, height: int = 32, label: str = "", placeholder: str = "", value: str = "", numeric: bool = False):
        self.rect = pygame.Rect(x, y, width, height)
        self.label = label
        self.placeholder = placeholder
        self.value = value
        self.numeric = numeric
        self.active = False
        self.cursor_pos = len(value)
        self.visible = True

    def draw(self, screen: pygame.Surface, font: pygame.font.Font, small_font: pygame.font.Font):
        if not self.visible: return
        if self.label:
            label_surf = small_font.render(self.label, True, COLORS["text"])
            screen.blit(label_surf, (self.rect.x, self.rect.y - 18))
        color = COLORS["bg_input_active"] if self.active else COLORS["bg_input"]
        pygame.draw.rect(screen, color, self.rect, border_radius=4)
        border_color = COLORS["border_highlight"] if self.active else COLORS["border"]
        pygame.draw.rect(screen, border_color, self.rect, 2 if self.active else 1, border_radius=4)
        display_text = self.value
        if self.active: display_text += "|"
        elif not self.value: display_text = self.placeholder
        text_color = COLORS["text"] if (self.value or self.active) else COLORS["text_dim"]
        text_surf = font.render(display_text, True, text_color)
        if text_surf.get_width() > self.rect.width - 16:
            text_surf = font.render("..." + display_text[-20:], True, text_color)
        screen.blit(text_surf, (self.rect.x + 8, self.rect.y + 8))

    def handle_event(self, event: pygame.event.Event) -> bool:
        if not self.visible: return False
        if event.type == pygame.MOUSEBUTTONDOWN:
            was_active = self.active
            self.active = self.rect.collidepoint(event.pos)
            if self.active != was_active: return True
        elif event.type == pygame.KEYDOWN and self.active:
            if event.key == pygame.K_BACKSPACE:
                if self.cursor_pos > 0:
                    self.value = self.value[: self.cursor_pos - 1] + self.value[self.cursor_pos :]
                    self.cursor_pos -= 1
            elif event.key == pygame.K_DELETE:
                if self.cursor_pos < len(self.value):
                    self.value = self.value[: self.cursor_pos] + self.value[self.cursor_pos + 1 :]
            elif event.key == pygame.K_LEFT: self.cursor_pos = max(0, self.cursor_pos - 1)
            elif event.key == pygame.K_RIGHT: self.cursor_pos = min(len(self.value), self.cursor_pos + 1)
            elif event.key == pygame.K_HOME: self.cursor_pos = 0
            elif event.key == pygame.K_END: self.cursor_pos = len(self.value)
            elif event.unicode.isprintable():
                if self.numeric and not (event.unicode.isdigit() or event.unicode in "-.+."): return True
                self.value = self.value[: self.cursor_pos] + event.unicode + self.value[self.cursor_pos :]
                self.cursor_pos += 1
            return True
        return False

    def get_value(self) -> str: return self.value
    def get_int(self) -> int:
        try: return int(self.value)
        except ValueError: return 0
    def get_float(self) -> float:
        try: return float(self.value)
        except ValueError: return 0.0

class Dropdown:
    """Выпадающий список"""
    def __init__(self, x: int, y: int, width: int, height: int = 32, options: List[str] = None, label: str = ""):
        self.rect = pygame.Rect(x, y, width, height)
        self.options = options or []
        self.selected = 0 if options else -1
        self.label = label
        self.opened = False
        self.visible = True
        self.on_select: Optional[Callable[[int, str], None]] = None

    def draw(self, screen: pygame.Surface, font: pygame.font.Font, small_font: pygame.font.Font):
        if not self.visible: return
        if self.label:
            label_surf = small_font.render(self.label, True, COLORS["text"])
            screen.blit(label_surf, (self.rect.x, self.rect.y - 18))
        pygame.draw.rect(screen, COLORS["bg_input"], self.rect, border_radius=4)
        pygame.draw.rect(screen, COLORS["border"], self.rect, 1, border_radius=4)
        if 0 <= self.selected < len(self.options): text = self.options[self.selected]
        else: text = "Выберите..."
        text_surf = font.render(text, True, COLORS["text"])
        screen.blit(text_surf, (self.rect.x + 8, self.rect.y + 8))
        arrow = "▼" if self.opened else "▶"
        arrow_surf = font.render(arrow, True, COLORS["text_dim"])
        screen.blit(arrow_surf, (self.rect.right - 20, self.rect.y + 8))
        if self.opened:
            list_height = len(self.options) * 28
            list_rect = pygame.Rect(self.rect.x, self.rect.bottom, self.rect.width, list_height)
            pygame.draw.rect(screen, COLORS["bg_panel"], list_rect, border_radius=4)
            pygame.draw.rect(screen, COLORS["border"], list_rect, 1, border_radius=4)
            for i, option in enumerate(self.options):
                opt_rect = pygame.Rect(self.rect.x, self.rect.bottom + i * 28, self.rect.width, 28)
                if opt_rect.collidepoint(pygame.mouse.get_pos()):
                    pygame.draw.rect(screen, COLORS["bg_hover"], opt_rect)
                opt_surf = font.render(option, True, COLORS["text"])
                screen.blit(opt_surf, (opt_rect.x + 8, opt_rect.y + 6))

    def handle_event(self, event: pygame.event.Event) -> bool:
        if not self.visible: return False
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.rect.collidepoint(event.pos):
                self.opened = not self.opened
                return True
            elif self.opened:
                for i, option in enumerate(self.options):
                    opt_rect = pygame.Rect(self.rect.x, self.rect.bottom + i * 28, self.rect.width, 28)
                    if opt_rect.collidepoint(event.pos):
                        self.selected = i
                        self.opened = False
                        if self.on_select: self.on_select(i, option)
                        return True
                self.opened = False
        return False

    def get_selected(self) -> Tuple[int, str]:
        if 0 <= self.selected < len(self.options): return self.selected, self.options[self.selected]
        return -1, ""

class DropDownMenu:
    """Выпадающее меню с пунктами и разделителями"""
    def __init__(self, x: int, y: int, items: List[Dict[str, Any]]):
        self.items = items
        self.item_height = 28
        self.padding = 4
        self.active = True
        max_w = 160
        for item in self.items:
            if item.get("type") == "separator": continue
            text = item.get("label", "")
            sc = item.get("shortcut", "")
            w = len(text) * 8 + len(sc) * 8 + 40
            if w > max_w: max_w = w
        visible_count = sum(1 for i in self.items if i.get("type") != "separator")
        self.height = visible_count * self.item_height + (len(self.items) - visible_count) * 10 + self.padding * 2
        self.width = max_w
        self.rect = pygame.Rect(x, y, self.width, self.height)

    def draw(self, screen: pygame.Surface, font: pygame.font.Font):
        if not self.active: return
        bg = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        bg.fill((35, 35, 42, 245))
        screen.blit(bg, self.rect.topleft)
        pygame.draw.rect(screen, COLORS["border"], self.rect, 1, border_radius=4)
        mx, my = pygame.mouse.get_pos()
        y = self.rect.y + self.padding
        for item in self.items:
            if item.get("type") == "separator":
                pygame.draw.line(screen, COLORS["border"], (self.rect.x + 8, y + 4), (self.rect.right - 8, y + 4))
                y += 10
                continue
            item_rect = pygame.Rect(self.rect.x, y, self.width, self.item_height)
            if item_rect.collidepoint(mx, my):
                pygame.draw.rect(screen, COLORS["bg_hover"], item_rect, border_radius=3)
            label = item.get("label", "")
            disabled = item.get("disabled", False)
            color = COLORS["text_dim"] if disabled else COLORS["text"]
            text_surf = font.render(label, True, color)
            screen.blit(text_surf, (item_rect.x + 12, item_rect.y + 6))
            sc = item.get("shortcut", "")
            if sc:
                sc_surf = font.render(sc, True, COLORS["text_dim"])
                screen.blit(sc_surf, (item_rect.right - sc_surf.get_width() - 12, item_rect.y + 6))
            y += self.item_height

    def handle_event(self, event: pygame.event.Event) -> Optional[str]:
        if not self.active: return None
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
                    if item.get("disabled"): return None
                    action = item.get("action")
                    if action: action()
                    return "selected"
                y += self.item_height
        return None

class Slider:
    """Слайдер для калибровки психики NPC (M0)"""
    def __init__(self, x: int, y: int, w: int, h: int, min_val: float, max_val: float, value: float, label: str, is_float: bool = True):
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
        pygame.draw.rect(screen, COLORS["bg_panel"], self.rect, border_radius=4)
        val_range = self.max_val - self.min_val
        ratio = (self.value - self.min_val) / val_range if val_range != 0 else 0
        fill_w = int(self.rect.width * ratio)
        fill_rect = pygame.Rect(self.rect.x, self.rect.y, fill_w, self.rect.height)
        pygame.draw.rect(screen, COLORS.get("btn_info", COLORS["btn_primary"]), fill_rect, border_radius=4)
        pygame.draw.rect(screen, COLORS["border"], self.rect, 2, border_radius=4)
        val_str = f"{self.value:.2f}" if self.is_float else str(self.value)
        label_surf = font.render(f"{self.label}: {val_str}", True, COLORS.get("text_default", COLORS["text_highlight"]))
        screen.blit(label_surf, (self.rect.x, self.rect.y - 22))