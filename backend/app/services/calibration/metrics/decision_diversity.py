"""
path: backend/app/services/calibration/metrics/decision_diversity.py
Назначение: Decision Diversity (ТЗ 14.1/14.2) — источник IntentEventAdapter:
    mean по NPC от unique(labels)/total(decisions). Label = intent_type из
    NPC_SPOKE/коммуникативных событий ( ObservabilityTap v2 ). Решение
    DEBT-INTENT-SOURCE: npc["intent"] писателя нет — датчик на шине.
Зависимости: .base, ..observability_tap.DECISION_EVENT_VALUES.
Основные сущности: DecisionDiversity.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Set

from app.services.calibration.metrics.base import CalibrationMetric
from app.services.calibration.observability_tap import DECISION_EVENT_VALUES

_K_RECORDS = "records"


class DecisionDiversity(CalibrationMetric):
    name = "decision_diversity"

    def __init__(self) -> None:
        self._seen: Dict[str, Set[str]] = {}
        self._totals: Dict[str, int] = {}

    def update(self, tick, state_snapshot, event=None) -> None:
        records: List[Any] = (event or {}).get(_K_RECORDS, [])
        for event_type, source, label in records:
            if event_type not in DECISION_EVENT_VALUES:
                continue
            self._seen.setdefault(source, set()).add(str(label))
            self._totals[source] = self._totals.get(source, 0) + 1

    def compute(self) -> Optional[float]:
        ratios = [
            len(self._seen[npc]) / total
            for npc, total in self._totals.items()
            if total > 0
        ]
        if not ratios:
            return None
        return sum(ratios) / len(ratios)

    def reset(self) -> None:
        self._seen.clear()
        self._totals.clear()