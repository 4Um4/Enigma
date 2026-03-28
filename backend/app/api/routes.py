from datetime import datetime
from typing import Literal, List

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

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
    PlayerInfo,
    WorldFact,
    SessionSummary,
    CharacterSheet,
    ModelSelection,
    ModelProvider
)
from app.services.character_service import CharacterService
from app.services.combat_service import CombatService
from app.services.knowledge_ingest import KnowledgeIngestService
from app.services.llm_service import llm_service
from app.services.game_loop_factory import game_loop
from app.services.readiness import ReadinessService
from app.services.campaign_state_service import get_campaign_state_service
from app.services.player_session_service import player_session_service
from app.services.llm.provider_manager import get_model_pool
from app.services.llm.router import get_router
from app.core.config import settings

import asyncio
import time
import os

router = APIRouter()
readiness_service = ReadinessService()
character_service = CharacterService()
combat_service = CombatService()
knowledge_ingest = KnowledgeIngestService(game_loop.layered_memory)
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
    from backend.data.runtime_ports import get_runtime_ports
    return get_runtime_ports()

@router.get("/health")
async def health() -> dict:
    from app.services.llm.provider_manager import get_model_pool
    pool = get_model_pool()
    
    llm_status = llm_service.check_health(use_cache=True)
    active_campaigns = list(player_session_service._sessions.keys())
    total_players = sum(
        1 for camp_id in active_campaigns 
        if player_session_service.is_player_active(camp_id)
    )
    pool_status = await pool.get_status()
    
    return {
        "status": "ok",
        "service": "local-ai-dm",
        "llm": llm_status.get("status", "unknown"),
        "llm_model": llm_status.get("model", None),
        "pool": pool_status,
        "players": total_players,
        "sessions": len(active_campaigns)
    }



@router.get("/system/status")
def system_status() -> dict:
    llm_status = llm_service.check_health(use_cache=False)
    memory_sessions = len(player_session_service._sessions)
    sessions_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "sessions")
    disk_sessions = len([f for f in os.listdir(sessions_dir) if f.endswith(".json")]) if os.path.exists(sessions_dir) else 0
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
            "frontend": 3000
        }
    }


@router.get("/system/requirements")
def system_requirements() -> dict:
    report = game_loop.system_requirements.check()
    return {"meets": report.meets, **report.details}


@router.get("/status/readiness", response_model=ReadinessReport)
def readiness_status() -> ReadinessReport:
    return readiness_service.report()


@router.post("/campaign/load", response_model=CampaignLoadResponse)
def load_campaign(request: CampaignLoadRequest) -> CampaignLoadResponse:
    return game_loop.load_campaign(request.campaign_id, request.world_id)


@router.post("/world/tick/{world_id}", response_model=WorldTickResponse)
def force_world_tick(world_id: str) -> WorldTickResponse:
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


