import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import psutil
except Exception:  # pragma: no cover - fallback path
    psutil = None


@dataclass
class RequirementReport:
    meets: bool
    details: dict[str, Any]


class SystemRequirements:
    """Checks host machine against minimum hardware profile (i7-9700F class / 16GB RAM)."""

    def __init__(self, min_physical_cores: int = 8, min_ram_gb: int = 8) -> None:
        self.min_physical_cores = min_physical_cores
        self.min_ram_gb = min_ram_gb

    def _cpu_model(self) -> str:
        cpuinfo = Path("/proc/cpuinfo")
        if cpuinfo.exists():
            for line in cpuinfo.read_text(
                encoding="utf-8", errors="ignore"
            ).splitlines():
                if line.lower().startswith("model name"):
                    return line.split(":", 1)[1].strip()
        return "unknown"

    def _detect_resources(self) -> tuple[int, int, float, str]:
        source = "psutil"
        if psutil is not None:
            physical_cores = psutil.cpu_count(logical=False) or 0
            logical_threads = psutil.cpu_count(logical=True) or 0
            ram_gb = round(psutil.virtual_memory().total / (1024**3), 2)
            return physical_cores, logical_threads, ram_gb, source

        source = "stdlib-fallback"
        logical_threads = os.cpu_count() or 0
        physical_cores = logical_threads
        page_size = os.sysconf("SC_PAGE_SIZE") if hasattr(os, "sysconf") else 0
        page_count = os.sysconf("SC_PHYS_PAGES") if hasattr(os, "sysconf") else 0
        total = (page_size * page_count) if page_size and page_count else 0
        ram_gb = round(total / (1024**3), 2) if total else 0.0
        return physical_cores, logical_threads, ram_gb, source

    def check(self) -> RequirementReport:
        physical_cores, logical_threads, ram_gb, source = self._detect_resources()
        cpu_model = self._cpu_model()

        meets = physical_cores >= self.min_physical_cores and ram_gb >= self.min_ram_gb
        details = {
            "cpu_model": cpu_model,
            "physical_cores": physical_cores,
            "logical_threads": logical_threads,
            "ram_gb": ram_gb,
            "detector": source,
            "minimum": {
                "physical_cores": self.min_physical_cores,
                "ram_gb": self.min_ram_gb,
                "target_profile": "Intel i7-9700F or better",
            },
        }
        return RequirementReport(meets=meets, details=details)
