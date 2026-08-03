# backend/app/services/probes/probes/spatial_coherence_probe.py
"""
SC-1: local_position не может быть (0.0, 0.0), если это явно не валидная координата.
"""
from ..probe_registry import Probe, ProbeContext, ProbeResult

class SpatialCoherenceProbe(Probe):
    name = "INV-SC-1-ZERO-POSITION"
    severity = "ERROR"

    def check(self, ctx: ProbeContext) -> ProbeResult:
        npc_pos = ctx.scene_state.get("npc_positions", {})
        for npc_id, pos_data in npc_pos.items():
            if not isinstance(pos_data, dict):
                continue
            lp = pos_data.get("local_position")
            if isinstance(lp, dict) and lp.get("x", 1.0) == 0.0 and lp.get("y", 1.0) == 0.0:
                return ProbeResult(
                    name=self.name,
                    severity=self.severity,
                    passed=False,
                    details=f"NPC '{npc_id}' has local_position (0.0, 0.0) at tick {ctx.tick_id}"
                )
        return ProbeResult(name=self.name, severity=self.severity, passed=True)