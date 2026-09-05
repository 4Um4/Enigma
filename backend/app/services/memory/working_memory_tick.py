"""
Working Memory — запись реплик NPC и decay в конце тика.

Вынесен из game_loop/__init__.py. P0.2 и P0.3 из R1 CONNECT.
Закон 5.1: все события идут через EventBus.
Закон 4.1.2: только MemoryManager пишет в память.

path: backend/app/services/memory/working_memory_tick.py
Назначение: Запись реплик NPC в Working Memory, STM и decay. Вынесено из game_loop.
Зависимости: event_bus, EventDTO, EventType, memory_manager (через параметр)
Основные сущности: write_npc_reactions_to_memory(), run_decay_and_resonance()
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from app.domain.communication import exposure_radius  # Р-В (SpeechExposure): SSOT-радиус речи
from app.domain.events import EventDTO
from app.models.temporal import TemporalContext
from app.services.events.event_bus import get_event_bus
from app.services.events.event_types import EventType

if TYPE_CHECKING:
    from app.services.memory.memory_manager import MemoryManager

logger = logging.getLogger(__name__)


def write_npc_reactions_to_memory(
    memory_manager: MemoryManager,
    npc_reactions: List[str],
    all_npcs_raw: Dict[str, Any] | list,
    campaign_id: str,
) -> None:
    """P0.2: ответы NPC → Working Memory + STM.

    Строит обратную маппинг имя → npc_id, затем для каждой реплики NPC:
    - публикует NPC_SPOKE в EventBus (persistence_level=working)
    - записывает в STM через memory_manager.add_dialogue_turn
    """
    # Обратная маппинг имя → npc_id для STM-записи
    name_to_id: Dict[str, str] = {}
    id_to_name: Dict[str, str] = {}
    if isinstance(all_npcs_raw, dict):
        for nid, ndata in all_npcs_raw.items():
            nname = ndata.get("name", "") if isinstance(ndata, dict) else ""
            if nname:
                name_to_id[nname.lower()] = nid
                id_to_name[nid] = nname
    elif isinstance(all_npcs_raw, list):
        for ndata in all_npcs_raw:
            if not isinstance(ndata, dict):
                continue
            nid = ndata.get("npc_id", "")
            nname = ndata.get("name", "")
            if nid and nname:
                name_to_id[nname.lower()] = nid
                id_to_name[nid] = nname

    for reaction in npc_reactions:
        if not isinstance(reaction, str):
            continue
        if not reaction or ":" not in reaction:
            continue

        npc_name_raw = reaction.split(":")[0].strip()
        npc_text = reaction.split(":", 1)[1].strip()[:120]
        # FT-3 FIX (S248, вердикт закрыт): пустой хвост ("Имя:" / "Имя:   ") —
        # артефакт парсинга DM-нарратива, не речь. Без гварда пустышка шла в
        # ОБА стока: NPC_SPOKE с content="" (6 хендлеров) и пустой ход в
        # STM-сессию (npc, player) — partner_id по умолчанию, источник
        # симптома «npc → player: ''» (§5d/FT-3). Пропуск, не запись.
        if not npc_text:
            continue
        matched_id = name_to_id.get(npc_name_raw.lower())

        # EventBus: NPC_SPOKE — Working Memory (Закон 5.1)
        try:
            get_event_bus().publish(
                # Р-В (SpeechExposure): радиус — SSOT-вывод из semantic;
                # 999-дефолт и хардкод запрещены (ADR-148). Импорт — шапка модуля.
                EventDTO.create(
                    event_type=EventType.NPC_SPOKE,
                    source=npc_name_raw,
                    payload={
                        "npc_id": matched_id or "",
                        "content": npc_text,
                        "action_type": "dialogue_key",
                    },
                    visibility="public",
                    radius=exposure_radius("normal"),  # Р-В: 999-дефолт запрещён (ADR-148)
                    persistence_level="working",
                )
            )
        except Exception as bus_err:
            logger.debug(f"[EVENT_BUS] npc_speech publish skipped: {bus_err}")

        # STM: записываем реплику NPC в его сессию (Закон 4.1.2)
        # Используем имя NPC как speaker — DM должен видеть "Купец Горан", не "merchant_goran"
        if matched_id:
            _speaker_name = id_to_name.get(matched_id, matched_id)
            logger.debug(
                f"[STM_WRITE] npc={matched_id} speaker={_speaker_name} text={npc_text[:60]}"
            )
            memory_manager.add_dialogue_turn(
                campaign_id=campaign_id,
                npc_id=matched_id,
                speaker=_speaker_name,
                text=npc_text,
            )


def run_decay_and_resonance(
    memory_manager: MemoryManager,
    campaign_id: str,
    temporal: TemporalContext,
    active_npc_ids: Optional[List[str]],
) -> None:
    """P0.3: decay + resonance для активных NPC.

    Decay запускается когда temporal.should_run_memory_decay == True.
    Decay → identity_weights → NPCIdentityL1 cache (РАЗРЫВ #2 закрыт).
    Resonance → identity_weights для каждого активного NPC.
    """
    if not temporal.should_run_memory_decay:
        return

    identity_weights = memory_manager.run_decay_if_needed(
        campaign_id,
        temporal.current_tick,
    )
    if identity_weights:
        for npc_id in active_npc_ids or []:
            resonance = memory_manager.detect_resonance(campaign_id, npc_id, actor_id="player")
            if not resonance:
                continue
            memory_manager.apply_identity_weights(campaign_id, npc_id, resonance)
