# path: backend/app/services/spatial/spatial_observatory_service.py
"""
Этот сервис будет жить на бэкенде и собирать SpatialObservatoryDTO. Он принимает сырой JSON карты и список NPC, строит эфемерный SpatialService, прогоняет через него всех NPC и возвращает полную картину для редактора.
Этот сервис — ядро Observatory. Он берет черновик карты, прогоняет его через канонический SpatialFactory/SpatialService (без дублирования логики), разрешает цели и пути, и возвращает чистый DTO.
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

from app.errors import SimulationIntegrityError
from app.domain.observatory import (
    ObservatoryAgentDTO, ObservatoryCausalDiagnosticDTO, ObservatoryEdgeDTO,
    ObservatoryNodeDTO, ObservatoryPathDTO, ObservatoryResolutionDTO,
    ObservatorySpatialIntentDTO, ObservatoryTopologyDTO, SpatialObservatoryDTO
)
from app.domain.spatial_target import (
    SpatialTargetIntent, SpatialTargetType, TargetResolutionStatus, SpatialResolutionMode
)
from app.models.spatial_contracts import NodeRole
from app.services.spatial.spatial_service import SpatialService
from app.services.spatial.spatial_target_resolver import SpatialTargetResolver

logger = logging.getLogger(__name__)

class SpatialObservatoryService:
    """
    ADR-O-330: Сервис проекции Spatial Kernel для редактора карт.
    Принимает черновик карты и агентов, возвращает ObservatoryDTO.
    """

    def inspect(
        self,
        campaign_id: str,
        location_id: str,
        editor_data: Dict[str, Any],
        agents_data: Dict[str, Any],
    ) -> SpatialObservatoryDTO:
        """
        Главная точка входа. Возвращает полную проекцию пространства.
        
        :param editor_data: Сырой JSON карты (nodes, walls, doors).
        :param agents_data: Словарь NPC позиций и их интентов {npc_id: {position, intent}}.
        """
        # 1. Собираем эфемерный SpatialService из черновика карты через SpatialFactory (L9 FIX)
        scene_state_stub = {"npc_positions": agents_data}
        try:
            from app.services.spatial.spatial_factory import SpatialFactory
            svc = SpatialFactory.build_for_campaign(
                campaign_id=campaign_id,
                location_id=location_id,
                scene_state=scene_state_stub,
                editor_data_override=editor_data
            )
        except SimulationIntegrityError as e:
            # S-OBS-06: Ловим критическую ошибку карты (например, стену без door_id)
            # и возвращаем её как каузальную диагностику, не валив сервер.
            logger.error(f"[OBSERVATORY] Map validation failed: {e.invariant_id}")
            return SpatialObservatoryDTO(
                topology=ObservatoryTopologyDTO(nodes=(), edges=()),
                agents=(),
                diagnostics=(ObservatoryCausalDiagnosticDTO(
                    phase="TOPOLOGY", status="CRITICAL",
                    code=e.invariant_id or "SIM_INTEGRITY_ERROR",
                    message=str(e)
                ),)
            )
        except Exception as e:
            logger.error(f"[OBSERVATORY] Unexpected compilation error: {e}", exc_info=True)
            return SpatialObservatoryDTO(
                topology=ObservatoryTopologyDTO(nodes=(), edges=()),
                agents=(),
                diagnostics=(ObservatoryCausalDiagnosticDTO(
                    phase="TOPOLOGY", status="CRITICAL", code="UNKNOWN_EXCEPTION",
                    message=str(e)
                ),)
            )
        
        if not svc:
            return SpatialObservatoryDTO(
                topology=ObservatoryTopologyDTO(nodes=(), edges=()),
                agents=(),
                diagnostics=(ObservatoryCausalDiagnosticDTO(
                    phase="TOPOLOGY", status="INVALID", code="GRAPH_BUILD_FAILED",
                    message="SpatialService failed to build from editor_data"
                ),)
            )
            
        # 2. Собираем топологию (S-OBS-03 / TEMPORARY INTERNAL PROJECTION)
        topo_nodes, topo_edges = self._extract_topology(svc)
        
        # 3. Разрешаем цели и пути для каждого NPC
        resolver = SpatialTargetResolver(svc)
        agent_projections = []
        global_diagnostics = []
        
        for npc_id, data in agents_data.items():
            pos = self._extract_pos(data)
            intent_data = data.get("intent")
            
            agent_dto = ObservatoryAgentDTO(actor_id=npc_id, position=pos)
            diagnostics = []
            
            if intent_data and pos:
                intent = SpatialTargetIntent(
                    target_type=SpatialTargetType[intent_data.get("target_type", "ANCHOR")],
                    target_id=intent_data.get("target_id"),
                    reason=intent_data.get("reason", "unknown"),
                    confidence=float(intent_data.get("confidence", 0.5)),
                    context_ref=intent_data.get("context_ref")
                )
                
                resolved = resolver.resolve(
                    intent, 
                    npc_positions=agents_data, 
                    actor_id=npc_id, 
                    location_id=location_id
                )
                
                if resolved.resolution_status != TargetResolutionStatus.RESOLVED:
                    diagnostics.append(ObservatoryCausalDiagnosticDTO(
                        phase="RESOLUTION", status=resolved.resolution_status.value,
                        code="RESOLUTION_FAILED", message=resolved.resolution_reason
                    ))
                else:
                    path_dto = self._calculate_path(
                        svc, pos, resolved.position, resolved.anchor_node_id, resolved.mode
                    )
                    if path_dto and path_dto.status == "BLOCKED":
                        diagnostics.append(ObservatoryCausalDiagnosticDTO(
                            phase="PATHFINDING", status="BLOCKED",
                            code=path_dto.failure_reason or "PATH_BLOCKED",
                            message="A* failed to find a route"
                        ))
                    
                    agent_dto = ObservatoryAgentDTO(
                        actor_id=npc_id, position=pos,
                        intent=ObservatorySpatialIntentDTO(
                            target_type=intent.target_type.value, target_id=intent.target_id,
                            reason=intent.reason, confidence=intent.confidence,
                            context_ref=intent.context_ref
                        ),
                        resolution=ObservatoryResolutionDTO(
                            status=resolved.resolution_status.value, mode=resolved.mode.value if resolved.mode else None,
                            position=resolved.position, anchor_node_id=resolved.anchor_node_id,
                            reason=resolved.resolution_reason
                        ),
                        path=path_dto,
                        diagnostics=tuple(diagnostics)
                    )
                    
            agent_projections.append(agent_dto)
            global_diagnostics.extend(diagnostics)
            
        return SpatialObservatoryDTO(
            topology=ObservatoryTopologyDTO(nodes=tuple(topo_nodes), edges=tuple(topo_edges)),
            agents=tuple(agent_projections),
            diagnostics=tuple(global_diagnostics)
        )

    def _extract_topology(self, svc: SpatialService) -> Tuple[List[ObservatoryNodeDTO], List[ObservatoryEdgeDTO]]:
        """Временная introspection. В будущем должна быть заменена на read-only API."""
        nodes = []
        for node_id, node_ref in svc._graph.items():
            nodes.append(ObservatoryNodeDTO(
                node_id=node_id,
                position=(node_ref.x, node_ref.y),
                role=node_ref.role.value,
                zone_id=node_ref.zone_id,
                is_boundary=(node_ref.role == NodeRole.BOUNDARY)
            ))
            
        edges = []
        for from_id, to_ids in svc._connections.items():
            for to_id in to_ids:
                traversable = True
                block_reason = None
                edges.append(ObservatoryEdgeDTO(
                    from_node_id=from_id, to_node_id=to_id,
                    traversable=traversable, block_reason=block_reason
                ))
        return nodes, edges

    def _calculate_path(
        self, 
        svc: SpatialService, 
        start_xy: Tuple[float, float], 
        target_xy: Tuple[float, float],
        target_node_id: Optional[str],
        mode: Optional[SpatialResolutionMode]
    ) -> Optional[ObservatoryPathDTO]:
        """Точно повторяет логику MovementEngine для вызова find_path."""
        if mode == SpatialResolutionMode.LOCAL_POSITION:
            return ObservatoryPathDTO(
                status="LOCAL_STEERING", points=(start_xy, target_xy), 
                node_ids=(), failure_reason=None
            )
            
        if not target_node_id:
            return ObservatoryPathDTO(
                status="BLOCKED", points=(), node_ids=(), 
                failure_reason="MISSING_TARGET_NODE_ID"
            )

        # Получаем NodeRef по каноническому ID, как это делает MovementEngine
        target_node = svc.get_node(target_node_id)
        if not target_node:
            return ObservatoryPathDTO(
                status="BLOCKED", points=(), node_ids=(), 
                failure_reason="TARGET_NODE_NOT_FOUND"
            )
            
        path_refs = svc.find_path(start_xy, target_node)
        if not path_refs:
            return ObservatoryPathDTO(
                status="BLOCKED", points=(), node_ids=(), 
                failure_reason="A_STAR_FAILED"
            )
            
        return ObservatoryPathDTO(
            status="OK",
            points=tuple((n.x, n.y) for n in path_refs),
            node_ids=tuple(n.node_id for n in path_refs),
            failure_reason=None
        )

    def _extract_pos(self, data: Any) -> Tuple[float, float]:
        """Безопасно извлекает координаты из данных агента."""
        if not isinstance(data, dict):
            return (0.0, 0.0)
        # Приоритетно читаем local_position, так как position может быть строкой (node_id)
        pos = data.get("local_position", data.get("position"))
        if isinstance(pos, dict):
            x, y = pos.get("x"), pos.get("y")
            if x is None or y is None: return (0.0, 0.0)
            try: return float(x), float(y)
            except (TypeError, ValueError) as e:
                logger.debug(f"Coord parse error: {e}")
                return (0.0, 0.0)
        if isinstance(pos, (list, tuple)) and len(pos) == 2:
            try: return float(pos[0]), float(pos[1])
            except (TypeError, ValueError) as e:
                logger.debug(f"Coord parse error: {e}")
                return (0.0, 0.0)
        return (0.0, 0.0)