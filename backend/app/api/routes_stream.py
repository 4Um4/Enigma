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

ФАЗА 3A: перед стримингом запускаются NPC Psychology движки:
  ActionClassifier → ThreatAssessor → PerceptionEngine → NPCCognition → PsycheEngine
  Результаты передаются в npc_agent и dm_agent через shared_context.
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

# === ФАЗА 3A: импорты NPC Psychology движков ===
from app.services.action_classifier import classifier, ActionType
from app.services.npc.npc_cognition    import process_player_action, build_npc_prompt, get_inner_thought
from app.services.npc.psyche_engine    import apply_stress, get_behavior_hint
from app.services.npc.threat_assessor  import assess_threat, get_threat_category, apply_threat_to_npc
from app.services.npc.perception_engine import assess_status, get_status_label, get_social_permissions

router = APIRouter()

# Используем тот же оркестратор что и routes.py
_orchestrator = GameOrchestrator()
_character_service = CharacterService()
_campaign_service = get_campaign_state_service()


def _sse(event: dict) -> str:
    """Форматирует dict в строку SSE события."""
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


# ──────────────────────────────────────────────────────────────────────────────
# ФАЗА 3A: синхронный запуск NPC Psychology движков
# Вызывается в event_generator() ДО запуска LLM агентов.
# ──────────────────────────────────────────────────────────────────────────────

