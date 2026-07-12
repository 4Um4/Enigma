from __future__ import annotations

# path: backend/app/models/will.py
# Назначение: Контракты системы Воли и Давления (WillpowerGate, ADR-031)
# Зависимости: domain.intent, models.delta_payloads
# Основные сущности: IntentPressureProfile, WillState, WillResponseDTO
"""
TODO: Временный контракт для разработки и тестирования WillpowerGate.
В будущем может быть расширен или переработан в зависимости от потребностей ADR-031 и взаимодействия с другими системами (эмоции, память, идентичность).
"""


from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from app.domain.intent import IntentDTO
from app.models.delta_payloads import EmotionPayload


class OriginLayer(Enum):
    """Источник давления на психику аватара (ADR-037)."""

    WILL_CONFLICT = "will_conflict"  # Конфликт намерений (Игрок vs Аватар)
    AFFECTIVE_RESONANCE = "affective_resonance"  # Резонанс с прошлыми травмами
    PHYSIOLOGICAL_OVERRIDE = "physiological_override"  # Боль, шок, кровопотеря


class EmbodiedVector(Enum):
    """Предрефлексивный моторный импульс аватара (ADR-037)."""

    AVOIDANCE = "avoidance"  # Избегание, бегство
    DESTROY = "destroy"  # Агрессия, нападение
    COLLAPSE = "collapse"  # Падение, обморок
    SUBMIT = "submit"  # Подчинение, сдача
    FREEZE = "freeze"  # Оцепенение, столбняк


@dataclass(frozen=True)
class IntentPressureProfile:
    """Вектор давления намерения на психику аватара.
    Вычисляется IntentPressureResolver (ADR-031).
    """

    violence: float = 0.0  # 0.0-1.0, физическое насилие
    humiliation: float = 0.0  # 0.0-1.0, унижение (своё или чужое)
    self_risk: float = 0.0  # 0.0-1.0, риск для жизни/здоровья аватара
    social_exposure: float = 0.0  # 0.0-1.0, социальная угроза (позор, изгнание)
    moral_violation: float = 0.0  # 0.0-1.0, нарушение внутренних убеждений
    identity_deviation: float = 0.0  # 0.0-1.0, отклонение от текущей модели Я
    trauma_trigger: float = 0.0  # 0.0-1.0, активация прошлого травматического опыта
    taboo_intensity: float = 0.0  # 0.0-1.0, нарушение культурных/личных табу


# B9-FIX: WillState унифицирован и перенесён в app.models.npc_state для избежания DOUBLE TRUTH.
from app.models.npc_state import WillState


@dataclass(frozen=True)
class WillResponseDTO:
    """Результат работы WillpowerGate (Cumulative Strain Model)."""

    state: WillState
    resistance: float = 0.0  # 0.0-1.0, вычисленная сила сопротивления
    fear_delta: float = 0.0  # Прирост страха
    stress_delta: float = 0.0  # Стресс от морального конфликта (0-100 scale)
    identity_damage: float = 0.0  # Урон идентичности (травма)
    generated_emotions: List[EmotionPayload] = field(
        default_factory=list
    )  # Эмоции конфликта
    generated_memories: List[Dict[str, Any]] = field(
        default_factory=list
    )  # Следы в аффективной памяти
    counter_offer: Optional[IntentDTO] = None  # Аватар предлагает альтернативу
    narration_hooks: List[str] = field(default_factory=list)  # Подсказки для LLM
    origin_layer: OriginLayer = OriginLayer.WILL_CONFLICT  # Источник давления
    embodied_vector: Optional[EmbodiedVector] = None  # Моторный импульс (для UI)
    social_signal: Optional[str] = (
        None  # The Fool Phase 2: Социальный сигнал (для CFRM)
    )
    crowd_threat_level: Optional[float] = (
        None  # The Fool Phase 2: Уровень угрозы для толпы (0.0-1.0)
    )


@dataclass(frozen=True)
class IntentResolution:
    """Результат Фазы 1: Семантический перевод (ADR-031 Fix).
    Содержит ТОЛЬКО канонический интент и вектор давления.
    Вычисление воли (Causal Resolution) перенесено в TickOrchestrator.
    """

    original_intent: IntentDTO
    pressure_profile: IntentPressureProfile = field(
        default_factory=IntentPressureProfile
    )
    movement_request: Optional[Any] = (
        None  # ADR-O-315: Готовый контракт движения от Слоя 1 (TYPE_CHECKING не нужен, используем Any)
    )
