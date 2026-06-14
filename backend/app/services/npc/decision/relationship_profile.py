# backend/app/services/npc/decision/relationship_profile.py
"""
R2-P1: Профиль реакции отношений — как личность модулирует социальные дельты.

Архитектурный инвариант:
  DecisionHub НЕ определяет "что значит событие".
  DecisionHub только определяет "как событие влияет на связь".
  Смысл (emotion/interpretation/narrative) — Фаза 9 (AffectiveIntegrator).

Вычисляется чистой функцией из drives_base.
При нейтральных drives (все 0.25) все множители = 1.0 (обратная совместимость).
"""

from dataclasses import dataclass
from typing import Dict

from app.services.npc.decision.profile_math import drive_multiplier as _drive_multiplier


@dataclass(frozen=True)
class RelationshipResponseProfile:
    """Как личность модулирует социальные дельты.

    Все множители: 1.0 = нейтральная реакция (обратная совместимость).
    >1.0 = усилена. <1.0 = приглушена. Минимум = 0.2 (20% базы).

    Примеры:
      трус (fear=0.6):   fear_from_aggression=2.12 → страх от удара в 2x сильнее
      храбрец (fear=0.05): fear_from_aggression=0.36 → страх от удара в 3x слабее
      фанатик (significance=0.6): trust_from_betrayal=2.12 → предательство в 2x больнее
      циник (significance=0.05): trust_from_betrayal=0.36 → предательство переносится легче
    """
    # Страх от физического насилия → fear_drive
    fear_from_aggression: float

    # Страх от угроз/шантажа → fear_drive
    fear_from_threat: float

    # Потеря доверия от предательства/насилия → significance_drive
    trust_from_betrayal: float

    # Рост доверия от помощи → desire (60%) + significance (40%)
    trust_from_help: float

    # Рельеф страха от помощи → fear_drive (трусы чувствуют больше облегчения)
    fear_relief_from_help: float

    @staticmethod
    def from_drives(drives_base: Dict[str, float]) -> "RelationshipResponseProfile":
        """Чистая функция: drives_base → профиль модуляции."""
        fear = drives_base.get("fear", 0.25)
        significance = drives_base.get("significance", 0.25)
        desire = drives_base.get("desire", 0.25)

        # Комбинированный drive для помощи: желание доминирует, значимость поддерживает
        help_drive = desire * 0.6 + significance * 0.4

        return RelationshipResponseProfile(
            fear_from_aggression=_drive_multiplier(fear),
            fear_from_threat=_drive_multiplier(fear),
            trust_from_betrayal=_drive_multiplier(significance),
            trust_from_help=_drive_multiplier(help_drive),
            fear_relief_from_help=_drive_multiplier(fear),
        )