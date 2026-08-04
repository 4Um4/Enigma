"""
Назначение: Экран настроек игры (Графика и Контент)
Зависимости: pygame, app.core.config, app.core.content_policy, display_manager
Основные сущности: SettingsScreen

path: /frontend/settings_screen.py
"""

import sys
from pathlib import Path
from typing import Optional

import pygame
import yaml

# Добавляем корень проекта в sys.path для импорта backend.app
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

import importlib
settings = importlib.import_module("app.core.config").settings
save_content_policy = importlib.import_module("app.core.content_policy").save_content_policy
from display_manager import load_display_settings, save_display_settings, get_available_resolutions, create_window

# === Минимальная цветовая схема (как в game_menu.py) ===
_MENU_COLORS = {
    "bg_dark": (18, 18, 23),
    "text": (220, 220, 220),
    "text_dim": (140, 140, 140),
    "btn_primary": (70, 100, 130),
    "btn_primary_hover": (90, 130, 160),
    "btn_secondary": (80, 80, 90),
    "btn_secondary_hover": (100, 100, 110),
    "btn_danger": (150, 60, 60),
    "btn_danger_hover": (180, 80, 80),
    "border": (60, 60, 70),
    "accent_blue": (70, 170, 255),
    "accent_green": (80, 200, 120),
    "accent_yellow": (220, 180, 60),
}

class _SettingsButton:
    def __init__(self, x, y, w, h, text, color, color_hover, on_click, is_selected=False, tooltip=""):
        self.rect = pygame.Rect(x, y, w, h)
        self.text = text
        self.color = color
        self.color_hover = color_hover
        self.on_click = on_click
        self.hovered = False
        self.is_selected = is_selected
        self.tooltip = tooltip

    def handle_event(self, event):
        if event.type == pygame.MOUSEMOTION:
            self.hovered = self.rect.collidepoint(event.pos)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.rect.collidepoint(event.pos):
                self.on_click()
                return True
        return False

    def draw(self, screen, font):
        color = self.color_hover if self.hovered else self.color
        pygame.draw.rect(screen, color, self.rect, border_radius=6)
        
        border_color = _MENU_COLORS["accent_blue"] if self.is_selected else _MENU_COLORS["border"]
        border_width = 2 if self.is_selected else 1
        pygame.draw.rect(screen, border_color, self.rect, border_width, border_radius=6)
        
        text_surf = font.render(self.text, True, _MENU_COLORS["text"])
        text_rect = text_surf.get_rect(center=self.rect.center)
        screen.blit(text_surf, text_rect)

