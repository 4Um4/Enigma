from datetime import datetime
from typing import Literal

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
)
from app.services.character_service import CharacterService
from app.services.combat_service import CombatService
from app.services.knowledge_ingest import KnowledgeIngestService
from app.services.llm_service import llm_service
from app.services.orchestrator import GameOrchestrator
from app.services.readiness import ReadinessService
from app.services.campaign_state_service import get_campaign_state_service
from app.services.player_session_service import player_session_service

router = APIRouter()
orchestrator = GameOrchestrator()
readiness_service = ReadinessService()
character_service = CharacterService()
combat_service = CombatService()
knowledge_ingest = KnowledgeIngestService(orchestrator.layered_memory)
campaign_service = get_campaign_state_service()

# Время старта приложения
import time
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


@router.get("/health")
def health() -> dict:
    """
    Health check endpoint.
    Возвращает статус всех сервисов системы.
    """
    # Проверяем LLM (с использованием кэша)
    llm_status = llm_service.check_health(use_cache=True)
    
    # Получаем количество активных игроков
    active_campaigns = list(player_session_service._sessions.keys())
    total_players = sum(
        1 for camp_id in active_campaigns 
        if player_session_service.is_player_active(camp_id)
    )
    
    return {
        "status": "ok",
        "service": "local-ai-dm",
        "llm": llm_status.get("status", "unknown"),
        "llm_model": llm_status.get("model", None),
        "players": total_players,
        "sessions": len(active_campaigns)
    }


@router.get("/system/status")
def system_status() -> dict:
    """
    System status endpoint для отладки.
    Возвращает детальную информацию о состоянии системы.
    """
    import time
    
    # LLM статус
    llm_status = llm_service.check_health(use_cache=False)  # Fresh check
    
    # Сессии в памяти
    memory_sessions = len(player_session_service._sessions)
    
    # Сессии на диске
    disk_sessions = 0
    import os
    sessions_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "sessions")
    if os.path.exists(sessions_dir):
        disk_sessions = len([f for f in os.listdir(sessions_dir) if f.endswith(".json")])
    
    # Uptime
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
    report = orchestrator.system_requirements.check()
    return {"meets": report.meets, **report.details}


@router.get("/status/readiness", response_model=ReadinessReport)
def readiness_status() -> ReadinessReport:
    return readiness_service.report()


@router.post("/campaign/load", response_model=CampaignLoadResponse)
def load_campaign(request: CampaignLoadRequest) -> CampaignLoadResponse:
    return orchestrator.load_campaign(request.campaign_id, request.world_id)


@router.post("/world/tick/{world_id}", response_model=WorldTickResponse)
def force_world_tick(world_id: str) -> WorldTickResponse:
    tick = orchestrator.trigger_world_tick(world_id)
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
def game_turn(request: ChatTurnRequest) -> ChatTurnResponse:
    # Проверяем, что игрок активен перед обработкой хода
    if request.actions:
        player_name = request.actions[0].player_name
        if not player_session_service.is_player_active(request.campaign_id, player_name):
            print(f"[TURN_REJECTED_NO_PLAYER] Campaign: {request.campaign_id}, Player: {player_name}")
            raise HTTPException(
                status_code=412,
                detail=f"Игрок '{player_name}' не активен. Пожалуйста, выберите персонажа."
            )
    
    try:
        return orchestrator.run_turn(request)
    except RuntimeError as exc:
        raise HTTPException(status_code=412, detail=str(exc)) from exc


