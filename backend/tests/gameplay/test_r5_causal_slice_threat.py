# path: /project/backend/tests/gameplay/test_r5_causal_slice_threat.py
"""
Файл: backend/tests/gameplay/test_r5_causal_slice_threat.py
Назначение: R5 — первый CAUSAL SLICE: NPC имеет причинно определённое
    DesiredChange (B.stop_hostile) ДО выбора способа; способ выбирается
    оценкой (value × chance × cost × legitimacy × personality) и
    деформирует utility СУЩЕСТВУЮЩИХ интентов (Modifier Contract).
    Законы CS1-CS6 мини-АДРа среза.
Зависимости: app.domain.desired_change, app.services.npc.causal_slice_threat,
    tests.gameplay.harness
Основные сущности: ThreatDesiredChangeProducer, DesiredChange
Запуск: cd backend && python -m pytest tests/gameplay/test_r5_causal_slice_threat.py -v
"""

from unittest.mock import MagicMock

import pytest

from app.domain.desired_change import DesiredChange, stop_hostile
from app.services.npc.causal_slice_threat import (
    ThreatDesiredChangeProducer,
)


def _kernel(threat: float):
    k = MagicMock()
    k.threat_gradient = threat
    return k


def _state(npc_id="maid_lusya", threat=0.6, drives=None, hp=1.0, archetype="maid"):
    s = MagicMock()
    s.npc_id = npc_id
    s.perceptual_kernel = _kernel(threat)
    s.effective_hp = 100.0 * hp
    s.stress = 20.0
    d = {"fear": 0.6, "control": 0.2, "significance": 0.2, "desire": 0.1}
    d.update(drives or {})
    s.drives = d  # drives-подобный словарь (producer читает по ключам)
    return s


class TestProducer:
    def test_t1_no_threat_no_desired_change(self):
        """T1 (ПИН, CS1-гейт): threat ниже порога → производитель
        молчит — срез аддитивен, мир без угроз не меняется."""
        dc = ThreatDesiredChangeProducer.resolve(
            _state(threat=0.1), rel={}, disposition={}, allies=0
        )
        assert dc is None

    def test_t2_threat_without_attribution_no_change(self):
        """T2 (ПИН): угроза есть, атрибуции нет (нет fear-пары, нет
        belief) → None: причина без «кого менять» не рождает цель."""
        dc = ThreatDesiredChangeProducer.resolve(
            _state(threat=0.8), rel={}, disposition={}, allies=0
        )
        assert dc is None

    def test_t3_desired_change_contract(self):
        """T3 (CS3): форма R4 — reason/state_type/target_of_change/
        addressee различены; desired_change существует ДО способа."""
        dc = ThreatDesiredChangeProducer.resolve(
            _state(), rel={"guard_borko": {"fear": 65.0, "trust": 10.0}},
            disposition={"warn": 0.3, "intimidate": 0.1}, allies=0,
        )
        assert dc is not None
        assert dc.reason == "threat"
        assert dc.state_type == "behavior"
        assert dc.target_of_change == "guard_borko"
        assert dc.addressee == "guard_borko"
        assert "flee" in dc.method_weights or dc.method_weights

    def test_t4_attribution_from_belief(self):
        """T4: второй источник атрибуции — belief (Proposition
        ATTACKED, object_id) живёт в epistemic-контуре."""
        prop = MagicMock()
        prop.subject_id = "guard_borko"
        prop.predicate.value = "ATTACKED"
        dc = ThreatDesiredChangeProducer.resolve(
            _state(), rel={}, disposition={}, allies=0, belief_source=prop,
        )
        assert dc is not None and dc.target_of_change == "guard_borko"

    def test_t5_weak_isolated_flee_dominant(self):
        """T5 (ЯДРО-ЭКСПЕРИМЕНТ): слабый, раненый, один, страшащийся
        → FLEE-вес доминирует над конфронтационными."""
        dc = ThreatDesiredChangeProducer.resolve(
            _state(threat=0.9, drives={"fear": 0.9, "control": 0.05}, hp=0.3),
            rel={"guard_borko": {"fear": 80.0, "trust": -20.0}},
            disposition={"intimidate": 0.0}, allies=0,
        )
        assert dc.method_weights["flee"] > dc.method_weights.get("intimidate", 0.0)
        assert dc.method_weights["flee"] > dc.method_weights.get("attack", 0.0)

    def test_t6_guard_with_allies_calls_help(self):
        """T6 (ЯДРО): та же цель, другой профиль — стражник с
        союзниками и легитимностью → CALL_FOR_HELP/INTIMIDATE
        доминирует над FLEE. Один DesiredChange → разные способы."""
        dc = ThreatDesiredChangeProducer.resolve(
            _state(npc_id="ally_guard", drives={"fear": 0.3, "control": 0.6,
                                                "significance": 0.7}, hp=1.0),
            rel={"guard_borko": {"fear": 40.0, "trust": -30.0}},
            disposition={"intimidate": 1.4, "warn": 0.5}, allies=2,
        )
        assert dc.method_weights["call_for_help"] > dc.method_weights["flee"]
        assert dc.method_weights["intimidate"] > dc.method_weights["flee"]

    def test_t7_pure_function_determinism(self):
        """T7 (A/A): одинаковые входы → байт-идентичный результат."""
        args = dict(
            state=_state(), rel={"guard_borko": {"fear": 65.0}},
            disposition={"warn": 0.5}, allies=1,
        )
        a = ThreatDesiredChangeProducer.resolve(**args)
        b = ThreatDesiredChangeProducer.resolve(**args)
        assert a is not None and b is not None
        assert a.method_weights == b.method_weights
        assert a == b  # frozen dataclass

    def test_t8_modifiers_contract(self):
        """T8 (CS2): to_modifiers — чистые числа по Modifier Contract;
        None → пустой dict (no-op для DecisionHub)."""
        dc = ThreatDesiredChangeProducer.resolve(
            _state(), rel={"guard_borko": {"fear": 65.0}}, disposition={}, allies=0,
        )
        mods = ThreatDesiredChangeProducer.to_modifiers(dc)
        assert isinstance(mods, dict)
        assert all(isinstance(v, float) for v in mods.values())
        assert ThreatDesiredChangeProducer.to_modifiers(None) == {}