def _run_npc_engines(
    location: str,
    action_text: str,
    action_type_str: str,
    char_data: dict,
) -> list:
    """
    Запускает Phase 3A движки для всех NPC в текущей локации.
    Возвращает список npc_contexts (система промптов + психология).
    При ошибке возвращает пустой список — не ломает стрим.
    """
    try:
        npcs_here = _orchestrator._get_npcs_in_location(location)
        if not npcs_here:
            return []

        npc_contexts = []
        player_markers = char_data.get("visible_markers", [])
        reputation     = char_data.get("reputation", {})

        for npc in npcs_here:
            # 1. Оценка угрозы
            threat_score = assess_threat(player_markers, action_type_str, reputation)
            threat_cat   = get_threat_category(threat_score)
            apply_threat_to_npc(npc, threat_score, threat_cat)

            # 2. Восприятие статуса игрока
            status_score = assess_status(player_markers)
            status_label = get_status_label(status_score)
            permissions  = get_social_permissions(player_markers, npc)

            # 3. NPCCognition — изменения доверия/страха
            action_deltas = process_player_action(npc, action_type_str, char_data, threat_score)

            # 4. PsycheEngine — подсказка поведения
            behavior_hint = get_behavior_hint(npc)

            # 5. Сборка системного промпта для NPC агента
            shared_ctx = {
                "location":    location,
                "action_type": action_type_str,
                "action_text": action_text,
            }
            npc_system_prompt = build_npc_prompt(
                npc, char_data, shared_ctx,
                behavior_hint=behavior_hint,
                perceived_status=status_label,
                threat_category=threat_cat,
            )

            # 6. Внутренняя мысль для Debug Mode
            inner_thought = get_inner_thought(npc, shared_ctx)

            npc_contexts.append({
                "npc_id":           npc["id"],
                "npc_name":         npc["name"],
                "tier":             npc.get("tier", "minor"),
                "gender":           npc.get("gender", ""),           # для местоимений в DM
                "description":      npc.get("description", ""),       # для вводной сцены
                "system_prompt":    npc_system_prompt,
                "inner_thought":    inner_thought,
                "behavior_hint":    behavior_hint,
                "threat_score":     threat_score,
                "threat_category":  threat_cat,
                "perceived_status": status_label,
                "permissions":      permissions,
                "action_deltas":    action_deltas,
            })

        # Сохраняем обновлённые состояния NPC
        all_npcs = _orchestrator._load_npcs()
        for updated_npc in npcs_here:
            for i, n in enumerate(all_npcs):
                if n["id"] == updated_npc["id"]:
                    all_npcs[i] = updated_npc
                    break
        _orchestrator._save_npcs(all_npcs)

        return npc_contexts

    except Exception as e:
        # Не ломаем стрим из-за ошибки Phase 3A
        import logging
        logging.getLogger(__name__).warning(f"[STREAM] NPC engines error: {e}")
        return []


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
    location = "tavern_silver_wolf"  # дефолт = slug (совпадает с location в major_npcs.json)
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

        # ── 2. ФАЗА 3A: Action Classifier + NPC Psychology движки ──────────
        # Классифицируем действие (Python, 0ms)
        act_type = classifier.classify(action_text)
        action_type_str = act_type.value

        # Сразу сообщаем клиенту тип действия — чтобы бейдж появился ДО токенов
        yield _sse({"type": "action_type", "value": action_type_str})

        # Загружаем данные персонажа
        char_data = {}
        try:
            chars = _character_service.list_characters(campaign_id)
            for ch in chars:
                if ch.name == player:
                    char_data = ch.model_dump()
                    break
        except Exception:
            pass

        # Запускаем NPC Psychology движки (Phase 3A)
        npc_contexts = _run_npc_engines(location, action_text, action_type_str, char_data)

        # has_major определяем здесь — до try/except с мета-моделями,
        # чтобы npc_importance был доступен даже если try упадёт
        has_major = any(ctx.get("tier") == "major" for ctx in npc_contexts)

        # ── SceneState (фаза S): инициализируем сцену если нет ────────────
        # SceneState — единственный источник истины об объектах в локации.
        # DM получает его первым блоком промпта через _build_scene_description().
        scene_state = {}
        try:
            scene_state = _orchestrator.scene_manager.get_scene_state(
                campaign_id, location
            )
            if scene_state is None:
                # Первый визит в локацию — создаём из шаблона
                time_of_day = "22:00"  # дефолт; TODO: брать из campaign_state.metadata
                if campaign_state:
                    tod = campaign_state.metadata.get("time_of_day", "")
                    if tod:
                        time_of_day = tod
                scene_state = _orchestrator.scene_manager.initialize_scene(
                    campaign_id, location, time_of_day
                )
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"[STREAM] SceneState error: {e}")
            scene_state = {}

        # ── recent_session: последние 2 хода для NPC continuity ────────────
        # Без этого NPC не помнят что было в прошлом ходу текущей сессии.
        recent_session = []
        try:
            recent_entries = _orchestrator.layered_memory.read_campaign_memory(
                campaign_id, limit=2
            )
            for entry in recent_entries:
                for act in entry.get("actions", []):
                    recent_session.append(
                        f"{act.get('player_name', '?')}: {act.get('action', '?')}"
                    )
                dm_text = entry.get("dm", "")
                if dm_text:
                    recent_session.append(f"[DM]: {dm_text[:120]}")
        except Exception:
            pass

        # ── ИСПРАВЛЕНИЕ: npc_contexts хранится на верхнем уровне shared_context,
        # а НЕ внутри python_engines. dm_agent итерирует python_engines.items()
        # и вызывает data.get() на каждом значении — список вместо dict → AttributeError.
        # npc_contexts читается отдельно в dm_agent и npc_agent.
        shared_context = {
            "campaign_id":    campaign_id,
            "location":       location,
            "action_type":    action_type_str,
            "player_name":    player,
            "python_engines": {},           # combat/sandbox данных нет в stream-роуте
            "npc_contexts":   npc_contexts, # Phase 3A — на верхнем уровне
            "scene_state":    scene_state,  # Фаза S — SceneState для DM
            "recent_session": recent_session,  # HF-3 — память текущей сессии для NPC
            "classification": [{
                "player": player,
                "type":   action_type_str,
            }],
        }

        # ── 3. Запускаем Rules агента (синхронно, без стриминга) ────────────
        actions = [PlayerAction(player_name=player, action=action_text)]

        try:
            rules_result = await _run_rules_agent(actions)
        except Exception:
            rules_result = {"checks": []}

        # Мета: какие модели роутер выберет для DM/NPC (для UI/дебага).
        try:
            router_llm = get_router()
            pool = get_model_pool()

            dm_key  = router_llm.select_model(Capability.NARRATIVE)
            # Если есть major NPC — используем DIALOGUE_GENERATION (npc_major модель)
            npc_cap = Capability.DIALOGUE_GENERATION if has_major else Capability.DIALOGUE
            npc_key = router_llm.select_model(npc_cap)

            dm_cfg  = pool.get_model_config(dm_key)  if pool else None
            npc_cfg = pool.get_model_config(npc_key) if pool else None

            yield _sse({
                "type": "model",
                "data": {
                    "dm": {
                        "key":      dm_key,
                        "name":     dm_cfg.name if dm_cfg else dm_key,
                        "provider": (dm_cfg.provider_type.value if dm_cfg else "unknown"),
                        "path":     (dm_cfg.path if dm_cfg else None),
                    },
                    "npc": {
                        "key":      npc_key,
                        "name":     npc_cfg.name if npc_cfg else npc_key,
                        "provider": (npc_cfg.provider_type.value if npc_cfg else "unknown"),
                        "path":     (npc_cfg.path if npc_cfg else None),
                    },
                    "active_pool_model": getattr(pool, "active_model_key", None),
                },
            })
        except Exception:
            pass

        # ── 4. NPC агент — сначала: он быстрее (120 токенов) ───────────────
        # Философия: NPC говорят SAMи → DM описывает МИР.
        # DM получает только физические действия NPC, не их речь.
        # Так игрок сначала видит что сказали NPC, потом что изменилось в мире.
        npc_importance = "major" if has_major else "mass"
        try:
            npc_result = await _run_npc_agent(
                campaign_id, location, actions, shared_context, npc_importance
            )
        except Exception:
            npc_result = {"npc_reactions": [], "npc_memory_updates": []}

        # NPC реакции отправляем СРАЗУ — до DM текста
        # Игрок видит что сказали NPC, затем DM описывает мир
        npc_reactions_early = npc_result.get("npc_reactions", [])
        if npc_reactions_early:
            yield _sse({
                "type":  "npc",
                "data":  npc_reactions_early,
                "model": npc_result.get("model"),
            })

        # ── 5. DM агент — описывает МИР, не пересказывает NPC ──────────────
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
                context=shared_context,
            ):
                token_count += 1
                yield _sse({"type": "token", "text": token, "n": token_count})

        except Exception as e:
            yield _sse({"type": "error", "text": str(e)})
            return
        # NPC реакции уже отправлены ДО текста DM (раздел 4)
        # ── 7. Финальный пакет со статистикой ──────────────────────────────
        elapsed_ms = int(time.time() * 1000 - start_ms)
        tps = round(token_count / (elapsed_ms / 1000), 1) if elapsed_ms > 0 else 0

        yield _sse({
            "type":   "done",
            "tokens": token_count,
            "ms":     elapsed_ms,
            "tps":    tps,
        })

        # ── 8. Сохраняем в память (фоново) ─────────────────────────────────
        try:
            _orchestrator.layered_memory.write_session_memory(
                campaign_id,
                {
                    "location":     location,
                    "last_actions": [{"player": player, "action": action_text}],
                    "dice_input_required": False,
                },
            )
            # Сохраняем в campaign_memory чтобы recent_session работал в следующем ходу.
            # Без этого NPC каждый ход начинают с нуля и не помнят предыдущих событий.
            _orchestrator.layered_memory.write_campaign_memory(
                campaign_id,
                {
                    "location": location,
                    "actions":  [{"player_name": player, "action": action_text}],
                    "dm":       "",  # DM текст недоступен здесь (стриминг завершён)
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


async def _run_npc_agent(
    campaign_id: str,
    location: str,
    actions: list,
    shared_context: dict,   # передаём shared_context с Phase 3A
    npc_importance: str = "mass",
) -> dict:
    """
    Запускает npc агента в thread pool.
    Передаёт shared_context с npc_contexts из Phase 3A.
    """
    import asyncio
    npc_memory = _orchestrator.layered_memory.read_npc_memory(
        campaign_id, limit=10
    )
    return await asyncio.to_thread(
        _orchestrator.npc_agent.run,
        location, actions, npc_memory, shared_context, npc_importance
    )