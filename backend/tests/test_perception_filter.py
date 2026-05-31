# backend/tests/test_perception_filter.py
"""
R4.3 — тесты PerceptionFilter с реальными координатами.
Проверяет: переход с player_distances на (x, y).
"""

import pytest
from app.services.npc.perception_filter import (
    _npc_distance,
    _can_see,
    filter_perceiving_npcs,
    _can_hear,
    calculate_clarity
)

import math
from unittest.mock import MagicMock


def _make_spatial_mock(scene: dict) -> MagicMock:
    """
    Mock SpatialQueryService из scene dict.
    Вычисляет дистанцию из (x,y) координат NPC и player_position.
    NPC без координат → 999.0 (вне радиуса).
    """
    mock = MagicMock()
    player_pos = scene.get("player_position", {})
    npc_positions = scene.get("npc_positions", {})
    px = float(player_pos.get("x", 0.0))
    py = float(player_pos.get("y", 0.0))

    def _player_distances(npc_ids):
        result = {}
        for nid in npc_ids:
            pos = npc_positions.get(nid, {})
            if "x" in pos and "y" in pos:
                dx = float(pos["x"]) - px
                dy = float(pos["y"]) - py
                result[nid] = math.sqrt(dx * dx + dy * dy)
            else:
                result[nid] = 999.0
        return result

    mock.player_distances.side_effect = _player_distances
    return mock

def _scene(npc_positions: dict, player_pos: dict,
           light: str = "bright") -> dict:
    return {
        "npc_positions": npc_positions,
        "player_position": player_pos,
        "environment": {"light_level": light},
    }


class TestNpcDistance:

    def test_uses_coordinates_when_available(self) -> None:
        """R4.3: дистанция через SpatialQueryService (3-4-5 треугольник)."""
        scene = _scene(
            npc_positions={"guard": {"x": 3.0, "y": 4.0, "activity": "working"}},
            player_pos={"x": 0.0, "y": 0.0},
        )
        sq = _make_spatial_mock(scene)
        assert _npc_distance("guard", sq) == pytest.approx(5.0)

    def test_uses_spatial_query_service(self) -> None:
        """_npc_distance делегирует запрос SpatialQueryService."""
        mock_sq = MagicMock()
        mock_sq.player_distances.return_value = {"guard": 12.5}
        assert _npc_distance("guard", mock_sq) == pytest.approx(12.5)
        mock_sq.player_distances.assert_called_once_with(["guard"])

    def test_unknown_npc_returns_999(self) -> None:
        """Неизвестный NPC — SpatialQueryService не знает его → 999."""
        mock_sq = MagicMock()
        mock_sq.player_distances.return_value = {}
        assert _npc_distance("ghost", mock_sq) == 999.0

    def test_none_spatial_query_returns_999(self) -> None:
        """None spatial_query → 999 (защитный fallback)."""
        assert _npc_distance("guard", None) == 999.0


class TestCanSee:

    def test_npc_within_15m_can_see(self) -> None:
        """NPC в 10м видит событие."""
        scene = _scene(
            npc_positions={"npc1": {"x": 10.0, "y": 0.0, "activity": "working"}},
            player_pos={"x": 0.0, "y": 0.0},
        )
        sq = _make_spatial_mock(scene)
        assert _can_see("npc1", sq, "tavern", scene) is True

    def test_npc_beyond_15m_cannot_see(self) -> None:
        """NPC в 20м не видит событие."""
        scene = _scene(
            npc_positions={"npc1": {"x": 20.0, "y": 0.0, "activity": "working"}},
            player_pos={"x": 0.0, "y": 0.0},
        )
        sq = _make_spatial_mock(scene)
        assert _can_see("npc1", sq, "tavern", scene) is False

    def test_sleeping_npc_cannot_see(self) -> None:
        """Спящий NPC не видит даже рядом."""
        scene = _scene(
            npc_positions={"npc1": {"x": 1.0, "y": 0.0, "activity": "sleeping"}},
            player_pos={"x": 0.0, "y": 0.0},
        )
        sq = _make_spatial_mock(scene)
        assert _can_see("npc1", sq, "tavern", scene) is False

    def test_dark_room_npc_cannot_see(self) -> None:
        """В темноте NPC не видит."""
        scene = _scene(
            npc_positions={"npc1": {"x": 2.0, "y": 0.0, "activity": "working"}},
            player_pos={"x": 0.0, "y": 0.0},
            light="dark",
        )
        sq = _make_spatial_mock(scene)
        assert _can_see("npc1", sq, "tavern", scene) is False

    def test_npc_without_coordinates_cannot_see(self) -> None:
        """NPC без координат: дистанция 999 → не видит (ADR-048)."""
        scene = {
            "npc_positions": {"npc1": {"location": "tavern", "activity": "working"}},
            "player_position": {"x": 0.0, "y": 0.0},
            "environment": {"light_level": "bright"},
        }
        sq = _make_spatial_mock(scene)
        assert _can_see("npc1", sq, "tavern", scene) is False