@router.post("/combat/next-turn/{campaign_id}/{combat_id}", response_model=CombatStateResponse)
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
        result = knowledge_ingest.ingest(
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


@router.post("/game/turn", response_model=ChatTurnResponse)
async def game_turn(request: ChatTurnRequest) -> ChatTurnResponse:
    if request.actions:
        player_name = request.actions[0].player_name
        if not player_session_service.is_player_active(request.campaign_id, player_name):
            raise HTTPException(
                status_code=412,
                detail=f"Игрок '{player_name}' не активен. Пожалуйста, выберите персонажа."
            )
    try:
        return await game_loop.run_turn(request)
    except RuntimeError as exc:
        raise HTTPException(status_code=412, detail=str(exc))


@router.post("/game/action")
async def game_action(request: dict) -> dict:
    try:
        from app.services.campaign_state_service import get_campaign_state_service

        player = request.get("player")
        campaign_id = request.get("campaign")
        action_text = request.get("action")

        if not player or not campaign_id or not action_text:
            raise HTTPException(status_code=400, detail="Поля 'player', 'campaign', 'action' обязательны")

        session = player_session_service.get_session(campaign_id)
        if session is None:
            raise HTTPException(status_code=412, detail=f"Сессия не найдена для кампании '{campaign_id}'")

        if not player_session_service.is_player_active(campaign_id, player):
            session.active = True
            session.last_heartbeat = datetime.now()
            if not player_session_service.is_player_active(campaign_id, player):
                raise HTTPException(status_code=412, detail=f"Игрок '{player}' не активен")

        pool = get_model_pool()
        router_llm = get_router()
        dm_model_key = router_llm.get_model_for_agent("dm")
        model_provider = await pool.get_model_async(dm_model_key, "ROUTE", timeout_sec=30)
        model_selection = ModelSelection(
            provider=ModelProvider.llama_cpp,
            model_name=model_provider.key if model_provider else "fallback",
            endpoint=settings.llama_cpp_server_url,
        )

        campaign_state = campaign_service.get_campaign_state(campaign_id)
        location = "Таверна Серебряный Волк"  # дефолт всегда
        if campaign_state:
            saved_location = campaign_state.metadata.get("current_location")
            if saved_location:
                location = saved_location

        turn_request = ChatTurnRequest(
            world_id=campaign_id,
            campaign_id=campaign_id,
            location=location,
            model=model_selection,
            actions=[PlayerAction(player_name=player, action=action_text)]
        )

        result = await game_loop.run_turn(turn_request)

        # Мета о моделях (для UI/дебага). Не ломает старые клиенты.
        dm_cfg = pool.get_model_config(dm_model_key) if pool else None
        npc_model_key = router_llm.get_model_for_agent("npc")
        npc_cfg = pool.get_model_config(npc_model_key) if pool else None

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
        }
    except HTTPException:
        raise  # пробрасываем дальше
    except Exception as e:
        import traceback
        error_path = "C:/DDD/Codex/VSC_Enigma/Enigma/backend/error.log"
        with open(error_path, "w", encoding="utf-8") as f:
            f.write(traceback.format_exc())
        print(f"🔥 Ошибка записана в {error_path}")
        raise HTTPException(status_code=500, detail="Internal Server Error (см. error.log)")


@router.get("/session/state/{campaign_id}", response_model=SessionInterfaceState)
def session_state(campaign_id: str) -> SessionInterfaceState:
    state = game_loop.session_state(campaign_id)
    state.players = [char.name for char in character_service.list_characters(campaign_id)]

    # Фаза S + 3B: добавляем metadata и scene_state для фронтенда
    # Фронтенд читает metadata.current_location и metadata.time_of_day
    try:
        import json
        # campaign_state.json хранит metadata (location, time) и scene_state напрямую
        cs_path = game_loop.data_dir / "campaigns" / campaign_id / "campaign_state.json"
        if cs_path.exists():
            cs = json.loads(cs_path.read_text(encoding="utf-8"))
            # Берём metadata как есть
            meta = cs.get("metadata", {})
            state.layers["metadata"] = meta
            # scene_state хранится прямо в campaign_state.json
            raw_scene = cs.get("scene_state")
            if raw_scene:
                state.layers["scene_state"] = raw_scene
            elif meta.get("current_location"):
                # Fallback: запрашиваем через SceneManager
                try:
                    scene = game_loop.scene_manager.get_scene_state(
                        campaign_id, meta["current_location"]
                    )
                    if scene:
                        state.layers["scene_state"] = scene
                except Exception:
                    pass
    except Exception:
        pass

    return state


