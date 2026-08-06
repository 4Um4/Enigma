# backend/app/services/probes/probes/causal_provenance_probe.py
"""
Invariant I: Causal Provenance. Любое изменение должно иметь причину.
Проверяем, что каждый NPC в all_npcs_raw имеет валидный id (источник идентичности).
"""
from ..probe_registry import Probe, ProbeContext, ProbeResult

class CausalProvenanceProbe(Probe):
    name = "INV-CAUSAL-PROVENANCE"
    severity = "ERROR"

    def check(self, ctx: ProbeContext) -> ProbeResult:
        for npc in ctx.all_npcs_raw:
            if not isinstance(npc, dict): continue
            npc_id = npc.get("id") or npc.get("npc_id")
            if not npc_id:
                return ProbeResult(
                    name=self.name,
                    severity=self.severity,
                    passed=False,
                    details=f"Tick {ctx.tick_id}: NPC without id in all_npcs_raw (Causal Provenance violation)"
                )
        return ProbeResult(name=self.name, severity=self.severity, passed=True)