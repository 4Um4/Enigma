"""
Шаг 5 (NO_LABEL_SATISFACTION): режимы насыщения потребностей.
OFF — легаси-ярлык (байт-идентично); ON — только outcome-факт конвертера;
подавление двойного трека (легаси-движение не конкурирует с конвертером).

Запуск: cd backend; python -m pytest tests/test_need_satisfaction_mode.py -v; cd ..
"""
import os
import unittest

from app.services.npc import activity_lifecycle_service as als
from app.services.npc.life_engine import LifeEngine


def _npc(needs, current=""):
    return {
        "id": "npc_t",
        "needs": needs,
        "routine": {"current": current},
        "activity_map": {
            "eating": {"location": "tavern", "position": "right_table", "display": "eating"},
            "socializing": {"location": "tavern", "position": "bar_area", "display": "socializing"},
        },
        "position": "main_hall",
        "location_id": "tavern",
    }


class TestNeedSatisfactionMode(unittest.TestCase):
    def setUp(self):
        self._old_a = os.environ.pop("ACTIVITY_LIFECYCLE_ENABLED", None)
        self._old_d = os.environ.pop("DESIRES_ENABLED", None)
        self._le = LifeEngine()

    def tearDown(self):
        os.environ.pop("ACTIVITY_LIFECYCLE_ENABLED", None)
        os.environ.pop("DESIRES_ENABLED", None)
        for _k, _v in (("ACTIVITY_LIFECYCLE_ENABLED", self._old_a), ("DESIRES_ENABLED", self._old_d)):
            if _v is not None:
                os.environ[_k] = _v

    def _on(self):
        os.environ["ACTIVITY_LIFECYCLE_ENABLED"] = "1"
        os.environ["DESIRES_ENABLED"] = "1"

    def test_off_label_resets_hunger_legacy(self):
        npc = _npc({"hunger": 0.5}, current="eating")
        self._le._tick_needs(npc)
        self.assertEqual(npc["needs"]["hunger"], 0.0)  # легаси байт-идентично

    def test_on_label_does_not_reset_hunger(self):
        self._on()
        npc = _npc({"hunger": 0.4}, current="eating")
        self._le._tick_needs(npc)
        self.assertAlmostEqual(npc["needs"]["hunger"], 0.48)  # рост, ярлык мёртв

    def test_suppression_only_for_catalogued_needs(self):
        self._on()
        self.assertTrue(als.legacy_need_suppressed("hunger"))     # food → EAT
        self.assertFalse(als.legacy_need_suppressed("social_urge"))  # нет записи
        os.environ["ACTIVITY_LIFECYCLE_ENABLED"] = ""
        self.assertFalse(als.legacy_need_suppressed("hunger"))    # частичный ON не подавляет

    def test_need_driven_movement_on_prefers_unsuppressed(self):
        self._on()
        npc = _npc({"hunger": 0.9, "social_urge": 0.6})
        goal = self._le._check_need_driven_movement(npc)
        self.assertIsNotNone(goal)
        self.assertIn("social_urge", str(goal.reason))  # hunger забран конвертером

    def test_need_driven_movement_off_targets_hunger(self):
        npc = _npc({"hunger": 0.9, "social_urge": 0.6})
        goal = self._le._check_need_driven_movement(npc)
        self.assertIsNotNone(goal)
        self.assertIn("hunger", str(goal.reason))  # легаси: argmax без подавления


if __name__ == "__main__":
    unittest.main()