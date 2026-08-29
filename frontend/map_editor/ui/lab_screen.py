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
from ui.graphs import BarChart, LineGraph

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
        # Задача 3: история принадлежит LabScreen (graphs.py — чистые
        # рендереры); выбранный NPC — клик по карточке.
        self.npc_history: dict = {}
        self.selected_npc_id: Optional[str] = None
        self._card_rects: list = []
        self.graph_trust = LineGraph("Доверие к игроку", -100.0, 100.0, "accent_green")
        self.graph_stress = LineGraph("Стресс", 0.0, 100.0, "accent_red")
        self.graph_drives = BarChart("Активные драйвы")
        self.runner = None
        self.experiment_id = "—"

    def enter(self):
        """Вызывается при переходе в режим Лаборатории."""
        from app.services.calibration.experiment_runner import ExperimentRunner, ExperimentConfig
        self.runner = ExperimentRunner()
        
        # В будущем: брать пресет из настроек UI
        preset_path = "config/calibration/test_presets/enigma_golden.yaml"
        config = ExperimentConfig(
            preset_path=preset_path,
            duration_ticks=300,
            scenario_path="config/calibration/scenarios/trust_probe_v1.yaml",
        )
        
        try:
            self.experiment_id = self.runner.start(config)
            self.is_running = True
            self.is_paused = False
            self.current_tick = 0
            self.npc_history = {}
            self.selected_npc_id = None
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

        # Задача 3: клик по карточке NPC = выбор для панели графиков
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for _rect, _nid in self._card_rects:
                if _rect.collidepoint(event.pos):
                    self.selected_npc_id = _nid
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
            # Задача 3: история на каждый тик (trust из SSOT-ключа
            # "npc→player", stress из psyche — те же источники, что у карточек)
            for npc in self.npc_states:
                _nid = npc.get("id", npc.get("npc_id", "?"))
                _hist = self.npc_history.setdefault(_nid, {"trust": [], "stress": []})
                _rel_pair = self.relationships.get(f"{_nid}→player", {})
                _hist["trust"].append(float(_rel_pair.get("trust", 0.0)))
                _hist["stress"].append(float(npc.get("psyche", {}).get("stress", 0)))
                if len(_hist["trust"]) > 300:
                    _hist["trust"].pop(0)
                    _hist["stress"].pop(0)
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
        
        # Задача 3: хитбоксы карточек (клик = выбор NPC для панели графиков)
        self._card_rects = []
        for i, npc in enumerate(self.npc_states):
            x = col1_x if i % 2 == 0 else col2_x
            if i % 2 == 0 and i > 0:
                y += card_h + spacing
            self._card_rects.append(
                (pygame.Rect(x, y, card_w, card_h),
                 npc.get("id", npc.get("npc_id", "?")))
            )
            self._draw_npc_card(x, y, card_w, card_h, npc)

        self._draw_graphs_panel(card_w, spacing)

    def _draw_graphs_panel(self, card_w: int, spacing: int):
        """Задача 3: правая панель — динамика доверия/стресса и драйвы
        выбранного NPC (клик по карточке). История — self.npc_history."""
        if not self.selected_npc_id and self.npc_states:
            self.selected_npc_id = self.npc_states[0].get(
                "id", self.npc_states[0].get("npc_id", "?")
            )
        if not self.selected_npc_id:
            return
        hist = self.npc_history.get(
            self.selected_npc_id, {"trust": [], "stress": []}
        )
        sel_npc = next(
            (n for n in self.npc_states
             if n.get("id", n.get("npc_id", "?")) == self.selected_npc_id),
            None,
        )

        panel_x = 20 + 2 * card_w + 2 * spacing
        panel_w = self.screen.get_width() - panel_x - 20
        if panel_w < 280:
            return  # узкий экран: карточки приоритетнее, панель не влезает

        header = self.font_bold.render(
            f"Динамика: {self.selected_npc_id.replace('_', ' ').title()}",
            True, COLORS["text_highlight"],
        )
        self.screen.blit(header, (panel_x, 112))
        self.graph_trust.draw(
            self.screen, (panel_x, 138, panel_w, 155),
            hist["trust"], COLORS, self.font_small, self.font_bold,
        )
        self.graph_stress.draw(
            self.screen, (panel_x, 303, panel_w, 155),
            hist["stress"], COLORS, self.font_small, self.font_bold,
        )
        drives = (sel_npc or {}).get("drives") or {}
        if drives:
            items = [
                ("Контроль", float(drives.get("control", 0.0)), "accent_yellow"),
                ("Значимость", float(drives.get("significance", 0.0)), "text_highlight"),
                ("Страх", float(drives.get("fear", 0.0)), "accent_red"),
                ("Желание", float(drives.get("desire", 0.0)), "accent_green"),
            ]
        else:
            items = []
        self.graph_drives.draw(
            self.screen, (panel_x, 468, panel_w, 130),
            items, COLORS, self.font_small, self.font_bold, max_val=1.0,
        )

    def _draw_npc_card(self, x: int, y: int, w: int, h: int, npc: dict):
        """Рисует карточку состояния NPC."""
        npc_id = npc.get("id", "unknown")
        npc_name = npc_id.replace("_", " ").title()
        
        # Фон карточки
        rect = pygame.Rect(x, y, w, h)
        pygame.draw.rect(self.screen, COLORS["bg_panel"], rect, border_radius=6)
        # Задача 3: выбранная карточка выделена зелёной рамкой
        _is_sel = npc_id == self.selected_npc_id
        pygame.draw.rect(
            self.screen,
            COLORS["accent_green"] if _is_sel else COLORS["border"],
            rect, 2 if _is_sel else 1, border_radius=6,
        )
        
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