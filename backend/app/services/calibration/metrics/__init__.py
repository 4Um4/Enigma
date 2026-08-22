"""
path: backend/app/services/calibration/metrics/__init__.py
Назначение: Пакет метрик M0 (План 2.2): сборка бандла, compute_all.
Зависимости: метрики-модули пакета.
Основные сущности: MetricsBundle, build_metrics_bundle.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.services.calibration.metrics.base import CalibrationMetric
from app.services.calibration.metrics.causal_depth import CausalDepth
from app.services.calibration.metrics.character_change import CharacterChangeRate
from app.services.calibration.metrics.decision_diversity import DecisionDiversity
from app.services.calibration.metrics.event_responsiveness import EventResponsiveness
from app.services.calibration.metrics.loop_rate import LoopRate

__all__ = [
    "CalibrationMetric",
    "CausalDepth",
    "CharacterChangeRate",
    "DecisionDiversity",
    "EventResponsiveness",
    "LoopRate",
    "MetricsBundle",
    "build_metrics_bundle",
]


class MetricsBundle:
    """Стриминговый бандл метрик M0: update по тикам → compute_all."""

    def __init__(self, metrics: List[CalibrationMetric]) -> None:
        self._metrics = metrics

    def update(
        self,
        tick: int,
        state_snapshot: Dict[str, Dict[str, Any]],
        event: Optional[Dict[str, Any]] = None,
    ) -> None:
        for metric in self._metrics:
            metric.update(tick, state_snapshot, event)

    def compute_all(self) -> Dict[str, Optional[float]]:
        return {metric.name: metric.compute() for metric in self._metrics}

    def reset(self) -> None:
        for metric in self._metrics:
            metric.reset()


def build_metrics_bundle() -> MetricsBundle:
    return MetricsBundle(
        [
            CharacterChangeRate(),
            DecisionDiversity(),
            LoopRate(),
            EventResponsiveness(),
            CausalDepth(),
        ]
    )