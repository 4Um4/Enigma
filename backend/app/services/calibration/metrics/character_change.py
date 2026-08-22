"""
path: backend/app/services/calibration/metrics/character_change.py
Назначение: Character Change Rate (ТЗ 14.1): средняя нормализованная
    скорость изменения вектора состояния NPC между тиками.
    Поля — подтверждённые runtime-ключи to_persistence_dict (§12.1 —
    ключи константами). Диапазон ~[0, 1].
Зависимости: .base.
Основные сущности: CharacterChangeRate.
"""
from __future__ import annotations

import math
from typing import Any, Dict, Optional, Tuple

from app.services.calibration.metrics.base import CalibrationMetric

_K_PSYCHE = "psyche"
_K_SOCIAL = "social_stats"
# (секция, ключ, min, max) — нормализация в [0, 1]
_FIELDS: Tuple[Tuple[str, str, float, float], ...] = (
    (_K_PSYCHE, "stress", 0.0, 100.0),
    (_K_PSYCHE, "identity_integrity", 0.0, 1.0),
    (_K_PSYCHE, "pressure_resistance", 0.0, 100.0),
    (_K_PSYCHE, "recent_failures", 0.0, 10.0),
    (_K_SOCIAL, "trust", 0.0, 100.0),
    (_K_SOCIAL, "fear_of_player", 0.0, 100.0),
)
_DIMS = len(_FIELDS)


def _vector(npc: Dict[str, Any]) -> Tuple[float, ...]:
    out = []
    for section, key, lo, hi in _FIELDS:
        raw = (npc.get(section) or {}).get(key, lo)
        try:
            value = float(raw)
        except (TypeError, ValueError):
            value = lo
        out.append(min(1.0, max(0.0, (value - lo) / (hi - lo))))
    return tuple(out)


class CharacterChangeRate(CalibrationMetric):
    name = "character_change_rate"

    def __init__(self) -> None:
        self._prev: Dict[str, Tuple[float, ...]] = {}
        self._deltas: list = []

    def update(self, tick, state_snapshot, event=None) -> None:
        for npc_id, npc in state_snapshot.items():
            vec = _vector(npc)
            prev = self._prev.get(npc_id)
            if prev is not None:
                sq = sum((a - b) ** 2 for a, b in zip(vec, prev))
                self._deltas.append(math.sqrt(sq / _DIMS))
            self._prev[npc_id] = vec

    def compute(self) -> Optional[float]:
        if not self._deltas:
            return None
        return sum(self._deltas) / len(self._deltas)

    def reset(self) -> None:
        self._prev.clear()
        self._deltas.clear()