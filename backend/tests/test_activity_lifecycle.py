"""
Конвертер деятельностей (Фаза 0.7): no-op при OFF, onset с причиной,
G3-ревалидация TAKE, терминал потребления (damage+release+сброс needs),
таймаут-фейл, reconcile владения (monkeypatch флагов реестра — import-time).

Запуск: cd backend; python -m pytest tests/test_activity_lifecycle.py -v; cd ..
"""
import os
import unittest
from types import SimpleNamespace
from unittest import mock

from app.domain.activity import ActivityState, ActivityStep, ActivityType, StepKind
from app.domain.world_object import ObjectRelationKind
from app.services.action import commitment_registry as cr_mod
from app.services.npc import activity_lifecycle_service as als
from app.services.world.world_object_store import WorldObjectStore

_FOOD_ID = "wo_test_food_001"
_FOOD_POS = (4.2, 5.4)


class _SpatialStub:
    def resolve_node(self, role, origin_xy=None, origin_zone=None, filters=None):
        return SimpleNamespace(zone_id="tavern", node_id="bar_area")


class _OrchStub:
    def _get_event_bus(self):
        return None

    def _resolve_spatial_service(self, ctx):
        return _SpatialStub()


def _scene_with_food():
    scene = {"location_id": "tavern"}
    WorldObjectStore.spawn(scene, _FOOD_ID, "food_portion", "tavern", _FOOD_POS)
    return scene


def _npc(**over):
    npc = {
        "npc_id": "npc_hungry",
        "needs": {"hunger": 0.9},
        "desires": [
            {
                "desire_id": "d:food", "subject_class": "food",
                "urgency": 0.9, "target_class": "food_portion",
                "provenance": [{"source": "need", "weight": 1.0, "origin_ref": "hunger"}],
                "born_tick": 1, "last_fulfilled_tick": -1,
                "weight": 1.0, "learned_from": [],
            }
        ],
        "local_position": {"x": 4.5, "y": 6.5},
        "position": "bar_area",
        "location_id": "tavern",
        # consciousness — FLOAT 0..1 (vital_state.py:164: float(...));
        # строка ломает ось и валит build_body_state_view
        "body_state": {
            "life_status": "ALIVE", "current_hp": 100, "pain": 0,
            "fatigue": 0, "blood_loss": 0.0, "consciousness": 1.0,
            "shock_impulse": 0.0, "injuries": {},
        },
    }
    npc.update(over)
    return npc


def _ctx(scene, npcs, tick=100):
    return SimpleNamespace(
        scene_state=scene, all_npcs_raw=npcs, tick_number=tick,
        campaign_id="test", tick_snapshot=None,
    )


def _activity_dict(npc_id, step_index, started, step_started, target=_FOOD_ID):
    steps = (
        ActivityStep(step_kind=StepKind.MOVE, target_ref="bar_area"),
        ActivityStep(step_kind=StepKind.OBJECT_ACTION, action_type="TAKE", target_ref=target),
        ActivityStep(step_kind=StepKind.BODY_ACTION, action_type="CONSUME", target_ref=target, duration_ticks=3),
    )
    return ActivityState(
        activity_id=ActivityState.build_id(npc_id, ActivityType.EAT, started),
        activity_type=ActivityType.EAT, desire_id="d:food", target_ref=target,
        steps=steps, step_index=step_index, step_started_tick=step_started,
        started_tick=started,
    ).to_dict()


