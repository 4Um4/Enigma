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

# 021 Calibration candidates (behavior-identical extraction)
_CLAIM_WEIGHT: float = 1.0
_SAME_SOURCE_BOOST: float = 0.2

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
        existing_record: Optional[EpistemicRecord],
        reliability_context: Optional[dict] = None
    ) -> EpistemicRecord:
        """
        Обрабатывает ClaimEvent и возвращает новую/обновлённую EpistemicRecord.

        ADR-O-360: reliability_context позволяет источнику события указать
        тип канала (testimony / direct_observation). Провайдер — единственный
        владелец формулы reliability; движок только пробрасывает контекст.
        """
        # 1. Оценка надёжности источника (делегируется провайдеру)
        _context = {"claim": claim}
        if reliability_context:
            _context.update(reliability_context)
        reliability = self._reliability_provider.get_reliability(
            observer=listener_id,
            source=claim.speaker_id,
            context=_context
        )
        
        # Базовый вес утверждения (в будущем может зависеть от speech_act)
        incoming_confidence = reliability * _CLAIM_WEIGHT

        current_tick = claim.tick

        if existing_record is None:
            # S199.6 FIX: Восстановлено first-order убеждение (claim.proposition) вместо преждевременного Second-Order ToM (ASSERTS).
            # Second-Order ToM будет реализован позже, как отдельный слой (EPISTEMIC-005), после прохождения EPISTEMIC CORE GATE.
            new_record = EpistemicRecord(
                agent_id=listener_id,
                proposition=claim.proposition,  # First-order belief: P (e.g. "B stole X")
                # S199 (Фаза 8.3): max(0.0, ...) — защита от ухода в минус при отрицательной reliability (враги).
                confidence=max(0.0, incoming_confidence),
                source_id=claim.speaker_id,
                source_claim_id=claim.claim_id,
                first_observed_tick=current_tick,
                last_updated_tick=current_tick
            )
            logger.info(f"[BELIEF_REVISE] New belief: {listener_id} believes {claim.proposition.subject_id} {claim.proposition.predicate.value} {claim.proposition.object_id} (conf={new_record.confidence:.2f})")
        else:
            # Обновление существующего убеждения
            if existing_record.source_id == claim.speaker_id:
                # Подтверждение от того же источника (небольшой буст)
                # S199 (Фаза 8.2): max(0.0, ...) — защита от ухода в минус при отрицательной reliability (враги).
                updated_conf = max(0.0, min(1.0, existing_record.confidence + (incoming_confidence * _SAME_SOURCE_BOOST)))
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
