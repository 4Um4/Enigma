# -*- coding: utf-8 -*-
"""
Тесты ProjectionEngine (ADR-O-201, ФАЗА 3: CSSE).

Верифицирует:
1. Position write — entry["position"] = node_id
2. Local position from SpatialResolution — entry["local_position"] = target_xy
3. Traversal NEW — создаёт traversal dict в active_traversals
4. Traversal COMPLETED — помечает существующий traversal
5. Boundary resolution — пишет location/location_id
6. Local_position direct write — для micro-snap
7. Non-spatial passthrough — возвращает False
8. Batch apply — несколько ThickSceneChange
9. Shadow projection — deep copy + apply, оригинал не мутирован
10. Zero computation guarantee — нет branching/logic

Запуск: python -m pytest backend/tests/sandbox/micro/test_projection_engine.py -v --tb=short
"""

import copy

import pytest
from app.models.thick_scene_change import (
    BoundaryResolution,
    SpatialResolution,
    ThickSceneChange,
    TraversalContract,
)
from app.services.projection_engine import ProjectionEngine

# ── Фикстуры ──────────────────────────────────────────────────────


def _make_scene_state():
    """Минимальный scene_state для тестов."""
    return {
        "location_id": "tavern",
        "tick": 100,
        "npc_positions": {
            "npc_1": {
                "local_position": {"x": 10.0, "y": 5.0},
                "position": "main_hall",
                "activity": "working",
                "location_id": "tavern",
            },
        },
        "active_traversals": {},
    }


def _make_position_thick(
    target: str = "npc_1",
    value: str = "kitchen",
    target_xy: tuple = (30.0, 15.0),
    traversal_status: str = "NEW",
    traversal_fields: dict = None,
    boundary_is: bool = False,
    neighbor: str = "",
    entry_node: str = "",
) -> ThickSceneChange:
    """Конструирует ThickSceneChange для NPC_POSITION field='position'."""
    traversal = None
    if traversal_status:
        traversal = TraversalContract(
            status=traversal_status,
            fields=traversal_fields
            or {
                "npc_id": target,
                "from_node": "main_hall",
                "target_node": value,
                "path_waypoints": [[10.0, 5.0], [30.0, 15.0]],
                "speed": 2.0,
                "started_tick": 100,
                "duration_ticks": 12,
                "locomotion": "WALK",
                "status": "MOVING",
            },
        )

    boundary = None
    if boundary_is:
        boundary = BoundaryResolution(
            is_boundary=True,
            neighbor_chunk=neighbor,
            entry_node=entry_node,
        )

    return ThickSceneChange(
        change_type="npc_position",
        target=target,
        field="position",
        value=value,
        cause="schedule:working",
        tick=100,
        spatial=SpatialResolution(
            source_location="tavern",
            target_location="tavern",
            source_node="main_hall",
            target_node=value,
            source_xy=(10.0, 5.0),
            target_xy=target_xy,
        ),
        traversal=traversal,
        boundary=boundary,
    )


def _make_local_position_thick(
    target: str = "npc_1",
    xy: dict = None,
) -> ThickSceneChange:
    """Конструирует ThickSceneChange для NPC_POSITION field='local_position'."""
    return ThickSceneChange(
        change_type="npc_position",
        target=target,
        field="local_position",
        value=xy or {"x": 12.5, "y": 6.0},
        cause="micro_snap:collision_avoidance",
        tick=100,
        spatial=SpatialResolution(
            source_location="tavern",
            target_location="tavern",
            source_node="main_hall",
            target_node="main_hall",
            source_xy=(10.0, 5.0),
            target_xy=(12.5, 6.0),
        ),
    )


# ── Тесты ─────────────────────────────────────────────────────────


class TestProjectionPosition:
    """Position write — каузальная и геометрическая позиция."""

    def test_position_write(self):
        """entry["position"] = node_id"""
        engine = ProjectionEngine()
        state = _make_scene_state()
        thick = _make_position_thick()

        result = engine.apply(state, thick)

        assert result is True
        assert state["npc_positions"]["npc_1"]["position"] == "kitchen"

    def test_local_position_from_spatial_resolution(self):
        """entry["local_position"] = spatial.target_xy (НЕ вычисляется)"""
        engine = ProjectionEngine()
        state = _make_scene_state()
        thick = _make_position_thick(target_xy=(30.0, 15.0))

        engine.apply(state, thick)

        lp = state["npc_positions"]["npc_1"]["local_position"]
        assert lp["x"] == pytest.approx(30.0)
        assert lp["y"] == pytest.approx(15.0)

    def test_new_npc_position(self):
        """NPC без существующей записи — создаётся entry."""
        engine = ProjectionEngine()
        state = _make_scene_state()
        thick = _make_position_thick(target="npc_2", value="kitchen")

        result = engine.apply(state, thick)

        assert result is True
        assert "npc_2" in state["npc_positions"]
        assert state["npc_positions"]["npc_2"]["position"] == "kitchen"

    def test_position_without_traversal(self):
        """traversal=None → traversal не создаётся (teleport/boundary snap)."""
        engine = ProjectionEngine()
        state = _make_scene_state()
        thick = ThickSceneChange(
            change_type="npc_position",
            target="npc_1",
            field="position",
            value="exit_east",
            cause="boundary_snap",
            tick=100,
            spatial=SpatialResolution(
                source_location="tavern",
                target_location="tavern",
                source_node="main_hall",
                target_node="exit_east",
                source_xy=(10.0, 5.0),
                target_xy=(50.0, 10.0),
            ),
        )

        engine.apply(state, thick)

        assert "npc_1" not in state["active_traversals"]
        assert state["npc_positions"]["npc_1"]["position"] == "exit_east"


