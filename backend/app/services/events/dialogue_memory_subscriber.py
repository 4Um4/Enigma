"""
Файл: backend/app/services/events/dialogue_memory_subscriber.py
Назначение: Слушает NPC_SPOKE и PLAYER_SPOKE и пишет EventMemory в narrative_cache.
Зависимости: app.services.memory.memory_manager, app.services.npc.npc_loader
Основные сущности: DialogueMemorySubscriber
"""

import logging
from dataclasses import replace
from typing import Any

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

            _sq = self._get_spatial_query() if self._get_spatial_query else None  # noqa: ENIGMA001

            payload = getattr(event, "payload", {}) or {}  # noqa: ENIGMA002
            # Фаза A Шаг 9.5 (вторая половина аудита №9): продюсеры кладут
            # спикера по-разному — working_memory_tick кладёт npc_id в payload
            # при source=ИМЯ; материализатор/intent_adapter — id в source.
            # Приоритет: payload.npc_id → source; финальный фолбэк — имя
            # (резолвится звеном 2 ниже). Иначе реплики NPC не становились
            # ничьей памятью (0 строк npc_spoke в живой БД).
            speaker = payload.get("npc_id") or getattr(event, "source", "")
            listener = payload.get("target_id", "player")

            affected_npcs = {speaker, listener}

            for npc_id in affected_npcs:
                if not npc_id or npc_id in ("all", "player"):
                    continue

                npc_dict = next(
                    (
                        n
                        for n in _npc_states
                        if n.get("id") == npc_id
                        or n.get("npc_id") == npc_id
                        # Шаг 9.5: name-фолбэк — событие с source=ИМЯ
                        # (RCE-цепочка) резолвится в id по списку NPC
                        or n.get("name", "") == npc_id
                    ),
                    None,
                )
                if not npc_dict:
                    continue

                from app.models.npc_state import NPCState
                from app.services.npc.npc_loader import load_l2_state_from_runtime_dict

                npc_state = load_l2_state_from_runtime_dict(npc_dict)
                # Шаг 9.6: name-фолбэк приносил ИМЯ в колонку npc_id
                # (репетиция: npc_id='Торнин') — ключ памяти замусоривался.
                # Инжектим канонический id из найденного npc_dict.
                _real_id = npc_dict.get("id") or npc_dict.get("npc_id") or npc_id
                new_payload = {**payload, "npc_id": _real_id}
                new_event = replace(event, payload=new_payload)

                self._memory.apply(
                    new_event, npc_state, campaign_id=_campaign_id, spatial_query=_sq
                )
                NPCState.to_persistence_dict(npc_state, npc_dict)

        except Exception as e:
            logger.exception(f"[DIALOGUE_MEM_SUB] Failed: {e}")
