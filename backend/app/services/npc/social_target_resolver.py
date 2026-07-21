from __future__ import annotations

# backend/app/services/npc/social_target_resolver.py
#
# S96: Социальный таргетинг. Выбирает цель для NPC-NPC взаимодействия.
# MVP: Возвращает ближайшего NPC. В будущем: учитывает отношения, долг, роль и т.д.
import logging
from typing import Any, List, Optional

logger = logging.getLogger(__name__)


class SocialTargetResolver:
    """Выбирает цель для социального взаимодействия (TALK, HELP и т.д.)."""

    @staticmethod
    def resolve(
        state: Any, spatial_query: Optional[Any], all_npc_ids: List[str]
    ) -> Optional[str]:
        if not spatial_query:
            return None

        _candidates = [nid for nid in all_npc_ids if nid != state.npc_id]
        if not _candidates:
            return None

        # P2-06: Фильтр по отношениям. NPC не общается с теми, кому не доверяет.
        _rel_cache = getattr(state, "relationship_cache", {})
        _filtered_candidates = []
        for nid in _candidates:
            _trust = _rel_cache.get(nid, {}).get("trust", 0.0)
            if _trust < -20:
                logger.debug(f"[SOCIAL_TARGET] {state.npc_id} skips {nid} (trust={_trust:.1f} < -20)")
                continue
            _filtered_candidates.append((nid, _trust))
            
        if not _filtered_candidates:
            # Все отношения негативные — одиночество
            return None

        # Предпочитаем цели с trust > 30
        _high_trust = [c for c in _filtered_candidates if c[1] > 30]
        _search_pool = _high_trust if _high_trust else _filtered_candidates

        _best_target = None
        _min_dist = float("inf")
        _SPEAK_RADIUS = 5.0  # NPC говорят только с теми, кто в 5 метрах

        for nid, _trust in _search_pool:
            _dist = spatial_query.distance(state.npc_id, nid)
            if _dist <= _SPEAK_RADIUS and _dist < _min_dist:
                # Проверка линии видимости (Line of Sight) — нет стен между ними
                if spatial_query.visibility(state.npc_id, nid):
                    _min_dist = _dist
                    _best_target = nid

        if _best_target:
            logger.warning(
                f"[SOCIAL_TARGET] npc={state.npc_id} -> target={_best_target} (dist={_min_dist:.1f}, LoS=True)"
            )
        return _best_target
