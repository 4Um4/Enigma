"""S1 integration verification — real DriftLab 1 tick with S1 OFF.

Run explicitly:
    A6_INTEGRATION=1 pytest backend/tests/sandbox/a6_ablation/test_s1_integration.py

Purpose: prove that during real pipeline execution, when the causal slice
layer is disabled, DecisionHub.apply_modifiers actually receives
causal_modifiers=None (not a dict). This is the S1 verification gate:
unit tests prove the patching mechanics; this test proves the downstream
observes the effect.

Gate assertions:
  1. At least one apply_modifiers call captured (some NPC decided).
  2. Every captured causal_modifiers is None (S1 effective — caller's `or None`
     turned the falsy `{}` into None, and downstream skipped the layer).

If gate fails: S1 is NOT effective in real pipeline — abort scoring matrix.
"""

import os

import pytest

if not os.getenv("A6_INTEGRATION"):
    pytest.skip(
        "A6_INTEGRATION=1 required — real DriftLab 1 tick integration check",
        allow_module_level=True,
    )

from tests.sandbox.SUPERBOX.drift_laboratory import (
    DriftConfig,
    DriftLaboratory,
)
from tests.sandbox.a6_ablation.s1_harness import (
    s1_layer_off,
    s1_probe_apply_modifiers,
)


def test_s1_integration_downstream_receives_none():
    """Real DriftLab 1 tick. Assert all apply_modifiers calls received None."""
    lab = DriftLaboratory(DriftConfig())
    captured = []
    try:
        lab._setup()
        with s1_layer_off():
            with s1_probe_apply_modifiers() as captured_list:
                lab._run_idle_tick_direct()
            captured = list(captured_list)
    finally:
        lab._teardown()

    # Gate 1: at least one decision happened (else verification is vacuous)
    assert len(captured) > 0, (
        "no apply_modifiers calls captured during 1 idle tick. "
        "Cannot verify S1 effectiveness. Possible causes: no NPCs in "
        "campaign/location, DriftLab _setup() failed silently, or "
        "_run_idle_tick_direct() errored (see stdout)."
    )

    # Gate 2: S1 effective — all downstream calls received None
    non_none = [c for c in captured if c is not None]
    assert non_none == [], (
        f"S1 not effective: {len(non_none)}/{len(captured)} apply_modifiers "
        f"calls received non-None causal_modifiers. Expected all None. "
        f"First 3: {non_none[:3]}"
    )

    # Diagnostic output for the operator (visible in pytest -s)
    print(f"[S1-INT] captured {len(captured)} apply_modifiers calls, all None")
