# backend/app/services/probes/probes/historical_constraint_probe.py
"""
Invariant II: Historical Constraint. Будущее вычисляется из истории.
Проверяем, что scene_state содержит историю (tick > 0, game_time > 0).
"""
from ..probe_registry import Probe, ProbeContext, ProbeResult

class HistoricalConstraintProbe(Probe):
    name = "INV-HISTORICAL-CONSTRAINT"
    severity = "WARN"

    def check(self, ctx: ProbeContext) -> ProbeResult:
        tick = ctx.scene_state.get("tick", 0)
        game_time = ctx.scene_state.get("game_time_seconds", 0.0)
        
        if tick == 0 or game_time == 0.0:
            return ProbeResult(
                name=self.name,
                severity=self.severity,
                passed=False,
                details=f"Tick {ctx.tick_id}: scene_state has no history (tick={tick}, game_time={game_time})"
            )
            
        return ProbeResult(name=self.name, severity=self.severity, passed=True)