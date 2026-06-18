from dataclasses import dataclass, field
from typing import Dict, Optional

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
    """Топология пространства решений, собранная из PerceptualKernel и AffectField."""
    deformation: UtilityFieldDeformation = field(default_factory=UtilityFieldDeformation)
    compression: ActionSpaceCompression = field(default_factory=ActionSpaceCompression)
    source: Optional[str] = None
    # S74: AffectField. Непрерывная кровоточащая мембрана.
    # Интеграл аффекта и его производные пробиваются в когницию,
    # даже если дискретный emotion_tag ещё NEUTRAL.
    affective_load: float = 0.0
    # (affective_velocity удалён за нарушение Rule X — ADR-101/112)
    affective_acceleration: float = 0.0

    @classmethod
    def from_kernel(cls, kernel: "PerceptualKernel") -> "DecisionContext":
        """
        ADR-049: Замыкание контура Восприятие→Решение.
        Проецирует субъективное когнитивное состояние в топологию выбора.
        Использует getattr для безопасности типов (Domain не знает Models, Закон 1.2).
        """
        # 1. Чтение сигналов из ядра (с fallback на базовый PerceptualKernel)
        _threat = getattr(kernel, 'threat_gradient', 0.0)
        _compliance = getattr(kernel, 'compliance_bias', 0.0)
        _aggr_inhibition = getattr(kernel, 'aggression_inhibition', 0.0)
        _init_suppression = getattr(kernel, 'initiative_suppression', 0.0)

        # 2. Топологическая деформация
        # Инвариант: Угроза искривляет utility в зависимости от смелости (инверсия inhibition).
        # Храбрые (низкий _aggr_inhibition) контратакуют. Трусливые бегут.
        _fight_or_flight = _threat * 0.8
        deformation = UtilityFieldDeformation(
            # Снижение подавления агрессии при угрозе у храбрых (агрессивная защита)
            aggression_suppression=max(0.0, _aggr_inhibition - (_fight_or_flight if _aggr_inhibition < 0.3 else 0.0)),
            initiative_suppression=_init_suppression,
            compliance_bias=_compliance,
            # Бегство мотивирует только трусливых (высокий _aggr_inhibition)
            escape_salience=_fight_or_flight if _aggr_inhibition >= 0.3 else 0.0
        )

        # 3. Экстремальное сжатие (паралич воли)
        constraints: Dict[str, float] = {}
        if _aggr_inhibition > 0.8:
            constraints["ATTACK"] = 0.0 # Агрессия невозможна
        if _init_suppression > 0.8:
            constraints["INTIMIDATE"] = 0.1 # Инициатива подавлена

        compression = ActionSpaceCompression(constraints=constraints)

        return cls(deformation=deformation, compression=compression, source="perceptual_kernel")
