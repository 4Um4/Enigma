# -*- coding: utf-8 -*-
"""
Тесты EventCompiler shadow mode (ADR-O-201, ФАЗА 0).

Верифицирует:
1. Passthrough не-пространственных изменений
2. Компиляция NPC_POSITION field='position' (traversal creation)
3. Boundary snap (кросс-локационное перемещение)
4. Ghost Position Interpolation (source_xy из активного транзита)
5. Deterministic jitter (воспроизводимость)
6. Teleport detection (микро-перемещение < 0.1)
7. Wall blocking + pathfinding
8. Node not found → None
9. local_position update

ФАЗА 0: EventCompiler не влияет на симуляцию.
Все тесты работают с чистыми DTO + минимальным SpatialService.

Запуск: python -m pytest backend/tests/sandbox/micro/test_event_compiler.py -v --tb=short
"""
import copy
import pytest

from app.models.spatial_contracts import NodeRef, NodeRole
from app.models.world_snapshot import WorldSnapshot, build_snapshot
from app.models.thick_scene_change import (
    ThickSceneChange, SpatialResolution, MotionPlan,
    BoundaryResolution, TraversalContract,
)
from app.services.scene_change import SceneChange, ChangeType
from app.services.event_compiler import EventCompiler


# ── Фикстуры ──────────────────────────────────────────────────────

def _make_node(node_id: str, role: NodeRole, x: float, y: float,
               zone_id: str = "tavern", tags: list = None) -> NodeRef:
    return NodeRef(
        node_id=node_id, role=role, x=x, y=y,
        zone_id=zone_id, tags=tags or [],
    )


def _make_test_spatial_service():
    """Минимальный SpatialService для тестов EventCompiler."""
    from app.services.spatial.spatial_service import SpatialService

    graph = {
        "tavern:main_hall": _make_node("tavern:main_hall", NodeRole.DEFAULT, 10.0, 5.0),
        "tavern:kitchen": _make_node("tavern:kitchen", NodeRole.DEFAULT, 30.0, 15.0),
        "tavern:exit_east": _make_node(
            "tavern:exit_east", NodeRole.BOUNDARY, 50.0, 10.0,
            tags=["boundary:exit", "direction:east", "neighbor_chunk:city_gate"],
        ),
        "city_gate:entry_west": _make_node(
            "city_gate:entry_west", NodeRole.ENTRANCE, 2.0, 8.0,
            zone_id="city_gate",
        ),
    }
    connections = {
        "tavern:main_hall": ["tavern:kitchen", "tavern:exit_east"],
        "tavern:kitchen": ["tavern:main_hall"],
        "tavern:exit_east": ["tavern:main_hall"],
        "city_gate:entry_west": [],
    }
    alias_map = {
        "main_hall": "tavern:main_hall",
        "kitchen": "tavern:kitchen",
        "exit_east": "tavern:exit_east",
        "entry_west": "city_gate:entry_west",
    }
    boundary_map = {
        "tavern:exit_east": {
            "neighbor_chunk": "city_gate",
            "entry_node_hint": "city_gate:entry_west",
            "entry_direction": "west",
        },
    }
    from app.models.spatial_contracts import SpatialOverlay
    overlay = SpatialOverlay()
    return SpatialService(graph, connections, alias_map, overlay, location_id="tavern", boundary_map=boundary_map)


def _make_scene_state():
    """Минимальный scene_state для тестов."""
    return {
        "location_id": "tavern",
        "tick": 100,
        "npc_positions": {
            "npc_1": {
                "local_position": {"x": 10.0, "y": 5.0},
                "position": "tavern:main_hall",
                "activity": "working",
                "location_id": "tavern",
            },
        },
        "active_traversals": {},
        "spatial_walls": [],
        "spatial_obstacles": [],
    }


