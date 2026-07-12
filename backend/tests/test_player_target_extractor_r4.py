from app.services.action.player_target_extractor import PlayerTargetExtractor


def test_extract_distances_from_spatial_context() -> None:
    extractor = PlayerTargetExtractor()
    scene_state = {
        "location_id": "tavern_silver_wolf",
        "npc_positions": {
            "player": {
                "location_id": "tavern_silver_wolf",
                "position": "main_hall",
                "local_position": {"x": 0.0, "y": 0.0},
            },
            "tavern_keeper_tornin": {
                "location_id": "tavern_silver_wolf",
                "position": "behind_bar",
                "local_position": {"x": 0.0, "y": 0.0},
            },
            "maid_lusya": {
                "location_id": "tavern_silver_wolf",
                "position": "main_hall",
                "local_position": {"x": 0.3, "y": 0.0},
            },
        },
    }
    npc_contexts = [
        {"npc_id": "tavern_keeper_tornin", "npc_name": "Торнин", "name_forms": ["торнин"]},
        {"npc_id": "maid_lusya", "npc_name": "Луся", "name_forms": ["луся"]},
    ]

    _, _, _, _, distances = extractor.extract("говорю Торнину", npc_contexts=npc_contexts, scene_state=scene_state)

    assert distances["maid_lusya"] < distances["tavern_keeper_tornin"]
    assert distances["tavern_keeper_tornin"] > 1.0
