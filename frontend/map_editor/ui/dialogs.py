"""
map_editor/ui/dialogs.py
Модальные окна: ModalDialog, CalibrationPanel
"""
from typing import Any, Callable, Dict, List, Optional
import pygame
from ui.components import Button, COLORS, Slider, TextInput, Dropdown

class ModalDialog:
    """Модальное окно с формой"""
    def __init__(self, screen: pygame.Surface, title: str, fields: List[Dict[str, Any]], on_confirm: Callable[[Dict[str, str]], None], on_cancel: Optional[Callable] = None):
        self.screen = screen
        self.title = title
        self.on_confirm = on_confirm
        self.on_cancel = on_cancel
        self.active = True
        self.width = 420
        self.field_height = 55
        self.button_height = 50
        self.padding = 20
        self.height = 80 + len(fields) * self.field_height + self.button_height
        screen_w, screen_h = screen.get_size()
        self.rect = pygame.Rect((screen_w - self.width) // 2, (screen_h - self.height) // 2, self.width, self.height)
        self.inputs: Dict[str, Any] = {}
        y = self.rect.y + 60
        for field in fields:
            key = field["key"]
            if field.get("type") == "choice":
                self.inputs[key] = Dropdown(self.rect.x + self.padding, y, self.width - self.padding * 2, 32, options=field.get("options", []), label=field.get("label", key))
            else:
                self.inputs[key] = TextInput(self.rect.x + self.padding, y, self.width - self.padding * 2, 32, label=field.get("label", key), placeholder=field.get("placeholder", ""), value=str(field.get("value", "")), numeric=field.get("type") in ("int", "float"))
            y += self.field_height
        btn_y = self.rect.bottom - 45
        self.btn_ok = Button(self.rect.right - 180, btn_y, 80, 35, "OK", color_key="btn_primary", on_click=self._on_ok)
        self.btn_cancel = Button(self.rect.right - 90, btn_y, 80, 35, "Отмена", color_key="btn_danger", on_click=self._on_cancel)

    def _on_ok(self):
        result = {}
        for k, v in self.inputs.items():
            if isinstance(v, Dropdown):
                _, val = v.get_selected()
                result[k] = val
            else: result[k] = v.get_value()
        self.on_confirm(result)
        self.active = False

    def _on_cancel(self):
        if self.on_cancel: self.on_cancel()
        self.active = False

    def draw(self, font: pygame.font.Font, small_font: pygame.font.Font):
        if not self.active: return
        overlay = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 150))
        self.screen.blit(overlay, (0, 0))
        pygame.draw.rect(self.screen, COLORS["bg_panel"], self.rect, border_radius=10)
        pygame.draw.rect(self.screen, COLORS["border"], self.rect, 2, border_radius=10)
        title_surf = font.render(self.title, True, COLORS["text_highlight"])
        self.screen.blit(title_surf, (self.rect.x + self.padding, self.rect.y + 15))
        for inp in self.inputs.values():
            if isinstance(inp, Dropdown): inp.draw(self.screen, font, small_font)
            else: inp.draw(self.screen, font, small_font)
        self.btn_ok.draw(self.screen, font)
        self.btn_cancel.draw(self.screen, font)

    def handle_event(self, event: pygame.event.Event) -> bool:
        if not self.active: return False
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if not self.rect.collidepoint(event.pos):
                is_dropdown_opened = any(hasattr(inp, 'opened') and inp.opened for inp in self.inputs.values())
                if is_dropdown_opened:
                    for inp in self.inputs.values():
                        if hasattr(inp, 'opened'): inp.opened = False
                    return True
                else:
                    self._on_cancel()
                    return True
        for inp in self.inputs.values():
            if inp.handle_event(event): return True
        if self.btn_ok.handle_event(event) or self.btn_cancel.handle_event(event): return True
        return False


# Описания параметров для UI (Концепция "Темпа истории")
PARAM_DESCRIPTIONS = {
    "willpower": "ВОЛЯ: Удерживает выбранное направление при конфликте мотивов.\n↑ Дольше сопротивляется давлению, реже меняет решение.\nСвязано с: Контроль, Порог слома.",
    "breakpoint": "ПОРОГ СЛОМА: Граница, после которой прежняя стратегия рушится.\n↑ Дольше держит старую модель поведения.\nПосле слома — резкий фазовый переход.",
    "loyalty_true": "ИСТИННАЯ ЛОЯЛЬНОСТЬ: Насколько цель встроена в ядро ценностей.\nНе текущее доверие! NPC может ненавидеть, но оставаться лояльным.\n(0-100)",
    "control": "КОНТРОЛЬ: Способность подавлять импульсы и страхи.\n↑ Меньше подвержен панике, точнее выполняет план.\nСвязано с: Воля.",
    "significance": "ЗНАЧИМОСТЬ: Множитель важности происходящего.\n↑ Сильнее реакция на события. Не любовь, а вес в системе.\nЗначимость × Страх = мощная комбинация.",
    "fear": "СТРАХ: Сила давления угрозы над другими мотивами.\n↑ Приоритет выживания/бегства. Конкурирует с Желанием.\nПри низком Контроле парализует действие.",
    "desire": "ЖЕЛАНИЕ: Сила притяжения цели.\n↑ Готовность рисковать ради результата.\nКонкурирует со Страхом."
}

