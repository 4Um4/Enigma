from __future__ import annotations

# backend/app/services/npc/social_target_resolver.py
#
# S96: Социальный таргетинг. Выбирает цель для NPC-NPC взаимодействия.
# MVP: Возвращает ближайшего NPC. В будущем: учитывает отношения, долг, роль и т.д.
import logging
from typing import Any, List, Optional

from app.core.constants import (
    SOCIAL_TRUST_NEUTRAL,
    SOCIAL_TRUST_HOSTILE_THRESHOLD,
    SOCIAL_TRUST_HIGH_THRESHOLD,
)

logger = logging.getLogger(__name__)


class SocialTargetResolver:
    """Выбирает цель для социального взаимодействия (TALK, HELP и т.д.)."""

    @staticmethod
    def resolve(
        state: Any, spatial_query: Optional[Any], all_npc_ids: List[str],
        relationship_store: Optional[Any] = None, campaign_id: str = ""
    ) -> Optional[str]:
        if not spatial_query:
            return None

        _candidates = [nid for nid in all_npc_ids if nid != state.npc_id]
        if not _candidates:
            return None

        _rel_store = relationship_store
        _c_id = campaign_id
        
        # S135: Загружаем все отношения этого NPC одним запросом из SSOT
        _all_rels = {}
        if _rel_store is not None:
            _all_rels = _rel_store.get(_c_id, state.npc_id)

        _filtered_candidates = []
        for nid in _candidates:
            _trust = SOCIAL_TRUST_NEUTRAL  # Vacuum semantics
            
            if _rel_store is not None:
                _target_key = f"{state.npc_id}→{nid}"
                _target_rel = _all_rels.get(_target_key, {})
                _trust = _target_rel.get("trust", SOCIAL_TRUST_NEUTRAL)
            else:
                # Legacy fallback (только если SSOT недоступен)
                _trust = getattr(state, "relationship_cache", {}).get(nid, {}).get("trust", SOCIAL_TRUST_NEUTRAL)
            
            # Отсекаем только явных врагов
            if _trust < SOCIAL_TRUST_HOSTILE_THRESHOLD:
                logger.debug(f"[SOCIAL_TARGET] {state.npc_id} skips {nid} (trust={_trust:.1f} < {SOCIAL_TRUST_HOSTILE_THRESHOLD})")
                continue
            _filtered_candidates.append((nid, _trust))
            
        if not _filtered_candidates:
            # Все отношения негативные — одиночество
            return None

        # Предпочитаем цели с высоким доверием
        _high_trust = [c for c in _filtered_candidates if c[1] > SOCIAL_TRUST_HIGH_THRESHOLD]
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