def _make_snapshot(scene_state=None, spatial_service=None, rng_seed=42):
    """Строит WorldSnapshot для тестов."""
    ss = scene_state or _make_scene_state()
    svc = spatial_service if spatial_service is not None else _make_test_spatial_service()
    return build_snapshot(
        tick=ss.get("tick", 100),
        campaign_id="test",
        location_id=ss.get("location_id", "tavern"),
        spatial_service=svc,
        scene_state=ss,
        rng_seed=rng_seed,
    )


# ══════════════════════════════════════════════════════════════════
# EventCompiler Tests
# ══════════════════════════════════════════════════════════════════

class TestEventCompilerPassthrough:
    """Не-пространственные изменения проходят без компиляции."""

    def test_object_state_passthrough(self):
        """OBJECT_STATE change → ThickSceneChange без spatial."""
        compiler = EventCompiler()
        snap = _make_snapshot()
        change = SceneChange(
            type=ChangeType.OBJECT_STATE,
            target="table_1",
            field="state",
            value="damaged",
            cause="combat",
            tick=100,
        )
        result = compiler.compile(snap, change)
        assert result is not None
        assert result.is_spatial is False
        assert result.spatial is None
        assert result.traversal is None

    def test_non_scene_change_returns_none(self):
        """Не-SceneChange объект → None."""
        compiler = EventCompiler()
        snap = _make_snapshot()
        result = compiler.compile(snap, "not_a_change")  # type: ignore
        assert result is None


class TestEventCompilerLocalPosition:
    """NPC_POSITION field='local_position' — простой xy update."""

    def test_local_position_update(self):
        """local_position → ThickSceneChange с teleport=True."""
        compiler = EventCompiler()
        snap = _make_snapshot()
        change = SceneChange(
            type=ChangeType.NPC_POSITION,
            target="npc_1",
            field="local_position",
            value={"x": 30.0, "y": 15.0},
            cause="traversal_complete",
            tick=100,
        )
        result = compiler.compile(snap, change)
        assert result is not None
        assert result.spatial is not None
        assert result.spatial.target_xy == (30.0, 15.0)
        assert result.motion is not None
        assert result.motion.is_teleport is True


