"""
Файл: backend/tests/sandbox/phenomenology/test_rumor_mutation.py
Назначение: Лаборатория Субъективных Реальностей. Проверка эпистемического расхождения (divergence).
Зависимости: app.services.cfrm.local_causal_solver, app.models.cfrm, sandbox.runtime.causal_trace
Основные сущности: TestRumorMutation

TODO:
- Добавить больше сценариев (например, искажение из-за предвзятости, влияние социальных связей на восприятие)
- Внедрить метрики для количественной оценки расхождения (например, divergence_score)
- Вынести общие фикстуры в отдельный файл для повторного использования
"""

from typing import Any, Dict, List

import pytest
from app.models.cfrm import (
    CausalAxis,
    ClusterDef,
    ClusterGraph,
    ClusterOccupancy,
    DisturbanceVector,
    EventBuffer,
    FieldDisturbance,
)
from app.services.cfrm.local_causal_solver import LocalCausalSolver

from sandbox.runtime.causal_trace import CausalTrace


@pytest.fixture
def trace() -> CausalTrace:
    return CausalTrace()


@pytest.fixture
def tavern_graph() -> ClusterGraph:
    """Таверна с двумя кластерами: main_hall и bar_area, соединенные дверью (мембрана)."""
    graph = ClusterGraph()
    graph.clusters = {
        "tavern:main_hall": ClusterDef(cluster_id="tavern:main_hall", boundary_cells=frozenset(["tavern:bar_area"])),
        "tavern:bar_area": ClusterDef(cluster_id="tavern:bar_area", boundary_cells=frozenset(["tavern:main_hall"])),
    }
    return graph


@pytest.fixture
def tavern_occupancy() -> ClusterOccupancy:
    """Игрок и Свидетель_A в главном зале. Свидетель_B в баре."""
    occ = ClusterOccupancy()
    occ.update_entity("player", "tavern:main_hall")
    occ.update_entity("witness_A", "tavern:main_hall")
    occ.update_entity("witness_B", "tavern:bar_area")
    return occ


@pytest.fixture
def minimal_npcs() -> List[Dict[str, Any]]:
    return [
        {"npc_id": "player", "perceptual_kernel": {}, "body_state": {"consciousness": 1.0}, "psyche": {"stress": 0.0}},
        {
            "npc_id": "witness_A",
            "perceptual_kernel": {},
            "body_state": {"consciousness": 1.0},
            "psyche": {"stress": 10.0},
        },
        {
            "npc_id": "witness_B",
            "perceptual_kernel": {},
            "body_state": {"consciousness": 1.0},
            "psyche": {"stress": 30.0},
        },  # Более стрессовый
    ]


@pytest.fixture
def combat_disturbance() -> FieldDisturbance:
    """Объективный факт: жестокий удар в главном зале."""
    return FieldDisturbance(
        origin_cluster="tavern:main_hall",
        disturbance_type=CausalAxis.PHYSICAL,
        magnitude=0.9,
        vectors=(DisturbanceVector.KINETIC, DisturbanceVector.ACOUSTIC, DisturbanceVector.MATTER),
        source_entity="player",
        semantic_seed="impact",
    )


def test_phenomenon_divergence_across_membrane(trace, tavern_graph, tavern_occupancy, minimal_npcs, combat_disturbance):
    """
    СЦЕНАРИЙ: Игрок бьет кого-то в main_hall. Witness_A видит это. Witness_B в bar_area слышит грохот.
    ОЖИДАНИЕ: Истина Witness_B эпистемически искажена (mutation_stage выше, certainty ниже).
    """
    solver = LocalCausalSolver()
    buffer = EventBuffer()

    # 1. LOG FIELD
    trace.observe(
        1,
        "FIELD",
        "player",
        "combat_disturbance",
        {"magnitude": combat_disturbance.magnitude, "seed": combat_disturbance.semantic_seed},
    )

    # Помещаем возмущение в буфер
    buffer.add(combat_disturbance, CausalAxis.PHYSICAL)

    # 2. SOLVE
    states = solver.solve(buffer, tavern_graph, tavern_occupancy, minimal_npcs)

    state_a = states.get("witness_A")
    state_b = states.get("witness_B")

    assert state_a is not None, "Witness_A не получил феноменологическое состояние"
    assert state_b is not None, "Witness_B не получил феноменологическое состояние"

    # 3. LOG MEMBRANE & PHENOMENON
    trace.observe(1, "MEMBRANE", "witness_A", "direct_observation", {"factor": 1.0})
    trace.observe(
        1,
        "PHENOMENON",
        "witness_A",
        "state_resolved",
        {"threat": state_a.threat_level, "anomaly": state_a.anomaly_score},
    )

    trace.observe(1, "MEMBRANE", "witness_B", "membrane_attenuation", {"factor": 0.3})  # Из логики LocalCausalSolver
    trace.observe(
        1,
        "PHENOMENON",
        "witness_B",
        "state_resolved",
        {"threat": state_b.threat_level, "anomaly": state_b.anomaly_score},
    )

    # 4. АУДИТ БАЛАНСА: Угроза для прямого свидетеля ВЫШЕ, чем для слухового
    # Witness_A видит "impact" (в списке угроз), Witness_B слышит "muffled_impact" (не в списке угроз)
    assert state_a.threat_level > state_b.threat_level, "Нарушение баланса: слух страшнее прямого наблюдения"

    # Аномальность: одиночный слабый слух (anomaly=0.1) гасится порогом 0.2 в _aggregate_phenomena
    assert state_b.anomaly_score == 0.0, "Одиночный глухой слух не должен превышать порог аномальности"

    print("\n--- CAUSAL TRACE REPORT ---")
    print(trace.print_lineage(trace.frames[-1].frame_id))
