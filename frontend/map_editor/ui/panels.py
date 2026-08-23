"""
map_editor/ui/panels.py
Составные панели UI: Toolbar, PropertyPanel
"""
from typing import Any, Dict, List, Optional
import pygame
from ui.components import Button, COLORS

class Toolbar:
    """Панель инструментов с группами кнопок"""
    def __init__(self, x: int, y: int, width: int, height: int = 40):
        self.rect = pygame.Rect(x, y, width, height)
        self.buttons: List[Button] = []
        self.groups: Dict[str, List[Button]] = {}
        self.current_group = ""

    def add_button(self, button: Button, group: str = ""):
        self.buttons.append(button)
        if group:
            if group not in self.groups: self.groups[group] = []
            self.groups[group].append(button)

    def add_separator(self, x: int):
        pass

    def draw(self, screen: pygame.Surface, font: pygame.font.Font):
        pygame.draw.rect(screen, COLORS["bg_menu"], self.rect)
        pygame.draw.line(screen, COLORS["border"], (self.rect.x, self.rect.bottom - 1), (self.rect.right, self.rect.bottom - 1))
        for btn in self.buttons: btn.draw(screen, font)

    def handle_event(self, event: pygame.event.Event) -> bool:
        for btn in self.buttons:
            if btn.handle_event(event): return True
        return False

class PropertyPanel:
    """Панель свойств выбранного объекта"""
    def __init__(self, x: int, y: int, width: int, height: int):
        self.rect = pygame.Rect(x, y, width, height)
        self.title = "СВОЙСТВА"
        self.content: List[Dict[str, Any]] = []
        self.buttons: List[Button] = []
        self.scroll_y = 0

    def set_content(self, title: str, items: List[Dict[str, Any]]):
        self.title = title
        self.content = items
        self.buttons.clear()
        y = self.rect.y + 60
        for item in items:
            if item.get("type") in ("toggle", "button"):
                btn = Button(self.rect.x + 15, y, 110, 28, text=item["label"], color_key="btn_success" if item.get("value") else "btn_danger")
                self.buttons.append((btn, item))
            if item.get("type") == "image": y += item.get("h", 64) + 10
            else: y += 32

    def draw(self, screen: pygame.Surface, font: pygame.font.Font, small_font: pygame.font.Font):
        pygame.draw.rect(screen, COLORS["bg_panel"], self.rect)
        pygame.draw.line(screen, COLORS["border"], (self.rect.left, self.rect.y), (self.rect.left, self.rect.bottom), 2)
        title_surf = font.render(self.title, True, COLORS["text_highlight"])
        screen.blit(title_surf, (self.rect.x + 15, self.rect.y + 15))
        if not self.content:
            hint = small_font.render("Выберите объект", True, COLORS["text_dim"])
            screen.blit(hint, (self.rect.x + 15, self.rect.y + 50))
            return
        y = self.rect.y + 50
        for item in self.content:
            if item.get("type") == "label":
                text = item.get("text", "")
                color = COLORS["text"] if item.get("important") else COLORS["text_dim"]
                surf = font.render(text, True, color)
                screen.blit(surf, (self.rect.x + 15, y))
                y += 22
            elif item.get("type") == "value":
                label = item.get("label", "")
                value = str(item.get("value", ""))
                label_surf = small_font.render(label + ":", True, COLORS["text_dim"])
                value_surf = font.render(value, True, COLORS["text"])
                screen.blit(label_surf, (self.rect.x + 15, y))
                screen.blit(value_surf, (self.rect.x + 100, y))
                y += 24
            elif item.get("type") == "image":
                surf = item.get("surface")
                w = item.get("w", 64)
                h = item.get("h", 64)
                if surf:
                    try:
                        scaled = pygame.transform.scale(surf, (w, h))
                        screen.blit(scaled, (self.rect.x + 15, y))
                    except Exception: pass
                y += h + 10
            elif item.get("type") == "section":
                y += 5
                pygame.draw.line(screen, COLORS["border"], (self.rect.x + 10, y), (self.rect.right - 10, y))
                y += 8
                sect_surf = font.render(item.get("text", ""), True, COLORS["text_highlight"])
                screen.blit(sect_surf, (self.rect.x + 15, y))
                y += 26
            elif item.get("type") in ("toggle", "button"):
                y += 5
                if item.get("type") == "button": color = COLORS.get("btn_primary", (50, 90, 130))
                else: color = COLORS["btn_success"] if item.get("value") else COLORS["btn_danger"]
                btn_rect = pygame.Rect(self.rect.x + 15, y, 180, 28)
                pygame.draw.rect(screen, color, btn_rect, border_radius=4)
                text_surf = font.render(item["label"], True, COLORS["text_highlight"])
                screen.blit(text_surf, (btn_rect.x + 10, btn_rect.y + 6))
                y += 35
            y += 5

    def handle_event(self, event: pygame.event.Event) -> Optional[str]:
        if event.type != pygame.MOUSEBUTTONDOWN or event.button != 1: return None
        y = self.rect.y + 50
        for item in self.content:
            if item.get("type") in ("toggle", "button"):
                y += 5
                btn_rect = pygame.Rect(self.rect.x + 15, y, 110, 28)
                if btn_rect.collidepoint(event.pos): return item.get("action")
                y += 35
            elif item.get("type") == "label": y += 22
            elif item.get("type") == "value": y += 24
            elif item.get("type") == "image": y += item.get("h", 64) + 10
            elif item.get("type") == "section": y += 5 + 8 + 26
            y += 5
        return None