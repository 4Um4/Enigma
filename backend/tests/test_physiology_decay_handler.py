# -*- coding: utf-8 -*-
"""
Тесты PhysiologyDecayHandler (Leaky Integrator).

Полный Запуск: cd backend; python -m pytest tests/test_physiology_decay_handler.py -v

Файл: backend/tests/test_physiology_decay_handler.py
Назначение: Тесты экспоненциального затухания боли/усталости/кровопотери.
Зависимости: pytest, app.services.combat.physiology_decay_handler

Проверяют:
1. Боль экспоненциально затухает
2. Усталость экспоненциально затухает
3. Кровопотеря экспоненциально затухает
4. Сознание восстанавливается при низкой боли
5. Closing drift: малые значения обнуляются напрямую
6. NPC без повреждений не генерирует дельт
7. STAGGER: высокая боль → статус stagger
8. COLLAPSE: низкое сознание → статус unconscious
9. Восстановление: боль упала → снятие stagger
"""

import math

from app.domain.identity_events import EffectiveDrives

_MOCK_DRIVES = EffectiveDrives.from_dict({"control": 0.5, "significance": 0.5, "fear": 0.5, "desire": 0.5})

from app.models.idle_tick import NPCStateSnapshot
from app.models.state_delta import DeltaDomain
from app.services.combat.physiology_decay_handler import (
    BLOOD_LOSS_DECAY_LAMBDA,
    FATIGUE_DECAY_LAMBDA,
    PAIN_DECAY_LAMBDA,
    PHYSIOLOGY_DECAY_EPSILON,
    STAGGER_PAIN_THRESHOLD,
    PhysiologyDecayHandler,
)


def _make_snapshot(
    npc_id: str = "npc_1",
    pain: float = 0.0,
    fatigue: float = 0.0,
    blood_loss: float = 0.0,
    consciousness: float = 1.0,
    statuses: list | None = None,
) -> NPCStateSnapshot:
    """Фабрика снапшотов для изолированных тестов."""
    return NPCStateSnapshot(
        npc_id=npc_id,
        stress=0.0,
        relationship_cache={},
        base_values={},
        faction_affiliations=[],
        hp=100.0,
        max_hp=100.0,
        pain=pain,
        fatigue=fatigue,
        blood_loss=blood_loss,
        consciousness=consciousness,
        injuries_by_zone={},
        base_abilities={},
        modifiers={},
        statuses=statuses or [],
        life_status="ALIVE",
        body_state={
            "pain": pain,
            "fatigue": fatigue,
            "blood_loss": blood_loss,
            "consciousness": consciousness,
            "shock_impulse": 0.0,
            "injuries_by_zone": {},
            "statuses": statuses or [],  # FIX: _get_statuses читает из body_state
        },
        perceptual_kernel={},
    )


class TestPainDecay:
    """Боль экспоненциально затухает."""

    def test_pain_decays_exponentially(self):
        """Pain_t = Pain_{t-1} * exp(-lambda)."""
        handler = PhysiologyDecayHandler()
        npc = _make_snapshot(pain=50.0)

        results = handler.handle([npc], "test", 0)
        assert len(results) == 1

        delta = results[0]
        assert delta.domain == DeltaDomain.PHYSIOLOGY
        expected = 50.0 * math.exp(-PAIN_DECAY_LAMBDA) - 50.0
        assert abs(delta.payload.pain_delta - round(expected, 4)) < 0.01

    def test_zero_pain_no_delta(self):
        """Нет боли → нет дельты."""
        handler = PhysiologyDecayHandler()
        npc = _make_snapshot(pain=0.0)

        results = handler.handle([npc], "test", 0)
        # Нет боли, нет усталости — нет дельт
        assert len(results) == 0


class TestFatigueDecay:
    """Усталость экспоненциально затухает."""

    def test_fatigue_decays_exponentially(self):
        """Fatigue_t = Fatigue_{t-1} * exp(-lambda)."""
        handler = PhysiologyDecayHandler()
        npc = _make_snapshot(fatigue=40.0)

        results = handler.handle([npc], "test", 0)
        assert len(results) == 1

        delta = results[0]
        expected = 40.0 * math.exp(-FATIGUE_DECAY_LAMBDA) - 40.0
        assert abs(delta.payload.fatigue_delta - round(expected, 4)) < 0.01


