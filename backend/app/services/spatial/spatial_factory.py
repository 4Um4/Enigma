"""
path: backend/app/services/spatial/spatial_factory.py
Назначение: Единая фабрика SpatialService с кэшированием на уровне кампании.
B3-FIX: убрано 3 точки входа (npc_orchestration, idle_tick, _resolve_spatial_service).
S113: Введён кэш _cache для предотвращения пересборки графа каждый тик.
"""

import logging
from typing import Any, Dict, Optional, Tuple

from app.services.spatial.spatial_service import SpatialService

logger = logging.getLogger(__name__)


class SpatialFactory:
    """Единственная точка входа для сборки SpatialService."""

    _cache: Dict[Tuple[str, str], SpatialService] = {}

    @staticmethod
    def build_for_campaign(
        campaign_id: str,
        location_id: str,
        scene_state: Dict[str, Any],
    ) -> Optional[SpatialService]:
        """Build SpatialService for campaign/location. Single authority.
        Возвращает кэшированный инстанс, если кампания и локация совпадают.
        """
        _cache_key = (campaign_id, location_id)

        # Возвращаем кэш, если он есть
        if _cache_key in SpatialFactory._cache:
            return SpatialFactory._cache[_cache_key]

        try:
            _svc = SpatialService.build_for_location(
                campaign_id=campaign_id,
                location_id=location_id,
                scene_state=scene_state,
            )
            if _svc:
                SpatialFactory._cache[_cache_key] = _svc
            return _svc
        except Exception as e:
            logger.error(
                f"[SPATIAL_FACTORY] build failed for {campaign_id}/{location_id}: {e}",
                exc_info=True,
            )
            return None

    @staticmethod
    def invalidate_cache(campaign_id: str) -> None:
        """Сброс кэша при смене кампании или выгрузке."""
        _keys_to_remove = [k for k in SpatialFactory._cache if k[0] == campaign_id]
        for k in _keys_to_remove:
            del SpatialFactory._cache[k]
