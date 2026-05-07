# backend/app/services/integration/world_snapshot_builder.py
# Назначение: Собирает WorldSnapshotDTO из финального состояния тика.
# Чистый маппер: dict → DTO. Не лезет в NPCState, DecisionHub, MemoryManager.
# Читает только scene_state dict и мета-данные тика.
# Зависимости: app.domain.snapshot, typing

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Tuple

from app.domain.snapshot import (
    NPCPositionDTO,
    VisibleEventDTO,
    WorldSnapshotDTO,
)

logger = logging.getLogger(__name__)


class WorldSnapshotBuilder:
    """Маппер: scene_state dict → WorldSnapshotDTO.
    
    Не имеет побочных эффектов. Не вызывает логику.
    Только агрегирует то, что уже вычислено другими фазами.
    """

    def build(
        self,
        scene_state: Dict,
        tick: int,
        last_event_id: Optional[str] = None,
    ) -> WorldSnapshotDTO:
        """Собирает снимок из финального состояния тика.
        
        Args:
            scene_state: dict из SceneStateManager.get_scene_state()
            tick: номер текущего тика
            last_event_id: ID последнего обработанного события (опционально)
        """
        if not scene_state:
            return self._empty_snapshot(tick)

        npc_positions = self._extract_npc_positions(scene_state)
        visible_events = self._extract_visible_events(scene_state)
        player_pos = self._extract_player_position(scene_state)
        location_id = scene_state.get("location_id", "")
        environment = scene_state.get("environment", {})
        version = tick

        return WorldSnapshotDTO(
            tick=tick,
            version=version,
            last_event_id=last_event_id,
            player_position=player_pos,
            npc_positions=npc_positions,
            visible_events=visible_events,
            available_actions=self._extract_available_actions(scene_state),
            location_id=location_id,
            weather=environment.get("weather_inside", "unknown"),
            time_of_day=environment.get("time_of_day", "day"),
        )

    def _extract_npc_positions(
        self, scene_state: Dict
    ) -> List[NPCPositionDTO]:
        """Вытаскивает позиции NPC из scene_state['npc_positions']."""
        result: List[NPCPositionDTO] = []
        npc_positions = scene_state.get("npc_positions", {})

        for npc_id, data in npc_positions.items():
            if not data.get("visible", True):
                continue

            local = data.get("local_position", {})
            result.append(NPCPositionDTO(
                npc_id=npc_id,
                x=local.get("x", 0.0),
                y=local.get("y", 0.0),
                location_id=data.get("location_id", ""),
                facing=data.get("facing", "south"),
                action=data.get("activity", "idle"),
                display_name=data.get("name", npc_id),
            ))

        return result

    def _extract_visible_events(
        self, scene_state: Dict
    ) -> List[VisibleEventDTO]:
        """Вытаскивает видимые события.
        
        TODO: когда EventDTO будет интегрирован в scene_state,
        фильтровать по visibility и радиусу от игрока.
        """
        # Пока событий в scene_state нет — пустой список
        return []

    def _extract_player_position(
        self, scene_state: Dict
    ) -> Tuple[float, float]:
        """Вытаскивает координаты игрока."""
        spatial = scene_state.get("player_spatial", {})
        local = spatial.get("local_position", {})
        return (local.get("x", 0.0), local.get("y", 0.0))

    def _extract_available_actions(
        self, scene_state: Dict
    ) -> List[str]:
        """Доступные действия на основе контекста.
        
        TODO: вычислять из ближайших объектов, NPC, инвентаря.
        """
        return ["look", "move", "talk"]

    def _empty_snapshot(self, tick: int) -> WorldSnapshotDTO:
        """Пустой снимок когда scene_state не загружен."""
        return WorldSnapshotDTO(
            tick=tick,
            version=0,
            last_event_id=None,
            player_position=(0.0, 0.0),
            npc_positions=[],
            visible_events=[],
            available_actions=["look", "move"],
            location_id="",
            weather="unknown",
            time_of_day="day",
        )