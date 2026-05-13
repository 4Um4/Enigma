from backend.app.models.cfrm import PsychologicalPressure
from backend.app.domain.decision_context import (
    DecisionContext, UtilityFieldDeformation, ActionSpaceCompression
)

def translate_pressure_to_context(pressure: PsychologicalPressure) -> DecisionContext:
    """
    Непрерывная математическая проекция топологии давления в деформацию пространства решений.
    Страх подавляет агрессию и усиливает бегство. Доминирование усиливает подчинение.
    """
    # 1. Топологическая деформация (90% случаев)
    aggression_sup = min(1.0, (pressure.fear * 0.7) + pressure.dominance_shift)
    obedience_amp = pressure.directive_obedience
    escape_sal = pressure.fear * 0.6 + pressure.uncertainty * 0.2
    social_sub = pressure.dominance_shift * 0.5

    # 2. Экстремальное сжатие (10% случаев - паралич воли)
    constraints = {}
    if pressure.fear > 0.8 and pressure.dominance_shift > 0.7:
        constraints["ATTACK"] = 0.1
        constraints["INTIMIDATE"] = 0.1

    return DecisionContext(
        deformation=UtilityFieldDeformation(
            aggression_suppression=aggression_sup,
            obedience_amplification=obedience_amp,
            escape_salience=escape_sal,
            social_submission_bias=social_sub
        ),
        compression=ActionSpaceCompression(constraints=constraints),
        source="cfrm_pressure"
    )
