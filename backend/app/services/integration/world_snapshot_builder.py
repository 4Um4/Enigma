# backend/app/services/integration/world_snapshot_builder.py
# Назначение: Собирает WorldSnapshotDTO из финального состояния тика.
# Чистый маппер: dict → DTO. Не лезет в NPCState, DecisionHub, MemoryManager.
# Читает только scene_state dict и мета-данные тика.
# Зависимости: app.domain.snapshot, typing

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

from typing import Dict, List, Optional, Tuple
from app.domain.snapshot import (
    NPCPositionDTO,
    VisibleEventDTO,
    WorldSnapshotDTO,
)


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
        avatar_state: Optional["AvatarStateDTO"] = None, # ADR-035
        all_npcs_raw: Optional[List[Dict]] = None, # ADR-037: Для вычисления среды
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
        self.avatar_state = avatar_state # Проброс проекции в DTO
        location_id = scene_state.get("location_id", "")
        environment = scene_state.get("environment", {})
        version = tick

        # ADR-037: Вычисление средового давления на основе психики NPC в сцене
        ambient_phenomenology = self._compute_ambient_phenomenology(all_npcs_raw)

        return WorldSnapshotDTO(
            tick=tick,
            version=version,
            last_event_id=last_event_id,
            player_position=player_pos,
            npc_positions=npc_positions,
            avatar_state=self.avatar_state, # ADR-035: Внедрение феноменологической проекции
            ambient_phenomenology=ambient_phenomenology, # ADR-037: Средовое давление
            visible_events=visible_events,
            available_actions=self._extract_available_actions(scene_state),
            location_id=location_id,
            weather=environment.get("weather_inside", "unknown"),
            time_of_day=environment.get("time_of_day", "day"),
            game_time_seconds=scene_state.get("game_time_seconds", 0),
            active_traversals=self._extract_active_traversals(scene_state),
        )

    def _extract_npc_positions(
        self, scene_state: Dict
    ) -> List[NPCPositionDTO]:
        """Вытаскивает позиции NPC из scene_state['npc_positions'].
        БАГ I FIX: Фильтрует NPC по текущей локации — NPC в других локациях не отрисовываются."""
        result: List[NPCPositionDTO] = []
        npc_positions = scene_state.get("npc_positions", {})
        current_location = scene_state.get("location_id", "")
        logger.info(f"[TRACE][SNAPSHOT_BUILD] npc_count={len(npc_positions)} keys={list(npc_positions.keys())[:5]} location={current_location}")

        for npc_id, data in npc_positions.items():
            # ADR-048: player читается через _extract_player_position,
            # в npc_positions он не нужен — иначе фронтенд рисует его как NPC
            if npc_id == "player":
                continue
            if not data.get("visible", True):
                continue
            # БАГ I FIX: NPC в другой локации не отрисовываются в текущей
            # ADR-048: location_id — авторитетный источник. "location" — легаси-мусор от переходов.
            npc_loc = data.get("location_id") or data.get("location", "")
            if npc_loc and current_location and npc_loc != current_location:
                continue

            local = data.get("local_position", {})
            logger.info(
                f"[TRACE][SNAPSHOT] "
                f"npc={npc_id} "
                f"x={local.get('x') or 0.0} "
                f"y={local.get('y') or 0.0}"
            )
            result.append(NPCPositionDTO(
                npc_id=npc_id,
                # ADR-FIX: None пробивает дефолт 0.0, если ключ существует. Явный каст.
                x=local.get("x") or 0.0,
                y=local.get("y") or 0.0,
                location_id=data.get("location_id", ""),
                facing=data.get("facing", "south"),
                action=data.get("activity", "idle"),
                display_name=data.get("name", npc_id),
                initiative_suppression=data.get("initiative_suppression", 0.0),
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
        # ADR-048: Игрок читается из единого словаря npc_positions
        spatial = scene_state.get("npc_positions", {}).get("player", {})
        local = spatial.get("local_position", {})
        return (local.get("x", 0.0), local.get("y", 0.0))

    def _extract_active_traversals(self, scene_state: Dict) -> list:
        """Конвертирует TraversalState из scene_state в dict для фронтенда (ADR-019).
        SnapshotBuilder НЕ мутирует scene_state. Только чистая проекция."""
        traversals = scene_state.get("active_traversals", {})
        result = [] # Инициализация аккумулятора
        
        for npc_id, trav in traversals.items():
            if trav.get("status") == "MOVING" and len(trav.get("path_waypoints", [])) >= 2:
                from_xy = trav["path_waypoints"][0]
                to_xy = trav["path_waypoints"][-1]

                result.append({
                    "npc_id": npc_id,
                    "status": "MOVING",
                    "path_waypoints": [[from_xy[0], from_xy[1]], [to_xy[0], to_xy[1]]],
                    "current_waypoint_idx": 0,
                    "started_tick": trav.get("started_tick", 0),
                    "duration_ticks": trav.get("duration_ticks", 1),
                    "speed": trav.get("speed", 2.0),
                    "locomotion": trav.get("locomotion", "WALK")
                })
        return result

    def _compute_ambient_phenomenology(self, all_npcs_raw: Optional[List[Dict]]) -> Optional[Dict[str, float]]:
        """Вычисляет феноменологическое давление среды на основе стресса и страха NPC (ADR-037)."""
        if not all_npcs_raw:
            return None
            
        total_stress, total_fear, count = 0.0, 0.0, 0
        for npc in all_npcs_raw:
            if npc.get("npc_id") == "player":
                continue
            psyche = npc.get("psyche", {})
            total_stress += float(psyche.get("stress", 0.0))
            total_fear += float(psyche.get("fear", 0.0))
            count += 1
            
        if count == 0:
            return None
            
        # Эмоциональная температура: от -1 (ледяное спокойствие) до 1 (паника/агрессия)
        avg_neg_emotion = (total_stress + total_fear) / (2 * count)
        emotional_temperature = (avg_neg_emotion * 2) - 1.0 
        
        # Давление скопления: количество NPC нормализованное
        proximity_compression = min(1.0, count / 5.0) # 5 NPC = максимальное давление
        
        return {
            "emotional_temperature": max(-1.0, min(1.0, emotional_temperature)),
            "proximity_compression": proximity_compression,
            "directional_pressure_bias": [0.0, 0.0] # Заглушка: вычисление вектора требует координат
        }

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
            game_time_seconds=0,
        )