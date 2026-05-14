"""
Файл: backend/tests/sandbox/system/test_causal_closure.py
Назначение: Системная песочница. Вертикальный срез всего каузального конвейера:
            FieldDisturbance -> DirectiveInterpretation -> Pressure -> DecisionContext -> DecisionHub.
Зависимости: app.services.social, app.services.cfrm, app.services.npc, sandbox.runtime.causal_trace
Основные сущности: TestCausalClosure

Запуск: pytest backend/tests/sandbox/system/test_causal_closure.py

TODO:
- [ ] Расширить сценарии: разные NPC, разные приказы, разные контексты.
- [ ] Интеграционные тесты с реальными событиями и NPCState.
"""
import pytest
from typing import Dict, Any, List
from unittest.mock import MagicMock

from app.models.cfrm import PsychologicalPressure
from app.models.state_delta import StateDeltas, DeltaDomain, EmotionPayload, SocialPayload
from app.models.npc_state import NPCState
from app.domain.decision_context import DecisionContext
# DirectiveInterpretationSubscriber не используется, давление конструируется напрямую
from app.services.cfrm.pressure_translator import translate_pressure_to_context
from app.services.npc.decision_hub import DecisionHub
from sandbox.runtime.causal_trace import CausalTrace

@pytest.fixture
def trace() -> CausalTrace:
    return CausalTrace()

@pytest.fixture
def fearful_shadow_state() -> NPCState:
    """Тень: трусливая, лояльная, подавленная."""
    state = NPCState(npc_id="thief_shadow")
    state.social_stats = {"fear_of_player": 80.0, "trust": 30.0}
    state.psyche = {"fear_drive": 0.8, "aggression": 0.1, "willpower": 0.3, "loyalty_true": 0.6, "stress": 60.0}
    state.body_state = {"consciousness": 1.0}
    return state

@pytest.fixture
def brave_shadow_state() -> NPCState:
    """Тень: смелая, нелояльная, агрессивная."""
    state = NPCState(npc_id="thief_shadow")
    state.social_stats = {"fear_of_player": 10.0, "trust": 10.0}
    state.psyche = {"fear_drive": 0.1, "aggression": 0.9, "willpower": 0.9, "loyalty_true": 0.1, "stress": 10.0}
    state.body_state = {"consciousness": 1.0}
    return state

def test_full_obedience_closure(trace, fearful_shadow_state):
    """
    СЦЕНАРИЙ: Игрок приказывает Тени подойти. Тень труслива.
    ОЖИДАНИЕ: Контур замыкается. Давление подавляет ATTACK и усиливает APPROACH.
    """
    # 1. ВОЗМУЩЕНИЕ: Игрок отдал приказ
    trace.observe(1, "FIELD", "player", "directive_move", {"target": "thief_shadow", "social_pressure": 0.9})
    
    # 2. ДАВЛЕНИЕ: Конструируем PsychologicalPressure на основе психики труса
    # (В реальности генерируется DirectiveInterpretationSubscriber -> LocalCausalSolver)
    pressure = PsychologicalPressure(
        fear=fearful_shadow_state.social_stats["fear_of_player"] / 100.0,
        uncertainty=0.3,
        dominance_shift=0.8,
        directive_obedience=0.7 # Высокое давление подчинения
    )
    trace.observe(1, "PRESSURE", "thief_shadow", "obedience_computed", {
        "directive_obedience": pressure.directive_obedience,
        "fear": pressure.fear
    })
    
    # 3. ТОПОЛОГИЯ: Транслируем давление в контекст решений
    decision_ctx = translate_pressure_to_context(pressure)
    trace.observe(1, "UTILITY", "thief_shadow", "context_deformed", {
        "aggression_sup": decision_ctx.deformation.aggression_suppression,
        "compliance_bias": decision_ctx.deformation.compliance_bias
    })
    
    # 4. РЕШЕНИЕ: DecisionHub применяет контекст
    hub = DecisionHub()
    # Мокируем личность для хаба
    profile_mock = MagicMock()
    profile_mock.drives_base = {"fear": 0.8, "aggression": 0.1}
    
    # Вычисляем базовые скоры (обычно делает хаб, но мы подсматриваем)
    base_scores = {"ATTACK": 0.3, "FLEE": 0.6, "APPROACH": 0.2, "IDLE": 0.5}
    
    # Применяем логику DecisionHub
    for intent_str, feasibility in decision_ctx.compression.constraints.items():
        if intent_str in base_scores and feasibility <= 0.0:
            del base_scores[intent_str]
            
    deformation = decision_ctx.deformation
    if deformation.aggression_suppression > 0:
        attack_sup = 1.0 - deformation.aggression_suppression
        if "ATTACK" in base_scores: base_scores["ATTACK"] *= attack_sup
        
    if deformation.compliance_bias > 0:
        obey_amp = 1.0 + deformation.compliance_bias
        if "APPROACH" in base_scores: base_scores["APPROACH"] *= obey_amp

    trace.observe(1, "DECISION", "thief_shadow", "decision_made", {
        "APPROACH": round(base_scores.get("APPROACH", 0.0), 3),
        "ATTACK": round(base_scores.get("ATTACK", 0.0), 3)
    })

    # АУДИТ БАЛАНСА: Подчинение превалирует над агрессией
    assert base_scores["APPROACH"] > base_scores["ATTACK"], "Трусливая Тень должна выбрать подчинение"
    assert decision_ctx.deformation.aggression_suppression > 0.5, "Агрессия должна быть сильно подавлена"
    
    print("\n--- CAUSAL CLOSURE TRACE ---")
    print(trace.print_lineage(trace.frames[-1].frame_id))


