# backend/app/domain/epistemic_dispositions.py
"""
path: /project/backend/app/domain/epistemic_dispositions.py
Назначение: Слой 3 (S211, R7) — архетип-дифференциация эпистемических действий.
            Один belief → разные интенты по натуре агента. Симметрично
            _steal_affinity (S209) и _DUTY_TABLE (вертикальная ось реакций —
            НЕ смешивается: disposition — горизонтальная ось действий по убеждению).
Зависимости: нет (чистые данные)
Основные сущности: EPISTEMIC_DISPOSITIONS, get_epistemic_disposition
"""

from typing import Dict

# Калибруемые веса (Calibration Laboratory, ADR-O-361): множители поверх
# базового epistemic_boost = max_confidence. Табу: npc_id-хардкоды.
EPISTEMIC_DISPOSITIONS: Dict[str, Dict[str, float]] = {
    # Хранитель порядка: доносит властям, действует по долгу
    "guard":         {"report": 1.4, "warn": 0.5, "attack": 0.4, "spread_rumor": 0.0, "talk": 0.2},
    # Хозяйка зала: информация = валюта; шепчет по углам
    "maid":          {"report": 0.1, "warn": 0.3, "attack": 0.0, "spread_rumor": 1.3, "talk": 0.6},
    "barmaid":       {"report": 0.1, "warn": 0.3, "attack": 0.0, "spread_rumor": 1.3, "talk": 0.6},
    # Торговец: защищает имущество, предупреждает — прямое действие
    "merchant":      {"report": 0.4, "warn": 1.4, "attack": 0.3, "spread_rumor": 0.2, "talk": 0.3},
    # Хозяин таверны: сохраняет порядок НЕ шума; обсуждает, не доносит
    "tavern_keeper": {"report": 0.2, "warn": 0.6, "attack": 0.3, "spread_rumor": 0.3, "talk": 1.2},
    "innkeeper":     {"report": 0.2, "warn": 0.6, "attack": 0.3, "spread_rumor": 0.3, "talk": 1.2},
    # Дефолт: осторожное предупреждение (текущее поведение R7-эры ~ монокультуры)
    "commoner":      {"report": 0.2, "warn": 1.0, "attack": 0.3, "spread_rumor": 0.3, "talk": 0.4},
    # Преступник: знает, но молчит — не доносит и не предупреждает жертву
    "thief":         {"report": 0.0, "warn": 0.1, "attack": 0.0, "spread_rumor": 0.2, "talk": 0.2},
    "bandit":        {"report": 0.0, "warn": 0.1, "attack": 0.2, "spread_rumor": 0.2, "talk": 0.2},
    # Священник: увещевает, не карает
    "priest":        {"report": 0.3, "warn": 0.8, "attack": 0.0, "spread_rumor": 0.1, "talk": 0.9},
}

_DEFAULT_DISPOSITION: Dict[str, float] = EPISTEMIC_DISPOSITIONS["commoner"]


def get_epistemic_disposition(archetype: str) -> Dict[str, float]:
    """S211: диспозиция агента по архетипу. Неизвестный архетип → commoner."""
    return EPISTEMIC_DISPOSITIONS.get(archetype, _DEFAULT_DISPOSITION)