class SettingsScreen:
    """Экран настроек. Владеет своим циклом отрисовки."""
    
    def __init__(self, screen: pygame.Surface, clock: pygame.time.Clock):
        self.screen = screen
        self.clock = clock
        self._result: Optional[str] = None  # "back" or None
        self._active_tab = "graphics" # По умолчанию открываем Графику
        
        self.font_title = pygame.font.SysFont("consolas", 36, bold=True)
        self.font_button = pygame.font.SysFont("consolas", 20, bold=True)
        self.font_small = pygame.font.SysFont("consolas", 14)
        
        # Настройки графики
        self._gfx_settings = load_display_settings()
        self._resolutions = get_available_resolutions()
        self._display_modes = ['windowed', 'borderless', 'exclusive']
        self._mode_names = {'windowed': 'Оконный', 'borderless': 'Безрамочный', 'exclusive': 'Полноэкранный'}
        
        # Настройки контента (заглушка, если не удалось получить)
        self.current_preset = getattr(settings.content_policy, "preset", "moderate")
        
        # Статус LLM-моделей
        self._llm_status = self._fetch_llm_status()
        
        self.buttons = self._build_buttons()

    def _build_buttons(self):
        buttons = []
        # Кнопки вкладок
        tab_w, tab_h = 200, 50
        gap = 20
        start_x = (self.screen.get_width() - (tab_w * 3 + gap * 2)) // 2
        start_y = 120
        
        buttons.append(_SettingsButton(start_x, start_y, tab_w, tab_h, "Графика", _MENU_COLORS["btn_primary"], _MENU_COLORS["btn_primary_hover"], lambda: self._switch_tab("graphics"), self._active_tab == "graphics"))
        buttons.append(_SettingsButton(start_x + tab_w + gap, start_y, tab_w, tab_h, "Контент", _MENU_COLORS["btn_primary"], _MENU_COLORS["btn_primary_hover"], lambda: self._switch_tab("content"), self._active_tab == "content"))
        buttons.append(_SettingsButton(start_x + (tab_w + gap)*2, start_y, tab_w, tab_h, "LLM Модели", _MENU_COLORS["btn_primary"], _MENU_COLORS["btn_primary_hover"], lambda: self._switch_tab("llm"), self._active_tab == "llm"))
        
        btn_w, btn_h = 300, 50
        x = (self.screen.get_width() - btn_w) // 2
        start_y = 220
        
        if self._active_tab == "graphics":
            # Кнопка переключения разрешения
            curr_res = self._gfx_settings.get('resolution', {'width': 1400, 'height': 900})
            res_str = f"Разрешение: {curr_res['width']}x{curr_res['height']}"
            buttons.append(_SettingsButton(x, start_y, btn_w, btn_h, res_str, _MENU_COLORS["btn_secondary"], _MENU_COLORS["btn_secondary_hover"], self._cycle_resolution))
            
            # Кнопки режимов экрана
            for i, mode in enumerate(self._display_modes):
                is_sel = self._gfx_settings.get('display_mode', 'windowed') == mode
                buttons.append(_SettingsButton(x, start_y + (i+1)*(btn_h+gap), btn_w, btn_h, self._mode_names[mode], _MENU_COLORS["btn_secondary"], _MENU_COLORS["btn_secondary_hover"], lambda m=mode: self._set_mode(m), is_sel))
                
            # Кнопка Применить
            buttons.append(_SettingsButton(x, start_y + 4*(btn_h+gap), btn_w, btn_h, "Применить", _MENU_COLORS["accent_green"], _MENU_COLORS["btn_primary_hover"], self._apply_graphics))
            buttons.append(_SettingsButton(x, start_y + 5*(btn_h+gap), btn_w, btn_h, "Назад", _MENU_COLORS["btn_danger"], _MENU_COLORS["btn_danger_hover"], lambda: setattr(self, "_result", "back")))

        elif self._active_tab == "content":
            # Кнопки контента
            buttons.append(_SettingsButton(x, start_y, btn_w, btn_h, "Безопасный (12+)", _MENU_COLORS["btn_secondary"], _MENU_COLORS["btn_secondary_hover"], lambda: self._set_preset("safe"), self.current_preset == "safe", tooltip="Никакого мата, секса, детального насилия."))
            buttons.append(_SettingsButton(x, start_y + btn_h + gap, btn_w, btn_h, "Подростковый (16+)", _MENU_COLORS["btn_secondary"], _MENU_COLORS["btn_secondary_hover"], lambda: self._set_preset("moderate"), self.current_preset == "moderate", tooltip="Лёгкая ругань, намёки на секс, физиологичное насилие без садизма."))
            buttons.append(_SettingsButton(x, start_y + 2*(btn_h + gap), btn_w, btn_h, "Взрослый (18+)", _MENU_COLORS["btn_secondary"], _MENU_COLORS["btn_secondary_hover"], lambda: self._set_preset("explicit"), self.current_preset == "explicit", tooltip="Полный 18+ контент: мат, explicit-секс, детальная жестокость, табу-практики."))
            buttons.append(_SettingsButton(x, start_y + 3*(btn_h + gap), btn_w, btn_h, "Назад", _MENU_COLORS["btn_danger"], _MENU_COLORS["btn_danger_hover"], lambda: setattr(self, "_result", "back")))

        elif self._active_tab == "llm":
            status = self._llm_status
            if not status:
                buttons.append(_SettingsButton(x, start_y, btn_w, btn_h, "Сервер недоступен", _MENU_COLORS["btn_danger"], _MENU_COLORS["btn_danger_hover"], lambda: None, tooltip="Убедитесь, что бэкенд запущен."))
            else:
                for i, (key, info) in enumerate(status.items()):
                    name = info.get("display_name", key)
                    is_dl = info.get("is_downloaded", False)
                    is_downloading = info.get("is_downloading", False)
                    progress = info.get("progress", 0.0)
                    
                    if is_dl:
                        color = _MENU_COLORS["accent_green"]
                        color_hover = _MENU_COLORS["btn_primary_hover"]
                        text = f"✅ {name}"
                        tooltip = "Модель уже скачана"
                        on_click = lambda: None
                    elif is_downloading:
                        color = _MENU_COLORS["btn_primary"]
                        color_hover = _MENU_COLORS["btn_primary"]
                        text = f"⏳ Скачивание... {progress}%"
                        tooltip = "Идет загрузка. Пожалуйста, подождите."
                        on_click = lambda: None
                    else:
                        color = _MENU_COLORS["btn_secondary"]
                        color_hover = _MENU_COLORS["btn_secondary_hover"]
                        text = f"⬇️ Скачать: {name}"
                        tooltip = "Нажмите, чтобы начать скачивание в фоне"
                        on_click = lambda k=key: self._download_llm(k)
                        
                    buttons.append(_SettingsButton(
                        x, start_y + i*(btn_h+gap), btn_w, btn_h, text, color, color_hover, 
                        on_click, 
                        is_selected=is_dl,
                        tooltip=tooltip
                    ))
            buttons.append(_SettingsButton(x, start_y + len(status)*(btn_h+gap) + gap, btn_w, btn_h, "Назад", _MENU_COLORS["btn_danger"], _MENU_COLORS["btn_danger_hover"], lambda: setattr(self, "_result", "back")))

        return buttons

    def _switch_tab(self, tab):
        self._active_tab = tab
        if tab == "llm":
            self._llm_status = self._fetch_llm_status()
        self.buttons = self._build_buttons()

    def _fetch_llm_status(self) -> dict:
        """Получает статус LLM-моделей с бэкенда."""
        import urllib.request
        import json
        try:
            with urllib.request.urlopen("http://localhost:8000/api/llm/status", timeout=2) as r:
                return json.loads(r.read())
        except Exception:
            return {}

    def _download_llm(self, model_key: str):
        """Отправляет запрос на скачивание модели в фоне."""
        import urllib.request
        try:
            req = urllib.request.Request(f"http://localhost:8000/api/llm/download/{model_key}", method="POST")
            urllib.request.urlopen(req, timeout=2)
        except Exception as e:
            print(f"Failed to start download: {e}")
        # Обновляем статус после клика
        self._llm_status = self._fetch_llm_status()
        self.buttons = self._build_buttons()

    def _cycle_resolution(self):
        curr_res = self._gfx_settings.get('resolution', {'width': 1400, 'height': 900})
        curr_tuple = (curr_res['width'], curr_res['height'])
        try:
            idx = self._resolutions.index(curr_tuple)
            next_idx = (idx + 1) % len(self._resolutions)
        except ValueError:
            next_idx = 0
        next_res = self._resolutions[next_idx]
        self._gfx_settings['resolution'] = {'width': next_res[0], 'height': next_res[1]}
        self.buttons = self._build_buttons()

    def _set_mode(self, mode):
        self._gfx_settings['display_mode'] = mode
        self.buttons = self._build_buttons()

    def _apply_graphics(self):
        save_display_settings(self._gfx_settings)
        # Пересоздаем окно немедленно
        self.screen = create_window()
        self.buttons = self._build_buttons()

    def _set_preset(self, preset):
        self.current_preset = preset
        try:
            settings.content_policy.preset = preset
            save_content_policy(settings)
        except Exception as e:
            print(f"Failed to save content policy: {e}")
        self.buttons = self._build_buttons()

    def run(self):
        self._result = None
        while self._result is None:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    sys.exit()
                elif event.type == pygame.VIDEORESIZE:
                    self.screen = pygame.display.set_mode((event.w, event.h), pygame.RESIZABLE)
                    self.buttons = self._build_buttons()
                else:
                    for btn in self.buttons:
                        if btn.handle_event(event):
                            break
                            
            # Поллинг статуса LLM каждые 2 секунды, если открыта вкладка
            if self._active_tab == "llm" and pygame.time.get_ticks() - getattr(self, "_last_llm_fetch", 0) > 2000:
                self._llm_status = self._fetch_llm_status()
                self.buttons = self._build_buttons()
                self._last_llm_fetch = pygame.time.get_ticks()

            self.screen.fill(_MENU_COLORS["bg_dark"])
            
            title_surf = self.font_title.render("Настройки", True, _MENU_COLORS["text"])
            title_rect = title_surf.get_rect(center=(self.screen.get_width() // 2, 60))
            self.screen.blit(title_surf, title_rect)
            
            for btn in self.buttons:
                btn.draw(self.screen, self.font_button)
            
            # Отрисовка тултипа
            hovered_btn = next((b for b in self.buttons if b.hovered and b.tooltip), None)
            if hovered_btn:
                tip_surf = self.font_small.render(hovered_btn.tooltip, True, _MENU_COLORS["text"])
                tip_rect = tip_surf.get_rect(center=(self.screen.get_width() // 2, self.screen.get_height() - 60))
                pad = 10
                bg_rect = tip_rect.inflate(pad * 2, pad)
                pygame.draw.rect(self.screen, _MENU_COLORS["btn_secondary"], bg_rect, border_radius=4)
                pygame.draw.rect(self.screen, _MENU_COLORS["border"], bg_rect, 1, border_radius=4)
                self.screen.blit(tip_surf, tip_rect)
                
            pygame.display.flip()
            self.clock.tick(30)