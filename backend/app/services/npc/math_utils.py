# backend/app/services/npc/math_utils.py
"""
R3.1 — Математические утилиты для NPC-систем.
Единая точка для saturation, нормализации и кривых затухания.
"""

from __future__ import annotations

import math
from typing import Literal


CurveType = Literal["soft", "sigmoid"]


def apply_saturation(
    current:   float,
    delta:     float,
    min_val:   float = 0.0,
    max_val:   float = 100.0,
    floor:     float = 0.1,
    curve:     CurveType = "soft",
    intensity: float = 1.0,
) -> tuple[float, float]:
    """
    Применяет delta к current с saturation — эффект слабеет у границ диапазона.
    Возвращает (new_value, effective_delta) — effective_delta нужен для логов R4.2.

    curve="soft":    линейный headroom с минимальным порогом floor.
    curve="sigmoid": S-образная кривая — быстро в середине, медленно у краёв.

    intensity > 1.5: hard cap override — saturation игнорируется для критических событий
                     (убийство родственника, катастрофическое предательство).
    """
    # Критическое событие обходит saturation полностью
    if intensity > 1.5:
        new_val = max(min_val, min(max_val, current + delta))
        return new_val, round(new_val - current, 4)

    if curve == "soft":
        if delta > 0:
            headroom = (max_val - current) / (max_val - min_val)
        else:
            headroom = (current - min_val) / (max_val - min_val)
        effective = delta * max(headroom, floor)

    else:  # sigmoid
        if delta > 0:
            distance = max_val - current
        else:
            distance = current - min_val
        # S-кривая: быстро набирает в центре, медленно у границ
        sigmoid = 2.0 / (1.0 + math.exp(-0.1 * distance)) - 1.0
        effective = delta * max(sigmoid, floor)

    new_val = max(min_val, min(max_val, current + effective))
    return round(new_val, 4), round(new_val - current, 4)


def normalize_to_unit(value: float, min_val: float, max_val: float) -> float:
    """
    Нормализует значение из [min_val, max_val] в [-1.0, 1.0].
    Используется при передаче весов из RelationshipStore в DecisionHub.
    """
    if max_val == min_val:
        return 0.0
    mid = (max_val + min_val) / 2.0
    half = (max_val - min_val) / 2.0
    return round((value - mid) / half, 4)