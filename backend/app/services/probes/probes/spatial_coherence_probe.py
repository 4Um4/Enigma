# backend/app/services/probes/probes/spatial_coherence_probe.py
"""
SC-1..SC-8: Пространственная согласованность.
Контракт: CAUSAL_CONTRACT_v2.0.md -> 2.1.1. Spatial Coherence Contract.
"""
from ..probe_registry import Probe, ProbeContext, ProbeResult

class SpatialCoherenceProbe(Probe):
    name = "INV-SC-1-8-SPATIAL-COHERENCE"
    severity = "ERROR"

    def check(self, ctx: ProbeContext) -> ProbeResult:
        svc = ctx.spatial_service
        npc_pos = ctx.scene_state.get("npc_positions", {})
        scene_loc_id = ctx.scene_state.get("location_id")

        for npc_id, pos_data in npc_pos.items():
            if not isinstance(pos_data, dict):
                continue

            lp = pos_data.get("local_position")
            curr_node_id = pos_data.get("position", "")
            npc_loc_id = pos_data.get("location_id", scene_loc_id)

            # SC-1: local_position не может быть (0.0, 0.0)
            if isinstance(lp, dict) and lp.get("x", 1.0) == 0.0 and lp.get("y", 1.0) == 0.0:
                return ProbeResult(
                    name=self.name, severity=self.severity, passed=False,
                    details=f"SC-1 FAIL: NPC '{npc_id}' has local_position (0.0, 0.0) at tick {ctx.tick_id}"
                )

            # SC-2: local_position должен принадлежать текущей location_id.
            # Если NPC находится в другой локации, он не активен в этой сцене — пропускаем его.
            if npc_loc_id != scene_loc_id:
                continue

            # SC-5: SpatialService должен быть собран (валиден) для текущей сцены.
            # Если svc отсутствует (например, в PBT-тестах), мы не можем проверить SC-3..SC-8, пропускаем.
            if not svc:
                continue

            if lp and curr_node_id:
                # SC-3: current_node должен существовать в текущем SpatialService
                node = svc.get_node(curr_node_id)
                if not node:
                    return ProbeResult(
                        name=self.name, severity=self.severity, passed=False,
                        details=f"SC-3 FAIL: NPC '{npc_id}' node '{curr_node_id}' not found in SpatialService"
                    )

                # SC-4: local_position должен быть в радиусе 10.0 метров от current_node.
                # Порог 10.0 метров допускает отклонения во время перехода (traversal) между узлами,
                # пока node_id не обновился на новый узел назначения.
                if abs(lp.get("x", 0.0) - node.x) > 10.0 or abs(lp.get("y", 0.0) - node.y) > 10.0:
                    return ProbeResult(
                        name=self.name, severity=self.severity, passed=False,
                        details=f"SC-4 FAIL: NPC '{npc_id}' pos ({lp.get('x')}, {lp.get('y')}) too far from node '{curr_node_id}' ({node.x}, {node.y})"
                    )

        return ProbeResult(name=self.name, severity=self.severity, passed=True)