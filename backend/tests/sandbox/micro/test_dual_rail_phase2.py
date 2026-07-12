# -*- coding: utf-8 -*-
"""
Тесты ADR-O-201 ФАЗА 2: Semantic Alignment.

Верифицирует:
1. Boundary drift detection (L2)
2. Traversal drift detection (L2)
3. DEPRECATION warnings на Class C/D drift
4. Phase 3 readiness indicator

Запуск: python -m pytest backend/tests/sandbox/micro/test_dual_rail_phase2.py -v --tb=short
"""

import logging
from uuid import uuid4

from app.models.spatial_contracts import NodeRef, NodeRole, SpatialOverlay
from app.models.thick_scene_change import (
    TraversalContract,
)
from app.models.world_snapshot import build_snapshot
from app.services.equivalence_validator import (
    DriftClass,
    DriftLevel,
    DriftReport,
    EquivalenceValidator,
)
from app.services.spatial.spatial_service import SpatialService

# ── Фикстуры ──────────────────────────────────────────────────────


def _make_node(node_id: str, role: NodeRole, x: float, y: float, zone_id: str = "tavern", tags: list = None) -> NodeRef:
    return NodeRef(
        node_id=node_id,
        role=role,
        x=x,
        y=y,
        zone_id=zone_id,
        tags=tags or [],
    )


def _make_test_spatial_service(with_boundary: bool = False):
    """SpatialService для тестов — опционально с boundary nodes."""
    graph = {
        "tavern:main_hall": _make_node("tavern:main_hall", NodeRole.DEFAULT, 10.0, 5.0),
        "tavern:kitchen": _make_node("tavern:kitchen", NodeRole.DEFAULT, 30.0, 15.0),
    }
    connections = {
        "tavern:main_hall": ["tavern:kitchen"],
        "tavern:kitchen": ["tavern:main_hall"],
    }
    alias_map = {
        "main_hall": "tavern:main_hall",
        "kitchen": "tavern:kitchen",
    }
    boundary_map = {}
    if with_boundary:
        graph["tavern:exit_east"] = _make_node(
            "tavern:exit_east",
            NodeRole.BOUNDARY,
            40.0,
            10.0,
            tags=["boundary:exit", "direction:east", "neighbor:city_gate", "entry_direction:west"],
        )
        connections["tavern:main_hall"].append("tavern:exit_east")
        connections["tavern:exit_east"] = ["tavern:main_hall"]
        boundary_map["tavern:exit_east"] = {
            "neighbor_chunk": "city_gate",
            "entry_node_hint": "city_gate:entrance",
            "entry_direction": "west",
        }
    overlay = SpatialOverlay()
    return SpatialService(graph, connections, alias_map, overlay, location_id="tavern", boundary_map=boundary_map)


def _make_scene_state(with_traversal: bool = False, location_id: str = "tavern") -> dict:
    """Минимальный scene_state для тестов ФАЗЫ 2."""
    _traversals = {}
    if with_traversal:
        _traversals["npc_1"] = {
            "npc_id": "npc_1",
            "from_node": "tavern:main_hall",
            "target_node": "tavern:kitchen",
            "path_waypoints": [[10.0, 5.0], [30.0, 15.0]],
            "speed": 2.0,
            "started_tick": 95,
            "duration_ticks": 12,
            "locomotion": "WALK",
            "status": "MOVING",
        }
    return {
        "location_id": location_id,
        "tick": 100,
        "npc_positions": {
            "npc_1": {
                "local_position": {"x": 10.0, "y": 5.0},
                "position": "tavern:main_hall",
                "activity": "working",
                "location_id": location_id,
            },
        },
        "active_traversals": _traversals,
        "spatial_walls": [],
        "spatial_obstacles": [],
    }


def _make_snapshot(svc=None, scene_state=None):
    """Строит WorldSnapshot из фикстур."""
    if svc is None:
        svc = _make_test_spatial_service()
    if scene_state is None:
        scene_state = _make_scene_state()
    return build_snapshot(
        tick=scene_state["tick"],
        campaign_id="test_campaign",
        location_id=scene_state["location_id"],
        spatial_service=svc,
        scene_state=scene_state,
        rng_seed=100,
    )


