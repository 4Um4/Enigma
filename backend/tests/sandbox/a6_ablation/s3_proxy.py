"""A6 S3 Proxy Logger — fail-loud diagnostic for causal producer failures.

READ-ONLY harness. Does NOT modify production code.

Purpose (Master Q1/S3): the pipeline's 4 causal slice producer call sites
wrap producer failures in `except Exception: logger.warning("...producer failed...")`,
which swallows the error and continues with no-op. That is silent-mute by design.

S3 diagnostic makes those failures visible by intercepting ONLY the 4
causal producer warnings, via a proxy logger installed on the pipeline
module-level `logger` binding. Non-causal warnings are delegated to the
real logger unchanged.

Precision (verified in 4a+4b pre-flight S3.2/S3.3):
  - 4 caller-side sites emit `[CAUSAL_SLICE]`, `[CAUSAL_SLICE_HUNGER]`,
    `[CAUSAL_SLICE_GRIEVANCE]`, `[CAUSAL_SLICE_AFFECTION]` followed by
    `producer failed (no-op)`.
  - 13 OTHER warnings in the same module (`[MEMORY]`, `[BELIEF]`, `[NEED_MODIFIERS]`,
    `[MEM-3]`, `[MEMORY_EVENT]`, `[APPROACH_NAV]`, `[FLEE_NAV]`, ...) do NOT
    contain `producer failed` — they pass through unchanged.

S3 is diagnostic, NOT part of scoring matrix. Do not compare its intent
distribution to S0-S2.
"""

from contextlib import contextmanager
from typing import Any, List, Optional


# Fatal markers — (prefix, substring). Both must be present for raise.
_FATAL_PREFIXES = (
    "[CAUSAL_SLICE",
    "[CAUSAL_SLICE_HUNGER",
    "[CAUSAL_SLICE_GRIEVANCE",
    "[CAUSAL_SLICE_AFFECTION",
)
_FATAL_SUBSTRING = "producer failed"


class _FailLoudLogger:
    """Proxy logger — raises RuntimeError for causal producer warnings only.

    All other methods (info, debug, error, exception, __getattr__) delegate
    to the real logger. Only `warning()` is intercepted.
    """

    def __init__(self, real_logger: Any) -> None:
        self._real = real_logger
        self.failures: List[str] = []

    def warning(self, msg: Any, *args: Any, **kwargs: Any) -> None:
        msg_str = str(msg) if not isinstance(msg, str) else msg
        is_causal = any(p in msg_str for p in _FATAL_PREFIXES)
        has_marker = _FATAL_SUBSTRING in msg_str
        if is_causal and has_marker:
            self.failures.append(msg_str)
            raise RuntimeError(f"[A6-S3-FAIL-LOUD] {msg_str}")
        return self._real.warning(msg, *args, **kwargs)

    def __getattr__(self, name: str) -> Any:
        # Delegate info/debug/error/exception/isEnabledFor/etc.
        return getattr(self._real, name)


@contextmanager
def s3_fail_loud_logger():
    """Install fail-loud proxy on npc_tick_pipeline.logger.

    Yields the proxy (with `.failures` list mutated in place).
    Restores original logger binding in finally.
    """
    import app.services.npc.npc_tick_pipeline as _ntp

    original = _ntp.logger
    proxy = _FailLoudLogger(original)
    try:
        _ntp.logger = proxy
        yield proxy
    finally:
        _ntp.logger = original
