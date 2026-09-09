"""
Шаг 6 (видимость): конвертер проецирует факт в npc_positions.activity
через SceneChange (сон-канал); R3 рендерит занятость в SceneContinuity.

Запуск: cd backend; python -m pytest tests/test_activity_visibility.py tests/test_activity_lifecycle.py -v; cd ..
"""
import os
import unittest
from types import SimpleNamespace

from app.domain.world_object import ObjectRelationKind
from app.services.npc import activity_lifecycle_service as als
from app.services.world.world_object_store import WorldObjectStore

_FOOD_ID = "wo_test_food_001"


class _SpatialStub:
    def resolve_node(self, role, origin_xy=None, origin_zone=None, filters=None):
        return SimpleNamespace(zone_id="tavern", node_id="bar_area")


class _OrchRecording:
    def __init__(self):
        self.applied = []
        self._spatial = _SpatialStub()

    def _get_event_bus(self):
        return None

    def _resolve_spatial_service(self, ctx):
        return self._spatial

    def _apply_with_shadow_observation(self, ctx, changes, phase_label=""):
        self.applied.append((phase_label, list(changes or [])))


def _scene_with_food():
    scene = {"location_id": "tavern"}
    WorldObjectStore.spawn(scene, _FOOD_ID, "food_portion", "tavern", (4.2, 5.4))
    return scene


def _npc():
    return {
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
        "body_state": {
            "life_status": "ALIVE", "current_hp": 100, "pain": 0,
            "fatigue": 0, "blood_loss": 0.0, "consciousness": 1.0,
            "shock_impulse": 0.0, "injuries": {},
        },
    }


def _ctx(scene, npcs, tick=100):
    return SimpleNamespace(
        scene_state=scene, all_npcs_raw=npcs, tick_number=tick,
        campaign_id="test", tick_snapshot=None,
    )


def _activity_dict(step_index, started, step_started):
    from app.domain.activity import ActivityState, ActivityStep, ActivityType, StepKind

    steps = (
        ActivityStep(step_kind=StepKind.MOVE, target_ref="bar_area"),
        ActivityStep(step_kind=StepKind.OBJECT_ACTION, action_type="TAKE", target_ref=_FOOD_ID),
        ActivityStep(step_kind=StepKind.BODY_ACTION, action_type="CONSUME", target_ref=_FOOD_ID, duration_ticks=3),
    )
    return ActivityState(
        activity_id=ActivityState.build_id("npc_hungry", ActivityType.EAT, started),
        activity_type=ActivityType.EAT, desire_id="d:food", target_ref=_FOOD_ID,
        steps=steps, step_index=step_index, step_started_tick=step_started,
        started_tick=started,
    ).to_dict()


class TestActivityVisibility(unittest.TestCase):
    def setUp(self):
        self._old_a = os.environ.pop("ACTIVITY_LIFECYCLE_ENABLED", None)
        self._old_d = os.environ.pop("DESIRES_ENABLED", None)
        os.environ["ACTIVITY_LIFECYCLE_ENABLED"] = "1"
        os.environ["DESIRES_ENABLED"] = "1"

    def tearDown(self):
        os.environ.pop("ACTIVITY_LIFECYCLE_ENABLED", None)
        os.environ.pop("DESIRES_ENABLED", None)
        for _k, _v in (("ACTIVITY_LIFECYCLE_ENABLED", self._old_a), ("DESIRES_ENABLED", self._old_d)):
            if _v is not None:
                os.environ[_k] = _v

    def _label_changes(self, orch):
        out = []
        for _label, changes in orch.applied:
            for ch in changes:
                if getattr(ch, "field", "") == "activity":
                    out.append(ch)
        return out

    def test_onset_emits_activity_label(self):
        scene = _scene_with_food()
        npc = _npc()
        orch = _OrchRecording()
        als.run_activity_lifecycle(_ctx(scene, [npc]), orch)
        labels = self._label_changes(orch)
        self.assertTrue(any(c.value == "eating" for c in labels))
        self.assertTrue(all(c.cause == "activity_lifecycle" for c in labels))

    def test_terminal_clears_activity_label(self):
        scene = _scene_with_food()
        WorldObjectStore.establish_relation(scene, _FOOD_ID, ObjectRelationKind.HELD_BY, "npc_hungry")
        npc = _npc()
        npc["activity_state"] = _activity_dict(2, 97, 97)
        orch = _OrchRecording()
        als.run_activity_lifecycle(_ctx(scene, [npc]), orch)
        labels = self._label_changes(orch)
        self.assertTrue(any(c.value == "" for c in labels))

    def test_r3_renders_activity_into_continuity(self):
        from app.services.scene.r3_direct_builder import build_r3_dm_frame

        shared = SimpleNamespace(
            npc_contexts=[], player_target_id="",
            scene_state={
                "npc_positions": {"npc_a": {"name": "Торнин", "activity": "eating"}},
                "line_of_sight": {},
            },
            spatial_query=None, world_tick_result=None,
            social_propagation=[], spatial_events=[],
            scene_continuity=None, action_type="", player_state={},
        )
        build_r3_dm_frame(shared, [], None)
        cont = shared.scene_continuity
        events = [str(e) for e in getattr(cont, "recent_events", [])]
        self.assertTrue(any("Торнин" in e and "ест" in e for e in events))


if __name__ == "__main__":
    unittest.main()