# -*- coding: utf-8 -*-
"""
Тесты Causal Kernel Architecture (ADR-O-201, ФАЗА 0).

Верифицирует:
1. WorldSnapshot: создание из scene_state, immutability (frozen=True),
   изоляция от мутации исходного dict
2. ThickSceneChange: структура, типизация, is_spatial property
3. EquivalenceValidator: классификация drift (5 классов, 4 уровня)

ФАЗА 0: Нулевое изменение поведения системы.
Все тесты работают с чистыми DTO — не требуют запуска симуляции.

Запуск: python -m pytest backend/tests/sandbox/ -v --tb=short
"""

from uuid import UUID

import pytest
from app.domain.identity_events import EffectiveDrives

_MOCK_DRIVES = EffectiveDrives.from_dict({"control": 0.5, "significance": 0.5, "fear": 0.5, "desire": 0.5})

from app.models.thick_scene_change import (
    BoundaryResolution,
    MotionPlan,
    SpatialResolution,
    ThickSceneChange,
    TraversalContract,
)
from app.models.world_snapshot import build_snapshot
from app.services.equivalence_validator import (
    DriftClass,
    DriftLevel,
    EquivalenceValidator,
)

# ── Фикстуры ──────────────────────────────────────────────────────


def _make_scene_state():
    """Минимальный scene_state для тестов (реалистичная структура)."""
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
            "npc_2": {
                "local_position": {"x": 20.0, "y": 15.0},
                "position": "kitchen",
                "activity": "idle",
                "location_id": "tavern",
            },
        },
        "active_traversals": {
            "npc_3": {
                "status": "MOVING",
                "target_node": "exit_east",
                "path_waypoints": [[10.0, 5.0], [50.0, 5.0]],
                "started_tick": 90,
                "duration_ticks": 20,
                "speed": 2.0,
            },
        },
        "spatial_walls": [],
        "spatial_obstacles": [],
    }


# ══════════════════════════════════════════════════════════════════
# WorldSnapshot
# ══════════════════════════════════════════════════════════════════


class TestWorldSnapshot:
    """Верификация: snapshot создаётся из scene_state и immutable."""

    def test_build_snapshot_creates_valid_snapshot(self):
        """Snapshot содержит все данные из scene_state."""
        ss = _make_scene_state()
        snap = build_snapshot(
            tick=100,
            campaign_id="test",
            location_id="tavern",
            spatial_service=None,
            scene_state=ss,
            rng_seed=42,
        )
        assert isinstance(snap.snapshot_id, UUID)
        assert snap.tick == 100
        assert snap.campaign_id == "test"
        assert snap.location_id == "tavern"
        assert len(snap.npc_positions) == 2
        assert len(snap.active_traversals) == 1
        assert snap.rng_seed == 42

    def test_snapshot_npc_positions_is_frozen_copy(self):
        """Мутация исходного scene_state НЕ влияет на snapshot (Rule 125)."""
        ss = _make_scene_state()
        snap = build_snapshot(
            tick=100,
            campaign_id="test",
            location_id="tavern",
            spatial_service=None,
            scene_state=ss,
            rng_seed=0,
        )
        # Мутируем оригинал
        ss["npc_positions"]["npc_1"]["local_position"]["x"] = 999.0
        # Snapshot не изменился — deep copy работает
        assert snap.npc_positions["npc_1"]["local_position"]["x"] == 10.0

    def test_snapshot_active_traversals_is_frozen_copy(self):
        """Мутация исходных traversals НЕ влияет на snapshot."""
        ss = _make_scene_state()
        snap = build_snapshot(
            tick=100,
            campaign_id="test",
            location_id="tavern",
            spatial_service=None,
            scene_state=ss,
            rng_seed=0,
        )
        # Мутируем оригинал
        ss["active_traversals"]["npc_3"]["status"] = "COMPLETED"
        # Snapshot не изменился
        assert snap.active_traversals["npc_3"]["status"] == "MOVING"

    def test_snapshot_is_immutable(self):
        """frozen=True: переназначение полей запрещено (Rule 125)."""
        ss = _make_scene_state()
        snap = build_snapshot(
            tick=100,
            campaign_id="test",
            location_id="tavern",
            spatial_service=None,
            scene_state=ss,
            rng_seed=0,
        )
        with pytest.raises(AttributeError):
            snap.tick = 200  # type: ignore[misc]

    def test_snapshot_handles_empty_scene_state(self):
        """Пустой scene_state не крашит build_snapshot."""
        snap = build_snapshot(
            tick=0,
            campaign_id="empty",
            location_id="void",
            spatial_service=None,
            scene_state={},
            rng_seed=0,
        )
        assert snap.npc_positions == {}
        assert snap.active_traversals == {}
        assert snap.tick == 0

    def test_snapshot_preserves_spatial_service_reference(self):
        """SpatialService передаётся по ссылке (не rebuild)."""

        class FakeSpatialService:
            """Заглушка для проверки reference integrity."""

            marker = "not_rebuilt"

        fake_svc = FakeSpatialService()
        snap = build_snapshot(
            tick=100,
            campaign_id="test",
            location_id="tavern",
            spatial_service=fake_svc,
            scene_state={},
            rng_seed=0,
        )
        # Тот же объект — не копия, не rebuild
        assert snap.spatial_service is fake_svc
        assert snap.spatial_service.marker == "not_rebuilt"


