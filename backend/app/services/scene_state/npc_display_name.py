"""
Назначение: npc_id → читаемое имя (кэш config/npc + эвристика). DEGOD ITER2: перенос из scene_state_manager.py (:2376–2412). Доказанные внешние потребители (dm_agent, recognition_layer, diagnose_spatial) продолжают работать через re-export в SSM.
Зависимости: app.services.npc.npc_loader (лениво)
Основные сущности: _NPC_NAME_CACHE, _NPC_NAME_CACHE_LOADED, _load_npc_names_cache, _npc_id_to_display
"""

import json
import logging

logger = logging.getLogger(__name__)

# Кэш имён NPC загружаемых из config/npc/individuals/
_NPC_NAME_CACHE: dict[str, str] = {}
_NPC_NAME_CACHE_LOADED = False


def _load_npc_names_cache() -> None:
    """Загружает id→name из config/npc/individuals/ один раз."""
    global _NPC_NAME_CACHE_LOADED
    if _NPC_NAME_CACHE_LOADED:
        return
    try:
        from app.services.npc.npc_loader import load_npcs_merged

        npcs = load_npcs_merged()
        for npc in npcs:
            nid = npc.get("id", "")
            name = npc.get("name", "")
            if nid and name:
                _NPC_NAME_CACHE[nid] = name
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        logger.error(f"[SCENE_MGR] Ошибка загрузки кэша NPC: {e}")
    _NPC_NAME_CACHE_LOADED = True


def _npc_id_to_display(npc_id: str) -> str:
    """
    Конвертирует npc_id в отображаемое имя.
    Приоритет: config/npc → эвристика из id.
    Generic: работает для любого npc_id без хардкода конкретных персонажей.
    """
    _load_npc_names_cache()
    if npc_id in _NPC_NAME_CACHE:
        return _NPC_NAME_CACHE[npc_id]
    # Эвристика: последнее слово id с заглавной буквой
    # "tavern_keeper_tornin" → "Tornin" → "Торнин" (если кириллица) или "Tornin"
    parts = npc_id.split("_")
    return parts[-1].capitalize() if parts else npc_id