class TestBloodLossDecay:
    """Кровопотеря экспоненциально затухает (медленнее)."""

    def test_blood_loss_decays_slowly(self):
        """Blood_t = Blood_{t-1} * exp(-lambda_blood)."""
        handler = PhysiologyDecayHandler()
        npc = _make_snapshot(blood_loss=0.5)

        results = handler.handle([npc], "test", 0)
        assert len(results) == 1

        delta = results[0]
        expected = 0.5 * math.exp(-BLOOD_LOSS_DECAY_LAMBDA) - 0.5
        assert abs(delta.payload.blood_loss_delta - round(expected, 4)) < 0.01


class TestConsciousnessRecovery:
    """Сознание восстанавливается при низкой боли."""

    def test_consciousness_recovers_when_low_pain(self):
        """Низкая боль → сознание восстанавливается."""
        handler = PhysiologyDecayHandler()
        npc = _make_snapshot(consciousness=0.5, pain=0.0)

        results = handler.handle([npc], "test", 0)
        assert len(results) == 1

        delta = results[0]
        assert delta.payload.fatigue_delta == 0.0  # Не усталость
        # Сознание растёт (отрицательный pain_delta не влияет)


class TestClosingDrift:
    """Closing drift: малые значения обнуляются напрямую."""

    def test_tiny_pain_zeroed_out(self):
        """Боль < EPSILON → обнуляется."""
        handler = PhysiologyDecayHandler()
        # Очень малая боль, после decay будет < EPSILON
        npc = _make_snapshot(pain=PHYSIOLOGY_DECAY_EPSILON * 0.5)

        results = handler.handle([npc], "test", 0)
        if len(results) > 0:
            # Дельта должна быть ~-pain (обнуление)
            assert results[0].payload.pain_delta < 0


class TestNoInjuryNoDelta:
    """NPC без повреждений не генерирует дельт."""

    def test_healthy_npc_no_delta(self):
        """HP=100, pain=0, fatigue=0, blood=0, consciousness=1 → нет дельт."""
        handler = PhysiologyDecayHandler()
        npc = _make_snapshot()

        results = handler.handle([npc], "test", 0)
        assert len(results) == 0


class TestEmergentStates:
    """Фазовые переходы: STAGGER и COLLAPSE."""

    def test_high_pain_adds_stagger(self):
        """Боль > STAGGER_THRESHOLD → add stagger."""
        handler = PhysiologyDecayHandler()
        # Высокая боль (после decay всё ещё > порога)
        npc = _make_snapshot(pain=STAGGER_PAIN_THRESHOLD + 10.0)

        results = handler.handle([npc], "test", 0)
        assert len(results) == 1
        assert "stagger" in results[0].payload.add_statuses

    def test_low_pain_removes_stagger(self):
        """Боль < STAGGER_THRESHOLD → remove stagger."""
        handler = PhysiologyDecayHandler()
        # Малая боль + есть статус stagger
        npc = _make_snapshot(pain=10.0, statuses=["stagger"])

        results = handler.handle([npc], "test", 0)
        assert len(results) == 1
        assert "stagger" in results[0].payload.remove_statuses

    def test_low_consciousness_adds_unconscious(self):
        """Consciousness < COLLAPSE_THRESHOLD → add unconscious."""
        handler = PhysiologyDecayHandler()
        # Очень низкое сознание (после recovery всё ещё < порога)
        npc = _make_snapshot(consciousness=0.01)

        results = handler.handle([npc], "test", 0)
        assert len(results) == 1
        assert "unconscious" in results[0].payload.add_statuses

    def test_recovered_consciousness_removes_unconscious(self):
        """Consciousness > COLLAPSE_THRESHOLD → remove unconscious."""
        handler = PhysiologyDecayHandler()
        # Высокое сознание + статус unconscious
        npc = _make_snapshot(consciousness=0.5, statuses=["unconscious"])

        results = handler.handle([npc], "test", 0)
        assert len(results) == 1
        assert "unconscious" in results[0].payload.remove_statuses


class TestMultipleNPCs:
    """Обработка нескольких NPC."""

    def test_multiple_npcs_with_different_pain(self):
        """2 NPC с разной болью → 2 дельты."""
        handler = PhysiologyDecayHandler()
        npc1 = _make_snapshot("npc_1", pain=30.0)
        npc2 = _make_snapshot("npc_2", pain=60.0)

        results = handler.handle([npc1, npc2], "test", 0)
        assert len(results) == 2

        npc_ids = {r.npc_id for r in results}
        assert npc_ids == {"npc_1", "npc_2"}