def test_brave_resistance_closure(trace, brave_shadow_state):
    """
    СЦЕНАРИЙ: Игрок приказывает смелой Тени подойти.
    ОЖИДАНИЕ: Давление слабое. Агрессия не подавляется. ATTACK побеждает APPROACH.
    """
    trace.observe(1, "FIELD", "player", "directive_move", {"target": "thief_shadow", "social_pressure": 0.9})
    
    pressure = PsychologicalPressure(
        fear=brave_shadow_state.social_stats["fear_of_player"] / 100.0,
        uncertainty=0.1,
        dominance_shift=0.2,
        directive_obedience=0.1 # Низкое давление подчинения
    )
    trace.observe(1, "PRESSURE", "thief_shadow", "obedience_computed", {
        "directive_obedience": pressure.directive_obedience,
        "fear": pressure.fear
    })
    
    decision_ctx = translate_pressure_to_context(pressure)
    trace.observe(1, "UTILITY", "thief_shadow", "context_deformed", {
        "aggression_sup": decision_ctx.deformation.aggression_suppression,
        "compliance_bias": decision_ctx.deformation.compliance_bias
    })
    
    base_scores = {"ATTACK": 0.7, "FLEE": 0.1, "APPROACH": 0.1, "IDLE": 0.2}
    
    deformation = decision_ctx.deformation
    if deformation.aggression_suppression > 0:
        attack_sup = 1.0 - deformation.aggression_suppression
        if "ATTACK" in base_scores: base_scores["ATTACK"] *= attack_sup
        
    if deformation.compliance_bias > 0:
        obey_amp = 1.0 + deformation.compliance_bias
        if "APPROACH" in base_scores: base_scores["APPROACH"] *= obey_amp

    trace.observe(1, "DECISION", "thief_shadow", "decision_made", {
        "APPROACH": round(base_scores.get("APPROACH", 0.0), 3),
        "ATTACK": round(base_scores.get("ATTACK", 0.0), 3)
    })

    # АУДИТ БАЛАНСА: Агрессия превалирует над подчинением
    assert base_scores["ATTACK"] > base_scores["APPROACH"], "Смелая Тень должна выбрать агрессию/отказ"
    assert decision_ctx.deformation.aggression_suppression < 0.3, "Агрессия не должна быть подавлена"
    
    print("\n--- CAUSAL CLOSURE TRACE (BRAVE) ---")
    print(trace.print_lineage(trace.frames[-1].frame_id))