"""A6 S1 Ablation Harness — disable causal slice layer for measurement.

READ-ONLY harness. Does NOT modify production code.
Uses monkeypatch-style override of producer class methods, restores in finally.

Layer: ThreatDesiredChangeProducer, HungerDesiredChangeProducer,
       GrievanceDesiredChangeProducer, AffectionDesiredChangeProducer
Effect of S1 (layer off): caller `X.to_modifiers(_dc) or None` -> `{} or None = None`
Downstream: `apply_modifiers(causal_modifiers=None)` -> no-op for causal
Other 9 modifier layers untouched.

Reference: npc_tick_pipeline.py:772/836/881/927 (or-None pattern)
           decision_hub.py:471-475 (skip falsy mod_dict)
"""
from contextlib import contextmanager
from typing import Dict, List, Optional

from app.services.npc.causal_slice_threat import ThreatDesiredChangeProducer
from app.services.npc.causal_slice_hunger import HungerDesiredChangeProducer
from app.services.npc.causal_slice_grievance import GrievanceDesiredChangeProducer
from app.services.npc.causal_slice_affection import AffectionDesiredChangeProducer
from app.services.npc.decision_hub import DecisionHub


_PRODUCERS = (
    ThreatDesiredChangeProducer,
    HungerDesiredChangeProducer,
    GrievanceDesiredChangeProducer,
    AffectionDesiredChangeProducer,
)


@contextmanager
def s1_layer_off():
    """S1: disable causal slice layer — all 4 producers return {}.

    Caller `X.to_modifiers(_dc) or None` -> `{} or None = None`.
    Downstream `apply_modifiers(causal_modifiers=None)` -> no-op.
    Other 9 modifier layers untouched.

    Restoration is guaranteed via finally, even on exception.
    Original staticmethod objects restored by identity (cls.__dict__).
    """
    originals = {cls: cls.__dict__["to_modifiers"] for cls in _PRODUCERS}
    try:
        for cls in _PRODUCERS:
            cls.to_modifiers = staticmethod(lambda dc: {})
        yield
    finally:
        for cls, orig in originals.items():
            cls.to_modifiers = orig


@contextmanager
def s1_probe_apply_modifiers():
    """Probe: record causal_modifiers value on every DecisionHub.apply_modifiers call.

    Yields a list, mutated in place. Each entry is causal_modifiers as seen
    by apply_modifiers: None (layer off / producer no-op) or Dict[str, float].
    """
    captured: List[Optional[Dict[str, float]]] = []
    original = DecisionHub.__dict__["apply_modifiers"]

    def _probe(scores, **kwargs):
        captured.append(kwargs.get("causal_modifiers"))
        return original.__func__(scores, **kwargs)

    try:
        DecisionHub.apply_modifiers = staticmethod(_probe)
        yield captured
    finally:
        DecisionHub.apply_modifiers = original