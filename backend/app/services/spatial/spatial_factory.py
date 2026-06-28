"""
path: backend/app/services/spatial/spatial_factory.py
Назначение: Единая фабрика SpatialService.
B3-FIX: убрано 3 точки входа (npc_orchestration, idle_tick, _resolve_spatial_service).
"""
import logging
from typing import Optional
from app.services.spatial.spatial_service import SpatialService

logger = logging.getLogger(__name__)

class SpatialFactory:
    """Единственная точка входа для сборки SpatialService."""

    @staticmethod
    def build_for_campaign(
        campaign_id: str,
        location_id: str,
        scene_state: dict,
    ) -> Optional[SpatialService]:
        """Build SpatialService for campaign/location. Single authority."""
        try:
            return SpatialService.build_for_location(
                campaign_id=campaign_id,
                location_id=location_id,
                scene_state=scene_state,
            )
        except Exception as e:
            logger.error(
                f"[SPATIAL_FACTORY] build failed for {campaign_id}/{location_id}: {e}",
                exc_info=True
            )
            return None