# backend/app/services/probes/probe_runner.py
"""
Запускает все зарегистрированные probes после тика.
"""
import logging
from typing import List
from .probe_registry import Probe, ProbeContext, ProbeResult

logger = logging.getLogger(__name__)

class ProbeRunner:
    def __init__(self, probes: List[Probe] | None = None) -> None:
        self._probes = probes or []

    def register(self, probe: Probe) -> None:
        self._probes.append(probe)

    def run_all(self, ctx: ProbeContext) -> List[ProbeResult]:
        results = []
        for probe in self._probes:
            try:
                res = probe.check(ctx)
                results.append(res)
                if not res.passed and res.severity == "ERROR":
                    logger.error(f"[PROBE_FAIL] {res.name}: {res.details}")
                elif not res.passed and res.severity == "WARN":
                    logger.warning(f"[PROBE_WARN] {res.name}: {res.details}")
            except Exception as e:
                logger.error(f"[PROBE_CRASH] {getattr(probe, 'name', 'Unknown')}: {e}")
                results.append(ProbeResult(name=probe.name, severity="ERROR", passed=False, details=f"Crashed: {e}"))
        return results