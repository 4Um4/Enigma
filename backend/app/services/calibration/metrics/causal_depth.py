"""
path: backend/app/services/calibration/metrics/causal_depth.py
Назначение: Causal Depth (ТЗ 14.1) — ЗАГЛУШКА-ОТКАЗ, не фейк:
    compute() возвращает None. Runtime-улики (S213): у диалоговых
    TraitDriftEvent tick_id=0 (нет временной оси для цепочек), а
    проводка CausalEntry (models/psychological.py:56) в наблюдаемый
    контур не археологизирована. Молчаливый ноль = фейк метрики
    (табу ADR-O-361) — поэтому явный None + DEBT-CAUSAL-DEPTH.
Зависимости: .base.
Основные сущности: CausalDepth.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from app.services.calibration.metrics.base import CalibrationMetric


class CausalDepth(CalibrationMetric):
    name = "causal_depth"

    def update(
        self,
        tick: int,
        state_snapshot: Dict[str, Dict[str, Any]],
        event: Dict[str, Any] | None = None,
    ) -> None:
        # Ничего не накапливаем: источника цепочек в M0 нет (см. докстринг).
        return

    def compute(self) -> Optional[float]:
        return None  # DEBT-CAUSAL-DEPTH (S213): источник не подключён

    def reset(self) -> None:
        return