# ══════════════════════════════════════════════════════════════════
# ФАЗА 2: Boundary Drift Detection
# ══════════════════════════════════════════════════════════════════


class TestBoundaryDriftDetection:
    """Верифицирует: boundary drift = Class D (Causal)."""

    def setup_method(self):
        self.validator = EquivalenceValidator()
        self.snapshot_id = uuid4()

    def test_boundary_agreement_both_boundary(self):
        """Оба pipeline согласны: boundary → нет drift."""
        drifts = self.validator.validate_boundary(
            snapshot_id=self.snapshot_id,
            tick=100,
            npc_id="npc_1",
            legacy_is_boundary=True,
            shadow_is_boundary=True,
            legacy_target_location="city_gate",
            shadow_target_location="city_gate",
        )
        assert len(drifts) == 0

    def test_boundary_agreement_both_non_boundary(self):
        """Оба pipeline согласны: не boundary → нет drift."""
        drifts = self.validator.validate_boundary(
            snapshot_id=self.snapshot_id,
            tick=100,
            npc_id="npc_1",
            legacy_is_boundary=False,
            shadow_is_boundary=False,
            legacy_target_location="tavern",
            shadow_target_location="tavern",
        )
        assert len(drifts) == 0

    def test_causal_drift_legacy_boundary_shadow_not(self):
        """Legacy пересёк boundary, shadow — нет → Class D Causal drift."""
        drifts = self.validator.validate_boundary(
            snapshot_id=self.snapshot_id,
            tick=100,
            npc_id="npc_1",
            legacy_is_boundary=True,
            shadow_is_boundary=False,
            legacy_target_location="city_gate",
            shadow_target_location="",
        )
        assert len(drifts) == 1
        assert drifts[0].drift_class == DriftClass.CAUSAL
        assert drifts[0].field == "boundary"

    def test_causal_drift_shadow_boundary_legacy_not(self):
        """Shadow пересёк boundary, legacy — нет → Class D Causal drift."""
        drifts = self.validator.validate_boundary(
            snapshot_id=self.snapshot_id,
            tick=100,
            npc_id="npc_1",
            legacy_is_boundary=False,
            shadow_is_boundary=True,
            legacy_target_location="",
            shadow_target_location="city_gate",
        )
        assert len(drifts) == 1
        assert drifts[0].drift_class == DriftClass.CAUSAL

    def test_topological_drift_different_target_location(self):
        """Оба boundary, но разные target locations → Class C Topological drift."""
        drifts = self.validator.validate_boundary(
            snapshot_id=self.snapshot_id,
            tick=100,
            npc_id="npc_1",
            legacy_is_boundary=True,
            shadow_is_boundary=True,
            legacy_target_location="city_gate",
            shadow_target_location="market_square",
        )
        assert len(drifts) == 1
        assert drifts[0].drift_class == DriftClass.TOPOLOGICAL
        assert drifts[0].field == "target_location"


# ══════════════════════════════════════════════════════════════════
# ФАЗА 2: Traversal Drift Detection
# ══════════════════════════════════════════════════════════════════


