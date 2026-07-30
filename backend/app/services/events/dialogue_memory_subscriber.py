"""
Файл: backend/app/services/events/dialogue_memory_subscriber.py
Назначение: Слушает NPC_SPOKE и PLAYER_SPOKE и пишет EventMemory в narrative_cache.
Зависимости: app.services.memory.memory_manager, app.services.npc.npc_loader
Основные сущности: DialogueMemorySubscriber
"""

import logging
from typing import Any
from dataclasses import replace

logger = logging.getLogger(__name__)


class DialogueMemorySubscriber:
    """Слушает диалоговые события и фиксирует их в L2 (narrative_cache)."""

    def __init__(
        self,
        memory_manager: Any,
        npc_states_provider: Any,
        campaign_id_provider: Any,
        spatial_query_provider: Any = None,
    ) -> None:
        self._memory = memory_manager
        self._get_npc_states = npc_states_provider
        self._get_campaign_id = campaign_id_provider
        self._get_spatial_query = spatial_query_provider

    def on_event(self, event: Any) -> None:
        try:
            _campaign_id = self._get_campaign_id()
            _npc_states = self._get_npc_states()
            if not _npc_states:
                return

            _sq = self._get_spatial_query() if self._get_spatial_query else None

            speaker = getattr(event, "source", "")
            payload = getattr(event, "payload", {}) or {}
            listener = payload.get("target_id", "player")

            affected_npcs = {speaker, listener}

            for npc_id in affected_npcs:
                if not npc_id or npc_id in ("all", "player"):
                    continue

                npc_dict = next(
                    (n for n in _npc_states if n.get("id") == npc_id or n.get("npc_id") == npc_id),
                    None,
                )
                if not npc_dict:
                    continue

                from app.services.npc.npc_loader import load_l2_state_from_runtime_dict
                from app.models.npc_state import NPCState

                npc_state = load_l2_state_from_runtime_dict(npc_dict)
                new_payload = {**payload, "npc_id": npc_id}
                new_event = replace(event, payload=new_payload)

                self._memory.apply(
                    new_event, npc_state, campaign_id=_campaign_id, spatial_query=_sq
                )
                NPCState.write_to_legacy(npc_state, npc_dict)

        except Exception as e:
            logger.exception(f"[DIALOGUE_MEM_SUB] Failed: {e}")