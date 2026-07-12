# -*- coding: utf-8 -*-
"""
Тесты ADR-O-201 ФАЗА 1: Dual Rail Execution.

Верифицирует:
1. Shadow compilation работает параллельно с legacy
2. Drift detection корректно классифицирует расхождения
3. Нулевое изменение поведения — legacy авторитетен

Запуск: python -m pytest backend/tests/sandbox/micro/test_dual_rail_phase1.py -v --tb=short
"""

from app.models.spatial_contracts import NodeRef, NodeRole, SpatialOverlay
from app.models.world_snapshot import build_snapshot
from app.services.equivalence_validator import DriftClass, EquivalenceValidator
from app.services.event_compiler import EventCompiler
from app.services.scene_change import ChangeType, SceneChange
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


def _make_test_spatial_service():
    """Минимальный SpatialService для тестов Dual Rail."""
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


# ══════════════════════════════════════════════════════════════════
# ФАЗА 1: Dual Rail Pipeline Tests
# ══════════════════════════════════════════════════════════════════


class TestDualRailPipeline:
    """Тесты pipeline: snapshot → compile → legacy apply → validate."""

    def setup_method(self):
        self.compiler = EventCompiler()
        self.validator = EquivalenceValidator()
        self.svc = _make_test_spatial_service()

    def test_no_drift_same_node_movement(self):
        """Legacy и shadow совпадают при перемещении в известный узел."""
        ss = _make_scene_state()
        snapshot = build_snapshot(
            tick=100,
            campaign_id="test",
            location_id="tavern",
            spatial_service=self.svc,
            scene_state=ss,
            rng_seed=100,
        )
        # Shadow: компилируем перемещение
        change = SceneChange(
            type=ChangeType.NPC_POSITION,
            target="npc_1",
            field="position",
            value="tavern:kitchen",
            cause="schedule",
            tick=100,
        )
        thick = self.compiler.compile(snapshot, change)
        assert thick is not None, "Shadow compilation should succeed"
        assert thick.spatial is not None, "Spatial resolution should be present"

        # Legacy: мутация scene_state (имитация apply_change)
        entry = ss["npc_positions"]["npc_1"]
        node = self.svc.get_node("tavern:kitchen")
        # Legacy записывает позицию узла как local_position
        # (с jitter, но мы используем deterministic jitter в shadow)
        entry["position"] = "tavern:kitchen"
        # Legacy apply_change добавляет jitter — для теста используем центр узла
        entry["local_position"] = {"x": node.x, "y": node.y}

        # Validate: legacy vs shadow
        drifts = self.validator.validate_position(
            snapshot_id=snapshot.snapshot_id,
            tick=100,
            npc_id="npc_1",
            legacy_position=entry["local_position"],
            shadow_position=thick.spatial.target_xy,
        )
        # Ожидаем Class A (cosmetic) drift из-за deterministic jitter
        _classes = [d.drift_class for d in drifts]
        # Не должно быть C/D/E drift
        assert DriftClass.TOPOLOGICAL not in _classes, "No topological drift expected"
        assert DriftClass.CAUSAL not in _classes, "No causal drift expected"
        assert DriftClass.ONTOLOGICAL not in _classes, "No ontological drift expected"

    def test_ontological_drift_npc_missing_in_shadow(self):
        """NPC существует в legacy, но shadow не смог скомпилировать."""
        ss = _make_scene_state()
        snapshot = build_snapshot(
            tick=100,
            campaign_id="test",
            location_id="tavern",
            spatial_service=self.svc,
            scene_state=ss,
            rng_seed=100,
        )
        # Legacy: NPC перемещается в неизвестный узел
        # Shadow: compile вернёт None (узел не найден)
        change = SceneChange(
            type=ChangeType.NPC_POSITION,
            target="npc_1",
            field="position",
            value="tavern:nonexistent",
            cause="test",
            tick=100,
        )
        thick = self.compiler.compile(snapshot, change)
        assert thick is None, "Shadow should fail for unknown node"

        # Legacy всё равно записал бы что-то (apply_change вернул бы False)
        # Но если legacy нашёл узел, а shadow нет — это ontological drift
        drifts = self.validator.validate_position(
            snapshot_id=snapshot.snapshot_id,
            tick=100,
            npc_id="npc_1",
            legacy_position={"x": 5.0, "y": 5.0},  # legacy нашёл узел
            shadow_position=None,  # shadow не нашёл
        )
        assert len(drifts) == 1
        assert drifts[0].drift_class == DriftClass.ONTOLOGICAL

    def test_cosmetic_drift_from_jitter(self):
        """Deterministic jitter вызывает Class A (cosmetic) drift."""
        ss = _make_scene_state()
        snapshot = build_snapshot(
            tick=100,
            campaign_id="test",
            location_id="tavern",
            spatial_service=self.svc,
            scene_state=ss,
            rng_seed=100,
        )
        change = SceneChange(
            type=ChangeType.NPC_POSITION,
            target="npc_1",
            field="position",
            value="tavern:kitchen",
            cause="schedule",
            tick=100,
        )
        thick = self.compiler.compile(snapshot, change)
        assert thick is not None

        # Legacy позиция = центр узла (без jitter)
        node = self.svc.get_node("tavern:kitchen")
        legacy_pos = {"x": node.x, "y": node.y}

        drifts = self.validator.validate_position(
            snapshot_id=snapshot.snapshot_id,
            tick=100,
            npc_id="npc_1",
            legacy_position=legacy_pos,
            shadow_position=thick.spatial.target_xy,
        )
        # Ожидаем Class A drift (jitter < 0.5 единиц от центра узла)
        if drifts:
            for d in drifts:
                assert d.drift_class in (DriftClass.COSMETIC, DriftClass.PROJECTION), (
                    f"Expected A or B drift, got {d.drift_class}: {d.description}"
                )

    def test_non_spatial_passthrough_no_drift(self):
        """Не-пространственные изменения не вызывают drift."""
        ss = _make_scene_state()
        snapshot = build_snapshot(
            tick=100,
            campaign_id="test",
            location_id="tavern",
            spatial_service=self.svc,
            scene_state=ss,
            rng_seed=100,
        )
        # NPC_STATE change — не пространственный
        change = SceneChange(
            type=ChangeType.NPC_STATE,
            target="npc_1",
            field="activity",
            value="sleeping",
            cause="schedule",
            tick=100,
        )
        thick = self.compiler.compile(snapshot, change)
        assert thick is not None, "Passthrough should succeed"
        assert thick.spatial is None, "Non-spatial change has no spatial resolution"

    def test_topology_drift_different_nodes(self):
        """Legacy и shadow резолвят разные узлы — Class C drift."""
        ss = _make_scene_state()
        snapshot = build_snapshot(
            tick=100,
            campaign_id="test",
            location_id="tavern",
            spatial_service=self.svc,
            scene_state=ss,
            rng_seed=100,
        )
        drifts = self.validator.validate_topology(
            snapshot_id=snapshot.snapshot_id,
            tick=100,
            npc_id="npc_1",
            legacy_node="tavern:main_hall",
            shadow_node="tavern:kitchen",
        )
        assert len(drifts) == 1
        assert drifts[0].drift_class == DriftClass.TOPOLOGICAL

    def test_no_drift_same_boundary(self):
        """Оба pipeline согласны на boundary — нет drift."""
        drifts = self.validator.validate_boundary(
            snapshot_id=type("obj", (object,), {"snapshot_id": type("obj", (object,), {"hex": "test"})})(),
            tick=100,
            npc_id="npc_1",
            legacy_is_boundary=True,
            shadow_is_boundary=True,
            legacy_target_location="city_gate",
            shadow_target_location="city_gate",
        )
        assert len(drifts) == 0, "Same boundary should produce no drift"
