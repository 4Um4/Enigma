"""
Назначение: Экран настроек игры (Графика, Контент, LLM)
Зависимости: pygame, app.core.config, app.core.content_policy, display_manager
Основные сущности: SettingsScreen
"""

import sys
import json
import urllib.request
import threading
from pathlib import Path
from typing import Optional

import pygame

# Добавляем корень проекта в sys.path для импорта backend.app
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

import importlib
settings = importlib.import_module("app.core.config").settings
save_content_policy = importlib.import_module("app.core.content_policy").save_content_policy
from app.core.content_policy import ContentPolicy
from display_manager import load_display_settings, save_display_settings, get_available_resolutions, create_window

# === Минимальная цветовая схема ===
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
        self._result: Optional[str] = None
        self._active_tab = "graphics"
        self._llm_test_log = ""
        self._last_llm_fetch = 0
        
        self.font_title = pygame.font.SysFont("consolas", 36, bold=True)
        self.font_button = pygame.font.SysFont("consolas", 20, bold=True)
        self.font_small = pygame.font.SysFont("consolas", 14)
        
        # Настройки графики
        self._gfx_settings = load_display_settings()
        self._resolutions = get_available_resolutions()
        self._display_modes = ['windowed', 'borderless']
        self._mode_names = {'windowed': 'Оконный', 'borderless': 'Полноэкранный'}
        self._dropdown_open = False
        
        # Определяем активный пресет по фактическим уровням контента
        cp = settings.content_policy
        if cp.profanity_level == 0 and cp.sexual_content_level == 0 and cp.violence_level == 1 and cp.taboo_practices_level == 0:
            self.current_preset = "safe"
        elif cp.profanity_level == 2 or cp.sexual_content_level == 2 or cp.taboo_practices_level == 2:
            self.current_preset = "explicit"
        else:
            self.current_preset = "moderate"
        
        self._llm_status = self._fetch_llm_status()
        self.buttons = self._build_buttons()

    def _build_buttons(self):
        buttons = []
        tab_w, tab_h = 200, 50
        gap = 20
        start_x = (self.screen.get_width() - (tab_w * 3 + gap * 2)) // 2
        start_y = 120
        
        buttons.append(_SettingsButton(start_x, start_y, tab_w, tab_h, "Графика", _MENU_COLORS["btn_primary"], _MENU_COLORS["btn_primary_hover"], lambda: self._switch_tab("graphics"), self._active_tab == "graphics"))
        buttons.append(_SettingsButton(start_x + tab_w + gap, start_y, tab_w, tab_h, "Контент", _MENU_COLORS["btn_primary"], _MENU_COLORS["btn_primary_hover"], lambda: self._switch_tab("content"), self._active_tab == "content"))
        buttons.append(_SettingsButton(start_x + (tab_w + gap)*2, start_y, tab_w, tab_h, "LLM Модели", _MENU_COLORS["btn_primary"], _MENU_COLORS["btn_primary_hover"], lambda: self._switch_tab("llm"), self._active_tab == "llm"))
        
        btn_w, btn_h = 400, 50
        x = (self.screen.get_width() - btn_w) // 2
        start_y = 220
        
        if self._active_tab == "graphics":
            curr_res = self._gfx_settings.get('resolution', {'width': 1400, 'height': 900})
            
            if not self._dropdown_open:
                res_str = f"Разрешение: {curr_res['width']}x{curr_res['height']} ▼"
                buttons.append(_SettingsButton(x, start_y, btn_w, btn_h, res_str, _MENU_COLORS["btn_secondary"], _MENU_COLORS["btn_secondary_hover"], self._toggle_dropdown))
                start_y += btn_h + gap
            else:
                res_str = f"Разрешение: {curr_res['width']}x{curr_res['height']} ▲"
                buttons.append(_SettingsButton(x, start_y, btn_w, btn_h, res_str, _MENU_COLORS["btn_primary"], _MENU_COLORS["btn_primary_hover"], self._toggle_dropdown))
                start_y += btn_h + gap
                
                info = pygame.display.Info()
                native_res = (info.current_w, info.current_h)
                
                for i, res in enumerate(self._resolutions):
                    res_str = f"{res[0]}x{res[1]}"
                    if res == native_res:
                        res_str += " (Рекомендуется)"
                    is_sel = (curr_res['width'], curr_res['height']) == res
                    buttons.append(_SettingsButton(x, start_y + i*(btn_h+gap), btn_w, btn_h, res_str, _MENU_COLORS["btn_secondary"], _MENU_COLORS["btn_secondary_hover"], lambda r=res: self._set_resolution(r), is_sel))
                    
                start_y += len(self._resolutions) * (btn_h + gap)
                buttons.append(_SettingsButton(x, start_y, btn_w, btn_h, "Закрыть список", _MENU_COLORS["btn_danger"], _MENU_COLORS["btn_danger_hover"], self._toggle_dropdown))
                start_y += btn_h + gap

            curr_mode = self._gfx_settings.get('display_mode', 'windowed')
            mode_str = f"Режим: < {self._mode_names.get(curr_mode, 'Оконный')} >"
            buttons.append(_SettingsButton(x, start_y, btn_w, btn_h, mode_str, _MENU_COLORS["btn_secondary"], _MENU_COLORS["btn_secondary_hover"], self._cycle_mode))
            
        elif self._active_tab == "content":
            buttons.append(_SettingsButton(x, start_y, btn_w, btn_h, "Безопасный (12+)", _MENU_COLORS["btn_secondary"], _MENU_COLORS["btn_secondary_hover"], lambda: self._set_preset("safe"), self.current_preset == "safe", tooltip="Никакого мата, секса, детального насилия."))
            buttons.append(_SettingsButton(x, start_y + btn_h + gap, btn_w, btn_h, "Подростковый (16+)", _MENU_COLORS["btn_secondary"], _MENU_COLORS["btn_secondary_hover"], lambda: self._set_preset("moderate"), self.current_preset == "moderate", tooltip="Лёгкая ругань, намёки на секс, физиологичное насилие без садизма."))
            buttons.append(_SettingsButton(x, start_y + 2*(btn_h + gap), btn_w, btn_h, "Взрослый (18+)", _MENU_COLORS["btn_secondary"], _MENU_COLORS["btn_secondary_hover"], lambda: self._set_preset("explicit"), self.current_preset == "explicit", tooltip="Полный 18+ контент: мат, explicit-секс, детальная жестокость, табу-практики."))
            
        elif self._active_tab == "llm":
            list_btn_h = 40
            list_gap = 10
            status = self._llm_status or {}
            llm_btn_w = 600
            llm_x = (self.screen.get_width() - llm_btn_w) // 2
            
            if not status or not isinstance(status, dict):
                buttons.append(_SettingsButton(llm_x, start_y, llm_btn_w, list_btn_h, "Нет доступных моделей", _MENU_COLORS["btn_secondary"], _MENU_COLORS["btn_secondary_hover"], lambda: None, tooltip="Бэкенд не вернул список. Проверьте config/llm_sources.json"))
            else:
                for i, (key, info) in enumerate(status.items()):
                    name = info.get("display_name", key)
                    is_dl = info.get("is_downloaded", False)
                    is_downloading = info.get("is_downloading", False)
                    progress = info.get("progress", 0.0)
                    is_active = key == getattr(settings, "default_model", None)
                    
                    if is_active:
                        text = f"🔵 АКТИВНА: {name}"
                        color = _MENU_COLORS["accent_blue"]
                        on_click = lambda: None
                    elif is_downloading:
                        text = f"⏳ Скачивание... {progress}%"
                        color = _MENU_COLORS["btn_primary"]
                        on_click = lambda: None
                    elif is_dl:
                        text = f"✅ Использовать: {name}"
                        color = _MENU_COLORS["accent_green"]
                        on_click = lambda k=key: self._select_llm(k)
                    else:
                        text = f"⬇️ Скачать: {name}"
                        color = _MENU_COLORS["btn_secondary"]
                        on_click = lambda k=key: self._download_llm(k)
                        
                    buttons.append(_SettingsButton(llm_x, start_y + i*(list_btn_h+list_gap), llm_btn_w, list_btn_h, text, color, _MENU_COLORS["btn_secondary_hover"], on_click, tooltip=f"Ключ: {key}"))

        # Универсальные кнопки внизу экрана (кроме вкладки LLM, там своя кнопка Назад)
        if self._active_tab != "llm":
            bottom_y = self.screen.get_height() - btn_h - 40
            buttons.append(_SettingsButton(self.screen.get_width() // 2 - btn_w - 20, bottom_y, btn_w, btn_h, "Применить", _MENU_COLORS["accent_green"], _MENU_COLORS["btn_primary_hover"], self._apply_graphics))
            buttons.append(_SettingsButton(self.screen.get_width() // 2 + 20, bottom_y, btn_w, btn_h, "Назад", _MENU_COLORS["btn_danger"], _MENU_COLORS["btn_danger_hover"], lambda: setattr(self, "_result", "back")))
        else:
            bottom_y = self.screen.get_height() - btn_h - 120
            buttons.append(_SettingsButton(self.screen.get_width() // 2 - 100, bottom_y, 200, btn_h, "Назад", _MENU_COLORS["btn_danger"], _MENU_COLORS["btn_danger_hover"], lambda: setattr(self, "_result", "back")))

        return buttons

    def _switch_tab(self, tab):
        self._active_tab = tab
        if tab == "llm":
            self._llm_status = self._fetch_llm_status()
        self.buttons = self._build_buttons()

    def _fetch_llm_status(self) -> dict:
        try:
            with urllib.request.urlopen("http://localhost:8000/api/llm/status", timeout=0.5) as r:
                return json.loads(r.read())
        except Exception:
            return getattr(self, "_llm_status", {})

    def _download_llm(self, model_key: str):
        try:
            req = urllib.request.Request(f"http://localhost:8000/api/llm/download/{model_key}", method="POST")
            urllib.request.urlopen(req, timeout=2)
        except Exception as e:
            print(f"Failed to start download: {e}")
        self._llm_status = self._fetch_llm_status()
        self.buttons = self._build_buttons()

    def _select_llm(self, model_key: str):
        """Отправляет запрос на смену модели в отдельном потоке, чтобы не вешать UI."""
        self._llm_test_log = "Смена модели... это может занять до 60 секунд."
        self.buttons = self._build_buttons()
        
        def _do_select():
            try:
                req = urllib.request.Request(f"http://localhost:8000/api/llm/select/{model_key}", method="POST")
                with urllib.request.urlopen(req, timeout=60.0) as r:
                    resp = json.loads(r.read())
                    self._llm_test_log = resp.get("test_response", "Модель сменена, но тестовый ответ пуст.")
            except Exception as e:
                self._llm_test_log = f"Ошибка смены модели: {e}"
            finally:
                settings.default_model = model_key
                self._llm_status = self._fetch_llm_status()
                self.buttons = self._build_buttons()
                
        threading.Thread(target=_do_select, daemon=True).start()

    def _toggle_dropdown(self):
        self._dropdown_open = not self._dropdown_open
        self.buttons = self._build_buttons()

    def _set_resolution(self, res):
        self._gfx_settings['resolution'] = {'width': res[0], 'height': res[1]}
        self._dropdown_open = False
        self.buttons = self._build_buttons()

    def _cycle_mode(self):
        curr_mode = self._gfx_settings.get('display_mode', 'windowed')
        try:
            idx = self._display_modes.index(curr_mode)
            next_idx = (idx + 1) % len(self._display_modes)
        except ValueError:
            next_idx = 0
        self._gfx_settings['display_mode'] = self._display_modes[next_idx]
        self.buttons = self._build_buttons()

    def _apply_graphics(self):
        save_display_settings(self._gfx_settings)
        self.screen = create_window()
        self.buttons = self._build_buttons()

    def _set_preset(self, preset):
        self.current_preset = preset
        try:
            if preset == "safe":
                settings._content_policy_cache = ContentPolicy.preset_off()
            elif preset == "moderate":
                settings._content_policy_cache = ContentPolicy.preset_moderate()
            elif preset == "explicit":
                settings._content_policy_cache = ContentPolicy.preset_explicit()
            save_content_policy(settings, preset)
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
                            
            if self._active_tab == "llm" and pygame.time.get_ticks() - self._last_llm_fetch > 2000:
                new_status = self._fetch_llm_status()
                if new_status != self._llm_status:
                    self._llm_status = new_status
                    self.buttons = self._build_buttons()
                self._last_llm_fetch = pygame.time.get_ticks()

            self.screen.fill(_MENU_COLORS["bg_dark"])
            
            title_surf = self.font_title.render("Настройки", True, _MENU_COLORS["text"])
            title_rect = title_surf.get_rect(center=(self.screen.get_width() // 2, 60))
            self.screen.blit(title_surf, title_rect)
            
            for btn in self.buttons:
                btn.draw(self.screen, self.font_button)
            
            hovered_btn = next((b for b in self.buttons if b.hovered and b.tooltip), None)
            if hovered_btn:
                tip_surf = self.font_small.render(hovered_btn.tooltip, True, _MENU_COLORS["text"])
                tip_rect = tip_surf.get_rect(center=(self.screen.get_width() // 2, self.screen.get_height() - 60))
                pad = 10
                bg_rect = tip_rect.inflate(pad * 2, pad)
                pygame.draw.rect(self.screen, _MENU_COLORS["btn_secondary"], bg_rect, border_radius=4)
                pygame.draw.rect(self.screen, _MENU_COLORS["border"], bg_rect, 1, border_radius=4)
                self.screen.blit(tip_surf, tip_rect)
                
            if self._active_tab == "llm" and self._llm_test_log:
                log_y = self.screen.get_height() - 180
                log_bg = pygame.Rect(50, log_y - 10, self.screen.get_width() - 100, 100)
                pygame.draw.rect(self.screen, (10, 10, 15), log_bg, border_radius=4)
                pygame.draw.rect(self.screen, _MENU_COLORS["border"], log_bg, 1, border_radius=4)
                
                lines = [self._llm_test_log[i:i+80] for i in range(0, len(self._llm_test_log), 80)]
                for i, line in enumerate(lines[:4]):
                    log_surf = self.font_small.render(f"Тест модели: {line}", True, _MENU_COLORS["accent_blue"])
                    self.screen.blit(log_surf, (60, log_y + i * 20))
                
            pygame.display.flip()
            self.clock.tick(60)