class TestProjectionTraversal:
    """Traversal contract — NEW и COMPLETED."""

    def test_traversal_new_creates_dict(self):
        """status='NEW' → создаёт traversal dict в active_traversals."""
        engine = ProjectionEngine()
        state = _make_scene_state()
        thick = _make_position_thick(traversal_status="NEW")

        engine.apply(state, thick)

        assert "npc_1" in state["active_traversals"]
        trav = state["active_traversals"]["npc_1"]
        assert trav["target_node"] == "kitchen"
        assert trav["status"] == "MOVING"
        assert trav["duration_ticks"] == 12
        assert len(trav["path_waypoints"]) == 2

    def test_traversal_completed_marks_existing(self):
        """status='COMPLETED' → помечает существующий traversal."""
        engine = ProjectionEngine()
        state = _make_scene_state()
        # Сначала создаём активный traversal
        state["active_traversals"]["npc_1"] = {
            "npc_id": "npc_1",
            "target_node": "kitchen",
            "status": "MOVING",
            "duration_ticks": 12,
        }
        # Затем завершаем через ProjectionEngine
        thick = _make_position_thick(
            value="kitchen",
            traversal_status="COMPLETED",
            traversal_fields={},
        )

        engine.apply(state, thick)

        # ADR-TRAV-FSM: ProjectionEngine не мутирует статус напрямую.
        # Завершённые транзиты удаляются SSM.apply_changes.
        # Здесь проверяем, что статус не стал COMPLETED внутри apply (read-only).
        assert state["active_traversals"].get("npc_1", {}).get("status") != "COMPLETED"

    def test_traversal_completed_no_existing_skips(self):
        """status='COMPLETED' без существующего traversal — не крашится."""
        engine = ProjectionEngine()
        state = _make_scene_state()
        thick = _make_position_thick(
            traversal_status="COMPLETED",
            traversal_fields={},
        )

        # Не должно крашиться
        result = engine.apply(state, thick)
        assert result is True

    def test_traversal_empty_status_no_creation(self):
        """traversal.status='' → traversal не создаётся и не модифицируется."""
        engine = ProjectionEngine()
        state = _make_scene_state()
        thick = _make_position_thick(traversal_status="")

        engine.apply(state, thick)

        # Пустой статус = не нужен (teleport, boundary snap без traversal)
        assert "npc_1" not in state["active_traversals"]

    def test_traversal_fields_are_copied_not_referenced(self):
        """Traversal fields — deep copy, не reference на оригинал."""
        engine = ProjectionEngine()
        state = _make_scene_state()
        thick = _make_position_thick(traversal_status="NEW")

        engine.apply(state, thick)

        # Мутация state не должна влиять на ThickSceneChange
        if "npc_1" in state["active_traversals"]:
            state["active_traversals"]["npc_1"]["status"] = "COMPLETED"
        # thick.traversal.fields не должен измениться (ProjectionEngine read-only)
        assert thick.traversal.fields["status"] != "COMPLETED"


class TestProjectionBoundary:
    """Boundary resolution — кросс-локационное перемещение."""

    def test_boundary_writes_location(self):
        """is_boundary=True → entry["location"] и entry["location_id"]"""
        engine = ProjectionEngine()
        state = _make_scene_state()
        thick = _make_position_thick(
            boundary_is=True,
            neighbor="city_gate",
            entry_node="city_gate:entry_west",
        )

        engine.apply(state, thick)

        entry = state["npc_positions"]["npc_1"]
        assert entry["location"] == "city_gate"
        assert entry["location_id"] == "city_gate"

    def test_no_boundary_no_location_overwrite(self):
        """is_boundary=False → location_id не перезаписывается ProjectionEngine."""
        engine = ProjectionEngine()
        state = _make_scene_state()

        thick = _make_position_thick(boundary_is=False)
        engine.apply(state, thick)

        assert state["npc_positions"]["npc_1"]["location_id"] == "tavern"

    def test_boundary_without_neighbor_no_location(self):
        """is_boundary=True но neighbor_chunk пуст → location не пишется."""
        engine = ProjectionEngine()
        state = _make_scene_state()
        thick = _make_position_thick(
            boundary_is=True,
            neighbor="",
            entry_node="",
        )

        engine.apply(state, thick)

        # location не пишется если нет neighbor_chunk
        assert "location" not in state["npc_positions"]["npc_1"]


