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

        # S166: Вкладки инструмента расследования (Закон XII)
        _tabs = [
            ("observations", "Наблюдения"),
            ("hypotheses", "Гипотезы"),
            ("facts", "Факты")
        ]

        for _tab_id, _tab_name in _tabs:
            _color = COLOR_TEXT_DEFAULT if _tab_id == active_tab else COLOR_TEXT_MUTED
            _tab_surf = _font_tab.render(_tab_name, True, _color)
            _journal_surf.blit(_tab_surf, (_tab_x, _tab_y))
            
            _abs_x = self.screen.get_width() - _panel_width + _tab_x
            _new_rects.append((_tab_id, pygame.Rect(_abs_x, _tab_y, _tab_surf.get_width(), _tab_surf.get_height())))
            _tab_x += _tab_surf.get_width() + 15

        _y_offset = 75
        _font_text = pygame.font.Font(None, 22)
        _font_name = pygame.font.Font(None, 26)

        if active_tab == "observations":
            if not journal_data:
                _empty_surf = _font_text.render("Вы ничего не заметили.", True, COLOR_TEXT_MUTED)
                _journal_surf.blit(_empty_surf, (15, _y_offset))
            else:
                for _entry in reversed(journal_data):
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
        elif active_tab == "hypotheses":
            _empty_surf = _font_text.render("У вас пока нет гипотез.", True, COLOR_TEXT_MUTED)
            _journal_surf.blit(_empty_surf, (15, _y_offset))
        elif active_tab == "facts":
            _empty_surf = _font_text.render("Установленных фактов нет.", True, COLOR_TEXT_MUTED)
            _journal_surf.blit(_empty_surf, (15, _y_offset))

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
        """S164: Minimalist HUD (Закон Минимального Вмешательства). 
        Рисует только критичные потребности в виде мини-иконок в углу."""
        if not status_data:
            return

        _needs = status_data.get("active_needs", [])
        _weight = status_data.get("current_weight", 0.0)
        _max_weight = status_data.get("max_weight", 0.0)

        _icon_size = 12
        _spacing = 6
        _start_x = 15
        _start_y = self.screen.get_height() - _icon_size - 15

        # 1. Иконка перегруза (вес)
        if _max_weight > 0 and _weight > _max_weight * 0.8:
            _color = (255, 50, 50) if _weight > _max_weight else (255, 165, 0)
            pygame.draw.rect(self.screen, _color, (_start_x, _start_y, _icon_size, _icon_size))
            _start_x += _icon_size + _spacing

        # 2. Иконки потребностей (только moderate и выше)
        _color_map = {
            "moderate": (255, 255, 0),
            "major": (255, 165, 0),
            "critical": (255, 50, 50),
            "extreme": (180, 0, 0)
        }
        _shape_map = {
            "food": "circle",      # Голод
            "income": "diamond",   # Финансы
            "shelter": "square",   # Усталость
            "social": "triangle"   # Одиночество
        }

        for need in _needs:
            _nid = need.get("id", "")
            _sev = need.get("severity", "minor")
            
            if _sev in _color_map:
                _color = _color_map[_sev]
                _shape = _shape_map.get(_nid, "square")
                
                if _shape == "circle":
                    pygame.draw.circle(self.screen, _color, (_start_x + _icon_size//2, _start_y + _icon_size//2), _icon_size//2)
                elif _shape == "diamond":
                    pygame.draw.polygon(self.screen, _color, [
                        (_start_x + _icon_size//2, _start_y),
                        (_start_x + _icon_size, _start_y + _icon_size//2),
                        (_start_x + _icon_size//2, _start_y + _icon_size),
                        (_start_x, _start_y + _icon_size//2)
                    ])
                elif _shape == "triangle":
                    pygame.draw.polygon(self.screen, _color, [
                        (_start_x + _icon_size//2, _start_y),
                        (_start_x + _icon_size, _start_y + _icon_size),
                        (_start_x, _start_y + _icon_size)
                    ])
                else: # square
                    pygame.draw.rect(self.screen, _color, (_start_x, _start_y, _icon_size, _icon_size))
                
                _start_x += _icon_size + _spacing