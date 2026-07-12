# -*- coding: utf-8 -*-
"""
path: backend/app/services/spatial/world_topology_provider.py
Назначение: Единый шлюз мира для ETKE-IK v1. Трансляция дискретной геометрии в непрерывное поле возможностей (Affordance).
Зависимости: SpatialService, motion_core
Основные сущности: WorldTopologyProvider
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from app.domain.motion_core import AffordanceVector, DeformationRecord, TracePayload
from app.services.spatial.spatial_service import SpatialService


class DynamicAffordanceField:
    """S91: State-object для хранения динамических деформаций среды (стигмергия).

    Разделён на два независимых слоя:
    1. Hard Override Layer: Структурные деформации (Absolute Override).
    2. Soft Trace Layer: Поведенческие следы (накопление и decay).
    """

    def __init__(self):
        # Слой 1: Hard Overrides (region -> zone_id -> type -> DeformationRecord)
        self._hard_overrides: Dict[str, Dict[str, Dict[str, DeformationRecord]]] = {}
        # Слой 2: Soft Traces (region -> zone_id -> trace_type -> accumulated float)
        self._traces: Dict[str, Dict[str, Dict[str, float]]] = {}

    def apply_deformation(
        self, region: str, zone_id: str, record: DeformationRecord
    ) -> None:
        """Слой 1: Применяет структурную деформацию (перезаписывает старую того же типа)."""
        if region not in self._hard_overrides:
            self._hard_overrides[region] = {}
        if zone_id not in self._hard_overrides[region]:
            self._hard_overrides[region][zone_id] = {}
        self._hard_overrides[region][zone_id][record.deformation_type] = record

    def apply_trace(self, payload: TracePayload) -> None:
        """Слой 2: Soft-layer стигмергии (не влияет напрямую на AffordanceVector)."""
        if payload.region not in self._traces:
            self._traces[payload.region] = {}
        if payload.zone_id not in self._traces[payload.region]:
            self._traces[payload.region][payload.zone_id] = {}

        current = self._traces[payload.region][payload.zone_id].get(
            payload.trace_type, 0.0
        )
        self._traces[payload.region][payload.zone_id][payload.trace_type] = (
            current + payload.magnitude
        )

    def get_hard_overrides(
        self, region: str, zone_id: str
    ) -> Dict[str, DeformationRecord]:
        """Возвращает все активные структурные деформации для зоны."""
        return self._hard_overrides.get(region, {}).get(zone_id, {})

    def get_soft_traces(self, region: str, zone_id: str) -> Dict[str, float]:
        """Возвращает все активные поведенческие следы для зоны."""
        return self._traces.get(region, {}).get(zone_id, {})

    def purge_hard_overrides(self, current_tick: int) -> None:
        """S91: Очистка истекших структурных деформаций (Hard Overrides)."""
        empty_zones_h = []
        for region, zones in self._hard_overrides.items():
            for zone_id, types in zones.items():
                expired_types = [
                    t
                    for t, rec in types.items()
                    if rec.ttl > 0 and (current_tick - rec.created_tick) > rec.ttl
                ]
                for t in expired_types:
                    del types[t]
                if not types:
                    empty_zones_h.append((region, zone_id))
        for region, zone_id in empty_zones_h:
            del self._hard_overrides[region][zone_id]
        empty_regions_h = [r for r, zones in self._hard_overrides.items() if not zones]
        for r in empty_regions_h:
            del self._hard_overrides[r]

    def step_decay(self, decay_rate: float = 0.9) -> None:
        """
        S91: Temporal update step for soft traces.
        Must be called by TickOrchestrator, not externally.
        """
        empty_zones_s = []
        for region, zones in self._traces.items():
            for zone_id, types in zones.items():
                for t_type in list(types.keys()):
                    types[t_type] *= decay_rate
                    if types[t_type] < 0.01:
                        del types[t_type]
                if not types:
                    empty_zones_s.append((region, zone_id))
        for region, zone_id in empty_zones_s:
            del self._traces[region][zone_id]
        empty_regions_s = [r for r, zones in self._traces.items() if not zones]
        for r in empty_regions_s:
            del self._traces[r]


class WorldTopologyProvider:
    """Единый интерфейс запроса свойств физического мира (Фасад).

    S91: Чистый фасад. Мержит базовую геометрию (SpatialService) с
    динамическими деформациями (DynamicAffordanceField).
    TODO (Долг): Базовые параметры (surface_grip=0.8) вынести в ZoneAffordanceProfile.
    """

    def __init__(
        self,
        spatial_service: Optional[SpatialService] = None,
        dynamic_field: Optional[DynamicAffordanceField] = None,
    ):
        self._svc = spatial_service
        self._dynamic_field = dynamic_field or DynamicAffordanceField()

    def set_spatial_service(self, svc: SpatialService) -> None:
        """S91: Инъекция SpatialService для персистентного провайдера."""
        self._svc = svc

    def query_affordance_field(
        self, region: str, pos: Tuple[float, float]
    ) -> AffordanceVector:
        """Запрашивает AffordanceVector для точки (x, y) в регионе (location_id).

        S91: Базовая геометрия мержится с активными деформациями (DynamicAffordanceField).
        """
        if not self._svc:
            return AffordanceVector(
                can_stand=1.0,
                can_pass=1.0,
                surface_grip=0.8,
                light_level=0.5,
                exposure=0.5,
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
                exposure=0.0,
            )

        # TODO (Долг): Вынести в ZoneAffordanceProfile
        base_affordance = {
            "can_stand": 1.0,
            "can_pass": 1.0,
            "surface_grip": 0.8,
            "drag_coefficient": 0.0,
            "light_level": 0.5,
            "exposure": 0.5,
        }

        # S91: Применяем Hard Overrides (Absolute Override)
        hard_overrides = self._dynamic_field.get_hard_overrides(region, zone_id)
        for def_type, record in hard_overrides.items():
            if def_type in base_affordance:
                base_affordance[def_type] = record.magnitude

        # S91: Применяем Soft Traces (Accumulation/Decay)
        traces = self._dynamic_field.get_soft_traces(region, zone_id)
        if "movement_density" in traces:
            base_affordance["drag_coefficient"] += traces["movement_density"] * 0.1

        return AffordanceVector(**base_affordance)

    def query_cluster_trace(self, region: str) -> Dict[str, Any]:
        """Запрашивает стигмергический след (SocialTraceField) для региона.

        TODO: В будущем будет возвращать movement_density, safety_confidence и т.д.
        """
        return {}

    def apply_deformation(
        self, region: str, zone_id: str, record: DeformationRecord
    ) -> None:
        """S91: Делегирует применение деформации в DynamicAffordanceField."""
        self._dynamic_field.apply_deformation(region, zone_id, record)
