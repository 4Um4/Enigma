"""
Пространственные события (Фаза 3.1).

Отслеживает переходы расстояний player→NPC между ходами.
Генерирует события: proximity_close, proximity_leave.

path: /backend/app/services/spatial/spatial_events.py
Назначение: Детекция переходов расстояний player→NPC между ходами
Зависимости: dataclasses, typing
Основные сущности: SpatialEvent, detect_transitions

Контракт:
- detect_transitions() — чистая функция, НЕ пишет состояние
- Вызывающий (game_loop) хранит prev_distances и решает что делать с результатами
- События идут в shared_context + SceneContinuity, НЕ в MicroEvent (разные домены)
"""

from dataclasses import dataclass
from typing import Dict, List


@dataclass(frozen=True)
class SpatialEvent:
    """Переход расстояния между ходами."""
    npc_id: str
    event_type: str          # "proximity_close" | "proximity_leave"
    prev_distance: float
    new_distance: float


# Пороги (метры) — согласованы с ROAD_MAP
PROXIMITY_CLOSE_THRESHOLD: float = 2.0    # ближе → событие приближения
PROXIMITY_LEAVE_THRESHOLD: float = 5.0    # дальше → событие отдаления


def detect_transitions(
    prev_distances: Dict[str, float],
    curr_distances: Dict[str, float],
    close_threshold: float = PROXIMITY_CLOSE_THRESHOLD,
    leave_threshold: float = PROXIMITY_LEAVE_THRESHOLD,
) -> List[SpatialEvent]:
    """
    Сравнивает расстояния текущего и предыдущего ходов.

    Правила перехода:
    - proximity_close: prev >= close_threshold AND curr < close_threshold
    - proximity_leave: prev < leave_threshold AND curr >= leave_threshold

    NPC отсутствующий в одном из словарей — пропускается.
    """
    events: List[SpatialEvent] = []

    for npc_id, curr_dist in curr_distances.items():
        if npc_id not in prev_distances:
            continue
        prev_dist = prev_distances[npc_id]

        # Приближение: пересёк порог сверху вниз
        if prev_dist >= close_threshold and curr_dist < close_threshold:
            events.append(SpatialEvent(
                npc_id=npc_id,
                event_type="proximity_close",
                prev_distance=prev_dist,
                new_distance=curr_dist,
            ))
        # Отдаление: пересёк порог снизу вверх
        elif prev_dist < leave_threshold and curr_dist >= leave_threshold:
            events.append(SpatialEvent(
                npc_id=npc_id,
                event_type="proximity_leave",
                prev_distance=prev_dist,
                new_distance=curr_dist,
            ))

    return events