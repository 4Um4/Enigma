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
    KnowledgeIngestResponse,
    ReadinessReport,
    SessionInterfaceState,
    WorldTickResponse,
)
from app.services.character_service import CharacterService
from app.services.combat_service import CombatService
from app.services.knowledge_ingest import KnowledgeIngestService
from app.services.orchestrator import GameOrchestrator
from app.services.readiness import ReadinessService

router = APIRouter()
orchestrator = GameOrchestrator()
readiness_service = ReadinessService()
character_service = CharacterService()
combat_service = CombatService()
knowledge_ingest = KnowledgeIngestService(orchestrator.layered_memory)


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
    return {"status": "ok", "service": "local-ai-dm"}


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
    try:
        return orchestrator.run_turn(request)
    except RuntimeError as exc:
        raise HTTPException(status_code=412, detail=str(exc)) from exc


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