class TestEventCompilerPositionChange:
    """NPC_POSITION field='position' — полная компиляция."""

    def test_simple_movement_creates_traversal(self):
        """Движение в пределах локации → traversal NEW."""
        compiler = EventCompiler()
        snap = _make_snapshot()
        change = SceneChange(
            type=ChangeType.NPC_POSITION,
            target="npc_1",
            field="position",
            value="kitchen",
            cause="schedule",
            tick=100,
        )
        result = compiler.compile(snap, change)
        assert result is not None
        assert result.is_spatial is True
        assert result.spatial is not None
        assert result.spatial.target_node == "tavern:kitchen"
        assert result.traversal is not None
        assert result.traversal.status == "NEW"
        assert result.traversal.fields["status"] == "MOVING"
        assert result.traversal.fields["duration_ticks"] > 0

    def test_node_not_found_returns_none(self):
        """Несуществующий узел → None (как apply_change returning False)."""
        compiler = EventCompiler()
        snap = _make_snapshot()
        change = SceneChange(
            type=ChangeType.NPC_POSITION,
            target="npc_1",
            field="position",
            value="nonexistent_room",
            cause="schedule",
            tick=100,
        )
        result = compiler.compile(snap, change)
        assert result is None

    def test_no_spatial_service_returns_none(self):
        """Нет spatial_service в snapshot → None."""
        compiler = EventCompiler()
        # Строим snapshot напрямую без spatial_service (не через _make_snapshot,
        # который подставляет дефолтный сервис)
        from app.models.world_snapshot import build_snapshot
        ss = _make_scene_state()
        snap = build_snapshot(
            tick=100, campaign_id="test", location_id="tavern",
            spatial_service=None, scene_state=ss, rng_seed=42,
        )
        change = SceneChange(
            type=ChangeType.NPC_POSITION,
            target="npc_1",
            field="position",
            value="kitchen",
            cause="schedule",
            tick=100,
        )
        result = compiler.compile(snap, change)
        assert result is None

    def test_target_local_xy_used_as_target(self):
        """target_local_xy в SceneChange → точные координаты цели."""
        compiler = EventCompiler()
        snap = _make_snapshot()
        change = SceneChange(
            type=ChangeType.NPC_POSITION,
            target="npc_1",
            field="position",
            value="kitchen",
            cause="reactive:approach",
            tick=100,
            target_local_xy=(25.0, 12.0),
        )
        result = compiler.compile(snap, change)
        assert result is not None
        # target_local_xy используется вместо jitter
        assert result.spatial.target_xy == (25.0, 12.0)

    def test_deterministic_jitter_reproducible(self):
        """Одинаковый rng_seed → одинаковый jitter (Rule 118)."""
        compiler = EventCompiler()
        snap1 = _make_snapshot(rng_seed=42)
        snap2 = _make_snapshot(rng_seed=42)
        change = SceneChange(
            type=ChangeType.NPC_POSITION,
            target="npc_1",
            field="position",
            value="kitchen",
            cause="schedule",
            tick=100,
        )
        result1 = compiler.compile(snap1, change)
        result2 = compiler.compile(snap2, change)
        assert result1 is not None and result2 is not None
        # Одинаковый seed → одинаковый target_xy
        assert result1.spatial.target_xy == result2.spatial.target_xy

    def test_different_seed_different_jitter(self):
        """Разный rng_seed → разный jitter."""
        compiler = EventCompiler()
        snap_a = _make_snapshot(rng_seed=42)
        snap_b = _make_snapshot(rng_seed=99)
        change = SceneChange(
            type=ChangeType.NPC_POSITION,
            target="npc_1",
            field="position",
            value="kitchen",
            cause="schedule",
            tick=100,
        )
        result_a = compiler.compile(snap_a, change)
        result_b = compiler.compile(snap_b, change)
        assert result_a is not None and result_b is not None
        # Разный seed → разный jitter (почти наверняка)
        assert result_a.spatial.target_xy != result_b.spatial.target_xy


class TestEventCompilerTeleport:
    """Микро-перемещение (< 0.1) → teleport, без traversal."""

    def test_teleport_no_traversal(self):
        """Расстояние < 0.1 → is_teleport=True, traversal=None."""
        compiler = EventCompiler()
        # NPC уже в kitchen (30, 15), target тоже kitchen
        ss = _make_scene_state()
        ss["npc_positions"]["npc_1"]["local_position"] = {"x": 30.0, "y": 15.0}
        snap = _make_snapshot(scene_state=ss)
        change = SceneChange(
            type=ChangeType.NPC_POSITION,
            target="npc_1",
            field="position",
            value="kitchen",
            cause="micro_move",
            tick=100,
            target_local_xy=(30.05, 15.03),  # < 0.1 distance
        )
        result = compiler.compile(snap, change)
        assert result is not None
        assert result.motion is not None
        assert result.motion.is_teleport is True


class TestEventCompilerBoundarySnap:
    """Кросс-локационное перемещение (ДОЛГ 6.2)."""

    def test_boundary_snap_with_target_location_id(self):
        """target_location_id != location_id → boundary snap."""
        compiler = EventCompiler()
        snap = _make_snapshot()
        change = SceneChange(
            type=ChangeType.NPC_POSITION,
            target="npc_1",
            field="position",
            value="city_gate:entry_west",
            cause="traversal_complete",
            tick=100,
            target_location_id="city_gate",
        )
        result = compiler.compile(snap, change)
        assert result is not None
        assert result.boundary is not None
        assert result.spatial.target_location == "city_gate"
        assert result.spatial.source_location == "tavern"

    def test_boundary_node_resolves_info(self):
        """Boundary node → is_boundary=True, neighbor_chunk заполнен.

        В legacy pipeline boundary resolution происходит при ЗАВЕРШЕНИИ traversal:
        _process_traversals заполняет target_location_id и отправляет SceneChange
        с value=boundary_node_id. EventCompiler видит target_location_id != location_id
        и переходит в _compile_boundary_snap.
        """
        compiler = EventCompiler()
        snap = _make_snapshot()
        # Traversal completed at boundary node — _process_traversals style
        change = SceneChange(
            type=ChangeType.NPC_POSITION,
            target="npc_1",
            field="position",
            value="tavern:exit_east",
            cause="traversal_complete",
            tick=100,
            target_location_id="city_gate",
        )
        result = compiler.compile(snap, change)
        assert result is not None
        assert result.boundary is not None
        assert result.boundary.is_boundary is True
        assert result.boundary.neighbor_chunk == "city_gate"
        assert result.boundary.entry_node == "city_gate:entry_west"


