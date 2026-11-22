# backend/app/services/npc/epistemic_store.py
"""
path: /project/backend/app/services/npc/epistemic_store.py
Назначение: Хранилище субъективных убеждений NPC.
Зависимости: app.domain.epistemology
Основные сущности: EpistemicStore
"""

import logging
from typing import Dict, List, Optional, Tuple

from app.domain.epistemology import AttributedBelief, EpistemicRecord, Proposition

logger = logging.getLogger(__name__)


class EpistemicStore:
    """
    Хранит убеждения NPC.
    Ключ: (agent_id, proposition, attribution_chain_signature).
    Полностью изолирован от RelationshipStore и L1Chronicle.
    """

    def __init__(self) -> None:
        self._records: Dict[Tuple[str, Proposition, Optional[str]], EpistemicRecord] = {}

    @staticmethod
    def _compute_chain_signature(chain: Optional[AttributedBelief]) -> Optional[str]:
        """
        Вычисляет сигнатуру цепочки атрибуции для индексации.
        Итеративный обход без рекурсии.
        """
        if chain is None:
            return None

        # Итеративный обход для извлечения всех holder_id
        holders = []
        current: Proposition | AttributedBelief = chain
        visited = set()

        while isinstance(current, AttributedBelief):
            obj_id = id(current)
            if obj_id in visited:
                raise ValueError("Structural cycle detected during signature computation")
            visited.add(obj_id)
            holders.append(current.holder_id)
            current = current.content

        # Сигнатура — это кортеж holder_id, преобразованный в строку
        return "|".join(holders)

    def _get_key(self, record: EpistemicRecord) -> Tuple[str, Proposition, Optional[str]]:
        """Вычисляет ключ для индексации записи."""
        chain_sig = self._compute_chain_signature(record.attribution_chain)
        return (record.agent_id, record.proposition, chain_sig)

    def get(self, agent_id: str, proposition: Optional[Proposition] = None,
            attribution_chain: Optional[AttributedBelief] = None) -> Optional[EpistemicRecord]:
        """
        S197: Возвращает запись об убеждении агента.

        Если proposition и attribution_chain не указаны, возвращает топ-1 по confidence.
        Если указаны, возвращает точное совпадение.
        """
        if proposition is None and attribution_chain is None:
            # Возвращаем топ-1 по confidence для данного agent_id
            records = [r for r in self._records.values() if r.agent_id == agent_id]
            return max(records, key=lambda r: r.confidence, default=None)

        if proposition is None:
            raise ValueError("proposition must be provided when attribution_chain is specified")

        # Точный поиск по ключу
        target_key = (agent_id, proposition, self._compute_chain_signature(attribution_chain))
        return self._records.get(target_key)

    def get_all_for_agent(self, agent_id: str) -> List[EpistemicRecord]:
        """Возвращает все записи для данного агента."""
        return [r for r in self._records.values() if r.agent_id == agent_id]

    def upsert(self, record: EpistemicRecord) -> None:
        """
        S296-приёмка (баг №2): upsert — точка записи без акторного фильтра.
        Ключ включает attribution_chain_signature, чтобы разные атрибуции не перезаписывали друг друга.
        """
        key = self._get_key(record)
        self._records[key] = record
        logger.debug(
            f"[EPISTEMIC_STORE] Upserted belief for {record.agent_id}: "
            f"{record.proposition} (chain={record.attribution_chain is not None}) "
            f"conf={record.confidence:.2f}"
        )

    def to_dict(self) -> list:
        """S193: Сериализует все записи в список словарей для scene_state."""
        records = []
        for record in self._records.values():
            records.append(record.to_dict())
        return records

    @classmethod
    def from_dict(cls, data: list) -> "EpistemicStore":
        """S193: Десериализует записи из scene_state с обратной совместимостью."""
        store = cls()
        if not data:
            return store

        for item in data:
            try:
                record = EpistemicRecord.from_dict(item)
                store.upsert(record)
            except Exception as e:
                logger.warning(f"[EPISTEMIC_STORE] Failed to deserialize record: {e}")
                # Обратная совместимость: пытаемся восстановить без attribution_chain
                try:
                    from app.domain.epistemology import Predicate, Proposition
                    prop_data = item.get("proposition", {})
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
                        last_updated_tick=item.get("last_updated_tick", 0),
                        source_type=item.get("source_type", ""),
                        original_source_id=item.get("original_source_id", ""),
                        seen_claim_ids=tuple(item.get("seen_claim_ids", []))
                    )
                    store.upsert(record)
                except Exception as e2:
                    logger.error(f"[EPISTEMIC_STORE] Fallback deserialization also failed: {e2}")

        return store
