"""
path: /frontend/map_editor/visual_casting_editor.py
Назначение: S176 Final. Визуальный редактор портретов с точным пиксельным кропом (Exact Crop).
Автор выбирает файл, выделяет мышью точную область спрайта и кликает по эмоции для назначения.
Зависимости: pygame, tkinter, ui_components, data_manager, sprite_registry
Основные сущности: VisualCastingEditor
"""
import os
import tkinter as tk
from tkinter import filedialog
from typing import Dict, List, Optional, Any, Tuple

import pygame
from ui_components import COLORS, Button, TextInput
from data_manager import STANDARD_EXPRESSIONS
from sprite_registry import sprite_registry

class VisualCastingEditor:
    """Визуальный инструмент для назначения портретов (Sprite Picker)."""

    def __init__(self, screen: pygame.Surface, npc_id: str, casting: Dict, simple_mode: bool = False):
        self.screen = screen
        self.npc_id = npc_id
        self.casting = casting
        self.active = True
        self.on_save = None
        self.simple_mode = simple_mode

        sw, sh = screen.get_size()
        w, h = min(1100, sw - 40), min(700, sh - 40)
        self.rect = pygame.Rect((sw - w) // 2, (sh - h) // 2, w, h)
        
        self._buttons: List[Button] = []
        self._emotion_buttons: List[Button] = []
        
        # Состояние спрайтшита
        self.sheet_surface: Optional[pygame.Surface] = None
        self.sheet_name: str = ""
        
        # Точный прямоугольник выделения (в пикселях оригинала)
        self.current_rect: Optional[pygame.Rect] = None
        self._selected_emotion: str = "neutral"
        
        # Настройки обработки спрайта
        self.threshold: int = 220
        self.outline: int = 1
        
        # Состояние ползунков
        self.dragging_slider: Optional[str] = None
        
        # Зум превью
        self.preview_zoom: float = 1.0
        
        # Локальный кэш назначенных ассетов: {expr_id: [sheet, x, y, w, h]}
        self._assigned: Dict[str, List[Any]] = {}
        self._parse_casting()
        
        # Для выделения мышью (экранные координаты)
        self.drag_start: Optional[Tuple[int, int]] = None
        self.drag_curr: Optional[Tuple[int, int]] = None
        
        # Сообщения (Toast)
        self.message: str = ""
        self.message_timer: int = 0
        
        self._build_ui()
        self._auto_load_sheet()

    def _parse_casting(self):
        """Извлекает уже назначенные ассеты из конфига для превью."""
        self._assigned.clear()
        for expr in STANDARD_EXPRESSIONS:
            asset = None
            if expr["id"] == "neutral":
                fallback = self.casting.get("fallback") or {}
                asset = fallback.get("asset")
            else:
                rule = next((r for r in self.casting.get("rules", []) if r.get("expression_id") == expr["id"]), None)
                if rule:
                    asset = rule.get("asset")
            # Игнорируем пустые дефолты ["", 0, 0]
            if asset and isinstance(asset, list) and len(asset) >= 3 and asset[0]:
                self._assigned[expr["id"]] = asset

    def _auto_load_sheet(self):
        """S176: Автозагрузка спрайтшита, если он уже назначен в конфиге."""
        if not self._assigned:
            return
        # Ищем первый валидный sheet_name
        for asset in self._assigned.values():
            if asset and isinstance(asset, list) and len(asset) >= 5 and asset[0]:
                sheet_name = asset[0]
                # Нормализуем путь для текущей ОС
                abs_path = os.path.normpath(os.path.join(sprite_registry.base_dir, sheet_name.replace("/", os.sep)))
                if not abs_path.endswith(".png"):
                    abs_path += ".png"
                if os.path.exists(abs_path):
                    self._load_sheet(abs_path)
                    self._show_message(f"Автозагрузка: {self.sheet_name}")
                    return

    def _show_message(self, text: str):
        """Показывает временное сообщение на экране."""
        self.message = text
        self.message_timer = pygame.time.get_ticks()

    def _build_ui(self):
        self._buttons.clear()
        self._emotion_buttons.clear()
        
        # Кнопки
        btn_load = Button(self.rect.x + 20, self.rect.bottom - 50, 120, 35, "Выбрать лист", color_key="btn_primary")
        btn_load.action = "load"
        self._buttons.append(btn_load)
        
        btn_save = Button(self.rect.right - 260, self.rect.bottom - 50, 120, 35, "Сохранить", color_key="btn_success")
        btn_save.action = "save"
        self._buttons.append(btn_save)
        
        if self.simple_mode:
            btn_apply = Button(self.rect.right - 130, self.rect.bottom - 50, 120, 35, "Применить", color_key="btn_primary")
            btn_apply.action = "apply_simple"
            self._buttons.append(btn_apply)
        else:
            btn_apply = Button(self.rect.right - 130, self.rect.bottom - 50, 120, 35, "Применить", color_key="btn_primary")
            btn_apply.action = "apply_portrait"
            self._buttons.append(btn_apply)
            
            # Кнопки эмоций
            y = self.rect.y + 60
            for expr in STANDARD_EXPRESSIONS:
                btn = Button(self.rect.x + 20, y, 350, 50, expr["label"], color_key="btn_secondary")
                btn.action = f"expr:{expr['id']}"
                self._emotion_buttons.append(btn)
                y += 60

    def _choose_file(self):
        """Открывает системный проводник для выбора PNG."""
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        file_path = filedialog.askopenfilename(
            title="Выберите спрайтшит",
            initialdir=sprite_registry.base_dir,
            filetypes=[("PNG Images", "*.png"), ("All Files", "*.*")]
        )
        root.destroy()
        if file_path:
            self._load_sheet(file_path)

    def _load_sheet(self, abs_path: str):
        """Загружает выбранный файл в pygame.Surface и вычисляет относительный путь."""
        try:
            self.sheet_surface = pygame.image.load(abs_path).convert_alpha()
            base_dir = os.path.abspath(sprite_registry.base_dir)
            rel_path = os.path.relpath(abs_path, base_dir)
            self.sheet_name = rel_path.replace("\\", "/")
            if self.sheet_name.endswith(".png"):
                self.sheet_name = self.sheet_name[:-4]
            # Сбрасываем выделение при новой загрузке
            self.current_rect = None
            self._show_message(f"Лист загружен: {self.sheet_name}")
        except Exception:
            self.sheet_surface = None
            self.sheet_name = ""
            self._show_message("Ошибка загрузки файла!")

    def handle_event(self, event: pygame.event.Event) -> bool:
        if not self.active: return False
            
        # Масштабирование превью колесом мыши
        if event.type == pygame.MOUSEWHEEL:
            prev_x, prev_y = self.rect.right - 220, self.rect.y + 60
            prev_rect = pygame.Rect(prev_x, prev_y, 200, 280)
            if prev_rect.collidepoint(pygame.mouse.get_pos()):
                if event.y > 0:
                    self.preview_zoom = min(4.0, self.preview_zoom + 0.2)
                else:
                    self.preview_zoom = max(0.5, self.preview_zoom - 0.2)
                return True

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if not self.rect.collidepoint(event.pos):
                self.active = False
                return True
                
            # Обработка кнопок
            for btn in self._buttons + self._emotion_buttons:
                if btn.handle_event(event):
                    if btn.action == "load":
                        self._choose_file()
                    elif btn.action == "save":
                        self._save()
                    elif btn.action == "apply_simple" or btn.action == "apply_portrait":
                        if self.current_rect and self.sheet_name:
                            r = self.current_rect
                            asset = [self.sheet_name, r.x, r.y, r.w, r.h, self.threshold, self.outline]
                            self._assigned[self._selected_emotion] = asset
                            self._show_message("Применено! Нажмите Сохранить для выхода.")
                        else:
                            self._show_message("Сначала выделите область!")
                            return True
                    elif btn.action.startswith("expr:"):
                        self._selected_emotion = btn.action.split(":")[1]
                        self._assign_picked()
                    return True
                    
            # Обработка ползунков
            if self._handle_sliders(event):
                return True
                    
            # Начало выделения на спрайтшите
            if self.sheet_surface:
                sheet_rect = self._get_sheet_rect()
                if sheet_rect.collidepoint(event.pos):
                    self.drag_start = event.pos
                    self.drag_curr = event.pos
                    return True
                    
        elif event.type == pygame.MOUSEMOTION:
            if self.dragging_slider:
                self._update_slider(event.pos)
                return True
                
            if self.drag_start:
                self.drag_curr = event.pos
                
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            if self.dragging_slider:
                self.dragging_slider = None
                return True
                
            if self.drag_start and self.sheet_surface:
                sheet_rect = self._get_sheet_rect()
                # Завершаем выделение только если отпустили внутри листа
                if sheet_rect.collidepoint(event.pos):
                    self._process_selection(sheet_rect)
                self.drag_start = None
                self.drag_curr = None
                return True
                
        return True

    def _handle_sliders(self, event) -> bool:
        """Обрабатывает клики по ползункам настроек."""
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            mx, my = event.pos
            # Ползунок порога
            if self.rect.x + 450 <= mx <= self.rect.x + 650 and abs(my - (self.rect.bottom - 80)) < 15:
                self.dragging_slider = "threshold"
                self._update_slider(event.pos)
                return True
            # Ползунок обводки
            if self.rect.x + 450 <= mx <= self.rect.x + 650 and abs(my - (self.rect.bottom - 50)) < 15:
                self.dragging_slider = "outline"
                self._update_slider(event.pos)
                return True
        return False

    def _update_slider(self, pos):
        """Обновляет значение ползунка в зависимости от позиции мыши."""
        mx, _ = pos
        # Ползунки теперь находятся на x + 450
        rel_x = max(0, min(200, mx - (self.rect.x + 450)))
        if self.dragging_slider == "threshold":
            self.threshold = int(50 + (rel_x / 200) * 205) # Диапазон 50-255
        elif self.dragging_slider == "outline":
            self.outline = int((rel_x / 200) * 6) # Диапазон 0-6

    def _draw_sliders(self, font):
        """Отрисовывает ползунки настроек."""
        x0 = self.rect.x + 450
        
        # Ползунок 1: Порог фона
        y0 = self.rect.bottom - 80
        pygame.draw.rect(self.screen, (50, 50, 50), (x0, y0, 200, 4), border_radius=2)
        t_pos = int(((self.threshold - 50) / 205) * 200)
        pygame.draw.circle(self.screen, (255, 255, 255), (x0 + t_pos, y0 + 2), 8)
        txt1 = font.render(f"Порог фона: {self.threshold}", True, COLORS["text"])
        self.screen.blit(txt1, (x0, y0 - 20))
        
        # Ползунок 2: Обводка
        y1 = self.rect.bottom - 50
        pygame.draw.rect(self.screen, (50, 50, 50), (x0, y1, 200, 4), border_radius=2)
        o_pos = int((self.outline / 6) * 200)
        pygame.draw.circle(self.screen, (255, 255, 255), (x0 + o_pos, y1 + 2), 8)
        txt2 = font.render(f"Обводка: {self.outline}px", True, COLORS["text"])
        self.screen.blit(txt2, (x0, y1 - 20))

    def _get_sheet_rect(self) -> pygame.Rect:
        """Вычисляет прямоугольник для отрисовки листа с сохранением пропорций."""
        max_w, max_h = 450, 500
        w, h = self.sheet_surface.get_size()
        scale = min(max_w / w, max_h / h)
        disp_w, disp_h = int(w * scale), int(h * scale)
        x = self.rect.x + 400
        y = self.rect.y + 60
        return pygame.Rect(x, y, disp_w, disp_h)

    def _process_selection(self, sheet_rect: pygame.Rect):
        """Обрабатывает выделение мышью: переводит экранные координаты в пиксели оригинала."""
        x1 = min(self.drag_start[0], self.drag_curr[0])
        y1 = min(self.drag_start[1], self.drag_curr[1])
        x2 = max(self.drag_start[0], self.drag_curr[0])
        y2 = max(self.drag_start[1], self.drag_curr[1])
        
        orig_w, orig_h = self.sheet_surface.get_size()
        scale_x = orig_w / sheet_rect.width
        scale_y = orig_h / sheet_rect.height
        
        # Переводим в координаты оригинального изображения
        ox1 = int((x1 - sheet_rect.x) * scale_x)
        oy1 = int((y1 - sheet_rect.y) * scale_y)
        ox2 = int((x2 - sheet_rect.x) * scale_x)
        oy2 = int((y2 - sheet_rect.y) * scale_y)
        
        w = ox2 - ox1
        h = oy2 - oy1
        
        # Запоминаем выделение, только если протянули мышь достаточно далеко
        if w > 5 and h > 5:
            self.current_rect = pygame.Rect(ox1, oy1, w, h)
            self._show_message("Область выделена. Кликните по эмоции.")

    def _assign_picked(self):
        """Назначает выделенную область на активную эмоцию."""
        if self.current_rect and self.sheet_name:
            r = self.current_rect
            # Сохраняем вместе с настройками threshold и outline
            self._assigned[self._selected_emotion] = [
                self.sheet_name, r.x, r.y, r.w, r.h, self.threshold, self.outline
            ]
            label = next((e["label"] for e in STANDARD_EXPRESSIONS if e["id"] == self._selected_emotion), "")
            self._show_message(f"Успех! Назначено на: {label}")
        else:
            self._show_message("Ошибка: Сначала выделите область на листе!")

    def _save(self):
        """Формирует и сохраняет структуру visual_casting."""
        new_casting = {"fallback": {}, "rules": []}
        for expr in STANDARD_EXPRESSIONS:
            asset = self._assigned.get(expr["id"])
            if asset and isinstance(asset, list) and len(asset) >= 5:
                # Принудительно сохраняем текущие значения ползунков для всех ассетов
                if len(asset) == 5:
                    asset.extend([self.threshold, self.outline])
                else:
                    asset[5] = self.threshold
                    asset[6] = self.outline
                    
                if expr["id"] == "neutral":
                    new_casting["fallback"] = {"expression_id": "neutral", "asset": asset}
                else:
                    new_casting["rules"].append({
                        "expression_id": expr["id"],
                        "priority": expr["priority"],
                        "asset": asset,
                        "evidence": expr["evidence"]
                    })
        self.casting = new_casting
        if self.on_save:
            self.on_save(self.casting)
        self.active = False

    def draw(self, font: pygame.font.Font, small_font: pygame.font.Font):
        if not self.active: return
        
        pygame.draw.rect(self.screen, COLORS["bg_panel"], self.rect, border_radius=8)
        pygame.draw.rect(self.screen, COLORS["border"], self.rect, 2, border_radius=8)
        
        title = font.render(f"Visual Picker: {self.npc_id}", True, COLORS["text_highlight"])
        self.screen.blit(title, (self.rect.x + 20, self.rect.y + 15))
        
        # Подсказка
        hint = small_font.render("1. Выделите спрайт мышью (белый фон удалится). 2. Сохраните пропорции и примените.", True, COLORS["text_dim"])
        self.screen.blit(hint, (self.rect.x + 20, self.rect.y + 40))
        
        # Отрисовка спрайтшита
        if self.sheet_surface:
            sheet_rect = self._get_sheet_rect()
            scaled = pygame.transform.scale(self.sheet_surface, (sheet_rect.width, sheet_rect.height))
            self.screen.blit(scaled, sheet_rect.topleft)
            
            orig_w, orig_h = self.sheet_surface.get_size()
            scale_x = sheet_rect.width / orig_w
            scale_y = sheet_rect.height / orig_h
                
            # Подсветка активного выделения
            if self.current_rect:
                r = self.current_rect
                hx = sheet_rect.x + int(r.x * scale_x)
                hy = sheet_rect.y + int(r.y * scale_y)
                hw = int(r.w * scale_x)
                hh = int(r.h * scale_y)
                pygame.draw.rect(self.screen, (255, 255, 0), (hx, hy, hw, hh), 2)
                
            # Отрисовка процесса перетаскивания
            if self.drag_start and self.drag_curr:
                rx = min(self.drag_start[0], self.drag_curr[0])
                ry = min(self.drag_start[1], self.drag_curr[1])
                rw = abs(self.drag_start[0] - self.drag_curr[0])
                rh = abs(self.drag_start[1] - self.drag_curr[1])
                drag_rect = pygame.Rect(rx, ry, rw, rh).clip(sheet_rect)
                s = pygame.Surface((drag_rect.w, drag_rect.h), pygame.SRCALPHA)
                s.fill((0, 255, 0, 60))
                self.screen.blit(s, drag_rect.topleft)
                pygame.draw.rect(self.screen, (0, 255, 0), drag_rect, 2)
        else:
            hint = small_font.render("Нажмите 'Выбрать лист' для загрузки изображения", True, COLORS["text_dim"])
            self.screen.blit(hint, (self.rect.x + 500, self.rect.y + 200))
            
        # Отрисовка эмоций
        for btn in self._emotion_buttons:
            is_selected = btn.action == f"expr:{self._selected_emotion}"
            btn.color_key = "btn_primary" if is_selected else "btn_secondary"
            btn.draw(self.screen, font)
            
            expr_id = btn.action.split(":")[1]
            asset = self._assigned.get(expr_id)
            
            # Зеленая рамка, если эмоция уже назначена
            if asset and isinstance(asset, list) and len(asset) >= 5:
                pygame.draw.rect(self.screen, (0, 255, 0), btn.rect, 3, border_radius=4)
                # Превью тайла на кнопке
                try:
                    surf = sprite_registry.get_rect(asset[0], int(asset[1]), int(asset[2]), int(asset[3]), int(asset[4]))
                    if surf:
                        scaled = pygame.transform.scale(surf, (40, 40))
                        self.screen.blit(scaled, (btn.rect.right - 50, btn.rect.y + 5))
                except Exception:
                    pass

        # Отрисовка ползунков
        self._draw_sliders(small_font)
        
        # Окно превью активной эмоции (Live Preview)
        prev_x, prev_y = self.rect.right - 220, self.rect.y + 60
        prev_w, prev_h = 200, 280
        pygame.draw.rect(self.screen, (30, 30, 30), (prev_x, prev_y, prev_w, prev_h), border_radius=4)
        pygame.draw.rect(self.screen, COLORS["border"], (prev_x, prev_y, prev_w, prev_h), 2, border_radius=4)
        
        expr_id = self._selected_emotion
        label = next((e["label"] for e in STANDARD_EXPRESSIONS if e["id"] == expr_id), "Нет")
        txt_title = small_font.render(f"Превью: {label} (Zoom: {self.preview_zoom:.1f}x)", True, COLORS["text"])
        self.screen.blit(txt_title, (prev_x + 10, prev_y + 10))
        
        asset = self._assigned.get(expr_id)
        if asset and isinstance(asset, list) and len(asset) >= 5:
            try:
                # Для превью всегда используем текущие значения ползунков, чтобы видеть изменения в реальном времени
                surf = sprite_registry.get_rect(asset[0], int(asset[1]), int(asset[2]), int(asset[3]), int(asset[4]), self.threshold, self.outline)
                if surf:
                    sw, sh = surf.get_size()
                    # Применяем зум к базовому размеру 160
                    base_size = int(160 * self.preview_zoom)
                    ratio = min(base_size / sw, base_size / sh)
                    nw, nh = int(sw * ratio), int(sh * ratio)
                    scaled = pygame.transform.smoothscale(surf, (nw, nh))
                    # Ограничиваем отрисовку рамкой превью, чтобы не вылезало
                    prev_clip = self.screen.get_clip()
                    self.screen.set_clip(pygame.Rect(prev_x, prev_y + 30, 200, 250))
                    self.screen.blit(scaled, (prev_x + (200 - nw) // 2, prev_y + 30 + (250 - nh) // 2))
                    self.screen.set_clip(prev_clip)
            except Exception:
                pass
        else:
            txt = small_font.render("Не назначено", True, COLORS["text_dim"])
            self.screen.blit(txt, (prev_x + 10, prev_y + 120))

        # Toast сообщение
        if self.message and pygame.time.get_ticks() - self.message_timer < 3000:
            msg_surf = small_font.render(self.message, True, (255, 255, 0))
            self.screen.blit(msg_surf, (self.rect.x + 20, self.rect.bottom - 90))
            
        # Кнопки
        for btn in self._buttons:
            btn.draw(self.screen, font)