# ══════════════════════════════════════════════════════════════════
# ThickSceneChange
# ══════════════════════════════════════════════════════════════════


class TestThickSceneChange:
    """Верификация: структура контракта и типизация."""

    def _make_thick_change(self):
        """Типичный ThickSceneChange для NPC_POSITION с traversal."""
        return ThickSceneChange(
            change_type="npc_position",
            target="npc_1",
            field="position",
            value="kitchen",
            cause="traversal_complete",
            tick=100,
            target_local_xy=None,
            target_location_id="",
            spatial=SpatialResolution(
                source_location="tavern",
                target_location="tavern",
                source_node="main_hall",
                target_node="kitchen",
                source_xy=(10.0, 5.0),
                target_xy=(20.0, 15.0),
            ),
            motion=MotionPlan(
                is_teleport=False,
                is_path_blocked=False,
                waypoints=((10.0, 5.0), (20.0, 15.0)),
                distance=14.14,
                duration_ticks=8,
                speed=2.0,
            ),
            boundary=BoundaryResolution(
                is_boundary=False,
                neighbor_chunk="",
                entry_node="",
            ),
            traversal=TraversalContract(
                status="NEW",
                fields={
                    "npc_id": "npc_1",
                    "from_node": "main_hall",
                    "target_node": "kitchen",
                    "path_waypoints": [[10.0, 5.0], [20.0, 15.0]],
                    "speed": 2.0,
                    "started_tick": 100,
                    "duration_ticks": 8,
                    "status": "MOVING",
                },
            ),
        )

    def test_thick_change_construction(self):
        """ThickSceneChange создаётся со всеми полями."""
        tc = self._make_thick_change()
        assert tc.target == "npc_1"
        assert tc.spatial.target_node == "kitchen"
        assert tc.motion.distance == pytest.approx(14.14, abs=0.01)
        assert tc.boundary.is_boundary is False
        assert tc.traversal.status == "NEW"

    def test_thick_change_is_spatial(self):
        """is_spatial property: npc_position = True, object_state = False."""
        tc = self._make_thick_change()
        assert tc.is_spatial is True

        non_spatial = ThickSceneChange(
            change_type="object_state",
            target="table_1",
            field="state",
            value="damaged",
            cause="combat",
            tick=100,
        )
        assert non_spatial.is_spatial is False

    def test_thick_change_needs_traversal(self):
        """needs_traversal: NEW и COMPLETED = True, пустой = False."""
        tc = self._make_thick_change()
        assert tc.needs_traversal is True

        no_traversal = ThickSceneChange(
            change_type="npc_position",
            target="npc_1",
            field="position",
            value="kitchen",
            cause="teleport",
            tick=100,
            traversal=TraversalContract(status="", fields={}),
        )
        assert no_traversal.needs_traversal is False

    def test_thick_change_is_immutable(self):
        """frozen=True: переназначение полей запрещено."""
        tc = self._make_thick_change()
        with pytest.raises(AttributeError):
            tc.target = "npc_2"  # type: ignore[misc]

    def test_thick_change_boundary_transition(self):
        """ThickSceneChange для boundary transition (ДОЛГ 6.2)."""
        tc = ThickSceneChange(
            change_type="npc_position",
            target="npc_1",
            field="position",
            value="tavern:entry_west",
            cause="traversal_complete",
            tick=100,
            target_location_id="city_gate",
            spatial=SpatialResolution(
                source_location="tavern",
                target_location="city_gate",
                source_node="tavern:exit_east",
                target_node="city_gate:entry_west",
                source_xy=(50.0, 5.0),
                target_xy=(2.0, 8.0),
            ),
            boundary=BoundaryResolution(
                is_boundary=True,
                neighbor_chunk="city_gate",
                entry_node="city_gate:entry_west",
            ),
        )
        assert tc.boundary.is_boundary is True
        assert tc.boundary.neighbor_chunk == "city_gate"
        assert tc.target_location_id == "city_gate"


# ══════════════════════════════════════════════════════════════════
# EquivalenceValidator
# ══════════════════════════════════════════════════════════════════


