"""
Песочница: Минимальный Замкнутый Контур (Приказ -> Подчинение)
Проверяет: Давление поля деформирует utility-space, делая агрессию недоступной.
"""
import pytest
from backend.app.models.cfrm import PsychologicalPressure
from backend.app.domain.decision_context import DecisionContext
from backend.app.services.cfrm.pressure_translator import translate_pressure_to_context

def test_command_pressure_crushes_attack_utility():
    """
    Сценарий: Источник власти отдаёт приказ.
    Ожидание: Агрессия подавляется топологически, подход усиливается.
    """
    # 1. Генерируем давление приказа (доминирование + страх)
    pressure = PsychologicalPressure(
        fear=0.9,
        uncertainty=0.2,
        dominance_shift=0.8,
        directive_obedience=0.7
    )
    
    # 2. Транслируем в топологию решений
    ctx = translate_pressure_to_context(pressure)
    
    # 3. Верифицируем трансляцию (Геометрия, не скрипты)
    assert ctx.deformation.aggression_suppression > 0.5, "Агрессия должна быть топологически подавлена"
    assert ctx.deformation.compliance_bias > 0.5, "Подчинение должно быть усилено"
    assert "ATTACK" in ctx.compression.constraints, "Экстремальное сжатие должно блокировать ATTACK"
    assert ctx.compression.constraints["ATTACK"] < 0.2, "Атака должна быть практически невозможна"
    
    # 4. Симуляция математики DecisionHub (как это будет применено в scores)
    mock_scores = {
        "ATTACK": 1.0,
        "INTIMIDATE": 0.8,
        "FLEE": 0.5,
        "APPROACH": 0.4
    }
    
    # Применяем логику из DecisionHub
    for intent_str, factor in ctx.compression.constraints.items():
        if intent_str in mock_scores:
            mock_scores[intent_str] *= factor
            
    deformation = ctx.deformation
    if deformation.aggression_suppression > 0:
        attack_sup = 1.0 - deformation.aggression_suppression
        mock_scores["ATTACK"] *= attack_sup
        mock_scores["INTIMIDATE"] *= attack_sup
        
    if deformation.escape_salience > 0:
        escape_amp = 1.0 + deformation.escape_salience
        mock_scores["FLEE"] *= escape_amp
        
    if deformation.compliance_bias > 0:
        obey_amp = 1.0 + deformation.compliance_bias
        mock_scores["APPROACH"] *= obey_amp
        
    # 5. Верификация исхода
    assert mock_scores["APPROACH"] > mock_scores["ATTACK"], "Подчинение должно превалировать над агрессией"
    assert mock_scores["ATTACK"] < 0.1, "Атака должна быть математически раздавлена"
    print(f"\n[CAUSAL TRACE] ATTACK={mock_scores['ATTACK']:.2f}, APPROACH={mock_scores['APPROACH']:.2f}")
