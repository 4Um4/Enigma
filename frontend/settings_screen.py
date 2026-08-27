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
_content_policy_mod = importlib.import_module("app.core.content_policy")
save_content_policy = _content_policy_mod.save_content_policy
ContentPolicy = _content_policy_mod.ContentPolicy
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

def _fit_font(text: str, max_w: int, base_size: int = 20, min_size: int = 11):
    """Подбирает размер шрифта под фактическую ширину текста (font.size),
    а не по количеству символов — длинные имена моделей всегда влезают."""
    _size = base_size
    while _size > min_size:
        _f = pygame.font.SysFont("consolas", _size, bold=True)
        if _f.size(text)[0] <= max_w:
            return _f
        _size -= 1
    return pygame.font.SysFont("consolas", min_size, bold=True)

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
        self._last_click_time = 0

    def handle_event(self, event):
        if event.type == pygame.MOUSEMOTION:
            self.hovered = self.rect.collidepoint(event.pos)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.rect.collidepoint(event.pos):
                self.on_click()
                return True
        return False

    def draw(self, screen, font):
        # Тактильный отклик: при наведении кнопка увеличивается
        _rect = self.rect.inflate(4, 4) if self.hovered else self.rect
        color = self.color_hover if self.hovered else self.color
        pygame.draw.rect(screen, color, _rect, border_radius=6)
        
        border_color = _MENU_COLORS["accent_blue"] if (self.is_selected or self.hovered) else _MENU_COLORS["border"]
        border_width = 2 if (self.is_selected or self.hovered) else 1
        pygame.draw.rect(screen, border_color, _rect, border_width, border_radius=6)
        
        _draw_font = getattr(self, "_font", font)
        text_surf = _draw_font.render(self.text, True, _MENU_COLORS["text"])
        text_rect = text_surf.get_rect(center=_rect.center)
        screen.blit(text_surf, text_rect)

