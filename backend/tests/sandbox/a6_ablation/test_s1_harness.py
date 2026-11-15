"""S1 harness tests — verify patch and restore correctness (unit, no DriftLab)."""
import pytest

from app.services.npc.decision_hub import DecisionHub

from tests.sandbox.a6_ablation.s1_harness import (
    _PRODUCERS,
    s1_layer_off,
    s1_probe_apply_modifiers,
)


def test_s1_layer_off_patches_all_producers():
    """Inside CM: all 4 producers return {} for any input (None or object)."""
    with s1_layer_off():
        for cls in _PRODUCERS:
            assert cls.to_modifiers(None) == {}, f"{cls.__name__}: None -> non-empty"
            assert cls.to_modifiers(object()) == {}, f"{cls.__name__}: non-None -> non-empty"


def test_s1_layer_off_restores_originals():
    """After CM: original staticmethod objects restored by identity (cls.__dict__)."""
    originals = {cls: cls.__dict__["to_modifiers"] for cls in _PRODUCERS}
    with s1_layer_off():
        pass
    for cls, orig in originals.items():
        assert cls.__dict__["to_modifiers"] is orig, (
            f"{cls.__name__}: original staticmethod not restored by identity"
        )


def test_s1_layer_off_restores_on_exception():
    """Restore even if CM body raises."""
    originals = {cls: cls.__dict__["to_modifiers"] for cls in _PRODUCERS}
    with pytest.raises(RuntimeError):
        with s1_layer_off():
            raise RuntimeError("boom")
    for cls, orig in originals.items():
        assert cls.__dict__["to_modifiers"] is orig


def test_s1_probe_captures_causal_modifiers():
    """Probe records causal_modifiers exactly as passed (None / dict / absent)."""
    scores = {"attack": 1.0, "flee": 0.5, "idle": 0.0}
    with s1_probe_apply_modifiers() as captured:
        DecisionHub.apply_modifiers(scores, causal_modifiers=None)
        DecisionHub.apply_modifiers(scores, causal_modifiers={"attack": 0.5})
        DecisionHub.apply_modifiers(scores)  # causal_modifiers kwarg absent
    assert captured == [None, {"attack": 0.5}, None], f"got: {captured}"


def test_s1_probe_restores_on_exception():
    """Probe restores original staticmethod on exception."""
    original = DecisionHub.__dict__["apply_modifiers"]
    with pytest.raises(RuntimeError):
        with s1_probe_apply_modifiers():
            raise RuntimeError("boom")
    assert DecisionHub.__dict__["apply_modifiers"] is original


def test_s1_layer_off_result_is_falsy_dict():
    """Contract sanity: producer returns {} (falsy), matches caller `or None` -> None."""
    with s1_layer_off():
        for cls in _PRODUCERS:
            result = cls.to_modifiers(object())
            assert isinstance(result, dict)
            assert result == {}
            assert not result