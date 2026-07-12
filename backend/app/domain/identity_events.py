"""
path: backend/app/domain/identity_events.py
Назначение: Онтология событий деформации идентичности (L1). L1 = время, а не состояние.
Зависимости: Нет
Основные сущности: TraitDriftEvent, L1EventStream
"""
from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Dict, List, Optional, Protocol


@dataclass(frozen=True)
class EffectiveDrives:
    """
    L3-P1: Projection Is Read-Only.
    Эфемерный, неизменяемый снимок драйвов на момент запроса.
    Любая попытка мутации (projection["fear"] = x) вызовет TypeError.
    """

    values: MappingProxyType[str, float]

    @staticmethod
    def from_dict(d: Dict[str, float]) -> "EffectiveDrives":
        return EffectiveDrives(values=MappingProxyType(d))

    def get(self, key: str, default: float = 0.0) -> float:
        return float(self.values.get(key, default))


@dataclass(frozen=True)
class TraitDriftEvent:
    """Единичная запись о давлении мира на личность (L1 -> L1.5 Contract).

    ADR-O-305A: Строгий математический мост между L1 Chronicle и PatternDetector.
    Содержит направленный вектор effect_value (-1.0 до 1.0) и observation_weight.
    event_type существует исключительно как provenance и запрещён в формулах.
    """

    tick_id: int
    target_id: str
    source_id: str
    effect_value: float
    observation_weight: float = 1.0
    event_type: str = "generic"


@dataclass(frozen=True)
class EvidenceOfPersistence:
    """Агрегированная статистика PatternDetector (L1.5).

    ADR-O-306: Чистая статистика. Не содержит психологических полей (trait, emotion).
    Является входом для BeliefCrystallizationEngine (L2.5).
    """

    source_id: str
    cumulative_effect: float
    behavior_variance: float


@dataclass(frozen=True)
class CrystallizedBelief:
    """
    Психологическая проекция агрегированной статистики (L2.5).

    ADR-O-305: Сформирован BeliefCrystallizationEngine на основе EvidenceOfPersistence
    и модулирован drives_base (L0).
    ADR-O-307: Подвержен асимметричной травме (x6 множитель для опровержений).
    """

    source_id: str
    trait: str  # fear, trust, loyalty (психологический якорь)
    weight: float  # Уверенность в убеждении (0.0 - 1.0)
    last_updated_tick: int


class L1EventStream(Protocol):
    """Append-only causal trace of identity deformation.

    Инвариант L1: L1 never mutates state. L1 only records causal pressure.
    """

    def append(self, event: TraitDriftEvent) -> None:
        """Единственная точка записи L1. Событие неизменяемо после создания."""
        ...

    def query(
        self, npc_id: str, t_from: int, t_to: Optional[int] = None
    ) -> List[TraitDriftEvent]:
        """Чтение истории деформаций для вычисления проекции DriveResolver'ом."""
        ...
