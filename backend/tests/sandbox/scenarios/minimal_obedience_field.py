"""
Minimal Obedience Field Test.
Проверяет не движение, а способность давления подчинения искривлять utility-space.

Файл: backend/tests/sandbox/scenarios/minimal_obedience_field.py
Назначение: Вертикальный срез каузальной трубы: Семантика → Давление → Utility → Цель.
Зависимости: pytest, fixtures, probes, runtime

TODO:
- В будущем можно расширить сценарий, добавив больше фазовых переходов, например, от цели к действию, и проверить, как давление влияет на фактическое поведение NPC.
"""
import pytest
from tests.sandbox.runtime.deterministic_clock import DeterministicClock
from tests.sandbox.runtime.causal_trace import CausalTrace
from tests.sandbox.probes.pressure_probe import PressureProbe
from tests.sandbox.probes.utility_probe import UtilityProbe
from tests.sandbox.fixtures.tavern_world import build_tavern_fixture

# Импортируем реальные компоненты ENIGMA (без LLM)
from app.models.cfrm import PsychologicalPressure
from app.services.social.directive_interpretation_subscriber import DirectiveInterpretationSubscriber

def test_directive_pressure_distorts_utility():
    """
    Сценарий: Игрок приказывает "Тень, иди сюда".
    Ожидание: Давление подчинения возникает и искажает скоринг цели 'approach_player'.
    """
    # 1. Инициализация Осциллографа
    clock = DeterministicClock()
    trace = CausalTrace()
    pressure_probe = PressureProbe(trace)
    utility_probe = UtilityProbe(trace)
    world = build_tavern_fixture()

    # 2. Семантический импульс (Игрок говорит)
    tick_1 = clock.tick()
    # Фиксируем первичное событие в трассировке
    speech_frame_id = trace.observe(
        tick=tick_1, phase="SEMANTIC", entity_id="player",
        event="PLAYER_SPOKE", data={"semantic_action": "MOVE", "target": "thief_shadow"}
    )

    # 3. Рождение давления (DirectiveInterpretationSubscriber)
    # Эмулируем работу шины, вызывая обработчик напрямую
    subscriber = DirectiveInterpretationSubscriber()
    
    # Мокаем EventDTO, так как мы тестируем логику, не I/O
    class MockEvent:
        type = "PLAYER_SPOKE"
        payload = {"semantic_action": "MOVE", "target_id": "thief_shadow", "social_pressure": 0.8}
    
    # Вычисляем давление
    # Передаем список всех NPC (как all_npcs_raw), чтобы подписчик мог найти цель
    all_npcs = list(world["npc_positions"].values())
    result = subscriber.handle(MockEvent(), all_npcs)
    
    # Пробник фиксирует рождение давления
    fear_pressure = 0.0
    stress_pressure = 0.0
    
    # Разворачиваем результат Phase8Handler
    deltas = []
    if hasattr(result, 'deltas'):
        deltas = result.deltas
    elif isinstance(result, list):
        deltas = result
        
    print(f"[DEBUG] DirectiveInterpretationSubscriber result type: {type(result)}, deltas count: {len(deltas)}")
    
    for delta in deltas:
        print(f"[DEBUG] Delta: domain={getattr(delta, 'domain', None)}, payload={getattr(delta, 'payload', None)}")
        # Извлекаем страх и стресс как меру давления подчинения
        if hasattr(delta, 'payload') and hasattr(delta.payload, 'fear_delta'):
            fear_pressure = abs(delta.payload.fear_delta) / 10.0 # Нормализация
        if hasattr(delta, 'payload') and hasattr(delta.payload, 'stress_delta'):
            stress_pressure = abs(delta.payload.stress_delta) / 20.0 # Нормализация
            
    # Итоговое давление подчинения = комбинация страха и стресса
    directive_obedience = max(fear_pressure, stress_pressure)
    assert directive_obedience > 0.1, "КАУЗАЛЬНЫЙ СРЫВ: Приказ не породил давления подчинения"
    
    pressure_probe.observe_pressure(
        tick=tick_1, entity_id="thief_shadow",
        pressure_type="DIRECTIVE_OBEDIENCE",
        magnitude=directive_obedience,
        parent_id=speech_frame_id
    )

    # 4. Искажение Utility Space (Эмуляция DecisionHub)
    tick_2 = clock.tick()
    
    # Базовый скоринг (до давления)
    base_approach_score = 0.1 # Тень обычно избегает близости
    
    # DecisionHub считывает давление и искажает скоринг
    # (Пока эмулируем формулу, так как в реальном хабе этого нет)
    fear_modifier = world["npc_positions"]["thief_shadow"]["psyche"]["fear"]
    willpower_modifier = world["npc_positions"]["thief_shadow"]["psyche"]["willpower"]
    
    # Чем выше страх и ниже воля, тем сильнее искажение
    # Используем fear_pressure (основной драйвер подчинения)
    utility_distortion = fear_pressure * (fear_modifier + (1.0 - willpower_modifier))
    new_approach_score = base_approach_score + utility_distortion
    
    pressure_frame = trace.find_frame("PRESSURE", "DIRECTIVE_OBEDIENCE", "thief_shadow")
    assert pressure_frame is not None, "Давление не было зафиксировано"
    
    utility_probe.observe_utility_shift(
        tick=tick_2, entity_id="thief_shadow",
        action="APPROACH_PLAYER",
        old_score=base_approach_score,
        new_score=new_approach_score,
        parent_id=pressure_frame.frame_id
    )

    # 5. Верификация: Приближение стало наиболее вероятным будущим?
    assert new_approach_score > 0.6, f"КАУЗАЛЬНЫЙ СРЫВ: Давление не исказило utility. Score: {new_approach_score}"
    
    # 6. Рождение Цели (Если скоринг победил, рождается Goal)
    # В реальной системе это сделает DecisionHub
    goal_frame_id = None
    if new_approach_score > 0.5: # Порог победы
        goal_frame_id = trace.observe(
            tick=tick_2, phase="DECISION", entity_id="thief_shadow",
            event="GOAL_EMERGED", data={"goal": "DESIRED_PROXIMITY_CLOSE", "target": "player"},
            parent_id=trace.find_frame("UTILITY", "APPROACH_PLAYER_SCORE_SHIFT", "thief_shadow").frame_id
        )

    assert goal_frame_id is not None, "Цель не родилась даже при высоком скоринге"

    # 7. Вывод Каузальной Линии (Доказательство легитимности)
    print("\n=== CAUSAL LINEAGE PROOF ===")
    print(trace.print_lineage(goal_frame_id))
    print("============================\n")