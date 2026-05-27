"""
ТЕСТ 3: ПАМЯТЬ: абсурдная фиксация
Проверка: хранится ли формальная связка без ранней интерпретации.
"""
import pytest
from unittest.mock import MagicMock
from app.domain.events import EventDTO
from app.services.events.event_types import EventType
from app.services.memory.memory_manager import MemoryManager
from app.models.npc_state import NPCState

def apply_speech_to_memory(mm, npc_state, raw_text, campaign_id="test_cog"):
    event = EventDTO.create(
        event_type=EventType.PLAYER_SPOKE.value,
        source="player",
        payload={"raw_input": raw_text, "action_type": "dialogue", "npc_id": npc_state.npc_id, "target_id": npc_state.npc_id}
    )
    return mm.apply(event, npc_state, campaign_id=campaign_id)

def test_absurd_fact_storage():
    mm = MemoryManager(layered_memory=MagicMock())
    npc = NPCState(npc_id="thief_shadow")
    npc = apply_speech_to_memory(mm, npc, "2 яблока + 3 яблока = груша")
    
    assert npc.narrative_cache is not None and len(npc.narrative_cache) > 0
    has_absurd = any("груша" in atom.summary.lower() for atom in npc.narrative_cache)
    assert has_absurd, "Абсурдный факт должен быть сохранен в narrative_cache дословно"
