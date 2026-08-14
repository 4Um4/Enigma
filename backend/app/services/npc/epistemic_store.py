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

    def get(self, agent_id: str, proposition: Proposition) -> Optional[EpistemicRecord]:
        return self._records.get((agent_id, proposition))

    def get_all_for_agent(self, agent_id: str) -> List[EpistemicRecord]:
        return [r for r in self._records.values() if r.agent_id == agent_id]

    def upsert(self, record: EpistemicRecord) -> None:
        self._records[(record.agent_id, record.proposition)] = record
        logger.debug(f"[EPISTEMIC_STORE] Upserted belief for {record.agent_id}: {record.proposition} conf={record.confidence:.2f}")
