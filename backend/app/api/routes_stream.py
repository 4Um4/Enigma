# -*- coding: utf-8 -*-
"""
Streaming routes — SSE эндпоинт для /api/game/action/stream

Игрок видит текст по мере генерации (эффект печатающей машинки).
Первый токен появляется через ~500ms вместо ожидания 8-30 секунд.

Формат SSE событий:
  data: {"type":"status", "text":"Мастер думает..."}      ← подготовка
  data: {"type":"token",  "text":"Вы ", "n":1}            ← токен
  data: {"type":"token",  "text":"видите", "n":2}         ← токен
  ...
  data: {"type":"npc",    "data":[...]}                   ← реакции NPC
  data: {"type":"done",   "tokens":512, "ms":8200, "tps":65}  ← финал
"""

from __future__ import annotations

import json
import time
from datetime import datetime

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.services.orchestrator import GameOrchestrator
from app.services.player_session_service import player_session_service
from app.services.character_service import CharacterService
from app.services.campaign_state_service import get_campaign_state_service
from app.models.schemas import PlayerAction, ChatTurnRequest, ModelSelection, ModelProvider
from app.services.llm.router import get_router, Capability
from app.services.llm.provider_manager import get_model_pool
from app.core.config import settings

router = APIRouter()

# Используем тот же оркестратор что и routes.py
_orchestrator = GameOrchestrator()
_character_service = CharacterService()
_campaign_service = get_campaign_state_service()


def _sse(event: dict) -> str:
    """Форматирует dict в строку SSE события."""
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


@router.post("/game/action/stream")
async def game_action_stream(request: dict):
    """
    SSE эндпоинт — токены идут в браузер по мере генерации DM агента.

    Принимает тот же формат что /api/game/action:
        {
          "player":   "Демеург",
          "campaign": "demo-campaign",
          "action":   "осматриваюсь вокруг"
        }

    Возвращает Server-Sent Events поток.
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

    # Получаем локацию
    location = "Таверна Серебряный Волк"
    campaign_state = _campaign_service.get_campaign_state(campaign_id)
    if campaign_state:
        saved = campaign_state.metadata.get("current_location")
        if saved:
            location = saved

    async def event_generator():
        """Генератор SSE событий."""
        start_ms = time.time() * 1000
        token_count = 0
        # Отправляем пустое событие чтобы разбудить буферизацию
        yield _sse({"type": "ping"})

        # ── 1. Статус: начинаем обработку ──────────────────────────────────
        yield _sse({"type": "status", "text": "Мастер думает..."})

        # ── 2. Запускаем Rules и NPC агентов (синхронно, без стриминга) ─────
        actions = [PlayerAction(player_name=player, action=action_text)]

        try:
            rules_result = await _run_rules_agent(actions)
        except Exception:
            rules_result = {"checks": []}

        # Мета: какие модели ПЛАНИРУЕТ роутер для DM/NPC (для UI/дебага).
        # Важно: реальные модели могут отличаться при фоллбэках, но для локального
        # пула (max_loaded=1) и фиксированных предпочтений это обычно совпадает.
        try:
            router_llm = get_router()
            pool = get_model_pool()

            dm_key = router_llm.select_model(Capability.NARRATIVE)
            npc_key = router_llm.select_model(Capability.DIALOGUE)

            dm_cfg = pool.get_model_config(dm_key) if pool else None
            npc_cfg = pool.get_model_config(npc_key) if pool else None

            yield _sse({
                "type": "model",
                "data": {
                    "dm": {
                        "key": dm_key,
                        "name": dm_cfg.name if dm_cfg else dm_key,
                        "provider": (dm_cfg.provider_type.value if dm_cfg else "unknown"),
                        "path": (dm_cfg.path if dm_cfg else None),
                    },
                    "npc": {
                        "key": npc_key,
                        "name": npc_cfg.name if npc_cfg else npc_key,
                        "provider": (npc_cfg.provider_type.value if npc_cfg else "unknown"),
                        "path": (npc_cfg.path if npc_cfg else None),
                    },
                    "active_pool_model": getattr(pool, "active_model_key", None),
                },
            })
        except Exception:
            pass

        try:
            npc_result = await _run_npc_agent(campaign_id, location, actions)
        except Exception:
            npc_result = {"npc_reactions": [], "npc_memory_updates": []}

        # ── 3. Стримим DM агента ────────────────────────────────────────────
        yield _sse({"type": "status", "text": "Мастер рассказывает..."})

        world_result = {"world_events": []}

        try:
            async for token in _orchestrator.dm_agent.stream_narrate(
                location=location,
                actions=actions,
                rules_result=rules_result,
                npc_result=npc_result,
                world_result=world_result,
                world_canon_exists=False,
                context=None,
            ):
                token_count += 1
                yield _sse({"type": "token", "text": token, "n": token_count})

        except Exception as e:
            yield _sse({"type": "error", "text": str(e)})
            return

        # ── 4. Отправляем реакции NPC ───────────────────────────────────────
        npc_reactions = npc_result.get("npc_reactions", [])
        if npc_reactions:
            # Дополнительно пробрасываем мету о модели, если есть (не ломает старый UI)
            yield _sse({
                "type": "npc",
                "data": npc_reactions,
                "model": npc_result.get("model"),
            })

        # ── 5. Финальный пакет со статистикой ──────────────────────────────
        elapsed_ms = int(time.time() * 1000 - start_ms)
        tps = round(token_count / (elapsed_ms / 1000), 1) if elapsed_ms > 0 else 0

        yield _sse({
            "type":   "done",
            "tokens": token_count,
            "ms":     elapsed_ms,
            "tps":    tps,
        })

        # ── 6. Сохраняем в память (фоново) ─────────────────────────────────
        try:
            _orchestrator.layered_memory.write_session_memory(
                campaign_id,
                {
                    "location":     location,
                    "last_actions": [{"player": player, "action": action_text}],
                    "dice_input_required": False,
                },
            )
        except Exception:
            pass  # Не ломаем стрим из-за ошибки памяти

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control":    "no-cache",
            "X-Accel-Buffering": "no",
            "Connection":       "keep-alive",
        },
    )


# ──────────────────────────────────────────────────────────────────────────────
# Вспомогательные async обёртки для агентов
# ──────────────────────────────────────────────────────────────────────────────

async def _run_rules_agent(actions: list) -> dict:
    """Запускает rules агента в thread pool (он синхронный)."""
    import asyncio
    return await asyncio.to_thread(
        _orchestrator.rules_agent.run, actions
    )


async def _run_npc_agent(campaign_id: str, location: str, actions: list) -> dict:
    """Запускает npc агента в thread pool."""
    import asyncio
    npc_memory = _orchestrator.layered_memory.read_npc_memory(
        campaign_id, limit=10
    )
    return await asyncio.to_thread(
        _orchestrator.npc_agent.run,
        location, actions, npc_memory, None, "mass"
    )
