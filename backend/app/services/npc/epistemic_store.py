# backend/app/services/npc/epistemic_store.py
"""
path: /project/backend/app/services/npc/epistemic_store.py
Назначение: In-memory хранилище субъективных убеждений агентов (EpistemicRecord).
Зависимости: app.domain.epistemology
"""

import logging
from typing import Dict, Tuple, List, Optional
from app.domain.epistemology import EpistemicRecord, Proposition

logger = logging.getLogger(__name__)

class EpistemicStore:
    """
    Хранит убеждения NPC.
    Ключ: (agent_id, proposition).
    Полностью изолирован от RelationshipStore и L1Chronicle.
    """
    def __init__(self):
        self._records: Dict[Tuple[str, Proposition], EpistemicRecord] = {}

    def get(self, agent_id: str, proposition: Optional[Proposition] = None) -> Optional[EpistemicRecord]:
        """S197: Возвращает запись об убеждении агента. Если proposition не указан, возвращает топ-1."""
        records = [r for r in self._records.values() if r.agent_id == agent_id]
        if not records:
            return None
        if proposition:
            for r in records:
                if r.proposition == proposition:
                    return r
            return None
        return max(records, key=lambda r: r.confidence, default=None)

    def get_all_for_agent(self, agent_id: str) -> List[EpistemicRecord]:
        return [r for r in self._records.values() if r.agent_id == agent_id]

    def upsert(self, record: EpistemicRecord) -> None:
        self._records[(record.agent_id, record.proposition)] = record
        logger.debug(f"[EPISTEMIC_STORE] Upserted belief for {record.agent_id}: {record.proposition} conf={record.confidence:.2f}")

    def to_dict(self) -> list:
        """S193: Сериализует все записи в список словарей для scene_state."""
        records = []
        for record in self._records.values():
            records.append({
                "agent_id": record.agent_id,
                "proposition": {
                    "subject_id": record.proposition.subject_id,
                    "predicate": record.proposition.predicate.value,
                    "object_id": record.proposition.object_id,
                    "polarity": record.proposition.polarity
                },
                "confidence": record.confidence,
                "source_id": record.source_id,
                "source_claim_id": record.source_claim_id,
                "first_observed_tick": record.first_observed_tick,
                "last_updated_tick": record.last_updated_tick
            })
        return records

    @classmethod
    def from_dict(cls, data: list) -> "EpistemicStore":
        """S193: Десериализует записи из scene_state."""
        from app.domain.epistemology import Predicate
        store = cls()
        if not data:
            return store
        for item in data:
            prop_data = item.get("proposition", {})
            try:
                prop = Proposition(
                    subject_id=prop_data.get("subject_id"),
                    predicate=Predicate(prop_data.get("predicate")),
                    object_id=prop_data.get("object_id"),
                    polarity=prop_data.get("polarity", True)
                )
                record = EpistemicRecord(
                    agent_id=item.get("agent_id"),
                    proposition=prop,
                    confidence=item.get("confidence", 0.0),
                    source_id=item.get("source_id", ""),
                    source_claim_id=item.get("source_claim_id", ""),
                    first_observed_tick=item.get("first_observed_tick", 0),
                    last_updated_tick=item.get("last_updated_tick", 0)
                )
                store.upsert(record)
            except Exception as e:
                logger.warning(f"[EPISTEMIC_STORE] Failed to deserialize record: {e}")
        return store
