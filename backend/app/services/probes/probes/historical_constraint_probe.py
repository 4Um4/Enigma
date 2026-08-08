# backend/app/services/probes/probes/historical_constraint_probe.py
"""
Invariant II: Historical Constraint. Будущее вычисляется из истории.
Проверяем, что каждый NPC, принявший решение (в mutation), имел вычисленную проекцию L3 (effective_drives).
L3 вычисляется из L0 + L2.5 (истории), а не из L0 напрямую.
"""
from ..probe_registry import Probe, ProbeContext, ProbeResult

class HistoricalConstraintProbe(Probe):
    name = "INV-HISTORICAL-CONSTRAINT"
    severity = "ERROR"

    def check(self, ctx: ProbeContext) -> ProbeResult:
        mutation = ctx.tick_mutation
        drives_map = ctx.effective_drives_map
        
        if not mutation or not drives_map:
            return ProbeResult(name=self.name, severity=self.severity, passed=True, details="No mutation or drives_map in context.")

        # Проверяем все интенты (решения NPC)
        for intent in getattr(mutation, "communication_intents", []) + getattr(mutation, "movement_intents", []):
            npc_id = getattr(intent, "speaker", None) or getattr(intent, "actor_id", None)
            if npc_id:
                # Если NPC принял решение, у него должен быть L3 (effective_drives)
                if npc_id not in drives_map:
                    return ProbeResult(
                        name=self.name,
                        severity=self.severity,
                        passed=False,
                        details=f"Tick {ctx.tick_id}: NPC {npc_id} made decision without L3 effective_drives (Historical Constraint violation)"
                    )
                    
        return ProbeResult(name=self.name, severity=self.severity, passed=True)