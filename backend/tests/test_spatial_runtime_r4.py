from app.services.npc.perception_filter import _can_hear, _can_see, extract_scene_awareness
from app.services.npc.spatial_runtime import line_of_sight, resolve_distance_between_entities, sound_reach


def _scene() -> dict:
    return {
        "location_id": "tavern_silver_wolf",
        "npc_positions": {
            "npc_a": {
                "location_id": "tavern_silver_wolf",
                "position": "behind_bar",
                "local_position": {"x": 0.0, "y": 0.0},
                "activity": "working",
            },
            "npc_b": {
                "location_id": "tavern_silver_wolf",
                "position": "main_hall",
                "local_position": {"x": 0.5, "y": 0.0},
                "activity": "working",
            },
            "npc_far": {
                "location_id": "tavern_silver_wolf",
                "position": "stairs",
                "local_position": {"x": 0.0, "y": 0.0},
                "activity": "working",
            },
        },
        "player_spatial": {
            "location_id": "tavern_silver_wolf",
            "position": "main_hall",
            "local_position": {"x": 0.0, "y": 0.0},
        },
        "player_position": {"x": 0.0, "y": 0.0},
        "environment": {"light_level": "dim"},
        "environment_modifiers": {"noise": 0.5, "density": 0.2, "danger": 0.0},
    }


def test_spatial_distance_uses_graph_and_local_offsets() -> None:
    scene = _scene()
    d = resolve_distance_between_entities(
        scene,
        scene["npc_positions"]["npc_a"],
        scene["player_spatial"],
    )
    assert d > 0.0


def test_los_reduced_by_density() -> None:
    scene = _scene()
    scene["environment"]["light_level"] = "bright"
    scene["environment_modifiers"]["density"] = 1.0
    assert line_of_sight(12.0, scene) is False


def test_sound_reach_modified_by_noise_and_density() -> None:
    scene = _scene()
    radius = sound_reach(10.0, scene)
    assert radius > 10.0


def test_perception_filter_uses_spatial_runtime() -> None:
    scene = _scene()
    assert _can_see("npc_b", scene, "tavern_silver_wolf") is True
    assert _can_hear("npc_far", scene, radius=1.0) is False


def test_extract_scene_awareness_returns_nearby_and_actions() -> None:
    scene = _scene()
    out = extract_scene_awareness("npc_b", ["npc_a", "npc_b", "npc_far"], scene)
    assert "nearby" in out and isinstance(out["nearby"], list)
    assert "available_actions" in out
    assert "move" in out["available_actions"]
