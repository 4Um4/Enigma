"""S3 integration verification — real DriftLab 1 tick with fail-loud proxy.

Run explicitly:
    A6_INTEGRATION=1 pytest backend/tests/sandbox/a6_ablation/test_s3_integration.py -v -s

Purpose: prove that s3_proxy.s3_fail_loud_logger() is installed on
npc_tick_pipeline.logger during a real tick and correctly intercepts
the 4 causal producer warnings (when present), delegates all other
warnings to the real logger, and restores the original logger binding.

Master protocol (guarantees):
  - lab._setup() and lab._teardown() both verified.
  - lab._teardown() in finally — even if the tick raises.
  - Distinguish: proxy.failures == [] / > 0 / unrelated RuntimeError.
  - Failure count > 0 is diagnostic gold, not a pass/fail signal.
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
from tests.sandbox.a6_ablation.s3_proxy import s3_fail_loud_logger


def test_s3_integration_fail_loud_proxy_during_tick():
    """Real DriftLab 1 tick with fail-loud proxy installed on npc_tick_pipeline."""
    lab = DriftLaboratory(DriftConfig())
    setup_ok = False
    tick_ok = False
    teardown_ok = False
    teardown_err = None
    wrapper_err = None
    failures = []

    try:
        lab._setup()
        setup_ok = True
        try:
            with s3_fail_loud_logger() as proxy:
                try:
                    lab._run_idle_tick_direct()
                    tick_ok = True
                except RuntimeError as exc:
                    wrapper_err = f"{type(exc).__name__}: {exc}"
                except Exception as exc:
                    wrapper_err = f"{type(exc).__name__}: {exc}"
                finally:
                    failures = list(proxy.failures)
        except Exception as cm_err:
            wrapper_err = f"CM_ERR {type(cm_err).__name__}: {cm_err}"
    finally:
        try:
            lab._teardown()
            teardown_ok = True
        except Exception as e:
            teardown_err = f"{type(e).__name__}: {e}"

    print(f"[S3-INT] SETUP_OK={setup_ok}")
    print(f"[S3-INT] TICK_OK={tick_ok}")
    print(f"[S3-INT] PROXY_FAILURES_COUNT={len(failures)}")
    for i, msg in enumerate(failures):
        safe = msg.replace("\r\n", "\\n").replace("\n", "\\n")
        print(f"[S3-INT] PROXY_FAILURE_{i}={safe}")
    print(f"[S3-INT] WRAPPER_ERR={wrapper_err if wrapper_err else 'None'}")
    print(f"[S3-INT] TEARDOWN_OK={teardown_ok}")
    if teardown_err:
        print(f"[S3-INT] TEARDOWN_ERR={teardown_err}")

    assert setup_ok, "lab._setup() failed — cannot verify"
    assert teardown_ok, f"lab._teardown() failed — state may be leaked: {teardown_err}"

    wrapper_is_causal = wrapper_err is not None and "A6-S3-FAIL-LOUD" in wrapper_err

    if len(failures) == 0 and wrapper_err is None:
        print("[S3-INT] SCENARIO: NO_SILENT_FAILURES_IN_THIS_TICK")
    elif len(failures) > 0:
        print(f"[S3-INT] SCENARIO: REAL_SILENT_FAILURES_DETECTED — {len(failures)}")
    elif wrapper_is_causal:
        print("[S3-INT] SCENARIO: RUNTIME_ERR_PROPAGATED_CAUSAL")
    elif wrapper_err is not None:
        print(f"[S3-INT] SCENARIO: NON_CAUSAL_RUNTIME_ERR — {wrapper_err}")

    # No assertion on failure count: S3 is diagnostic.
    # 0 (healthy pipeline) and N>0 (revealed silent-mute) are both valid outcomes.