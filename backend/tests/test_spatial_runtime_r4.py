from pathlib import Path

import pytest
from app.core.constants import PERCEPTION_RADIUS
from app.services.npc.perception_filter import _can_hear, _can_see, extract_scene_awareness
from app.services.scene_state_manager import _derive_environment_modifiers
from app.services.spatial.spatial_runtime import (
    extract_scene_for_npc,
    line_of_sight,
    resolve_distance_between_entities,
    sound_bleeds_to_adjacent,
    sound_reach,
)


def test_stealth_npc_not_visible_from_distance() -> None:
    """Невидимый NPC дальше 1.5м не обнаруживается."""
    scene = _scene()
    scene["npc_positions"]["thief"] = {
        "location_id": "tavern_silver_wolf",
        "position": "corner_table",
        "local_position": {"x": 5.0, "y": 5.0},
        "activity": "observing",
        "visible": False,
    }
    out = extract_scene_for_npc(scene, "npc_b", ["thief"])
    assert not any(x["npc_id"] == "thief" for x in out["nearby"])


def test_stealth_npc_detected_at_close_range() -> None:
    """Невидимый NPC вплотную (≤1.5м) обнаруживается с флагом detected."""
    scene = _scene()
    # main_hall (0,0) и npc_b тоже в main_hall — дистанция ~0
    scene["npc_positions"]["hidden_close"] = {
        "location_id": "tavern_silver_wolf",
        "position": "main_hall",
        "local_position": {"x": 0.1, "y": 0.0},
        "activity": "hiding",
        "visible": False,
    }
    scene["environment"]["light_level"] = "bright"
    out = extract_scene_for_npc(scene, "npc_b", ["hidden_close"])
    detected = [x for x in out["nearby"] if x["npc_id"] == "hidden_close"]
    assert detected, "Вплотную невидимый NPC должен быть обнаружен"
    assert detected[0].get("detected") is True


def test_player_included_in_scene_snapshot() -> None:
    """Снимок сцены содержит данные об игроке если он в радиусе."""
    scene = _scene()
    out = extract_scene_for_npc(scene, "npc_b", [])
    assert "player" in out
    assert out["player"] is not None
    assert "distance" in out["player"]
    assert "in_los" in out["player"]


def test_minor_npc_cannot_perceive_far_target() -> None:
    """Minor NPC (радиус 3м) не воспринимает цель на 8м."""
    scene = _scene()
    out = extract_scene_for_npc(
        scene, "npc_a", ["npc_far"],
        perception_radius=PERCEPTION_RADIUS["minor"],
    )
    assert not any(x["npc_id"] == "npc_far" for x in out["nearby"])


def test_major_npc_perceives_far_target() -> None:
    """Major NPC (радиус 15м) воспринимает цель на 8м."""
    scene = _scene()
    out = extract_scene_for_npc(
        scene, "npc_a", ["npc_far"],
        perception_radius=PERCEPTION_RADIUS["major"],
    )
    assert any(x["npc_id"] == "npc_far" for x in out["nearby"])


def test_derive_environment_modifiers_dungeon() -> None:
    """Подземелье: высокая опасность, темнота → низкий light, высокий danger."""
    tv = {"light_level": "dark", "noise_level": "silent"}
    mods = _derive_environment_modifiers(tv, "dungeon")
    assert mods["light"] == 0.0
    assert mods["noise"] == 0.0
    assert mods["danger"] == 0.6


