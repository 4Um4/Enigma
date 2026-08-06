"""
path: /frontend/analysis_renderer.py
Назначение: Рендерер Третьего когнитивного слоя (Осознанный анализ). Журнал, Инвентарь, Статус.
Зависимости: pygame, constants, i18n
Основные сущности: AnalysisRenderer
"""
import pygame
import logging

from constants import (
    COLOR_DEATH_TITLE,
    COLOR_JOURNAL_TITLE,
    COLOR_NARRATOR,
    COLOR_NPC_NAME,
    COLOR_TEXT_DEFAULT,
    COLOR_TEXT_MUTED,
    COLOR_TEXT_OBS_LINE,
    COLOR_TEXT_OBS_TITLE,
    COLOR_TEXT_SCALE_HIGHLIGHT,
)
from i18n import t

logger = logging.getLogger(__name__)

class AnalysisRenderer:
    """Отвечает за отрисовку панелей, которые игрок открывает осознанно."""

    def __init__(self, screen: pygame.Surface):
        self.screen = screen

    def draw_journal(self, journal_data: list, active_tab: str, tab_rects: list) -> list:
        """Отрисовка панели Журнала (ADR-JOURNAL). Возвращает обновлённые хитбоксы вкладок."""
        if not journal_data:
            return []

        _panel_width = self.screen.get_width() // 3
        _journal_surf = pygame.Surface(
            (_panel_width, self.screen.get_height()), pygame.SRCALPHA
        )
        _journal_surf.fill((20, 20, 30, 220))

        _font_title = pygame.font.Font(None, 32)
        _title_surf = _font_title.render(t("ui:journal_title"), True, COLOR_JOURNAL_TITLE)
        _journal_surf.blit(_title_surf, (15, 15))

        _font_tab = pygame.font.Font(None, 24)
        _tab_y = 50
        _tab_x = 15
        _new_rects = []

        # Уникальные спикеры для вкладок
        _speakers = list(dict.fromkeys([e.get("speaker", "???") for e in journal_data]))
        if "all" not in _speakers:
            _speakers.insert(0, "all")

        for _spk in _speakers:
            _tab_name = "Все" if _spk == "all" else _spk
            _color = COLOR_TEXT_DEFAULT if _spk == active_tab else COLOR_TEXT_MUTED
            _tab_surf = _font_tab.render(_tab_name, True, _color)
            _journal_surf.blit(_tab_surf, (_tab_x, _tab_y))
            
            _abs_x = self.screen.get_width() - _panel_width + _tab_x
            _new_rects.append((_spk, pygame.Rect(_abs_x, _tab_y, _tab_surf.get_width(), _tab_surf.get_height())))
            _tab_x += _tab_surf.get_width() + 15

        _y_offset = 75

        if not journal_data:
            _font_text = pygame.font.Font(None, 22)
            _empty_surf = _font_text.render(t("ui:journal_empty"), True, COLOR_TEXT_MUTED)
            _journal_surf.blit(_empty_surf, (15, _y_offset))
        else:
            _font_name = pygame.font.Font(None, 26)
            _font_text = pygame.font.Font(None, 22)

            _filtered_data = journal_data if active_tab == "all" else [e for e in journal_data if e.get("speaker") == active_tab]

            for _entry in reversed(_filtered_data):
                _speaker = _entry.get("speaker", "???")
                _text = _entry.get("text", "")

                if _speaker == t("ui:narrator"):
                    _color = COLOR_NARRATOR
                elif _speaker == t("ui:npc_label"):
                    _color = COLOR_NPC_NAME
                else:
                    _color = COLOR_TEXT_DEFAULT

                _name_surf = _font_name.render(f"{_speaker}:", True, _color)
                _journal_surf.blit(_name_surf, (15, _y_offset))
                _y_offset += 24

                _words = _text.split(" ")
                _lines = []
                _current_line = ""
                for _word in _words:
                    _test_line = _current_line + _word + " "
                    if _font_text.size(_test_line)[0] < _panel_width - 30:
                        _current_line = _test_line
                    else:
                        _lines.append(_current_line)
                        _current_line = _word + " "
                _lines.append(_current_line)

                for _line in _lines:
                    _text_surf = _font_text.render(_line, True, COLOR_TEXT_DEFAULT)
                    _journal_surf.blit(_text_surf, (15, _y_offset))
                    _y_offset += 20

                _y_offset += 10
                if _y_offset > self.screen.get_height() - 40:
                    break

        self.screen.blit(_journal_surf, (self.screen.get_width() - _panel_width, 0))
        return _new_rects

    def draw_inventory(self, topo_dict: dict) -> None:
        """Отрисовка панели инвентаря (BodyTopology)."""
        if not topo_dict:
            return

        _panel_width = self.screen.get_width() // 3
        _inv_surf = pygame.Surface((_panel_width, self.screen.get_height()), pygame.SRCALPHA)
        _inv_surf.fill((20, 20, 30, 220))

        _font_title = pygame.font.Font(None, 32)
        _title_surf = _font_title.render("ИНВЕНТАРЬ", True, COLOR_JOURNAL_TITLE)
        _inv_surf.blit(_title_surf, (15, 15))

        _font_slot = pygame.font.Font(None, 26)
        _font_item = pygame.font.Font(None, 22)
        _font_stats = pygame.font.Font(None, 24)

        _y_offset = 50

        _slot_groups = [
            ("Руки", topo_dict.get("hands", {})),
            ("Надето", topo_dict.get("worn", {})),
            ("Пояс", topo_dict.get("belt", [])),
            ("Карманы", topo_dict.get("pockets", [])),
            ("Рюкзак", topo_dict.get("backpack", [])),
            ("Скрытое", topo_dict.get("hidden", [])),
        ]

        _contents = topo_dict.get("contents", {})

        for _group_name, _slots in _slot_groups:
            if not _slots:
                continue

            _grp_surf = _font_slot.render(f"[{_group_name}]", True, COLOR_TEXT_OBS_TITLE)
            _inv_surf.blit(_grp_surf, (15, _y_offset))
            _y_offset += 28

            _slot_list = list(_slots.values()) if isinstance(_slots, dict) else _slots

            for _slot in _slot_list:
                _slot_id = _slot.get("slot_id", "unknown")
                _body_part = _slot.get("body_part", "")
                _items = _contents.get(_slot_id, [])

                _slot_label = f"  - {_body_part} ({_slot_id})"
                _slot_surf = _font_item.render(_slot_label, True, COLOR_TEXT_MUTED)
                _inv_surf.blit(_slot_surf, (20, _y_offset))
                _y_offset += 22

                if _items:
                    for _item in _items:
                        _item_name = _item.get("name", "Предмет")
                        _weight = _item.get("weight", 0.0)
                        _bulk = _item.get("bulk", 1)
                        _item_text = f"    • {_item_name} (В:{_weight} кг, Г:{_bulk})"
                        _item_surf = _font_item.render(_item_text, True, COLOR_TEXT_DEFAULT)
                        _inv_surf.blit(_item_surf, (25, _y_offset))
                        _y_offset += 20
                
                _y_offset += 5
                if _y_offset > self.screen.get_height() - 100:
                    break
            
            if _y_offset > self.screen.get_height() - 100:
                break

        _y_stats = self.screen.get_height() - 80
        _total_weight = sum(i.get("weight", 0.0) for items in _contents.values() for i in items)
        _total_bulk = sum(i.get("bulk", 1) for items in _contents.values() for i in items)
        _carry_cap = topo_dict.get("strength_score", 10) * 15.0

        _weight_color = COLOR_TEXT_DEFAULT if _total_weight <= _carry_cap else COLOR_DEATH_TITLE

        _stats_w = _font_stats.render(f"Вес: {_total_weight:.1f} / {_carry_cap:.1f}", True, _weight_color)
        _stats_b = _font_stats.render(f"Габаритность: {_total_bulk}", True, COLOR_TEXT_DEFAULT)
        
        _inv_surf.blit(_stats_w, (15, _y_stats))
        _inv_surf.blit(_stats_b, (15, _y_stats + 25))

        self.screen.blit(_inv_surf, (self.screen.get_width() - _panel_width, 0))

    def draw_embodied_status(self, status_data: dict) -> None:
        """S151: Отрисовка текстовой панели статуса аватара (Embodied Status)."""
        if not status_data:
            return

        _panel_w, _panel_h = 260, 180
        _surf = pygame.Surface((_panel_w, _panel_h), pygame.SRCALPHA)
        _surf.fill((15, 15, 20, 200)) # Полупрозрачный фон

        _font_title = pygame.font.Font(None, 28)
        _font_text = pygame.font.Font(None, 24)

        _y = 10
        
        # Заголовок
        _title = _font_title.render("СОСТОЯНИЕ", True, (200, 200, 200))
        _surf.blit(_title, (10, _y))
        _y += 35

        # Золото, еда и вес
        _gold = status_data.get("gold", 0.0)
        _food = status_data.get("food_count", 0.0)
        _weight = status_data.get("current_weight", 0.0)
        _max_weight = status_data.get("max_weight", 0.0)

        _gold_txt = _font_text.render(f"Золото:      {_gold:.1f} G", True, (255, 215, 0))
        _surf.blit(_gold_txt, (10, _y)); _y += 25

        _food_txt = _font_text.render(f"Провизия:    {_food:.0f} порц.", True, (200, 200, 200))
        _surf.blit(_food_txt, (10, _y)); _y += 25

        if _max_weight > 0:
            _weight_txt = _font_text.render(f"Вес:         {_weight:.1f}/{_max_weight:.0f}", True, (200, 200, 200))
            _surf.blit(_weight_txt, (10, _y)); _y += 25

        # Разделитель
        pygame.draw.line(_surf, (100, 100, 100), (10, _y), (_panel_w - 10, _y))
        _y += 10

        # Активные потребности
        _needs = status_data.get("active_needs", [])
        
        _color_map = {
            "minor": (200, 200, 200),
            "moderate": (255, 255, 0),
            "major": (255, 165, 0),
            "critical": (255, 50, 50),
            "extreme": (180, 0, 0)
        }
        _label_map = {
            "food": "Голод",
            "income": "Финансы",
            "shelter": "Усталость",
            "social": "Одиночество"
        }
        _state_map = {
            "food":      {"minor": "Лёгкий", "moderate": "Заметный", "major": "Сильный", "critical": "Критический", "extreme": "Мучительный"},
            "income":    {"minor": "Стабильны", "moderate": "Напряжённы", "major": "Скудны", "critical": "Критичны", "extreme": "Нищета"},
            "shelter":   {"minor": "Лёгкая", "moderate": "Заметная", "major": "Сильная", "critical": "Критическая", "extreme": "Изнеможение"},
            "social":    {"minor": "Лёгкое", "moderate": "Заметное", "major": "Сильное", "critical": "Критическое", "extreme": "Тотальное"}
        }

        for need in _needs:
            _nid = need.get("id", "")
            _sev = need.get("severity", "minor")
            _label = _label_map.get(_nid, _nid)
            _need_states = _state_map.get(_nid, {})
            _state_txt = _need_states.get(_sev, _sev.capitalize())
            _color = _color_map.get(_sev, (200, 200, 200))
            _txt = f"{_label:<12} {_state_txt}"
            _need_surf = _font_text.render(_txt, True, _color)
            _surf.blit(_need_surf, (10, _y))
            _y += 25

        _x = 15
        _y_pos = self.screen.get_height() - _panel_h - 15
        self.screen.blit(_surf, (_x, _y_pos))