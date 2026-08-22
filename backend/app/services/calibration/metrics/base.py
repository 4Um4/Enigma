"""
path: backend/app/services/calibration/metrics/base.py
Назначение: Контракт метрик лаборатории (План 2.3): стриминг
    update(tick, snapshot, event) → compute(). snapshot = {npc_id: npc_dict}
    (реальные runtime-ключи, археология to_persistence_dict).
Зависимости: стандартная библиотека.
Основные сущности: CalibrationMetric.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional


class CalibrationMetric(ABC):
    name: str

    @abstractmethod
    def update(
        self,
        tick: int,
        state_snapshot: Dict[str, Dict[str, Any]],
        event: Optional[Dict[str, Any]] = None,
    ) -> None:
        ...

    @abstractmethod
    def compute(self) -> Optional[float]:
        ...

    @abstractmethod
    def reset(self) -> None:
        ...