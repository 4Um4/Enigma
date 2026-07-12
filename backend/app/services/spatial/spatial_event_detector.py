# -*- coding: utf-8 -*-
"""
Слой 4: SpatialEventDetector — детекция пространственных событий.

Сравнивает позиции NPC до и после тика, генерирует EventDTO:
  - NPC_MOVED: NPC перешёл в другой узел графа
  - NPC_PROXIMITY_CLOSE: два NPC сблизились (< порога)
  - NPC_PROXIMITY_LEAVE: два NPC разошлись (> порога)

Вызывается после MovementEngine (фаза 0), публикует через EventBus (фаза 2).

path: backend/app/services/spatial/spatial_event_detector.py
Назначение: Слой 4 — детекция пространственных событий при движении NPC. Переходы узлов, сближение/расхождение.
Зависимости: domain.events.EventDTO, services.events.event_bus, services.events.event_types
Основные сущности: SpatialEventDetector
"""
from __future__ import annotations

import logging
import math
from typing import Any, Dict, Tuple

from app.domain.events import EventDTO
from app.services.events.event_types import EventType

logger = logging.getLogger(__name__)

# Порогы расстояния в метрах
_PROXIMITY_CLOSE_THRESHOLD: float = 2.0  # ближе = "подошёл"
_PROXIMITY_LEAVE_THRESHOLD: float = 3.5  # дальше = "отошёл"


def _npc_positions_snapshot(scene_state: Dict[str, Any]) -> Dict[str, Tuple[float, float, str]]:
    """Извлекает {(npc_id): (x, y, position_str)} из scene_state.

    Returns:
        Словарь для сравнения между тиками.
    """
    result: Dict[str, Tuple[float, float, str]] = {}
    for npc_id, npc_data in (scene_state.get("npc_positions") or {}).items():
        lp = npc_data.get("local_position") or {}
        x = float(lp.get("x", 0.0))
        y = float(lp.get("y", 0.0))
        pos_str = str(npc_data.get("position", ""))
        result[npc_id] = (x, y, pos_str)
    return result


def _compute_pair_distances(
    positions: Dict[str, Tuple[float, float, str]],
) -> Dict[Tuple[str, str], float]:
    """Вычисляет расстояния между всеми парами NPC."""
    ids = list(positions.keys())
    pairs: Dict[Tuple[str, str], float] = {}
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            x1, y1, _ = positions[ids[i]]
            x2, y2, _ = positions[ids[j]]
            dist = math.hypot(x2 - x1, y2 - y1)
            pairs[(ids[i], ids[j])] = dist
    return pairs


class SpatialEventDetector:
    """Детектор пространственных событий. Без состояния между тиками."""

    def detect_and_publish(
        self,
        old_positions: Dict[str, Tuple[float, float, str]],
        new_scene_state: Dict[str, Any],
    ) -> list[EventDTO]:
        """Сравнивает позиции, публикует события через EventBus.

        Args:
            old_positions: снимок ДО тика (из _npc_positions_snapshot)
            new_scene_state: scene_state ПОСЛЕ применения изменений

        Returns:
            Список созданных EventDTO (для логов/тестов)
        """
        new_positions = _npc_positions_snapshot(new_scene_state)
        events: list[EventDTO] = []

        # 1. Переходы узлов
        for npc_id, (nx, ny, new_node) in new_positions.items():
            if npc_id not in old_positions:
                continue
            _, _, old_node = old_positions[npc_id]
            if old_node and new_node and old_node != new_node:
                event = EventDTO.create(
                    event_type=EventType.NPC_MOVED.value,
                    source=npc_id,
                    payload={
                        "from_node": old_node,
                        "to_node": new_node,
                        "x": nx,
                        "y": ny,
                    },
                    visibility="public",
                    radius=15.0,
                    persistence_level="working",
                )
                events.append(event)
                logger.debug(f"[SPATIAL] {npc_id}: {old_node} → {new_node}")

        # 2. Проксимитет: сравниваем расстояния между парами
        old_pairs = _compute_pair_distances(old_positions)
        new_pairs = _compute_pair_distances(new_positions)

        for pair_key, new_dist in new_pairs.items():
            if pair_key not in old_pairs:
                continue
            old_dist = old_pairs[pair_key]
            npc_a, npc_b = pair_key

            # Были далеко → стали близко
            if (
                old_dist >= _PROXIMITY_CLOSE_THRESHOLD
                and new_dist < _PROXIMITY_CLOSE_THRESHOLD
            ):
                event = EventDTO.create(
                    event_type=EventType.NPC_PROXIMITY_CLOSE.value,
                    source=npc_a,
                    payload={
                        "npc_a": npc_a,
                        "npc_b": npc_b,
                        "distance": round(new_dist, 2),
                    },
                    visibility="public",
                    radius=5.0,
                    persistence_level="working",
                )
                events.append(event)
                logger.debug(
                    f"[SPATIAL] Проксимитет: {npc_a} ↔ {npc_b} ({new_dist:.1f}м)"
                )

            # Были близко → стали далеко
            elif (
                old_dist < _PROXIMITY_LEAVE_THRESHOLD
                and new_dist >= _PROXIMITY_LEAVE_THRESHOLD
            ):
                event = EventDTO.create(
                    event_type=EventType.NPC_PROXIMITY_LEAVE.value,
                    source=npc_a,
                    payload={
                        "npc_a": npc_a,
                        "npc_b": npc_b,
                        "distance": round(new_dist, 2),
                    },
                    visibility="public",
                    radius=5.0,
                    persistence_level="working",
                )
                events.append(event)
                logger.debug(
                    f"[SPATIAL] Расхождение: {npc_a} ↔ {npc_b} ({new_dist:.1f}м)"
                )

        # Публикуем все через EventBus
        if events:
            from app.services.events.event_bus import get_event_bus

            bus = get_event_bus()
            for event in events:
                bus.publish(event)

        return events
