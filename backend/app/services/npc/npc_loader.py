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
from typing import Any, Dict

from app.models.npc_profile import NPCProfileL0, PsycheBase

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