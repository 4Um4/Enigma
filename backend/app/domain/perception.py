# path: backend/app/domain/perception.py
# Назначение: Контракты феноменологического восприятия (ТЗ EMBODIED UI PERCEPTION).
# Промежуточные DTO между каузальной симуляцией и линзой игрока.
# Зависимости: dataclasses, typing

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class ProjectionFrame:
    """Моментальный феноменологический снимок NPC (T+0).
    Порождается CFRM. Владелец — каузальное давление, а не протухший стейт.
    Без этого Perception Service слеп к становлению состояния."""
    entity_id: str
    threat: float                 # Актуальная угроза (из projected_kernel)
    suppression: float            # Подавление инициативы (initiative_suppression)
    salience: float               # Вычисленная значимость для внимания
    embodied_signal: str          # Социальный сигнал: "avoid_gaze", "freeze", "calm"
    expires_tick: int             # Каузальный срок годности


@dataclass(frozen=True)
class PerceptionEvent:
    """Единица смысла, попадающая в поле внимания.
    Генерируется PhenomenologyProjectionService из ProjectionFrame (T+0)."""
    salience: float               # 0.0-1.0 Важность события
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