@router.get("/npcs/{campaign_id}")
def get_npcs(campaign_id: str) -> dict:
    """Возвращает major NPC для NPC-панели фронтенда."""
    try:
        npc_path = game_loop.data_dir / "npcs" / "major_npcs.json"
        if not npc_path.exists():
            return {"npcs": []}
        import json
        with open(npc_path, encoding="utf-8") as f:
            npcs = json.load(f)
        # Возвращаем все поля — фронтенд сам разберётся что показать
        return {"npcs": npcs, "count": len(npcs)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/import/world")
async def import_world(file: UploadFile) -> dict:
    content = (await file.read()).decode("utf-8", errors="ignore")
    entry_id = game_loop.layered_memory.write_world_canon(
        "manual", {"source": file.filename or "world.txt", "content": content}
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
        "sessions_count": summary.get("sessions_count", 0)
    }


@router.get("/interface/players/{campaign_id}")
def get_interface_players(campaign_id: str) -> List[dict]:
    characters = character_service.list_characters(campaign_id)
    return [{
        "name": c.name,
        "race": c.race or "Человек",
        "class": c.class_name or "Воин",
        "level": c.level,
        "hp": c.hp,
        "maxHp": c.max_hp,
        "ac": c.ac,
        "effects": c.effects
    } for c in characters]


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
        effects=request.get("effects", [])
    )
    stored = character_service.upsert_character(campaign_id, char)
    return {"status": "ok", "player": stored.model_dump()}


@router.get("/interface/facts/{campaign_id}")
def get_interface_facts(campaign_id: str, category: str = None) -> List[dict]:
    facts = campaign_service.get_world_facts(campaign_id, category=category)
    return [{"id": f.id, "text": f.text, "category": f.category, "tags": f.tags} for f in facts]


@router.post("/interface/facts/{campaign_id}")
def add_interface_fact(campaign_id: str, request: dict) -> dict:
    fact = campaign_service.add_world_fact(
        campaign_id,
        request.get("text", ""),
        category=request.get("category", "lore"),
        tags=request.get("tags", [])
    )
    return {"status": "ok", "fact": fact.model_dump()}


@router.get("/interface/sessions/{campaign_id}")
def get_interface_sessions(campaign_id: str) -> List[dict]:
    sessions = campaign_service.get_session_summaries(campaign_id)
    return [{"id": s.id, "date": s.date, "summary": s.summary, "location": s.location} for s in sessions]


# === Player Session / Heartbeat ===

@router.post("/player/heartbeat", response_model=HeartbeatResponse)
def player_heartbeat(request: HeartbeatRequest) -> HeartbeatResponse:
    characters = character_service.list_characters(request.campaign_id)
    if not any(c.name == request.player_name for c in characters):
        raise HTTPException(status_code=412, detail=f"Персонаж '{request.player_name}' не найден")
    session = player_session_service.heartbeat(request.campaign_id, request.player_name)
    return HeartbeatResponse(active=session.active, player_name=request.player_name, message="Heartbeat обновлён")


@router.get("/player/active/{campaign_id}")
def get_active_players(campaign_id: str) -> List[str]:
    return player_session_service.get_all_active_players(campaign_id)


@router.get("/player/session/{campaign_id}", response_model=PlayerSessionResponse)
def get_player_session(campaign_id: str) -> PlayerSessionResponse:
    session = player_session_service.get_session(campaign_id)
    if not session:
        return PlayerSessionResponse(player=None, active=False)
    return PlayerSessionResponse(player=session.player_name, active=player_session_service.is_player_active(campaign_id))


@router.post("/player/session/{campaign_id}", response_model=PlayerSessionResponse)
def create_player_session(campaign_id: str, request: dict) -> PlayerSessionResponse:
    player_name = request.get("player")
    if not player_name:
        raise HTTPException(status_code=400, detail="Поле 'player' обязательно")
    characters = character_service.list_characters(campaign_id)
    if not any(c.name == player_name for c in characters):
        raise HTTPException(status_code=404, detail=f"Персонаж '{player_name}' не найден")
    session = player_session_service.select_player(campaign_id, player_name)
    return PlayerSessionResponse(player=player_name, active=True)


@router.post("/player/select", response_model=PlayerSelectResponse)
def select_player(request: PlayerSelectRequest) -> PlayerSelectResponse:
    characters = character_service.list_characters(request.campaign_id)
    if not any(c.name == request.player for c in characters):
        raise HTTPException(status_code=404, detail=f"Персонаж '{request.player}' не найден")
    player_session_service.select_player(request.campaign_id, request.player)
    return PlayerSelectResponse(status="ok", player=request.player)