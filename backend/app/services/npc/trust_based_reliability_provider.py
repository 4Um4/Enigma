path: /project/backend/app/services/npc/trust_based_reliability_provider.py
Назначение: Адаптер SourceReliabilityProvider, читающий trust из RelationshipStore.
            Реализует EPISTEMIC-002: reliability источника = функция от доверия к нему.
Зависимости: RelationshipStore (readonly), SourceReliabilityProvider (protocol)
Основные сущности: TrustBasedReliabilityProvider
"""
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

# Порог врага: если trust < -30, утверждения NPC вызывают обратный эффект
# (игрок не верит, confidence падает).
_ENEMY_TRUST_THRESHOLD: float = -30.0

class TrustBasedReliabilityProvider:
    """
    EPISTEMIC-002: Надёжность источника = нормированное доверие наблюдателя к источнику.
    
    Каузальная цепь:
      RelationshipStore.get_pair(observer, source)
        → нормализация в [0, 1]
        → если ниже порога врага → инверсия (отрицательная надёжность)
        → BeliefRevisionEngine.revise() использует как множитель confidence_delta
    """
    
    def __init__(self, relationship_store, campaign_id: str) -> None:
        self._store = relationship_store
        self._campaign_id = campaign_id

    def get_reliability(
        self, observer: str, source: str, context: Optional[dict] = None
    ) -> float:
        """
        Возвращает надёжность источника в диапазоне [-1.0, 1.0].
        0.0 = нейтрально (нет данных), 1.0 = абсолютное доверие, -1.0 = абсолютное недоверие.
        """
        try:
            rel_data = self._store.get_pair(self._campaign_id, observer, source)
            trust = float(rel_data.get("trust", 0.0))
        except Exception:
            trust = 0.0
            
        # Если наблюдатель считает источник врагом — обратный эффект
        if trust < _ENEMY_TRUST_THRESHOLD:
            # Нормируем недоверие: -30 -> 0.0, -100 -> -1.0
            return -(abs(trust) - abs(_ENEMY_TRUST_THRESHOLD)) / (100.0 - abs(_ENIEY_TRUST_THRESHOLD))
            
        # Нормальное доверие: 0 -> 0.0, 100 -> 1.0
        return max(0.0, trust / 100.0)