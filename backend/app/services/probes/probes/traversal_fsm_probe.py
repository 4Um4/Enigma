# backend/app/services/probes/probes/traversal_fsm_probe.py
"""
ADR-TRAV-FSM: Детектор Zombie Traversals.
Проверяет, что в active_traversals нет терминальных статусов (COMPLETED, CANCELLED).
"""
from ..probe_registry import Probe, ProbeContext, ProbeResult

class TraversalFSMProbe(Probe):
    name = "INV-TRAV-ZOMBIE"
    severity = "ERROR"

    def check(self, ctx: ProbeContext) -> ProbeResult:
        travs = ctx.scene_state.get("active_traversals", {})
        if not travs:
            return ProbeResult(name=self.name, severity=self.severity, passed=True)
            
        _terminal_statuses = {"COMPLETED", "CANCELLED"}
        _zombies = []
        
        for npc_id, t in travs.items():
            if not isinstance(t, dict):
                continue
            status = t.get("status", "").upper()
            if status in _terminal_statuses:
                _zombies.append(f"{npc_id}={status}")
                
        if _zombies:
            return ProbeResult(
                name=self.name,
                severity=self.severity,
                passed=False,
                details=f"Zombie traversals detected: {', '.join(_zombies)} at tick {ctx.tick_id}"
            )
            
        return ProbeResult(name=self.name, severity=self.severity, passed=True)