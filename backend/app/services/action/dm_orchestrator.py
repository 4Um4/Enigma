# backend/app/services/action/dm_orchestrator.py
"""
path: backend/app/services/action/dm_orchestrator.py
Назначение: Фасад DM — объединяет Router + Scene Builder + Validator.
Зависимости: dm_router, dm_scene_builder
Основные сущности: DMOrchestrator, DMResult
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Dict, List, Optional

from app.services.action.dm_router import DMRouter, RouterResult
from app.services.action.dm_scene_builder import DMSceneBuilder, SceneContext

if TYPE_CHECKING:
    from app.services.npc.decision_hub import EventContext


@dataclass(frozen=True)
class DMResult:
    """
    Полный результат работы DM (этапы 1-2-3).
    """
    is_valid: bool
    event_context: Optional[EventContext] = None
    scene_context: Optional[SceneContext] = None
    error: Optional[str] = None
    
    @property
    def can_proceed(self) -> bool:
        """Можно ли передавать в DecisionHub?"""
        return self.is_valid and self.event_context is not None


class DMOrchestrator:
    """
    Фасад DM System.
    
    Объединяет:
      - Router (этап 1): классификация действия
      - Scene Builder (этап 2): контекст сцены
      - Validator (этап 3): проверка возможности
    
    DM = координатор, не принимает решений за NPC.
    """
    
    def __init__(self) -> None:
        self._router = DMRouter()
        self._scene_builder = DMSceneBuilder()
    
    def process_player_action(
        self,
        raw_input: str,
        player_data: Dict[str, Any],
        player_markers: List[str],
        target_npc_id: Optional[str],
        spatial_data: Dict[str, Any],
        current_day: int,
        current_tick: int,
    ) -> DMResult:
        """
        Полный pipeline DM: Router → Scene Builder → Validator.
        
        Возвращает DMResult с EventContext, готовым для DecisionHub.
        """
        # --- Этап 1: Router (классификация + базовая валидация) ---
        router_result = self._router.parse_and_validate(
            raw_input=raw_input,
            player_data=player_data,
            player_markers=player_markers,
            target_npc_id=target_npc_id,
            distance=spatial_data.get("distance_to_target", 999.0),
            location=spatial_data.get("location_id", "unknown"),
            current_day=current_day,
            current_tick=current_tick,
        )
        
        if not router_result.is_valid:
            return DMResult(
                is_valid=False,
                error=f"Router: {router_result.error.value} — {router_result.error_details}"
            )
        
        # --- Этап 2: Scene Builder (контекст сцены) ---
        scene_ctx = self._scene_builder.build_scene_context(
            player_location=spatial_data.get("location_id", "unknown"),
            spatial_data=spatial_data,
            event_ctx=router_result.event_context,
        )
        
        # Обогащаем EventContext данными сцены
        enriched_event = self._scene_builder.enrich_event_context(
            router_result.event_context,
            scene_ctx,
        )
        
        # --- Этап 3: Дополнительная валидация (Scene-based) ---
        # Проверка: цель NPC реально видит игрока?
        if target_npc_id and target_npc_id not in scene_ctx.line_of_sight:
            return DMResult(
                is_valid=False,
                error=f"Validator: NPC '{target_npc_id}' не видит игрока — действие невозможно"
            )
        
        return DMResult(
            is_valid=True,
            event_context=enriched_event,
            scene_context=scene_ctx,
        )