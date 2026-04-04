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
    # Размер скользящего окна рабочей памяти — подбирается эмпирически.
    # 20 событий достаточно для одной сцены без переполнения контекста.
    WORKING_MEMORY_SIZE: int = 20

    def __init__(self, layered_memory: LayeredMemory, data_dir: str = "data") -> None:
        self._layered = layered_memory
        self._working = WorkingMemory(maxlen=self.WORKING_MEMORY_SIZE)
        self._relationships = RelationshipStore(data_dir=data_dir)
        self._tick_counters: Dict[str, int] = {}

    @property
    def working_memory(self) -> WorkingMemory:
        return self._working

    def build_debug_snapshot(
        self,
        campaign_id: str,
        world_id: str,
        npc_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Полный снимок памяти — только для отладки и логов.
        НЕ передавать в LLM: нарушает ограничение контекста (решение №11).
        """
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

    def get_weights_for_decision(
        self,
        campaign_id: str,
        npc_id: str,
        target_id: str,
    ) -> Dict[str, float]:
        """
        Возвращает числовые веса для формулы score() в Decision Hub.
        Память не передаётся в LLM — только в Python-ядро.
        """
        rel = self._relationships.get_pair(campaign_id, npc_id, target_id)
        recent = self._working.get(campaign_id)

        # Суммируем важность последних событий с участием target_id.
        # Затухание уже применено в run_decay_if_needed.
        recent_pressure = sum(
            e.get("importance", 0.0)
            for e in recent
            if e.get("actor") == target_id or e.get("target") == target_id
        )

        return {
            "trust":           rel.get("trust", 0.0),
            "fear":            rel.get("fear", 0.0),
            "debt":            rel.get("debt", 0.0),
            "recent_pressure": min(recent_pressure, 100.0),  # кап 100
        }

    def run_decay_if_needed(self, campaign_id: str, current_tick: int) -> None:
        last = self._tick_counters.get(campaign_id, 0)
        if current_tick - last < DECAY_EVERY:
            return
        working = self._working.get(campaign_id)
        if not working:
            self._tick_counters[campaign_id] = current_tick
            return
        # Формируем новый список до записи — атомарность через замену целиком.
        # Если apply_decay упадёт — старые данные не тронуты.
        decayed = apply_decay(working)
        survived = [e for e in decayed if not e.get("archived")]
        self._working.replace_all(campaign_id, survived)
        self._tick_counters[campaign_id] = current_tick