"""E0-PILOT-10: Regression test — redirect must NOT be double-counted in score."""
import pytest
from app.services.npc.decision_hub import DecisionHub
try:
    from app.models.npc_state import Intent, EmotionTag
except ImportError:
    from app.models.schemas import Intent, EmotionTag


class TestRedirectNotDoubleCounted:
    def test_emotion_returns_field_mod_only_negative_redirect(self):
        dh = DecisionHub()
        drives = {"fear": 0.45, "control": 0.25, "significance": 0.2, "desire": 0.2}
        result = dh._emotion_modifier(
            intent=Intent.TALK.value, emotion=EmotionTag.ANGRY,
            drives=drives, affective_load=0.5,
        )
        assert result == pytest.approx(0.0, abs=0.001), f"Expected 0.0, got {result}"

    def test_last_redirect_still_set_negative(self):
        dh = DecisionHub()
        drives = {"fear": 0.45, "control": 0.25, "significance": 0.2, "desire": 0.2}
        dh._emotion_modifier(
            intent=Intent.TALK.value, emotion=EmotionTag.ANGRY,
            drives=drives, affective_load=0.5,
        )
        assert dh._last_redirect == pytest.approx(-0.02, abs=0.005)

    def test_emotion_returns_field_mod_only_positive_redirect(self):
        dh = DecisionHub()
        drives = {"fear": 0.05, "control": 0.6, "significance": 0.25, "desire": 0.25}
        result = dh._emotion_modifier(
            intent=Intent.ATTACK.value, emotion=EmotionTag.ANGRY,
            drives=drives, affective_load=0.5,
        )
        assert result == pytest.approx(0.1425, abs=0.01), f"Expected ~0.1425, got {result}"

    def test_last_redirect_still_set_positive(self):
        dh = DecisionHub()
        drives = {"fear": 0.05, "control": 0.6, "significance": 0.25, "desire": 0.25}
        dh._emotion_modifier(
            intent=Intent.ATTACK.value, emotion=EmotionTag.ANGRY,
            drives=drives, affective_load=0.5,
        )
        assert dh._last_redirect > 0

    def test_redirect_not_equal_to_emotion_when_nonzero(self):
        dh = DecisionHub()
        drives = {"fear": 0.05, "control": 0.6, "significance": 0.25, "desire": 0.25}
        emotion_mod = dh._emotion_modifier(
            intent=Intent.ATTACK.value, emotion=EmotionTag.ANGRY,
            drives=drives, affective_load=0.5,
        )
        assert emotion_mod != pytest.approx(dh._last_redirect, abs=0.001)

    def test_low_energy_no_crash(self):
        dh = DecisionHub()
        drives = {"fear": 0.45, "control": 0.25, "significance": 0.2, "desire": 0.2}
        result = dh._emotion_modifier(
            intent=Intent.TALK.value, emotion=EmotionTag.ANGRY,
            drives=drives, affective_load=0.005,
        )
        assert result == pytest.approx(0.0, abs=0.001)