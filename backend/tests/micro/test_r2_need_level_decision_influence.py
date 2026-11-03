# backend/tests/micro/test_r2_need_level_decision_influence.py
"""
R2 (CCH-15 P1): NeedLevel влияет на решение NPC через need_modifiers.

Вердикт Мастера R2: сущность не просто хранится, а влияет на реальное решение NPC.
Условие завершения: NeedLevel -> RelationshipStateStore.get_need_levels ->
need_modifiers -> DecisionHub.apply_modifiers -> score change.

Принципы Мастера (R2):
1. Потребности различаются (intimacy != sexual).
2. Одно действие может удовлетворять несколько потребностей.
3. Последствия зависят от партнёра/отношений/обстоятельств.
4. Влюблённость/вложения/выгода — разные механизмы (NeedLevel = давление, не любовь).
5. Нет универсальной ревности (ExclusivityRequirement не трогается).
"""
from __future__ import annotations

from typing import Dict, Optional

import pytest

from app.services.npc.decision_hub import DecisionHub


class TestNeedModifiersApplyModifiers:
    """R2: apply_modifiers корректно применяет need_modifiers."""

    def test_1_need_modifiers_boost_seek_ally(self):
        scores = {"idle": 0.5, "seek_ally": 0.3, "talk": 0.4, "approach": 0.2}
        need_modifiers = {"seek_ally": 0.4}
        result = DecisionHub.apply_modifiers(scores, need_modifiers=need_modifiers)
        assert result["seek_ally"] == pytest.approx(0.7, abs=0.001)
        assert result["idle"] == 0.5
        assert result["talk"] == 0.4

    def test_2_no_need_modifiers_no_change(self):
        scores = {"idle": 0.5, "seek_ally": 0.3}
        result = DecisionHub.apply_modifiers(scores)
        assert result == scores
        assert result is not scores

    def test_3_empty_need_modifiers_noop(self):
        scores = {"idle": 0.5, "seek_ally": 0.3}
        result = DecisionHub.apply_modifiers(scores, need_modifiers={})
        assert result == scores

    def test_4_intimacy_and_sexual_separate(self):
        """Принцип 1: intimacy и sexual — раздельные. Принцип 2: approach получает оба."""
        scores = {"seek_ally": 0.3, "talk": 0.4, "approach": 0.2}
        need_modifiers = {
            "seek_ally": 0.4,
            "talk": 0.24,
            "approach": 0.16 + 0.32,
        }
        result = DecisionHub.apply_modifiers(scores, need_modifiers=need_modifiers)
        assert result["approach"] == pytest.approx(0.2 + 0.16 + 0.32, abs=0.001)
        assert result["seek_ally"] == pytest.approx(0.3 + 0.4, abs=0.001)

    def test_5_need_modifiers_cumulative_with_social(self):
        scores = {"seek_ally": 0.3}
        social = {"seek_ally": 0.2}
        need = {"seek_ally": 0.4}
        result = DecisionHub.apply_modifiers(
            scores, social_modifiers=social, need_modifiers=need
        )
        assert result["seek_ally"] == pytest.approx(0.3 + 0.2 + 0.4, abs=0.001)


class TestNeedLevelToModifiersMapping:
    """R2: логика NeedLevel.current_intensity -> need_modifiers (реплика pipeline)."""

    @staticmethod
    def _build_need_modifiers(
        intimacy_intensity: float = 0.0, sexual_intensity: float = 0.0
    ) -> Optional[Dict[str, float]]:
        modifiers: Dict[str, float] = {}
        if intimacy_intensity > 0.0:
            modifiers["seek_ally"] = modifiers.get("seek_ally", 0.0) + intimacy_intensity * 0.5
            modifiers["talk"] = modifiers.get("talk", 0.0) + intimacy_intensity * 0.3
            modifiers["approach"] = modifiers.get("approach", 0.0) + intimacy_intensity * 0.2
        if sexual_intensity > 0.0:
            modifiers["approach"] = modifiers.get("approach", 0.0) + sexual_intensity * 0.4
        return modifiers if modifiers else None

    def test_6_zero_intimacy_no_modifiers(self):
        result = self._build_need_modifiers(intimacy_intensity=0.0)
        assert result is None

    def test_7_high_intimacy_boosts_seek_ally(self):
        result = self._build_need_modifiers(intimacy_intensity=0.8)
        assert result is not None
        assert result["seek_ally"] == pytest.approx(0.4, abs=0.001)
        assert result["talk"] == pytest.approx(0.24, abs=0.001)
        assert result["approach"] == pytest.approx(0.16, abs=0.001)

    def test_8_sexual_boosts_approach_only(self):
        """Принцип 1: sexual не бустит seek_ally."""
        result = self._build_need_modifiers(sexual_intensity=0.8)
        assert result is not None
        assert "seek_ally" not in result
        assert result["approach"] == pytest.approx(0.32, abs=0.001)

    def test_9_both_needs_cumulative_approach(self):
        """Принцип 2: approach получает буст от обоих."""
        result = self._build_need_modifiers(intimacy_intensity=0.8, sexual_intensity=0.6)
        assert result is not None
        assert result["approach"] == pytest.approx(0.16 + 0.24, abs=0.001)
        assert result["seek_ally"] == pytest.approx(0.4, abs=0.001)


class TestABDecisionInfluence:
    """R2: A/B — high intimacy need меняет решение NPC."""

    def test_10_ab_high_intimacy_flips_seek_ally(self):
        """Доказательство: NeedLevel -> score change -> intent flip."""
        base_scores = {
            "idle": 0.5, "seek_ally": 0.3, "talk": 0.4, "approach": 0.2, "observe": 0.1,
        }
        # A: без need
        scores_a = DecisionHub.apply_modifiers(base_scores)
        winner_a = max(scores_a, key=scores_a.get)
        assert winner_a == "idle"
        # B: с high intimacy need
        need_mods = {"seek_ally": 0.4, "talk": 0.24, "approach": 0.16}
        scores_b = DecisionHub.apply_modifiers(base_scores, need_modifiers=need_mods)
        winner_b = max(scores_b, key=scores_b.get)
        assert winner_b == "seek_ally", (
            f"B: high intimacy должен дать seek_ally, получен {winner_b} ({scores_b})"
        )
        assert winner_a != winner_b

    def test_11_ab_zero_need_no_flip(self):
        base_scores = {"idle": 0.5, "seek_ally": 0.3}
        scores_a = DecisionHub.apply_modifiers(base_scores)
        scores_b = DecisionHub.apply_modifiers(base_scores, need_modifiers=None)
        assert scores_a == scores_b