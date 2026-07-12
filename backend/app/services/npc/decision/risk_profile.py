# backend/app/services/npc/decision/risk_profile.py
"""
R2-P2: Профиль восприятия риска — как личность модулирует оценку опасности.

Архитектурный инвариант:
  risk.py вычисляет объективную опасность (свидетели, оружие, дистанция).
  RiskPerceptionProfile модулирует СУБЪЕКТИВНОЕ восприятие.

Два независимых модификатора (НЕ отношение):
  fear_drive  → threat_sensitivity: умножает воспринимаемый риск
  control_drive → sense_of_control: умножает воспринимаемый риск (<1.0 = подавляет)

Восприятие риска ≠ готовность рисковать.
  desire НЕ трогает риск. Желание рисковать — на этапе выбора действия (utility).

Формула:
  perceived_risk = base_risk × threat_sensitivity × sense_of_control

При нейтральных drives (0.25): оба множителя = 1.0 → обратная совместимость.
"""

from dataclasses import dataclass
from typing import Dict

from app.services.npc.decision.profile_math import drive_multiplier


@dataclass(frozen=True)
class RiskPerceptionProfile:
    """Как личность модулирует восприятие риска.

    threat_sensitivity: fear_drive → насколько остро чувствуется угроза.
      1.0 = нейтрально. >1.0 = параноик. <1.0 = бесстрашный.

    sense_of_control: control_drive → насколько субъект верит в свою способность влиять.
      1.0 = нейтрально. <1.0 = чувствует беспомощность (усиливает риск).
      >1.0 = чувствует контроль (снижает риск).

    Важно: это НЕ отношение. Это два независимых фильтра восприятия.
    fear=0.6, control=0.05 (растерянный параноик):
      perceived = base × 2.18 × 0.69 ≈ base × 1.50
    fear=0.6, control=0.6 (одержимый выживальщик):
      perceived = base × 2.18 × 2.18 ≈ base × 4.75... но они НЕ одинаковы:
      первый — паникёр, второй — тактик. Разница проявится в ACTION (DecisionHub scoring).
    """

    threat_sensitivity: float
    sense_of_control: float

    @staticmethod
    def from_drives(drives_base: Dict[str, float]) -> "RiskPerceptionProfile":
        """Чистая функция: drives_base → профиль восприятия риска."""
        fear = drives_base.get("fear", 0.25)
        control = drives_base.get("control", 0.25)

        return RiskPerceptionProfile(
            threat_sensitivity=drive_multiplier(fear),
            sense_of_control=drive_multiplier(control),
        )

    def perceive(self, base_risk: float) -> float:
        """Применяет профиль личности к объективному риску.

        Формула: base_risk × threat_sensitivity / sense_of_control
        sense_of_control > 1.0 → снижает воспринимаемый риск (чувство контроля)
        sense_of_control < 1.0 → повышает воспринимаемый риск (беспомощность)
        Минимум sense_of_control = 0.2 (защита от деления на ноль).
        """
        perceived = (
            base_risk * self.threat_sensitivity / max(self.sense_of_control, 0.2)
        )
        return min(perceived, 1.0)
