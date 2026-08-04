"""
path: backend/app/services/spatial/spatial_factory.py
Назначение: Единая фабрика SpatialService с кэшированием на уровне кампании.
B3-FIX: убрано 3 точки входа (npc_orchestration, idle_tick, _resolve_spatial_service).
S113: Введён кэш _cache для предотвращения пересборки графа каждый тик.
"""

import hashlib
import logging
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from app.services.spatial.spatial_service import SpatialService

logger = logging.getLogger(__name__)


class SpatialFactory:
    """Единственная точка входа для сборки SpatialService."""

    # S-03.1: Кэшируем SpatialService вместе с SHA-256 fingerprint
    _cache: Dict[Tuple[str, str], Tuple[SpatialService, str]] = {}

    @staticmethod
    def _get_map_fingerprint(campaign_id: str, location_id: str) -> str:
        """Вычисляет SHA-256 от файла карты для надёжной инвалидации кэша."""
        project_root = Path(__file__).resolve().parents[4]
        campaign_dir = project_root / "frontend" / "map_editor" / "campaigns" / campaign_id
        loc_file = campaign_dir / "locations" / f"{location_id}.json"
        if not loc_file.exists():
            loc_file = campaign_dir / f"{location_id}.json"
        if not loc_file.exists():
            return ""
        return hashlib.sha256(loc_file.read_bytes()).hexdigest()

    @staticmethod
    def build_for_campaign(
        campaign_id: str,
        location_id: str,
        scene_state: Dict[str, Any],
        editor_data_override: Optional[Dict[str, Any]] = None,
    ) -> Optional[SpatialService]:
        """Build SpatialService for campaign/location. Single authority.
        Возвращает кэшированный инстанс, если fingerprint карты совпадает.
        """
        # ADR-O-330: Если передан editor_data_override (Spatial Observatory), не используем кэш.
        if editor_data_override is not None:
            return SpatialService.build_for_location(
                campaign_id=campaign_id,
                location_id=location_id,
                scene_state=scene_state,
                editor_data_override=editor_data_override,
            )

        _cache_key = (campaign_id, location_id)
        current_fp = SpatialFactory._get_map_fingerprint(campaign_id, location_id)

        if _cache_key in SpatialFactory._cache:
            cached_svc, cached_fp = SpatialFactory._cache[_cache_key]
            if cached_fp == current_fp and current_fp != "":
                # BUG-SPATIAL-029 FIX: Обновляем overlay перед возвратом кэшированного сервиса
                from app.services.spatial.spatial_overlay import build_overlay_from_scene
                cached_svc.set_overlay(build_overlay_from_scene(scene_state))
                return cached_svc
            # S-03.1: Карта изменена или отсутствует — инвалидируем кэш
            logger.info(f"[SPATIAL_FACTORY] Map changed for {_cache_key}. Rebuilding graph.")
            del SpatialFactory._cache[_cache_key]

        try:
            _svc = SpatialService.build_for_location(
                campaign_id=campaign_id,
                location_id=location_id,
                scene_state=scene_state,
            )
            if _svc and current_fp != "":
                SpatialFactory._cache[_cache_key] = (_svc, current_fp)
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
