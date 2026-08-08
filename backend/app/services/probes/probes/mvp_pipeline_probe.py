"""ENIGMA SELF-HEALING (Level 1): MvpPipelineProbe.
Проверяет, что mvp_controller загружен и трекеры обновляются (ловит N1, M-03).
"""
import logging
from typing import Any
from app.services.probes.probe_registry import Probe, ProbeContext, ProbeResult

logger = logging.getLogger(__name__)

class MvpPipelineProbe(Probe):
    name = "INV-MVP-PIPELINE"
    severity = "ERROR"

    def check(self, ctx: ProbeContext) -> ProbeResult:
        mvp = ctx.mvp_controller
        
        # N1: mvp_controller is None
        if mvp is None:
            return ProbeResult(
                name=self.name,
                severity="CRITICAL",
                passed=False,
                details="mvp_controller is None after tick — see startup log for canon_path error (N1)"
            )
            
        # N1: TruthState not loaded
        if mvp.truth_state is None:
            return ProbeResult(
                name=self.name,
                severity="CRITICAL",
                passed=False,
                details="mvp_controller.truth_state is None — init_campaign not called or failed?"
            )
            
        # M-03: FateTracker empty after tick > 1 (TICK_COMPLETED not firing)
        if ctx.tick_id > 1:
            fate_states = mvp.fate_tracker.get_all_states()
            if len(fate_states) == 0:
                return ProbeResult(
                    name=self.name,
                    severity="HIGH",
                    passed=False,
                    details=f"FateTracker empty after tick {ctx.tick_id} — TICK_COMPLETED subscriber not firing? (M-03/N2)"
                )

        return ProbeResult(name=self.name, severity=self.severity, passed=True)