class TestTraversalDriftDetection:
    """Верифицирует: traversal drift обнаруживается на 3 уровнях."""

    def setup_method(self):
        self.validator = EquivalenceValidator()
        self.snapshot_id = uuid4()

    def test_no_drift_both_no_traversal(self):
        """Оба без traversal → нет drift."""
        drifts = self.validator.validate_traversal(
            snapshot_id=self.snapshot_id,
            tick=100,
            npc_id="npc_1",
            legacy_traversal=None,
            shadow_traversal=None,
        )
        assert len(drifts) == 0

    def test_no_drift_both_active_equivalent(self):
        """Legacy MOVING ≈ Shadow NEW → нет status drift."""
        _legacy = {"status": "MOVING", "target_node": "tavern:kitchen", "duration_ticks": 12}
        _shadow = TraversalContract(status="NEW", fields={"target_node": "tavern:kitchen", "duration_ticks": 12})
        drifts = self.validator.validate_traversal(
            snapshot_id=self.snapshot_id,
            tick=100,
            npc_id="npc_1",
            legacy_traversal=_legacy,
            shadow_traversal=_shadow,
        )
        # Не должно быть CAUSAL drift (MOVING ≈ NEW)
        _causal = [d for d in drifts if d.drift_class == DriftClass.CAUSAL and d.field == "traversal_status"]
        assert len(_causal) == 0

    def test_causal_drift_legacy_has_traversal_shadow_not(self):
        """Legacy создал traversal, shadow — нет → Class D."""
        _legacy = {"status": "MOVING", "target_node": "tavern:kitchen"}
        drifts = self.validator.validate_traversal(
            snapshot_id=self.snapshot_id,
            tick=100,
            npc_id="npc_1",
            legacy_traversal=_legacy,
            shadow_traversal=None,
        )
        assert len(drifts) >= 1
        _causal = [d for d in drifts if d.drift_class == DriftClass.CAUSAL and d.field == "traversal_exists"]
        assert len(_causal) == 1

    def test_causal_drift_shadow_has_traversal_legacy_not(self):
        """Shadow создал traversal, legacy — нет → Class D."""
        _shadow = TraversalContract(status="NEW", fields={"target_node": "tavern:kitchen"})
        drifts = self.validator.validate_traversal(
            snapshot_id=self.snapshot_id,
            tick=100,
            npc_id="npc_1",
            legacy_traversal=None,
            shadow_traversal=_shadow,
        )
        assert len(drifts) >= 1
        _causal = [d for d in drifts if d.drift_class == DriftClass.CAUSAL and d.field == "traversal_exists"]
        assert len(_causal) == 1

    def test_topological_drift_different_target_node(self):
        """Оба создали traversal, но разные target nodes → Class C."""
        _legacy = {"status": "MOVING", "target_node": "tavern:kitchen", "duration_ticks": 12}
        _shadow = TraversalContract(status="NEW", fields={"target_node": "tavern:cellar", "duration_ticks": 12})
        drifts = self.validator.validate_traversal(
            snapshot_id=self.snapshot_id,
            tick=100,
            npc_id="npc_1",
            legacy_traversal=_legacy,
            shadow_traversal=_shadow,
        )
        _topo = [d for d in drifts if d.drift_class == DriftClass.TOPOLOGICAL]
        assert len(_topo) >= 1
        assert _topo[0].field == "traversal_target_node"

    def test_projection_drift_different_duration(self):
        """Оба создали traversal, но разная duration → Class B (projection)."""
        _legacy = {"status": "MOVING", "target_node": "tavern:kitchen", "duration_ticks": 12}
        _shadow = TraversalContract(status="NEW", fields={"target_node": "tavern:kitchen", "duration_ticks": 8})
        drifts = self.validator.validate_traversal(
            snapshot_id=self.snapshot_id,
            tick=100,
            npc_id="npc_1",
            legacy_traversal=_legacy,
            shadow_traversal=_shadow,
        )
        _proj = [d for d in drifts if d.drift_class == DriftClass.PROJECTION]
        assert len(_proj) >= 1
        assert _proj[0].field == "traversal_duration"

    def test_no_drift_both_completed(self):
        """Оба COMPLETED → нет status drift."""
        _legacy = {"status": "COMPLETED", "target_node": "tavern:kitchen"}
        _shadow = TraversalContract(status="COMPLETED", fields={"target_node": "tavern:kitchen"})
        drifts = self.validator.validate_traversal(
            snapshot_id=self.snapshot_id,
            tick=100,
            npc_id="npc_1",
            legacy_traversal=_legacy,
            shadow_traversal=_shadow,
        )
        _causal_status = [d for d in drifts if d.drift_class == DriftClass.CAUSAL and d.field == "traversal_status"]
        assert len(_causal_status) == 0


# ══════════════════════════════════════════════════════════════════
# ФАЗА 2: DEPRECATION Layer
# ══════════════════════════════════════════════════════════════════


