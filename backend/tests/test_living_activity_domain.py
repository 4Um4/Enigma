"""
Round-trip и детерминизм доменных сущностей Living Activity.
§12.3: объекты создаются ТОЛЬКО через from_dict из реальных dict-структур
(форма npc["desires"] / npc["activity_state"]); вариации — dataclasses.replace,
не конструктор-мечтания.
"""
import dataclasses
import unittest

from app.domain.desire import Desire, DesireSource, ProvenanceEntry
from app.domain.activity import (
    ActivityState,
    ActivityStep,
    ActivityType,
    InterruptionPolicy,
    StepKind,
)


# Реальная runtime-структура (как её пишет DesireGenerator)
REAL_DESIRE_DICT = {
    "desire_id": "d:food",
    "subject_class": "food",
    "urgency": 0.56,
    "target_class": "food_portion",
    "provenance": [
        {"source": "need", "weight": 1.0, "origin_ref": "hunger"},
    ],
    "born_tick": 118,
    "last_fulfilled_tick": -1,
    "weight": 1.0,
    "learned_from": [],
}

# Реальная runtime-структура (как её пишет конвертер Phase 0.7)
REAL_ACTIVITY_DICT = {
    "activity_id": "tavern_keeper_tornin:eat:124",
    "activity_type": "eat",
    "desire_id": "d:food",
    "target_ref": "obj_tavern_portion_0001",
    "steps": [
        {"step_kind": "move", "action_type": "", "target_ref": "tavern:kitchen", "duration_ticks": 1},
        {"step_kind": "object_action", "action_type": "TAKE", "target_ref": "obj_tavern_portion_0001", "duration_ticks": 1},
        {"step_kind": "body_action", "action_type": "CONSUME", "target_ref": "obj_tavern_portion_0001", "duration_ticks": 3},
    ],
    "step_index": 0,
    "started_tick": 124,
    "interruption_policy": "stub",
}


class TestDesireRoundTrip(unittest.TestCase):
    def test_round_trip_preserves_all_fields(self):
        d = Desire.from_dict(REAL_DESIRE_DICT)
        d2 = Desire.from_dict(d.to_dict())
        self.assertEqual(d, d2)

    def test_multi_cause_provenance_survives_round_trip(self):
        # L-M1: множественная причинность — с рождения, переживает сериализацию
        d = dataclasses.replace(
            Desire.from_dict(REAL_DESIRE_DICT),
            provenance=(
                ProvenanceEntry(source=DesireSource.NEED, weight=0.8, origin_ref="hunger"),
                ProvenanceEntry(source=DesireSource.DRIVE, weight=0.3, origin_ref="control"),
            ),
        )
        d2 = Desire.from_dict(d.to_dict())
        self.assertEqual(len(d2.provenance), 2)
        self.assertEqual(d2.dominant_source, DesireSource.NEED)

    def test_stable_id_deterministic(self):
        self.assertEqual(Desire.stable_id("food"), Desire.stable_id("food"))
        self.assertNotEqual(Desire.stable_id("food"), Desire.stable_id("money"))

    def test_bounds_clamped_before_commit(self):
        # ADR-O-207: кламп — до коммита, не после
        hot = dataclasses.replace(Desire.from_dict(REAL_DESIRE_DICT), urgency=5.0)
        self.assertEqual(hot.urgency, 1.0)


class TestActivityRoundTrip(unittest.TestCase):
    def test_round_trip_preserves_steps(self):
        a = ActivityState.from_dict(REAL_ACTIVITY_DICT)
        a2 = ActivityState.from_dict(a.to_dict())
        self.assertEqual(a, a2)
        self.assertEqual(len(a2.steps), 3)
        self.assertEqual(a2.steps[1].action_type, "TAKE")
        self.assertEqual(a2.steps[2].step_kind, StepKind.BODY_ACTION)
        self.assertEqual(a2.steps[2].duration_ticks, 3)

    def test_step_index_is_resume_token(self):
        # INTERRUPTION_PRESERVES_GOAL: step_index — персистентный resume-токен
        a = ActivityState.from_dict(REAL_ACTIVITY_DICT)
        mid = dataclasses.replace(a, step_index=2)
        self.assertEqual(ActivityState.from_dict(mid.to_dict()).step_index, 2)

    def test_build_id_deterministic(self):
        self.assertEqual(
            ActivityState.build_id("npc_a", ActivityType.EAT, 124),
            ActivityState.build_id("npc_a", ActivityType.EAT, 124),
        )
        self.assertNotEqual(
            ActivityState.build_id("npc_a", ActivityType.EAT, 124),
            ActivityState.build_id("npc_a", ActivityType.EAT, 125),
        )

    def test_onset_fact_required(self):
        # ACTIVITY_ONSET_FACT: факт без причины — громкий отказ, не тихий None
        broken = dict(REAL_ACTIVITY_DICT)
        broken["desire_id"] = ""
        with self.assertRaises(ValueError):
            ActivityState.from_dict(broken)


if __name__ == "__main__":
    unittest.main()