class TestCanHear:

    def test_loud_sound_wakes_sleeping_npc(self) -> None:
        """Звук radius=20 будит спящего NPC в 5м."""
        scene = _scene(
            npc_positions={"npc1": {"x": 5.0, "y": 0.0, "activity": "sleeping"}},
            player_pos={"x": 0.0, "y": 0.0},
        )
        sq = _make_spatial_mock(scene)
        assert _can_hear("npc1", sq, radius=20.0, scene_state=scene) is True

    def test_quiet_sound_does_not_wake_sleeping_npc(self) -> None:
        """Тихий звук radius=5 не будит спящего."""
        scene = _scene(
            npc_positions={"npc1": {"x": 3.0, "y": 0.0, "activity": "sleeping"}},
            player_pos={"x": 0.0, "y": 0.0},
        )
        sq = _make_spatial_mock(scene)
        assert _can_hear("npc1", sq, radius=5.0, scene_state=scene) is False

    def test_awake_npc_hears_within_radius(self) -> None:
        """Бодрствующий NPC слышит звук в пределах радиуса."""
        scene = _scene(
            npc_positions={"npc1": {"x": 8.0, "y": 0.0, "activity": "working"}},
            player_pos={"x": 0.0, "y": 0.0},
        )
        sq = _make_spatial_mock(scene)
        assert _can_hear("npc1", sq, radius=10.0, scene_state=scene) is True
        assert _can_hear("npc1", sq, radius=5.0,  scene_state=scene) is False


class TestFilterIntegration:
    """P2 — интеграционный тест: NPC в радиусе получает событие, дальний — нет."""

    def test_close_npc_perceives_theft_far_does_not(self) -> None:
        """
        NPC в 5м воспринимает кражу, NPC в 20м — нет.
        Проверяет полный путь filter_perceiving_npcs с координатами.
        """
        scene = {
            "npc_positions": {
                "guard_close": {"x": 5.0,  "y": 0.0, "activity": "working",
                                "location": "tavern"},
                "guard_far":   {"x": 20.0, "y": 0.0, "activity": "working",
                                "location": "tavern"},
            },
            "player_position": {"x": 0.0, "y": 0.0},
            "environment": {"light_level": "bright"},
        }
        event = {
            "event_type": "PLAYER_ATTACKED",
            "actor_id":   "player",
            "location":   "tavern",
            "radius":     10.0,
            "visible_to": [],
            "audible_to": [],
        }
        sq = _make_spatial_mock(scene)
        result = filter_perceiving_npcs(
            ["guard_close", "guard_far"], event, scene, sq
        )
        assert "guard_close" in result, "Близкий NPC должен воспринять событие"
        assert "guard_far"   not in result, "Дальний NPC не должен воспринять событие"      


class TestCalculateClarity:

    def test_close_bright_low_stress(self) -> None:
        """Рядом, светло, без стресса → высокая clarity."""
        assert calculate_clarity(3.0, "bright", 10.0) >= 0.9

    def test_far_dim_high_stress(self) -> None:
        """Далеко, темновато, стресс → низкая clarity."""
        assert calculate_clarity(12.0, "dim", 80.0) < 0.5

    def test_dark_caps_at_zero(self) -> None:
        """Экстремальные условия не дают отрицательного результата."""
        result = calculate_clarity(20.0, "dark", 95.0)
        assert result >= 0.0          
