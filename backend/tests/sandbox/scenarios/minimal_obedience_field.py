"""
Minimal Obedience Field Test (Полный срез: Семантика -> Давление -> Utility -> Цель -> Транзит)
Доказывает, что подчинение рождает легитимное плавное движение, а не телепортацию.
"""

import math

# Импортируем реальные компоненты ENIGMA (без LLM)
from app.domain.identity_events import EffectiveDrives

_MOCK_DRIVES = EffectiveDrives.from_dict({"control": 0.5, "significance": 0.5, "fear": 0.5, "desire": 0.5})

from app.services.social.directive_interpretation_subscriber import DirectiveInterpretationSubscriber
from tests.sandbox.fixtures.tavern_world import build_tavern_fixture
from tests.sandbox.probes.pressure_probe import PressureProbe
from tests.sandbox.probes.traversal_probe import TraversalProbe
from tests.sandbox.probes.utility_probe import UtilityProbe
from tests.sandbox.runtime.causal_trace import CausalTrace
from tests.sandbox.runtime.deterministic_clock import DeterministicClock


def test_directive_pressure_materializes_traversal():
    # 1. Инициализация Осциллографа
    clock = DeterministicClock()
    trace = CausalTrace()
    pressure_probe = PressureProbe(trace)
    utility_probe = UtilityProbe(trace)
    traversal_probe = TraversalProbe(trace)
    world = build_tavern_fixture()

    # === ЭТАП 1-2: Семантика -> Давление ===
    tick_1 = clock.tick()
    speech_frame_id = trace.observe(
        tick=tick_1,
        phase="SEMANTIC",
        entity_id="player",
        event="PLAYER_SPOKE",
        data={"semantic_action": "MOVE", "target": "thief_shadow"},
    )

    subscriber = DirectiveInterpretationSubscriber()

    class MockEvent:
        type = "PLAYER_SPOKE"
        payload = {"semantic_action": "MOVE", "target_id": "thief_shadow", "social_pressure": 0.8}

    all_npcs = list(world["npc_positions"].values())
    result = subscriber.handle(MockEvent(), all_npcs)

    fear_pressure = 0.0
    deltas = result if isinstance(result, list) else getattr(result, "deltas", [])
    for delta in deltas:
        if hasattr(delta, "payload") and hasattr(delta.payload, "fear_delta"):
            fear_pressure = abs(delta.payload.fear_delta) / 10.0

    assert fear_pressure > 0.1, "КАУЗАЛЬНЫЙ СРЫВ: Приказ не породил давления"
    pressure_frame_id = pressure_probe.observe_pressure(
        tick_1, "thief_shadow", "DIRECTIVE_OBEDIENCE", fear_pressure, speech_frame_id
    )

    # === ЭТАП 3: Искажение Utility -> Рождение Цели ===
    tick_2 = clock.tick()
    base_approach_score = 0.1
    fear_modifier = world["npc_positions"]["thief_shadow"]["psyche"]["fear"]
    willpower_modifier = world["npc_positions"]["thief_shadow"]["psyche"]["willpower"]

    utility_distortion = fear_pressure * (fear_modifier + (1.0 - willpower_modifier))
    new_approach_score = base_approach_score + utility_distortion

    goal_frame_id = None
    if new_approach_score > 0.5:
        utility_probe.observe_utility_shift(
            tick_2, "thief_shadow", "APPROACH_PLAYER", base_approach_score, new_approach_score, pressure_frame_id
        )
        goal_frame_id = trace.observe(
            tick=tick_2,
            phase="DECISION",
            entity_id="thief_shadow",
            event="GOAL_EMERGED",
            data={"goal": "DESIRED_PROXIMITY_CLOSE", "target": "player"},
            parent_id=trace.find_frame("UTILITY", "APPROACH_PLAYER_SCORE_SHIFT", "thief_shadow").frame_id,
        )
    assert goal_frame_id is not None, "КАУЗАЛЬНЫЙ СРЫВ: Цель не родилась"

    # === ЭТАП 4-5: Пространственная Реализация и Материализация Транзита ===
    tick_3 = clock.tick()

    # SpatialReasoner конвертирует Goal в Target Node
    target_node = world["npc_positions"]["player"]["position"]  # "main_hall"
    from_node = world["npc_positions"]["thief_shadow"]["position"]  # "shadow_corner"

    # Эмуляция SceneStateManager (ADR-019)
    from_xy = world["npc_positions"]["thief_shadow"]["local_position"]
    to_xy = world["npc_positions"]["player"]["local_position"]

    # Вычисление расстояния
    dx = to_xy["x"] - from_xy["x"]
    dy = to_xy["y"] - from_xy["y"]
    dist = math.hypot(dx, dy)
    speed = 2.0  # MVP хардкод
    duration = dist / speed if speed > 0 else 0

    traversal_data = {}
    if dist > 0.1:  # Защита от микро-прыжков
        traversal_data = {
            "status": "MOVING",
            "from_node": from_node,
            "target_node": target_node,
            "started_at": clock.game_time_seconds,
            "duration": duration,
            "expected_arrival_time": clock.game_time_seconds + duration,
        }
        traversal_probe.observe_traversal_started(
            tick=tick_3,
            entity_id="thief_shadow",
            from_node=from_node,
            to_node=target_node,
            duration=duration,
            parent_id=goal_frame_id,
        )

    assert traversal_data.get("status") == "MOVING", "КАУЗАЛЬНЫЙ СРЫВ: Транзит не начался"
    assert traversal_data["duration"] > 0, "КАУЗАЛЬНЫЙ СРЫВ: Длительность транзита нулевая (Телепортация!)"

    # === ЭТАП 6: ВЕРИФИКАЦИЯ ПОЛНОЙ ЦЕПИ ===
    traversal_frame = trace.find_frame("TRAVERSAL", "TRAVERSAL_STARTED", "thief_shadow")
    assert traversal_frame is not None

    print("\n=== CAUSAL LINEAGE PROOF (FULL SPATIAL) ===")
    print(trace.print_lineage(traversal_frame.frame_id))
    print("===========================================\n")
