from datetime import datetime
from typing import Literal, List

from fastapi import APIRouter, Body, File, Form, HTTPException, UploadFile, Request

# A2-FIX: snapshot_npc_positions_to_dict удалён (canonical Dict)
from app.models.schemas import (
    CampaignLoadRequest,
    CampaignLoadResponse,
    CharacterListResponse,
    CharacterUpsertRequest,
    ChatTurnRequest,
    ChatTurnResponse,
    CombatActionRequest,
    CombatStartRequest,
    CombatStateResponse,
    HeartbeatRequest,
    HeartbeatResponse,
    KnowledgeIngestResponse,
    PlayerAction,
    PlayerSelectRequest,
    PlayerSelectResponse,
    PlayerSessionResponse,
    ReadinessReport,
    SessionInterfaceState,
    WorldTickResponse,
    CharacterSheet,
    ModelSelection,
    ModelProvider,
)
from app.services.character_service import CharacterService
from app.services.combat_service import CombatService
from app.services.llm.health import check_llm_health
from fastapi import Depends
from app.services.game_loop_accessor import get_game_loop
from app.services.readiness import ReadinessService
from app.services.campaign_state_service import get_campaign_state_service
from app.services.player_session_service import player_session_service
from app.services.llm.provider_manager import get_model_pool
from app.services.llm.router import get_router
from app.core.config import settings

import time
import os

import logging

logger = logging.getLogger(__name__)

router = APIRouter()
readiness_service = ReadinessService()
character_service = CharacterService(root=str(settings.saves_dir))
combat_service = CombatService()
# knowledge_ingest создаётся внутри функции (строка 198)
campaign_service = get_campaign_state_service()

# Время старта приложения
app_start_time = time.time()


def _combat_response(state) -> CombatStateResponse:
    return CombatStateResponse(
        campaign_id=state.campaign_id,
        combat_id=state.combat_id,
        round=state.round,
        turn_index=state.turn_index,
        order=state.order,
        participants=state.participants,
        log=state.log,
    )


@router.get("/ports")
def get_ports() -> dict:
    from data.runtime_ports import get_runtime_ports

    return get_runtime_ports()


@router.get("/health")
async def health(request: Request) -> dict:
    from app.services.llm.provider_manager import get_model_pool

    pool = get_model_pool()

    llm_status = check_llm_health(use_cache=True)
    active_campaigns = list(player_session_service._sessions.keys())
    total_players = sum(
        bool(player_session_service.is_player_active(camp_id))
        for camp_id in active_campaigns
    )
    pool_status = await pool.get_status()

    # DEBT-STARTUP-1: Статус фоновых задач старта
    startup_status = getattr(request.app.state, "startup_status", {})
    _llm_server = startup_status.get("llm_server", "unknown")
    _llm_health = startup_status.get("llm_health", "unknown")
    _llm_overall = (
        "ready" if _llm_server == "ready" and _llm_health == "ready" else _llm_server
    )

    return {
        "status": "ok",
        "service": "local-ai-dm",
        "llm": _llm_overall,
        "llm_model": llm_status.get("model", None),
        "pool": pool_status,
        "players": total_players,
        "sessions": len(active_campaigns),
        "startup": startup_status,
    }


@router.get("/system/status")
def system_status(game_loop=Depends(get_game_loop)) -> dict:
    llm_status = check_llm_health(use_cache=False)
    memory_sessions = len(player_session_service._sessions)
    sessions_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "sessions"
    )
    disk_sessions = (
        len([f for f in os.listdir(sessions_dir) if f.endswith(".json")])
        if os.path.exists(sessions_dir)
        else 0
    )
    uptime = int(time.time() - app_start_time)
    return {
        "backend": "ok",
        "llm": llm_status.get("status", "error"),
        "llm_model": llm_status.get("model", "unknown"),
        "memory_sessions": memory_sessions,
        "disk_sessions": disk_sessions,
        "uptime": uptime,
        "ports": {
            "llm": 8080,
            "backend": 8000,
        },
    }