class TestActivityLifecycle(unittest.TestCase):
    def setUp(self):
        self._old = os.environ.pop("ACTIVITY_LIFECYCLE_ENABLED", None)
        os.environ["ACTIVITY_LIFECYCLE_ENABLED"] = "1"

    def tearDown(self):
        os.environ.pop("ACTIVITY_LIFECYCLE_ENABLED", None)
        if self._old is not None:
            os.environ["ACTIVITY_LIFECYCLE_ENABLED"] = self._old

    def test_off_is_byte_identical_noop(self):
        os.environ["ACTIVITY_LIFECYCLE_ENABLED"] = ""
        npc = _npc()
        goals = als.run_activity_lifecycle(_ctx(_scene_with_food(), [npc]), _OrchStub())
        self.assertEqual(goals, [])
        self.assertNotIn("activity_state", npc)

    def test_onset_born_with_cause_and_emits_goal(self):
        # ACTIVITY_ONSET_FACT: рождение = желание+адрес, не ярлык
        scene = _scene_with_food()
        npc = _npc()
        goals = als.run_activity_lifecycle(_ctx(scene, [npc]), _OrchStub())
        self.assertEqual(len(goals), 1)
        self.assertEqual(goals[0].target_node_id, "bar_area")
        self.assertIn("activity:eat:d:food", str(goals[0].reason))
        st = npc["activity_state"]
        self.assertEqual(st["desire_id"], "d:food")
        self.assertEqual(st["target_ref"], _FOOD_ID)
        self.assertEqual(st["steps"][0]["target_ref"], "bar_area")

    def test_onset_without_food_keeps_desire_pressing(self):
        scene = {"location_id": "tavern"}  # еда не спавнена
        npc = _npc()
        goals = als.run_activity_lifecycle(_ctx(scene, [npc]), _OrchStub())
        self.assertEqual(goals, [])
        self.assertNotIn("activity_state", npc)
        self.assertEqual(npc["desires"][0]["urgency"], 0.9)  # давление живо

    def test_take_step_establishes_held_by(self):
        # G3: ревалидация W2 прошла → типизированная мутация стора
        scene = _scene_with_food()
        npc = _npc(
            local_position={"x": 4.3, "y": 5.4},
            activity_state=_activity_dict("npc_hungry", 1, 98, 98),
        )
        als.run_activity_lifecycle(_ctx(scene, [npc], tick=100), _OrchStub())
        obj = WorldObjectStore.get(scene, _FOOD_ID)
        self.assertEqual(obj.holder, "npc_hungry")
        self.assertEqual(npc["activity_state"]["step_index"], 2)

    def test_consume_terminal_resets_need_depletes_releases(self):
        scene = _scene_with_food()
        WorldObjectStore.establish_relation(
            scene, _FOOD_ID, ObjectRelationKind.HELD_BY, "npc_hungry"
        )
        npc = _npc(
            activity_state=_activity_dict("npc_hungry", 2, 97, 97),
        )
        als.run_activity_lifecycle(_ctx(scene, [npc], tick=100), _OrchStub())
        obj = WorldObjectStore.get(scene, _FOOD_ID)
        self.assertEqual(obj.state, "DESTROYED")          # damage-закон О6
        self.assertIsNone(obj.holder)                     # явный release
        self.assertEqual(npc["needs"]["hunger"], 0.0)     # только outcome-фактом
        self.assertNotIn("activity_state", npc)
        self.assertEqual(npc["desires"][0]["last_fulfilled_tick"], 100)

    def test_timeout_failure_keeps_need_pressing(self):
        scene = _scene_with_food()
        npc = _npc(activity_state=_activity_dict("npc_hungry", 0, 10, 10))
        als.run_activity_lifecycle(_ctx(scene, [npc], tick=100), _OrchStub())
        self.assertNotIn("activity_state", npc)
        self.assertEqual(npc["needs"]["hunger"], 0.9)     # сброса нет — только outcome

    def test_reconcile_born_executing_commitment(self):
        scene = _scene_with_food()
        # Шаг тела ещё В ПРОЦЕССЕ (100-99 < 3): иначе конвертер легально
        # завершит деятельность ДО reconcile — фикстур не должен врать
        npc = _npc(activity_state=_activity_dict("npc_hungry", 2, 90, 99))
        WorldObjectStore.establish_relation(
            scene, _FOOD_ID, ObjectRelationKind.HELD_BY, "npc_hungry"
        )
        with mock.patch.object(cr_mod, "COMMITMENT_REGISTRY_ENABLED", True), \
             mock.patch.object(cr_mod, "S203_4_OWNERSHIP_MIRRORS", True):
            als.run_activity_lifecycle(_ctx(scene, [npc], tick=100), _OrchStub())
            cm = cr_mod.CommitmentRegistry.get_active(scene, "npc_hungry")
        self.assertIsNotNone(cm)
        self.assertEqual(cm.get("executor"), "activity")
        self.assertIn(cm.get("status"), ("EXECUTING", "COMMITTED"))

    def test_reconcile_completes_when_activity_finished(self):
        scene = _scene_with_food()
        # Рождение (tick 100, еда в процессе) → факт удалён → COMPLETED
        npc = _npc(activity_state=_activity_dict("npc_hungry", 2, 90, 99))
        WorldObjectStore.establish_relation(
            scene, _FOOD_ID, ObjectRelationKind.HELD_BY, "npc_hungry"
        )
        with mock.patch.object(cr_mod, "COMMITMENT_REGISTRY_ENABLED", True), \
             mock.patch.object(cr_mod, "S203_4_OWNERSHIP_MIRRORS", True):
            als.run_activity_lifecycle(_ctx(scene, [npc], tick=100), _OrchStub())
            self.assertIsNotNone(
                cr_mod.CommitmentRegistry.get_active(scene, "npc_hungry")
            )  # born-EXECUTING доказан, не предполагался
            # Деятельность завершилась; желание больше не давит (сыт)
            npc.pop("activity_state", None)
            npc["desires"][0]["urgency"] = 0.3
            als.run_activity_lifecycle(_ctx(scene, [npc], tick=101), _OrchStub())
            cm = cr_mod.CommitmentRegistry.get_active(scene, "npc_hungry")
        self.assertIsNone(cm)  # COMPLETED → ушёл в историю


if __name__ == "__main__":
    unittest.main()