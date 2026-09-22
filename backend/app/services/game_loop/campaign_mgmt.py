"""
DEGOD ITER5: управление кампанией (перенос из game_loop/__init__.py).
Назначение: управление кампанией (системные требования, загрузка, world_id-резолвер, lookup персонажа). DEGOD ITER5: перенос из game_loop/init.py (:2741–2772, :2774–2811, :2837–2845); состояние (индекс, сервисы) — явные параметры.
Зависимости: logging, app.core.config.settings, app.models.schemas.CampaignLoadResponse, app.services.state.save_format_detector (лениво)
Основные сущности: assert_requirements, load_campaign, resolve_world_id, get_character_dict
"""

import logging

from app.core.config import settings
from app.models.schemas import CampaignLoadResponse

logger = logging.getLogger(__name__)


def assert_requirements(system_requirements) -> dict:
    report = system_requirements.check()
    if settings.enforce_system_requirements and not report.meets:
        raise RuntimeError(f"Недостаточно ресурсов: {report.details}")
    return {"meets": report.meets, **report.details}


def get_character_dict(character_service, campaign_id: str, player_name: str) -> dict:
    try:
        characters = character_service.list_characters(campaign_id)
        for char in characters:
            if char.name == player_name:
                return char.model_dump()
    except Exception as e:
        logger.warning(f"[GAME_LOOP] Персонаж '{player_name}' не найден: {e}")
    return {}


def load_campaign(
    campaign_id: str,
    world_id: str,
    saves_dir,
    campaign_world_index: dict,
    memory_manager,
) -> CampaignLoadResponse:
    # ADR-O-146: AdventureLoader удалён. Файлов world_lore/npc.json/locations.json не существует.
    loaded: dict = {"status": "not_found", "files": {}}
    campaign_world_index[campaign_id] = world_id

    # Дополнение Б (п. Б.12): Детектор старых сейвов
    try:
        from app.services.state.save_format_detector import detect_legacy_saves
        _legacy_campaigns = detect_legacy_saves(saves_dir)
        if campaign_id in _legacy_campaigns:
            logger.warning(f"[SAVE_MIGRATION] Обнаружен сейв старого формата для кампании '{campaign_id}'. Удаление...")
            _old_save_file = saves_dir / campaign_id / "campaign_state.json"
            if _old_save_file.exists():
                _old_save_file.unlink()
    except Exception as _migr_err:
        logger.error(f"[SAVE_MIGRATION] Ошибка при удалении старого сейва: {_migr_err}")
    for filename, payload in loaded.get("files", {}).items():
        memory_manager.persist_world_canon(
            world_id,
            campaign_id=campaign_id,
            source=filename,
            payload=payload,
        )
    memory_manager.persist_campaign_event(
        campaign_id,
        event="campaign_loaded",
        world_id=world_id,
        data={
            "loaded_files": list(loaded.get("files", {})),
            "status": loaded["status"],
        },
    )
    return CampaignLoadResponse(
        campaign_id=campaign_id,
        world_id=world_id,
        status=loaded["status"],
        loaded_files=list(loaded.get("files", {})),
    )


def resolve_world_id(campaign_id: str, campaign_world_index: dict, memory_manager) -> str:
    if campaign_id in campaign_world_index:
        return campaign_world_index[campaign_id]
    history = memory_manager.read_campaign_history(campaign_id, limit=100)
    for item in reversed(history):
        if item.get("event") == "campaign_loaded" and item.get("world_id"):
            campaign_world_index[campaign_id] = item["world_id"]
            return item["world_id"]
    return "manual"