@router.post("/game/action")
def game_action(request: dict) -> dict:
    """
    Упрощённый endpoint для отправки хода.
    Принимает: {player: "name", campaign: "id", action: "текст действия"}
    Возвращает: {response: "ответ DM", ...}
    """
    # Логирование входящего запроса
    print(f"[GAME_ACTION_RAW_REQUEST] {request}")
    
    player = request.get("player")
    campaign_id = request.get("campaign")
    action_text = request.get("action")
    
    print(f"[GAME_ACTION_PARSED] player={player}, campaign={campaign_id}, action={action_text}")
    
    if not player:
        raise HTTPException(status_code=400, detail="Поле 'player' обязательно")
    if not campaign_id:
        raise HTTPException(status_code=400, detail="Поле 'campaign' обязательно")
    if not action_text:
        raise HTTPException(status_code=400, detail="Поле 'action' обязательно")
    
    # Проверяем, что игрок активен - с детальным логированием
    session = player_session_service.get_session(campaign_id)
    if session is None:
        print(f"[GAME_ACTION_412] Сессия не найдена: campaign={campaign_id}, player={player}")
        raise HTTPException(
            status_code=412,
            detail=f"Сессия не найдена для кампании '{campaign_id}'. Пожалуйста, выберите персонажа."
        )
    
    if not player_session_service.is_player_active(campaign_id, player):
        # Детальное логирование причины
        elapsed = (datetime.now() - session.last_heartbeat).total_seconds()
        print(f"[GAME_ACTION_412] Сессия неактивна: campaign={campaign_id}, player={player}, "
              f"active={session.active}, elapsed={elapsed:.1f}s, ttl={player_session_service.ttl_seconds}s")
        
        # Fallback: форсируем активацию на первый action (устраняет race condition)
        session.active = True
        session.last_heartbeat = datetime.now()
        print(f"[GAME_ACTION_FORCE_ACTIVE] Campaign: {campaign_id}, Player: {player}")
        
        # Проверяем снова после активации
        if not player_session_service.is_player_active(campaign_id, player):
            raise HTTPException(
                status_code=412,
                detail=f"Игрок '{player}' не активен в кампании '{campaign_id}'. Пожалуйста, выберите персонажа."
            )
    
    # Получаем текущую модель LLM через LlmManager
    print(f"[GAME_ACTION_MODEL] Getting model for agent 'dm'...")
    model_selection = orchestrator.llm_manager.get_default_model_for_agent("dm")
    print(f"[GAME_ACTION_MODEL] Selected model: {model_selection.model_name}, provider: {model_selection.provider}")
    
    player_action = PlayerAction(
        player_name=player,
        action=action_text
    )
    
    # Получаем текущую локацию
    from app.services.campaign_state_service import get_campaign_state_service
    campaign_service = get_campaign_state_service()
    campaign_state = campaign_service.get_campaign_state(campaign_id)
    location = campaign_state.metadata.get("current_location", "unknown") if campaign_state else "unknown"
    
    print(f"[GAME_ACTION_ORCHESTRATOR] Calling run_turn with location={location}")
    
    turn_request = ChatTurnRequest(
        world_id=campaign_id,
        campaign_id=campaign_id,
        location=location,
        model=model_selection,
        actions=[player_action]
    )
    
    try:
        print(f"[GAME_ACTION_RUN_TURN] Executing orchestrator.run_turn...")
        result = orchestrator.run_turn(turn_request)
        
        # Логирование ответа
        response_preview = result.dm_response[:200] if result.dm_response else "EMPTY"
        print(f"[GAME_ACTION_RESPONSE] preview: {response_preview}...")
        
        print(f"[GAME_ACTION_COMPLETE] player={player}, campaign={campaign_id}")
        
        return {
            "response": result.dm_response,
            "npc_reactions": result.npc_reactions,
            "world_changes": result.world_changes,
            "journal_entry_id": result.journal_entry_id
        }
    except RuntimeError as exc:
        print(f"[GAME_ACTION_ERROR] {str(exc)}")
        raise HTTPException(status_code=412, detail=str(exc))


@router.get("/session/state/{campaign_id}", response_model=SessionInterfaceState)
def session_state(campaign_id: str) -> SessionInterfaceState:
    state = orchestrator.session_state(campaign_id)
    state.players = [char.name for char in character_service.list_characters(campaign_id)]
    return state


@router.post("/import/world")
async def import_world(file: UploadFile) -> dict:
    content = (await file.read()).decode("utf-8", errors="ignore")
    entry_id = orchestrator.import_world_text(file.filename or "world.txt", content)
    return {"import_id": entry_id, "filename": file.filename}


# === Новые endpoints для интерфейса ===

@router.get("/interface/campaign/{campaign_id}")
def get_campaign_info(campaign_id: str) -> dict:
    """Получить информацию о кампании для интерфейса."""
    summary = campaign_service.get_summary(campaign_id)
    return {
        "campaign_id": campaign_id,
        "campaign_name": summary.get("campaign_name", "Без названия"),
        "players_count": summary.get("players_count", 0),
        "facts_count": summary.get("facts_count", 0),
        "sessions_count": summary.get("sessions_count", 0)
    }


@router.get("/interface/players/{campaign_id}")
def get_interface_players(campaign_id: str) -> list[dict]:
    """Получить игроков с HP и эффектами для интерфейса."""
    characters = character_service.list_characters(campaign_id)
    players_data = []
    for char in characters:
        players_data.append({
            "name": char.name,
            "race": char.race or "Человек",
            "class": char.class_name or "Воин",
            "level": char.level,
            "hp": char.hp,
            "maxHp": char.max_hp,
            "ac": char.ac,
            "effects": char.effects
        })
    return players_data


@router.post("/interface/players/{campaign_id}")
def add_interface_player(campaign_id: str, request: dict) -> dict:
    """Добавить игрока через интерфейс."""
    from app.models.schemas import CharacterSheet
    
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
    return {
        "status": "ok",
        "player": {
            "name": stored.name,
            "race": stored.race,
            "class": stored.class_name,
            "level": stored.level,
            "hp": stored.hp,
            "maxHp": stored.max_hp,
            "ac": stored.ac
        }
    }


