# -*- coding: utf-8 -*-
"""
path: /project/backend/tests/test_commitment_ssm_integration.py
Назначение: S203.1 (Stage 2A) — интеграционный микротест SSM <-> CommitmentRegistry.
    Ветка материализации traversal (SSM.apply_change, ADR-O-323) требует валидный
    SpatialService с узлом-целью (guard svc+node, ~1217) — SpatialFactory стабится
    на границе модуля (SSM импортирует фабрику внутри метода, ~1207).
    Три контракта: (1) born-materialization: born-MOVING traversal (Н-50) ->
    born-EXECUTING commitment с verbatim cause; (2) ADR-130.1 внешний guard:
    in-flight MOVING traversal не суперседится; (3) суперсессия ОСИРОТЕВШЕГО
    commitment при новой материализации (обход Н-46a-класса без зеркала:
    engine pop / death-cleanup). Н-52: внутренняя suppression-ветка мертва,
    покрыта внешним guard'ом.
Зависимости: pytest, app.services.scene_state_manager, app.domain.traversal_schema,
    app.services.scene_change, app.services.action.commitment_registry
Основные сущности: TestSSMCommitmentMirror
"""

from types import SimpleNamespace

import pytest

from app.domain.traversal_schema import TraversalProposal
from app.services.scene_change import ChangeType, SceneChange
from app.services.scene_state_manager import SceneStateManager

_NPC = "npc_t"
_NODE_A = "tavern_bar"
_NODE_B = "tavern_door"


class _StubSpatial:
    """Минимальный SpatialService-стаб: узлы A/B существуют, прочие — нет."""

    def __init__(self) -> None:
        self._nodes = {
            _NODE_A: SimpleNamespace(node_id=_NODE_A, x=2.0, y=2.0),
            _NODE_B: SimpleNamespace(node_id=_NODE_B, x=5.0, y=1.0),
        }

    def get_node(self, node_id: str):
        return self._nodes.get(node_id)


def _make_proposal(tick: int, target: str) -> TraversalProposal:
    """Proposal по фактической сигнатуре traversal_schema.py:122-137 (археология)."""
    return TraversalProposal(
        npc_id=_NPC,
        source_node="hall_center",
        target_node=target,
        path_waypoints=((0.0, 0.0), (1.0, 1.0), (2.0, 2.0)),
        distance=2.8,
        speed=1.0,
        duration_ticks=3,
        source_intent_id="test-intent-1",
        planned_tick=tick,
        topology_version=1,  # ADR-O-323: Mandatory contract
    )


def _make_change(tick: int, target: str, cause: str = "life_engine_schedule") -> SceneChange:
    """SceneChange по фактической сигнатуре scene_change.py:56-66."""
    return SceneChange(
        type=ChangeType.NPC_POSITION,
        target=_NPC,
        field="position",
        value=target,
        cause=cause,
        tick=tick,
        traversal_proposal=_make_proposal(tick=tick, target=target),
    )


@pytest.fixture
def scene_state() -> dict:
    return {
        "location_id": "tavern",
        "npc_positions": {_NPC: {"position": "hall_center", "location_id": "tavern"}},
        "active_traversals": {},
    }


@pytest.fixture
def stub_spatial(monkeypatch) -> None:
    """Стаб фабрики на границе модуля: SSM импортирует SpatialFactory внутри
    apply_change — патч атрибута класса ловится в момент вызова."""
    import app.services.spatial.spatial_factory as sf

    monkeypatch.setattr(
        sf.SpatialFactory,
        "build_for_campaign",
        lambda **kwargs: _StubSpatial(),
    )


class TestSSMCommitmentMirror:
    def test_materialization_mirrors_commitment(self, scene_state, stub_spatial):
        """Свежая материализация: born-MOVING traversal (Н-50) -> born-EXECUTING
        commitment, cause verbatim от upstream (№7: SSM не классифицирует)."""
        ssm = SceneStateManager()

        applied = ssm.apply_changes(
            "test_campaign", [_make_change(tick=5, target=_NODE_A)], scene_state
        )

        assert applied == 1
        trav = scene_state["active_traversals"][_NPC]
        assert trav["status"] == "MOVING"
        assert trav["target_node"] == _NODE_A
        cm = scene_state["active_commitments"][_NPC]
        assert cm["status"] == "EXECUTING"
        assert cm["action"] == "MOVE"
        assert cm["cause"] == "life_engine_schedule"
        assert cm["target_id"] == _NODE_A
        assert cm["executor"] == "traversal"
        assert cm["ordinal"] == 1
        assert scene_state["commitment_ordinals"][_NPC] == 1
        # Локальная позиция — из узла-цели стаба (ветка без target_local_xy)
        assert scene_state["npc_positions"][_NPC]["local_position"] == {"x": 2.0, "y": 2.0}

    def test_inflight_traversal_not_superseded(self, scene_state, stub_spatial):
        """ADR-130.1 внешний guard: пока traversal MOVING, новая материализация
        (даже к другой цели) не входит в ветку создания — traversal и commitment
        сохраняют владельца (ordinal/commitment_id неизменны). Н-52: внутренняя
        suppression-ветка недостижима — работает именно внешний guard."""
        ssm = SceneStateManager()
        ssm.apply_changes("test_campaign", [_make_change(tick=5, target=_NODE_A)], scene_state)
        cm_id = scene_state["active_commitments"][_NPC]["commitment_id"]
        ordinal_before = scene_state["commitment_ordinals"][_NPC]

        # Другая цель: early-exit не срабатывает (значение отлично), внешний
        # guard (traversal MOVING) блокирует ветку материализации.
        ssm.apply_changes("test_campaign", [_make_change(tick=6, target=_NODE_B)], scene_state)

        assert scene_state["commitment_ordinals"][_NPC] == ordinal_before
        assert scene_state["active_commitments"][_NPC]["commitment_id"] == cm_id
        assert scene_state["active_traversals"][_NPC]["target_node"] == _NODE_A
        assert len(scene_state["active_commitments"]) == 1

    def test_orphaned_commitment_superseded(self, scene_state, stub_spatial):
        """Суперсессия: traversal исчез БЕЗ зеркала (обход Н-46a-класса:
        movement_engine:330 / orchestrator death-cleanup) -> активный commitment
        осиротел -> новая материализация прерывает его (INTERRUPTED/SUPERSEDED)
        и становится владельцем с parent-цепочкой (№3a)."""
        ssm = SceneStateManager()
        ssm.apply_changes("test_campaign", [_make_change(tick=5, target=_NODE_A)], scene_state)
        first_id = scene_state["active_commitments"][_NPC]["commitment_id"]

        # Симуляция незеркалированного обхода: traversal убран напрямую.
        scene_state["active_traversals"].pop(_NPC)

        ssm.apply_changes("test_campaign", [_make_change(tick=7, target=_NODE_B)], scene_state)

        cm2 = scene_state["active_commitments"][_NPC]
        assert cm2["target_id"] == _NODE_B
        assert cm2["parent_commitment_id"] == first_id
        hist = scene_state["commitment_history"][_NPC]
        assert hist[-1]["status"] == "INTERRUPTED"
        assert hist[-1]["interrupt_reason"] == "SUPERSEDED_BY_NEW_MATERIALIZATION"
        assert scene_state["commitment_ordinals"][_NPC] == 2