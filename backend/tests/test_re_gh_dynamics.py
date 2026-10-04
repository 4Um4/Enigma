# path: backend/tests/test_re_gh_dynamics.py
# Назначение: микротесты G/H (ADR-O-419): Ф1/Ф3/Ф4/С5 + time-driven контур.
# Зависимости: app.services.social.relationship_dynamics, app.domain.relationship_contracts
# Основные сущности: TestSatisfactionFormula, TestReliefFormula, TestTimeDriven

from app.domain.relationship_contracts import NeedLevel
from app.services.social.relationship_dynamics import (
    compute_time_driven_deltas,
    relief_of,
    satisfaction_of,
    total_satisfaction,
)


class TestSatisfactionFormula:
    def test_at_and_below_target_full(self) -> None:
        assert satisfaction_of(0.3, 0.3) == 1.0
        assert satisfaction_of(0.1, 0.3) == 1.0  # без пересыщения (Ф1)

    def test_piecewise_linear(self) -> None:
        # p=0.6, target=0.3 → 1 - 0.3/0.7
        assert abs(satisfaction_of(0.6, 0.3) - (1.0 - 0.3 / 0.7)) < 1e-9

    def test_target_one_always_full(self) -> None:
        assert satisfaction_of(1.0, 1.0) == 1.0


class TestReliefFormula:
    def test_ceiling_at_current_pressure(self) -> None:
        # Потолок: не снять больше накопленного (Ф3, Δp = −min(relief, p))
        assert relief_of(10.0, 1.0, 0.3, 0.2) == 0.2

    def test_quality_and_substitutability(self) -> None:
        # Свой источник: S = 1 — substitutability НЕ применяется (Ф3)
        assert relief_of(0.5, 0.5, 0.2, 1.0) == 0.5 * 0.5
        # Чужой источник: × substitutability слота
        assert relief_of(0.5, 0.5, 0.2, 1.0, own_source=False) == 0.5 * 0.5 * 0.2
        # Полностью незаместимая (S=0) → relief = 0
        assert relief_of(0.5, 1.0, 0.0, 1.0, own_source=False) == 0.0


class TestTotalSatisfaction:
    def test_full_when_all_satisfied(self) -> None:
        levels = {nid: NeedLevel(need_id=nid) for nid in ("sexual", "intimacy")}
        assert total_satisfaction(levels) == 1.0

    def test_empty_levels_is_placeholder_default(self) -> None:
        assert total_satisfaction({}) == 1.0  # NeedLevel-дефолты p=0 ≤ target


class TestTimeDriven:
    def _scene(self, p: float, f: float) -> dict:
        # Структура по контракту стора (E2); приватные носители легальны в тестах (I.4)
        return {
            "relationship_state": {
                "needs": {
                    "npc1": {
                        "sexual": {"need_id": "sexual", "current_intensity": p,
                                   "satiation": 0.0, "frustration": f},
                    }
                }
            }
        }

    def test_below_quantum_noop(self) -> None:
        scene = self._scene(0.0, 0.0)
        assert compute_time_driven_deltas(scene, ("npc1",), 1800.0, 1) == []
        assert scene["relationship_state"].get("dynamics") is None  # книга не создаётся

    def test_pressure_grows_one_quantum(self) -> None:
        scene = self._scene(0.0, 0.0)
        deltas = compute_time_driven_deltas(scene, ("npc1",), 3600.0, 1)
        d = next(x for x in deltas if x.npc_id == "npc1" and x.payload.need_id == "sexual")
        assert abs(d.payload.pressure_delta - (0.1 / 24.0)) < 1e-6
        assert scene["relationship_state"]["dynamics"]["last_quantum_seconds"] == 3600.0

    def test_bg_frustration_requires_pressure_above_threshold(self) -> None:
        # rigidity=0.5 → порог 0.5: p=0.6 > порог → фон > 0
        scene = self._scene(0.6, 0.0)
        deltas = compute_time_driven_deltas(scene, ("npc1",), 86400.0, 1)
        d = next(x for x in deltas if x.payload.need_id == "sexual")
        assert d.payload.frustration_delta > 0.0

    def test_deterministic_cause_uuid5(self) -> None:
        s1, s2 = self._scene(0.0, 0.0), self._scene(0.0, 0.0)
        d1 = compute_time_driven_deltas(s1, ("npc1",), 3600.0, 7)
        d2 = compute_time_driven_deltas(s2, ("npc1",), 3600.0, 7)
        assert [x.payload.source_event_id for x in d1] == [x.payload.source_event_id for x in d2]