@router.get("/interface/facts/{campaign_id}")
def get_interface_facts(campaign_id: str, category: str = None) -> list[dict]:
    """Получить факты мира для интерфейса."""
    facts = campaign_service.get_world_facts(campaign_id, category=category)
    return [{"id": f.id, "text": f.text, "category": f.category, "tags": f.tags} for f in facts]


@router.post("/interface/facts/{campaign_id}")
def add_interface_fact(campaign_id: str, request: dict) -> dict:
    """Добавить факт через интерфейс."""
    text = request.get("text", "")
    category = request.get("category", "lore")
    tags = request.get("tags", [])
    
    fact = campaign_service.add_world_fact(campaign_id, text, category=category, tags=tags)
    return {"status": "ok", "fact": {"id": fact.id, "text": fact.text, "category": fact.category}}


@router.get("/interface/sessions/{campaign_id}")
def get_interface_sessions(campaign_id: str) -> list[dict]:
    """Получить сессии для интерфейса."""
    sessions = campaign_service.get_session_summaries(campaign_id)
    return [{"id": s.id, "date": s.date, "summary": s.summary, "location": s.location} for s in sessions]


# === Player Session / Heartbeat ===

@router.post("/player/heartbeat", response_model=HeartbeatResponse)
def player_heartbeat(request: HeartbeatRequest) -> HeartbeatResponse:
    """
    Обновить или создать сессию игрока (heartbeat).
    Вызывается фронтендом каждую секунду для отслеживания активности.
    """
    # Проверяем, что персонаж существует в кампании
    characters = character_service.list_characters(request.campaign_id)
    player_exists = any(char.name == request.player_name for char in characters)
    
    if not player_exists:
        raise HTTPException(
            status_code=412,
            detail=f"Персонаж '{request.player_name}' не найден в кампании '{request.campaign_id}'"
        )
    
    # Обновляем сессию
    session = player_session_service.heartbeat(request.campaign_id, request.player_name)
    
    return HeartbeatResponse(
        active=session.active,
        player_name=request.player_name,
        message="Heartbeat обновлён"
    )


@router.get("/player/active/{campaign_id}")
def get_active_players(campaign_id: str) -> list[str]:
    """Получить список активных игроков для кампании."""
    return player_session_service.get_all_active_players(campaign_id)


# === Новые API для системы выбора персонажа ===

@router.get("/player/session/{campaign_id}", response_model=PlayerSessionResponse)
def get_player_session(campaign_id: str) -> PlayerSessionResponse:
    """
    Получить текущую сессию игрока.
    Single Source of Truth - backend хранит состояние.
    """
    session = player_session_service.get_session(campaign_id)
    
    if session is None:
        return PlayerSessionResponse(
            player=None,
            active=False
        )
    
    # Проверяем, активна ли сессия (не истёк ли heartbeat)
    is_active = player_session_service.is_player_active(campaign_id)
    
    return PlayerSessionResponse(
        player=session.player_name,
        active=is_active
    )


@router.post("/player/session/{campaign_id}", response_model=PlayerSessionResponse)
def create_player_session(campaign_id: str, request: dict) -> PlayerSessionResponse:
    """
    Создать новую сессию игрока.
    Принимает {player: "name"} в теле запроса.
    """
    player_name = request.get("player")
    
    if not player_name:
        raise HTTPException(
            status_code=400,
            detail="Поле 'player' обязательно"
        )
    
    # Проверяем, что персонаж существует в кампании
    characters = character_service.list_characters(campaign_id)
    player_exists = any(char.name == player_name for char in characters)
    
    if not player_exists:
        raise HTTPException(
            status_code=404,
            detail=f"Персонаж '{player_name}' не найден в кампании '{campaign_id}'"
        )
    
    # Создаём сессию
    session = player_session_service.select_player(campaign_id, player_name)
    
    print(f"[SESSION_CREATED] Campaign: {campaign_id}, Player: {player_name}")
    
    return PlayerSessionResponse(
        player=player_name,
        active=True
    )


@router.post("/player/select", response_model=PlayerSelectResponse)
def select_player(request: PlayerSelectRequest) -> PlayerSelectResponse:
    """
    Выбрать персонажа для игры.
    Создаёт новую сессию и активирует игрока.
    """
    # Проверяем, что персонаж существует в кампании
    characters = character_service.list_characters(request.campaign_id)
    player_exists = any(char.name == request.player for char in characters)
    
    if not player_exists:
        raise HTTPException(
            status_code=404,
            detail=f"Персонаж '{request.player}' не найден в кампании '{request.campaign_id}'"
        )
    
    # Создаём сессию (атомарная операция)
    session = player_session_service.select_player(request.campaign_id, request.player)
    
    print(f"[PLAYER_SELECTED] Campaign: {request.campaign_id}, Player: {request.player}")
    
    return PlayerSelectResponse(
        status="ok",
        player=request.player
    )
