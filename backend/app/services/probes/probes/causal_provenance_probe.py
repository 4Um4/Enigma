# backend/app/services/probes/probes/causal_provenance_probe.py
"""
Invariant I: Causal Provenance. Любое изменение должно иметь причину.
Проверяем, что каждая дельта в tick_mutation имеет соответствующее событие в l1_drift_events.
"""
from ..probe_registry import Probe, ProbeContext, ProbeResult

class CausalProvenanceProbe(Probe):
    name = "INV-CAUSAL-PROVENANCE"
    severity = "ERROR"

    def check(self, ctx: ProbeContext) -> ProbeResult:
        mutation = ctx.tick_mutation
        if not mutation:
            return ProbeResult(name=self.name, severity=self.severity, passed=True, details="No mutation in context.")

        # Получаем список всех ID NPC, для которых сгенерированы L1 события
        l1_npc_ids = {getattr(e, "target_id", None) for e in getattr(mutation, "l1_drift_events", [])}  # noqa: ENIGMA002
        
        # Проверяем дельты (npc_deltas)
        for delta in getattr(mutation, "npc_deltas", []):  # noqa: ENIGMA002
            delta_npc_id = getattr(delta, "npc_id", None)  # noqa: ENIGMA002
            if delta_npc_id and delta_npc_id not in l1_npc_ids:
                # Если есть дельта, но нет L1 события — это нарушение причинно-следственной связи
                return ProbeResult(
                    name=self.name,
                    severity=self.severity,
                    passed=False,
                    details=f"Tick {ctx.tick_id}: NPC {delta_npc_id} has state delta but no L1 drift event (Causal Provenance violation)"
                )

        return ProbeResult(name=self.name, severity=self.severity, passed=True)