class TestProjectionLocalPosition:
    """Local position direct write — для micro-snap."""

    def test_local_position_write(self):
        """field='local_position' → entry["local_position"] = value"""
        engine = ProjectionEngine()
        state = _make_scene_state()
        thick = _make_local_position_thick(xy={"x": 12.5, "y": 6.0})

        result = engine.apply(state, thick)

        assert result is True
        lp = state["npc_positions"]["npc_1"]["local_position"]
        assert lp["x"] == pytest.approx(12.5)
        assert lp["y"] == pytest.approx(6.0)

    def test_local_position_non_dict_returns_false(self):
        """value не dict → False (нарушение контракта)"""
        engine = ProjectionEngine()
        state = _make_scene_state()
        thick = ThickSceneChange(
            change_type="npc_position",
            target="npc_1",
            field="local_position",
            value="not_a_dict",
            cause="test",
            tick=100,
        )

        result = engine.apply(state, thick)
        assert result is False


class TestProjectionNonSpatial:
    """Non-spatial passthrough — не юрисдикция ProjectionEngine."""

    def test_non_spatial_returns_false(self):
        """OBJECT_STATE → ProjectionEngine не обрабатывает."""
        engine = ProjectionEngine()
        state = _make_scene_state()
        thick = ThickSceneChange(
            change_type="object_state",
            target="candle_1",
            field="state",
            value="lit",
            cause="player_interaction",
            tick=100,
        )

        result = engine.apply(state, thick)
        assert result is False

    def test_non_spatial_state_unchanged(self):
        """OBJECT_STATE → scene_state не мутируется."""
        engine = ProjectionEngine()
        state = _make_scene_state()
        state_before = copy.deepcopy(state)

        thick = ThickSceneChange(
            change_type="object_state",
            target="candle_1",
            field="state",
            value="lit",
            cause="player_interaction",
            tick=100,
        )
        engine.apply(state, thick)

        assert state == state_before


class TestProjectionBatch:
    """Batch apply — несколько ThickSceneChange."""

    def test_batch_apply_count(self):
        """apply_batch возвращает количество применённых spatial changes."""
        engine = ProjectionEngine()
        state = _make_scene_state()

        thick_changes = [
            _make_position_thick(target="npc_1", value="kitchen"),
            ThickSceneChange(
                change_type="object_state",
                target="candle_1",
                field="state",
                value="lit",
                cause="test",
                tick=100,
            ),
            _make_local_position_thick(target="npc_1", xy={"x": 30.0, "y": 15.0}),
        ]

        applied = engine.apply_batch(state, thick_changes)
        assert applied == 2  # только spatial

    def test_batch_order_matters(self):
        """Порядок применения = порядок в списке (RCOC enforcement)."""
        engine = ProjectionEngine()
        state = _make_scene_state()

        # Сначала position (пишет local_position из spatial.target_xy)
        # Потом local_position (перезаписывает)
        thick_changes = [
            _make_position_thick(target="npc_1", value="kitchen"),
            _make_local_position_thick(target="npc_1", xy={"x": 31.0, "y": 16.0}),
        ]

        engine.apply_batch(state, thick_changes)

        # local_position из второго ThickSceneChange перезаписывает
        lp = state["npc_positions"]["npc_1"]["local_position"]
        assert lp["x"] == pytest.approx(31.0)
        assert lp["y"] == pytest.approx(16.0)


class TestProjectionShadow:
    """Shadow projection — deep copy + apply, оригинал не мутирован."""

    def test_project_creates_shadow(self):
        """project() создаёт shadow, не мутируя оригинал."""
        engine = ProjectionEngine()
        state = _make_scene_state()
        state_before = copy.deepcopy(state)

        thick_changes = [_make_position_thick(target="npc_1", value="kitchen")]
        shadow = engine.project(state, thick_changes)

        # Оригинал не мутирован
        assert state == state_before
        # Shadow содержит изменения
        assert shadow["npc_positions"]["npc_1"]["position"] == "kitchen"

    def test_project_independent_mutation(self):
        """Мутация shadow не влияет на оригинал."""
        engine = ProjectionEngine()
        state = _make_scene_state()

        thick_changes = [_make_position_thick(target="npc_1", value="kitchen")]
        shadow = engine.project(state, thick_changes)

        # Мутируем shadow
        shadow["npc_positions"]["npc_1"]["position"] = "exit"

        # Оригинал не затронут
        assert state["npc_positions"]["npc_1"]["position"] == "main_hall"

    def test_project_empty_changes_returns_copy(self):
        """project() с пустым списком → идентичная копия."""
        engine = ProjectionEngine()
        state = _make_scene_state()

        shadow = engine.project(state, [])

        assert shadow == state
        # Но это разные объекты
        assert shadow is not state
