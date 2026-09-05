"""
path: backend/app/services/calibration/metrics/loop_rate.py
Назначение: Loop Rate (ТЗ 14.1/14.2): доля переходов тик→тик без смены
    решения (label) — mean по NPC; источник IntentEventAdapter (Tap v2).
    M0-аппроксимация: отношение по всей сессии; окно 20 тиков (ТЗ 14.2) —
    уточнение в M2 при живых длинных сериях.
Зависимости: .base, ..observability_tap.DECISION_EVENT_VALUES.
Основные сущности: LoopRate.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.services.calibration.metrics.base import CalibrationMetric
from app.services.calibration.observability_tap import DECISION_EVENT_VALUES

_K_RECORDS = "records"


class LoopRate(CalibrationMetric):
    name = "loop_rate"

    def __init__(self) -> None:
        self._prev: Dict[str, str] = {}
        self._unchanged: Dict[str, int] = {}
        self._pairs: Dict[str, int] = {}

    def update(
        self,
        tick: int,
        state_snapshot: Dict[str, Dict[str, Any]],
        event: Dict[str, Any] | None = None,
    ) -> None:
        records: List[Any] = (event or {}).get(_K_RECORDS, [])
        last_seen: Dict[str, str] = {}
        for event_type, source, label in records:
            if event_type not in DECISION_EVENT_VALUES:
                continue
            label = str(label)
            prev = self._prev.get(source)
            if prev is not None:
                self._pairs[source] = self._pairs.get(source, 0) + 1
                if label == prev:
                    self._unchanged[source] = self._unchanged.get(source, 0) + 1
            last_seen[source] = label
        # Последний label тика — базис сравнения следующего тика.
        for source, label in last_seen.items():
            self._prev[source] = label

    def compute(self) -> Optional[float]:
        ratios = [
            self._unchanged.get(npc, 0) / pairs
            for npc, pairs in self._pairs.items()
            if pairs > 0
        ]
        if not ratios:
            return None
        return sum(ratios) / len(ratios)

    def reset(self) -> None:
        self._prev.clear()
        self._unchanged.clear()
        self._pairs.clear()