class TestEventCompilerGhostInterpolation:
    """Ghost Position Interpolation — source_xy из активного транзита."""

    def test_active_traversal_interpolated_source(self):
        """NPC с активным транзитом → source_xy интерполирована."""
        compiler = EventCompiler()
        ss = _make_scene_state()
        # NPC в движении 50% прогресса
        ss["active_traversals"]["npc_1"] = {
            "status": "MOVING",
            "path_waypoints": [[10.0, 5.0], [30.0, 15.0]],
            "started_tick": 90,
            "duration_ticks": 20,
            "speed": 2.0,
            "target_node": "kitchen",
        }
        ss["tick"] = 100  # 50% прогресс
        snap = _make_snapshot(scene_state=ss)
        change = SceneChange(
            type=ChangeType.NPC_POSITION,
            target="npc_1",
            field="position",
            value="exit_east",
            cause="reactive:flee",
            tick=100,
        )
        result = compiler.compile(snap, change)
        assert result is not None
        # source_xy ≈ (20.0, 10.0) — интерполяция 50%
        sx, sy = result.spatial.source_xy
        assert 19.0 < sx < 21.0  # допускаем небольшую погрешность
        assert 9.0 < sy < 11.0


class TestEventCompilerTraversalContract:
    """Traversal contract — полная спецификация для ProjectionEngine."""

    def test_traversal_fields_match_legacy(self):
        """Поля traversal совпадают с legacy traversal_dict."""
        compiler = EventCompiler()
        snap = _make_snapshot()
        change = SceneChange(
            type=ChangeType.NPC_POSITION,
            target="npc_1",
            field="position",
            value="kitchen",
            cause="schedule",
            tick=100,
        )
        result = compiler.compile(snap, change)
        assert result is not None
        assert result.traversal is not None
        fields = result.traversal.fields
        # Все ключи legacy traversal_dict
        assert "npc_id" in fields
        assert "from_node" in fields
        assert "target_node" in fields
        assert "path_waypoints" in fields
        assert "speed" in fields
        assert "started_tick" in fields
        assert "duration_ticks" in fields
        assert "status" in fields
        assert fields["npc_id"] == "npc_1"
        assert fields["target_node"] == "kitchen"
        assert fields["status"] == "MOVING"
        assert fields["speed"] == 2.0

    def test_traversal_waypoints_include_source_and_target(self):
        """Waypoints начинаются с source_xy и заканчиваются target_xy."""
        compiler = EventCompiler()
        snap = _make_snapshot()
        change = SceneChange(
            type=ChangeType.NPC_POSITION,
            target="npc_1",
            field="position",
            value="kitchen",
            cause="schedule",
            tick=100,
        )
        result = compiler.compile(snap, change)
        assert result is not None
        wp = result.traversal.fields["path_waypoints"]
        # Первый waypoint ≈ source, последний ≈ target
        assert len(wp) >= 2
        # Source: (10, 5) — позиция npc_1
        assert abs(wp[0][0] - 10.0) < 1.0
        assert abs(wp[0][1] - 5.0) < 1.0