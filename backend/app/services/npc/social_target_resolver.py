# backend/app/services/npc/social_target_resolver.py
#
# S96: Социальный таргетинг. Выбирает цель для NPC-NPC взаимодействия.
# MVP: Возвращает ближайшего NPC. В будущем: учитывает отношения, долг, роль и т.д.
from __future__ import annotations
import logging
from typing import Any, List, Optional

logger = logging.getLogger(__name__)

class SocialTargetResolver:
    """Выбирает цель для социального взаимодействия (TALK, HELP и т.д.)."""
    
    @staticmethod
    def resolve(state: Any, spatial_query: Optional[Any], all_npc_ids: List[str]) -> Optional[str]:
        if not spatial_query:
            return None
        
        # MVP: Возвращаем ближайшего NPC.
        _candidates = [nid for nid in all_npc_ids if nid != state.npc_id]
        if not _candidates:
            return None
            
        _target = spatial_query.get_nearest_npc(state.npc_id, _candidates)
        if _target:
            logger.debug(f"[SOCIAL_TARGET] npc={state.npc_id} -> target={_target} (nearest)")
        return _target