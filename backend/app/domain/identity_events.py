"""
path: backend/app/domain/identity_events.py
Назначение: Онтология событий деформации идентичности (L1). L1 = время, а не состояние.
Зависимости: Нет
Основные сущности: TraitDriftEvent, L1EventStream
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import List, Protocol, Optional, Dict
from types import MappingProxyType

@dataclass(frozen=True)
class EffectiveDrives:
    """
    L3-P1: Projection Is Read-Only.
    Эфемерный, неизменяемый снимок драйвов на момент запроса.
    Любая попытка мутации (projection["fear"] = x) вызовет TypeError.
    """
    values: MappingProxyType

    @staticmethod
    def from_dict(d: Dict[str, float]) -> 'EffectiveDrives':
        return EffectiveDrives(values=MappingProxyType(d))

    def get(self, key: str, default: float = 0.0) -> float:
        return self.values.get(key, default)

    def items(self):
        return self.values.items()

    def keys(self):
        return self.values.keys()

    def values(self):
        return self.values.values()

@dataclass(frozen=True)
class TraitDriftEvent:
    """Единичная запись о давлении мира на личность.
    
    Не изменяет состояние напрямую. 
    Является входом для DriveResolver для вычисления проекции драйвов.
    """
    npc_id: str
    trait: str       # Имя драйва (fear, control, significance, desire)
    delta: float     # Величина деформации (может быть отрицательной)
    source: str      # Каузальный источник (tifl_pressure, will_break, resonance)
    tick: int        # Метка времени симуляции


class L1EventStream(Protocol):
    """Append-only causal trace of identity deformation.
    
    Инвариант L1: L1 never mutates state. L1 only records causal pressure.
    """
    def append(self, event: TraitDriftEvent) -> None:
        """Единственная точка записи L1. Событие неизменяемо после создания."""
        ...

    def query(self, npc_id: str, t_from: int, t_to: Optional[int] = None) -> List[TraitDriftEvent]:
        """Чтение истории деформаций для вычисления проекции DriveResolver'ом."""
        ...