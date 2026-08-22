"""
path: backend/tests/calibration_lab/test_m0_superbox.py
Назначение: M0-AC-005 — overlay констант пресета НЕ ЛОМАЕТ инварианты
    SUPERBOX: дельта против baseline (тот же сценарий-набор без overlay).
    Прямое «всё зелёное» некорректно: часть сценариев может быть красной
    pre-existing (параллельные сессии правят SUPERBOX). S213: globs
    адаптера не включают semantic_torture — skip-assert был проверкой
    пустого множества, удалён.
Зависимости: superbox_adapter, pytest.
Основные сущности: TestSuperboxOverlayDelta.
"""
from pathlib import Path

import pytest

from app.services.calibration.superbox_adapter import SuperboxAdapter

_REPO_ROOT = Path(__file__).resolve().parents[3]
_GOLDEN = str(
    _REPO_ROOT / "config" / "calibration" / "test_presets" / "enigma_golden.yaml"
)
_SUSPECT = (
    "tests/sandbox/SUPERBOX/scenarios/"
    "epistemic_second_order_attribution_test.py"
)


@pytest.mark.slow
class TestSuperboxOverlayDelta:
    def test_ac005_overlay_does_not_break_invariants(self) -> None:
        adapter = SuperboxAdapter()
        baseline = adapter.run_baseline([_SUSPECT])
        under = adapter.run_under_preset(_GOLDEN, extra_args=[_SUSPECT])
        if baseline.failed > 0:
            pytest.skip(
                f"Baseline красный pre-existing (failed={baseline.failed}) — "
                "overlay-дельта неопределима; сценарий в чужой зоне владения"
            )
        assert under.failed == 0, (
            f"Overlay золотой области ломает SUPERBOX-инвариант "
            f"({_SUSPECT}): baseline green, overlay red — регрессия ADR-O-361"
        )