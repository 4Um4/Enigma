"""
path: backend/app/services/calibration/metrics/event_responsiveness.py
Назначение: Event Responsiveness (ТЗ 14.1/14.2): доля тиков с событиями,
    после которых (тот же/следующий тик) сменилось решение хотя бы у одного
    NPC. Смена решения — по label (intent_type) записей Tap v2.
    Наследует недетерминизм async-слоя (DEBT-QUIESCE): в replay-вердикт
    не входит, только в metrics-отчёт.
Зависимости: .base, ..observability_tap.DECISION_EVENT_VALUES.
Основные сущности: EventResponsiveness.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from app.services.calibration.metrics.base import CalibrationMetric
from app.services.calibration.observability_tap import DECISION_EVENT_VALUES

_K_RECORDS = "records"
_K_COUNT = "count"


class EventResponsiveness(CalibrationMetric):
    name = "event_responsiveness"

    def __init__(self) -> None:
        self._last_label: Dict[str, str] = {}
        self._ticks: List[Tuple[int, bool]] = []

    def update(self, tick, state_snapshot, event=None) -> None:
        records: List[Any] = (event or {}).get(_K_RECORDS, [])
        changed = False
        for event_type, source, label in records:
            if event_type not in DECISION_EVENT_VALUES:
                continue
            label = str(label)
            prev = self._last_label.get(source)
            if prev is not None and label != prev:
                changed = True
            self._last_label[source] = label
        count = int((event or {}).get(_K_COUNT, 0))
        self._ticks.append((count, changed))

    def compute(self) -> Optional[float]:
        event_ticks = [i for i, (c, _) in enumerate(self._ticks) if c > 0]
        if not event_ticks:
            return None
        responsive = 0
        for i in event_ticks:
            if (
                self._ticks[i][1]
                or (i + 1 < len(self._ticks) and self._ticks[i + 1][1])
            ):
                responsive += 1
        return responsive / len(event_ticks)

    def reset(self) -> None:
        self._last_label.clear()
        self._ticks.clear()