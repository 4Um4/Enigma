# backend/app/services/npc/npc_loader.py
"""
Migration Adapter (JSON -> L0 Profile).
Отвечает за извлечение Immutable-данных из грязного формата major_npcs.json.
Всё, что относится к динамике (stress, routine, memory_trace), — отбрасывается.
Назначение: Адаптер миграции. Отсекает легаси-мусор из JSON и собирает чистый NPCProfileL0.
Зависимости: app.models.npc_profile, typing
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from app.models.npc_profile import NPCProfileL0, PsycheBase
from app.services.npc.npc_state import NPCStateL2
from app.services.npc.npc_state import WillState

from app.services.npc.decision_hub import DecisionHub, EventContext

logger = logging.getLogger(__name__)


def load_profile_from_legacy_json(raw_data: Dict[str, Any]) -> NPCProfileL0:
    """
    Парсит словарь из major_npcs.json в строгий NPCProfileL0.
    
    ПРАВИЛО: Если обязательного поля нет — падаем сразу. 
    Ошибки в JSON профиля — это критический сбой кампании.
    """
    try:
        psyche_raw = raw_data.get("psyche", {})
        
        psyche_base = PsycheBase(
            willpower=int(psyche_raw.get("willpower", 50)),
            breakpoint=int(psyche_raw.get("breakpoint", 80)),
            loyalty_base=int(psyche_raw.get("loyalty_true", psyche_raw.get("loyalty_base", 50)))
        )
        
        # Извлекаем только базовые драйвы. Динамические веса (social_stats) игнорируются.
        drives_raw = raw_data.get("drives", {})
        drives_base = {
            "control": float(drives_raw.get("control", 0.0)),
            "significance": float(drives_raw.get("significance", 0.0)),
            "fear": float(drives_raw.get("fear", 0.0)),
            "desire": float(drives_raw.get("desire", 0.0)),
        }

        profile = NPCProfileL0(
            id=raw_data["id"],
            name=raw_data.get("name", "Unknown"),
            tier=raw_data.get("tier", "minor"),
            drives_base=drives_base,
            psyche_base=psyche_base,
            # voice_profile и backstory пока берем как есть, если есть.
            # В будущем они будут формироваться из отдельных файлов лора.
            voice_profile=raw_data.get("voice_profile", ""),
            backstory=raw_data.get("description", ""),
        )
        
        return profile

    except (KeyError, ValueError, TypeError) as e:
        logger.error(f"[NPC_LOADER] Failed to parse profile from JSON: {e}. Raw keys: {raw_data.keys()}")
        raise ValueError(f"Invalid NPC profile format for id={raw_data.get('id', 'UNKNOWN')}: {e}")


def load_l2_state_from_runtime_dict(raw_data: Dict[str, Any]) -> NPCStateL2:
    """
    Извлекает ДИНАМИЧЕСКОЕ состояние из runtime-словаря (SceneState / JSON).
    В отличие от L0 (который immutable), это меняется каждый тик.
    
    ВНИМАНИЕ: Это временный мост. Когда будет реализован R1.8 (Iron-Man Persistence),
    L2 будет загружаться из SQLite/Сохранения, а не из сырого JSON.
    """
    psyche = raw_data.get("psyche", {})
    ss = raw_data.get("social_stats", {})
    
    # Безопасный маппинг строк из грязного JSON в строгие Enum'ы
    will_str = psyche.get("state", "free")
    try:
        will_enum = WillState(will_str)
    except ValueError:
        will_enum = WillState.FREE

    return NPCStateL2(
        npc_id=raw_data.get("id", "unknown"),
        stress=float(psyche.get("stress", 0.0)),
        will_state=will_enum,
        
        # Система слома
        identity_integrity=float(psyche.get("identity_integrity", 1.0)),
        pressure_resistance=float(psyche.get("pressure_resistance", 0.0)),
        resentment=float(psyche.get("resentment", 0.0)),
        dependency=float(psyche.get("dependency", 0.0)),
        
        trauma_markers=set(psyche.get("trauma_flags", [])),
        relationship_cache={
            "trust": float(ss.get("trust", 0.0)),
            "fear": float(ss.get("fear_of_player", 0.0)),
            "debt": float(ss.get("debt", 0.0)),
        }
    )


def execute_npc_decision(raw_npc_dict: Dict[str, Any], event_ctx: EventContext, seed: Optional[int] = None) -> 'DecisionResult':
    """
    DM Execution Facade (Этап 5).
    Берет грязные данные NPC из сцены, приводит к чистым типам и получает решение.
    
    ВНИМАНИЕ: Эта функция не меняет состояние (StateApplicator вызывается отдельно).
    """
    # 1. Извлекаем статику и динамику в строгие контракты
    profile_l0 = load_profile_from_legacy_json(raw_npc_dict)
    state_l2 = load_l2_state_from_runtime_dict(raw_npc_dict)
    
    # 2. Вычисляем решение
    hub = DecisionHub(seed=seed)
    result = hub.compute(
        state=state_l2,
        personality=profile_l0,
        event=event_ctx
    )
    
    return result    