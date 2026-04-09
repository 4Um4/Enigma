# backend/app/services/action/dm_scene_builder.py
"""
path: backend/app/services/action/dm_scene_builder.py
Назначение: Этап 2 DM — Scene Builder. Определение "здесь и сейчас".
Зависимости: app.services.npc.decision_hub.EventContext
Основные сущности: SceneContext, DMSceneBuilder
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Dict, List, Optional, Set

if TYPE_CHECKING:
    from app.services.npc.decision_hub import EventContext


@dataclass(frozen=True)
class SceneContext:
    """
    Контекст сцены — что реально происходит "здесь и сейчас".
    DM Scene Builder определяет это, не принимая решений.
    """
    location_id: str
    nearby_npcs: List[Dict[str, Any]]  # NPC в радиусе видимости
    visible_objects: List[str]
    environmental_modifiers: Dict[str, float] = field(default_factory=dict)
    line_of_sight: Dict[str, bool] = field(default_factory=dict)  # npc_id -> видит ли игрока


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
        spatial_data: Dict[str, Any],  # Из R4 Spatial System
        event_ctx: EventContext,
    ) -> SceneContext:
        """
        Строит полный контекст сцены на основе пространственных данных.
        """
        # Извлекаем NPC в радиусе видимости
        all_npcs = spatial_data.get("npcs", [])
        nearby_npcs = self._filter_by_visibility(all_npcs, player_location, spatial_data)
        
        # Рассчитываем LOS для каждого NPC
        los = self._calculate_los(nearby_npcs, player_location, spatial_data)
        
        # Environmental modifiers (R4.4)
        modifiers = self._get_environmental_modifiers(spatial_data)
        
        # Обновляем EventContext witness_count (теперь точно!)
        # Это важно: witness_count должен считаться ПОСЛЕ фильтрации видимости
        visible_witnesses = sum(1 for npc in nearby_npcs if los.get(npc["id"], False))
        
        # Возвращаем SceneContext
        return SceneContext(
            location_id=player_location,
            nearby_npcs=nearby_npcs,
            visible_objects=spatial_data.get("objects", []),
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
                continue  # NPC в другой локации
            
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
        """
        Line of Sight — кто видит игрока.
        Учитывает: свет, препятствия, направление взгляда NPC.
        """
        los = {}
        light_level = spatial_data.get("light_level", 1.0)  # 0.0-1.0
        
        for npc in npcs:
            npc_id = npc["id"]
            distance = npc.get("distance_to_player", 999.0)
            
            # Базовая видимость: чем ближе, тем лучше видно
            base_visibility = max(0.0, 1.0 - (distance / 20.0))
            
            # Модификатор света
            visibility = base_visibility * light_level
            
            # NPC смотрит в сторону игрока?
            facing_player = npc.get("facing_towards_player", True)
            if not facing_player:
                visibility *= 0.3  # Сложно заметить, если не смотрит
            
            los[npc_id] = visibility > 0.2  # Порог видимости
        
        return los
    
    def _get_environmental_modifiers(self, spatial_data: Dict) -> Dict[str, float]:
        """Извлекает модификаторы среды (R4.4)."""
        return {
            "light": spatial_data.get("light_level", 1.0),
            "noise": spatial_data.get("noise_level", 0.0),
            "density": spatial_data.get("crowd_density", 0.0),
            "danger": spatial_data.get("ambient_danger", 0.0),
        }
    
    def enrich_event_context(
        self,
        event_ctx: EventContext,
        scene_ctx: SceneContext,
    ) -> EventContext:
        """
        Обогащает EventContext данными сцены.
        EventContext frozen — создаём копию через dataclass.replace().
        """
        # Пересчитываем witness_count на основе реальной видимости
        visible_count = sum(1 for visible in scene_ctx.line_of sight.values() if visible)
        
        # Не мутируем исходный контекст, создаём обновлённую копию
        return dataclasses.replace(
            event_ctx,
            witness_count=visible_count,
        )