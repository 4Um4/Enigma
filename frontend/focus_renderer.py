"""
path: /frontend/focus_renderer.py
Назначение: Рендерер Первого когнитивного слоя (Фокус). Рисует поверх мира (Слой 0).
Отвечает за Speech Bubbles, manifestations и input bubble.
Зависимости: pygame, constants
Основные сущности: FocusRenderer
"""
import math
import random
import pygame
from typing import Optional, Dict
from constants import COLOR_MANIFEST_DEFAULT

class FocusRenderer:
    """Рисует элементы фокуса внимания поверх сцены."""

    def __init__(self, font_small: pygame.font.Font):
        self.font_small = font_small
        self._activity_cache = {}  # S165: Кэш для отслеживания смены активности
        self._activity_timers = {} # S165: Таймеры исчезновения маркеров

    def draw_manifestations(self, screen: pygame.Surface, npc_coords: dict, manifest_indicators: dict) -> None:
        """Отрисовка наблюдаемых физических проявлений (текст под именем)."""
        if not manifest_indicators:
            return
            
        for npc_id, coords in npc_coords.items():
            _manif = manifest_indicators.get(npc_id)
            if _manif and _manif.get("text"):
                _manif_text = _manif.get("text", "")
                _manif_color = _manif.get("color", COLOR_MANIFEST_DEFAULT)
                _manif_surf = self.font_small.render(_manif_text, True, _manif_color)
                screen.blit(
                    _manif_surf, 
                    (coords["sx"] - _manif_surf.get_width() // 2, coords["sy"] + coords["radius"] + 14)
                )

    def draw_action_markers(self, screen: pygame.Surface, npc_coords: dict, entities: list) -> None:
        """S163/S165: Отрисовка пиктограмм действий над NPC (Закон Локальности и Временности)."""
        _activity_map = {
            "working": (180, 180, 180),
            "eating": (200, 180, 100),
            "talking": (100, 180, 100),
            "walking": (150, 150, 200),
            "idle": None,
        }
        _now = pygame.time.get_ticks()
        
        for entity in entities:
            if entity.entity_type != "npc" or not entity.visible:
                continue
                
            _coords = npc_coords.get(entity.entity_id)
            if not _coords:
                continue
                
            _activity = getattr(entity, "activity", "idle")
            
            # S165: Запускаем таймер только при смене активности
            if _activity != self._activity_cache.get(entity.entity_id):
                if _activity in _activity_map and _activity_map[_activity] is not None:
                    self._activity_timers[entity.entity_id] = _now + 1000  # Живёт 1 секунду
                self._activity_cache[entity.entity_id] = _activity

            # Рисуем, если таймер активен
            if _now < self._activity_timers.get(entity.entity_id, 0):
                _color = _activity_map.get(_activity, (255, 255, 255))
                _sx = _coords["sx"]
                _sy = _coords["sy"] - _coords["radius"] - 32
                
                # Плавное исчезновение в последние 0.2 секунды
                _time_left = self._activity_timers[entity.entity_id] - _now
                if _time_left < 200:
                    _alpha = int(255 * (_time_left / 200.0))
                else:
                    _alpha = 255

                # S167: Микро-анимации действий (плавный синусоидальный цикл)
                _anim_phase = (_now % 800) / 800.0 * 2 * math.pi
                _anim_offset = math.sin(_anim_phase) * 4  # Амплитуда 4 пикселя

                _icon_surf = pygame.Surface((16, 16), pygame.SRCALPHA)

                if _activity == "working":
                    # Молоток: черенок + головка, двигается вверх-вниз
                    pygame.draw.line(_icon_surf, (*_color, _alpha), (8, 8), (8, 8 + _anim_offset), 2)
                    pygame.draw.rect(_icon_surf, (*_color, _alpha), (5, 4 + _anim_offset, 6, 4))
                elif _activity == "eating":
                    # Кружка: эллипс + ручка, поднимается ко рту
                    pygame.draw.ellipse(_icon_surf, (*_color, _alpha), (4, 6, 8, 8))
                    pygame.draw.arc(_icon_surf, (*_color, _alpha), (10, 6, 6, 6), 4.7, 7.8, 2)
                    screen.blit(_icon_surf, (_sx - 8, _sy - 8 - _anim_offset))
                    return
                elif _activity == "walking":
                    # Следы: два прямоугольника, пульсирующие по фазе
                    _step = int(_anim_phase / math.pi) % 2
                    pygame.draw.rect(_icon_surf, (*_color, _alpha), (4, 8, 4, 2) if _step == 0 else (10, 8, 4, 2))
                else:
                    # Базовый квадрат (fallback)
                    pygame.draw.rect(_icon_surf, (*_color, _alpha), (5, 5, 6, 6))

                screen.blit(_icon_surf, (_sx - 8, _sy - 8))

    def draw_bubbles(self, screen: pygame.Surface, npc_coords: dict, speech_bubbles: dict, player_coords: dict, player_speech: Optional[dict]) -> None:
        """Отрисовка речевых облачков с разрешением коллизий."""
        _pending_bubbles = []
        
        # NPC Bubbles
        if speech_bubbles:
            for npc_id, coords in npc_coords.items():
                _bubble_data = speech_bubbles.get(npc_id)
                if _bubble_data:
                    _age = pygame.time.get_ticks() - _bubble_data["tick"]
                    if _age < 6000:
                        if _age < 200:
                            _alpha = int(255 * (_age / 200.0))  # Fade-in 0.2 сек
                        elif _age < 5000:
                            _alpha = 255  # Удержание
                        else:
                            _alpha = int(255 * (1.0 - (_age - 5000) / 1000.0))  # Fade-out 1.0 сек
                        _btxt = _bubble_data["text"]
                        _max_w = 180
                        _max_lines = 10
                        _line_h = self.font_small.get_height() + 2
                        _words = _btxt.split(" ")
                        _lines = []
                        _cur = ""
                        for _w in _words:
                            _test = (_cur + " " + _w).strip()
                            if self.font_small.size(_test)[0] <= _max_w:
                                _cur = _test
                            else:
                                if _cur: _lines.append(_cur)
                                _cur = _w
                        if _cur: _lines.append(_cur)
                        if len(_lines) > _max_lines:
                            _combined = " ".join(_lines[:_max_lines])
                            _last_sent = max(_combined.rfind("."), _combined.rfind("!"), _combined.rfind("?"), _combined.rfind("—"))
                            if _last_sent > len(_combined) // 2:
                                _words2 = _combined[: _last_sent + 1].split(" ")
                                _lines = []
                                _cur2 = ""
                                for _w2 in _words2:
                                    _test2 = (_cur2 + " " + _w2).strip()
                                    if self.font_small.size(_test2)[0] <= _max_w:
                                        _cur2 = _test2
                                    else:
                                        if _cur2: _lines.append(_cur2)
                                        _cur2 = _w2
                                if _cur2: _lines.append(_cur2)
                            else:
                                _lines = _lines[:_max_lines]
                                _lines[-1] = _lines[-1].rstrip(" ,—") + "…"
                        _bub_h = len(_lines) * _line_h + 10
                        _bub_w = max(self.font_small.size(line)[0] for line in _lines) + 14 if _lines else 40
                        _bub_x = coords["sx"] - _bub_w // 2
                        _bub_y = coords["sy"] - coords["radius"] - 22 - _bub_h
                        # S162: Epistemic Honesty - проброс параметров восприятия
                        _clarity = _bubble_data.get("auditory_clarity", 1.0)
                        _delivery = _bubble_data.get("delivery_type", "NORMAL")
                        # Прозрачность зависит от того, насколько чётко игрок услышал текст
                        _final_alpha = int(_alpha * max(0.2, _clarity))
                        _pending_bubbles.append({
                            "x": _bub_x, "y": _bub_y, "w": _bub_w, "h": _bub_h, 
                            "lines": _lines, "alpha": _final_alpha, 
                            "delivery_type": _delivery, "is_player": False,
                            "auditory_clarity": _clarity,
                            "is_slam": _bubble_data.get("attention_weight", 0.0) >= 1.0
                        })

        # Player Bubble
        if player_speech:
            _age = pygame.time.get_ticks() - player_speech["tick"]
            if _age < 4000:
                if _age < 200:
                    _alpha = int(255 * (_age / 200.0))  # Fade-in 0.2 сек
                elif _age < 3000:
                    _alpha = 255  # Удержание
                else:
                    _alpha = int(255 * (1.0 - (_age - 3000) / 1000.0))  # Fade-out 1.0 сек
                _btxt = player_speech["text"]
                _max_w = 180
                _max_lines = 2
                _line_h = self.font_small.get_height() + 2
                _words = _btxt.split(" ")
                _lines = []
                _cur = ""
                for _w in _words:
                    _test = (_cur + " " + _w).strip()
                    if self.font_small.size(_test)[0] <= _max_w:
                        _cur = _test
                    else:
                        if _cur: _lines.append(_cur)
                        _cur = _w
                if _cur: _lines.append(_cur)
                if len(_lines) > _max_lines:
                    _combined = " ".join(_lines[:_max_lines])
                    _last_sent = max(_combined.rfind("."), _combined.rfind("!"), _combined.rfind("?"), _combined.rfind("—"))
                    if _last_sent > len(_combined) // 2:
                        _words2 = _combined[: _last_sent + 1].split(" ")
                        _lines = []
                        _cur2 = ""
                        for _w2 in _words2:
                            _test2 = (_cur2 + " " + _w2).strip()
                            if self.font_small.size(_test2)[0] <= _max_w:
                                _cur2 = _test2
                            else:
                                if _cur2: _lines.append(_cur2)
                                _cur2 = _w2
                        if _cur2: _lines.append(_cur2)
                    else:
                        _lines = _lines[:_max_lines]
                        _lines[-1] = _lines[-1].rstrip(" ,—") + "…"
                _bub_h = len(_lines) * _line_h + 10
                _bub_w = max(self.font_small.size(line)[0] for line in _lines) + 14 if _lines else 40
                _bub_x = player_coords["sx"] - _bub_w // 2
                _bub_y = player_coords["sy"] - 28 - _bub_h
                # Игрок всегда слышит себя чётко
                _pending_bubbles.append({"x": _bub_x, "y": _bub_y, "w": _bub_w, "h": _bub_h, "lines": _lines, "alpha": _alpha, "delivery_type": "NORMAL", "is_player": True})

        if _pending_bubbles:
            self._resolve_and_draw_bubbles(screen, _pending_bubbles)

    def _resolve_and_draw_bubbles(self, screen: pygame.Surface, bubbles: list) -> None:
        """Алгоритм Relaxation для расталкивания речевых облачков (AABB collision)."""
        for _ in range(5):
            for i in range(len(bubbles)):
                for j in range(i + 1, len(bubbles)):
                    b1 = bubbles[i]
                    b2 = bubbles[j]
                    overlap_x = min(b1["x"] + b1["w"], b2["x"] + b2["w"]) - max(b1["x"], b2["x"])
                    overlap_y = min(b1["y"] + b1["h"], b2["y"] + b2["h"]) - max(b1["y"], b2["y"])

                    if overlap_x > 0 and overlap_y > 0:
                        if overlap_x < overlap_y:
                            push = overlap_x / 2 + 1
                            if b1["x"] < b2["x"]:
                                b1["x"] -= push
                                b2["x"] += push
                            else:
                                b1["x"] += push
                                b2["x"] -= push
                        else:
                            push = overlap_y / 2 + 1
                            if b1["y"] < b2["y"]:
                                b1["y"] -= push
                                b2["y"] += push
                            else:
                                b1["y"] += push
                                b2["y"] -= push

        _line_h = self.font_small.get_height() + 2
        for bub in bubbles:
            _bub_x = int(bub["x"])
            _bub_y = int(bub["y"])
            _bub_w = int(bub["w"])
            _bub_h = int(bub["h"])
            _alpha = int(bub["alpha"])
            _is_player = bub.get("is_player", False)
            _delivery = bub.get("delivery_type", "NORMAL")
            _clarity = bub.get("auditory_clarity", 1.0)
            
            _is_slam = bub.get("is_slam", False)
            
            _bg = pygame.Surface((_bub_w, _bub_h), pygame.SRCALPHA)
            if _is_player:
                _bg.fill((15, 30, 50, min(_alpha, 210)))
                _border_color = (80, 160, 240, _alpha)
                _text_color = (200, 230, 255)
            else:
                _bg.fill((25, 25, 45, min(_alpha, 210)))
                _border_color = (160, 170, 220, _alpha)
                if _delivery == "SHOUT":
                    _text_color = (255, 80, 80)
                    _border_color = (255, 50, 50, _alpha)
                elif _delivery == "WHISPER":
                    _text_color = (160, 160, 160)
                else:
                    _text_color = (255, 255, 255)

            # S170: SLAM-события масштабируются на 1.2x и получают жёсткую рамку
            if _is_slam:
                _border_color = (255, 255, 255, _alpha)
                pygame.draw.rect(_bg, _border_color, _bg.get_rect(), 3, border_radius=4)
            else:
                pygame.draw.rect(_bg, _border_color, _bg.get_rect(), 1, border_radius=4)
                
            screen.blit(_bg, (_bub_x, _bub_y))
            for _li, _ll in enumerate(bub["lines"]):
                # S169: Epistemic Honesty - рваный текст при плохой слышимости
                if not _is_player and _clarity < 0.5:
                    _ragged_ll = "".join([c if random.random() < (_clarity + 0.2) else "." for c in _ll])
                else:
                    _ragged_ll = _ll
                    
                _ls = self.font_small.render(_ragged_ll, True, _text_color)
                _la = _ls.copy()
                _la.set_alpha(_alpha)
                screen.blit(_la, (_bub_x + 7, _bub_y + 5 + _li * _line_h))