def _scene() -> dict:
    return {
        "location_id": "tavern_silver_wolf",
        "npc_positions": {
            # ADR-048: Игрок внедрен как npc_id="player" в npc_positions
            "player": {
                "location_id": "tavern_silver_wolf",
                "position": "main_hall",
                "local_position": {"x": 0.0, "y": 0.0},
                "activity": "idle",
            },
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
                "local_position": {"x": 8.0, "y": 0.0},
                "activity": "working",
            },
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
        scene["npc_positions"]["player"],
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
    from unittest.mock import MagicMock
    scene = _scene()

    _distances = {"npc_b": 5.0, "npc_far": 25.0}
    mock_sq = MagicMock()
    mock_sq.player_distances.side_effect = (
        lambda ids: {nid: _distances.get(nid, 999.0) for nid in ids}
    )

    assert _can_see("npc_b", mock_sq, "tavern_silver_wolf", scene) is True
    assert _can_hear("npc_far", mock_sq, radius=1.0, scene_state=scene) is False


def test_extract_scene_awareness_returns_nearby_and_actions() -> None:
    scene = _scene()
    out = extract_scene_awareness("npc_b", ["npc_a", "npc_b", "npc_far"], scene)
    assert "nearby" in out and isinstance(out["nearby"], list)
    assert "available_actions" in out
    assert "move" in out["available_actions"]


def test_derive_environment_modifiers_tavern_day() -> None:
    """Таверна днём: шумно, светло."""
    tv = {"light_level": "bright", "noise_level": "moderate"}
    mods = _derive_environment_modifiers(tv, "tavern")
    assert mods["light"] == 1.0
    assert mods["noise"] == 0.5
    assert mods["danger"] == 0.1


def test_dynamic_density_reduces_los_with_many_npcs() -> None:
    """Толпа NPC увеличивает density и режет LOS."""
    scene = _scene()
    # Добавляем 10 NPC → density = 0.2 (base) + 10*0.05 = 0.7
    for i in range(10):
        scene["npc_positions"][f"crowd_{i}"] = {
            "location_id": "tavern_silver_wolf",
            "position": "main_hall",
            "local_position": {"x": float(i), "y": 0.0},
            "activity": "standing",
        }
    scene["environment"]["light_level"] = "bright"
    # При density=0.7: los_range = 15 - 0.7*6 = 10.8м → 11м не видно
    assert line_of_sight(11.0, scene) is False


def test_dynamic_density_empty_scene_uses_base() -> None:
    """Пустая сцена — density только базовая, LOS не режется."""
    scene = _scene()
    scene["npc_positions"] = {}
    scene["environment_modifiers"]["density"] = 0.0
    scene["environment"]["light_level"] = "bright"
    # base_range=15, density=0 → los_range=15м
    assert line_of_sight(14.0, scene) is True


def test_sound_bleeds_to_adjacent_loud_event() -> None:
    """Громкий звук (radius > threshold) просачивается в соседние локации."""
    templates = Path(__file__).parent.parent / "data" / "locations" / "location_templates.json"
    if not templates.exists():
        pytest.skip("location_templates.json отсутствует")
    scene = _scene()
    scene["environment_modifiers"]["noise"] = 1.0
    scene["environment_modifiers"]["density"] = 0.0
    # sound_reach(10.0) = 10 + 1.0*4 - 0 = 14.0 > 12.0 → должен просочиться
    adjacent = sound_bleeds_to_adjacent(
        scene, base_radius=10.0,
        bleed_threshold=12.0,
        data_dir=str(Path(__file__).parent.parent / "data"),
    )
    assert isinstance(adjacent, list)
    assert "city_gate" in adjacent or "market_square" in adjacent or "inn_rooms" in adjacent


def test_sound_bleeds_quiet_event_stays_local() -> None:
    """Тихий звук (radius < threshold) не выходит за пределы локации."""
    scene = _scene()
    scene["environment_modifiers"]["noise"] = 0.0
    scene["environment_modifiers"]["density"] = 0.5
    # sound_reach(2.0) = 2 + 0 - 0.5*3 = 0.5 < 12.0 → не просачивается
    adjacent = sound_bleeds_to_adjacent(
        scene, base_radius=2.0,
        bleed_threshold=12.0,
        data_dir=str(Path(__file__).parent.parent / "data"),
    )
    assert adjacent == []
