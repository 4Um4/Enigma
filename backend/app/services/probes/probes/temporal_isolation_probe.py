# backend/app/services/probes/probes/temporal_isolation_probe.py
"""
Invariant III: Temporal Isolation. Входные данные тика не мутируются во время вычисления.
Проверяем, что scene_state не содержит маркеров мутации.
"""
from ..probe_registry import Probe, ProbeContext, ProbeResult

class TemporalIsolationProbe(Probe):
    name = "INV-TEMPORAL-ISOLATION"
    severity = "ERROR"

    def check(self, ctx: ProbeContext) -> ProbeResult:
        if "__mutated_during_tick" in ctx.scene_state:
            return ProbeResult(
                name=self.name,
                severity=self.severity,
                passed=False,
                details=f"Tick {ctx.tick_id}: scene_state mutated during tick execution"
            )
        return ProbeResult(name=self.name, severity=self.severity, passed=True)