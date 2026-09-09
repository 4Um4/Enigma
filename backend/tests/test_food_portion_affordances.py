"""
Мини-запись ADR-O-376 (Living Activity EAT): food_portion — полный
W2-каркас + SpawnMapping. Объекты рождаются реальным путём стора
(§12.3: фабрика, не конструкторы-мечтания); вариации — dataclass_replace.
Истощение (damage-терминал О6) — контур конвертера (Шаг 4), не спавнера.

Запуск: cd backend; python -m pytest tests/test_food_portion_affordances.py -v; cd ..
"""
import unittest

from app.domain.semantic_action import WorldActionType
from app.domain.world_object import dataclass_replace
from app.services.world.affordance_resolver import (
    _AFFORDANCE_TABLE,
    effective_state,
)
from app.services.world.world_object_spawner import (
    _EDITOR_TYPE_TO_ARCHETYPE,
    WorldObjectSpawner,
    _deterministic_object_id,
)
from app.services.world.world_object_store import WorldObjectStore


class TestFoodPortionEffectiveState(unittest.TestCase):
    def setUp(self):
        self._scene: dict = {}
        WorldObjectStore.spawn(
            self._scene, "wo_test_food", "food_portion", "tavern", (4.2, 4.3)
        )
        self._obj = WorldObjectStore.get(self._scene, "wo_test_food")

    def test_fresh_spawn_is_available(self):
        self.assertEqual(effective_state(self._obj), "AVAILABLE")

    def test_holder_derives_held(self):
        held = dataclass_replace(self._obj, holder="npc_test")
        self.assertEqual(effective_state(held), "HELD")

    def test_damage_track_is_honest(self):
        destroyed = dataclass_replace(self._obj, state="DESTROYED")
        self.assertEqual(effective_state(destroyed), "DESTROYED")


class TestFoodPortionW2Rows(unittest.TestCase):
    def test_available_row_take_move(self):
        row = _AFFORDANCE_TABLE[("food_portion", "AVAILABLE")]
        verbs = {a.action_type for a in row}
        self.assertIn(WorldActionType.TAKE, verbs)
        self.assertIn(WorldActionType.MOVE, verbs)
        for a in row:  # В9: явные предусловия на каждом действии
            names = {p.predicate for p in a.preconditions}
            self.assertIn("STATE_IS", names)
            self.assertIn("IS_ADJACENT_TO", names)

    def test_held_row_place_drop_discard(self):
        row = _AFFORDANCE_TABLE[("food_portion", "HELD")]
        verbs = {a.action_type for a in row}
        self.assertEqual(
            verbs,
            {WorldActionType.PLACE, WorldActionType.DROP, WorldActionType.DISCARD},
        )
        for a in row:
            names = {p.predicate for p in a.preconditions}
            self.assertIn("HOLDER_IS", names)

    def test_consumed_terminal_has_no_actions(self):
        # Истощённая порция — честная пустая строка (как container/LOCKED)
        self.assertNotIn(("food_portion", "DESTROYED"), _AFFORDANCE_TABLE)


class TestFoodPortionSpawn(unittest.TestCase):
    def test_spawn_mapping_registered(self):
        self.assertEqual(
            _EDITOR_TYPE_TO_ARCHETYPE.get("food_portion"), "food_portion"
        )

    def test_editor_flow_spawns_food(self):
        scene: dict = {}
        editor_data = {
            "objects": [
                {
                    "type": "food_portion",
                    "id": "obj_42",
                    "position": {"x": 4.2, "y": 4.3},
                    "properties": {},
                }
            ]
        }
        report = WorldObjectSpawner.spawn_from_editor(
            scene, "test_campaign", "tavern", editor_data
        )
        self.assertEqual(report.spawned, 1)
        obj = WorldObjectStore.get(
            scene, _deterministic_object_id("test_campaign", "tavern", "obj_42")
        )
        self.assertEqual(obj.archetype, "food_portion")
        self.assertEqual(obj.state, "INTACT")

    def test_identity_deterministic(self):
        self.assertEqual(
            _deterministic_object_id("c", "tavern", "obj_42"),
            _deterministic_object_id("c", "tavern", "obj_42"),
        )


if __name__ == "__main__":
    unittest.main()