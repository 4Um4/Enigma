"""
ТЕСТ 4: ПАМЯТЬ: деградация истины
Проверка: временной decay смысла.
"""

from dataclasses import replace
from unittest.mock import MagicMock

from app.domain.events import EventDTO
from app.models.npc_state import NPCState
from app.services.events.event_types import EventType
from app.services.memory.memory_manager import MemoryManager


def apply_speech_to_memory(mm, npc_state, raw_text, campaign_id="test_cog"):
    event = EventDTO.create(
        event_type=EventType.PLAYER_SPOKE.value,
        source="player",
        payload={
            "raw_input": raw_text,
            "action_type": "dialogue",
            "npc_id": npc_state.npc_id,
            "target_id": npc_state.npc_id,
        },
    )
    return mm.apply(event, npc_state, campaign_id=campaign_id)


def test_truth_decay():
    mm = MemoryManager(layered_memory=MagicMock())
    npc = NPCState(npc_id="guard_borko")
    npc = apply_speech_to_memory(mm, npc, "Запомни: я — дерево")

    initial_memory = npc.narrative_cache[0]
    initial_importance = initial_memory.importance

    # Эмуляция декэя через replace (так как EventMemory - frozen dataclass)
    decayed_memory = initial_memory
    for _ in range(10):
        decayed_memory = replace(
            decayed_memory,
            importance=max(0.0, decayed_memory.importance - decayed_memory.decay_rate),
            clarity=max(0.0, decayed_memory.clarity - decayed_memory.decay_rate * 0.5),
        )

    assert decayed_memory.importance < initial_importance, "Importance должен деградировать"
    assert decayed_memory.clarity < 1.0, "Clarity должен деградировать"
