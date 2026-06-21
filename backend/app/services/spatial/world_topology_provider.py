# -*- coding: utf-8 -*-
"""
path: backend/app/services/spatial/world_topology_provider.py
Назначение: Единый шлюз мира для ETKE-IK v1. Трансляция дискретной геометрии в непрерывное поле возможностей (Affordance).
Зависимости: SpatialService, motion_core
Основные сущности: WorldTopologyProvider
"""
from __future__ import annotations

from typing import Tuple, Dict, Any, Optional
from app.domain.motion_core import AffordanceVector
from app.services.spatial.spatial_service import SpatialService

class WorldTopologyProvider:
    """Единый интерфейс запроса свойств физического мира.
    
    В отличие от SpatialService (который отдает граф и узлы),
    этот провайдер отдает непрерывные физические свойства (Affordance)
    для любой координаты (x, y).
    """
    
    def __init__(self, spatial_service: Optional[SpatialService] = None):
        self._svc = spatial_service
        # S91: Кэш динамических деформаций. Ключ: (region, zone_id).
        self._active_deformations: Dict[Tuple[str, str], Dict[str, float]] = {}
        
    def query_affordance_field(self, region: str, pos: Tuple[float, float]) -> AffordanceVector:
        """Запрашивает AffordanceVector для точки (x, y) в регионе (location_id).
        
        S91: Базовая геометрия мержится с активными деформациями (DynamicAffordanceField).
        """
        if not self._svc:
            return AffordanceVector(
                can_stand=1.0,
                can_pass=1.0,
                surface_grip=0.8,
                light_level=0.5,
                exposure=0.5
            )
            
        # S91: Получаем zone_id для кэширования деформаций
        zone_id = self._svc.get_zone_id(pos[0], pos[1])
        
        if not zone_id:
            # Точка вне полигонов комнат — стена/препятствие
            return AffordanceVector(
                can_stand=0.0,
                can_pass=0.0,
                surface_grip=0.0,
                drag_coefficient=1.0,
                light_level=0.0,
                exposure=0.0
            )
            
        # Базовые параметры внутри комнаты
        base_affordance = {
            "can_stand": 1.0,
            "can_pass": 1.0,
            "surface_grip": 0.8,
            "drag_coefficient": 0.0,
            "light_level": 0.5,
            "exposure": 0.5
        }
        
        # S91: Применяем деформации, если они есть для этой зоны
        deformations = self._active_deformations.get((region, zone_id))
        if deformations:
            base_affordance.update(deformations)
            
        return AffordanceVector(**base_affordance)

    def query_cluster_trace(self, region: str) -> Dict[str, Any]:
        """Запрашивает стигмергический след (SocialTraceField) для региона.
        
        TODO: В будущем будет возвращать movement_density, safety_confidence и т.д.
        """
        return {}

    def apply_deformation(self, region: str, zone_id: str, payload: Dict[str, float]) -> None:
        """S91: Применяет динамическую деформацию к полю возможностей зоны.
        
        Изменяет свойства среды (напр. разрушение укрытия, разлитие масла).
        """
        key = (region, zone_id)
        if key not in self._active_deformations:
            self._active_deformations[key] = {}
        self._active_deformations[key].update(payload)