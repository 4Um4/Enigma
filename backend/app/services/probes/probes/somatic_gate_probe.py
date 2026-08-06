# backend/app/services/probes/probes/somatic_gate_probe.py
"""
ADR-O-139: Somatic Gate. Body → Somatic → Semantic.
Проверяем, что NPC в шоке (>0.7) не имеют активных перемещений (MOVING).
"""
from ..probe_registry import Probe, ProbeContext, ProbeResult

class SomaticGateProbe(Probe):
    name = "INV-SOMATIC-GATE"
    severity = "WARN"

    def check(self, ctx: ProbeContext) -> ProbeResult:
        active_traversals = ctx.scene_state.get("active_traversals", {})
        npc_positions = ctx.scene_state.get("npc_positions", {})
        
        for npc in ctx.all_npcs_raw:
            if not isinstance(npc, dict): continue
            npc_id = npc.get("id") or npc.get("npc_id")
            if not npc_id: continue
            
            body_state = npc.get("body_state", {})
            shock = body_state.get("shock", 0.0)
            
            if shock > 0.7:
                # Если NPC в шоке, но имеет активное перемещение — нарушение
                trav = active_traversals.get(npc_id, {})
                if trav.get("status") == "MOVING":
                    return ProbeResult(
                        name=self.name,
                        severity=self.severity,
                        passed=False,
                        details=f"Tick {ctx.tick_id}: NPC {npc_id} in shock ({shock:.2f}) but is MOVING"
                    )
                    
        return ProbeResult(name=self.name, severity=self.severity, passed=True)