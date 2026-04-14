# backend/app/services/action/dm_scene_builder.py
"""
path: backend/app/services/action/dm_scene_builder.py
Назначение: Этап 2 DM — Scene Builder. Определение "здесь и сейчас".
Зависимости: app.services.action.dm_router.RawEvent, app.services.npc.decision_hub.EventContext
Основные сущности: SceneContext, DMSceneBuilder
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set

if TYPE_CHECKING:
    from app.services.action.dm_router import RawEvent
    from app.services.npc.decision_hub import EventContext


@dataclass(frozen=True)
class SceneContext:
    """
    Контекст сцены — что реально происходит "здесь и сейчас".
    DM Scene Builder определяет это, не принимая решений.
    """
    location_id: str
    nearby_npcs: List[Dict[str, Any]]
    visible_objects: List[str]
    environmental_modifiers: Dict[str, float] = field(default_factory=dict)
    line_of_sight: Dict[str, bool] = field(default_factory=dict)


class DMSceneBuilder:
    """
    Этап 2 DM — Scene Builder.
    
    Ответственность:
      - Определить кто/что в сцене
      - Применить environmental modifiers (свет, шум, плотность)
      - НЕ принимать решения — только описывать сцену
    """
    
    def build_scene_context(
        self,
        player_location: str,
        spatial_data: Dict[str, Any],
        raw_event: Optional[Any] = None,
    ) -> SceneContext:
        """
        Строит полный контекст сцены на основе пространственных данных.
        Salience Engine фильтрует объекты по важности.
        """
        all_npcs = spatial_data.get("npcs", [])
        nearby_npcs = self._filter_by_visibility(all_npcs, player_location, spatial_data)
        los = self._calculate_los(nearby_npcs, player_location, spatial_data)
        modifiers = self._get_environmental_modifiers(spatial_data)
        
        # Salience Engine: фильтруем объекты перед передачей в LLM
        _event_type = getattr(raw_event, "event_type", "player_interacts") if raw_event else "player_interacts"
        _raw_objects = spatial_data.get("objects", {})
        
        from app.services.scene.salience_engine import SalienceEngine
        _filtered_pairs = SalienceEngine().get_filtered_objects(
            objects=_raw_objects,
            event_type=_event_type,
            max_npc_stress=0.0,  # stress ещё не доступен на этом этапе
        )
        # Конвертируем обратно в dict для совместимости с SceneContext
        _filtered_objects = {obj_id: obj for obj_id, obj in _filtered_pairs}
        
        return SceneContext(
            location_id=player_location,
            nearby_npcs=nearby_npcs,
            visible_objects=_filtered_objects,
            environmental_modifiers=modifiers,
            line_of_sight=los,
        )
    
    def _filter_by_visibility(
        self,
        npcs: List[Dict],
        player_location: str,
        spatial_data: Dict,
    ) -> List[Dict]:
        """Фильтрует NPC по дистанции видимости."""
        visibility_radius = spatial_data.get("visibility_radius", 20.0)
        
        result = []
        for npc in npcs:
            npc_loc = npc.get("location_id")
            if npc_loc != player_location:
                continue
            distance = npc.get("distance_to_player", 999.0)
            if distance <= visibility_radius:
                result.append(npc)
        
        return result
    
    def _calculate_los(
        self,
        npcs: List[Dict],
        player_location: str,
        spatial_data: Dict,
    ) -> Dict[str, bool]:
        """Line of Sight — кто видит игрока."""
        los = {}
        light_level = spatial_data.get("light_level", 1.0)
        
        for npc in npcs:
            npc_id = npc.get("npc_id", npc.get("id", "unknown"))
            distance = npc.get("distance_to_player", 999.0)
            base_visibility = max(0.0, 1.0 - (distance / 20.0))
            visibility = base_visibility * light_level
            facing_player = npc.get("facing_towards_player", True)
            if not facing_player:
                visibility *= 0.3
            los[npc_id] = visibility > 0.2
        
        return los
    
    def _get_environmental_modifiers(self, spatial_data: Dict) -> Dict[str, float]:
        """Извлекает модификаторы среды (R4.4)."""
        return {
            "light": spatial_data.get("light_level", 1.0),
            "noise": spatial_data.get("noise_level", 0.0),
            "density": spatial_data.get("crowd_density", 0.0),
            "danger": spatial_data.get("ambient_danger", 0.0),
        }
    
    def enrich_raw_event(
        self,
        raw_event: Any,
        scene_context: SceneContext,
    ) -> EventContext:
        """
        Создаёт EventContext из RawEvent + данные сцены.
        SceneBuilder — единственное место где текстовые факты становятся миром.
        """
        from app.services.action.dm_router import RawEvent
        from app.services.npc.decision_hub import EventContext

        visible_count = sum(1 for v in scene_context.line_of_sight.values() if v)

        if isinstance(raw_event, RawEvent):
            return EventContext(
                event_type=raw_event.event_type,
                actor_id=raw_event.actor_id,
                intensity=raw_event.base_intensity,
                witness_count=visible_count,
                location=scene_context.location_id,
                day=0,
            )

        return EventContext(
            event_type="player_interacts",
            actor_id="player",
            witness_count=visible_count,
            location=scene_context.location_id,
        )