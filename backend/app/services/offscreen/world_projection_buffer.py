"""
path: backend/app/services/offscreen/world_projection_buffer.py
Назначение: Shadow causality layer. Reads committed world state, builds narrative
diff, generates WorldProjectionEvent[] как производный слой.
НЕ мутирует первичную реальность (scene_state, npc_states).
Зависимости: app.domain.world_projection
"""
from __future__ import annotations

import logging
import uuid
from typing import List, Dict, Any

from app.domain.world_projection import WorldProjectionEvent, ProjectionType

logger = logging.getLogger(__name__)


class WorldProjectionBuffer:
    """Stateless causal projection engine. Генерирует вторичные эффекты
    (слухи, репутацию) из committed state.

    Вызывается в конце Фазы 10 (после commit). Является чистой функцией (pure function).
    НЕ хранит состояние между тиками. Исторические данные предоставляются вызывающим кодом.
    """

    def project(
        self,
        tick: int,
        campaign_id: str,
        location_id: str,
        all_npcs_raw: List[Dict[str, Any]],
        significant_events: List[Dict[str, Any]],
        previous_npcs_raw: List[Dict[str, Any]],  # Обязательный вход. Отсутствие = баг.
    ) -> List[WorldProjectionEvent]:
        """Строит проекцию последствий. НЕ мутирует входные данные. Stateless.
        Форма: project(state_t, state_t-1) → WorldProjectionEvent[]
        """
        projections: List[WorldProjectionEvent] = []

        # 1. Анализ significant_events на предмет рождения слухов
        for event in significant_events:
            if event.get("type") in ("combat", "death", "steal"):
                projections.append(
                    WorldProjectionEvent(
                        event_id=f"proj_{uuid.uuid4().hex[:8]}",
                        tick=tick,
                        projection_type=ProjectionType.RUMOR,
                        source_id=event.get("source", "world"),
                        location_id=location_id,
                        description=f"Прошёл слух о событии: {event.get('description', 'что-то случилось')}",
                        salience=0.8 if event.get("type") == "death" else 0.5,
                    )
                )

        # 2. Анализ изменений состояния NPC (строгий diff state_t vs state_t-1)
        _prev_map = {
            (n.get("npc_id") or n.get("id")): n
            for n in previous_npcs_raw
            if n.get("npc_id") != "player"
        }

        for npc_dict in all_npcs_raw:
            npc_id = npc_dict.get("npc_id") or npc_dict.get("id")
            if not npc_id or npc_id == "player":
                continue

            prev_state = _prev_map.get(npc_id, {})

            # Детект кровотечения/ран для вторичных эффектов
            current_bs = npc_dict.get("body_state", {})
            prev_bs = prev_state.get("body_state", {})

            if (
                current_bs.get("blood_loss", 0) > 0.5
                and prev_bs.get("blood_loss", 0) <= 0.5
            ):
                projections.append(
                    WorldProjectionEvent(
                        event_id=f"proj_{uuid.uuid4().hex[:8]}",
                        tick=tick,
                        projection_type=ProjectionType.AMBIENT,
                        source_id=npc_id,
                        location_id=location_id,
                        description=f"{npc_dict.get('name', npc_id)} сильно истекает кровью.",
                        salience=0.6,
                    )
                )

        return projections
