# backend/app/services/memory/memory_manager.py
"""
R1.1 + R1.2 + R1.3 + R1.4 + R1.5 — MemoryManager полный.
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional
from app.services.memory import LayeredMemory
from app.services.memory.working_memory import WorkingMemory
from app.services.memory.importance_engine import score_event, apply_decay, DECAY_EVERY
from app.services.memory.relationship_store import RelationshipStore
from app.services.memory.contradiction_resolver import resolve_all


class MemoryManager:
    def __init__(self, layered_memory: LayeredMemory, data_dir: str = "data") -> None:
        self._layered = layered_memory
        self._working = WorkingMemory(maxlen=5)
        self._relationships = RelationshipStore(data_dir=data_dir)
        self._tick_counters: Dict[str, int] = {}

    @property
    def working_memory(self) -> WorkingMemory:
        return self._working

    def build_context_for_turn(
        self,
        campaign_id: str,
        world_id: str,
        npc_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        context = self._layered.build_context(world_id, campaign_id)
        context["working_memory"] = self._working.get(campaign_id)
        context["relationships"] = self._relationships.get_all(campaign_id)
        return context

    def record_event(
        self,
        campaign_id: str,
        event: Dict[str, Any],
    ) -> None:
        importance = score_event(event)
        event_with_score = {**event, "importance": importance}
        self._working.push(campaign_id, event_with_score)
        self._layered.write_session_memory(campaign_id, event_with_score)

    def update_relationship(
        self,
        campaign_id: str,
        source: str,
        target: str,
        delta: Dict[str, float],
    ) -> None:
        self._relationships.update(campaign_id, source, target, delta)

    def get_relationships(self, campaign_id: str) -> Dict[str, Any]:
        return self._relationships.get_all(campaign_id)

    def update_beliefs(
        self,
        beliefs: List[Dict[str, Any]],
        new_event: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        return resolve_all(beliefs, new_event)

    def run_decay_if_needed(self, campaign_id: str, current_tick: int) -> None:
        last = self._tick_counters.get(campaign_id, 0)
        if current_tick - last < DECAY_EVERY:
            return
        self._tick_counters[campaign_id] = current_tick
        working = self._working.get(campaign_id)
        if working:
            decayed = apply_decay(working)
            self._working.clear(campaign_id)
            for event in decayed:
                if not event.get("archived"):
                    self._working.push(campaign_id, event)