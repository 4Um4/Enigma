"""
Файл: backend/app/services/state/world_diff_applicator.py
Назначение: Применяет WorldStateDiff к новой кампании. Единственный шлюз персистентности.
Зависимости: typing, app.models.world_state_diff, app.services.state.world_continuity_mode
"""

from typing import Dict, Any
from app.models.world_state_diff import WorldStateDiff
from app.models.world_continuity import WorldContinuityMode

# Fate outcodes, при которых NPC физически покидает новую кампанию
_ABSENT_FATES = {"escaped", "liberated", "imprisoned", "missing"}
# Fate outcodes, при которых NPC остаётся в мире, но мёртв
_DEAD_FATES = {"killed_by_guild", "death", "suicide"}

class WorldStateApplicator:
    """Применяет WorldStateDiff к кэшу NPC новой кампании.
    
    Единственный легитимный способ перенести последствия
    из одной кампании в другую.
    """
    
    def __init__(self, mode: WorldContinuityMode = WorldContinuityMode.ISOLATED) -> None:
        self._mode = mode

    def apply(self, diff: WorldStateDiff, npc_cache: Dict[str, Any]) -> None:
        """Мутирует npc_cache в соответствии с diff (если режим CONTINUOUS)."""
        if self._mode == WorldContinuityMode.ISOLATED:
            return
            
        for npc_id, fate in diff.npc_fates.items():
            if npc_id not in npc_cache:
                continue
                
            if fate in _ABSENT_FATES:
                # Сбежавшие/пленённые NPC исчезают из новой кампании
                del npc_cache[npc_id]
            elif fate in _DEAD_FATES:
                # BUG-FB-007 FIX: life_status пишется в body_state, а не в корень (ADR-127 Death Lock).
                # Иначе мёртвые NPC оживают в новой кампании, так как tick_orchestrator читает body_state.
                _bs = npc_cache[npc_id].setdefault("body_state", {})
                _bs["life_status"] = "DEAD"
                _bs["current_hp"] = 0
                _bs["consciousness"] = 0.0