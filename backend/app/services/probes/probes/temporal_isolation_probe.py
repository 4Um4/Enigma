# backend/app/services/probes/probes/temporal_isolation_probe.py
"""
Invariant III: Temporal Isolation. Входные данные тика не мутируются во время вычисления.
Проверяем, что хеш TickState до pipeline совпадает с хешем после.
"""
from ..probe_registry import Probe, ProbeContext, ProbeResult

class TemporalIsolationProbe(Probe):
    name = "INV-TEMPORAL-ISOLATION"
    severity = "ERROR"

    def check(self, ctx: ProbeContext) -> ProbeResult:
        hash_before = ctx.tick_state_hash_before
        hash_after = ctx.tick_state_hash_after
        
        if hash_before is not None and hash_after is not None:
            if hash_before != hash_after:
                return ProbeResult(
                    name=self.name,
                    severity=self.severity,
                    passed=False,
                    details=f"Tick {ctx.tick_id}: TickState mutated during pipeline execution (hash mismatch)"
                )
        return ProbeResult(name=self.name, severity=self.severity, passed=True)