"""
path: /frontend/portrait_renderer.py
Назначение: Рендерер портретов (JRPG/VN style) во время диалога.
Отвечает только за отрисовку ExpressionResult с плавным Fade-in/Fade-out.
Зависимости: pygame, sprite_registry, expression_resolver
Основные сущности: PortraitRenderer
"""
import logging
from typing import Any, List, Optional

import pygame
from sprite_registry import sprite_registry
from expression_resolver import ExpressionResult

logger = logging.getLogger(__name__)

class PortraitRenderer:
    """Рисует портреты NPC и Игрока во время активного диалога. Не знает о конфигах."""

    def __init__(self):
        self._fade_state = {}  # target_id: {"alpha": float, "target": float, "last_update": int}

    def draw(
        self,
        screen: pygame.Surface,
        entities: List[Any],
        npc_speech_bubbles: dict,
        player_speech: Optional[dict],
        casting_repo: Any
    ):
        """Отрисовка портретов. Активируется только при наличии реплик."""
        _now = pygame.time.get_ticks()
        screen_w, screen_h = screen.get_size()
        _size = 192  # Размер портрета
        
        # 1. Игрок (справа)
        _player_entity = next((e for e in entities if e.entity_id == "player"), None)
        _player_result = casting_repo.resolve_entity(_player_entity) if _player_entity else None
        
        self._update_fade("player", player_speech is not None, _now)
        self._draw_portrait(screen, "player", _player_result.asset if _player_result else None, screen_w - _size - 20, screen_h - _size - 40)

        # 2. NPC (слева)
        _active_npc_id = None
        if npc_speech_bubbles:
            _sorted = sorted(npc_speech_bubbles.items(), key=lambda item: item[1].get("tick", 0), reverse=True)
            if _sorted:
                _active_npc_id = _sorted[0][0]
        
        if _active_npc_id:
            _entity = next((e for e in entities if e.entity_id == _active_npc_id), None)
            _result = casting_repo.resolve_entity(_entity) if _entity else None
            
            self._update_fade(_active_npc_id, True, _now)
            self._draw_portrait(screen, _active_npc_id, _result.asset if _result else None, 20, screen_h - _size - 40)
        else:
            for npc_id in list(self._fade_state.keys()):
                if npc_id != "player":
                    self._update_fade(npc_id, False, _now)
                    _asset = casting_repo.get_fallback_asset(npc_id)
                    self._draw_portrait(screen, npc_id, _asset, 20, screen_h - _size - 40)

    def _update_fade(self, target_id: str, is_active: bool, now: int):
        """Плавный Fade-in (0.2 сек) и Fade-out (1.0 сек)."""
        state = self._fade_state.get(target_id, {"alpha": 0.0, "target": 0.0, "last_update": now})
        dt = max(0.001, (now - state["last_update"]) / 1000.0)
        state["last_update"] = now
        state["target"] = 255.0 if is_active else 0.0
        
        speed = 1275.0 if state["target"] > state["alpha"] else 255.0
        
        if state["alpha"] < state["target"]:
            state["alpha"] = min(state["target"], state["alpha"] + speed * dt)
        else:
            state["alpha"] = max(state["target"], state["alpha"] - speed * dt)
            
        self._fade_state[target_id] = state

    def _draw_portrait(self, screen: pygame.Surface, target_id: str, sprite_info: Optional[list], x: int, y: int):
        """Отрисовка спрайта с учётом альфа-канала."""
        state = self._fade_state.get(target_id)
        # S176 FIX: Если путь пустой или данных нет — не рисуем квадрат вообще
        if not state or state["alpha"] <= 0.1 or not sprite_info or len(sprite_info) < 3 or not sprite_info[0]:
            return
            
        try:
            # S176: Поддержка точного пиксельного кропа [sheet, x, y, w, h, threshold, outline]
            if len(sprite_info) >= 5:
                _t = int(sprite_info[5]) if len(sprite_info) > 5 else 220
                _o = int(sprite_info[6]) if len(sprite_info) > 6 else 1
                _surf = sprite_registry.get_rect(
                    sprite_info[0], 
                    int(sprite_info[1]), 
                    int(sprite_info[2]), 
                    int(sprite_info[3]), 
                    int(sprite_info[4]),
                    _t,
                    _o
                )
            else:
                # Легаси: сеточный формат [sheet, col, row]
                _surf = sprite_registry.get(sprite_info[0], sprite_info[1], sprite_info[2])
                
            if _surf:
                # S176 FIX: Сохраняем пропорции портрета, чтобы не сплющивать модель
                sw, sh = _surf.get_size()
                ratio = min(192 / sw, 192 / sh)
                nw, nh = int(sw * ratio), int(sh * ratio)
                _scaled = pygame.transform.smoothscale(_surf, (nw, nh))
                _scaled.set_alpha(int(state["alpha"]))
                # Выравниваем по правому краю для игрока и левому для NPC
                blit_x = x if x > screen.get_width() / 2 else x + (192 - nw)
                screen.blit(_scaled, (blit_x, y + (192 - nh) // 2))
        except Exception:
            pass