@router.post("/api/debug/llm/restart")
async def restart_llm():
    """Перезапуск llama-server при падении. Используется лаунчером и recovery-механизмом."""
    try:
        from app.main import _restart_llama_server

        success = _restart_llama_server()
        return {"restarted": success, "url": settings.llama_cpp_server_url}
    except Exception as e:
        return {"restarted": False, "error": str(e)}


@router.get("/system/requirements")
def system_requirements(game_loop=Depends(get_game_loop)) -> dict:
    report = game_loop.system_requirements.check()
    return {"meets": report.meets, **report.details}


@router.get("/status/readiness", response_model=ReadinessReport)
def readiness_status() -> ReadinessReport:
    return readiness_service.report()


@router.post("/campaign/load", response_model=CampaignLoadResponse)
def load_campaign(
    request: CampaignLoadRequest, game_loop=Depends(get_game_loop)
) -> CampaignLoadResponse:
    return game_loop.load_campaign(request.campaign_id, request.world_id)


@router.post("/game/skip_time/{campaign_id}")
def skip_time(
    campaign_id: str, ticks: int = 10, game_loop=Depends(get_game_loop)
) -> dict:
    """
    Промотка времени (Time Skip) — вызывает TimeSkipExecutor.
    Использует Policy B (остановка на значимом событии).
    """
    try:
        return game_loop.skip_time(campaign_id, ticks)
    except Exception as e:
        import traceback

        print(f"[SKIP_TIME_BE] ERROR: {e}\n{traceback.format_exc()}")
        return {"status": "error", "error": str(e), "npc_positions": {}}


@router.post("/game/idle_tick/{campaign_id}")
def idle_tick(campaign_id: str, game_loop=Depends(get_game_loop)) -> dict:
    """
    Тик мира без действия игрока — вызывается pygame по таймеру.
    Делегирует GameLoop.idle_tick() → TickOrchestrator (10 фаз, Устав §3).
    """
    try:
        _result = game_loop.idle_tick(campaign_id)

        # npc_positions из world_snapshot через конвертер (обратная совместимость)
        _npc_pos_dict: dict = {}
        _ws = (
            _result.get("world_snapshot")
            if isinstance(_result, dict)
            else getattr(_result, "world_snapshot", None)
        )
        if _ws is not None:
            _npc_pos = (
                _ws.get("npc_positions")
                if isinstance(_ws, dict)
                else getattr(_ws, "npc_positions", None)
            )
            # A2-FIX: npc_positions уже Dict[str, NPCPositionDTO] (canonical). Адаптер удалён.
            if isinstance(_npc_pos, dict):
                _npc_pos_dict = _npc_pos
            elif isinstance(_npc_pos, list):
                # Fallback для legacy snapshots (если кто-то вернёт List)
                _npc_pos_dict = {
                    p.get("npc_id"): p
                    for p in _npc_pos
                    if isinstance(p, dict) and "npc_id" in p
                }

        _status = _result.get("status") if isinstance(_result, dict) else _result.status
        _events = (
            _result.get("significant_events")
            if isinstance(_result, dict)
            else _result.significant_events
        )

        return {
            "status": _status,
            "npc_positions": _npc_pos_dict,
            "events": _events,
            "world_snapshot": _ws,
        }
    except Exception as e:
        import traceback

        print(f"[IDLE_TICK_BE] ERROR: {e}\n{traceback.format_exc()}")
        return {"status": "error", "error": str(e), "npc_positions": {}}


@router.post("/world/tick/{world_id}", response_model=WorldTickResponse)
def force_world_tick(
    world_id: str, game_loop=Depends(get_game_loop)
) -> WorldTickResponse:
    tick = game_loop.world_scheduler.maybe_tick(world_id, force=True)
    return WorldTickResponse(world_id=world_id, **tick)


@router.post("/characters/upsert")
def upsert_character(request: CharacterUpsertRequest) -> dict:
    stored = character_service.upsert_character(request.campaign_id, request.character)
    return {"status": "ok", "character": stored.model_dump()}


