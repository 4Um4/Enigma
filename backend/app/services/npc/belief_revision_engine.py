# backend/app/services/npc/belief_revision_engine.py
"""
path: /project/backend/app/services/npc/belief_revision_engine.py
Назначение: Детерминированный движок ревизии убеждений.
Зависимости: app.domain.epistemology
"""

import logging
from typing import Protocol, Optional
from app.domain.epistemology import ClaimEvent, EpistemicRecord, Proposition, Predicate

logger = logging.getLogger(__name__)

class SourceReliabilityProvider(Protocol):
    """
    Интерфейс для получения надёжности источника.
    Изолирует движок убеждений от социальных систем (RelationshipStore).
    """
    def get_reliability(self, observer: str, source: str, context: Optional[dict] = None) -> float:
        ...

class BeliefRevisionEngine:
    """
    DeterministicBeliefRevisionPolicy v0.1.
    Не использует LLM. Не мутирует RelationshipStore.
    """
    def __init__(self, reliability_provider: SourceReliabilityProvider):
        self._reliability_provider = reliability_provider

    def revise(
        self,
        listener_id: str,
        claim: ClaimEvent,
        existing_record: Optional[EpistemicRecord]
    ) -> EpistemicRecord:
        """
        Обрабатывает ClaimEvent и возвращает новую/обновлённую EpistemicRecord.
        """
        # 1. Оценка надёжности источника (делегируется провайдеру)
        reliability = self._reliability_provider.get_reliability(
            observer=listener_id,
            source=claim.speaker_id,
            context={"claim": claim}
        )
        
        # Базовый вес утверждения (в будущем может зависеть от speech_act)
        claim_weight = 1.0
        incoming_confidence = reliability * claim_weight

        current_tick = claim.tick

        if existing_record is None:
            # S199: Second-Order ToM. Формируем вторичную пропозицию: A ASSERTS P.
            # Слушатель B верит, что говорящий A утверждает P.
            second_order_object = f"{claim.proposition.subject_id}_{claim.proposition.predicate.value}_{claim.proposition.object_id}"
            second_order_prop = Proposition(
                subject_id=claim.speaker_id,
                predicate=Predicate.ASSERTS,
                object_id=second_order_object,
                polarity=True
            )
            new_record = EpistemicRecord(
                agent_id=listener_id,
                proposition=second_order_prop,
                confidence=incoming_confidence,
                source_id=claim.speaker_id,
                source_claim_id=claim.claim_id,
                first_observed_tick=current_tick,
                last_updated_tick=current_tick
            )
            logger.info(f"[BELIEF_REVISE] New 2nd-order belief: {listener_id} believes {claim.speaker_id} asserts {claim.proposition.subject_id} {claim.proposition.predicate.value} (conf={new_record.confidence:.2f})")
        else:
            # Обновление существующего убеждения
            if existing_record.source_id == claim.speaker_id:
                # Подтверждение от того же источника (небольшой буст)
                # S199 (Фаза 8.2): max(0.0, ...) — защита от ухода в минус при отрицательной reliability (враги).
                updated_conf = max(0.0, min(1.0, existing_record.confidence + (incoming_confidence * 0.2)))
            else:
                # Независимое подтверждение (больший буст)
                updated_conf = max(0.0, min(1.0, existing_record.confidence + incoming_confidence))
            
            new_record = EpistemicRecord(
                agent_id=listener_id,
                proposition=claim.proposition,
                confidence=updated_conf,
                source_id=claim.speaker_id, # Обновляем источник на самый свежий
                source_claim_id=claim.claim_id,
                first_observed_tick=existing_record.first_observed_tick,
                last_updated_tick=current_tick
            )
            logger.info(f"[BELIEF_REVISE] Updated belief: {listener_id} belief updated to conf={new_record.confidence:.2f}")

        return new_record
