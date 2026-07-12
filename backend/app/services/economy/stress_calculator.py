"""
Единый расчёт стресса от экономики и потребностей.
Используется и в game_loop, и в sandbox — без дублирования.

path: /backend/app/services/economy/stress_calculator.py
Назначение: Единая логика расчёта стресса от экономики/потребностей
Зависимости: app.models.economy (EconomicProfile), app.services.economy.need_engine (NeedEngine)
Основные сущности: calculate_economic_stress()
"""
from __future__ import annotations

from typing import Tuple

from app.models.economy import EconomicProfile
from app.services.economy.need_engine import NeedEngine


def calculate_economic_stress(
    profile: EconomicProfile,
    need_engine: NeedEngine,
) -> Tuple[float, str]:
    """
    Вычисляет прирост стресса от экономических факторов.

    Возвращает:
        (stress_delta, reason) — reason для логирования

    Факторы:
    1. Бедность (wealth < threshold) — микростресс каждый тик
    2. Долги (overdue obligations) — микростресс каждый тик
    3. Критическая потребность (urgency > 0.85) — пропорционально глубине
    """
    total_stress = 0.0
    reasons = []

    # 1. Бедность
    wealth_stress = need_engine.get_wealth_stress(profile)
    if wealth_stress > 0:
        total_stress += wealth_stress
        reasons.append(f"бедность +{wealth_stress:.3f}")

    # 2. Долги
    obligation_stress = need_engine.get_obligation_stress(profile)
    if obligation_stress > 0:
        total_stress += obligation_stress
        reasons.append(f"долги +{obligation_stress:.3f}")

    # 3. Критические потребности — стресс пропорционально глубине
    # (0.95 - 0.85) * 10 = 1.0 стресса/тик при максимуме
    for need in profile.base_needs:
        if need.effective_urgency > 0.85:
            need_stress = (need.effective_urgency - 0.85) * 10.0
            total_stress += need_stress
            reasons.append(f"{need.need_type.value} +{need_stress:.2f}")

    reason_str = ", ".join(reasons) if reasons else ""
    return round(total_stress, 4), reason_str