@router.get("/characters/{campaign_id}", response_model=CharacterListResponse)
def list_characters(campaign_id: str) -> CharacterListResponse:
    characters = character_service.list_characters(campaign_id)
    return CharacterListResponse(campaign_id=campaign_id, characters=characters)


@router.post("/combat/start", response_model=CombatStateResponse)
def combat_start(request: CombatStartRequest) -> CombatStateResponse:
    state = combat_service.start(
        request.campaign_id,
        request.combat_id,
        [item.model_dump() for item in request.participants],
    )
    return _combat_response(state)


@router.post("/combat/attack", response_model=CombatStateResponse)
def combat_attack(request: CombatActionRequest) -> CombatStateResponse:
    state = combat_service.resolve_attack(
        request.campaign_id,
        request.combat_id,
        request.attacker,
        request.target,
        request.d20_roll,
        request.attack_bonus,
        request.target_ac,
        request.damage,
    )
    return _combat_response(state)


@router.post(
    "/combat/next-turn/{campaign_id}/{combat_id}", response_model=CombatStateResponse
)
def combat_next_turn(campaign_id: str, combat_id: str) -> CombatStateResponse:
    state = combat_service.next_turn(campaign_id, combat_id)
    return _combat_response(state)


@router.post("/knowledge/import", response_model=KnowledgeIngestResponse)
async def import_knowledge(
    world_id: str = Form(...),
    campaign_id: str = Form(...),
    kind: Literal["world", "rules", "characters", "npc", "campaign"] = Form(...),
    file: UploadFile = File(...),
) -> KnowledgeIngestResponse:
    raw = await file.read()
    try:
        from app.services.knowledge_ingest import KnowledgeIngestService

        _ki = KnowledgeIngestService(game_loop.memory_manager)
        result = _ki.ingest(
            world_id=world_id,
            campaign_id=campaign_id,
            kind=kind,
            filename=file.filename or "unknown.txt",
            raw=raw,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return KnowledgeIngestResponse(
        kind=result.kind,
        filename=result.filename,
        extracted_chars=result.extracted_chars,
        entry_id=result.entry_id,
        notes=result.notes,
    )


@router.post("/avatar/gender")
async def set_avatar_gender(payload: dict):
    """ADR-GENDER: Эндпоинт смены пола аватара."""
    gender = payload.get("gender", "male")
    game_loop.avatar_service.set_gender(gender)
    return {"status": "ok", "gender": gender}


@router.post("/game/turn", response_model=ChatTurnResponse)
async def game_turn(request: ChatTurnRequest) -> ChatTurnResponse:
    if request.actions:
        player_name = request.actions[0].player_name
        if not player_session_service.is_player_active(
            request.campaign_id, player_name
        ):
            raise HTTPException(
                status_code=412,
                detail=f"Игрок '{player_name}' не активен. Пожалуйста, выберите персонажа.",
            )
    try:
        return await game_loop.run_turn(request)
    except RuntimeError as exc:
        raise HTTPException(status_code=412, detail=str(exc))


@router.post("/game/action")
async def game_action(request: dict, game_loop=Depends(get_game_loop)) -> dict:
    try:
        player = request.get("player")
        campaign_id = request.get("campaign")
        action_text = request.get("action")
        is_telegraph = request.get("is_telegraph", False)

        if not player or not campaign_id or not action_text:
            raise HTTPException(
                status_code=400,
                detail="Поля 'player', 'campaign', 'action' обязательны",
            )

        # Телеграф NPC — не действие игрока, пропускаем через idle_tick
        if is_telegraph:
            # NPC телеграф обрабатывается как фоновый тик, не засоряет историю игрока
            return {
                "response": "",
                "npc_reactions": [],
                "world_changes": {},
                "journal_entry_id": None,
            }

        session = player_session_service.get_session(campaign_id)
        if session is None:
            raise HTTPException(
                status_code=412,
                detail=f"Сессия не найдена для кампании '{campaign_id}'",
            )

        if not player_session_service.is_player_active(campaign_id, player):
            session.active = True
            session.last_heartbeat = datetime.now()
            if not player_session_service.is_player_active(campaign_id, player):
                raise HTTPException(
                    status_code=412, detail=f"Игрок '{player}' не активен"
                )

        pool = get_model_pool()
        router_llm = get_router()
        dm_model_key = router_llm.get_model_for_agent("dm")
        model_provider = await pool.get_model_async(
            dm_model_key, "ROUTE", timeout_sec=30
        )
        model_selection = ModelSelection(
            provider=ModelProvider.llama_cpp,
            model_name=model_provider.key if model_provider else "fallback",
            endpoint=settings.llama_cpp_server_url,
        )

        # Позиция игрока от фронтенда — пробрасывается через DTO, сохраняется атомарно в commit_tick
        player_x = request.get("player_x", 0.0)
        player_y = request.get("player_y", 0.0)
        _player_pos: tuple[float, float] | None = None
        if player_x != 0.0 or player_y != 0.0:
            _player_pos = (player_x, player_y)

        # S82: Backend = deterministic spatial oracle.
        # Вычисляет actual_chunk из world_position НЕЗАВИСИМО от frontend prediction.
        # ИНВАРИАНТ: world_position = PRIMARY spatial input.
        # player_position = LEGACY, игнорируется для spatial logic.
        _world_x_raw = request.get("world_x")
        _world_y_raw = request.get("world_y")
        world_x: float | None = (
            float(_world_x_raw) if _world_x_raw is not None else None
        )
        world_y: float | None = (
            float(_world_y_raw) if _world_y_raw is not None else None
        )
        confirmed_location_id: str | None = None

        campaign_state = campaign_service.get_campaign_state(campaign_id)
        # A1-FIX: Убран хардкод "tavern_silver_wolf". Используем официальный API SceneStateManager.
        location = game_loop.scene_manager.find_starting_location(campaign_id)
        if campaign_state:
            if saved_location := campaign_state.metadata.get("current_location"):
                location = saved_location

        # S82: Spatial Oracle — backend ВЫЧИСЛЯЕТ actual_chunk из world_position.
        # (0,0) — валидная координата. Проверяем is not None, а не != 0.
        # Backend ВСЕГДА пересчитывает. Никогда не доверяет frontend prediction.
        if world_x is not None and world_y is not None:
            try:
                from app.services.spatial.spatial_registry import SpatialRegistry

                _registry = SpatialRegistry.get_or_load(campaign_id)
                if _registry is not None:
                    _actual_chunks = _registry.find_chunks(world_x, world_y)
                    if _actual_chunks:
                        _actual_chunk_id = _actual_chunks[0].location_id
                        if _actual_chunk_id != location:
                            logger.info(
                                f"[SPATIAL_ORACLE] location updated: "
                                f"{location} → {_actual_chunk_id} "
                                f"(world=({world_x:.1f}, {world_y:.1f}))"
                            )
                        location = _actual_chunk_id
                        confirmed_location_id = _actual_chunk_id
                        # Обновляем metadata для следующего запроса
                        # S83: Сохраняем world_position — idle_tick сможет вызвать Oracle
                        if campaign_state:
                            campaign_state.metadata["current_location"] = (
                                _actual_chunk_id
                            )
                            campaign_state.metadata["player_world_x"] = world_x
                            campaign_state.metadata["player_world_y"] = world_y
                            # A1-FIX: Atomic commit (Устав §4.2.1). Persistence parity with Direct path.
                            campaign_service.save(campaign_id)
                    else:
                        logger.warning(
                            f"[SPATIAL_ORACLE] world_position ({world_x:.1f}, {world_y:.1f}) "
                            f"outside all chunks — using saved location"
                        )
            except Exception as e:
                logger.warning(f"[SPATIAL_ORACLE] Registry lookup failed: {e}")

        turn_request = ChatTurnRequest(
            world_id=campaign_id,
            campaign_id=campaign_id,
            location=location,
            model=model_selection,
            actions=[PlayerAction(player_name=player, action=action_text)],
            player_position=_player_pos,
        )

        result = await game_loop.run_turn(turn_request)
        if result is None or not hasattr(result, "dm_response"):
            logger.error(
                "[ROUTES] game_loop.run_turn returned None or invalid object — pipeline failure"
            )
            raise HTTPException(
                status_code=500,
                detail="Game loop returned invalid response — internal pipeline failure",
            )

        # Мета о моделях (для UI/дебага). Не ломает старые клиенты.
        dm_cfg = pool.get_model_config(dm_model_key) if pool else None
        npc_model_key = router_llm.get_model_for_agent("npc")
        npc_cfg = pool.get_model_config(npc_model_key) if pool else None

        # TASK 1: Force Merge — извлекаем world_snapshot из результата тика (ADR-0014)
        _ws_dict = None
        _npc_pos_dict = None
        if hasattr(result, "world_snapshot") and result.world_snapshot is not None:
            from dataclasses import asdict, is_dataclass

            # Универсальная конвертация: Dataclass / Pydantic / Dict
            ws = result.world_snapshot
            if is_dataclass(ws):
                _ws_dict = asdict(ws)
            elif hasattr(ws, "model_dump"):  # Pydantic v2
                _ws_dict = ws.model_dump()
            elif hasattr(ws, "dict"):  # Pydantic v1
                _ws_dict = ws.dict()
            elif isinstance(ws, dict):
                _ws_dict = ws

            if _ws_dict:
                _raw_positions = _ws_dict.get("npc_positions", {})
                # A2-FIX: npc_positions уже Dict[str, NPCPositionDTO] (canonical). Адаптер удалён.
                if isinstance(_raw_positions, dict):
                    _npc_pos_dict = _raw_positions
                elif isinstance(_raw_positions, list):
                    # Fallback для legacy snapshots
                    _npc_pos_dict = {
                        p.get("npc_id", f"npc_{i}"): p
                        for i, p in enumerate(_raw_positions)
                        if isinstance(p, dict)
                    }

        if result is None:
            raise HTTPException(
                status_code=500,
                detail="Game loop returned None — internal pipeline failure",
            )

        return {
            "response": result.dm_response,
            "npc_reactions": result.npc_reactions,
            "world_changes": result.world_changes,
            "journal_entry_id": result.journal_entry_id,
            "dm_model": {
                "key": dm_model_key,
                "name": dm_cfg.name if dm_cfg else dm_model_key,
                "provider": (dm_cfg.provider_type.value if dm_cfg else "unknown"),
                "path": (dm_cfg.path if dm_cfg else None),
            },
            "npc_model": {
                "key": npc_model_key,
                "name": npc_cfg.name if npc_cfg else npc_model_key,
                "provider": (npc_cfg.provider_type.value if npc_cfg else "unknown"),
                "path": (npc_cfg.path if npc_cfg else None),
            },
            "active_pool_model": getattr(pool, "active_model_key", None),
            # TASK 1: Force Merge — передаём world_snapshot на фронтенд (ADR-0014)
            "world_snapshot": _ws_dict,
            "npc_positions": _npc_pos_dict,
            # ADR-041: Проброс конфликта воли для Resistance Medium фронтенда
            # ADR-075: Строгий контракт. result — это Pydantic ChatTurnResponse.
            "will_conflict_data": result.will_conflict_data,
            # S82: Backend подтверждает spatial truth. Frontend reconciles при расхождении.
            "confirmed_location_id": confirmed_location_id,
        }
    except HTTPException:
        raise  # пробрасываем дальше
    except Exception as e:
        import traceback

        # FIX-1: Убран локальный `from app.core.config import settings` —
        # он вызывал UnboundLocalError на строке 325 (settings.llama_cpp_server_url).
        # Глобального импорта (строка 43) достаточно.
        # FIX-2: Используем os.path вместо Path (Path не импортирован, os — да).
        try:
            _error_log_dir = os.path.join(os.path.dirname(settings.data_dir), "logs")
            os.makedirs(_error_log_dir, exist_ok=True)
            _error_path = os.path.join(_error_log_dir, "error.log")
            with open(_error_path, "w", encoding="utf-8") as f:
                f.write(traceback.format_exc())
            logger.error(f"[GAME_ACTION] error.log written to {_error_path}")
        except Exception as log_err:
            logger.error(f"[GAME_ACTION] failed to write error.log: {log_err}")

        # Полный traceback в cds_backend.log
        logger.error(f"[GAME_ACTION] {e}\n{traceback.format_exc()}")
        raise HTTPException(
            status_code=500, detail=f"Internal Server Error: {str(e)[:200]}"
        )


@router.get("/session/state/{campaign_id}", response_model=SessionInterfaceState)
def session_state(
    campaign_id: str, game_loop=Depends(get_game_loop)
) -> SessionInterfaceState:
    state = game_loop.session_state(campaign_id)
    state.players = [
        char.name for char in character_service.list_characters(campaign_id)
    ]
    return state


@router.get("/npcs/{campaign_id}")
def get_npcs(campaign_id: str, game_loop=Depends(get_game_loop)) -> dict:
    """Возвращает NPC текущей локации для NPC-панели фронтенда."""
    try:
        from app.services.npc.npc_loader import load_npcs_merged

        npcs = load_npcs_merged()

        # Определяем текущую локацию игрока
        current_location = None
        try:
            import json

            cs_path = game_loop.saves_dir / campaign_id / "campaign_state.json"
            if cs_path.exists():
                cs = json.loads(cs_path.read_text(encoding="utf-8-sig"))
                current_location = cs.get("scene_state", {}).get(
                    "location_id"
                ) or cs.get("metadata", {}).get("current_location")
        except Exception as e:
            print(f"[ROUTES] Ошибка чтения current_location: {e}")

        # Фильтруем по локации если она известна
        if current_location:
            npcs = [npc for npc in npcs if npc.get("location_id") == current_location]

        return {"npcs": npcs, "count": len(npcs)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/import/world")
async def import_world(file: UploadFile, game_loop=Depends(get_game_loop)) -> dict:
    content = (await file.read()).decode("utf-8", errors="ignore")
    entry_id = game_loop.memory_manager.persist_world_canon(
        "manual",
        campaign_id="",
        source=file.filename or "world.txt",
        payload={"content": content},
    )
    return {"import_id": entry_id, "filename": file.filename}


# === Интерфейсные endpoints ===


@router.get("/interface/campaign/{campaign_id}")
def get_campaign_info(campaign_id: str) -> dict:
    summary = campaign_service.get_summary(campaign_id)
    return {
        "campaign_id": campaign_id,
        "campaign_name": summary.get("campaign_name", "Без названия"),
        "players_count": summary.get("players_count", 0),
        "facts_count": summary.get("facts_count", 0),
        "sessions_count": summary.get("sessions_count", 0),
    }


@router.get("/interface/players/{campaign_id}")
def get_interface_players(campaign_id: str) -> List[dict]:
    characters = character_service.list_characters(campaign_id)
    return [
        {
            "name": c.name,
            "race": c.race or "Человек",
            "class": c.class_name or "Воин",
            "level": c.level,
            "hp": c.hp,
            "maxHp": c.max_hp,
            "ac": c.ac,
            "effects": c.effects,
        }
        for c in characters
    ]


@router.post("/interface/players/{campaign_id}")
def add_interface_player(campaign_id: str, request: dict) -> dict:
    char = CharacterSheet(
        name=request.get("name", "Новый персонаж"),
        race=request.get("race", ""),
        class_name=request.get("class", ""),
        level=request.get("level", 1),
        hp=request.get("hp", 10),
        max_hp=request.get("maxHp", 10),
        ac=request.get("ac", 10),
        effects=request.get("effects", []),
    )
    stored = character_service.upsert_character(campaign_id, char)
    return {"status": "ok", "player": stored.model_dump()}


@router.get("/interface/facts/{campaign_id}")
def get_interface_facts(campaign_id: str, category: str = None) -> List[dict]:
    facts = campaign_service.get_world_facts(campaign_id, category=category)
    return [
        {"id": f.id, "text": f.text, "category": f.category, "tags": f.tags}
        for f in facts
    ]


@router.post("/interface/facts/{campaign_id}")
def add_interface_fact(campaign_id: str, request: dict) -> dict:
    fact = campaign_service.add_world_fact(
        campaign_id,
        request.get("text", ""),
        category=request.get("category", "lore"),
        tags=request.get("tags", []),
    )
    return {"status": "ok", "fact": fact.model_dump()}


@router.get("/interface/sessions/{campaign_id}")
def get_interface_sessions(campaign_id: str) -> List[dict]:
    sessions = campaign_service.get_session_summaries(campaign_id)
    return [
        {"id": s.id, "date": s.date, "summary": s.summary, "location": s.location}
        for s in sessions
    ]


# === Player Session / Heartbeat ===


@router.post("/player/heartbeat", response_model=HeartbeatResponse)
def player_heartbeat(request: HeartbeatRequest) -> HeartbeatResponse:
    characters = character_service.list_characters(request.campaign_id)
    if all(c.name != request.player_name for c in characters):
        raise HTTPException(
            status_code=412, detail=f"Персонаж '{request.player_name}' не найден"
        )
    session = player_session_service.heartbeat(request.campaign_id, request.player_name)
    return HeartbeatResponse(
        active=session.active,
        player_name=request.player_name,
        message="Heartbeat обновлён",
    )


@router.get("/player/active/{campaign_id}")
def get_active_players(campaign_id: str) -> List[str]:
    return player_session_service.get_all_active_players(campaign_id)


@router.get("/player/session/{campaign_id}", response_model=PlayerSessionResponse)
def get_player_session(campaign_id: str) -> PlayerSessionResponse:
    if session := player_session_service.get_session(campaign_id):
        return PlayerSessionResponse(
            player=session.player_name,
            active=player_session_service.is_player_active(campaign_id),
        )
    else:
        return PlayerSessionResponse(player=None, active=False)


@router.post("/game/new/{campaign_id}")
def new_game(campaign_id: str, game_loop=Depends(get_game_loop)) -> dict:
    """ADR-O-146: Сброс runtime мира к чистому static. Оставляет персонажей."""
    result = game_loop.new_game(campaign_id)
    return result


@router.post("/game/{campaign_id}/scene_state")
def update_scene_state(
    campaign_id: str, scene_state: dict = Body(...), game_loop=Depends(get_game_loop)
) -> dict:
    """B1.4-FIX: receive scene_state updates from frontend (player position)."""
    game_loop.scene_manager.save_scene_state(campaign_id, scene_state)
    return {"status": "ok"}


@router.post("/player/session/{campaign_id}", response_model=PlayerSessionResponse)
def create_player_session(
    campaign_id: str, request: dict, game_loop=Depends(get_game_loop)
) -> PlayerSessionResponse:
    player_name = request.get("player")
    if not player_name:
        raise HTTPException(status_code=400, detail="Поле 'player' обязательно")
    characters = character_service.list_characters(campaign_id)
    if all(c.name != player_name for c in characters):
        raise HTTPException(
            status_code=404, detail=f"Персонаж '{player_name}' не найден"
        )
    session = player_session_service.select_player(campaign_id, player_name)
    # Сбрасываем флаг сессии — следующий ход будет session_start (сброс стресса NPC)
    game_loop.reset_session_flag(campaign_id)
    # Инициализируем сцену из editor JSON — чтобы Pygame мог рендерить до первого хода
    from app.services.game_loop.scene_init import ensure_scene_initialized

    ensure_scene_initialized(game_loop, campaign_id)
    return PlayerSessionResponse(player=player_name, active=True)


@router.post("/player/select", response_model=PlayerSelectResponse)
def select_player(request: PlayerSelectRequest) -> PlayerSelectResponse:
    characters = character_service.list_characters(request.campaign_id)
    if all(c.name != request.player for c in characters):
        raise HTTPException(
            status_code=404, detail=f"Персонаж '{request.player}' не найден"
        )
    player_session_service.select_player(request.campaign_id, request.player)
    return PlayerSelectResponse(status="ok", player=request.player)
