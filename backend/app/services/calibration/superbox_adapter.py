"""
path: backend/app/services/calibration/superbox_adapter.py
Назначение: Прогон SUPERBOX-инвариантных сценариев под overlay констант
    пресета (M0-AC-005). Offline-subset: epistemic_*/modifier_*; LLM-
    зависимые (semantic_torture) исключаются с ЯВНЫМ логом (не молча).
    Запуск — pytest.main в текущем процессе: overlay identity-патч
    действует на все загруженные модули (ADR-O-361).
Зависимости: pytest, app.services.calibration.preset_io.
Основные сущности: SuperboxAdapter, SuperboxRunResult.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

from app.services.calibration.config_overlay import overlay_constants
from app.services.calibration.preset_io import Preset, load_preset

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[4]
_SCENARIOS_DIR = (
    _REPO_ROOT / "backend" / "tests" / "sandbox" / "SUPERBOX" / "scenarios"
)

# LLM-зависимые сценарии: в offline-контуре дают ложно-красные результаты.
_LLM_DEPENDENT: frozenset = frozenset({"semantic_torture_test.py"})


@dataclass(frozen=True)
class SuperboxRunResult:
    passed: int
    failed: int
    skipped_scenarios: List[str] = field(default_factory=list)


def _scenario_files() -> List[Path]:
    return sorted(
        f
        for f in _SCENARIOS_DIR.glob("epistemic_*.py")
    ) + sorted(
        f
        for f in _SCENARIOS_DIR.glob("modifier_*.py")
    )


class SuperboxAdapter:
    """M0-AC-005: инварианты SUPERBOX зелёны при overlay констант пресета."""

    def run_baseline(
        self, files: List[str] | None = None
    ) -> SuperboxRunResult:
        """Baseline: тот же набор сценариев БЕЗ overlay (для дельта-вердикта
        AC-005: 'overlay не ломает', а не 'всё зелёное при любом pre-existing')."""
        import pytest

        args = ["-q", "--tb=line", "-p", "no:cacheprovider"]
        if files:
            args.extend(files)
        else:
            args.extend(str(f) for f in _scenario_files())
        exit_code = pytest.main(args)
        return SuperboxRunResult(
            passed=0 if exit_code != 0 else 1,
            failed=0 if exit_code == 0 else 1,
            skipped_scenarios=[],
        )

    def run_under_preset(
        self, preset_path: str, *, extra_args: List[str] | None = None
    ) -> SuperboxRunResult:
        preset: Preset = load_preset(preset_path)
        files = _scenario_files()
        skipped = [f.name for f in files if f.name in _LLM_DEPENDENT]
        runnable = [str(f) for f in files if f.name not in _LLM_DEPENDENT]
        if skipped:
            logger.warning(
                "[SUPERBOX_ADAPTER] LLM-зависимые сценарии пропущены "
                "(offline-контур калибровки): %s", skipped
            )
        import pytest

        args = ["-q", "--tb=line", "-p", "no:cacheprovider", *runnable]
        if extra_args:
            args.extend(extra_args)
        with overlay_constants(
            preset.constants,
            require_loaded=("app.services.npc.decision_hub",),
        ):
            exit_code = pytest.main(args)
        passed = 0 if exit_code != 0 else 1  # грубый статус; детали в логе
        failed = 0 if exit_code == 0 else 1
        return SuperboxRunResult(passed=passed, failed=failed, skipped_scenarios=skipped)