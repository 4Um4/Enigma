"""
Guarded-продюсер DesireSet: no-op при OFF, upsert при ON, идемпотентность,
история рождения не перезаписывается, детерминизм округлений.

Запуск: cd backend; python -m pytest tests/test_desire_generator.py -v; cd ..
"""
import os
import unittest

from app.services.npc import desire_generator as dg


def _npc(needs=None):
    return {
        "npc_id": "tavern_keeper_tornin",
        "needs": needs if needs is not None else {"hunger": 0.56},
    }


class TestDesireGeneratorGuard(unittest.TestCase):
    def setUp(self):
        self._old = os.environ.pop("DESIRES_ENABLED", None)
        os.environ["DESIRES_ENABLED"] = "1"

    def tearDown(self):
        os.environ.pop("DESIRES_ENABLED", None)
        if self._old is not None:
            os.environ["DESIRES_ENABLED"] = self._old

    def test_off_is_byte_identical_noop(self):
        os.environ["DESIRES_ENABLED"] = ""
        npc = _npc()
        dg.update_all([npc], tick=100)
        # Ключ даже не создаётся: полный no-op
        self.assertNotIn("desires", npc)

    def test_hunger_births_food_desire_with_provenance(self):
        npc = _npc({"hunger": 0.56})
        dg.update_all([npc], tick=118)
        d = npc["desires"][0]
        self.assertEqual(d["desire_id"], "d:food")
        self.assertEqual(d["urgency"], 0.56)
        self.assertEqual(d["target_class"], "food_portion")
        self.assertEqual(d["provenance"][0]["origin_ref"], "hunger")
        self.assertEqual(d["born_tick"], 118)

    def test_upsert_updates_urgency_preserves_history(self):
        # L-M1: born-структура причинности не перезаписывается upsert'ом
        npc = _npc({"hunger": 0.56})
        dg.update_all([npc], tick=118)
        npc["needs"]["hunger"] = 0.9
        dg.update_all([npc], tick=200)
        desires = npc["desires"]
        self.assertEqual(len(desires), 1)       # нет дублей (idempotent)
        self.assertEqual(desires[0]["urgency"], 0.9)
        self.assertEqual(desires[0]["born_tick"], 118)  # история не тронута

    def test_no_needs_no_crash_no_key(self):
        npc = {"npc_id": "player"}
        dg.update_all([npc], tick=1)
        self.assertNotIn("desires", npc)

    def test_all_four_need_sources_complete(self):
        npc = _npc(
            {"hunger": 0.8, "shelter_urge": 0.3, "social_urge": 0.6, "fatigue": 0.4}
        )
        dg.update_all([npc], tick=1)
        ids = {d["desire_id"] for d in npc["desires"]}
        self.assertEqual(ids, {"d:food", "d:shelter", "d:social", "d:rest"})

    def test_bounds_clamped_before_write(self):
        npc = _npc({"hunger": 5.0})
        dg.update_all([npc], tick=1)
        self.assertEqual(npc["desires"][0]["urgency"], 1.0)


if __name__ == "__main__":
    unittest.main()