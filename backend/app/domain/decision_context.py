from dataclasses import dataclass, field
from typing import Dict, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from backend.app.models.npc_state import PerceptualKernel

@dataclass(frozen=True)
class UtilityFieldDeformation:
    """Топологическое давление на геометрию выбора. Непрерывные векторы."""
    aggression_suppression: float = 0.0
    initiative_suppression: float = 0.0
    compliance_bias: float = 0.0
    escape_salience: float = 0.0

@dataclass(frozen=True)
class ActionSpaceCompression:
    """
    Feasibility-слой. Экстремальное сужение пространства возможного.
    0.0 = действие физически/психически невозможно (feasibility = 0).
    """
    # TODO(S28): Заменить строковые ключи на enum IntentType при рефакторинге
    constraints: Dict[str, float] = field(default_factory=dict)

@dataclass(frozen=True)
class DecisionContext:
    """Топология пространства решений, собранная из PerceptualKernel."""
    deformation: UtilityFieldDeformation = field(default_factory=UtilityFieldDeformation)
    compression: ActionSpaceCompression = field(default_factory=ActionSpaceCompression)
    source: Optional[str] = None

    @classmethod
    def from_kernel(cls, kernel: "PerceptualKernel") -> "DecisionContext":
        """Прямая проекция геометрии восприятия в геометрию решений. Без промежуточных DTO."""
        # 1. Деформация (90% случаев)
        deformation = UtilityFieldDeformation(
            aggression_suppression=kernel.aggression_inhibition,
            initiative_suppression=kernel.initiative_suppression,
            compliance_bias=kernel.compliance_bias,
            escape_salience=kernel.threat_gradient * 0.5
        )
        
        # 2. Сжатие / Feasibility (10% - жесткие блокировки)
        constraints = {}
        if kernel.initiative_suppression > 0.8:
            constraints["ATTACK"] = 0.0     # Паралич воли = атака невозможна
            constraints["INTIMIDATE"] = 0.0
        if kernel.aggression_inhibition > 0.9 and kernel.compliance_bias > 0.7:
            constraints["RESIST"] = 0.0     # Тотальное подавление = сопротивление невозможно

        return cls(
            deformation=deformation,
            compression=ActionSpaceCompression(constraints=constraints),
            source="perceptual_kernel"
        )
