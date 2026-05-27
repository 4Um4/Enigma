# path: backend/app/domain/perception.py
# Назначение: Контракты феноменологического восприятия (ТЗ EMBODIED UI PERCEPTION).
# Промежуточные DTO между каузальной симуляцией и линзой игрока.
# Зависимости: dataclasses, typing

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class PerceptionEvent:
    """Единица смысла, попадающая в поле внимания.
    Генерируется PhenomenologyProjectionService из сырых стейтов."""
    salience: float               # 0.0-1.0 Важность события (вычисляется из magnitude дельт)
    category: Literal[
        "ATMOSPHERE",             # Фоновое давление (Слой 2)
        "PERIPHERAL",             # Кинетика/поведение NPC (Слой 1)
        "CENTRAL",                # Фокус внимания (Слой 3)
        "RUMOR",                  # Слух (Слой 4)
        "RECONSTRUCTION"          # Пост-фактум (Слой 5)
    ]
    semantic_seed: str            # Наблюдение: "замер", "крик", "запах_крови"
    source_cluster: str           # ID кластера/NPC
    expiration_tick: int          # Когда событие теряет актуальность