class SettingsScreen:
    """Экран настроек. Владеет своим циклом отрисовки."""
    
    # Виртуальное разрешение для масштабирования UI
    VIRTUAL_W, VIRTUAL_H = 1920, 1080
    
    def __init__(self, screen: pygame.Surface, clock: pygame.time.Clock):
        self.screen = screen
        self.clock = clock
        self._result: Optional[str] = None
        self._active_tab = "graphics"
        
        # Рассчитываем масштаб под текущее разрешение
        self._scale = min(
            screen.get_width() / self.VIRTUAL_W,
            screen.get_height() / self.VIRTUAL_H
        )
        
        # Прокрутка для списка моделей
        self._scroll_y = 0
        self._max_scroll = 0
        self._llm_test_log = ""
        self._last_llm_fetch = 0
        
        # Масштабируем шрифты под разрешение
        _title_size = max(24, int(36 * self._scale))
        _button_size = max(16, int(20 * self._scale))
        _small_size = max(12, int(14 * self._scale))
        
        self.font_title = pygame.font.SysFont("consolas", _title_size, bold=True)
        self.font_button = pygame.font.SysFont("consolas", _button_size, bold=True)
        self.font_small = pygame.font.SysFont("consolas", _small_size)
        
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
        self._llm_scroll_y = 0
        self.buttons = self._build_buttons()

    def _build_buttons(self):
        buttons = []
        # Масштабируем размеры кнопок
        tab_w = int(200 * self._scale)
        tab_h = int(50 * self._scale)
        gap = int(20 * self._scale)
        start_x = (self.screen.get_width() - (tab_w * 4 + gap * 3)) // 2  # AUDIT #14: вкладок четыре
        start_y = 120
        
        buttons.append(_SettingsButton(start_x, start_y, tab_w, tab_h, "Графика", _MENU_COLORS["btn_primary"], _MENU_COLORS["btn_primary_hover"], lambda: self._switch_tab("graphics"), self._active_tab == "graphics"))
        buttons.append(_SettingsButton(start_x + tab_w + gap, start_y, tab_w, tab_h, "Контент", _MENU_COLORS["btn_primary"], _MENU_COLORS["btn_primary_hover"], lambda: self._switch_tab("content"), self._active_tab == "content"))
        buttons.append(_SettingsButton(start_x + (tab_w + gap)*2, start_y, tab_w, tab_h, "LLM Модели", _MENU_COLORS["btn_primary"], _MENU_COLORS["btn_primary_hover"], lambda: self._switch_tab("llm"), self._active_tab == "llm"))
        buttons.append(_SettingsButton(start_x + (tab_w + gap)*3, start_y, tab_w, tab_h, "Управление", _MENU_COLORS["btn_primary"], _MENU_COLORS["btn_primary_hover"], lambda: self._switch_tab("controls"), self._active_tab == "controls"))
        
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
            # Динамическая высота списка с учетом масштаба
            _list_height = int((self.screen.get_height() - 300) * self._scale)
            _max_y = self.screen.get_height() - 200
            self._max_scroll = 0  # пересчитывается ниже, когда списки собраны
            
            if not status or not isinstance(status, dict):
                buttons.append(_SettingsButton(llm_x, start_y, llm_btn_w, list_btn_h, "Нет доступных моделей", _MENU_COLORS["btn_secondary"], _MENU_COLORS["btn_secondary_hover"], lambda: None, tooltip="Бэкенд не вернул список. Проверьте config/llm_sources.json"))
            else:
                # Разделяем на установленные и доступные для скачивания
                _installed = []
                _available = []
                for key, info in status.items():
                    if not isinstance(info, dict): continue
                    if info.get("is_downloaded", False) or info.get("is_downloading", False) or info.get("error", False):
                        _installed.append((key, info))
                    else:
                        _available.append((key, info))
                
                # Рассчитываем максимальную прокрутку (списки собраны — считаем безопасно)
                _content_height = (len(_installed) + len(_available)) * (list_btn_h + list_gap) + 2 * (list_btn_h + list_gap)
                self._max_scroll = max(0, _content_height - _list_height)
                self._llm_scroll_y = min(self._llm_scroll_y, self._max_scroll)
                # Сохраняем для отрисовки скроллбара в run() (там списков уже нет)
                self._list_height = _list_height
                self._content_height = _content_height
                
                _y_offset = start_y - self._llm_scroll_y
                
                # Заголовок "Установленные"
                if _installed:
                    buttons.append(_SettingsButton(llm_x, _y_offset, llm_btn_w, list_btn_h, "--- Установленные ---", _MENU_COLORS["bg_dark"], _MENU_COLORS["bg_dark"], lambda: None))
                    _y_offset += list_btn_h + list_gap
                    
                for key, info in _installed:
                    if _y_offset > _max_y: break  # Обрезка по высоте
                    if _y_offset > start_y - list_btn_h:
                        name = info.get("display_name", key)
                        is_dl = info.get("is_downloaded", False)
                        is_downloading = info.get("is_downloading", False)
                        is_error = info.get("error", False)
                        progress = info.get("progress", 0.0)
                        is_active = info.get("is_active", False)
                        _f_size = info.get("file_size_mb", 0)
                        _r_size = info.get("remote_size_mb", 0)
                        _size_str = f"{_f_size}/{_r_size} МБ" if _r_size > 0 else f"{_f_size} МБ"
                        
                        # Адаптивный шрифт
                        # шрифт подбирается через _fit_font ниже
                        
                        _is_corrupted = _f_size > 0 and _r_size > 0 and _f_size < _r_size * 0.99
                        _is_recommended = info.get("recommended", False)
                        _rec_prefix = "⭐ РЕКОМЕНДУЕТСЯ: " if _is_recommended and not is_active else ""
                        
                        if _is_corrupted:
                            text = f"[X] Повреждена: {name} ({_size_str}). Скачать заново?"
                            color = _MENU_COLORS["btn_danger"]
                            on_click = lambda k=key: self._download_llm(k, force=True)
                            tooltip="Файл повреждён или недокачан. Нажмите, чтобы удалить и скачать заново."
                        elif is_active and is_dl:
                            text = f"[АКТИВНА] {name} ({_size_str})"
                            color = _MENU_COLORS["accent_blue"]
                            on_click = lambda k=key: self._show_model_actions_modal(k)
                            tooltip="Модель активна. Нажмите для выбора действия."
                        elif is_active and not is_dl:
                            text = f"[СКАЧАТЬ-АКТИВНАЯ] {name} ({_r_size} МБ)"
                            color = _MENU_COLORS["btn_danger"]
                            on_click = lambda k=key: self._download_llm(k)
                            tooltip="ВНИМАНИЕ: Модель выбрана, но её нет на диске! Нажмите, чтобы скачать."
                        elif is_downloading:
                            text = f"[ЗАГРУЗКА] {progress}% ({_f_size}/{_r_size} МБ)"
                            color = _MENU_COLORS["btn_primary"]
                            on_click = lambda: None
                            tooltip="Идёт загрузка. Поддерживается докачка при обрыве."
                        elif is_error:
                            _err_msg = info.get("error_message", "Неизвестная ошибка")
                            text = f"[ОШИБКА] {_err_msg[:30]}. Повторить?"
                            color = _MENU_COLORS["btn_danger"]
                            on_click = lambda k=key: self._download_llm(k)
                            tooltip=f"Ошибка: {_err_msg}"
                        elif is_dl:
                            text = f"[ГОТОВО] Использовать: {name} ({_size_str})"
                            color = _MENU_COLORS["accent_green"]
                            on_click = lambda k=key: self._show_model_actions_modal(k)
                            tooltip="Модель скачана. Нажмите для выбора действия."
                            
                        _btn = _SettingsButton(llm_x, _y_offset, llm_btn_w, list_btn_h, text, color, _MENU_COLORS["btn_secondary_hover"], on_click, tooltip=tooltip)
                        # Переопределяем шрифт для кнопки
                        _btn._font = _fit_font(text, llm_btn_w - 24)
                        buttons.append(_btn)
                    _y_offset += list_btn_h + list_gap

                # Заголовок "Доступные для скачивания"
                if _available and _y_offset < _max_y:
                    buttons.append(_SettingsButton(llm_x, _y_offset, llm_btn_w, list_btn_h, "--- Доступные для скачивания ---", _MENU_COLORS["bg_dark"], _MENU_COLORS["bg_dark"], lambda: None))
                    _y_offset += list_btn_h + list_gap
                    
                for key, info in _available:
                    if _y_offset > _max_y: break
                    if _y_offset > start_y - list_btn_h:
                        name = info.get("display_name", key)
                        _r_size = info.get("remote_size_mb", 0)
                        _is_recommended = info.get("recommended", False)
                        _is_gated = info.get("gated", False)
                        # шрифт подбирается через _fit_font ниже
                        
                        if _is_recommended:
                            text = f"[РЕКОМЕНД.] Скачать: {name} ({_r_size} МБ)"
                            color = _MENU_COLORS["accent_green"]  # Зелёная для рекомендованных
                            on_click = lambda k=key: self._download_llm(k)
                            tooltip="Нажмите, чтобы начать скачивание."
                        elif _is_gated:
                            text = f"[ЛИЦЕНЗИЯ] {name} ({_r_size} МБ)"
                            color = _MENU_COLORS["btn_secondary"]
                            on_click = lambda k=key: self._download_llm(k)
                            tooltip="Требуется вход на huggingface.co и принятие лицензии. Без токена HF_TOKEN скачивание вернёт 401. Можно скачать вручную в папку Models LLM."
                        else:
                            text = f"[СКАЧАТЬ] {name} ({_r_size} МБ)"
                            color = _MENU_COLORS["btn_secondary"]
                            on_click = lambda k=key: self._download_llm(k)
                            tooltip="Нажмите, чтобы начать скачивание."
                        
                        _btn = _SettingsButton(llm_x, _y_offset, llm_btn_w, list_btn_h, text, color, _MENU_COLORS["btn_secondary_hover"], on_click, tooltip=tooltip)
                        _btn._font = _fit_font(text, llm_btn_w - 24)
                        buttons.append(_btn)
                    _y_offset += list_btn_h + list_gap

        elif self._active_tab == "controls":
            from keybindings import DEFAULT_KEYBINDS, load_keybinds, save_keybinds
            self._keybinds = load_keybinds()
            list_btn_h = 40
            list_gap = 10
            ctrl_btn_w = 500
            ctrl_x = (self.screen.get_width() - ctrl_btn_w) // 2
            
            _action_names = {
                "move_up": "Движение вверх", "move_down": "Движение вниз",
                "move_left": "Движение влево", "move_right": "Движение вправо",
                "interact": "Взаимодействие (E)", "open_journal": "Журнал (J)",
                "dialogue_open": "Диалоговое окно (Tab)",
                "pause": "Пауза (ESC)", "console_enter": "Отправить ввод (Enter)"
            }
            
            for i, (key, val) in enumerate(self._keybinds.items()):
                name = _action_names.get(key, key)
                text = f"{name}: [{val.upper()}]"
                # Кнопка переназначения (пока заглушка, требующая отдельной логики ожидания клавиши)
                buttons.append(_SettingsButton(ctrl_x, start_y + i*(list_btn_h+list_gap), ctrl_btn_w, list_btn_h, text, _MENU_COLORS["btn_secondary"], _MENU_COLORS["btn_secondary_hover"], lambda k=key: self._rebind_key(k), tooltip="Нажмите, чтобы изменить клавишу"))

        # Универсальные кнопки внизу экрана (кроме вкладки LLM, там своя кнопка Назад)
        if self._active_tab not in ("llm", "controls"):  # AUDIT #14: controls сохраняет бинды сразу
            bottom_y = self.screen.get_height() - btn_h - 40
            buttons.append(_SettingsButton(self.screen.get_width() // 2 - btn_w - 20, bottom_y, btn_w, btn_h, "Применить", _MENU_COLORS["accent_green"], _MENU_COLORS["btn_primary_hover"], self._apply_graphics))
            buttons.append(_SettingsButton(self.screen.get_width() // 2 + 20, bottom_y, btn_w, btn_h, "Назад", _MENU_COLORS["btn_danger"], _MENU_COLORS["btn_danger_hover"], lambda: setattr(self, "_result", "back")))
            buttons.append(_SettingsButton(self.screen.get_width() // 2 + btn_w + 60, bottom_y, btn_w, btn_h, "Выход из игры", _MENU_COLORS["btn_danger"], _MENU_COLORS["btn_danger_hover"], self._confirm_exit))
        else:
            bottom_y = self.screen.get_height() - btn_h - 120
            buttons.append(_SettingsButton(self.screen.get_width() // 2 - 210, bottom_y, 200, btn_h, "Назад", _MENU_COLORS["btn_danger"], _MENU_COLORS["btn_danger_hover"], lambda: setattr(self, "_result", "back")))
            buttons.append(_SettingsButton(self.screen.get_width() // 2 + 10, bottom_y, 200, btn_h, "Выход из игры", _MENU_COLORS["btn_danger"], _MENU_COLORS["btn_danger_hover"], self._confirm_exit))

        return buttons

    def _switch_tab(self, tab):
        self._active_tab = tab
        if tab == "llm":
            self._llm_status = self._fetch_llm_status()
        self._llm_scroll_y = 0
        self.buttons = self._build_buttons()

    def _fetch_llm_status(self) -> dict:
        try:
            with urllib.request.urlopen("http://localhost:8000/api/llm/status", timeout=2.0) as r:
                _data = json.loads(r.read())
                # Фильтруем служебные поля, оставляем только словари моделей
                _models = {k: v for k, v in _data.items() if isinstance(v, dict) and "display_name" in v}
                return _models
        except Exception as e:
            print(f"UI: Ошибка получения статуса LLM: {e}")
            return getattr(self, "_llm_status", {})

    def _download_llm(self, model_key: str, force: bool = False):
        # Защита от двойного клика: если модалка уже открыта — игнорируем
        if getattr(self, "_is_dl_modal_open", False):
            return
        self._is_dl_modal_open = True
        
        try:
            _url = f"http://localhost:8000/api/llm/download/{model_key}"
            if force:
                _url += "?force=true"
            req = urllib.request.Request(_url, method="POST")
            urllib.request.urlopen(req, timeout=2)
        except Exception as e:
            print(f"Failed to start download: {e}")
            
        # Открываем модальное окно с прогресс-баром
        self._show_download_modal(model_key)
        
        self._llm_status = self._fetch_llm_status()
        self._llm_scroll_y = 0
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

    def _show_download_modal(self, model_key: str):
        """Блокирует UI и показывает прогресс скачивания со скоростью и временем."""
        import pygame
        import time
        
        _font = pygame.font.SysFont("consolas", 24, bold=True)
        _small_font = pygame.font.SysFont("consolas", 16)
        _dw, _dh = 500, 250  # Увеличили высоту для доп. текста
        _dx = (self.screen.get_width() - _dw) // 2
        _dy = (self.screen.get_height() - _dh) // 2
        _bar_rect = pygame.Rect(_dx + 50, _dy + 100, 400, 30)
        _cancel_rect = pygame.Rect(_dx + _dw//2 - 90, _dy + _dh - 55, 180, 38)
        
        waiting = True
        _last_tick = 0
        _last_size = 0
        _last_time = time.time()
        _speed_str = "..."
        _eta_str = "..."
        
        while waiting:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    sys.exit(0)
                elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    waiting = False
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    if _cancel_rect.collidepoint(event.pos):
                        # Отмена с удалением недокачанного файла на бэкенде
                        try:
                            _req = urllib.request.Request(
                                f"http://localhost:8000/api/llm/cancel/{model_key}", method="POST"
                            )
                            urllib.request.urlopen(_req, timeout=2)
                        except Exception as _e:
                            print(f"Failed to cancel download: {_e}")
                        waiting = False
                        
            _now = pygame.time.get_ticks()
            if _now - _last_tick > 1000:  # Обновляем раз в секунду для расчёта скорости
                _status = self._fetch_llm_status()
                _info = _status.get(model_key, {})
                
                _prog = _info.get("progress", 0.0)
                if _info.get("is_downloaded", False) or _prog >= 100.0:
                    # Скачано: НЕ советуем перезапуск — активация на лету возможна
                    # (llm_select перезапускает llama-server без перезапуска игры:
                    # kill + restart; диалоги подхватятся через llama_cpp_server_url).
                    # Спрашиваем игрока: активировать сейчас?
                    _q_font = pygame.font.SysFont("consolas", 18, bold=True)
                    _yes_rect = pygame.Rect(_dx + _dw//2 - 190, _dy + _dh - 60, 170, 40)
                    _no_rect = pygame.Rect(_dx + _dw//2 + 20, _dy + _dh - 60, 170, 40)
                    _choosing = True
                    while _choosing:
                        for event in pygame.event.get():
                            if event.type == pygame.QUIT:
                                sys.exit(0)
                            elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                                _choosing = False
                            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                                if _yes_rect.collidepoint(event.pos):
                                    _choosing = False
                                    waiting = False
                                    # Активация на лету: select = kill + restart
                                    # llama-server + тестовый промпт (вопрос/ответ)
                                    self._test_llm_modal(model_key)
                                elif _no_rect.collidepoint(event.pos):
                                    _choosing = False
                        pygame.draw.rect(self.screen, (20, 20, 20), (_dx, _dy, _dw, _dh), border_radius=8)
                        pygame.draw.rect(self.screen, _MENU_COLORS["accent_green"], (_dx, _dy, _dw, _dh), 2, border_radius=8)
                        _t1 = _q_font.render("Модель скачана!", True, _MENU_COLORS["accent_green"])
                        self.screen.blit(_t1, _t1.get_rect(center=(_dx + _dw//2, _dy + 60)))
                        _t2 = _small_font.render("Активировать сейчас? Сервер перезапустится,", True, _MENU_COLORS["text"])
                        self.screen.blit(_t2, _t2.get_rect(center=(_dx + _dw//2, _dy + 110)))
                        _t3 = _small_font.render("перезапуск игры не нужен.", True, _MENU_COLORS["text"])
                        self.screen.blit(_t3, _t3.get_rect(center=(_dx + _dw//2, _dy + 132)))
                        _mouse = pygame.mouse.get_pos()
                        _yh = _yes_rect.collidepoint(_mouse)
                        pygame.draw.rect(self.screen, _MENU_COLORS["accent_green"] if _yh else _MENU_COLORS["btn_primary"], _yes_rect.inflate(4, 4), border_radius=6)
                        _yt = _small_font.render("Да, активировать", True, _MENU_COLORS["text"])
                        self.screen.blit(_yt, _yt.get_rect(center=_yes_rect.center))
                        _nh = _no_rect.collidepoint(_mouse)
                        pygame.draw.rect(self.screen, _MENU_COLORS["btn_secondary_hover"] if _nh else _MENU_COLORS["btn_secondary"], _no_rect.inflate(4, 4), border_radius=6)
                        _nt = _small_font.render("Позже", True, _MENU_COLORS["text"])
                        self.screen.blit(_nt, _nt.get_rect(center=_no_rect.center))
                        pygame.display.flip()
                        self.clock.tick(30)
                    break
                if _info.get("error", False):
                    waiting = False
                    _err_msg = _info.get("error_message", "Неизвестная ошибка")
                    _err_surf = _small_font.render(f"Ошибка: {_err_msg}", True, (255, 50, 50))
                    self.screen.blit(_err_surf, _err_surf.get_rect(center=(_dx + _dw//2, _dy + 200)))
                    pygame.display.flip()
                    time.sleep(3)
                    break
                _f_size = _info.get("file_size_mb", 0)
                _r_size = _info.get("remote_size_mb", 0)
                
                # Вычисляем скорость (МБ/с)
                _curr_time = time.time()
                _dt = _curr_time - _last_time
                if _dt > 0:
                    _speed = (_f_size - _last_size) / _dt
                    if _speed > 0:
                        _speed_str = f"{_speed:.1f} МБ/с"
                        if _r_size > 0 and _speed > 0:
                            _eta_secs = (_r_size - _f_size) / _speed
                            _eta_str = f"~{int(_eta_secs // 60)}м {int(_eta_secs % 60)}с"
                            
                _last_size = _f_size
                _last_time = _curr_time
                _last_tick = _now
                
            # Рисуем окно
            pygame.draw.rect(self.screen, (20, 20, 20), (_dx, _dy, _dw, _dh), border_radius=8)
            pygame.draw.rect(self.screen, _MENU_COLORS["accent_blue"], (_dx, _dy, _dw, _dh), 2, border_radius=8)
            
            _title = _font.render("Скачивание модели...", True, _MENU_COLORS["text"])
            self.screen.blit(_title, _title.get_rect(center=(_dx + _dw//2, _dy + 40)))
            
            pygame.draw.rect(self.screen, (50, 50, 50), _bar_rect, border_radius=6)
            _fill_w = int(400 * (_prog / 100.0))
            if _fill_w > 0:
                pygame.draw.rect(self.screen, _MENU_COLORS["accent_green"], (_bar_rect.x, _bar_rect.y, _fill_w, _bar_rect.h), border_radius=6)
                
            _pct_text = _small_font.render(f"{_prog:.1f}%", True, _MENU_COLORS["text"])
            self.screen.blit(_pct_text, _pct_text.get_rect(center=_bar_rect.center))
            
            # Текст скорости и времени
            _stats_text = _small_font.render(f"Скорость: {_speed_str} | Осталось: {_eta_str}", True, _MENU_COLORS["text_dim"])
            self.screen.blit(_stats_text, _stats_text.get_rect(center=(_dx + _dw//2, _dy + 150)))
            
            _hint = _small_font.render("ESC - свернуть окно (загрузка продолжится)", True, _MENU_COLORS["text_dim"])
            self.screen.blit(_hint, _hint.get_rect(center=(_dx + _dw//2, _dy + 210)))
            
            # Кнопка отмены с подсветкой
            _c_hovered = _cancel_rect.collidepoint(pygame.mouse.get_pos())
            _c_color = _MENU_COLORS["btn_danger_hover"] if _c_hovered else _MENU_COLORS["btn_danger"]
            pygame.draw.rect(self.screen, _c_color, _cancel_rect.inflate(4, 4), border_radius=6)
            _c_text = _small_font.render("Отменить загрузку", True, _MENU_COLORS["text"])
            self.screen.blit(_c_text, _c_text.get_rect(center=_cancel_rect.center))
            
            pygame.display.flip()
            self.clock.tick(30)
            
        self._is_dl_modal_open = False  # Сбрасываем флаг при выходе из модалки

    def _show_model_actions_modal(self, model_key: str):
        """Показывает окно с выбором: Сделать активной, Скачать заново, Проверить модель."""
        import pygame
        _dw, _dh = 400, 350
        _dx = (self.screen.get_width() - _dw) // 2
        _dy = (self.screen.get_height() - _dh) // 2
        
        _font = pygame.font.SysFont("consolas", 24, bold=True)
        _btn_font = pygame.font.SysFont("consolas", 20, bold=True)
        
        _btn_w = 300
        _btn_h = 50
        _btn_x = _dx + (_dw - _btn_w) // 2
        
        _active_rect = pygame.Rect(_btn_x, _dy + 100, _btn_w, _btn_h)
        _redownload_rect = pygame.Rect(_btn_x, _dy + 170, _btn_w, _btn_h)
        _test_rect = pygame.Rect(_btn_x, _dy + 240, _btn_w, _btn_h)
        
        waiting = True
        while waiting:
            for event in pygame.event.get():
                if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    waiting = False
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    if _active_rect.collidepoint(event.pos):
                        self._select_llm(model_key)
                        waiting = False
                    elif _redownload_rect.collidepoint(event.pos):
                        self._download_llm(model_key, force=True)
                        waiting = False
                    elif _test_rect.collidepoint(event.pos):
                        self._test_llm_modal(model_key)
                        waiting = False
                elif event.type == pygame.QUIT:
                    sys.exit(0)
                    
            # Подсветка наведённых кнопок
            _mouse_pos = pygame.mouse.get_pos()
            _a_hovered = _active_rect.collidepoint(_mouse_pos)
            _r_hovered = _redownload_rect.collidepoint(_mouse_pos)
            _t_hovered = _test_rect.collidepoint(_mouse_pos)
            
            pygame.draw.rect(self.screen, (20, 20, 20), (_dx, _dy, _dw, _dh), border_radius=8)
            pygame.draw.rect(self.screen, _MENU_COLORS["accent_green"], (_dx, _dy, _dw, _dh), 2, border_radius=8)
            
            _title = _font.render("Действия с моделью", True, _MENU_COLORS["text"])
            self.screen.blit(_title, _title.get_rect(center=(_dx + _dw//2, _dy + 50)))
            
            _a_color = _MENU_COLORS["accent_blue"] if _a_hovered else _MENU_COLORS["accent_green"]
            pygame.draw.rect(self.screen, _a_color, _active_rect.inflate(4, 4), border_radius=6)
            _a_text = _btn_font.render("Сделать активной", True, _MENU_COLORS["text"])
            self.screen.blit(_a_text, _a_text.get_rect(center=_active_rect.center))
            
            _r_color = _MENU_COLORS["btn_danger_hover"] if _r_hovered else _MENU_COLORS["btn_danger"]
            pygame.draw.rect(self.screen, _r_color, _redownload_rect.inflate(4, 4), border_radius=6)
            _r_text = _btn_font.render("Скачать заново", True, _MENU_COLORS["text"])
            self.screen.blit(_r_text, _r_text.get_rect(center=_redownload_rect.center))
            
            _t_color = _MENU_COLORS["btn_primary_hover"] if _t_hovered else _MENU_COLORS["btn_primary"]
            pygame.draw.rect(self.screen, _t_color, _test_rect.inflate(4, 4), border_radius=6)
            _t_text = _btn_font.render("Проверить модель", True, _MENU_COLORS["text"])
            self.screen.blit(_t_text, _t_text.get_rect(center=_test_rect.center))
            
            pygame.display.flip()
            self.clock.tick(30)
        self.buttons = self._build_buttons()

    def _test_llm_modal(self, model_key: str):
        """Отправляет тестовый промпт и показывает ответ модели с переносом слов."""
        import pygame
        import textwrap
        
        _dw, _dh = 700, 450
        _dx = (self.screen.get_width() - _dw) // 2
        _dy = (self.screen.get_height() - _dh) // 2
        
        _font = pygame.font.SysFont("consolas", 24, bold=True)
        _small_font = pygame.font.SysFont("consolas", 14)
        
        # Рисуем ожидание
        pygame.draw.rect(self.screen, (20, 20, 20), (_dx, _dy, _dw, _dh), border_radius=8)
        _wait = _font.render("Идёт проверка модели...", True, _MENU_COLORS["text"])
        self.screen.blit(_wait, _wait.get_rect(center=(_dx + _dw//2, _dy + _dh//2)))
        pygame.display.flip()
        
        # Отправляем запрос
        try:
            req = urllib.request.Request(f"http://localhost:8000/api/llm/select/{model_key}", method="POST")
            with urllib.request.urlopen(req, timeout=120.0) as r:
                resp = json.loads(r.read())
                _question = resp.get("test_prompt", "")
                _answer = resp.get("test_response", "Модель не ответила.")
        except Exception as e:
            _question = ""
            _answer = f"Ошибка проверки: {e}"
            
        # Показываем ответ
        waiting = True
        while waiting:
            for event in pygame.event.get():
                if event.type == pygame.KEYDOWN and event.key in (pygame.K_ESCAPE, pygame.K_RETURN):
                    waiting = False
                elif event.type == pygame.QUIT:
                    sys.exit(0)
                    
            pygame.draw.rect(self.screen, (20, 20, 20), (_dx, _dy, _dw, _dh), border_radius=8)
            pygame.draw.rect(self.screen, _MENU_COLORS["accent_blue"], (_dx, _dy, _dw, _dh), 2, border_radius=8)
            
            _title = _font.render("Проверка модели", True, _MENU_COLORS["text"])
            self.screen.blit(_title, _title.get_rect(center=(_dx + _dw//2, _dy + 40)))
            
            _y = _dy + 90
            if _question:
                _q_title = _small_font.render("Вопрос:", True, _MENU_COLORS["accent_blue"])
                self.screen.blit(_q_title, (_dx + 20, _y))
                _y += 20
                # Перенос по словам (ширина 80 символов)
                _q_lines = textwrap.wrap(_question, width=80)
                for line in _q_lines[:4]:
                    _q_surf = _small_font.render(line, True, _MENU_COLORS["text_dim"])
                    self.screen.blit(_q_surf, (_dx + 20, _y))
                    _y += 18
                _y += 15
            
            _a_title = _small_font.render("Ответ:", True, _MENU_COLORS["accent_green"])
            self.screen.blit(_a_title, (_dx + 20, _y))
            _y += 20
            _a_lines = textwrap.wrap(_answer, width=80)
            for line in _a_lines[:7]:
                _a_surf = _small_font.render(line, True, _MENU_COLORS["text"])
                self.screen.blit(_a_surf, (_dx + 20, _y))
                _y += 18
            
            _hint = _small_font.render("Нажмите ESC или ENTER для закрытия", True, _MENU_COLORS["text_dim"])
            self.screen.blit(_hint, _hint.get_rect(center=(_dx + _dw//2, _dy + _dh - 25)))
            
            pygame.display.flip()
            self.clock.tick(30)
        self.buttons = self._build_buttons()

    def _confirm_exit(self):
        """Показывает диалог подтверждения выхода с кнопками Да/Нет."""
        import pygame
        _dw, _dh = 400, 250
        _dx = (self.screen.get_width() - _dw) // 2
        _dy = (self.screen.get_height() - _dh) // 2
        
        _font = pygame.font.SysFont("consolas", 24, bold=True)
        _btn_font = pygame.font.SysFont("consolas", 20, bold=True)
        
        _yes_rect = pygame.Rect(_dx + 40, _dy + 150, 140, 50)
        _no_rect = pygame.Rect(_dx + 220, _dy + 150, 140, 50)
        
        waiting = True
        while waiting:
            for event in pygame.event.get():
                if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    waiting = False
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    if _yes_rect.collidepoint(event.pos):
                        sys.exit(0)
                    elif _no_rect.collidepoint(event.pos):
                        waiting = False
                elif event.type == pygame.QUIT:
                    sys.exit(0)
                    
            # Подсветка наведённых кнопок
            _mouse_pos = pygame.mouse.get_pos()
            _yes_hovered = _yes_rect.collidepoint(_mouse_pos)
            _no_hovered = _no_rect.collidepoint(_mouse_pos)
            
            # Рисуем прямо на экране для гарантии отображения
            pygame.draw.rect(self.screen, (20, 20, 20), (_dx, _dy, _dw, _dh), border_radius=8)
            pygame.draw.rect(self.screen, _MENU_COLORS["btn_danger"], (_dx, _dy, _dw, _dh), 2, border_radius=8)
            
            _q = _font.render("Выйти из игры?", True, _MENU_COLORS["text"])
            self.screen.blit(_q, _q.get_rect(center=(_dx + _dw//2, _dy + 80)))
            
            _y_color = _MENU_COLORS["btn_danger_hover"] if _yes_hovered else _MENU_COLORS["btn_danger"]
            pygame.draw.rect(self.screen, _y_color, _yes_rect.inflate(4, 4), border_radius=6)
            _yes_text = _btn_font.render("Да", True, _MENU_COLORS["text"])
            self.screen.blit(_yes_text, _yes_text.get_rect(center=_yes_rect.center))
            
            _n_color = _MENU_COLORS["btn_secondary_hover"] if _no_hovered else _MENU_COLORS["btn_secondary"]
            pygame.draw.rect(self.screen, _n_color, _no_rect.inflate(4, 4), border_radius=6)
            _no_text = _btn_font.render("Нет", True, _MENU_COLORS["text"])
            self.screen.blit(_no_text, _no_text.get_rect(center=_no_rect.center))
            
            pygame.display.flip()
            self.clock.tick(30)
        self.buttons = self._build_buttons()

    def _rebind_key(self, action: str):
        """Открывает диалог ожидания нажатия новой клавиши."""
        # Визуальная подсказка
        self._llm_test_log = f"Нажмите новую клавишу для '{action}'..."
        self.buttons = self._build_buttons()
        
        import pygame
        waiting = True
        while waiting:
            for event in pygame.event.get():
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        waiting = False
                    else:
                        from keybindings import save_keybinds
                        _new_key = pygame.key.name(event.key).replace(" ", "_")
                        self._keybinds[action] = _new_key
                        save_keybinds(self._keybinds)
                        waiting = False
            self.screen.fill(_MENU_COLORS["bg_dark"])
            _surf = self.font_title.render("Нажмите клавишу...", True, _MENU_COLORS["text"])
            self.screen.blit(_surf, _surf.get_rect(center=(self.screen.get_width()//2, self.screen.get_height()//2)))
            pygame.display.flip()
            self.clock.tick(30)
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

    def run(self, initial_tab: str = "graphics"):
        self._active_tab = initial_tab
        self.buttons = self._build_buttons()
        self._result = None
        while self._result is None:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    sys.exit()
                elif event.type == pygame.VIDEORESIZE:
                    self.screen = pygame.display.set_mode((event.w, event.h), pygame.RESIZABLE)
                    self.buttons = self._build_buttons()
                elif event.type == pygame.MOUSEWHEEL:
                    if self._active_tab == "llm":
                        # Прокрутка с ускорением на высоких разрешениях
                        _scroll_speed = int(60 * self._scale)
                        self._llm_scroll_y = max(0, self._llm_scroll_y - event.y * _scroll_speed)
                        self.buttons = self._build_buttons()
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        self._result = "back"
                    elif event.key == pygame.K_RETURN:
                        hovered_btn = next((b for b in self.buttons if b.hovered), None)
                        if hovered_btn:
                            hovered_btn.on_click()
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
                
            # Полоса прокрутки для списка моделей
            if self._active_tab == "llm" and self._max_scroll > 0:
                _scrollbar_w = 8
                _scrollbar_x = self.screen.get_width() - 20
                _scrollbar_h = getattr(self, "_list_height", 0)
                _scrollbar_y = 150
                _content_h = getattr(self, "_content_height", 1)
                
                if _scrollbar_h > 0 and _content_h > _scrollbar_h:
                    # Фон полосы прокрутки
                    pygame.draw.rect(self.screen, (40, 40, 40), (_scrollbar_x, _scrollbar_y, _scrollbar_w, _scrollbar_h), border_radius=4)
                    
                    # Позиция ползунка
                    _thumb_h = max(30, int(_scrollbar_h * (_scrollbar_h / _content_h)))
                    _thumb_y = _scrollbar_y + int((_scrollbar_h - _thumb_h) * (self._llm_scroll_y / self._max_scroll))
                    
                    # Ползунок
                    pygame.draw.rect(self.screen, (100, 100, 100), (_scrollbar_x, _thumb_y, _scrollbar_w, _thumb_h), border_radius=4)
            
            pygame.display.flip()
            self.clock.tick(60)