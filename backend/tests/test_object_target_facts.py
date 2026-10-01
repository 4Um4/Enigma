# path: /project/backend/tests/test_object_target_facts.py
# Назначение: G3 Этап 2 (ADR-O-410 §6) — детерминированный целевой
#     резолвер воли: compute_object_target_facts (pure). nearest Euclidean
#     + лексикографический object_id tie-break; только carrier FREE;
#     TARGETABLE_ARCHETYPES — calibration policy (v1: chair→TAKE).
# Зависимости: pytest, app.services.world.object_target_facts
# Основные сущности: compute_object_target_facts, TARGETABLE_ARCHETYPES
# Запуск: cd backend; python -m pytest tests/test_object_target_facts.py -v -s; cd ..
from typing import Any, Dict

from app.services.world.object_target_facts import (
    TARGETABLE_ARCHETYPES,
    compute_object_target_facts,
)


class _Snap:
    """Минимальный замороженный снапшот (паттерн affordance_facts-тестов)."""

    def __init__(self, objects: Dict[str, Any], npcs: Dict[str, Any]) -> None:
        self.world_objects = objects
        self.npc_positions = npcs


def _wo(oid: str, arch: str, x: float, y: float) -> Dict[str, Any]:
    return {
        "object_id": oid, "archetype": arch, "location_id": "tavern",
        "position": [x, y], "state": "AVAILABLE", "carrier_mode": "FREE",
        "damage": 0.0, "holder": None, "container_id": None,
        "supported_by": None, "attachment": None, "occupancy": None,
        "used_by": None, "ownership": None, "interaction_history_ref": None,
    }


def _npc(x: float, y: float) -> Dict[str, Any]:
    return {"local_position": {"x": x, "y": y}}


class TestDeterministicSelection:
    def test_nearest_object_selected(self):
        snap = _Snap(
            {"chair_far": _wo("chair_far", "chair", 20.0, 20.0),
             "chair_near": _wo("chair_near", "chair", 8.3, 12.9)},
            {"thief_shadow": _npc(8.1, 13.0)},
        )
        facts = compute_object_target_facts(snap, ("thief_shadow",), "tavern")
        assert facts == {"thief_shadow": "chair_near"}

    def test_lexicographic_tie_break(self):
        snap = _Snap(
            {"chair_b": _wo("chair_b", "chair", 8.4, 13.1),
             "chair_a": _wo("chair_a", "chair", 8.4, 13.1)},
            {"thief_shadow": _npc(8.1, 13.0)},
        )
        facts = compute_object_target_facts(snap, ("thief_shadow",), "tavern")
        assert facts == {"thief_shadow": "chair_a"}

    def test_policy_table_v1_chair_only(self):
        assert dict(TARGETABLE_ARCHETYPES) == {"chair": "TAKE"}


class TestSemantics:
    def test_non_free_carrier_excluded(self):
        snap = _Snap(
            {"chair_held": _wo("chair_held", "chair", 8.3, 12.9)},
            {"thief_shadow": _npc(8.1, 13.0)},
        )
        snap.world_objects["chair_held"]["carrier_mode"] = "HELD"
        snap.world_objects["chair_held"]["holder"] = "someone"
        facts = compute_object_target_facts(snap, ("thief_shadow",), "tavern")
        assert facts == {}

    def test_wrong_archetype_excluded(self):
        snap = _Snap(
            {"cup_1": _wo("cup_1", "cup", 8.3, 12.9)},
            {"thief_shadow": _npc(8.1, 13.0)},
        )
        facts = compute_object_target_facts(snap, ("thief_shadow",), "tavern")
        assert facts == {}

    def test_other_location_excluded(self):
        snap = _Snap(
            {"chair_1": _wo("chair_1", "chair", 8.3, 12.9)},
            {"thief_shadow": _npc(8.1, 13.0)},
        )
        snap.world_objects["chair_1"]["location_id"] = "cellar"
        facts = compute_object_target_facts(snap, ("thief_shadow",), "tavern")
        assert facts == {}

    def test_empty_world_honest_zero(self):
        snap = _Snap({}, {"thief_shadow": _npc(8.1, 13.0)})
        assert compute_object_target_facts(snap, ("thief_shadow",), "tavern") == {}