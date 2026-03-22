# -*- coding: utf-8 -*-
"""
Streaming routes — SSE эндпоинт для /api/game/action/stream

РЕФАКТОРИНГ S.0: routes_stream.py теперь ТОЛЬКО транспорт.
Вся игровая логика (ActionClassifier, PhysicsValidator, NPC Psychology,
SceneState, S.0 player_target, name_forms) живёт в orchestrator.stream_turn().

routes_stream.py делает ровно три вещи:
  1. Принимает HTTP запрос
  2. Вызывает orchestrator.stream_turn()
  3. Пересылает SSE события клиенту

Формат SSE событий (не меняется):
  data: {"type":"ping"}
  data: {"type":"status",      "text":"Мастер думает..."}
  data: {"type":"action_type", "value":"SOCIAL"}
  data: {"type":"model",       "data":{...}}
  data: {"type":"npc",         "data":[...]}
  data: {"type":"token",       "text":"Вы ", "n":1}
  data: {"type":"done",        "tokens":512, "ms":8200, "tps":65}
"""

from __future__ import annotations

import json
from datetime import datetime

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.services.orchestrator import GameOrchestrator
from app.services.player_session_service import player_session_service
from app.services.campaign_state_service import get_campaign_state_service

router = APIRouter()

_orchestrator = GameOrchestrator()
_campaign_service = get_campaign_state_service()


def _sse(event: dict) -> str:
    """Форматирует dict в строку SSE события."""
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


@router.post("/game/action/stream")
async def game_action_stream(request: dict):
    """
    SSE эндпоинт — токены идут в браузер по мере генерации DM агента.

    Принимает:
        {
          "player":   "Демеург",
          "campaign": "demo-campaign",
          "action":   "осматриваюсь вокруг"
        }

    Возвращает Server-Sent Events поток.
    Вся логика в orchestrator.stream_turn() — здесь только транспорт.
    """
    player      = request.get("player")
    campaign_id = request.get("campaign")
    action_text = request.get("action")

    if not player or not campaign_id or not action_text:
        raise HTTPException(
            status_code=400,
            detail="Поля 'player', 'campaign', 'action' обязательны"
        )

    # Проверка сессии
    session = player_session_service.get_session(campaign_id)
    if session is None:
        raise HTTPException(
            status_code=412,
            detail=f"Сессия не найдена для кампании '{campaign_id}'"
        )

    if not player_session_service.is_player_active(campaign_id, player):
        session.active = True
        session.last_heartbeat = datetime.now()
        if not player_session_service.is_player_active(campaign_id, player):
            raise HTTPException(
                status_code=412,
                detail=f"Игрок '{player}' не активен"
            )

    # Получаем локацию из campaign_state
    location = "tavern_silver_wolf"
    campaign_state = _campaign_service.get_campaign_state(campaign_id)
    if campaign_state:
        saved = campaign_state.metadata.get("current_location")
        if saved:
            location = saved

    async def event_generator():
        """
        Простой генератор: вызывает orchestrator.stream_turn() и
        пересылает всё что оттуда приходит.
        """
        async for event in _orchestrator.stream_turn(
            campaign_id=campaign_id,
            player=player,
            action_text=action_text,
            location=location,
            campaign_state=campaign_state,
        ):
            yield _sse(event)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control":     "no-cache",
            "X-Accel-Buffering": "no",
            "Connection":        "keep-alive",
        },
    )