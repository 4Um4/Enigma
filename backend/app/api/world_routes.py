"""
path: backend/app/api/world_routes.py
Назначение: Эндпоинт world_state — единственный способ frontend получить снимок мира.
Зависимости: fastapi, app.domain.snapshot, app.services.integration.world_snapshot_builder
Основные сущности: world_router
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query, HTTPException, Request

from app.domain.snapshot import WorldSnapshotDTO
from app.services.scene_state_manager import get_scene_state_manager

world_router = APIRouter(tags=["world"])


@world_router.get("/world_state", response_model=WorldSnapshotDTO)
def get_world_state(
    request: Request,
    campaign_id: str = Query(..., description="ID кампании"),
    after_tick: Optional[int] = Query(None, description="Вернуть только если tick > after_tick"),
) -> WorldSnapshotDTO:
    """Возвращает текущий снимок мира.
    
    Frontend вызывает после каждого idle_tick.
    Параметр after_tick позволяет не рендерить заново если ничего не изменилось.
    """
    from app.services.integration.world_snapshot_builder import WorldSnapshotBuilder

    # Берём тот же scene_manager что и game_loop — единый источник истины
    mgr = request.app.state.game_loop.scene_manager if request.app.state.game_loop else get_scene_state_manager()
    scene_state = mgr.get_scene_state(campaign_id, location_id="")

    if not scene_state:
        raise HTTPException(status_code=404, detail=f"Campaign '{campaign_id}' not found")

    # Единый источник тика — TemporalEngine, не scene_state (Устав §3)
    _game_loop = request.app.state.game_loop
    if _game_loop:
        current_tick = _game_loop.get_current_tick(campaign_id)
    else:
        from app.services.npc.life_engine import get_life_engine
        current_tick = get_life_engine().get_current_tick(campaign_id)

    # 304 Not Modified: frontend уже на этом тике
    if after_tick is not None and current_tick <= after_tick:
        raise HTTPException(status_code=304, detail="Not modified")

    builder = WorldSnapshotBuilder()
    return builder.build(scene_state=scene_state, tick=current_tick)