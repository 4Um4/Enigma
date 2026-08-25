"""
map_editor/ui/lab_screen.py
Полноэкранный интерфейс Лаборатории калибровки психики (Вариант B).
Управляет запуском симуляции, отображает графики и состояние NPC в реальном времени.
"""
import sys
import os
import pygame
from typing import Optional

from ui.components import Button, COLORS
from tools.constants import MODE_LOCAL

# Вычисляем абсолютный путь к папке backend и добавляем в sys.path
_BACKEND_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', 'backend'))
if _BACKEND_PATH not in sys.path:
    sys.path.insert(0, _BACKEND_PATH)


class LabScreen:
    """Управляет отрисовкой и логикой полноэкранного режима Лаборатории."""

    def __init__(self, core):
        self.core = core
        self.screen = core.screen
        self.font = core.font
        self.font_small = core.font_small
        self.font_bold = core.font_bold
        
        # Кнопки управления
        btn_y = 60
        self.btn_pause = Button(20, btn_y, 110, 30, "Пауза", color_key="btn_primary")
        self.btn_step = Button(140, btn_y, 110, 30, "Шаг +1", color_key="btn_secondary")
        self.btn_speed = Button(260, btn_y, 110, 30, "Скор x1", color_key="btn_secondary")
        self.btn_exit = Button(self.screen.get_width() - 140, 10, 120, 30, "Выход (Esc)", color_key="btn_danger")
        
        # Состояние симуляции
        self.is_running = False
        self.is_paused = False
        self.speed_multiplier = 1
        self.current_tick = 0
        self.npc_states = []
        self.relationships = {}
        self.runner = None
        self.experiment_id = "—"

    def enter(self):
        """Вызывается при переходе в режим Лаборатории."""
        from app.services.calibration.experiment_runner import ExperimentRunner, ExperimentConfig
        self.runner = ExperimentRunner()
        
        # В будущем: брать пресет из настроек UI
        preset_path = "config/calibration/test_presets/enigma_golden.yaml"
        config = ExperimentConfig(preset_path=preset_path, duration_ticks=300)
        
        try:
            self.experiment_id = self.runner.start(config)
            self.is_running = True
            self.is_paused = False
            self.current_tick = 0
            self.core._show_toast("Симуляция запущена")
        except Exception as e:
            self.core._show_toast(f"Ошибка запуска: {e}")
            self.is_running = False

    def exit(self):
        """Вызывается при выходе из режима Лаборатории."""
        if self.is_running and self.runner:
            try:
                self.runner.stop()
                self.core._show_toast("Симуляция остановлена")
            except Exception as e:
                print(f"Ошибка остановки симуляции: {e}")
            self.is_running = False
            self.runner = None

    def handle_event(self, event: pygame.event.Event) -> bool:
        """Обрабатывает события мыши и клавиатуры в Лаборатории."""
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self.exit()
                self.core.mode = MODE_LOCAL
                return True
            elif event.key == pygame.K_SPACE:
                self.is_paused = not self.is_paused
                return True
            elif event.key == pygame.K_RIGHT and self.is_paused:
                # Шаг вперёд при паузе
                self._step_simulation(1)
                return True
                
        # Кнопки UI
        if self.btn_exit.handle_event(event):
            self.exit()
            self.core.mode = MODE_LOCAL
            return True
            
        if self.btn_pause.handle_event(event):
            self.is_paused = not self.is_paused
            return True
            
        if self.btn_step.handle_event(event):
            self._step_simulation(1)
            return True
            
        if self.btn_speed.handle_event(event):
            # Циклически меняем скорость: 1 -> 2 -> 5 -> 10
            speeds = [1, 2, 5, 10]
            curr_idx = speeds.index(self.speed_multiplier) if self.speed_multiplier in speeds else 0
            next_idx = (curr_idx + 1) % len(speeds)
            self.speed_multiplier = speeds[next_idx]
            self.btn_speed.text = f"Скор x{self.speed_multiplier}"
            return True
            
        return False

    def _step_simulation(self, ticks: int):
        """Внутренний метод для выполнения тиков."""
        if not self.is_running or not self.runner:
            return
        try:
            state = self.runner.step(ticks)
            self.current_tick = state.get("tick", 0)
            self.npc_states = state.get("npcs", [])
            self.relationships = state.get("relationships", {})
        except Exception as e:
            print(f"Ошибка симуляции: {e}")
            self.is_running = False

    def update(self):
        """Обновляет состояние симуляции (вызывается каждый кадр)."""
        if not self.is_running or not self.runner or self.is_paused:
            return
            
        # Делаем N тиков за кадр в зависимости от скорости
        self._step_simulation(self.speed_multiplier)

    def draw(self):
        """Отрисовывает интерфейс Лаборатории."""
        # Фон
        self.screen.fill(COLORS["bg_dark"])
        
        # Верхняя панель
        pygame.draw.rect(self.screen, COLORS["bg_menu"], (0, 0, self.screen.get_width(), 50))
        pygame.draw.line(self.screen, COLORS["border"], (0, 50), (self.screen.get_width(), 50))
        
        # Заголовок
        title = self.font_bold.render("ЛАБОРАТОРИЯ КАЛИБРОВКИ ПСИХИКИ ENIGMA", True, COLORS["text_highlight"])
        self.screen.blit(title, (20, 12))
        
        # Кнопка выхода
        self.btn_exit.draw(self.screen, self.font)
        
        # Панель управления
        ctrl_y = 60
        self.btn_pause.text = "Продолжить" if self.is_paused else "Пауза"
        self.btn_pause.color_key = "btn_success" if self.is_paused else "btn_primary"
        self.btn_pause.draw(self.screen, self.font)
        self.btn_step.draw(self.screen, self.font)
        self.btn_speed.draw(self.screen, self.font)
        
        # Информация о симуляции
        status_text = "ПАУЗА" if self.is_paused else ("АКТИВНА" if self.is_running else "ОСТАНОВЛЕНА")
        status_color = COLORS["accent_yellow"] if self.is_paused else (COLORS["accent_green"] if self.is_running else COLORS["accent_red"])
        
        info_text = f"Тик: {self.current_tick} | Статус: {status_text} | Скорость: x{self.speed_multiplier}"
        info = self.font_small.render(info_text, True, status_color)
        self.screen.blit(info, (400, 65))
        
        # Отрисовка карточек NPC
        y = 110
        card_w = 380
        card_h = 120
        spacing = 15
        
        # Размещаем в 2 колонки
        col1_x = 20
        col2_x = 20 + card_w + spacing
        
        for i, npc in enumerate(self.npc_states):
            x = col1_x if i % 2 == 0 else col2_x
            if i % 2 == 0 and i > 0:
                y += card_h + spacing
                
            self._draw_npc_card(x, y, card_w, card_h, npc)

    def _draw_npc_card(self, x: int, y: int, w: int, h: int, npc: dict):
        """Рисует карточку состояния NPC."""
        npc_id = npc.get("id", "unknown")
        npc_name = npc_id.replace("_", " ").title()
        
        # Фон карточки
        rect = pygame.Rect(x, y, w, h)
        pygame.draw.rect(self.screen, COLORS["bg_panel"], rect, border_radius=6)
        pygame.draw.rect(self.screen, COLORS["border"], rect, 1, border_radius=6)
        
        # Имя NPC
        name_surf = self.font.render(npc_name, True, COLORS["text_highlight"])
        self.screen.blit(name_surf, (rect.x + 10, rect.y + 5))
        
        # Данные
        psyche = npc.get("psyche", {})
        # Trust живёт в RelationshipStore (SSOT): кэш в NPCState запрещён
        # (L13) и не обновляется. Направление NPC -> player (компилятор:
        # source=цель действия, target=actor).
        
        stress = float(psyche.get("stress", 0))
        _rel_pair = self.relationships.get(f"{npc_id}→player", {})
        trust = float(_rel_pair.get("trust", 0.0))
        willpower = float(psyche.get("willpower", 0))
        breakpoint = float(psyche.get("breakpoint", 0))
        
        # Полоска стресса (красная)
        bar_x = rect.x + 10
        bar_w = w - 20
        # Фон полоски
        pygame.draw.rect(self.screen, COLORS["bg_input"], (bar_x, rect.y + 35, bar_w, 12), border_radius=2)
        # Заполнение
        stress_ratio = min(1.0, stress / 100.0)
        fill_w = int(bar_w * stress_ratio)
        stress_color = COLORS["accent_red"] if stress > breakpoint else COLORS["accent_yellow"]
        pygame.draw.rect(self.screen, stress_color, (bar_x, rect.y + 35, fill_w, 12), border_radius=2)
        # Подпись
        stress_txt = self.font_small.render(f"Стресс: {stress:.0f} / 100", True, COLORS["text"])
        self.screen.blit(stress_txt, (bar_x, rect.y + 50))
        
        # Полоска доверия (зелёная)
        pygame.draw.rect(self.screen, COLORS["bg_input"], (bar_x, rect.y + 70, bar_w, 12), border_radius=2)
        # Trust может быть от -100 до 100
        trust_ratio = abs(trust) / 100.0
        fill_w = int(bar_w * trust_ratio)
        trust_color = COLORS["accent_green"] if trust >= 0 else COLORS["accent_red"]
        pygame.draw.rect(self.screen, trust_color, (bar_x, rect.y + 70, fill_w, 12), border_radius=2)
        trust_txt = self.font_small.render(f"Доверие: {trust:.0f}", True, COLORS["text"])
        self.screen.blit(trust_txt, (bar_x, rect.y + 85))
        
        # Воля и Порог (справа)
        stats_x = rect.x + w - 100
        will_surf = self.font_small.render(f"Воля: {willpower:.0f}", True, COLORS["text"])
        self.screen.blit(will_surf, (stats_x, rect.y + 35))
        bp_surf = self.font_small.render(f"Порог: {breakpoint:.0f}", True, COLORS["text"])
        self.screen.blit(bp_surf, (stats_x, rect.y + 55))