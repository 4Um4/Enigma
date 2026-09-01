"""
Файл: backend/app/services/spatial/spatial_target_resolver.py

Мы создадим SpatialTargetResolver, который будет жить в services/spatial/ и использовать существующий SpatialService для разрешения SpatialTargetIntent в ResolvedSpatialTarget.
Поскольку в старой системе Anchor ID часто совпадает с Node ID (или ролью узла), наш первый адаптер будет использовать существующие методы SpatialService (get_node и resolve_node), но возвращать уже новый,
чистый DTO ResolvedSpatialTarget. Это позволит нам начать использовать новую онтологию без поломки старого движка.
"""
from typing import Dict, Optional, Tuple

import logging

logger = logging.getLogger(__name__)
from app.domain.spatial_target import (
    SpatialTargetIntent, ResolvedSpatialTarget, TargetResolutionStatus, SpatialTargetType, SpatialResolutionMode
)
from app.services.spatial.spatial_service import SpatialService

def _extract_xy(entry: Optional[Dict]) -> Optional[Tuple[float, float]]:
    """Строгое и безопасное извлечение координат из разных форматов позиций."""
    if not entry: return None
    pos = entry.get("local_position", entry.get("position"))
    if isinstance(pos, dict):
        x, y = pos.get("x"), pos.get("y")
        if x is None or y is None: return None
        try: return float(x), float(y)
        except (TypeError, ValueError) as e:
            logger.debug(f"Coord parse error: {e}")
            return None
    if isinstance(pos, (list, tuple)) and len(pos) == 2:
        try: return float(pos[0]), float(pos[1])
        except (TypeError, ValueError) as e:
            logger.debug(f"Coord parse error: {e}")
            return None
    return None

class SpatialTargetResolver:
    """
    ADR-O-330: Адаптер, преобразующий SpatialTargetIntent в ResolvedSpatialTarget.
    Реализует SA-2 (Spatial Resolution Authority).
    """
    def __init__(self, spatial_service: SpatialService):
        self._spatial_service = spatial_service

    def resolve(
        self, 
        intent: SpatialTargetIntent, 
        npc_positions: Optional[Dict[str, Dict]] = None,
        actor_id: Optional[str] = None,
        location_id: Optional[str] = None
    ) -> ResolvedSpatialTarget:
        """
        Разрешает намерение в физическую координату и точку входа в граф.
        """
        if intent.target_type == SpatialTargetType.ANCHOR:
            return self._resolve_anchor_target(intent, location_id)
            
        if intent.target_type == SpatialTargetType.REGION and intent.reason == "flee":
            return self._resolve_flee_target(intent, npc_positions, actor_id, location_id)
        
        return ResolvedSpatialTarget(
            intent=intent,
            resolution_status=TargetResolutionStatus.UNAVAILABLE,
            mode=None,
            resolution_reason=f"Unsupported target_type: {intent.target_type}"
        )

    def _resolve_anchor_target(self, intent: SpatialTargetIntent, location_id: Optional[str] = None) -> ResolvedSpatialTarget:
        target_id = intent.target_id
        if not target_id:
            return ResolvedSpatialTarget(
                intent=intent, resolution_status=TargetResolutionStatus.UNAVAILABLE,
                mode=None, resolution_reason="Anchor target_id is missing"
            )
            
        # 1. Пытаемся найти узел по точному ID (если Anchor привязан к node_id)
        node = self._spatial_service.get_node(target_id)
        
        # 2. Если нет, пытаемся найти по семантической роли (например, "bar")
        if not node:
            from app.models.spatial_contracts import NodeRole
            try:
                # S143 FIX: Конвертируем строку в Enum, так как resolve_node ожидает NodeRole
                role_enum = NodeRole(target_id)
                node = self._spatial_service.resolve_node(role=role_enum, origin_zone=location_id)
            except ValueError as e:
                logger.debug(f"NodeRole not found for target_id={target_id}: {e}")  # Строка не соответствует ни одной роли NodeRole
            
        if not node:
            return ResolvedSpatialTarget(
                intent=intent, resolution_status=TargetResolutionStatus.UNAVAILABLE,
                mode=None, resolution_reason=f"Anchor {target_id} not found in graph"
            )
            
        return ResolvedSpatialTarget(
            intent=intent,
            resolution_status=TargetResolutionStatus.RESOLVED,
            mode=SpatialResolutionMode.NAV_NODE,
            position=(node.x, node.y),
            anchor_node_id=node.node_id,
            resolution_reason="Anchor resolved successfully"
        )

    def _resolve_flee_target(
        self,
        intent: SpatialTargetIntent,
        npc_positions: Optional[Dict[str, Dict]],
        actor_id: Optional[str],
        location_id: Optional[str]
    ) -> ResolvedSpatialTarget:
        threat_id = intent.context_ref
        if not threat_id or not npc_positions or threat_id not in npc_positions:
            return ResolvedSpatialTarget(
                intent=intent, resolution_status=TargetResolutionStatus.UNAVAILABLE,
                mode=None, resolution_reason=f"FLEE threat {threat_id} not found"
            )
            
        threat_xy = _extract_xy(npc_positions.get(threat_id))
        actor_xy = _extract_xy(npc_positions.get(actor_id)) if actor_id else None  # noqa: ENIGMA001
        
        if not threat_xy:
            return ResolvedSpatialTarget(
                intent=intent, resolution_status=TargetResolutionStatus.UNAVAILABLE,
                mode=None, resolution_reason=f"FLEE threat {threat_id} has no position"
            )
            
        # LEGACY BRIDGE: get_furthest() пока остаётся стратегией выбора макро-цели.
        furthest_ref = self._spatial_service.get_furthest(
            zone_id=location_id,
            origin_xy=threat_xy,
            exclude_node_ids=set()
        )
        
        if furthest_ref:
            # Если нашли дальний узел — возвращаем макро-цель
            return ResolvedSpatialTarget(
                intent=intent,
                resolution_status=TargetResolutionStatus.RESOLVED,
                mode=SpatialResolutionMode.NAV_NODE,
                position=(furthest_ref.x, furthest_ref.y),
                anchor_node_id=furthest_ref.node_id,
                resolution_reason="FLEE resolved to furthest node"
            )
            
        # Fallback: если графа нет или узел не найден — вычисляем микро-вектор (Micro-FLEE)
        if actor_xy:
            _dx = actor_xy[0] - threat_xy[0]
            _dy = actor_xy[1] - threat_xy[1]
            _dist = (_dx**2 + _dy**2) ** 0.5
            if _dist > 0.01:
                # Вектор от угрозы к актору: нормируем и продолжаем на 3 метра
                _ndx = _dx / _dist
                _ndy = _dy / _dist
                micro_pos = (_ndx * 3.0 + actor_xy[0], _ndy * 3.0 + actor_xy[1])
                return ResolvedSpatialTarget(
                    intent=intent,
                    resolution_status=TargetResolutionStatus.RESOLVED,
                    mode=SpatialResolutionMode.LOCAL_POSITION,
                    position=micro_pos,
                    resolution_reason="FLEE resolved to micro-position"
                )
                
        return ResolvedSpatialTarget(
            intent=intent, resolution_status=TargetResolutionStatus.UNAVAILABLE,
            mode=None, resolution_reason="FLEE failed: no macro node and no actor pos for micro"
        )