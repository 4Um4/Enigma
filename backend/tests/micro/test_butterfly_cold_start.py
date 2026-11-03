# backend/tests/micro/test_butterfly_cold_start.py
"""COGNITIVE-CONTINUITY-01 Etap 5 — cold-start клейм delivery (proposition exception)."""
from app.services.phases.post_decision import _prop_target_in_reach


def test_target_in_reach_same_location_close():
    scene = {"npc_positions": {
        "maid_lusya": {"position": "tavern:kitchen", "local_position": (0.0, 0.0)},
        "tavern_keeper_tornin": {"position": "tavern:bar", "local_position": (5.0, 0.0)},
    }}
    assert _prop_target_in_reach(scene, "maid_lusya", "tavern_keeper_tornin") is True


def test_target_out_of_reach_far():
    scene = {"npc_positions": {
        "maid_lusya": {"position": "tavern:kitchen", "local_position": (0.0, 0.0)},
        "tavern_keeper_tornin": {"position": "tavern:bar", "local_position": (12.0, 0.0)},
    }}
    assert _prop_target_in_reach(scene, "maid_lusya", "tavern_keeper_tornin") is False


def test_target_different_location():
    scene = {"npc_positions": {
        "maid_lusya": {"position": "tavern:kitchen", "local_position": (0.0, 0.0)},
        "tavern_keeper_tornin": {"position": "street:main", "local_position": (1.0, 0.0)},
    }}
    assert _prop_target_in_reach(scene, "maid_lusya", "tavern_keeper_tornin") is False


def test_target_missing_data():
    scene = {"npc_positions": {"maid_lusya": {"position": "tavern:kitchen"}}}
    assert _prop_target_in_reach(scene, "maid_lusya", "tavern_keeper_tornin") is False