class CalibrationPanel:
    """Модальная панель для редактирования psyche и drives NPC"""
    def __init__(self, screen: pygame.Surface, npc_id: str, npc_name: str, psyche: Dict, drives: Dict):
        self.screen = screen
        self.npc_id = npc_id
        self.npc_name = npc_name
        self.active = True
        self.width = 540
        self.height = 580
        screen_w, screen_h = screen.get_size()
        self.rect = pygame.Rect((screen_w - self.width) // 2, (screen_h - self.height) // 2, self.width, self.height)
        self.title = f"🧠 Калибровка: {self.npc_name}"
        self.warning_text = "Это лабораторные ручки. В модели они взаимодействуют."
        self.hovered_slider_key: Optional[str] = None
        self.sliders = []
        y = self.rect.y + 90
        self.sliders.append({"slider": Slider(self.rect.x + 20, y, 500, 20, 0, 100, psyche.get("willpower", 50), "Воля (willpower)", is_float=False), "key": "willpower"})
        y += 50
        self.sliders.append({"slider": Slider(self.rect.x + 20, y, 500, 20, 0, 100, psyche.get("breakpoint", 65), "Порог слома (breakpoint)", is_float=False), "key": "breakpoint"})
        y += 50
        self.sliders.append({"slider": Slider(self.rect.x + 20, y, 500, 20, 0, 100, float(psyche.get("loyalty_true", 0.0)), "Истинная лояльность (loyalty_true)", is_float=False), "key": "loyalty_true"})
        y += 60
        self.sliders.append({"slider": Slider(self.rect.x + 20, y, 500, 20, 0.0, 1.0, drives.get("control", 0.3), "Контроль (control)"), "key": "control"})
        y += 50
        self.sliders.append({"slider": Slider(self.rect.x + 20, y, 500, 20, 0.0, 1.0, drives.get("significance", 0.3), "Значимость (significance)"), "key": "significance"})
        y += 50
        self.sliders.append({"slider": Slider(self.rect.x + 20, y, 500, 20, 0.0, 1.0, drives.get("fear", 0.3), "Страх (fear)"), "key": "fear"})
        y += 50
        self.sliders.append({"slider": Slider(self.rect.x + 20, y, 500, 20, 0.0, 1.0, drives.get("desire", 0.3), "Желание (desire)"), "key": "desire"})
        self.btn_save = Button(self.rect.x + 280, self.rect.y + 520, 110, 35, "Сохранить")
        self.btn_cancel = Button(self.rect.x + 400, self.rect.y + 520, 110, 35, "Отмена")
        self.on_save: Optional[Callable[[Dict, Dict], None]] = None

    def handle_event(self, event: pygame.event.Event) -> None:
        if not self.active: return
        mouse_pos = pygame.mouse.get_pos()
        self.hovered_slider_key = None
        for item in self.sliders:
            slider = item["slider"]
            hover_rect = pygame.Rect(slider.rect.x, slider.rect.y - 25, slider.rect.width, slider.rect.height + 25)
            if hover_rect.collidepoint(mouse_pos): self.hovered_slider_key = item["key"]
            slider.handle_event(event)
        if event.type == pygame.MOUSEBUTTONDOWN:
            if self.btn_save.rect.collidepoint(event.pos): self._save()
            elif self.btn_cancel.rect.collidepoint(event.pos): self.active = False

    def _save(self) -> None:
        if self.on_save:
            psyche = {"willpower": self.sliders[0]["slider"].value, "breakpoint": self.sliders[1]["slider"].value, "loyalty_true": float(self.sliders[2]["slider"].value)}
            drives = {"control": self.sliders[3]["slider"].value, "significance": self.sliders[4]["slider"].value, "fear": self.sliders[5]["slider"].value, "desire": self.sliders[6]["slider"].value}
            self.on_save(psyche, drives)
        self.active = False

    def draw(self, font: pygame.font.Font, small_font: pygame.font.Font) -> None:
        if not self.active: return
        overlay = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 100))
        self.screen.blit(overlay, (0, 0))
        pygame.draw.rect(self.screen, COLORS["bg_panel"], self.rect, border_radius=8)
        pygame.draw.rect(self.screen, COLORS["border"], self.rect, 2, border_radius=8)
        title_surf = font.render(self.title, True, COLORS["text_highlight"])
        self.screen.blit(title_surf, (self.rect.x + 20, self.rect.y + 15))
        warn_surf = small_font.render(self.warning_text, True, COLORS.get("text_dim", (200, 200, 200)))
        self.screen.blit(warn_surf, (self.rect.x + 20, self.rect.y + 45))
        for item in self.sliders: item["slider"].draw(self.screen, small_font)
        desc_rect = pygame.Rect(self.rect.x + 20, self.rect.y + 420, 500, 90)
        pygame.draw.rect(self.screen, COLORS.get("bg_input", (30, 30, 30)), desc_rect, border_radius=4)
        pygame.draw.rect(self.screen, COLORS["border"], desc_rect, 1, border_radius=4)
        if self.hovered_slider_key and self.hovered_slider_key in PARAM_DESCRIPTIONS:
            desc_text = PARAM_DESCRIPTIONS[self.hovered_slider_key]
        else:
            desc_text = "Наведите курсор на параметр, чтобы увидеть его роль в системе.\n\nЦель: калибровка темпа возникновения истории, а не просто чисел."
        lines = desc_text.split('\n')
        for i, line in enumerate(lines):
            txt_surf = small_font.render(line, True, COLORS.get("text_default", (220, 220, 220)))
            self.screen.blit(txt_surf, (desc_rect.x + 10, desc_rect.y + 10 + i * 20))
        self.btn_save.draw(self.screen, small_font)
        self.btn_cancel.draw(self.screen, small_font)