from app.domain.identity_events import EffectiveDrives

_MOCK_DRIVES = EffectiveDrives.from_dict({"control": 0.5, "significance": 0.5, "fear": 0.5, "desire": 0.5})

from app.services.action.player_target_extractor import PlayerTargetExtractor


def test_extract_distances_from_spatial_context() -> None:
    extractor = PlayerTargetExtractor()
    scene_state = {
        "location_id": "tavern_silver_wolf",
        "npc_positions": {
            "player": {
                "location_id": "tavern_silver_wolf",
                "position": "main_hall",
                "local_position": {"x": 10.0, "y": 10.0},
            },
            "tavern_keeper_tornin": {
                "location_id": "tavern_silver_wolf",
                "position": "behind_bar",
                "local_position": {"x": 15.0, "y": 15.0},
            },
            "maid_lusya": {
                "location_id": "tavern_silver_wolf",
                "position": "main_hall",
                "local_position": {"x": 10.5, "y": 10.0},
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


def test_sticky_target_is_ignored_when_npc_is_not_in_current_scene() -> None:
    extractor = PlayerTargetExtractor()
    scene_state = {
        "location_id": "city_gate",
        "player_target_npc": "tavern_keeper_tornin",
        "player_target_npc_name": "Торнин Серебряная Луна",
        "npc_positions": {
            "player": {
                "location_id": "city_gate",
                "local_position": {"x": 5.0, "y": 5.0},
            },
            "merchant_goran": {
                "location_id": "city_gate",
                "local_position": {"x": 6.0, "y": 5.0},
            },
            "blacksmith_orm": {
                "location_id": "city_gate",
                "local_position": {"x": 7.0, "y": 5.0},
            },
            "thief_shadow": {
                "location_id": "city_gate",
                "local_position": {"x": 9.0, "y": 5.0},
            },
        },
    }
    npc_contexts = [
        {"npc_id": "merchant_goran", "npc_name": "Горан", "name_forms": ["горан"]},
        {"npc_id": "blacksmith_orm", "npc_name": "Орм", "name_forms": ["орм"]},
        {"npc_id": "thief_shadow", "npc_name": "Тень", "name_forms": ["тень"]},
    ]

    for action in ("Привет! Как тебя зовут?", "Я тебя спрашиваю", "говорю тебе"):
        target_id, *_ = extractor.extract(
            action,
            npc_contexts=npc_contexts,
            scene_state=scene_state,
        )

        assert target_id == "merchant_goran"


def test_sticky_target_is_kept_when_npc_is_in_current_scene() -> None:
    extractor = PlayerTargetExtractor()
    scene_state = {
        "location_id": "tavern_silver_wolf",
        "player_target_npc": "tavern_keeper_tornin",
        "player_target_npc_name": "Торнин",
        "npc_positions": {
            "player": {"location_id": "tavern_silver_wolf"},
            "tavern_keeper_tornin": {"location_id": "tavern_silver_wolf"},
            "maid_lusya": {"location_id": "tavern_silver_wolf"},
        },
    }
    npc_contexts = [
        {"npc_id": "tavern_keeper_tornin", "npc_name": "Торнин", "name_forms": ["торнин"]},
        {"npc_id": "maid_lusya", "npc_name": "Луся", "name_forms": ["луся"]},
    ]

    target_id, *_ = extractor.extract(
        "говорю тебе",
        npc_contexts=npc_contexts,
        scene_state=scene_state,
    )

    assert target_id == "tavern_keeper_tornin"


def test_neutral_greeting_does_not_inherit_sticky_target() -> None:
    extractor = PlayerTargetExtractor()
    scene_state = {
        "location_id": "tavern_silver_wolf",
        "player_target_npc": "tavern_keeper_tornin",
        "player_target_npc_name": "\u0422\u043e\u0440\u043d\u0438\u043d",
        "npc_positions": {
            "player": {
                "location_id": "tavern_silver_wolf",
                "local_position": {"x": 0.0, "y": 0.0},
            },
            "tavern_keeper_tornin": {
                "location_id": "tavern_silver_wolf",
                "local_position": {"x": 50.0, "y": 0.0},
            },
            "maid_lusya": {
                "location_id": "tavern_silver_wolf",
                "local_position": {"x": 60.0, "y": 0.0},
            },
        },
    }
    npc_contexts = [
        {
            "npc_id": "tavern_keeper_tornin",
            "npc_name": "\u0422\u043e\u0440\u043d\u0438\u043d",
            "name_forms": ["\u0442\u043e\u0440\u043d\u0438\u043d"],
        },
        {
            "npc_id": "maid_lusya",
            "npc_name": "\u041b\u0443\u0441\u044f",
            "name_forms": ["\u043b\u0443\u0441\u044f"],
        },
    ]

    target_id, *_ = extractor.extract(
        "\u041f\u0440\u0438\u0432\u0435\u0442 \u0440\u0435\u0431\u044f\u0442\u0430!",
        npc_contexts=npc_contexts,
        scene_state=scene_state,
    )

    assert target_id is None
