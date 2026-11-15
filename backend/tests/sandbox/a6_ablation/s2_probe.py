"""A6 S2 probe — capture allies for threat + grievance producers only.

SCOPE (variant C): hunger and affection do not accept allies parameter.
They are NOT wrapped — pass through unchanged, no side effect.
"""

from contextlib import contextmanager
from typing import Dict, List, NamedTuple, Optional

from app.services.npc.causal_slice_threat import ThreatDesiredChangeProducer
from app.services.npc.causal_slice_grievance import GrievanceDesiredChangeProducer


_PRODUCER_TAGS = (
    (ThreatDesiredChangeProducer, "threat"),
    (GrievanceDesiredChangeProducer, "grievance"),
)


class ProducerCall(NamedTuple):
    tag: str
    npc_id: str
    tick_id: Optional[object]
    allies: int
    method_weights: Dict[str, float]


@contextmanager
def probe_producer_calls():
    """Capture per-call info for threat + grievance only. Restore in finally."""
    captured: List[ProducerCall] = []
    originals = [(cls, cls.__dict__["resolve"]) for cls, _ in _PRODUCER_TAGS]

    def _make_wrapper(orig_func, tag_name):
        def _wrapper(*args, **kwargs):
            result = orig_func(*args, **kwargs)
            npc_id = kwargs.get("who") or ""
            if not npc_id:
                state_arg = kwargs.get("state")
                npc_id = getattr(state_arg, "npc_id", "") if state_arg is not None else ""
            tick_id = getattr(kwargs.get("state"), "tick_id", None)
            allies = kwargs.get("allies", 0)
            weights = dict(result.method_weights) if result is not None else {}
            captured.append(
                ProducerCall(
                    tag=tag_name,
                    npc_id=npc_id,
                    tick_id=tick_id,
                    allies=int(allies),
                    method_weights=weights,
                )
            )
            return result

        return _wrapper

    try:
        for cls, tag in _PRODUCER_TAGS:
            orig = cls.__dict__["resolve"]
            cls.resolve = staticmethod(_make_wrapper(orig.__func__, tag))
        yield captured
    finally:
        for cls, orig in originals:
            cls.resolve = orig
