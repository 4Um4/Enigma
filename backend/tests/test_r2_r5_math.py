# backend/tests/test_r2_r5_math.py
"""
Тест чистой математики R2 (DecisionHub) и R5 (ResolutionEngine).
Проверка: Подаем ввод -> получаем expected_success, outcome, gap.
Запуск: python -m pytest backend/tests/test_r2_r5_math.py -v -s
"""
import pytest
from app.services.npc.decision_hub import DecisionHub, EventContext, DecisionResult
from app.services.npc.resolution_engine import ResolutionEngine, ResolutionOutcome
from app.services.npc.npc_state import (
    NPCState, NPCPersonality, WillState, NPCTier, EmotionTag
)

def test_r2_r5_core_math():
    """Сценарий: Игрок с мечом нападает на стражника Торнина."""
    
    # 1. Подготовка статической личности (Immutable)
    personality = NPCPersonality(
        npc_id="tornin",
        tier=NPCTier.MAJOR,
        drives_base={"control": 0.5, "significance": 0.3, "fear": 0.1, "desire": 0.1},
        willpower=60.0,
        breakpoint=80.0,
        loyalty_base=50.0,
        voice_profile="Грубый бас",
        backstory="Бывший стражник"
    )

    # 2. Подготовка динамического состояния (Mutable)
    state = NPCState(
        npc_id="tornin",
        stress=30.0,          # Небольшой стресс
        will_state=WillState.FREE,
        emotion=EmotionTag.NEUTRAL
    )

    # 3. Событие от игрока (Формируется будущим DM-Router)
    event = EventContext(
        event_type="player_attack", # Тип действия
        actor_id="player",
        intensity=1.0,
        distance=3.0,
        witness_count=1
    )

    # ==========================================
    # R2: DECISION CORE (Что решает NPC?)
    # ==========================================
    hub = DecisionHub(seed=42) # Фиксированный seed для повторяемости
    decision: DecisionResult = hub.compute(
        state=state,
        personality=personality,
        event=event
    )

    print("\n--- R2: DECISION HUB ---")
    print(f"Выбранное намерение (Intent): {decision.intent.value}")
    print(f"Цель намерения: {decision.intent_target}")
    print(f"Итоговый Score (Expected Success): {decision.score:.4f}")

    # Проверки R2
    assert decision.intent is not None, "Hub должен выбрать intent"
    assert decision.score >= 0, "Score не может быть отрицательным"

    # ==========================================
    # R5: RESOLUTION ENGINE (Бросок кубиков)
    # ==========================================
    engine = ResolutionEngine(seed=42) # Фиксированный seed
    outcome: ResolutionOutcome = engine.resolve(
        state=state,
        personality=personality,
        expected_success=decision.score, # R2 передает шанс в R5
        context_modifier=0.0
    )

    print("\n--- R5: RESOLUTION ENGINE ---")
    print(f"Сырой бросок D20: {outcome.dice_roll}")
    print(f"Финальное значение (0-1): {outcome.final_value:.4f}")
    print(f"Actual Success (вес полосы): {outcome.actual_success:.4f}")
    print(f"GAP (Actual - Expected): {outcome.gap:.4f}")
    print(f"Эмоция сюрприза: {outcome.surprise_emotion}")
    print(f"Успех? {outcome.is_success}")

    # Проверки R5
    assert outcome.dice_roll >= 1 and outcome.dice_roll <= 20, "Бросок вне диапазона D20"
    assert -1.0 <= outcome.gap <= 1.0, "Gap вне логичного диапазона"
    assert outcome.outcome_band is not None, "Должна быть определена полоса исхода"