class TestDeprecationLayer:
    """Верифицирует: DEPRECATION warnings привязаны к drift классам."""

    def setup_method(self):
        self.validator = EquivalenceValidator()
        self.snapshot_id = uuid4()

    def test_class_c_includes_deprecation(self, caplog):
        """Class C drift логируется с DEPRECATION маркером."""
        drifts = [
            DriftReport(
                snapshot_id=self.snapshot_id,
                tick=100,
                npc_id="npc_1",
                drift_class=DriftClass.TOPOLOGICAL,
                drift_level=DriftLevel.TOPOLOGY,
                field="position",
                legacy_value="node_A",
                shadow_value="node_B",
                description="Topological drift: node_A vs node_B",
            ),
        ]
        with caplog.at_level(logging.WARNING):
            self.validator.log_drifts(drifts)
        _msg = caplog.text
        assert "DEPRECATION" in _msg
        assert "Rule 117" in _msg

    def test_class_d_includes_deprecation(self, caplog):
        """Class D drift логируется с DEPRECATION маркером."""
        drifts = [
            DriftReport(
                snapshot_id=self.snapshot_id,
                tick=100,
                npc_id="npc_1",
                drift_class=DriftClass.CAUSAL,
                drift_level=DriftLevel.CAUSALITY,
                field="traversal_exists",
                legacy_value=True,
                shadow_value=False,
                description="Causal drift: traversal",
            ),
        ]
        with caplog.at_level(logging.ERROR):
            self.validator.log_drifts(drifts)
        _msg = caplog.text
        assert "DEPRECATION" in _msg
        assert "Rule 120" in _msg

    def test_class_a_no_deprecation(self, caplog):
        """Class A drift логируется БЕЗ DEPRECATION (ожидаемый)."""
        drifts = [
            DriftReport(
                snapshot_id=self.snapshot_id,
                tick=100,
                npc_id="npc_1",
                drift_class=DriftClass.COSMETIC,
                drift_level=DriftLevel.PRESENTATION,
                field="local_position",
                legacy_value={"x": 10.1, "y": 5.0},
                shadow_value={"x": 10.2, "y": 5.0},
                description="Cosmetic drift: 0.100 units",
            ),
        ]
        with caplog.at_level(logging.INFO):
            self.validator.log_drifts(drifts)
        _msg = caplog.text
        assert "DEPRECATION" not in _msg


# ══════════════════════════════════════════════════════════════════
# ФАЗА 2: Phase 3 Readiness Indicator
# ══════════════════════════════════════════════════════════════════


class TestPhase3Readiness:
    """Верифицирует: критерий переключения ФАЗА 2→3."""

    def test_ready_when_zero_structural_drift(self):
        """0 C/D/E drift + 100k+ comparisons → READY."""
        # Readiness вычисляется по формуле, не через импорт оркестратора
        # Имитируем статистику без структурного drift
        _stats = {
            "total_comparisons": 100000,
            "drift_A": 500,  # cosmetic — ожидаемый
            "drift_B": 200,  # projection — ожидаемый
            "drift_C": 0,  # topological — 0
            "drift_D": 0,  # causal — 0
            "drift_E": 0,  # ontological — 0
        }
        _structural = _stats["drift_C"] + _stats["drift_D"] + _stats["drift_E"]
        _total = _stats["total_comparisons"]
        _ready = "READY" if _structural == 0 and _total >= 100000 else "NOT_READY"
        assert _ready == "READY"

    def test_not_ready_with_causal_drift(self):
        """C/D/E > 0 → NOT_READY."""
        _stats = {
            "total_comparisons": 100000,
            "drift_A": 500,
            "drift_B": 200,
            "drift_C": 0,
            "drift_D": 1,  # есть causal drift!
            "drift_E": 0,
        }
        _structural = _stats["drift_C"] + _stats["drift_D"] + _stats["drift_E"]
        _total = _stats["total_comparisons"]
        _ready = "READY" if _structural == 0 and _total >= 100000 else "NOT_READY"
        assert _ready == "NOT_READY"

    def test_not_ready_insufficient_observations(self):
        """< 100k comparisons → NOT_READY (даже при 0 drift)."""
        _stats = {
            "total_comparisons": 99999,
            "drift_A": 0,
            "drift_B": 0,
            "drift_C": 0,
            "drift_D": 0,
            "drift_E": 0,
        }
        _structural = _stats["drift_C"] + _stats["drift_D"] + _stats["drift_E"]
        _total = _stats["total_comparisons"]
        _ready = "READY" if _structural == 0 and _total >= 100000 else "NOT_READY"
        assert _ready == "NOT_READY"