class TestEquivalenceValidator:
    """Верификация: классификация drift (5 классов, 4 уровня)."""

    def setup_method(self):
        self.validator = EquivalenceValidator()
        self.snap_id = UUID("12345678-1234-5678-1234-567812345678")

    # ── Class A: Cosmetic ─────────────────────────────────────────

    def test_cosmetic_drift_small_position_diff(self):
        """A: Cosmetic — позиция отличается < 0.5 единиц."""
        drifts = self.validator.validate_position(
            snapshot_id=self.snap_id,
            tick=100,
            npc_id="npc_1",
            legacy_position={"x": 10.0, "y": 5.0},
            shadow_position=(10.1, 5.05),
        )
        assert len(drifts) == 1
        assert drifts[0].drift_class == DriftClass.COSMETIC
        assert drifts[0].drift_level == DriftLevel.PRESENTATION

    # ── Class B: Projection ───────────────────────────────────────

    def test_projection_drift_large_position_diff(self):
        """B: Projection — позиция отличается > 0.5 единиц."""
        drifts = self.validator.validate_position(
            snapshot_id=self.snap_id,
            tick=100,
            npc_id="npc_1",
            legacy_position={"x": 10.0, "y": 5.0},
            shadow_position=(12.0, 7.0),
        )
        assert any(d.drift_class == DriftClass.PROJECTION for d in drifts)

    # ── Class C: Topological ──────────────────────────────────────

    def test_topological_drift_different_nodes(self):
        """C: Topological — разные узлы графа."""
        drifts = self.validator.validate_topology(
            snapshot_id=self.snap_id,
            tick=100,
            npc_id="npc_1",
            legacy_node="kitchen",
            shadow_node="main_hall",
        )
        assert len(drifts) == 1
        assert drifts[0].drift_class == DriftClass.TOPOLOGICAL
        assert drifts[0].drift_level == DriftLevel.TOPOLOGY

    def test_topological_drift_canonical_prefix_normalization(self):
        """C: Topological — canonical ID с префиксом локации (нормализация)."""
        drifts = self.validator.validate_topology(
            snapshot_id=self.snap_id,
            tick=100,
            npc_id="npc_1",
            legacy_node="tavern:kitchen",
            shadow_node="kitchen",
        )
        # После нормализации (убрать префикс) — одинаковые узлы
        assert len(drifts) == 0

    # ── Class D: Causal ───────────────────────────────────────────

    def test_causal_drift_boundary_mismatch(self):
        """D: Causal — legacy boundary, shadow non-boundary."""
        drifts = self.validator.validate_boundary(
            snapshot_id=self.snap_id,
            tick=100,
            npc_id="npc_1",
            legacy_is_boundary=True,
            shadow_is_boundary=False,
            legacy_target_location="city_gate",
            shadow_target_location="",
        )
        assert len(drifts) == 1
        assert drifts[0].drift_class == DriftClass.CAUSAL
        assert drifts[0].drift_level == DriftLevel.CAUSALITY
        assert drifts[0].is_fatal is True

    # ── Class E: Ontological ──────────────────────────────────────

    def test_ontological_drift_npc_missing_in_legacy(self):
        """E: Ontological — NPC отсутствует в legacy, но есть в shadow."""
        drifts = self.validator.validate_position(
            snapshot_id=self.snap_id,
            tick=100,
            npc_id="npc_1",
            legacy_position=None,
            shadow_position=(10.0, 5.0),
        )
        assert len(drifts) == 1
        assert drifts[0].drift_class == DriftClass.ONTOLOGICAL
        assert drifts[0].drift_level == DriftLevel.IDENTITY
        assert drifts[0].is_fatal is True

    def test_ontological_drift_npc_missing_in_shadow(self):
        """E: Ontological — NPC есть в legacy, но отсутствует в shadow."""
        drifts = self.validator.validate_position(
            snapshot_id=self.snap_id,
            tick=100,
            npc_id="npc_1",
            legacy_position={"x": 10.0, "y": 5.0},
            shadow_position=None,
        )
        assert len(drifts) == 1
        assert drifts[0].drift_class == DriftClass.ONTOLOGICAL

    # ── No drift ──────────────────────────────────────────────────

    def test_no_drift_identical_positions(self):
        """Нет drift при идентичных позициях."""
        drifts = self.validator.validate_position(
            snapshot_id=self.snap_id,
            tick=100,
            npc_id="npc_1",
            legacy_position={"x": 10.0, "y": 5.0},
            shadow_position=(10.0, 5.0),
        )
        assert len(drifts) == 0

    def test_no_drift_both_missing(self):
        """Нет drift когда NPC отсутствует в обоих."""
        drifts = self.validator.validate_position(
            snapshot_id=self.snap_id,
            tick=100,
            npc_id="npc_1",
            legacy_position=None,
            shadow_position=None,
        )
        assert len(drifts) == 0

    def test_no_drift_same_boundary(self):
        """Нет drift при одинаковых boundary resolutions."""
        drifts = self.validator.validate_boundary(
            snapshot_id=self.snap_id,
            tick=100,
            npc_id="npc_1",
            legacy_is_boundary=True,
            shadow_is_boundary=True,
            legacy_target_location="city_gate",
            shadow_target_location="city_gate",
        )
        assert len(drifts) == 0
